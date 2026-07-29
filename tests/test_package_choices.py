from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from vampip.analysis import package_id
from vampip.database import SCHEMA_VERSION, connect
from vampip.inventory import ensure_content_hashes, rows_for_root, scan
from vampip.manager_state import (
    add_pin,
    get_package_choice,
    list_package_choices,
    remove_package_choice,
    resolve_managed_set,
    set_package_choice,
)
from vampip.models import DISABLED_SUFFIX
from vampip.profiles import PackageCopyChoice, PackageCopyChoiceError, preferred, resolve
from vampip.switching import build_switch_plan, logical_relative_path


def make_var(
    path: Path,
    *,
    creator: str,
    package: str,
    dependencies: tuple[str, ...] = (),
    payload: bytes = b"payload",
) -> None:
    metadata = {
        "creatorName": creator,
        "packageName": package,
        "dependencies": {
            dependency: {"dependencies": {}} for dependency in dependencies
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps(metadata))
        archive.writestr("Custom/data.bin", payload)


class PackageCopyChoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addons = self.base / "AddonPackages"
        self.state = self.base / "state"
        self.addons.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_schema_and_choice_helpers_are_root_scoped_and_case_insensitive(
        self,
    ) -> None:
        root = str(self.addons.resolve())
        with connect(self.state) as database:
            columns = {
                row["name"]
                for row in database.execute(
                    "PRAGMA table_info(manager_package_choices)"
                )
            }
            self.assertEqual(
                columns,
                {
                    "root",
                    "package_id",
                    "selected_content_sha256",
                    "preferred_logical_path",
                    "selected_utc",
                },
            )
            version = database.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            self.assertEqual(int(version["value"]), SCHEMA_VERSION)
            self.assertGreaterEqual(SCHEMA_VERSION, 6)

            first = set_package_choice(
                database,
                root,
                "Creator.Asset.1",
                "1:first",
                preferred_logical_path="Collection/Creator.Asset.1.var",
            )
            self.assertEqual(first.selected_content_sha256, "1:first")
            self.assertEqual(
                get_package_choice(database, root, "creator.asset.1"),
                first,
            )
            self.assertEqual(
                list(list_package_choices(database, root)),
                ["creator.asset.1"],
            )

            updated = set_package_choice(
                database,
                root,
                "creator.asset.1",
                "1:second",
            )
            self.assertEqual(
                get_package_choice(database, root, "CREATOR.ASSET.1"),
                PackageCopyChoice(
                    package_id="Creator.Asset.1",
                    selected_content_sha256=updated.selected_content_sha256,
                ),
            )
            count = database.execute(
                """
                SELECT COUNT(*) AS count FROM manager_package_choices
                WHERE root = ?
                """,
                (root,),
            ).fetchone()
            self.assertEqual(count["count"], 1)
            self.assertEqual(list_package_choices(database, "another-root"), {})
            self.assertTrue(
                remove_package_choice(database, root, "CREATOR.ASSET.1")
            )
            self.assertIsNone(
                get_package_choice(database, root, "Creator.Asset.1")
            )
            self.assertFalse(
                remove_package_choice(database, root, "Creator.Asset.1")
            )

    def test_schema_five_state_is_migrated_without_special_rebuild(self) -> None:
        self.state.mkdir()
        database_path = self.state / "inventory.sqlite3"
        old = sqlite3.connect(database_path)
        old.executescript(
            """
            CREATE TABLE schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_meta(key, value)
            VALUES ('schema_version', '5');
            """
        )
        old.commit()
        old.close()

        with connect(self.state) as database:
            version = database.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            table = database.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'manager_package_choices'
                """
            ).fetchone()
            self.assertEqual(int(version["value"]), SCHEMA_VERSION)
            self.assertIsNotNone(table)

    def _make_conflicting_scene_copies(self) -> None:
        make_var(
            self.addons / "Owner.Scene.1.var",
            creator="Owner",
            package="Scene",
            dependencies=("Dep.First.1",),
            payload=b"first scene",
        )
        make_var(
            self.addons
            / "Collection"
            / f"Owner.Scene.1.var{DISABLED_SUFFIX}",
            creator="Owner",
            package="Scene",
            dependencies=("Dep.Second.1",),
            payload=b"second scene",
        )
        make_var(
            self.addons / "Dep.First.1.var",
            creator="Dep",
            package="First",
        )
        make_var(
            self.addons / "Dep.Second.1.var",
            creator="Dep",
            package="Second",
        )

    def test_choice_drives_dependency_traversal_and_physical_switch(self) -> None:
        self._make_conflicting_scene_copies()
        root = str(self.addons.resolve())
        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(ensure_content_hashes(database, rows), 4)
            rows = rows_for_root(database, self.addons)
            scene_rows = [
                row for row in rows if package_id(row) == "Owner.Scene.1"
            ]
            chosen = next(
                row for row in scene_rows if not row["enabled"]
            )
            set_package_choice(
                database,
                root,
                "Owner.Scene.1",
                chosen["content_sha256"],
                preferred_logical_path=logical_relative_path(chosen),
            )
            choices = list_package_choices(database, root)

            direct = resolve(["Owner.Scene.1"], rows, choices=choices)
            selected_ids = {package_id(row) for row in direct.selected}
            self.assertEqual(
                selected_ids,
                {"Owner.Scene.1", "Dep.Second.1"},
            )
            selected_scene = next(
                row
                for row in direct.selected
                if package_id(row) == "Owner.Scene.1"
            )
            self.assertEqual(selected_scene["path"], chosen["path"])

            add_pin(database, "Owner.Scene.1")
            desired, missing = resolve_managed_set(
                database,
                rows,
                choices=choices,
            )
            self.assertEqual(set(desired), selected_ids)
            self.assertEqual(missing, ())

            plan = build_switch_plan(
                rows,
                desired,
                disable_unselected=True,
                choices=choices,
            )
            enabled_paths = {row["path"] for row in plan.to_enable}
            disabled_paths = {row["path"] for row in plan.to_disable}
            other_scene = next(
                row for row in scene_rows if row["path"] != chosen["path"]
            )
            self.assertIn(chosen["path"], enabled_paths)
            self.assertIn(other_scene["path"], disabled_paths)

    def test_logical_path_is_only_a_hint_within_selected_content(self) -> None:
        canonical = self.addons / "Creator.Asset.1.var"
        make_var(canonical, creator="Creator", package="Asset")
        repack = self.addons / "Collection" / "Creator.Asset.1.var"
        repack.parent.mkdir()
        repack.write_bytes(canonical.read_bytes())

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            ensure_content_hashes(database, rows)
            rows = rows_for_root(database, self.addons)
            canonical_row = next(
                row for row in rows if row["relative_path"] == canonical.name
            )
            repack_row = next(
                row for row in rows if row["relative_path"] != canonical.name
            )
            self.assertEqual(
                canonical_row["content_sha256"],
                repack_row["content_sha256"],
            )
            choice = PackageCopyChoice(
                package_id="Creator.Asset.1",
                selected_content_sha256=repack_row["content_sha256"],
                preferred_logical_path=logical_relative_path(repack_row),
            )
            self.assertEqual(preferred(rows, choice)["path"], repack_row["path"])

            moved_hint = PackageCopyChoice(
                package_id="Creator.Asset.1",
                selected_content_sha256=repack_row["content_sha256"],
                preferred_logical_path="Old/Creator.Asset.1.var",
            )
            self.assertEqual(
                preferred(rows, moved_hint)["path"],
                canonical_row["path"],
            )

    def test_stale_or_unverifiable_choice_fails_closed(self) -> None:
        self._make_conflicting_scene_copies()
        with connect(self.state) as database:
            scan(self.addons, database)
            unhashed = rows_for_root(database, self.addons)
            choice = PackageCopyChoice(
                package_id="Owner.Scene.1",
                selected_content_sha256="1:not-installed",
            )
            choices = {"owner.scene.1": choice}
            with self.assertRaises(PackageCopyChoiceError) as unverified:
                resolve(["Owner.Scene.1"], unhashed, choices=choices)
            self.assertEqual(unverified.exception.reason, "unverified")

            ensure_content_hashes(database, unhashed)
            hashed = rows_for_root(database, self.addons)
            with self.assertRaises(PackageCopyChoiceError) as stale:
                resolve(["Owner.Scene.1"], hashed, choices=choices)
            self.assertEqual(stale.exception.reason, "stale")
            self.assertEqual(len(stale.exception.available_content_sha256), 2)

            with self.assertRaises(PackageCopyChoiceError):
                build_switch_plan(
                    hashed,
                    ["Owner.Scene.1"],
                    disable_unselected=True,
                    choices=choices,
                )


if __name__ == "__main__":
    unittest.main()

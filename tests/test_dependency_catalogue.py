from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import unittest
import zipfile

from vampip.database import connect
from vampip.inventory import rows_for_root, scan
from vampip.manager_state import add_pin, list_package_choices
from vampip.models import DISABLED_SUFFIX
from vampip.references import package_dependency_graph
from vampip.service import ManagerService, PackageConflictError
from vampip.web import ManagerHTTPServer

from tests.test_vampip import make_var


def insert_local_scene(
    connection: sqlite3.Connection,
    vam_root: Path,
    resource_path: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO catalog_resources (
            root, source, resource_key, creator, package_name,
            versions_json, resource_path, resource_type, atom_type,
            favorite, hidden, tags_json, imported_utc
        ) VALUES (?, 'browserassist', ?, '', '', '[]', ?, 'Scene', '',
                  0, 0, '[]', '2026-01-01T00:00:00+00:00')
        """,
        (
            str(vam_root),
            f"local-scene:{resource_path}",
            resource_path.replace("/", "\\"),
        ),
    )
    return int(cursor.lastrowid)


def make_conflicting_scene_fixture(base: Path) -> tuple[Path, Path, int]:
    vam_root = base / "VaM"
    addons = vam_root / "AddonPackages"
    state = base / "state"
    addons.mkdir(parents=True)

    make_var(
        addons / "Fork.Asset.1.var",
        creator="Fork",
        package="Asset",
        dependencies={"Branch.Left.1": {"dependencies": {}}},
        payload=b"left package contents",
    )
    second = addons / "Collection" / "Fork.Asset.1.var"
    make_var(
        second,
        creator="Fork",
        package="Asset",
        dependencies={"Branch.Right.1": {"dependencies": {}}},
        payload=b"right package contents",
    )
    second.rename(Path(f"{second}{DISABLED_SUFFIX}"))
    make_var(
        addons / "Branch.Left.1.var",
        creator="Branch",
        package="Left",
    )
    make_var(
        addons / "Branch.Right.1.var",
        creator="Branch",
        package="Right",
    )

    resource_path = "Saves/scene/Conflict.json"
    scene = vam_root / resource_path
    scene.parent.mkdir(parents=True)
    scene.write_text(
        '{"asset":"Fork.Asset.1:/Custom/data.vam"}',
        encoding="utf-8",
    )
    with connect(state) as connection:
        resource_id = insert_local_scene(
            connection,
            vam_root,
            resource_path,
        )
    return addons, state, resource_id


class PackageDependencyGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.addons = base / "AddonPackages"
        self.state = base / "state"
        self.addons.mkdir()
        make_var(
            self.addons / "Graph.A.1.var",
            creator="Graph",
            package="A",
            dependencies={"Graph.B.1": {"dependencies": {}}},
        )
        make_var(
            self.addons / "Graph.B.1.var",
            creator="Graph",
            package="B",
            dependencies={"Graph.C.1": {"dependencies": {}}},
        )
        make_var(
            self.addons / "Graph.C.1.var",
            creator="Graph",
            package="C",
            dependencies={"Graph.A.1": {"dependencies": {}}},
        )
        with connect(self.state) as connection:
            scan(self.addons, connection)
            self.rows = rows_for_root(connection, self.addons)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_graph_labels_direct_transitive_missing_and_cycles(self) -> None:
        graph = package_dependency_graph(
            ["Graph.A.1", "Absent.Root.1"],
            self.rows,
        )
        dependencies = {
            str(item["requested"]).casefold(): item
            for item in graph["dependencies"]
        }

        self.assertEqual(
            graph["counts"],
            {
                "total": 4,
                "direct": 2,
                "transitive": 2,
                "missing": 1,
                "conflicts": 0,
            },
        )
        self.assertFalse(graph["truncated"])
        self.assertEqual(graph["edge_count"], 5)
        self.assertTrue(dependencies["graph.a.1"]["direct"])
        self.assertEqual(dependencies["graph.a.1"]["state"], "active")
        self.assertEqual(
            set(dependencies["graph.a.1"]["required_by"]),
            {"<resource>", "Graph.C.1"},
        )
        self.assertFalse(dependencies["graph.b.1"]["direct"])
        self.assertEqual(
            dependencies["graph.b.1"]["required_by"],
            ["Graph.A.1"],
        )
        self.assertFalse(dependencies["graph.c.1"]["direct"])
        self.assertEqual(
            dependencies["graph.c.1"]["required_by"],
            ["Graph.B.1"],
        )
        self.assertTrue(dependencies["absent.root.1"]["direct"])
        self.assertEqual(dependencies["absent.root.1"]["state"], "missing")
        self.assertIsNone(dependencies["absent.root.1"]["resolved_id"])

    def test_graph_stops_at_node_and_edge_safety_bounds(self) -> None:
        node_limited = package_dependency_graph(
            ["Graph.A.1"],
            self.rows,
            max_nodes=2,
            max_edges=100,
        )
        self.assertTrue(node_limited["truncated"])
        self.assertEqual(len(node_limited["dependencies"]), 2)
        self.assertEqual(node_limited["edge_count"], 2)

        edge_limited = package_dependency_graph(
            ["Graph.A.1"],
            self.rows,
            max_nodes=100,
            max_edges=1,
        )
        self.assertTrue(edge_limited["truncated"])
        self.assertEqual(len(edge_limited["dependencies"]), 1)
        self.assertEqual(edge_limited["edge_count"], 1)


class DependencyConflictServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addons, self.state, self.resource_id = make_conflicting_scene_fixture(
            self.base
        )
        self.service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_details_discovers_real_conflict_and_unresolved_load_is_structured(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        self.assertEqual(details["resource"]["name"], "Conflict")
        self.assertTrue(details["resource"]["local"])
        self.assertEqual(details["roots"], ["Fork.Asset.1"])
        self.assertEqual(details["counts"]["direct"], 1)
        self.assertEqual(details["counts"]["transitive"], 2)
        self.assertEqual(details["counts"]["conflicts"], 1)
        self.assertFalse(details["truncated"])

        dependencies = {
            item["resolved_id"]: item
            for item in details["dependencies"]
            if item["resolved_id"] is not None
        }
        self.assertEqual(dependencies["Fork.Asset.1"]["state"], "conflict")
        self.assertTrue(dependencies["Fork.Asset.1"]["direct"])
        self.assertTrue(dependencies["Fork.Asset.1"]["conflict"])
        self.assertFalse(dependencies["Branch.Left.1"]["direct"])
        self.assertFalse(dependencies["Branch.Right.1"]["direct"])

        self.assertEqual(len(details["conflicts"]), 1)
        conflict = details["conflicts"][0]
        self.assertEqual(conflict["package_id"], "Fork.Asset.1")
        self.assertFalse(conflict["resolved"])
        self.assertFalse(conflict["choice_stale"])
        self.assertRegex(conflict["report_revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(conflict["copies"]), 2)
        self.assertEqual(
            {
                tuple(copy["dependencies"])
                for copy in conflict["copies"]
            },
            {("Branch.Left.1",), ("Branch.Right.1",)},
        )
        for copy in conflict["copies"]:
            self.assertRegex(copy["copy_id"], r"^[0-9a-f]{32}$")
            self.assertRegex(copy["content_sha256"], r"^1:[0-9a-f]{64}$")
            self.assertRegex(copy["content_fingerprint"], r"^[0-9a-f]{12}$")
            self.assertNotIn(str(self.base), copy["copy_id"])

        with self.assertRaises(PackageConflictError) as raised:
            self.service.lease(["Fork.Asset.1"], apply=False)
        document = raised.exception.document()
        self.assertEqual(document["code"], "package_copy_conflict")
        self.assertIn("same-ID packages contain different data", document["error"])
        self.assertEqual(document["conflicts"][0]["package_id"], "Fork.Asset.1")
        with connect(self.state) as connection:
            leases = connection.execute(
                "SELECT COUNT(*) FROM manager_leases"
            ).fetchone()[0]
        self.assertEqual(leases, 0)

    def test_packaged_resource_missing_from_preferred_fork_shows_resolver(
        self,
    ) -> None:
        active = self.addons / "Pack.Scene.1.var"
        make_var(
            active,
            creator="Pack",
            package="Scene",
            payload=b"preferred copy without the scene",
        )
        hidden = self.addons / "Collection" / "Pack.Scene.1.var"
        make_var(
            hidden,
            creator="Pack",
            package="Scene",
            payload=b"other copy",
        )
        with zipfile.ZipFile(hidden, "a") as archive:
            archive.writestr(
                "Saves/scene/Forked.json",
                '{"asset":"Branch.Right.1:/Custom/data.vam"}',
            )
        hidden.rename(Path(f"{hidden}{DISABLED_SUFFIX}"))
        self.service.scan_packages()
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', 'forked-packaged-scene',
                          'Pack', 'Scene', '["1"]',
                          'Saves\\scene\\Forked.json', 'Scene', '',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (str(self.service.vam_root),),
            )
            packaged_resource_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO catalog_resource_versions(
                    resource_id, version_text
                ) VALUES (?, '1')
                """,
                (packaged_resource_id,),
            )

        details = self.service.resource_details(packaged_resource_id)

        self.assertEqual(details["roots"], ["Pack.Scene.1"])
        self.assertEqual(details["counts"]["conflicts"], 1)
        self.assertEqual(
            details["conflicts"][0]["package_id"],
            "Pack.Scene.1",
        )
        self.assertFalse(details["conflicts"][0]["resolved"])
        conflict = details["conflicts"][0]
        containing_copy = next(
            copy for copy in conflict["copies"] if not copy["active"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            containing_copy["copy_id"],
            conflict["report_revision"],
        )
        leased = self.service.lease_resource(
            packaged_resource_id,
            apply=False,
        )
        with connect(self.state) as connection:
            context = connection.execute(
                """
                SELECT kind, resource_id, package_version, owner_package_id,
                       archive_member
                FROM manager_lease_contexts
                WHERE lease_id = ?
                """,
                (leased["lease_id"],),
            ).fetchone()
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["kind"], "resource")
        self.assertEqual(context["resource_id"], packaged_resource_id)
        self.assertEqual(context["package_version"], "1")
        self.assertEqual(context["owner_package_id"], "Pack.Scene.1")
        self.assertEqual(context["archive_member"], "Saves/scene/Forked.json")

        refreshed = self.service.resource_details(packaged_resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        missing_copy = next(
            copy for copy in refreshed_conflict["copies"] if copy["active"]
        )
        with self.assertRaisesRegex(
            ValueError,
            "active leased resource uses this package",
        ):
            self.service.choose_package_copy(
                refreshed_conflict["package_id"],
                missing_copy["copy_id"],
                refreshed_conflict["report_revision"],
            )
        with connect(self.state) as connection:
            saved = list_package_choices(
                connection,
                str(self.addons),
            )["pack.scene.1"]
        self.assertEqual(
            saved.selected_content_sha256,
            containing_copy["content_sha256"],
        )

    def test_resource_lease_blocks_owner_copy_change_until_release(self) -> None:
        member = "Saves/scene/Switchable.json"
        active = self.addons / "Pack.Switchable.1.var"
        make_var(
            active,
            creator="Pack",
            package="Switchable",
            payload=b"left scene package",
        )
        with zipfile.ZipFile(active, "a") as archive:
            archive.writestr(
                member,
                '{"asset":"Branch.Left.1:/Custom/data.vam"}',
            )
        hidden = self.addons / "Collection" / "Pack.Switchable.1.var"
        make_var(
            hidden,
            creator="Pack",
            package="Switchable",
            payload=b"right scene package",
        )
        with zipfile.ZipFile(hidden, "a") as archive:
            archive.writestr(
                member,
                '{"asset":"Branch.Right.1:/Custom/data.vam"}',
            )
        hidden.rename(Path(f"{hidden}{DISABLED_SUFFIX}"))
        self.service.scan_packages()
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', 'switchable-packaged-scene',
                          'Pack', 'Switchable', '["1"]', ?, 'Scene', '',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (str(self.service.vam_root), member.replace("/", "\\")),
            )
            packaged_resource_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO catalog_resource_versions(
                    resource_id, version_text
                ) VALUES (?, '1')
                """,
                (packaged_resource_id,),
            )

        details = self.service.resource_details(packaged_resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy for copy in conflict["copies"] if copy["active"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        leased = self.service.lease_resource(
            packaged_resource_id,
            apply=False,
        )
        refreshed = self.service.resource_details(packaged_resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy for copy in refreshed_conflict["copies"] if not copy["active"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "active leased resource uses this package",
        ):
            self.service.choose_package_copy(
                refreshed_conflict["package_id"],
                right_copy["copy_id"],
                refreshed_conflict["report_revision"],
            )
        with connect(self.state) as connection:
            packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (leased["lease_id"],),
                )
            }
        self.assertEqual(
            packages,
            {
                "Pack.Switchable.1",
                "Branch.Left.1",
            },
        )

    def test_resource_lease_blocks_dependency_copy_change_until_release(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        self.service.lease_resource(self.resource_id, apply=False)
        refreshed = self.service.resource_details(self.resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy
            for copy in refreshed_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "active leased resource uses this package",
        ):
            self.service.choose_package_copy(
                refreshed_conflict["package_id"],
                right_copy["copy_id"],
                refreshed_conflict["report_revision"],
            )

    def test_opaque_choice_validation_persists_selected_dependency_branch(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        revision = conflict["report_revision"]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "32-character opaque token",
        ):
            self.service.choose_package_copy(
                "Fork.Asset.1",
                right_copy["relative_path"],
                revision,
            )
        with self.assertRaisesRegex(
            FileExistsError,
            "package copies changed",
        ):
            self.service.choose_package_copy(
                "Fork.Asset.1",
                right_copy["copy_id"],
                "0" * 64,
            )
        with self.assertRaisesRegex(
            FileExistsError,
            "selected package copy is stale",
        ):
            self.service.choose_package_copy(
                "Fork.Asset.1",
                "f" * 32,
                revision,
            )

        selected = self.service.choose_package_copy(
            "Fork.Asset.1",
            right_copy["copy_id"],
            revision,
        )
        self.assertTrue(selected["saved"])
        self.assertEqual(selected["package_id"], "Fork.Asset.1")
        self.assertEqual(
            selected["selected_content_sha256"],
            right_copy["content_sha256"],
        )
        self.assertFalse(selected["requires_vam_close"])
        listed_hidden = self.service.list_packages(
            query="Fork.Asset.1",
            state="hidden",
        )
        listed_active = self.service.list_packages(
            query="Fork.Asset.1",
            state="active",
        )
        self.assertEqual(
            [item["id"] for item in listed_hidden["items"]],
            ["Fork.Asset.1"],
        )
        self.assertEqual(listed_active["items"], [])
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        with self.assertRaisesRegex(
            FileExistsError,
            "package copies changed",
        ):
            self.service.choose_package_copy(
                "Fork.Asset.1",
                left_copy["copy_id"],
                revision,
            )

        with connect(self.state) as connection:
            choice = list_package_choices(
                connection,
                str(self.addons),
            )["fork.asset.1"]
        self.assertEqual(
            choice.selected_content_sha256,
            right_copy["content_sha256"],
        )

        restarted = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
        )
        refreshed = restarted.resource_details(self.resource_id)
        self.assertTrue(refreshed["conflicts"][0]["resolved"])
        self.assertEqual(
            refreshed["conflicts"][0]["selected_content_sha256"],
            right_copy["content_sha256"],
        )
        resolved_ids = {
            item["resolved_id"]
            for item in refreshed["dependencies"]
            if item["resolved_id"] is not None
        }
        self.assertEqual(
            resolved_ids,
            {"Fork.Asset.1", "Branch.Right.1"},
        )

        lease = restarted.lease(["Fork.Asset.1"], apply=False)
        with connect(self.state) as connection:
            leased_packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (lease["lease_id"],),
                )
            }
        self.assertEqual(
            leased_packages,
            {"Fork.Asset.1", "Branch.Right.1"},
        )
        self.assertNotIn("Branch.Left.1", leased_packages)

    def test_stale_choice_with_one_remaining_copy_can_be_repaired(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            right_copy["copy_id"],
            conflict["report_revision"],
        )

        (self.addons / right_copy["relative_path"]).unlink()
        self.service.scan_packages()
        stale = self.service.resource_details(self.resource_id)

        self.assertEqual(stale["counts"]["conflicts"], 1)
        stale_conflict = stale["conflicts"][0]
        self.assertTrue(stale_conflict["choice_stale"])
        self.assertFalse(stale_conflict["resolved"])
        self.assertEqual(len(stale_conflict["copies"]), 1)
        with self.assertRaises(PackageConflictError) as raised:
            self.service.lease(["Fork.Asset.1"], apply=False)
        self.assertEqual(
            raised.exception.code,
            "package_copy_choice_stale",
        )
        remaining = stale_conflict["copies"][0]
        repaired = self.service.choose_package_copy(
            stale_conflict["package_id"],
            remaining["copy_id"],
            stale_conflict["report_revision"],
        )
        self.assertTrue(repaired["saved"])
        self.assertEqual(
            repaired["selected_content_sha256"],
            remaining["content_sha256"],
        )

    def test_first_lease_after_selected_hash_cache_reset_succeeds(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            right_copy["copy_id"],
            conflict["report_revision"],
        )
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE package_files SET content_sha256 = NULL
                WHERE creator = 'Fork' AND package_name = 'Asset'
                """
            )

        lease = self.service.lease(["Fork.Asset.1"], apply=False)

        self.assertRegex(str(lease["lease_id"]), r"^[0-9a-f]{32}$")
        with connect(self.state) as connection:
            packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (lease["lease_id"],),
                )
            }
        self.assertEqual(packages, {"Fork.Asset.1", "Branch.Right.1"})

    def test_first_lease_repairs_multiple_selected_hash_caches(self) -> None:
        details = self.service.resource_details(self.resource_id)
        first_conflict = details["conflicts"][0]
        first_copy = next(
            copy
            for copy in first_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        self.service.choose_package_copy(
            first_conflict["package_id"],
            first_copy["copy_id"],
            first_conflict["report_revision"],
        )

        make_var(
            self.addons / "Other.Asset.1.var",
            creator="Other",
            package="Asset",
            payload=b"first other copy",
        )
        other_hidden = self.addons / "Collection" / "Other.Asset.1.var"
        make_var(
            other_hidden,
            creator="Other",
            package="Asset",
            payload=b"second other copy",
        )
        other_hidden.rename(Path(f"{other_hidden}{DISABLED_SUFFIX}"))
        other_scene_path = "Saves/scene/OtherConflict.json"
        other_scene = self.service.vam_root / other_scene_path
        other_scene.parent.mkdir(parents=True, exist_ok=True)
        other_scene.write_text(
            '{"asset":"Other.Asset.1:/Custom/data.vam"}',
            encoding="utf-8",
        )
        self.service.scan_packages()
        with connect(self.state) as connection:
            other_resource_id = insert_local_scene(
                connection,
                self.service.vam_root,
                other_scene_path,
            )
        other_details = self.service.resource_details(other_resource_id)
        other_conflict = other_details["conflicts"][0]
        other_copy = next(
            copy for copy in other_conflict["copies"] if not copy["active"]
        )
        self.service.choose_package_copy(
            other_conflict["package_id"],
            other_copy["copy_id"],
            other_conflict["report_revision"],
        )
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE package_files SET content_sha256 = NULL
                WHERE (creator = 'Fork' AND package_name = 'Asset')
                   OR (creator = 'Other' AND package_name = 'Asset')
                """
            )

        lease = self.service.lease(
            ["Fork.Asset.1", "Other.Asset.1"],
            apply=False,
        )

        with connect(self.state) as connection:
            packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (lease["lease_id"],),
                )
            }
        self.assertEqual(
            packages,
            {"Fork.Asset.1", "Branch.Right.1", "Other.Asset.1"},
        )

    def test_first_reconcile_after_selected_hash_cache_reset_succeeds(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            right_copy["copy_id"],
            conflict["report_revision"],
        )
        self.service.pin(["Fork.Asset.1"])
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE package_files SET content_sha256 = NULL
                WHERE creator = 'Fork' AND package_name = 'Asset'
                """
            )

        plan = self.service.reconcile(apply=False, activate=True)

        self.assertEqual(plan["desired_packages"], 2)

    def test_first_details_after_single_selected_hash_reset_is_not_stale(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            right_copy["copy_id"],
            conflict["report_revision"],
        )
        (self.addons / left_copy["relative_path"]).unlink()
        self.service.scan_packages()
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE package_files SET content_sha256 = NULL
                WHERE creator = 'Fork' AND package_name = 'Asset'
                """
            )

        refreshed = self.service.resource_details(self.resource_id)

        self.assertEqual(refreshed["counts"]["conflicts"], 0)
        self.assertEqual(refreshed["conflicts"], [])
        package_entry = next(
            item
            for item in refreshed["dependencies"]
            if item["resolved_id"] == "Fork.Asset.1"
        )
        self.assertNotEqual(package_entry["state"], "choice-stale")
        self.assertFalse(package_entry["choice_stale"])

    def test_changing_choice_expands_existing_lease_dependency_snapshot(
        self,
    ) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        lease = self.service.lease(["Fork.Asset.1"], apply=False)

        refreshed = self.service.resource_details(self.resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy
            for copy in refreshed_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        changed = self.service.choose_package_copy(
            refreshed_conflict["package_id"],
            right_copy["copy_id"],
            refreshed_conflict["report_revision"],
        )

        self.assertEqual(changed["affected_leases"], 1)
        self.assertGreaterEqual(changed["added_lease_packages"], 1)
        with connect(self.state) as connection:
            leased_packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (lease["lease_id"],),
                )
            }
        self.assertEqual(
            leased_packages,
            {"Fork.Asset.1", "Branch.Left.1", "Branch.Right.1"},
        )

    def test_choice_rejects_missing_dependency_required_by_a_pin(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        self.service.pin(["Fork.Asset.1"])
        (self.addons / "Branch.Right.1.var").unlink()
        self.service.scan_packages()
        refreshed = self.service.resource_details(self.resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy
            for copy in refreshed_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "unavailable pinned dependencies: Branch.Right.1",
        ):
            self.service.choose_package_copy(
                refreshed_conflict["package_id"],
                right_copy["copy_id"],
                refreshed_conflict["report_revision"],
            )

        with connect(self.state) as connection:
            saved = list_package_choices(
                connection,
                str(self.addons),
            )["fork.asset.1"]
        self.assertEqual(
            saved.selected_content_sha256,
            left_copy["content_sha256"],
        )

    def test_unrelated_missing_pin_does_not_block_copy_choice(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )
        with connect(self.state) as connection:
            add_pin(connection, "Unrelated.Missing.1")

        selected = self.service.choose_package_copy(
            conflict["package_id"],
            right_copy["copy_id"],
            conflict["report_revision"],
        )

        self.assertTrue(selected["saved"])
        self.assertEqual(
            selected["selected_content_sha256"],
            right_copy["content_sha256"],
        )

    def test_expired_lease_does_not_block_a_new_copy_choice(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        lease = self.service.lease(["Fork.Asset.1"], apply=False)
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE manager_leases
                SET expires_utc = '2000-01-01T00:00:00+00:00'
                WHERE id = ?
                """,
                (lease["lease_id"],),
            )
        (self.addons / "Branch.Right.1.var").unlink()
        self.service.scan_packages()
        refreshed = self.service.resource_details(self.resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy
            for copy in refreshed_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        selected = self.service.choose_package_copy(
            refreshed_conflict["package_id"],
            right_copy["copy_id"],
            refreshed_conflict["report_revision"],
        )

        self.assertTrue(selected["saved"])
        self.assertEqual(selected["affected_leases"], 0)

    def test_failed_multi_lease_validation_does_not_partially_expand(self) -> None:
        details = self.service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        left_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Left.1"]
        )
        self.service.choose_package_copy(
            conflict["package_id"],
            left_copy["copy_id"],
            conflict["report_revision"],
        )
        first = self.service.lease(["Fork.Asset.1"], apply=False)
        make_var(
            self.addons / "Extra.Root.1.var",
            creator="Extra",
            package="Root",
        )
        self.service.scan_packages()
        self.service.lease(
            ["Fork.Asset.1", "Extra.Root.1"],
            apply=False,
        )
        (self.addons / "Extra.Root.1.var").unlink()
        self.service.scan_packages()
        refreshed = self.service.resource_details(self.resource_id)
        refreshed_conflict = refreshed["conflicts"][0]
        right_copy = next(
            copy
            for copy in refreshed_conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "unavailable dependencies: Extra.Root.1",
        ):
            self.service.choose_package_copy(
                refreshed_conflict["package_id"],
                right_copy["copy_id"],
                refreshed_conflict["report_revision"],
            )

        with connect(self.state) as connection:
            first_packages = {
                row["package_id"]
                for row in connection.execute(
                    """
                    SELECT package_id FROM manager_lease_packages
                    WHERE lease_id = ?
                    """,
                    (first["lease_id"],),
                )
            }
            saved = list_package_choices(
                connection,
                str(self.addons),
            )["fork.asset.1"]
        self.assertEqual(
            first_packages,
            {"Fork.Asset.1", "Branch.Left.1"},
        )
        self.assertEqual(
            saved.selected_content_sha256,
            left_copy["content_sha256"],
        )

    def test_reconcile_rechecks_selected_content_against_live_vam_state(
        self,
    ) -> None:
        running = False
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [4321] if running else [],
        )
        details = service.resource_details(self.resource_id)
        conflict = details["conflicts"][0]
        hidden_copy = next(
            copy for copy in conflict["copies"] if not copy["active"]
        )
        service.choose_package_copy(
            conflict["package_id"],
            hidden_copy["copy_id"],
            conflict["report_revision"],
        )
        service.pin(["Fork.Asset.1"])

        running = True
        with self.assertRaises(PackageConflictError) as raised:
            service.reconcile(apply=True, activate=True)
        self.assertEqual(
            raised.exception.code,
            "package_copy_switch_requires_vam_close",
        )
        self.assertTrue((self.addons / "Fork.Asset.1.var").is_file())
        self.assertTrue(
            (
                self.addons
                / "Collection"
                / f"Fork.Asset.1.var{DISABLED_SUFFIX}"
            ).is_file()
        )


class DependencyCatalogueWebTests(unittest.TestCase):
    """Loopback integration coverage; requires permission to open a test socket."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.addons, self.state, self.resource_id = make_conflicting_scene_fixture(
            base
        )
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
        )
        self.token = "dependency-catalogue-test-token"
        self.server = ManagerHTTPServer(
            ("127.0.0.1", 0),
            service,
            self.token,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=10,
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request_json(
        self,
        method: str,
        path: str,
        document: dict[str, object] | None = None,
        *,
        authorized: bool = True,
    ) -> tuple[int, dict[str, object]]:
        payload = (
            json.dumps(document).encode("utf-8")
            if document is not None
            else None
        )
        headers: dict[str, str] = {}
        if authorized:
            headers["X-VAMPIP-Token"] = self.token
        if payload is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(payload))
        self.connection.request(
            method,
            path,
            body=payload,
            headers=headers,
        )
        response = self.connection.getresponse()
        status = response.status
        body = json.loads(response.read().decode("utf-8"))
        return status, body

    def test_authenticated_details_choice_and_structured_conflict_routes(
        self,
    ) -> None:
        status, unauthorized = self.request_json(
            "GET",
            f"/api/resources/{self.resource_id}/details",
            authorized=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized["error"], "invalid manager token")

        status, details = self.request_json(
            "GET",
            f"/api/resources/{self.resource_id}/details",
        )
        self.assertEqual(status, 200)
        conflict = details["conflicts"][0]
        right_copy = next(
            copy
            for copy in conflict["copies"]
            if copy["dependencies"] == ["Branch.Right.1"]
        )

        status, blocked = self.request_json(
            "POST",
            "/api/leases",
            {"roots": ["Fork.Asset.1"], "apply": False},
        )
        self.assertEqual(status, 409)
        self.assertEqual(blocked["code"], "package_copy_conflict")
        self.assertEqual(blocked["conflicts"][0]["package_id"], "Fork.Asset.1")

        status, chosen = self.request_json(
            "POST",
            "/api/package-copy-choice",
            {
                "package_id": "Fork.Asset.1",
                "copy_id": right_copy["copy_id"],
                "report_revision": conflict["report_revision"],
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(chosen["saved"])
        self.assertEqual(
            chosen["selected_content_sha256"],
            right_copy["content_sha256"],
        )

        status, lease = self.request_json(
            "POST",
            "/api/leases",
            {"roots": ["Fork.Asset.1"], "apply": False},
        )
        self.assertEqual(status, 200)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", lease["lease_id"]))


if __name__ == "__main__":
    unittest.main()

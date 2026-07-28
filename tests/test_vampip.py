from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from vampip.analysis import (
    duplicate_candidate_rows,
    identity_conflicts,
    missing_dependencies,
    verified_duplicate_groups,
    version_families,
)
from vampip.cli import main
from vampip.content_audit import audit_contents
from vampip.database import connect
from vampip.inventory import (
    archive_content_sha256,
    ensure_content_hashes,
    rows_for_root,
    scan,
)
from vampip.models import parse_dependency_ref, parse_var_filename
from vampip.operations import (
    candidates_from_duplicates,
    install_archive,
    quarantine_candidates,
    restore_manifest,
    reverse_dependency_blockers,
    select_packages,
)
from vampip.profiles import (
    activation_plan,
    apply_activation,
    load_profile,
    resolve,
    rollback_activation,
    save_profile,
)


def make_var(
    path: Path,
    *,
    creator: str,
    package: str,
    dependencies: dict | None = None,
    payload: bytes = b"payload",
) -> None:
    metadata = {
        "creatorName": creator,
        "packageName": package,
        "dependencies": dependencies or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps(metadata))
        archive.writestr("Custom/data.bin", payload)


def repack_var(
    source: Path,
    destination: Path,
    *,
    replace_members: dict[str, bytes] | None = None,
) -> None:
    replacements = replace_members or {}
    with zipfile.ZipFile(source) as archive:
        members = [
            (entry.filename, archive.read(entry))
            for entry in archive.infolist()
        ]

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        archive.comment = b"repacked container"
        for index, (name, contents) in enumerate(reversed(members)):
            entry = zipfile.ZipInfo(
                name,
                date_time=(2001, 2, 3, 4, 5, 6),
            )
            entry.compress_type = zipfile.ZIP_STORED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.comment = f"repacked member {index}".encode("ascii")
            archive.writestr(entry, replacements.get(name, contents))


def set_nonstandard_zip_version_high_byte(
    path: Path,
    *,
    entry_name: str,
    high_byte: int,
) -> None:
    with zipfile.ZipFile(path) as archive:
        entry = archive.getinfo(entry_name)
        local_header_offset = entry.header_offset
        central_directory_offset = archive.start_dir

    contents = bytearray(path.read_bytes())
    contents[local_header_offset + 5] = high_byte
    while central_directory_offset < len(contents):
        if contents[central_directory_offset : central_directory_offset + 4] != (
            b"PK\x01\x02"
        ):
            break
        name_length = int.from_bytes(
            contents[
                central_directory_offset + 28 : central_directory_offset + 30
            ],
            "little",
        )
        extra_length = int.from_bytes(
            contents[
                central_directory_offset + 30 : central_directory_offset + 32
            ],
            "little",
        )
        comment_length = int.from_bytes(
            contents[
                central_directory_offset + 32 : central_directory_offset + 34
            ],
            "little",
        )
        name_start = central_directory_offset + 46
        name_end = name_start + name_length
        if contents[name_start:name_end].decode("utf-8") == entry_name:
            contents[central_directory_offset + 7] = high_byte
            path.write_bytes(contents)
            return
        central_directory_offset = (
            name_end + extra_length + comment_length
        )
    raise AssertionError(f"central-directory entry not found: {entry_name}")


class NameParsingTests(unittest.TestCase):
    def test_package_name_and_copy_suffixes(self) -> None:
        parsed = parse_var_filename("Creator.Package.With_Dots.12_1.var")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.creator, "Creator")
        self.assertEqual(parsed.package, "Package.With_Dots")
        self.assertEqual(parsed.version, 12)
        self.assertEqual(parsed.copy_suffix, "_1")
        self.assertEqual(parsed.canonical_filename, "Creator.Package.With_Dots.12.var")

        windows_copy = parse_var_filename("Creator.Package.12 (1).var")
        self.assertIsNotNone(windows_copy)
        assert windows_copy is not None
        self.assertEqual(windows_copy.copy_suffix, " (1)")

    def test_dependency_reference(self) -> None:
        latest = parse_dependency_ref("Creator.Some.Package.latest")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertTrue(latest.is_latest)
        exact = parse_dependency_ref("Creator.Some.Package.7")
        self.assertIsNotNone(exact)
        assert exact is not None
        self.assertEqual(exact.version, 7)


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addons = self.base / "AddonPackages"
        self.state = self.base / "state"
        self.addons.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_scan_cache_dependencies_and_versions(self) -> None:
        dependencies = {
            "Dep.Asset.latest": {
                "dependencies": {
                    "Nested.Asset.2": {"dependencies": {}},
                }
            }
        }
        make_var(
            self.addons / "Owner.Scene.1.var",
            creator="Owner",
            package="Scene",
            dependencies=dependencies,
        )
        make_var(
            self.addons / "Owner.Scene.2.var",
            creator="Owner",
            package="Scene",
        )
        with connect(self.state) as database:
            first = scan(self.addons, database)
            self.assertEqual(first.inspected, 2)
            second = scan(self.addons, database)
            self.assertEqual(second.unchanged, 2)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(len(version_families(rows)), 1)
            missing = missing_dependencies(rows)
            self.assertIn(("Owner.Scene.1", "Dep.Asset.latest"), missing)
            self.assertIn(("Owner.Scene.1", "Nested.Asset.2"), missing)

    def test_replaced_inode_invalidates_cache(self) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset", payload=b"first")
        with connect(self.state) as database:
            scan(self.addons, database)
            old = rows_for_root(database, self.addons)[0]
            replacement = self.addons / "replacement.var"
            make_var(
                replacement,
                creator="Owner",
                package="Asset",
                payload=b"other",
            )
            os.utime(replacement, ns=(old["mtime_ns"], old["mtime_ns"]))
            os.replace(replacement, archive)
            result = scan(self.addons, database)
            self.assertEqual(result.inspected, 1)

    def test_content_hash_cache_follows_rename_and_invalidates_changed_archive(
        self,
    ) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")

        with connect(self.state) as database:
            scan(self.addons, database)
            initial_rows = rows_for_root(database, self.addons)
            self.assertEqual(ensure_content_hashes(database, initial_rows), 1)
            initial = rows_for_root(database, self.addons)[0]
            initial_hash = initial["content_sha256"]
            self.assertTrue(initial_hash)

            moved = self.addons / "Collection" / archive.name
            moved.parent.mkdir()
            archive.rename(moved)
            renamed_scan = scan(self.addons, database)
            self.assertEqual(renamed_scan.inspected, 0)
            renamed = rows_for_root(database, self.addons)[0]
            self.assertEqual(renamed["path"], str(moved.resolve()))
            self.assertEqual(renamed["content_sha256"], initial_hash)
            self.assertEqual(ensure_content_hashes(database, [renamed]), 0)

            make_var(
                moved,
                creator="Owner",
                package="Asset",
                payload=bytes(range(256)) * 8,
            )
            self.assertNotEqual(moved.stat().st_size, renamed["size"])
            changed_scan = scan(self.addons, database)
            self.assertEqual(changed_scan.inspected, 1)
            changed = rows_for_root(database, self.addons)[0]
            self.assertIsNone(changed["content_sha256"])

            self.assertEqual(ensure_content_hashes(database, [changed]), 1)
            rehashed = rows_for_root(database, self.addons)[0]
            self.assertNotEqual(rehashed["content_sha256"], initial_hash)

    def test_content_hash_rejects_nonempty_explicit_directory(self) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")
        with zipfile.ZipFile(archive, "a") as opened:
            directory = zipfile.ZipInfo("Custom/Unexpected/")
            directory.create_system = 3
            directory.external_attr = (stat.S_IFDIR | 0o755) << 16
            opened.writestr(directory, b"directory payload")

        with self.assertRaisesRegex(ValueError, "directory contains data"):
            archive_content_sha256(archive)

    def test_content_hash_rejects_unix_directory_without_trailing_slash(
        self,
    ) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")
        with zipfile.ZipFile(archive, "a") as opened:
            directory = zipfile.ZipInfo("Custom/Unexpected")
            directory.create_system = 3
            directory.external_attr = (stat.S_IFDIR | 0o755) << 16
            opened.writestr(directory, b"")

        with self.assertRaisesRegex(
            ValueError,
            "directory path has no trailing slash",
        ):
            archive_content_sha256(archive)

    def test_malformed_cached_content_hash_is_recalculated(self) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(ensure_content_hashes(database, rows), 1)
            valid_hash = rows_for_root(database, self.addons)[0][
                "content_sha256"
            ]
            malformed_hash = f"{valid_hash[:-1]}z"
            database.execute(
                """
                UPDATE package_files
                SET content_sha256 = ?
                WHERE path = ?
                """,
                (malformed_hash, str(archive.resolve())),
            )

            malformed = rows_for_root(database, self.addons)
            self.assertEqual(malformed[0]["content_sha256"], malformed_hash)
            self.assertEqual(ensure_content_hashes(database, malformed), 1)
            repaired = rows_for_root(database, self.addons)[0]
            self.assertEqual(repaired["content_sha256"], valid_hash)

    def test_scan_reports_external_enable_and_active_removal(self) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")
        hidden = Path(f"{archive}.vampip-disabled")
        archive.rename(hidden)

        with connect(self.state) as database:
            initial = scan(self.addons, database)
            self.assertEqual(initial.active_changed, 0)

            hidden.rename(archive)
            enabled = scan(self.addons, database)
            self.assertEqual(enabled.active_changed, 1)

            archive.unlink()
            removed = scan(self.addons, database)
            self.assertEqual(removed.active_changed, 1)
            self.assertEqual(removed.removed, 1)

    def test_inspection_version_invalidates_unchanged_archive_cache(self) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")
        with connect(self.state) as database:
            first = scan(self.addons, database)
            self.assertEqual(first.inspected, 1)
            database.execute(
                """
                UPDATE schema_meta SET value = '0'
                WHERE key LIKE 'archive_inspection_version:%'
                """
            )

            upgraded = scan(self.addons, database)
            self.assertEqual(upgraded.inspected, 1)
            self.assertEqual(upgraded.unchanged, 0)

            cached = scan(self.addons, database)
            self.assertEqual(cached.inspected, 0)
            self.assertEqual(cached.unchanged, 1)

    def test_doctor_reports_sharpziplib_incompatible_version_high_byte(
        self,
    ) -> None:
        archive = self.addons / "Owner.Asset.1.var"
        make_var(archive, creator="Owner", package="Asset")
        set_nonstandard_zip_version_high_byte(
            archive,
            entry_name="meta.json",
            high_byte=3,
        )

        with zipfile.ZipFile(archive) as opened:
            entry = opened.getinfo("meta.json")
            self.assertEqual(entry.extract_version, 20)
            self.assertEqual(entry.reserved, 3)

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--addon-dir",
                    str(self.addons),
                    "--state-dir",
                    str(self.state),
                    "doctor",
                    "--refresh",
                ]
            )

        self.assertEqual(exit_code, 1)
        report = output.getvalue()
        self.assertIn("Invalid archives/names:       1", report)
        self.assertIn("invalid Owner.Asset.1.var", report)
        self.assertIn("VaM/SharpZipLib-incompatible ZIP entry 'meta.json'", report)
        self.assertIn("version required to extract is 788", report)

    def test_duplicates_quarantine_and_restore(self) -> None:
        original = self.addons / "Creator.Asset.1.var"
        nested = self.addons / "Collection" / "Creator.Asset.1.var"
        make_var(original, creator="Creator", package="Asset")
        nested.parent.mkdir()
        nested.write_bytes(original.read_bytes())

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(len(duplicate_candidate_rows(rows)), 2)
            groups, calculated = verified_duplicate_groups(database, rows)
            self.assertEqual(calculated, 2)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].keeper["relative_path"], original.name)
            manifest = quarantine_candidates(
                self.addons,
                candidates_from_duplicates(groups),
                self.base / "quarantine",
            )

        self.assertTrue(original.exists())
        self.assertFalse(nested.exists())
        self.assertEqual(restore_manifest(manifest), 1)
        self.assertTrue(nested.exists())

    def test_conflict_and_install_refusal(self) -> None:
        first = self.addons / "Creator.Asset.1.var"
        make_var(first, creator="Creator", package="Asset", payload=b"first")
        incoming = self.base / "Creator.Asset.1.var"
        make_var(incoming, creator="Creator", package="Asset", payload=b"different")
        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            with self.assertRaises(ValueError):
                install_archive(incoming, self.addons, rows)

        conflict = self.addons / "Collection" / "Creator.Asset.1.var"
        conflict.parent.mkdir()
        conflict.write_bytes(incoming.read_bytes())
        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(len(identity_conflicts(rows)), 1)

    def test_repacked_package_is_logically_already_installed(self) -> None:
        installed = self.addons / "Creator.Asset.1.var"
        incoming = self.base / installed.name
        make_var(installed, creator="Creator", package="Asset")
        repack_var(installed, incoming)

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            status, location = install_archive(incoming, self.addons, rows)

        self.assertEqual(status, "already installed")
        self.assertEqual(location, installed)

    def test_verified_repack_is_not_an_identity_conflict(self) -> None:
        original = self.addons / "Creator.Asset.1.var"
        repacked = self.addons / "Collection" / original.name
        make_var(original, creator="Creator", package="Asset")
        repack_var(original, repacked)

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            self.assertEqual(ensure_content_hashes(database, rows), 2)
            checked = rows_for_root(database, self.addons)
            self.assertEqual(identity_conflicts(checked), [])

    def test_reverse_dependency_blocks_uninstall(self) -> None:
        make_var(
            self.addons / "Owner.Scene.1.var",
            creator="Owner",
            package="Scene",
            dependencies={"Dep.Asset.latest": {"dependencies": {}}},
        )
        make_var(
            self.addons / "Dep.Asset.2.var",
            creator="Dep",
            package="Asset",
        )
        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            selected = select_packages(rows, "Dep.Asset")
            blockers = reverse_dependency_blockers(rows, selected)
            self.assertEqual(blockers, [("Owner.Scene.1", "Dep.Asset.latest")])

    def test_profile_activation_is_dependency_closed_and_reversible(self) -> None:
        make_var(
            self.addons / "Owner.Scene.1.var",
            creator="Owner",
            package="Scene",
            dependencies={"Dep.Asset.latest": {"dependencies": {}}},
        )
        make_var(
            self.addons / "Dep.Asset.1.var",
            creator="Dep",
            package="Asset",
        )
        latest = self.addons / "Dep.Asset.2.var"
        make_var(latest, creator="Dep", package="Asset")
        duplicate = self.addons / "Collection" / "Dep.Asset.2.var"
        duplicate.parent.mkdir()
        duplicate.write_bytes(latest.read_bytes())
        make_var(
            self.addons / "Other.Unrelated.1.var",
            creator="Other",
            package="Unrelated",
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            resolution = resolve(["Owner.Scene"], rows)
            self.assertEqual({row["version"] for row in resolution.selected}, {1, 2})
            self.assertEqual(len(resolution.selected), 2)
            save_profile(self.state, "scene", ["Owner.Scene"], resolution)
            profile = load_profile(self.state, "scene")
            plan = activation_plan("scene", profile["packages"], rows)
            self.assertEqual(plan.active_after, 2)
            self.assertEqual(len(plan.to_disable), 3)
            manifest = apply_activation(self.state, self.addons, plan)

            rescanned = scan(self.addons, database)
            self.assertEqual(rescanned.found, 5)
            self.assertEqual(rescanned.inspected, 0)
            current = rows_for_root(database, self.addons)
            self.assertEqual(sum(row["enabled"] for row in current), 2)

        self.assertEqual(rollback_activation(manifest), 3)
        with connect(self.state) as database:
            rescanned = scan(self.addons, database)
            self.assertEqual(rescanned.inspected, 0)
            current = rows_for_root(database, self.addons)
            self.assertEqual(sum(row["enabled"] for row in current), 5)

    def test_content_audit_separates_cross_and_intra_archive_copies(self) -> None:
        payload = b"repeated-large-payload" * 100
        first = self.addons / "Creator.First.1.var"
        with zipfile.ZipFile(first, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "meta.json",
                json.dumps({"creatorName": "Creator", "packageName": "First"}),
            )
            archive.writestr("Custom/one.bin", payload)
            archive.writestr("Custom/two.bin", payload)
        second = self.addons / "Creator.Second.1.var"
        make_var(
            second,
            creator="Creator",
            package="Second",
            payload=payload,
        )
        with connect(self.state) as database:
            scan(self.addons, database)
            rows = rows_for_root(database, self.addons)
            result = audit_contents(rows, minimum_size=100)
        self.assertEqual(len(result.cross_archive_groups), 1)
        self.assertEqual(result.cross_archive_groups[0].archive_count, 2)
        self.assertEqual(len(result.intra_archive_groups), 1)
        self.assertEqual(result.intra_archive_groups[0].extra_entries, 1)


if __name__ == "__main__":
    unittest.main()

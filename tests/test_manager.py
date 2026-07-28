from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

from vampip.database import SCHEMA_VERSION, connect
from vampip.bridge import install_bridge
from vampip.inventory import rows_for_root, scan
from vampip.manager_state import list_leases
from vampip.service import ManagerService
from vampip.switching import rollback_switch

from tests.test_vampip import make_var


class ManagerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.vam_root = self.base / "VaM"
        self.addons = self.vam_root / "AddonPackages"
        self.state = self.base / "state"
        self.addons.mkdir(parents=True)

        make_var(
            self.addons / "Core.Base.1.var",
            creator="Core",
            package="Base",
        )
        make_var(
            self.addons / "Scene.Show.1.var",
            creator="Scene",
            package="Show",
            dependencies={"Asset.Dep.latest": {"dependencies": {}}},
        )
        make_var(
            self.addons / "Asset.Dep.1.var",
            creator="Asset",
            package="Dep",
        )
        make_var(
            self.addons / "Other.Unrelated.1.var",
            creator="Other",
            package="Unrelated",
        )
        hidden = self.addons / "Legacy.Hidden.1.var"
        make_var(hidden, creator="Legacy", package="Hidden")
        hidden.rename(Path(f"{hidden}.vampip-disabled"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def service(self, pids: list[int] | None = None) -> ManagerService:
        return ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: list(pids or []),
        )

    def enabled_ids(self) -> set[str]:
        with connect(self.state) as connection:
            scan(self.addons, connection)
            return {
                f"{row['creator']}.{row['package_name']}.{row['version_text']}"
                for row in rows_for_root(connection, self.addons)
                if row["valid"] and row["enabled"]
            }

    def test_managed_mode_lease_release_and_baseline_restore(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        activation = service.reconcile(apply=True, activate=True)
        self.assertEqual(activation["desired_packages"], 1)
        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})

        leased = service.lease(["Scene.Show"], days=3, apply=True)
        self.assertTrue(leased["applied"])
        self.assertEqual(
            self.enabled_ids(),
            {"Core.Base.1", "Scene.Show.1", "Asset.Dep.1"},
        )

        service.release(leased["lease_id"], apply=True)
        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})

        restored = service.deactivate(apply=True)
        self.assertFalse(restored["managed_mode"])
        self.assertEqual(
            self.enabled_ids(),
            {
                "Core.Base.1",
                "Scene.Show.1",
                "Asset.Dep.1",
                "Other.Unrelated.1",
            },
        )
        self.assertNotIn("Legacy.Hidden.1", self.enabled_ids())

    def test_running_vam_defers_disable_but_live_enables(self) -> None:
        offline = self.service()
        offline.pin(["Core.Base"])
        offline.reconcile(apply=True, activate=True)

        running = self.service([4321])
        leased = running.lease(["Scene.Show"], apply=True)
        self.assertEqual(
            self.enabled_ids(),
            {"Core.Base.1", "Scene.Show.1", "Asset.Dep.1"},
        )
        request = (
            self.vam_root
            / "Saves"
            / "PluginData"
            / "VAMPip"
            / "Bridge"
            / "request.json"
        )
        self.assertTrue(request.is_file())
        self.assertEqual(json.loads(request.read_text())["command"], "rescan")

        released = running.release(leased["lease_id"], apply=True)
        self.assertEqual(released["reconcile"]["pending_disable"], 2)
        self.assertEqual(
            self.enabled_ids(),
            {"Core.Base.1", "Scene.Show.1", "Asset.Dep.1"},
        )

        offline.reconcile(apply=True)
        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})

    def test_offline_reconcile_removes_expired_lease_after_cleanup(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        service.reconcile(apply=True, activate=True)
        leased = service.lease(["Scene.Show"], apply=True)
        with connect(self.state) as connection:
            connection.execute(
                "UPDATE manager_leases SET expires_utc = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", leased["lease_id"]),
            )

        reconciled = service.reconcile(apply=True)

        self.assertEqual(reconciled["expired_leases_removed"], 1)
        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})
        with connect(self.state) as connection:
            self.assertEqual(list_leases(connection), [])

    def test_lease_is_removed_when_apply_requires_managed_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "managed mode is not active"):
            self.service().lease(["Scene.Show"], apply=True)
        with connect(self.state) as connection:
            self.assertEqual(list_leases(connection), [])

    def test_activation_preview_is_read_only(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])

        preview = service.reconcile(apply=False, activate=True)

        self.assertEqual(preview["desired_packages"], 1)
        self.assertEqual(preview["disable"], 3)
        self.assertEqual(
            self.enabled_ids(),
            {
                "Core.Base.1",
                "Scene.Show.1",
                "Asset.Dep.1",
                "Other.Unrelated.1",
            },
        )
        status = service.status()
        self.assertFalse(status["managed_mode"])
        self.assertEqual(status["baseline_count"], 0)

    def test_manager_switch_manifest_rolls_back(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        result = service.reconcile(apply=True, activate=True)
        manifest = Path(str(result["manifest"]))
        self.assertTrue(manifest.is_file())
        restored = rollback_switch(manifest)
        self.assertEqual(restored, 3)
        self.assertIn("Other.Unrelated.1", self.enabled_ids())

    def test_manager_rollback_refuses_a_replaced_package(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        result = service.reconcile(apply=True, activate=True)
        manifest = Path(str(result["manifest"]))
        hidden = self.addons / "Scene.Show.1.var.vampip-disabled"
        replacement = hidden.with_suffix(".replacement")
        replacement.write_bytes(hidden.read_bytes())
        replacement.replace(hidden)

        with self.assertRaisesRegex(ValueError, "changed since the switch"):
            rollback_switch(manifest)

    def test_baseline_preserves_case_distinct_linux_paths(self) -> None:
        enabled = self.addons / "Case.Path.1.var"
        disabled = self.addons / "case.path.1.var"
        make_var(enabled, creator="Case", package="Path")
        make_var(disabled, creator="case", package="path")
        disabled.rename(Path(f"{disabled}.vampip-disabled"))
        service = self.service()
        service.pin(["Core.Base"])

        service.reconcile(apply=True, activate=True)
        service.deactivate(apply=True)

        self.assertTrue(enabled.is_file())
        self.assertTrue(Path(f"{disabled}.vampip-disabled").is_file())
        self.assertFalse(disabled.is_file())

    def test_manager_rejects_same_id_same_size_content_conflict(self) -> None:
        conflicting = self.addons / "Collection" / "Core.Base.1.var"
        make_var(
            conflicting,
            creator="Core",
            package="Base",
            payload=b"DIFFERENT",
        )
        original = self.addons / "Core.Base.1.var"
        make_var(
            original,
            creator="Core",
            package="Base",
            payload=b"ORIGINAL!",
        )
        self.assertEqual(original.stat().st_size, conflicting.stat().st_size)
        with self.assertRaisesRegex(ValueError, "different data"):
            self.service().pin(["Core.Base"])

    def test_launch_uses_the_scoped_proton_script_without_a_shell(self) -> None:
        script = self.vam_root / "launch-vam-desktop-proton.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        fake_process = mock.Mock(pid=8765)
        with mock.patch(
            "vampip.service.subprocess.Popen",
            return_value=fake_process,
        ) as popen:
            result = self.service().launch_vam(reconcile=False)
        self.assertEqual(result["pid"], 8765)
        positional, keywords = popen.call_args
        self.assertEqual(positional[0], [str(script)])
        self.assertNotIn("shell", keywords)
        self.assertTrue(keywords["start_new_session"])

    def test_bridge_installer_is_idempotent_and_refuses_overwrite(self) -> None:
        installed = install_bridge(self.vam_root)
        self.assertEqual(len(installed), 2)
        self.assertTrue(all(path.is_file() for path in installed))
        self.assertEqual(install_bridge(self.vam_root), installed)
        installed[0].write_text("different", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            install_bridge(self.vam_root)


class DatabaseMigrationTests(unittest.TestCase):
    def test_v01_package_table_is_extended_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            database = state / "inventory.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE package_files (
                    path TEXT PRIMARY KEY,
                    root TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    basename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    device INTEGER NOT NULL,
                    inode INTEGER NOT NULL,
                    creator TEXT,
                    package_name TEXT,
                    version INTEGER,
                    version_text TEXT,
                    canonical_filename TEXT,
                    valid INTEGER NOT NULL,
                    error TEXT,
                    dependencies_json TEXT NOT NULL DEFAULT '[]',
                    sha256 TEXT,
                    scan_generation TEXT NOT NULL
                );
                INSERT INTO package_files(
                    path, root, relative_path, basename, size, mtime_ns,
                    device, inode, valid, dependencies_json, scan_generation
                ) VALUES (
                    '/tmp/test.var', '/tmp', 'test.var', 'test.var', 1, 1,
                    1, 1, 0, '[]', 'old'
                );
                """
            )
            connection.commit()
            connection.close()

            with connect(state) as migrated:
                row = migrated.execute("SELECT enabled FROM package_files").fetchone()
                version = migrated.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                self.assertEqual(row["enabled"], 1)
                self.assertEqual(int(version["value"]), SCHEMA_VERSION)
                self.assertIsNotNone(
                    migrated.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'manager_leases'
                        """
                    ).fetchone()
                )
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

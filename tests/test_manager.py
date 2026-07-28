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
from vampip.manager_state import add_pin, list_leases
from vampip.session_plugins import SessionPluginPresetError
from vampip.service import ManagerService
from vampip.switching import rollback_switch

from tests.test_vampip import make_var


def write_session_plugin_defaults(
    vam_root: Path,
    *,
    enabled_package: str = "Scene.Show.1",
    disabled_package: str = "Other.Unrelated.1",
    include_loose: bool = True,
) -> Path:
    plugins = {
        "plugin#0": (
            f"{enabled_package}:/Custom/Scripts/Enabled/Enabled.cslist"
        ),
        "plugin#1": (
            f"{disabled_package}:/Custom/Scripts/Disabled/Disabled.cslist"
        ),
    }
    storables: list[dict[str, object]] = [
        {"id": "plugin#0_Enabled", "enabled": "true"},
        {"id": "plugin#1_Disabled", "enabled": "false"},
    ]
    if include_loose:
        plugins["plugin#2"] = "Custom/Scripts/Loose/Loose.cslist"
        storables.append({"id": "plugin#2_Loose", "enabled": True})
        loose = vam_root / "Custom" / "Scripts" / "Loose" / "Loose.cslist"
        loose.parent.mkdir(parents=True, exist_ok=True)
        loose.write_text("Loose.cs\n", encoding="utf-8")
    storables.insert(0, {"id": "PluginManager", "plugins": plugins})

    path = (
        vam_root
        / "Custom"
        / "PluginPresets"
        / "Plugins_UserDefaults.vap"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"storables": storables}), encoding="utf-8")
    return path


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

    def test_session_plugins_reports_package_and_loose_plugin_state(self) -> None:
        write_session_plugin_defaults(
            self.vam_root,
            enabled_package="Scene.Show.1",
            disabled_package="Other.Unrelated.1",
        )
        missing_source = (
            "Missing.Plugin.1:/Custom/Scripts/Missing/Missing.cslist"
        )
        preset_path = (
            self.vam_root
            / "Custom"
            / "PluginPresets"
            / "Plugins_UserDefaults.vap"
        )
        preset = json.loads(preset_path.read_text(encoding="utf-8"))
        preset["storables"][0]["plugins"]["plugin#3"] = missing_source
        preset["storables"].append(
            {"id": "plugin#3_Missing", "enabled": True}
        )
        preset_path.write_text(json.dumps(preset), encoding="utf-8")

        service = self.service()
        service.pin(["Scene.Show.1"])
        result = service.session_plugins()

        self.assertTrue(result["exists"])
        self.assertEqual(result["preset"], str(preset_path))
        self.assertEqual(
            result["enabled_packaged_roots"],
            ["Scene.Show.1", "Missing.Plugin.1"],
        )
        self.assertEqual(
            result["counts"],
            {
                "total": 4,
                "enabled": 3,
                "packaged": 3,
                "enabled_packaged": 2,
                "loose": 1,
                "already_pinned": 1,
                "missing": 1,
            },
        )
        items = {
            str(item["package_ref"] or item["source"]): item
            for item in result["items"]
        }
        scene = items["Scene.Show.1"]
        self.assertTrue(scene["installed"])
        self.assertTrue(scene["active"])
        self.assertTrue(scene["pinned"])
        self.assertEqual(scene["resolved_package"], "Scene.Show.1")

        disabled = items["Other.Unrelated.1"]
        self.assertFalse(disabled["enabled"])
        self.assertTrue(disabled["installed"])
        self.assertTrue(disabled["active"])
        self.assertFalse(disabled["pinned"])

        loose = items["Custom/Scripts/Loose/Loose.cslist"]
        self.assertTrue(loose["loose"])
        self.assertTrue(loose["installed"])
        self.assertTrue(loose["active"])
        self.assertFalse(loose["pinned"])

        missing = items["Missing.Plugin.1"]
        self.assertFalse(missing["installed"])
        self.assertFalse(missing["active"])
        self.assertIsNone(missing["resolved_package"])

        (
            self.vam_root
            / "Custom"
            / "Scripts"
            / "Loose"
            / "Loose.cslist"
        ).unlink()
        refreshed = service.session_plugins()
        refreshed_loose = next(
            item for item in refreshed["items"] if item["loose"]
        )
        self.assertFalse(refreshed_loose["installed"])
        self.assertFalse(refreshed_loose["active"])

    def test_import_session_plugins_pins_enabled_only_and_can_apply_disabled(
        self,
    ) -> None:
        write_session_plugin_defaults(self.vam_root)
        service = self.service()

        imported = service.import_session_plugins(apply=True)

        self.assertEqual(imported["roots"], ["Scene.Show.1"])
        self.assertEqual(imported["pinned"], 1)
        self.assertEqual(imported["already_pinned"], 0)
        self.assertEqual(imported["resolved_packages"], 2)
        self.assertFalse(imported["managed_mode"])
        self.assertFalse(imported["applied"])
        self.assertNotIn("reconcile", imported)
        self.assertEqual(
            [pin["root_ref"] for pin in service.status()["pins"]],
            ["Scene.Show.1"],
        )

        activation = service.reconcile(apply=True, activate=True)
        self.assertEqual(activation["session_default_roots"], 1)
        self.assertEqual(activation["session_defaults_pinned"], 0)
        self.assertEqual(
            self.enabled_ids(),
            {"Scene.Show.1", "Asset.Dep.1"},
        )

        with_disabled = service.import_session_plugins(
            include_disabled=True,
            apply=True,
        )
        self.assertEqual(
            with_disabled["roots"],
            ["Scene.Show.1", "Other.Unrelated.1"],
        )
        self.assertEqual(with_disabled["pinned"], 1)
        self.assertEqual(with_disabled["already_pinned"], 1)
        self.assertEqual(with_disabled["resolved_packages"], 3)
        self.assertTrue(with_disabled["applied"])
        self.assertIn("reconcile", with_disabled)
        self.assertEqual(
            self.enabled_ids(),
            {"Scene.Show.1", "Asset.Dep.1", "Other.Unrelated.1"},
        )
        self.assertNotIn(
            "Custom/Scripts/Loose/Loose.cslist",
            [pin["root_ref"] for pin in service.status()["pins"]],
        )

    def test_session_import_reports_pin_success_when_apply_fails(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        service.reconcile(apply=True, activate=True)
        write_session_plugin_defaults(self.vam_root)
        with connect(self.state) as connection:
            add_pin(connection, "Missing.Required.1")

        result = service.import_session_plugins(apply=True)

        self.assertEqual(result["pinned"], 1)
        self.assertFalse(result["applied"])
        self.assertIn("managed package resolution failed", result["reconcile_error"])
        self.assertNotIn("reconcile", result)
        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})
        self.assertEqual(
            {pin["root_ref"] for pin in service.status()["pins"]},
            {"Core.Base", "Missing.Required.1", "Scene.Show.1"},
        )

    def test_first_activation_preserves_enabled_session_package_only(self) -> None:
        write_session_plugin_defaults(self.vam_root)
        service = self.service()
        original_enabled = self.enabled_ids()

        preview = service.reconcile(apply=False, activate=True)

        self.assertEqual(preview["desired_packages"], 2)
        self.assertEqual(preview["session_default_roots"], 1)
        self.assertEqual(preview["session_defaults_pinned"], 0)
        self.assertEqual(self.enabled_ids(), original_enabled)
        preview_status = service.status()
        self.assertFalse(preview_status["managed_mode"])
        self.assertEqual(preview_status["pins"], [])
        self.assertEqual(preview_status["baseline_count"], 0)

        activation = service.reconcile(apply=True, activate=True)

        self.assertEqual(activation["desired_packages"], 2)
        self.assertEqual(activation["session_default_roots"], 1)
        self.assertEqual(activation["session_defaults_pinned"], 1)
        self.assertEqual(
            self.enabled_ids(),
            {"Scene.Show.1", "Asset.Dep.1"},
        )
        status = service.status()
        self.assertTrue(status["managed_mode"])
        self.assertEqual(
            [pin["root_ref"] for pin in status["pins"]],
            ["Scene.Show.1"],
        )
        self.assertNotIn("Other.Unrelated.1", self.enabled_ids())

    def test_malformed_session_defaults_block_activation_without_mutation(
        self,
    ) -> None:
        preset = (
            self.vam_root
            / "Custom"
            / "PluginPresets"
            / "Plugins_UserDefaults.vap"
        )
        preset.parent.mkdir(parents=True, exist_ok=True)
        preset.write_text("{not valid JSON", encoding="utf-8")
        service = self.service()
        original_enabled = self.enabled_ids()

        with self.assertRaises(SessionPluginPresetError):
            service.reconcile(apply=True, activate=True)

        self.assertEqual(self.enabled_ids(), original_enabled)
        status = service.status()
        self.assertFalse(status["managed_mode"])
        self.assertEqual(status["pins"], [])
        self.assertEqual(status["baseline_count"], 0)

    def test_unresolved_session_default_blocks_activation_without_mutation(
        self,
    ) -> None:
        write_session_plugin_defaults(
            self.vam_root,
            enabled_package="Missing.Plugin.1",
            include_loose=False,
        )
        service = self.service()
        original_enabled = self.enabled_ids()

        with self.assertRaisesRegex(
            ValueError,
            "managed package resolution failed: Missing.Plugin.1",
        ):
            service.reconcile(apply=True, activate=True)

        self.assertEqual(self.enabled_ids(), original_enabled)
        status = service.status()
        self.assertFalse(status["managed_mode"])
        self.assertEqual(status["pins"], [])
        self.assertEqual(status["baseline_count"], 0)

    def test_activation_rolls_back_if_session_pins_cannot_be_saved(self) -> None:
        write_session_plugin_defaults(self.vam_root)
        service = self.service()
        original_enabled = self.enabled_ids()

        with mock.patch.object(
            ManagerService,
            "_add_session_plugin_pins",
            side_effect=sqlite3.OperationalError("simulated write failure"),
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError,
                "simulated write failure",
            ):
                service.reconcile(apply=True, activate=True)

        self.assertEqual(self.enabled_ids(), original_enabled)
        status = service.status()
        self.assertFalse(status["managed_mode"])
        self.assertEqual(status["pins"], [])
        self.assertGreater(status["baseline_count"], 0)

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
        source = installed[0].read_text(encoding="utf-8")
        self.assertIn('BridgeVersion = "0.1.3"', source)
        self.assertNotRegex(source, r"(?m)^\s*Type(?:\s|\.)")
        self.assertNotIn("new Type[]", source)
        self.assertNotIn("System.Reflection", source)
        self.assertNotIn("System.Type", source)
        self.assertNotIn("BindingFlags", source)
        self.assertNotIn("TargetInvocationException", source)
        self.assertNotIn(".GetType(", source)
        self.assertNotIn("typeof(", source)
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

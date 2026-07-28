from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

from vampip.database import SCHEMA_VERSION, connect
from vampip.bridge import install_bridge, read_bridge_request, read_bridge_status
from vampip.inventory import rows_for_root, scan
from vampip.manager_state import add_pin, list_leases
from vampip.session_plugins import SessionPluginPresetError
from vampip.service import ManagerService
from vampip.switching import rollback_switch
from vampip.web import AutoReconciler

from tests.test_vampip import make_var, repack_var


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

    def test_running_vam_resource_version_lease_only_enables_hidden_update(
        self,
    ) -> None:
        member = "Saves/scene/Versioned.json"
        metadata = {
            "creatorName": "Creator",
            "packageName": "Bundle",
            "dependencies": {},
        }
        for version in (2, 4):
            archive_path = self.addons / f"Creator.Bundle.{version}.var"
            with zipfile.ZipFile(
                archive_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.writestr("meta.json", json.dumps(metadata))
                archive.writestr(
                    member,
                    json.dumps({"version": version}),
                )
            if version == 4:
                archive_path.rename(
                    Path(f"{archive_path}.vampip-disabled")
                )

        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', 'versioned-scene',
                          'Creator', 'Bundle', '["2"]', ?, 'Scene', '',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (str(self.vam_root), member.replace("/", "\\")),
            )
            resource_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO catalog_resource_versions(
                    resource_id, version_text
                ) VALUES (?, '2')
                """,
                (resource_id,),
            )

        offline = self.service()
        offline.pin(["Creator.Bundle.2"])
        offline.reconcile(apply=True, activate=True)
        self.assertEqual(self.enabled_ids(), {"Creator.Bundle.2"})
        offline.unpin("Creator.Bundle.2", apply=False)

        running = self.service([4321])
        leased = running.lease_resource(
            resource_id,
            package_version=4,
            apply=True,
        )

        self.assertEqual(leased["selected_version"], "4")
        self.assertEqual(
            leased["discovered_roots"],
            ["Creator.Bundle.4"],
        )
        self.assertEqual(leased["reconcile"]["enable"], 1)
        self.assertEqual(leased["reconcile"]["disable"], 0)
        self.assertEqual(leased["reconcile"]["pending_disable"], 1)
        self.assertTrue(leased["reconcile"]["vam_running"])
        self.assertEqual(
            self.enabled_ids(),
            {"Creator.Bundle.2", "Creator.Bundle.4"},
        )
        request = read_bridge_request(self.vam_root)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request["command"], "rescan")

        listed = running.search_resources()["items"]
        resource = next(item for item in listed if item["id"] == resource_id)
        self.assertEqual(resource["selected_version"], "4")
        self.assertFalse(resource["update_available"])

    def test_deactivate_rechecks_vam_after_inventory_preparation(self) -> None:
        offline = self.service()
        offline.pin(["Core.Base"])
        offline.reconcile(apply=True, activate=True)
        probes = 0

        def process_probe() -> list[int]:
            nonlocal probes
            probes += 1
            return [] if probes == 1 else [9876]

        service = ManagerService(
            self.addons,
            self.state,
            process_probe=process_probe,
        )
        with self.assertRaisesRegex(
            ValueError,
            "started while the baseline restore was being prepared",
        ):
            service.deactivate(apply=True)

        self.assertEqual(self.enabled_ids(), {"Core.Base.1"})
        self.assertTrue(service.status()["managed_mode"])

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

    def test_status_refresh_discovers_new_package_version(self) -> None:
        downloads = self.addons / "Downloads"
        downloads.mkdir()
        service = self.service()
        initial = service.status()

        make_var(
            downloads / "Scene.Show.2.var",
            creator="Scene",
            package="Show",
        )

        refreshed = service.status()
        listed = service.list_packages(query="Scene.Show")

        self.assertEqual(
            refreshed["packages"]["total"],
            initial["packages"]["total"] + 1,
        )
        self.assertEqual(
            {item["id"] for item in listed["items"]},
            {"Scene.Show.1", "Scene.Show.2"},
        )

    def test_status_refresh_skips_full_scan_when_inventory_is_unchanged(
        self,
    ) -> None:
        service = self.service()
        initial = service.status()

        with mock.patch("vampip.service.scan", wraps=scan) as full_scan:
            refreshed = service.status()

        full_scan.assert_not_called()
        self.assertEqual(refreshed["packages"], initial["packages"])

    def test_auto_reconciler_rescans_new_enabled_package_once_while_vam_runs(
        self,
    ) -> None:
        downloads = self.addons / "Downloads"
        downloads.mkdir()
        offline = self.service()
        offline.pin(["Core.Base"])
        offline.reconcile(apply=True, activate=True)

        running = self.service([4321])
        running.set_auto_reconcile(False)
        running.status()
        make_var(
            downloads / "Fresh.Download.1.var",
            creator="Fresh",
            package="Download",
        )
        reconciler = AutoReconciler(running, interval=0.01)

        with (
            mock.patch(
                "vampip.bridge._write_request",
                return_value="rescan-request",
            ) as write_bridge_request,
            mock.patch.object(
                reconciler._stop,
                "wait",
                side_effect=[False, False, True],
            ),
        ):
            reconciler._run()

        write_bridge_request.assert_called_once()
        self.assertEqual(
            write_bridge_request.call_args.args[1]["command"],
            "rescan",
        )

    def test_auto_reconciler_waits_until_a_new_archive_is_valid(self) -> None:
        downloads = self.addons / "Downloads"
        downloads.mkdir()
        self.service().status()
        running = self.service([4321])
        running.status()
        incoming = downloads / "Fresh.Download.1.var"
        incoming.write_bytes(b"incomplete download")

        invalid_reconciler = AutoReconciler(running, interval=0.01)
        with (
            mock.patch("vampip.bridge._write_request") as write_bridge_request,
            mock.patch.object(
                invalid_reconciler._stop,
                "wait",
                side_effect=[False, True],
            ),
        ):
            invalid_reconciler._run()
        write_bridge_request.assert_not_called()

        make_var(
            incoming,
            creator="Fresh",
            package="Download",
        )
        valid_reconciler = AutoReconciler(running, interval=0.01)
        with (
            mock.patch(
                "vampip.bridge._write_request",
                return_value="rescan-request",
            ) as write_bridge_request,
            mock.patch.object(
                valid_reconciler._stop,
                "wait",
                side_effect=[False, False, True],
            ),
        ):
            valid_reconciler._run()
        write_bridge_request.assert_called_once()

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
        operation = service.activity()["operation"]
        self.assertEqual(operation["status"], "failed")
        self.assertFalse(operation["busy"])
        self.assertEqual(operation["completed"], operation["total"])
        self.assertEqual(operation["enabled"], 0)
        self.assertEqual(operation["disabled"], 0)

    def test_manager_switch_manifest_rolls_back(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        result = service.reconcile(apply=True, activate=True)
        manifest = Path(str(result["manifest"]))
        self.assertTrue(manifest.is_file())
        restored = rollback_switch(manifest)
        self.assertEqual(restored, 3)
        self.assertIn("Other.Unrelated.1", self.enabled_ids())

    def test_activity_stays_live_during_reconcile_and_coalesces_auto_work(
        self,
    ) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        started = threading.Event()
        release = threading.Event()
        launch_entered = threading.Event()
        popen_called = threading.Event()
        errors: list[BaseException] = []
        launch_errors: list[BaseException] = []
        launch_results: list[dict[str, object]] = []
        script = self.vam_root / "launch-vam-desktop-proton.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

        def slow_apply(*args, **kwargs):
            callback = kwargs["progress_callback"]
            callback(
                {
                    "phase": "applying",
                    "total": 3,
                    "completed": 1,
                    "enable": 0,
                    "disable": 3,
                }
            )
            started.set()
            release.wait(timeout=5)
            callback(
                {
                    "phase": "final",
                    "status": "complete",
                    "total": 3,
                    "completed": 3,
                    "enable": 0,
                    "disable": 3,
                }
            )
            return None

        def reconcile() -> None:
            try:
                service.reconcile(apply=True, activate=True)
            except BaseException as exc:
                errors.append(exc)

        def launch() -> None:
            launch_entered.set()
            try:
                launch_results.append(service.launch_vam(reconcile=False))
            except BaseException as exc:
                launch_errors.append(exc)

        def fake_popen(*args, **kwargs):
            popen_called.set()
            return mock.Mock(pid=9876)

        with (
            mock.patch("vampip.service.apply_switch", side_effect=slow_apply),
            mock.patch("vampip.service.subprocess.Popen", side_effect=fake_popen),
        ):
            worker = threading.Thread(target=reconcile)
            worker.start()
            self.assertTrue(started.wait(timeout=5))

            activity = service.activity()
            self.assertFalse(activity["vam"]["running"])
            self.assertTrue(activity["operation"]["busy"])
            self.assertEqual(activity["operation"]["status"], "applying")
            self.assertEqual(activity["operation"]["completed"], 1)
            self.assertEqual(activity["operation"]["disable_total"], 3)
            self.assertEqual(activity["operation"]["disabled"], 1)
            self.assertIsNone(service.reconcile_if_idle(apply=True))

            launcher = threading.Thread(target=launch)
            launcher.start()
            self.assertTrue(launch_entered.wait(timeout=5))
            self.assertFalse(popen_called.wait(timeout=0.05))

            release.set()
            worker.join(timeout=5)
            launcher.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertFalse(launcher.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(launch_errors, [])
        self.assertEqual(launch_results[0]["pid"], 9876)
        self.assertTrue(popen_called.is_set())
        completed = service.activity()["operation"]
        self.assertFalse(completed["busy"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["disabled"], 3)

    def test_activity_uses_current_process_probe_without_status_lock(self) -> None:
        pids = [4321]
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: list(pids),
        )

        first = service.activity()
        self.assertTrue(first["vam"]["running"])
        self.assertEqual(first["vam"]["pids"], [4321])

        pids.clear()
        second = service.activity()
        self.assertFalse(second["vam"]["running"])
        self.assertEqual(second["vam"]["pids"], [])

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

    def test_manager_accepts_same_id_harmless_unequal_size_zip_repack(
        self,
    ) -> None:
        original = self.addons / "Core.Base.1.var"
        repacked = self.addons / "Collection" / original.name
        repack_var(original, repacked)

        self.assertNotEqual(original.read_bytes(), repacked.read_bytes())
        self.assertNotEqual(original.stat().st_size, repacked.stat().st_size)
        with (
            zipfile.ZipFile(original) as source,
            zipfile.ZipFile(repacked) as copy,
        ):
            source_members = {
                entry.filename: source.read(entry)
                for entry in source.infolist()
            }
            copy_members = {
                entry.filename: copy.read(entry)
                for entry in copy.infolist()
            }
            self.assertEqual(copy.namelist(), list(reversed(source.namelist())))
            self.assertTrue(
                all(
                    entry.compress_type == zipfile.ZIP_STORED
                    for entry in copy.infolist()
                )
            )
        self.assertEqual(copy_members, source_members)

        result = self.service().pin(["Core.Base"])
        self.assertEqual(result["resolved_packages"], 1)
        with connect(self.state) as connection:
            rows = [
                row
                for row in rows_for_root(connection, self.addons)
                if row["creator"] == "Core" and row["package_name"] == "Base"
            ]
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            len({row["content_sha256"] for row in rows}),
            1,
        )
        self.assertTrue(rows[0]["content_sha256"])

    def test_manager_rejects_same_id_meta_json_only_conflict(self) -> None:
        original = self.addons / "Core.Base.1.var"
        conflicting = self.addons / "Collection" / original.name
        with zipfile.ZipFile(original) as archive:
            metadata = json.loads(archive.read("meta.json"))
        metadata["licenseType"] = "Questionable"
        repack_var(
            original,
            conflicting,
            replace_members={
                "meta.json": json.dumps(metadata).encode("utf-8"),
            },
        )

        with (
            zipfile.ZipFile(original) as source,
            zipfile.ZipFile(conflicting) as copy,
        ):
            self.assertEqual(
                source.read("Custom/data.bin"),
                copy.read("Custom/data.bin"),
            )
            self.assertNotEqual(
                source.read("meta.json"),
                copy.read("meta.json"),
            )

        with self.assertRaisesRegex(
            ValueError,
            r"different data: Core\.Base\.1",
        ):
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

    def test_launch_uses_mailbox_then_operation_lock_order(self) -> None:
        service = self.service()
        service.pin(["Core.Base"])
        service.reconcile(apply=True, activate=True)
        script = self.vam_root / "launch-vam-desktop-proton.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
        launch_attempted_mailbox = threading.Event()
        mailbox_held = threading.Event()
        operation_acquired: list[bool] = []
        launch_errors: list[BaseException] = []
        launch_results: list[dict[str, object]] = []
        raw_mailbox_lock = service._bridge_mailbox_lock

        class SignallingRLock:
            def acquire(
                self,
                blocking: bool = True,
                timeout: float = -1,
            ) -> bool:
                if threading.current_thread().name == "managed-launch":
                    launch_attempted_mailbox.set()
                if timeout == -1:
                    return raw_mailbox_lock.acquire(blocking)
                return raw_mailbox_lock.acquire(blocking, timeout)

            def release(self) -> None:
                raw_mailbox_lock.release()

            def __enter__(self) -> SignallingRLock:
                self.acquire()
                return self

            def __exit__(self, *args: object) -> None:
                self.release()

        service._bridge_mailbox_lock = SignallingRLock()  # type: ignore[assignment]

        def contend() -> None:
            with service._bridge_mailbox_lock:
                mailbox_held.set()
                if not launch_attempted_mailbox.wait(2):
                    return
                acquired = service._operation_gate.acquire(timeout=0.5)
                operation_acquired.append(acquired)
                if acquired:
                    service._operation_gate.release()

        def launch() -> None:
            try:
                launch_results.append(service.launch_vam())
            except BaseException as error:
                launch_errors.append(error)

        contender = threading.Thread(target=contend, name="mailbox-contender")
        contender.start()
        self.assertTrue(mailbox_held.wait(2))
        with mock.patch(
            "vampip.service.subprocess.Popen",
            return_value=mock.Mock(pid=8765),
        ):
            launcher = threading.Thread(target=launch, name="managed-launch")
            launcher.start()
            contender.join(2)
            launcher.join(2)

        self.assertFalse(contender.is_alive())
        self.assertFalse(launcher.is_alive())
        self.assertEqual(operation_acquired, [True])
        self.assertEqual(launch_errors, [])
        self.assertEqual(launch_results[0]["pid"], 8765)

    def test_bridge_installer_is_idempotent_and_refuses_overwrite(self) -> None:
        installed = install_bridge(self.vam_root)
        self.assertEqual(len(installed), 2)
        self.assertTrue(all(path.is_file() for path in installed))
        source = installed[0].read_text(encoding="utf-8")
        self.assertIn('BridgeVersion = "0.6.1"', source)
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

    def test_bridge_status_accepts_vam_simplejson_scalar_strings(self) -> None:
        status_path = (
            self.vam_root
            / "Saves"
            / "PluginData"
            / "VAMPip"
            / "Bridge"
            / "status.json"
        )
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps(
                {
                    "protocol": "1",
                    "bridgeVersion": "0.1.3",
                    "state": "ready",
                    "ok": "false",
                    "message": "Bridge ready.",
                }
            ),
            encoding="utf-8",
        )

        status = read_bridge_status(self.vam_root)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status["protocol"], 1)
        self.assertIs(status["ok"], False)
        self.assertEqual(status["state"], "ready")


class DatabaseMigrationTests(unittest.TestCase):
    def test_newer_schema_is_rejected_before_local_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            database = state / "inventory.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                f"""
                CREATE TABLE schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT INTO schema_meta(key, value)
                VALUES ('schema_version', '{SCHEMA_VERSION + 1}');
                CREATE TABLE future_only (value TEXT);
                """
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(sqlite3.DatabaseError, "newer"):
                with connect(state):
                    self.fail("newer schemas must not be opened")

            unchanged = sqlite3.connect(database)
            try:
                tables = {
                    str(row[0])
                    for row in unchanged.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table'
                        """
                    )
                }
                self.assertEqual(
                    tables,
                    {"schema_meta", "future_only"},
                )
                self.assertEqual(
                    unchanged.execute("PRAGMA journal_mode").fetchone()[0],
                    "delete",
                )
            finally:
                unchanged.close()

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
                row = migrated.execute(
                    "SELECT enabled, content_sha256 FROM package_files"
                ).fetchone()
                version = migrated.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                self.assertEqual(row["enabled"], 1)
                self.assertIsNone(row["content_sha256"])
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

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import vampip.switching as switching
from vampip.models import DISABLED_SUFFIX
from vampip.switching import (
    SwitchPlan,
    apply_switch,
    classify_switch_move,
    inspect_switch,
    rollback_switch,
)


def package_row(path: Path, index: int) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path),
        "relative_path": path.name,
        "creator": "Creator",
        "package_name": f"Package{index}",
        "version_text": "1",
        "size": stat.st_size,
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": None,
    }


class SwitchJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addons = self.base / "AddonPackages"
        self.state = self.base / "state"
        self.addons.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def disable_plan(self, count: int) -> tuple[SwitchPlan, list[Path]]:
        paths: list[Path] = []
        rows: list[dict[str, object]] = []
        for index in range(count):
            path = self.addons / f"Creator.Package{index}.1.var"
            path.write_bytes(f"package-{index}".encode())
            paths.append(path)
            rows.append(package_row(path, index))
        return (
            SwitchPlan(
                desired_ids=(),
                to_enable=(),
                to_disable=tuple(rows),  # type: ignore[arg-type]
            ),
            paths,
        )

    def test_format_2_switch_is_linear_and_reports_progress(self) -> None:
        plan, paths = self.disable_plan(65)
        callbacks: list[dict[str, object]] = []

        with mock.patch(
            "vampip.switching._write_json_atomic",
            wraps=switching._write_json_atomic,
        ) as canonical_writes:
            manifest = apply_switch(
                self.state,
                self.addons,
                plan,
                run_name="linear",
                allow_disable=True,
                progress_callback=callbacks.append,
            )
            self.assertIsNotNone(manifest)
            self.assertEqual(canonical_writes.call_count, 2)

            document = json.loads(Path(manifest).read_text(encoding="utf-8"))
            self.assertEqual(document["format"], 2)
            self.assertEqual(document["status"], "complete")
            self.assertEqual(document["completed_count"], 65)
            self.assertTrue(
                all("status" not in entry for entry in document["moves"])
            )

            progress_path = Path(manifest).parent / document["progress_file"]
            events = [
                json.loads(line)
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                sum(event["event"] == "move-complete" for event in events),
                65,
            )
            self.assertEqual(events[0]["event"], "start")
            self.assertEqual(events[-1]["event"], "applied")

            applying = [
                event["completed"]
                for event in callbacks
                if event["phase"] == "applying"
            ]
            self.assertEqual(applying, [0, 64, 65])
            self.assertEqual(callbacks[0]["phase"], "preparing")
            self.assertEqual(callbacks[-1]["phase"], "final")
            self.assertEqual(callbacks[-1]["completed"], 65)

            inspection = inspect_switch(Path(manifest))
            self.assertEqual(inspection["state_counts"], {"target": 65})
            self.assertTrue(inspection["safe_to_rollback"])
            rollback_callbacks: list[dict[str, object]] = []
            self.assertEqual(
                rollback_switch(
                    Path(manifest),
                    progress_callback=rollback_callbacks.append,
                ),
                65,
            )
            self.assertEqual(rollback_callbacks[0]["phase"], "rolling-back")
            self.assertEqual(rollback_callbacks[-1]["phase"], "final")
            self.assertEqual(canonical_writes.call_count, 4)

        self.assertTrue(all(path.is_file() for path in paths))
        self.assertTrue(
            all(not Path(f"{path}{DISABLED_SUFFIX}").exists() for path in paths)
        )
        rolled_back = inspect_switch(Path(manifest))
        self.assertEqual(rolled_back["state_counts"], {"source": 65})
        self.assertFalse(rolled_back["safe_to_rollback"])

    def test_automatic_rollback_uses_filesystem_identity_after_failure(self) -> None:
        plan, paths = self.disable_plan(3)
        callbacks: list[dict[str, object]] = []
        real_rename = switching._rename_noreplace
        attempted = 0
        failed = False

        def fail_second_package_move(source: object, target: object) -> None:
            nonlocal attempted, failed
            source_path = Path(source)
            target_path = Path(target)
            is_forward_package_move = (
                source_path.parent == self.addons
                and target_path.parent == self.addons
                and str(target_path).endswith(DISABLED_SUFFIX)
            )
            if is_forward_package_move:
                attempted += 1
                if attempted == 2 and not failed:
                    failed = True
                    raise OSError("simulated rename failure")
            real_rename(source_path, target_path)

        with mock.patch(
            "vampip.switching._rename_noreplace",
            side_effect=fail_second_package_move,
        ):
            with self.assertRaisesRegex(OSError, "simulated rename failure"):
                apply_switch(
                    self.state,
                    self.addons,
                    plan,
                    run_name="failure",
                    allow_disable=True,
                    progress_callback=callbacks.append,
                )

        self.assertTrue(all(path.is_file() for path in paths))
        manifests = list((self.state / "manager-runs").glob("*.json"))
        self.assertEqual(len(manifests), 1)
        document = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(document["format"], 2)
        self.assertEqual(document["status"], "rolled-back")
        self.assertEqual(document["completed_count"], 1)
        self.assertEqual(document["rolled_back_count"], 1)
        self.assertEqual(callbacks[-1]["phase"], "error")
        self.assertEqual(callbacks[-1]["status"], "rolled-back")

    def test_automatic_rollback_finds_a_move_completed_before_interrupt(self) -> None:
        plan, paths = self.disable_plan(2)
        real_rename = switching._rename_noreplace
        interrupted = False

        def rename_then_interrupt(source: Path, target: Path) -> None:
            nonlocal interrupted
            real_rename(source, target)
            if not interrupted and str(target).endswith(DISABLED_SUFFIX):
                interrupted = True
                raise KeyboardInterrupt("simulated asynchronous interruption")

        with mock.patch(
            "vampip.switching._rename_noreplace",
            side_effect=rename_then_interrupt,
        ):
            with self.assertRaisesRegex(
                KeyboardInterrupt,
                "asynchronous interruption",
            ):
                apply_switch(
                    self.state,
                    self.addons,
                    plan,
                    run_name="interrupted-after-rename",
                    allow_disable=True,
                )

        self.assertTrue(all(path.is_file() for path in paths))
        manifest = next((self.state / "manager-runs").glob("*.json"))
        document = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(document["status"], "rolled-back")
        self.assertEqual(document["completed_count"], 1)
        self.assertEqual(document["rolled_back_count"], 1)

    def test_format_2_rollback_preflights_every_move_before_mutation(self) -> None:
        plan, paths = self.disable_plan(2)
        manifest = apply_switch(
            self.state,
            self.addons,
            plan,
            run_name="conflict",
            allow_disable=True,
        )
        self.assertIsNotNone(manifest)
        targets = [Path(f"{path}{DISABLED_SUFFIX}") for path in paths]
        paths[0].write_bytes(targets[0].read_bytes())

        inspection = inspect_switch(Path(manifest))
        self.assertEqual(inspection["state_counts"], {"conflict": 1, "target": 1})
        self.assertEqual(inspection["unsafe_count"], 1)
        self.assertFalse(inspection["safe_to_rollback"])
        with self.assertRaisesRegex(ValueError, "not fully applied.*conflict"):
            rollback_switch(Path(manifest))

        # The second move was not rolled back before the conflict was found.
        self.assertFalse(paths[1].exists())
        self.assertTrue(targets[1].is_file())

    def test_interrupted_applying_switch_can_be_inspected_and_rolled_back(
        self,
    ) -> None:
        plan, paths = self.disable_plan(3)
        manifest = apply_switch(
            self.state,
            self.addons,
            plan,
            run_name="interrupted",
            allow_disable=True,
        )
        self.assertIsNotNone(manifest)
        manifest = Path(manifest)
        document = json.loads(manifest.read_text(encoding="utf-8"))

        # Model a crash after the first move. The canonical plan remains in
        # applying state, later moves are still at their sources, and the last
        # append-only event is torn.
        document["status"] = "applying"
        document["completed_count"] = 1
        document.pop("completed_utc", None)
        manifest.write_text(json.dumps(document), encoding="utf-8")
        for path in paths[1:]:
            switching._rename_noreplace(
                Path(f"{path}{DISABLED_SUFFIX}"),
                path,
            )
        progress_path = manifest.parent / document["progress_file"]
        with progress_path.open("ab") as progress:
            progress.write(b'{"event":"torn')

        inspection = inspect_switch(manifest)
        self.assertEqual(
            inspection["state_counts"],
            {"target": 1, "source": 2},
        )
        self.assertTrue(inspection["safe_to_rollback"])
        self.assertEqual(rollback_switch(manifest), 1)
        self.assertTrue(all(path.is_file() for path in paths))
        self.assertEqual(
            json.loads(manifest.read_text(encoding="utf-8"))["status"],
            "rolled-back",
        )
        progress_lines = progress_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("manual-rollback-complete" in line for line in progress_lines))

    def test_switch_never_overwrites_a_target_created_during_rename(self) -> None:
        plan, paths = self.disable_plan(2)
        real_rename = switching._rename_noreplace
        forward_moves = 0

        def inject_target(source: Path, target: Path) -> None:
            nonlocal forward_moves
            if target.parent == self.addons and str(target).endswith(DISABLED_SUFFIX):
                forward_moves += 1
                if forward_moves == 2:
                    target.write_bytes(b"injected-target")
            real_rename(source, target)

        with mock.patch(
            "vampip.switching._rename_noreplace",
            side_effect=inject_target,
        ):
            with self.assertRaises(FileExistsError):
                apply_switch(
                    self.state,
                    self.addons,
                    plan,
                    run_name="no-clobber-apply",
                    allow_disable=True,
                )

        self.assertTrue(paths[0].is_file())
        self.assertTrue(paths[1].is_file())
        self.assertEqual(
            Path(f"{paths[1]}{DISABLED_SUFFIX}").read_bytes(),
            b"injected-target",
        )
        manifest = next((self.state / "manager-runs").glob("*.json"))
        self.assertEqual(
            json.loads(manifest.read_text(encoding="utf-8"))["status"],
            "rollback-failed",
        )
        self.assertGreater(inspect_switch(manifest)["unsafe_count"], 0)

    def test_rollback_never_overwrites_a_source_created_during_rename(self) -> None:
        plan, paths = self.disable_plan(1)
        manifest = apply_switch(
            self.state,
            self.addons,
            plan,
            run_name="no-clobber-rollback",
            allow_disable=True,
        )
        self.assertIsNotNone(manifest)
        target = Path(f"{paths[0]}{DISABLED_SUFFIX}")
        real_rename = switching._rename_noreplace

        def inject_source(source: Path, destination: Path) -> None:
            destination.write_bytes(b"injected-source")
            real_rename(source, destination)

        with mock.patch(
            "vampip.switching._rename_noreplace",
            side_effect=inject_source,
        ):
            with self.assertRaises(FileExistsError):
                rollback_switch(Path(manifest))

        self.assertEqual(paths[0].read_bytes(), b"injected-source")
        self.assertTrue(target.is_file())
        self.assertEqual(
            json.loads(Path(manifest).read_text(encoding="utf-8"))["status"],
            "rollback-failed",
        )

    def test_rollback_refuses_a_manifest_pointing_at_another_progress_file(
        self,
    ) -> None:
        plan, _ = self.disable_plan(1)
        manifest = apply_switch(
            self.state,
            self.addons,
            plan,
            run_name="progress-path",
            allow_disable=True,
        )
        self.assertIsNotNone(manifest)
        manifest = Path(manifest)
        victim = manifest.parent / "unrelated.log"
        victim.write_bytes(b"preserve-me")
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["progress_file"] = victim.name
        manifest.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid progress journal"):
            rollback_switch(manifest)
        self.assertEqual(victim.read_bytes(), b"preserve-me")

    def test_switch_refuses_before_journalling_without_no_clobber_rename(
        self,
    ) -> None:
        plan, paths = self.disable_plan(1)
        with mock.patch("vampip.switching._RENAMEAT2", None):
            with self.assertRaisesRegex(OSError, "RENAME_NOREPLACE"):
                apply_switch(
                    self.state,
                    self.addons,
                    plan,
                    run_name="unsupported-runtime",
                    allow_disable=True,
                )
        self.assertTrue(paths[0].is_file())
        self.assertFalse((self.state / "manager-runs").exists())

    def test_move_classifier_detects_missing_and_replaced_files(self) -> None:
        plan, paths = self.disable_plan(1)
        row = plan.to_disable[0]
        source = paths[0]
        target = Path(f"{source}{DISABLED_SUFFIX}")
        entry = {
            "source": str(source),
            "target": str(target),
            "device": row["device"],
            "inode": row["inode"],
            "size": row["size"],
            "mtime_ns": row["mtime_ns"],
        }
        self.assertEqual(classify_switch_move(entry), "source")
        source.replace(target)
        self.assertEqual(classify_switch_move(entry), "target")
        target.unlink()
        self.assertEqual(classify_switch_move(entry), "missing")
        source.write_bytes(b"replacement")
        self.assertEqual(classify_switch_move(entry), "source-changed")

    def test_format_1_rollback_remains_compatible_and_refuses_superseded(
        self,
    ) -> None:
        source = self.addons / "Legacy.Package.1.var"
        target = Path(f"{source}{DISABLED_SUFFIX}")
        source.write_bytes(b"legacy")
        source.replace(target)
        manifest = self.state / "legacy.json"
        self.state.mkdir()
        document = {
            "format": 1,
            "kind": "manager-switch",
            "addon_dir": str(self.addons.resolve()),
            "status": "complete",
            "moves": [
                {
                    "action": "disable",
                    "source": str(source.resolve()),
                    "target": str(target.resolve()),
                    "status": "complete",
                }
            ],
        }
        manifest.write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(rollback_switch(manifest), 1)
        self.assertTrue(source.is_file())

        source.replace(target)
        document["status"] = "superseded"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "superseded"):
            rollback_switch(manifest)
        self.assertTrue(target.is_file())


if __name__ == "__main__":
    unittest.main()

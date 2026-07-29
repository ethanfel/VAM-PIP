from __future__ import annotations

import unittest
from pathlib import Path
import json
import tempfile
from unittest import mock

from vampip.body_proportions import (
    build_analysis,
    normalize_regions,
    signature_from_live,
    signature_from_manifest,
)
from vampip.bridge import (
    bridge_directory,
    request_person_body_proportions,
    request_undo_person_body_proportions,
)
from vampip.service import ManagerService


def _person() -> dict[str, object]:
    points = {
        "left-shoulder": (-0.2, 1.4, 0.0),
        "right-shoulder": (0.2, 1.4, 0.0),
        "left-elbow": (-0.5, 1.4, 0.0),
        "right-elbow": (0.5, 1.4, 0.0),
        "left-wrist": (-0.75, 1.4, 0.0),
        "right-wrist": (0.75, 1.4, 0.0),
        "left-hip": (-0.15, 0.9, 0.0),
        "right-hip": (0.15, 0.9, 0.0),
        "left-knee": (-0.15, 0.45, 0.0),
        "right-knee": (0.15, 0.45, 0.0),
        "left-ankle": (-0.15, 0.0, 0.0),
        "right-ankle": (0.15, 0.0, 0.0),
        "neck": (0.0, 1.5, 0.0),
    }
    return {
        "keypointNames": list(points),
        "keypoints3d": [list(point) for point in points.values()],
    }


def _live_status() -> dict[str, object]:
    return {
        "ready": True,
        "revision": "a" * 32,
        "measurements": {
            "upperArm": 0.27,
            "forearm": 0.24,
            "thigh": 0.41,
            "shin": 0.41,
            "torso": 0.56,
            "shoulderSpan": 0.35,
            "hipSpan": 0.30,
        },
        "morphs": [
            {
                "key": "1" * 32,
                "name": "Legs Length",
                "region": "Pose/General",
                "value": 0.0,
                "min": -1.0,
                "max": 1.0,
            },
            {
                "key": "2" * 32,
                "name": "Upper Body Length",
                "region": "Pose/General",
                "value": 0.0,
                "min": -1.0,
                "max": 1.0,
            },
            {
                "key": "3" * 32,
                "name": "Shoulder Width",
                "region": "Pose/General",
                "value": 0.0,
                "min": -1.0,
                "max": 1.0,
            },
        ],
        "undoAvailable": False,
    }


class BodyProportionTests(unittest.TestCase):
    def test_legacy_manifest_uses_named_landmark_distances(self) -> None:
        signature = signature_from_manifest({"people": [_person()]}, 0)

        self.assertEqual(signature["space"], "mhr-landmark-distance-fallback")
        measurements = signature["measurements"]
        self.assertAlmostEqual(measurements["upperArm"]["meters"], 0.3)
        self.assertAlmostEqual(measurements["forearm"]["meters"], 0.25)
        self.assertAlmostEqual(measurements["thigh"]["meters"], 0.45)
        self.assertAlmostEqual(measurements["shin"]["meters"], 0.45)
        self.assertAlmostEqual(measurements["shoulderSpan"]["meters"], 0.4)
        self.assertAlmostEqual(measurements["hipSpan"]["meters"], 0.3)
        self.assertAlmostEqual(
            sum(
                measurements[name]["ratio"]
                for name in ("torso", "thigh", "shin")
            ),
            1.0,
        )

    def test_embedded_signature_is_rebased_to_comparable_structure(self) -> None:
        person = _person()
        person["bodyProportions"] = {
            "schema": 1,
            "space": "mhr-neutral-bind",
            "normalizer": {"id": "stature", "meters": 1.7},
            "measurements": {
                "upperArm": {"meters": 0.30, "confidence": 0.9},
                "forearm": {"meters": 0.25, "confidence": 0.9},
                "thigh": {"meters": 0.45, "confidence": 0.9},
                "shin": {"meters": 0.45, "confidence": 0.9},
                "torso": {"meters": 0.60, "confidence": 0.9},
                "shoulderSpan": {"meters": 0.40, "confidence": 0.8},
                "hipSpan": {"meters": 0.30, "confidence": 0.8},
            },
            "overallConfidence": 0.85,
        }

        signature = signature_from_manifest({"people": [person]}, 0)

        self.assertEqual(signature["space"], "mhr-neutral-bind")
        self.assertEqual(signature["normalizer"]["id"], "structural-length")
        self.assertAlmostEqual(signature["normalizer"]["meters"], 1.5)

    def test_analysis_proposes_only_loaded_bounded_morphs(self) -> None:
        target = signature_from_manifest({"people": [_person()]}, 0)
        status = _live_status()
        live = signature_from_live(status)

        result = build_analysis(
            target,
            live,
            status,
            strength=1.0,
            regions=normalize_regions(["arms", "legs", "torso", "widths"]),
        )

        self.assertTrue(result["ready"])
        self.assertLessEqual(len(result["changes"]), 8)
        self.assertTrue(
            all(abs(change["delta"]) <= 0.25 for change in result["changes"])
        )
        self.assertTrue(
            all(change["name"] != "Arms Short" for change in result["changes"])
        )
        self.assertTrue(
            any(item["region"] == "arms" for item in result["unavailable"])
        )
        self.assertNotIn("preserveHeight", result)
        self.assertIn("final height", result["warning"])

    def test_analysis_rejects_ambiguous_or_already_applied_morphs(self) -> None:
        target = signature_from_manifest({"people": [_person()]}, 0)
        status = _live_status()
        status["morphs"].append(
            {
                **status["morphs"][0],
                "key": "4" * 32,
            }
        )
        result = build_analysis(
            target,
            signature_from_live(status),
            status,
            strength=1.0,
            regions=normalize_regions(["legs"]),
        )
        self.assertFalse(result["canApply"])
        self.assertIn(
            "Multiple verified Legs Length",
            result["unavailable"][0]["reason"],
        )

        status = _live_status()
        status["undoAvailable"] = True
        result = build_analysis(
            target,
            signature_from_live(status),
            status,
            strength=1.0,
            regions=normalize_regions(["legs"]),
        )
        self.assertFalse(result["canApply"])
        self.assertTrue(result["undoAvailable"])

    def test_invalid_live_measurement_and_region_are_rejected(self) -> None:
        status = _live_status()
        status["measurements"]["shin"] = float("nan")
        with self.assertRaises(ValueError):
            signature_from_live(status)
        with self.assertRaises(ValueError):
            normalize_regions(["face"])


class BodyProportionBridgeRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vam_root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self) -> dict[str, object]:
        return json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )

    def test_apply_uses_only_opaque_revisioned_morph_changes(self) -> None:
        request_person_body_proportions(
            self.vam_root,
            target_uid="Person",
            expected_revision="a" * 32,
            changes=[{"key": "b" * 32, "value": 0.125}],
        )

        request = self.request()
        self.assertEqual(request["command"], "setPersonBodyProportions")
        self.assertEqual(request["targetUid"], "Person")
        self.assertEqual(request["expectedRevision"], "a" * 32)
        self.assertEqual(
            request["changes"],
            [{"key": "b" * 32, "value": 0.125}],
        )
        self.assertNotIn("name", json.dumps(request).casefold())

    def test_apply_rejects_duplicate_or_unbounded_changes(self) -> None:
        with self.assertRaises(ValueError):
            request_person_body_proportions(
                self.vam_root,
                target_uid="Person",
                expected_revision="a" * 32,
                changes=[
                    {"key": "b" * 32, "value": 0.1},
                    {"key": "b" * 32, "value": 0.2},
                ],
            )
        with self.assertRaises(ValueError):
            request_person_body_proportions(
                self.vam_root,
                target_uid="Person",
                expected_revision="a" * 32,
                changes=[{"key": "b" * 32, "value": float("inf")}],
            )

    def test_undo_is_bound_to_target_and_catalog_revision(self) -> None:
        request_undo_person_body_proportions(
            self.vam_root,
            target_uid="Person",
            expected_revision="c" * 32,
        )

        request = self.request()
        self.assertEqual(request["command"], "undoPersonBodyProportions")
        self.assertEqual(request["targetUid"], "Person")
        self.assertEqual(request["expectedRevision"], "c" * 32)


class BodyProportionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        addons = root / "VaM" / "AddonPackages"
        addons.mkdir(parents=True)
        self.service = ManagerService(
            addons,
            root / "state",
            process_probe=lambda: [],
        )
        self.job_id = "d" * 32
        self.job_revision = "e" * 32
        self.body = _live_status()
        self.scene = {
            "available": True,
            "vam_running": True,
            "atoms": [{"uid": "Person", "type": "Person"}],
            "persons": [
                {
                    "uid": "Person",
                    "selected": True,
                    "bodyProportions": self.body,
                }
            ],
            "sam3d": {"applied": False},
        }
        self.manager = mock.Mock()
        self.manager.get.return_value = {
            "id": self.job_id,
            "state": "succeeded",
            "revision": self.job_revision,
        }
        self.manager.manifest.return_value = {
            "jobId": self.job_id,
            "revision": self.job_revision,
            "people": [_person()],
        }

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def analysis(self) -> dict[str, object]:
        with (
            mock.patch.object(
                self.service,
                "_require_live_capability",
                return_value=self.scene,
            ),
            mock.patch.object(
                self.service,
                "_sam3d",
                return_value=self.manager,
            ),
        ):
            return self.service.sam3d_body_proportions(
                self.job_id,
                target_uid="Person",
                strength=0.5,
            )

    def test_analysis_is_revision_bound_and_keeps_physics_out(self) -> None:
        result = self.analysis()

        self.assertEqual(result["job_revision"], self.job_revision)
        self.assertRegex(result["analysis_revision"], r"^[0-9a-f]{32}$")
        self.assertNotIn("preserveHeight", result)
        self.assertIn("physics", result["warning"])
        self.assertEqual(result["proposed_morphs"], result["changes"])

    def test_apply_recomputes_analysis_and_queues_only_opaque_changes(self) -> None:
        analysis = self.analysis()
        with (
            mock.patch.object(
                self.service,
                "_require_live_capability",
                return_value=self.scene,
            ),
            mock.patch.object(
                self.service,
                "_sam3d",
                return_value=self.manager,
            ),
        ):
            result = self.service.apply_sam3d_body_proportions(
                self.job_id,
                expected_job_revision=self.job_revision,
                expected_analysis_revision=analysis["analysis_revision"],
                target_uid="Person",
                strength=0.5,
            )

        self.assertEqual(result["action_state"], "queued")
        request = json.loads(
            (
                bridge_directory(self.service.vam_root) / "request.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(request["command"], "setPersonBodyProportions")
        self.assertEqual(request["expectedRevision"], self.body["revision"])
        self.assertNotIn("name", json.dumps(request).casefold())

    def test_analysis_rejects_morphing_under_an_applied_pose(self) -> None:
        self.scene["sam3d"] = {"applied": True}

        result = self.analysis()

        self.assertFalse(result["can_apply"])
        self.assertIn("Undo", result["apply_blocked_reason"])

    def test_analysis_rejects_a_second_fit_until_person_undo(self) -> None:
        self.body["undoAvailable"] = True
        self.body["undoRevision"] = "f" * 32

        result = self.analysis()

        self.assertTrue(result["person_fit_active"])
        self.assertFalse(result["can_apply"])
        self.assertTrue(result["can_undo"])
        self.assertIn("one-level", result["apply_blocked_reason"])


if __name__ == "__main__":
    unittest.main()

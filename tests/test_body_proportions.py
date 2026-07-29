from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
import json
import tempfile
from unittest import mock

from vampip.body_proportions import (
    build_analysis,
    consensus_body_signatures,
    normalize_regions,
    signature_from_live,
    signature_from_manifest,
)
from vampip.bridge import (
    bridge_directory,
    request_person_body_proportions,
    request_undo_person_body_proportions,
)
from vampip.sam3d import Sam3dJobError
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
        "bodyShapeReady": True,
        "bodyShapePreparing": False,
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


def _neutral_signature(
    *,
    values: dict[str, float] | None = None,
    confidences: dict[str, float] | None = None,
    scale: float = 1.0,
) -> dict[str, object]:
    meters = {
        "upperArm": 0.30,
        "forearm": 0.25,
        "thigh": 0.45,
        "shin": 0.45,
        "torso": 0.60,
        "shoulderSpan": 0.40,
        "hipSpan": 0.30,
    }
    meters.update(values or {})
    quality = {metric: 0.8 for metric in meters}
    quality.update(confidences or {})
    measurements: dict[str, dict[str, float]] = {}
    for metric, value in meters.items():
        item = {
            "meters": value * scale,
            "confidence": quality[metric],
        }
        if metric in {"upperArm", "forearm", "thigh", "shin"}:
            item["leftMeters"] = value * scale
            item["rightMeters"] = value * scale
        measurements[metric] = item
    person = _person()
    person["bodyProportions"] = {
        "schema": 1,
        "space": "mhr-neutral-bind",
        "normalizer": {"id": "stature", "meters": 1.70 * scale},
        "measurements": measurements,
        "overallConfidence": sum(quality.values()) / len(quality),
    }
    return signature_from_manifest({"people": [person]}, 0)


def _person_with_body_signature(
    signature: dict[str, object],
) -> dict[str, object]:
    person = _person()
    person["bodyProportions"] = signature
    return person


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

    def test_single_signature_consensus_preserves_exact_behavior(self) -> None:
        signature = _neutral_signature()

        consensus = consensus_body_signatures(
            [signature],
            source_ids=["1" * 32],
        )

        self.assertIs(consensus, signature)
        self.assertNotIn("consensus", consensus)

    def test_consensus_rejects_an_obvious_metric_outlier_and_tracks_sources(
        self,
    ) -> None:
        signatures = [
            _neutral_signature(values={"upperArm": 0.300}),
            _neutral_signature(values={"upperArm": 0.306}),
            _neutral_signature(
                values={"upperArm": 0.720},
                confidences={"upperArm": 1.0},
            ),
        ]
        original = json.dumps(signatures, sort_keys=True)

        consensus = consensus_body_signatures(
            signatures,
            source_ids=["1" * 32, "2" * 32, "3" * 32],
        )

        self.assertEqual(json.dumps(signatures, sort_keys=True), original)
        self.assertEqual(consensus["schema"], 1)
        self.assertEqual(consensus["space"], "mhr-neutral-bind")
        self.assertAlmostEqual(
            consensus["measurements"]["upperArm"]["meters"],
            0.303,
            places=6,
        )
        report = consensus["consensus"]
        self.assertEqual(report["sourceCount"], 3)
        self.assertEqual(
            [source["jobId"] for source in report["sources"]],
            ["1" * 32, "2" * 32, "3" * 32],
        )
        upper_arm = report["measurements"]["upperArm"]
        self.assertEqual(upper_arm["usedSourceIndices"], [0, 1])
        self.assertEqual(upper_arm["rejectedSourceIndices"], [2])
        self.assertEqual(upper_arm["usedCount"], 2)
        self.assertGreater(upper_arm["inputRelativeRange"], 1.0)
        self.assertEqual(report["rejectedMeasurementCount"], 1)
        self.assertIn("not a learned probability", report["confidenceSemantics"])

    def test_consensus_uses_bounded_confidence_weight_and_reports_disagreement(
        self,
    ) -> None:
        consensus = consensus_body_signatures(
            [
                _neutral_signature(
                    values={"upperArm": 0.30},
                    confidences={"upperArm": 0.0},
                ),
                _neutral_signature(
                    values={"upperArm": 0.40},
                    confidences={"upperArm": 1.0},
                ),
            ]
        )

        upper_arm = consensus["measurements"]["upperArm"]
        self.assertGreater(upper_arm["meters"], 0.35)
        self.assertLess(upper_arm["meters"], 0.40)
        report = consensus["consensus"]["measurements"]["upperArm"]
        self.assertEqual(report["usedSourceIndices"], [0, 1])
        self.assertEqual(report["rejectedSourceIndices"], [])
        self.assertGreater(report["relativeDisagreement"], 0.0)
        self.assertGreater(
            consensus["consensus"]["maximumRelativeDisagreement"],
            0.0,
        )

    def test_consensus_is_scale_invariant_and_bounds_input_contract(self) -> None:
        baseline = _neutral_signature()
        consensus = consensus_body_signatures(
            [baseline, _neutral_signature(scale=1.25)]
        )

        for metric in baseline["measurements"]:
            self.assertAlmostEqual(
                consensus["measurements"][metric]["ratio"],
                baseline["measurements"][metric]["ratio"],
            )
        with self.assertRaisesRegex(ValueError, "1 to 8"):
            consensus_body_signatures([])
        with self.assertRaisesRegex(ValueError, "1 to 8"):
            consensus_body_signatures([baseline] * 9)
        with self.assertRaisesRegex(ValueError, "unique"):
            consensus_body_signatures(
                [baseline, baseline],
                source_ids=["1" * 32, "1" * 32],
            )
        non_neutral = signature_from_live(_live_status())
        with self.assertRaisesRegex(ValueError, "neutral"):
            consensus_body_signatures([baseline, non_neutral])


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

    def multi_reference_analysis(
        self,
        manifests: dict[str, dict[str, object]],
        references: str,
    ) -> dict[str, object]:
        self.manager.get.side_effect = lambda job_id: {
            "id": job_id,
            "state": "succeeded",
            "revision": manifests[job_id]["revision"],
        }
        self.manager.manifest.side_effect = lambda job_id: manifests[job_id]
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
                references=references,
                strength=0.5,
            )

    def test_analysis_is_revision_bound_and_keeps_physics_out(self) -> None:
        result = self.analysis()

        self.assertEqual(result["job_revision"], self.job_revision)
        self.assertRegex(result["analysis_revision"], r"^[0-9a-f]{32}$")
        self.assertNotIn("preserveHeight", result)
        self.assertIn("physics", result["warning"])
        self.assertEqual(result["proposed_morphs"], result["changes"])

    def test_succeeded_job_list_and_detail_publish_body_reference_support(
        self,
    ) -> None:
        neutral = _person_with_body_signature(_neutral_signature())
        manifest = {
            "jobId": self.job_id,
            "revision": self.job_revision,
            "people": [neutral, _person()],
        }
        job = {
            "id": self.job_id,
            "state": "succeeded",
            "revision": self.job_revision,
        }
        self.manager.list.return_value = {
            "items": [job],
            "limit": 30,
            "offset": 0,
        }
        self.manager.get.return_value = job
        self.manager.manifest.return_value = manifest
        expected = [
            {
                "person_index": 0,
                "space": "mhr-neutral-bind",
                "multi_reference": True,
            },
            {
                "person_index": 1,
                "space": "mhr-landmark-distance-fallback",
                "multi_reference": False,
            },
        ]

        with (
            mock.patch.object(
                self.service,
                "_sam3d",
                return_value=self.manager,
            ),
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value={},
            ),
        ):
            listed = self.service.sam3d_jobs()["items"][0]
            with mock.patch.object(
                self.service,
                "_sync_sam3d_capture_history",
                return_value=job,
            ):
                detailed = self.service.sam3d_job(self.job_id)

        self.assertEqual(listed["body_reference_support"], expected)
        self.assertEqual(detailed["body_reference_support"], expected)
        self.assertEqual(self.manager.manifest.call_count, 2)

    def test_body_reference_support_is_bounded_and_fails_closed(self) -> None:
        oversized = {
            "people": [
                _person_with_body_signature(_neutral_signature())
                for _ in range(40)
            ]
        }
        support = self.service._sam3d_body_reference_support_from_manifest(
            oversized
        )
        self.assertEqual(len(support), 32)
        self.assertTrue(all(item["multi_reference"] for item in support))

        job = {
            "id": self.job_id,
            "state": "succeeded",
            "revision": self.job_revision,
        }
        self.manager.list.return_value = {"items": [job]}
        self.manager.manifest.side_effect = Sam3dJobError("unreadable")
        with (
            mock.patch.object(
                self.service,
                "_sam3d",
                return_value=self.manager,
            ),
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value={},
            ),
        ):
            listed = self.service.sam3d_jobs()["items"][0]
        self.assertEqual(listed["body_reference_support"], [])

    def test_multi_reference_validation_rejects_bad_reference_sets(self) -> None:
        other_job_id = "f" * 32
        cases = (
            (
                "malformed",
                "not-a-reference",
                "only <32hex-job-id>:<body-index>",
            ),
            (
                "duplicate job",
                f"{self.job_id}:0,{self.job_id}:1",
                "duplicate SAM3D job",
            ),
            (
                "non-primary first reference",
                f"{other_job_id}:0,{self.job_id}:0",
                "first body reference must match",
            ),
        )

        for label, references, expected_error in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.service.sam3d_body_proportions(
                        self.job_id,
                        target_uid="Person",
                        references=references,
                    )

    def test_multi_reference_names_every_incompatible_legacy_job(self) -> None:
        secondary_job_id = "f" * 32
        manifests = {
            self.job_id: {
                "jobId": self.job_id,
                "revision": self.job_revision,
                "people": [_person()],
            },
            secondary_job_id: {
                "jobId": secondary_job_id,
                "revision": "1" * 32,
                "people": [_person()],
            },
        }
        references = f"{self.job_id}:0,{secondary_job_id}:0"

        with self.assertRaisesRegex(
            ValueError,
            (
                "Incompatible SAM3D job IDs: "
                f"{self.job_id}, {secondary_job_id}"
            ),
        ):
            self.multi_reference_analysis(manifests, references)

    def test_two_reference_analysis_reports_canonical_provenance(self) -> None:
        secondary_job_id = "f" * 32
        secondary_revision = "1" * 32
        primary_signature = _neutral_signature(
            values={"upperArm": 0.30},
        )
        secondary_signature = _neutral_signature(
            values={"upperArm": 0.33},
        )
        manifests = {
            self.job_id: {
                "jobId": self.job_id,
                "revision": self.job_revision,
                "people": [_person_with_body_signature(primary_signature)],
            },
            secondary_job_id: {
                "jobId": secondary_job_id,
                "revision": secondary_revision,
                "people": [
                    _person(),
                    _person_with_body_signature(secondary_signature),
                ],
            },
        }
        references = f"{self.job_id}:0,{secondary_job_id}:1"

        result = self.multi_reference_analysis(manifests, references)

        provenance = [
            {
                "job_id": item["job_id"],
                "person_index": item["person_index"],
                "job_revision": item["job_revision"],
            }
            for item in result["reference_jobs"]
        ]
        self.assertEqual(
            provenance,
            [
                {
                    "job_id": self.job_id,
                    "person_index": 0,
                    "job_revision": self.job_revision,
                },
                {
                    "job_id": secondary_job_id,
                    "person_index": 1,
                    "job_revision": secondary_revision,
                },
            ],
        )
        self.assertEqual(result["reference_count"], 2)
        self.assertTrue(
            all(
                isinstance(item["confidence"], float)
                for item in result["reference_jobs"]
            )
        )
        expected_reference_revision = hashlib.sha256(
            json.dumps(
                result["reference_jobs"],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()[:32]
        self.assertEqual(
            result["reference_set_revision"],
            expected_reference_revision,
        )
        self.assertEqual(result["job_revision"], self.job_revision)
        self.assertEqual(result["target"]["consensus"]["sourceCount"], 2)
        self.assertEqual(
            [
                item["jobId"]
                for item in result["target"]["consensus"]["sources"]
            ],
            [self.job_id, secondary_job_id],
        )
        self.assertRegex(result["analysis_revision"], r"^[0-9a-f]{32}$")

    def test_any_reference_revision_invalidates_the_analysis(self) -> None:
        secondary_job_id = "f" * 32
        references = f"{self.job_id}:0,{secondary_job_id}:1"
        people = {
            self.job_id: [
                _person_with_body_signature(_neutral_signature()),
            ],
            secondary_job_id: [
                _person(),
                _person_with_body_signature(
                    _neutral_signature(values={"forearm": 0.27}),
                ),
            ],
        }

        def manifests(
            primary_revision: str,
            secondary_revision: str,
        ) -> dict[str, dict[str, object]]:
            return {
                self.job_id: {
                    "jobId": self.job_id,
                    "revision": primary_revision,
                    "people": people[self.job_id],
                },
                secondary_job_id: {
                    "jobId": secondary_job_id,
                    "revision": secondary_revision,
                    "people": people[secondary_job_id],
                },
            }

        baseline = self.multi_reference_analysis(
            manifests(self.job_revision, "1" * 32),
            references,
        )
        changed_revisions = (
            ("primary", "2" * 32, "1" * 32),
            ("secondary", self.job_revision, "3" * 32),
        )
        for label, primary_revision, secondary_revision in changed_revisions:
            with self.subTest(reference=label):
                changed = self.multi_reference_analysis(
                    manifests(primary_revision, secondary_revision),
                    references,
                )
                self.assertNotEqual(
                    changed["reference_set_revision"],
                    baseline["reference_set_revision"],
                )
                self.assertNotEqual(
                    changed["analysis_revision"],
                    baseline["analysis_revision"],
                )

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

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from vampip.body_shape import (
    build_body_shape_analysis,
    normalize_shape_regions,
)
from vampip.bridge import bridge_directory
from vampip.sam3d_body_shape import (
    BODY_SHAPE_METRICS,
    BODY_SHAPE_REGION_METRICS,
    validate_body_shape,
)
from vampip.service import ManagerService, _public_body_proportions


_REGION_FOR_METRIC = {
    metric: region
    for region, metrics in BODY_SHAPE_REGION_METRICS.items()
    for metric in metrics
}
_BILATERAL_METRICS = {
    "upperThighGirth",
    "upperThighWidth",
    "upperThighDepth",
}


def _shape_signature(
    *,
    changed: dict[str, float] | None = None,
) -> dict[str, object]:
    normalizer = 1.5
    ratios = {
        "bustGirth": 0.58,
        "bustWidth": 0.25,
        "bustDepth": 0.18,
        "underbustGirth": 0.49,
        "underbustWidth": 0.23,
        "underbustDepth": 0.14,
        "breastGirthExcess": 0.09,
        "breastDepthExcess": 0.04,
        "breastProjection": 0.035,
        "waistGirth": 0.43,
        "waistWidth": 0.20,
        "waistDepth": 0.13,
        "seatGirth": 0.62,
        "seatWidth": 0.29,
        "seatDepth": 0.20,
        "gluteProjection": 0.045,
        "upperThighGirth": 0.34,
        "upperThighWidth": 0.15,
        "upperThighDepth": 0.12,
    }
    ratios.update(changed or {})
    regions = {
        region: {
            "geometryConfidence": 0.8,
            "evidenceConfidence": 0.7,
            "confidence": 0.7,
        }
        for region in BODY_SHAPE_REGION_METRICS
    }
    measurements: dict[str, dict[str, float]] = {}
    for metric in BODY_SHAPE_METRICS:
        meters = ratios[metric] * normalizer
        item = {
            "meters": meters,
            "ratio": ratios[metric],
            "confidence": regions[_REGION_FOR_METRIC[metric]]["confidence"],
        }
        if metric in _BILATERAL_METRICS:
            item["leftMeters"] = meters
            item["rightMeters"] = meters
        measurements[metric] = item
    result: dict[str, object] = {
        "schema": 1,
        "space": "mhr-neutral-bind",
        "normalizer": {"id": "structural-length", "meters": normalizer},
        "confidenceKind": "heuristic-evidence-consistency",
        "measurements": measurements,
        "regions": regions,
        "planes": {
            "bustTorsoFraction": 0.68,
            "underbustTorsoFraction": 0.57,
            "waistTorsoFraction": 0.45,
            "seatTorsoFraction": 0.02,
            "upperThighLegFraction": 0.35,
        },
        "overallConfidence": 0.7,
    }
    validate_body_shape(result)
    return result


def _shape_morph(
    key: str,
    name: str,
    region: str,
    responses: dict[str, float],
    *,
    built_in: bool = True,
) -> dict[str, object]:
    return {
        "key": key,
        "name": name,
        "region": "Morph/Universal",
        "fitKind": "shape",
        "shapeRegion": region,
        "shapeResponses": responses,
        "builtIn": built_in,
        "value": 0.0,
        "min": -1.0,
        "max": 1.0,
    }


def _person() -> dict[str, object]:
    points = {
        "left-shoulder": (-0.2, 1.4, 0.0),
        "right-shoulder": (0.2, 1.4, 0.0),
        "left-elbow": (-0.5, 1.4, 0.0),
        "right-elbow": (0.5, 1.4, 0.0),
        "left-wrist": (-0.75, 1.4, 0.0),
        "right-wrist": (0.75, 1.4, 0.0),
        "left-hip": (-0.15, 1.1, 0.0),
        "right-hip": (0.15, 1.1, 0.0),
        "left-knee": (-0.15, 0.5, 0.0),
        "right-knee": (0.15, 0.5, 0.0),
        "left-ankle": (-0.15, 0.0, 0.0),
        "right-ankle": (0.15, 0.0, 0.0),
        "neck": (0.0, 1.5, 0.0),
    }
    return {
        "keypointNames": list(points),
        "keypoints3d": [list(point) for point in points.values()],
    }


def _live_body_status() -> dict[str, object]:
    current_shape = _shape_signature()
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
        "bodyShape": current_shape,
        "bodyShapeReady": True,
        "bodyShapePreparing": False,
        "morphs": [
            {
                "key": "1" * 32,
                "name": "Legs Length",
                "region": "Pose/General",
                "fitKind": "structure",
                "value": 0.0,
                "min": -1.0,
                "max": 1.0,
            },
            _shape_morph(
                "2" * 32,
                "Breasts Size",
                "breasts",
                {
                    "breastGirthExcess": 0.05,
                    "breastProjection": 0.03,
                },
            ),
        ],
        "undoAvailable": False,
    }


class BodyShapeSolverTests(unittest.TestCase):
    def test_solver_uses_only_verified_builtins_and_bounds_changes(self) -> None:
        live = _shape_signature()
        target = _shape_signature(
            changed={
                "breastGirthExcess": 0.13,
                "breastProjection": 0.055,
            }
        )
        status = _live_body_status()
        status["morphs"].append(
            _shape_morph(
                "3" * 32,
                "Breasts Size",
                "breasts",
                {"breastProjection": 1.0},
                built_in=False,
            )
        )

        result = build_body_shape_analysis(
            target,
            live,
            status,
            strength=1.0,
            regions=normalize_shape_regions(["breasts"]),
        )

        self.assertEqual(len(result["changes"]), 1)
        change = result["changes"][0]
        self.assertEqual(change["name"], "Breasts Size")
        self.assertEqual(change["fitKind"], "shape")
        self.assertLessEqual(abs(change["delta"]), 0.25)
        self.assertIn("Face morphs", result["warning"])

    def test_explicit_null_shape_regions_is_an_explicit_noop(self) -> None:
        self.assertEqual(normalize_shape_regions(None), frozenset())

    def test_empty_shape_regions_is_an_explicit_noop(self) -> None:
        result = build_body_shape_analysis(
            _shape_signature(),
            _shape_signature(),
            _live_body_status(),
            strength=0.5,
            regions=normalize_shape_regions([]),
        )
        self.assertEqual(result["regions"], [])
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["unavailable"], [])

    def test_morph_name_must_match_its_published_shape_region(self) -> None:
        status = _live_body_status()
        status["morphs"][1]["shapeRegion"] = "waist"
        result = build_body_shape_analysis(
            _shape_signature(
                changed={
                    "breastGirthExcess": 0.13,
                    "breastProjection": 0.055,
                }
            ),
            _shape_signature(),
            status,
            strength=1.0,
            regions=["breasts"],
        )

        self.assertEqual(result["changes"], [])
        self.assertEqual(result["unavailable"][0]["region"], "breasts")

    def test_each_allowlisted_shape_region_can_propose_its_exact_builtin(
        self,
    ) -> None:
        cases = (
            (
                "breasts",
                "Breasts Size",
                "breastGirthExcess",
                0.04,
            ),
            ("waist", "Waist Width", "waistGirth", 0.05),
            ("hips", "Hip Size", "seatWidth", 0.04),
            ("glutes", "Glutes Size", "gluteProjection", 0.03),
            ("thighs", "Thighs Size", "upperThighGirth", 0.04),
        )
        for index, (region, name, metric, response) in enumerate(cases):
            with self.subTest(region=region):
                status = _live_body_status()
                status["morphs"] = [
                    _shape_morph(
                        f"{index + 4:x}" * 32,
                        name,
                        region,
                        {metric: response},
                    )
                ]
                current = _shape_signature()
                current_ratio = current["measurements"][metric]["ratio"]
                target = _shape_signature(
                    changed={metric: current_ratio + response * 0.5}
                )
                result = build_body_shape_analysis(
                    target,
                    current,
                    status,
                    strength=1.0,
                    regions=[region],
                )

                self.assertEqual(
                    [change["name"] for change in result["changes"]],
                    [name],
                )

    def test_coupled_shape_morphs_are_solved_together(self) -> None:
        current = _shape_signature()
        target = _shape_signature(
            changed={
                "seatWidth": 0.31,
                "seatDepth": 0.22,
                "gluteProjection": 0.06,
            }
        )
        status = _live_body_status()
        status["morphs"] = [
            _shape_morph(
                "4" * 32,
                "Hip Size",
                "hips",
                {"seatWidth": 0.05, "seatDepth": 0.01},
            ),
            _shape_morph(
                "5" * 32,
                "Glutes Size",
                "glutes",
                {
                    "seatWidth": 0.01,
                    "seatDepth": 0.04,
                    "gluteProjection": 0.03,
                },
            ),
        ]
        result = build_body_shape_analysis(
            target,
            current,
            status,
            strength=1.0,
            regions=["hips", "glutes"],
        )

        self.assertEqual(
            {change["name"] for change in result["changes"]},
            {"Hip Size", "Glutes Size"},
        )

    def test_coupled_solver_preserves_a_region_that_already_matches(self) -> None:
        current = _shape_signature()
        target = _shape_signature(changed={"waistGirth": 0.48})
        status = _live_body_status()
        status["morphs"] = [
            _shape_morph(
                "6" * 32,
                "Waist Width",
                "waist",
                {"waistGirth": 0.05},
            ),
            _shape_morph(
                "7" * 32,
                "Hip Size",
                "hips",
                {"waistGirth": 0.05, "seatWidth": 0.05},
            ),
        ]
        result = build_body_shape_analysis(
            target,
            current,
            status,
            strength=1.0,
            regions=["waist", "hips"],
        )

        changes = {change["name"]: change["delta"] for change in result["changes"]}
        self.assertIn("Waist Width", changes)
        self.assertLess(abs(changes.get("Hip Size", 0.0)), 0.01)

    def test_public_scene_copy_preserves_only_valid_shape_contract(self) -> None:
        status = _live_body_status()
        status["bodyShapeReady"] = True
        status["bodyShapePreparing"] = False
        status["bodyShapeReason"] = "neutral mesh ready"
        status["undoPending"] = True
        public = _public_body_proportions(status)

        self.assertIsNotNone(public)
        assert public is not None
        self.assertTrue(public["bodyShapeReady"])
        self.assertFalse(public["bodyShapePreparing"])
        self.assertEqual(public["bodyShapeReason"], "neutral mesh ready")
        self.assertTrue(public["undoPending"])
        validate_body_shape(public["bodyShape"])
        shape_morph = next(
            morph for morph in public["morphs"] if morph.get("fitKind") == "shape"
        )
        self.assertTrue(shape_morph["builtIn"])
        self.assertEqual(shape_morph["shapeRegion"], "breasts")
        self.assertEqual(
            set(shape_morph["shapeResponses"]),
            {"breastGirthExcess", "breastProjection"},
        )

        simplejson = json.loads(
            json.dumps(status),
            parse_int=str,
            parse_float=str,
        )
        seat = simplejson["bodyShape"]["measurements"]["seatGirth"]
        seat["ratio"] = str(float(seat["ratio"]) + 5e-7)
        public = _public_body_proportions(simplejson)
        assert public is not None
        self.assertTrue(public["bodyShapeReady"])
        validate_body_shape(public["bodyShape"])
        self.assertIsInstance(
            public["bodyShape"]["measurements"]["bustGirth"]["meters"],
            float,
        )
        rejected_simplejson = json.loads(json.dumps(simplejson))
        rejected_seat = rejected_simplejson["bodyShape"]["measurements"]["seatGirth"]
        rejected_seat["ratio"] = str(float(rejected_seat["ratio"]) + 1e-3)
        rejected_public = _public_body_proportions(rejected_simplejson)
        assert rejected_public is not None
        self.assertNotIn("bodyShape", rejected_public)

        tampered = _live_body_status()
        tampered["bodyShape"] = dict(tampered["bodyShape"])
        tampered["bodyShape"]["unexpected"] = True
        public = _public_body_proportions(tampered)
        assert public is not None
        self.assertNotIn("bodyShape", public)

        preparing = _live_body_status()
        preparing.pop("bodyShape")
        preparing["bodyShapeReady"] = False
        preparing["bodyShapePreparing"] = True
        public = _public_body_proportions(preparing)
        assert public is not None
        self.assertFalse(public["bodyShapeReady"])
        self.assertTrue(public["bodyShapePreparing"])

        overflowed = _live_body_status()
        overflowed["bodyShape"] = dict(overflowed["bodyShape"])
        overflowed["bodyShape"]["normalizer"] = {
            "id": "structural-length",
            "meters": 10**400,
        }
        public = _public_body_proportions(overflowed)
        assert public is not None
        self.assertNotIn("bodyShape", public)


class BodyShapeServiceTests(unittest.TestCase):
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
        target_shape = _shape_signature(
            changed={
                "breastGirthExcess": 0.13,
                "breastProjection": 0.055,
            }
        )
        person = _person()
        person["bodyShape"] = target_shape
        self.manager = mock.Mock()
        self.manager.get.return_value = {
            "id": self.job_id,
            "state": "succeeded",
            "revision": self.job_revision,
        }
        self.manager.manifest.return_value = {
            "jobId": self.job_id,
            "revision": self.job_revision,
            "people": [person],
        }
        self.manager.body_shape.return_value = target_shape
        self.body = _live_body_status()
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

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def _analysis(self) -> dict[str, object]:
        with (
            mock.patch.object(
                self.service,
                "_require_live_capability",
                return_value=self.scene,
            ) as capability,
            mock.patch.object(
                self.service,
                "_sam3d",
                return_value=self.manager,
            ),
        ):
            result = self.service.sam3d_body_proportions(
                self.job_id,
                target_uid="Person",
                strength=0.5,
                regions=["legs"],
                shape_strength=1.0,
                shape_regions=["breasts"],
            )
        capability.assert_called_once_with(
            "person-body-shape-v1",
            action_label="analyzing body proportions",
        )
        return result

    def test_analysis_combines_structure_and_shape_without_face_or_physics(
        self,
    ) -> None:
        result = self._analysis()

        kinds = {change["fitKind"] for change in result["changes"]}
        self.assertEqual(kinds, {"structure", "shape"})
        self.assertEqual(result["proposed_morphs"], result["changes"])
        self.assertEqual(
            result["shape_changes"][0]["name"],
            "Breasts Size",
        )
        self.assertIn("Face morphs", result["warning"])
        self.assertNotIn("physics", json.dumps(result["changes"]).casefold())

    def test_missing_live_shape_fails_before_legacy_reference_backfill(
        self,
    ) -> None:
        self.body.pop("bodyShape")
        self.body["bodyShapeReady"] = False
        self.body["bodyShapeReason"] = "neutral mesh is still settling"
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
            ) as get_manager,
            self.assertRaisesRegex(
                ValueError,
                "neutral mesh is still settling",
            ),
        ):
            self.service.sam3d_body_proportions(
                self.job_id,
                target_uid="Person",
                shape_regions=["breasts"],
            )

        get_manager.assert_not_called()
        self.manager.body_shape.assert_not_called()

    def test_pending_exact_undo_blocks_a_second_body_fit(self) -> None:
        self.body["undoPending"] = True
        analysis = self._analysis()

        self.assertTrue(analysis["person_fit_active"])
        self.assertTrue(analysis["undo_pending"])
        self.assertFalse(analysis["can_apply"])
        self.assertFalse(analysis["can_undo"])
        self.assertIn("settling", analysis["apply_blocked_reason"])

    def test_structure_analysis_waits_for_stable_shape_cache_before_apply(
        self,
    ) -> None:
        self.body.pop("bodyShape")
        self.body["bodyShapeReady"] = False
        self.body["bodyShapePreparing"] = True
        self.body["bodyShapeReason"] = (
            "Neutral body-shape measurements are being prepared."
        )
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
            analysis = self.service.sam3d_body_proportions(
                self.job_id,
                target_uid="Person",
                regions=["legs"],
                shape_regions=[],
            )

        self.assertTrue(analysis["ready"])
        self.assertTrue(analysis["changes"])
        self.assertFalse(analysis["body_shape_ready"])
        self.assertTrue(analysis["body_shape_preparing"])
        self.assertFalse(analysis["canApply"])
        self.assertFalse(analysis["can_apply"])
        self.assertIn(
            "Structure analysis and review remain available",
            analysis["apply_blocked_reason"],
        )

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
            self.assertRaisesRegex(ValueError, "stable cache"),
        ):
            self.service.apply_sam3d_body_proportions(
                self.job_id,
                expected_job_revision=self.job_revision,
                expected_analysis_revision=analysis["analysis_revision"],
                target_uid="Person",
                regions=["legs"],
                shape_regions=[],
            )

    def test_failed_shape_cache_blocks_structure_apply_with_bridge_reason(
        self,
    ) -> None:
        self.body.pop("bodyShape")
        self.body["bodyShapeReady"] = False
        self.body["bodyShapePreparing"] = False
        self.body["bodyShapeReason"] = "The neutral mesh could not be measured."
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
            analysis = self.service.sam3d_body_proportions(
                self.job_id,
                target_uid="Person",
                regions=["legs"],
                shape_regions=[],
            )

        self.assertFalse(analysis["body_shape_ready"])
        self.assertFalse(analysis["body_shape_preparing"])
        self.assertFalse(analysis["can_apply"])
        self.assertIn(
            "The neutral mesh could not be measured.",
            analysis["apply_blocked_reason"],
        )

    def test_apply_queues_structure_and_shape_as_one_atomic_request(self) -> None:
        analysis = self._analysis()
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
                regions=["legs"],
                shape_strength=1.0,
                shape_regions=["breasts"],
            )

        request = json.loads(
            (bridge_directory(self.service.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["action_state"], "queued")
        self.assertEqual(request["command"], "setPersonBodyProportions")
        self.assertEqual(len(request["changes"]), 2)
        self.assertEqual(
            {item["key"] for item in request["changes"]},
            {"1" * 32, "2" * 32},
        )


if __name__ == "__main__":
    unittest.main()

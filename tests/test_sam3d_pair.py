from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_sam3d import sample_manifest
from vampip.bridge import bridge_directory, request_sam3d_pair_apply
from vampip.sam3d_vam import (
    VAM_CONTROLLER_IDS,
    build_vam_pair_solution,
    sam3d_solution_revision,
)
from vampip.service import ManagerService


def pair_manifest(job_id: str) -> dict[str, object]:
    manifest = sample_manifest(job_id)
    second = copy.deepcopy(manifest["people"][0])
    second["index"] = 1
    second["bbox"] = [0.0, 24.0, 64.0, 64.0]
    second["predCamT"] = [0.2, 0.1, 2.5]
    second["keypoints2d"] = [
        [point[0] + 4.0, point[1]]
        for point in second["keypoints2d"]
    ]
    manifest["people"].append(second)
    return manifest


def rotate_vector(
    rotation: list[float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z, w = rotation
    q_vector = (x, y, z)

    def cross(
        left: tuple[float, float, float],
        right: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        return (
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0],
        )

    first = cross(q_vector, vector)
    doubled = tuple(2.0 * value for value in first)
    second = cross(q_vector, doubled)
    return tuple(
        vector[index] + w * doubled[index] + second[index]
        for index in range(3)
    )


def normalized_dot(
    left: tuple[float, float, float] | list[float],
    right: tuple[float, float, float] | list[float],
) -> float:
    left_length = math.sqrt(sum(value * value for value in left))
    right_length = math.sqrt(sum(value * value for value in right))
    return (
        sum(a * b for a, b in zip(left, right))
        / left_length
        / right_length
    )


class Sam3dPairSolutionTests(unittest.TestCase):
    def test_pair_bridge_request_is_opaque_and_revision_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vam_root = Path(directory)
            request_sam3d_pair_apply(
                vam_root,
                job_id="a" * 32,
                expected_revision="b" * 32,
                solution_sha256="c" * 64,
                camera_uid="SAM Camera",
                create_camera=False,
            )
            request = json.loads(
                (bridge_directory(vam_root) / "request.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(request["command"], "applySam3dPair")
        self.assertEqual(request["jobId"], "a" * 32)
        self.assertEqual(request["expectedRevision"], "b" * 32)
        self.assertEqual(request["solutionSha256"], "c" * 64)
        self.assertEqual(request["cameraUid"], "SAM Camera")
        self.assertFalse(request["createCamera"])
        self.assertNotIn("path", json.dumps(request).casefold())

    def test_pair_solution_uses_one_shared_camera_and_distinct_subjects(
        self,
    ) -> None:
        job_id = "a" * 32
        solution = build_vam_pair_solution(
            pair_manifest(job_id),
            job_id=job_id,
            subjects=[
                {
                    "target_uid": "Primary",
                    "person_index": 0,
                    "height_m": 1.65,
                },
                {
                    "target_uid": "Partner",
                    "person_index": 1,
                    "height_m": 1.82,
                },
            ],
            primary_subject_index=0,
            horizontal_fov=60.0,
        )

        self.assertEqual(solution["schema"], 2)
        self.assertEqual(
            solution["coordinateSpace"],
            "shared-camera-subjects",
        )
        self.assertEqual(solution["primarySubjectIndex"], 0)
        self.assertEqual(solution["camera"]["flatHorizontalFov"], 60.0)
        subjects = solution["subjects"]
        self.assertEqual(
            [subject["targetUid"] for subject in subjects],
            ["Primary", "Partner"],
        )
        self.assertEqual(
            [subject["personIndex"] for subject in subjects],
            [0, 1],
        )
        for subject in subjects:
            self.assertEqual(len(subject["cameraFromHip"]), 3)
            self.assertEqual(len(subject["controllers"]), 19)
            self.assertEqual(
                {item["id"] for item in subject["controllers"]},
                VAM_CONTROLLER_IDS,
            )
            self.assertTrue(
                all("enabled" not in item for item in subject["controllers"])
            )
            self.assertEqual(subject["genitals"], [])
        self.assertNotEqual(
            subjects[0]["cameraFromHip"],
            subjects[1]["cameraFromHip"],
        )
        self.assertEqual(
            solution["revision"],
            sam3d_solution_revision(solution),
        )

    def test_preapply_genital_editor_is_bounded_and_testes_are_opt_in(
        self,
    ) -> None:
        job_id = "b" * 32
        editor = {
            "enabled": True,
            "base_locked": True,
            "segment_lengths_locked": True,
            "testes_enabled": False,
            "handles": {
                "base": [0.50, 0.62, 0.0],
                "mid": [0.50, 0.58, -0.04],
                "tip": [0.50, 0.54, -0.08],
            },
        }
        solution = build_vam_pair_solution(
            pair_manifest(job_id),
            job_id=job_id,
            subjects=[
                {
                    "target_uid": "Primary",
                    "person_index": 0,
                    "height_m": 1.65,
                },
                {
                    "target_uid": "Partner",
                    "person_index": 1,
                    "height_m": 1.82,
                    "genital_editor": editor,
                },
            ],
        )

        genitals = solution["subjects"][1]["genitals"]
        self.assertEqual(
            [item["id"] for item in genitals],
            [
                "penisBaseControl",
                "penisMidControl",
                "penisTipControl",
            ],
        )
        self.assertTrue(
            all(set(item) == {"id", "position"} for item in genitals)
        )
        self.assertNotIn(
            "testesControl",
            {item["id"] for item in genitals},
        )

        with_testes = copy.deepcopy(editor)
        with_testes["testes_enabled"] = True
        with_testes["handles"]["testes"] = [0.50, 0.66, 0.0]
        solution = build_vam_pair_solution(
            pair_manifest(job_id),
            job_id=job_id,
            subjects=[
                {
                    "target_uid": "Primary",
                    "person_index": 0,
                    "height_m": 1.65,
                },
                {
                    "target_uid": "Partner",
                    "person_index": 1,
                    "height_m": 1.82,
                    "genital_editor": with_testes,
                },
            ],
        )
        self.assertIn(
            "testesControl",
            {item["id"] for item in solution["subjects"][1]["genitals"]},
        )

    def test_pair_solution_rejects_ambiguous_or_unbounded_drafts(self) -> None:
        job_id = "c" * 32
        manifest = pair_manifest(job_id)
        duplicate_target = [
            {"target_uid": "Person", "person_index": 0},
            {"target_uid": "Person", "person_index": 1},
        ]
        with self.assertRaisesRegex(ValueError, "distinct"):
            build_vam_pair_solution(
                manifest,
                job_id=job_id,
                subjects=duplicate_target,
            )

        invalid_editor = {
            "enabled": True,
            "testes_enabled": True,
            "handles": {
                "base": [0.5, 0.6],
                "mid": [0.5, 0.5],
                "tip": [1.5, 0.4],
            },
        }
        with self.assertRaisesRegex(ValueError, "testes handle|source image"):
            build_vam_pair_solution(
                manifest,
                job_id=job_id,
                subjects=[
                    {"target_uid": "Primary", "person_index": 0},
                    {
                        "target_uid": "Partner",
                        "person_index": 1,
                        "genital_editor": invalid_editor,
                    },
                ],
            )

    def test_manual_subject_disables_hidden_controls_and_uses_extended_canvas(
        self,
    ) -> None:
        job_id = "d" * 32
        manifest = sample_manifest(job_id)
        solution = build_vam_pair_solution(
            manifest,
            job_id=job_id,
            subjects=[
                {
                    "target_uid": "Primary",
                    "person_index": 0,
                    "height_m": 1.65,
                },
                {
                    "target_uid": "Manual partner",
                    "person_index": 1,
                    "height_m": 1.82,
                    "manual_editor": {
                        "enabled": True,
                        "controllers": {
                            "hipControl": [0.52, 1.20, 0.20],
                            "chestControl": [0.50, 0.72, 0.05],
                            "lHandControl": [-0.25, 0.72, -0.10],
                            "rHandControl": [1.25, 0.72, -0.10],
                        },
                    },
                },
            ],
            primary_subject_index=0,
            horizontal_fov=60.0,
        )

        manual = solution["subjects"][1]
        self.assertEqual(manual["personIndex"], 1)
        self.assertEqual(len(manual["controllers"]), 19)
        self.assertEqual(
            {value["id"] for value in manual["controllers"]},
            VAM_CONTROLLER_IDS,
        )
        controllers = {
            value["id"]: value
            for value in manual["controllers"]
        }
        self.assertEqual(controllers["hipControl"]["position"], [0.0, 0.0, 0.0])
        self.assertEqual(
            controllers["headControl"],
            {"id": "headControl", "enabled": False},
        )
        enabled_ids = {
            "hipControl",
            "chestControl",
            "lHandControl",
            "rHandControl",
        }
        self.assertEqual(
            {
                controller_id
                for controller_id, value in controllers.items()
                if value.get("enabled") is not False
            },
            enabled_ids,
        )
        self.assertNotEqual(
            manual["cameraFromHip"],
            solution["subjects"][0]["cameraFromHip"],
        )
        for controller_id in enabled_ids:
            value = controllers[controller_id]
            self.assertEqual(set(value), {"id", "position", "rotation"})
            self.assertLessEqual(max(map(abs, value["position"])), 5.0)
        for controller_id in VAM_CONTROLLER_IDS - enabled_ids:
            self.assertEqual(
                controllers[controller_id],
                {"id": controller_id, "enabled": False},
            )

    def test_manual_subject_contract_is_strict_and_primary_stays_automatic(
        self,
    ) -> None:
        job_id = "e" * 32
        manifest = sample_manifest(job_id)
        base_subjects = [
            {"target_uid": "Primary", "person_index": 0},
            {
                "target_uid": "Manual partner",
                "person_index": 1,
                "manual_editor": {
                    "enabled": True,
                    "controllers": {"hipControl": [0.5, 1.1, 0.0]},
                },
            },
        ]
        with self.assertRaisesRegex(ValueError, "primary.*must use SAM3D"):
            build_vam_pair_solution(
                manifest,
                job_id=job_id,
                subjects=base_subjects,
                primary_subject_index=1,
            )

        invalid_cases = (
            (
                {"enabled": True, "controllers": {"headControl": [0.5, 0.2]}},
                "requires a hipControl",
            ),
            (
                {
                    "enabled": True,
                    "controllers": {
                        "hipControl": [1.51, 0.5],
                    },
                },
                "extended source canvas",
            ),
            (
                {
                    "enabled": True,
                    "controllers": {
                        "hipControl": [0.5, 0.5, 1.01],
                    },
                },
                "depth offset",
            ),
            (
                {
                    "enabled": True,
                    "controllers": {
                        "hipControl": [0.5, 0.5],
                        "penisTipControl": [0.5, 0.6],
                    },
                },
                "not allowlisted",
            ),
        )
        for editor, message in invalid_cases:
            with self.subTest(message=message):
                subjects = copy.deepcopy(base_subjects)
                subjects[1]["manual_editor"] = editor
                with self.assertRaisesRegex(ValueError, message):
                    build_vam_pair_solution(
                        manifest,
                        job_id=job_id,
                        subjects=subjects,
                    )

    def test_duplicate_automatic_bodies_require_manual_replacement(self) -> None:
        job_id = "f" * 32
        manifest = pair_manifest(job_id)
        manifest["people"][1]["keypoints2d"] = copy.deepcopy(
            manifest["people"][0]["keypoints2d"]
        )
        with self.assertRaisesRegex(ValueError, "same reconstructed body"):
            build_vam_pair_solution(
                manifest,
                job_id=job_id,
                subjects=[
                    {"target_uid": "Primary", "person_index": 0},
                    {"target_uid": "Partner", "person_index": 1},
                ],
            )

    def test_manual_facing_defaults_to_camera_and_flips_torso_and_head(
        self,
    ) -> None:
        job_id = "1" * 32
        manifest = sample_manifest(job_id)

        def build(facing: str | None) -> dict[str, object]:
            editor: dict[str, object] = {
                "enabled": True,
                "controllers": {
                    "hipControl": [0.50, 0.70, 0.0],
                    "chestControl": [0.50, 0.40, 0.0],
                    "neckControl": [0.50, 0.28, 0.0],
                    "headControl": [0.50, 0.16, 0.0],
                    "lShoulderControl": [0.34, 0.42, 0.08],
                    "rShoulderControl": [0.66, 0.48, -0.08],
                },
            }
            if facing is not None:
                editor["facing"] = facing
            return build_vam_pair_solution(
                manifest,
                job_id=job_id,
                subjects=[
                    {"target_uid": "Primary", "person_index": 0},
                    {
                        "target_uid": "Manual partner",
                        "person_index": 1,
                        "manual_editor": editor,
                    },
                ],
                horizontal_fov=60.0,
            )

        implicit = build(None)
        camera = build("camera")
        away = build("away")
        self.assertEqual(
            implicit["subjects"][1]["controllers"],
            camera["subjects"][1]["controllers"],
        )

        def controller_map(
            solution: dict[str, object],
        ) -> dict[str, dict[str, object]]:
            return {
                value["id"]: value
                for value in solution["subjects"][1]["controllers"]
            }

        camera_controllers = controller_map(camera)
        away_controllers = controller_map(away)
        camera_from_hip = camera["subjects"][1]["cameraFromHip"]
        camera_forward = rotate_vector(
            camera_controllers["hipControl"]["rotation"],
            (0.0, 0.0, 1.0),
        )
        away_forward = rotate_vector(
            away_controllers["hipControl"]["rotation"],
            (0.0, 0.0, 1.0),
        )
        self.assertGreater(normalized_dot(camera_forward, camera_from_hip), 0.0)
        self.assertLess(normalized_dot(away_forward, camera_from_hip), 0.0)

        camera_head_forward = rotate_vector(
            camera_controllers["headControl"]["rotation"],
            (0.0, 0.0, 1.0),
        )
        away_head_forward = rotate_vector(
            away_controllers["headControl"]["rotation"],
            (0.0, 0.0, 1.0),
        )
        self.assertGreater(
            normalized_dot(camera_head_forward, camera_forward),
            0.99,
        )
        self.assertGreater(
            normalized_dot(away_head_forward, away_forward),
            0.99,
        )

        right = rotate_vector(
            camera_controllers["hipControl"]["rotation"],
            (1.0, 0.0, 0.0),
        )
        shoulder_axis = tuple(
            camera_controllers["rShoulderControl"]["position"][index]
            - camera_controllers["lShoulderControl"]["position"][index]
            for index in range(3)
        )
        self.assertGreater(abs(normalized_dot(right, shoulder_axis)), 0.95)

    def test_manual_facing_and_controller_chain_lengths_are_strict(self) -> None:
        job_id = "2" * 32
        manifest = sample_manifest(job_id)
        base_editor = {
            "enabled": True,
            "facing": "camera",
            "controllers": {
                "hipControl": [0.50, 0.70, 0.0],
                "chestControl": [0.50, 0.40, 0.0],
                "lShoulderControl": [0.35, 0.42, 0.0],
                "rShoulderControl": [0.65, 0.42, 0.0],
                "lArmControl": [0.30, 0.50, 0.0],
                "lElbowControl": [0.25, 0.60, 0.0],
            },
        }

        invalid_editors: list[tuple[dict[str, object], str]] = []
        invalid_facing = copy.deepcopy(base_editor)
        invalid_facing["facing"] = "sideways"
        invalid_editors.append((invalid_facing, "facing must be camera or away"))

        collapsed_torso = copy.deepcopy(base_editor)
        collapsed_torso["controllers"]["chestControl"] = [0.50, 0.70, 0.0]
        invalid_editors.append((collapsed_torso, "torso axis is too short"))

        collapsed_shoulders = copy.deepcopy(base_editor)
        collapsed_shoulders["controllers"]["rShoulderControl"] = [
            0.35,
            0.42,
            0.0,
        ]
        invalid_editors.append(
            (collapsed_shoulders, "bilateral shoulder axis is too short")
        )

        parallel_shoulders = copy.deepcopy(base_editor)
        parallel_shoulders["controllers"]["lShoulderControl"] = [
            0.50,
            0.50,
            0.0,
        ]
        parallel_shoulders["controllers"]["rShoulderControl"] = [
            0.50,
            0.30,
            0.0,
        ]
        invalid_editors.append(
            (parallel_shoulders, "parallel to the torso up axis")
        )

        collapsed_arm = copy.deepcopy(base_editor)
        collapsed_arm["controllers"]["lElbowControl"] = [0.30, 0.50, 0.0]
        invalid_editors.append((collapsed_arm, "chain is too short"))

        for editor, message in invalid_editors:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    build_vam_pair_solution(
                        manifest,
                        job_id=job_id,
                        subjects=[
                            {"target_uid": "Primary", "person_index": 0},
                            {
                                "target_uid": "Manual partner",
                                "person_index": 1,
                                "manual_editor": editor,
                            },
                        ],
                    )


class Sam3dPairServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addons = self.base / "VaM" / "AddonPackages"
        self.addons.mkdir(parents=True)
        self.job_id = "a" * 32
        self.job_revision = "b" * 32
        self.manifest = pair_manifest(self.job_id)
        self.manifest["revision"] = self.job_revision
        self.manager = mock.Mock()
        self.manager.get.return_value = {
            "id": self.job_id,
            "state": "succeeded",
            "revision": self.job_revision,
        }
        self.manager.manifest.return_value = self.manifest
        self.service = ManagerService(
            self.addons,
            self.base / "state",
            process_probe=lambda: [1234],
            sam3d_manager=self.manager,
        )
        self.scene = {
            "available": True,
            "vam_running": True,
            "bridge": {"instanceId": "bridge-instance"},
            "capabilities": [
                "sam3d-pair-apply-v1",
                "sam3d-camera-vrfunscript-v1",
            ],
            "atoms": [
                {"uid": "Primary", "type": "Person"},
                {"uid": "Partner", "type": "Person"},
                {
                    "uid": "SAM Camera",
                    "type": "Empty",
                    "sam3dCamera": {"compatible": True},
                },
            ],
            "sam3d": {"applied": False},
        }
        self.service._require_live_capability = mock.Mock(
            return_value=self.scene
        )
        self.subjects = [
            {"target_uid": "Primary", "person_index": 0, "height_m": 1.65},
            {"target_uid": "Partner", "person_index": 1, "height_m": 1.82},
        ]

    def tearDown(self) -> None:
        self.service.close()
        self.temporary.cleanup()

    def test_pair_apply_is_revision_bound_and_records_both_targets(self) -> None:
        result = self.service.apply_sam3d_pair(
            self.job_id,
            expected_job_revision=self.job_revision,
            subjects=self.subjects,
            primary_subject_index=1,
            camera_uid="SAM Camera",
            horizontal_fov=61.0,
        )

        self.assertEqual(result["action_state"], "queued")
        self.assertEqual(result["job_revision"], self.job_revision)
        self.assertEqual(
            result["subjects"],
            [
                {"target_uid": "Primary", "person_index": 0},
                {"target_uid": "Partner", "person_index": 1},
            ],
        )
        self.assertEqual(result["primary_subject_index"], 1)
        self.service._require_live_capability.assert_called_once_with(
            "sam3d-pair-apply-v1",
            action_label="applying a paired SAM3D pose",
        )
        self.manager.record_vam_action.assert_called_once()
        action = self.manager.record_vam_action.call_args
        self.assertEqual(action.kwargs["action"], "apply-pair")
        self.assertEqual(action.kwargs["target_uid"], "Partner")
        request = json.loads(
            (bridge_directory(self.base / "VaM") / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(request["command"], "applySam3dPair")
        self.assertEqual(request["jobId"], self.job_id)
        self.assertEqual(request["expectedRevision"], result["solution_revision"])

    def test_pair_apply_requires_exactly_two_distinct_person_targets(self) -> None:
        for subjects in (self.subjects[:1], self.subjects + [self.subjects[0]]):
            with self.subTest(count=len(subjects)):
                with self.assertRaisesRegex(ValueError, "exactly two"):
                    self.service.apply_sam3d_pair(
                        self.job_id,
                        expected_job_revision=self.job_revision,
                        subjects=subjects,
                        primary_subject_index=0,
                        camera_uid="SAM Camera",
                    )

        duplicate = [
            {"target_uid": "Primary", "person_index": 0},
            {"target_uid": "Primary", "person_index": 1},
        ]
        with self.assertRaisesRegex(ValueError, "distinct Person"):
            self.service.apply_sam3d_pair(
                self.job_id,
                expected_job_revision=self.job_revision,
                subjects=duplicate,
                primary_subject_index=0,
                camera_uid="SAM Camera",
            )

    def test_pair_apply_requires_camera_capability_and_exact_revision(self) -> None:
        self.service._require_live_capability.return_value = {
            **self.scene,
            "capabilities": ["sam3d-pair-apply-v1"],
        }
        with self.assertRaisesRegex(ValueError, "VR/Funscript camera"):
            self.service.apply_sam3d_pair(
                self.job_id,
                expected_job_revision=self.job_revision,
                subjects=self.subjects,
                primary_subject_index=0,
                camera_uid="SAM Camera",
            )

        self.service._require_live_capability.return_value = self.scene
        with self.assertRaisesRegex(ValueError, "revision has changed"):
            self.service.apply_sam3d_pair(
                self.job_id,
                expected_job_revision="c" * 32,
                subjects=self.subjects,
                primary_subject_index=0,
                camera_uid="SAM Camera",
            )

    def test_pair_apply_accepts_one_sam_body_plus_one_manual_subject(self) -> None:
        manifest = sample_manifest(self.job_id)
        manifest["revision"] = self.job_revision
        self.manager.manifest.return_value = manifest
        subjects = [
            {"target_uid": "Primary", "person_index": 0, "height_m": 1.65},
            {
                "target_uid": "Partner",
                "person_index": 1,
                "height_m": 1.82,
                "manual_editor": {
                    "enabled": True,
                    "controllers": {
                        "hipControl": [0.5, 1.2, 0.15],
                        "lHandControl": [-0.2, 0.75, -0.1],
                        "rHandControl": [1.2, 0.75, -0.1],
                    },
                },
            },
        ]

        result = self.service.apply_sam3d_pair(
            self.job_id,
            expected_job_revision=self.job_revision,
            subjects=subjects,
            primary_subject_index=0,
            camera_uid="SAM Camera",
        )

        self.assertEqual(result["action_state"], "queued")
        solution = json.loads(
            self.service._sam3d_solution_path(self.job_id).read_text(
                encoding="ascii"
            )
        )
        self.assertEqual(solution["schema"], 2)
        self.assertEqual(len(solution["subjects"][1]["controllers"]), 19)
        self.assertEqual(
            {
                value["id"]
                for value in solution["subjects"][1]["controllers"]
            },
            VAM_CONTROLLER_IDS,
        )
        manual_controllers = {
            value["id"]: value
            for value in solution["subjects"][1]["controllers"]
        }
        self.assertEqual(
            manual_controllers["headControl"],
            {"id": "headControl", "enabled": False},
        )
        self.assertEqual(
            sum(
                value.get("enabled") is False
                for value in manual_controllers.values()
            ),
            16,
        )
        self.assertEqual(
            set(manual_controllers["hipControl"]),
            {"id", "position", "rotation"},
        )

    def test_duplicate_automatic_pair_is_rejected_before_bridge_request(
        self,
    ) -> None:
        manifest = pair_manifest(self.job_id)
        manifest["revision"] = self.job_revision
        manifest["people"][1]["keypoints2d"] = copy.deepcopy(
            manifest["people"][0]["keypoints2d"]
        )
        self.manager.manifest.return_value = manifest

        with self.assertRaisesRegex(ValueError, "same reconstructed body"):
            self.service.apply_sam3d_pair(
                self.job_id,
                expected_job_revision=self.job_revision,
                subjects=self.subjects,
                primary_subject_index=0,
                camera_uid="SAM Camera",
            )

        self.manager.record_vam_action.assert_not_called()
        self.assertFalse(
            (bridge_directory(self.base / "VaM") / "request.json").exists()
        )


if __name__ == "__main__":
    unittest.main()

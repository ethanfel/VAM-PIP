from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None  # type: ignore[assignment]

from vampip.sam3d import Sam3dJobManager, Sam3dJobPaths
from vampip.sam3d_body_shape import (
    BODY_SHAPE_METRICS,
    BODY_SHAPE_REGIONS,
    BODY_SHAPE_REGION_METRICS,
    body_shape_sidecar_revision,
    consensus_body_shapes,
    validate_body_shape,
    validate_body_shape_sidecar,
)
from vampip.sam3d_shape_geometry import derive_body_shape


def _keypoints() -> np.ndarray:
    points = np.zeros((70, 3), dtype=np.float64)
    points[0] = [0.0, 1.60, 0.16]
    points[5] = [0.20, 1.40, 0.0]
    points[6] = [-0.20, 1.40, 0.0]
    points[9] = [0.13, 0.90, 0.0]
    points[10] = [-0.13, 0.90, 0.0]
    points[11] = [0.13, 0.45, 0.0]
    points[12] = [-0.13, 0.45, 0.0]
    points[13] = [0.13, 0.00, 0.0]
    points[14] = [-0.13, 0.00, 0.0]
    return points


def _closed_rings(
    vertices: list[list[float]],
    faces: list[list[int]],
    ys: np.ndarray,
    center_x: float,
    radii_x: np.ndarray,
    radii_z: np.ndarray,
    centers_z: np.ndarray,
    *,
    segments: int = 48,
) -> None:
    first_ring = len(vertices)
    for y, radius_x, radius_z, center_z in zip(
        ys,
        radii_x,
        radii_z,
        centers_z,
    ):
        for index in range(segments):
            angle = 2.0 * np.pi * index / segments
            vertices.append(
                [
                    center_x + float(radius_x) * np.cos(angle),
                    float(y),
                    float(center_z) + float(radius_z) * np.sin(angle),
                ]
            )
    for ring in range(len(ys) - 1):
        current = first_ring + ring * segments
        following = current + segments
        for index in range(segments):
            next_index = (index + 1) % segments
            faces.append([current + index, following + index, following + next_index])
            faces.append(
                [current + index, following + next_index, current + next_index]
            )
    lower_center = len(vertices)
    vertices.append([center_x, float(ys[0]), float(centers_z[0])])
    upper_center = len(vertices)
    vertices.append([center_x, float(ys[-1]), float(centers_z[-1])])
    lower = first_ring
    upper = first_ring + (len(ys) - 1) * segments
    for index in range(segments):
        next_index = (index + 1) % segments
        faces.append([lower_center, lower + next_index, lower + index])
        faces.append([upper_center, upper + index, upper + next_index])


def _synthetic_body() -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []

    torso_y = np.linspace(0.80, 1.48, 137)
    torso_t = (torso_y - 0.90) / 0.50
    seat = np.exp(-(((torso_t - 0.02) / 0.18) ** 2))
    waist = np.exp(-(((torso_t - 0.50) / 0.14) ** 2))
    bust = np.exp(-(((torso_t - 0.72) / 0.10) ** 2))
    _closed_rings(
        vertices,
        faces,
        torso_y,
        0.0,
        0.18 + 0.045 * seat - 0.045 * waist + 0.035 * bust,
        0.115 + 0.050 * seat - 0.025 * waist + 0.060 * bust,
        -0.018 * seat + 0.018 * bust,
    )

    leg_y = np.linspace(0.0, 0.82, 83)
    leg_fraction = leg_y / leg_y[-1]
    leg_x = 0.060 + 0.035 * leg_fraction
    leg_z = 0.055 + 0.030 * leg_fraction
    for center_x in (0.13, -0.13):
        _closed_rings(
            vertices,
            faces,
            leg_y,
            center_x,
            leg_x,
            leg_z,
            np.zeros_like(leg_y),
        )
    return (
        np.asarray(vertices, dtype=np.float64),
        np.asarray(faces, dtype=np.int64),
    )


def _signature() -> dict[str, object]:
    vertices, faces = _synthetic_body()
    points = _keypoints()
    return derive_body_shape(
        vertices,
        points,
        faces,
        posed_keypoints=points,
        np=np,
    )


def _scale_region(
    signature: dict[str, object],
    region: str,
    factor: float,
) -> None:
    normalizer = float(signature["normalizer"]["meters"])  # type: ignore[index]
    measurements = signature["measurements"]
    assert isinstance(measurements, dict)
    for metric in BODY_SHAPE_REGION_METRICS[region]:
        item = measurements[metric]
        assert isinstance(item, dict)
        item["meters"] = round(float(item["meters"]) * factor, 8)
        item["ratio"] = round(float(item["meters"]) / normalizer, 8)
        for side in ("leftMeters", "rightMeters"):
            if side in item:
                item[side] = round(float(item[side]) * factor, 8)


@unittest.skipIf(np is None, "NumPy is optional and unavailable")
class Sam3dBodyShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.signature = _signature()

    def test_neutral_mesh_signature_has_expected_regions_and_metrics(self) -> None:
        signature = copy.deepcopy(self.signature)
        validate_body_shape(signature)

        self.assertEqual(
            set(signature["measurements"]),
            set(BODY_SHAPE_METRICS),
        )
        self.assertEqual(set(signature["regions"]), set(BODY_SHAPE_REGIONS))
        self.assertGreater(
            signature["measurements"]["breastProjection"]["meters"],
            0.0,
        )
        self.assertGreater(
            signature["measurements"]["gluteProjection"]["meters"],
            0.0,
        )
        self.assertGreater(
            signature["measurements"]["seatWidth"]["meters"],
            signature["measurements"]["waistWidth"]["meters"],
        )
        self.assertLessEqual(signature["overallConfidence"], 0.70)
        self.assertEqual(
            signature["measurements"]["upperThighGirth"]["meters"],
            (
                signature["measurements"]["upperThighGirth"]["leftMeters"]
                + signature["measurements"]["upperThighGirth"]["rightMeters"]
            )
            / 2.0,
        )

    def test_validation_rejects_tampered_ratios_confidence_and_planes(self) -> None:
        signature = copy.deepcopy(self.signature)
        signature["measurements"]["waistGirth"]["ratio"] = 3.0
        with self.assertRaisesRegex(ValueError, "waistGirth"):
            validate_body_shape(signature)

        signature = copy.deepcopy(self.signature)
        signature["regions"]["glutes"]["confidence"] = 0.99
        with self.assertRaisesRegex(ValueError, "glutes confidence"):
            validate_body_shape(signature)

        signature = copy.deepcopy(self.signature)
        signature["planes"]["bustTorsoFraction"] = 0.9
        with self.assertRaisesRegex(ValueError, "planes"):
            validate_body_shape(signature)

    def test_consensus_rejects_one_source_as_a_whole_region(self) -> None:
        baseline = copy.deepcopy(self.signature)
        matching = copy.deepcopy(self.signature)
        outlier = copy.deepcopy(self.signature)
        _scale_region(outlier, "breasts", 1.75)
        validate_body_shape(outlier)

        result = consensus_body_shapes(
            [baseline, matching, outlier],
            source_ids=[
                "0" * 32,
                "1" * 32,
                "2" * 32,
            ],
        )

        validate_body_shape(result)
        breast_report = result["consensus"]["regions"]["breasts"]
        waist_report = result["consensus"]["regions"]["waist"]
        self.assertEqual(breast_report["usedSourceIndices"], [0, 1])
        self.assertEqual(breast_report["rejectedSourceIndices"], [2])
        self.assertEqual(waist_report["usedSourceIndices"], [0, 1, 2])
        self.assertEqual(
            result["measurements"]["bustGirth"]["meters"],
            baseline["measurements"]["bustGirth"]["meters"],
        )

    def test_single_consensus_input_preserves_exact_object(self) -> None:
        signature = copy.deepcopy(self.signature)
        self.assertIs(consensus_body_shapes([signature]), signature)

    def test_sidecar_revision_binds_shape_and_source(self) -> None:
        document: dict[str, object] = {
            "schema": 1,
            "kind": "vampip-sam3d-body-shape-sidecar",
            "source": {
                "arraysSha256": "a" * 64,
                "arraysBytes": 123,
                "personIndex": 0,
                "mhrSha256": "b" * 64,
                "identityBasisSha256": "c" * 64,
            },
            "bodyShape": copy.deepcopy(self.signature),
        }
        document["revision"] = body_shape_sidecar_revision(document)
        validate_body_shape_sidecar(document)

        document["bodyShape"]["measurements"]["seatWidth"]["meters"] += 0.01
        with self.assertRaises(ValueError):
            validate_body_shape_sidecar(document)

    def test_manager_returns_embedded_shape_without_backfill(self) -> None:
        manager = object.__new__(Sam3dJobManager)
        signature = copy.deepcopy(self.signature)
        manager.get = lambda job_id: {"state": "succeeded"}  # type: ignore[method-assign]
        manager.manifest = lambda job_id: {  # type: ignore[method-assign]
            "people": [{"bodyShape": signature}]
        }

        self.assertIs(manager.body_shape("a" * 32, 0), signature)

    def test_manager_reuses_source_bound_legacy_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            arrays = directory / "arrays.npz"
            arrays.write_bytes(b"legacy-arrays")
            sidecar = directory / "body-shape-v1-person-0.json"
            document: dict[str, object] = {
                "schema": 1,
                "kind": "vampip-sam3d-body-shape-sidecar",
                "source": {
                    "arraysSha256": hashlib.sha256(arrays.read_bytes()).hexdigest(),
                    "arraysBytes": arrays.stat().st_size,
                    "personIndex": 0,
                    "mhrSha256": "b" * 64,
                    "identityBasisSha256": "c" * 64,
                },
                "bodyShape": copy.deepcopy(self.signature),
            }
            document["revision"] = body_shape_sidecar_revision(document)
            sidecar.write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            paths = Sam3dJobPaths(
                directory=directory,
                source=directory / "source.png",
                request=directory / "request.json",
                manifest=directory / "manifest.json",
                overlay=directory / "overlay.png",
                arrays=arrays,
                log=directory / "worker.log",
            )
            manager = object.__new__(Sam3dJobManager)
            manager.get = lambda job_id: {"state": "succeeded"}  # type: ignore[method-assign]
            manager.manifest = lambda job_id: {  # type: ignore[method-assign]
                "people": [{}]
            }
            manager._paths = lambda job_id: paths  # type: ignore[method-assign]

            result = manager.body_shape("a" * 32, 0)

            self.assertEqual(result, self.signature)

    def test_dependency_free_schema_module_does_not_import_numpy(self) -> None:
        module_path = (
            Path(__file__).parents[1] / "src" / "vampip" / "sam3d_body_shape.py"
        )
        text = module_path.read_text(encoding="utf-8")
        self.assertNotIn("import numpy", text)


if __name__ == "__main__":
    unittest.main()

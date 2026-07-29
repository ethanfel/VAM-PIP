from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import numpy as np

from tests.test_sam3d import FakeWorker, png_header
from vampip.sam3d import Sam3dJobError, Sam3dJobManager, Sam3dWorkerConfig
from vampip.sam3d_body_signature import (
    BODY_PROPORTION_MEASUREMENTS,
    derive_body_proportions,
    validate_body_proportions,
)
from vampip.sam3d_worker import (
    NUMERIC_ARRAY_SHAPES,
    _validate_stored_numeric_arrays,
    _validated_person_arrays,
)


def neutral_keypoints() -> list[list[float]]:
    points = [[0.0, 0.0, 0.0] for _ in range(70)]
    values = {
        5: [-0.20, 1.40, 0.0],
        6: [0.20, 1.40, 0.0],
        7: [-0.50, 1.40, 0.0],
        8: [0.50, 1.40, 0.0],
        9: [-0.15, 0.90, 0.0],
        10: [0.15, 0.90, 0.0],
        11: [-0.15, 0.45, 0.0],
        12: [0.15, 0.45, 0.0],
        13: [-0.15, 0.00, 0.0],
        14: [0.15, 0.00, 0.0],
        41: [0.75, 1.40, 0.0],
        62: [-0.75, 1.40, 0.0],
    }
    for index, value in values.items():
        points[index] = value
    return points


def numeric_output() -> dict[str, np.ndarray]:
    return {
        name: np.zeros(shape, dtype=np.float64)
        for name, shape in NUMERIC_ARRAY_SHAPES.items()
    }


class Sam3dBodySignatureTests(unittest.TestCase):
    def test_neutral_signature_has_exact_measurements_and_normalized_ratios(
        self,
    ) -> None:
        signature = derive_body_proportions(
            neutral_keypoints(),
            stature_m=1.70,
        )

        self.assertEqual(signature["space"], "mhr-neutral-bind")
        self.assertEqual(signature["normalizer"], {"id": "stature", "meters": 1.7})
        self.assertEqual(
            set(signature["measurements"]),
            set(BODY_PROPORTION_MEASUREMENTS),
        )
        measurements = signature["measurements"]
        self.assertAlmostEqual(measurements["upperArm"]["meters"], 0.30)
        self.assertAlmostEqual(measurements["forearm"]["meters"], 0.25)
        self.assertAlmostEqual(measurements["thigh"]["meters"], 0.45)
        self.assertAlmostEqual(measurements["shin"]["meters"], 0.45)
        self.assertAlmostEqual(measurements["torso"]["meters"], 0.50)
        self.assertAlmostEqual(measurements["shoulderSpan"]["meters"], 0.40)
        self.assertAlmostEqual(measurements["hipSpan"]["meters"], 0.30)
        self.assertAlmostEqual(
            measurements["upperArm"]["ratio"],
            0.30 / 1.70,
        )
        self.assertEqual(measurements["upperArm"]["confidence"], 1.0)
        validate_body_proportions(signature)

    def test_signature_validation_rejects_tampered_and_nonfinite_values(
        self,
    ) -> None:
        signature = derive_body_proportions(
            neutral_keypoints(),
            stature_m=1.70,
        )
        signature["measurements"]["thigh"]["ratio"] = 0.99
        with self.assertRaisesRegex(ValueError, "thigh"):
            validate_body_proportions(signature)

        signature = derive_body_proportions(
            neutral_keypoints(),
            stature_m=1.70,
        )
        signature["measurements"]["shin"]["meters"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_body_proportions(signature)

    def test_worker_array_contract_is_exact_float32_and_finite(self) -> None:
        normalized = _validated_person_arrays(
            np,
            numeric_output(),
            person_index=0,
        )
        self.assertEqual(
            set(normalized),
            {
                f"person_0_{name}"
                for name in NUMERIC_ARRAY_SHAPES
            },
        )
        self.assertTrue(
            all(value.dtype == np.dtype(np.float32) for value in normalized.values())
        )

        missing = numeric_output()
        missing.pop("shape_params")
        with self.assertRaisesRegex(ValueError, "shape_params"):
            _validated_person_arrays(np, missing, person_index=0)

        invalid = numeric_output()
        invalid["scale_params"][0] = np.inf
        with self.assertRaisesRegex(ValueError, "scale_params"):
            _validated_person_arrays(np, invalid, person_index=0)

    def test_stored_npz_is_reopened_and_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "arrays.npz"
            arrays = _validated_person_arrays(
                np,
                numeric_output(),
                person_index=0,
            )
            np.savez_compressed(path, **arrays)
            _validate_stored_numeric_arrays(np, path, person_count=1)

            arrays["person_0_pred_cam_t"] = np.zeros(4, dtype=np.float32)
            np.savez_compressed(path, **arrays)
            with self.assertRaisesRegex(ValueError, "pred_cam_t"):
                _validate_stored_numeric_arrays(np, path, person_count=1)

    def test_completed_job_binds_arrays_bytes_into_persisted_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            python = base / "env" / "python"
            python.parent.mkdir()
            python.write_bytes(b"")
            python.chmod(0o700)
            repo = base / "sam-3d-body"
            (repo / "sam_3d_body").mkdir(parents=True)
            (repo / "sam_3d_body" / "__init__.py").write_text(
                "",
                encoding="utf-8",
            )
            checkpoint = base / "model" / "model.ckpt"
            checkpoint.parent.mkdir()
            checkpoint.write_bytes(b"checkpoint")
            (checkpoint.parent / "model_config.yaml").write_text(
                "MODEL:\n  BACKBONE:\n    TYPE: vit_hmr_512_384\n",
                encoding="utf-8",
            )
            mhr = checkpoint.parent / "assets" / "mhr_model.pt"
            mhr.parent.mkdir()
            mhr.write_bytes(b"mhr")
            config = Sam3dWorkerConfig(
                python=python,
                conda_executable=None,
                conda_env=None,
                repo=repo,
                checkpoint=checkpoint,
                mhr=mhr,
            )
            manager = Sam3dJobManager(
                base / "state",
                config=config,
                worker=FakeWorker(),
            )
            try:
                created = manager.create(png_header(), "image/png")
                manager.queue(created["id"])
                manager._queue.join()
                manifest = manager.manifest(created["id"])
                metadata = manifest["artifacts"]["arraysMetadata"]
                self.assertRegex(metadata["sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(metadata["bytes"], len(b"test-npz"))

                paths = manager._paths(created["id"])
                paths.arrays.write_bytes(b"tampered")
                with self.assertRaisesRegex(Sam3dJobError, "validation"):
                    manager.manifest(created["id"])
            finally:
                manager.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest import mock

from vampip.bridge import bridge_directory, install_bridge
from vampip.database import connect
from vampip.sam3d import (
    SAM3D_MODEL_CONFIG_LIMIT,
    Sam3dConfigurationError,
    Sam3dJobError,
    Sam3dJobManager,
    Sam3dWorkerConfig,
    SubprocessSam3dWorker,
    inspect_image,
)
from vampip.sam3d_vam import (
    MHR70_NAMES,
    VAM_CONTROLLER_IDS,
    build_vam_solution,
)
from vampip.sam3d_worker import _pinned_torch_hub_loader
from vampip.service import ManagerService


def png_header(width: int = 64, height: int = 64) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )


def sample_people() -> list[dict[str, object]]:
    points = [[0.0, 0.0, 0.0] for _ in MHR70_NAMES]

    def set_point(name: str, x: float, y: float, z: float = 0.0) -> None:
        points[MHR70_NAMES.index(name)] = [x, y, z]

    set_point("nose", 0.0, -0.82, -0.02)
    set_point("left-eye", -0.04, -0.84, -0.03)
    set_point("right-eye", 0.04, -0.84, -0.03)
    set_point("left-ear", -0.09, -0.79, 0.0)
    set_point("right-ear", 0.09, -0.79, 0.0)
    set_point("neck", 0.0, -0.62, 0.0)
    for side, sign in (("left", -1.0), ("right", 1.0)):
        set_point(f"{side}-shoulder", 0.22 * sign, -0.55, 0.0)
        set_point(f"{side}-acromion", 0.22 * sign, -0.55, 0.0)
        set_point(f"{side}-elbow", 0.43 * sign, -0.52, 0.02)
        set_point(f"{side}-wrist", 0.65 * sign, -0.50, 0.02)
        set_point(f"{side}-middle-tip", 0.75 * sign, -0.50, 0.02)
        set_point(f"{side}-hip", 0.11 * sign, 0.0, 0.0)
        set_point(f"{side}-knee", 0.11 * sign, 0.48, 0.02)
        set_point(f"{side}-ankle", 0.11 * sign, 0.92, 0.0)
        set_point(f"{side}-heel", 0.11 * sign, 0.94, -0.08)
        set_point(f"{side}-big-toe-tip", 0.09 * sign, 0.96, 0.16)
        set_point(f"{side}-small-toe-tip", 0.13 * sign, 0.96, 0.15)
    return [
        {
            "index": 0,
            "bbox": [5.0, 3.0, 59.0, 63.0],
            "focalLength": 100.0,
            "predCamT": [0.0, 0.0, 3.0],
            "keypointNames": list(MHR70_NAMES),
            "keypoints3d": points,
            "keypoints2d": [[32.0, 32.0] for _ in MHR70_NAMES],
        }
    ]


def sample_manifest(job_id: str) -> dict[str, object]:
    return {
        "schema": 1,
        "engine": {
            "name": "facebookresearch/sam-3d-body",
            "mode": "native-standalone",
        },
        "jobId": job_id,
        "source": {
            "width": 64,
            "height": 64,
            "contentType": "image/png",
            "bbox": [0.0, 0.0, 64.0, 64.0],
            "verticalFov": None,
        },
        "people": sample_people(),
        "artifacts": {"arrays": "arrays.npz", "overlay": "overlay.png"},
    }


class FakeWorker:
    def __call__(self, config, paths, runtime_dir) -> None:
        request = json.loads(paths.request.read_text(encoding="utf-8"))
        manifest = sample_manifest(request["jobId"])
        if request["schema"] == 2:
            manifest["schema"] = 2
            manifest["engine"].update(
                {
                    "modelId": request["modelId"],
                    "backbone": config.public_status()["backbone"],
                }
            )
        manifest["source"]["bbox"] = request["bbox"]
        manifest["source"]["verticalFov"] = request["verticalFov"]
        paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        paths.overlay.write_bytes(png_header())
        paths.arrays.write_bytes(b"test-npz")


class Sam3dBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.state = self.base / "state"
        self.vam_root = self.base / "VaM"
        self.addons = self.vam_root / "AddonPackages"
        self.addons.mkdir(parents=True)
        python = self.base / "sam3d-conda" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        python.chmod(0o700)
        repo = self.base / "sam-3d-body"
        (repo / "sam_3d_body").mkdir(parents=True)
        (repo / "sam_3d_body" / "__init__.py").write_text("", encoding="utf-8")
        checkpoint = self.base / "models" / "model.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(b"checkpoint")
        (checkpoint.parent / "model_config.yaml").write_text(
            "MODEL:\n  BACKBONE:\n    TYPE: vit_hmr_512_384\n",
            encoding="utf-8",
        )
        mhr = self.base / "models" / "assets" / "mhr_model.pt"
        mhr.parent.mkdir()
        mhr.write_bytes(b"mhr")
        self.config = Sam3dWorkerConfig(
            python=python,
            conda_executable=None,
            conda_env=None,
            repo=repo,
            checkpoint=checkpoint,
            mhr=mhr,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def manager(self, worker=None) -> Sam3dJobManager:
        return Sam3dJobManager(
            self.state,
            config=self.config,
            worker=worker or FakeWorker(),
        )

    def dual_model_manager(self, worker=None) -> Sam3dJobManager:
        checkpoint = self.base / "models" / "dinov3" / "model.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(b"dino-checkpoint")
        (checkpoint.parent / "model_config.yaml").write_text(
            "MODEL:\n  BACKBONE:\n    TYPE: dinov3_vith16plus\n",
            encoding="utf-8",
        )
        dinov3_repo = self.base / "dinov3"
        (dinov3_repo / "dinov3").mkdir(parents=True)
        (dinov3_repo / "dinov3" / "__init__.py").write_text(
            "",
            encoding="utf-8",
        )
        (dinov3_repo / "hubconf.py").write_text("", encoding="utf-8")
        dino_config = replace(
            self.config,
            checkpoint=checkpoint,
            dinov3_repo=dinov3_repo,
        )
        return Sam3dJobManager(
            self.state,
            model_configs={
                "dinov3_vith16plus": dino_config,
                "vit_hmr_512_384": self.config,
            },
            default_model_id="dinov3_vith16plus",
            worker=worker or FakeWorker(),
        )

    def completed_job(self) -> tuple[Sam3dJobManager, dict[str, object]]:
        manager = self.manager()
        created = manager.create(
            png_header(),
            "image/png",
            bbox=[0.0, 0.0, 64.0, 64.0],
            vertical_fov=55.0,
        )
        manager.queue(created["id"])
        manager._queue.join()
        return manager, manager.get(created["id"])

    def test_upload_header_validation_rejects_spoofing_and_pixel_bombs(self) -> None:
        info = inspect_image(png_header(3840, 2160), "image/png")
        self.assertEqual((info.width, info.height), (3840, 2160))
        with self.assertRaisesRegex(ValueError, "does not match"):
            inspect_image(png_header(), "image/jpeg")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            inspect_image(png_header(30_000, 30_000), "image/png")

    def test_worker_status_reports_missing_components_without_importing_models(
        self,
    ) -> None:
        config = Sam3dWorkerConfig(
            python=None,
            conda_executable=None,
            conda_env=None,
            repo=None,
            checkpoint=None,
            mhr=None,
        )
        manager = Sam3dJobManager(self.state, config=config, worker=FakeWorker())
        status = manager.status()
        self.assertFalse(status["available"])
        self.assertFalse(status["comfyui_used"])
        self.assertGreaterEqual(len(status["worker"]["errors"]), 4)

    def test_dinov3_checkpoint_requires_a_pinned_native_checkout(self) -> None:
        assert self.config.checkpoint is not None
        stale_vit_repo = replace(
            self.config,
            dinov3_repo=self.base / "missing-dinov3",
        )
        self.assertEqual(stale_vit_repo.errors(), [])
        self.assertEqual(
            stale_vit_repo.public_status()["model"],
            "SAM 3D Body ViT-H",
        )

        (self.config.checkpoint.parent / "model_config.yaml").write_text(
            "MODEL:\n  BACKBONE:\n    TYPE: dinov3_vith16plus\n",
            encoding="utf-8",
        )
        missing = replace(self.config, dinov3_repo=None)
        self.assertIn(
            "the pinned official DINOv3 repository is not configured",
            missing.errors(),
        )

        dinov3_repo = self.base / "dinov3"
        (dinov3_repo / "dinov3").mkdir(parents=True)
        (dinov3_repo / "dinov3" / "__init__.py").write_text(
            "",
            encoding="utf-8",
        )
        (dinov3_repo / "hubconf.py").write_text("", encoding="utf-8")
        configured = replace(self.config, dinov3_repo=dinov3_repo)

        self.assertEqual(configured.errors(), [])
        status = configured.public_status()
        self.assertEqual(status["model"], "SAM 3D Body DINOv3-H+")
        self.assertEqual(status["backbone"], "dinov3_vith16plus")
        self.assertTrue(status["dinov3_repository"])

    def test_dual_model_jobs_are_immutable_labeled_and_serialized(self) -> None:
        calls: list[str] = []

        class RecordingWorker:
            def __call__(worker_self, config, paths, runtime_dir) -> None:
                calls.append(str(config.public_status()["backbone"]))
                FakeWorker()(config, paths, runtime_dir)

        manager = self.dual_model_manager(worker=RecordingWorker())
        status = manager.status()
        self.assertTrue(status["available"])
        self.assertEqual(
            status["worker"]["default_model_id"],
            "dinov3_vith16plus",
        )
        self.assertEqual(
            {
                model["id"]
                for model in status["worker"]["models"]
                if model["configured"]
            },
            {"dinov3_vith16plus", "vit_hmr_512_384"},
        )

        comparison_id = "1" * 32
        created = manager.create(
            png_header(),
            "image/png",
            model_id="vit_hmr_512_384",
            comparison_id=comparison_id,
        )
        self.assertEqual(created["model"]["id"], "vit_hmr_512_384")
        self.assertEqual(created["model"]["name"], "SAM 3D Body ViT-H")
        self.assertEqual(created["comparison_id"], comparison_id)
        request = json.loads(
            manager._paths(created["id"]).request.read_text(encoding="utf-8")
        )
        self.assertEqual(request["schema"], 2)
        self.assertEqual(request["modelId"], "vit_hmr_512_384")
        self.assertEqual(request["comparisonId"], comparison_id)

        manager.queue(created["id"])
        manager._queue.join()
        completed = manager.get(created["id"])
        self.assertEqual(completed["state"], "succeeded")
        self.assertEqual(calls, ["vit_hmr_512_384"])
        manifest = manager.manifest(created["id"])
        self.assertEqual(
            manifest["engine"],
            {
                "name": "facebookresearch/sam-3d-body",
                "mode": "native-standalone",
                "modelId": "vit_hmr_512_384",
                "backbone": "vit_hmr_512_384",
            },
        )

    def test_job_model_identity_survives_profile_removal(self) -> None:
        manager = self.dual_model_manager()
        dino_config = manager.model_configs["dinov3_vith16plus"]
        created = manager.create(
            png_header(),
            "image/png",
            model_id="vit_hmr_512_384",
        )
        manager.close()

        restarted = Sam3dJobManager(
            self.state,
            model_configs={"dinov3_vith16plus": dino_config},
            default_model_id="dinov3_vith16plus",
            worker=FakeWorker(),
        )
        try:
            self.assertEqual(
                restarted.get(created["id"])["model"],
                {
                    "id": "vit_hmr_512_384",
                    "name": "SAM 3D Body ViT-H",
                    "backbone": "vit_hmr_512_384",
                },
            )
        finally:
            restarted.close()

    def test_comparison_group_is_bound_to_exact_inputs_and_models(self) -> None:
        manager = self.dual_model_manager()
        source = png_header()
        bbox = [0.0, 0.0, 64.0, 64.0]

        comparison_id = "1" * 32
        first = manager.create(
            source,
            "image/png",
            bbox=bbox,
            vertical_fov=55.0,
            model_id="dinov3_vith16plus",
            comparison_id=comparison_id,
        )
        second = manager.create(
            source,
            "image/png",
            bbox=bbox,
            vertical_fov=55.0,
            model_id="vit_hmr_512_384",
            comparison_id=comparison_id,
        )
        self.assertEqual(first["comparison_id"], comparison_id)
        self.assertEqual(second["comparison_id"], comparison_id)
        with self.assertRaisesRegex(ValueError, "already contains two"):
            manager.create(
                source,
                "image/png",
                bbox=bbox,
                vertical_fov=55.0,
                model_id="dinov3_vith16plus",
                comparison_id=comparison_id,
            )

        duplicate_id = "2" * 32
        manager.create(
            source,
            "image/png",
            model_id="dinov3_vith16plus",
            comparison_id=duplicate_id,
        )
        with self.assertRaisesRegex(ValueError, "distinct model IDs"):
            manager.create(
                source,
                "image/png",
                model_id="dinov3_vith16plus",
                comparison_id=duplicate_id,
            )

        changed_source_id = "3" * 32
        manager.create(
            source,
            "image/png",
            model_id="dinov3_vith16plus",
            comparison_id=changed_source_id,
        )
        with self.assertRaisesRegex(ValueError, "identical source bytes"):
            manager.create(
                source + b"different",
                "image/png",
                model_id="vit_hmr_512_384",
                comparison_id=changed_source_id,
            )

        changed_camera_id = "4" * 32
        manager.create(
            source,
            "image/png",
            bbox=bbox,
            vertical_fov=55.0,
            model_id="dinov3_vith16plus",
            comparison_id=changed_camera_id,
        )
        with self.assertRaisesRegex(ValueError, "same source, box, and FOV"):
            manager.create(
                source,
                "image/png",
                bbox=[1.0, 0.0, 64.0, 64.0],
                vertical_fov=55.0,
                model_id="vit_hmr_512_384",
                comparison_id=changed_camera_id,
            )

    def test_comparison_rejects_non_official_model_profiles(self) -> None:
        manager = Sam3dJobManager(
            self.state,
            model_configs={"custom_vit": self.config},
            default_model_id="custom_vit",
            worker=FakeWorker(),
        )
        with self.assertRaisesRegex(ValueError, r"only DINOv3-H\+ and ViT-H"):
            manager.create(
                png_header(),
                "image/png",
                model_id="custom_vit",
                comparison_id="5" * 32,
            )

    def test_model_registry_rejects_unknown_and_mismatched_profiles(self) -> None:
        manager = self.dual_model_manager()
        with self.assertRaisesRegex(
            Sam3dConfigurationError,
            "not configured",
        ):
            manager.create(
                png_header(),
                "image/png",
                model_id="unknown_model",
            )

        mismatched = Sam3dJobManager(
            self.state / "mismatch",
            model_configs={"dinov3_vith16plus": self.config},
            default_model_id="dinov3_vith16plus",
            worker=FakeWorker(),
        )
        created = mismatched.create(png_header(), "image/png")
        with self.assertRaisesRegex(
            Sam3dConfigurationError,
            "uses checkpoint backbone",
        ):
            mismatched.queue(created["id"])

    def test_legacy_schema_one_job_remains_readable_and_runnable(self) -> None:
        manager = self.manager()
        created = manager.create(png_header(), "image/png")
        paths = manager._paths(created["id"])
        request = json.loads(paths.request.read_text(encoding="utf-8"))
        request["schema"] = 1
        request.pop("modelId")
        encoded = json.dumps(request, separators=(",", ":"), sort_keys=True)
        paths.request.write_text(encoded, encoding="utf-8")
        with connect(self.state) as connection:
            connection.execute(
                "UPDATE sam3d_jobs SET request_json = ? WHERE id = ?",
                (encoded, created["id"]),
            )

        manager.queue(created["id"])
        manager._queue.join()
        completed = manager.get(created["id"])
        self.assertEqual(completed["state"], "succeeded")
        self.assertIsNone(completed["model"])
        self.assertEqual(manager.manifest(created["id"])["schema"], 1)

    def test_worker_rejects_model_config_without_supported_backbone(self) -> None:
        assert self.config.checkpoint is not None
        (self.config.checkpoint.parent / "model_config.yaml").write_text(
            "MODEL:\n  BACKBONE:\n    TYPE: unsupported_encoder\n",
            encoding="utf-8",
        )
        self.assertIn(
            "model_config.yaml does not declare a supported "
            "dinov3_* or vit_hmr* backbone",
            self.config.errors(),
        )
        manager = Sam3dJobManager(
            self.state,
            config=self.config,
            worker=FakeWorker(),
        )
        self.assertFalse(manager.status()["available"])

    def test_worker_rejects_unsafe_model_config_files(self) -> None:
        assert self.config.checkpoint is not None
        config_path = self.config.checkpoint.parent / "model_config.yaml"
        cases = {
            "oversized": b" " * (SAM3D_MODEL_CONFIG_LIMIT + 1),
            "invalid UTF-8": b"\xff",
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                config_path.write_bytes(payload)
                errors = self.config.errors()
                self.assertTrue(
                    any("model_config.yaml" in error for error in errors)
                )
                self.assertFalse(self.config.configured)
                self.assertFalse(self.config.public_status()["model_config"])

    def test_dinov3_torch_hub_is_redirected_to_the_pinned_checkout(self) -> None:
        dinov3_repo = self.base / "dinov3"
        original_load = mock.Mock(return_value="model")
        load = _pinned_torch_hub_loader(original_load, dinov3_repo)

        self.assertEqual(
            load(
                "facebookresearch/dinov3",
                "dinov3_vith16plus",
                source="github",
                pretrained=False,
            ),
            "model",
        )
        original_load.assert_called_once_with(
            str(dinov3_repo),
            "dinov3_vith16plus",
            source="local",
            pretrained=False,
        )
        with self.assertRaisesRegex(RuntimeError, "unexpected remote"):
            load(
                "untrusted/example",
                "model",
                source="github",
            )
        with self.assertRaisesRegex(RuntimeError, "unexpected DINOv3"):
            load(
                "facebookresearch/dinov3",
                "dinov3_vitl16",
                source="github",
                pretrained=False,
            )
        with self.assertRaisesRegex(RuntimeError, "downloads are disabled"):
            load(
                "facebookresearch/dinov3",
                "dinov3_vith16plus",
                source="github",
                pretrained=True,
            )
        with self.assertRaisesRegex(RuntimeError, "unexpected DINOv3"):
            load(
                "facebookresearch/dinov3",
                "dinov3_vith16plus",
                source="github",
                pretrained=False,
                force_reload=True,
            )

    def test_subprocess_worker_starts_an_isolated_sanitized_session(self) -> None:
        manager = self.manager()
        created = manager.create(png_header(), "image/png")
        paths = manager._paths(created["id"])
        process = mock.Mock()
        process.pid = 43210
        process.wait.return_value = 0
        inherited = {
            "PATH": "/usr/bin",
            "SAFE_KEEP": "yes",
            "LD_PRELOAD": "/tmp/inject.so",
            "LD_LIBRARY_PATH": "/tmp/libs",
            "CONDA_PREFIX": "/tmp/conda",
            "_CONDA_EXE": "/tmp/conda/bin/conda",
            "VIRTUAL_ENV": "/tmp/venv",
            "VIRTUAL_ENV_PROMPT": "venv",
            "_CE_CONDA": "1",
            "PYTHONPATH": "/tmp/python",
            "PYTHONWARNINGS": "ignore",
            "PYTHONNOUSERSITE": "0",
            "COMFYUI_ROOT": "/tmp/ComfyUI",
            "OTHER_MODEL_PATH": "/tmp/ComfyUI/models",
            "HF_TOKEN": "secret",
            "HF_TOKEN_PATH": "/tmp/token",
            "HTTPS_PROXY": "http://proxy.invalid",
            "WANDB_API_KEY": "secret",
        }
        with (
            mock.patch.dict(os.environ, inherited, clear=True),
            mock.patch(
                "vampip.sam3d.subprocess.Popen",
                return_value=process,
            ) as popen,
        ):
            SubprocessSam3dWorker()(
                self.config,
                paths,
                manager.runtime_dir,
            )

        options = popen.call_args.kwargs
        self.assertTrue(options["start_new_session"])
        command = popen.call_args.args[0]
        self.assertEqual(
            command[command.index("--model-id") + 1],
            "vit_hmr_512_384",
        )
        self.assertEqual(
            command[command.index("--backbone") + 1],
            "vit_hmr_512_384",
        )
        environment = options["env"]
        self.assertEqual(environment["SAFE_KEEP"], "yes")
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(environment["WANDB_MODE"], "disabled")
        self.assertEqual(
            environment["TMPDIR"],
            str(manager.runtime_dir / "tmp"),
        )
        for key in inherited:
            if key not in {"PATH", "SAFE_KEEP", "PYTHONNOUSERSITE"}:
                self.assertNotIn(key, environment)
        process.wait.assert_called_once_with(
            timeout=self.config.timeout_seconds
        )

        assert self.config.checkpoint is not None
        (self.config.checkpoint.parent / "model_config.yaml").write_text(
            "MODEL:\n  BACKBONE:\n    TYPE: dinov3_vith16plus\n",
            encoding="utf-8",
        )
        dinov3_repo = self.base / "dinov3"
        (dinov3_repo / "dinov3").mkdir(parents=True)
        (dinov3_repo / "dinov3" / "__init__.py").write_text(
            "",
            encoding="utf-8",
        )
        (dinov3_repo / "hubconf.py").write_text("", encoding="utf-8")
        config = replace(self.config, dinov3_repo=dinov3_repo)
        with mock.patch(
            "vampip.sam3d.subprocess.Popen",
            return_value=process,
        ) as dino_popen:
            SubprocessSam3dWorker()(
                config,
                paths,
                manager.runtime_dir,
            )
        command = dino_popen.call_args.args[0]
        option = command.index("--dinov3-repo")
        self.assertEqual(command[option + 1], str(dinov3_repo))

    def test_subprocess_timeout_terminates_then_kills_process_group(self) -> None:
        manager = self.manager()
        created = manager.create(png_header(), "image/png")
        paths = manager._paths(created["id"])
        process = mock.Mock()
        process.pid = 43210
        process.wait.side_effect = [
            subprocess.TimeoutExpired("sam3d-worker", 1800),
            subprocess.TimeoutExpired("sam3d-worker", 5),
            -signal.SIGKILL,
        ]
        with (
            mock.patch(
                "vampip.sam3d.subprocess.Popen",
                return_value=process,
            ) as popen,
            mock.patch("vampip.sam3d.os.killpg") as killpg,
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded"):
                SubprocessSam3dWorker()(
                    self.config,
                    paths,
                    manager.runtime_dir,
                )

        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(
            killpg.call_args_list,
            [
                mock.call(process.pid, signal.SIGTERM),
                mock.call(process.pid, signal.SIGKILL),
            ],
        )
        self.assertEqual(process.wait.call_count, 3)

    def test_retry_removes_all_stale_worker_outputs_before_launch(self) -> None:
        class FailingThenFreshWorker:
            def __init__(self) -> None:
                self.calls = 0
                self.saw_clean_retry = False

            def __call__(self, config, paths, runtime_dir) -> None:
                self.calls += 1
                if self.calls == 1:
                    paths.manifest.write_text("stale", encoding="utf-8")
                    paths.overlay.write_bytes(b"stale")
                    paths.arrays.write_bytes(b"stale")
                    raise RuntimeError("first attempt failed")
                self.saw_clean_retry = not any(
                    path.exists()
                    for path in (
                        paths.manifest,
                        paths.overlay,
                        paths.arrays,
                    )
                )
                FakeWorker()(config, paths, runtime_dir)

        worker = FailingThenFreshWorker()
        manager = Sam3dJobManager(
            self.state,
            config=self.config,
            worker=worker,
        )
        created = manager.create(png_header(), "image/png")
        manager.queue(created["id"])
        manager._queue.join()
        self.assertEqual(manager.get(created["id"])["state"], "failed")

        manager.queue(created["id"])
        manager._queue.join()
        self.assertTrue(worker.saw_clean_retry)
        self.assertEqual(manager.get(created["id"])["state"], "succeeded")

    def test_fake_worker_contract_persists_job_outside_tmp(self) -> None:
        manager, job = self.completed_job()
        self.assertEqual(job["state"], "succeeded")
        self.assertEqual(job["person_count"], 1)
        self.assertRegex(job["revision"], r"^[0-9a-f]{32}$")
        directory = manager.jobs_dir / job["id"]
        self.assertTrue((directory / "source.png").is_file())
        self.assertTrue((directory / "manifest.json").is_file())
        self.assertEqual(
            directory.parent,
            self.state.resolve() / "sam3d" / "jobs",
        )
        self.assertEqual(manager.manifest(job["id"])["revision"], job["revision"])

    def test_manifest_revalidates_identity_content_and_revisions_on_read(
        self,
    ) -> None:
        manager, job = self.completed_job()
        path = manager.jobs_dir / job["id"] / "manifest.json"
        original = path.read_bytes()
        document = json.loads(original)

        document["people"][0]["focalLength"] = 101.0
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(Sam3dJobError, "revision"):
            manager.manifest(job["id"])

        path.write_bytes(original)
        document = json.loads(original)
        document["jobId"] = "f" * 32
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(Sam3dJobError, "validation"):
            manager.manifest(job["id"])

        path.write_bytes(original)
        document = json.loads(original)
        document["schema"] = 1
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(Sam3dJobError, "validation"):
            manager.manifest(job["id"])

        path.write_bytes(original)
        document = json.loads(original)
        document["revision"] = "f" * 32
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(Sam3dJobError, "revision"):
            manager.manifest(job["id"])

        path.write_bytes(original)
        with connect(self.state) as connection:
            connection.execute(
                "UPDATE sam3d_jobs SET revision = ? WHERE id = ?",
                ("f" * 32, job["id"]),
            )
        with self.assertRaisesRegex(Sam3dJobError, "revision"):
            manager.manifest(job["id"])

    def test_manifest_revalidates_size_on_read(self) -> None:
        manager, job = self.completed_job()
        path = manager.jobs_dir / job["id"] / "manifest.json"
        path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(Sam3dJobError, "validation"):
            manager.manifest(job["id"])

    def test_manifest_is_bound_to_the_persisted_request_contract(self) -> None:
        manager, job = self.completed_job()
        directory = manager.jobs_dir / job["id"]
        manifest_path = directory / "manifest.json"
        request_path = directory / "request.json"
        original_manifest = manifest_path.read_bytes()
        original_request = request_path.read_bytes()

        mutations = (
            lambda document: document["source"].__setitem__(
                "contentType", "image/jpeg"
            ),
            lambda document: document["source"].__setitem__(
                "bbox", [0.0, 0.0, 63.0, 64.0]
            ),
            lambda document: document["source"].__setitem__(
                "verticalFov", 56.0
            ),
            lambda document: document["people"][0].__setitem__(
                "keypointNames", list(reversed(MHR70_NAMES))
            ),
            lambda document: document["engine"].__setitem__(
                "modelId", "dinov3_vith16plus"
            ),
            lambda document: document.__setitem__(
                "engine", {"name": "other", "mode": "native-standalone"}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = json.loads(original_manifest)
                mutate(document)
                manifest_path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(Sam3dJobError, "validation"):
                    manager.manifest(job["id"])
                manifest_path.write_bytes(original_manifest)

        request = json.loads(original_request)
        manifest = json.loads(original_manifest)
        request["verticalFov"] = 56.0
        manifest["source"]["verticalFov"] = 56.0
        request_path.write_text(json.dumps(request), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(Sam3dJobError, "validation"):
            manager.manifest(job["id"])

    def test_vam_solution_uses_exact_bounded_bridge_schema(self) -> None:
        job_id = "a" * 32
        solution = build_vam_solution(
            sample_manifest(job_id),
            job_id=job_id,
            person_index=0,
            height_m=1.65,
            aspect_ratio="16:9",
            output_resolution="1280x720 (HD)",
            image_format="jpeg",
            horizontal_fov=72.0,
        )
        self.assertEqual(solution["schema"], 1)
        self.assertEqual(
            solution["coordinateSpace"],
            "selected-person-hip-relative",
        )
        self.assertEqual(len(solution["controllers"]), 19)
        self.assertEqual(
            {item["id"] for item in solution["controllers"]},
            VAM_CONTROLLER_IDS,
        )
        camera = solution["camera"]
        self.assertEqual(
            set(camera),
            {
                "position",
                "rotation",
                "flatHorizontalFov",
                "aspectRatio",
                "outputResolution",
                "imageFormat",
                "basename",
            },
        )
        self.assertEqual(camera["aspectRatio"], "16:9")
        self.assertEqual(camera["outputResolution"], "1280x720 (HD)")
        self.assertEqual(camera["imageFormat"], "jpeg")
        self.assertEqual(camera["basename"], job_id)
        self.assertEqual(camera["flatHorizontalFov"], 72.0)
        self.assertNotIn("requestId", camera)
        self.assertRegex(solution["revision"], r"^[0-9a-f]{32}$")

    def test_vam_solution_maps_head_to_vam_pivot_and_full_face_frame(self) -> None:
        job_id = "c" * 32
        manifest = sample_manifest(job_id)
        person = manifest["people"][0]
        points = person["keypoints3d"]
        face = {
            "nose": [0.0, -0.715, 0.08],
            "left-eye": [-0.04, -0.735, 0.05],
            "right-eye": [0.04, -0.735, 0.05],
            "left-ear": [-0.09, -0.735, 0.0],
            "right-ear": [0.09, -0.735, 0.0],
        }
        for name, point in face.items():
            points[MHR70_NAMES.index(name)] = point
        # A frontal face has broad bilateral spans, so it must retain the
        # established eye-to-ear frame even when nose pitch differs slightly.
        points2d = person["keypoints2d"]
        frontal = {
            "nose": [32.0, 20.0],
            "left-eye": [27.0, 18.0],
            "right-eye": [37.0, 18.0],
            "left-ear": [23.0, 22.0],
            "right-ear": [41.0, 22.0],
            "left-shoulder": [10.0, 38.0],
            "right-shoulder": [54.0, 38.0],
        }
        for name, point in frontal.items():
            points2d[MHR70_NAMES.index(name)] = point
        solution = build_vam_solution(
            manifest,
            job_id=job_id,
            height_m=1.65,
        )
        controllers = {item["id"]: item for item in solution["controllers"]}
        neck = controllers["neckControl"]
        head = controllers["headControl"]
        offset = [
            head["position"][axis] - neck["position"][axis]
            for axis in range(3)
        ]
        self.assertAlmostEqual(offset[0], 0.0, places=6)
        # The stable ear midpoint corrects the generic VaM bind pivot toward
        # this person's inferred skull center.
        self.assertLess(offset[1], 1.65 * 0.0655)
        self.assertGreater(offset[1], 0.09)
        self.assertLess(offset[2], 1.65 * 0.0045)
        self.assertGreater(offset[2], 0.0)
        for actual, expected in zip(
            head["rotation"],
            [0.0, 0.0, 0.0, 1.0],
        ):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_vam_solution_profile_uses_nose_forward_when_eyes_bias_pitch(
        self,
    ) -> None:
        job_id = "7" * 32
        manifest = sample_manifest(job_id)
        person = manifest["people"][0]
        points3d = person["keypoints3d"]
        points2d = person["keypoints2d"]
        # Real DINO rear-profile landmarks from cfefe.../50e...: the hidden
        # eye biases the legacy frame upward, while nose and neck agree.
        landmarks = {
            "nose": (
                [0.1858126819, -1.4645458460, 0.2914017737],
                [649.3406982, 181.5389557],
            ),
            "left-eye": (
                [0.1559330523, -1.5081348419, 0.3152230382],
                [624.3892212, 151.9182129],
            ),
            "right-eye": (
                [0.1573862135, -1.4971610308, 0.2529760599],
                [629.4364014, 148.3008728],
            ),
            "left-ear": (
                [0.0594783053, -1.4980165958, 0.3589602411],
                [548.6457520, 167.8433685],
            ),
            "right-ear": (
                [0.0626854971, -1.4706892967, 0.2128210217],
                [554.3181763, 161.7621155],
            ),
            "neck": (
                [0.0231966171, -1.3516864777, 0.2664923072],
                [521.5877075, 266.9781799],
            ),
            "left-shoulder": (
                [-0.1459932178, -1.3289077282, 0.2944751382],
                [388.6115723, 288.5788574],
            ),
            "right-shoulder": (
                [0.1632560641, -1.3152276278, 0.1947005540],
                [638.2306519, 287.1569824],
            ),
        }
        for name, (point3d, point2d) in landmarks.items():
            index = MHR70_NAMES.index(name)
            points3d[index] = point3d
            points2d[index] = point2d

        legacy_manifest = json.loads(json.dumps(manifest))
        legacy_manifest["people"][0]["keypoints2d"] = [
            [32.0, 32.0] for _ in MHR70_NAMES
        ]
        profile = build_vam_solution(manifest, job_id=job_id)
        legacy = build_vam_solution(legacy_manifest, job_id=job_id)
        profile_head = {
            item["id"]: item for item in profile["controllers"]
        }["headControl"]
        legacy_head = {
            item["id"]: item for item in legacy["controllers"]
        }["headControl"]

        rotation_dot = abs(
            sum(
                left * right
                for left, right in zip(
                    profile_head["rotation"],
                    legacy_head["rotation"],
                )
            )
        )
        correction = math.degrees(
            2.0 * math.acos(min(1.0, rotation_dot))
        )
        self.assertAlmostEqual(correction, 20.1698, places=3)
        for actual, expected in zip(
            profile_head["rotation"],
            [-0.00790073, 0.68890222, -0.12095509, 0.71464759],
        ):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_vam_solution_validates_named_2d_keypoints(self) -> None:
        job_id = "6" * 32
        manifest = sample_manifest(job_id)
        manifest["people"][0]["keypoints2d"][0][0] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            build_vam_solution(manifest, job_id=job_id)

        manifest = sample_manifest(job_id)
        manifest["people"][0]["keypointNames"] = list(reversed(MHR70_NAMES))
        with self.assertRaisesRegex(ValueError, "names"):
            build_vam_solution(manifest, job_id=job_id)

    def test_vam_solution_head_matches_front_camera_body_yaw(self) -> None:
        job_id = "f" * 32
        manifest = sample_manifest(job_id)
        points = manifest["people"][0]["keypoints3d"]
        for left_name, right_name in (
            ("left-hip", "right-hip"),
            ("left-shoulder", "right-shoulder"),
        ):
            left = points[MHR70_NAMES.index(left_name)]
            right = points[MHR70_NAMES.index(right_name)]
            left[0], right[0] = abs(left[0]), -abs(right[0])
        face = {
            "nose": [0.0, -0.715, -0.08],
            "left-eye": [0.04, -0.735, -0.05],
            "right-eye": [-0.04, -0.735, -0.05],
            "left-ear": [0.09, -0.735, 0.0],
            "right-ear": [-0.09, -0.735, 0.0],
        }
        for name, point in face.items():
            points[MHR70_NAMES.index(name)] = point

        solution = build_vam_solution(manifest, job_id=job_id)
        controllers = {item["id"]: item for item in solution["controllers"]}
        neck_rotation = controllers["neckControl"]["rotation"]
        head_rotation = controllers["headControl"]["rotation"]
        self.assertAlmostEqual(
            abs(sum(a * b for a, b in zip(neck_rotation, head_rotation))),
            1.0,
            places=6,
        )
        self.assertAlmostEqual(abs(head_rotation[1]), 1.0, places=6)

    def test_vam_solution_head_frame_falls_back_for_degenerate_face(self) -> None:
        job_id = "d" * 32
        manifest = sample_manifest(job_id)
        person = manifest["people"][0]
        points = person["keypoints3d"]
        collapsed = [0.0, -0.62, 0.0]
        for name in (
            "nose",
            "left-eye",
            "right-eye",
            "left-ear",
            "right-ear",
        ):
            points[MHR70_NAMES.index(name)] = list(collapsed)

        solution = build_vam_solution(manifest, job_id=job_id)
        controllers = {item["id"]: item for item in solution["controllers"]}
        self.assertEqual(
            controllers["headControl"]["rotation"],
            controllers["neckControl"]["rotation"],
        )
        neck = controllers["neckControl"]["position"]
        head = controllers["headControl"]["position"]
        self.assertAlmostEqual(head[1] - neck[1], 1.65 * 0.0655, places=6)
        self.assertAlmostEqual(head[2] - neck[2], 1.65 * 0.0045, places=6)
        self.assertAlmostEqual(
            sum(
                component * component
                for component in controllers["headControl"]["rotation"]
            ),
            1.0,
            places=6,
        )

    def test_vam_solution_preserves_an_inverted_head_frame(self) -> None:
        job_id = "e" * 32
        manifest = sample_manifest(job_id)
        points = manifest["people"][0]["keypoints3d"]
        face = {
            "nose": [0.0, -0.755, 0.08],
            "left-eye": [0.04, -0.735, 0.05],
            "right-eye": [-0.04, -0.735, 0.05],
            "left-ear": [0.09, -0.735, 0.0],
            "right-ear": [-0.09, -0.735, 0.0],
        }
        for name, point in face.items():
            points[MHR70_NAMES.index(name)] = point

        solution = build_vam_solution(manifest, job_id=job_id)
        controllers = {item["id"]: item for item in solution["controllers"]}
        head = controllers["headControl"]
        self.assertAlmostEqual(head["rotation"][0], 0.0, places=6)
        self.assertAlmostEqual(head["rotation"][1], 0.0, places=6)
        self.assertAlmostEqual(abs(head["rotation"][2]), 1.0, places=6)
        self.assertAlmostEqual(head["rotation"][3], 0.0, places=6)
        hip_rotation = controllers["hipControl"]["rotation"]
        neck_rotation = controllers["neckControl"]["rotation"]
        neck_arc = 2.0 * math.acos(
            min(
                1.0,
                abs(
                    sum(
                        a * b
                        for a, b in zip(hip_rotation, neck_rotation)
                    )
                ),
            )
        )
        self.assertAlmostEqual(math.degrees(neck_arc), 40.0, places=5)

    def test_vam_solution_rejects_outlier_ears_for_head_pivot(self) -> None:
        job_id = "8" * 32
        manifest = sample_manifest(job_id)
        points = manifest["people"][0]["keypoints3d"]
        face = {
            "nose": [0.0, -0.715, 0.08],
            "left-eye": [-0.04, -0.735, 0.05],
            "right-eye": [0.04, -0.735, 0.05],
            # A 32 cm raw ear span is outside the bounded anatomical window,
            # even though it still produces a mathematically valid face frame.
            "left-ear": [-0.16, -0.735, 0.0],
            "right-ear": [0.16, -0.735, 0.0],
        }
        for name, point in face.items():
            points[MHR70_NAMES.index(name)] = point

        solution = build_vam_solution(manifest, job_id=job_id)
        controllers = {item["id"]: item for item in solution["controllers"]}
        neck = controllers["neckControl"]["position"]
        head = controllers["headControl"]["position"]
        self.assertAlmostEqual(head[0] - neck[0], 0.0, places=7)
        self.assertAlmostEqual(
            head[1] - neck[1],
            1.65 * 0.0655,
            places=7,
        )
        self.assertAlmostEqual(
            head[2] - neck[2],
            1.65 * 0.0045,
            places=7,
        )

    def test_vam_solution_uses_observed_skull_and_splits_extreme_head_yaw(
        self,
    ) -> None:
        job_id = "9" * 32
        manifest = sample_manifest(job_id)
        points = manifest["people"][0]["keypoints3d"]
        # Synthetic equivalent of the rear-view capture: the torso remains
        # camera-aligned while the skull is laterally displaced and the face
        # turns 90 degrees. Canonical face axes are right=-Z, up=+Y,
        # forward=+X after conversion to Unity coordinates.
        face = {
            "nose": [0.12, -0.78, 0.02],
            "left-eye": [0.09, -0.76, 0.08],
            "right-eye": [0.09, -0.76, -0.04],
            "left-ear": [0.04, -0.76, 0.11],
            "right-ear": [0.04, -0.76, -0.07],
        }
        for name, point in face.items():
            points[MHR70_NAMES.index(name)] = point

        solution = build_vam_solution(manifest, job_id=job_id)
        controllers = {item["id"]: item for item in solution["controllers"]}
        hip_rotation = controllers["hipControl"]["rotation"]
        neck_rotation = controllers["neckControl"]["rotation"]
        head_rotation = controllers["headControl"]["rotation"]
        neck = controllers["neckControl"]["position"]
        head = controllers["headControl"]["position"]

        # The old fixed bind offset produced only ~7 mm of lateral movement
        # for this yaw. The observed ear midpoint now moves the skull pivot
        # materially toward SAM's ~34 mm lateral estimate.
        self.assertGreater(head[0] - neck[0], 0.025)
        self.assertGreater(head[1] - neck[1], 0.11)
        self.assertGreater(head[2] - neck[2], 0.005)

        torso_neck_dot = abs(
            sum(a * b for a, b in zip(hip_rotation, neck_rotation))
        )
        neck_head_dot = abs(
            sum(a * b for a, b in zip(neck_rotation, head_rotation))
        )
        torso_head_dot = abs(
            sum(a * b for a, b in zip(hip_rotation, head_rotation))
        )
        self.assertLess(torso_neck_dot, 0.99)
        self.assertLess(neck_head_dot, 0.99)
        self.assertGreater(torso_neck_dot, torso_head_dot)
        self.assertGreater(neck_head_dot, torso_head_dot)
        self.assertAlmostEqual(abs(head_rotation[1]), 2**-0.5, places=6)
        neck_arc = 2.0 * math.acos(min(1.0, torso_neck_dot))
        self.assertAlmostEqual(math.degrees(neck_arc), 40.0, places=5)

    def test_vam_solution_rejects_camera_outside_bridge_bounds(self) -> None:
        job_id = "b" * 32
        manifest = sample_manifest(job_id)
        manifest["people"][0]["predCamT"] = [0.0, 0.0, 100.0]
        with self.assertRaisesRegex(ValueError, "camera position"):
            build_vam_solution(
                manifest,
                job_id=job_id,
                person_index=0,
                height_m=1.65,
            )

    def test_person_selection_is_revision_guarded_and_persistent(self) -> None:
        manager, job = self.completed_job()
        selected = manager.select_person(
            job["id"],
            expected_revision=job["revision"],
            person_index=0,
        )
        self.assertEqual(selected["selected_person_index"], 0)
        with self.assertRaisesRegex(ValueError, "revision"):
            manager.select_person(
                job["id"],
                expected_revision="f" * 32,
                person_index=0,
            )

    def test_apply_publishes_fixed_solution_and_revision_bound_request(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        scene = {
            "available": True,
            "vam_running": True,
            "capabilities": [
                "atom-add",
                "sam3d-apply-v1",
                "sam3d-camera-vrfunscript-v1",
            ],
            "atoms": [
                {"uid": "Person", "type": "Person"},
                {
                    "uid": "SAM Camera",
                    "type": "Empty",
                    "sam3dCamera": {"compatible": True},
                },
            ],
        }
        service._require_live_capability = mock.Mock(return_value=scene)
        result = service.apply_sam3d_result(
            job["id"],
            expected_job_revision=job["revision"],
            target_uid="Person",
            camera_uid="SAM Camera",
            aspect_ratio="16:9",
            output_resolution="1280x720 (HD)",
        )
        solution_path = (
            self.vam_root
            / "Saves"
            / "PluginData"
            / "VAMPip"
            / "SAM3D"
            / f"{job['id']}.json"
        )
        solution = json.loads(solution_path.read_text(encoding="utf-8"))
        request = json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(request["command"], "applySam3dResult")
        self.assertEqual(request["jobId"], job["id"])
        self.assertEqual(
            request["expectedRevision"],
            solution["revision"],
        )
        self.assertRegex(request["solutionSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            request["solutionSha256"],
            hashlib.sha256(solution_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(result["solution_revision"], solution["revision"])
        self.assertNotIn("sourcePath", json.dumps(request))

    def test_reference_stages_validated_source_and_publishes_opaque_request(
        self,
    ) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        scene = {
            "available": True,
            "vam_running": True,
            "capabilities": [
                "sam3d-reference-v1",
                "sam3d-camera-vrfunscript-v1",
            ],
            "atoms": [
                {"uid": "Person", "type": "Person"},
                {
                    "uid": "SAM Camera",
                    "type": "Empty",
                    "sam3dCamera": {"compatible": True},
                },
            ],
        }
        service._require_live_capability = mock.Mock(return_value=scene)

        result = service.show_sam3d_reference(
            job["id"],
            expected_job_revision=job["revision"],
            target_uid="Person",
            person_index=0,
            height_m=1.65,
            camera_uid="SAM Camera",
            create_camera=False,
            horizontal_fov=70.0,
        )

        staged = (
            self.vam_root
            / "Custom"
            / "Images"
            / "VAMPip"
            / "SAM3D"
            / f"{job['id']}.png"
        )
        source, _ = manager.artifact(job["id"], "source")
        self.assertEqual(staged.read_bytes(), source.read_bytes())
        self.assertEqual(
            result["reference"]["resource_ref"],
            f"Custom/Images/VAMPip/SAM3D/{job['id']}.png",
        )
        self.assertEqual(
            result["reference"]["sha256"],
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        request = json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(request["command"], "showSam3dReference")
        self.assertEqual(request["expectedJobRevision"], job["revision"])
        self.assertEqual(
            request["referenceResourceRef"],
            f"Custom/Images/VAMPip/SAM3D/{job['id']}.png",
        )
        self.assertEqual(request["referenceSha256"], result["reference"]["sha256"])
        self.assertEqual(request["referenceWidth"], 64)
        self.assertEqual(request["referenceHeight"], 64)
        self.assertRegex(request["solutionSha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("sourcePath", json.dumps(request))

    def test_reference_staging_is_immutable_and_rejects_symlink_sources(
        self,
    ) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            sam3d_manager=manager,
        )
        reference = service._stage_sam3d_reference(manager, job["id"], job)
        staged = (
            self.vam_root
            / Path(str(reference["resource_ref"]))
        )
        staged.write_bytes(png_header(32, 32))
        with self.assertRaisesRegex(FileExistsError, "different data"):
            service._stage_sam3d_reference(manager, job["id"], job)

        staged.unlink()
        source, _ = manager.artifact(job["id"], "source")
        replacement = self.base / "replacement.png"
        replacement.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(replacement)
        with self.assertRaisesRegex(ValueError, "regular file"):
            service._stage_sam3d_reference(manager, job["id"], job)
        source.unlink()
        source.write_bytes(b"not-a-png")
        with self.assertRaisesRegex(ValueError, "magic/header"):
            service._stage_sam3d_reference(manager, job["id"], job)

    def test_apply_keep_reference_stages_without_a_visible_panel(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        service._require_live_capability = mock.Mock(
            return_value={
                "available": True,
                "vam_running": True,
                "capabilities": [
                    "sam3d-apply-v1",
                    "sam3d-camera-vrfunscript-v1",
                ],
                "atoms": [
                    {"uid": "Person", "type": "Person"},
                    {
                        "uid": "SAM Camera",
                        "type": "Empty",
                        "sam3dCamera": {"compatible": True},
                    },
                ],
                "sam3d": {
                    "applied": False,
                    "reference": {"active": False},
                },
            }
        )
        result = service.apply_sam3d_result(
            job["id"],
            expected_job_revision=job["revision"],
            target_uid="Person",
            camera_uid="SAM Camera",
            keep_reference=True,
        )
        request = json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )
        staged = (
            self.vam_root
            / "Custom"
            / "Images"
            / "VAMPip"
            / "SAM3D"
            / f"{job['id']}.png"
        )
        self.assertTrue(staged.is_file())
        self.assertIs(request["keepReference"], True)
        self.assertEqual(request["expectedJobRevision"], job["revision"])
        self.assertEqual(
            request["referenceResourceRef"],
            f"Custom/Images/VAMPip/SAM3D/{job['id']}.png",
        )
        self.assertEqual(
            request["referenceSha256"],
            hashlib.sha256(staged.read_bytes()).hexdigest(),
        )
        self.assertEqual(request["referenceWidth"], 64)
        self.assertEqual(request["referenceHeight"], 64)
        self.assertEqual(result["reference"]["resource_ref"], request["referenceResourceRef"])

    def test_job_decoration_exposes_only_matching_live_reference(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            sam3d_manager=manager,
        )
        service._scene_snapshot = mock.Mock(
            return_value={
                "available": True,
                "vam_running": True,
                "bridge": {"instanceId": "bridge-instance"},
                "sam3d": {
                    "applied": False,
                    "reference": {
                        "active": True,
                        "atomUid": "VAMPip SAM3D Reference",
                        "jobId": job["id"],
                        "jobRevision": job["revision"],
                        "solutionRevision": "f" * 32,
                        "targetUid": "Person",
                        "sourceWidth": 64,
                        "sourceHeight": 64,
                        "alignedToPose": True,
                    },
                },
            }
        )
        decorated = service.sam3d_job(job["id"])
        self.assertEqual(
            decorated["reference"],
            {
                "active": True,
                "visible": True,
                "job_id": job["id"],
                "job_revision": job["revision"],
                "solution_revision": "f" * 32,
                "target_uid": "Person",
                "atom_uid": "VAMPip SAM3D Reference",
                "aligned_to_pose": True,
                "mode": "pose-aligned",
                "source_width": 64,
                "source_height": 64,
            },
        )

    def test_solution_reload_recomputes_revision_before_undo(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        solution = build_vam_solution(
            manager.manifest(job["id"]),
            job_id=job["id"],
        )
        path = service._sam3d_solution_path(job["id"])
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(solution), encoding="utf-8")
        service._require_live_capability = mock.Mock(
            return_value={
                "available": True,
                "vam_running": True,
                "capabilities": ["sam3d-undo-v1"],
                "sam3d": {
                    "applied": True,
                    "undoAvailable": True,
                    "jobId": job["id"],
                    "revision": solution["revision"],
                    "targetUid": "Person",
                    "cameraUid": "SAM Camera",
                },
            }
        )
        service._queue_bridge_request = mock.Mock(return_value="c" * 32)

        tampered = dict(solution)
        tampered["controllers"] = list(solution["controllers"])
        tampered["controllers"][0] = dict(tampered["controllers"][0])
        tampered["controllers"][0]["position"] = [1.0, 0.0, 0.0]
        path.write_text(json.dumps(tampered), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "revision"):
            service.undo_sam3d_result(
                job["id"],
                expected_revision=solution["revision"],
            )
        service._queue_bridge_request.assert_not_called()

    def test_apply_rejects_reapply_while_exact_solution_is_live(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        solution = build_vam_solution(
            manager.manifest(job["id"]),
            job_id=job["id"],
        )
        scene = {
            "available": True,
            "vam_running": True,
            "bridge": {"instanceId": "bridge-instance"},
            "capabilities": [
                "sam3d-apply-v1",
                "sam3d-camera-vrfunscript-v1",
            ],
            "atoms": [
                {"uid": "Person", "type": "Person"},
                {
                    "uid": "SAM Camera",
                    "type": "Empty",
                    "sam3dCamera": {"compatible": True},
                },
            ],
            "sam3d": {
                "applied": True,
                "undoAvailable": True,
                "jobId": job["id"],
                "revision": solution["revision"],
                "targetUid": "Person",
                "cameraUid": "SAM Camera",
            },
        }
        service._require_live_capability = mock.Mock(return_value=scene)

        with self.assertRaisesRegex(ValueError, "undo"):
            service.apply_sam3d_result(
                job["id"],
                expected_job_revision=job["revision"],
                target_uid="Person",
                camera_uid="SAM Camera",
            )

        self.assertFalse(
            (bridge_directory(self.vam_root) / "request.json").exists()
        )
        self.assertFalse(service._sam3d_solution_path(job["id"]).exists())

    def test_apply_rejects_a_post_success_modified_manifest(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        service._require_live_capability = mock.Mock(
            return_value={
                "available": True,
                "vam_running": True,
                "capabilities": [
                    "sam3d-apply-v1",
                    "sam3d-camera-vrfunscript-v1",
                ],
                "atoms": [
                    {"uid": "Person", "type": "Person"},
                    {
                        "uid": "SAM Camera",
                        "type": "Empty",
                        "sam3dCamera": {"compatible": True},
                    },
                ],
            }
        )
        path = manager.jobs_dir / job["id"] / "manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["people"][0]["predCamT"] = [0.0, 0.0, 2.0]
        path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(Sam3dJobError, "revision"):
            service.apply_sam3d_result(
                job["id"],
                expected_job_revision=job["revision"],
                target_uid="Person",
                camera_uid="SAM Camera",
            )
        self.assertFalse(
            (bridge_directory(self.vam_root) / "request.json").exists()
        )
        self.assertFalse(service._sam3d_solution_path(job["id"]).exists())

    def test_capture_requires_current_solution_revision_and_camera(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        scene = {
            "available": True,
            "vam_running": True,
            "bridge": {"instanceId": "bridge-instance"},
            "capabilities": [
                "sam3d-capture-v1",
                "sam3d-camera-vrfunscript-v1",
            ],
            "atoms": [
                {
                    "uid": "SAM Camera",
                    "type": "Empty",
                    "sam3dCamera": {"compatible": True},
                }
            ],
        }
        service._require_live_capability = mock.Mock(return_value=scene)
        solution = build_vam_solution(
            manager.manifest(job["id"]),
            job_id=job["id"],
        )
        solution_path = service._sam3d_solution_path(job["id"])
        solution_path.parent.mkdir(parents=True)
        solution_path.write_text(json.dumps(solution), encoding="utf-8")
        service._queue_bridge_request = mock.Mock(
            side_effect=lambda writer: writer()
        )

        with self.assertRaisesRegex(ValueError, "must be applied"):
            service.capture_sam3d_result(
                job["id"],
                expected_revision=solution["revision"],
                camera_uid="SAM Camera",
            )

        scene["sam3d"] = {
            "applied": True,
            "undoAvailable": True,
            "jobId": "f" * 32,
            "revision": solution["revision"],
            "targetUid": "Person",
            "cameraUid": "SAM Camera",
        }
        with self.assertRaisesRegex(ValueError, "must be applied"):
            service.capture_sam3d_result(
                job["id"],
                expected_revision=solution["revision"],
                camera_uid="SAM Camera",
            )

        scene["sam3d"]["jobId"] = job["id"]
        scene["sam3d"]["revision"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "must be applied"):
            service.capture_sam3d_result(
                job["id"],
                expected_revision=solution["revision"],
                camera_uid="SAM Camera",
            )

        scene["sam3d"]["revision"] = solution["revision"]
        scene["sam3d"]["cameraUid"] = "Other Camera"
        with self.assertRaisesRegex(ValueError, "camera_uid"):
            service.capture_sam3d_result(
                job["id"],
                expected_revision=solution["revision"],
                camera_uid="SAM Camera",
            )

        scene["sam3d"]["cameraUid"] = "SAM Camera"
        result = service.capture_sam3d_result(
            job["id"],
            expected_revision=solution["revision"],
            camera_uid="SAM Camera",
        )
        self.assertRegex(result["bridge_request"], r"^[0-9a-f]{32}$")
        request = json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(request["command"], "captureSam3dResult")
        self.assertEqual(
            request["solutionSha256"],
            hashlib.sha256(solution_path.read_bytes()).hexdigest(),
        )
        action = manager.get(job["id"])["last_vam_action"]
        self.assertEqual(action["action"], "capture")
        self.assertEqual(action["capture_extension"], "jpg")
        self.assertEqual(action["capture_content_type"], "image/jpeg")

    def test_successful_capture_history_survives_later_terminal_actions(
        self,
    ) -> None:
        manager, job = self.completed_job()
        revision = str(job["revision"])
        capture_request = "b" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=revision,
            request_id=capture_request,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="jpg",
            capture_content_type="image/jpeg",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=capture_request,
            state="succeeded",
            message="capture complete",
        )
        captured = manager.get(job["id"])["last_capture"]
        self.assertEqual(
            captured,
            {
                "request_id": capture_request,
                "revision": revision,
                "target_uid": "Person",
                "camera_uid": "SAM Camera",
                "extension": "jpg",
                "content_type": "image/jpeg",
                "captured_at_utc": captured["captured_at_utc"],
            },
        )

        undo_request = "c" * 32
        manager.record_vam_action(
            job["id"],
            action="undo",
            revision=revision,
            request_id=undo_request,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=undo_request,
            state="succeeded",
            message="undo complete",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=undo_request,
            state="failed",
            message="late conflicting result",
        )
        after_undo = manager.get(job["id"])
        self.assertEqual(after_undo["last_capture"], captured)
        self.assertEqual(after_undo["last_vam_action"]["state"], "succeeded")

        failed_capture = "d" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=revision,
            request_id=failed_capture,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="png",
            capture_content_type="image/png",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=failed_capture,
            state="failed",
            message="renderer failed",
        )
        after_failure = manager.get(job["id"])
        self.assertEqual(after_failure["last_capture"], captured)
        self.assertEqual(after_failure["last_vam_action"]["state"], "failed")
        self.assertEqual(after_failure["captures"], [captured])

    def test_successful_captures_keep_newest_fifty_per_job(self) -> None:
        manager, job = self.completed_job()
        revision = str(job["revision"])
        for index in range(55):
            request_id = f"{index + 1:032x}"
            manager.record_vam_action(
                job["id"],
                action="capture",
                revision=revision,
                request_id=request_id,
                target_uid="Person",
                camera_uid="SAM Camera",
                capture_extension="jpg",
                capture_content_type="image/jpeg",
            )
            manager.reconcile_vam_action(
                job["id"],
                request_id=request_id,
                state="succeeded",
                message="capture complete",
            )

        document = manager.get(job["id"])
        captures = document["captures"]
        self.assertEqual(len(captures), 50)
        self.assertEqual(captures[0]["request_id"], f"{55:032x}")
        self.assertEqual(captures[-1]["request_id"], f"{6:032x}")
        self.assertEqual(
            document["last_capture"]["request_id"],
            f"{55:032x}",
        )
        manager.close()
        restarted = self.manager()
        persisted = restarted.get(job["id"])
        self.assertEqual(
            [capture["request_id"] for capture in persisted["captures"]],
            [capture["request_id"] for capture in captures],
        )
        restarted.close()

    def test_capture_backfill_scans_new_and_legacy_roots(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
            sam3d_manager=manager,
        )
        service._scene_snapshot = mock.Mock(return_value={"available": False})
        legacy_request = "a" * 32
        current_request = "b" * 32
        invalid_request = "c" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=str(job["revision"]),
            request_id=current_request,
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="png",
            capture_content_type="image/png",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=current_request,
            state="succeeded",
            message="capture complete",
        )
        legacy_root = self.vam_root / "Saves" / "VR_Videos_And_Funscripts"
        current_root = self.vam_root / "Saves" / "screenshots" / "VAMPip"
        legacy_root.mkdir(parents=True)
        current_root.mkdir(parents=True)
        legacy = legacy_root / f"vampip_{legacy_request}_{job['id']}.jpg"
        current = current_root / f"vampip_{current_request}_{job['id']}.png"
        ignored = current_root / f"not-vampip_{invalid_request}_{job['id']}.png"
        legacy.write_bytes(b"legacy-jpeg")
        current.write_bytes(b"current-png")
        ignored.write_bytes(b"ignored")
        os.utime(legacy, (1000, 1000))
        os.utime(current, (2000, 2000))

        document = service.sam3d_job(job["id"])
        self.assertEqual(
            [capture["request_id"] for capture in document["captures"]],
            [current_request, legacy_request],
        )
        self.assertEqual(document["captures"][0]["size_bytes"], 11)
        self.assertEqual(document["captures"][0]["revision"], job["revision"])
        self.assertEqual(document["captures"][0]["target_uid"], "Person")
        self.assertEqual(document["captures"][0]["camera_uid"], "SAM Camera")
        self.assertEqual(
            document["captures"][0]["captured_at_utc"],
            "1970-01-01T00:33:20+00:00",
        )
        self.assertEqual(document["last_capture"]["request_id"], current_request)
        current_path, current_type = service.sam3d_capture_artifact(
            job["id"],
            current_request,
        )
        legacy_path, legacy_type = service.sam3d_capture_artifact(
            job["id"],
            legacy_request,
        )
        latest_path, latest_type = service.sam3d_artifact(
            job["id"],
            "capture",
        )
        self.assertEqual((current_path, current_type), (current, "image/png"))
        self.assertEqual((legacy_path, legacy_type), (legacy, "image/jpeg"))
        self.assertEqual((latest_path, latest_type), (current, "image/png"))
        with self.assertRaisesRegex(FileNotFoundError, "history"):
            service.sam3d_capture_artifact(job["id"], invalid_request)
        pending = current_root / f"vampip_{invalid_request}_{job['id']}.jpg"
        pending.write_bytes(b"incomplete")
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=str(job["revision"]),
            request_id=invalid_request,
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="jpg",
            capture_content_type="image/jpeg",
        )
        refreshed = service.sam3d_job(job["id"])
        self.assertNotIn(
            invalid_request,
            [capture["request_id"] for capture in refreshed["captures"]],
        )
        later_request = "d" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=str(job["revision"]),
            request_id=later_request,
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="jpg",
            capture_content_type="image/jpeg",
        )
        after_later_request = service.sam3d_job(job["id"])
        self.assertNotIn(
            invalid_request,
            [
                capture["request_id"]
                for capture in after_later_request["captures"]
            ],
        )
        listed = service.sam3d_jobs()["items"]
        listed_job = next(item for item in listed if item["id"] == job["id"])
        self.assertNotIn("captures", listed_job)

    def test_capture_artifact_survives_undo_and_manager_restart(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
            sam3d_manager=manager,
        )
        solution = build_vam_solution(
            manager.manifest(job["id"]),
            job_id=job["id"],
        )
        solution_path = service._sam3d_solution_path(job["id"])
        solution_path.parent.mkdir(parents=True)
        solution_path.write_text(json.dumps(solution), encoding="utf-8")
        request_id = "b" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=solution["revision"],
            request_id=request_id,
            bridge_instance="old-bridge",
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="jpg",
            capture_content_type="image/jpeg",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=request_id,
            state="succeeded",
            message="capture complete",
        )
        capture = (
            self.vam_root
            / "Saves"
            / "VR_Videos_And_Funscripts"
            / f"vampip_{request_id}_{job['id']}.jpg"
        )
        capture.parent.mkdir(parents=True)
        capture.write_bytes(b"jpeg")
        path, content_type = service.sam3d_artifact(job["id"], "capture")
        self.assertEqual(path, capture)
        self.assertEqual(content_type, "image/jpeg")

        undo_request = "c" * 32
        manager.record_vam_action(
            job["id"],
            action="undo",
            revision=solution["revision"],
            request_id=undo_request,
            bridge_instance="old-bridge",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=undo_request,
            state="succeeded",
            message="undo complete",
        )
        service.close()

        restarted = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
        )
        restarted._scene_snapshot = mock.Mock(
            side_effect=AssertionError(
                "durable capture lookup must not require the live bridge"
            )
        )
        path, content_type = restarted.sam3d_artifact(job["id"], "capture")
        self.assertEqual(path, capture)
        self.assertEqual(content_type, "image/jpeg")

        restarted._scene_snapshot = mock.Mock(
            return_value={"available": False}
        )
        decorated = restarted.sam3d_job(job["id"])
        self.assertTrue(decorated["capture_requested"])
        self.assertTrue(decorated["captured"])
        self.assertEqual(
            decorated["last_capture"]["request_id"],
            request_id,
        )
        self.assertEqual(decorated["last_vam_action"]["action"], "undo")
        restarted.close()

    def test_restarted_bridge_with_same_request_stays_pending(self) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        request_id = "e" * 32
        manager.record_vam_action(
            job["id"],
            action="apply",
            revision="d" * 32,
            request_id=request_id,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        service._scene_snapshot = mock.Mock(
            return_value={
                "available": True,
                "bridge": {
                    "instanceId": "bridge-two",
                    "requestId": request_id,
                    "state": "applying-sam3d",
                    "message": "Applying.",
                },
                "sam3d": {
                    "applied": False,
                    "undoAvailable": False,
                },
            }
        )

        pending = service.sam3d_job(job["id"])

        self.assertEqual(pending["action_state"], "running")
        self.assertEqual(
            manager.get(job["id"])["last_vam_action"]["state"],
            "queued",
        )

    def test_terminal_vam_action_cannot_change_terminal_state(self) -> None:
        manager, job = self.completed_job()
        request_id = "e" * 32
        manager.record_vam_action(
            job["id"],
            action="apply",
            revision="d" * 32,
            request_id=request_id,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=request_id,
            state="succeeded",
            message="Applied.",
        )
        terminal = manager.get(job["id"])["last_vam_action"]

        manager.reconcile_vam_action(
            job["id"],
            request_id=request_id,
            state="failed",
            message="Late conflicting failure.",
        )

        persisted = manager.get(job["id"])["last_vam_action"]
        self.assertEqual(persisted["state"], "succeeded")
        self.assertEqual(persisted["message"], "Applied.")
        self.assertEqual(
            persisted["finished_at_utc"],
            terminal["finished_at_utc"],
        )

    def test_job_state_tracks_live_bridge_outcome_not_mailbox_submission(
        self,
    ) -> None:
        manager, job = self.completed_job()
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [1234],
            sam3d_manager=manager,
        )
        revision = "d" * 32
        request_id = "e" * 32
        manager.record_vam_action(
            job["id"],
            action="apply",
            revision=revision,
            request_id=request_id,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        scene = {
            "available": True,
            "bridge": {
                "instanceId": "bridge-one",
                "requestId": request_id,
                "state": "applying-sam3d",
                "message": "Applying.",
            },
            "sam3d": {"applied": False, "undoAvailable": False},
        }
        service._scene_snapshot = mock.Mock(return_value=scene)

        pending = service.sam3d_job(job["id"])
        self.assertEqual(pending["action_state"], "running")
        self.assertFalse(pending["applied"])
        self.assertFalse(pending["can_undo"])

        scene["bridge"].update(
            {
                "state": "ok",
                "lastCompletedRequestId": request_id,
                "message": "Applied.",
            }
        )
        scene["sam3d"] = {
            "applied": True,
            "undoAvailable": True,
            "jobId": job["id"],
            "revision": revision,
            "targetUid": "Person",
            "cameraUid": "SAM Camera",
            "lastAction": {
                "requestId": request_id,
                "jobId": job["id"],
                "revision": revision,
                "action": "apply",
                "state": "ok",
                "message": "Applied.",
            },
        }
        applied = service.sam3d_job(job["id"])
        self.assertEqual(applied["action_state"], "succeeded")
        self.assertTrue(applied["applied"])
        self.assertTrue(applied["can_undo"])
        self.assertEqual(
            manager.get(job["id"])["last_vam_action"]["state"],
            "succeeded",
        )

        scene["bridge"] = {
            "instanceId": "bridge-two",
            "requestId": "1" * 32,
            "state": "ok",
        }
        scene["sam3d"] = {"applied": False, "undoAvailable": False}
        after_restart = service.sam3d_job(job["id"])
        self.assertEqual(after_restart["action_state"], "succeeded")
        self.assertFalse(after_restart["applied"])

        scene["bridge"] = {
            "instanceId": "bridge-one",
            "requestId": request_id,
            "state": "ok",
            "lastCompletedRequestId": request_id,
        }
        scene["sam3d"] = {
            "applied": True,
            "undoAvailable": True,
            "jobId": job["id"],
            "revision": revision,
            "targetUid": "Person",
            "cameraUid": "SAM Camera",
        }
        failed_request = "f" * 32
        manager.record_vam_action(
            job["id"],
            action="apply",
            revision=revision,
            request_id=failed_request,
            bridge_instance="bridge-one",
            target_uid="Other Person",
            camera_uid="SAM Camera",
        )
        scene["sam3d"]["lastAction"] = {
            "requestId": failed_request,
            "jobId": job["id"],
            "revision": revision,
            "action": "apply",
            "state": "error",
            "message": "Target disappeared.",
        }
        failed = service.sam3d_job(job["id"])
        self.assertEqual(failed["action_state"], "failed")
        self.assertFalse(failed["applied"])
        self.assertFalse(failed["can_undo"])

    def test_manager_close_closes_owned_worker(self) -> None:
        worker = mock.Mock()
        worker.close = mock.Mock()
        manager = Sam3dJobManager(
            self.state,
            config=self.config,
            worker=worker,
        )
        manager.close()
        worker.close.assert_called_once_with()
        with self.assertRaisesRegex(Sam3dJobError, "shutting down"):
            manager.queue("a" * 32)

    def test_bridge_install_includes_camera_preset_and_renderer_tree(self) -> None:
        installed = install_bridge(self.vam_root)
        camera_preset = (
            self.vam_root
            / "Custom"
            / "Atom"
            / "Empty"
            / "Preset_VAMPipSAM3DCamera.vap"
        )
        renderer = (
            self.vam_root
            / "Custom"
            / "Scripts"
            / "VAMPip"
            / "VRRendererX"
            / "Eosin_VRRenderer.cslist"
        )
        self.assertIn(camera_preset, installed)
        self.assertIn(renderer, installed)
        self.assertTrue(renderer.is_file())

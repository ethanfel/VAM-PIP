"""Standalone native SAM 3D Body worker.

This module is intentionally executable by a dedicated Python/Conda
interpreter. It does not import VAM-PIP or ComfyUI, and all heavyweight
dependencies remain on the worker side of the subprocess boundary.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any


MHR70_NAMES = (
    "nose",
    "left-eye",
    "right-eye",
    "left-ear",
    "right-ear",
    "left-shoulder",
    "right-shoulder",
    "left-elbow",
    "right-elbow",
    "left-hip",
    "right-hip",
    "left-knee",
    "right-knee",
    "left-ankle",
    "right-ankle",
    "left-big-toe-tip",
    "left-small-toe-tip",
    "left-heel",
    "right-big-toe-tip",
    "right-small-toe-tip",
    "right-heel",
    "right-thumb-tip",
    "right-thumb-first-joint",
    "right-thumb-second-joint",
    "right-thumb-third-joint",
    "right-index-tip",
    "right-index-first-joint",
    "right-index-second-joint",
    "right-index-third-joint",
    "right-middle-tip",
    "right-middle-first-joint",
    "right-middle-second-joint",
    "right-middle-third-joint",
    "right-ring-tip",
    "right-ring-first-joint",
    "right-ring-second-joint",
    "right-ring-third-joint",
    "right-pinky-tip",
    "right-pinky-first-joint",
    "right-pinky-second-joint",
    "right-pinky-third-joint",
    "right-wrist",
    "left-thumb-tip",
    "left-thumb-first-joint",
    "left-thumb-second-joint",
    "left-thumb-third-joint",
    "left-index-tip",
    "left-index-first-joint",
    "left-index-second-joint",
    "left-index-third-joint",
    "left-middle-tip",
    "left-middle-first-joint",
    "left-middle-second-joint",
    "left-middle-third-joint",
    "left-ring-tip",
    "left-ring-first-joint",
    "left-ring-second-joint",
    "left-ring-third-joint",
    "left-pinky-tip",
    "left-pinky-first-joint",
    "left-pinky-second-joint",
    "left-pinky-third-joint",
    "left-wrist",
    "left-olecranon",
    "right-olecranon",
    "left-cubital-fossa",
    "right-cubital-fossa",
    "left-acromion",
    "right-acromion",
    "neck",
)

BODY_LINKS = (
    (5, 6),
    (5, 7),
    (7, 62),
    (6, 8),
    (8, 41),
    (5, 9),
    (6, 10),
    (9, 10),
    (9, 11),
    (11, 13),
    (13, 17),
    (13, 15),
    (13, 16),
    (10, 12),
    (12, 14),
    (14, 20),
    (14, 18),
    (14, 19),
    (69, 0),
    (69, 5),
    (69, 6),
)

MODEL_CONFIG_LIMIT = 64 * 1024


def _model_config_path(checkpoint: Path) -> Path | None:
    for candidate in (
        checkpoint.parent / "model_config.yaml",
        checkpoint.parent.parent / "model_config.yaml",
    ):
        if candidate.is_file():
            return candidate
    return None


def _checkpoint_backbone(config_path: Path) -> str | None:
    if config_path.stat().st_size > MODEL_CONFIG_LIMIT:
        raise ValueError("model_config.yaml exceeds the safe size limit")
    text = config_path.read_text(encoding="utf-8")
    for match in re.finditer(
        r"(?mi)^\s*TYPE\s*:\s*['\"]?([a-z0-9_+.-]{1,128})['\"]?\s*(?:#.*)?$",
        text,
    ):
        name = match.group(1).casefold()
        if name.startswith(("dinov3_", "vit_hmr")):
            return name
    return None


def _pinned_torch_hub_loader(
    original_load: Any,
    dinov3_repo: Path | None,
) -> Any:
    def local_only_load(
        repo_or_dir: object,
        model: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        source = kwargs.get("source", "github")
        if source != "github":
            return original_load(repo_or_dir, model, *args, **kwargs)
        if repo_or_dir != "facebookresearch/dinov3":
            raise RuntimeError(f"unexpected remote Torch Hub repository: {repo_or_dir}")
        if model != "dinov3_vith16plus":
            raise RuntimeError(f"unexpected DINOv3 Torch Hub model: {model}")
        if kwargs.get("pretrained") is not False:
            raise RuntimeError("DINOv3 pretrained weight downloads are disabled")
        unexpected = set(kwargs) - {"source", "pretrained", "drop_path"}
        if unexpected:
            raise RuntimeError(
                "unexpected DINOv3 Torch Hub options: " + ", ".join(sorted(unexpected))
            )
        if dinov3_repo is None:
            raise RuntimeError(
                "the pinned official DINOv3 repository is not configured"
            )
        kwargs["source"] = "local"
        return original_load(str(dinov3_repo), model, *args, **kwargs)

    return local_only_load


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _finite_list(value: Any, *, expected: int | None = None) -> list[float]:
    flattened = value.reshape(-1).tolist() if hasattr(value, "reshape") else list(value)
    result = [float(item) for item in flattened]
    if expected is not None and len(result) != expected:
        raise ValueError(f"model output has {len(result)} values; expected {expected}")
    if not all(math.isfinite(item) for item in result):
        raise ValueError("model output contains a non-finite value")
    return result


def _nested_finite(value: Any) -> list[object]:
    result = value.tolist() if hasattr(value, "tolist") else value

    def validate(item: Any) -> Any:
        if isinstance(item, list):
            return [validate(child) for child in item]
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("model output contains a non-finite value")
        return number

    return validate(result)


def _camera_intrinsics(
    torch: Any,
    *,
    width: int,
    height: int,
    vertical_fov: float | None,
) -> Any | None:
    if vertical_fov is None:
        return None
    focal = height / (2.0 * math.tan(math.radians(vertical_fov) / 2.0))
    return torch.tensor(
        [
            [
                [focal, 0.0, width / 2.0],
                [0.0, focal, height / 2.0],
                [0.0, 0.0, 1.0],
            ]
        ],
        dtype=torch.float32,
    )


def _draw_overlay(cv2: Any, image: Any, people: list[dict[str, object]]) -> Any:
    overlay = image.copy()
    for person_index, person in enumerate(people):
        color = (
            (64, 220, 255)
            if person_index == 0
            else (80 + (person_index * 37) % 150, 210, 110)
        )
        bbox = person["bbox"]
        cv2.rectangle(
            overlay,
            (int(round(bbox[0])), int(round(bbox[1]))),
            (int(round(bbox[2])), int(round(bbox[3]))),
            color,
            2,
        )
        keypoints = person["keypoints2d"]
        for first, second in BODY_LINKS:
            a, b = keypoints[first], keypoints[second]
            cv2.line(
                overlay,
                (int(round(a[0])), int(round(a[1]))),
                (int(round(b[0])), int(round(b[1]))),
                color,
                2,
                cv2.LINE_AA,
            )
        for x, y in keypoints:
            cv2.circle(
                overlay,
                (int(round(x)), int(round(y))),
                2,
                color,
                -1,
                cv2.LINE_AA,
            )
    return overlay


def run(
    *,
    repo: Path,
    checkpoint: Path,
    mhr: Path,
    dinov3_repo: Path | None,
    source: Path,
    request_path: Path,
    output_dir: Path,
) -> None:
    repo = repo.resolve()
    checkpoint = checkpoint.resolve()
    mhr = mhr.resolve()
    if dinov3_repo is not None:
        dinov3_repo = dinov3_repo.resolve()
    source = source.resolve()
    request_path = request_path.resolve()
    output_dir = output_dir.resolve()
    if not (repo / "sam_3d_body" / "__init__.py").is_file():
        raise ValueError("repo is not a native SAM 3D Body source checkout")
    if not checkpoint.is_file():
        raise ValueError("SAM 3D Body checkpoint is missing")
    model_config = _model_config_path(checkpoint)
    if model_config is None:
        raise ValueError(
            "model_config.yaml is missing beside the checkpoint or in its parent"
        )
    backbone = _checkpoint_backbone(model_config)
    if backbone is not None and backbone.startswith("dinov3_"):
        if backbone != "dinov3_vith16plus":
            raise ValueError(f"the DINOv3 backbone is unsupported: {backbone}")
        if dinov3_repo is None:
            raise ValueError("the pinned official DINOv3 repository is not configured")
        if any("comfyui" in part.casefold() for part in dinov3_repo.parts):
            raise ValueError(
                "the official DINOv3 repository must not be inside ComfyUI"
            )
        if not (
            (dinov3_repo / "hubconf.py").is_file()
            and (dinov3_repo / "dinov3" / "__init__.py").is_file()
        ):
            raise ValueError(
                "the official DINOv3 repository is not a native source checkout"
            )
    if not mhr.is_file():
        raise ValueError("MHR TorchScript model is missing")
    if not source.is_file() or not request_path.is_file():
        raise ValueError("worker input is missing")
    output_dir.mkdir(parents=True, exist_ok=True)

    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request, dict) or request.get("schema") != 1:
        raise ValueError("worker request schema is unsupported")
    width = request.get("sourceWidth")
    height = request.get("sourceHeight")
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("worker request source dimensions are invalid")
    bbox = request.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("worker request bbox is invalid")
    vertical_fov = request.get("verticalFov")
    if vertical_fov is not None:
        vertical_fov = float(vertical_fov)

    # The manager sets MOMENTUM_ENABLED=0; repeat it before importing the
    # official package so the explicit gated MHR TorchScript asset is used.
    os.environ["MOMENTUM_ENABLED"] = "0"
    sys.path.insert(0, str(repo))
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body  # type: ignore

    if not torch.cuda.is_available():
        raise RuntimeError(
            "native SAM 3D Body currently requires a CUDA-capable PyTorch worker"
        )
    image_bgr = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("OpenCV could not decode the uploaded image")
    decoded_height, decoded_width = image_bgr.shape[:2]
    if decoded_width != width or decoded_height != height:
        raise ValueError("decoded image dimensions do not match the upload header")

    # The upstream loader currently passes ``weights_only=False`` to
    # ``torch.load``. Checkpoints are data, not trusted Python programs, so
    # force PyTorch's restricted tensor-only loader while that call runs.
    # This remains compatible with Meta's plain state-dict checkpoints.
    original_torch_load = torch.load
    original_torch_hub_load = torch.hub.load

    def restricted_torch_load(*args: Any, **kwargs: Any) -> Any:
        kwargs["weights_only"] = True
        return original_torch_load(*args, **kwargs)

    torch.load = restricted_torch_load
    torch.hub.load = _pinned_torch_hub_loader(
        original_torch_hub_load,
        dinov3_repo,
    )
    try:
        model, model_cfg = load_sam_3d_body(
            str(checkpoint),
            device=torch.device("cuda"),
            mhr_path=str(mhr),
        )
    finally:
        torch.load = original_torch_load
        torch.hub.load = original_torch_hub_load
    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=model,
        model_cfg=model_cfg,
        human_detector=None,
        human_segmentor=None,
        fov_estimator=None,
    )
    camera_intrinsics = _camera_intrinsics(
        torch,
        width=width,
        height=height,
        vertical_fov=vertical_fov,
    )
    outputs = estimator.process_one_image(
        str(source),
        bboxes=np.asarray([bbox], dtype=np.float32),
        cam_int=camera_intrinsics,
        inference_type="full",
    )
    if not outputs:
        raise RuntimeError("SAM 3D Body did not return a person")

    people: list[dict[str, object]] = []
    arrays: dict[str, Any] = {}
    numeric_array_names = (
        "pred_keypoints_3d",
        "pred_keypoints_2d",
        "pred_vertices",
        "pred_cam_t",
        "pred_pose_raw",
        "global_rot",
        "body_pose_params",
        "hand_pose_params",
        "scale_params",
        "shape_params",
        "expr_params",
        "pred_joint_coords",
        "pred_global_rots",
        "mhr_model_params",
        "lhand_bbox",
        "rhand_bbox",
    )
    for index, output in enumerate(outputs):
        keypoints3d = _nested_finite(output["pred_keypoints_3d"])
        keypoints2d = _nested_finite(output["pred_keypoints_2d"])
        if len(keypoints3d) != 70 or len(keypoints2d) != 70:
            raise RuntimeError("SAM 3D Body returned an unexpected keypoint layout")
        person = {
            "index": index,
            "bbox": _finite_list(output["bbox"], expected=4),
            "focalLength": _finite_list(
                np.asarray(output["focal_length"]).reshape(1),
                expected=1,
            )[0],
            "predCamT": _finite_list(output["pred_cam_t"], expected=3),
            "keypointNames": list(MHR70_NAMES),
            "keypoints3d": keypoints3d,
            "keypoints2d": keypoints2d,
        }
        people.append(person)
        for name in numeric_array_names:
            value = output.get(name)
            if value is not None:
                arrays[f"person_{index}_{name}"] = np.asarray(value)
    arrays_path = output_dir / "arrays.npz"
    arrays_partial = output_dir / ".arrays.npz.partial"
    with arrays_partial.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(arrays_partial, arrays_path)

    overlay = _draw_overlay(cv2, image_bgr, people)
    overlay_partial = output_dir / ".overlay.png.partial"
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        raise RuntimeError("OpenCV could not encode the result overlay")
    overlay_partial.write_bytes(encoded.tobytes())
    os.replace(overlay_partial, output_dir / "overlay.png")

    manifest = {
        "schema": 1,
        "engine": {
            "name": "facebookresearch/sam-3d-body",
            "mode": "native-standalone",
        },
        "jobId": request["jobId"],
        "source": {
            "width": width,
            "height": height,
            "contentType": request["sourceType"],
            "bbox": [float(item) for item in bbox],
            "verticalFov": vertical_fov,
        },
        "people": people,
        "artifacts": {
            "arrays": "arrays.npz",
            "overlay": "overlay.png",
        },
    }
    _atomic_json(output_dir / "manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--mhr", required=True, type=Path)
    parser.add_argument("--dinov3-repo", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    run(
        repo=args.repo,
        checkpoint=args.checkpoint,
        mhr=args.mhr,
        dinov3_repo=args.dinov3_repo,
        source=args.source,
        request_path=args.request,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

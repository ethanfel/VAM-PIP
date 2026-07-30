"""Standalone native SAM 3D Body worker.

This module is intentionally executable by a dedicated Python/Conda
interpreter. It does not import VAM-PIP or ComfyUI, and all heavyweight
dependencies remain on the worker side of the subprocess boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

if __package__:
    from .sam3d_body_signature import derive_body_proportions
    from .sam3d_shape_geometry import derive_body_shape
else:
    from sam3d_body_signature import derive_body_proportions
    from sam3d_shape_geometry import derive_body_shape


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
MAX_BBOXES = 4
NUMERIC_ARRAY_SHAPES = {
    "pred_keypoints_3d": (70, 3),
    "pred_keypoints_2d": (70, 2),
    "pred_vertices": (18439, 3),
    "pred_cam_t": (3,),
    "pred_pose_raw": (266,),
    "global_rot": (3,),
    "body_pose_params": (133,),
    "hand_pose_params": (108,),
    "scale_params": (28,),
    "shape_params": (45,),
    "expr_params": (72,),
    "pred_joint_coords": (127, 3),
    "pred_global_rots": (127, 3, 3),
    "mhr_model_params": (204,),
    "lhand_bbox": (4,),
    "rhand_bbox": (4,),
}


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


def _validated_numeric_array(
    np: Any,
    value: Any,
    *,
    name: str,
) -> Any:
    """Return one exact, finite float32 array from the official model output."""

    expected_shape = NUMERIC_ARRAY_SHAPES[name]
    array = np.asarray(value)
    if (
        tuple(array.shape) != expected_shape
        or array.dtype == np.dtype(bool)
        or not np.issubdtype(array.dtype, np.number)
        or np.issubdtype(array.dtype, np.complexfloating)
        or not bool(np.isfinite(array).all())
    ):
        raise ValueError(
            f"SAM 3D Body {name} must be finite numeric data with shape "
            f"{expected_shape}"
        )
    normalized = np.ascontiguousarray(array, dtype=np.float32)
    if not bool(np.isfinite(normalized).all()):
        raise ValueError(f"SAM 3D Body {name} overflows float32")
    return normalized


def _validated_person_arrays(
    np: Any,
    output: dict[str, Any],
    *,
    person_index: int,
) -> dict[str, Any]:
    missing = set(NUMERIC_ARRAY_SHAPES) - set(output)
    if missing:
        raise ValueError(
            "SAM 3D Body numeric output is incomplete: " + ", ".join(sorted(missing))
        )
    return {
        f"person_{person_index}_{name}": _validated_numeric_array(
            np,
            output[name],
            name=name,
        )
        for name in NUMERIC_ARRAY_SHAPES
    }


def _validate_stored_numeric_arrays(
    np: Any,
    path: Path,
    *,
    person_count: int,
) -> None:
    expected = {
        f"person_{person_index}_{name}": shape
        for person_index in range(person_count)
        for name, shape in NUMERIC_ARRAY_SHAPES.items()
    }
    try:
        with np.load(path, allow_pickle=False) as stored:
            if len(stored.files) != len(expected) or set(stored.files) != set(expected):
                raise ValueError("stored SAM 3D Body arrays have an invalid key set")
            for name, shape in expected.items():
                array = stored[name]
                if (
                    tuple(array.shape) != shape
                    or array.dtype != np.dtype(np.float32)
                    or not bool(np.isfinite(array).all())
                ):
                    raise ValueError(f"stored SAM 3D Body array {name} is invalid")
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "stored SAM 3D Body"
        ):
            raise
        raise ValueError("stored SAM 3D Body arrays are unreadable") from error


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _neutral_body_identity(
    model: Any,
    output: dict[str, Any],
    *,
    np: Any,
    torch: Any,
) -> dict[str, dict[str, object]]:
    """Regenerate the inferred identity in the neutral MHR bind pose."""

    head = getattr(model, "head_pose", None)
    if head is None or not callable(getattr(head, "mhr_forward", None)):
        raise RuntimeError("SAM 3D Body model has no neutral MHR geometry path")
    device = head.scale_mean.device
    dtype = head.scale_mean.dtype

    def tensor(name: str) -> Any:
        return torch.as_tensor(
            np.asarray(output[name]),
            device=device,
            dtype=dtype,
        ).reshape(1, -1)

    with torch.no_grad():
        neutral = head.mhr_forward(
            global_trans=torch.zeros((1, 3), device=device, dtype=dtype),
            global_rot=torch.zeros((1, 3), device=device, dtype=dtype),
            body_pose_params=torch.zeros_like(tensor("body_pose_params")),
            hand_pose_params=torch.zeros_like(tensor("hand_pose_params")),
            scale_params=tensor("scale_params"),
            shape_params=tensor("shape_params"),
            expr_params=torch.zeros_like(tensor("expr_params")),
            return_keypoints=True,
        )
    if not isinstance(neutral, tuple) or len(neutral) < 2:
        raise RuntimeError("neutral MHR geometry returned an invalid result")
    vertices = neutral[0].detach().cpu().numpy()[0]
    keypoints = neutral[1].detach().cpu().numpy()[0, :70]
    if (
        tuple(vertices.shape) != NUMERIC_ARRAY_SHAPES["pred_vertices"]
        or tuple(keypoints.shape) != NUMERIC_ARRAY_SHAPES["pred_keypoints_3d"]
        or not bool(np.isfinite(vertices).all())
        or not bool(np.isfinite(keypoints).all())
    ):
        raise RuntimeError("neutral MHR geometry is invalid")

    shoulder_midpoint = (
        keypoints[MHR70_NAMES.index("left-shoulder")]
        + keypoints[MHR70_NAMES.index("right-shoulder")]
    ) * 0.5
    hip_midpoint = (
        keypoints[MHR70_NAMES.index("left-hip")]
        + keypoints[MHR70_NAMES.index("right-hip")]
    ) * 0.5
    longitudinal_axis = shoulder_midpoint - hip_midpoint
    axis_length = float(np.linalg.norm(longitudinal_axis))
    if not math.isfinite(axis_length) or axis_length <= 1e-6:
        raise RuntimeError("neutral MHR longitudinal axis is invalid")
    longitudinal_axis = longitudinal_axis / axis_length
    projections = vertices @ longitudinal_axis
    stature = float(np.max(projections) - np.min(projections))
    return {
        "bodyProportions": derive_body_proportions(
            keypoints.tolist(),
            stature_m=stature,
        ),
        "bodyShape": derive_body_shape(
            vertices,
            keypoints,
            head.faces.detach().cpu().numpy(),
            posed_keypoints=np.asarray(output["pred_keypoints_3d"]),
            np=np,
        ),
    }


def _neutral_body_proportions(
    model: Any,
    output: dict[str, Any],
    *,
    np: Any,
    torch: Any,
) -> dict[str, object]:
    """Compatibility wrapper for callers that only need skeletal proportions."""

    return _neutral_body_identity(
        model,
        output,
        np=np,
        torch=torch,
    )["bodyProportions"]


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


def _request_bboxes(
    request: dict[str, Any],
    *,
    width: int,
    height: int,
) -> list[list[float]]:
    if request.get("schema") == 3:
        raw_bboxes: object = request.get("bboxes")
        if (
            not isinstance(raw_bboxes, list)
            or not 1 <= len(raw_bboxes) <= MAX_BBOXES
        ):
            raise ValueError("worker request bboxes are invalid")
    else:
        raw_bboxes = [request.get("bbox")]

    bboxes: list[list[float]] = []
    for raw_bbox in raw_bboxes:
        if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
            raise ValueError("worker request bbox is invalid")
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in raw_bbox
        ):
            raise ValueError("worker request bbox is invalid")
        bbox = [float(item) for item in raw_bbox]
        x1, y1, x2, y2 = bbox
        if (
            x1 < 0.0
            or y1 < 0.0
            or x2 <= x1
            or y2 <= y1
            or x2 > width
            or y2 > height
            or (x2 - x1) * (y2 - y1) < 256.0
        ):
            raise ValueError("worker request bbox is invalid")
        bboxes.append(bbox)
    return bboxes


def run(
    *,
    repo: Path,
    checkpoint: Path,
    mhr: Path,
    model_id: str,
    expected_backbone: str,
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
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9_.+-]{0,63}", model_id)
        or not re.fullmatch(
            r"[a-z0-9][a-z0-9_.+-]{0,127}",
            expected_backbone,
        )
        or backbone != expected_backbone
    ):
        raise ValueError("worker checkpoint identity does not match its model profile")
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
    if not isinstance(request, dict) or request.get("schema") not in {1, 2, 3}:
        raise ValueError("worker request schema is unsupported")
    if request.get("schema") in {2, 3} and request.get("modelId") != model_id:
        raise ValueError("worker request model does not match the checkpoint")
    width = request.get("sourceWidth")
    height = request.get("sourceHeight")
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("worker request source dimensions are invalid")
    bboxes = _request_bboxes(request, width=width, height=height)
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
        bboxes=np.asarray(bboxes, dtype=np.float32),
        cam_int=camera_intrinsics,
        inference_type="full",
    )
    if not isinstance(outputs, (list, tuple)) or len(outputs) != len(bboxes):
        raise RuntimeError(
            "SAM 3D Body result count does not match the requested boxes"
        )

    people: list[dict[str, object]] = []
    arrays: dict[str, Any] = {}
    for index, output in enumerate(outputs):
        keypoints3d = _nested_finite(output["pred_keypoints_3d"])
        keypoints2d = _nested_finite(output["pred_keypoints_2d"])
        if len(keypoints3d) != 70 or len(keypoints2d) != 70:
            raise RuntimeError("SAM 3D Body returned an unexpected keypoint layout")
        neutral_identity = _neutral_body_identity(
            model,
            output,
            np=np,
            torch=torch,
        )
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
            **neutral_identity,
        }
        people.append(person)
        arrays.update(
            _validated_person_arrays(
                np,
                output,
                person_index=index,
            )
        )
    arrays_path = output_dir / "arrays.npz"
    arrays_partial = output_dir / ".arrays.npz.partial"
    with arrays_partial.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(arrays_partial, arrays_path)
    _validate_stored_numeric_arrays(
        np,
        arrays_path,
        person_count=len(people),
    )
    arrays_metadata = {
        "schema": 1,
        "format": "numpy-npz",
        "sha256": _file_sha256(arrays_path),
        "bytes": arrays_path.stat().st_size,
        "people": len(people),
    }

    overlay = _draw_overlay(cv2, image_bgr, people)
    overlay_partial = output_dir / ".overlay.png.partial"
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        raise RuntimeError("OpenCV could not encode the result overlay")
    overlay_partial.write_bytes(encoded.tobytes())
    os.replace(overlay_partial, output_dir / "overlay.png")

    engine = {
        "name": "facebookresearch/sam-3d-body",
        "mode": "native-standalone",
    }
    if request["schema"] in {2, 3}:
        engine.update(
            {
                "modelId": model_id,
                "backbone": backbone,
            }
        )
    source_manifest: dict[str, object] = {
        "width": width,
        "height": height,
        "contentType": request["sourceType"],
        "verticalFov": vertical_fov,
    }
    if request["schema"] == 3:
        source_manifest["bboxes"] = bboxes
    else:
        source_manifest["bbox"] = bboxes[0]
    manifest = {
        "schema": request["schema"],
        "engine": engine,
        "jobId": request["jobId"],
        "source": source_manifest,
        "people": people,
        "artifacts": {
            "arrays": "arrays.npz",
            "arraysMetadata": arrays_metadata,
            "overlay": "overlay.png",
        },
    }
    _atomic_json(output_dir / "manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--mhr", required=True, type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--backbone", required=True)
    parser.add_argument("--dinov3-repo", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    run(
        repo=args.repo,
        checkpoint=args.checkpoint,
        mhr=args.mhr,
        model_id=args.model_id,
        expected_backbone=args.backbone,
        dinov3_repo=args.dinov3_repo,
        source=args.source,
        request_path=args.request,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

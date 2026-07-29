"""CPU-only body-shape sidecar worker for completed SAM3D jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from .sam3d_body_shape import (
        body_shape_sidecar_revision,
        validate_body_shape_sidecar,
    )
    from .sam3d_shape_geometry import derive_body_shape
except ImportError:  # Direct execution by the isolated SAM interpreter.
    from sam3d_body_shape import (  # type: ignore[no-redef]
        body_shape_sidecar_revision,
        validate_body_shape_sidecar,
    )
    from sam3d_shape_geometry import derive_body_shape  # type: ignore[no-redef]


_ARRAYS_LIMIT = 512 * 1024 * 1024
_MHR_LIMIT = 2 * 1024 * 1024 * 1024
_CHECKPOINT_LIMIT = 4 * 1024 * 1024 * 1024
_STATE_KEYS = (
    "head_pose.scale_mean",
    "head_pose.scale_comps",
    "head_pose.faces",
    "head_pose.keypoint_mapping",
)


def _safe_input(path: Path, *, label: str, maximum: int) -> None:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size < 1
        or path.stat().st_size > maximum
    ):
        raise ValueError(f"{label} is missing or outside its safe size limit")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tensor_digest(tensors: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for name in _STATE_KEYS:
        tensor = tensors[name].detach().cpu().contiguous()
        digest.update(name.encode("ascii") + b"\0")
        digest.update(str(tuple(tensor.shape)).encode("ascii") + b"\0")
        digest.update(str(tensor.dtype).encode("ascii") + b"\0")
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def _checkpoint_identity(torch: Any, checkpoint: Path) -> dict[str, Any]:
    try:
        loaded = torch.load(
            checkpoint,
            map_location="cpu",
            weights_only=True,
            mmap=True,
        )
    except TypeError:
        # Kept for compatible isolated runtimes predating torch.load(mmap=...).
        loaded = torch.load(
            checkpoint,
            map_location="cpu",
            weights_only=True,
        )
    if not isinstance(loaded, dict):
        raise ValueError("SAM3D checkpoint state is invalid")
    state = loaded.get("state_dict", loaded)
    if not isinstance(state, dict) or any(name not in state for name in _STATE_KEYS):
        raise ValueError("SAM3D checkpoint has no neutral MHR identity basis")
    result = {name: state[name] for name in _STATE_KEYS}
    expected = {
        "head_pose.scale_mean": (68,),
        "head_pose.scale_comps": (28, 68),
        "head_pose.faces": (36874, 3),
        "head_pose.keypoint_mapping": (308, 18566),
    }
    for name, shape in expected.items():
        tensor = result[name]
        if (
            not hasattr(tensor, "shape")
            or tuple(tensor.shape) != shape
            or (
                name == "head_pose.faces"
                and tensor.dtype
                not in {
                    torch.int32,
                    torch.int64,
                }
            )
            or (name != "head_pose.faces" and not bool(torch.isfinite(tensor).all()))
        ):
            raise ValueError(f"SAM3D checkpoint {name} is invalid")
    return result


def _array(
    np: Any,
    stored: Any,
    name: str,
    shape: tuple[int, ...],
) -> Any:
    if name not in stored:
        raise ValueError(f"SAM3D arrays are missing {name}")
    value = np.asarray(stored[name])
    if (
        tuple(value.shape) != shape
        or value.dtype == np.dtype(bool)
        or not np.issubdtype(value.dtype, np.number)
        or not bool(np.isfinite(value).all())
    ):
        raise ValueError(f"SAM3D array {name} is invalid")
    return np.ascontiguousarray(value, dtype=np.float32)


def neutral_identity_from_arrays(
    arrays_path: Path,
    *,
    person_index: int,
    checkpoint: Path,
    mhr_path: Path,
    np: Any,
    torch: Any,
) -> tuple[Any, Any, Any, Any, str]:
    """Reconstruct neutral vertices/keypoints from one persisted person."""

    if isinstance(person_index, bool) or not isinstance(person_index, int):
        raise TypeError("person_index must be an integer")
    if not 0 <= person_index <= 15:
        raise ValueError("person_index is outside the supported range")
    _safe_input(arrays_path, label="SAM3D arrays", maximum=_ARRAYS_LIMIT)
    _safe_input(checkpoint, label="SAM3D checkpoint", maximum=_CHECKPOINT_LIMIT)
    _safe_input(mhr_path, label="MHR model", maximum=_MHR_LIMIT)

    prefix = f"person_{person_index}_"
    try:
        with np.load(arrays_path, allow_pickle=False) as stored:
            shape_params = _array(
                np,
                stored,
                prefix + "shape_params",
                (45,),
            )
            scale_params = _array(
                np,
                stored,
                prefix + "scale_params",
                (28,),
            )
            posed_keypoints = _array(
                np,
                stored,
                prefix + "pred_keypoints_3d",
                (70, 3),
            )
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("SAM3D array"):
            raise
        raise ValueError("SAM3D arrays are unreadable") from error

    identity = _checkpoint_identity(torch, checkpoint)
    scale_mean = identity["head_pose.scale_mean"].detach().cpu()
    scale_comps = identity["head_pose.scale_comps"].detach().cpu()
    dtype = scale_mean.dtype
    shape_tensor = torch.as_tensor(shape_params, dtype=dtype).reshape(1, -1)
    scale_tensor = torch.as_tensor(scale_params, dtype=dtype).reshape(1, -1)
    scales = scale_mean.reshape(1, -1) + scale_tensor @ scale_comps
    model_params = torch.cat(
        (torch.zeros((1, 136), dtype=dtype), scales),
        dim=1,
    )
    mhr = torch.jit.load(str(mhr_path), map_location="cpu").eval()
    with torch.no_grad():
        neutral = mhr(
            shape_tensor,
            model_params,
            torch.zeros((1, 72), dtype=dtype),
        )
    if not isinstance(neutral, tuple) or len(neutral) < 2:
        raise ValueError("MHR neutral geometry result is invalid")
    vertices_tensor = neutral[0]
    skeleton_state = neutral[1]
    if tuple(vertices_tensor.shape) != (1, 18439, 3) or tuple(
        skeleton_state.shape[:2]
    ) != (1, 127):
        raise ValueError("MHR neutral geometry shape is invalid")
    vertices = vertices_tensor.detach().cpu().numpy()[0] / 100.0
    joints = skeleton_state.detach().cpu()[0, :, :3] / 100.0
    mapping = identity["head_pose.keypoint_mapping"].detach().cpu()
    keypoints = (
        mapping
        @ torch.cat(
            (torch.as_tensor(vertices, dtype=mapping.dtype), joints),
            dim=0,
        )
    ).numpy()[:70]
    faces = identity["head_pose.faces"].detach().cpu().numpy()
    if not bool(np.isfinite(vertices).all()) or not bool(np.isfinite(keypoints).all()):
        raise ValueError("MHR neutral geometry contains non-finite values")
    return (
        vertices,
        keypoints,
        faces,
        posed_keypoints,
        _tensor_digest(identity),
    )


def build_body_shape_sidecar(
    arrays_path: Path,
    *,
    person_index: int,
    checkpoint: Path,
    mhr_path: Path,
    np: Any,
    torch: Any,
) -> dict[str, object]:
    """Build a source-bound shape sidecar without changing the SAM3D job."""

    (
        vertices,
        keypoints,
        faces,
        posed_keypoints,
        identity_basis_sha256,
    ) = neutral_identity_from_arrays(
        arrays_path,
        person_index=person_index,
        checkpoint=checkpoint,
        mhr_path=mhr_path,
        np=np,
        torch=torch,
    )
    body_shape = derive_body_shape(
        vertices,
        keypoints,
        faces,
        posed_keypoints=posed_keypoints,
        np=np,
    )
    document: dict[str, object] = {
        "schema": 1,
        "kind": "vampip-sam3d-body-shape-sidecar",
        "source": {
            "arraysSha256": _file_sha256(arrays_path),
            "arraysBytes": arrays_path.stat().st_size,
            "personIndex": person_index,
            "mhrSha256": _file_sha256(mhr_path),
            "identityBasisSha256": identity_basis_sha256,
        },
        "bodyShape": body_shape,
    }
    document["revision"] = body_shape_sidecar_revision(document)
    validate_body_shape_sidecar(document)
    return document


def write_body_shape_sidecar(
    output: Path,
    document: dict[str, object],
) -> None:
    """Atomically write one already validated body-shape sidecar."""

    validate_body_shape_sidecar(document)
    if output.is_symlink() or not output.parent.is_dir():
        raise ValueError("body-shape sidecar output path is invalid")
    temporary = output.with_name(f".{output.name}.partial")
    if temporary.is_symlink():
        raise ValueError("body-shape sidecar temporary path is invalid")
    temporary.write_text(
        json.dumps(
            document,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--mhr", required=True, type=Path)
    parser.add_argument("--arrays", required=True, type=Path)
    parser.add_argument("--person-index", type=int, default=0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    import numpy as np
    import torch

    document = build_body_shape_sidecar(
        args.arrays,
        person_index=args.person_index,
        checkpoint=args.checkpoint,
        mhr_path=args.mhr,
        np=np,
        torch=torch,
    )
    write_body_shape_sidecar(args.output, document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_body_shape_sidecar",
    "neutral_identity_from_arrays",
    "write_body_shape_sidecar",
]

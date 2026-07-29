from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
from typing import Callable
import uuid

from vampip.database import connect
from vampip.runtime import atomic_write_text
from vampip.sam3d_body_signature import validate_body_proportions
from vampip.sam3d_vam import MHR70_NAMES


SAM3D_UPLOAD_LIMIT = 32 * 1024 * 1024
SAM3D_MAX_PIXELS = 50_000_000
SAM3D_MAX_DIMENSION = 32_768
SAM3D_MANIFEST_LIMIT = 4 * 1024 * 1024
SAM3D_MODEL_CONFIG_LIMIT = 64 * 1024
SAM3D_CAPTURE_HISTORY_LIMIT = 50
SAM3D_CAPTURE_FILE_LIMIT = 256 * 1024 * 1024
SAM3D_ARRAYS_FILE_LIMIT = 512 * 1024 * 1024
SAM3D_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
SAM3D_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9_.+-]{0,63}$")
SAM3D_COMPARISON_MODEL_IDS = frozenset(
    {"dinov3_vith16plus", "vit_hmr_512_384"}
)
SAM3D_ARTIFACTS = frozenset({"source", "manifest", "overlay"})
_TERMINAL_STATES = frozenset(
    {"succeeded", "failed", "interrupted", "cancelled"}
)
_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_CAPTURE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
}
_OFFICIAL_MODEL_NAMES = {
    "dinov3_vith16plus": "SAM 3D Body DINOv3-H+",
    "vit_hmr_512_384": "SAM 3D Body ViT-H",
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _arrays_artifact_metadata(
    path: Path,
    *,
    person_count: int,
) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size < 1
        or path.stat().st_size > SAM3D_ARRAYS_FILE_LIMIT
    ):
        raise RuntimeError("SAM 3D Body arrays are missing or too large")
    return {
        "schema": 1,
        "format": "numpy-npz",
        "sha256": _file_sha256(path),
        "bytes": path.stat().st_size,
        "people": person_count,
    }


def _valid_arrays_artifact_metadata(
    value: object,
    *,
    person_count: int,
) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"schema", "format", "sha256", "bytes", "people"}
        and value.get("schema") == 1
        and value.get("format") == "numpy-npz"
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"])) is not None
        and not isinstance(value.get("bytes"), bool)
        and isinstance(value.get("bytes"), int)
        and 1 <= int(value["bytes"]) <= SAM3D_ARRAYS_FILE_LIMIT
        and not isinstance(value.get("people"), bool)
        and value.get("people") == person_count
    )


class Sam3dConfigurationError(RuntimeError):
    """The isolated native worker is not configured or is unsafe."""


class Sam3dJobError(RuntimeError):
    """A SAM3D job cannot perform the requested state transition."""


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    extension: str
    width: int
    height: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_job_id(value: object) -> str:
    if not isinstance(value, str) or SAM3D_JOB_ID.fullmatch(value) is None:
        raise ValueError("SAM3D job ID must be a lowercase 32-character token")
    return value


def validate_model_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("SAM3D model ID must be a string")
    model_id = value.strip().casefold()
    if SAM3D_MODEL_ID.fullmatch(model_id) is None:
        raise ValueError("SAM3D model ID is invalid")
    return model_id


def _normalize_capture_record(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    request_id = value.get("request_id")
    extension = value.get("extension")
    content_type = value.get("content_type")
    captured_at = value.get("captured_at_utc")
    if (
        not isinstance(request_id, str)
        or SAM3D_JOB_ID.fullmatch(request_id) is None
        or not isinstance(extension, str)
        or _CAPTURE_CONTENT_TYPES.get(extension) != content_type
        or not isinstance(captured_at, str)
        or len(captured_at) > 64
    ):
        return None
    try:
        timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None

    revision = value.get("revision")
    if revision is not None and (
        not isinstance(revision, str) or SAM3D_JOB_ID.fullmatch(revision) is None
    ):
        return None
    record: dict[str, object] = {
        "request_id": request_id,
        "revision": revision,
        "target_uid": None,
        "camera_uid": None,
        "extension": extension,
        "content_type": content_type,
        "captured_at_utc": timestamp.astimezone(timezone.utc).isoformat(),
    }
    for key in ("target_uid", "camera_uid"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or len(item) > 256:
                return None
            record[key] = item
    size_bytes = value.get("size_bytes")
    if size_bytes is not None:
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or size_bytes > SAM3D_CAPTURE_FILE_LIMIT
        ):
            return None
        record["size_bytes"] = size_bytes
    return record


def _capture_record_timestamp(record: dict[str, object]) -> float:
    return datetime.fromisoformat(
        str(record["captured_at_utc"]).replace("Z", "+00:00")
    ).timestamp()


def _capture_history_from_result(
    result: dict[str, object],
) -> list[dict[str, object]]:
    by_request: dict[str, dict[str, object]] = {}
    raw_history = result.get("capture_history")
    if isinstance(raw_history, list):
        for value in raw_history:
            record = _normalize_capture_record(value)
            if record is not None:
                by_request[str(record["request_id"])] = record
    latest = _normalize_capture_record(result.get("last_capture"))
    if latest is not None:
        request_id = str(latest["request_id"])
        by_request[request_id] = {
            **by_request.get(request_id, {}),
            **latest,
        }
    return sorted(
        by_request.values(),
        key=lambda record: (
            _capture_record_timestamp(record),
            str(record["request_id"]),
        ),
        reverse=True,
    )[:SAM3D_CAPTURE_HISTORY_LIMIT]


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 24
        or data[:8] != b"\x89PNG\r\n\x1a\n"
        or data[12:16] != b"IHDR"
    ):
        return None
    return (
        int.from_bytes(data[16:20], "big"),
        int.from_bytes(data[20:24], "big"),
    )


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    position = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position < len(data):
        while position < len(data) and data[position] != 0xFF:
            position += 1
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xDA or position + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            return None
        if marker in sof_markers:
            if segment_length < 7:
                return None
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 30
        or data[:4] != b"RIFF"
        or data[8:12] != b"WEBP"
    ):
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 ":
        if len(data) < 30 or data[23:26] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None


def inspect_image(data: bytes, declared_content_type: str) -> ImageInfo:
    if not isinstance(data, bytes):
        raise TypeError("image body must be bytes")
    if not data:
        raise ValueError("image body is empty")
    if len(data) > SAM3D_UPLOAD_LIMIT:
        raise ValueError("image body exceeds the 32 MiB upload limit")
    content_type = declared_content_type.split(";", 1)[0].strip().casefold()
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in _CONTENT_TYPE_EXTENSIONS:
        raise ValueError("Content-Type must be image/jpeg, image/png, or image/webp")
    parsers = {
        "image/jpeg": _jpeg_dimensions,
        "image/png": _png_dimensions,
        "image/webp": _webp_dimensions,
    }
    dimensions = parsers[content_type](data)
    if dimensions is None:
        raise ValueError("image magic/header does not match Content-Type")
    width, height = dimensions
    if (
        width < 1
        or height < 1
        or width > SAM3D_MAX_DIMENSION
        or height > SAM3D_MAX_DIMENSION
        or width * height > SAM3D_MAX_PIXELS
    ):
        raise ValueError("image dimensions exceed the safe decoding limit")
    return ImageInfo(
        content_type=content_type,
        extension=_CONTENT_TYPE_EXTENSIONS[content_type],
        width=width,
        height=height,
    )


def _unsafe_comfy_path(path: Path) -> bool:
    return any("comfyui" in part.casefold() for part in path.parts)


def _model_config_path(checkpoint: Path | None) -> Path | None:
    if checkpoint is None or not checkpoint.is_file():
        return None
    for candidate in (
        checkpoint.parent / "model_config.yaml",
        checkpoint.parent.parent / "model_config.yaml",
    ):
        if candidate.is_file():
            return candidate
    return None


def _model_config_validation_error(checkpoint: Path | None) -> str | None:
    config_path = _model_config_path(checkpoint)
    if config_path is None:
        return None
    try:
        if config_path.stat().st_size > SAM3D_MODEL_CONFIG_LIMIT:
            return "model_config.yaml exceeds the safe size limit"
        config_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "model_config.yaml is not valid UTF-8"
    except OSError:
        return "model_config.yaml cannot be read"
    return None


def _checkpoint_backbone(checkpoint: Path | None) -> str | None:
    config_path = _model_config_path(checkpoint)
    if config_path is None:
        return None
    try:
        if config_path.stat().st_size > SAM3D_MODEL_CONFIG_LIMIT:
            return None
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for match in re.finditer(
        r"(?mi)^\s*TYPE\s*:\s*['\"]?([a-z0-9_+.-]{1,128})['\"]?\s*(?:#.*)?$",
        text,
    ):
        name = match.group(1).casefold()
        if name.startswith(("dinov3_", "vit_hmr")):
            return name
    return None


def _checkpoint_model_name(checkpoint: Path | None) -> str:
    backbone = _checkpoint_backbone(checkpoint)
    if backbone == "dinov3_vith16plus":
        return "SAM 3D Body DINOv3-H+"
    if backbone is not None and backbone.startswith("dinov3_"):
        return "SAM 3D Body DINOv3"
    if backbone is not None and backbone.startswith("vit_hmr"):
        return "SAM 3D Body ViT-H"
    return "SAM 3D Body"


def _checkpoint_model_id(checkpoint: Path | None) -> str:
    backbone = _checkpoint_backbone(checkpoint)
    return backbone if backbone is not None else "default"


@dataclass(frozen=True)
class Sam3dWorkerConfig:
    python: Path | None
    conda_executable: Path | None
    conda_env: str | None
    repo: Path | None
    checkpoint: Path | None
    mhr: Path | None
    timeout_seconds: int = 1800
    dinov3_repo: Path | None = None

    @classmethod
    def from_environment(cls) -> "Sam3dWorkerConfig":
        python_value = os.environ.get("VAMPIP_SAM3D_PYTHON", "").strip()
        conda_env = os.environ.get("VAMPIP_SAM3D_CONDA_ENV", "").strip() or None
        conda_value = os.environ.get("VAMPIP_CONDA_EXECUTABLE", "").strip()
        if conda_value:
            conda_executable = Path(conda_value).expanduser().resolve()
        elif conda_env:
            found = shutil.which("conda")
            conda_executable = Path(found).resolve() if found else None
        else:
            conda_executable = None
        timeout_value = os.environ.get("VAMPIP_SAM3D_TIMEOUT_SECONDS", "1800")
        try:
            timeout_seconds = max(60, min(7200, int(timeout_value)))
        except ValueError:
            timeout_seconds = 1800

        def optional_path(name: str) -> Path | None:
            value = os.environ.get(name, "").strip()
            return Path(value).expanduser().resolve() if value else None

        return cls(
            python=(
                Path(python_value).expanduser().resolve()
                if python_value
                else None
            ),
            conda_executable=conda_executable,
            conda_env=conda_env,
            repo=optional_path("VAMPIP_SAM3D_REPO"),
            checkpoint=optional_path("VAMPIP_SAM3D_CHECKPOINT"),
            mhr=optional_path("VAMPIP_SAM3D_MHR"),
            dinov3_repo=optional_path("VAMPIP_SAM3D_DINOV3_REPO"),
            timeout_seconds=timeout_seconds,
        )

    def errors(self) -> list[str]:
        errors: list[str] = []
        if bool(self.python) == bool(self.conda_env):
            errors.append(
                "configure exactly one of VAMPIP_SAM3D_PYTHON or "
                "VAMPIP_SAM3D_CONDA_ENV"
            )
        if self.python is not None:
            if not self.python.is_file():
                errors.append("the dedicated SAM3D Python interpreter is missing")
            elif not os.access(self.python, os.X_OK):
                errors.append(
                    "the dedicated SAM3D Python interpreter is not executable"
                )
            elif self.python == Path(sys.executable).resolve():
                errors.append("SAM3D must use a dedicated interpreter, not VAM-PIP's")
            elif _unsafe_comfy_path(self.python):
                errors.append("the SAM3D interpreter must not be inside ComfyUI")
        if self.conda_env is not None:
            if (
                len(self.conda_env) > 128
                or re.fullmatch(r"[A-Za-z0-9_.-]+", self.conda_env) is None
                or self.conda_env.casefold() == "base"
                or "comfy" in self.conda_env.casefold()
            ):
                errors.append("the dedicated Conda environment name is unsafe")
            if self.conda_executable is None or not self.conda_executable.is_file():
                errors.append("the Conda executable is missing")
            elif not os.access(self.conda_executable, os.X_OK):
                errors.append("the Conda executable is not executable")
        for label, value in (
            ("official SAM 3D Body repository", self.repo),
            ("SAM 3D Body checkpoint", self.checkpoint),
            ("MHR TorchScript model", self.mhr),
        ):
            if value is None:
                errors.append(f"the {label} is not configured")
            elif _unsafe_comfy_path(value):
                errors.append(f"the {label} must not be inside ComfyUI")
            elif label.endswith("repository"):
                if not (value / "sam_3d_body" / "__init__.py").is_file():
                    errors.append(f"the {label} is not a native source checkout")
            elif not value.is_file():
                errors.append(f"the {label} is missing")
        if self.checkpoint is not None and self.checkpoint.is_file():
            if _model_config_path(self.checkpoint) is None:
                errors.append(
                    "model_config.yaml is missing beside the checkpoint "
                    "or in its parent directory"
                )
            else:
                config_error = _model_config_validation_error(self.checkpoint)
                if config_error is not None:
                    errors.append(config_error)
        backbone = _checkpoint_backbone(self.checkpoint)
        if (
            self.checkpoint is not None
            and self.checkpoint.is_file()
            and _model_config_path(self.checkpoint) is not None
            and _model_config_validation_error(self.checkpoint) is None
            and backbone is None
        ):
            errors.append(
                "model_config.yaml does not declare a supported "
                "dinov3_* or vit_hmr* backbone"
            )
        uses_dinov3 = bool((backbone or "").startswith("dinov3_"))
        if uses_dinov3:
            if backbone != "dinov3_vith16plus":
                errors.append(f"the DINOv3 backbone is unsupported: {backbone}")
            elif self.dinov3_repo is None:
                errors.append("the pinned official DINOv3 repository is not configured")
            elif _unsafe_comfy_path(self.dinov3_repo):
                errors.append(
                    "the official DINOv3 repository must not be inside ComfyUI"
                )
            elif not (
                (self.dinov3_repo / "hubconf.py").is_file()
                and (self.dinov3_repo / "dinov3" / "__init__.py").is_file()
            ):
                errors.append(
                    "the official DINOv3 repository is not a native source checkout"
                )
        return errors

    @property
    def configured(self) -> bool:
        return not self.errors()

    def command_prefix(self) -> list[str]:
        errors = self.errors()
        if errors:
            raise Sam3dConfigurationError("; ".join(errors))
        if self.python is not None:
            return [str(self.python)]
        assert self.conda_executable is not None
        assert self.conda_env is not None
        return [
            str(self.conda_executable),
            "run",
            "--no-capture-output",
            "-n",
            self.conda_env,
            "python",
        ]

    def public_status(self) -> dict[str, object]:
        errors = self.errors()
        model_config = (
            _model_config_path(self.checkpoint) is not None
            and _model_config_validation_error(self.checkpoint) is None
        )
        backbone = _checkpoint_backbone(self.checkpoint)
        return {
            "configured": not errors,
            "model": _checkpoint_model_name(self.checkpoint),
            "backbone": backbone,
            "launcher": (
                "dedicated-python"
                if self.python is not None
                else ("conda" if self.conda_env is not None else None)
            ),
            "environment": self.conda_env,
            "native_repository": bool(
                self.repo is not None
                and (self.repo / "sam_3d_body" / "__init__.py").is_file()
            ),
            "checkpoint": bool(
                self.checkpoint is not None and self.checkpoint.is_file()
            ),
            "model_config": model_config,
            "mhr": bool(self.mhr is not None and self.mhr.is_file()),
            "dinov3_repository": bool(
                self.dinov3_repo is not None
                and (self.dinov3_repo / "hubconf.py").is_file()
                and (self.dinov3_repo / "dinov3" / "__init__.py").is_file()
            ),
            "errors": errors,
        }


def _environment_model_configs(
) -> tuple[str, dict[str, Sam3dWorkerConfig]]:
    primary = Sam3dWorkerConfig.from_environment()
    primary_id = _checkpoint_model_id(primary.checkpoint)
    configs = {primary_id: primary}

    def optional_path(name: str) -> Path | None:
        value = os.environ.get(name, "").strip()
        return Path(value).expanduser().resolve() if value else None

    for model_id, prefix in (
        ("dinov3_vith16plus", "VAMPIP_SAM3D_DINOV3"),
        ("vit_hmr_512_384", "VAMPIP_SAM3D_VITH"),
    ):
        checkpoint = optional_path(f"{prefix}_CHECKPOINT")
        mhr = optional_path(f"{prefix}_MHR")
        if checkpoint is None and mhr is None:
            continue
        configs[model_id] = replace(
            primary,
            checkpoint=checkpoint,
            mhr=mhr,
            dinov3_repo=(
                primary.dinov3_repo
                if model_id == "dinov3_vith16plus"
                else None
            ),
        )

    requested_default = os.environ.get(
        "VAMPIP_SAM3D_DEFAULT_MODEL",
        "",
    ).strip()
    if requested_default:
        try:
            requested_default = validate_model_id(requested_default)
        except ValueError:
            requested_default = ""
    default_model_id = (
        requested_default
        if requested_default in configs
        else primary_id
    )
    return default_model_id, configs


@dataclass(frozen=True)
class Sam3dJobPaths:
    directory: Path
    source: Path
    request: Path
    manifest: Path
    overlay: Path
    arrays: Path
    log: Path


class SubprocessSam3dWorker:
    def __init__(self) -> None:
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[bytes] | None = None
        self._closed = False

    @staticmethod
    def _environment(runtime_dir: Path) -> dict[str, str]:
        cache_dir = runtime_dir / "cache"
        temp_dir = runtime_dir / "tmp"
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        environment: dict[str, str] = {}
        blocked_environment_keys = {
            "ALL_PROXY",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "HF_HUB_TOKEN",
            "HF_TOKEN",
            "HF_TOKEN_PATH",
            "HUGGING_FACE_HUB_TOKEN",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "WANDB_API_KEY",
        }
        for key, value in os.environ.items():
            upper_key = key.upper()
            if (
                upper_key in blocked_environment_keys
                or upper_key.startswith("LD_")
                or upper_key.startswith("CONDA")
                or upper_key.startswith("_CONDA")
                or upper_key.startswith("VIRTUAL_ENV")
                or upper_key.startswith("_CE_")
                or upper_key.startswith("PYTHON")
                or "COMFY" in upper_key
                or "comfyui" in value.casefold()
            ):
                continue
            environment[key] = value
        environment.update(
            {
                "PYTHONNOUSERSITE": "1",
                "MOMENTUM_ENABLED": "0",
                "HF_HOME": str(cache_dir / "huggingface"),
                "HF_HUB_OFFLINE": "1",
                "TORCH_HOME": str(cache_dir / "torch"),
                "TRANSFORMERS_OFFLINE": "1",
                "WANDB_MODE": "disabled",
                "XDG_CACHE_HOME": str(cache_dir / "xdg"),
                "TMPDIR": str(temp_dir),
            }
        )
        return environment

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

        # The group leader can exit while a model-loader child remains alive.
        # Always address the original process group with SIGKILL after the
        # grace period; ESRCH simply means the complete group already exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def __call__(
        self,
        config: Sam3dWorkerConfig,
        paths: Sam3dJobPaths,
        runtime_dir: Path,
    ) -> None:
        assert config.repo is not None
        assert config.checkpoint is not None
        assert config.mhr is not None
        worker_script = Path(__file__).with_name("sam3d_worker.py").resolve()
        command = [
            *config.command_prefix(),
            str(worker_script),
            "--repo",
            str(config.repo),
            "--checkpoint",
            str(config.checkpoint),
            "--mhr",
            str(config.mhr),
            "--model-id",
            _checkpoint_model_id(config.checkpoint),
            "--backbone",
            _checkpoint_backbone(config.checkpoint) or "unknown",
        ]
        uses_dinov3 = bool(
            (_checkpoint_backbone(config.checkpoint) or "").startswith("dinov3_")
        )
        if uses_dinov3 and config.dinov3_repo is not None:
            command.extend(["--dinov3-repo", str(config.dinov3_repo)])
        command.extend(
            [
                "--source",
                str(paths.source),
                "--request",
                str(paths.request),
                "--output-dir",
                str(paths.directory),
            ]
        )
        environment = self._environment(runtime_dir)
        with paths.log.open("ab") as log:
            with self._process_lock:
                if self._closed:
                    raise RuntimeError("SAM 3D Body worker is shutting down")
            process = subprocess.Popen(
                command,
                cwd=paths.directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            with self._process_lock:
                if self._closed:
                    self._terminate_process_group(process)
                    raise RuntimeError("SAM 3D Body worker is shutting down")
                self._active_process = process
            try:
                try:
                    return_code = process.wait(timeout=config.timeout_seconds)
                except subprocess.TimeoutExpired as error:
                    self._terminate_process_group(process)
                    raise RuntimeError(
                        f"SAM 3D Body exceeded {config.timeout_seconds} seconds"
                    ) from error
            finally:
                with self._process_lock:
                    if self._active_process is process:
                        self._active_process = None
            if return_code != 0:
                raise RuntimeError(
                    f"SAM 3D Body worker exited with status {return_code}"
                )

    def close(self) -> None:
        with self._process_lock:
            self._closed = True
            process = self._active_process
        if process is not None:
            self._terminate_process_group(process)


WorkerCallable = Callable[
    [Sam3dWorkerConfig, Sam3dJobPaths, Path],
    None,
]


class Sam3dJobManager:
    """Persistent, one-GPU-job-at-a-time native SAM3D orchestrator."""

    def __init__(
        self,
        state_dir: Path,
        *,
        config: Sam3dWorkerConfig | None = None,
        model_configs: dict[str, Sam3dWorkerConfig] | None = None,
        default_model_id: str | None = None,
        worker: WorkerCallable | None = None,
    ) -> None:
        if config is not None and model_configs is not None:
            raise ValueError("configure either one SAM3D model or a model registry")
        if model_configs is None:
            if config is not None:
                inferred_id = _checkpoint_model_id(config.checkpoint)
                configured_default = inferred_id
                model_configs = {inferred_id: config}
            else:
                configured_default, model_configs = (
                    _environment_model_configs()
                )
        else:
            configured_default = next(iter(model_configs), "")
        if not 1 <= len(model_configs) <= 8:
            raise ValueError("SAM3D model registry must contain 1 to 8 models")
        normalized_configs: dict[str, Sam3dWorkerConfig] = {}
        for raw_model_id, model_config in model_configs.items():
            model_id = validate_model_id(raw_model_id)
            if not isinstance(model_config, Sam3dWorkerConfig):
                raise TypeError("SAM3D model registry values must be worker configs")
            if model_id in normalized_configs:
                raise ValueError("SAM3D model registry IDs must be unique")
            normalized_configs[model_id] = model_config
        if default_model_id is None:
            default_model_id = configured_default
        default_model_id = validate_model_id(default_model_id)
        if default_model_id not in normalized_configs:
            raise ValueError("default SAM3D model is not in the registry")

        self.state_dir = state_dir.expanduser().resolve()
        self.root = self.state_dir / "sam3d"
        self.jobs_dir = self.root / "jobs"
        self.runtime_dir = self.root / "runtime"
        self.jobs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.model_configs = normalized_configs
        self.default_model_id = default_model_id
        # Keep the historical attribute for callers that inspect the default
        # standalone worker configuration.
        self.config = self.model_configs[self.default_model_id]
        self.worker = worker or SubprocessSam3dWorker()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._recover_and_resume()

    def _profile_errors(
        self,
        model_id: str,
        config: Sam3dWorkerConfig,
    ) -> list[str]:
        errors = config.errors()
        actual_id = _checkpoint_model_id(config.checkpoint)
        if actual_id != model_id:
            errors.append(
                f"the {model_id} profile uses checkpoint backbone {actual_id}"
            )
        return errors

    def _config_for_model(self, value: object) -> Sam3dWorkerConfig:
        model_id = validate_model_id(value)
        try:
            config = self.model_configs[model_id]
        except KeyError as error:
            raise Sam3dConfigurationError(
                f"SAM3D model is not configured: {model_id}"
            ) from error
        errors = self._profile_errors(model_id, config)
        if errors:
            raise Sam3dConfigurationError("; ".join(errors))
        return config

    def _model_id_from_request(
        self,
        request: dict[str, object],
    ) -> str:
        value = request.get("modelId")
        if value is None:
            return self.default_model_id
        return validate_model_id(value)

    def _config_for_job(self, job_id: str) -> Sam3dWorkerConfig:
        with connect(self.state_dir) as connection:
            row = connection.execute(
                "SELECT request_json FROM sam3d_jobs WHERE id = ?",
                (validate_job_id(job_id),),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"SAM3D job not found: {job_id}")
        try:
            request = json.loads(row["request_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise Sam3dJobError("SAM3D job request is unreadable") from error
        if not isinstance(request, dict):
            raise Sam3dJobError("SAM3D job request is invalid")
        return self._config_for_model(self._model_id_from_request(request))

    def _recover_and_resume(self) -> None:
        queued: list[str] = []
        lock_path = self.runtime_dir / "worker.lock"
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            try:
                with connect(self.state_dir) as connection:
                    now = _utc_now()
                    connection.execute(
                        """
                        UPDATE sam3d_jobs
                        SET state = 'interrupted', stage = 'interrupted',
                            updated_utc = ?, error = ?
                        WHERE state = 'running'
                        """,
                        (now, "manager stopped while the worker was running"),
                    )
                    queued = [
                        str(row["id"])
                        for row in connection.execute(
                            """
                            SELECT id FROM sam3d_jobs
                            WHERE state = 'queued'
                            ORDER BY created_utc
                            """
                        )
                    ]
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        for job_id in queued:
            self._queue.put(job_id)
        if queued:
            self._ensure_thread()

    def _paths(self, job_id: str, source_type: str | None = None) -> Sam3dJobPaths:
        job_id = validate_job_id(job_id)
        directory = self.jobs_dir / job_id
        if source_type is None:
            with connect(self.state_dir) as connection:
                row = connection.execute(
                    "SELECT source_type FROM sam3d_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
            if row is None:
                raise FileNotFoundError(f"SAM3D job not found: {job_id}")
            source_type = str(row["source_type"])
        try:
            extension = _CONTENT_TYPE_EXTENSIONS[source_type]
        except KeyError as error:
            raise Sam3dJobError("SAM3D job source type is invalid") from error
        return Sam3dJobPaths(
            directory=directory,
            source=directory / f"source.{extension}",
            request=directory / "request.json",
            manifest=directory / "manifest.json",
            overlay=directory / "overlay.png",
            arrays=directory / "arrays.npz",
            log=directory / "worker.log",
        )

    @staticmethod
    def _request_values(
        *,
        image: ImageInfo,
        bbox: list[float] | None,
        vertical_fov: float | None,
    ) -> tuple[list[float], float | None]:
        if bbox is None:
            bbox = [0.0, 0.0, float(image.width), float(image.height)]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("bbox must contain x1,y1,x2,y2")
        values: list[float] = []
        for item in bbox:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("bbox must contain finite numbers")
            number = float(item)
            if not math.isfinite(number):
                raise ValueError("bbox must contain finite numbers")
            values.append(number)
        x1, y1, x2, y2 = values
        if (
            x1 < 0.0
            or y1 < 0.0
            or x2 <= x1
            or y2 <= y1
            or x2 > image.width
            or y2 > image.height
            or (x2 - x1) * (y2 - y1) < 256.0
        ):
            raise ValueError("bbox is outside the image or too small")
        if vertical_fov is not None:
            if isinstance(vertical_fov, bool) or not isinstance(
                vertical_fov, (int, float)
            ):
                raise ValueError("vertical_fov must be a finite number")
            vertical_fov = float(vertical_fov)
            if (
                not math.isfinite(vertical_fov)
                or vertical_fov < 5.0
                or vertical_fov > 170.0
            ):
                raise ValueError("vertical_fov must be between 5 and 170 degrees")
        return values, vertical_fov

    def create(
        self,
        image_data: bytes,
        content_type: str,
        *,
        bbox: list[float] | None = None,
        vertical_fov: float | None = None,
        model_id: str | None = None,
        comparison_id: str | None = None,
    ) -> dict[str, object]:
        image = inspect_image(image_data, content_type)
        bbox, vertical_fov = self._request_values(
            image=image,
            bbox=bbox,
            vertical_fov=vertical_fov,
        )
        if model_id is None:
            model_id = self.default_model_id
        model_id = validate_model_id(model_id)
        if model_id not in self.model_configs:
            raise Sam3dConfigurationError(
                f"SAM3D model is not configured: {model_id}"
            )
        if comparison_id is not None:
            if (
                not isinstance(comparison_id, str)
                or SAM3D_JOB_ID.fullmatch(comparison_id) is None
            ):
                raise ValueError(
                    "SAM3D comparison ID must be a lowercase 32-character token"
                )
            if model_id not in SAM3D_COMPARISON_MODEL_IDS:
                raise ValueError(
                    "SAM3D comparisons support only DINOv3-H+ and ViT-H"
                )
        job_id = uuid.uuid4().hex
        paths = self._paths(job_id, image.content_type)
        paths.directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        paths.source.write_bytes(image_data)
        try:
            paths.source.chmod(0o600)
        except OSError:
            pass
        request = {
            "schema": 2,
            "jobId": job_id,
            "modelId": model_id,
            "sourceType": image.content_type,
            "sourceWidth": image.width,
            "sourceHeight": image.height,
            "bbox": bbox,
            "verticalFov": vertical_fov,
        }
        if comparison_id is not None:
            request["comparisonId"] = comparison_id
        atomic_write_text(
            paths.request,
            json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        now = _utc_now()
        try:
            with connect(self.state_dir) as connection:
                # Serialize comparison membership checks with insertion. Two
                # simultaneous uploads must not both observe an empty group.
                connection.execute("BEGIN IMMEDIATE")
                if comparison_id is not None:
                    self._validate_comparison_group(
                        connection,
                        comparison_id=comparison_id,
                        model_id=model_id,
                        image=image,
                        image_data=image_data,
                        bbox=bbox,
                        vertical_fov=vertical_fov,
                    )
                connection.execute(
                    """
                    INSERT INTO sam3d_jobs (
                        id, created_utc, updated_utc, state, stage, progress,
                        source_type, source_width, source_height, request_json
                    ) VALUES (?, ?, ?, 'uploaded', 'uploaded', 0.0, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        now,
                        now,
                        image.content_type,
                        image.width,
                        image.height,
                        json.dumps(
                            request,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    ),
                )
        except Exception:
            # These paths are unique to this not-yet-persisted job.
            paths.request.unlink(missing_ok=True)
            paths.source.unlink(missing_ok=True)
            try:
                paths.directory.rmdir()
            except OSError:
                pass
            raise
        return self.get(job_id)

    def _validate_comparison_group(
        self,
        connection: sqlite3.Connection,
        *,
        comparison_id: str,
        model_id: str,
        image: ImageInfo,
        image_data: bytes,
        bbox: list[float],
        vertical_fov: float | None,
    ) -> None:
        members: list[tuple[sqlite3.Row, dict[str, object]]] = []
        for row in connection.execute(
            """
            SELECT id, source_type, source_width, source_height, request_json
            FROM sam3d_jobs
            """
        ):
            try:
                request = json.loads(row["request_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if (
                isinstance(request, dict)
                and request.get("comparisonId") == comparison_id
            ):
                members.append((row, request))

        if len(members) >= len(SAM3D_COMPARISON_MODEL_IDS):
            raise ValueError("SAM3D comparison already contains two model jobs")
        if not members:
            return

        row, request = members[0]
        try:
            existing_model_id = validate_model_id(request.get("modelId"))
        except ValueError as error:
            raise ValueError(
                "existing SAM3D comparison member has invalid model identity"
            ) from error
        if existing_model_id not in SAM3D_COMPARISON_MODEL_IDS:
            raise ValueError(
                "existing SAM3D comparison member is not an official model"
            )
        if existing_model_id == model_id:
            raise ValueError(
                "SAM3D comparison must use distinct model IDs"
            )
        if (
            row["source_type"] != image.content_type
            or row["source_width"] != image.width
            or row["source_height"] != image.height
            or request.get("sourceType") != image.content_type
            or request.get("sourceWidth") != image.width
            or request.get("sourceHeight") != image.height
            or request.get("bbox") != bbox
            or request.get("verticalFov") != vertical_fov
        ):
            raise ValueError(
                "SAM3D comparison jobs must use the same source, box, and FOV"
            )

        existing_paths = self._paths(
            str(row["id"]),
            str(row["source_type"]),
        )
        try:
            with existing_paths.source.open("rb") as stream:
                existing_data = stream.read(SAM3D_UPLOAD_LIMIT + 1)
        except OSError as error:
            raise ValueError(
                "existing SAM3D comparison source is unavailable"
            ) from error
        if (
            len(existing_data) > SAM3D_UPLOAD_LIMIT
            or len(existing_data) != len(image_data)
            or hashlib.sha256(existing_data).digest()
            != hashlib.sha256(image_data).digest()
        ):
            raise ValueError(
                "SAM3D comparison jobs must use identical source bytes"
            )

    def _public_model(self, model_id: str) -> dict[str, object]:
        config = self.model_configs.get(model_id)
        status = config.public_status() if config is not None else None
        backbone: object = (
            model_id
            if model_id != "default"
            else (status or {}).get("backbone")
        )
        name = _OFFICIAL_MODEL_NAMES.get(model_id)
        if name is None and status is not None:
            name = str(status["model"])
        if name is None:
            name = model_id
        return {
            "id": model_id,
            "name": name,
            "backbone": backbone,
        }

    def _document(self, row: sqlite3.Row) -> dict[str, object]:
        try:
            request = json.loads(row["request_json"])
        except (TypeError, json.JSONDecodeError):
            request = {}
        try:
            result = json.loads(row["result_json"])
        except (TypeError, json.JSONDecodeError):
            result = {}
        if not isinstance(request, dict):
            request = {}
        if not isinstance(result, dict):
            result = {}
        model: dict[str, object] | None = None
        raw_model_id = request.get("modelId")
        if isinstance(raw_model_id, str):
            try:
                model_id = validate_model_id(raw_model_id)
            except ValueError:
                pass
            else:
                model = self._public_model(model_id)
        capture_history = _capture_history_from_result(result)
        return {
            "id": str(row["id"]),
            "state": str(row["state"]),
            "stage": str(row["stage"]),
            "progress": max(0.0, min(1.0, float(row["progress"]))),
            "created_at_utc": str(row["created_utc"]),
            "updated_at_utc": str(row["updated_utc"]),
            "source": {
                "content_type": str(row["source_type"]),
                "width": int(row["source_width"]),
                "height": int(row["source_height"]),
            },
            "bbox": request.get("bbox"),
            "vertical_fov": request.get("verticalFov"),
            "model": model,
            "comparison_id": request.get("comparisonId"),
            "person_count": result.get("person_count"),
            "selected_person_index": result.get("selected_person_index", 0),
            "last_vam_action": result.get("last_vam_action"),
            "last_capture": result.get("last_capture"),
            "captures": capture_history,
            "error": str(row["error"]) if row["error"] is not None else None,
            "revision": str(row["revision"]) if row["revision"] else None,
            "terminal": str(row["state"]) in _TERMINAL_STATES,
        }

    def merge_capture_history(
        self,
        job_id: str,
        captures: list[dict[str, object]],
    ) -> dict[str, object]:
        """Merge bounded, validated capture discoveries into one persisted job."""

        job_id = validate_job_id(job_id)
        normalized: list[dict[str, object]] = []
        for value in captures:
            record = _normalize_capture_record(value)
            if record is None:
                raise ValueError("SAM3D capture metadata is invalid")
            normalized.append(record)
        with connect(self.state_dir) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT result_json FROM sam3d_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"SAM3D job not found: {job_id}")
            try:
                result = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                result = {}
            if not isinstance(result, dict):
                result = {}

            by_request = {
                str(record["request_id"]): record
                for record in _capture_history_from_result(result)
            }
            for record in normalized:
                request_id = str(record["request_id"])
                existing = by_request.get(request_id, {})
                merged = {**existing, **record}
                for key in ("revision", "target_uid", "camera_uid"):
                    if existing.get(key) is not None:
                        merged[key] = existing[key]
                by_request[request_id] = merged
            history = sorted(
                by_request.values(),
                key=lambda record: (
                    _capture_record_timestamp(record),
                    str(record["request_id"]),
                ),
                reverse=True,
            )[:SAM3D_CAPTURE_HISTORY_LIMIT]
            result["capture_history"] = history
            if history:
                result["last_capture"] = history[0]

            encoded = json.dumps(
                result,
                separators=(",", ":"),
                sort_keys=True,
            )
            if encoded != row["result_json"]:
                connection.execute(
                    "UPDATE sam3d_jobs SET result_json = ? WHERE id = ?",
                    (encoded, job_id),
                )
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, object]:
        job_id = validate_job_id(job_id)
        with connect(self.state_dir) as connection:
            row = connection.execute(
                "SELECT * FROM sam3d_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"SAM3D job not found: {job_id}")
        return self._document(row)

    def list(self, *, limit: int = 30, offset: int = 0) -> dict[str, object]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError("offset must be an integer")
        if limit < 1 or limit > 100 or offset < 0 or offset > 1_000_000:
            raise ValueError("limit/offset are outside the accepted range")
        with connect(self.state_dir) as connection:
            total = int(
                connection.execute("SELECT COUNT(*) FROM sam3d_jobs").fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT * FROM sam3d_jobs
                ORDER BY created_utc DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return {
            "items": [self._document(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def status(self) -> dict[str, object]:
        with connect(self.state_dir) as connection:
            counts = {
                str(row["state"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT state, COUNT(*) AS count
                    FROM sam3d_jobs GROUP BY state
                    """
                )
            }
        models: list[dict[str, object]] = []
        for model_id, config in self.model_configs.items():
            model = config.public_status()
            errors = self._profile_errors(model_id, config)
            model["configured"] = not errors
            model["errors"] = errors
            model["id"] = model_id
            model["name"] = model["model"]
            model["default"] = model_id == self.default_model_id
            models.append(model)
        models.sort(
            key=lambda model: (
                not bool(model["default"]),
                str(model["name"]),
            )
        )
        worker = dict(
            next(
                model
                for model in models
                if model["id"] == self.default_model_id
            )
        )
        worker["models"] = models
        worker["default_model_id"] = self.default_model_id
        available = any(bool(model["configured"]) for model in models)
        return {
            "available": available,
            "worker": worker,
            "busy": bool(counts.get("running", 0) or counts.get("queued", 0)),
            "counts": counts,
            "limits": {
                "upload_bytes": SAM3D_UPLOAD_LIMIT,
                "image_pixels": SAM3D_MAX_PIXELS,
                "image_dimension": SAM3D_MAX_DIMENSION,
            },
            "storage": "persistent-state",
            "comfyui_used": False,
        }

    def queue(self, job_id: str) -> dict[str, object]:
        job_id = validate_job_id(job_id)
        if self._closed.is_set():
            raise Sam3dJobError("SAM3D manager is shutting down")
        self._config_for_job(job_id)
        now = _utc_now()
        with connect(self.state_dir) as connection:
            cursor = connection.execute(
                """
                UPDATE sam3d_jobs
                SET state = 'queued', stage = 'queued', progress = 0.0,
                    updated_utc = ?, error = NULL
                WHERE id = ? AND state IN (
                    'uploaded', 'failed', 'interrupted', 'cancelled'
                )
                """,
                (now, job_id),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT state FROM sam3d_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if row is None:
                    raise FileNotFoundError(f"SAM3D job not found: {job_id}")
                raise Sam3dJobError(
                    f"SAM3D job cannot be queued from state {row['state']}"
                )
        self._queue.put(job_id)
        self._ensure_thread()
        return self.get(job_id)

    def _ensure_thread(self) -> None:
        with self._thread_lock:
            if self._closed.is_set():
                return
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="vampip-sam3d-worker",
                daemon=True,
            )
            self._thread.start()

    def _worker_loop(self) -> None:
        while not self._closed.is_set():
            try:
                job_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                with self._thread_lock:
                    if self._queue.empty():
                        self._thread = None
                        return
                continue
            try:
                self._run_one(job_id)
            finally:
                self._queue.task_done()

    def _run_one(self, job_id: str) -> None:
        lock_path = self.runtime_dir / "worker.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with connect(self.state_dir) as connection:
                    cursor = connection.execute(
                        """
                        UPDATE sam3d_jobs
                        SET state = 'running', stage = 'inference',
                            progress = 0.1, updated_utc = ?, error = NULL
                        WHERE id = ? AND state = 'queued'
                        """,
                        (_utc_now(), job_id),
                    )
                if cursor.rowcount != 1:
                    return
                paths = self._paths(job_id)
                try:
                    config = self._config_for_job(job_id)
                    for stale_path in (
                        paths.manifest,
                        paths.overlay,
                        paths.arrays,
                    ):
                        stale_path.unlink(missing_ok=True)
                    self.worker(config, paths, self.runtime_dir)
                    manifest, revision = self._validated_manifest(job_id, paths)
                    person_count = len(manifest["people"])
                    with connect(self.state_dir) as connection:
                        connection.execute(
                            """
                            UPDATE sam3d_jobs
                            SET state = 'succeeded', stage = 'complete',
                                progress = 1.0, updated_utc = ?, error = NULL,
                                revision = ?, result_json = ?
                            WHERE id = ? AND state = 'running'
                            """,
                            (
                                _utc_now(),
                                revision,
                                json.dumps(
                                    {"person_count": person_count},
                                    separators=(",", ":"),
                                ),
                                job_id,
                            ),
                        )
                except Exception as error:
                    message = str(error).strip() or error.__class__.__name__
                    state = (
                        "interrupted"
                        if self._closed.is_set()
                        else "failed"
                    )
                    with connect(self.state_dir) as connection:
                        connection.execute(
                            """
                            UPDATE sam3d_jobs
                            SET state = ?, stage = ?,
                                progress = 0.0, updated_utc = ?, error = ?
                            WHERE id = ? AND state = 'running'
                            """,
                            (
                                state,
                                state,
                                _utc_now(),
                                message[:1000],
                                job_id,
                            ),
                        )
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        close_worker = getattr(self.worker, "close", None)
        if callable(close_worker):
            close_worker()
        with self._thread_lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)

    def _read_validated_manifest(
        self,
        job_id: str,
        paths: Sam3dJobPaths,
    ) -> tuple[dict[str, object], str]:
        try:
            with paths.manifest.open("rb") as stream:
                encoded = stream.read(SAM3D_MANIFEST_LIMIT + 1)
        except FileNotFoundError as error:
            raise RuntimeError(
                "SAM 3D Body worker did not produce manifest.json"
            ) from error
        except OSError as error:
            raise RuntimeError("SAM 3D Body manifest is unreadable") from error
        if len(encoded) > SAM3D_MANIFEST_LIMIT:
            raise RuntimeError("SAM 3D Body manifest is too large")
        try:
            manifest = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("SAM 3D Body manifest is unreadable") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") not in {1, 2}
            or manifest.get("jobId") != job_id
        ):
            raise RuntimeError("SAM 3D Body manifest identity/schema is invalid")
        source = manifest.get("source")
        people = manifest.get("people")
        try:
            request_encoded = paths.request.read_bytes()
            if len(request_encoded) > 64 * 1024:
                raise RuntimeError("SAM 3D Body request is too large")
            request = json.loads(request_encoded.decode("utf-8"))
        except RuntimeError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError("SAM 3D Body request is unreadable") from error
        with connect(self.state_dir) as connection:
            request_row = connection.execute(
                """
                SELECT source_type, source_width, source_height, request_json
                FROM sam3d_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if request_row is None:
            raise RuntimeError("SAM 3D Body request has no persisted job")
        try:
            persisted_request = json.loads(request_row["request_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "SAM 3D Body persisted request is unreadable"
            ) from error
        legacy_request_keys = {
            "schema",
            "jobId",
            "sourceType",
            "sourceWidth",
            "sourceHeight",
            "bbox",
            "verticalFov",
        }
        model_request_keys = legacy_request_keys | {"modelId"}
        comparison_request_keys = model_request_keys | {"comparisonId"}
        request_schema = (
            request.get("schema")
            if isinstance(request, dict)
            else None
        )
        request_key_set = (
            frozenset(request)
            if isinstance(request, dict)
            else frozenset()
        )
        request_shape_valid = (
            request_schema == 1
            and request_key_set == legacy_request_keys
        ) or (
            request_schema == 2
            and request_key_set
            in {frozenset(model_request_keys), frozenset(comparison_request_keys)}
        )
        if (
            not isinstance(request, dict)
            or not isinstance(persisted_request, dict)
            or request != persisted_request
            or not request_shape_valid
            or request.get("jobId") != job_id
            or request.get("sourceType") != request_row["source_type"]
            or request.get("sourceWidth") != request_row["source_width"]
            or request.get("sourceHeight") != request_row["source_height"]
        ):
            raise RuntimeError(
                "SAM 3D Body request identity/content is invalid"
            )
        expected_engine: dict[str, object] = {
            "name": "facebookresearch/sam-3d-body",
            "mode": "native-standalone",
        }
        if request_schema == 2:
            try:
                request_model_id = validate_model_id(request.get("modelId"))
            except ValueError as error:
                raise RuntimeError(
                    "SAM 3D Body request model is invalid"
                ) from error
            if request_model_id == "default":
                request_config = self.model_configs.get(request_model_id)
                backbone = (
                    _checkpoint_backbone(request_config.checkpoint)
                    if request_config is not None
                    else None
                )
            else:
                backbone = request_model_id
            if backbone is None:
                raise RuntimeError(
                    "SAM 3D Body request model backbone is invalid"
                )
            comparison_id = request.get("comparisonId")
            if comparison_id is not None and (
                not isinstance(comparison_id, str)
                or SAM3D_JOB_ID.fullmatch(comparison_id) is None
            ):
                raise RuntimeError(
                    "SAM 3D Body comparison identity is invalid"
                )
            expected_engine.update(
                {
                    "modelId": request_model_id,
                    "backbone": backbone,
                }
            )
        if manifest.get("schema") != request_schema:
            raise RuntimeError(
                "SAM 3D Body manifest/request schema is invalid"
            )
        request_width = request.get("sourceWidth")
        request_height = request.get("sourceHeight")
        request_type = request.get("sourceType")
        if (
            isinstance(request_width, bool)
            or not isinstance(request_width, int)
            or isinstance(request_height, bool)
            or not isinstance(request_height, int)
            or not isinstance(request_type, str)
            or request_type not in _CONTENT_TYPE_EXTENSIONS
        ):
            raise RuntimeError(
                "SAM 3D Body request source is invalid"
            )
        try:
            request_bbox, request_vertical_fov = self._request_values(
                image=ImageInfo(
                    content_type=request_type,
                    extension=_CONTENT_TYPE_EXTENSIONS[request_type],
                    width=request_width,
                    height=request_height,
                ),
                bbox=request.get("bbox"),
                vertical_fov=request.get("verticalFov"),
            )
        except ValueError as error:
            raise RuntimeError(
                "SAM 3D Body request camera inputs are invalid"
            ) from error
        engine = manifest.get("engine")
        artifacts = manifest.get("artifacts")
        base_artifacts = {
            "arrays": "arrays.npz",
            "overlay": "overlay.png",
        }
        artifacts_valid = artifacts == base_artifacts
        arrays_metadata: object = None
        if (
            isinstance(artifacts, dict)
            and set(artifacts) == {
                "arrays",
                "arraysMetadata",
                "overlay",
            }
            and artifacts.get("arrays") == "arrays.npz"
            and artifacts.get("overlay") == "overlay.png"
        ):
            arrays_metadata = artifacts.get("arraysMetadata")
            artifacts_valid = _valid_arrays_artifact_metadata(
                arrays_metadata,
                person_count=len(people) if isinstance(people, list) else 0,
            )
        if (
            not isinstance(source, dict)
            or set(source) != {
                "width",
                "height",
                "contentType",
                "bbox",
                "verticalFov",
            }
            or source.get("width") != request_width
            or source.get("height") != request_height
            or source.get("contentType") != request_type
            or source.get("bbox") != request_bbox
            or source.get("verticalFov") != request_vertical_fov
            or engine != expected_engine
            or not artifacts_valid
            or not isinstance(people, list)
            or not 1 <= len(people) <= 16
        ):
            raise RuntimeError("SAM 3D Body manifest contents are invalid")
        for person_index, person in enumerate(people):
            if (
                not isinstance(person, dict)
                or person.get("index") != person_index
                or person.get("keypointNames") != list(MHR70_NAMES)
            ):
                raise RuntimeError("SAM 3D Body person result is invalid")
            for name, rows, columns in (
                ("keypoints3d", 70, 3),
                ("keypoints2d", 70, 2),
            ):
                values = person.get(name)
                if (
                    not isinstance(values, list)
                    or len(values) != rows
                    or any(
                        not isinstance(row, list)
                        or len(row) != columns
                        or any(
                            isinstance(item, bool)
                            or not isinstance(item, (int, float))
                            or not math.isfinite(float(item))
                            for item in row
                        )
                        for row in values
                    )
                ):
                    raise RuntimeError(f"SAM 3D Body {name} result is invalid")
            for name, size in (("bbox", 4), ("predCamT", 3)):
                values = person.get(name)
                if (
                    not isinstance(values, list)
                    or len(values) != size
                    or any(
                        isinstance(item, bool)
                        or not isinstance(item, (int, float))
                        or not math.isfinite(float(item))
                        for item in values
                    )
                ):
                    raise RuntimeError(f"SAM 3D Body {name} result is invalid")
            focal = person.get("focalLength")
            if (
                isinstance(focal, bool)
                or not isinstance(focal, (int, float))
                or not math.isfinite(float(focal))
                or float(focal) <= 0.0
            ):
                raise RuntimeError("SAM 3D Body focal length is invalid")
            body_proportions = person.get("bodyProportions")
            if body_proportions is not None:
                try:
                    validate_body_proportions(body_proportions)
                except ValueError as error:
                    raise RuntimeError(
                        "SAM 3D Body body proportions are invalid"
                    ) from error
        if arrays_metadata is not None:
            actual_metadata = _arrays_artifact_metadata(
                paths.arrays,
                person_count=len(people),
            )
            if arrays_metadata != actual_metadata:
                raise RuntimeError(
                    "SAM 3D Body arrays do not match their artifact metadata"
                )
        unsigned_manifest = dict(manifest)
        unsigned_manifest.pop("revision", None)
        canonical = json.dumps(
            unsigned_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        revision = hashlib.sha256(canonical).hexdigest()[:32]
        return manifest, revision

    def _validated_manifest(
        self,
        job_id: str,
        paths: Sam3dJobPaths,
    ) -> tuple[dict[str, object], str]:
        manifest, revision = self._read_validated_manifest(job_id, paths)
        if not paths.overlay.is_file() or paths.overlay.stat().st_size > 32 * 1024 * 1024:
            raise RuntimeError("SAM 3D Body overlay is missing or too large")
        artifacts = manifest["artifacts"]
        if "arraysMetadata" not in artifacts:
            artifacts["arraysMetadata"] = _arrays_artifact_metadata(
                paths.arrays,
                person_count=len(manifest["people"]),
            )
            unsigned_manifest = dict(manifest)
            unsigned_manifest.pop("revision", None)
            canonical = json.dumps(
                unsigned_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            revision = hashlib.sha256(canonical).hexdigest()[:32]
        manifest["revision"] = revision
        atomic_write_text(
            paths.manifest,
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        return manifest, revision

    def manifest(self, job_id: str) -> dict[str, object]:
        job_id = validate_job_id(job_id)
        job = self.get(job_id)
        if job["state"] != "succeeded":
            raise Sam3dJobError("SAM3D job has not completed successfully")
        paths = self._paths(job_id)
        try:
            manifest, computed_revision = self._read_validated_manifest(
                job_id,
                paths,
            )
        except RuntimeError as error:
            raise Sam3dJobError(
                "persisted SAM3D manifest failed validation"
            ) from error
        manifest_revision = manifest.get("revision")
        database_revision = job.get("revision")
        if (
            not isinstance(manifest_revision, str)
            or SAM3D_JOB_ID.fullmatch(manifest_revision) is None
            or not isinstance(database_revision, str)
            or SAM3D_JOB_ID.fullmatch(database_revision) is None
            or manifest_revision != computed_revision
            or database_revision != computed_revision
        ):
            raise Sam3dJobError(
                "persisted SAM3D manifest revision does not match the completed job"
            )
        return manifest

    def select_person(
        self,
        job_id: str,
        *,
        expected_revision: str,
        person_index: int,
    ) -> dict[str, object]:
        job_id = validate_job_id(job_id)
        if (
            not isinstance(expected_revision, str)
            or re.fullmatch(r"[0-9a-f]{32}", expected_revision) is None
        ):
            raise ValueError(
                "expected_revision must be a lowercase 32-character token"
            )
        if isinstance(person_index, bool) or not isinstance(person_index, int):
            raise TypeError("person_index must be an integer")
        with connect(self.state_dir) as connection:
            row = connection.execute(
                """
                SELECT state, revision, result_json
                FROM sam3d_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"SAM3D job not found: {job_id}")
            if row["state"] != "succeeded":
                raise Sam3dJobError(
                    "SAM3D person selection requires a successful job"
                )
            if row["revision"] != expected_revision:
                raise ValueError("SAM3D job revision has changed")
            try:
                result = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                result = {}
            if not isinstance(result, dict):
                result = {}
            count = result.get("person_count")
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or person_index < 0
                or person_index >= count
            ):
                raise ValueError("person_index is not available in this result")
            result["selected_person_index"] = person_index
            connection.execute(
                """
                UPDATE sam3d_jobs SET result_json = ?, updated_utc = ?
                WHERE id = ?
                """,
                (
                    json.dumps(result, separators=(",", ":"), sort_keys=True),
                    _utc_now(),
                    job_id,
                ),
            )
        return self.get(job_id)

    def artifact(self, job_id: str, name: str) -> tuple[Path, str]:
        if name not in SAM3D_ARTIFACTS:
            raise ValueError("unknown SAM3D artifact")
        job = self.get(job_id)
        paths = self._paths(job_id)
        if name == "source":
            path = paths.source
            content_type = str(job["source"]["content_type"])
        elif name == "manifest":
            if job["state"] != "succeeded":
                raise Sam3dJobError("SAM3D manifest is not available yet")
            self.manifest(job_id)
            path = paths.manifest
            content_type = "application/json"
        else:
            if job["state"] != "succeeded":
                raise Sam3dJobError("SAM3D overlay is not available yet")
            path = paths.overlay
            content_type = "image/png"
        if not path.is_file():
            raise FileNotFoundError(f"SAM3D artifact not found: {name}")
        return path, content_type

    def record_vam_action(
        self,
        job_id: str,
        *,
        action: str,
        revision: str,
        request_id: str,
        bridge_instance: str = "",
        target_uid: str | None = None,
        camera_uid: str | None = None,
        capture_extension: str | None = None,
        capture_content_type: str | None = None,
    ) -> None:
        job_id = validate_job_id(job_id)
        if action == "capture":
            if capture_extension is None or capture_content_type is None:
                raise ValueError(
                    "capture extension and content type are required"
                )
            if (
                _CAPTURE_CONTENT_TYPES.get(capture_extension)
                != capture_content_type
            ):
                raise ValueError("invalid SAM3D capture content type")
        elif capture_extension is not None or capture_content_type is not None:
            raise ValueError(
                "capture metadata is only valid for capture actions"
            )
        with connect(self.state_dir) as connection:
            row = connection.execute(
                "SELECT result_json FROM sam3d_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"SAM3D job not found: {job_id}")
            try:
                result = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                result = {}
            if not isinstance(result, dict):
                result = {}
            previous = result.get("last_vam_action")
            if isinstance(previous, dict):
                if target_uid is None and isinstance(
                    previous.get("target_uid"), str
                ):
                    target_uid = str(previous["target_uid"])
                if camera_uid is None and isinstance(
                    previous.get("camera_uid"), str
                ):
                    camera_uid = str(previous["camera_uid"])
            action_record: dict[str, object] = {
                "action": action,
                "revision": revision,
                "request_id": request_id,
                "bridge_instance": bridge_instance,
                "target_uid": target_uid,
                "camera_uid": camera_uid,
                "state": "queued",
                "message": "Waiting for the VaM bridge to accept the request.",
                "created_at_utc": _utc_now(),
            }
            if capture_extension is not None:
                action_record["capture_extension"] = capture_extension
                action_record["capture_content_type"] = capture_content_type
            result["last_vam_action"] = action_record
            connection.execute(
                """
                UPDATE sam3d_jobs SET result_json = ?, updated_utc = ?
                WHERE id = ?
                """,
                (
                    json.dumps(result, separators=(",", ":"), sort_keys=True),
                    _utc_now(),
                    job_id,
                ),
            )

    def reconcile_vam_action(
        self,
        job_id: str,
        *,
        request_id: str,
        state: str,
        message: str,
    ) -> None:
        job_id = validate_job_id(job_id)
        if state not in {"succeeded", "failed", "stale"}:
            raise ValueError("invalid VaM action terminal state")
        with connect(self.state_dir) as connection:
            # Serialize the read/modify/write so a late bridge poll cannot
            # overwrite a terminal result chosen by another request thread.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT result_json FROM sam3d_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"SAM3D job not found: {job_id}")
            try:
                result = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                return
            if not isinstance(result, dict):
                return
            action = result.get("last_vam_action")
            if (
                not isinstance(action, dict)
                or action.get("request_id") != request_id
            ):
                return
            if action.get("state") in {"succeeded", "failed", "stale"}:
                return
            action["state"] = state
            action["message"] = str(message)[:1000]
            finished_at_utc = _utc_now()
            action["finished_at_utc"] = finished_at_utc
            if state == "succeeded" and action.get("action") == "capture":
                extension = action.get("capture_extension")
                content_type = action.get("capture_content_type")
                revision = action.get("revision")
                if (
                    isinstance(extension, str)
                    and _CAPTURE_CONTENT_TYPES.get(extension) == content_type
                    and SAM3D_JOB_ID.fullmatch(request_id) is not None
                    and isinstance(revision, str)
                    and SAM3D_JOB_ID.fullmatch(revision) is not None
                ):
                    capture = {
                        "request_id": request_id,
                        "revision": revision,
                        "target_uid": action.get("target_uid"),
                        "camera_uid": action.get("camera_uid"),
                        "extension": extension,
                        "content_type": content_type,
                        "captured_at_utc": finished_at_utc,
                    }
                    history = {
                        str(record["request_id"]): record
                        for record in _capture_history_from_result(result)
                    }
                    history[request_id] = capture
                    result["capture_history"] = sorted(
                        history.values(),
                        key=lambda record: (
                            _capture_record_timestamp(record),
                            str(record["request_id"]),
                        ),
                        reverse=True,
                    )[:SAM3D_CAPTURE_HISTORY_LIMIT]
                    result["last_capture"] = capture
            connection.execute(
                """
                UPDATE sam3d_jobs SET result_json = ?, updated_utc = ?
                WHERE id = ?
                """,
                (
                    json.dumps(result, separators=(",", ":"), sort_keys=True),
                    _utc_now(),
                    job_id,
                ),
            )

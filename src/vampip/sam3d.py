from __future__ import annotations

from dataclasses import dataclass
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
from vampip.sam3d_vam import MHR70_NAMES


SAM3D_UPLOAD_LIMIT = 32 * 1024 * 1024
SAM3D_MAX_PIXELS = 50_000_000
SAM3D_MAX_DIMENSION = 32_768
SAM3D_MANIFEST_LIMIT = 4 * 1024 * 1024
SAM3D_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
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


@dataclass(frozen=True)
class Sam3dWorkerConfig:
    python: Path | None
    conda_executable: Path | None
    conda_env: str | None
    repo: Path | None
    checkpoint: Path | None
    mhr: Path | None
    timeout_seconds: int = 1800

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
            config_candidates = (
                self.checkpoint.parent / "model_config.yaml",
                self.checkpoint.parent.parent / "model_config.yaml",
            )
            if not any(candidate.is_file() for candidate in config_candidates):
                errors.append(
                    "model_config.yaml is missing beside the checkpoint "
                    "or in its parent directory"
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
        model_config = bool(
            self.checkpoint is not None
            and (
                (self.checkpoint.parent / "model_config.yaml").is_file()
                or (
                    self.checkpoint.parent.parent / "model_config.yaml"
                ).is_file()
            )
        )
        return {
            "configured": not errors,
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
            "errors": errors,
        }


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
        for key, value in os.environ.items():
            upper_key = key.upper()
            if (
                upper_key.startswith("LD_")
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
                "TORCH_HOME": str(cache_dir / "torch"),
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
            "--source",
            str(paths.source),
            "--request",
            str(paths.request),
            "--output-dir",
            str(paths.directory),
        ]
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
        worker: WorkerCallable | None = None,
    ) -> None:
        self.state_dir = state_dir.expanduser().resolve()
        self.root = self.state_dir / "sam3d"
        self.jobs_dir = self.root / "jobs"
        self.runtime_dir = self.root / "runtime"
        self.jobs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.config = config or Sam3dWorkerConfig.from_environment()
        self.worker = worker or SubprocessSam3dWorker()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._recover_and_resume()

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
    ) -> dict[str, object]:
        image = inspect_image(image_data, content_type)
        bbox, vertical_fov = self._request_values(
            image=image,
            bbox=bbox,
            vertical_fov=vertical_fov,
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
            "schema": 1,
            "jobId": job_id,
            "sourceType": image.content_type,
            "sourceWidth": image.width,
            "sourceHeight": image.height,
            "bbox": bbox,
            "verticalFov": vertical_fov,
        }
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
        with connect(self.state_dir) as connection:
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
                    json.dumps(request, separators=(",", ":"), sort_keys=True),
                ),
            )
        return self.get(job_id)

    @staticmethod
    def _document(row: sqlite3.Row) -> dict[str, object]:
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
            "person_count": result.get("person_count"),
            "selected_person_index": result.get("selected_person_index", 0),
            "last_vam_action": result.get("last_vam_action"),
            "last_capture": result.get("last_capture"),
            "error": str(row["error"]) if row["error"] is not None else None,
            "revision": str(row["revision"]) if row["revision"] else None,
            "terminal": str(row["state"]) in _TERMINAL_STATES,
        }

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
        worker = self.config.public_status()
        return {
            "available": bool(worker["configured"]),
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
        errors = self.config.errors()
        if errors:
            raise Sam3dConfigurationError("; ".join(errors))
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
                    for stale_path in (
                        paths.manifest,
                        paths.overlay,
                        paths.arrays,
                    ):
                        stale_path.unlink(missing_ok=True)
                    self.worker(self.config, paths, self.runtime_dir)
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
            or manifest.get("schema") != 1
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
        request_keys = {
            "schema",
            "jobId",
            "sourceType",
            "sourceWidth",
            "sourceHeight",
            "bbox",
            "verticalFov",
        }
        if (
            not isinstance(request, dict)
            or not isinstance(persisted_request, dict)
            or request != persisted_request
            or set(request) != request_keys
            or request.get("schema") != 1
            or request.get("jobId") != job_id
            or request.get("sourceType") != request_row["source_type"]
            or request.get("sourceWidth") != request_row["source_width"]
            or request.get("sourceHeight") != request_row["source_height"]
        ):
            raise RuntimeError(
                "SAM 3D Body request identity/content is invalid"
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
            or engine
            != {
                "name": "facebookresearch/sam-3d-body",
                "mode": "native-standalone",
            }
            or artifacts
            != {
                "arrays": "arrays.npz",
                "overlay": "overlay.png",
            }
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
        if not paths.arrays.is_file() or paths.arrays.stat().st_size > 512 * 1024 * 1024:
            raise RuntimeError("SAM 3D Body arrays are missing or too large")
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
                    result["last_capture"] = {
                        "request_id": request_id,
                        "revision": revision,
                        "target_uid": action.get("target_uid"),
                        "camera_uid": action.get("camera_uid"),
                        "extension": extension,
                        "content_type": content_type,
                        "captured_at_utc": finished_at_utc,
                    }
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

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
import uuid

from vampip.analysis import package_id
from vampip.models import DISABLED_SUFFIX
from vampip.profiles import preferred


_RUN_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_PROGRESS_FSYNC_BATCH = 64
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1

_LIBC = ctypes.CDLL(None, use_errno=True)
_RENAMEAT2 = getattr(_LIBC, "renameat2", None)
if _RENAMEAT2 is not None:
    _RENAMEAT2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    _RENAMEAT2.restype = ctypes.c_int

ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class SwitchPlan:
    desired_ids: tuple[str, ...]
    to_enable: tuple[sqlite3.Row, ...]
    to_disable: tuple[sqlite3.Row, ...]

    @property
    def active_after(self) -> int:
        return len(self.desired_ids)


def logical_relative_path(row: sqlite3.Row) -> str:
    value = str(row["relative_path"])
    if value.casefold().endswith(DISABLED_SUFFIX):
        return value[: -len(DISABLED_SUFFIX)]
    return value


def build_switch_plan(
    rows: list[sqlite3.Row],
    desired_ids: list[str] | tuple[str, ...],
    *,
    disable_unselected: bool,
) -> SwitchPlan:
    """Build a package switch without modifying the filesystem.

    Invalid archives are deliberately left untouched. A manager profile cannot
    resolve their identity reliably, so hiding them automatically would make a
    bad archive harder to diagnose.
    """

    by_id: dict[str, list[sqlite3.Row]] = {}
    display_ids: dict[str, str] = {}
    for row in rows:
        if not row["valid"] or not row["version_text"]:
            continue
        identity = package_id(row)
        key = identity.casefold()
        by_id.setdefault(key, []).append(row)
        display_ids.setdefault(key, identity)

    desired_paths: set[str] = set()
    missing: list[str] = []
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for identity in desired_ids:
        key = identity.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates = by_id.get(key)
        if not candidates:
            missing.append(identity)
            continue
        selected = preferred(candidates)
        desired_paths.add(selected["path"])
        normalized_ids.append(display_ids[key])
    if missing:
        raise ValueError(
            "desired packages are no longer present: " + ", ".join(missing[:10])
        )

    to_enable: list[sqlite3.Row] = []
    to_disable: list[sqlite3.Row] = []
    for row in rows:
        if not row["valid"] or not row["version_text"]:
            continue
        selected = row["path"] in desired_paths
        if selected and not row["enabled"]:
            to_enable.append(row)
        elif disable_unselected and not selected and row["enabled"]:
            to_disable.append(row)

    def order(row: sqlite3.Row) -> str:
        return str(row["relative_path"]).casefold()

    return SwitchPlan(
        desired_ids=tuple(sorted(normalized_ids, key=str.casefold)),
        to_enable=tuple(sorted(to_enable, key=order)),
        to_disable=tuple(sorted(to_disable, key=order)),
    )


def build_baseline_restore_plan(
    rows: list[sqlite3.Row],
    baseline: dict[str, bool],
) -> SwitchPlan:
    """Restore exact per-file enabled states captured before managed mode."""

    to_enable: list[sqlite3.Row] = []
    to_disable: list[sqlite3.Row] = []
    desired_ids: dict[str, str] = {}
    folded_baseline: dict[str, list[bool]] = {}
    for key, value in baseline.items():
        folded_baseline.setdefault(key.casefold(), []).append(value)
    for row in rows:
        if not row["valid"] or not row["version_text"]:
            continue
        logical_path = logical_relative_path(row)
        if logical_path in baseline:
            wanted = baseline[logical_path]
        else:
            case_insensitive = folded_baseline.get(logical_path.casefold(), [])
            wanted = case_insensitive[0] if len(case_insensitive) == 1 else None
        if wanted is None:
            continue
        if wanted:
            identity = package_id(row)
            desired_ids.setdefault(identity.casefold(), identity)
            if not row["enabled"]:
                to_enable.append(row)
        elif row["enabled"]:
            to_disable.append(row)

    def order(row: sqlite3.Row) -> str:
        return str(row["relative_path"]).casefold()

    return SwitchPlan(
        desired_ids=tuple(sorted(desired_ids.values(), key=str.casefold)),
        to_enable=tuple(sorted(to_enable, key=order)),
        to_disable=tuple(sorted(to_disable, key=order)),
    )


def _destination(row: sqlite3.Row, *, enable: bool) -> Path:
    source = Path(row["path"])
    if enable:
        source_text = str(source)
        if not source_text.casefold().endswith(DISABLED_SUFFIX):
            raise ValueError(f"not a VAM-PIP-disabled package: {source}")
        return Path(source_text[: -len(DISABLED_SUFFIX)])
    if source.name.casefold().endswith(DISABLED_SUFFIX):
        raise ValueError(f"package is already disabled: {source}")
    return Path(f"{source}{DISABLED_SUFFIX}")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, target: Path) -> None:
    """Atomically rename one archive without ever replacing another path."""

    if _RENAMEAT2 is None:
        raise OSError(
            errno.ENOSYS,
            "renameat2(RENAME_NOREPLACE) is required for safe package switches",
        )
    result = _RENAMEAT2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
    """Durably replace one canonical switch manifest."""

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class _ProgressJournal:
    """Small append-only switch evidence, flushed and fsynced in batches."""

    def __init__(self, path: Path, *, create: bool) -> None:
        self.path = path
        flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        handle = None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError(
                    "progress journal must be one non-linked regular file: "
                    f"{path}"
                )
            torn_tail = False
            if create:
                _fsync_directory(path.parent)
            elif metadata.st_size:
                os.lseek(descriptor, -1, os.SEEK_END)
                torn_tail = os.read(descriptor, 1) != b"\n"
            handle = os.fdopen(descriptor, "a", encoding="utf-8")
            descriptor = -1
            if torn_tail:
                # Preserve a crash-torn final line as evidence, but ensure
                # every newly appended event starts on its own line.
                handle.write("\n")
        except BaseException:
            if handle is not None:
                handle.close()
            elif descriptor >= 0:
                os.close(descriptor)
            raise
        self._handle = handle
        self._pending = 1 if torn_tail else 0

    def append(self, event: Mapping[str, object], *, sync: bool = False) -> None:
        self._handle.write(
            json.dumps(
                dict(event),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        self._pending += 1
        if sync or self._pending >= _PROGRESS_FSYNC_BATCH:
            self.sync()

    def sync(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._pending = 0

    def close(self) -> None:
        if not self._handle.closed:
            if self._pending:
                self.sync()
            self._handle.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    phase: str,
    total: int,
    completed: int,
    enable: int,
    disable: int,
    **extra: object,
) -> None:
    if callback is None:
        return
    event: dict[str, object] = {
        "phase": phase,
        "total": total,
        "completed": completed,
        "enable": enable,
        "disable": disable,
    }
    event.update(extra)
    try:
        callback(event)
    except Exception:
        # Progress is observational. A UI/logging failure must never decide
        # whether package visibility is changed or rolled back.
        pass


def _matches_recorded_identity(
    path: Path,
    entry: Mapping[str, object],
) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        stat = path.stat()
        expected = (
            int(entry["device"]),
            int(entry["inode"]),
            int(entry["size"]),
            int(entry["mtime_ns"]),
        )
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return expected == (
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    )


def _matches_legacy_identity(
    path: Path,
    entry: Mapping[str, object],
) -> bool:
    """Match the optional identity fields accepted by format-1 rollback."""

    if path.is_symlink() or not path.is_file():
        return False
    try:
        stat = path.stat()
        for field, actual in (
            ("device", stat.st_dev),
            ("inode", stat.st_ino),
            ("size", stat.st_size),
            ("mtime_ns", stat.st_mtime_ns),
        ):
            expected = entry.get(field)
            if expected is not None and int(expected) != actual:
                return False
    except (OSError, TypeError, ValueError):
        return False
    return True


def classify_switch_move(entry: Mapping[str, object]) -> str:
    """Classify a journalled move using both paths and recorded identity.

    ``source`` and ``target`` mean exactly one path exists and still has the
    recorded device/inode/size/mtime identity. Every other result is unsafe
    for an unattended rename.
    """

    source_value = entry.get("source")
    target_value = entry.get("target")
    if not isinstance(source_value, str) or not isinstance(target_value, str):
        return "invalid"
    source = Path(source_value)
    target = Path(target_value)
    source_exists = os.path.lexists(source)
    target_exists = os.path.lexists(target)
    if source_exists and target_exists:
        return "conflict"
    if not source_exists and not target_exists:
        return "missing"
    if source_exists:
        return (
            "source"
            if _matches_recorded_identity(source, entry)
            else "source-changed"
        )
    return (
        "target"
        if _matches_recorded_identity(target, entry)
        else "target-changed"
    )


class ManagerLockBusyError(RuntimeError):
    """Raised when a non-blocking manager lock is already owned."""


@contextmanager
def manager_lock(
    state_dir: Path,
    *,
    blocking: bool = True,
) -> Iterator[None]:
    """Serialize all manager operations that can rename archives."""

    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        state_dir.chmod(0o700)
    except OSError:
        pass
    lock_path = state_dir / "manager.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    locked = False
    try:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - the manager targets Linux
            fcntl = None
        if fcntl is not None:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as error:
                raise ManagerLockBusyError(
                    f"manager lock is already held: {lock_path}"
                ) from error
            locked = True
        yield
    finally:
        if locked:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _manifest_path(state_dir: Path, run_name: str) -> Path:
    run_dir = state_dir / "manager-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _RUN_NAME.sub("-", run_name).strip("-") or "switch"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = run_dir / f"{timestamp}-{safe_name}.json"
    if path.exists():
        path = run_dir / f"{timestamp}-{safe_name}-{uuid.uuid4().hex[:8]}.json"
    return path


def _progress_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(".progress.jsonl")


def _progress_path_from_manifest(
    manifest_path: Path,
    document: Mapping[str, object],
) -> Path:
    value = document.get("progress_file")
    expected = _progress_path(manifest_path)
    if not isinstance(value, str) or value != expected.name:
        raise ValueError("manager switch manifest has an invalid progress journal")
    return expected


def _validated_move_paths(
    entry: Mapping[str, object],
    addon_dir: Path,
) -> tuple[Path, Path]:
    source_value = entry.get("source")
    target_value = entry.get("target")
    if not isinstance(source_value, str) or not isinstance(target_value, str):
        raise ValueError("manager switch manifest has an invalid move path")
    source = Path(source_value)
    target = Path(target_value)
    if not source.is_absolute() or not target.is_absolute():
        raise ValueError("manager switch manifest paths must be absolute")

    action = entry.get("action")
    if action == "enable":
        if not source_value.casefold().endswith(DISABLED_SUFFIX):
            raise ValueError("manager switch manifest has an invalid enable path")
        expected = Path(source_value[: -len(DISABLED_SUFFIX)])
    elif action == "disable":
        if source_value.casefold().endswith(DISABLED_SUFFIX):
            raise ValueError("manager switch manifest has an invalid disable path")
        expected = Path(f"{source_value}{DISABLED_SUFFIX}")
    else:
        raise ValueError("manager switch manifest has an invalid action")
    if expected != target:
        raise ValueError("manager switch manifest contains mismatched paths")

    if not source.parent.resolve().is_relative_to(
        addon_dir
    ) or not target.parent.resolve().is_relative_to(addon_dir):
        raise ValueError("manager switch manifest path escapes AddonPackages")
    return source, target


def _load_switch_manifest(
    manifest_path: Path,
) -> tuple[dict[str, object], Path, list[dict[str, object]]]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("format") not in (1, 2)
        or document.get("kind") != "manager-switch"
        or not isinstance(document.get("moves"), list)
    ):
        raise ValueError("unsupported manager switch manifest")
    addon_value = document.get("addon_dir")
    if not isinstance(addon_value, str):
        raise ValueError("manager switch manifest has no AddonPackages root")
    addon_dir = Path(addon_value).resolve()

    moves: list[dict[str, object]] = []
    for value in document["moves"]:
        if not isinstance(value, dict):
            raise ValueError("manager switch manifest has an invalid move")
        _validated_move_paths(value, addon_dir)
        moves.append(value)
    if document.get("format") == 2:
        _progress_path_from_manifest(manifest_path, document)
    return document, addon_dir, moves


def _recorded_expected_state(
    document: Mapping[str, object],
    entry: Mapping[str, object],
) -> str | None:
    if document.get("format") == 1:
        status = entry.get("status")
        if status == "complete":
            return "target"
        if status in ("planned", "rolled-back"):
            return "source"
        return None
    status = document.get("status")
    if status == "complete":
        return "target"
    if status == "rolled-back":
        return "source"
    return None


def inspect_switch(manifest_path: Path) -> dict[str, object]:
    """Read-only comparison of a switch manifest with current filesystem state."""

    document, _, moves = _load_switch_manifest(manifest_path)
    state_counts: dict[str, int] = {}
    recorded_counts: dict[str, int] = {}
    unsafe_sample: list[dict[str, object]] = []
    inconsistent_sample: list[dict[str, object]] = []
    unsafe_count = 0
    inconsistent_count = 0
    safe_states = {"source", "target"}

    for index, entry in enumerate(moves):
        state = classify_switch_move(entry)
        state_counts[state] = state_counts.get(state, 0) + 1
        recorded = entry.get("status") if document.get("format") == 1 else None
        if isinstance(recorded, str):
            recorded_counts[recorded] = recorded_counts.get(recorded, 0) + 1
        summary = {
            "index": index,
            "package_id": entry.get("package_id"),
            "action": entry.get("action"),
            "state": state,
        }
        if state not in safe_states:
            unsafe_count += 1
            if len(unsafe_sample) < 20:
                unsafe_sample.append(summary)
        expected = _recorded_expected_state(document, entry)
        if expected is not None and state != expected:
            inconsistent_count += 1
            if len(inconsistent_sample) < 20:
                inconsistent_sample.append({**summary, "expected": expected})

    status = document.get("status")
    switch_format = int(document["format"])
    if switch_format == 2:
        recoverable_status = status in {
            "applying",
            "complete",
            "rolling-back",
            "rollback-failed",
        }
        state_is_recoverable = (
            unsafe_count == 0
            and state_counts.get("source", 0)
            + state_counts.get("target", 0)
            == len(moves)
        )
        complete_is_consistent = (
            status != "complete"
            or state_counts.get("target", 0) == len(moves)
        )
        safe_to_rollback = (
            recoverable_status
            and state_is_recoverable
            and complete_is_consistent
        )
    else:
        safe_to_rollback = (
            status == "complete"
            and unsafe_count == 0
            and state_counts.get("target", 0) == len(moves)
            and recorded_counts.get("complete", 0) == len(moves)
        )
    return {
        "manifest": str(manifest_path.resolve()),
        "format": switch_format,
        "status": status,
        "total": len(moves),
        "state_counts": state_counts,
        "recorded_status_counts": recorded_counts,
        "unsafe_count": unsafe_count,
        "unsafe_sample": unsafe_sample,
        "inconsistent_count": inconsistent_count,
        "inconsistent_sample": inconsistent_sample,
        "safe_to_rollback": safe_to_rollback,
    }


def apply_switch(
    state_dir: Path,
    addon_dir: Path,
    plan: SwitchPlan,
    *,
    run_name: str,
    allow_disable: bool,
    lock_held: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> Path | None:
    """Apply a switch atomically per file with an append-only progress journal.

    Enabling happens first. If a later operation fails, completed renames are
    immediately rolled back. This favours leaving extra packages visible over
    leaving a requested dependency unavailable.
    """

    enable_count = len(plan.to_enable)
    disable_count = len(plan.to_disable)
    total = enable_count + disable_count
    _emit_progress(
        progress_callback,
        phase="preparing",
        total=total,
        completed=0,
        enable=enable_count,
        disable=disable_count,
    )
    if plan.to_disable and not allow_disable:
        error = "refusing to disable packages while VaM may be running"
        _emit_progress(
            progress_callback,
            phase="error",
            total=total,
            completed=0,
            enable=enable_count,
            disable=disable_count,
            status="refused",
            error=error,
        )
        raise ValueError(error)
    if not plan.to_enable and not plan.to_disable:
        _emit_progress(
            progress_callback,
            phase="final",
            total=0,
            completed=0,
            enable=0,
            disable=0,
            status="unchanged",
        )
        return None
    if _RENAMEAT2 is None:
        error = (
            "this Linux runtime does not expose "
            "renameat2(RENAME_NOREPLACE), which VAM-PIP requires to switch "
            "packages without overwriting files"
        )
        _emit_progress(
            progress_callback,
            phase="error",
            total=total,
            completed=0,
            enable=enable_count,
            disable=disable_count,
            status="refused",
            error=error,
        )
        raise OSError(errno.ENOSYS, error)

    addon_dir = addon_dir.resolve()
    manifest_path: Path | None = None
    progress: _ProgressJournal | None = None
    completed_count = 0
    document: dict[str, object] | None = None
    error_emitted = False
    lock_context = nullcontext() if lock_held else manager_lock(state_dir)
    try:
        with lock_context:
            moves: list[dict[str, object]] = []
            for action, selected_rows, enable in (
                ("enable", plan.to_enable, True),
                ("disable", plan.to_disable, False),
            ):
                for row in selected_rows:
                    source = Path(row["path"]).resolve()
                    if not source.is_relative_to(addon_dir):
                        raise ValueError(
                            f"package is outside AddonPackages: {source}"
                        )
                    target = _destination(row, enable=enable).resolve()
                    entry: dict[str, object] = {
                        "action": action,
                        "source": str(source),
                        "target": str(target),
                        "package_id": package_id(row),
                        "size": row["size"],
                        "device": row["device"],
                        "inode": row["inode"],
                        "mtime_ns": row["mtime_ns"],
                        "sha256": row["sha256"],
                    }
                    _validated_move_paths(entry, addon_dir)
                    moves.append(entry)

            for entry in moves:
                source = Path(str(entry["source"]))
                target = Path(str(entry["target"]))
                state = classify_switch_move(entry)
                if state == "missing":
                    raise FileNotFoundError(f"managed package is missing: {source}")
                if state in ("target", "target-changed", "conflict"):
                    raise FileExistsError(
                        f"package rename target already exists: {target}"
                    )
                if state != "source":
                    raise ValueError(
                        f"managed package changed since the inventory scan: {source}"
                    )

            manifest_path = _manifest_path(state_dir, run_name)
            progress_path = _progress_path(manifest_path)
            document = {
                "format": 2,
                "kind": "manager-switch",
                "created_utc": _utc_now(),
                "addon_dir": str(addon_dir),
                "desired_packages": list(plan.desired_ids),
                "status": "applying",
                "move_count": total,
                "enable_count": enable_count,
                "disable_count": disable_count,
                "completed_count": 0,
                "progress_file": progress_path.name,
                "progress_fsync_batch": _PROGRESS_FSYNC_BATCH,
                "moves": moves,
            }
            progress = _ProgressJournal(progress_path, create=True)
            progress.append(
                {
                    "event": "start",
                    "utc": _utc_now(),
                    "total": total,
                },
                sync=True,
            )
            _write_json_atomic(manifest_path, document)
            _emit_progress(
                progress_callback,
                phase="applying",
                total=total,
                completed=0,
                enable=enable_count,
                disable=disable_count,
                status="applying",
            )

            try:
                for index, entry in enumerate(moves):
                    source = Path(str(entry["source"]))
                    target = Path(str(entry["target"]))
                    _rename_noreplace(source, target)
                    if classify_switch_move(entry) != "target":
                        raise ValueError(
                            "managed package identity changed during switch: "
                            f"{target}"
                        )
                    completed_count = index + 1
                    progress.append(
                        {
                            "event": "move-complete",
                            "utc": _utc_now(),
                            "move": index,
                            "completed": completed_count,
                        }
                    )
                    if (
                        completed_count % _PROGRESS_FSYNC_BATCH == 0
                        or completed_count == total
                    ):
                        _emit_progress(
                            progress_callback,
                            phase="applying",
                            total=total,
                            completed=completed_count,
                            enable=enable_count,
                            disable=disable_count,
                            status="applying",
                        )

                progress.append(
                    {
                        "event": "applied",
                        "utc": _utc_now(),
                        "completed": total,
                    },
                    sync=True,
                )
                document["status"] = "complete"
                document["completed_count"] = total
                document["completed_utc"] = _utc_now()
                _write_json_atomic(manifest_path, document)
            except BaseException as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                states_at_failure = [
                    classify_switch_move(entry) for entry in moves
                ]
                applied_indices = [
                    index
                    for index, state in enumerate(states_at_failure)
                    if state == "target"
                ]
                completed_count = len(applied_indices)
                _emit_progress(
                    progress_callback,
                    phase="rolling-back",
                    total=completed_count,
                    completed=0,
                    enable=0,
                    disable=0,
                    status="rolling-back",
                )
                document["status"] = "rolling-back"
                document["completed_count"] = completed_count
                document["error"] = error_text
                journal_errors: list[str] = []
                try:
                    progress.append(
                        {
                            "event": "apply-error",
                            "utc": _utc_now(),
                            "completed": completed_count,
                            "error": error_text,
                        },
                        sync=True,
                    )
                except Exception as journal_exc:
                    journal_errors.append(
                        f"progress journal: {type(journal_exc).__name__}: "
                        f"{journal_exc}"
                    )
                try:
                    _write_json_atomic(manifest_path, document)
                except Exception as journal_exc:
                    journal_errors.append(
                        f"canonical manifest: {type(journal_exc).__name__}: "
                        f"{journal_exc}"
                    )

                rollback_errors: list[str] = []
                rolled_back = 0
                for move_index in reversed(applied_indices):
                    entry = moves[move_index]
                    current = Path(str(entry["target"]))
                    original = Path(str(entry["source"]))
                    try:
                        state = classify_switch_move(entry)
                        if state != "target":
                            raise ValueError(
                                "automatic rollback found unsafe filesystem "
                                f"state {state!r} for {current}"
                            )
                        _rename_noreplace(current, original)
                        if classify_switch_move(entry) != "source":
                            raise ValueError(
                                "managed package identity changed during rollback: "
                                f"{original}"
                            )
                        rolled_back += 1
                        if (
                            rolled_back % _PROGRESS_FSYNC_BATCH == 0
                            or rolled_back == completed_count
                        ):
                            _emit_progress(
                                progress_callback,
                                phase="rolling-back",
                                total=completed_count,
                                completed=rolled_back,
                                enable=0,
                                disable=0,
                                status="rolling-back",
                            )
                        try:
                            progress.append(
                                {
                                    "event": "move-rolled-back",
                                    "utc": _utc_now(),
                                    "move": move_index,
                                    "rolled_back": rolled_back,
                                }
                            )
                        except Exception as journal_exc:
                            journal_errors.append(
                                "progress journal: "
                                f"{type(journal_exc).__name__}: {journal_exc}"
                            )
                    except Exception as rollback_exc:
                        rollback_errors.append(
                            f"{type(rollback_exc).__name__}: {rollback_exc}"
                        )

                filesystem_errors = [
                    f"move {index} remains in unsafe state {state!r}"
                    for index, entry in enumerate(moves)
                    if (state := classify_switch_move(entry)) != "source"
                ]
                all_errors = (
                    rollback_errors
                    + filesystem_errors
                    + journal_errors
                )
                document["rolled_back_count"] = rolled_back
                document["status"] = (
                    "rollback-failed" if all_errors else "rolled-back"
                )
                if all_errors:
                    document["rollback_errors"] = all_errors
                document["rolled_back_utc"] = _utc_now()
                terminal_journal_errors: list[str] = []
                try:
                    progress.append(
                        {
                            "event": document["status"],
                            "utc": _utc_now(),
                            "rolled_back": rolled_back,
                            "errors": len(all_errors),
                        },
                        sync=True,
                    )
                except Exception as journal_exc:
                    terminal_journal_errors.append(
                        "terminal progress journal: "
                        f"{type(journal_exc).__name__}: {journal_exc}"
                    )
                if terminal_journal_errors:
                    document["status"] = "rollback-failed"
                    document.setdefault("rollback_errors", []).extend(
                        terminal_journal_errors
                    )
                try:
                    _write_json_atomic(manifest_path, document)
                except Exception as journal_exc:
                    terminal_journal_errors.append(
                        "terminal canonical manifest: "
                        f"{type(journal_exc).__name__}: {journal_exc}"
                    )
                    document["status"] = "rollback-failed"
                if terminal_journal_errors and hasattr(exc, "add_note"):
                    exc.add_note("; ".join(terminal_journal_errors))
                _emit_progress(
                    progress_callback,
                    phase="error",
                    total=completed_count,
                    completed=rolled_back,
                    enable=0,
                    disable=0,
                    status=document["status"],
                    error="; ".join([error_text, *terminal_journal_errors]),
                )
                error_emitted = True
                raise
    except BaseException as exc:
        if not error_emitted:
            _emit_progress(
                progress_callback,
                phase="error",
                total=total,
                completed=completed_count,
                enable=enable_count,
                disable=disable_count,
                status=(document or {}).get("status", "failed"),
                error=f"{type(exc).__name__}: {exc}",
            )
        raise
    finally:
        if progress is not None:
            primary_error_active = sys.exc_info()[0] is not None
            try:
                progress.close()
            except Exception:
                if not primary_error_active:
                    raise

    _emit_progress(
        progress_callback,
        phase="final",
        total=total,
        completed=total,
        enable=enable_count,
        disable=disable_count,
        status="complete",
    )
    return manifest_path


def _rollback_format_1(
    manifest_path: Path,
    document: dict[str, object],
    addon_dir: Path,
    moves: list[dict[str, object]],
    progress_callback: ProgressCallback | None,
) -> int:
    rollback_total = sum(entry.get("status") == "complete" for entry in moves)
    _emit_progress(
        progress_callback,
        phase="rolling-back",
        total=rollback_total,
        completed=0,
        enable=0,
        disable=0,
        status="rolling-back",
    )
    restored = 0
    for entry in reversed(moves):
        if entry.get("status") != "complete":
            continue
        original, current = _validated_move_paths(entry, addon_dir)
        if original.exists():
            raise FileExistsError(f"rollback target already exists: {original}")
        if not current.is_file():
            raise FileNotFoundError(f"managed package is missing: {current}")
        if not _matches_legacy_identity(current, entry):
            raise ValueError(f"managed package changed since the switch: {current}")
        _rename_noreplace(current, original)
        if not _matches_legacy_identity(original, entry) or current.exists():
            raise ValueError(
                f"managed package identity changed during rollback: {original}"
            )
        entry["status"] = "rolled-back"
        restored += 1
        if (
            restored % _PROGRESS_FSYNC_BATCH == 0
            or restored == rollback_total
        ):
            _emit_progress(
                progress_callback,
                phase="rolling-back",
                total=rollback_total,
                completed=restored,
                enable=0,
                disable=0,
                status="rolling-back",
            )
        _write_json_atomic(manifest_path, document)
    document["status"] = "rolled-back"
    document["rolled_back_utc"] = _utc_now()
    _write_json_atomic(manifest_path, document)
    _emit_progress(
        progress_callback,
        phase="final",
        total=rollback_total,
        completed=restored,
        enable=0,
        disable=0,
        status="rolled-back",
    )
    return restored


def _rollback_format_2(
    manifest_path: Path,
    document: dict[str, object],
    addon_dir: Path,
    moves: list[dict[str, object]],
    progress_callback: ProgressCallback | None,
) -> int:
    status = document.get("status")
    if status == "rolled-back":
        states = [classify_switch_move(entry) for entry in moves]
        if all(state == "source" for state in states):
            _emit_progress(
                progress_callback,
                phase="final",
                total=0,
                completed=0,
                enable=0,
                disable=0,
                status="rolled-back",
            )
            return 0
        raise ValueError("rolled-back manager switch no longer matches the filesystem")
    if status not in (
        "applying",
        "complete",
        "rolling-back",
        "rollback-failed",
    ):
        raise ValueError(
            f"manager switch status {status!r} is not safe to roll back"
        )

    states = [classify_switch_move(entry) for entry in moves]
    for index, state in enumerate(states):
        if status == "complete" and state != "target":
            if state in ("source-changed", "target-changed"):
                changed_key = (
                    "source" if state == "source-changed" else "target"
                )
                changed_path = Path(str(moves[index][changed_key]))
                raise ValueError(
                    f"managed package changed since the switch: {changed_path}"
                )
            raise ValueError(
                "completed manager switch is not fully applied: "
                f"move {index} is {state}"
            )
        if status != "complete" and state not in ("source", "target"):
            raise ValueError(
                "interrupted manager rollback has unsafe filesystem state: "
                f"move {index} is {state}"
            )

    progress_path = _progress_path_from_manifest(manifest_path, document)
    progress = _ProgressJournal(
        progress_path,
        create=not progress_path.exists(),
    )
    rollback_total = states.count("target")
    _emit_progress(
        progress_callback,
        phase="rolling-back",
        total=rollback_total,
        completed=0,
        enable=0,
        disable=0,
        status="rolling-back",
    )
    restored = 0
    try:
        document["status"] = "rolling-back"
        document.pop("rollback_errors", None)
        document.pop("rollback_error", None)
        _write_json_atomic(manifest_path, document)
        progress.append(
            {
                "event": "manual-rollback-start",
                "utc": _utc_now(),
                "remaining": states.count("target"),
            },
            sync=True,
        )
        for index in range(len(moves) - 1, -1, -1):
            entry = moves[index]
            state = classify_switch_move(entry)
            if state == "source":
                continue
            if state != "target":
                raise ValueError(
                    "manager switch changed during rollback: "
                    f"move {index} is {state}"
                )
            original, current = _validated_move_paths(entry, addon_dir)
            _rename_noreplace(current, original)
            if classify_switch_move(entry) != "source":
                raise ValueError(
                    "managed package identity changed during rollback: "
                    f"{original}"
                )
            restored += 1
            if (
                restored % _PROGRESS_FSYNC_BATCH == 0
                or restored == rollback_total
            ):
                _emit_progress(
                    progress_callback,
                    phase="rolling-back",
                    total=rollback_total,
                    completed=restored,
                    enable=0,
                    disable=0,
                    status="rolling-back",
                )
            progress.append(
                {
                    "event": "move-rolled-back",
                    "utc": _utc_now(),
                    "move": index,
                    "rolled_back": restored,
                }
            )
        progress.append(
            {
                "event": "manual-rollback-complete",
                "utc": _utc_now(),
                "restored": restored,
            },
            sync=True,
        )
        document["status"] = "rolled-back"
        document["rolled_back_count"] = restored
        document["already_at_source_count"] = states.count("source")
        document["rolled_back_utc"] = _utc_now()
        _write_json_atomic(manifest_path, document)
        _emit_progress(
            progress_callback,
            phase="final",
            total=rollback_total,
            completed=restored,
            enable=0,
            disable=0,
            status="rolled-back",
        )
    except BaseException as exc:
        document["status"] = "rollback-failed"
        document["rollback_error"] = f"{type(exc).__name__}: {exc}"
        persistence_errors: list[str] = []
        try:
            progress.append(
                {
                    "event": "manual-rollback-error",
                    "utc": _utc_now(),
                    "restored": restored,
                    "error": document["rollback_error"],
                },
                sync=True,
            )
        except Exception as journal_exc:
            persistence_errors.append(
                "rollback progress journal: "
                f"{type(journal_exc).__name__}: {journal_exc}"
            )
        if persistence_errors:
            document["rollback_persistence_errors"] = persistence_errors
        try:
            _write_json_atomic(manifest_path, document)
        except Exception as journal_exc:
            persistence_errors.append(
                "rollback canonical manifest: "
                f"{type(journal_exc).__name__}: {journal_exc}"
            )
        if persistence_errors and hasattr(exc, "add_note"):
            exc.add_note("; ".join(persistence_errors))
        _emit_progress(
            progress_callback,
            phase="error",
            total=rollback_total,
            completed=restored,
            enable=0,
            disable=0,
            status="rollback-failed",
            error="; ".join(
                [str(document["rollback_error"]), *persistence_errors]
            ),
        )
        raise
    finally:
        primary_error_active = sys.exc_info()[0] is not None
        try:
            progress.close()
        except Exception:
            if not primary_error_active:
                raise
    return restored


def rollback_switch(
    manifest_path: Path,
    *,
    progress_callback: ProgressCallback | None = None,
) -> int:
    document, addon_dir, moves = _load_switch_manifest(manifest_path)
    if document.get("status") == "superseded":
        raise ValueError("refusing to roll back a superseded manager switch")
    if document["format"] == 1:
        return _rollback_format_1(
            manifest_path,
            document,
            addon_dir,
            moves,
            progress_callback,
        )
    return _rollback_format_2(
        manifest_path,
        document,
        addon_dir,
        moves,
        progress_callback,
    )

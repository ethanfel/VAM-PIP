from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterator
import uuid

from vampip.analysis import package_id
from vampip.models import DISABLED_SUFFIX
from vampip.profiles import preferred


_RUN_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


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


def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def manager_lock(state_dir: Path) -> Iterator[None]:
    """Serialize all manager operations that can rename archives."""

    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        state_dir.chmod(0o700)
    except OSError:
        pass
    lock_path = state_dir / "manager.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - the manager targets Linux
            fcntl = None
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
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


def apply_switch(
    state_dir: Path,
    addon_dir: Path,
    plan: SwitchPlan,
    *,
    run_name: str,
    allow_disable: bool,
    lock_held: bool = False,
) -> Path | None:
    """Apply a switch atomically per file and journal every rename.

    Enabling happens first. If a later operation fails, completed renames are
    immediately rolled back. This favours leaving extra packages visible over
    leaving a requested dependency unavailable.
    """

    if plan.to_disable and not allow_disable:
        raise ValueError("refusing to disable packages while VaM may be running")
    if not plan.to_enable and not plan.to_disable:
        return None

    addon_dir = addon_dir.resolve()
    moves: list[dict[str, object]] = []
    for action, selected_rows, enable in (
        ("enable", plan.to_enable, True),
        ("disable", plan.to_disable, False),
    ):
        for row in selected_rows:
            source = Path(row["path"]).resolve()
            if not source.is_relative_to(addon_dir):
                raise ValueError(f"package is outside AddonPackages: {source}")
            target = _destination(row, enable=enable)
            moves.append(
                {
                    "action": action,
                    "source": str(source),
                    "target": str(target),
                    "package_id": package_id(row),
                    "size": row["size"],
                    "device": row["device"],
                    "inode": row["inode"],
                    "mtime_ns": row["mtime_ns"],
                    "sha256": row["sha256"],
                    "status": "planned",
                }
            )

    for entry in moves:
        source = Path(str(entry["source"]))
        target = Path(str(entry["target"]))
        if not source.is_file():
            raise FileNotFoundError(f"managed package is missing: {source}")
        if target.exists():
            raise FileExistsError(f"package rename target already exists: {target}")
        stat = source.stat()
        expected_identity = (
            int(entry["device"]),
            int(entry["inode"]),
            int(entry["size"]),
            int(entry["mtime_ns"]),
        )
        current_identity = (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
        )
        if current_identity != expected_identity:
            raise ValueError(
                f"managed package changed since the inventory scan: {source}"
            )

    manifest_path = _manifest_path(state_dir, run_name)
    document: dict[str, object] = {
        "format": 1,
        "kind": "manager-switch",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "addon_dir": str(addon_dir),
        "desired_packages": list(plan.desired_ids),
        "status": "planned",
        "moves": moves,
    }
    _write_json_atomic(manifest_path, document)

    lock_context = nullcontext() if lock_held else manager_lock(state_dir)
    with lock_context:
        document["status"] = "applying"
        _write_json_atomic(manifest_path, document)
        completed: list[dict[str, object]] = []
        try:
            for entry in moves:
                os.replace(str(entry["source"]), str(entry["target"]))
                entry["status"] = "complete"
                completed.append(entry)
                _write_json_atomic(manifest_path, document)
        except BaseException as exc:
            document["status"] = "rolling-back"
            document["error"] = f"{type(exc).__name__}: {exc}"
            _write_json_atomic(manifest_path, document)
            rollback_errors: list[str] = []
            for entry in reversed(completed):
                current = Path(str(entry["target"]))
                original = Path(str(entry["source"]))
                try:
                    if original.exists():
                        raise FileExistsError(
                            f"automatic rollback target exists: {original}"
                        )
                    os.replace(current, original)
                    entry["status"] = "rolled-back"
                except OSError as rollback_exc:
                    entry["status"] = "rollback-failed"
                    rollback_errors.append(str(rollback_exc))
                _write_json_atomic(manifest_path, document)
            document["status"] = "rollback-failed" if rollback_errors else "rolled-back"
            if rollback_errors:
                document["rollback_errors"] = rollback_errors
            _write_json_atomic(manifest_path, document)
            raise

        document["status"] = "complete"
        document["completed_utc"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(manifest_path, document)
    return manifest_path


def rollback_switch(manifest_path: Path) -> int:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        document.get("format") != 1
        or document.get("kind") != "manager-switch"
        or not isinstance(document.get("moves"), list)
    ):
        raise ValueError("unsupported manager switch manifest")

    addon_value = document.get("addon_dir")
    if not isinstance(addon_value, str):
        raise ValueError("manager switch manifest has no AddonPackages root")
    addon_dir = Path(addon_value).resolve()

    restored = 0
    for entry in reversed(document["moves"]):
        if entry.get("status") != "complete":
            continue
        current = Path(str(entry["target"]))
        original = Path(str(entry["source"]))
        action = entry.get("action")
        if action == "enable":
            if not str(original).casefold().endswith(DISABLED_SUFFIX):
                raise ValueError("manager switch manifest has an invalid enable path")
            expected = Path(str(original)[: -len(DISABLED_SUFFIX)])
        elif action == "disable":
            expected = Path(f"{original}{DISABLED_SUFFIX}")
        else:
            raise ValueError("manager switch manifest has an invalid action")
        if expected != current:
            raise ValueError("manager switch manifest contains mismatched paths")
        original_parent = original.parent.resolve()
        current_parent = current.parent.resolve()
        if not original_parent.is_relative_to(
            addon_dir
        ) or not current_parent.is_relative_to(addon_dir):
            raise ValueError("manager switch manifest path escapes AddonPackages")
        if original.exists():
            raise FileExistsError(f"rollback target already exists: {original}")
        if not current.is_file():
            raise FileNotFoundError(f"managed package is missing: {current}")
        stat = current.stat()
        for field, actual in (
            ("device", stat.st_dev),
            ("inode", stat.st_ino),
            ("size", stat.st_size),
            ("mtime_ns", stat.st_mtime_ns),
        ):
            expected = entry.get(field)
            if expected is not None and int(expected) != actual:
                raise ValueError(f"managed package changed since the switch: {current}")
        os.replace(current, original)
        entry["status"] = "rolled-back"
        restored += 1
        _write_json_atomic(manifest_path, document)
    document["status"] = "rolled-back"
    document["rolled_back_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json_atomic(manifest_path, document)
    return restored

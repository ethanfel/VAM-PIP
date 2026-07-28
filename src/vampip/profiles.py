from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from vampip.analysis import family_id, package_id
from vampip.models import DISABLED_SUFFIX, parse_dependency_ref


_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class Resolution:
    selected: tuple[sqlite3.Row, ...]
    missing: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ActivationPlan:
    profile_name: str
    selected_ids: tuple[str, ...]
    to_enable: tuple[sqlite3.Row, ...]
    to_disable: tuple[sqlite3.Row, ...]

    @property
    def active_after(self) -> int:
        return len(self.selected_ids)


def _logical_relative(row: sqlite3.Row) -> str:
    value = row["relative_path"]
    if value.casefold().endswith(DISABLED_SUFFIX):
        return value[: -len(DISABLED_SUFFIX)]
    return value


def _preferred_key(row: sqlite3.Row) -> tuple[int, int, int, int, str]:
    relative = Path(_logical_relative(row))
    return (
        len(relative.parts),
        0 if relative.name == row["canonical_filename"] else 1,
        0 if row["enabled"] else 1,
        len(str(relative)),
        str(relative).casefold(),
    )


def preferred(rows: list[sqlite3.Row]) -> sqlite3.Row:
    return min(rows, key=_preferred_key)


def _choose_latest(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    if not rows:
        return None
    numeric = [row for row in rows if row["version"] is not None]
    if numeric:
        highest = max(row["version"] for row in numeric)
        return preferred([row for row in numeric if row["version"] == highest])
    return preferred(rows)


def resolve(roots: list[str], rows: list[sqlite3.Row]) -> Resolution:
    valid = [row for row in rows if row["valid"] and row["version_text"]]
    by_full: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_family: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in valid:
        by_full[package_id(row).casefold()].append(row)
        by_family[family_id(row).casefold()].append(row)

    def choose(reference: str) -> sqlite3.Row | None:
        key = reference.casefold()
        if key in by_full:
            return preferred(by_full[key])
        dependency = parse_dependency_ref(reference)
        if dependency is not None:
            if dependency.is_latest:
                return _choose_latest(by_family.get(dependency.family_key, []))
            return None
        return _choose_latest(by_family.get(key, []))

    pending: deque[tuple[str, str]] = deque(("<root>", root) for root in roots)
    selected: dict[str, sqlite3.Row] = {}
    missing: set[tuple[str, str]] = set()
    while pending:
        owner, reference = pending.popleft()
        row = choose(reference)
        if row is None:
            missing.add((owner, reference))
            continue
        key = package_id(row).casefold()
        if key in selected:
            continue
        selected[key] = row
        try:
            dependencies = json.loads(row["dependencies_json"])
        except json.JSONDecodeError:
            dependencies = []
        for dependency in dependencies:
            pending.append((package_id(row), dependency))

    selected_rows = tuple(
        sorted(selected.values(), key=lambda row: package_id(row).casefold())
    )
    return Resolution(
        selected=selected_rows,
        missing=tuple(
            sorted(missing, key=lambda item: (item[0].casefold(), item[1].casefold()))
        ),
    )


def profile_path(state_dir: Path, name: str) -> Path:
    if not _PROFILE_NAME.fullmatch(name):
        raise ValueError(
            "profile name may contain only letters, numbers, dot, underscore, and dash"
        )
    return state_dir / "profiles" / f"{name}.json"


def save_profile(
    state_dir: Path, name: str, roots: list[str], resolution: Resolution
) -> Path:
    path = profile_path(state_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": 1,
        "name": name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "roots": roots,
        "packages": [package_id(row) for row in resolution.selected],
        "missing": [
            {"required_by": owner, "reference": reference}
            for owner, reference in resolution.missing
        ],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_profile(state_dir: Path, name: str) -> dict[str, object]:
    path = profile_path(state_dir, name)
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("format") != 1
        or not isinstance(document.get("packages"), list)
        or not isinstance(document.get("roots"), list)
    ):
        raise ValueError(f"unsupported or corrupt profile: {path}")
    return document


def list_profiles(state_dir: Path) -> list[dict[str, object]]:
    directory = state_dir / "profiles"
    if not directory.is_dir():
        return []
    result = []
    for path in sorted(directory.glob("*.json")):
        try:
            result.append(load_profile(state_dir, path.stem))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return result


def activation_plan(
    name: str, package_ids: list[str], rows: list[sqlite3.Row]
) -> ActivationPlan:
    by_full: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if row["valid"] and row["version_text"]:
            by_full[package_id(row).casefold()].append(row)

    desired_paths: set[str] = set()
    missing: list[str] = []
    for identity in package_ids:
        candidates = by_full.get(identity.casefold(), [])
        if not candidates:
            missing.append(identity)
            continue
        desired_paths.add(preferred(candidates)["path"])
    if missing:
        raise ValueError(
            "profile packages are no longer present: " + ", ".join(missing[:10])
        )

    to_enable = []
    to_disable = []
    for row in rows:
        should_enable = row["path"] in desired_paths
        if should_enable and not row["enabled"]:
            to_enable.append(row)
        elif not should_enable and row["enabled"]:
            to_disable.append(row)
    return ActivationPlan(
        profile_name=name,
        selected_ids=tuple(package_ids),
        to_enable=tuple(sorted(to_enable, key=lambda row: row["relative_path"])),
        to_disable=tuple(sorted(to_disable, key=lambda row: row["relative_path"])),
    )


def _destination(row: sqlite3.Row, *, enable: bool) -> Path:
    source = Path(row["path"])
    if enable:
        source_text = str(source)
        if not source_text.casefold().endswith(DISABLED_SUFFIX):
            raise ValueError(f"not a disabled package: {source}")
        return Path(source_text[: -len(DISABLED_SUFFIX)])
    return Path(f"{source}{DISABLED_SUFFIX}")


def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def apply_activation(state_dir: Path, addon_dir: Path, plan: ActivationPlan) -> Path:
    addon_dir = addon_dir.resolve()
    moves: list[dict[str, object]] = []
    for action, rows, enable in (
        ("disable", plan.to_disable, False),
        ("enable", plan.to_enable, True),
    ):
        for row in rows:
            source = Path(row["path"]).resolve()
            if not source.is_relative_to(addon_dir):
                raise ValueError(f"package is outside AddonPackages: {source}")
            target = _destination(row, enable=enable)
            moves.append(
                {
                    "action": action,
                    "source": str(source),
                    "target": str(target),
                    "package_id": package_id(row) if row["valid"] else row["basename"],
                    "status": "planned",
                }
            )

    for entry in moves:
        target = Path(str(entry["target"]))
        if target.exists():
            raise FileExistsError(
                f"profile rename target already exists: {target}; "
                "run duplicate cleanup first"
            )

    run_dir = state_dir / "profile-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_path = run_dir / f"{timestamp}-{plan.profile_name}.json"
    if manifest_path.exists():
        manifest_path = run_dir / (
            f"{timestamp}-{plan.profile_name}-{uuid.uuid4().hex[:8]}.json"
        )
    document: dict[str, object] = {
        "format": 1,
        "kind": "profile-activation",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "profile": plan.profile_name,
        "addon_dir": str(addon_dir),
        "moves": moves,
    }
    _write_json_atomic(manifest_path, document)

    # Disable first so selected enables cannot leave unrelated packages exposed
    # if the process is interrupted.
    for entry in moves:
        source = Path(str(entry["source"]))
        target = Path(str(entry["target"]))
        os.replace(source, target)
        entry["status"] = "complete"
        _write_json_atomic(manifest_path, document)
    return manifest_path


def rollback_activation(manifest_path: Path) -> int:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        document.get("format") != 1
        or document.get("kind") != "profile-activation"
        or not isinstance(document.get("moves"), list)
    ):
        raise ValueError("unsupported profile activation manifest")
    addon_value = document.get("addon_dir")
    if not isinstance(addon_value, str):
        raise ValueError("profile activation manifest has no AddonPackages root")
    addon_dir = Path(addon_value).resolve()
    restored = 0
    for entry in reversed(document["moves"]):
        if entry.get("status") != "complete":
            continue
        current = Path(entry["target"])
        original = Path(entry["source"])
        action = entry.get("action")
        if action == "enable":
            if not str(original).casefold().endswith(DISABLED_SUFFIX):
                raise ValueError("profile manifest has an invalid enable path")
            expected = Path(str(original)[: -len(DISABLED_SUFFIX)])
        elif action == "disable":
            expected = Path(f"{original}{DISABLED_SUFFIX}")
        else:
            raise ValueError("profile manifest has an invalid action")
        if current != expected:
            raise ValueError("profile manifest contains mismatched paths")
        if not original.parent.resolve().is_relative_to(
            addon_dir
        ) or not current.parent.resolve().is_relative_to(addon_dir):
            raise ValueError("profile manifest path escapes AddonPackages")
        if original.exists():
            raise FileExistsError(f"rollback target already exists: {original}")
        if not current.exists():
            raise FileNotFoundError(f"profile-managed file is missing: {current}")
        os.replace(current, original)
        entry["status"] = "rolled-back"
        restored += 1
        _write_json_atomic(manifest_path, document)
    return restored

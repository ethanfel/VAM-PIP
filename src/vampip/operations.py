from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

from vampip.analysis import DuplicateGroup, family_id, package_id
from vampip.inventory import (
    archive_content_sha256,
    inspect_archive,
    is_archive_content_sha256,
)
from vampip.models import parse_dependency_ref, parse_var_filename


@dataclass(frozen=True)
class MoveCandidate:
    row: sqlite3.Row
    reason: str
    sha256: str | None


def candidates_from_duplicates(
    groups: list[DuplicateGroup],
) -> list[MoveCandidate]:
    return [
        MoveCandidate(
            row=row,
            reason=f"duplicate of {group.keeper['relative_path']}",
            sha256=group.sha256,
        )
        for group in groups
        for row in group.redundant
    ]


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def quarantine_candidates(
    addon_dir: Path,
    candidates: list[MoveCandidate],
    quarantine_base: Path,
) -> Path:
    addon_dir = addon_dir.resolve()
    quarantine_base = quarantine_base.resolve()
    if quarantine_base == addon_dir or quarantine_base.is_relative_to(addon_dir):
        raise ValueError("quarantine must be outside AddonPackages")

    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = quarantine_base / run_name
    if run_dir.exists():
        run_dir = quarantine_base / f"{run_name}-{uuid.uuid4().hex[:8]}"
    files_dir = run_dir / "files"
    files_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"

    entries: list[dict[str, object]] = []
    for candidate in candidates:
        source = Path(candidate.row["path"]).resolve()
        if not source.is_relative_to(addon_dir):
            raise ValueError(f"refusing path outside AddonPackages: {source}")
        relative = source.relative_to(addon_dir)
        target = files_dir / relative
        entries.append(
            {
                "source": str(source),
                "quarantined": str(target),
                "relative_path": str(relative),
                "size": candidate.row["size"],
                "sha256": candidate.sha256,
                "reason": candidate.reason,
                "status": "planned",
            }
        )

    manifest: dict[str, object] = {
        "format": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "addon_dir": str(addon_dir),
        "entries": entries,
    }
    _write_manifest(manifest_path, manifest)

    for entry in entries:
        source = Path(str(entry["source"]))
        target = Path(str(entry["quarantined"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"quarantine target already exists: {target}")
        shutil.move(str(source), str(target))
        entry["status"] = "quarantined"
        _write_manifest(manifest_path, manifest)

    return manifest_path


def restore_manifest(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not isinstance(manifest.get("entries"), list):
        raise ValueError("unsupported quarantine manifest")
    addon_value = manifest.get("addon_dir")
    if not isinstance(addon_value, str):
        raise ValueError("quarantine manifest has no AddonPackages root")
    addon_dir = Path(addon_value).resolve()
    files_dir = (manifest_path.resolve().parent / "files").resolve()

    restored = 0
    for entry in manifest["entries"]:
        if entry.get("status") != "quarantined":
            continue
        relative_value = entry.get("relative_path")
        if not isinstance(relative_value, str):
            raise ValueError("quarantine manifest entry has no relative path")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("quarantine manifest has an unsafe relative path")
        source = Path(str(entry["quarantined"]))
        target = Path(str(entry["source"]))
        expected_source = files_dir / relative
        expected_target = addon_dir / relative
        if source.resolve() != expected_source.resolve():
            raise ValueError("quarantine manifest source path was modified")
        if target.resolve() != expected_target.resolve():
            raise ValueError("quarantine manifest restore path was modified")
        if not target.parent.resolve().is_relative_to(addon_dir):
            raise ValueError("quarantine restore path escapes AddonPackages")
        if target.exists():
            raise FileExistsError(f"restore target already exists: {target}")
        if not source.is_file():
            raise FileNotFoundError(f"quarantined file is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        entry["status"] = "restored"
        restored += 1
        _write_manifest(manifest_path, manifest)
    return restored


def install_archive(
    source: Path,
    addon_dir: Path,
    rows: list[sqlite3.Row],
    *,
    hardlink: bool = False,
    dry_run: bool = False,
) -> tuple[str, Path | None]:
    source = source.resolve()
    addon_dir = addon_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    details = inspect_archive(source)
    if not details["valid"]:
        raise ValueError(f"{source.name}: {details['error']}")
    parsed = parse_var_filename(source)
    assert parsed is not None

    matching = [
        row
        for row in rows
        if row["valid"] and package_id(row).casefold() == parsed.full_key
    ]
    source_digest: str | None = None
    for row in matching:
        source_digest = source_digest or archive_content_sha256(source)
        existing_digest = (
            str(row["content_sha256"])
            if is_archive_content_sha256(row["content_sha256"])
            else archive_content_sha256(Path(row["path"]))
        )
        if source_digest == existing_digest:
            return "already installed", Path(row["path"])
    if matching:
        locations = ", ".join(row["relative_path"] for row in matching)
        raise ValueError(
            f"{parsed.full_id} is already installed with different content: {locations}"
        )

    destination = addon_dir / parsed.canonical_filename
    if destination.exists() and destination.resolve() != source:
        raise FileExistsError(destination)
    if destination.resolve() == source:
        return "already installed", destination
    if dry_run:
        return "would install", destination

    addon_dir.mkdir(parents=True, exist_ok=True)
    temporary = addon_dir / f".{destination.name}.{uuid.uuid4().hex}.partial"
    try:
        if hardlink:
            os.link(source, temporary)
        else:
            shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return "installed", destination


def select_packages(rows: list[sqlite3.Row], selector: str) -> list[sqlite3.Row]:
    selector_key = selector.casefold()
    exact = [
        row
        for row in rows
        if row["valid"] and package_id(row).casefold() == selector_key
    ]
    if exact:
        return exact
    return [
        row
        for row in rows
        if row["valid"] and family_id(row).casefold() == selector_key
    ]


def reverse_dependency_blockers(
    rows: list[sqlite3.Row], selected: list[sqlite3.Row]
) -> list[tuple[str, str]]:
    selected_paths = {row["path"] for row in selected}
    remaining = [row for row in rows if row["path"] not in selected_paths]
    families = {family_id(row).casefold() for row in remaining if row["valid"]}
    full_ids = {package_id(row).casefold() for row in remaining if row["valid"]}
    removed_families = {family_id(row).casefold() for row in selected}
    removed_full_ids = {package_id(row).casefold() for row in selected}
    blockers: set[tuple[str, str]] = set()

    for row in remaining:
        try:
            dependencies = json.loads(row["dependencies_json"])
        except json.JSONDecodeError:
            continue
        for value in dependencies:
            dependency = parse_dependency_ref(value)
            if dependency is None:
                continue
            if (
                dependency.is_latest
                and dependency.family_key in removed_families
                and dependency.family_key not in families
            ):
                blockers.add((package_id(row), value))
            elif (
                not dependency.is_latest
                and dependency.full_key in removed_full_ids
                and dependency.full_key not in full_ids
            ):
                blockers.add((package_id(row), value))
    return sorted(blockers)

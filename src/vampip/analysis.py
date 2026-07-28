from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from vampip.inventory import ensure_hashes, is_archive_content_sha256
from vampip.models import parse_dependency_ref


@dataclass(frozen=True)
class DuplicateGroup:
    package_id: str
    sha256: str
    keeper: sqlite3.Row
    redundant: tuple[sqlite3.Row, ...]

    @property
    def logical_bytes(self) -> int:
        return sum(row["size"] for row in self.redundant)

    @property
    def physical_bytes(self) -> int:
        keeper_inode = (self.keeper["device"], self.keeper["inode"])
        redundant_inodes = {
            (row["device"], row["inode"])
            for row in self.redundant
            if (row["device"], row["inode"]) != keeper_inode
        }
        sizes: dict[tuple[int, int], int] = {}
        for row in self.redundant:
            inode = (row["device"], row["inode"])
            if inode in redundant_inodes:
                sizes[inode] = row["size"]
        return sum(sizes.values())


@dataclass(frozen=True)
class VersionFamily:
    family: str
    versions: tuple[int, ...]
    file_count: int
    bytes: int
    exactly_pinned: tuple[int, ...]


def package_id(row: sqlite3.Row) -> str:
    return f"{row['creator']}.{row['package_name']}.{row['version_text']}"


def family_id(row: sqlite3.Row) -> str:
    return f"{row['creator']}.{row['package_name']}"


def duplicate_candidate_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    groups: dict[tuple[str, str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if not row["valid"] or not row["version_text"]:
            continue
        key = (
            family_id(row).casefold(),
            str(row["version_text"]).casefold(),
            row["size"],
        )
        groups[key].append(row)
    return [row for group in groups.values() if len(group) > 1 for row in group]


def _keeper_key(row: sqlite3.Row) -> tuple[int, int, int, int, str]:
    relative = Path(row["relative_path"])
    return (
        0 if row["enabled"] else 1,
        len(relative.parts),
        0 if row["basename"] == row["canonical_filename"] else 1,
        len(row["relative_path"]),
        row["relative_path"].casefold(),
    )


def verified_duplicate_groups(
    connection: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    calculate: bool = True,
) -> tuple[list[DuplicateGroup], int]:
    candidates = duplicate_candidate_rows(rows)
    calculated = ensure_hashes(connection, candidates) if calculate else 0
    if calculated:
        by_path = {
            row["path"]: row
            for row in connection.execute(
                "SELECT * FROM package_files WHERE root = ?",
                (rows[0]["root"],),
            )
        }
        rows = [by_path[row["path"]] for row in rows if row["path"] in by_path]

    digest_groups: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if not row["valid"] or not row["version_text"] or not row["sha256"]:
            continue
        key = (
            family_id(row).casefold(),
            str(row["version_text"]).casefold(),
            row["sha256"],
        )
        digest_groups[key].append(row)

    result: list[DuplicateGroup] = []
    for group in digest_groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_keeper_key)
        result.append(
            DuplicateGroup(
                package_id=package_id(ordered[0]),
                sha256=ordered[0]["sha256"],
                keeper=ordered[0],
                redundant=tuple(ordered[1:]),
            )
        )
    result.sort(key=lambda group: (-group.physical_bytes, group.package_id.casefold()))
    return result, calculated


def identity_conflicts(rows: list[sqlite3.Row]) -> list[tuple[str, list[sqlite3.Row]]]:
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if row["valid"] and row["version_text"]:
            groups[package_id(row).casefold()].append(row)

    conflicts = []
    for group in groups.values():
        content_hashes = [
            str(row["content_sha256"] or "")
            for row in group
            if is_archive_content_sha256(row["content_sha256"])
        ]
        if len(content_hashes) == len(group):
            if len(set(content_hashes)) > 1:
                conflicts.append((package_id(group[0]), group))
            continue
        sizes = {row["size"] for row in group}
        known_hashes = {row["sha256"] for row in group if row["sha256"]}
        if len(sizes) > 1 or len(known_hashes) > 1:
            conflicts.append((package_id(group[0]), group))
    conflicts.sort(key=lambda item: item[0].casefold())
    return conflicts


def version_families(rows: list[sqlite3.Row]) -> list[VersionFamily]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    display: dict[str, str] = {}
    pinned: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if not row["valid"]:
            continue
        key = family_id(row).casefold()
        grouped[key].append(row)
        display.setdefault(key, family_id(row))
        try:
            dependencies = json.loads(row["dependencies_json"])
        except json.JSONDecodeError:
            dependencies = []
        for value in dependencies:
            dependency = parse_dependency_ref(value)
            if dependency and dependency.version is not None:
                pinned[dependency.family_key].add(dependency.version)

    result = []
    for key, group in grouped.items():
        versions = sorted(
            {row["version"] for row in group if row["version"] is not None}
        )
        if len(versions) < 2:
            continue
        result.append(
            VersionFamily(
                family=display[key],
                versions=tuple(versions),
                file_count=len(group),
                bytes=sum(row["size"] for row in group),
                exactly_pinned=tuple(sorted(pinned.get(key, set()))),
            )
        )
    result.sort(key=lambda item: (-len(item.versions), item.family.casefold()))
    return result


def missing_dependencies(
    rows: list[sqlite3.Row],
) -> list[tuple[str, str]]:
    families = {
        family_id(row).casefold()
        for row in rows
        if row["valid"] and row["version_text"]
    }
    full_ids = {
        package_id(row).casefold()
        for row in rows
        if row["valid"] and row["version_text"]
    }
    missing: set[tuple[str, str]] = set()
    for row in rows:
        if not row["valid"]:
            continue
        try:
            dependencies = json.loads(row["dependencies_json"])
        except json.JSONDecodeError:
            continue
        for value in dependencies:
            dependency = parse_dependency_ref(value)
            if dependency is None:
                continue
            available = (
                dependency.family_key in families
                if dependency.is_latest
                else dependency.full_key in full_ids
            )
            if not available:
                missing.add((package_id(row), value))
    return sorted(missing, key=lambda item: (item[0].casefold(), item[1].casefold()))

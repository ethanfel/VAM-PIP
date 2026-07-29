from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import re
import sqlite3
from typing import BinaryIO, Mapping
import zipfile

from vampip.analysis import family_id, package_id
from vampip.catalog import resolve_resource_archive
from vampip.inventory import is_archive_content_sha256
from vampip.models import parse_dependency_ref
from vampip.profiles import preferred


_REFERENCE_END = re.compile(rb"\.(?:[0-9]+|latest):[/\\]", re.IGNORECASE)
_TEXT_EXTENSIONS = {
    ".cfg",
    ".cs",
    ".cslist",
    ".json",
    ".prefs",
    ".txt",
    ".vaj",
    ".vap",
    ".xml",
}
_CHUNK_SIZE = 1024 * 1024
_REFERENCE_WINDOW = 2048
MAX_RESOURCE_TEXT_BYTES = 256 * 1024 * 1024


def scan_package_references(
    handle: BinaryIO,
    *,
    maximum_bytes: int = MAX_RESOURCE_TEXT_BYTES,
) -> set[str]:
    found: dict[str, str] = {}
    overlap = b""
    total = 0
    while True:
        chunk = handle.read(min(_CHUNK_SIZE, maximum_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_bytes:
            raise ValueError(
                f"resource text exceeds the {maximum_bytes // (1024 * 1024)} MiB "
                "reference-scan safety limit"
            )
        data = overlap + chunk
        for match in _REFERENCE_END.finditer(data):
            identity_end = match.end() - 2
            window_start = max(0, match.start() - _REFERENCE_WINDOW)
            quote = max(
                data.rfind(b'"', window_start, match.start()),
                data.rfind(b"'", window_start, match.start()),
            )
            if quote < 0:
                continue
            identity = data[quote + 1 : identity_end].decode("utf-8", errors="ignore")
            parsed = parse_dependency_ref(identity)
            if parsed is not None:
                found.setdefault(parsed.full_key, parsed.full_id)
        overlap = data[-_REFERENCE_WINDOW:]
    return set(found.values())


def resource_package_roots(
    connection: sqlite3.Connection,
    vam_root: Path,
    resource_id: int,
    *,
    addon_root: Path,
    version_text: str | None = None,
    package_choices: Mapping[str, object] | None = None,
) -> list[str]:
    location = resolve_resource_archive(
        connection,
        vam_root,
        resource_id,
        addon_root=addon_root,
        version_text=version_text,
        package_choices=package_choices,
    )
    if location is None:
        raise ValueError("resource is missing from its installed package")

    roots: dict[str, str] = {}
    if location.package_ref:
        roots[location.package_ref.casefold()] = location.package_ref

    suffix = Path(location.resource_path.replace("\\", "/")).suffix.casefold()
    if suffix not in _TEXT_EXTENSIONS:
        return sorted(roots.values(), key=str.casefold)

    if location.local_path is not None:
        with location.local_path.open("rb") as handle:
            references = scan_package_references(handle)
    else:
        assert location.archive_path is not None
        assert location.archive_member is not None
        try:
            with zipfile.ZipFile(location.archive_path) as archive:
                info = archive.getinfo(location.archive_member)
                if info.file_size > MAX_RESOURCE_TEXT_BYTES:
                    raise ValueError(
                        "resource is too large to scan safely for package references"
                    )
                with archive.open(info) as handle:
                    references = scan_package_references(handle)
        except (KeyError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise ValueError(f"could not scan resource references: {exc}") from exc

    for reference in references:
        roots.setdefault(reference.casefold(), reference)
    return sorted(roots.values(), key=str.casefold)


def package_dependency_graph(
    roots: list[str],
    rows: list[sqlite3.Row],
    *,
    package_choices: Mapping[str, object] | None = None,
    max_nodes: int = 2048,
    max_edges: int = 4096,
) -> dict[str, object]:
    """Build a bounded package dependency graph for a catalogue resource.

    The roots are references detected directly in the resource. Package
    metadata then supplies transitive edges. A same-ID group with different
    logical contents is deliberately marked as a conflict. Until the user has
    selected a content digest, dependencies from every variant are followed so
    the catalogue does not hide a branch merely because path ordering happened
    to choose another physical archive.
    """

    if max_nodes < 1 or max_edges < 1:
        raise ValueError("dependency graph limits must be positive")

    choices = package_choices or {}
    valid = [row for row in rows if row["valid"] and row["version_text"]]
    by_full: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_family: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in valid:
        by_full[package_id(row).casefold()].append(row)
        by_family[family_id(row).casefold()].append(row)

    def exact_group(reference: str) -> list[sqlite3.Row]:
        key = reference.casefold()
        if key in by_full:
            return by_full[key]
        dependency = parse_dependency_ref(reference)
        family_key = dependency.family_key if dependency is not None else key
        family_rows = by_family.get(family_key, [])
        if dependency is not None and not dependency.is_latest:
            return []
        numeric = [row for row in family_rows if row["version"] is not None]
        if numeric:
            newest = max(int(row["version"]) for row in numeric)
            return [row for row in numeric if int(row["version"]) == newest]
        if not family_rows:
            return []
        selected = preferred(family_rows)
        selected_id = package_id(selected).casefold()
        return [row for row in family_rows if package_id(row).casefold() == selected_id]

    root_keys = {root.casefold() for root in roots}
    pending: deque[tuple[str, str, bool]] = deque(
        ("<resource>", root, True) for root in roots
    )
    entries: dict[tuple[str, str], dict[str, object]] = {}
    expanded: set[str] = set()
    conflict_ids: dict[str, str] = {}
    ambiguous_ids: dict[str, str] = {}
    edge_count = 0
    truncated = False

    while pending:
        if len(entries) >= max_nodes or edge_count >= max_edges:
            truncated = True
            break
        owner, reference, direct = pending.popleft()
        edge_count += 1
        group = exact_group(reference)
        if not group:
            key = (reference.casefold(), "")
            entry = entries.setdefault(
                key,
                {
                    "requested": reference,
                    "resolved_id": None,
                    "state": "missing",
                    "active": False,
                    "direct": direct or reference.casefold() in root_keys,
                    "conflict": False,
                    "choice_stale": False,
                    "required_by": [],
                },
            )
            required_by = entry["required_by"]
            assert isinstance(required_by, list)
            if owner not in required_by:
                required_by.append(owner)
            if direct:
                entry["direct"] = True
            continue

        identity = package_id(group[0])
        identity_key = identity.casefold()
        hashed_signatures = [
            str(row["content_sha256"])
            for row in group
            if is_archive_content_sha256(row["content_sha256"])
        ]
        signatures = set(hashed_signatures)
        fully_hashed = len(hashed_signatures) == len(group)
        conflicting = len(group) > 1 and (not fully_hashed or len(signatures) > 1)
        if len(group) > 1 and not fully_hashed:
            ambiguous_ids.setdefault(identity_key, identity)
        if conflicting:
            conflict_ids.setdefault(identity_key, identity)

        choice = choices.get(identity_key)
        choice_stale = False
        try:
            selected = preferred(group, choice)
        except ValueError:
            # A stale digest must fail closed for actual loading. The details
            # view still follows every physical variant so the user can repair
            # the choice from the conflict panel.
            selected = preferred(group)
            choice_stale = True
            conflict_ids.setdefault(identity_key, identity)

        entry_key = (reference.casefold(), identity_key)
        state = "conflict" if conflicting and choice is None else (
            "active" if bool(selected["enabled"]) else "hidden"
        )
        if choice_stale:
            state = "choice-stale"
        entry = entries.setdefault(
            entry_key,
            {
                "requested": reference,
                "resolved_id": identity,
                "state": state,
                "active": bool(selected["enabled"]),
                "direct": direct or reference.casefold() in root_keys,
                "conflict": conflicting,
                "choice_stale": choice_stale,
                "required_by": [],
            },
        )
        required_by = entry["required_by"]
        assert isinstance(required_by, list)
        if owner not in required_by:
            required_by.append(owner)
        if direct:
            entry["direct"] = True
        if identity_key in expanded:
            continue
        expanded.add(identity_key)

        traversal_rows: list[sqlite3.Row]
        if conflicting and choice is None:
            # Follow one row per logical digest, plus every unhashed row until
            # the caller hydrates hashes and rebuilds the graph.
            traversal_rows = []
            seen_signatures: set[str] = set()
            for row in group:
                signature = str(row["content_sha256"] or f"path:{row['path']}")
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                traversal_rows.append(row)
        elif choice_stale:
            traversal_rows = list(group)
        else:
            traversal_rows = [selected]

        seen_dependencies: set[str] = set()
        for package_row in traversal_rows:
            try:
                dependencies = json.loads(package_row["dependencies_json"])
            except (TypeError, json.JSONDecodeError):
                dependencies = []
            if not isinstance(dependencies, list):
                continue
            for dependency in dependencies:
                if not isinstance(dependency, str):
                    continue
                normalized = dependency.strip()
                if (
                    not normalized
                    or normalized.casefold() in seen_dependencies
                    or parse_dependency_ref(normalized) is None
                ):
                    continue
                seen_dependencies.add(normalized.casefold())
                pending.append((identity, normalized, False))

    dependencies = list(entries.values())
    for entry in dependencies:
        required_by = entry.get("required_by")
        if isinstance(required_by, list):
            required_by.sort(key=str.casefold)
    dependencies.sort(
        key=lambda entry: (
            0 if bool(entry["direct"]) else 1,
            0 if str(entry["state"]) in {"missing", "conflict", "choice-stale"} else 1,
            str(entry["resolved_id"] or entry["requested"]).casefold(),
            str(entry["requested"]).casefold(),
        )
    )
    direct_count = sum(bool(entry["direct"]) for entry in dependencies)
    missing_count = sum(entry["state"] == "missing" for entry in dependencies)
    return {
        "dependencies": dependencies,
        "counts": {
            "total": len(dependencies),
            "direct": direct_count,
            "transitive": len(dependencies) - direct_count,
            "missing": missing_count,
            "conflicts": len(conflict_ids),
        },
        "conflict_ids": sorted(conflict_ids.values(), key=str.casefold),
        "ambiguous_ids": sorted(ambiguous_ids.values(), key=str.casefold),
        "truncated": truncated,
        "edge_count": edge_count,
    }

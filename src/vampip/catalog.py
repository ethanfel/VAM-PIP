from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
from typing import Any, Iterable
import uuid
import zipfile


BROWSERASSIST_SOURCE = "browserassist"
_SUPPORTED_STORE_FORMAT = 3
_MAX_MANIFEST_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_THUMBNAIL_BYTES = 16 * 1024 * 1024

_REQUIRED_RESOURCE_COLUMNS = {
    "id",
    "root",
    "source",
    "resource_key",
    "creator",
    "package_name",
    "versions_json",
    "resource_path",
    "resource_type",
    "atom_type",
    "favorite",
    "hidden",
    "tags_json",
    "imported_utc",
}
_REQUIRED_SOURCE_COLUMNS = {
    "root",
    "source",
    "source_path",
    "imported_utc",
    "resource_count",
}
_REQUIRED_VERSION_COLUMNS = {
    "resource_id",
    "version_text",
}


class CatalogImportError(ValueError):
    """Raised when a catalogue snapshot cannot be imported safely."""


class CatalogSchemaError(RuntimeError):
    """Raised when the connected database lacks the v0.2 catalogue schema."""


@dataclass(frozen=True)
class CatalogImportResult:
    source: str
    source_path: Path
    imported_utc: str
    resource_count: int
    packaged_count: int
    local_count: int
    unmatched_user_rows: int
    preserved_hidden_count: int


@dataclass(frozen=True)
class ResourceLocation:
    resource_id: int
    resource_path: str
    creator: str
    package_name: str
    version_text: str | None
    package_ref: str | None
    enabled: bool
    archive_path: Path | None
    archive_member: str | None
    local_path: Path | None

    @property
    def packaged(self) -> bool:
        return self.archive_path is not None


@dataclass(frozen=True)
class ThumbnailResult:
    path: Path
    content_type: str
    size: int
    etag: str
    cache_hit: bool
    version_text: str | None


@dataclass(frozen=True)
class _CatalogRecord:
    resource_key: str
    creator: str
    package_name: str
    versions: tuple[str, ...]
    resource_path: str
    resource_type: str
    atom_type: str
    favorite: bool
    hidden: bool
    tags: tuple[dict[str, str], ...]


def _root_text(root: Path | str) -> str:
    return str(Path(root).expanduser().resolve())


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _check_schema(connection: sqlite3.Connection) -> None:
    resource_columns = _table_columns(connection, "catalog_resources")
    source_columns = _table_columns(connection, "catalog_sources")
    version_columns = _table_columns(connection, "catalog_resource_versions")
    missing_resources = _REQUIRED_RESOURCE_COLUMNS - resource_columns
    missing_sources = _REQUIRED_SOURCE_COLUMNS - source_columns
    missing_versions = _REQUIRED_VERSION_COLUMNS - version_columns
    if missing_resources or missing_sources or missing_versions:
        details = []
        if missing_resources:
            details.append(
                "catalog_resources missing " + ", ".join(sorted(missing_resources))
            )
        if missing_sources:
            details.append(
                "catalog_sources missing " + ", ".join(sorted(missing_sources))
            )
        if missing_versions:
            details.append(
                "catalog_resource_versions missing "
                + ", ".join(sorted(missing_versions))
            )
        raise CatalogSchemaError("; ".join(details))


def _stable_file_bytes(path: Path) -> bytes:
    before = path.stat()
    if before.st_size > _MAX_MANIFEST_BYTES:
        raise CatalogImportError(
            f"BrowserAssist data file is unexpectedly large: {path}"
        )
    payload = path.read_bytes()
    after = path.stat()
    before_key = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_key = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_key != after_key or len(payload) != before.st_size:
        raise CatalogImportError(
            f"BrowserAssist data changed while it was being read: {path}"
        )
    return payload


def _json_document(path: Path) -> dict[str, Any]:
    try:
        payload = _stable_file_bytes(path)
        value = json.loads(payload.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogImportError(
            f"could not read BrowserAssist data {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CatalogImportError(f"BrowserAssist data is not a JSON object: {path}")
    return value


def _intish(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _boolish(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        folded = value.strip().casefold()
        if folded in {"1", "true", "yes", "on", "active"}:
            return True
        if folded in {
            "",
            "0",
            "false",
            "no",
            "off",
            "inactive",
            "indeterminate",
        }:
            return False
    return default


def _require_format(document: dict[str, Any], key: str, path: Path) -> None:
    actual = _intish(document.get(key))
    if actual != _SUPPORTED_STORE_FORMAT:
        raise CatalogImportError(
            f"unsupported {key} in {path}: "
            f"expected {_SUPPORTED_STORE_FORMAT}, got {document.get(key)!r}"
        )


def _require_rows(
    document: dict[str, Any], key: str, path: Path
) -> list[dict[str, Any]]:
    rows = document.get(key)
    if not isinstance(rows, list):
        raise CatalogImportError(f"{path} has no {key!r} array")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CatalogImportError(f"{path} {key}[{index}] is not a JSON object")
        result.append(row)
    return result


def _required_text(row: dict[str, Any], key: str, *, path: Path, index: int) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise CatalogImportError(f"{path} resources[{index}] has invalid {key!r}")
    return value


def _normalize_versions(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    versions: dict[str, None] = {}
    for item in value:
        if isinstance(item, bool) or isinstance(item, (dict, list)):
            continue
        text = str(item).strip()
        if text:
            versions.setdefault(text, None)

    def key(version: str) -> tuple[int, int | str]:
        try:
            return (0, int(version))
        except ValueError:
            return (1, version.casefold())

    return tuple(sorted(versions, key=key))


def _normalize_tags(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("tagName")
        category = item.get("tagCategory", "")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(category, str):
            category = str(category)
        identity = (name, category)
        if identity in seen:
            continue
        seen.add(identity)
        result.append({"tagName": name, "tagCategory": category})
    return tuple(result)


def _logical_key(creator: str, package_name: str, path: str) -> str:
    return json.dumps(
        [creator, package_name, path],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _snapshot_paths(source_path: Path) -> dict[str, tuple[Path, ...]]:
    groups = {
        "core": tuple(
            sorted(
                (source_path / "VARResourcesCoreData").glob("*.manifest"),
                key=lambda path: str(path).casefold(),
            )
        ),
        "user": tuple(
            sorted(
                (source_path / "VARResourcesUserData").glob("*.userData"),
                key=lambda path: str(path).casefold(),
            )
        ),
        "local": tuple(
            sorted(
                (source_path / "LocalResourcesUserData").glob("*.userData"),
                key=lambda path: str(path).casefold(),
            )
        ),
    }
    if not groups["core"]:
        raise CatalogImportError(
            "BrowserAssist core catalogue was not found under "
            f"{source_path / 'VARResourcesCoreData'}"
        )
    return groups


def _path_fingerprint(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _load_snapshot(
    source_path: Path,
) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    paths = _snapshot_paths(source_path)
    try:
        before = {
            path: _path_fingerprint(path) for group in paths.values() for path in group
        }
    except OSError as exc:
        raise CatalogImportError(
            f"could not stat BrowserAssist catalogue: {exc}"
        ) from exc

    documents = {
        group: [(path, _json_document(path)) for path in group_paths]
        for group, group_paths in paths.items()
    }

    try:
        after_paths = _snapshot_paths(source_path)
        after = {
            path: _path_fingerprint(path)
            for group in after_paths.values()
            for path in group
        }
    except OSError as exc:
        raise CatalogImportError(
            f"BrowserAssist catalogue changed during import: {exc}"
        ) from exc
    if paths != after_paths or before != after:
        raise CatalogImportError(
            "BrowserAssist catalogue changed during import; retry after it is idle"
        )
    return documents


def _user_resource_map(
    documents: Iterable[tuple[Path, dict[str, Any]]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path, document in documents:
        _require_format(document, "VARUserDataStoreFormat", path)
        for index, row in enumerate(_require_rows(document, "resources", path)):
            creator = _required_text(row, "creatorName", path=path, index=index)
            package_name = _required_text(row, "packageName", path=path, index=index)
            resource_path = _required_text(
                row, "resourceFullFileName", path=path, index=index
            )
            key = creator, package_name, resource_path
            if key in result:
                raise CatalogImportError(
                    f"duplicate BrowserAssist user-data resource key: {key!r}"
                )
            result[key] = row
    return result


def _packaged_records(
    core_documents: Iterable[tuple[Path, dict[str, Any]]],
    user_rows: dict[tuple[str, str, str], dict[str, Any]],
) -> tuple[list[_CatalogRecord], set[tuple[str, str, str]]]:
    records: list[_CatalogRecord] = []
    seen: set[tuple[str, str, str]] = set()
    matched_user: set[tuple[str, str, str]] = set()
    for path, document in core_documents:
        _require_format(document, "VARManifestStoreFormat", path)
        for index, row in enumerate(_require_rows(document, "resources", path)):
            creator = _required_text(row, "creatorName", path=path, index=index)
            package_name = _required_text(row, "packageName", path=path, index=index)
            resource_path = _required_text(
                row, "resourceFullFileName", path=path, index=index
            )
            resource_type = _required_text(row, "resourceType", path=path, index=index)
            atom_type_value = row.get("presetAtomType", "")
            atom_type = (
                atom_type_value
                if isinstance(atom_type_value, str)
                else str(atom_type_value)
            )
            key = creator, package_name, resource_path
            if key in seen:
                raise CatalogImportError(
                    f"duplicate BrowserAssist core resource key: {key!r}"
                )
            seen.add(key)
            user = user_rows.get(key, {})
            if user:
                matched_user.add(key)
            records.append(
                _CatalogRecord(
                    resource_key=_logical_key(*key),
                    creator=creator,
                    package_name=package_name,
                    versions=_normalize_versions(row.get("varVersions")),
                    resource_path=resource_path,
                    resource_type=resource_type,
                    atom_type=atom_type,
                    favorite=_boolish(user.get("baFavourite")),
                    hidden=_boolish(user.get("baHidden")),
                    tags=_normalize_tags(user.get("Tags")),
                )
            )
    return records, matched_user


def _local_records(
    documents: Iterable[tuple[Path, dict[str, Any]]],
) -> list[_CatalogRecord]:
    records: list[_CatalogRecord] = []
    seen: set[str] = set()
    for path, document in documents:
        _require_format(document, "LocalUserDataStoreFormat", path)
        for index, row in enumerate(_require_rows(document, "resources", path)):
            resource_path = _required_text(
                row, "resourceFullFileName", path=path, index=index
            )
            resource_type = _required_text(row, "resourceType", path=path, index=index)
            if resource_path in seen:
                raise CatalogImportError(
                    f"duplicate BrowserAssist local resource path: {resource_path!r}"
                )
            seen.add(resource_path)
            atom_type_value = row.get("presetAtomType", "")
            atom_type = (
                atom_type_value
                if isinstance(atom_type_value, str)
                else str(atom_type_value)
            )
            records.append(
                _CatalogRecord(
                    resource_key=_logical_key("", "", resource_path),
                    creator="",
                    package_name="",
                    versions=(),
                    resource_path=resource_path,
                    resource_type=resource_type,
                    atom_type=atom_type,
                    favorite=_boolish(row.get("baFavourite")),
                    hidden=_boolish(row.get("baHidden")),
                    tags=_normalize_tags(row.get("Tags")),
                )
            )
    return records


def import_browserassist(
    connection: sqlite3.Connection,
    vam_root: Path | str,
    source_path: Path | str | None = None,
    *,
    source: str = BROWSERASSIST_SOURCE,
    addon_root: Path | str | None = None,
) -> CatalogImportResult:
    """Import one stable BrowserAssist snapshot.

    Parsing and snapshot validation happen before database mutation. The
    logical upsert and stale-row deletion are then protected by a savepoint.
    Existing resource IDs survive successful refreshes. Resources omitted
    only because every installed copy of their package is hidden retain their
    last-good metadata and version links. Any failure leaves the previous
    generation untouched.
    """

    _check_schema(connection)
    root = Path(vam_root).expanduser().resolve()
    packages_root = (
        Path(addon_root).expanduser().resolve()
        if addon_root is not None
        else (root / "AddonPackages").resolve()
    )
    catalogue_path = (
        Path(source_path).expanduser().resolve()
        if source_path is not None
        else root / "Saves" / "PluginData" / "JayJayWon" / "BrowserAssist"
    )
    documents = _load_snapshot(catalogue_path)
    user_rows = _user_resource_map(documents["user"])
    packaged, matched_user = _packaged_records(documents["core"], user_rows)
    local = _local_records(documents["local"])
    records = packaged + local

    imported_utc = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    root_value = str(root)
    packages_root_value = str(packages_root)
    savepoint = f"catalog_import_{uuid.uuid4().hex}"
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        connection.executemany(
            """
            INSERT INTO catalog_resources (
                root, source, resource_key, creator, package_name,
                versions_json, resource_path, resource_type, atom_type,
                favorite, hidden, tags_json, imported_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(root, source, resource_key) DO UPDATE SET
                creator = excluded.creator,
                package_name = excluded.package_name,
                versions_json = excluded.versions_json,
                resource_path = excluded.resource_path,
                resource_type = excluded.resource_type,
                atom_type = excluded.atom_type,
                favorite = excluded.favorite,
                hidden = excluded.hidden,
                tags_json = excluded.tags_json,
                imported_utc = excluded.imported_utc
            """,
            [
                (
                    root_value,
                    source,
                    record.resource_key,
                    record.creator,
                    record.package_name,
                    json.dumps(
                        record.versions,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    record.resource_path,
                    record.resource_type,
                    record.atom_type,
                    int(record.favorite),
                    int(record.hidden),
                    json.dumps(
                        record.tags,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    imported_utc,
                )
                for record in records
            ],
        )
        hidden_stale_predicate = """
            creator != '' AND package_name != ''
            AND EXISTS (
                SELECT 1
                FROM catalog_resource_versions AS rv
                JOIN package_files AS pf
                  ON pf.root = ?
                 AND pf.valid = 1
                 AND pf.enabled = 0
                 AND pf.creator = catalog_resources.creator COLLATE NOCASE
                 AND pf.package_name =
                     catalog_resources.package_name COLLATE NOCASE
                 AND pf.version_text = rv.version_text COLLATE NOCASE
                WHERE rv.resource_id = catalog_resources.id
            )
            AND NOT EXISTS (
                SELECT 1
                FROM catalog_resource_versions AS rv
                JOIN package_files AS pf
                  ON pf.root = ?
                 AND pf.valid = 1
                 AND pf.enabled = 1
                 AND pf.creator = catalog_resources.creator COLLATE NOCASE
                 AND pf.package_name =
                     catalog_resources.package_name COLLATE NOCASE
                 AND pf.version_text = rv.version_text COLLATE NOCASE
                WHERE rv.resource_id = catalog_resources.id
            )
        """
        preserved_hidden_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*)
                FROM catalog_resources
                WHERE root = ? AND source = ? AND imported_utc != ?
                  AND ({hidden_stale_predicate})
                """,
                (
                    root_value,
                    source,
                    imported_utc,
                    packages_root_value,
                    packages_root_value,
                ),
            ).fetchone()[0]
        )
        connection.execute(
            f"""
            DELETE FROM catalog_resources
            WHERE root = ? AND source = ? AND imported_utc != ?
              AND NOT ({hidden_stale_predicate})
            """,
            (
                root_value,
                source,
                imported_utc,
                packages_root_value,
                packages_root_value,
            ),
        )
        connection.execute(
            """
            DELETE FROM catalog_resource_versions
            WHERE resource_id IN (
                SELECT id FROM catalog_resources
                WHERE root = ? AND source = ? AND imported_utc = ?
            )
            """,
            (root_value, source, imported_utc),
        )
        resource_ids = {
            row["resource_key"]: int(row["id"])
            for row in connection.execute(
                """
                SELECT id, resource_key FROM catalog_resources
                WHERE root = ? AND source = ?
                """,
                (root_value, source),
            )
        }
        version_links = [
            (resource_ids[record.resource_key], version)
            for record in records
            for version in record.versions
            if record.resource_key in resource_ids
        ]
        connection.executemany(
            """
            INSERT INTO catalog_resource_versions(resource_id, version_text)
            VALUES (?, ?)
            """,
            version_links,
        )
        effective_counts = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN creator = '' AND package_name = '' THEN 1
                        ELSE 0
                    END
                ) AS local_count
            FROM catalog_resources
            WHERE root = ? AND source = ?
            """,
            (root_value, source),
        ).fetchone()
        effective_total = int(effective_counts["total"])
        effective_local = int(effective_counts["local_count"] or 0)
        effective_packaged = effective_total - effective_local
        connection.execute(
            """
            INSERT INTO catalog_sources (
                root, source, source_path, imported_utc, resource_count
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(root, source) DO UPDATE SET
                source_path = excluded.source_path,
                imported_utc = excluded.imported_utc,
                resource_count = excluded.resource_count
            """,
            (
                root_value,
                source,
                str(catalogue_path),
                imported_utc,
                effective_total,
            ),
        )
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    except BaseException:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise

    return CatalogImportResult(
        source=source,
        source_path=catalogue_path,
        imported_utc=imported_utc,
        resource_count=effective_total,
        packaged_count=effective_packaged,
        local_count=effective_local,
        unmatched_user_rows=len(user_rows) - len(matched_user),
        preserved_hidden_count=preserved_hidden_count,
    )


def _json_list(value: str) -> list[Any]:
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return result if isinstance(result, list) else []


def _display_name(resource_path: str) -> str:
    filename = resource_path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]
    if stem.casefold().startswith("preset_"):
        return stem[7:]
    return stem


def _resource_document(row: sqlite3.Row) -> dict[str, object]:
    tags = _json_list(row["tags_json"])
    return {
        "id": row["id"],
        "source": row["source"],
        "key": row["resource_key"],
        "creator": row["creator"],
        "package": row["package_name"],
        "versions": [str(value) for value in _json_list(row["versions_json"])],
        "path": row["resource_path"],
        "display_name": _display_name(row["resource_path"]),
        "resource_type": row["resource_type"],
        "atom_type": row["atom_type"],
        "favorite": bool(row["favorite"]),
        "hidden": bool(row["hidden"]),
        "tags": tags,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tag_identities(row: sqlite3.Row) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for tag in _json_list(row["tags_json"]):
        if isinstance(tag, dict):
            name = tag.get("tagName")
            category = tag.get("tagCategory", "")
            if isinstance(name, str):
                identities.add((name.casefold(), str(category).casefold()))
        elif isinstance(tag, str):
            identities.add((tag.casefold(), ""))
    return identities


def search_resources(
    connection: sqlite3.Connection,
    vam_root: Path | str,
    *,
    query: str = "",
    resource_type: str | None = None,
    resource_types: Iterable[str] | None = None,
    atom_type: str | None = None,
    atom_types: Iterable[str] | None = None,
    creator: str | None = None,
    package_name: str | None = None,
    tag: str | None = None,
    tag_category: str | None = None,
    favorite: bool | None = None,
    hidden: bool | None = None,
    source: str | None = BROWSERASSIST_SOURCE,
    addon_root: Path | str | None = None,
    package_state: str | None = None,
    include_package_state: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, object]:
    """Search imported resources with deterministic pagination."""

    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    where = ["root = ?"]
    parameters: list[object] = [_root_text(vam_root)]
    if source is not None:
        where.append("source = ?")
        parameters.append(source)
    if package_state is not None:
        if package_state not in {"active", "hidden", "missing", "local"}:
            raise ValueError(
                "package_state must be active, hidden, missing, local, or None"
            )
        packages_root = (
            Path(addon_root).expanduser().resolve()
            if addon_root is not None
            else (Path(vam_root).expanduser().resolve() / "AddonPackages")
        )
        installed = """
            EXISTS (
                SELECT 1
                FROM catalog_resource_versions AS rv
                JOIN package_files AS pf
                  ON pf.root = ?
                 AND pf.valid = 1
                 AND pf.creator = catalog_resources.creator COLLATE NOCASE
                 AND pf.package_name =
                     catalog_resources.package_name COLLATE NOCASE
                 AND pf.version_text = rv.version_text COLLATE NOCASE
                WHERE rv.resource_id = catalog_resources.id
            )
        """
        active = installed.replace(
            "AND pf.valid = 1", "AND pf.valid = 1 AND pf.enabled = 1"
        )
        packaged = "(creator != '' OR package_name != '')"
        local = "(creator = '' AND package_name = '')"
        if package_state == "local":
            where.append(local)
        elif package_state == "active":
            where.append(f"({local} OR {active})")
            parameters.append(str(packages_root))
        elif package_state == "hidden":
            where.append(f"({packaged} AND {installed} AND NOT {active})")
            parameters.extend((str(packages_root), str(packages_root)))
        else:
            where.append(f"({packaged} AND NOT {installed})")
            parameters.append(str(packages_root))
    selected_resource_types = {
        value.strip()
        for value in ([resource_type] if resource_type is not None else [])
        + list(resource_types or ())
        if isinstance(value, str) and value.strip()
    }
    selected_atom_types = {
        value.strip()
        for value in ([atom_type] if atom_type is not None else [])
        + list(atom_types or ())
        if isinstance(value, str) and value.strip()
    }
    for column, values in (
        ("resource_type", selected_resource_types),
        ("atom_type", selected_atom_types),
    ):
        if values:
            ordered = sorted(values, key=str.casefold)
            where.append(
                "(" + " OR ".join(f"{column} = ? COLLATE NOCASE" for _ in ordered) + ")"
            )
            parameters.extend(ordered)
    for column, value in (
        ("creator", creator),
        ("package_name", package_name),
    ):
        if value is not None:
            where.append(f"{column} = ? COLLATE NOCASE")
            parameters.append(value)
    if favorite is not None:
        where.append("favorite = ?")
        parameters.append(int(favorite))
    if hidden is not None:
        where.append("hidden = ?")
        parameters.append(int(hidden))
    if query.strip():
        pattern = f"%{_escape_like(query.strip())}%"
        fields = (
            "creator",
            "package_name",
            "resource_path",
            "resource_type",
            "atom_type",
            "tags_json",
        )
        where.append(
            "("
            + " OR ".join(
                f"{field} COLLATE NOCASE LIKE ? ESCAPE '\\'" for field in fields
            )
            + ")"
        )
        parameters.extend(pattern for _ in fields)

    where_sql = " AND ".join(where)
    order_sql = """
        ORDER BY favorite DESC,
                 resource_type COLLATE NOCASE,
                 creator COLLATE NOCASE,
                 package_name COLLATE NOCASE,
                 resource_path COLLATE NOCASE,
                 id
    """
    if tag is None:
        total = int(
            connection.execute(
                f"SELECT COUNT(*) FROM catalog_resources WHERE {where_sql}",
                parameters,
            ).fetchone()[0]
        )
        rows = list(
            connection.execute(
                f"""
                SELECT * FROM catalog_resources
                WHERE {where_sql}
                {order_sql}
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            )
        )
    else:
        rows = list(
            connection.execute(
                f"""
                SELECT * FROM catalog_resources
                WHERE {where_sql}
                {order_sql}
                """,
                parameters,
            )
        )
        tag_key = tag.casefold()
        category_key = tag_category.casefold() if tag_category is not None else None
        rows = [
            row
            for row in rows
            if any(
                name == tag_key and (category_key is None or category == category_key)
                for name, category in _tag_identities(row)
            )
        ]
        total = len(rows)
        rows = rows[offset : offset + limit]

    items = [_resource_document(row) for row in rows]
    if include_package_state and rows:
        resolver = _ResourceResolver(
            connection,
            Path(vam_root).expanduser().resolve(),
            addon_root=addon_root,
        )
        for row, item in zip(rows, items):
            item.update(resolver.resource_state(row))
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _facet_rows(counter: Counter[str]) -> list[dict[str, object]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0].casefold())
        )
    ]


def catalog_facets(
    connection: sqlite3.Connection,
    vam_root: Path | str,
    *,
    source: str | None = BROWSERASSIST_SOURCE,
) -> dict[str, object]:
    where = "root = ?"
    parameters: list[object] = [_root_text(vam_root)]
    if source is not None:
        where += " AND source = ?"
        parameters.append(source)
    rows = list(
        connection.execute(
            f"""
            SELECT resource_type, atom_type, creator, tags_json
            FROM catalog_resources
            WHERE {where}
            """,
            parameters,
        )
    )
    resource_types = Counter(str(row["resource_type"]) for row in rows)
    atom_types = Counter(str(row["atom_type"]) for row in rows if row["atom_type"])
    creators = Counter(str(row["creator"]) for row in rows if row["creator"])
    tags: Counter[tuple[str, str]] = Counter()
    for row in rows:
        per_resource: set[tuple[str, str]] = set()
        for value in _json_list(row["tags_json"]):
            if not isinstance(value, dict):
                continue
            name = value.get("tagName")
            category = value.get("tagCategory", "")
            if isinstance(name, str) and name:
                per_resource.add((name, str(category)))
        tags.update(per_resource)
    tag_rows = [
        {"name": name, "category": category, "count": count}
        for (name, category), count in sorted(
            tags.items(),
            key=lambda item: (
                -item[1],
                item[0][0].casefold(),
                item[0][1].casefold(),
            ),
        )
    ]
    return {
        "total": len(rows),
        "resource_types": _facet_rows(resource_types),
        "atom_types": _facet_rows(atom_types),
        "creators": _facet_rows(creators),
        "tags": tag_rows,
    }


def _safe_local_path(root: Path, resource_path: str) -> Path | None:
    normalized = resource_path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        return None
    if any(":" in part for part in pure.parts):
        return None
    candidate = root.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _normalized_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _member_indexes(
    archive: zipfile.ZipFile,
) -> tuple[
    dict[str, zipfile.ZipInfo],
    dict[str, list[zipfile.ZipInfo]],
]:
    exact: dict[str, zipfile.ZipInfo] = {}
    folded: dict[str, list[zipfile.ZipInfo]] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        normalized = _normalized_member(info.filename)
        exact.setdefault(normalized, info)
        folded.setdefault(normalized.casefold(), []).append(info)
    return exact, folded


def _find_member(
    exact: dict[str, zipfile.ZipInfo],
    folded: dict[str, list[zipfile.ZipInfo]],
    candidates: Iterable[str],
) -> zipfile.ZipInfo | None:
    normalized_candidates = [_normalized_member(value) for value in candidates]
    for candidate in normalized_candidates:
        info = exact.get(candidate)
        if info is not None:
            return info
    for candidate in normalized_candidates:
        matches = folded.get(candidate.casefold(), [])
        if len(matches) == 1:
            return matches[0]
    return None


def _allowed_versions(row: sqlite3.Row) -> set[str]:
    return {
        str(value).strip().casefold()
        for value in _json_list(row["versions_json"])
        if str(value).strip()
    }


def _copy_sort_key(row: sqlite3.Row) -> tuple[object, ...]:
    version = row["version"]
    numeric_group = 0 if version is not None else 1
    numeric_order = -int(version) if version is not None else 0
    relative = Path(row["relative_path"])
    return (
        0 if row["enabled"] else 1,
        numeric_group,
        numeric_order,
        len(relative.parts),
        0 if relative.name == row["canonical_filename"] else 1,
        len(str(relative)),
        str(relative).casefold(),
    )


class _ResourceResolver:
    def __init__(
        self,
        connection: sqlite3.Connection,
        vam_root: Path,
        *,
        addon_root: Path | str | None,
    ) -> None:
        self.vam_root = vam_root
        packages_root = (
            Path(addon_root).expanduser().resolve()
            if addon_root is not None
            else (vam_root / "AddonPackages").resolve()
        )
        self.packages: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in connection.execute(
            """
            SELECT * FROM package_files
            WHERE root = ? AND valid = 1 AND version_text IS NOT NULL
            """,
            (str(packages_root),),
        ):
            key = (
                str(row["creator"]).casefold(),
                str(row["package_name"]).casefold(),
            )
            self.packages.setdefault(key, []).append(row)
        for rows in self.packages.values():
            rows.sort(key=_copy_sort_key)
        self.archive_indexes: dict[
            Path,
            tuple[
                dict[str, zipfile.ZipInfo],
                dict[str, list[zipfile.ZipInfo]],
            ]
            | None,
        ] = {}

    def candidates(self, row: sqlite3.Row) -> list[sqlite3.Row]:
        allowed = _allowed_versions(row)
        if not allowed:
            return []
        key = (
            str(row["creator"]).casefold(),
            str(row["package_name"]).casefold(),
        )
        return [
            package_row
            for package_row in self.packages.get(key, ())
            if str(package_row["version_text"]).casefold() in allowed
        ]

    def _archive_index(
        self, archive_path: Path
    ) -> (
        tuple[
            dict[str, zipfile.ZipInfo],
            dict[str, list[zipfile.ZipInfo]],
        ]
        | None
    ):
        if archive_path not in self.archive_indexes:
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    self.archive_indexes[archive_path] = _member_indexes(archive)
            except (
                OSError,
                RuntimeError,
                NotImplementedError,
                zipfile.BadZipFile,
                zipfile.LargeZipFile,
            ):
                self.archive_indexes[archive_path] = None
        return self.archive_indexes[archive_path]

    def resolve_row(self, row: sqlite3.Row) -> ResourceLocation | None:
        creator = str(row["creator"])
        package_name = str(row["package_name"])
        resource_path = str(row["resource_path"])
        if not creator and not package_name:
            local_path = _safe_local_path(self.vam_root, resource_path)
            if local_path is None or not local_path.is_file():
                return None
            return ResourceLocation(
                resource_id=int(row["id"]),
                resource_path=resource_path,
                creator="",
                package_name="",
                version_text=None,
                package_ref=None,
                enabled=True,
                archive_path=None,
                archive_member=None,
                local_path=local_path,
            )

        wanted = _normalized_member(resource_path)
        for package_row in self.candidates(row):
            archive_path = Path(package_row["path"])
            indexes = self._archive_index(archive_path)
            if indexes is None:
                continue
            exact, folded = indexes
            member = _find_member(exact, folded, (wanted,))
            if member is None:
                continue
            version_text = str(package_row["version_text"])
            return ResourceLocation(
                resource_id=int(row["id"]),
                resource_path=resource_path,
                creator=str(package_row["creator"]),
                package_name=str(package_row["package_name"]),
                version_text=version_text,
                package_ref=(
                    f"{package_row['creator']}."
                    f"{package_row['package_name']}.{version_text}"
                ),
                enabled=bool(package_row["enabled"]),
                archive_path=archive_path,
                archive_member=member.filename,
                local_path=None,
            )
        return None

    @staticmethod
    def _candidate_ref(package_row: sqlite3.Row) -> str:
        return (
            f"{package_row['creator']}."
            f"{package_row['package_name']}."
            f"{package_row['version_text']}"
        )

    def resource_state(self, row: sqlite3.Row) -> dict[str, object]:
        creator = str(row["creator"])
        package_name = str(row["package_name"])
        location = self.resolve_row(row)
        if location is not None:
            return {
                "package_ref": location.package_ref,
                "selected_version": location.version_text,
                "enabled": location.enabled,
                "missing": False,
                "missing_reason": None,
                "local": location.local_path is not None,
            }
        if not creator and not package_name:
            return {
                "package_ref": None,
                "selected_version": None,
                "enabled": False,
                "missing": True,
                "missing_reason": "resource",
                "local": True,
            }
        candidates = self.candidates(row)
        if candidates:
            candidate = candidates[0]
            return {
                "package_ref": self._candidate_ref(candidate),
                "selected_version": str(candidate["version_text"]),
                "enabled": bool(candidate["enabled"]),
                "missing": True,
                "missing_reason": "resource",
                "local": False,
            }
        return {
            "package_ref": None,
            "selected_version": None,
            "enabled": False,
            "missing": True,
            "missing_reason": "package",
            "local": False,
        }


def resolve_resource_archive(
    connection: sqlite3.Connection,
    vam_root: Path | str,
    resource_id: int,
    *,
    addon_root: Path | str | None = None,
) -> ResourceLocation | None:
    """Resolve a resource to a real loose file or matching archive member.

    A package version is eligible only when BrowserAssist associates the
    resource with that version and the installed ZIP actually contains the
    member. This avoids incorrectly choosing a newer family version that
    removed the selected scene or preset.
    """

    root = Path(vam_root).expanduser().resolve()
    row = connection.execute(
        """
        SELECT * FROM catalog_resources
        WHERE id = ? AND root = ?
        """,
        (int(resource_id), str(root)),
    ).fetchone()
    if row is None:
        return None
    return _ResourceResolver(
        connection,
        root,
        addon_root=addon_root,
    ).resolve_row(row)


def _sibling_jpg_names(resource_name: str) -> tuple[str, str]:
    normalized = _normalized_member(resource_name)
    if "." in normalized.rsplit("/", 1)[-1]:
        base = normalized.rsplit(".", 1)[0]
    else:
        base = normalized
    return f"{base}.jpg", f"{base}.JPG"


def _bounded_file_read(
    path: Path, max_bytes: int
) -> tuple[bytes, os.stat_result] | None:
    try:
        before = path.stat()
        if before.st_size > max_bytes:
            return None
        with path.open("rb") as handle:
            data = handle.read(max_bytes + 1)
        after = path.stat()
    except OSError:
        return None
    if len(data) > max_bytes:
        return None
    before_key = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_key = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_key != after_key or len(data) != before.st_size:
        return None
    return data, after


def _write_cache(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(data)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _cache_result(
    cache_path: Path,
    *,
    etag: str,
    cache_hit: bool,
    version_text: str | None,
) -> ThumbnailResult:
    return ThumbnailResult(
        path=cache_path,
        content_type="image/jpeg",
        size=cache_path.stat().st_size,
        etag=etag,
        cache_hit=cache_hit,
        version_text=version_text,
    )


def _cached_thumbnail(
    cache_root: Path,
    identity: bytes,
    *,
    expected_size: int,
    max_bytes: int,
    version_text: str | None,
) -> tuple[ThumbnailResult | None, Path, str]:
    digest = hashlib.sha256(identity).hexdigest()
    cache_path = cache_root / digest[:2] / f"{digest}.jpg"
    etag = f'"{digest}"'
    try:
        cache_size = cache_path.stat().st_size
    except OSError:
        return None, cache_path, etag
    if cache_size != expected_size or cache_size > max_bytes:
        return None, cache_path, etag
    return (
        _cache_result(
            cache_path,
            etag=etag,
            cache_hit=True,
            version_text=version_text,
        ),
        cache_path,
        etag,
    )


def get_resource_thumbnail(
    connection: sqlite3.Connection,
    vam_root: Path | str,
    resource_id: int,
    cache_dir: Path | str,
    *,
    addon_root: Path | str | None = None,
    max_bytes: int = DEFAULT_MAX_THUMBNAIL_BYTES,
) -> ThumbnailResult | None:
    """Return a bounded, lazily cached sibling-JPG thumbnail."""

    max_bytes = int(max_bytes)
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    location = resolve_resource_archive(
        connection,
        vam_root,
        resource_id,
        addon_root=addon_root,
    )
    if location is None:
        return None
    cache_root = Path(cache_dir).expanduser().resolve()

    if location.local_path is not None:
        lower, upper = _sibling_jpg_names(str(location.local_path))
        candidates = (Path(lower), Path(upper))
        thumbnail_path = next((path for path in candidates if path.is_file()), None)
        if thumbnail_path is None:
            return None
        try:
            initial_stat = thumbnail_path.stat()
        except OSError:
            return None
        if initial_stat.st_size > max_bytes:
            return None
        identity = json.dumps(
            [
                "local",
                initial_stat.st_dev,
                initial_stat.st_ino,
                initial_stat.st_size,
                initial_stat.st_mtime_ns,
            ],
            separators=(",", ":"),
        ).encode()
        cached, cache_path, etag = _cached_thumbnail(
            cache_root,
            identity,
            expected_size=initial_stat.st_size,
            max_bytes=max_bytes,
            version_text=location.version_text,
        )
        if cached is not None:
            return cached
        read = _bounded_file_read(thumbnail_path, max_bytes)
        if read is None:
            return None
        data, final_stat = read
        initial_key = (
            initial_stat.st_dev,
            initial_stat.st_ino,
            initial_stat.st_size,
            initial_stat.st_mtime_ns,
        )
        final_key = (
            final_stat.st_dev,
            final_stat.st_ino,
            final_stat.st_size,
            final_stat.st_mtime_ns,
        )
        if initial_key != final_key:
            return None
    else:
        assert location.archive_path is not None
        assert location.archive_member is not None
        try:
            archive_stat = location.archive_path.stat()
            with zipfile.ZipFile(location.archive_path) as archive:
                exact, folded = _member_indexes(archive)
                info = _find_member(
                    exact,
                    folded,
                    _sibling_jpg_names(location.archive_member),
                )
                if info is None or info.file_size > max_bytes:
                    return None
                identity = json.dumps(
                    [
                        "archive",
                        archive_stat.st_dev,
                        archive_stat.st_ino,
                        archive_stat.st_size,
                        archive_stat.st_mtime_ns,
                        _normalized_member(info.filename),
                        info.CRC,
                        info.file_size,
                        info.compress_size,
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                cached, cache_path, etag = _cached_thumbnail(
                    cache_root,
                    identity,
                    expected_size=info.file_size,
                    max_bytes=max_bytes,
                    version_text=location.version_text,
                )
                if cached is not None:
                    return cached
                with archive.open(info) as handle:
                    data = handle.read(max_bytes + 1)
        except (
            OSError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
        ):
            return None
        if len(data) > max_bytes or len(data) != info.file_size:
            return None
    _write_cache(cache_path, data)
    return _cache_result(
        cache_path,
        etag=etag,
        cache_hit=False,
        version_text=location.version_text,
    )

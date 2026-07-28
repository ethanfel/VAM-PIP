from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat as stat_module
import time
import unicodedata
import uuid
import zipfile
import zlib

from vampip.models import DISABLED_SUFFIX, parse_dependency_ref, parse_var_filename


ARCHIVE_INSPECTION_VERSION = 1
ARCHIVE_CONTENT_HASH_VERSION = 1
_ARCHIVE_CONTENT_HASH_PREFIX = f"{ARCHIVE_CONTENT_HASH_VERSION}:"
_MAX_CONTENT_HASH_MEMBERS = 250_000
_MAX_CONTENT_HASH_PATH_BYTES = 4096
_MAX_CONTENT_HASH_UNCOMPRESSED = 512 * 1024**3
_MAX_CONTENT_HASH_EXPANSION_RATIO = 1_000
_MIN_CONTENT_HASH_EXPANSION_ALLOWANCE = 2 * 1024**3
_SUPPORTED_VAR_COMPRESSION = {
    zipfile.ZIP_STORED,
    zipfile.ZIP_DEFLATED,
}


@dataclass(frozen=True)
class ScanResult:
    found: int
    inspected: int
    unchanged: int
    invalid: int
    removed: int
    added: int
    active_changed: int
    elapsed: float


def _iter_var_files(root: Path) -> Iterable[Path]:
    for directory, _, filenames in os.walk(root):
        base = Path(directory)
        for filename in filenames:
            folded = filename.casefold()
            if folded.endswith(".var") or folded.endswith(f".var{DISABLED_SUFFIX}"):
                yield base / filename


def _fingerprint_entries(
    entries: Iterable[tuple[str, int, int, int, int]],
) -> str:
    ordered = sorted(entries)
    digest = hashlib.blake2b(digest_size=16)
    for relative_path, size, mtime_ns, device, inode in ordered:
        digest.update(os.fsencode(relative_path))
        digest.update(b"\0")
        for value in (size, mtime_ns, device, inode):
            digest.update(str(value).encode("ascii"))
            digest.update(b"\0")
    return f"1:{len(ordered)}:{digest.hexdigest()}"


def inventory_fingerprint(root: Path) -> str:
    """Return a cheap recursive identity for package directory contents."""

    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"AddonPackages directory does not exist: {root}")
    root_text = os.fspath(root)
    entries: list[tuple[str, int, int, int, int]] = []
    pending = [(root_text, "")]
    while pending:
        directory, prefix = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                directory_entries = list(iterator)
        except OSError:
            continue
        for entry in directory_entries:
            relative_path = prefix + entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, relative_path + os.sep))
                    continue
                folded = entry.name.casefold()
                if not (
                    folded.endswith(".var")
                    or folded.endswith(f".var{DISABLED_SUFFIX}")
                ):
                    continue
                stat = entry.stat()
            except OSError:
                continue
            entries.append(
                (
                    relative_path,
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_dev,
                    stat.st_ino,
                )
            )
    return _fingerprint_entries(entries)


def inventory_changed(connection: sqlite3.Connection, root: Path) -> bool:
    """Return whether package paths or filesystem identities changed."""

    root = root.resolve()
    key = f"inventory_fingerprint:{root}"
    stored = connection.execute(
        "SELECT value FROM schema_meta WHERE key = ?",
        (key,),
    ).fetchone()
    return stored is None or stored["value"] != inventory_fingerprint(root)


def _flatten_dependencies(value: object) -> list[str]:
    found: dict[str, None] = {}

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        for key, details in node.items():
            if isinstance(key, str) and parse_dependency_ref(key):
                found.setdefault(key, None)
            if isinstance(details, dict):
                visit(details.get("dependencies"))

    visit(value)
    return list(found)


def _vam_zip_version_error(archive: zipfile.ZipFile) -> str | None:
    for entry in archive.infolist():
        if not entry.reserved:
            continue
        version_required = entry.extract_version | (entry.reserved << 8)
        return (
            f"VaM/SharpZipLib-incompatible ZIP entry {entry.filename!r}: "
            f"version required to extract is {version_required} "
            f"(nonzero high byte {entry.reserved})"
        )
    return None


def inspect_archive(path: Path) -> dict[str, object]:
    parsed = parse_var_filename(path)
    result: dict[str, object] = {
        "creator": parsed.creator if parsed else None,
        "package_name": parsed.package if parsed else None,
        "version": parsed.version if parsed else None,
        "version_text": parsed.version_text if parsed else None,
        "canonical_filename": parsed.canonical_filename if parsed else None,
        "valid": 0,
        "error": None,
        "dependencies_json": "[]",
    }
    if parsed is None:
        result["error"] = "filename is not creator.package.version.var"
        return result

    try:
        with zipfile.ZipFile(path) as archive:
            if version_error := _vam_zip_version_error(archive):
                result["error"] = version_error
                return result
            metadata_names = [
                name for name in archive.namelist() if name.casefold() == "meta.json"
            ]
            if not metadata_names:
                result["error"] = "archive has no root meta.json"
                return result
            with archive.open(metadata_names[0]) as handle:
                metadata = json.loads(handle.read().decode("utf-8-sig"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    if not isinstance(metadata, dict):
        result["error"] = "meta.json is not a JSON object"
        return result

    warnings: list[str] = []
    meta_creator = metadata.get("creatorName")
    meta_package = metadata.get("packageName")
    if (
        isinstance(meta_creator, str)
        and meta_creator.casefold() != parsed.creator.casefold()
    ):
        warnings.append(f"creator metadata says {meta_creator!r}")
    if (
        isinstance(meta_package, str)
        and meta_package.casefold() != parsed.package.casefold()
    ):
        warnings.append(f"package metadata says {meta_package!r}")

    result["valid"] = 1
    result["error"] = "; ".join(warnings) or None
    result["dependencies_json"] = json.dumps(
        _flatten_dependencies(metadata.get("dependencies", {})),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return result


def scan(root: Path, connection: sqlite3.Connection) -> ScanResult:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"AddonPackages directory does not exist: {root}")

    inspection_key = f"archive_inspection_version:{root}"
    stored_inspection_version = connection.execute(
        "SELECT value FROM schema_meta WHERE key = ?",
        (inspection_key,),
    ).fetchone()
    force_inspection = (
        stored_inspection_version is None
        or stored_inspection_version["value"] != str(ARCHIVE_INSPECTION_VERSION)
    )

    started = time.monotonic()
    generation = uuid.uuid4().hex
    existing = {
        row["path"]: row
        for row in connection.execute(
            """
            SELECT *
            FROM package_files WHERE root = ?
            """,
            (str(root),),
        )
    }
    existing_by_inode: dict[tuple[int, int], sqlite3.Row] = {}
    for row in existing.values():
        existing_by_inode.setdefault((row["device"], row["inode"]), row)
    found = inspected = unchanged = added = active_changed = 0
    fingerprint_entries: list[tuple[str, int, int, int, int]] = []

    upsert = """
        INSERT INTO package_files (
            path, root, relative_path, basename, size, mtime_ns, device, inode,
            creator, package_name, version, version_text, canonical_filename,
            valid, error, dependencies_json, sha256, content_sha256, enabled,
            scan_generation
        ) VALUES (
            :path, :root, :relative_path, :basename, :size, :mtime_ns, :device,
            :inode, :creator, :package_name, :version, :version_text,
            :canonical_filename, :valid, :error, :dependencies_json, :sha256,
            :content_sha256, :enabled, :scan_generation
        )
        ON CONFLICT(path) DO UPDATE SET
            root=excluded.root,
            relative_path=excluded.relative_path,
            basename=excluded.basename,
            size=excluded.size,
            mtime_ns=excluded.mtime_ns,
            device=excluded.device,
            inode=excluded.inode,
            creator=excluded.creator,
            package_name=excluded.package_name,
            version=excluded.version,
            version_text=excluded.version_text,
            canonical_filename=excluded.canonical_filename,
            valid=excluded.valid,
            error=excluded.error,
            dependencies_json=excluded.dependencies_json,
            sha256=excluded.sha256,
            content_sha256=excluded.content_sha256,
            enabled=excluded.enabled,
            scan_generation=excluded.scan_generation
    """

    for path in _iter_var_files(root):
        found += 1
        try:
            stat = path.stat()
        except OSError:
            continue
        path_text = str(path.resolve())
        relative_path = os.path.relpath(path, root)
        fingerprint_entries.append(
            (
                relative_path,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_dev,
                stat.st_ino,
            )
        )
        cached = existing.get(path_text)
        enabled = 0 if path.name.casefold().endswith(DISABLED_SUFFIX) else 1
        cached_unchanged = (
            cached is not None
            and cached["size"] == stat.st_size
            and cached["mtime_ns"] == stat.st_mtime_ns
            and cached["device"] == stat.st_dev
            and cached["inode"] == stat.st_ino
        )
        moved = (
            existing_by_inode.get((stat.st_dev, stat.st_ino))
            if cached is None
            else None
        )
        inspect_active_change = False
        if cached is None and moved is None:
            added += 1
            if enabled:
                inspect_active_change = True
        elif cached is not None and not cached_unchanged and enabled:
            inspect_active_change = True

        if cached is None:
            if (
                not force_inspection
                and moved is not None
                and moved["size"] == stat.st_size
                and moved["mtime_ns"] == stat.st_mtime_ns
            ):
                parsed = parse_var_filename(path)
                connection.execute(
                    upsert,
                    {
                        "path": path_text,
                        "root": str(root),
                        "relative_path": str(path.resolve().relative_to(root)),
                        "basename": path.name,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "device": stat.st_dev,
                        "inode": stat.st_ino,
                        "creator": parsed.creator if parsed else moved["creator"],
                        "package_name": (
                            parsed.package if parsed else moved["package_name"]
                        ),
                        "version": parsed.version if parsed else moved["version"],
                        "version_text": (
                            parsed.version_text if parsed else moved["version_text"]
                        ),
                        "canonical_filename": (
                            parsed.canonical_filename
                            if parsed
                            else moved["canonical_filename"]
                        ),
                        "valid": moved["valid"],
                        "error": moved["error"],
                        "dependencies_json": moved["dependencies_json"],
                        "sha256": moved["sha256"],
                        "content_sha256": moved["content_sha256"],
                        "enabled": enabled,
                        "scan_generation": generation,
                    },
                )
                if enabled and not moved["enabled"] and moved["valid"]:
                    active_changed += 1
                unchanged += 1
                continue

        if not force_inspection and cached_unchanged:
            connection.execute(
                """
                UPDATE package_files
                SET scan_generation = ?, device = ?, inode = ?, enabled = ?,
                    relative_path = ?, basename = ?
                WHERE path = ?
                """,
                (
                    generation,
                    stat.st_dev,
                    stat.st_ino,
                    enabled,
                    str(path.resolve().relative_to(root)),
                    path.name,
                    path_text,
                ),
            )
            unchanged += 1
            continue

        details = inspect_archive(path)
        inspected += 1
        if inspect_active_change and details["valid"]:
            active_changed += 1
        connection.execute(
            upsert,
            {
                "path": path_text,
                "root": str(root),
                "relative_path": str(path.resolve().relative_to(root)),
                "basename": path.name,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "device": stat.st_dev,
                "inode": stat.st_ino,
                "sha256": cached["sha256"] if cached_unchanged else None,
                "content_sha256": (
                    cached["content_sha256"] if cached_unchanged else None
                ),
                "enabled": enabled,
                "scan_generation": generation,
                **details,
            },
        )

    removed_active = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM package_files
            WHERE root = ? AND scan_generation != ?
              AND enabled = 1 AND valid = 1
            """,
            (str(root), generation),
        ).fetchone()[0]
    )
    active_changed += removed_active
    cursor = connection.execute(
        "DELETE FROM package_files WHERE root = ? AND scan_generation != ?",
        (str(root), generation),
    )
    connection.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (inspection_key, str(ARCHIVE_INSPECTION_VERSION)),
    )
    connection.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (
            f"inventory_fingerprint:{root}",
            _fingerprint_entries(fingerprint_entries),
        ),
    )
    invalid_total = connection.execute(
        "SELECT COUNT(*) FROM package_files WHERE root = ? AND valid = 0",
        (str(root),),
    ).fetchone()[0]
    connection.commit()
    return ScanResult(
        found=found,
        inspected=inspected,
        unchanged=unchanged,
        invalid=invalid_total,
        removed=cursor.rowcount,
        added=added,
        active_changed=active_changed,
        elapsed=time.monotonic() - started,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _content_hash_member_path(entry: zipfile.ZipInfo) -> tuple[str, bool]:
    original = entry.orig_filename
    if not original or "\0" in original:
        raise ValueError("ZIP member has an empty or NUL-containing path")
    normalized = original.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/"):
        raise ValueError(f"ZIP member has an unsafe absolute path: {original!r}")

    unix_mode = (
        (entry.external_attr >> 16) & 0xFFFF
        if entry.create_system == 3
        else 0
    )
    unix_type = stat_module.S_IFMT(unix_mode)
    directory = normalized.endswith("/")
    if unix_type == stat_module.S_IFDIR and not directory:
        raise ValueError(
            f"ZIP directory path has no trailing slash: {original!r}"
        )
    if directory:
        normalized = normalized.rstrip("/")
    parts = normalized.split("/")
    if (
        not normalized
        or any(not part or part in {".", ".."} or ":" in part for part in parts)
    ):
        raise ValueError(f"ZIP member has an unsafe path: {original!r}")
    if unix_type not in {0, stat_module.S_IFREG, stat_module.S_IFDIR}:
        raise ValueError(f"ZIP member is not a regular file: {original!r}")
    if directory and unix_type not in {0, stat_module.S_IFDIR}:
        raise ValueError(f"ZIP directory has incompatible attributes: {original!r}")
    if not directory and unix_type not in {0, stat_module.S_IFREG}:
        raise ValueError(f"ZIP file has incompatible attributes: {original!r}")
    return normalized, directory


def is_archive_content_sha256(value: object) -> bool:
    text = str(value or "")
    payload = text.removeprefix(_ARCHIVE_CONTENT_HASH_PREFIX)
    return (
        len(text) == len(_ARCHIVE_CONTENT_HASH_PREFIX) + 64
        and text.startswith(_ARCHIVE_CONTENT_HASH_PREFIX)
        and all(character in "0123456789abcdef" for character in payload)
    )


def archive_content_sha256(path: Path) -> str:
    """Hash logical VAR member names and bytes, ignoring ZIP repack metadata."""

    members: list[tuple[bytes, zipfile.ZipInfo]] = []
    collision_names: dict[str, str] = {}
    directory_names: set[str] = set()
    declared_total = 0
    try:
        with path.open("rb") as raw:
            before = os.fstat(raw.fileno())
            expansion_limit = min(
                _MAX_CONTENT_HASH_UNCOMPRESSED,
                max(
                    _MIN_CONTENT_HASH_EXPANSION_ALLOWANCE,
                    before.st_size * _MAX_CONTENT_HASH_EXPANSION_RATIO,
                ),
            )
            with zipfile.ZipFile(raw) as archive:
                entries = archive.infolist()
                if len(entries) > _MAX_CONTENT_HASH_MEMBERS:
                    raise ValueError(
                        f"ZIP has too many members ({len(entries):,})"
                    )
                for entry in entries:
                    normalized, directory = _content_hash_member_path(entry)
                    collision_key = unicodedata.normalize(
                        "NFC",
                        normalized,
                    ).casefold()
                    name = normalized.encode("utf-8")
                    if len(name) > _MAX_CONTENT_HASH_PATH_BYTES:
                        raise ValueError(
                            f"ZIP member path is too long: {entry.orig_filename!r}"
                        )
                    if entry.flag_bits & 0x1:
                        raise ValueError(
                            f"ZIP member is encrypted: {entry.orig_filename!r}"
                        )
                    if entry.compress_type not in _SUPPORTED_VAR_COMPRESSION:
                        raise ValueError(
                            "ZIP member uses unsupported compression "
                            f"{entry.compress_type}: {entry.orig_filename!r}"
                        )
                    if directory:
                        if entry.file_size != 0:
                            raise ValueError(
                                "ZIP directory contains data: "
                                f"{entry.orig_filename!r}"
                            )
                        directory_names.add(collision_key)
                        continue
                    previous = collision_names.get(collision_key)
                    if previous is not None:
                        raise ValueError(
                            "ZIP has ambiguous duplicate member paths: "
                            f"{previous!r}, {entry.orig_filename!r}"
                        )
                    collision_names[collision_key] = entry.orig_filename
                    declared_total += int(entry.file_size)
                    if declared_total > expansion_limit:
                        raise ValueError(
                            "ZIP member data exceeds the logical hashing "
                            "expansion limit"
                        )
                    members.append((name, entry))

                file_names = set(collision_names)
                all_names = file_names | directory_names
                for name in all_names:
                    if name in directory_names:
                        if name in file_names:
                            raise ValueError(
                                f"ZIP path is both a file and directory: {name!r}"
                            )
                    parts = name.split("/")
                    for index in range(1, len(parts)):
                        ancestor = "/".join(parts[:index])
                        if ancestor in file_names:
                            raise ValueError(
                                "ZIP file path is also a parent directory: "
                                f"{ancestor!r}"
                            )

                records: list[tuple[bytes, int, bytes]] = []
                actual_total = 0
                for name, entry in sorted(
                    members,
                    key=lambda value: value[0],
                ):
                    member_digest = hashlib.sha256()
                    member_size = 0
                    with archive.open(entry, "r") as handle:
                        while chunk := handle.read(8 * 1024 * 1024):
                            member_digest.update(chunk)
                            member_size += len(chunk)
                            actual_total += len(chunk)
                            if actual_total > expansion_limit:
                                raise ValueError(
                                    "ZIP expands beyond the logical hashing "
                                    "safety limit"
                                )
                    if member_size != entry.file_size:
                        raise ValueError(
                            "ZIP member size changed while reading: "
                            f"{entry.orig_filename!r}"
                        )
                    records.append((name, member_size, member_digest.digest()))
            after = os.fstat(raw.fileno())
    except (
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
    ) as exc:
        raise ValueError(
            f"could not read logical VAR contents: {type(exc).__name__}: {exc}"
        ) from exc

    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise ValueError("archive changed while its logical contents were hashed")

    digest = hashlib.sha256()
    digest.update(b"VAM-PIP logical VAR contents\0")
    digest.update(ARCHIVE_CONTENT_HASH_VERSION.to_bytes(4, "big"))
    digest.update(len(records).to_bytes(8, "big"))
    for name, member_size, member_digest in records:
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(member_size.to_bytes(8, "big"))
        digest.update(member_digest)
    return f"{_ARCHIVE_CONTENT_HASH_PREFIX}{digest.hexdigest()}"


def _row_matches_stat(row: sqlite3.Row, file_stat: os.stat_result) -> bool:
    return (
        row["size"] == file_stat.st_size
        and row["mtime_ns"] == file_stat.st_mtime_ns
        and row["device"] == file_stat.st_dev
        and row["inode"] == file_stat.st_ino
    )


def ensure_content_hashes(
    connection: sqlite3.Connection,
    rows: Iterable[sqlite3.Row],
) -> int:
    """Lazily cache logical VAR hashes without changing raw SHA semantics."""

    calculated = 0
    seen_paths: set[str] = set()
    cached_by_file: dict[tuple[int, int, int, int], str] = {}
    cached_by_raw_hash: dict[str, str] = {}
    row_list = list(rows)
    for row in row_list:
        content_hash = str(row["content_sha256"] or "")
        if not is_archive_content_sha256(content_hash):
            continue
        try:
            current = Path(str(row["path"])).stat()
        except OSError as exc:
            raise ValueError(
                f"could not verify logical contents of {row['relative_path']}: {exc}"
            ) from exc
        if not _row_matches_stat(row, current):
            raise ValueError(
                f"package changed before logical hashing: {row['relative_path']}"
            )
        file_key = (
            row["device"],
            row["inode"],
            row["size"],
            row["mtime_ns"],
        )
        cached_by_file[file_key] = content_hash
        if row["sha256"]:
            cached_by_raw_hash[str(row["sha256"])] = content_hash

    pending: list[tuple[str, sqlite3.Row]] = []
    for row in row_list:
        path_text = str(row["path"])
        if path_text in seen_paths:
            continue
        seen_paths.add(path_text)
        content_hash = str(row["content_sha256"] or "")
        if is_archive_content_sha256(content_hash):
            continue

        file_key = (
            row["device"],
            row["inode"],
            row["size"],
            row["mtime_ns"],
        )
        digest = cached_by_file.get(file_key)
        if digest is None and row["sha256"]:
            digest = cached_by_raw_hash.get(str(row["sha256"]))
        path = Path(path_text)
        try:
            before = path.stat()
        except OSError as exc:
            raise ValueError(
                f"could not verify logical contents of {row['relative_path']}: {exc}"
            ) from exc
        if not _row_matches_stat(row, before):
            raise ValueError(
                f"package changed before logical hashing: {row['relative_path']}"
            )
        if digest is None:
            try:
                digest = archive_content_sha256(path)
            except ValueError as exc:
                raise ValueError(
                    "could not verify logical contents of "
                    f"{row['relative_path']}: {exc}"
                ) from exc
            calculated += 1
        try:
            after = path.stat()
        except OSError as exc:
            raise ValueError(
                f"package changed after logical hashing: {row['relative_path']}"
            ) from exc
        if not _row_matches_stat(row, after):
            raise ValueError(
                f"package changed during logical hashing: {row['relative_path']}"
            )
        cached_by_file[file_key] = digest
        if row["sha256"]:
            cached_by_raw_hash[str(row["sha256"])] = digest
        pending.append((digest, row))

    for digest, row in pending:
        cursor = connection.execute(
            """
            UPDATE package_files
            SET content_sha256 = ?
            WHERE path = ? AND size = ? AND mtime_ns = ?
              AND device = ? AND inode = ?
            """,
            (
                digest,
                row["path"],
                row["size"],
                row["mtime_ns"],
                row["device"],
                row["inode"],
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise ValueError(
                "package inventory changed while saving logical hash: "
                f"{row['relative_path']}"
            )
    connection.commit()
    return calculated


def ensure_hashes(connection: sqlite3.Connection, rows: Iterable[sqlite3.Row]) -> int:
    calculated = 0
    seen_paths: set[str] = set()
    for row in rows:
        path_text = row["path"]
        if path_text in seen_paths or row["sha256"]:
            continue
        seen_paths.add(path_text)
        path = Path(path_text)
        try:
            digest = sha256_file(path)
        except OSError:
            continue
        connection.execute(
            "UPDATE package_files SET sha256 = ? WHERE path = ?",
            (digest, path_text),
        )
        calculated += 1
    connection.commit()
    return calculated


def rows_for_root(
    connection: sqlite3.Connection, root: Path, *, valid_only: bool = False
) -> list[sqlite3.Row]:
    where = "root = ?"
    if valid_only:
        where += " AND valid = 1"
    return list(
        connection.execute(
            f"SELECT * FROM package_files WHERE {where} ORDER BY relative_path",
            (str(root.resolve()),),
        )
    )

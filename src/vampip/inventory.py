from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
import zipfile

from vampip.models import DISABLED_SUFFIX, parse_dependency_ref, parse_var_filename


@dataclass(frozen=True)
class ScanResult:
    found: int
    inspected: int
    unchanged: int
    invalid: int
    removed: int
    elapsed: float


def _iter_var_files(root: Path) -> Iterable[Path]:
    for directory, _, filenames in os.walk(root):
        base = Path(directory)
        for filename in filenames:
            folded = filename.casefold()
            if folded.endswith(".var") or folded.endswith(f".var{DISABLED_SUFFIX}"):
                yield base / filename


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
    found = inspected = unchanged = 0

    upsert = """
        INSERT INTO package_files (
            path, root, relative_path, basename, size, mtime_ns, device, inode,
            creator, package_name, version, version_text, canonical_filename,
            valid, error, dependencies_json, sha256, enabled, scan_generation
        ) VALUES (
            :path, :root, :relative_path, :basename, :size, :mtime_ns, :device,
            :inode, :creator, :package_name, :version, :version_text,
            :canonical_filename, :valid, :error, :dependencies_json, :sha256,
            :enabled, :scan_generation
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
        cached = existing.get(path_text)
        enabled = 0 if path.name.casefold().endswith(DISABLED_SUFFIX) else 1

        if cached is None:
            moved = existing_by_inode.get((stat.st_dev, stat.st_ino))
            if (
                moved is not None
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
                        "enabled": enabled,
                        "scan_generation": generation,
                    },
                )
                unchanged += 1
                continue

        if (
            cached is not None
            and cached["size"] == stat.st_size
            and cached["mtime_ns"] == stat.st_mtime_ns
            and cached["device"] == stat.st_dev
            and cached["inode"] == stat.st_ino
        ):
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
                "sha256": None,
                "enabled": enabled,
                "scan_generation": generation,
                **details,
            },
        )
        if found % 250 == 0:
            connection.commit()

    cursor = connection.execute(
        "DELETE FROM package_files WHERE root = ? AND scan_generation != ?",
        (str(root), generation),
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
        elapsed=time.monotonic() - started,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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

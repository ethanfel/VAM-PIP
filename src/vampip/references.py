from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import BinaryIO
import zipfile

from vampip.catalog import resolve_resource_archive
from vampip.models import parse_dependency_ref


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
) -> list[str]:
    location = resolve_resource_archive(
        connection,
        vam_root,
        resource_id,
        addon_root=addon_root,
        version_text=version_text,
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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import zipfile


@dataclass(frozen=True)
class ContentOccurrence:
    archive_path: str
    archive_relative: str
    entry_name: str
    compressed_size: int


@dataclass(frozen=True)
class ContentGroup:
    uncompressed_size: int
    crc32: int
    archive_count: int
    estimated_redundant_compressed_bytes: int
    samples: tuple[ContentOccurrence, ...]


@dataclass(frozen=True)
class IntraArchiveGroup:
    archive_relative: str
    uncompressed_size: int
    crc32: int
    extra_entries: int
    estimated_redundant_compressed_bytes: int
    entry_names: tuple[str, ...]


@dataclass(frozen=True)
class ContentAudit:
    archives_scanned: int
    archives_skipped: int
    unreadable_archives: int
    entries_considered: int
    cross_archive_groups: tuple[ContentGroup, ...]
    intra_archive_groups: tuple[IntraArchiveGroup, ...]

    @property
    def cross_archive_estimate(self) -> int:
        return sum(
            group.estimated_redundant_compressed_bytes
            for group in self.cross_archive_groups
        )

    @property
    def intra_archive_estimate(self) -> int:
        return sum(
            group.estimated_redundant_compressed_bytes
            for group in self.intra_archive_groups
        )


def audit_contents(
    rows: list[sqlite3.Row],
    *,
    minimum_size: int,
    skip_paths: set[str] | None = None,
) -> ContentAudit:
    skip_paths = skip_paths or set()
    # One occurrence per archive is used for cross-archive estimates. Repeated
    # paths inside one archive are accounted for separately.
    across: dict[tuple[int, int], dict[str, ContentOccurrence]] = {}
    intra: list[IntraArchiveGroup] = []
    scanned = skipped = unreadable = considered = 0

    for row in rows:
        if row["path"] in skip_paths:
            skipped += 1
            continue
        archive_path = Path(row["path"])
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and info.file_size >= minimum_size
                ]
        except (OSError, zipfile.BadZipFile):
            unreadable += 1
            continue
        scanned += 1
        considered += len(infos)

        within: dict[tuple[int, int], list[zipfile.ZipInfo]] = {}
        for info in infos:
            key = (info.file_size, info.CRC)
            within.setdefault(key, []).append(info)

        for (size, crc), matches in within.items():
            ordered = sorted(matches, key=lambda info: info.compress_size)
            representative = ordered[0]
            occurrence = ContentOccurrence(
                archive_path=row["path"],
                archive_relative=row["relative_path"],
                entry_name=representative.filename,
                compressed_size=representative.compress_size,
            )
            across.setdefault((size, crc), {})[row["path"]] = occurrence
            if len(ordered) > 1:
                intra.append(
                    IntraArchiveGroup(
                        archive_relative=row["relative_path"],
                        uncompressed_size=size,
                        crc32=crc,
                        extra_entries=len(ordered) - 1,
                        estimated_redundant_compressed_bytes=sum(
                            info.compress_size for info in ordered[1:]
                        ),
                        entry_names=tuple(info.filename for info in ordered[:5]),
                    )
                )

    cross: list[ContentGroup] = []
    for (size, crc), by_archive in across.items():
        if len(by_archive) < 2:
            continue
        occurrences = sorted(
            by_archive.values(),
            key=lambda item: (item.compressed_size, item.archive_relative.casefold()),
        )
        cross.append(
            ContentGroup(
                uncompressed_size=size,
                crc32=crc,
                archive_count=len(occurrences),
                estimated_redundant_compressed_bytes=sum(
                    item.compressed_size for item in occurrences[1:]
                ),
                samples=tuple(occurrences[:4]),
            )
        )

    cross.sort(
        key=lambda group: (
            -group.estimated_redundant_compressed_bytes,
            -group.archive_count,
        )
    )
    intra.sort(
        key=lambda group: (
            -group.estimated_redundant_compressed_bytes,
            group.archive_relative.casefold(),
        )
    )
    return ContentAudit(
        archives_scanned=scanned,
        archives_skipped=skipped,
        unreadable_archives=unreadable,
        entries_considered=considered,
        cross_archive_groups=tuple(cross),
        intra_archive_groups=tuple(intra),
    )

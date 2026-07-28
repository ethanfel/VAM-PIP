from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA_VERSION = 3


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS package_files (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    basename TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    device INTEGER NOT NULL,
    inode INTEGER NOT NULL,
    creator TEXT,
    package_name TEXT,
    version INTEGER,
    version_text TEXT,
    canonical_filename TEXT,
    valid INTEGER NOT NULL,
    error TEXT,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    sha256 TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    scan_generation TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_package_root ON package_files(root);
CREATE INDEX IF NOT EXISTS idx_package_identity
    ON package_files(creator, package_name, version_text);
CREATE INDEX IF NOT EXISTS idx_package_sha256 ON package_files(sha256);

CREATE TABLE IF NOT EXISTS manager_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manager_pins (
    root_ref TEXT PRIMARY KEY COLLATE NOCASE,
    label TEXT,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manager_leases (
    id TEXT PRIMARY KEY,
    label TEXT,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_manager_leases_expiry
    ON manager_leases(expires_utc);

CREATE TABLE IF NOT EXISTS manager_lease_roots (
    lease_id TEXT NOT NULL REFERENCES manager_leases(id) ON DELETE CASCADE,
    root_ref TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (lease_id, root_ref)
);
CREATE INDEX IF NOT EXISTS idx_manager_lease_roots_ref
    ON manager_lease_roots(root_ref);

CREATE TABLE IF NOT EXISTS manager_lease_packages (
    lease_id TEXT NOT NULL REFERENCES manager_leases(id) ON DELETE CASCADE,
    package_id TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (lease_id, package_id)
);
CREATE INDEX IF NOT EXISTS idx_manager_lease_packages_id
    ON manager_lease_packages(package_id);

CREATE TABLE IF NOT EXISTS manager_baseline (
    root TEXT NOT NULL,
    logical_relative_path TEXT NOT NULL,
    package_id TEXT NOT NULL COLLATE NOCASE,
    baseline_enabled INTEGER NOT NULL,
    recorded_utc TEXT NOT NULL,
    PRIMARY KEY (root, logical_relative_path)
);

CREATE TABLE IF NOT EXISTS catalog_resources (
    id INTEGER PRIMARY KEY,
    root TEXT NOT NULL,
    source TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    creator TEXT NOT NULL,
    package_name TEXT NOT NULL,
    versions_json TEXT NOT NULL DEFAULT '[]',
    resource_path TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    atom_type TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    imported_utc TEXT NOT NULL,
    UNIQUE(root, source, resource_key)
);
CREATE INDEX IF NOT EXISTS idx_catalog_root_type
    ON catalog_resources(root, resource_type);
CREATE INDEX IF NOT EXISTS idx_catalog_root_creator
    ON catalog_resources(root, creator);
CREATE INDEX IF NOT EXISTS idx_catalog_root_family
    ON catalog_resources(root, creator, package_name);

CREATE TABLE IF NOT EXISTS catalog_resource_versions (
    resource_id INTEGER NOT NULL
        REFERENCES catalog_resources(id) ON DELETE CASCADE,
    version_text TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (resource_id, version_text)
);
CREATE INDEX IF NOT EXISTS idx_catalog_resource_versions_version
    ON catalog_resource_versions(version_text, resource_id);

CREATE TABLE IF NOT EXISTS catalog_sources (
    root TEXT NOT NULL,
    source TEXT NOT NULL,
    source_path TEXT NOT NULL,
    imported_utc TEXT NOT NULL,
    resource_count INTEGER NOT NULL,
    PRIMARY KEY (root, source)
);

"""


def database_path(state_dir: Path) -> Path:
    return state_dir / "inventory.sqlite3"


@contextmanager
def connect(state_dir: Path) -> Iterator[sqlite3.Connection]:
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        state_dir.chmod(0o700)
    except OSError:
        # Some mounted Windows filesystems do not implement Unix mode bits.
        # Loopback authentication remains enforced in that environment.
        pass
    path = database_path(state_dir)
    connection = sqlite3.connect(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(package_files)")
    }
    if "enabled" not in columns:
        connection.execute(
            "ALTER TABLE package_files ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1"
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_package_resource_resolution
        ON package_files(
            root,
            creator COLLATE NOCASE,
            package_name COLLATE NOCASE,
            version_text COLLATE NOCASE,
            valid,
            enabled
        )
        """
    )
    stored_version = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if stored_version is not None and int(stored_version["value"]) > SCHEMA_VERSION:
        connection.close()
        raise sqlite3.DatabaseError(
            "VAM-PIP state was created by a newer, incompatible version"
        )
    connection.execute(
        """
        INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

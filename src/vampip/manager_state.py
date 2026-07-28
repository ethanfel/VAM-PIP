from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import secrets
import sqlite3
import uuid

from vampip.analysis import package_id
from vampip.profiles import Resolution, resolve
from vampip.switching import logical_relative_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _as_utc(parsed)


def get_setting(
    connection: sqlite3.Connection, key: str, default: object = None
) -> object:
    row = connection.execute(
        "SELECT value_json FROM manager_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value_json"])
    except json.JSONDecodeError:
        return default


def set_setting(
    connection: sqlite3.Connection,
    key: str,
    value: object,
    *,
    now: datetime | None = None,
) -> None:
    timestamp = _as_utc(now or utc_now()).isoformat()
    connection.execute(
        """
        INSERT INTO manager_settings(key, value_json, updated_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_utc = excluded.updated_utc
        """,
        (key, json.dumps(value, ensure_ascii=False), timestamp),
    )


def get_or_create_api_token(connection: sqlite3.Connection) -> str:
    existing = get_setting(connection, "api_token")
    if isinstance(existing, str) and len(existing) >= 32:
        return existing
    token = secrets.token_urlsafe(32)
    set_setting(connection, "api_token", token)
    return token


def add_pin(
    connection: sqlite3.Connection,
    root_ref: str,
    *,
    label: str | None = None,
    now: datetime | None = None,
) -> None:
    reference = root_ref.strip()
    if not reference:
        raise ValueError("pin package reference cannot be empty")
    connection.execute(
        """
        INSERT INTO manager_pins(root_ref, label, created_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(root_ref) DO UPDATE SET label = excluded.label
        """,
        (reference, label, _as_utc(now or utc_now()).isoformat()),
    )


def remove_pin(connection: sqlite3.Connection, root_ref: str) -> bool:
    cursor = connection.execute(
        "DELETE FROM manager_pins WHERE root_ref = ? COLLATE NOCASE",
        (root_ref.strip(),),
    )
    return cursor.rowcount > 0


def list_pins(connection: sqlite3.Connection) -> list[dict[str, object]]:
    return [
        {
            "root_ref": row["root_ref"],
            "label": row["label"],
            "created_utc": row["created_utc"],
        }
        for row in connection.execute(
            "SELECT * FROM manager_pins ORDER BY root_ref COLLATE NOCASE"
        )
    ]


def create_lease(
    connection: sqlite3.Connection,
    roots: list[str],
    resolution: Resolution,
    *,
    days: float = 3,
    label: str | None = None,
    now: datetime | None = None,
) -> str:
    if not 0 < days <= 3650:
        raise ValueError("lease duration must be greater than 0 and at most 3650 days")
    normalized_roots = list(
        dict.fromkeys(root.strip() for root in roots if root.strip())
    )
    if not normalized_roots:
        raise ValueError("a lease needs at least one package root")
    if resolution.missing:
        summary = ", ".join(reference for _, reference in resolution.missing[:10])
        raise ValueError(f"cannot lease unresolved packages: {summary}")
    if not resolution.selected:
        raise ValueError("lease roots resolved to no installed packages")

    created = _as_utc(now or utc_now())
    expires = created + timedelta(days=days)
    lease_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO manager_leases(id, label, created_utc, expires_utc)
        VALUES (?, ?, ?, ?)
        """,
        (lease_id, label, created.isoformat(), expires.isoformat()),
    )
    connection.executemany(
        "INSERT INTO manager_lease_roots(lease_id, root_ref) VALUES (?, ?)",
        ((lease_id, root) for root in normalized_roots),
    )
    connection.executemany(
        "INSERT INTO manager_lease_packages(lease_id, package_id) VALUES (?, ?)",
        ((lease_id, package_id(row)) for row in resolution.selected),
    )
    return lease_id


def renew_lease(
    connection: sqlite3.Connection,
    lease_id: str,
    *,
    days: float = 3,
    now: datetime | None = None,
) -> str:
    if not 0 < days <= 3650:
        raise ValueError("lease duration must be greater than 0 and at most 3650 days")
    row = connection.execute(
        "SELECT expires_utc FROM manager_leases WHERE id = ?", (lease_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown lease: {lease_id}")
    current = _as_utc(now or utc_now())
    existing_expiry = _parse_utc(row["expires_utc"])
    base = max(current, existing_expiry)
    expires = base + timedelta(days=days)
    connection.execute(
        "UPDATE manager_leases SET expires_utc = ? WHERE id = ?",
        (expires.isoformat(), lease_id),
    )
    return expires.isoformat()


def remove_lease(connection: sqlite3.Connection, lease_id: str) -> bool:
    cursor = connection.execute("DELETE FROM manager_leases WHERE id = ?", (lease_id,))
    return cursor.rowcount > 0


def remove_expired_leases(
    connection: sqlite3.Connection, *, now: datetime | None = None
) -> int:
    current = _as_utc(now or utc_now())
    expired = [
        row["id"]
        for row in connection.execute("SELECT id, expires_utc FROM manager_leases")
        if _parse_utc(row["expires_utc"]) <= current
    ]
    if expired:
        connection.executemany(
            "DELETE FROM manager_leases WHERE id = ?",
            ((lease_id,) for lease_id in expired),
        )
    return len(expired)


def list_leases(
    connection: sqlite3.Connection, *, now: datetime | None = None
) -> list[dict[str, object]]:
    current = _as_utc(now or utc_now())
    leases: list[dict[str, object]] = []
    rows = connection.execute(
        "SELECT * FROM manager_leases ORDER BY expires_utc, id"
    ).fetchall()
    for row in rows:
        roots = [
            item["root_ref"]
            for item in connection.execute(
                """
                SELECT root_ref FROM manager_lease_roots
                WHERE lease_id = ? ORDER BY root_ref COLLATE NOCASE
                """,
                (row["id"],),
            )
        ]
        packages = [
            item["package_id"]
            for item in connection.execute(
                """
                SELECT package_id FROM manager_lease_packages
                WHERE lease_id = ? ORDER BY package_id COLLATE NOCASE
                """,
                (row["id"],),
            )
        ]
        expiry = _parse_utc(row["expires_utc"])
        leases.append(
            {
                "id": row["id"],
                "label": row["label"],
                "created_utc": row["created_utc"],
                "expires_utc": row["expires_utc"],
                "expired": expiry <= current,
                "roots": roots,
                "packages": packages,
            }
        )
    return leases


def resolve_managed_set(
    connection: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    extra_roots: list[str] | tuple[str, ...] = (),
    now: datetime | None = None,
) -> tuple[list[str], tuple[tuple[str, str], ...]]:
    """Resolve pins and union them with exact snapshots from active leases."""

    current = _as_utc(now or utc_now())
    pin_roots = [
        row["root_ref"]
        for row in connection.execute(
            "SELECT root_ref FROM manager_pins ORDER BY root_ref COLLATE NOCASE"
        )
    ]
    known_roots = {root.casefold() for root in pin_roots}
    for root in extra_roots:
        normalized = root.strip()
        if normalized and normalized.casefold() not in known_roots:
            pin_roots.append(normalized)
            known_roots.add(normalized.casefold())
    pin_resolution = resolve(pin_roots, rows)
    desired = {
        package_id(row).casefold(): package_id(row) for row in pin_resolution.selected
    }

    for row in connection.execute(
        """
        SELECT p.package_id, MAX(l.expires_utc) AS last_expiry
        FROM manager_lease_packages AS p
        JOIN manager_leases AS l ON l.id = p.lease_id
        GROUP BY p.package_id COLLATE NOCASE
        """
    ):
        package = row["package_id"]
        if _parse_utc(row["last_expiry"]) > current:
            desired.setdefault(package.casefold(), package)

    return (
        sorted(desired.values(), key=str.casefold),
        pin_resolution.missing,
    )


def ensure_baseline(
    connection: sqlite3.Connection,
    root: str,
    rows: list[sqlite3.Row],
    *,
    now: datetime | None = None,
) -> int:
    recorded = _as_utc(now or utc_now()).isoformat()
    added = 0
    for row in rows:
        if not row["valid"] or not row["version_text"]:
            continue
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO manager_baseline(
                root, logical_relative_path, package_id,
                baseline_enabled, recorded_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                root,
                logical_relative_path(row),
                package_id(row),
                int(bool(row["enabled"])),
                recorded,
            ),
        )
        added += cursor.rowcount
    return added


def load_baseline(connection: sqlite3.Connection, root: str) -> dict[str, bool]:
    return {
        row["logical_relative_path"]: bool(row["baseline_enabled"])
        for row in connection.execute(
            """
            SELECT logical_relative_path, baseline_enabled
            FROM manager_baseline WHERE root = ?
            """,
            (root,),
        )
    }


def clear_baseline(connection: sqlite3.Connection, root: str) -> int:
    cursor = connection.execute("DELETE FROM manager_baseline WHERE root = ?", (root,))
    return cursor.rowcount

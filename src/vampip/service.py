from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Callable

from vampip.analysis import family_id, package_id
from vampip.bridge import read_bridge_status, request_rescan
from vampip.catalog import (
    catalog_facets as load_catalog_facets,
    get_resource_thumbnail,
    import_browserassist,
    search_resources as find_catalog_resources,
)
from vampip.database import connect
from vampip.inventory import ScanResult, ensure_hashes, rows_for_root, scan
from vampip.manager_state import (
    add_pin,
    clear_baseline,
    create_lease,
    ensure_baseline,
    get_setting,
    list_leases,
    list_pins,
    load_baseline,
    remove_lease,
    remove_expired_leases,
    remove_pin,
    renew_lease,
    resolve_managed_set,
    set_setting,
)
from vampip.profiles import preferred, resolve
from vampip.references import resource_package_roots
from vampip.runtime import derive_vam_root, find_vam_processes
from vampip.switching import (
    SwitchPlan,
    apply_switch,
    build_baseline_restore_plan,
    build_switch_plan,
    manager_lock,
)


class ManagerService:
    """High-level, daemon-optional manager operations.

    All mutating methods work without the web server, which keeps the existing
    CLI useful for recovery. Filesystem switches are serialized with a Linux
    advisory lock and journalled before the first rename.
    """

    def __init__(
        self,
        addon_dir: Path,
        state_dir: Path,
        *,
        vam_root: Path | None = None,
        process_probe: Callable[[], list[int]] | None = None,
    ) -> None:
        self.addon_dir = addon_dir.expanduser().resolve()
        self.state_dir = state_dir.expanduser().resolve()
        self.vam_root = (
            vam_root.expanduser().resolve()
            if vam_root is not None
            else derive_vam_root(self.addon_dir)
        )
        self._process_probe = process_probe or find_vam_processes

    def _rows(
        self, connection: sqlite3.Connection, *, refresh: bool
    ) -> tuple[list[sqlite3.Row], ScanResult | None]:
        existing = rows_for_root(connection, self.addon_dir)
        result = None
        if refresh or not existing:
            result = scan(self.addon_dir, connection)
            existing = rows_for_root(connection, self.addon_dir)
        return existing, result

    def scan_packages(self) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, result = self._rows(connection, refresh=True)
        assert result is not None
        return {
            "found": result.found,
            "inspected": result.inspected,
            "cached": result.unchanged,
            "invalid": result.invalid,
            "vanished": result.removed,
            "elapsed": result.elapsed,
            "active": sum(bool(row["enabled"]) for row in rows),
        }

    def import_catalog(self) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                self._rows(connection, refresh=True)
                result = import_browserassist(connection, self.vam_root)
        document = asdict(result)
        document["source_path"] = str(result.source_path)
        return document

    def search_resources(
        self,
        *,
        query: str = "",
        resource_type: str = "",
        state: str = "all",
        favorite: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        if state not in {"all", "active", "hidden", "missing", "local"}:
            raise ValueError(
                "resource state must be all, active, hidden, missing, or local"
            )
        with connect(self.state_dir) as connection:
            result = find_catalog_resources(
                connection,
                self.vam_root,
                query=query,
                resource_type=resource_type or None,
                favorite=favorite,
                addon_root=self.addon_dir,
                package_state=None if state == "all" else state,
                limit=limit,
                offset=offset,
            )
            for item in result["items"]:
                if bool(item.get("missing")):
                    item["state"] = "missing"
                    item["active"] = False
                elif bool(item.get("local")):
                    item["state"] = "local"
                    item["active"] = True
                else:
                    item["state"] = "active" if bool(item.get("enabled")) else "hidden"
                    item["active"] = bool(item.get("enabled"))
        return result

    def catalog_facets(self) -> dict[str, object]:
        with connect(self.state_dir) as connection:
            return load_catalog_facets(connection, self.vam_root)

    def resource_thumbnail(self, resource_id: int) -> tuple[Path, str] | None:
        with connect(self.state_dir) as connection:
            result = get_resource_thumbnail(
                connection,
                self.vam_root,
                resource_id,
                self.state_dir / "thumbnails",
                addon_root=self.addon_dir,
            )
        if result is None:
            return None
        return result.path, result.content_type

    def lease_resource(
        self,
        resource_id: int,
        *,
        days: float = 3,
        label: str | None = None,
        apply: bool = True,
    ) -> dict[str, object]:
        with connect(self.state_dir) as connection:
            self._rows(connection, refresh=False)
            roots = resource_package_roots(
                connection,
                self.vam_root,
                int(resource_id),
                addon_root=self.addon_dir,
            )
            row = connection.execute(
                """
                SELECT resource_path FROM catalog_resources
                WHERE id = ? AND root = ?
                """,
                (int(resource_id), str(self.vam_root)),
            ).fetchone()
        if not roots:
            return {
                "resource_id": int(resource_id),
                "lease_id": None,
                "roots": [],
                "resolved_packages": 0,
                "applied": False,
                "already_local": True,
            }
        if label is None and row is not None:
            label = Path(
                str(row["resource_path"]).replace("\\", "/")
            ).stem.removeprefix("Preset_")
        result = self.lease(
            roots,
            days=days,
            label=label,
            apply=apply,
        )
        result["resource_id"] = int(resource_id)
        result["discovered_roots"] = roots
        return result

    def _running_pids(self) -> list[int]:
        return self._process_probe()

    def _verify_desired_copies(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
        desired_ids: list[str],
    ) -> list[sqlite3.Row]:
        """Hash only ambiguous desired copies and reject content conflicts."""

        desired = {identity.casefold() for identity in desired_ids}
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            if row["valid"] and row["version_text"]:
                key = package_id(row).casefold()
                if key in desired:
                    grouped.setdefault(key, []).append(row)

        hash_rows: list[sqlite3.Row] = []
        for group in grouped.values():
            if len(group) > 1 and len({row["size"] for row in group}) == 1:
                hash_rows.extend(row for row in group if not row["sha256"])
        if hash_rows:
            ensure_hashes(connection, hash_rows)
            rows = rows_for_root(connection, self.addon_dir)

        grouped.clear()
        for row in rows:
            if row["valid"] and row["version_text"]:
                key = package_id(row).casefold()
                if key in desired:
                    grouped.setdefault(key, []).append(row)
        conflicts: list[str] = []
        for group in grouped.values():
            if len(group) < 2:
                continue
            signatures = {(row["size"], row["sha256"]) for row in group}
            if len(signatures) > 1:
                conflicts.append(package_id(group[0]))
        if conflicts:
            raise ValueError(
                "same-ID packages contain different data: "
                + ", ".join(sorted(conflicts, key=str.casefold)[:10])
            )
        return rows

    def status(self, *, refresh_if_empty: bool = True) -> dict[str, object]:
        with connect(self.state_dir) as connection:
            rows, scan_result = self._rows(
                connection,
                refresh=refresh_if_empty
                and not rows_for_root(connection, self.addon_dir),
            )
            managed_mode = bool(get_setting(connection, "managed_mode", False))
            auto_reconcile = bool(get_setting(connection, "auto_reconcile", True))
            pins = list_pins(connection)
            leases = list_leases(connection)
            catalog_count = connection.execute(
                "SELECT COUNT(*) FROM catalog_resources WHERE root = ?",
                (str(self.vam_root),),
            ).fetchone()[0]
            baseline_count = connection.execute(
                "SELECT COUNT(*) FROM manager_baseline WHERE root = ?",
                (str(self.addon_dir),),
            ).fetchone()[0]
            pending_disable = 0
            pending_enable = 0
            missing: tuple[tuple[str, str], ...] = ()
            if managed_mode:
                desired, missing = resolve_managed_set(connection, rows)
                try:
                    pending_plan = build_switch_plan(
                        rows, desired, disable_unselected=True
                    )
                    pending_disable = len(pending_plan.to_disable)
                    pending_enable = len(pending_plan.to_enable)
                except ValueError:
                    pending_disable = 0
                    pending_enable = 0
        pids = self._running_pids()
        return {
            "addon_dir": str(self.addon_dir),
            "vam_root": str(self.vam_root),
            "state_dir": str(self.state_dir),
            "managed_mode": managed_mode,
            "auto_reconcile": auto_reconcile,
            "packages": {
                "total": len(rows),
                "valid": sum(bool(row["valid"]) for row in rows),
                "invalid": sum(not bool(row["valid"]) for row in rows),
                "active": sum(bool(row["enabled"]) for row in rows),
                "hidden": sum(not bool(row["enabled"]) for row in rows),
            },
            "pins": pins,
            "leases": leases,
            "baseline_count": baseline_count,
            "catalog_resources": catalog_count,
            "pending_enable": pending_enable,
            "pending_disable": pending_disable,
            "missing_pins": [
                {"required_by": owner, "reference": reference}
                for owner, reference in missing
            ],
            "vam": {
                "running": bool(pids),
                "pids": pids,
            },
            "bridge": read_bridge_status(self.vam_root),
            "initial_scan": (
                {
                    "found": scan_result.found,
                    "elapsed": scan_result.elapsed,
                }
                if scan_result is not None
                else None
            ),
        }

    def list_packages(
        self,
        *,
        query: str = "",
        state: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        if state not in {"all", "active", "hidden", "invalid"}:
            raise ValueError("package state must be all, active, hidden, or invalid")
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        needle = query.strip().casefold()
        with connect(self.state_dir) as connection:
            rows, _ = self._rows(connection, refresh=False)

        grouped: dict[str, list[sqlite3.Row]] = {}
        invalid: list[sqlite3.Row] = []
        for row in rows:
            if not row["valid"] or not row["version_text"]:
                invalid.append(row)
                continue
            grouped.setdefault(package_id(row).casefold(), []).append(row)

        items: list[dict[str, object]] = []
        for group in grouped.values():
            selected = preferred(group)
            identity = package_id(selected)
            active = any(bool(row["enabled"]) for row in group)
            if needle and needle not in identity.casefold():
                continue
            if state == "active" and not active:
                continue
            if state == "hidden" and active:
                continue
            if state == "invalid":
                continue
            try:
                dependencies = json.loads(selected["dependencies_json"])
            except json.JSONDecodeError:
                dependencies = []
            items.append(
                {
                    "id": identity,
                    "family": family_id(selected),
                    "creator": selected["creator"],
                    "package": selected["package_name"],
                    "version": selected["version_text"],
                    "active": active,
                    "valid": True,
                    "size": selected["size"],
                    "relative_path": selected["relative_path"],
                    "copies": len(group),
                    "dependencies": dependencies,
                }
            )
        if state in {"all", "invalid"}:
            for row in invalid:
                identity = row["basename"]
                if needle and needle not in identity.casefold():
                    continue
                items.append(
                    {
                        "id": identity,
                        "family": None,
                        "creator": None,
                        "package": None,
                        "version": None,
                        "active": bool(row["enabled"]),
                        "valid": False,
                        "size": row["size"],
                        "relative_path": row["relative_path"],
                        "copies": 1,
                        "dependencies": [],
                        "error": row["error"],
                    }
                )
        items.sort(key=lambda item: str(item["id"]).casefold())
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def pin(
        self,
        roots: list[str],
        *,
        label: str | None = None,
        apply: bool = False,
    ) -> dict[str, object]:
        if not roots:
            raise ValueError("at least one package reference is required")
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, _ = self._rows(connection, refresh=True)
                resolution = resolve(roots, rows)
                if resolution.missing:
                    summary = ", ".join(
                        reference for _, reference in resolution.missing[:10]
                    )
                    raise ValueError(f"cannot pin unresolved packages: {summary}")
                rows = self._verify_desired_copies(
                    connection,
                    rows,
                    [package_id(row) for row in resolution.selected],
                )
                for root in roots:
                    add_pin(connection, root, label=label)
        result: dict[str, object] = {
            "roots": roots,
            "resolved_packages": len(resolution.selected),
        }
        if apply:
            result["reconcile"] = self.reconcile(apply=True)
        return result

    def unpin(self, root: str, *, apply: bool = False) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                removed = remove_pin(connection, root)
        result: dict[str, object] = {"removed": removed, "root": root}
        if apply and removed:
            result["reconcile"] = self.reconcile(apply=True)
        return result

    def lease(
        self,
        roots: list[str],
        *,
        days: float = 3,
        label: str | None = None,
        apply: bool = True,
    ) -> dict[str, object]:
        if not roots:
            raise ValueError("at least one package reference is required")
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, _ = self._rows(connection, refresh=True)
                resolution = resolve(roots, rows)
                rows = self._verify_desired_copies(
                    connection,
                    rows,
                    [package_id(row) for row in resolution.selected],
                )
                resolution = resolve(roots, rows)
                lease_id = create_lease(
                    connection,
                    roots,
                    resolution,
                    days=days,
                    label=label,
                )
                managed_mode = bool(get_setting(connection, "managed_mode", False))
        result: dict[str, object] = {
            "lease_id": lease_id,
            "roots": roots,
            "resolved_packages": len(resolution.selected),
            "applied": False,
        }
        if apply:
            if not managed_mode:
                with connect(self.state_dir) as connection:
                    remove_lease(connection, lease_id)
                raise ValueError(
                    "managed mode is not active; configure pins and activate it first"
                )
            result["reconcile"] = self.reconcile(apply=True)
            result["applied"] = True
        return result

    def renew(self, lease_id: str, *, days: float = 3) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                expires = renew_lease(connection, lease_id, days=days)
        return {"lease_id": lease_id, "expires_utc": expires}

    def release(self, lease_id: str, *, apply: bool = True) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                removed = remove_lease(connection, lease_id)
        result: dict[str, object] = {"lease_id": lease_id, "removed": removed}
        if apply and removed:
            result["reconcile"] = self.reconcile(apply=True)
        return result

    @staticmethod
    def _plan_document(
        plan: SwitchPlan,
        *,
        running: bool,
        pending_disable: int,
        manifest: Path | None = None,
        bridge_request: str | None = None,
        expired_leases_removed: int = 0,
    ) -> dict[str, object]:
        return {
            "desired_packages": len(plan.desired_ids),
            "enable": len(plan.to_enable),
            "disable": len(plan.to_disable),
            "pending_disable": pending_disable,
            "vam_running": running,
            "manifest": str(manifest) if manifest else None,
            "bridge_request": bridge_request,
            "expired_leases_removed": expired_leases_removed,
        }

    def reconcile(
        self,
        *,
        apply: bool,
        activate: bool = False,
    ) -> dict[str, object]:
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, _ = self._rows(connection, refresh=True)
                root_text = str(self.addon_dir)
                managed_mode = bool(get_setting(connection, "managed_mode", False))
                activating = activate and not managed_mode
                if not managed_mode and not activating:
                    if apply:
                        raise ValueError(
                            "managed mode is not active; activate it explicitly first"
                        )
                    return {
                        "managed_mode": False,
                        "desired_packages": 0,
                        "enable": 0,
                        "disable": 0,
                        "pending_disable": 0,
                        "vam_running": bool(self._running_pids()),
                        "manifest": None,
                        "bridge_request": None,
                    }

                desired, missing = resolve_managed_set(connection, rows)
                if missing:
                    summary = ", ".join(reference for _, reference in missing[:10])
                    raise ValueError(f"pinned package resolution failed: {summary}")
                rows = self._verify_desired_copies(connection, rows, desired)

                full_plan = build_switch_plan(rows, desired, disable_unselected=True)
                pids = self._running_pids()
                running = bool(pids)
                plan = (
                    build_switch_plan(rows, desired, disable_unselected=False)
                    if running
                    else full_plan
                )
                pending_disable = len(full_plan.to_disable) if running else 0
                if not apply:
                    return self._plan_document(
                        plan,
                        running=running,
                        pending_disable=pending_disable,
                    )

                # Persist the rollback baseline before the first filesystem
                # rename, but only for a real activation. A dry-run activation
                # must remain entirely read-only.
                ensure_baseline(connection, root_text, rows)
                if activating:
                    connection.commit()
                manifest = apply_switch(
                    self.state_dir,
                    self.addon_dir,
                    plan,
                    run_name="managed-reconcile",
                    allow_disable=not running,
                    lock_held=True,
                )
                if activating:
                    set_setting(connection, "managed_mode", True)
                    connection.commit()
                if manifest is not None:
                    scan(self.addon_dir, connection)
                expired_leases_removed = (
                    remove_expired_leases(connection) if not running else 0
                )

        bridge_request = None
        if running and plan.to_enable:
            bridge_request = request_rescan(self.vam_root)
        return self._plan_document(
            plan,
            running=running,
            pending_disable=pending_disable,
            manifest=manifest,
            bridge_request=bridge_request,
            expired_leases_removed=expired_leases_removed,
        )

    def deactivate(self, *, apply: bool) -> dict[str, object]:
        pids = self._running_pids()
        if pids and apply:
            raise ValueError("close VaM before restoring the pre-manager package set")
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, _ = self._rows(connection, refresh=True)
                managed_mode = bool(get_setting(connection, "managed_mode", False))
                baseline = load_baseline(connection, str(self.addon_dir))
                if not baseline:
                    if managed_mode:
                        raise ValueError(
                            "cannot restore the pre-manager package set because "
                            "its baseline is missing; use a manager switch "
                            "manifest for recovery"
                        )
                    return {
                        "managed_mode": False,
                        "enable": 0,
                        "disable": 0,
                        "manifest": None,
                    }
                plan = build_baseline_restore_plan(rows, baseline)
                if not apply:
                    return {
                        "managed_mode": True,
                        "enable": len(plan.to_enable),
                        "disable": len(plan.to_disable),
                        "manifest": None,
                    }
                manifest = apply_switch(
                    self.state_dir,
                    self.addon_dir,
                    plan,
                    run_name="restore-baseline",
                    allow_disable=True,
                    lock_held=True,
                )
                if manifest is not None:
                    scan(self.addon_dir, connection)
                clear_baseline(connection, str(self.addon_dir))
                set_setting(connection, "managed_mode", False)
        return {
            "managed_mode": False,
            "enable": len(plan.to_enable),
            "disable": len(plan.to_disable),
            "manifest": str(manifest) if manifest else None,
        }

    def set_auto_reconcile(self, enabled: bool) -> None:
        with connect(self.state_dir) as connection:
            set_setting(connection, "auto_reconcile", bool(enabled))

    def auto_reconcile_enabled(self) -> bool:
        with connect(self.state_dir) as connection:
            return bool(get_setting(connection, "auto_reconcile", True))

    def launch_vam(self, *, reconcile: bool = True) -> dict[str, object]:
        pids = self._running_pids()
        if pids:
            raise ValueError(
                "VaM is already running with process IDs " + ", ".join(map(str, pids))
            )

        reconcile_result = None
        with connect(self.state_dir) as connection:
            managed_mode = bool(get_setting(connection, "managed_mode", False))
            configured = get_setting(connection, "launch_script")
        if reconcile and managed_mode:
            reconcile_result = self.reconcile(apply=True)

        if isinstance(configured, str) and configured.strip():
            script = Path(configured).expanduser().resolve()
        else:
            script = (self.vam_root / "launch-vam-desktop-proton.sh").resolve()
        if not script.is_file():
            raise FileNotFoundError(
                "VaM launch script was not found; expected " + str(script)
            )
        if not script.is_relative_to(self.vam_root):
            raise ValueError("configured launch script must be inside the VaM folder")
        if not os.access(script, os.X_OK):
            raise ValueError(f"VaM launch script is not executable: {script}")

        log_path = self.vam_root / "logs" / "vampip-launch.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [str(script)],
                cwd=self.vam_root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return {
            "launched": True,
            "pid": process.pid,
            "script": str(script),
            "log": str(log_path),
            "reconcile": reconcile_result,
        }

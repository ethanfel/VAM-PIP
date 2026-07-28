from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
from typing import Callable
import uuid

from vampip.analysis import family_id, package_id
from vampip.bridge import (
    read_bridge_status,
    read_bridge_request,
    read_scene_status,
    request_add_person,
    request_person_preset,
    request_rescan,
    request_scene_load,
    request_select_atom,
    request_select_person,
)
from vampip.catalog import (
    catalog_facets as load_catalog_facets,
    get_resource_thumbnail,
    import_browserassist,
    resolve_resource_archive,
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
from vampip.models import parse_dependency_ref
from vampip.profiles import preferred, resolve
from vampip.references import resource_package_roots
from vampip.runtime import derive_vam_root, find_vam_processes
from vampip.session_plugins import (
    SessionPlugin,
    load_session_plugin_defaults,
)
from vampip.switching import (
    SwitchPlan,
    apply_switch,
    build_baseline_restore_plan,
    build_switch_plan,
    manager_lock,
    rollback_switch,
)


class LiveActionBusyError(RuntimeError):
    """Raised when an ordered VaM bridge action is still in flight."""


_PERSON_PRESET_CATEGORIES: tuple[dict[str, object], ...] = (
    {
        "id": "preset-appearance",
        "label": "Appearance presets",
        "resource_types": ("Preset Appearance",),
        "preset_kind": "appearance",
        "required_capability": "person-preset-appearance",
        "path_prefix": "Custom/Atom/Person/Appearance/",
        "risk": "high",
        "risk_reason": (
            "May replace morphs, hair, clothing, skin, materials, physics, and scale."
        ),
    },
    {
        "id": "preset-animation",
        "label": "Animation presets",
        "resource_types": ("Preset Animation",),
        "preset_kind": "animation",
        "required_capability": "person-preset-animation",
        "path_prefix": "Custom/Atom/Person/AnimationPresets/",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's animation preset.",
    },
    {
        "id": "preset-breast-physics",
        "label": "Breast physics presets",
        "resource_types": ("Preset Breast Physics",),
        "preset_kind": "breastPhysics",
        "required_capability": "person-preset-breast-physics",
        "path_prefix": "Custom/Atom/Person/BreastPhysics/",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's breast physics parameters.",
    },
    {
        "id": "preset-clothing",
        "label": "Clothing presets",
        "resource_types": ("Preset Clothing",),
        "preset_kind": "clothing",
        "required_capability": "person-preset-clothing",
        "path_prefix": "Custom/Atom/Person/Clothing/",
        "risk": "high",
        "risk_reason": "May replace or remove the selected Person's current clothing.",
    },
    {
        "id": "preset-general",
        "label": "General Person presets",
        "resource_types": ("Preset General",),
        "preset_kind": "general",
        "required_capability": "person-preset-general",
        "path_prefix": "Custom/Atom/Person/General/",
        "risk": "critical",
        "risk_reason": "May replace most of the selected Person, including plugins.",
    },
    {
        "id": "preset-glute-physics",
        "label": "Glute physics presets",
        "resource_types": ("Preset Glute Physics",),
        "preset_kind": "glutePhysics",
        "required_capability": "person-preset-glute-physics",
        "path_prefix": "Custom/Atom/Person/GlutePhysics/",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's glute physics parameters.",
    },
    {
        "id": "preset-hair",
        "label": "Hair presets",
        "resource_types": ("Preset Hair",),
        "preset_kind": "hair",
        "required_capability": "person-preset-hair",
        "path_prefix": "Custom/Atom/Person/Hair/",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's hair preset.",
    },
    {
        "id": "preset-morphs",
        "label": "Morph presets",
        "resource_types": ("Preset Morphs",),
        "preset_kind": "morphs",
        "required_capability": "person-preset-morphs",
        "path_prefix": "Custom/Atom/Person/Morphs/",
        "risk": "high",
        "risk_reason": "May substantially change appearance and physical morphs.",
    },
    {
        "id": "preset-plugins",
        "label": "Person plugin presets",
        "resource_types": ("Preset Plugins",),
        "preset_kind": "plugins",
        "required_capability": "person-preset-plugins",
        "path_prefix": "Custom/Atom/Person/Plugins/",
        "risk": "critical",
        "risk_reason": "Loads executable plugin code into the selected Person.",
    },
    {
        "id": "preset-pose",
        "label": "Pose presets",
        "resource_types": ("Preset Pose",),
        "preset_kind": "pose",
        "required_capability": "person-preset-pose",
        "path_prefix": "Custom/Atom/Person/Pose/",
        "risk": "high",
        "risk_reason": "May move controllers and change physics or lock state.",
    },
    {
        "id": "preset-skin",
        "label": "Skin presets",
        "resource_types": ("Preset Skin",),
        "preset_kind": "skin",
        "required_capability": "person-preset-skin",
        "path_prefix": "Custom/Atom/Person/Skin/",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's skin preset and materials.",
    },
)

_OTHER_WORKSPACE_CATEGORIES: tuple[dict[str, object], ...] = (
    {
        "id": "scene",
        "label": "Scenes",
        "group": "scenes",
        "resource_types": ("Scene",),
        "target_kind": "none",
        "operation": "load-scene",
        "required_capability": "scene-load",
        "risk": "critical",
        "risk_reason": "Replace mode discards the current scene; merge adds its contents.",
        "browseable": True,
        "live_action": True,
        "merge_supported": True,
    },
    {
        "id": "subscenes",
        "label": "SubScenes",
        "group": "scenes",
        "resource_types": ("SubScenes",),
        "target_kind": "subscene",
        "operation": "load-subscene",
        "required_capability": "subscene-load",
        "risk": "high",
        "risk_reason": "Creates or replaces a SubScene atom and its contents.",
        "browseable": True,
        "live_action": False,
        "merge_supported": False,
    },
    {
        "id": "custom-unity-assets",
        "label": "Custom Unity Assets",
        "group": "atoms",
        "resource_types": ("Custom Unity Assets",),
        "target_kind": "custom-unity-asset",
        "operation": "load-custom-unity-asset",
        "required_capability": "custom-unity-asset-load",
        "risk": "critical",
        "risk_reason": "Unity assets may contain executable plugin assemblies.",
        "browseable": True,
        "live_action": False,
        "merge_supported": False,
    },
    {
        "id": "plugins",
        "label": "Plugins",
        "group": "plugins",
        "resource_types": ("Plugins",),
        "target_kind": "plugin-target",
        "operation": "load-plugin",
        "required_capability": "plugin-apply",
        "risk": "critical",
        "risk_reason": "Loads executable plugin code with unknown target compatibility.",
        "browseable": True,
        "live_action": False,
        "merge_supported": True,
    },
    {
        "id": "clothing-items-female",
        "label": "Female clothing items",
        "group": "person",
        "resource_types": ("Clothing (Female)",),
        "target_kind": "person",
        "operation": "toggle-clothing-item",
        "required_capability": "person-clothing-item-toggle",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's active clothing items.",
        "browseable": True,
        "live_action": False,
        "merge_supported": False,
    },
    {
        "id": "clothing-items-male",
        "label": "Male clothing items",
        "group": "person",
        "resource_types": ("Clothing (Male)",),
        "target_kind": "person",
        "operation": "toggle-clothing-item",
        "required_capability": "person-clothing-item-toggle",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's active clothing items.",
        "browseable": True,
        "live_action": False,
        "merge_supported": False,
    },
    {
        "id": "clothing-item-presets",
        "label": "Clothing item presets",
        "group": "person",
        "resource_types": ("Clothing Item Presets",),
        "target_kind": "person-clothing-item",
        "operation": "load-clothing-item-preset",
        "required_capability": "person-clothing-item-preset",
        "risk": "medium",
        "risk_reason": "Changes materials or physics for a selected clothing item.",
        "browseable": True,
        "live_action": False,
        "merge_supported": True,
    },
)

_PERSON_PRESET_BY_RESOURCE_TYPE = {
    str(category["resource_types"][0]).casefold(): category
    for category in _PERSON_PRESET_CATEGORIES
}


def _atom_preset_category_id(atom_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", atom_type.casefold()).strip("-") or "atom"
    digest = hashlib.sha256(atom_type.casefold().encode("utf-8")).hexdigest()[:8]
    return f"preset-atom-{slug}-{digest}"


class ManagerService:
    """High-level, daemon-optional manager operations.

    All mutating methods work without the web server, which keeps the existing
    CLI useful for recovery. Filesystem switches are serialized with a Linux
    advisory lock and journalled before the first rename.
    """

    _TERMINAL_OPERATION_STATES = {
        "idle",
        "completed",
        "failed",
        "cancelled",
    }
    _OPERATION_COUNT_FIELDS = {
        "total",
        "completed",
        "enable_total",
        "disable_total",
        "enabled",
        "disabled",
    }

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
        self._instance_id = uuid.uuid4().hex
        # The file lock remains the cross-process safety boundary. This
        # in-process gate also lets the web auto-reconciler coalesce duplicate
        # requests and expose one canonical operation to the live UI.
        self._operation_gate = threading.RLock()
        # One re-entrant gate owns every in-process write to the bridge's
        # single request mailbox. Composite actions hold it across package
        # reconciliation and request publication so a standalone rescan
        # cannot replace an ordered live action (or vice versa).
        self._bridge_mailbox_lock = threading.RLock()
        self._activity_lock = threading.Lock()
        self._operation_sequence = 0
        self._operation: dict[str, object] = {
            "id": 0,
            "status": "idle",
            "run_name": None,
            "total": 0,
            "completed": 0,
            "enable_total": 0,
            "disable_total": 0,
            "enabled": 0,
            "disabled": 0,
            "manifest": None,
            "error": None,
        }

    def _begin_operation(self, run_name: str) -> int:
        with self._activity_lock:
            self._operation_sequence += 1
            operation_id = self._operation_sequence
            self._operation = {
                "id": operation_id,
                "status": "preparing",
                "run_name": run_name,
                "total": 0,
                "completed": 0,
                "enable_total": 0,
                "disable_total": 0,
                "enabled": 0,
                "disabled": 0,
                "manifest": None,
                "error": None,
            }
        return operation_id

    def _update_operation(
        self,
        operation_id: int,
        snapshot: dict[str, object],
    ) -> None:
        """Merge a best-effort switch callback into canonical live activity."""

        if not isinstance(snapshot, dict):
            return

        with self._activity_lock:
            if self._operation.get("id") != operation_id:
                return
            previous = dict(self._operation)

        updates: dict[str, object] = {}
        aliases = {
            "enable_total": ("enable_total", "enable"),
            "disable_total": ("disable_total", "disable"),
        }
        for key in self._OPERATION_COUNT_FIELDS:
            candidates = aliases.get(key, (key,))
            value = next(
                (snapshot[name] for name in candidates if name in snapshot),
                None,
            )
            if value is None:
                continue
            try:
                updates[key] = max(0, int(value))
            except (TypeError, ValueError):
                continue

        if "run_name" in snapshot:
            updates["run_name"] = str(snapshot["run_name"])
        if "manifest" in snapshot:
            manifest = snapshot["manifest"]
            updates["manifest"] = str(manifest) if manifest is not None else None
        if "error" in snapshot:
            updates["error"] = str(snapshot["error"])

        phase = str(snapshot.get("phase", "")).casefold()
        switch_status = str(snapshot.get("status", "")).casefold()
        if phase in {"preparing", "applying"}:
            updates["status"] = phase
        elif phase == "rolling-back":
            updates["status"] = "rolling-back"
        elif phase == "error":
            updates["status"] = "rolling-back"
        elif phase == "final" or switch_status in {"complete", "completed"}:
            # The filesystem work is followed by an inventory refresh. It is
            # only terminal once the whole service operation returns.
            updates["status"] = "finalizing"
        elif switch_status:
            updates["status"] = switch_status

        enable_total = int(
            updates.get(
                "enable_total",
                previous.get("enable_total", 0),
            )
        )
        disable_total = int(
            updates.get(
                "disable_total",
                previous.get("disable_total", 0),
            )
        )
        completed = int(
            updates.get(
                "completed",
                previous.get("completed", 0),
            )
        )
        updates.setdefault("enabled", min(enable_total, completed))
        updates.setdefault(
            "disabled",
            min(disable_total, max(0, completed - enable_total)),
        )

        with self._activity_lock:
            if self._operation.get("id") != operation_id:
                return
            self._operation.update(updates)

    def _finish_operation(
        self,
        operation_id: int,
        *,
        status: str,
        result: dict[str, object] | None = None,
        error: BaseException | None = None,
    ) -> None:
        with self._activity_lock:
            if self._operation.get("id") != operation_id:
                return
            if result is not None:
                enable = max(0, int(result.get("enable", 0)))
                disable = max(0, int(result.get("disable", 0)))
                self._operation.update(
                    {
                        "total": enable + disable,
                        "completed": enable + disable,
                        "enable_total": enable,
                        "disable_total": disable,
                        "enabled": enable,
                        "disabled": disable,
                        "manifest": result.get("manifest"),
                    }
                )
            self._operation["status"] = status
            self._operation["error"] = (
                f"{type(error).__name__}: {error}" if error is not None else None
            )

    def activity(self) -> dict[str, object]:
        """Report live VaM PIDs and switch progress without manager_lock()."""

        pids = list(self._running_pids())
        with self._activity_lock:
            operation = dict(self._operation)
        operation["busy"] = (
            str(operation.get("status", "")).casefold()
            not in self._TERMINAL_OPERATION_STATES
        )
        return {
            "manager_instance": self._instance_id,
            "vam": {
                "running": bool(pids),
                "pids": pids,
            },
            "operation": operation,
        }

    def persons(self) -> dict[str, object]:
        """Return the bridge-published scene snapshot without manager locks.

        The historical method name is retained for callers of
        ``/api/vam/persons``. New clients should use :meth:`scene`.
        """

        pids = list(self._running_pids())
        bridge = read_bridge_status(self.vam_root)
        request = read_bridge_request(self.vam_root)
        if request is not None and not self._bridge_request_is_terminal(
            request,
            bridge,
        ):
            queued_bridge = dict(bridge or {})
            request_id = str(request.get("requestId") or "")
            if str(queued_bridge.get("requestId") or "") != request_id:
                queued_bridge.update(
                    {
                        "requestId": request_id,
                        "state": "queued",
                        "ok": False,
                        "message": "Waiting for the VaM bridge to accept the request.",
                    }
                )
            bridge = queued_bridge
        scene = read_scene_status(self.vam_root)
        scene_fresh = False
        if scene:
            updated = scene.get("updatedAtUtc")
            if isinstance(updated, str):
                try:
                    parsed = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - parsed).total_seconds()
                    scene_fresh = -5 <= age <= 10
                except ValueError:
                    pass
        available = bool(
            pids
            and scene
            and scene_fresh
            and bridge
            and scene.get("instanceId") == bridge.get("instanceId")
        )
        return {
            "available": available,
            "vam_running": bool(pids),
            "loading": bool(scene.get("loading")) if available and scene else False,
            "selected_uid": (
                str(scene.get("selectedUid") or "") if available and scene else ""
            ),
            "atoms": (list(scene.get("atoms") or []) if available and scene else []),
            "persons": (
                list(scene.get("persons") or []) if available and scene else []
            ),
            "capabilities": (
                list(scene.get("capabilities") or []) if available and scene else []
            ),
            "bridge": bridge,
            "updated_at_utc": (
                scene.get("updatedAtUtc") if available and scene else None
            ),
        }

    def scene(self) -> dict[str, object]:
        """Return the canonical bridge-published live scene snapshot."""

        return self.persons()

    @staticmethod
    def _bridge_request_is_terminal(
        request: dict[str, object],
        status: dict[str, object] | None,
    ) -> bool:
        request_id = str(request.get("requestId") or "")
        return bool(
            request_id
            and status
            and str(status.get("requestId") or "") == request_id
            and str(status.get("state") or "").casefold() in {"ok", "error"}
        )

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
                result = import_browserassist(
                    connection,
                    self.vam_root,
                    addon_root=self.addon_dir,
                )
        document = asdict(result)
        document["source_path"] = str(result.source_path)
        return document

    def _workspace_category_descriptors(
        self,
        connection: sqlite3.Connection,
    ) -> list[dict[str, object]]:
        rows = list(
            connection.execute(
                """
                SELECT resource_type, atom_type,
                       COUNT(*) AS resource_count,
                       SUM(
                           CASE
                               WHEN creator = '' AND package_name = '' THEN 1
                               ELSE 0
                           END
                       ) AS local_count
                FROM catalog_resources
                WHERE root = ?
                GROUP BY resource_type COLLATE NOCASE, atom_type COLLATE NOCASE
                """,
                (str(self.vam_root),),
            )
        )
        counts: dict[tuple[str, str], tuple[int, int]] = {}
        atom_labels: dict[str, str] = {}
        for row in rows:
            resource_type = str(row["resource_type"])
            atom_type = str(row["atom_type"])
            key = (resource_type.casefold(), atom_type.casefold())
            count = int(row["resource_count"])
            local = int(row["local_count"] or 0)
            previous = counts.get(key, (0, 0))
            counts[key] = (previous[0] + count, previous[1] + local)
            if atom_type:
                atom_labels.setdefault(atom_type.casefold(), atom_type)

        def category_counts(
            resource_types: object,
            atom_types: object = (),
        ) -> tuple[int, int]:
            selected_resources = {
                str(value).casefold()
                for value in resource_types
                if isinstance(value, str)
            }
            selected_atoms = {
                str(value).casefold() for value in atom_types if isinstance(value, str)
            }
            total = 0
            local = 0
            for (resource_type, atom_type), values in counts.items():
                if resource_type not in selected_resources:
                    continue
                if selected_atoms and atom_type not in selected_atoms:
                    continue
                total += values[0]
                local += values[1]
            return total, local

        categories: list[dict[str, object]] = []
        for template in _OTHER_WORKSPACE_CATEGORIES:
            descriptor = dict(template)
            descriptor["resource_types"] = list(template["resource_types"])
            descriptor["atom_types"] = []
            total, local = category_counts(descriptor["resource_types"])
            descriptor.update(
                {
                    "count": total,
                    "local_count": local,
                    "packaged_count": total - local,
                }
            )
            categories.append(descriptor)

        for template in _PERSON_PRESET_CATEGORIES:
            descriptor = dict(template)
            descriptor.update(
                {
                    "group": "person",
                    "resource_types": list(template["resource_types"]),
                    # BrowserAssist leaves presetAtomType blank for many valid
                    # loose Person presets. The resource type itself is
                    # Person-specific; runtime apply still rejects any
                    # non-empty atom type other than Person.
                    "atom_types": [],
                    "target_kind": "person",
                    "operation": "apply-person-preset",
                    "required_capability": str(template["required_capability"]),
                    "browseable": True,
                    "live_action": True,
                    "merge_supported": True,
                }
            )
            descriptor.pop("path_prefix", None)
            total, local = category_counts(descriptor["resource_types"])
            descriptor.update(
                {
                    "count": total,
                    "local_count": local,
                    "packaged_count": total - local,
                }
            )
            categories.append(descriptor)

        preset_atom_key = "preset atom"
        preset_atom_types = sorted(
            {
                atom_type
                for resource_type, atom_type in counts
                if resource_type == preset_atom_key and atom_type
            },
            key=lambda value: atom_labels.get(value, value).casefold(),
        )
        for atom_type_key in preset_atom_types:
            atom_type = atom_labels.get(atom_type_key, atom_type_key)
            total, local = category_counts(("Preset Atom",), (atom_type,))
            categories.append(
                {
                    "id": _atom_preset_category_id(atom_type),
                    "label": f"{atom_type} presets",
                    "group": "atoms",
                    "resource_types": ["Preset Atom"],
                    "atom_types": [atom_type],
                    "target_kind": "atom",
                    "target_atom_type": atom_type,
                    "operation": "apply-atom-preset",
                    "required_capability": "atom-preset-apply",
                    "risk": "high",
                    "risk_reason": (
                        f"May replace state on a {atom_type} atom or create one."
                    ),
                    "browseable": True,
                    "live_action": False,
                    "merge_supported": True,
                    "count": total,
                    "local_count": local,
                    "packaged_count": total - local,
                }
            )
        return categories

    def workspace_categories(self) -> dict[str, object]:
        """Return the server-owned catalogue/action registry."""

        with connect(self.state_dir) as connection:
            categories = self._workspace_category_descriptors(connection)
        return {
            "categories": categories,
            "category_count": len(categories),
            "resource_count": sum(int(category["count"]) for category in categories),
        }

    def search_resources(
        self,
        *,
        query: str = "",
        resource_type: str = "",
        resource_types: list[str] | None = None,
        category: str = "",
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
            selected_types = [
                value
                for value in (resource_types or [])
                if isinstance(value, str) and value.strip()
            ]
            selected_atom_types: list[str] = []
            category_id = category.strip()
            if category_id:
                if resource_type.strip() or selected_types:
                    raise ValueError("category cannot be combined with type filters")
                categories = self._workspace_category_descriptors(connection)
                descriptor = next(
                    (item for item in categories if str(item["id"]) == category_id),
                    None,
                )
                if descriptor is None:
                    raise ValueError(f"unknown workspace category: {category_id}")
                selected_types = [str(value) for value in descriptor["resource_types"]]
                selected_atom_types = [str(value) for value in descriptor["atom_types"]]
            result = find_catalog_resources(
                connection,
                self.vam_root,
                query=query,
                resource_type=resource_type or None,
                resource_types=selected_types,
                atom_types=selected_atom_types,
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
            if category_id:
                result["category"] = category_id
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
        bridge_rescan: bool = True,
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
            bridge_rescan=bridge_rescan,
        )
        result["resource_id"] = int(resource_id)
        result["discovered_roots"] = roots
        return result

    @staticmethod
    def _catalog_resource_reference(
        location: object,
        *,
        required_prefix: str,
        extension: str,
        require_preset_basename: bool,
    ) -> str:
        resource_path = str(getattr(location, "resource_path", "")).replace("\\", "/")
        archive_member = getattr(location, "archive_member", None)
        candidate = str(archive_member or resource_path).replace("\\", "/")
        if (
            not candidate
            or candidate != candidate.strip()
            or candidate.startswith("/")
            or ":" in candidate
            or any(
                ord(character) < 32 or ord(character) == 127 for character in candidate
            )
        ):
            raise ValueError("the selected catalog resource has an unsafe path")
        parts = candidate.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("the selected catalog resource has an unsafe path")

        prefix_parts = required_prefix.rstrip("/").split("/")
        if len(parts) <= len(prefix_parts) or [
            part.casefold() for part in parts[: len(prefix_parts)]
        ] != [part.casefold() for part in prefix_parts]:
            raise ValueError(
                f"the selected catalog resource is outside {required_prefix}"
            )
        filename = parts[-1]
        if not filename.casefold().endswith(extension.casefold()):
            raise ValueError(f"the selected catalog resource is not a {extension} file")
        if require_preset_basename and not filename.casefold().startswith("preset_"):
            raise ValueError("the selected preset basename must begin with Preset_")

        package_ref = getattr(location, "package_ref", None)
        if package_ref:
            package_ref = str(package_ref)
            package_parts = package_ref.split(".")
            if (
                "/" in package_ref
                or "\\" in package_ref
                or ":" in package_ref
                or len(package_parts) < 3
                or any(not part for part in package_parts)
            ):
                raise ValueError("the selected catalog package reference is unsafe")
            return f"{package_ref}:/{candidate}"
        return candidate

    @staticmethod
    def _validate_target_uid(target_uid: object) -> str:
        if not isinstance(target_uid, str):
            raise TypeError("target_uid must be a string")
        uid = target_uid.strip()
        if (
            not uid
            or len(uid) > 200
            or any(ord(character) < 32 or ord(character) == 127 for character in uid)
        ):
            raise ValueError("target_uid must contain 1 to 200 printable characters")
        return uid

    def _ensure_bridge_mailbox_idle(self) -> None:
        request = read_bridge_request(self.vam_root)
        if request is None:
            return
        status = read_bridge_status(self.vam_root)
        if not self._bridge_request_is_terminal(request, status):
            raise LiveActionBusyError(
                "the VaM bridge is still handling another request"
            )

    def _queue_bridge_request(self, writer: Callable[[], str]) -> str:
        """Publish one ordered request after an atomic in-process idle check."""

        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            return writer()

    def _try_queue_bridge_request(
        self,
        writer: Callable[[], str],
    ) -> tuple[str | None, str | None]:
        """Avoid overwriting an external request after local work succeeded."""

        try:
            return self._queue_bridge_request(writer), None
        except LiveActionBusyError as error:
            return None, str(error)

    @staticmethod
    def _lease_requires_bridge_rescan(
        lease: dict[str, object],
        *,
        packaged: bool,
    ) -> bool:
        """Return whether a composite action made packages newly visible.

        Loose resources never require a package rescan. For packaged
        resources, a completed reconciliation exposes its exact enable count;
        unknown/custom lease results stay conservative.
        """

        if not packaged:
            return False
        reconcile = lease.get("reconcile")
        if not isinstance(reconcile, dict):
            return True
        enabled = reconcile.get("enable")
        if isinstance(enabled, bool) or not isinstance(enabled, int):
            return True
        return enabled > 0

    def _require_live_capability(
        self,
        capability: str,
        *,
        action_label: str,
    ) -> dict[str, object]:
        scene = self.scene()
        if not scene["vam_running"]:
            raise ValueError(f"VaM must be running before {action_label}")
        if not scene["available"]:
            raise ValueError(
                "the protocol-2 VAM-PIP bridge is not publishing a live scene snapshot"
            )
        capabilities = {str(value) for value in scene.get("capabilities", [])}
        if capability not in capabilities:
            raise ValueError(f"the loaded VAM-PIP bridge does not provide {capability}")
        return scene

    def apply_resource(
        self,
        resource_id: int,
        *,
        target_uid: str | None = None,
        days: float = 3,
        merge: bool = False,
        confirm_replace: bool = False,
        confirm_critical: bool = False,
    ) -> dict[str, object]:
        """Apply a live-action resource selected solely by catalog identity."""

        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            return self._apply_resource_locked(
                resource_id,
                target_uid=target_uid,
                days=days,
                merge=merge,
                confirm_replace=confirm_replace,
                confirm_critical=confirm_critical,
            )

    def apply_person_resource(
        self,
        resource_id: int,
        *,
        target_uid: str,
        days: float = 3,
        merge: bool = False,
        confirm_critical: bool = False,
    ) -> dict[str, object]:
        """Compatibility wrapper for catalog-backed Person preset application."""

        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            return self._apply_resource_locked(
                resource_id,
                target_uid=target_uid,
                days=days,
                merge=merge,
                confirm_replace=False,
                confirm_critical=confirm_critical,
                expected_target_kind="person",
            )

    def _apply_resource_locked(
        self,
        resource_id: int,
        *,
        target_uid: str | None,
        days: float,
        merge: bool,
        confirm_replace: bool,
        confirm_critical: bool,
        expected_target_kind: str | None = None,
    ) -> dict[str, object]:
        if (
            isinstance(resource_id, bool)
            or not isinstance(resource_id, int)
            or resource_id < 1
        ):
            raise ValueError("resource_id must be a positive integer")
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            raise TypeError("days must be a number")
        if not isinstance(merge, bool):
            raise TypeError("merge must be a boolean")
        if not isinstance(confirm_replace, bool):
            raise TypeError("confirm_replace must be a boolean")
        if not isinstance(confirm_critical, bool):
            raise TypeError("confirm_critical must be a boolean")

        with connect(self.state_dir) as connection:
            self._rows(connection, refresh=False)
            row = connection.execute(
                """
                SELECT resource_type, atom_type FROM catalog_resources
                WHERE id = ? AND root = ?
                """,
                (int(resource_id), str(self.vam_root)),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown catalog resource: {int(resource_id)}")
            location = resolve_resource_archive(
                connection,
                self.vam_root,
                int(resource_id),
                addon_root=self.addon_dir,
            )
        if location is None:
            raise ValueError("the selected catalog resource file is not installed")

        resource_type = str(row["resource_type"])
        atom_type = str(row["atom_type"])
        person_spec = _PERSON_PRESET_BY_RESOURCE_TYPE.get(resource_type.casefold())
        if person_spec is not None:
            target_kind = "person"
            operation = "apply-person-preset"
            category_id = str(person_spec["id"])
        elif resource_type.casefold() == "scene":
            target_kind = "none"
            operation = "load-scene"
            category_id = "scene"
        else:
            raise ValueError(
                f"{resource_type or 'this resource type'} is browse-only in this version"
            )
        if expected_target_kind is not None and target_kind != expected_target_kind:
            raise ValueError("the selected resource is not a Person preset")

        label = Path(location.resource_path.replace("\\", "/")).stem.removeprefix(
            "Preset_"
        )
        if person_spec is not None:
            if person_spec["risk"] == "critical" and not confirm_critical:
                raise ValueError(
                    "confirm_critical must be true before applying "
                    f"{person_spec['label']}"
                )
            if atom_type and atom_type.casefold() != "person":
                raise ValueError(
                    "the selected Person preset targets a different atom type"
                )
            uid = self._validate_target_uid(target_uid)
            scene = self._require_live_capability(
                str(person_spec["required_capability"]),
                action_label="a Person preset can be applied",
            )
            person_uids = {
                str(person.get("uid"))
                for person in scene.get("persons", [])
                if isinstance(person, dict) and person.get("uid") is not None
            }
            if uid not in person_uids:
                raise ValueError(f"Person atom is no longer available: {uid}")
            resource_ref = self._catalog_resource_reference(
                location,
                required_prefix=str(person_spec["path_prefix"]),
                extension=".vap",
                require_preset_basename=True,
            )
            lease = self.lease_resource(
                resource_id,
                days=float(days),
                label=f"{person_spec['label']}: {label}",
                apply=location.packaged,
                bridge_rescan=False,
            )
            rescan = self._lease_requires_bridge_rescan(
                lease,
                packaged=location.packaged,
            )
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_person_preset(
                    self.vam_root,
                    target_uid=uid,
                    preset_kind=str(person_spec["preset_kind"]),
                    resource_ref=resource_ref,
                    rescan=rescan,
                    merge=merge,
                )
            )
            return {
                "resource_id": resource_id,
                "category": category_id,
                "operation": operation,
                "target_uid": uid,
                "preset_kind": str(person_spec["preset_kind"]),
                "resource_ref": resource_ref,
                "merge": merge,
                "rescan": rescan,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
                "lease": lease,
            }

        if target_uid is not None:
            raise ValueError("target_uid is not accepted when loading a Scene")
        if not merge and not confirm_replace:
            raise ValueError(
                "confirm_replace must be true when replacing the current Scene"
            )
        self._require_live_capability(
            "scene-load",
            action_label="a Scene can be loaded",
        )
        resource_ref = self._catalog_resource_reference(
            location,
            required_prefix="Saves/scene/",
            extension=".json",
            require_preset_basename=False,
        )
        lease = self.lease_resource(
            resource_id,
            days=float(days),
            label=f"Scene: {label}",
            apply=location.packaged,
            bridge_rescan=False,
        )
        rescan = self._lease_requires_bridge_rescan(
            lease,
            packaged=location.packaged,
        )
        request_id, bridge_message = self._try_queue_bridge_request(
            lambda: request_scene_load(
                self.vam_root,
                resource_ref,
                rescan=rescan,
                merge=merge,
            )
        )
        return {
            "resource_id": resource_id,
            "category": category_id,
            "operation": operation,
            "target_uid": None,
            "resource_ref": resource_ref,
            "merge": merge,
            "rescan": rescan,
            "bridge_request": request_id,
            "bridge_busy": bridge_message is not None,
            "bridge_message": bridge_message,
            "lease": lease,
        }

    def add_person(self, target_uid: str) -> dict[str, object]:
        """Idempotently add a Person atom through the bridge."""

        uid = self._validate_target_uid(target_uid)
        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            scene = self._require_live_capability(
                "person-add",
                action_label="a Person can be added",
            )
            person_uids = {
                str(person.get("uid"))
                for person in scene.get("persons", [])
                if isinstance(person, dict) and person.get("uid") is not None
            }
            if uid in person_uids:
                return {
                    "operation": "add-person",
                    "target_uid": uid,
                    "already_exists": True,
                    "bridge_request": None,
                    "bridge_busy": False,
                    "bridge_message": None,
                }
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_add_person(self.vam_root, uid)
            )
            return {
                "operation": "add-person",
                "target_uid": uid,
                "already_exists": False,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
            }

    def select_person(self, target_uid: str) -> dict[str, object]:
        """Idempotently select an existing Person atom through the bridge."""

        uid = self._validate_target_uid(target_uid)
        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            scene = self._require_live_capability(
                "person-select",
                action_label="a Person can be selected",
            )
            person_uids = {
                str(person.get("uid"))
                for person in scene.get("persons", [])
                if isinstance(person, dict) and person.get("uid") is not None
            }
            if uid not in person_uids:
                raise ValueError(f"Person atom is no longer available: {uid}")
            already_selected = str(scene.get("selected_uid") or "") == uid
            request_id = None
            bridge_message = None
            if not already_selected:
                request_id, bridge_message = self._try_queue_bridge_request(
                    lambda: request_select_person(self.vam_root, uid)
                )
            return {
                "operation": "select-person",
                "target_uid": uid,
                "already_selected": already_selected,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
            }

    def select_atom(self, target_uid: str) -> dict[str, object]:
        """Idempotently select an existing atom through the bridge."""

        uid = self._validate_target_uid(target_uid)
        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            scene = self._require_live_capability(
                "atom-select",
                action_label="an atom can be selected",
            )
            atom_uids = {
                str(atom.get("uid"))
                for atom in scene.get("atoms", [])
                if isinstance(atom, dict) and atom.get("uid") is not None
            }
            if uid not in atom_uids:
                raise ValueError(f"Atom is no longer available: {uid}")
            already_selected = str(scene.get("selected_uid") or "") == uid
            request_id = None
            bridge_message = None
            if not already_selected:
                request_id, bridge_message = self._try_queue_bridge_request(
                    lambda: request_select_atom(self.vam_root, uid)
                )
            return {
                "operation": "select-atom",
                "target_uid": uid,
                "already_selected": already_selected,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
            }

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

    @staticmethod
    def _session_plugin_root_row(
        plugin: SessionPlugin,
        rows: list[sqlite3.Row],
    ) -> sqlite3.Row | None:
        """Return the archive selected for one packaged plugin root."""

        if plugin.package_ref is None:
            return None
        resolution = resolve([plugin.package_ref], rows)
        if any(
            owner == "<root>" and reference.casefold() == plugin.package_ref.casefold()
            for owner, reference in resolution.missing
        ):
            return None

        reference = plugin.package_ref.casefold()
        for row in resolution.selected:
            if package_id(row).casefold() == reference:
                return row

        dependency = parse_dependency_ref(plugin.package_ref)
        if dependency is not None and dependency.is_latest:
            for row in resolution.selected:
                if family_id(row).casefold() == dependency.family_key:
                    return row
        return None

    def _loose_session_plugin_exists(self, plugin: SessionPlugin) -> bool:
        """Check a loose virtual path without escaping the VaM root."""

        if not plugin.loose:
            return False
        relative = plugin.source_path.replace("\\", "/").lstrip("/")
        if not relative:
            return False
        try:
            root = self.vam_root.resolve()
            candidate = (root / relative).resolve()
        except (OSError, RuntimeError):
            return False
        if not candidate.is_relative_to(root):
            return False
        try:
            return candidate.is_file()
        except OSError:
            return False

    @staticmethod
    def _add_session_plugin_pins(
        connection: sqlite3.Connection,
        roots: list[str] | tuple[str, ...],
    ) -> int:
        """Add exact session-default roots without replacing user labels."""

        existing = {str(pin["root_ref"]).casefold() for pin in list_pins(connection)}
        added = 0
        for root in roots:
            if root.casefold() in existing:
                continue
            add_pin(connection, root, label="VaM session default")
            existing.add(root.casefold())
            added += 1
        return added

    def session_plugins(self) -> dict[str, object]:
        """Describe VaM's default Session Plugins preset and package state."""

        preset = load_session_plugin_defaults(self.vam_root)
        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
            rows, _ = self._rows(connection, refresh=False)
            pins = list_pins(connection)

        pinned_roots = {str(pin["root_ref"]).casefold() for pin in pins}
        enabled_roots = list(preset.enabled_package_roots)
        session_resolution = resolve(enabled_roots, rows)
        items: list[dict[str, object]] = []
        for plugin in preset.plugins:
            root_row = self._session_plugin_root_row(plugin, rows)
            loose_available = self._loose_session_plugin_exists(plugin)
            items.append(
                {
                    "slot": plugin.slot,
                    "slot_index": plugin.slot_index,
                    "source": plugin.source,
                    "source_path": plugin.source_path,
                    "package_ref": plugin.package_ref,
                    "enabled": plugin.enabled,
                    "packaged": plugin.packaged,
                    "loose": plugin.loose,
                    "installed": loose_available or root_row is not None,
                    "package_installed": (
                        root_row is not None if plugin.packaged else None
                    ),
                    "active": (
                        loose_available
                        or (root_row is not None and bool(root_row["enabled"]))
                    ),
                    "pinned": (
                        plugin.package_ref is not None
                        and plugin.package_ref.casefold() in pinned_roots
                    ),
                    "resolved_package": (
                        package_id(root_row) if root_row is not None else None
                    ),
                }
            )

        return {
            "preset": str(preset.path),
            "exists": preset.exists,
            "items": items,
            "enabled_packaged_roots": enabled_roots,
            "missing": [
                {"required_by": owner, "reference": reference}
                for owner, reference in session_resolution.missing
            ],
            "counts": {
                "total": len(preset.plugins),
                "enabled": sum(plugin.enabled for plugin in preset.plugins),
                "packaged": sum(plugin.packaged for plugin in preset.plugins),
                "enabled_packaged": sum(
                    plugin.enabled and plugin.packaged for plugin in preset.plugins
                ),
                "loose": sum(
                    plugin.enabled and plugin.loose for plugin in preset.plugins
                ),
                "already_pinned": sum(
                    root.casefold() in pinned_roots for root in enabled_roots
                ),
                "missing": len(session_resolution.missing),
            },
        }

    def import_session_plugins(
        self,
        *,
        include_disabled: bool = False,
        apply: bool = False,
    ) -> dict[str, object]:
        """Pin packaged plugins referenced by VaM's default session preset."""

        preset = load_session_plugin_defaults(self.vam_root)
        roots = list(
            preset.package_roots if include_disabled else preset.enabled_package_roots
        )
        pinned = 0
        already_pinned = 0
        resolved_packages = 0
        managed_mode = False
        reconcile_result: dict[str, object] | None = None
        reconcile_error: str | None = None
        with manager_lock(self.state_dir):
            with connect(self.state_dir) as connection:
                rows, _ = self._rows(connection, refresh=bool(roots))
                existing = {
                    str(pin["root_ref"]).casefold() for pin in list_pins(connection)
                }
                already_pinned = sum(root.casefold() in existing for root in roots)
                if roots:
                    resolution = resolve(roots, rows)
                    if resolution.missing:
                        summary = ", ".join(
                            (
                                reference
                                if owner == "<root>"
                                else f"{reference} (required by {owner})"
                            )
                            for owner, reference in resolution.missing[:10]
                        )
                        raise ValueError(
                            "cannot preserve unresolved session-plugin "
                            f"packages: {summary}"
                        )
                    rows = self._verify_desired_copies(
                        connection,
                        rows,
                        [package_id(row) for row in resolution.selected],
                    )
                    resolved_packages = len(resolution.selected)
                    pinned = self._add_session_plugin_pins(connection, roots)
                managed_mode = bool(get_setting(connection, "managed_mode", False))
        if apply and managed_mode and roots:
            try:
                reconcile_result = self.reconcile(apply=True)
            except (OSError, ValueError, sqlite3.Error) as exc:
                reconcile_error = str(exc)

        result: dict[str, object] = {
            "preset": str(preset.path),
            "exists": preset.exists,
            "include_disabled": include_disabled,
            "roots": roots,
            "pinned": pinned,
            "already_pinned": already_pinned,
            "resolved_packages": resolved_packages,
            "managed_mode": managed_mode,
            "applied": False,
        }
        if reconcile_result is not None:
            result["reconcile"] = reconcile_result
            result["applied"] = True
        if reconcile_error is not None:
            result["reconcile_error"] = reconcile_error
        return result

    def status(self, *, refresh_if_empty: bool = True) -> dict[str, object]:
        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
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
        bridge_rescan: bool = True,
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
            result["reconcile"] = self.reconcile(
                apply=True,
                bridge_rescan=bridge_rescan,
            )
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
        bridge_busy: bool = False,
        bridge_message: str | None = None,
        expired_leases_removed: int = 0,
        session_default_roots: int = 0,
        session_defaults_pinned: int = 0,
    ) -> dict[str, object]:
        return {
            "desired_packages": len(plan.desired_ids),
            "enable": len(plan.to_enable),
            "disable": len(plan.to_disable),
            "pending_disable": pending_disable,
            "vam_running": running,
            "manifest": str(manifest) if manifest else None,
            "bridge_request": bridge_request,
            "bridge_busy": bridge_busy,
            "bridge_message": bridge_message,
            "expired_leases_removed": expired_leases_removed,
            "session_default_roots": session_default_roots,
            "session_defaults_pinned": session_defaults_pinned,
        }

    def reconcile(
        self,
        *,
        apply: bool,
        activate: bool = False,
        bridge_rescan: bool = True,
    ) -> dict[str, object]:
        # Lock order is bridge mailbox -> operation gate -> filesystem
        # manager lock. Composite live actions already own the mailbox gate
        # when they recurse here through lease_resource().
        with self._bridge_mailbox_lock:
            with self._operation_gate:
                return self._run_reconcile(
                    apply=apply,
                    activate=activate,
                    bridge_rescan=bridge_rescan,
                )

    def reconcile_if_idle(
        self,
        *,
        apply: bool = True,
        activate: bool = False,
        bridge_rescan: bool = True,
    ) -> dict[str, object] | None:
        """Reconcile now, or coalesce the request into work already running."""

        if not self._bridge_mailbox_lock.acquire(blocking=False):
            return None
        try:
            if not self._operation_gate.acquire(blocking=False):
                return None
            try:
                return self._run_reconcile(
                    apply=apply,
                    activate=activate,
                    bridge_rescan=bridge_rescan,
                )
            finally:
                self._operation_gate.release()
        finally:
            self._bridge_mailbox_lock.release()

    def _run_reconcile(
        self,
        *,
        apply: bool,
        activate: bool,
        bridge_rescan: bool = True,
    ) -> dict[str, object]:
        operation_id = self._begin_operation("managed-reconcile") if apply else None
        try:
            result = self._reconcile(
                apply=apply,
                activate=activate,
                bridge_rescan=bridge_rescan,
                _operation_id=operation_id,
            )
        except BaseException as exc:
            if operation_id is not None:
                self._finish_operation(
                    operation_id,
                    status="failed",
                    error=exc,
                )
            raise
        if operation_id is not None:
            self._finish_operation(
                operation_id,
                status="completed",
                result=result,
            )
        return result

    def _reconcile(
        self,
        *,
        apply: bool,
        activate: bool,
        bridge_rescan: bool,
        _operation_id: int | None,
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
                        "bridge_busy": False,
                        "bridge_message": None,
                        "session_default_roots": 0,
                        "session_defaults_pinned": 0,
                    }

                session_roots: tuple[str, ...] = ()
                if activating:
                    session_roots = load_session_plugin_defaults(
                        self.vam_root
                    ).enabled_package_roots
                desired, missing = resolve_managed_set(
                    connection,
                    rows,
                    extra_roots=session_roots,
                )
                if missing:
                    summary = ", ".join(reference for _, reference in missing[:10])
                    raise ValueError(f"managed package resolution failed: {summary}")
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
                        session_default_roots=len(session_roots),
                    )

                # A pre-existing ordered bridge action must win before package
                # visibility changes. Otherwise the switch could require a
                # rescan that cannot be queued, while a later reconciliation
                # sees no remaining files to enable and never retries it.
                if bridge_rescan and running and plan.to_enable:
                    self._ensure_bridge_mailbox_idle()

                # Persist any newly observed rollback baseline rows before the
                # first filesystem rename. Dry runs returned above without
                # creating baseline state.
                baseline_added = ensure_baseline(connection, root_text, rows)
                if baseline_added or activating:
                    connection.commit()
                manifest = apply_switch(
                    self.state_dir,
                    self.addon_dir,
                    plan,
                    run_name="managed-reconcile",
                    allow_disable=not running,
                    lock_held=True,
                    progress_callback=(
                        (
                            lambda snapshot: self._update_operation(
                                _operation_id,
                                snapshot,
                            )
                        )
                        if _operation_id is not None
                        else None
                    ),
                )
                session_defaults_pinned = 0
                if activating:
                    try:
                        session_defaults_pinned = self._add_session_plugin_pins(
                            connection,
                            session_roots,
                        )
                        set_setting(connection, "managed_mode", True)
                        connection.commit()
                    except BaseException:
                        try:
                            connection.rollback()
                        except Exception:
                            pass
                        if manifest is not None:
                            try:
                                rollback_switch(
                                    manifest,
                                    progress_callback=(
                                        (
                                            lambda snapshot: self._update_operation(
                                                _operation_id,
                                                snapshot,
                                            )
                                        )
                                        if _operation_id is not None
                                        else None
                                    ),
                                )
                            except BaseException as rollback_error:
                                raise RuntimeError(
                                    "managed activation changed package "
                                    "visibility, then saving its pins/mode and "
                                    "the automatic filesystem rollback both "
                                    f"failed; recover with {manifest}"
                                ) from rollback_error
                            try:
                                scan(self.addon_dir, connection)
                                connection.commit()
                            except Exception:
                                try:
                                    connection.rollback()
                                except Exception:
                                    pass
                        raise
                if manifest is not None:
                    scan(self.addon_dir, connection)
                expired_leases_removed = (
                    remove_expired_leases(connection) if not running else 0
                )

        bridge_request = None
        bridge_message = None
        if bridge_rescan and running and plan.to_enable:
            bridge_request, bridge_message = self._try_queue_bridge_request(
                lambda: request_rescan(self.vam_root)
            )
        return self._plan_document(
            plan,
            running=running,
            pending_disable=pending_disable,
            manifest=manifest,
            bridge_request=bridge_request,
            bridge_busy=bridge_message is not None,
            bridge_message=bridge_message,
            expired_leases_removed=expired_leases_removed,
            session_default_roots=len(session_roots),
            session_defaults_pinned=session_defaults_pinned,
        )

    def deactivate(self, *, apply: bool) -> dict[str, object]:
        with self._operation_gate:
            operation_id = self._begin_operation("restore-baseline") if apply else None
            try:
                result = self._deactivate(
                    apply=apply,
                    _operation_id=operation_id,
                )
            except BaseException as exc:
                if operation_id is not None:
                    self._finish_operation(
                        operation_id,
                        status="failed",
                        error=exc,
                    )
                raise
            if operation_id is not None:
                self._finish_operation(
                    operation_id,
                    status="completed",
                    result=result,
                )
            return result

    def _deactivate(
        self,
        *,
        apply: bool,
        _operation_id: int | None,
    ) -> dict[str, object]:
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
                pids = self._running_pids()
                if pids:
                    raise ValueError(
                        "VaM started while the baseline restore was being "
                        "prepared; close it before restoring packages"
                    )
                manifest = apply_switch(
                    self.state_dir,
                    self.addon_dir,
                    plan,
                    run_name="restore-baseline",
                    allow_disable=True,
                    lock_held=True,
                    progress_callback=(
                        (
                            lambda snapshot: self._update_operation(
                                _operation_id,
                                snapshot,
                            )
                        )
                        if _operation_id is not None
                        else None
                    ),
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
        # Keep launch inside the same in-process gate as package switches. The
        # lock is reentrant because a managed launch reconciles before Popen.
        with self._operation_gate:
            return self._launch_vam_locked(reconcile=reconcile)

    def _launch_vam_locked(self, *, reconcile: bool) -> dict[str, object]:
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
        pids = self._running_pids()
        if pids:
            raise ValueError(
                "VaM started while its managed package set was being prepared; "
                "detected process IDs " + ", ".join(map(str, pids))
            )
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

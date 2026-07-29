from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
from typing import Callable, Iterator
import uuid

from vampip.analysis import family_id, package_id
from vampip.bridge import (
    ATOM_TYPE_ALLOWLIST,
    bridge_directory,
    read_bridge_status,
    read_bridge_request,
    read_scene_status,
    read_timeline_status,
    request_add_atom,
    request_add_person,
    request_atom_preset,
    request_custom_unity_asset_choice,
    request_custom_unity_asset_load,
    request_person_clothing,
    request_person_body_proportions,
    request_person_hair_item,
    request_person_preset,
    request_rescan,
    request_scene_load,
    request_select_atom,
    request_select_person,
    request_sam3d_apply,
    request_sam3d_capture,
    request_sam3d_undo,
    request_subscene_load,
    request_timeline_control,
    request_undo_person_body_proportions,
    TIMELINE_CONTROL_OPERATIONS,
)
from vampip.body_proportions import (
    build_analysis as build_body_proportion_analysis,
    consensus_body_signatures,
    normalize_regions as normalize_body_proportion_regions,
    normalize_strength as normalize_body_proportion_strength,
    signature_from_live as live_body_proportion_signature,
    signature_from_manifest as sam3d_body_proportion_signature,
)
from vampip.body_shape import (
    build_body_shape_analysis,
    live_body_shape,
    normalize_shape_regions,
    normalize_shape_strength,
)
from vampip.catalog import (
    catalog_facets as load_catalog_facets,
    get_resource_thumbnail,
    import_browserassist,
    package_resource_summaries,
    package_resources_for_copy,
    resolve_resource_archive,
    search_resources as find_catalog_resources,
)
from vampip.database import connect
from vampip.inventory import (
    ScanResult,
    ensure_content_hashes,
    inventory_changed,
    is_archive_content_sha256,
    rows_for_root,
    scan,
)
from vampip.manager_state import (
    add_pin,
    clear_baseline,
    create_lease,
    ensure_baseline,
    get_lease_context,
    get_setting,
    list_leases,
    list_package_choices,
    list_pins,
    load_baseline,
    remove_lease,
    remove_expired_leases,
    remove_pin,
    renew_lease,
    resolve_managed_set,
    set_package_choice,
    set_lease_context,
    set_setting,
)
from vampip.models import parse_dependency_ref
from vampip.profiles import (
    PackageCopyChoice,
    PackageCopyChoiceError,
    Resolution,
    preferred,
    resolve,
)
from vampip.references import package_dependency_graph, resource_package_roots
from vampip.runtime import atomic_write_text, derive_vam_root, find_vam_processes
from vampip.sam3d import (
    SAM3D_CAPTURE_FILE_LIMIT,
    SAM3D_CAPTURE_HISTORY_LIMIT,
    Sam3dJobManager,
    Sam3dJobError,
    validate_job_id as validate_sam3d_job_id,
)
from vampip.sam3d_body_shape import (
    BODY_SHAPE_METRICS,
    BODY_SHAPE_REGIONS,
    consensus_body_shapes,
    normalize_vam_body_shape,
)
from vampip.sam3d_vam import (
    VR_RENDERER_RESOLUTIONS,
    build_vam_solution,
    sam3d_solution_revision,
)
from vampip.session_plugins import (
    SessionPlugin,
    load_session_plugin_defaults,
)
from vampip.switching import (
    ManagerLockBusyError,
    SwitchPlan,
    apply_switch,
    build_baseline_restore_plan,
    build_switch_plan,
    logical_relative_path,
    manager_lock,
    rollback_switch,
)


_SAM3D_CAPTURE_FILENAME = re.compile(
    r"^vampip_([0-9a-f]{32})_([0-9a-f]{32})\.(jpg|png)$"
)
_SAM3D_CAPTURE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
}
_SAM3D_BODY_REFERENCE = re.compile(r"^([0-9a-f]{32}):([0-9]{1,2})$")
_SAM3D_BODY_REFERENCE_LIMIT = 8
_SAM3D_BODY_INDEX_LIMIT = 31


class LiveActionBusyError(RuntimeError):
    """Raised when an ordered VaM bridge action is still in flight."""


class PackageConflictError(ValueError):
    """A package identity needs an explicit, structured user decision."""

    def __init__(
        self,
        message: str,
        conflicts: list[dict[str, object]],
        *,
        code: str = "package_copy_conflict",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.conflicts = conflicts

    def document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "error": str(self),
            "conflicts": self.conflicts,
        }


def _normalize_sam3d_body_references(
    job_id: str,
    person_index: int,
    references: object,
) -> tuple[tuple[str, int], ...]:
    """Validate a bounded ordered set of immutable SAM3D body references."""

    job_id = validate_sam3d_job_id(job_id)
    if (
        isinstance(person_index, bool)
        or not isinstance(person_index, int)
        or not 0 <= person_index <= _SAM3D_BODY_INDEX_LIMIT
    ):
        raise ValueError("person_index is outside its supported range")
    if references is None:
        return ((job_id, person_index),)
    if not isinstance(references, str):
        raise TypeError("references must be a comma-separated string")
    if not references or len(references) > 512:
        raise ValueError("references is empty or exceeds its supported size")
    raw_tokens = references.split(",")
    if not 1 <= len(raw_tokens) <= _SAM3D_BODY_REFERENCE_LIMIT:
        raise ValueError(
            f"references must contain between 1 and {_SAM3D_BODY_REFERENCE_LIMIT} jobs"
        )
    normalized: list[tuple[str, int]] = []
    seen_jobs: set[str] = set()
    for raw_token in raw_tokens:
        token = raw_token.strip().casefold()
        match = _SAM3D_BODY_REFERENCE.fullmatch(token)
        if match is None:
            raise ValueError(
                "references must contain only <32hex-job-id>:<body-index> tokens"
            )
        reference_job_id = match.group(1)
        reference_index = int(match.group(2))
        if reference_index > _SAM3D_BODY_INDEX_LIMIT:
            raise ValueError("a reference body index exceeds its supported range")
        if reference_job_id in seen_jobs:
            raise ValueError("references contains a duplicate SAM3D job")
        seen_jobs.add(reference_job_id)
        normalized.append((reference_job_id, reference_index))
    if normalized[0] != (job_id, person_index):
        raise ValueError(
            "the first body reference must match the request job and person_index"
        )
    return tuple(normalized)


def _choice_digest(choice: object | None) -> str | None:
    value = getattr(choice, "selected_content_sha256", None)
    return str(value) if value else None


def _package_copy_id(row: sqlite3.Row) -> str:
    payload = "\0".join(
        (
            str(row["root"]),
            str(row["path"]),
            str(row["size"]),
            str(row["mtime_ns"]),
            str(row["content_sha256"] or ""),
        )
    )
    return hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()[
        :32
    ]


def _package_conflict_document(
    group: list[sqlite3.Row],
    *,
    choice: object | None,
    vam_running: bool,
) -> dict[str, object]:
    """Serialize one already-hashed same-ID group without accepting paths."""

    ordered = sorted(
        group,
        key=lambda row: (
            logical_relative_path(row).casefold(),
            str(row["relative_path"]).casefold(),
        ),
    )
    identity = package_id(ordered[0])
    selected_digest = _choice_digest(choice)
    available_digests = {
        str(row["content_sha256"])
        for row in ordered
        if is_archive_content_sha256(row["content_sha256"])
    }
    choice_stale = bool(
        selected_digest is not None and selected_digest not in available_digests
    )
    selected_physical_path: str | None = None
    if choice is not None and not choice_stale:
        try:
            selected_physical_path = str(preferred(ordered, choice)["path"])
        except ValueError:
            selected_physical_path = None
    copies: list[dict[str, object]] = []
    for row in ordered:
        try:
            dependencies = json.loads(row["dependencies_json"])
        except (TypeError, json.JSONDecodeError):
            dependencies = []
        if not isinstance(dependencies, list):
            dependencies = []
        logical_path = logical_relative_path(row)
        digest = str(row["content_sha256"] or "")
        digest_selected = bool(
            selected_digest is not None and digest == selected_digest
        )
        path_selected = bool(
            digest_selected and str(row["path"]) == selected_physical_path
        )
        copies.append(
            {
                "copy_id": _package_copy_id(row),
                "relative_path": str(row["relative_path"]),
                "logical_relative_path": logical_path,
                "size": int(row["size"]),
                "mtime_ns": int(row["mtime_ns"]),
                "active": bool(row["enabled"]),
                "enabled": bool(row["enabled"]),
                "content_sha256": digest,
                "content_fingerprint": (
                    digest.removeprefix("1:")[:12]
                    if is_archive_content_sha256(digest)
                    else None
                ),
                "selected": path_selected,
                "selected_content": digest_selected,
                "dependencies": [
                    value for value in dependencies if isinstance(value, str)
                ],
            }
        )
    revision_payload = json.dumps(
        [
            identity.casefold(),
            selected_digest,
            (
                str(getattr(choice, "preferred_logical_path", "") or "")
                if choice is not None
                else ""
            ),
            [
                [
                    item["copy_id"],
                    item["content_sha256"],
                    item["active"],
                ]
                for item in copies
            ],
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    report_revision = hashlib.sha256(revision_payload.encode("utf-8")).hexdigest()
    nonselected_active = bool(
        selected_digest
        and any(
            bool(row["enabled"]) and str(row["content_sha256"] or "") != selected_digest
            for row in ordered
        )
    )
    return {
        "package_id": identity,
        "report_revision": report_revision,
        "selected_content_sha256": selected_digest,
        "choice_stale": choice_stale,
        "resolved": bool(selected_digest and not choice_stale),
        "requires_vam_close": bool(vam_running and nonselected_active),
        "copies": copies,
    }


_LIVE_PACKAGE_RESCAN_SETTING = "pending_live_package_rescan"


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
        "risk": "critical",
        "risk_reason": (
            "Creates or replaces a SubScene and may load executable plugin code."
        ),
        "browseable": True,
        "live_action": "SubScene" in ATOM_TYPE_ALLOWLIST,
        "merge_supported": False,
        "target_atom_type": "SubScene",
        "create_supported": "SubScene" in ATOM_TYPE_ALLOWLIST,
        "create_capability": "atom-add",
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
        "risk_reason": (
            "DLL loading is forced off, but already-running code is not unloaded."
        ),
        "browseable": True,
        "live_action": "CustomUnityAsset" in ATOM_TYPE_ALLOWLIST,
        "merge_supported": False,
        "target_atom_type": "CustomUnityAsset",
        "create_supported": "CustomUnityAsset" in ATOM_TYPE_ALLOWLIST,
        "create_capability": "atom-add",
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
        "operation": "set-person-clothing",
        "required_capability": "person-clothing-item-toggle",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's active clothing items.",
        "browseable": True,
        "live_action": True,
        "merge_supported": False,
    },
    {
        "id": "clothing-items-male",
        "label": "Male clothing items",
        "group": "person",
        "resource_types": ("Clothing (Male)",),
        "target_kind": "person",
        "operation": "set-person-clothing",
        "required_capability": "person-clothing-item-toggle",
        "risk": "medium",
        "risk_reason": "Changes the selected Person's active clothing items.",
        "browseable": True,
        "live_action": True,
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


_EQUIPMENT_SLOT_KEYWORDS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "high-heels",
        frozenset(
            {
                "heel",
                "heels",
                "highheel",
                "highheels",
                "pump",
                "pumps",
                "stiletto",
                "stilettos",
            }
        ),
    ),
    (
        "bras",
        frozenset({"bra", "bras", "bralette", "bralettes"}),
    ),
    (
        "panties-underwear",
        frozenset(
            {
                "briefs",
                "knickers",
                "lingerie",
                "panty",
                "panties",
                "thong",
                "thongs",
                "underwear",
            }
        ),
    ),
    (
        "full-body",
        frozenset(
            {
                "bodysuit",
                "bodysuits",
                "catsuit",
                "catsuits",
                "dress",
                "dresses",
                "gown",
                "gowns",
                "jumpsuit",
                "jumpsuits",
                "outfit",
                "outfits",
                "robe",
                "robes",
                "romper",
                "rompers",
            }
        ),
    ),
    (
        "tops",
        frozenset(
            {
                "blouse",
                "blouses",
                "coat",
                "coats",
                "corset",
                "corsets",
                "hoodie",
                "hoodies",
                "jacket",
                "jackets",
                "shirt",
                "shirts",
                "sweater",
                "sweaters",
                "top",
                "tops",
                "vest",
                "vests",
            }
        ),
    ),
    (
        "bottoms",
        frozenset(
            {
                "bottom",
                "bottoms",
                "jeans",
                "leggings",
                "pants",
                "shorts",
                "skirt",
                "skirts",
                "trousers",
            }
        ),
    ),
    (
        "stockings-socks",
        frozenset(
            {
                "garter",
                "garters",
                "hosiery",
                "pantyhose",
                "sock",
                "socks",
                "stocking",
                "stockings",
                "tights",
            }
        ),
    ),
    (
        "shoes-boots",
        frozenset(
            {
                "boot",
                "boots",
                "footwear",
                "sandal",
                "sandals",
                "shoe",
                "shoes",
                "slipper",
                "slippers",
                "sneaker",
                "sneakers",
            }
        ),
    ),
    (
        "head",
        frozenset(
            {
                "cap",
                "caps",
                "crown",
                "hat",
                "hats",
                "headwear",
                "mask",
                "masks",
                "veil",
            }
        ),
    ),
    (
        "neck",
        frozenset(
            {
                "choker",
                "chokers",
                "collar",
                "collars",
                "necklace",
                "necklaces",
                "scarf",
                "scarves",
                "tie",
                "ties",
            }
        ),
    ),
    (
        "arms-hands",
        frozenset(
            {
                "armband",
                "armbands",
                "bracelet",
                "bracelets",
                "glove",
                "gloves",
                "mitten",
                "mittens",
                "sleeve",
                "sleeves",
                "wristband",
                "wristbands",
            }
        ),
    ),
    (
        "body-fx",
        frozenset(
            {
                "bodypaint",
                "decal",
                "decals",
                "effect",
                "effects",
                "fx",
                "makeup",
                "paint",
                "tattoo",
                "tattoos",
            }
        ),
    ),
    (
        "accessories",
        frozenset(
            {
                "accessories",
                "accessory",
                "belt",
                "belts",
                "earring",
                "earrings",
                "glasses",
                "jewelry",
                "piercing",
                "piercings",
                "tail",
                "tails",
                "wing",
                "wings",
            }
        ),
    ),
)


def _equipment_text(value: object, *, maximum: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return ""
    return text


def _bounded_int(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = 2_147_483_647,
) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if minimum <= value <= maximum else None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?(?:0|[1-9][0-9]{0,9})", text):
            parsed = int(text)
            if minimum <= parsed <= maximum:
                return parsed
    return None


def _nonnegative_int(value: object) -> int:
    parsed = _bounded_int(value)
    return parsed if parsed is not None else 0


def _presentation_text(value: object, *, maximum: int) -> str:
    text = _equipment_text(value, maximum=maximum)
    normalized = text.replace("\\", "/")
    if (
        not text
        or re.match(r"^[a-z]:/", normalized, flags=re.IGNORECASE)
        or normalized.startswith("/")
        or ":/" in normalized
        or re.search(
            r"(?:^|/)(?:custom|addonpackages)(?:/|$)",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.search(r"\.var(?::|/|$)", normalized, flags=re.IGNORECASE)
    ):
        return ""
    return text


def _presentation_tags(value: object, *, maximum: int = 128) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw_tag in value:
        tag = _presentation_text(raw_tag, maximum=100)
        identity = tag.casefold()
        if not tag or identity in seen:
            continue
        seen.add(identity)
        result.append(tag)
        if len(result) >= maximum:
            break
    return result


def _revision_scoped_key(revision: str, kind: str, index: int) -> str:
    digest = hashlib.sha256(f"{revision}\0{kind}\0{index}".encode("utf-8")).hexdigest()[
        :24
    ]
    return f"{kind}-{digest}"


def _public_capabilities(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    capabilities: list[str] = []
    seen: set[str] = set()
    for raw_capability in value[:128]:
        capability = _equipment_text(raw_capability, maximum=100)
        if not re.fullmatch(r"[a-z0-9-]+", capability) or capability in seen:
            continue
        seen.add(capability)
        capabilities.append(capability)
    return capabilities


def _public_bridge_status(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    protocol = _nonnegative_int(value.get("protocol"))
    if protocol:
        result["protocol"] = protocol
    for key, maximum in (
        ("bridgeVersion", 64),
        ("instanceId", 128),
        ("requestId", 128),
        ("lastCompletedRequestId", 128),
        ("state", 64),
        ("updatedAtUtc", 64),
        ("startedAtUtc", 64),
        ("finishedAtUtc", 64),
        ("backend", 64),
        ("message", 1000),
    ):
        text = _equipment_text(value.get(key), maximum=maximum)
        if text:
            result[key] = text
    if isinstance(value.get("ok"), bool):
        result["ok"] = value["ok"]
    capabilities = _public_capabilities(value.get("capabilities"))
    if capabilities:
        result["capabilities"] = capabilities
    return result


def _sam3d_settlement_number(
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if (
            re.fullmatch(
                r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?",
                value,
            )
            is None
        ):
            return None
    elif not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return None
    return number


def _sam3d_settlement_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _public_sam3d_settlement_vector(
    value: object,
    *,
    quaternion: bool,
) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    keys = ("x", "y", "z", "w") if quaternion else ("x", "y", "z")
    limit = 1.0001 if quaternion else 1_000.0
    result: dict[str, float] = {}
    for key in keys:
        number = _sam3d_settlement_number(
            value.get(key),
            minimum=-limit,
            maximum=limit,
        )
        if number is None:
            return None
        result[key] = number
    return result


def _public_sam3d_settlement_transform(
    value: object,
) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    position = _public_sam3d_settlement_vector(
        value.get("position"),
        quaternion=False,
    )
    rotation = _public_sam3d_settlement_vector(
        value.get("rotation"),
        quaternion=True,
    )
    if position is None or rotation is None:
        return None
    return {"position": position, "rotation": rotation}


def _public_sam3d_settlement(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    schema = _bounded_int(value.get("schema"), minimum=1, maximum=1)
    if schema is None:
        return None

    raw_error = value.get("error")
    result: dict[str, object] = {
        "schema": schema,
        "available": False,
        "error": _equipment_text(raw_error, maximum=1000),
        "settleFrames": (_bounded_int(value.get("settleFrames"), maximum=120) or 0),
        "controllerLimit": (_bounded_int(value.get("controllerLimit"), maximum=2) or 0),
        "controllers": [],
    }
    request_id = _equipment_text(value.get("requestId"), maximum=32).casefold()
    if re.fullmatch(r"[0-9a-f]{32}", request_id) is not None:
        result["requestId"] = request_id

    captured_at = _equipment_text(value.get("capturedAtUtc"), maximum=64)
    if captured_at:
        try:
            timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
        if timestamp is not None and timestamp.tzinfo is not None:
            result["capturedAtUtc"] = captured_at

    controllers: list[dict[str, object]] = []
    raw_controllers = value.get("controllers")
    seen: set[str] = set()
    if isinstance(raw_controllers, list):
        for raw_controller in raw_controllers[:2]:
            if not isinstance(raw_controller, dict):
                continue
            controller_id = raw_controller.get("id")
            if (
                controller_id not in {"headControl", "neckControl"}
                or controller_id in seen
            ):
                continue
            seen.add(controller_id)
            controller: dict[str, object] = {"id": controller_id}
            for key in ("requested", "actual"):
                transform = _public_sam3d_settlement_transform(raw_controller.get(key))
                if transform is not None:
                    controller[key] = transform
            position_error = _sam3d_settlement_number(
                raw_controller.get("positionErrorMeters"),
                minimum=0.0,
                maximum=1_000.0,
            )
            if position_error is not None:
                controller["positionErrorMeters"] = position_error
            rotation_error = _sam3d_settlement_number(
                raw_controller.get("rotationErrorDegrees"),
                minimum=0.0,
                maximum=180.0,
            )
            if rotation_error is not None:
                controller["rotationErrorDegrees"] = rotation_error

            raw_state = raw_controller.get("state")
            if isinstance(raw_state, dict):
                state: dict[str, object] = {}
                for key in ("position", "rotation"):
                    token = _equipment_text(raw_state.get(key), maximum=32)
                    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", token):
                        state[key] = token
                for key in (
                    "physicsEnabled",
                    "possessed",
                    "startedPossess",
                    "isGrabbing",
                ):
                    flag = raw_state.get(key)
                    parsed_flag = _sam3d_settlement_bool(flag)
                    if parsed_flag is not None:
                        state[key] = parsed_flag
                if state:
                    controller["state"] = state
            controllers.append(controller)
    result["controllers"] = controllers
    available = _sam3d_settlement_bool(value.get("available"))
    result["available"] = bool(
        available is True
        and raw_error == ""
        and {item["id"] for item in controllers} == {"headControl", "neckControl"}
        and all(
            {
                "requested",
                "actual",
                "positionErrorMeters",
                "rotationErrorDegrees",
            }.issubset(item)
            for item in controllers
        )
    )
    return result


def _public_sam3d_status(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {
        "applied": value.get("applied") is True,
        "undoAvailable": value.get("undoAvailable") is True,
    }
    for key in ("jobId", "revision"):
        token = _equipment_text(value.get(key), maximum=32).casefold()
        if re.fullmatch(r"[0-9a-f]{32}", token) is not None:
            result[key] = token
    for key in ("targetUid", "cameraUid"):
        uid = _equipment_text(value.get(key), maximum=200)
        if uid:
            result[key] = uid

    raw_action = value.get("lastAction")
    if isinstance(raw_action, dict):
        action: dict[str, object] = {}
        request_id = _equipment_text(
            raw_action.get("requestId"),
            maximum=32,
        ).casefold()
        job_id = _equipment_text(
            raw_action.get("jobId"),
            maximum=32,
        ).casefold()
        revision = _equipment_text(
            raw_action.get("revision"),
            maximum=32,
        ).casefold()
        command = _equipment_text(raw_action.get("command"), maximum=64)
        state = _equipment_text(raw_action.get("state"), maximum=16)
        command_map = {
            "applySam3dResult": "apply",
            "undoSam3dResult": "undo",
            "captureSam3dResult": "capture",
        }
        if re.fullmatch(r"[0-9a-f]{32}", request_id) is not None:
            action["requestId"] = request_id
        if re.fullmatch(r"[0-9a-f]{32}", job_id) is not None:
            action["jobId"] = job_id
        if re.fullmatch(r"[0-9a-f]{32}", revision) is not None:
            action["revision"] = revision
        if command in command_map:
            action["action"] = command_map[command]
        if state in {"ok", "error"}:
            action["state"] = state
        camera_uid = _equipment_text(
            raw_action.get("cameraUid"),
            maximum=200,
        )
        if camera_uid:
            action["cameraUid"] = camera_uid
        message = _equipment_text(raw_action.get("message"), maximum=1000)
        if message:
            action["message"] = message
        if action:
            result["lastAction"] = action
    settlement = _public_sam3d_settlement(value.get("settlement"))
    if settlement is not None:
        result["settlement"] = settlement
    return result


def _public_body_proportions(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    revision = _equipment_text(value.get("revision"), maximum=32).casefold()
    if re.fullmatch(r"[0-9a-f]{32}", revision) is None:
        revision = ""
    undo_revision = _equipment_text(
        value.get("undoRevision"),
        maximum=32,
    ).casefold()
    if re.fullmatch(r"[0-9a-f]{32}", undo_revision) is None:
        undo_revision = ""
    measurements: dict[str, float] = {}
    raw_measurements = value.get("measurements")
    if isinstance(raw_measurements, dict):
        for key in (
            "upperArm",
            "forearm",
            "thigh",
            "shin",
            "torso",
            "shoulderSpan",
            "hipSpan",
        ):
            raw = raw_measurements.get(key)
            if isinstance(raw, dict):
                raw = raw.get("meters")
            number = _sam3d_settlement_number(
                raw,
                minimum=0.000001,
                maximum=10.0,
            )
            if number is not None:
                measurements[key] = number

    morphs: list[dict[str, object]] = []
    seen: set[str] = set()
    raw_morphs = value.get("morphs")
    if isinstance(raw_morphs, list):
        for raw in raw_morphs[:64]:
            if not isinstance(raw, dict):
                continue
            key = _equipment_text(raw.get("key"), maximum=32).casefold()
            name = _presentation_text(raw.get("name"), maximum=128)
            if re.fullmatch(r"[0-9a-f]{32}", key) is None or key in seen or not name:
                continue
            current = _sam3d_settlement_number(
                raw.get("value"),
                minimum=-100.0,
                maximum=100.0,
            )
            minimum = _sam3d_settlement_number(
                raw.get("min"),
                minimum=-100.0,
                maximum=100.0,
            )
            maximum = _sam3d_settlement_number(
                raw.get("max"),
                minimum=-100.0,
                maximum=100.0,
            )
            if (
                current is None
                or minimum is None
                or maximum is None
                or minimum > maximum
                or current < minimum - 1e-5
                or current > maximum + 1e-5
            ):
                continue
            seen.add(key)
            public_morph: dict[str, object] = {
                "key": key,
                "name": name,
                "region": _presentation_text(
                    raw.get("region"),
                    maximum=128,
                ),
                "value": current,
                "min": minimum,
                "max": maximum,
            }
            fit_kind = _equipment_text(raw.get("fitKind"), maximum=16)
            if fit_kind in {"structure", "shape"}:
                public_morph["fitKind"] = fit_kind
            if isinstance(raw.get("builtIn"), bool):
                public_morph["builtIn"] = raw["builtIn"]
            if fit_kind == "shape":
                shape_region = _equipment_text(
                    raw.get("shapeRegion"),
                    maximum=16,
                )
                raw_responses = raw.get("shapeResponses")
                responses: dict[str, float] = {}
                if shape_region in BODY_SHAPE_REGIONS and isinstance(
                    raw_responses, dict
                ):
                    for metric in BODY_SHAPE_METRICS:
                        response = _sam3d_settlement_number(
                            raw_responses.get(metric),
                            minimum=-10.0,
                            maximum=10.0,
                        )
                        if response is not None:
                            responses[metric] = response
                if shape_region in BODY_SHAPE_REGIONS and responses:
                    public_morph["shapeRegion"] = shape_region
                    public_morph["shapeResponses"] = responses
            morphs.append(public_morph)

    body_shape: dict[str, object] | None = None
    raw_body_shape = value.get("bodyShape")
    try:
        body_shape = normalize_vam_body_shape(raw_body_shape)
    except (TypeError, ValueError):
        pass

    result: dict[str, object] = {
        "ready": bool(
            value.get("ready") is True and revision and len(measurements) == 7
        ),
        "selectedOnly": value.get("selectedOnly") is True,
        "revision": revision or None,
        "undoRevision": undo_revision or None,
        "measurements": measurements,
        "morphs": morphs,
        "undoAvailable": value.get("undoAvailable") is True,
        "undoPending": value.get("undoPending") is True,
        "bodyShapeReady": value.get("bodyShapeReady") is True,
        "bodyShapePreparing": value.get("bodyShapePreparing") is True,
    }
    body_shape_reason = _presentation_text(
        value.get("bodyShapeReason"),
        maximum=512,
    )
    if body_shape_reason:
        result["bodyShapeReason"] = body_shape_reason
    if body_shape is not None:
        result["bodyShape"] = body_shape
    return result


def _public_cua_status(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    choices: list[dict[str, object]] = []
    raw_choices = value.get("choices")
    if isinstance(raw_choices, list):
        seen_indices: set[int] = set()
        for raw_choice in raw_choices[:128]:
            if not isinstance(raw_choice, dict):
                continue
            index = _bounded_int(raw_choice.get("index"))
            label = _equipment_text(raw_choice.get("label"), maximum=256)
            if index is None or index in seen_indices or not label:
                continue
            seen_indices.add(index)
            choices.append({"index": index, "label": label})
    selected_index = _bounded_int(
        value.get("selectedIndex"),
        minimum=-1,
    )
    if selected_index is None:
        selected_index = -1
    choice_token = _equipment_text(value.get("choiceToken"), maximum=32)
    if re.fullmatch(r"[0-9a-fA-F]{32}", choice_token) is None:
        choice_token = ""
    load_dll = value.get("loadDll")
    return {
        "loadDll": load_dll if isinstance(load_dll, bool) else None,
        "ready": value.get("ready") is True,
        "isAssetLoaded": value.get("isAssetLoaded") is True,
        "choiceToken": choice_token,
        "choiceCount": _nonnegative_int(value.get("choiceCount")),
        "selectedIndex": selected_index,
        "choices": choices,
        "choicesTruncated": value.get("choicesTruncated") is True,
    }


def _public_sam3d_camera_status(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    compatible = value.get("compatible") is True
    status = _equipment_text(value.get("status"), maximum=80)
    fov_value = value.get("flatHorizontalFov")
    fov = (
        float(fov_value)
        if (
            not isinstance(fov_value, bool)
            and isinstance(fov_value, (int, float))
            and math.isfinite(float(fov_value))
            and 1.0 <= float(fov_value) <= 179.0
        )
        else None
    )
    aspect_value = value.get("aspectRatio")
    aspect_ratio = (
        aspect_value
        if isinstance(aspect_value, str) and aspect_value in VR_RENDERER_RESOLUTIONS
        else None
    )
    output_resolution: str | None = None
    raw_resolution = value.get("outputResolution")
    if (
        aspect_ratio is not None
        and isinstance(raw_resolution, str)
        and raw_resolution in VR_RENDERER_RESOLUTIONS[aspect_ratio]
    ):
        output_resolution = raw_resolution
    return {
        "compatible": compatible,
        "status": status,
        "flatHorizontalFov": fov,
        "aspectRatio": aspect_ratio,
        "outputResolution": output_resolution,
    }


def _public_scene_atoms(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    atoms: list[dict[str, object]] = []
    for raw_atom in value:
        if not isinstance(raw_atom, dict):
            continue
        uid = _equipment_text(raw_atom.get("uid"), maximum=200)
        atom_type = _equipment_text(raw_atom.get("type"), maximum=200)
        if not uid or not atom_type:
            continue
        atom: dict[str, object] = {
            "uid": uid,
            "type": atom_type,
            "selected": raw_atom.get("selected") is True,
        }
        cua = _public_cua_status(raw_atom.get("cua"))
        if cua is not None and atom_type == "CustomUnityAsset":
            atom["cua"] = cua
        sam3d_camera = _public_sam3d_camera_status(raw_atom.get("sam3dCamera"))
        if sam3d_camera is not None and atom_type == "Empty":
            atom["sam3dCamera"] = sam3d_camera
        atoms.append(atom)
    return atoms


def _equipment_member(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    member = value.replace("\\", "/")
    while member.startswith("./"):
        member = member[2:]
    if (
        not member
        or member != member.strip()
        or member.startswith("/")
        or ":" in member
        or any(ord(character) < 32 or ord(character) == 127 for character in member)
    ):
        return None
    parts = member.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return member


def _equipment_resource_type(member: str) -> str | None:
    folded = member.casefold()
    if not folded.endswith(".vam"):
        return None
    if folded.startswith("custom/clothing/female/"):
        return "Clothing (Female)"
    if folded.startswith("custom/clothing/male/"):
        return "Clothing (Male)"
    return None


def _equipment_version(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    text = str(value or "").strip()
    if not text.isdecimal():
        return None
    version = int(text)
    return version if version <= 2_147_483_647 else None


def _equipment_json_list(value: object) -> list[object]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _equipment_version_is_eligible(
    row: sqlite3.Row,
    version_text: str,
) -> bool:
    allowed = {
        str(value).strip().casefold()
        for value in _equipment_json_list(row["versions_json"])
        if str(value).strip()
    }
    identity = version_text.casefold()
    if identity in allowed:
        return True
    numeric_allowed = [int(value) for value in allowed if value.isdecimal()]
    return (
        version_text.isdecimal()
        and bool(numeric_allowed)
        and int(version_text) > max(numeric_allowed)
    )


def _equipment_metadata(
    row: sqlite3.Row,
    package_version: int | None,
) -> tuple[str, list[str]]:
    selected: dict[str, object] | None = None
    if package_version is not None:
        for entry in _equipment_json_list(row["clothing_versions_json"]):
            if (
                isinstance(entry, dict)
                and _equipment_version(entry.get("version")) == package_version
            ):
                selected = entry
                break

    display_name = (
        _equipment_text(selected.get("display_name"), maximum=500)
        if selected is not None
        else ""
    )
    if not display_name:
        filename = str(row["resource_path"]).replace("\\", "/").rsplit("/", 1)[-1]
        display_name = _equipment_text(filename.rsplit(".", 1)[0], maximum=500)
    if not display_name:
        display_name = "Unnamed clothing item"

    tags: list[str] = []
    seen: set[str] = set()

    def add_tag(value: object) -> None:
        tag = _equipment_text(value, maximum=100)
        identity = tag.casefold()
        if not tag or identity in seen or len(tags) >= 128:
            return
        seen.add(identity)
        tags.append(tag)

    for entry in _equipment_json_list(row["tags_json"]):
        if isinstance(entry, dict):
            add_tag(entry.get("tagName"))
    if selected is not None:
        selected_tags = selected.get("tags")
        if isinstance(selected_tags, list):
            for tag in selected_tags:
                add_tag(tag)
    return display_name, tags


def _equipment_slot(display_name: str, tags: list[str]) -> str:
    tag_words = {
        word for tag in tags for word in re.findall(r"[a-z0-9]+", tag.casefold())
    }
    name_words = set(re.findall(r"[a-z0-9]+", display_name.casefold()))
    for words in (tag_words, name_words):
        for slot, keywords in _EQUIPMENT_SLOT_KEYWORDS:
            if words & keywords:
                return slot
    return "unsorted"


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
        sam3d_manager: Sam3dJobManager | None = None,
    ) -> None:
        self.addon_dir = addon_dir.expanduser().resolve()
        self.state_dir = state_dir.expanduser().resolve()
        self.vam_root = (
            vam_root.expanduser().resolve()
            if vam_root is not None
            else derive_vam_root(self.addon_dir)
        )
        self._process_probe = process_probe or find_vam_processes
        self._sam3d_manager = sam3d_manager
        self._sam3d_manager_lock = threading.Lock()
        self._closed = False
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
        self._bridge_mailbox_transaction_depth = 0
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

    def _scene_snapshot(
        self,
        *,
        include_clothing_refs: bool,
    ) -> dict[str, object]:
        """Return one fresh bridge scene, optionally retaining private join keys."""

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
        persons = list(scene.get("persons") or []) if available and scene else []
        atoms = list(scene.get("atoms") or []) if available and scene else []
        capabilities = (
            list(scene.get("capabilities") or []) if available and scene else []
        )
        selected_uid = (
            str(scene.get("selectedUid") or "") if available and scene else ""
        )
        sam3d = (
            _public_sam3d_status(scene.get("sam3d")) if available and scene else None
        )
        if not include_clothing_refs:
            public_persons: list[object] = []
            for person in persons:
                if not isinstance(person, dict):
                    continue
                uid = _equipment_text(person.get("uid"), maximum=200)
                if not uid:
                    continue
                public_person: dict[str, object] = {
                    "uid": uid,
                    "selected": person.get("selected") is True,
                }
                body_proportions = _public_body_proportions(
                    person.get("bodyProportions")
                )
                if body_proportions is not None:
                    public_person["bodyProportions"] = body_proportions
                clothing = person.get("clothing")
                if isinstance(clothing, dict):
                    public_clothing: dict[str, object] = {
                        "ready": clothing.get("ready") is True,
                        "gender": (
                            str(clothing.get("gender") or "")
                            if str(clothing.get("gender") or "").casefold()
                            in {"female", "male", "both", "none"}
                            else "Unknown"
                        ),
                        "activeCount": _nonnegative_int(clothing.get("activeCount")),
                        "lockedCount": _nonnegative_int(clothing.get("lockedCount")),
                        "truncated": clothing.get("truncated") is True,
                        "revision": _equipment_text(
                            clothing.get("revision"),
                            maximum=32,
                        ),
                    }
                    raw_active_items = clothing.get("activeItems")
                    if isinstance(raw_active_items, list):
                        public_active_items: list[dict[str, object]] = []
                        for raw_item in raw_active_items[:256]:
                            if not isinstance(raw_item, dict):
                                continue
                            display_name = _presentation_text(
                                raw_item.get("displayName"),
                                maximum=256,
                            )
                            public_active_items.append(
                                {
                                    "displayName": (
                                        display_name or "Unnamed clothing item"
                                    ),
                                    "tags": _presentation_tags(
                                        raw_item.get("tags"),
                                        maximum=32,
                                    ),
                                    "locked": raw_item.get("locked") is True,
                                }
                            )
                        public_clothing["activeItems"] = public_active_items
                    public_person["clothing"] = public_clothing
                else:
                    public_person.pop("clothing", None)
                hair = person.get("hair")
                if isinstance(hair, dict):
                    public_hair: dict[str, object] = {
                        "ready": hair.get("ready") is True,
                        "revision": _equipment_text(
                            hair.get("revision"),
                            maximum=32,
                        ),
                        "activeCount": _nonnegative_int(hair.get("activeCount")),
                        "lockedCount": _nonnegative_int(hair.get("lockedCount")),
                        "truncated": hair.get("truncated") is True,
                        "items": [],
                    }
                    public_hair_items: list[dict[str, object]] = []
                    raw_hair_items = hair.get("items")
                    if isinstance(raw_hair_items, list):
                        for raw_item in raw_hair_items[:128]:
                            if not isinstance(raw_item, dict):
                                continue
                            display_name = _presentation_text(
                                raw_item.get("displayName"),
                                maximum=256,
                            )
                            public_hair_items.append(
                                {
                                    "displayName": (
                                        display_name or "Unnamed hair item"
                                    ),
                                    "tags": _presentation_tags(
                                        raw_item.get("tags"),
                                        maximum=32,
                                    ),
                                    "locked": raw_item.get("locked") is True,
                                    "simulated": (raw_item.get("simulated") is True),
                                }
                            )
                    public_hair["items"] = public_hair_items
                    public_person["hair"] = public_hair
                public_persons.append(public_person)
            persons = public_persons
            atoms = _public_scene_atoms(atoms)
            capabilities = _public_capabilities(capabilities)
            bridge = _public_bridge_status(bridge)
            selected_uid = _equipment_text(selected_uid, maximum=200)
        return {
            "available": available,
            "vam_running": bool(pids),
            "loading": bool(scene.get("loading")) if available and scene else False,
            "selected_uid": selected_uid,
            "atoms": atoms,
            "persons": persons,
            "capabilities": capabilities,
            "bridge": bridge,
            "sam3d": sam3d,
            "updated_at_utc": (
                scene.get("updatedAtUtc") if available and scene else None
            ),
        }

    def persons(self) -> dict[str, object]:
        """Return the public bridge-published scene snapshot without locks.

        The historical method name is retained for callers of
        ``/api/vam/persons``. Exact clothing resource refs remain private join
        keys inside the manager.
        """

        return self._scene_snapshot(include_clothing_refs=False)

    def scene(self) -> dict[str, object]:
        """Return the canonical bridge-published live scene snapshot."""

        return self.persons()

    def _sam3d(self) -> Sam3dJobManager:
        with self._sam3d_manager_lock:
            if self._closed:
                raise RuntimeError("manager service is closed")
            if self._sam3d_manager is None:
                self._sam3d_manager = Sam3dJobManager(self.state_dir)
            return self._sam3d_manager

    def close(self) -> None:
        with self._sam3d_manager_lock:
            if self._closed:
                return
            self._closed = True
            manager = self._sam3d_manager
            self._sam3d_manager = None
        if manager is not None:
            manager.close()

    @staticmethod
    def _sam3d_bridge_instance(scene: dict[str, object]) -> str:
        bridge = scene.get("bridge")
        if not isinstance(bridge, dict):
            return ""
        value = bridge.get("instanceId")
        return str(value) if isinstance(value, str) and 0 < len(value) <= 128 else ""

    @staticmethod
    def _sam3d_body_reference_support_from_manifest(
        manifest: object,
    ) -> list[dict[str, object]]:
        """Return bounded, fail-closed body-reference compatibility metadata."""

        if not isinstance(manifest, dict):
            return []
        people = manifest.get("people")
        if not isinstance(people, list):
            return []
        support: list[dict[str, object]] = []
        for person_index, person in enumerate(people[: _SAM3D_BODY_INDEX_LIMIT + 1]):
            space = "unavailable"
            multi_reference = False
            if isinstance(person, dict):
                try:
                    signature = sam3d_body_proportion_signature(
                        manifest,
                        person_index,
                    )
                except (KeyError, TypeError, ValueError):
                    pass
                else:
                    raw_space = signature.get("space")
                    if isinstance(raw_space, str) and 0 < len(raw_space) <= 64:
                        space = raw_space
                    multi_reference = bool(
                        space == "mhr-neutral-bind"
                        and isinstance(person.get("bodyProportions"), dict)
                    )
            support.append(
                {
                    "person_index": person_index,
                    "space": space,
                    "multi_reference": multi_reference,
                }
            )
        return support

    def _sam3d_body_reference_support(
        self,
        document: dict[str, object],
    ) -> list[dict[str, object]]:
        if document.get("state") != "succeeded":
            return []
        job_id = document.get("id")
        if not isinstance(job_id, str) or re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
            return []
        try:
            manifest = self._sam3d().manifest(job_id)
        except (
            FileNotFoundError,
            OSError,
            RuntimeError,
            Sam3dJobError,
            TypeError,
            ValueError,
        ):
            return []
        return self._sam3d_body_reference_support_from_manifest(manifest)

    def _decorate_sam3d_job(
        self,
        document: dict[str, object],
        scene: dict[str, object],
        *,
        include_body_reference_support: bool = True,
    ) -> dict[str, object]:
        result = dict(document)
        result.pop("settlement", None)
        result.pop("body_reference_support", None)
        job_id = str(result.get("id") or "")
        raw_action = result.get("last_vam_action")
        action = dict(raw_action) if isinstance(raw_action, dict) else {}
        action_name = str(action.get("action") or "")
        request_id = str(action.get("request_id") or "")
        revision = str(action.get("revision") or "")
        current_instance = self._sam3d_bridge_instance(scene)
        action_instance = str(action.get("bridge_instance") or "")
        action_state = str(action.get("state") or "queued")
        action_message = str(action.get("message") or "")

        live = scene.get("sam3d")
        live = live if isinstance(live, dict) else {}
        last_live_action = live.get("lastAction")
        last_live_action = (
            last_live_action if isinstance(last_live_action, dict) else {}
        )
        same_live_action = bool(
            request_id
            and last_live_action.get("requestId") == request_id
            and last_live_action.get("jobId") == job_id
            and last_live_action.get("revision") == revision
        )
        action_pending = action_state in {"queued", "running"}
        if action_pending and same_live_action:
            action_state = {
                "ok": "succeeded",
                "error": "failed",
            }.get(str(last_live_action.get("state") or ""), "unknown")
            action_message = str(last_live_action.get("message") or "")
        elif action_pending:
            bridge = scene.get("bridge")
            bridge = bridge if isinstance(bridge, dict) else {}
            same_bridge_request = bool(
                request_id and bridge.get("requestId") == request_id
            )
            if same_bridge_request:
                bridge_state = str(bridge.get("state") or "").casefold()
                if bridge_state == "error":
                    action_state = "failed"
                elif (
                    bridge_state == "ok"
                    and bridge.get("lastCompletedRequestId") == request_id
                ):
                    action_state = "succeeded"
                else:
                    action_state = (
                        "queued"
                        if bridge_state in {"", "queued", "deferred-loading"}
                        else "running"
                    )
                action_message = str(bridge.get("message") or "")
            elif (
                action_state in {"queued", "running"}
                and action_instance
                and current_instance != action_instance
            ):
                action_state = "stale"
                action_message = (
                    "VaM or the bridge restarted before this action was confirmed."
                )

        action_target_uid = str(action.get("target_uid") or "")
        action_camera_uid = str(action.get("camera_uid") or "")
        current_applied = bool(
            live.get("applied") is True
            and live.get("jobId") == job_id
            and live.get("revision") == revision
            and action_target_uid
            and live.get("targetUid") == action_target_uid
            and action_camera_uid
            and live.get("cameraUid") == action_camera_uid
        )
        if (
            current_applied
            and action_name == "apply"
            and action_state in {"queued", "running"}
        ):
            action_state = "succeeded"
        can_undo = bool(current_applied and live.get("undoAvailable") is True)
        solution_revision = (
            revision
            if re.fullmatch(r"[0-9a-f]{32}", revision) is not None
            else (str(live.get("revision")) if current_applied else "")
        )
        camera_uid = (
            str(live.get("cameraUid") or "")
            if current_applied
            else str(action.get("camera_uid") or "")
        )

        if (
            action
            and request_id
            and action_state in {"succeeded", "failed", "stale"}
            and action.get("state") != action_state
        ):
            self._sam3d().reconcile_vam_action(
                job_id,
                request_id=request_id,
                state=action_state,
                message=action_message,
            )
            persisted_capture = self._sam3d().get(job_id).get("last_capture")
            if isinstance(persisted_capture, dict):
                result["last_capture"] = persisted_capture
        if action:
            action["state"] = action_state
            action["message"] = action_message
            result["last_vam_action"] = action
        capture_requested = bool(
            action_name == "capture" or isinstance(result.get("last_capture"), dict)
        )
        captured = False
        if capture_requested:
            try:
                self.sam3d_artifact(job_id, "capture")
            except (FileNotFoundError, OSError, ValueError, Sam3dJobError):
                pass
            else:
                captured = True
        result.update(
            {
                "action_state": action_state if action else None,
                "action_message": action_message if action else "",
                "applied": current_applied,
                "can_undo": can_undo,
                "solution_revision": solution_revision or None,
                "camera_uid": camera_uid or None,
                "capture_requested": capture_requested,
                "captured": captured,
            }
        )
        if current_applied:
            settlement = _public_sam3d_settlement(live.get("settlement"))
            if settlement is not None:
                result["settlement"] = settlement
        if include_body_reference_support and result.get("state") == "succeeded":
            result["body_reference_support"] = self._sam3d_body_reference_support(
                result
            )
        return result

    def _sam3d_capture_roots(self) -> tuple[Path, Path]:
        saves = self.vam_root / "Saves"
        return (
            (saves / "screenshots" / "VAMPip").resolve(),
            (saves / "VR_Videos_And_Funscripts").resolve(),
        )

    def _sync_sam3d_capture_history(
        self,
        job_id: str,
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        job = self._sam3d().get(job_id)
        action = job.get("last_vam_action")
        incomplete_request = ""
        raw_captures = job.get("captures")
        raw_captures = raw_captures if isinstance(raw_captures, list) else []
        successful_requests = {
            str(capture["request_id"])
            for capture in raw_captures
            if isinstance(capture, dict) and isinstance(capture.get("request_id"), str)
        }
        if (
            isinstance(action, dict)
            and action.get("action") == "capture"
            and isinstance(action.get("request_id"), str)
        ):
            action_request = str(action["request_id"])
            if action.get("state") == "succeeded":
                successful_requests.add(action_request)
            else:
                incomplete_request = action_request

        discovered: dict[str, dict[str, object]] = {}
        pattern = f"vampip_*_{job_id}.*"
        capture_roots = self._sam3d_capture_roots()
        current_root = capture_roots[0]
        for root in capture_roots:
            try:
                candidates = root.glob(pattern)
                for candidate in candidates:
                    match = _SAM3D_CAPTURE_FILENAME.fullmatch(candidate.name)
                    if match is None or match.group(2) != job_id:
                        continue
                    request_id, _matched_job, extension = match.groups()
                    if request_id == incomplete_request:
                        # The prompt-free renderer writes directly to its final
                        # unique name. Do not index an incomplete or failed
                        # current request.
                        continue
                    if root == current_root and request_id not in successful_requests:
                        # Unlike the legacy renderer, the prompt-free writer
                        # has no temporary suffix. Only bridge-confirmed writes
                        # from this directory are safe to expose as captures.
                        continue
                    try:
                        if candidate.is_symlink():
                            continue
                        resolved = candidate.resolve(strict=True)
                        info = resolved.stat()
                    except (FileNotFoundError, OSError):
                        continue
                    if (
                        resolved.parent != root
                        or resolved.name != candidate.name
                        or not resolved.is_file()
                        or info.st_size < 1
                        or info.st_size > SAM3D_CAPTURE_FILE_LIMIT
                    ):
                        continue
                    try:
                        captured_at_utc = datetime.fromtimestamp(
                            info.st_mtime,
                            timezone.utc,
                        ).isoformat()
                    except (OSError, OverflowError, ValueError):
                        continue
                    discovered.setdefault(
                        request_id,
                        {
                            "request_id": request_id,
                            "revision": None,
                            "target_uid": None,
                            "camera_uid": None,
                            "extension": extension,
                            "content_type": _SAM3D_CAPTURE_CONTENT_TYPES[extension],
                            "captured_at_utc": captured_at_utc,
                            "size_bytes": info.st_size,
                        },
                    )
            except OSError:
                continue
        if not discovered:
            return job
        recent = sorted(
            discovered.values(),
            key=lambda capture: (
                str(capture["captured_at_utc"]),
                str(capture["request_id"]),
            ),
            reverse=True,
        )[:SAM3D_CAPTURE_HISTORY_LIMIT]
        return self._sam3d().merge_capture_history(
            job_id,
            recent,
        )

    def sam3d_status(self) -> dict[str, object]:
        return self._sam3d().status()

    def sam3d_jobs(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> dict[str, object]:
        result = self._sam3d().list(limit=limit, offset=offset)
        scene = self._scene_snapshot(include_clothing_refs=False)
        items = result.get("items")
        if isinstance(items, list):
            decorated: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                document = self._decorate_sam3d_job(item, scene)
                # Capture history is intentionally a job-detail surface. This
                # keeps the recent-jobs response bounded independently.
                document.pop("captures", None)
                decorated.append(document)
            result["items"] = decorated
        return result

    def sam3d_job(self, job_id: str) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        document = self._sam3d().get(job_id)
        scene = self._scene_snapshot(include_clothing_refs=False)
        # Reconcile a just-finished bridge request before scanning. Direct final
        # writes from a still-running capture are deliberately not backfilled.
        self._decorate_sam3d_job(
            document,
            scene,
            include_body_reference_support=False,
        )
        document = self._sync_sam3d_capture_history(job_id)
        return self._decorate_sam3d_job(document, scene)

    def create_sam3d_job(
        self,
        image_data: bytes,
        content_type: str,
        *,
        bbox: list[float] | None = None,
        vertical_fov: float | None = None,
        model_id: str | None = None,
        comparison_id: str | None = None,
    ) -> dict[str, object]:
        return self._sam3d().create(
            image_data,
            content_type,
            bbox=bbox,
            vertical_fov=vertical_fov,
            model_id=model_id,
            comparison_id=comparison_id,
        )

    def run_sam3d_job(self, job_id: str) -> dict[str, object]:
        return self._sam3d().queue(job_id)

    def select_sam3d_person(
        self,
        job_id: str,
        *,
        expected_revision: str,
        person_index: int,
    ) -> dict[str, object]:
        return self._sam3d().select_person(
            job_id,
            expected_revision=expected_revision,
            person_index=person_index,
        )

    def _sam3d_capture_path(
        self,
        job_id: str,
        request_id: str,
        extension: str,
    ) -> Path:
        job_id = validate_sam3d_job_id(job_id)
        request_id = validate_sam3d_job_id(request_id)
        if extension not in _SAM3D_CAPTURE_CONTENT_TYPES:
            raise ValueError("SAM3D capture metadata is invalid")
        filename = f"vampip_{request_id}_{job_id}.{extension}"
        for root in self._sam3d_capture_roots():
            path = root / filename
            try:
                if path.is_symlink():
                    continue
                resolved = path.resolve(strict=True)
                info = resolved.stat()
            except (FileNotFoundError, OSError):
                continue
            if (
                resolved.parent == root
                and resolved.name == filename
                and resolved.is_file()
                and 0 < info.st_size <= SAM3D_CAPTURE_FILE_LIMIT
            ):
                return resolved
        raise FileNotFoundError("SAM3D capture is not available yet")

    def sam3d_capture_artifact(
        self,
        job_id: str,
        request_id: str,
    ) -> tuple[Path, str]:
        job_id = validate_sam3d_job_id(job_id)
        request_id = validate_sam3d_job_id(request_id)
        job = self._sync_sam3d_capture_history(job_id)
        captures = job.get("captures")
        if not isinstance(captures, list):
            raise FileNotFoundError("SAM3D capture is not in this job history")
        capture = next(
            (
                item
                for item in captures
                if isinstance(item, dict) and item.get("request_id") == request_id
            ),
            None,
        )
        if capture is None:
            raise FileNotFoundError("SAM3D capture is not in this job history")
        extension = capture.get("extension")
        content_type = capture.get("content_type")
        if (
            not isinstance(extension, str)
            or _SAM3D_CAPTURE_CONTENT_TYPES.get(extension) != content_type
        ):
            raise ValueError("SAM3D capture metadata is invalid")
        return (
            self._sam3d_capture_path(job_id, request_id, extension),
            str(content_type),
        )

    def sam3d_artifact(
        self,
        job_id: str,
        name: str,
    ) -> tuple[Path, str]:
        if name == "capture":
            job_id = validate_sam3d_job_id(job_id)
            job = self._sync_sam3d_capture_history(job_id)
            capture = job.get("last_capture")
            if capture is not None and not isinstance(capture, dict):
                raise ValueError("SAM3D capture metadata is invalid")
            if isinstance(capture, dict):
                request_id = capture.get("request_id")
                revision = capture.get("revision")
                extension = capture.get("extension")
                content_type = capture.get("content_type")
                if (
                    not isinstance(request_id, str)
                    or re.fullmatch(r"[0-9a-f]{32}", request_id) is None
                    or (
                        revision is not None
                        and (
                            not isinstance(revision, str)
                            or re.fullmatch(r"[0-9a-f]{32}", revision) is None
                        )
                    )
                    or (extension, content_type)
                    not in {
                        ("jpg", "image/jpeg"),
                        ("png", "image/png"),
                    }
                ):
                    raise ValueError("SAM3D capture metadata is invalid")
            else:
                action = job.get("last_vam_action")
                if (
                    not isinstance(action, dict)
                    or action.get("action") != "capture"
                    or not isinstance(action.get("request_id"), str)
                    or re.fullmatch(
                        r"[0-9a-f]{32}",
                        action["request_id"],
                    )
                    is None
                    or not isinstance(action.get("revision"), str)
                ):
                    raise FileNotFoundError("SAM3D capture has not been requested")
                scene = self._scene_snapshot(include_clothing_refs=False)
                live = scene.get("sam3d")
                live = live if isinstance(live, dict) else {}
                live_action = live.get("lastAction")
                live_action = live_action if isinstance(live_action, dict) else {}
                live_succeeded = bool(
                    live_action.get("action") == "capture"
                    and live_action.get("requestId") == action["request_id"]
                    and live_action.get("jobId") == job_id
                    and live_action.get("revision") == action["revision"]
                    and live_action.get("state") == "ok"
                )
                stored_succeeded = action.get("state") == "succeeded"
                if not (live_succeeded or stored_succeeded):
                    raise FileNotFoundError("SAM3D capture is not confirmed complete")
                request_id = action["request_id"]
                revision = action["revision"]
                solution = self._load_sam3d_solution(job_id, revision)
                extension, content_type = self._sam3d_capture_media(solution)
            return (
                self._sam3d_capture_path(
                    job_id,
                    str(request_id),
                    str(extension),
                ),
                str(content_type),
            )
        return self._sam3d().artifact(job_id, name)

    @staticmethod
    def _sam3d_capture_media(
        solution: dict[str, object],
    ) -> tuple[str, str]:
        camera = solution.get("camera")
        image_format = camera.get("imageFormat") if isinstance(camera, dict) else None
        if image_format == "jpeg":
            return "jpg", "image/jpeg"
        if image_format == "png":
            return "png", "image/png"
        raise ValueError("SAM3D capture image format is invalid")

    @staticmethod
    def _sam3d_solution_revision(value: object, *, label: str) -> str:
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
            raise ValueError(f"{label} must be a lowercase 32-character token")
        return value

    def _sam3d_solution_path(self, job_id: str) -> Path:
        job_id = validate_sam3d_job_id(job_id)
        return (
            self.vam_root
            / "Saves"
            / "PluginData"
            / "VAMPip"
            / "SAM3D"
            / f"{job_id}.json"
        )

    def _read_sam3d_solution(
        self,
        job_id: str,
        expected_revision: object,
    ) -> tuple[dict[str, object], str]:
        expected = self._sam3d_solution_revision(
            expected_revision,
            label="expected_revision",
        )
        path = self._sam3d_solution_path(job_id)
        try:
            encoded = path.read_bytes()
            if len(encoded) > 1024 * 1024:
                raise ValueError("SAM3D bridge solution is unexpectedly large")
            document = json.loads(encoded.decode("utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"SAM3D bridge solution not found: {job_id}"
            ) from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("SAM3D bridge solution is unreadable") from error
        if (
            not isinstance(document, dict)
            or document.get("schema") != 1
            or document.get("jobId") != job_id
            or document.get("revision") != expected
            or sam3d_solution_revision(document) != expected
        ):
            raise ValueError("SAM3D bridge solution revision does not match")
        return document, hashlib.sha256(encoded).hexdigest()

    def _load_sam3d_solution(
        self,
        job_id: str,
        expected_revision: object,
    ) -> dict[str, object]:
        document, _ = self._read_sam3d_solution(
            job_id,
            expected_revision,
        )
        return document

    @staticmethod
    def _sam3d_camera_atom(
        scene: dict[str, object],
        camera_uid: str,
    ) -> dict[str, object] | None:
        return next(
            (
                atom
                for atom in scene.get("atoms", [])
                if isinstance(atom, dict)
                and atom.get("uid") == camera_uid
                and atom.get("type") == "Empty"
            ),
            None,
        )

    @staticmethod
    def _require_current_sam3d_application(
        scene: dict[str, object],
        *,
        job_id: str,
        revision: str,
        camera_uid: str | None = None,
    ) -> dict[str, object]:
        live = scene.get("sam3d")
        if (
            not isinstance(live, dict)
            or live.get("applied") is not True
            or live.get("undoAvailable") is not True
            or live.get("jobId") != job_id
            or live.get("revision") != revision
        ):
            raise ValueError(
                "the current SAM3D solution must be applied in this VaM session"
            )
        if camera_uid is not None and live.get("cameraUid") != camera_uid:
            raise ValueError(
                "camera_uid does not match the currently applied SAM3D solution"
            )
        return live

    @staticmethod
    def _live_body_proportion_status(
        scene: dict[str, object],
        target_uid: str,
    ) -> dict[str, object]:
        person = next(
            (
                value
                for value in scene.get("persons", [])
                if isinstance(value, dict) and value.get("uid") == target_uid
            ),
            None,
        )
        if person is None:
            raise ValueError("the selected Person is no longer available")
        status = person.get("bodyProportions")
        if not isinstance(status, dict) or status.get("ready") is not True:
            raise ValueError(
                "the bridge has not published body proportions for this Person; "
                "select the Person in VaM and refresh"
            )
        if status.get("selectedOnly") is True and person.get("selected") is not True:
            raise ValueError(
                "body proportions are available only for the Person selected in VaM"
            )
        return status

    @staticmethod
    def _body_analysis_revision(document: dict[str, object]) -> str:
        unsigned = {
            key: value
            for key, value in document.items()
            if key not in {"analysis_revision", "analysisRevision"}
        }
        encoded = json.dumps(
            unsigned,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()[:32]

    def sam3d_body_proportions(
        self,
        job_id: str,
        *,
        target_uid: object,
        person_index: int = 0,
        references: object = None,
        strength: object = 0.5,
        regions: object = None,
        shape_strength: object = 0.5,
        shape_regions: object = (),
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        reference_values = _normalize_sam3d_body_references(
            job_id,
            person_index,
            references,
        )
        strength_value = normalize_body_proportion_strength(strength)
        region_values = normalize_body_proportion_regions(regions)
        shape_strength_value = normalize_shape_strength(shape_strength)
        shape_region_values = normalize_shape_regions(shape_regions)
        shape_enabled = bool(shape_region_values)
        scene = self._require_live_capability(
            ("person-body-shape-v1" if shape_enabled else "person-body-proportions-v1"),
            action_label="analyzing body proportions",
        )
        target_uid, _ = self._validate_live_atom_target(
            scene,
            target_uid,
            expected_atom_type="Person",
            create_if_missing=False,
        )
        body_status = self._live_body_proportion_status(scene, target_uid)
        body_shape_ready = body_status.get("bodyShapeReady") is True
        body_shape_preparing = body_status.get("bodyShapePreparing") is True
        body_shape_reason = _presentation_text(
            body_status.get("bodyShapeReason"),
            maximum=512,
        )
        current_body_shape: dict[str, object] | None = None
        if shape_enabled:
            if not body_shape_ready:
                raise ValueError(
                    "VaM body-shape measurements are unavailable: "
                    + (
                        body_shape_reason
                        or "neutral body-shape calibration is not ready"
                    )
                )
            try:
                current_body_shape = live_body_shape(body_status.get("bodyShape"))
            except ValueError as exc:
                if body_shape_reason:
                    raise ValueError(
                        "VaM body-shape measurements are unavailable: "
                        + body_shape_reason
                    ) from exc
                raise
        manager = self._sam3d()
        signatures: list[dict[str, object]] = []
        shape_signatures: list[dict[str, object]] = []
        reference_jobs: list[dict[str, object]] = []
        incompatible_jobs: list[str] = []
        multi_reference = len(reference_values) > 1
        structure_enabled = bool(region_values)
        for reference_position, (
            reference_job_id,
            reference_index,
        ) in enumerate(reference_values):
            job = manager.get(reference_job_id)
            if job["state"] != "succeeded":
                raise Sam3dJobError(
                    "every body reference must be a successfully completed SAM3D job"
                )
            manifest = manager.manifest(reference_job_id)
            reference_revision = str(manifest["revision"])
            support = self._sam3d_body_reference_support_from_manifest(manifest)
            selected_support = next(
                (item for item in support if item["person_index"] == reference_index),
                None,
            )
            if (
                structure_enabled
                and multi_reference
                and (
                    selected_support is None
                    or selected_support["multi_reference"] is not True
                )
            ):
                incompatible_jobs.append(reference_job_id)
                continue
            signature = sam3d_body_proportion_signature(
                manifest,
                reference_index,
            )
            if structure_enabled or reference_position == 0:
                signatures.append(signature)
            shape_signature: dict[str, object] | None = None
            if shape_enabled:
                shape_signature = manager.body_shape(
                    reference_job_id,
                    reference_index,
                )
                shape_signatures.append(shape_signature)
            reference_job: dict[str, object] = {
                "job_id": reference_job_id,
                "person_index": reference_index,
                "job_revision": reference_revision,
                "confidence": (
                    signature["overallConfidence"]
                    if structure_enabled or shape_signature is None
                    else shape_signature["overallConfidence"]
                ),
            }
            if shape_signature is not None:
                reference_job["shape_confidence"] = shape_signature["overallConfidence"]
            reference_jobs.append(reference_job)
        if incompatible_jobs:
            raise ValueError(
                "Multi-reference body fitting requires neutral MHR body "
                "signatures. Incompatible SAM3D job IDs: "
                + ", ".join(incompatible_jobs)
            )
        target = (
            consensus_body_signatures(
                signatures,
                source_ids=[item[0] for item in reference_values],
            )
            if structure_enabled
            else signatures[0]
        )
        consensus = target.get("consensus")
        reference_disagreement = (
            float(consensus["overallRelativeDisagreement"])
            if isinstance(consensus, dict)
            and isinstance(
                consensus.get("overallRelativeDisagreement"),
                (int, float),
            )
            else None
        )
        job_revision = str(reference_jobs[0]["job_revision"])
        reference_set_revision = hashlib.sha256(
            json.dumps(
                reference_jobs,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()[:32]
        current = live_body_proportion_signature(body_status)
        analysis = build_body_proportion_analysis(
            target,
            current,
            body_status,
            strength=strength_value,
            regions=region_values,
        )
        structure_changes = list(analysis["changes"])
        shape_analysis: dict[str, object] | None = None
        shape_target: dict[str, object] | None = None
        shape_reference_disagreement: float | None = None
        if shape_enabled:
            assert current_body_shape is not None
            shape_target = consensus_body_shapes(
                shape_signatures,
                source_ids=[item[0] for item in reference_values],
            )
            shape_consensus = shape_target.get("consensus")
            if isinstance(shape_consensus, dict) and isinstance(
                shape_consensus.get("overallRelativeDisagreement"),
                (int, float),
            ):
                shape_reference_disagreement = float(
                    shape_consensus["overallRelativeDisagreement"]
                )
            shape_analysis = build_body_shape_analysis(
                shape_target,
                current_body_shape,
                body_status,
                strength=shape_strength_value,
                regions=shape_region_values,
            )
        shape_changes = (
            list(shape_analysis["changes"]) if shape_analysis is not None else []
        )
        combined_changes: list[dict[str, object]] = []
        seen_change_keys: set[str] = set()
        for change in [*structure_changes, *shape_changes]:
            if not isinstance(change, dict):
                continue
            key = change.get("key")
            if not isinstance(key, str) or key in seen_change_keys:
                continue
            seen_change_keys.add(key)
            combined_changes.append(change)
            if len(combined_changes) >= 16:
                break
        analysis["structure_changes"] = structure_changes
        analysis["shape_measurements"] = (
            shape_analysis["measurements"] if shape_analysis is not None else []
        )
        analysis["shape_changes"] = shape_changes
        analysis["shape_unavailable"] = (
            shape_analysis["unavailable"] if shape_analysis is not None else []
        )
        analysis["shape_confidence"] = (
            shape_analysis["confidence"] if shape_analysis is not None else None
        )
        analysis["shape_regions"] = sorted(shape_region_values)
        analysis["shape_strength"] = shape_strength_value
        analysis["shape_target"] = shape_target
        analysis["shape_current"] = (
            shape_analysis["current"] if shape_analysis is not None else None
        )
        analysis["shape_reference_disagreement"] = shape_reference_disagreement
        analysis["changes"] = combined_changes
        analysis["canApply"] = bool(
            analysis["ready"]
            and combined_changes
            and body_shape_ready
            and body_status.get("undoAvailable") is not True
            and body_status.get("undoPending") is not True
        )
        if shape_analysis is not None:
            analysis["warning"] = f"{analysis['warning']} {shape_analysis['warning']}"
        live_sam3d = scene.get("sam3d")
        pose_applied = bool(
            isinstance(live_sam3d, dict) and live_sam3d.get("applied") is True
        )
        undo_available = body_status.get("undoAvailable") is True
        undo_pending = body_status.get("undoPending") is True
        person_fit_active = undo_available or undo_pending
        result: dict[str, object] = {
            **analysis,
            "job_id": job_id,
            "job_revision": job_revision,
            "reference_jobs": reference_jobs,
            "reference_count": len(reference_jobs),
            "reference_set_revision": reference_set_revision,
            "target_uid": target_uid,
            "person_index": person_index,
            "proposed_morphs": analysis["changes"],
            "confidence": target["overallConfidence"],
            "model_disagreement": None,
            "reference_disagreement": reference_disagreement,
            "reference_consensus": consensus,
            # The bridge owns one exact undo snapshot per Person, independent
            # of whichever reconstruction happens to be open in the UI.
            "applied": person_fit_active,
            "person_fit_active": person_fit_active,
            "apply_revision": (
                body_status.get("undoRevision") if undo_available else None
            ),
            "can_apply": bool(
                analysis["canApply"] and not pose_applied and not person_fit_active
            ),
            "can_undo": undo_available,
            "undo_pending": undo_pending,
            "pose_applied": pose_applied,
            "body_shape_ready": body_shape_ready,
            "body_shape_preparing": body_shape_preparing,
        }
        if not body_shape_ready:
            result["canApply"] = False
            result["can_apply"] = False
            if body_shape_preparing:
                result["apply_blocked_reason"] = (
                    "VaM is preparing its neutral body-shape calibration. "
                    "Structure analysis and review remain available, but Apply "
                    "will unlock only after the bridge publishes a stable cache."
                )
            else:
                result["apply_blocked_reason"] = (
                    "Apply requires a valid neutral body-shape calibration from "
                    "VaM" + (f": {body_shape_reason}" if body_shape_reason else ".")
                )
        elif undo_pending:
            result["canApply"] = False
            result["can_apply"] = False
            result["apply_blocked_reason"] = (
                "VaM is settling the new body mesh and preparing its exact "
                "undo snapshot. Wait for the next bridge refresh."
            )
        elif person_fit_active:
            result["canApply"] = False
            result["can_apply"] = False
            result["apply_blocked_reason"] = (
                "This Person already has an active body fit. Restore its "
                "one-level morph snapshot before applying another fit."
            )
        elif pose_applied:
            result["canApply"] = False
            result["can_apply"] = False
            result["apply_blocked_reason"] = (
                "Undo the current SAM3D pose before changing body proportions."
            )
        revision = self._body_analysis_revision(result)
        result["analysis_revision"] = revision
        result["analysisRevision"] = revision
        bridge_request = read_bridge_request(self.vam_root)
        bridge_status = scene.get("bridge")
        if (
            isinstance(bridge_request, dict)
            and bridge_request.get("command")
            in {
                "setPersonBodyProportions",
                "undoPersonBodyProportions",
            }
            and bridge_request.get("targetUid") == target_uid
            and isinstance(bridge_status, dict)
            and bridge_status.get("requestId") == bridge_request.get("requestId")
        ):
            state = str(bridge_status.get("state") or "").casefold()
            if state:
                result["state"] = state
            message = str(bridge_status.get("message") or "")
            if message:
                result["message"] = message
        return result

    def apply_sam3d_body_proportions(
        self,
        job_id: str,
        *,
        expected_job_revision: object,
        expected_analysis_revision: object,
        target_uid: object,
        person_index: int = 0,
        references: object = None,
        strength: object = 0.5,
        regions: object = None,
        shape_strength: object = 0.5,
        shape_regions: object = (),
    ) -> dict[str, object]:
        expected_job_revision = self._sam3d_solution_revision(
            expected_job_revision,
            label="expected_job_revision",
        )
        expected_analysis_revision = self._sam3d_solution_revision(
            expected_analysis_revision,
            label="expected_analysis_revision",
        )
        analysis = self.sam3d_body_proportions(
            job_id,
            target_uid=target_uid,
            person_index=person_index,
            references=references,
            strength=strength,
            regions=regions,
            shape_strength=shape_strength,
            shape_regions=shape_regions,
        )
        if analysis["job_revision"] != expected_job_revision:
            raise ValueError("SAM3D job revision has changed; analyze again")
        if analysis["analysis_revision"] != expected_analysis_revision:
            raise ValueError(
                "the Person, morph catalog, or fit settings changed; analyze again"
            )
        if analysis.get("can_apply") is not True:
            reason = analysis.get("apply_blocked_reason")
            raise ValueError(
                str(reason or "no safe body-proportion morph changes are available")
            )
        body_revision = analysis.get("bodyRevision")
        if not isinstance(body_revision, str):
            raise ValueError("the live body-proportion catalog has no revision")
        changes = [
            {"key": item["key"], "value": item["value"]}
            for item in analysis["changes"]
            if isinstance(item, dict)
            and isinstance(item.get("key"), str)
            and isinstance(item.get("value"), (int, float))
        ]
        request_id = self._queue_bridge_request(
            lambda: request_person_body_proportions(
                self.vam_root,
                target_uid=str(analysis["target_uid"]),
                expected_revision=body_revision,
                changes=changes,
            )
        )
        return {
            "job_id": job_id,
            "job_revision": expected_job_revision,
            "reference_jobs": analysis["reference_jobs"],
            "reference_count": analysis["reference_count"],
            "reference_set_revision": analysis["reference_set_revision"],
            "analysis_revision": expected_analysis_revision,
            "apply_revision": None,
            "bridge_request": request_id,
            "target_uid": analysis["target_uid"],
            "proposed_morphs": analysis["changes"],
            "action_state": "queued",
            "applied": False,
            "can_undo": False,
            "message": (
                "Body-proportion morphs are queued in VaM. Apply the pose and "
                "camera after the bridge reports completion. Body Scale is "
                "unchanged, but length morphs can change final height."
            ),
        }

    def undo_sam3d_body_proportions(
        self,
        job_id: str,
        *,
        target_uid: object,
        expected_apply_revision: object,
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        expected = self._sam3d_solution_revision(
            expected_apply_revision,
            label="expected_apply_revision",
        )
        scene = self._require_live_capability(
            "person-body-proportions-v1",
            action_label="undoing body proportions",
        )
        target_uid, _ = self._validate_live_atom_target(
            scene,
            target_uid,
            expected_atom_type="Person",
            create_if_missing=False,
        )
        body_status = self._live_body_proportion_status(scene, target_uid)
        if body_status.get("undoAvailable") is not True:
            raise ValueError("no matching body-proportion undo is available")
        revision = body_status.get("undoRevision")
        if revision != expected:
            raise ValueError(
                "the Person or body-proportion state changed; refresh before undo"
            )
        request_id = self._queue_bridge_request(
            lambda: request_undo_person_body_proportions(
                self.vam_root,
                target_uid=target_uid,
                expected_revision=expected,
            )
        )
        return {
            "job_id": job_id,
            "apply_revision": expected,
            "bridge_request": request_id,
            "target_uid": target_uid,
            "action_state": "queued",
            "message": "The previous body-proportion morph values are being restored.",
        }

    def apply_sam3d_result(
        self,
        job_id: str,
        *,
        expected_job_revision: object,
        target_uid: object,
        camera_uid: object,
        create_camera: bool = False,
        person_index: int = 0,
        height_m: float = 1.65,
        aspect_ratio: str = "16:9",
        output_resolution: str = "1280x720 (HD)",
        image_format: str = "jpeg",
        horizontal_fov: float | None = None,
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        expected_job_revision = self._sam3d_solution_revision(
            expected_job_revision,
            label="expected_job_revision",
        )
        if not isinstance(create_camera, bool):
            raise TypeError("create_camera must be a boolean")
        scene = self._require_live_capability(
            "sam3d-apply-v1",
            action_label="applying a SAM3D pose",
        )
        live_sam3d = scene.get("sam3d")
        if isinstance(live_sam3d, dict) and live_sam3d.get("applied") is True:
            raise ValueError(
                "undo the currently applied SAM3D solution before applying another"
            )
        capabilities = {str(value) for value in scene.get("capabilities", [])}
        if "sam3d-camera-vrfunscript-v1" not in capabilities:
            raise ValueError(
                "the loaded VAM-PIP bridge does not provide the VR/Funscript camera"
            )
        target_uid, _ = self._validate_live_atom_target(
            scene,
            target_uid,
            expected_atom_type="Person",
            create_if_missing=False,
        )
        camera_uid, camera_exists = self._validate_live_atom_target(
            scene,
            camera_uid,
            expected_atom_type="Empty",
            create_if_missing=create_camera,
        )
        if camera_exists:
            camera_atom = self._sam3d_camera_atom(scene, camera_uid)
            if (
                camera_atom is None
                or not isinstance(camera_atom.get("sam3dCamera"), dict)
                or camera_atom["sam3dCamera"].get("compatible") is not True
            ):
                raise ValueError(
                    "camera_uid is not a compatible VR/Funscript camera atom"
                )

        manager = self._sam3d()
        job = manager.get(job_id)
        if job["state"] != "succeeded":
            raise Sam3dJobError("SAM3D job has not completed successfully")
        if job.get("revision") != expected_job_revision:
            raise ValueError("SAM3D job revision has changed; refresh before applying")
        manifest = manager.manifest(job_id)
        if manifest.get("revision") != expected_job_revision:
            raise ValueError("SAM3D job revision has changed; refresh before applying")
        solution = build_vam_solution(
            manifest,
            job_id=job_id,
            person_index=person_index,
            height_m=height_m,
            aspect_ratio=aspect_ratio,
            output_resolution=output_resolution,
            image_format=image_format,
            horizontal_fov=horizontal_fov,
        )
        solution_revision = str(solution["revision"])
        solution_payload = (
            json.dumps(
                solution,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        solution_sha256 = hashlib.sha256(solution_payload.encode("ascii")).hexdigest()
        solution_path = self._sam3d_solution_path(job_id)
        with self._bridge_mailbox_transaction():
            solution_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                solution_path.parent.chmod(0o700)
            except OSError:
                pass
            atomic_write_text(solution_path, solution_payload)
            try:
                solution_path.chmod(0o600)
            except OSError:
                pass
            bridge_request = request_sam3d_apply(
                self.vam_root,
                job_id=job_id,
                expected_revision=solution_revision,
                solution_sha256=solution_sha256,
                target_uid=target_uid,
                camera_uid=camera_uid,
                create_camera=create_camera,
            )
        manager.record_vam_action(
            job_id,
            action="apply",
            revision=solution_revision,
            request_id=bridge_request,
            bridge_instance=self._sam3d_bridge_instance(scene),
            target_uid=target_uid,
            camera_uid=camera_uid,
        )
        return {
            "job_id": job_id,
            "job_revision": expected_job_revision,
            "solution_revision": solution_revision,
            "bridge_request": bridge_request,
            "target_uid": target_uid,
            "camera_uid": camera_uid,
            "create_camera": create_camera,
            "action_state": "queued",
        }

    def undo_sam3d_result(
        self,
        job_id: str,
        *,
        expected_revision: object,
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        scene = self._require_live_capability(
            "sam3d-undo-v1",
            action_label="undoing a SAM3D pose",
        )
        solution = self._load_sam3d_solution(job_id, expected_revision)
        revision = str(solution["revision"])
        live = self._require_current_sam3d_application(
            scene,
            job_id=job_id,
            revision=revision,
        )
        bridge_request = self._queue_bridge_request(
            lambda: request_sam3d_undo(
                self.vam_root,
                job_id=job_id,
                expected_revision=revision,
            )
        )
        self._sam3d().record_vam_action(
            job_id,
            action="undo",
            revision=revision,
            request_id=bridge_request,
            bridge_instance=self._sam3d_bridge_instance(scene),
            target_uid=str(live.get("targetUid") or ""),
            camera_uid=str(live.get("cameraUid") or ""),
        )
        return {
            "job_id": job_id,
            "solution_revision": revision,
            "bridge_request": bridge_request,
            "action_state": "queued",
        }

    def capture_sam3d_result(
        self,
        job_id: str,
        *,
        expected_revision: object,
        camera_uid: object,
    ) -> dict[str, object]:
        job_id = validate_sam3d_job_id(job_id)
        scene = self._require_live_capability(
            "sam3d-capture-v1",
            action_label="capturing a SAM3D camera",
        )
        capabilities = {str(value) for value in scene.get("capabilities", [])}
        if "sam3d-camera-vrfunscript-v1" not in capabilities:
            raise ValueError(
                "the loaded VAM-PIP bridge does not provide the VR/Funscript camera"
            )
        camera_uid, _ = self._validate_live_atom_target(
            scene,
            camera_uid,
            expected_atom_type="Empty",
            create_if_missing=False,
        )
        camera_atom = self._sam3d_camera_atom(scene, camera_uid)
        if (
            camera_atom is None
            or not isinstance(camera_atom.get("sam3dCamera"), dict)
            or camera_atom["sam3dCamera"].get("compatible") is not True
        ):
            raise ValueError("camera_uid is not a compatible VR/Funscript camera atom")
        solution, solution_sha256 = self._read_sam3d_solution(
            job_id,
            expected_revision,
        )
        revision = str(solution["revision"])
        capture_extension, capture_content_type = self._sam3d_capture_media(solution)
        live = self._require_current_sam3d_application(
            scene,
            job_id=job_id,
            revision=revision,
            camera_uid=camera_uid,
        )
        bridge_request = self._queue_bridge_request(
            lambda: request_sam3d_capture(
                self.vam_root,
                job_id=job_id,
                expected_revision=revision,
                solution_sha256=solution_sha256,
                camera_uid=camera_uid,
            )
        )
        self._sam3d().record_vam_action(
            job_id,
            action="capture",
            revision=revision,
            request_id=bridge_request,
            bridge_instance=self._sam3d_bridge_instance(scene),
            target_uid=str(live.get("targetUid") or ""),
            camera_uid=camera_uid,
            capture_extension=capture_extension,
            capture_content_type=capture_content_type,
        )
        return {
            "job_id": job_id,
            "solution_revision": revision,
            "bridge_request": bridge_request,
            "camera_uid": camera_uid,
            "action_state": "queued",
        }

    @staticmethod
    def _timeline_document_is_fresh(document: dict[str, object]) -> bool:
        updated = document.get("updatedAtUtc")
        if not isinstance(updated, str):
            return False
        try:
            parsed = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - parsed).total_seconds()
        return -5 <= age <= 10

    @staticmethod
    def _timeline_token(value: object) -> str:
        if not isinstance(value, str) or len(value) != 32:
            return ""
        if any(character not in "0123456789abcdefABCDEF" for character in value):
            return ""
        return value.lower()

    @staticmethod
    def _timeline_number(
        value: object,
        *,
        lower: float,
        upper: float,
        default: float = 0.0,
    ) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            text = value.strip()
            if not text or len(text) > 32:
                return default
            try:
                result = float(text)
            except ValueError:
                return default
        elif isinstance(value, (int, float)):
            result = float(value)
        else:
            return default
        if not math.isfinite(result):
            return default
        return min(upper, max(lower, result))

    @classmethod
    def _public_timeline_item(
        cls,
        value: object,
        *,
        kind: str,
    ) -> dict[str, object] | None:
        if not isinstance(value, dict):
            return None
        item_id = cls._timeline_token(value.get("id"))
        if not item_id:
            return None
        item: dict[str, object] = {
            "id": item_id,
            "name": _presentation_text(value.get("name"), maximum=256),
            "selected": value.get("selected") is True,
        }
        if kind in {"layer", "clip"}:
            segment_id = cls._timeline_token(value.get("segmentId"))
            item["segmentId"] = segment_id or None
        if kind == "clip":
            layer_id = cls._timeline_token(value.get("layerId"))
            item.update(
                {
                    "layerId": layer_id or None,
                    "qualified": _presentation_text(
                        value.get("qualified"),
                        maximum=512,
                    ),
                    "length": cls._timeline_number(
                        value.get("length"),
                        lower=0,
                        upper=86400,
                    ),
                    "loop": value.get("loop") is True,
                    "playing": value.get("playing") is True,
                    "main": value.get("main") is True,
                    "time": cls._timeline_number(
                        value.get("time"),
                        lower=0,
                        upper=86400,
                    ),
                    "speed": cls._timeline_number(
                        value.get("speed"),
                        lower=-1,
                        upper=5,
                        default=1,
                    ),
                    "weight": cls._timeline_number(
                        value.get("weight"),
                        lower=0,
                        upper=1,
                        default=1,
                    ),
                    "targetCount": _nonnegative_int(value.get("targetCount")),
                }
            )
        return item

    @classmethod
    def _public_timeline_instance(
        cls,
        value: object,
    ) -> dict[str, object] | None:
        if not isinstance(value, dict):
            return None
        timeline_id = cls._timeline_token(value.get("id"))
        revision = cls._timeline_token(value.get("revision"))
        if not timeline_id or not revision:
            return None

        controls = value.get("controls")
        public_controls: list[str] = []
        if isinstance(controls, list):
            seen: set[str] = set()
            for control in controls[:32]:
                if (
                    isinstance(control, str)
                    and control in TIMELINE_CONTROL_OPERATIONS
                    and control not in seen
                ):
                    seen.add(control)
                    public_controls.append(control)

        transport = value.get("transport")
        if not isinstance(transport, dict):
            transport = {}
        public_transport: dict[str, object] = {
            "playing": transport.get("playing") is True,
            "paused": transport.get("paused") is True,
            "time": cls._timeline_number(
                transport.get("time"),
                lower=0,
                upper=86400,
            ),
            "clipTime": cls._timeline_number(
                transport.get("clipTime"),
                lower=0,
                upper=86400,
            ),
            "duration": cls._timeline_number(
                transport.get("duration"),
                lower=0,
                upper=86400,
            ),
            "speed": cls._timeline_number(
                transport.get("speed"),
                lower=-1,
                upper=5,
                default=1,
            ),
            "weight": cls._timeline_number(
                transport.get("weight"),
                lower=0,
                upper=1,
                default=1,
            ),
            "locked": transport.get("locked") is True,
        }

        current = value.get("current")
        if not isinstance(current, dict):
            current = {}
        public_current: dict[str, object] = {}
        for source, destination in (
            ("clipId", "clipId"),
            ("segmentId", "segmentId"),
            ("layerId", "layerId"),
        ):
            token = cls._timeline_token(current.get(source))
            public_current[destination] = token or None
        for key, maximum in (
            ("qualified", 512),
            ("name", 256),
            ("segment", 256),
            ("layer", 256),
        ):
            public_current[key] = _presentation_text(
                current.get(key),
                maximum=maximum,
            )

        collections: dict[str, list[dict[str, object]]] = {}
        for collection_name, kind, maximum in (
            ("segments", "segment", 64),
            ("layers", "layer", 128),
            ("clips", "clip", 256),
        ):
            public_items: list[dict[str, object]] = []
            raw_items = value.get(collection_name)
            if isinstance(raw_items, list):
                for raw_item in raw_items[:maximum]:
                    item = cls._public_timeline_item(raw_item, kind=kind)
                    if item is not None:
                        public_items.append(item)
            collections[collection_name] = public_items

        raw_counts = value.get("counts")
        counts = raw_counts if isinstance(raw_counts, dict) else {}
        raw_limits = value.get("limits")
        limits = raw_limits if isinstance(raw_limits, dict) else {}
        raw_truncated = value.get("truncated")
        truncated = raw_truncated if isinstance(raw_truncated, dict) else {}
        raw_error = value.get("error")
        public_error: dict[str, str] | None = None
        if isinstance(raw_error, dict):
            code = re.sub(
                r"[^a-z0-9-]",
                "",
                _presentation_text(
                    raw_error.get("code"),
                    maximum=64,
                ).casefold(),
            )[:64]
            message = _presentation_text(
                raw_error.get("message"),
                maximum=500,
            )
            if code or message:
                public_error = {
                    "code": code or "adapter-error",
                    "message": (message or "Timeline adapter reported an error."),
                }
        return {
            "id": timeline_id,
            "revision": revision,
            "atomUid": _presentation_text(value.get("atomUid"), maximum=200),
            "label": (
                _presentation_text(value.get("label"), maximum=256) or "Timeline"
            ),
            "enhanced": value.get("enhanced") is True,
            "adapterVersion": _presentation_text(
                value.get("adapterVersion"),
                maximum=64,
            ),
            "ready": value.get("ready") is True,
            "selected": value.get("selected") is True,
            "stateSequence": _nonnegative_int(value.get("stateSequence")),
            "transport": public_transport,
            "current": public_current,
            **collections,
            "counts": {
                "segments": min(
                    1_000_000,
                    _nonnegative_int(counts.get("segments")),
                ),
                "layers": min(
                    1_000_000,
                    _nonnegative_int(counts.get("layers")),
                ),
                "clips": min(
                    1_000_000,
                    _nonnegative_int(counts.get("clips")),
                ),
                "publishedSegments": len(collections["segments"]),
                "publishedLayers": len(collections["layers"]),
                "publishedClips": len(collections["clips"]),
            },
            "limits": {
                "maxSegments": min(
                    64,
                    _nonnegative_int(limits.get("maxSegments")),
                ),
                "maxLayers": min(
                    128,
                    _nonnegative_int(limits.get("maxLayers")),
                ),
                "maxClips": min(
                    256,
                    _nonnegative_int(limits.get("maxClips")),
                ),
                "maxClipsGlobally": min(
                    1024,
                    _nonnegative_int(limits.get("maxClipsGlobally")),
                ),
                "allocatedClips": min(
                    256,
                    _nonnegative_int(limits.get("allocatedClips")),
                ),
            },
            "truncated": {
                "segments": truncated.get("segments") is True,
                "layers": truncated.get("layers") is True,
                "clips": truncated.get("clips") is True,
            },
            "error": public_error,
            "controls": public_controls,
        }

    def timeline(self) -> dict[str, object]:
        """Return the public, bounded Timeline roster from the live bridge."""

        pids = list(self._running_pids())
        bridge = read_bridge_status(self.vam_root)
        document = read_timeline_status(self.vam_root)
        available = bool(
            pids
            and bridge
            and document
            and self._timeline_document_is_fresh(document)
            and document.get("instanceId") == bridge.get("instanceId")
        )
        instances: list[dict[str, object]] = []
        if available and document:
            raw_instances = document.get("instances")
            if isinstance(raw_instances, list):
                for raw_instance in raw_instances[:32]:
                    instance = self._public_timeline_instance(raw_instance)
                    if instance is not None:
                        instances.append(instance)
        timeline_capability_allowlist = {
            "timeline-roster",
            "timeline-transport",
            "timeline-animation-play",
            "timeline-adapter-v1",
        }
        capabilities = (
            [
                capability
                for capability in _public_capabilities(document.get("capabilities"))
                if capability in timeline_capability_allowlist
            ]
            if available and document
            else []
        )
        raw_counts = document.get("counts") if available and document else None
        counts = raw_counts if isinstance(raw_counts, dict) else {}
        raw_limits = document.get("limits") if available and document else None
        limits = raw_limits if isinstance(raw_limits, dict) else {}
        return {
            "available": available,
            "vam_running": bool(pids),
            "loading": (
                document.get("loading") is True if available and document else False
            ),
            "timeline_protocol": (
                _nonnegative_int(document.get("timelineProtocol"))
                if available and document
                else None
            ),
            "instances": instances,
            "truncated": (
                document.get("truncated") is True if available and document else False
            ),
            "counts": {
                "instances": min(
                    1_000_000,
                    _nonnegative_int(counts.get("instances")),
                ),
                "publishedInstances": len(instances),
                "clips": min(
                    32_000_000,
                    _nonnegative_int(counts.get("clips")),
                ),
                "publishedClips": sum(len(instance["clips"]) for instance in instances),
            },
            "limits": {
                "maxInstances": min(
                    32,
                    _nonnegative_int(limits.get("maxInstances")),
                ),
                "maxClips": min(
                    256,
                    _nonnegative_int(limits.get("maxClips")),
                ),
                "maxClipsGlobally": min(
                    1024,
                    _nonnegative_int(limits.get("maxClipsGlobally")),
                ),
            },
            "capabilities": capabilities,
            "bridge": _public_bridge_status(bridge),
            "updated_at_utc": (
                document.get("updatedAtUtc") if available and document else None
            ),
        }

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
            if result.active_changed and self._running_pids():
                set_setting(connection, _LIVE_PACKAGE_RESCAN_SETTING, True)
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
            "added": result.added,
            "active_changed": result.active_changed,
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
            supported = atom_type in ATOM_TYPE_ALLOWLIST
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
                    "risk": "critical",
                    "risk_reason": (
                        f"May replace a {atom_type} atom and load executable plugins."
                    ),
                    "browseable": True,
                    "live_action": supported,
                    "merge_supported": True,
                    "create_supported": supported,
                    "create_capability": "atom-add",
                    "unsupported_reason": (
                        None
                        if supported
                        else "This atom type is not in VaM's native allowlist."
                    ),
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
        target_uid: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        if state not in {"all", "active", "hidden", "missing", "local"}:
            raise ValueError(
                "resource state must be all, active, hidden, missing, or local"
            )
        with connect(self.state_dir) as connection:
            package_choices = list_package_choices(
                connection,
                str(self.addon_dir),
            )
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
                package_choices=package_choices,
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
            clothing_items = [
                item
                for item in result["items"]
                if str(item.get("resource_type") or "").casefold()
                in {"clothing (female)", "clothing (male)"}
            ]
            if clothing_items and target_uid:
                self._annotate_clothing_state(clothing_items, target_uid)
            for item in clothing_items:
                item.pop("resolved_resource_ref", None)
            if category_id:
                result["category"] = category_id
        return result

    def _annotate_clothing_state(
        self,
        items: list[dict[str, object]],
        target_uid: str,
    ) -> None:
        """Join exact resolved catalogue refs to one live Person snapshot."""

        uid = self._validate_target_uid(target_uid)
        scene = self._scene_snapshot(include_clothing_refs=True)
        if not bool(scene.get("available")):
            return
        person = next(
            (
                value
                for value in scene.get("persons", [])
                if isinstance(value, dict) and str(value.get("uid") or "") == uid
            ),
            None,
        )
        if person is None:
            return
        clothing = person.get("clothing")
        if not isinstance(clothing, dict):
            return
        revision = str(clothing.get("revision") or "")
        if re.fullmatch(r"[0-9a-fA-F]{32}", revision) is None:
            return
        raw_active = clothing.get("activeResourceRefs")
        active_refs = (
            {
                str(value).replace("\\", "/").casefold()
                for value in raw_active
                if isinstance(value, str) and value
            }
            if isinstance(raw_active, list)
            else set()
        )
        raw_locked = clothing.get("lockedResourceRefs")
        locked_refs = (
            {
                str(value).replace("\\", "/").casefold()
                for value in raw_locked
                if isinstance(value, str) and value
            }
            if isinstance(raw_locked, list)
            else set()
        )
        gender = str(clothing.get("gender") or "").casefold()
        truncated = bool(clothing.get("truncated"))
        for item in items:
            resource_ref = item.get("resolved_resource_ref")
            if not isinstance(resource_ref, str) or not resource_ref:
                continue
            worn = resource_ref.replace("\\", "/").casefold() in active_refs
            resource_type = str(item.get("resource_type") or "").casefold()
            compatible = (
                gender in {"female", "both"}
                if resource_type == "clothing (female)"
                else gender in {"male", "both"}
            )
            item["clothing_revision"] = revision
            item["worn"] = True if worn else (None if truncated else False)
            item["clothing_locked"] = (
                resource_ref.replace("\\", "/").casefold() in locked_refs
            )
            item["clothing_compatible"] = compatible

    def person_equipment(self, target_uid: str) -> dict[str, object]:
        """Return a bounded public projection of one Person's worn clothing.

        Exact VaM resource references stay inside this method. They are joined
        to catalogue rows and reduced to opaque numeric IDs plus presentation
        metadata before the result leaves the service boundary.
        """

        uid = self._validate_target_uid(target_uid)
        result: dict[str, object] = {
            "available": False,
            "target_uid": uid,
            "revision": "",
            "ready": False,
            "gender": "Unknown",
            "active_count": 0,
            "locked_count": 0,
            "identified_count": 0,
            "unidentified_count": 0,
            "truncated": False,
            "complete": False,
            "items": [],
        }
        scene = self._scene_snapshot(include_clothing_refs=True)
        if not bool(scene.get("available")):
            return result

        person = next(
            (
                value
                for value in scene.get("persons", [])
                if isinstance(value, dict) and str(value.get("uid") or "") == uid
            ),
            None,
        )
        if person is None:
            raise ValueError(f"Person atom is no longer available: {uid}")

        result["available"] = True
        clothing = person.get("clothing")
        if not isinstance(clothing, dict):
            return result

        ready = clothing.get("ready") is True
        raw_gender = str(clothing.get("gender") or "").casefold()
        gender = {
            "female": "Female",
            "male": "Male",
            "both": "Both",
            "none": "None",
        }.get(raw_gender, "Unknown")

        revision = str(clothing.get("revision") or "")
        active_count = _nonnegative_int(clothing.get("activeCount"))
        locked_count = _nonnegative_int(clothing.get("lockedCount"))
        truncated = clothing.get("truncated") is True
        result.update(
            {
                "revision": revision,
                "ready": ready,
                "gender": gender,
                "active_count": active_count,
                "locked_count": locked_count,
                "truncated": truncated,
            }
        )
        if not ready:
            return result
        if re.fullmatch(r"[0-9a-fA-F]{32}", revision) is None:
            raise ValueError(
                "the selected Person has an invalid live clothing revision"
            )

        active_refs: list[str] = []
        active_identities: set[str] = set()
        raw_active = clothing.get("activeResourceRefs")
        if isinstance(raw_active, list):
            for value in raw_active:
                if not isinstance(value, str) or not value:
                    continue
                identity = value.replace("\\", "/").casefold()
                if identity in active_identities:
                    continue
                active_identities.add(identity)
                active_refs.append(value)
        raw_locked = clothing.get("lockedResourceRefs")
        locked_refs = (
            {
                str(value).replace("\\", "/").casefold()
                for value in raw_locked
                if isinstance(value, str) and value
            }
            if isinstance(raw_locked, list)
            else set()
        )

        active_items: list[dict[str, object]] = []
        raw_active_items = clothing.get("activeItems")
        if isinstance(raw_active_items, list):
            for raw_item in raw_active_items[:256]:
                if not isinstance(raw_item, dict):
                    continue
                resource_ref = raw_item.get("resourceRef")
                display_name = _presentation_text(
                    raw_item.get("displayName"),
                    maximum=256,
                )
                active_items.append(
                    {
                        "resource_ref": (
                            resource_ref
                            if isinstance(resource_ref, str) and resource_ref
                            else ""
                        ),
                        "display_name": (display_name or "Unnamed clothing item"),
                        "tags": _presentation_tags(
                            raw_item.get("tags"),
                            maximum=32,
                        ),
                        "locked": raw_item.get("locked") is True,
                    }
                )
        roster_published = isinstance(raw_active_items, list)
        if not roster_published:
            active_items = [
                {
                    "resource_ref": resource_ref,
                    "display_name": "Unnamed clothing item",
                    "tags": [],
                    "locked": (
                        resource_ref.replace("\\", "/").casefold() in locked_refs
                    ),
                }
                for resource_ref in active_refs
            ]

        active_count = max(active_count, len(active_items), len(active_refs))
        roster_locked_count = sum(
            1 for item in active_items if item.get("locked") is True
        )
        locked_count = min(
            active_count,
            max(locked_count, roster_locked_count, len(locked_refs)),
        )
        result["active_count"] = active_count
        result["locked_count"] = locked_count

        with connect(self.state_dir) as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT id, creator, package_name, resource_path,
                           versions_json, tags_json,
                           clothing_versions_json
                    FROM catalog_resources
                    WHERE root = ?
                      AND (
                          LOWER(REPLACE(resource_path, CHAR(92), '/'))
                              LIKE 'custom/clothing/female/%.vam'
                          OR LOWER(REPLACE(resource_path, CHAR(92), '/'))
                              LIKE 'custom/clothing/male/%.vam'
                      )
                    ORDER BY id
                    """,
                    (str(self.vam_root),),
                )
            )
            package_states: dict[
                tuple[str, str],
                dict[str, bool],
            ] = {}
            for package_row in connection.execute(
                """
                SELECT creator, package_name, version_text, enabled
                FROM package_files
                WHERE root = ? AND valid = 1 AND version_text IS NOT NULL
                """,
                (str(self.addon_dir),),
            ):
                family = (
                    str(package_row["creator"] or "").casefold(),
                    str(package_row["package_name"] or "").casefold(),
                )
                version_text = str(package_row["version_text"] or "")
                versions = package_states.setdefault(family, {})
                versions[version_text] = versions.get(version_text, False) or bool(
                    package_row["enabled"]
                )

        local_rows: dict[str, list[sqlite3.Row]] = {}
        packaged_rows: dict[
            tuple[str, str],
            list[tuple[sqlite3.Row, int | None, str]],
        ] = {}
        for row in rows:
            member = _equipment_member(row["resource_path"])
            if member is None or _equipment_resource_type(member) is None:
                continue
            member_identity = member.casefold()
            creator = str(row["creator"] or "")
            package_name = str(row["package_name"] or "")
            if not creator and not package_name:
                local_rows.setdefault(member_identity, []).append(row)
                continue
            if not creator or not package_name:
                continue
            family = (creator.casefold(), package_name.casefold())
            for version_text, enabled in package_states.get(family, {}).items():
                if not _equipment_version_is_eligible(row, version_text):
                    continue
                package_ref = f"{creator}.{package_name}.{version_text}".casefold()
                packaged_rows.setdefault(
                    (package_ref, member_identity),
                    [],
                ).append(
                    (
                        row,
                        _equipment_version(version_text),
                        "active" if enabled else "hidden",
                    )
                )

        items: list[dict[str, object]] = []
        for item_index, active_item in enumerate(active_items):
            raw_ref = str(active_item.get("resource_ref") or "")
            normalized_ref = raw_ref.replace("\\", "/")
            package_ref, separator, raw_member = normalized_ref.partition(":/")
            member = _equipment_member(raw_member if separator else normalized_ref)
            resource_type = (
                _equipment_resource_type(member) if member is not None else None
            )

            row: sqlite3.Row | None = None
            package_version: int | None = None
            local = not bool(separator)
            state = "local"
            if resource_type is not None and separator:
                matches = packaged_rows.get(
                    (package_ref.casefold(), member.casefold()),
                    [],
                )
                if matches:
                    row, package_version, state = matches[0]
            elif resource_type is not None and member is not None:
                matches = local_rows.get(member.casefold(), [])
                if matches:
                    row = matches[0]

            if row is not None and resource_type is not None:
                display_name, tags = _equipment_metadata(row, package_version)
                resource_id = int(row["id"])
                items.append(
                    {
                        "id": resource_id,
                        "key": f"resource-{resource_id}",
                        "actionable": True,
                        "display_name": display_name,
                        "creator": _equipment_text(
                            row["creator"],
                            maximum=500,
                        ),
                        "package": _equipment_text(
                            row["package_name"],
                            maximum=500,
                        ),
                        "resource_type": resource_type,
                        "tags": tags,
                        "slot": _equipment_slot(display_name, tags),
                        "locked": active_item.get("locked") is True,
                        "package_version": package_version,
                        "local": local,
                        "state": state,
                    }
                )
                continue

            display_name = _presentation_text(
                active_item.get("display_name"),
                maximum=256,
            )
            if not display_name:
                display_name = "Unnamed clothing item"
            tags = _presentation_tags(
                active_item.get("tags"),
                maximum=32,
            )
            fallback_resource_type = resource_type
            if fallback_resource_type is None:
                fallback_resource_type = {
                    "female": "Clothing (Female)",
                    "male": "Clothing (Male)",
                }.get(raw_gender, "Clothing")
            items.append(
                {
                    "id": None,
                    "key": _revision_scoped_key(
                        revision,
                        "equipment",
                        item_index,
                    ),
                    "actionable": False,
                    "display_name": display_name,
                    "creator": "",
                    "package": "",
                    "resource_type": fallback_resource_type,
                    "tags": tags,
                    "slot": _equipment_slot(display_name, tags),
                    "locked": active_item.get("locked") is True,
                    "package_version": None,
                    "local": False,
                    "state": "in-game",
                }
            )

        identified_count = sum(1 for item in items if item.get("actionable") is True)
        unidentified_count = max(active_count - identified_count, 0)
        result.update(
            {
                "identified_count": identified_count,
                "unidentified_count": unidentified_count,
                "complete": (not truncated and len(items) == active_count),
                "items": items,
            }
        )
        return result

    def person_hair(self, target_uid: str) -> dict[str, object]:
        """Return a bounded, presentation-only view of active Person hair."""

        uid = self._validate_target_uid(target_uid)
        result: dict[str, object] = {
            "available": False,
            "target_uid": uid,
            "revision": "",
            "ready": False,
            "active_count": 0,
            "locked_count": 0,
            "truncated": False,
            "complete": False,
            "items": [],
        }
        scene = self._scene_snapshot(include_clothing_refs=True)
        if not bool(scene.get("available")):
            return result

        person = next(
            (
                value
                for value in scene.get("persons", [])
                if isinstance(value, dict) and str(value.get("uid") or "") == uid
            ),
            None,
        )
        if person is None:
            raise ValueError(f"Person atom is no longer available: {uid}")

        result["available"] = True
        hair = person.get("hair")
        if not isinstance(hair, dict):
            return result

        ready = hair.get("ready") is True
        revision = str(hair.get("revision") or "")
        active_count = _nonnegative_int(hair.get("activeCount"))
        locked_count = _nonnegative_int(hair.get("lockedCount"))
        truncated = hair.get("truncated") is True
        result.update(
            {
                "revision": revision,
                "ready": ready,
                "active_count": active_count,
                "locked_count": locked_count,
                "truncated": truncated,
            }
        )
        if not ready:
            return result
        if re.fullmatch(r"[0-9a-fA-F]{32}", revision) is None:
            raise ValueError("the selected Person has an invalid live hair revision")

        items: list[dict[str, object]] = []
        raw_items = hair.get("items")
        capabilities = {
            str(value)
            for value in scene.get("capabilities", [])
            if isinstance(value, str)
        }
        action_token_counts: dict[str, int] = {}
        if isinstance(raw_items, list):
            for raw_item in raw_items[:128]:
                if not isinstance(raw_item, dict):
                    continue
                action_token = raw_item.get("actionToken")
                if (
                    isinstance(action_token, str)
                    and re.fullmatch(r"[0-9a-fA-F]{32}", action_token) is not None
                ):
                    identity = action_token.casefold()
                    action_token_counts[identity] = (
                        action_token_counts.get(identity, 0) + 1
                    )
        action_surface_ready = (
            "person-hair-item-toggle" in capabilities
            and not truncated
            and isinstance(raw_items, list)
            and len(raw_items) <= 128
            and len(raw_items) == active_count
            and all(isinstance(raw_item, dict) for raw_item in raw_items)
        )
        if isinstance(raw_items, list):
            for item_index, raw_item in enumerate(raw_items[:128]):
                if not isinstance(raw_item, dict):
                    continue
                display_name = _presentation_text(
                    raw_item.get("displayName"),
                    maximum=256,
                )
                action_token = raw_item.get("actionToken")
                has_action_token = (
                    isinstance(action_token, str)
                    and re.fullmatch(r"[0-9a-fA-F]{32}", action_token) is not None
                    and action_token_counts.get(
                        action_token.casefold(),
                        0,
                    )
                    == 1
                )
                locked = raw_item.get("locked") is True
                items.append(
                    {
                        "key": _revision_scoped_key(
                            revision,
                            "hair",
                            item_index,
                        ),
                        "actionable": (
                            action_surface_ready and has_action_token and not locked
                        ),
                        "display_name": display_name or "Unnamed hair item",
                        "tags": _presentation_tags(
                            raw_item.get("tags"),
                            maximum=32,
                        ),
                        "locked": locked,
                        "simulated": raw_item.get("simulated") is True,
                        "state": "in-game",
                    }
                )

        active_count = max(active_count, len(items))
        locked_count = min(
            active_count,
            max(
                locked_count,
                sum(1 for item in items if item["locked"] is True),
            ),
        )
        result.update(
            {
                "active_count": active_count,
                "locked_count": locked_count,
                "complete": not truncated and len(items) == active_count,
                "items": items,
            }
        )
        return result

    def set_person_hair(
        self,
        *,
        target_uid: str,
        revision: str,
        item_key: str,
        active: bool,
    ) -> dict[str, object]:
        """Disable one exact unlocked Hair layer from a fresh live roster."""

        uid = self._validate_target_uid(target_uid)
        if (
            not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-fA-F]{32}", revision) is None
        ):
            raise ValueError("revision must contain exactly 32 hexadecimal characters")
        if (
            not isinstance(item_key, str)
            or re.fullmatch(r"hair-[0-9a-f]{24}", item_key) is None
        ):
            raise ValueError("item_key is not a valid opaque Hair item key")
        if not isinstance(active, bool):
            raise TypeError("active must be a boolean")
        if active:
            raise ValueError("active Hair layers can only be removed externally")

        with self._bridge_mailbox_transaction():
            scene = self._require_live_capability(
                "person-hair-item-toggle",
                action_label="an active Hair layer can be removed",
                include_clothing_refs=True,
            )
            person = next(
                (
                    value
                    for value in scene.get("persons", [])
                    if isinstance(value, dict) and str(value.get("uid") or "") == uid
                ),
                None,
            )
            if person is None:
                raise ValueError(f"Person atom is no longer available: {uid}")
            hair = person.get("hair")
            if not isinstance(hair, dict) or hair.get("ready") is not True:
                raise ValueError("the selected Person has no ready live Hair snapshot")
            live_revision = str(hair.get("revision") or "")
            if live_revision != revision:
                raise ValueError(
                    "the Person Hair revision is stale; refresh and try again"
                )
            if hair.get("truncated") is True:
                raise ValueError(
                    "the Person Hair roster is truncated and cannot be changed safely"
                )

            raw_items = hair.get("items")
            if not isinstance(raw_items, list):
                raise ValueError(
                    "the selected Person has no actionable live Hair roster"
                )
            if (
                len(raw_items) > 128
                or len(raw_items) != _nonnegative_int(hair.get("activeCount"))
                or any(not isinstance(raw_item, dict) for raw_item in raw_items)
            ):
                raise ValueError(
                    "the Person Hair roster is incomplete or ambiguous; "
                    "refresh and try again"
                )
            matches: list[dict[str, object]] = []
            for item_index, raw_item in enumerate(raw_items[:128]):
                if (
                    isinstance(raw_item, dict)
                    and _revision_scoped_key(
                        live_revision,
                        "hair",
                        item_index,
                    )
                    == item_key
                ):
                    matches.append(raw_item)
            if len(matches) != 1:
                raise ValueError(
                    "the Hair item key is stale or ambiguous; refresh and try again"
                )
            selected = matches[0]
            if selected.get("locked") is True:
                raise ValueError(
                    "the Hair layer is locked in VaM and cannot be removed externally"
                )
            action_token = selected.get("actionToken")
            if (
                not isinstance(action_token, str)
                or re.fullmatch(r"[0-9a-fA-F]{32}", action_token) is None
            ):
                raise ValueError(
                    "the Hair layer does not have a valid private action token"
                )
            token_identity = action_token.casefold()
            token_matches = sum(
                1
                for raw_item in raw_items[:128]
                if isinstance(raw_item, dict)
                and isinstance(raw_item.get("actionToken"), str)
                and str(raw_item["actionToken"]).casefold() == token_identity
            )
            if token_matches != 1:
                raise ValueError(
                    "the Hair layer action token is ambiguous; refresh and try again"
                )

            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_person_hair_item(
                    self.vam_root,
                    target_uid=uid,
                    action_token=action_token,
                    active=False,
                    revision=revision,
                )
            )
            return {
                "operation": "set-person-hair",
                "target_uid": uid,
                "revision": revision,
                "item_key": item_key,
                "active": False,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
            }

    def catalog_facets(self) -> dict[str, object]:
        with connect(self.state_dir) as connection:
            return load_catalog_facets(connection, self.vam_root)

    def resource_thumbnail(
        self,
        resource_id: int,
        *,
        package_version: int | str | None = None,
    ) -> tuple[Path, str] | None:
        version_text = self._validate_lookup_package_version(package_version)
        with connect(self.state_dir) as connection:
            package_choices = list_package_choices(
                connection,
                str(self.addon_dir),
            )
            result = get_resource_thumbnail(
                connection,
                self.vam_root,
                resource_id,
                self.state_dir / "thumbnails",
                addon_root=self.addon_dir,
                version_text=version_text,
                package_choices=package_choices,
            )
        if result is None:
            return None
        return result.path, result.content_type

    def resource_details(
        self,
        resource_id: int,
        *,
        package_version: int | str | None = None,
    ) -> dict[str, object]:
        """Return a lazy, bounded dependency catalogue for one resource."""

        if (
            isinstance(resource_id, bool)
            or not isinstance(resource_id, int)
            or resource_id < 1
        ):
            raise ValueError("resource_id must be a positive integer")
        version_text = self._validate_lookup_package_version(package_version)
        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
            rows, _ = self._rows(connection, refresh=False)
            resource = connection.execute(
                """
                SELECT id, creator, package_name, versions_json, resource_path,
                       resource_type, atom_type
                FROM catalog_resources
                WHERE id = ? AND root = ?
                """,
                (resource_id, str(self.vam_root)),
            ).fetchone()
            if resource is None:
                raise FileNotFoundError(f"unknown catalog resource: {resource_id}")
            choices = list_package_choices(connection, str(self.addon_dir))
            roots_from_fallback = False
            try:
                roots = resource_package_roots(
                    connection,
                    self.vam_root,
                    resource_id,
                    addon_root=self.addon_dir,
                    version_text=version_text,
                    package_choices=choices,
                )
            except ValueError as exc:
                if str(exc) != "resource is missing from its installed package":
                    raise
                creator = str(resource["creator"])
                package_name = str(resource["package_name"])
                family_ids = sorted(
                    {
                        package_id(row)
                        for row in rows
                        if (
                            row["valid"]
                            and row["version_text"]
                            and str(row["creator"]).casefold() == creator.casefold()
                            and str(row["package_name"]).casefold()
                            == package_name.casefold()
                            and (
                                version_text is None
                                or str(row["version_text"]).casefold()
                                == version_text.casefold()
                            )
                        )
                    },
                    key=str.casefold,
                )
                rows, repair_reports = self._package_conflict_reports(
                    connection,
                    rows,
                    family_ids,
                    choices=choices,
                )
                roots = [str(report["package_id"]) for report in repair_reports]
                if not roots:
                    raise
                roots_from_fallback = True
            graph = package_dependency_graph(
                roots,
                rows,
                package_choices=choices,
            )

            ambiguous = [str(value) for value in graph.get("ambiguous_ids", [])]
            if ambiguous:
                rows, _ = self._package_conflict_reports(
                    connection,
                    rows,
                    ambiguous,
                    choices=choices,
                )
                # Logical hashes can distinguish harmless repacks from genuine
                # forks and can change which dependency branches are relevant.
                choices = list_package_choices(connection, str(self.addon_dir))
                try:
                    roots = resource_package_roots(
                        connection,
                        self.vam_root,
                        resource_id,
                        addon_root=self.addon_dir,
                        version_text=version_text,
                        package_choices=choices,
                    )
                    roots_from_fallback = False
                except ValueError as exc:
                    if (
                        not roots_from_fallback
                        or str(exc) != "resource is missing from its installed package"
                    ):
                        raise
                graph = package_dependency_graph(
                    roots,
                    rows,
                    package_choices=choices,
                )

            conflict_ids = [str(value) for value in graph.get("conflict_ids", [])]
            conflict_keys = {identity.casefold() for identity in conflict_ids}
            graph_hash_hydration_needed = any(
                row["valid"]
                and row["version_text"]
                and package_id(row).casefold() in conflict_keys
                and not is_archive_content_sha256(row["content_sha256"])
                for row in rows
            )
            rows, conflicts = self._package_conflict_reports(
                connection,
                rows,
                conflict_ids,
                choices=choices,
            )
            if graph_hash_hydration_needed:
                # A saved choice can initially look stale simply because its
                # only remaining copy has not been logically hashed yet. The
                # conflict report hydrates those hashes, so rebuild the graph
                # before returning rather than publishing one stale frame.
                try:
                    roots = resource_package_roots(
                        connection,
                        self.vam_root,
                        resource_id,
                        addon_root=self.addon_dir,
                        version_text=version_text,
                        package_choices=choices,
                    )
                    roots_from_fallback = False
                except ValueError as exc:
                    if (
                        not roots_from_fallback
                        or str(exc) != "resource is missing from its installed package"
                    ):
                        raise
                graph = package_dependency_graph(
                    roots,
                    rows,
                    package_choices=choices,
                )
                refreshed_conflict_ids = [
                    str(value) for value in graph.get("conflict_ids", [])
                ]
                rows, conflicts = self._package_conflict_reports(
                    connection,
                    rows,
                    refreshed_conflict_ids,
                    choices=choices,
                )
            try:
                location = resolve_resource_archive(
                    connection,
                    self.vam_root,
                    resource_id,
                    addon_root=self.addon_dir,
                    version_text=version_text,
                    package_choices=choices,
                )
            except ValueError as exc:
                if (
                    not roots_from_fallback
                    or str(exc) != "resource is missing from its installed package"
                ):
                    raise
                location = None

        dependencies = graph.get("dependencies")
        if not isinstance(dependencies, list):
            dependencies = []
        reports = {str(report["package_id"]).casefold(): report for report in conflicts}
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                continue
            resolved_id = dependency.get("resolved_id")
            report = (
                reports.get(str(resolved_id).casefold())
                if resolved_id is not None
                else None
            )
            if report is not None:
                dependency["conflict"] = True
                dependency["conflict_resolved"] = bool(report.get("resolved"))
                dependency["selected_content_sha256"] = report.get(
                    "selected_content_sha256"
                )

        counts = graph.get("counts")
        if not isinstance(counts, dict):
            counts = {}
        counts["conflicts"] = len(conflicts)
        path = str(resource["resource_path"])
        return {
            "resource": {
                "id": resource_id,
                "name": Path(path.replace("\\", "/")).stem.removeprefix("Preset_"),
                "resource_path": path,
                "resource_type": str(resource["resource_type"]),
                "atom_type": str(resource["atom_type"]),
                "creator": str(resource["creator"]),
                "package": str(resource["package_name"]),
                "package_ref": location.package_ref if location is not None else None,
                "selected_version": (
                    location.version_text if location is not None else version_text
                ),
                "local": bool(location is not None and location.local_path is not None),
            },
            "detected": True,
            "roots": roots,
            "counts": counts,
            "dependencies": dependencies,
            "conflicts": conflicts,
            "truncated": bool(graph.get("truncated")),
            "edge_count": int(graph.get("edge_count") or 0),
        }

    def choose_package_copy(
        self,
        package_identity: str,
        copy_id: str | None,
        report_revision: str,
    ) -> dict[str, object]:
        """Persist a content choice after validating an opaque report token."""

        identity = package_identity.strip() if isinstance(package_identity, str) else ""
        opaque_copy = copy_id.strip() if isinstance(copy_id, str) else ""
        revision = report_revision.strip() if isinstance(report_revision, str) else ""
        parsed = parse_dependency_ref(identity)
        if (
            not identity
            or len(identity) > 500
            or parsed is None
            or parsed.full_id.casefold() != identity.casefold()
        ):
            raise ValueError("package_id must be an exact package identity")
        if not opaque_copy or re.fullmatch(r"[0-9a-f]{32}", opaque_copy) is None:
            raise ValueError("copy_id must be a 32-character opaque token")
        if re.fullmatch(r"[0-9a-f]{64}", revision) is None:
            raise ValueError("report_revision must be a 64-character token")

        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
            rows, _ = self._rows(connection, refresh=True)
            choices = list_package_choices(connection, str(self.addon_dir))
            rows, reports = self._package_conflict_reports(
                connection,
                rows,
                [identity],
                choices=choices,
            )
            if not reports:
                raise ValueError(
                    f"{identity} does not currently have different same-ID contents"
                )
            report = reports[0]
            if report["report_revision"] != revision:
                raise FileExistsError(
                    "the package copies changed; refresh the dependency report"
                )
            copies = report.get("copies")
            selected_copy = (
                next(
                    (
                        item
                        for item in copies
                        if isinstance(item, dict) and item.get("copy_id") == opaque_copy
                    ),
                    None,
                )
                if isinstance(copies, list)
                else None
            )
            if selected_copy is None:
                raise FileExistsError(
                    "the selected package copy is stale; refresh and try again"
                )
            digest = selected_copy.get("content_sha256")
            if not is_archive_content_sha256(digest):
                raise ValueError("the selected package copy could not be verified")
            choice = PackageCopyChoice(
                package_id=str(report["package_id"]),
                selected_content_sha256=str(digest),
                preferred_logical_path=str(selected_copy["logical_relative_path"]),
            )
            tentative_choices = dict(choices)
            tentative_choices[identity.casefold()] = choice

            # Validate every persistent consumer under the proposed choice
            # before mutating any choice or lease row. Logical hash hydration
            # commits its cache internally, so all user-visible writes must
            # stay below this validation phase to preserve atomicity.
            validation_ids: dict[str, str] = {}
            pin_roots = [str(pin["root_ref"]) for pin in list_pins(connection)]
            if pin_roots:
                pin_graph = package_dependency_graph(
                    pin_roots,
                    rows,
                    package_choices=choices,
                )
                pin_uses_choice = any(
                    isinstance(dependency, dict)
                    and str(dependency.get("resolved_id") or "").casefold()
                    == identity.casefold()
                    for dependency in pin_graph.get("dependencies", [])
                )
                if pin_uses_choice or bool(pin_graph.get("truncated")):
                    pin_resolution = self._resolve_package_roots(
                        connection,
                        rows,
                        [identity],
                        tentative_choices,
                    )
                    if pin_resolution.missing:
                        missing = ", ".join(
                            reference for _, reference in pin_resolution.missing[:10]
                        )
                        raise ValueError(
                            "the selected package content needs unavailable "
                            f"pinned dependencies: {missing}"
                        )
                    for package_row in pin_resolution.selected:
                        selected_id = package_id(package_row)
                        validation_ids[selected_id.casefold()] = selected_id

            active_leases = [
                lease
                for lease in list_leases(connection)
                if not bool(lease["expired"])
                and any(
                    str(package).casefold() == identity.casefold()
                    for package in lease["packages"]
                )
            ]
            prepared_leases: list[tuple[str, Resolution]] = []
            for lease in active_leases:
                lease_id = str(lease["id"])
                lease_context = get_lease_context(connection, lease_id)
                if lease_context is None:
                    raise ValueError(
                        "an active lease predates safe package-copy choices; "
                        "release and reload that asset before changing content"
                    )
                snapshot_ids = [str(package) for package in lease["packages"]]
                lease_roots = list(snapshot_ids)
                if lease_context["kind"] == "resource":
                    # Resource scans currently retain package identities but
                    # not every referenced member path. Swapping any affected
                    # fork could therefore remove an embedded asset even when
                    # its package still resolves. Keep the active resource
                    # immutable; release/reload it after making the choice.
                    raise ValueError(
                        "an active leased resource uses this package; "
                        "release and reload that asset before changing content"
                    )
                lease_resolution = self._resolve_package_roots(
                    connection,
                    rows,
                    lease_roots,
                    tentative_choices,
                )
                if lease_resolution.missing:
                    missing = ", ".join(
                        reference for _, reference in lease_resolution.missing[:10]
                    )
                    raise ValueError(
                        "the selected package content needs unavailable "
                        f"dependencies: {missing}"
                    )
                prepared_leases.append((lease_id, lease_resolution))
                for package_row in lease_resolution.selected:
                    selected_id = package_id(package_row)
                    validation_ids[selected_id.casefold()] = selected_id

            rows = rows_for_root(connection, self.addon_dir)
            rows, downstream_conflicts = self._package_conflict_reports(
                connection,
                rows,
                list(validation_ids.values()),
                choices=tentative_choices,
            )
            unresolved = [
                item for item in downstream_conflicts if not bool(item.get("resolved"))
            ]
            if unresolved:
                raise PackageConflictError(
                    "the selected content reaches another unresolved "
                    "same-ID package conflict",
                    unresolved,
                )

            added_lease_packages = 0
            for lease_id, lease_resolution in prepared_leases:
                for package_row in lease_resolution.selected:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO manager_lease_packages(
                            lease_id, package_id
                        ) VALUES (?, ?)
                        """,
                        (lease_id, package_id(package_row)),
                    )
                    added_lease_packages += cursor.rowcount

            choice = set_package_choice(
                connection,
                str(self.addon_dir),
                choice.package_id,
                choice.selected_content_sha256,
                preferred_logical_path=choice.preferred_logical_path,
            )
            connection.commit()
            refreshed_report = _package_conflict_document(
                [
                    row
                    for row in rows
                    if (
                        row["valid"]
                        and row["version_text"]
                        and package_id(row).casefold() == identity.casefold()
                    )
                ],
                choice=choice,
                vam_running=bool(self._running_pids()),
            )
        return {
            "saved": True,
            "package_id": str(refreshed_report["package_id"]),
            "selected_content_sha256": str(digest),
            "requires_vam_close": bool(refreshed_report.get("requires_vam_close")),
            "affected_leases": len(prepared_leases),
            "added_lease_packages": added_lease_packages,
            "conflict": refreshed_report,
        }

    def lease_resource(
        self,
        resource_id: int,
        *,
        package_version: int | None = None,
        days: float = 3,
        label: str | None = None,
        apply: bool = True,
        bridge_rescan: bool = True,
    ) -> dict[str, object]:
        version_text = self._validate_package_version(package_version)
        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
            rows, _ = self._rows(connection, refresh=True)
            package_choices = list_package_choices(
                connection,
                str(self.addon_dir),
            )
            roots = resource_package_roots(
                connection,
                self.vam_root,
                int(resource_id),
                addon_root=self.addon_dir,
                version_text=version_text,
                package_choices=package_choices,
            )
            resource_location = resolve_resource_archive(
                connection,
                self.vam_root,
                int(resource_id),
                addon_root=self.addon_dir,
                version_text=version_text,
                package_choices=package_choices,
            )
            if resource_location is None:
                raise ValueError("resource is missing from its installed package")
            row = connection.execute(
                """
                SELECT resource_path FROM catalog_resources
                WHERE id = ? AND root = ?
                """,
                (int(resource_id), str(self.vam_root)),
            ).fetchone()
            if label is None and row is not None:
                label = Path(
                    str(row["resource_path"]).replace("\\", "/")
                ).stem.removeprefix("Preset_")
            if roots:
                lease_id, resolution, managed_mode = self._create_lease_record(
                    connection,
                    rows,
                    roots,
                    days=days,
                    label=label,
                )
                set_lease_context(
                    connection,
                    lease_id,
                    kind="resource",
                    resource_id=int(resource_id),
                    package_version=resource_location.version_text,
                    owner_package_id=resource_location.package_ref,
                    resource_path=resource_location.resource_path,
                    archive_member=resource_location.archive_member,
                )
                if apply and not managed_mode:
                    raise ValueError(
                        "managed mode is not active; configure pins and "
                        "activate it first"
                    )
        if not roots:
            return {
                "resource_id": int(resource_id),
                "lease_id": None,
                "roots": [],
                "resolved_packages": 0,
                "applied": False,
                "already_local": True,
            }
        result: dict[str, object] = {
            "resource_id": int(resource_id),
            "lease_id": lease_id,
            "roots": roots,
            "resolved_packages": len(resolution.selected),
            "applied": False,
        }
        if apply:
            result["reconcile"] = self.reconcile(
                apply=True,
                bridge_rescan=bridge_rescan,
            )
            result["applied"] = True
        if version_text is not None:
            result["selected_version"] = version_text
        result["discovered_roots"] = roots
        return result

    @staticmethod
    def _catalog_resource_reference(
        location: object,
        *,
        required_prefix: str,
        extension: str | tuple[str, ...],
        require_preset_basename: bool,
    ) -> str:
        resource_path = str(getattr(location, "resource_path", "")).replace("\\", "/")
        archive_member = getattr(location, "archive_member", None)
        candidate = str(archive_member or resource_path).replace("\\", "/")
        if archive_member is not None:
            while candidate.startswith("./"):
                candidate = candidate[2:]
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
        extensions = (extension,) if isinstance(extension, str) else extension
        if not extensions or any(
            not isinstance(value, str) or not value for value in extensions
        ):
            raise ValueError("catalog resource extension policy is invalid")
        if not any(
            filename.casefold().endswith(value.casefold()) for value in extensions
        ):
            expected = " or ".join(extensions)
            raise ValueError(f"the selected catalog resource is not a {expected} file")
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

    @staticmethod
    def _validate_package_version(package_version: object) -> str | None:
        if package_version is None:
            return None
        if (
            isinstance(package_version, bool)
            or not isinstance(package_version, int)
            or package_version < 0
            or package_version > 2_147_483_647
        ):
            raise ValueError("package_version must be an integer from 0 to 2147483647")
        return str(package_version)

    @staticmethod
    def _validate_lookup_package_version(
        package_version: object,
    ) -> str | None:
        """Validate a read-only exact package lookup version.

        VaM package identities may use the literal ``latest`` suffix.  Live
        mutations deliberately continue to use ``_validate_package_version``
        and therefore remain numeric-only.
        """

        if package_version is None:
            return None
        if isinstance(package_version, str) and package_version.casefold() == "latest":
            return "latest"
        if (
            isinstance(package_version, bool)
            or not isinstance(package_version, int)
            or package_version < 0
            or package_version > 2_147_483_647
        ):
            raise ValueError(
                "package_version must be an integer from 0 to 2147483647 or latest"
            )
        return str(package_version)

    @staticmethod
    def _validate_category_id(category_id: object) -> str:
        if not isinstance(category_id, str):
            raise TypeError("category_id must be a string")
        value = category_id.strip()
        if (
            not value
            or len(value) > 200
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("category_id must contain 1 to 200 printable characters")
        return value

    def _workspace_category(self, category_id: object) -> dict[str, object]:
        value = self._validate_category_id(category_id)
        with connect(self.state_dir) as connection:
            categories = self._workspace_category_descriptors(connection)
        category = next(
            (
                descriptor
                for descriptor in categories
                if str(descriptor.get("id") or "") == value
            ),
            None,
        )
        if category is None:
            raise ValueError(f"unknown workspace category: {value}")
        return category

    def _validate_live_atom_target(
        self,
        scene: dict[str, object],
        target_uid: object,
        *,
        expected_atom_type: str,
        create_if_missing: bool,
    ) -> tuple[str, bool]:
        uid = self._validate_target_uid(target_uid)
        existing = next(
            (
                atom
                for atom in scene.get("atoms", [])
                if isinstance(atom, dict) and str(atom.get("uid") or "") == uid
            ),
            None,
        )
        if existing is not None:
            if create_if_missing:
                raise ValueError("create_if_missing requires target_uid to be absent")
            actual_type = str(existing.get("type") or "")
            if actual_type != expected_atom_type:
                raise ValueError(
                    f"Atom {uid} has type {actual_type or '<unknown>'}; "
                    f"expected {expected_atom_type}"
                )
            return uid, True
        if not create_if_missing:
            raise ValueError(f"Atom is no longer available: {uid}")
        capabilities = {str(value) for value in scene.get("capabilities", [])}
        if "atom-add" not in capabilities:
            raise ValueError("the loaded VAM-PIP bridge does not provide atom-add")
        return uid, False

    def _ensure_bridge_mailbox_idle(self) -> None:
        request = read_bridge_request(self.vam_root)
        if request is None:
            return
        status = read_bridge_status(self.vam_root)
        if not self._bridge_request_is_terminal(request, status):
            raise LiveActionBusyError(
                "the VaM bridge is still handling another request"
            )

    @contextmanager
    def _bridge_mailbox_transaction(
        self,
        *,
        require_idle: bool = True,
        blocking: bool = True,
    ) -> Iterator[None]:
        """Reserve the bridge mailbox across one composite live action.

        The in-process lock orders local actions, while the dedicated file
        lock extends that reservation to other manager processes. Callers may
        safely reconcile package visibility before publishing their request:
        another manager cannot occupy the mailbox in between those steps.
        """

        with self._bridge_mailbox_lock:
            if self._bridge_mailbox_transaction_depth:
                if require_idle:
                    self._ensure_bridge_mailbox_idle()
                self._bridge_mailbox_transaction_depth += 1
                try:
                    yield
                finally:
                    self._bridge_mailbox_transaction_depth -= 1
                return

            lock_dir = bridge_directory(self.vam_root) / ".vampip-mailbox-lock"
            with manager_lock(lock_dir, blocking=blocking):
                if require_idle:
                    self._ensure_bridge_mailbox_idle()
                self._bridge_mailbox_transaction_depth = 1
                try:
                    yield
                finally:
                    self._bridge_mailbox_transaction_depth = 0

    def _queue_bridge_request(self, writer: Callable[[], str]) -> str:
        """Publish one ordered request after an atomic cross-process check."""

        # This is deliberately distinct from state_dir/manager.lock.
        # Live actions can reconcile packages before publication; a dedicated
        # mailbox lock avoids reversing that filesystem lock's order while
        # still serializing managers that use different state directories for
        # the same VaM installation.
        with self._bridge_mailbox_transaction():
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

    def rescan_discovered_packages_if_idle(self) -> str | None:
        """Publish one core VaM rescan for externally changed active archives."""

        with connect(self.state_dir) as connection:
            pending = bool(get_setting(connection, _LIVE_PACKAGE_RESCAN_SETTING, False))
        if not pending:
            return None
        if not self._running_pids():
            with manager_lock(self.state_dir), connect(self.state_dir) as connection:
                set_setting(connection, _LIVE_PACKAGE_RESCAN_SETTING, False)
            return None

        try:
            with self._bridge_mailbox_transaction(blocking=False):
                with (
                    manager_lock(self.state_dir),
                    connect(self.state_dir) as connection,
                ):
                    if not bool(
                        get_setting(
                            connection,
                            _LIVE_PACKAGE_RESCAN_SETTING,
                            False,
                        )
                    ):
                        return None
                    if not self._running_pids():
                        set_setting(
                            connection,
                            _LIVE_PACKAGE_RESCAN_SETTING,
                            False,
                        )
                        return None
                    request_id = request_rescan(self.vam_root)
                    set_setting(
                        connection,
                        _LIVE_PACKAGE_RESCAN_SETTING,
                        False,
                    )
                    return request_id
        except (LiveActionBusyError, ManagerLockBusyError):
            return None

    @staticmethod
    def _lease_requires_bridge_rescan(
        lease: dict[str, object],
    ) -> bool:
        """Return whether a composite action depends on VaM packages.

        Inventory ``enabled`` state only describes the filesystem. It does not
        prove that a running VaM FileManager has registered an archive, for
        example when a valid package appeared externally just before this
        action. Keep the rescan ordered with every package-backed live load;
        the bridge rate-limits redundant core rescans. Resources with no
        package references explicitly report ``already_local`` and remain the
        only safe no-rescan case. Unknown or custom lease results stay
        conservative.
        """

        if lease.get("already_local") is True:
            return False
        roots = lease.get("discovered_roots", lease.get("roots"))
        if isinstance(roots, (list, tuple)) and any(
            isinstance(root, str) and bool(root.strip()) for root in roots
        ):
            return True
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
        include_clothing_refs: bool = False,
    ) -> dict[str, object]:
        scene = (
            self._scene_snapshot(include_clothing_refs=True)
            if include_clothing_refs
            else self.scene()
        )
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
        package_version: int | None = None,
        target_uid: str | None = None,
        days: float = 3,
        merge: bool = False,
        create_if_missing: bool = False,
        confirm_replace: bool = False,
        confirm_critical: bool = False,
    ) -> dict[str, object]:
        """Apply a live-action resource selected solely by catalog identity."""

        with self._bridge_mailbox_transaction():
            return self._apply_resource_locked(
                resource_id,
                package_version=package_version,
                target_uid=target_uid,
                days=days,
                merge=merge,
                create_if_missing=create_if_missing,
                confirm_replace=confirm_replace,
                confirm_critical=confirm_critical,
            )

    def set_person_clothing(
        self,
        resource_id: int,
        *,
        package_version: int | None = None,
        target_uid: str,
        active: bool,
        revision: str,
        days: float = 3,
    ) -> dict[str, object]:
        """Wear or remove one catalog-selected clothing item idempotently."""

        if (
            isinstance(resource_id, bool)
            or not isinstance(resource_id, int)
            or resource_id < 1
        ):
            raise ValueError("resource_id must be a positive integer")
        version_text = self._validate_package_version(package_version)
        uid = self._validate_target_uid(target_uid)
        if not isinstance(active, bool):
            raise TypeError("active must be a boolean")
        if (
            not isinstance(revision, str)
            or re.fullmatch(
                r"[0-9a-fA-F]{32}",
                revision,
            )
            is None
        ):
            raise ValueError("revision must contain exactly 32 hexadecimal characters")
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            raise TypeError("days must be a number")

        with self._bridge_mailbox_transaction():
            with connect(self.state_dir) as connection:
                self._rows(connection, refresh=False)
                package_choices = list_package_choices(
                    connection,
                    str(self.addon_dir),
                )
                row = connection.execute(
                    """
                    SELECT resource_type, atom_type, resource_path
                    FROM catalog_resources
                    WHERE id = ? AND root = ?
                    """,
                    (resource_id, str(self.vam_root)),
                ).fetchone()
                if row is None:
                    raise ValueError(f"unknown catalog resource: {resource_id}")
                resource_type = str(row["resource_type"]).casefold()
                prefixes = {
                    "clothing (female)": "Custom/Clothing/Female/",
                    "clothing (male)": "Custom/Clothing/Male/",
                }
                required_prefix = prefixes.get(resource_type)
                if required_prefix is None:
                    raise ValueError(
                        f"{row['resource_type'] or 'this resource type'} "
                        "is not an individual clothing item"
                    )
                atom_type = str(row["atom_type"] or "")
                if atom_type and atom_type.casefold() != "person":
                    raise ValueError(
                        "the selected clothing item targets a different atom type"
                    )
                location = resolve_resource_archive(
                    connection,
                    self.vam_root,
                    resource_id,
                    addon_root=self.addon_dir,
                    version_text=version_text,
                    package_choices=package_choices,
                )
            if location is None:
                raise ValueError(
                    "the selected catalog clothing resource is not installed"
                )

            scene = self._require_live_capability(
                "person-clothing-item-toggle",
                action_label="an individual clothing item can be changed",
                include_clothing_refs=True,
            )
            person = next(
                (
                    value
                    for value in scene.get("persons", [])
                    if isinstance(value, dict) and str(value.get("uid") or "") == uid
                ),
                None,
            )
            if person is None:
                raise ValueError(f"Person atom is no longer available: {uid}")
            clothing = person.get("clothing")
            if not isinstance(clothing, dict):
                raise ValueError("the selected Person has no live clothing snapshot")
            live_revision = str(clothing.get("revision") or "")
            if live_revision != revision:
                raise ValueError(
                    "the Person clothing revision is stale; refresh and try again"
                )

            resource_ref = self._catalog_resource_reference(
                location,
                required_prefix=required_prefix,
                extension=".vam",
                require_preset_basename=False,
            )
            gender = str(clothing.get("gender") or "").casefold()
            compatible = (
                gender in {"female", "both"}
                if resource_type == "clothing (female)"
                else gender in {"male", "both"}
            )
            if active and not compatible:
                raise ValueError(
                    "the selected clothing item is incompatible with the "
                    "Person's current gender"
                )
            raw_active_refs = clothing.get("activeResourceRefs")
            active_refs = (
                {
                    str(value).replace("\\", "/").casefold()
                    for value in raw_active_refs
                    if isinstance(value, str) and value
                }
                if isinstance(raw_active_refs, list)
                else set()
            )
            normalized_resource_ref = resource_ref.replace("\\", "/").casefold()
            if (
                not active
                and version_text is not None
                and normalized_resource_ref not in active_refs
            ):
                raise ValueError(
                    "the selected exact clothing package version is not currently worn"
                )
            raw_locked_refs = clothing.get("lockedResourceRefs")
            locked_refs = (
                {
                    str(value).replace("\\", "/").casefold()
                    for value in raw_locked_refs
                    if isinstance(value, str) and value
                }
                if isinstance(raw_locked_refs, list)
                else set()
            )
            if not active and normalized_resource_ref in locked_refs:
                raise ValueError(
                    "the selected clothing item is locked in VaM and cannot "
                    "be removed externally"
                )
            lease: dict[str, object] | None = None
            rescan = False
            if active:
                label = Path(str(row["resource_path"]).replace("\\", "/")).stem
                lease = self.lease_resource(
                    resource_id,
                    days=float(days),
                    label=f"Clothing: {label}",
                    apply=True,
                    bridge_rescan=False,
                    **(
                        {"package_version": package_version}
                        if package_version is not None
                        else {}
                    ),
                )
                rescan = self._lease_requires_bridge_rescan(lease)

            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_person_clothing(
                    self.vam_root,
                    target_uid=uid,
                    resource_ref=resource_ref,
                    active=active,
                    revision=revision,
                    rescan=rescan,
                )
            )
            return {
                "resource_id": resource_id,
                "selected_version": location.version_text,
                "category": (
                    "clothing-items-female"
                    if resource_type == "clothing (female)"
                    else "clothing-items-male"
                ),
                "operation": "set-person-clothing",
                "target_uid": uid,
                "active": active,
                "rescan": rescan,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
                "lease": lease,
            }

    def apply_person_resource(
        self,
        resource_id: int,
        *,
        package_version: int | None = None,
        target_uid: str,
        days: float = 3,
        merge: bool = False,
        confirm_critical: bool = False,
    ) -> dict[str, object]:
        """Compatibility wrapper for catalog-backed Person preset application."""

        with self._bridge_mailbox_transaction():
            return self._apply_resource_locked(
                resource_id,
                package_version=package_version,
                target_uid=target_uid,
                days=days,
                merge=merge,
                create_if_missing=False,
                confirm_replace=False,
                confirm_critical=confirm_critical,
                expected_target_kind="person",
            )

    def _apply_resource_locked(
        self,
        resource_id: int,
        *,
        package_version: int | None,
        target_uid: str | None,
        days: float,
        merge: bool,
        create_if_missing: bool,
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
        version_text = self._validate_package_version(package_version)
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            raise TypeError("days must be a number")
        if not isinstance(merge, bool):
            raise TypeError("merge must be a boolean")
        if not isinstance(create_if_missing, bool):
            raise TypeError("create_if_missing must be a boolean")
        if not isinstance(confirm_replace, bool):
            raise TypeError("confirm_replace must be a boolean")
        if not isinstance(confirm_critical, bool):
            raise TypeError("confirm_critical must be a boolean")

        with connect(self.state_dir) as connection:
            self._rows(connection, refresh=False)
            package_choices = list_package_choices(
                connection,
                str(self.addon_dir),
            )
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
                version_text=version_text,
                package_choices=package_choices,
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
        elif resource_type.casefold() == "preset atom":
            target_kind = "atom"
            operation = "apply-atom-preset"
            category_id = _atom_preset_category_id(atom_type)
        elif resource_type.casefold() == "subscenes":
            target_kind = "subscene"
            operation = "load-subscene"
            category_id = "subscenes"
        elif resource_type == "Custom Unity Assets":
            target_kind = "custom-unity-asset"
            operation = "load-custom-unity-asset"
            category_id = "custom-unity-assets"
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
            if create_if_missing:
                raise ValueError(
                    "create_if_missing is not supported for Person presets"
                )
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
                apply=True,
                bridge_rescan=False,
                **(
                    {"package_version": package_version}
                    if package_version is not None
                    else {}
                ),
            )
            rescan = self._lease_requires_bridge_rescan(lease)
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
                "selected_version": location.version_text,
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

        if target_kind == "atom":
            if atom_type not in ATOM_TYPE_ALLOWLIST:
                raise ValueError(
                    f"Preset Atom for {atom_type or '<unknown>'} is browse-only "
                    "because the atom type is not in VaM's native allowlist"
                )
            if not confirm_critical:
                raise ValueError(
                    "confirm_critical must be true before applying an Atom preset"
                )
            if create_if_missing and merge:
                raise ValueError(
                    "merge is not supported when create_if_missing is true"
                )
            scene = self._require_live_capability(
                "atom-preset-apply",
                action_label="an Atom preset can be applied",
            )
            uid, target_exists = self._validate_live_atom_target(
                scene,
                target_uid,
                expected_atom_type=atom_type,
                create_if_missing=create_if_missing,
            )
            if target_exists and not merge and not confirm_replace:
                raise ValueError(
                    "confirm_replace must be true when replacing an existing Atom"
                )
            resource_ref = self._catalog_resource_reference(
                location,
                required_prefix=f"Custom/Atom/{atom_type}/",
                extension=".vap",
                require_preset_basename=True,
            )
            lease = self.lease_resource(
                resource_id,
                days=float(days),
                label=f"{atom_type} preset: {label}",
                apply=True,
                bridge_rescan=False,
                **(
                    {"package_version": package_version}
                    if package_version is not None
                    else {}
                ),
            )
            rescan = self._lease_requires_bridge_rescan(lease)
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_atom_preset(
                    self.vam_root,
                    target_uid=uid,
                    atom_type=atom_type,
                    resource_ref=resource_ref,
                    rescan=rescan,
                    merge=merge,
                    create_if_missing=create_if_missing,
                )
            )
            return {
                "resource_id": resource_id,
                "selected_version": location.version_text,
                "category": category_id,
                "operation": operation,
                "target_uid": uid,
                "target_atom_type": atom_type,
                "target_existed": target_exists,
                "create_if_missing": create_if_missing,
                "resource_ref": resource_ref,
                "merge": merge,
                "rescan": rescan,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
                "lease": lease,
            }

        if target_kind == "custom-unity-asset":
            target_atom_type = "CustomUnityAsset"
            if atom_type not in {"", target_atom_type}:
                raise ValueError(
                    "the selected Custom Unity Asset catalog resource has an "
                    "invalid atom type"
                )
            if merge:
                raise ValueError(
                    "merge is not supported when loading a Custom Unity Asset"
                )
            if not confirm_critical:
                raise ValueError(
                    "confirm_critical must be true before loading a Custom Unity Asset"
                )
            scene = self._require_live_capability(
                "custom-unity-asset-load",
                action_label="a Custom Unity Asset can be loaded",
            )
            uid, target_exists = self._validate_live_atom_target(
                scene,
                target_uid,
                expected_atom_type=target_atom_type,
                create_if_missing=create_if_missing,
            )
            if target_exists and not confirm_replace:
                raise ValueError(
                    "confirm_replace must be true when replacing an existing "
                    "Custom Unity Asset"
                )
            resource_ref = self._catalog_resource_reference(
                location,
                required_prefix="Custom/Assets/",
                extension=(".assetbundle", ".scene"),
                require_preset_basename=False,
            )
            lease = self.lease_resource(
                resource_id,
                days=float(days),
                label=f"Custom Unity Asset: {label}",
                apply=True,
                bridge_rescan=False,
                **(
                    {"package_version": package_version}
                    if package_version is not None
                    else {}
                ),
            )
            rescan = self._lease_requires_bridge_rescan(lease)
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_custom_unity_asset_load(
                    self.vam_root,
                    target_uid=uid,
                    resource_ref=resource_ref,
                    rescan=rescan,
                    create_if_missing=create_if_missing,
                )
            )
            return {
                "resource_id": resource_id,
                "selected_version": location.version_text,
                "category": category_id,
                "operation": operation,
                "target_uid": uid,
                "target_atom_type": target_atom_type,
                "target_existed": target_exists,
                "create_if_missing": create_if_missing,
                "resource_ref": resource_ref,
                "merge": False,
                "rescan": rescan,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
                "lease": lease,
            }

        if target_kind == "subscene":
            if "SubScene" not in ATOM_TYPE_ALLOWLIST:
                raise ValueError(
                    "SubScenes are browse-only because SubScene is not in "
                    "VaM's native allowlist"
                )
            if atom_type != "SubScene":
                raise ValueError(
                    "the selected SubScene catalog resource has an invalid atom type"
                )
            if merge:
                raise ValueError("merge is not supported when loading a SubScene")
            if not confirm_critical:
                raise ValueError(
                    "confirm_critical must be true before loading a SubScene"
                )
            scene = self._require_live_capability(
                "subscene-load",
                action_label="a SubScene can be loaded",
            )
            uid, target_exists = self._validate_live_atom_target(
                scene,
                target_uid,
                expected_atom_type="SubScene",
                create_if_missing=create_if_missing,
            )
            if target_exists and not confirm_replace:
                raise ValueError(
                    "confirm_replace must be true when replacing an existing SubScene"
                )
            resource_ref = self._catalog_resource_reference(
                location,
                required_prefix="Custom/SubScene/",
                extension=".json",
                require_preset_basename=False,
            )
            lease = self.lease_resource(
                resource_id,
                days=float(days),
                label=f"SubScene: {label}",
                apply=True,
                bridge_rescan=False,
                **(
                    {"package_version": package_version}
                    if package_version is not None
                    else {}
                ),
            )
            rescan = self._lease_requires_bridge_rescan(lease)
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_subscene_load(
                    self.vam_root,
                    target_uid=uid,
                    resource_ref=resource_ref,
                    rescan=rescan,
                    create_if_missing=create_if_missing,
                )
            )
            return {
                "resource_id": resource_id,
                "selected_version": location.version_text,
                "category": category_id,
                "operation": operation,
                "target_uid": uid,
                "target_atom_type": "SubScene",
                "target_existed": target_exists,
                "create_if_missing": create_if_missing,
                "resource_ref": resource_ref,
                "merge": False,
                "rescan": rescan,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
                "lease": lease,
            }

        if create_if_missing:
            raise ValueError("create_if_missing is not accepted when loading a Scene")
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
            apply=True,
            bridge_rescan=False,
            **(
                {"package_version": package_version}
                if package_version is not None
                else {}
            ),
        )
        rescan = self._lease_requires_bridge_rescan(lease)
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
            "selected_version": location.version_text,
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

    def select_custom_unity_asset_choice(
        self,
        target_uid: str,
        choice_index: int,
        choice_token: str,
    ) -> dict[str, object]:
        """Select one bridge-published asset from a loaded CUA bundle."""

        uid = self._validate_target_uid(target_uid)
        if (
            isinstance(choice_index, bool)
            or not isinstance(choice_index, int)
            or choice_index < 1
        ):
            raise ValueError("choice_index must be a positive integer")
        if not isinstance(choice_token, str):
            raise TypeError("choice_token must be a string")
        if re.fullmatch(r"[0-9a-fA-F]{32}", choice_token) is None:
            raise ValueError("choice_token must be exactly 32 hexadecimal characters")

        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            scene = self._require_live_capability(
                "custom-unity-asset-choice",
                action_label="a Custom Unity Asset choice can be selected",
            )
            atom = next(
                (
                    value
                    for value in scene.get("atoms", [])
                    if isinstance(value, dict) and str(value.get("uid") or "") == uid
                ),
                None,
            )
            if atom is None:
                raise ValueError(f"Atom is no longer available: {uid}")
            actual_type = str(atom.get("type") or "")
            if actual_type != "CustomUnityAsset":
                raise ValueError(
                    f"Atom {uid} has type {actual_type or '<unknown>'}; "
                    "expected CustomUnityAsset"
                )
            cua = atom.get("cua")
            if not isinstance(cua, dict):
                raise ValueError(
                    "the Custom Unity Asset atom has no current bundle choices"
                )
            if cua.get("loadDll") is not False:
                raise ValueError(
                    "asset choices are unavailable unless DLL loading is off"
                )
            live_token = cua.get("choiceToken")
            if (
                not isinstance(live_token, str)
                or re.fullmatch(r"[0-9a-fA-F]{32}", live_token) is None
                or live_token != choice_token
            ):
                raise ValueError(
                    "the Custom Unity Asset choice token is stale or invalid"
                )
            choices = cua.get("choices")
            choice_exists = bool(
                isinstance(choices, list)
                and any(
                    isinstance(choice, dict)
                    and type(choice.get("index")) is int
                    and choice["index"] == choice_index
                    for choice in choices
                )
            )
            if not choice_exists:
                raise ValueError(
                    "choice_index is not present in the current bundle choices"
                )
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_custom_unity_asset_choice(
                    self.vam_root,
                    target_uid=uid,
                    choice_index=choice_index,
                    choice_token=choice_token,
                )
            )
            return {
                "operation": "select-custom-unity-asset-choice",
                "target_uid": uid,
                "target_atom_type": "CustomUnityAsset",
                "choice_index": choice_index,
                "choice_token": choice_token,
                "bridge_request": request_id,
                "bridge_busy": bridge_message is not None,
                "bridge_message": bridge_message,
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

    def add_atom(
        self,
        category_id: str,
        target_uid: str,
    ) -> dict[str, object]:
        """Idempotently add the allowlisted atom type owned by a category."""

        category = self._workspace_category(category_id)
        operation = str(category.get("operation") or "")
        if not bool(category.get("live_action")) or operation not in {
            "apply-atom-preset",
            "load-custom-unity-asset",
            "load-subscene",
        }:
            raise ValueError(
                f"workspace category {category['id']} is browse-only in this version"
            )
        atom_type = str(category.get("target_atom_type") or "")
        if operation == "apply-atom-preset":
            if atom_type not in ATOM_TYPE_ALLOWLIST:
                raise ValueError(
                    f"workspace category {category['id']} has an unsupported atom type"
                )
        elif operation == "load-subscene":
            if atom_type != "SubScene" or atom_type not in ATOM_TYPE_ALLOWLIST:
                raise ValueError(
                    "the SubScene category has an invalid or unsupported atom type"
                )
        elif atom_type != "CustomUnityAsset" or atom_type not in ATOM_TYPE_ALLOWLIST:
            raise ValueError(
                "the Custom Unity Asset category has an invalid or unsupported "
                "atom type"
            )

        uid = self._validate_target_uid(target_uid)
        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            scene = self._require_live_capability(
                "atom-add",
                action_label="an Atom can be added",
            )
            existing = next(
                (
                    atom
                    for atom in scene.get("atoms", [])
                    if isinstance(atom, dict) and str(atom.get("uid") or "") == uid
                ),
                None,
            )
            if existing is not None:
                actual_type = str(existing.get("type") or "")
                if actual_type != atom_type:
                    raise ValueError(
                        f"Atom {uid} has type {actual_type or '<unknown>'}; "
                        f"expected {atom_type}"
                    )
                return {
                    "operation": "add-atom",
                    "category": str(category["id"]),
                    "target_uid": uid,
                    "target_atom_type": atom_type,
                    "already_exists": True,
                    "bridge_request": None,
                    "bridge_busy": False,
                    "bridge_message": None,
                }
            request_id, bridge_message = self._try_queue_bridge_request(
                lambda: request_add_atom(
                    self.vam_root,
                    atom_type=atom_type,
                    target_uid=uid,
                )
            )
            return {
                "operation": "add-atom",
                "category": str(category["id"]),
                "target_uid": uid,
                "target_atom_type": atom_type,
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

    def control_timeline(
        self,
        *,
        timeline_id: object,
        expected_revision: object,
        operation: object,
        value: object = None,
        clip_id: object = None,
        segment_id: object = None,
        layer_id: object = None,
    ) -> dict[str, object]:
        """Queue one fixed Timeline operation against a published revision."""

        timeline_token = self._timeline_token(timeline_id)
        if not timeline_token:
            raise ValueError("timeline_id must be a 32-character opaque token")
        revision = self._timeline_token(expected_revision)
        if not revision:
            raise ValueError("expected_revision must be a 32-character opaque token")
        if (
            not isinstance(operation, str)
            or operation not in TIMELINE_CONTROL_OPERATIONS
        ):
            accepted = ", ".join(sorted(TIMELINE_CONTROL_OPERATIONS))
            raise ValueError(f"op must be one of: {accepted}")

        supplied_ids = {
            "clipId": clip_id,
            "segmentId": segment_id,
            "layerId": layer_id,
        }
        operation_id = {
            "selectClip": ("clips", "clipId"),
            "playClip": ("clips", "clipId"),
            "selectSegment": ("segments", "segmentId"),
            "selectLayer": ("layers", "layerId"),
        }.get(operation)
        item_token: str | None = None
        if operation_id is not None:
            _, id_name = operation_id
            item_token = self._timeline_token(supplied_ids[id_name])
            if not item_token:
                json_name = {
                    "clipId": "clip_id",
                    "segmentId": "segment_id",
                    "layerId": "layer_id",
                }[id_name]
                raise ValueError(f"{json_name} must be a 32-character opaque token")
            unexpected_ids = [
                {
                    "clipId": "clip_id",
                    "segmentId": "segment_id",
                    "layerId": "layer_id",
                }[name]
                for name, identifier in supplied_ids.items()
                if name != id_name and identifier is not None
            ]
            if unexpected_ids:
                raise ValueError(
                    f"{operation} does not accept " + ", ".join(sorted(unexpected_ids))
                )
        elif any(identifier is not None for identifier in supplied_ids.values()):
            raise ValueError(f"{operation} does not accept an item ID")

        if operation == "setLocked":
            if not isinstance(value, bool):
                raise TypeError("setLocked value must be a boolean")
        elif operation in {"setTime", "setSpeed", "setWeight"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{operation} value must be a finite number")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{operation} value must be a finite number")
            lower, upper = {
                "setTime": (0.0, 86400.0),
                "setSpeed": (-1.0, 5.0),
                "setWeight": (0.0, 1.0),
            }[operation]
            if not lower <= number <= upper:
                raise ValueError(
                    f"{operation} value must be between {lower:g} and {upper:g}"
                )
            value = number
        elif value is not None:
            raise ValueError(f"{operation} does not accept a value")

        with self._bridge_mailbox_lock:
            self._ensure_bridge_mailbox_idle()
            timeline = self.timeline()
            if not timeline["vam_running"]:
                raise ValueError("VaM must be running before controlling Timeline")
            if not timeline["available"]:
                raise ValueError(
                    "the VAM-PIP bridge is not publishing a fresh Timeline snapshot"
                )
            instance = next(
                (
                    candidate
                    for candidate in timeline.get("instances", [])
                    if isinstance(candidate, dict)
                    and candidate.get("id") == timeline_token
                ),
                None,
            )
            if instance is None:
                raise ValueError("Timeline instance is no longer available")
            if instance.get("revision") != revision:
                raise ValueError(
                    "Timeline catalog changed; refresh before sending this control"
                )
            controls = {str(control) for control in instance.get("controls", [])}
            if operation not in controls:
                raise ValueError(
                    f"the selected Timeline instance does not provide {operation}"
                )
            if operation_id is not None:
                collection_name, _ = operation_id
                collection = instance.get(collection_name)
                if not isinstance(collection, list) or not any(
                    isinstance(item, dict) and item.get("id") == item_token
                    for item in collection
                ):
                    raise ValueError(
                        "Timeline item is not part of the expected revision"
                    )

            request_id = self._queue_bridge_request(
                lambda: request_timeline_control(
                    self.vam_root,
                    timeline_id=timeline_token,
                    expected_revision=revision,
                    operation=operation,
                    item_id=item_token,
                    value=value,
                )
            )
        return {
            "timeline_id": timeline_token,
            "expected_revision": revision,
            "operation": operation,
            "bridge_request": request_id,
            "bridge_busy": False,
            "bridge_message": None,
        }

    def _running_pids(self) -> list[int]:
        return self._process_probe()

    def _package_conflict_reports(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
        package_ids: list[str] | tuple[str, ...],
        *,
        choices: dict[str, PackageCopyChoice] | None = None,
        vam_running: bool | None = None,
    ) -> tuple[list[sqlite3.Row], list[dict[str, object]]]:
        """Hydrate and serialize genuine logical conflicts for exact IDs."""

        wanted = {identity.casefold() for identity in package_ids}
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            if row["valid"] and row["version_text"]:
                key = package_id(row).casefold()
                if key in wanted:
                    grouped.setdefault(key, []).append(row)
        current_choices = choices
        if current_choices is None:
            current_choices = list_package_choices(
                connection,
                str(self.addon_dir),
            )
        hash_rows = [
            row
            for key, group in grouped.items()
            if len(group) > 1 or key in current_choices
            for row in group
        ]
        if hash_rows:
            ensure_content_hashes(connection, hash_rows)
            rows = rows_for_root(connection, self.addon_dir)
            grouped.clear()
            for row in rows:
                if row["valid"] and row["version_text"]:
                    key = package_id(row).casefold()
                    if key in wanted:
                        grouped.setdefault(key, []).append(row)

        running = (
            bool(self._running_pids()) if vam_running is None else bool(vam_running)
        )
        reports: list[dict[str, object]] = []
        for key, group in grouped.items():
            signatures = [
                str(row["content_sha256"])
                for row in group
                if is_archive_content_sha256(row["content_sha256"])
            ]
            unique_signatures = set(signatures)
            choice = current_choices.get(key) if current_choices else None
            selected_digest = _choice_digest(choice)
            stale = bool(
                selected_digest is not None and selected_digest not in unique_signatures
            )
            genuine_conflict = len(group) > 1 and (
                len(signatures) != len(group) or len(unique_signatures) > 1
            )
            if not genuine_conflict and not stale:
                continue
            reports.append(
                _package_conflict_document(
                    group,
                    choice=choice,
                    vam_running=running,
                )
            )
        reports.sort(key=lambda report: str(report["package_id"]).casefold())
        return rows, reports

    def _resolve_package_roots(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
        roots: list[str],
        choices: dict[str, PackageCopyChoice],
    ) -> Resolution:
        current_rows = rows
        repaired_choices: set[str] = set()
        while True:
            try:
                return resolve(roots, current_rows, choices=choices)
            except PackageCopyChoiceError as exc:
                current_rows, reports = self._package_conflict_reports(
                    connection,
                    current_rows,
                    [exc.package_id],
                    choices=choices,
                )
                unresolved = [
                    report for report in reports if not bool(report.get("resolved"))
                ]
                if unresolved:
                    raise PackageConflictError(
                        "saved package-copy choice needs attention: " + exc.package_id,
                        unresolved,
                        code="package_copy_choice_stale",
                    ) from exc
                choice_key = exc.package_id.casefold()
                if choice_key in repaired_choices:
                    raise
                repaired_choices.add(choice_key)

    def _verify_desired_copies(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
        desired_ids: list[str],
        *,
        vam_running: bool | None = None,
    ) -> list[sqlite3.Row]:
        """Compare logical contents of ambiguous desired package copies."""

        choices = list_package_choices(connection, str(self.addon_dir))
        rows, reports = self._package_conflict_reports(
            connection,
            rows,
            desired_ids,
            choices=choices,
            vam_running=vam_running,
        )
        unresolved = [report for report in reports if not bool(report.get("resolved"))]
        if unresolved:
            identities = ", ".join(
                str(report["package_id"]) for report in unresolved[:10]
            )
            raise PackageConflictError(
                "same-ID packages contain different data: " + identities,
                unresolved,
            )
        unsafe_live = [
            report for report in reports if bool(report.get("requires_vam_close"))
        ]
        if unsafe_live:
            identities = ", ".join(
                str(report["package_id"]) for report in unsafe_live[:10]
            )
            raise PackageConflictError(
                "close VaM to switch away from the active conflicting copy: "
                + identities,
                unsafe_live,
                code="package_copy_switch_requires_vam_close",
            )
        return rows

    @staticmethod
    def _session_plugin_root_row(
        plugin: SessionPlugin,
        rows: list[sqlite3.Row],
        choices: dict[str, PackageCopyChoice] | None = None,
    ) -> sqlite3.Row | None:
        """Return the archive selected for one packaged plugin root."""

        if plugin.package_ref is None:
            return None
        resolution = resolve([plugin.package_ref], rows, choices=choices)
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
            choices = list_package_choices(connection, str(self.addon_dir))

        pinned_roots = {str(pin["root_ref"]).casefold() for pin in pins}
        enabled_roots = list(preset.enabled_package_roots)
        session_resolution = resolve(enabled_roots, rows, choices=choices)
        items: list[dict[str, object]] = []
        for plugin in preset.plugins:
            root_row = self._session_plugin_root_row(plugin, rows, choices)
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
                choices = list_package_choices(connection, str(self.addon_dir))
                existing = {
                    str(pin["root_ref"]).casefold() for pin in list_pins(connection)
                }
                already_pinned = sum(root.casefold() in existing for root in roots)
                if roots:
                    resolution = self._resolve_package_roots(
                        connection,
                        rows,
                        roots,
                        choices,
                    )
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
            existing = rows_for_root(connection, self.addon_dir)
            rows, scan_result = self._rows(
                connection,
                refresh=refresh_if_empty
                and (not existing or inventory_changed(connection, self.addon_dir)),
            )
            managed_mode = bool(get_setting(connection, "managed_mode", False))
            auto_reconcile = bool(get_setting(connection, "auto_reconcile", True))
            pins = list_pins(connection)
            leases = list_leases(connection)
            choices = list_package_choices(connection, str(self.addon_dir))
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
            package_choice_issue: dict[str, str] | None = None
            if managed_mode:
                try:
                    desired, missing = resolve_managed_set(
                        connection,
                        rows,
                        choices=choices,
                    )
                    pending_plan = build_switch_plan(
                        rows,
                        desired,
                        disable_unselected=True,
                        choices=choices,
                    )
                    pending_disable = len(pending_plan.to_disable)
                    pending_enable = len(pending_plan.to_enable)
                except PackageCopyChoiceError as exc:
                    package_choice_issue = {
                        "package_id": exc.package_id,
                        "error": str(exc),
                    }
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
            "package_choice_issue": package_choice_issue,
            "missing_pins": [
                {"required_by": owner, "reference": reference}
                for owner, reference in missing
            ],
            "vam": {
                "running": bool(pids),
                "pids": pids,
            },
            "bridge": _public_bridge_status(read_bridge_status(self.vam_root)),
            "initial_scan": (
                {
                    "found": scan_result.found,
                    "added": scan_result.added,
                    "active_changed": scan_result.active_changed,
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
            choices = list_package_choices(connection, str(self.addon_dir))

        grouped: dict[str, list[sqlite3.Row]] = {}
        invalid: list[sqlite3.Row] = []
        for row in rows:
            if not row["valid"] or not row["version_text"]:
                invalid.append(row)
                continue
            grouped.setdefault(package_id(row).casefold(), []).append(row)

        items: list[dict[str, object]] = []
        selected_rows: dict[str, sqlite3.Row] = {}
        for group in grouped.values():
            identity_key = package_id(group[0]).casefold()
            choice = choices.get(identity_key)
            try:
                selected = preferred(group, choice)
                choice_stale = False
            except PackageCopyChoiceError:
                selected = preferred(group)
                choice_stale = True
            identity = package_id(selected)
            selected_rows[identity.casefold()] = selected
            active = bool(selected["enabled"])
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
                    "copy_choice": _choice_digest(choice),
                    "copy_choice_stale": choice_stale,
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
        paged = items[offset : offset + limit]
        package_rows = [
            selected_rows[str(item["id"]).casefold()]
            for item in paged
            if bool(item["valid"])
        ]
        with connect(self.state_dir) as connection:
            resource_summaries = package_resource_summaries(
                connection,
                self.vam_root,
                package_rows,
            )
        for item in paged:
            if not bool(item["valid"]):
                item.update(
                    {
                        "resource_count": 0,
                        "resource_type_count": 0,
                        "resource_types": [],
                        "resource_previews": [],
                    }
                )
                continue
            item.update(
                resource_summaries.get(
                    str(item["id"]).casefold(),
                    {
                        "resource_count": 0,
                        "resource_type_count": 0,
                        "resource_types": [],
                        "resource_previews": [],
                    },
                )
            )
        return {
            "items": paged,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def package_resources(
        self,
        package_identity: str,
        *,
        query: str = "",
        resource_types: list[str] | None = None,
        state: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        """Browse catalogue entries verified against one selected package copy."""

        if not isinstance(package_identity, str):
            raise TypeError("package identity must be a string")
        if (
            not package_identity
            or len(package_identity) > 500
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in package_identity
            )
        ):
            raise ValueError(
                "package identity must contain 1 to 500 printable characters"
            )
        reference = parse_dependency_ref(package_identity)
        if reference is None:
            raise ValueError("package identity must be creator.package.version")
        if not isinstance(query, str):
            raise TypeError("q must be a string")
        if len(query) > 500 or any(not character.isprintable() for character in query):
            raise ValueError("q must contain at most 500 printable characters")
        if resource_types is None:
            resource_types = []
        if not isinstance(resource_types, list) or not all(
            isinstance(value, str) for value in resource_types
        ):
            raise TypeError("type filters must be a list of strings")
        if len(resource_types) > 64:
            raise ValueError("at most 64 type filters may be supplied")
        if any(
            len(value) > 200 or any(not character.isprintable() for character in value)
            for value in resource_types
        ):
            raise ValueError(
                "each type filter must contain at most 200 printable characters"
            )
        with manager_lock(self.state_dir), connect(self.state_dir) as connection:
            copies = list(
                connection.execute(
                    """
                    SELECT * FROM package_files
                    WHERE root = ? AND valid = 1
                      AND creator = ? COLLATE NOCASE
                      AND package_name = ? COLLATE NOCASE
                      AND version_text = ? COLLATE NOCASE
                    ORDER BY relative_path COLLATE NOCASE
                    """,
                    (
                        str(self.addon_dir),
                        reference.creator,
                        reference.package,
                        reference.version_text,
                    ),
                )
            )
            if not copies:
                raise FileNotFoundError(
                    f"unknown installed package: {package_identity}"
                )
            choices = list_package_choices(connection, str(self.addon_dir))
            choice = choices.get(reference.full_key)
            rows, conflicts = self._package_conflict_reports(
                connection,
                copies,
                [reference.full_id],
                choices=choices,
            )
            copies = [
                row
                for row in rows
                if (
                    row["valid"]
                    and row["version_text"]
                    and package_id(row).casefold() == reference.full_key
                )
            ]
            unresolved = [
                conflict for conflict in conflicts if not bool(conflict.get("resolved"))
            ]
            if unresolved:
                stale = any(
                    bool(conflict.get("choice_stale")) for conflict in unresolved
                )
                raise PackageConflictError(
                    (
                        "saved package-copy choice needs attention: "
                        if stale
                        else "same-ID packages contain different data: "
                    )
                    + reference.full_id,
                    unresolved,
                    code=(
                        "package_copy_choice_stale"
                        if stale
                        else "package_copy_conflict"
                    ),
                )
            try:
                selected = preferred(copies, choice)
                choice_stale = False
            except PackageCopyChoiceError as exc:
                # Hash hydration above must turn every stale selection into a
                # structured report instead of browsing an arbitrary fallback.
                raise PackageConflictError(
                    "saved package-copy choice needs attention: " + reference.full_id,
                    conflicts,
                    code="package_copy_choice_stale",
                ) from exc
            result = package_resources_for_copy(
                connection,
                self.vam_root,
                selected,
                query=query,
                resource_types=resource_types,
                package_state=state,
                limit=limit,
                offset=offset,
            )
        result["package"] = {
            "id": package_id(selected),
            "family": family_id(selected),
            "creator": selected["creator"],
            "package": selected["package_name"],
            "version": selected["version_text"],
            "active": bool(selected["enabled"]),
            "relative_path": selected["relative_path"],
            "copies": len(copies),
            "copy_choice": _choice_digest(choice),
            "copy_choice_stale": choice_stale,
        }
        return result

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
                choices = list_package_choices(connection, str(self.addon_dir))
                resolution = self._resolve_package_roots(
                    connection,
                    rows,
                    roots,
                    choices,
                )
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

    def _create_lease_record(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
        roots: list[str],
        *,
        days: float,
        label: str | None,
    ) -> tuple[str, Resolution, bool]:
        choices = list_package_choices(connection, str(self.addon_dir))
        resolution = self._resolve_package_roots(
            connection,
            rows,
            roots,
            choices,
        )
        rows = self._verify_desired_copies(
            connection,
            rows,
            [package_id(row) for row in resolution.selected],
        )
        choices = list_package_choices(connection, str(self.addon_dir))
        resolution = self._resolve_package_roots(
            connection,
            rows,
            roots,
            choices,
        )
        lease_id = create_lease(
            connection,
            roots,
            resolution,
            days=days,
            label=label,
        )
        return (
            lease_id,
            resolution,
            bool(get_setting(connection, "managed_mode", False)),
        )

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
                lease_id, resolution, managed_mode = self._create_lease_record(
                    connection,
                    rows,
                    roots,
                    days=days,
                    label=label,
                )
                set_lease_context(
                    connection,
                    lease_id,
                    kind="generic",
                )
                if apply and not managed_mode:
                    raise ValueError(
                        "managed mode is not active; configure pins and "
                        "activate it first"
                    )
        result: dict[str, object] = {
            "lease_id": lease_id,
            "roots": roots,
            "resolved_packages": len(resolution.selected),
            "applied": False,
        }
        if apply:
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
        # Applied reconciliation follows the shared mailbox -> operation ->
        # state lock order across manager processes. Dry runs do not mutate
        # packages or publish bridge work, so they need only local ordering.
        if not apply:
            with self._bridge_mailbox_lock:
                with self._operation_gate:
                    return self._run_reconcile(
                        apply=False,
                        activate=activate,
                        bridge_rescan=bridge_rescan,
                    )

        with self._bridge_mailbox_transaction(require_idle=False):
            with self._operation_gate:
                return self._run_reconcile(
                    apply=True,
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
            if not apply:
                if not self._operation_gate.acquire(blocking=False):
                    return None
                try:
                    return self._run_reconcile(
                        apply=False,
                        activate=activate,
                        bridge_rescan=bridge_rescan,
                    )
                finally:
                    self._operation_gate.release()

            try:
                with self._bridge_mailbox_transaction(
                    require_idle=False,
                    blocking=False,
                ):
                    if not self._operation_gate.acquire(blocking=False):
                        return None
                    try:
                        return self._run_reconcile(
                            apply=True,
                            activate=activate,
                            bridge_rescan=bridge_rescan,
                        )
                    finally:
                        self._operation_gate.release()
            except ManagerLockBusyError:
                return None
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
                choices = list_package_choices(
                    connection,
                    str(self.addon_dir),
                )
                repaired_choices: set[str] = set()
                while True:
                    try:
                        desired, missing = resolve_managed_set(
                            connection,
                            rows,
                            extra_roots=session_roots,
                            choices=choices,
                        )
                        break
                    except PackageCopyChoiceError as exc:
                        rows, reports = self._package_conflict_reports(
                            connection,
                            rows,
                            [exc.package_id],
                            choices=choices,
                        )
                        unresolved = [
                            report
                            for report in reports
                            if not bool(report.get("resolved"))
                        ]
                        if unresolved:
                            raise PackageConflictError(
                                "saved package-copy choice needs attention: "
                                + exc.package_id,
                                unresolved,
                                code="package_copy_choice_stale",
                            ) from exc
                        choice_key = exc.package_id.casefold()
                        if choice_key in repaired_choices:
                            raise
                        repaired_choices.add(choice_key)
                if missing:
                    summary = ", ".join(reference for _, reference in missing[:10])
                    raise ValueError(f"managed package resolution failed: {summary}")
                pids = self._running_pids()
                running = bool(pids)
                rows = self._verify_desired_copies(
                    connection,
                    rows,
                    desired,
                    vam_running=running,
                )
                choices = list_package_choices(connection, str(self.addon_dir))

                full_plan = build_switch_plan(
                    rows,
                    desired,
                    disable_unselected=True,
                    choices=choices,
                )
                plan = (
                    build_switch_plan(
                        rows,
                        desired,
                        disable_unselected=False,
                        choices=choices,
                    )
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

                # VaM is external to the manager lock and may have started or
                # stopped while dependency hashing and plan construction ran.
                # Recheck immediately before the filesystem switch, then
                # revalidate conflict safety against the same runtime decision
                # that selects the disabling or enable-only plan.
                final_pids = self._running_pids()
                final_running = bool(final_pids)
                if final_running != running:
                    running = final_running
                    pids = final_pids
                    rows = self._verify_desired_copies(
                        connection,
                        rows,
                        desired,
                        vam_running=running,
                    )
                    choices = list_package_choices(
                        connection,
                        str(self.addon_dir),
                    )
                    full_plan = build_switch_plan(
                        rows,
                        desired,
                        disable_unselected=True,
                        choices=choices,
                    )
                    plan = (
                        build_switch_plan(
                            rows,
                            desired,
                            disable_unselected=False,
                            choices=choices,
                        )
                        if running
                        else full_plan
                    )
                    pending_disable = len(full_plan.to_disable) if running else 0
                    if bridge_rescan and running and plan.to_enable:
                        self._ensure_bridge_mailbox_idle()
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
        # Reserve the shared mailbox before the operation gate. A managed
        # launch can then nest applied reconciliation without reversing the
        # lock order used by composite live actions.
        with self._bridge_mailbox_transaction(require_idle=False):
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

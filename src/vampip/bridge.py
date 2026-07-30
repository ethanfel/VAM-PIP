from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources
import json
import os
from pathlib import Path
import math
import uuid

from vampip.runtime import atomic_write_text


PROTOCOL_VERSION = 2
TIMELINE_PROTOCOL_VERSION = 1
BRIDGE_RELATIVE_DIR = Path("Saves") / "PluginData" / "VAMPip" / "Bridge"
MAX_RESOURCE_REF_LENGTH = 1000
SCENE_RESOURCE_PREFIX = "Saves/scene/"
SUBSCENE_RESOURCE_PREFIX = "Custom/SubScene/"
CUSTOM_UNITY_ASSET_RESOURCE_PREFIX = "Custom/Assets/"
SAM3D_REFERENCE_RESOURCE_PREFIX = "Custom/Images/VAMPip/SAM3D/"
CLOTHING_RESOURCE_PREFIXES = (
    "Custom/Clothing/Female/",
    "Custom/Clothing/Male/",
)
PERSON_PRESET_PREFIXES = {
    "appearance": "Custom/Atom/Person/Appearance/",
    "animation": "Custom/Atom/Person/AnimationPresets/",
    "breastPhysics": "Custom/Atom/Person/BreastPhysics/",
    "clothing": "Custom/Atom/Person/Clothing/",
    "general": "Custom/Atom/Person/General/",
    "glutePhysics": "Custom/Atom/Person/GlutePhysics/",
    "hair": "Custom/Atom/Person/Hair/",
    "morphs": "Custom/Atom/Person/Morphs/",
    "plugins": "Custom/Atom/Person/Plugins/",
    "pose": "Custom/Atom/Person/Pose/",
    "skin": "Custom/Atom/Person/Skin/",
}
TIMELINE_CONTROL_OPERATIONS = frozenset(
    {
        "play",
        "pause",
        "stop",
        "reset",
        "nextFrame",
        "previousFrame",
        "selectClip",
        "playClip",
        "selectSegment",
        "selectLayer",
        "setTime",
        "setSpeed",
        "setWeight",
        "setLocked",
    }
)
TIMELINE_ID_OPERATIONS = {
    "selectClip": "clipId",
    "playClip": "clipId",
    "selectSegment": "segmentId",
    "selectLayer": "layerId",
}
# VaM 1.22 native non-Person atom types, audited against BrowserAssist 39's
# static native-type registry. Packaged/custom atom types are deliberately not
# accepted: creation and generic preset loading must not become an arbitrary
# AddAtomByType surface.
ATOM_TYPE_ALLOWLIST = frozenset(
    {
        "AnimationPattern",
        "AnimationStep",
        "AptBook01",
        "AptBook02",
        "AptBookShelf",
        "AptChair",
        "AptCoffeeTable",
        "AptJacuzzi",
        "AptJacuzziProp",
        "AptJacuzziRailing",
        "AptLamp",
        "AptOutdoorLight",
        "AptPatioChair",
        "AptPicture01",
        "AptPicture02",
        "AptPlant",
        "AptPlanter",
        "AptRug",
        "AptSmartTV",
        "AptSmartWebTV",
        "AptSofa",
        "AptSpeaker",
        "AptTVStand",
        "AudioSource",
        "Button",
        "Capsule",
        "CityScape",
        "CityScapeNight",
        "ClothGrabSphere",
        "CollisionTrigger",
        "Crypt",
        "Cube",
        "CustomUnityAsset",
        "CyberpunkApartment",
        "CyberpunkApartmentDecor",
        "CyberpunkBed",
        "CyberpunkBedPillow01",
        "CyberpunkBedPillow02",
        "CyberpunkBedPillow03",
        "CyberpunkChair",
        "CyberpunkCoffeeTable",
        "CyberpunkComputer",
        "CyberpunkComputerChair",
        "CyberpunkControlScreen",
        "CyberpunkDresser01",
        "CyberpunkDresser02",
        "CyberpunkKeyboard",
        "CyberpunkLaptop",
        "CyberpunkLight",
        "CyberpunkMouse",
        "CyberpunkMousepad",
        "CyberpunkRemote",
        "CyberpunkSofa",
        "CyberpunkSofaCushion01",
        "CyberpunkSofaCushion02",
        "CyberpunkTable",
        "CyberpunkTablet",
        "CyberpunkWallLight01",
        "CyberpunkWallLight02",
        "CycleForce",
        "DecoDowntimeChair",
        "DecoDowntimeCoffeeTable",
        "DecoDowntimeSideTable",
        "DecoDowntimeStand",
        "Dildo",
        "DreamHomeTV",
        "DreamHomeWebTV",
        "DreamStreetBedroom",
        "DSBR_2TierTable",
        "DSBR_Bed",
        "DSBR_BedPillow",
        "DSBR_Bench",
        "DSBR_BuiltInShelves",
        "DSBR_Chair",
        "DSBR_DecorativePillow",
        "DSBR_Ottoman",
        "DSBR_Shelf",
        "DSBR_ThrowPillow",
        "Empty",
        "Glass",
        "Glass-Stained",
        "GrabPoint",
        "ImagePanel",
        "ImagePanelEmissive",
        "ImagePanelTransparent",
        "ImagePanelTransparentEmissive",
        "InvisibleLight",
        "InvisiblePanel",
        "ISCapsule",
        "ISCone",
        "ISCube",
        "ISCylinder",
        "IslBench",
        "IslFencePost",
        "IslFenceSection",
        "IslOverlook",
        "IslPatioChair",
        "IslPlantWFlowers",
        "IslPotA",
        "IslPotB",
        "IslPotSmall",
        "IslRailingGlass",
        "IslStool",
        "IslTerrain",
        "IslTopiary",
        "IslTree",
        "IslTreePlanter",
        "IslWallPost",
        "IslWallSection",
        "ISSphere",
        "ISTube",
        "LookAtTrigger",
        "LoungeChair",
        "ModernRoomBed",
        "ModernRoomLargeLamp",
        "OldStyleBed",
        "OldStyleChair",
        "OldStylePillow01",
        "OldStylePillow02",
        "OldStyleRoom",
        "OldStyleSideTable",
        "OldStyleVanityStool",
        "Paddle",
        "PlayerNavigationPanel",
        "ReflectiveSlate",
        "ReflectiveWoodPanel",
        "RhythmAudioSource",
        "RhythmForce",
        "SimpleSign",
        "SimSheet",
        "SkullQueenSword",
        "Slate",
        "SpaceBox",
        "Sphere",
        "SubScene",
        "SyncForce",
        "TechnoDancePole",
        "TechnoGirder",
        "TechnoLight",
        "TechnoLightBar",
        "TechnoLightBar+Light",
        "TechnoNeonCircle",
        "TechnoNeonCircle+Light",
        "TechnoNeonHeart",
        "TechnoNeonHeart+Light",
        "TechnoNeonSquare",
        "TechnoNeonSquare+Light",
        "TechnoNeonTriangle",
        "TechnoNeonTriangle+Light",
        "TechnoRingLight",
        "TechnoRingLight+Light",
        "TechnoRoom",
        "TechnoRoundCage",
        "TechnoRoundPlatform",
        "TechnoThrone",
        "Torch",
        "ToyAH",
        "ToyBP",
        "UIButton",
        "UISlider",
        "UIText",
        "UIToggle",
        "VaMLogo",
        "VaMSign",
        "VariableTrigger",
        "Wall",
        "WebBrowser",
        "WebPanel",
        "WebPanelEmissive",
        "WindowCamera",
        "WoodPanel",
    }
)


def bridge_directory(vam_root: Path) -> Path:
    return vam_root.resolve() / BRIDGE_RELATIVE_DIR


def _write_request(vam_root: Path, document: dict[str, object]) -> str:
    request_id = uuid.uuid4().hex
    document = {
        "protocol": PROTOCOL_VERSION,
        "requestId": request_id,
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        **document,
    }
    path = bridge_directory(vam_root) / "request.json"
    atomic_write_text(
        path,
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
    )
    return request_id


def request_rescan(
    vam_root: Path,
    *,
    browser_assist: str = "auto",
) -> str:
    if browser_assist not in {"auto", "off"}:
        raise ValueError("browser_assist must be 'auto' or 'off'")
    return _write_request(
        vam_root,
        {
            "command": "rescan",
            "browserAssist": browser_assist,
        },
    )


def _validate_opaque_token(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) != 32 or any(
        character not in "0123456789abcdefABCDEF" for character in value
    ):
        raise ValueError(f"{label} must be a 32-character opaque token")
    return value.lower()


def _validate_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if len(value) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in value
    ):
        raise ValueError(f"{label} must be a 64-character SHA-256 digest")
    return value.lower()


def request_timeline_control(
    vam_root: Path,
    *,
    timeline_id: str,
    expected_revision: str,
    operation: str,
    item_id: str | None = None,
    value: float | bool | None = None,
) -> str:
    """Publish one revision-bound, allowlisted Timeline operation.

    Browser-facing IDs are bridge-minted opaque tokens. Timeline labels,
    plugin IDs, storable names, and action names are intentionally absent
    from this mailbox document.
    """

    timeline_id = _validate_opaque_token(timeline_id, label="timeline_id")
    expected_revision = _validate_opaque_token(
        expected_revision,
        label="expected_revision",
    )
    if not isinstance(operation, str):
        raise TypeError("operation must be a string")
    if operation not in TIMELINE_CONTROL_OPERATIONS:
        accepted = ", ".join(sorted(TIMELINE_CONTROL_OPERATIONS))
        raise ValueError(f"operation must be one of: {accepted}")

    document: dict[str, object] = {
        "command": "controlTimeline",
        "timelineId": timeline_id,
        "expectedRevision": expected_revision,
        "operation": operation,
    }
    id_field = TIMELINE_ID_OPERATIONS.get(operation)
    if id_field is not None:
        if item_id is None:
            raise ValueError(f"{operation} requires an opaque item ID")
        document[id_field] = _validate_opaque_token(item_id, label=id_field)
    elif item_id is not None:
        raise ValueError(f"{operation} does not accept an item ID")

    if operation == "setLocked":
        if not isinstance(value, bool):
            raise TypeError("setLocked value must be a boolean")
        document["value"] = value
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
        if number < lower or number > upper:
            raise ValueError(
                f"{operation} value must be between {lower:g} and {upper:g}"
            )
        document["value"] = number
    elif value is not None:
        raise ValueError(f"{operation} does not accept a value")

    return _write_request(vam_root, document)


def _validate_target_uid(target_uid: str) -> str:
    if not isinstance(target_uid, str):
        raise TypeError("target_uid must be a string")
    target_uid = target_uid.strip()
    if not target_uid or len(target_uid) > 200:
        raise ValueError("target_uid must contain 1 to 200 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in target_uid):
        raise ValueError("target_uid must not contain control characters")
    return target_uid


def _validate_atom_type(atom_type: str) -> str:
    if not isinstance(atom_type, str):
        raise TypeError("atom_type must be a string")
    if atom_type not in ATOM_TYPE_ALLOWLIST:
        raise ValueError("atom_type is not an allowlisted VaM 1.22 native atom type")
    return atom_type


def _validate_person_preset_resource_ref(
    preset_kind: str,
    resource_ref: str,
) -> None:
    try:
        required_prefix = PERSON_PRESET_PREFIXES[preset_kind]
    except KeyError as error:
        accepted = ", ".join(PERSON_PRESET_PREFIXES)
        raise ValueError(f"preset_kind must be one of: {accepted}") from error
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=required_prefix,
        extension=".vap",
        require_preset_basename=True,
    )


def _validate_clothing_resource_ref(resource_ref: str) -> None:
    package_separator = resource_ref.find(":/")
    member = (
        resource_ref[package_separator + 2 :]
        if package_separator >= 0
        else resource_ref
    )
    prefix = next(
        (
            candidate
            for candidate in CLOTHING_RESOURCE_PREFIXES
            if member.casefold().startswith(candidate.casefold())
        ),
        None,
    )
    if prefix is None:
        accepted = " or ".join(CLOTHING_RESOURCE_PREFIXES)
        raise ValueError(f"clothing resource_ref must be below {accepted}")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=prefix,
        extension=".vam",
        require_preset_basename=False,
    )


def _validate_revision(revision: str) -> str:
    if not isinstance(revision, str):
        raise TypeError("revision must be a string")
    if len(revision) != 32 or any(
        character not in "0123456789abcdefABCDEF" for character in revision
    ):
        raise ValueError("revision must contain exactly 32 hexadecimal characters")
    return revision


def _validate_allowlisted_resource_ref(
    resource_ref: str,
    *,
    required_prefix: str,
    extension: str,
    require_preset_basename: bool,
) -> None:
    if not resource_ref or len(resource_ref) > MAX_RESOURCE_REF_LENGTH:
        raise ValueError(
            f"resource_ref must contain 1 to {MAX_RESOURCE_REF_LENGTH} characters"
        )
    if resource_ref != resource_ref.strip():
        raise ValueError("resource_ref must not have leading or trailing whitespace")
    if "\\" in resource_ref:
        raise ValueError("resource_ref must use forward slashes")
    if any(ord(character) < 32 or ord(character) == 127 for character in resource_ref):
        raise ValueError("resource_ref must not contain control characters")
    if resource_ref.startswith("/") or "://" in resource_ref:
        raise ValueError("resource_ref must not be an absolute path or URI")
    if not resource_ref.casefold().endswith(extension.casefold()):
        raise ValueError(f"resource_ref must name a {extension} resource")
    if require_preset_basename and not resource_ref.rsplit("/", 1)[
        -1
    ].casefold().startswith("preset_"):
        raise ValueError("resource_ref basename must begin with Preset_")
    if any(segment in {"", ".", ".."} for segment in resource_ref.split("/")):
        raise ValueError("resource_ref must not contain empty, '.' or '..' segments")

    package_separator = resource_ref.find(":/")
    if package_separator < 0:
        if ":" in resource_ref or not resource_ref.casefold().startswith(
            required_prefix.casefold()
        ):
            raise ValueError(f"local resource_ref must begin with {required_prefix}")
        return

    package_ref = resource_ref[:package_separator]
    package_member = resource_ref[package_separator + 2 :]
    package_parts = package_ref.split(".")
    if (
        ":" in package_ref
        or "/" in package_ref
        or len(package_parts) < 3
        or any(not part for part in package_parts)
        or ":" in package_member
        or not package_member.casefold().startswith(required_prefix.casefold())
    ):
        raise ValueError(
            "packaged resource_ref must be "
            f"creator.package.version:/{required_prefix}*{extension}"
        )
    if ":/" in package_member:
        raise ValueError("resource_ref contains more than one package separator")


def request_person_preset(
    vam_root: Path,
    target_uid: str,
    preset_kind: str,
    resource_ref: str,
    *,
    rescan: bool = True,
    merge: bool = False,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_person_preset_resource_ref(preset_kind, resource_ref)
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    if not isinstance(merge, bool):
        raise TypeError("merge must be a bool")

    return _write_request(
        vam_root,
        {
            "command": "applyPersonPreset",
            "targetUid": target_uid,
            "presetKind": preset_kind,
            "resourceRef": resource_ref,
            "rescan": rescan,
            "merge": merge,
        },
    )


def request_add_person(vam_root: Path, target_uid: str) -> str:
    return _write_request(
        vam_root,
        {
            "command": "addPerson",
            "targetUid": _validate_target_uid(target_uid),
        },
    )


def request_select_person(vam_root: Path, target_uid: str) -> str:
    return _write_request(
        vam_root,
        {
            "command": "selectPerson",
            "targetUid": _validate_target_uid(target_uid),
        },
    )


def request_person_clothing(
    vam_root: Path,
    target_uid: str,
    resource_ref: str,
    *,
    active: bool,
    revision: str,
    rescan: bool = True,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_clothing_resource_ref(resource_ref)
    if not isinstance(active, bool):
        raise TypeError("active must be a bool")
    revision = _validate_revision(revision)
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    return _write_request(
        vam_root,
        {
            "command": "setPersonClothingResource",
            "targetUid": target_uid,
            "resourceRef": resource_ref,
            "desiredState": "worn" if active else "removed",
            "revision": revision,
            "rescan": rescan,
        },
    )


def request_person_hair_item(
    vam_root: Path,
    target_uid: str,
    action_token: str,
    *,
    active: bool,
    revision: str,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    action_token = _validate_revision(action_token)
    if not isinstance(active, bool):
        raise TypeError("active must be a bool")
    if active:
        raise ValueError("active Hair layers can only be removed externally")
    revision = _validate_revision(revision)
    return _write_request(
        vam_root,
        {
            "command": "setPersonHairItem",
            "targetUid": target_uid,
            "actionToken": action_token,
            "desiredState": "removed",
            "revision": revision,
        },
    )


def request_person_body_proportions(
    vam_root: Path,
    *,
    target_uid: str,
    expected_revision: str,
    changes: list[dict[str, object]],
) -> str:
    if not isinstance(changes, list):
        raise TypeError("changes must be a list")
    if not 1 <= len(changes) <= 16:
        raise ValueError("changes must contain between 1 and 16 morph updates")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, change in enumerate(changes):
        if not isinstance(change, dict) or set(change) != {"key", "value"}:
            raise ValueError(f"changes[{index}] must contain only key and value")
        key = _validate_opaque_token(
            change["key"],
            label=f"changes[{index}].key",
        )
        if key in seen:
            raise ValueError("changes contains a duplicate morph key")
        value = change["value"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or abs(float(value)) > 1.0
        ):
            raise ValueError(f"changes[{index}].value must be a bounded finite number")
        seen.add(key)
        normalized.append({"key": key, "value": float(value)})
    return _write_request(
        vam_root,
        {
            "command": "setPersonBodyProportions",
            "targetUid": _validate_target_uid(target_uid),
            "expectedRevision": _validate_opaque_token(
                expected_revision,
                label="expected_revision",
            ),
            "changes": normalized,
        },
    )


def request_undo_person_body_proportions(
    vam_root: Path,
    *,
    target_uid: str,
    expected_revision: str,
) -> str:
    return _write_request(
        vam_root,
        {
            "command": "undoPersonBodyProportions",
            "targetUid": _validate_target_uid(target_uid),
            "expectedRevision": _validate_opaque_token(
                expected_revision,
                label="expected_revision",
            ),
        },
    )


def request_select_atom(vam_root: Path, target_uid: str) -> str:
    return _write_request(
        vam_root,
        {
            "command": "selectAtom",
            "targetUid": _validate_target_uid(target_uid),
        },
    )


def request_add_atom(vam_root: Path, atom_type: str, target_uid: str) -> str:
    return _write_request(
        vam_root,
        {
            "command": "addAtom",
            "atomType": _validate_atom_type(atom_type),
            "targetUid": _validate_target_uid(target_uid),
        },
    )


def request_atom_preset(
    vam_root: Path,
    target_uid: str,
    atom_type: str,
    resource_ref: str,
    *,
    rescan: bool = True,
    merge: bool = False,
    create_if_missing: bool = False,
) -> str:
    atom_type = _validate_atom_type(atom_type)
    target_uid = _validate_target_uid(target_uid)
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=f"Custom/Atom/{atom_type}/",
        extension=".vap",
        require_preset_basename=True,
    )
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    if not isinstance(merge, bool):
        raise TypeError("merge must be a bool")
    if not isinstance(create_if_missing, bool):
        raise TypeError("create_if_missing must be a bool")
    if merge and create_if_missing:
        raise ValueError("merge and create_if_missing cannot both be true")
    return _write_request(
        vam_root,
        {
            "command": "applyAtomPreset",
            "targetUid": target_uid,
            "atomType": atom_type,
            "resourceRef": resource_ref,
            "rescan": rescan,
            "merge": merge,
            "createIfMissing": create_if_missing,
        },
    )


def request_subscene_load(
    vam_root: Path,
    target_uid: str,
    resource_ref: str,
    *,
    rescan: bool = True,
    create_if_missing: bool = False,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=SUBSCENE_RESOURCE_PREFIX,
        extension=".json",
        require_preset_basename=False,
    )
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    if not isinstance(create_if_missing, bool):
        raise TypeError("create_if_missing must be a bool")
    return _write_request(
        vam_root,
        {
            "command": "loadSubscene",
            "targetUid": target_uid,
            "resourceRef": resource_ref,
            "rescan": rescan,
            "createIfMissing": create_if_missing,
        },
    )


def _validate_custom_unity_asset_resource_ref(resource_ref: str) -> None:
    folded = resource_ref.casefold()
    if folded.endswith(".assetbundle"):
        extension = ".assetbundle"
    elif folded.endswith(".scene"):
        extension = ".scene"
    else:
        raise ValueError("resource_ref must name a .assetbundle or .scene resource")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=CUSTOM_UNITY_ASSET_RESOURCE_PREFIX,
        extension=extension,
        require_preset_basename=False,
    )


def request_custom_unity_asset_load(
    vam_root: Path,
    target_uid: str,
    resource_ref: str,
    *,
    rescan: bool = True,
    create_if_missing: bool = False,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_custom_unity_asset_resource_ref(resource_ref)
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    if not isinstance(create_if_missing, bool):
        raise TypeError("create_if_missing must be a bool")
    return _write_request(
        vam_root,
        {
            "command": "loadCustomUnityAsset",
            "targetUid": target_uid,
            "resourceRef": resource_ref,
            "rescan": rescan,
            "createIfMissing": create_if_missing,
        },
    )


def request_custom_unity_asset_choice(
    vam_root: Path,
    target_uid: str,
    choice_index: int,
    choice_token: str,
) -> str:
    target_uid = _validate_target_uid(target_uid)
    if isinstance(choice_index, bool) or not isinstance(choice_index, int):
        raise TypeError("choice_index must be an int")
    if choice_index <= 0 or choice_index > 2_147_483_647:
        raise ValueError("choice_index must be a positive 32-bit chooser index")
    if not isinstance(choice_token, str):
        raise TypeError("choice_token must be a string")
    if len(choice_token) != 32 or any(
        character not in "0123456789abcdefABCDEF" for character in choice_token
    ):
        raise ValueError("choice_token must contain exactly 32 hexadecimal characters")
    return _write_request(
        vam_root,
        {
            "command": "selectCustomUnityAssetChoice",
            "targetUid": target_uid,
            "choiceIndex": choice_index,
            "choiceToken": choice_token.casefold(),
        },
    )


def request_scene_load(
    vam_root: Path,
    resource_ref: str,
    *,
    rescan: bool = True,
    merge: bool = False,
) -> str:
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=SCENE_RESOURCE_PREFIX,
        extension=".json",
        require_preset_basename=False,
    )
    if not isinstance(rescan, bool):
        raise TypeError("rescan must be a bool")
    if not isinstance(merge, bool):
        raise TypeError("merge must be a bool")
    return _write_request(
        vam_root,
        {
            "command": "loadScene",
            "resourceRef": resource_ref,
            "rescan": rescan,
            "merge": merge,
        },
    )


def request_sam3d_apply(
    vam_root: Path,
    *,
    job_id: str,
    expected_revision: str,
    solution_sha256: str,
    target_uid: str,
    camera_uid: str,
    create_camera: bool,
    keep_reference: bool = False,
    expected_job_revision: str | None = None,
    resource_ref: str | None = None,
    resource_sha256: str | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
) -> str:
    if not isinstance(create_camera, bool):
        raise TypeError("create_camera must be a bool")
    if not isinstance(keep_reference, bool):
        raise TypeError("keep_reference must be a bool")
    reference_fields = (
        expected_job_revision,
        resource_ref,
        resource_sha256,
        source_width,
        source_height,
    )
    if keep_reference:
        if any(value is None for value in reference_fields):
            raise ValueError(
                "keep_reference requires the exact staged reference metadata"
            )
    elif any(value is not None for value in reference_fields):
        raise ValueError(
            "staged reference metadata is only valid when keep_reference is true"
        )
    document: dict[str, object] = {
        "command": "applySam3dResult",
        "jobId": _validate_opaque_token(job_id, label="job_id"),
        "expectedRevision": _validate_opaque_token(
            expected_revision,
            label="expected_revision",
        ),
        "solutionSha256": _validate_sha256(
            solution_sha256,
            label="solution_sha256",
        ),
        "targetUid": _validate_target_uid(target_uid),
        "cameraUid": _validate_target_uid(camera_uid),
        "createCamera": create_camera,
        "keepReference": keep_reference,
    }
    if keep_reference:
        document.update(
            _sam3d_reference_request_fields(
                job_id=job_id,
                expected_job_revision=expected_job_revision,
                resource_ref=resource_ref,
                resource_sha256=resource_sha256,
                source_width=source_width,
                source_height=source_height,
            )
        )
    return _write_request(
        vam_root,
        document,
    )


def request_sam3d_pair_apply(
    vam_root: Path,
    *,
    job_id: str,
    expected_revision: str,
    solution_sha256: str,
    camera_uid: str,
    create_camera: bool,
) -> str:
    if not isinstance(create_camera, bool):
        raise TypeError("create_camera must be a bool")
    return _write_request(
        vam_root,
        {
            "command": "applySam3dPair",
            "jobId": _validate_opaque_token(job_id, label="job_id"),
            "expectedRevision": _validate_opaque_token(
                expected_revision,
                label="expected_revision",
            ),
            "solutionSha256": _validate_sha256(
                solution_sha256,
                label="solution_sha256",
            ),
            "cameraUid": _validate_target_uid(camera_uid),
            "createCamera": create_camera,
        },
    )


def _sam3d_reference_request_fields(
    *,
    job_id: str,
    expected_job_revision: object,
    resource_ref: object,
    resource_sha256: object,
    source_width: object,
    source_height: object,
) -> dict[str, object]:
    job_id = _validate_opaque_token(job_id, label="job_id")
    expected_job_revision = _validate_opaque_token(
        expected_job_revision,
        label="expected_job_revision",
    )
    if not isinstance(resource_ref, str):
        raise TypeError("resource_ref must be a string")
    extension = Path(resource_ref).suffix.casefold()
    if extension not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("SAM3D reference resource_ref must name a JPG or PNG image")
    _validate_allowlisted_resource_ref(
        resource_ref,
        required_prefix=SAM3D_REFERENCE_RESOURCE_PREFIX,
        extension=extension,
        require_preset_basename=False,
    )
    expected_ref = f"{SAM3D_REFERENCE_RESOURCE_PREFIX}{job_id}{extension}"
    if resource_ref != expected_ref:
        raise ValueError(
            "SAM3D reference resource_ref must exactly match its job ID"
        )
    resource_sha256 = _validate_sha256(
        resource_sha256,
        label="resource_sha256",
    )
    dimensions: list[int] = []
    for label, value in (
        ("source_width", source_width),
        ("source_height", source_height),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an int")
        if value < 1 or value > 32_768:
            raise ValueError(f"{label} must be between 1 and 32768")
        dimensions.append(value)
    if dimensions[0] * dimensions[1] > 50_000_000:
        raise ValueError("SAM3D reference dimensions exceed the safe pixel limit")
    return {
        "expectedJobRevision": expected_job_revision,
        "referenceResourceRef": resource_ref,
        "referenceSha256": resource_sha256,
        "referenceWidth": dimensions[0],
        "referenceHeight": dimensions[1],
    }


def request_sam3d_reference(
    vam_root: Path,
    *,
    job_id: str,
    expected_job_revision: str,
    expected_revision: str,
    solution_sha256: str,
    resource_ref: str,
    resource_sha256: str,
    source_width: int,
    source_height: int,
    target_uid: str,
    camera_uid: str,
    create_camera: bool,
) -> str:
    if not isinstance(create_camera, bool):
        raise TypeError("create_camera must be a bool")
    document: dict[str, object] = {
        "command": "showSam3dReference",
        "jobId": _validate_opaque_token(job_id, label="job_id"),
        "expectedRevision": _validate_opaque_token(
            expected_revision,
            label="expected_revision",
        ),
        "solutionSha256": _validate_sha256(
            solution_sha256,
            label="solution_sha256",
        ),
        "targetUid": _validate_target_uid(target_uid),
        "cameraUid": _validate_target_uid(camera_uid),
        "createCamera": create_camera,
    }
    document.update(
        _sam3d_reference_request_fields(
            job_id=job_id,
            expected_job_revision=expected_job_revision,
            resource_ref=resource_ref,
            resource_sha256=resource_sha256,
            source_width=source_width,
            source_height=source_height,
        )
    )
    return _write_request(vam_root, document)


def request_remove_sam3d_reference(
    vam_root: Path,
    *,
    job_id: str,
    expected_job_revision: str,
) -> str:
    return _write_request(
        vam_root,
        {
            "command": "removeSam3dReference",
            "jobId": _validate_opaque_token(job_id, label="job_id"),
            "expectedJobRevision": _validate_opaque_token(
                expected_job_revision,
                label="expected_job_revision",
            ),
        },
    )


def request_sam3d_undo(
    vam_root: Path,
    *,
    job_id: str,
    expected_revision: str,
) -> str:
    return _write_request(
        vam_root,
        {
            "command": "undoSam3dResult",
            "jobId": _validate_opaque_token(job_id, label="job_id"),
            "expectedRevision": _validate_opaque_token(
                expected_revision,
                label="expected_revision",
            ),
        },
    )


def request_sam3d_capture(
    vam_root: Path,
    *,
    job_id: str,
    expected_revision: str,
    solution_sha256: str,
    camera_uid: str,
) -> str:
    return _write_request(
        vam_root,
        {
            "command": "captureSam3dResult",
            "jobId": _validate_opaque_token(job_id, label="job_id"),
            "expectedRevision": _validate_opaque_token(
                expected_revision,
                label="expected_revision",
            ),
            "solutionSha256": _validate_sha256(
                solution_sha256,
                label="solution_sha256",
            ),
            "cameraUid": _validate_target_uid(camera_uid),
        },
    )


def _read_bridge_document(
    path: Path,
    *,
    accepted_protocols: frozenset[int] = frozenset({PROTOCOL_VERSION}),
) -> dict[str, object] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    protocol = document.get("protocol")
    if isinstance(protocol, str):
        try:
            protocol = int(protocol)
        except ValueError:
            return None
    if isinstance(protocol, bool) or protocol not in accepted_protocols:
        return None
    document["protocol"] = protocol
    return document


def _normalize_bool(document: dict[str, object], key: str) -> None:
    value = document.get(key)
    if not isinstance(value, str):
        return
    folded = value.strip().casefold()
    if folded == "true":
        document[key] = True
    elif folded == "false":
        document[key] = False


def _normalize_nonnegative_int(document: dict[str, object], key: str) -> None:
    value = document.get(key)
    if not isinstance(value, str):
        return
    text = value.strip()
    if text.isdecimal() and len(text) <= 10:
        parsed = int(text)
        if parsed <= 2_147_483_647:
            document[key] = parsed


def read_scene_status(vam_root: Path) -> dict[str, object] | None:
    document = _read_bridge_document(bridge_directory(vam_root) / "scene.json")
    if document is None:
        return None
    _normalize_bool(document, "loading")
    persons = document.get("persons")
    if isinstance(persons, list):
        for person in persons:
            if isinstance(person, dict):
                _normalize_bool(person, "selected")
                clothing = person.get("clothing")
                if isinstance(clothing, dict):
                    _normalize_bool(clothing, "ready")
                    _normalize_bool(clothing, "truncated")
                    _normalize_nonnegative_int(clothing, "activeCount")
                    _normalize_nonnegative_int(clothing, "lockedCount")
                    active_items = clothing.get("activeItems")
                    if isinstance(active_items, list):
                        for item in active_items[:256]:
                            if isinstance(item, dict):
                                _normalize_bool(item, "locked")
                hair = person.get("hair")
                if isinstance(hair, dict):
                    _normalize_bool(hair, "ready")
                    _normalize_bool(hair, "truncated")
                    _normalize_nonnegative_int(hair, "activeCount")
                    _normalize_nonnegative_int(hair, "lockedCount")
                    hair_items = hair.get("items")
                    if isinstance(hair_items, list):
                        for item in hair_items[:128]:
                            if not isinstance(item, dict):
                                continue
                            _normalize_bool(item, "locked")
                            _normalize_bool(item, "simulated")
                body_proportions = person.get("bodyProportions")
                if isinstance(body_proportions, dict):
                    for key in (
                        "ready",
                        "selectedOnly",
                        "undoAvailable",
                        "undoPending",
                        "blockedBySam3d",
                        "bodyShapeReady",
                        "bodyShapePreparing",
                    ):
                        _normalize_bool(body_proportions, key)
                    measurements = body_proportions.get("measurements")
                    if isinstance(measurements, dict):
                        for measurement in measurements.values():
                            if isinstance(measurement, dict):
                                _normalize_bool(measurement, "available")
                                _normalize_bool(measurement, "bilateral")
                    morphs = body_proportions.get("morphs")
                    if isinstance(morphs, list):
                        for morph in morphs[:64]:
                            if isinstance(morph, dict):
                                _normalize_bool(morph, "builtIn")
    atoms = document.get("atoms")
    if isinstance(atoms, list):
        for atom in atoms:
            if isinstance(atom, dict):
                _normalize_bool(atom, "selected")
                cua = atom.get("cua")
                if isinstance(cua, dict):
                    for key in (
                        "loadDll",
                        "ready",
                        "isAssetLoaded",
                        "choicesTruncated",
                    ):
                        _normalize_bool(cua, key)
                sam3d_camera = atom.get("sam3dCamera")
                if isinstance(sam3d_camera, dict):
                    _normalize_bool(sam3d_camera, "compatible")
    sam3d = document.get("sam3d")
    if isinstance(sam3d, dict):
        _normalize_bool(sam3d, "applied")
        _normalize_bool(sam3d, "undoAvailable")
    return document


def read_timeline_status(vam_root: Path) -> dict[str, object] | None:
    """Read the bridge's independently refreshed, bounded Timeline roster."""

    document = _read_bridge_document(bridge_directory(vam_root) / "timeline.json")
    if document is None:
        return None
    _normalize_nonnegative_int(document, "timelineProtocol")
    if document.get("timelineProtocol") != TIMELINE_PROTOCOL_VERSION:
        return None
    _normalize_bool(document, "loading")
    _normalize_bool(document, "truncated")
    root_counts = document.get("counts")
    if isinstance(root_counts, dict):
        for key in (
            "instances",
            "publishedInstances",
            "clips",
            "publishedClips",
        ):
            _normalize_nonnegative_int(root_counts, key)
    root_limits = document.get("limits")
    if isinstance(root_limits, dict):
        for key in (
            "maxInstances",
            "maxClips",
            "maxClipsGlobally",
        ):
            _normalize_nonnegative_int(root_limits, key)
    instances = document.get("instances")
    if isinstance(instances, list):
        for instance in instances[:32]:
            if not isinstance(instance, dict):
                continue
            for key in (
                "enhanced",
                "ready",
                "selected",
                "playing",
                "paused",
                "locked",
                "clipsTruncated",
                "segmentsTruncated",
                "layersTruncated",
            ):
                _normalize_bool(instance, key)
            for key in (
                "clipCount",
                "segmentCount",
                "layerCount",
                "stateSequence",
            ):
                _normalize_nonnegative_int(instance, key)
            transport = instance.get("transport")
            if isinstance(transport, dict):
                for key in ("playing", "paused", "locked"):
                    _normalize_bool(transport, key)
            truncated = instance.get("truncated")
            if isinstance(truncated, dict):
                for key in ("segments", "layers", "clips"):
                    _normalize_bool(truncated, key)
            counts = instance.get("counts")
            if isinstance(counts, dict):
                for key in (
                    "segments",
                    "layers",
                    "clips",
                    "publishedSegments",
                    "publishedLayers",
                    "publishedClips",
                ):
                    _normalize_nonnegative_int(counts, key)
            limits = instance.get("limits")
            if isinstance(limits, dict):
                for key in (
                    "maxSegments",
                    "maxLayers",
                    "maxClips",
                    "maxClipsGlobally",
                    "allocatedClips",
                ):
                    _normalize_nonnegative_int(limits, key)
            for collection_name in ("clips", "segments", "layers"):
                collection = instance.get(collection_name)
                if not isinstance(collection, list):
                    continue
                for item in collection:
                    if isinstance(item, dict):
                        for key in (
                            "selected",
                            "loop",
                            "playing",
                            "main",
                        ):
                            _normalize_bool(item, key)
                        _normalize_nonnegative_int(item, "targetCount")
    return document


def read_bridge_request(vam_root: Path) -> dict[str, object] | None:
    return _read_bridge_document(bridge_directory(vam_root) / "request.json")


def read_bridge_status(vam_root: Path) -> dict[str, object] | None:
    document = _read_bridge_document(
        bridge_directory(vam_root) / "status.json",
        accepted_protocols=frozenset({1, PROTOCOL_VERSION}),
    )
    if document is None:
        return None

    # VaM 1.22's bundled SimpleJSON can serialize AsBool values as JSON
    # strings. Normalize them while still accepting native JSON scalars.
    _normalize_bool(document, "ok")
    return document


def install_bridge(vam_root: Path, *, force: bool = False) -> list[Path]:
    resolved_root = vam_root.resolve()
    destination = resolved_root / "Custom" / "Scripts" / "VAMPip" / "Bridge"
    source_root = resources.files("vampip").joinpath("bridge_assets")
    planned: list[tuple[Path, bytes]] = []
    for name in ("VAMPipBridge.cs", "VAMPipBridge.cslist"):
        planned.append((destination / name, source_root.joinpath(name).read_bytes()))

    preset_target = (
        resolved_root / "Custom" / "Atom" / "Empty" / "Preset_VAMPipSAM3DCamera.vap"
    )
    preset_payload = source_root.joinpath("Preset_VAMPipSAM3DCamera.vap").read_bytes()
    planned.append((preset_target, preset_payload))

    renderer_source = (
        resources.files("vampip").joinpath("renderer_assets").joinpath("VRRendererX")
    )
    renderer_target = resolved_root / "Custom" / "Scripts" / "VAMPip" / "VRRendererX"

    def plan_renderer_tree(source: object, renderer_destination: Path) -> None:
        for child in sorted(  # type: ignore[attr-defined]
            source.iterdir(),
            key=lambda entry: entry.name,
        ):
            target = renderer_destination / child.name
            if child.is_dir():
                plan_renderer_tree(child, target)
                continue
            planned.append((target, child.read_bytes()))

    plan_renderer_tree(renderer_source, renderer_target)

    # Validate the complete install set before creating directories or writing
    # files. A conflict in a late renderer asset must not leave the bridge or
    # camera preset partially installed.
    needs_write: list[bool] = []
    for target, payload in planned:
        if not target.exists():
            needs_write.append(True)
            continue
        if not target.is_file():
            raise FileExistsError(
                f"bridge target is not a file and will not be overwritten: {target}"
            )
        current = target.read_bytes()
        differs = current != payload
        if differs and not force:
            raise FileExistsError(
                f"bridge file differs and will not be overwritten: {target}"
            )
        needs_write.append(differs)

    installed: list[Path] = []
    for (target, payload), write_required in zip(planned, needs_write, strict=True):
        if write_required:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, target)
        installed.append(target)
    return installed

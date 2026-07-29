from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

from vampip.bridge import read_bridge_request, request_select_atom
from vampip.database import connect
from vampip.inventory import scan
from vampip.manager_state import list_leases
from vampip.service import LiveActionBusyError, ManagerService, _equipment_slot


HAIR_MEMBER = "Custom/Atom/Person/Hair/Example/Preset_Soft Bob.vap"
SCENE_MEMBER = "Saves/scene/Example Scene.json"
EMPTY_PRESET_MEMBER = "Custom/Atom/Empty/Example/Preset_Empty.vap"
SUBSCENE_MEMBER = "Custom/SubScene/Example/Room.json"
CUA_BUNDLE_MEMBER = "Custom/Assets/Example/Props.assetbundle"
CUA_SCENE_MEMBER = "Custom/Assets/Example/Environment.scene"
CUA_WRONG_SUFFIX_MEMBER = "Custom/Assets/Example/NotABundle.json"
CLOTHING_MEMBER = "Custom/Clothing/Female/Example/Everyday/Everyday Shirt.vam"
UNSUPPORTED_ATOM_PRESET_MEMBER = "Custom/Atom/PackageDefinedWidget/Preset_Unsafe.vap"
PERSON_PRESET_MEMBERS = {
    "Preset Appearance": (
        "appearance",
        "Custom/Atom/Person/Appearance/Example/Preset_Appearance.vap",
    ),
    "Preset Animation": (
        "animation",
        "Custom/Atom/Person/AnimationPresets/Example/Preset_Animation.vap",
    ),
    "Preset Breast Physics": (
        "breastPhysics",
        "Custom/Atom/Person/BreastPhysics/Example/Preset_Breast.vap",
    ),
    "Preset Clothing": (
        "clothing",
        "Custom/Atom/Person/Clothing/Example/Preset_Clothing.vap",
    ),
    "Preset General": (
        "general",
        "Custom/Atom/Person/General/Example/Preset_General.vap",
    ),
    "Preset Glute Physics": (
        "glutePhysics",
        "Custom/Atom/Person/GlutePhysics/Example/Preset_Glute.vap",
    ),
    "Preset Hair": ("hair", HAIR_MEMBER),
    "Preset Morphs": (
        "morphs",
        "Custom/Atom/Person/Morphs/Example/Preset_Morphs.vap",
    ),
    "Preset Plugins": (
        "plugins",
        "Custom/Atom/Person/Plugins/Example/Preset_Plugins.vap",
    ),
    "Preset Pose": (
        "pose",
        "Custom/Atom/Person/Pose/Example/Preset_Pose.vap",
    ),
    "Preset Skin": (
        "skin",
        "Custom/Atom/Person/Skin/Example/Preset_Skin.vap",
    ),
}


def make_hair_var(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "meta.json",
            json.dumps(
                {
                    "creatorName": "Creator",
                    "packageName": "HairPack",
                    "dependencies": {},
                }
            ),
        )
        for _, member in PERSON_PRESET_MEMBERS.values():
            archive.writestr(member, json.dumps({"storables": []}))
        archive.writestr(SCENE_MEMBER, json.dumps({"atoms": []}))
        archive.writestr(EMPTY_PRESET_MEMBER, json.dumps({"storables": []}))
        archive.writestr(SUBSCENE_MEMBER, json.dumps({"storables": []}))
        archive.writestr(CUA_BUNDLE_MEMBER, b"asset bundle")
        archive.writestr(CUA_SCENE_MEMBER, b"asset bundle")
        archive.writestr(CUA_WRONG_SUFFIX_MEMBER, b"not an asset bundle")
        archive.writestr(
            CLOTHING_MEMBER,
            json.dumps(
                {
                    "itemType": "ClothingFemale",
                    "uid": "Example:Everyday Shirt",
                }
            ),
        )
        archive.writestr(
            UNSUPPORTED_ATOM_PRESET_MEMBER,
            json.dumps({"storables": []}),
        )


class PersonWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vam_root = Path(self.temporary.name) / "VaM"
        self.addons = self.vam_root / "AddonPackages"
        self.state = Path(self.temporary.name) / "state"
        self.archive = self.addons / "Creator.HairPack.1.var"
        make_hair_var(self.archive)
        self.pids: list[int] = []
        self.service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: list(self.pids),
        )
        with connect(self.state) as connection:
            scan(self.addons, connection)
        self.resource_id = self.insert_resource(
            "Preset Hair",
            HAIR_MEMBER,
            key="hair-resource",
        )

    def insert_resource(
        self,
        resource_type: str,
        resource_path: str,
        *,
        atom_type: str = "Person",
        key: str | None = None,
    ) -> int:
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', ?, 'Creator',
                          'HairPack', '["1"]', ?, ?, ?,
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (
                    str(self.vam_root),
                    key or f"{resource_type}:{resource_path}",
                    resource_path.replace("/", "\\"),
                    resource_type,
                    atom_type,
                ),
            )
            resource_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO catalog_resource_versions(resource_id, version_text)
                VALUES (?, '1')
                """,
                (resource_id,),
            )
        return resource_id

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def roster() -> dict[str, object]:
        return {
            "available": True,
            "vam_running": True,
            "loading": False,
            "selected_uid": "Person",
            "atoms": [
                {"uid": "Person", "type": "Person", "selected": True},
                {"uid": "Person 2", "type": "Person", "selected": False},
                {"uid": "Light", "type": "InvisibleLight", "selected": False},
                {"uid": "Empty Target", "type": "Empty", "selected": False},
                {
                    "uid": "SubScene Target",
                    "type": "SubScene",
                    "selected": False,
                },
                {
                    "uid": "CUA Target",
                    "type": "CustomUnityAsset",
                    "selected": False,
                    "cua": {
                        "loadDll": False,
                        "ready": True,
                        "choiceToken": "a" * 32,
                        "choiceCount": 2,
                        "selectedIndex": 0,
                        "choicesTruncated": False,
                        "choices": [
                            {"index": 1, "label": "Chair"},
                            {"index": 3, "label": "Table"},
                        ],
                    },
                },
                {"uid": "Wrong Target", "type": "Button", "selected": False},
            ],
            "persons": [
                {"uid": "Person", "selected": True},
                {"uid": "Person 2", "selected": False},
            ],
            "capabilities": [
                "atom-roster",
                "atom-add",
                "atom-preset-apply",
                "atom-select",
                "custom-unity-asset-choice",
                "custom-unity-asset-load",
                "scene-load",
                "subscene-load",
                "person-roster",
                "person-preset-appearance",
                "person-preset-animation",
                "person-preset-breast-physics",
                "person-preset-clothing",
                "person-preset-general",
                "person-preset-glute-physics",
                "person-preset-hair",
                "person-preset-morphs",
                "person-preset-plugins",
                "person-preset-pose",
                "person-preset-skin",
                "person-add",
                "person-select",
            ],
        }

    @staticmethod
    def clothing_roster(
        *,
        gender: str = "Female",
        active_refs: list[str] | None = None,
        locked_refs: list[str] | None = None,
        active_count: int | str | None = None,
        locked_count: int | str | None = None,
        active_items: list[dict[str, object]] | None = None,
        revision: str = "a" * 32,
        truncated: bool = False,
    ) -> dict[str, object]:
        roster = PersonWorkspaceTests.roster()
        roster["capabilities"].append("person-clothing-item-toggle")
        for person in roster["persons"]:
            person["clothing"] = {
                "ready": True,
                "gender": gender,
                "activeResourceRefs": list(active_refs or []),
                "lockedResourceRefs": list(locked_refs or []),
                "activeCount": (
                    len(active_refs or []) if active_count is None else active_count
                ),
                "lockedCount": (
                    len(locked_refs or []) if locked_count is None else locked_count
                ),
                "truncated": truncated,
                "revision": revision,
            }
            if active_items is not None:
                person["clothing"]["activeItems"] = list(active_items)
        return roster

    @staticmethod
    def hair_roster(
        *,
        active_count: int | str = 1,
        locked_count: int | str = 0,
        revision: str = "b" * 32,
        truncated: bool = False,
        items: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        roster = PersonWorkspaceTests.roster()
        roster["capabilities"].append("person-hair-roster")
        hair_items = (
            [
                {
                    "displayName": "Soft Bob",
                    "tags": ["Sim", "Short"],
                    "locked": False,
                    "simulated": True,
                }
            ]
            if items is None
            else items
        )
        for person in roster["persons"]:
            person["hair"] = {
                "ready": True,
                "activeCount": active_count,
                "lockedCount": locked_count,
                "truncated": truncated,
                "revision": revision,
                "items": list(hair_items),
            }
        return roster

    def test_individual_clothing_search_joins_private_live_state(self) -> None:
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="female-clothing",
        )
        resource_ref = f"Creator.HairPack.1:/{CLOTHING_MEMBER}"
        roster = self.clothing_roster(
            active_refs=[resource_ref],
            locked_refs=[resource_ref],
        )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=roster,
        ) as scene:
            result = self.service.search_resources(
                category="clothing-items-female",
                target_uid="Person",
            )

        scene.assert_called_once_with(include_clothing_refs=True)
        self.assertEqual(result["category"], "clothing-items-female")
        item = next(value for value in result["items"] if value["id"] == resource_id)
        self.assertTrue(item["worn"])
        self.assertTrue(item["clothing_locked"])
        self.assertTrue(item["clothing_compatible"])
        self.assertEqual(item["clothing_revision"], "a" * 32)
        self.assertNotIn("resolved_resource_ref", item)

    def test_public_scene_never_exposes_exact_clothing_join_keys(self) -> None:
        self.pids.append(1234)
        raw_person = self.clothing_roster(
            active_refs=[f"Creator.HairPack.1:/{CLOTHING_MEMBER}"],
            locked_refs=[f"Creator.HairPack.1:/{CLOTHING_MEMBER}"],
            active_items=[
                {
                    "resourceRef": (
                        f"Creator.HairPack.1:/{CLOTHING_MEMBER}"
                    ),
                    "uid": "private-clothing-uid",
                    "displayName": "Everyday Shirt",
                    "tags": ["Tops", "/home/private/clothing"],
                    "locked": True,
                }
            ],
        )["persons"][0]
        raw_person["hair"] = {
            "ready": True,
            "activeCount": 1,
            "lockedCount": 0,
            "truncated": False,
            "revision": "b" * 32,
            "items": [
                {
                    "displayName": "Soft Bob",
                    "tags": [
                        "Sim",
                        "Private.Hair.1:/Custom/Hair/Secret.vam",
                    ],
                    "locked": False,
                    "simulated": True,
                    "resourceRef": "Private.Hair.1:/Custom/Hair/Secret.vam",
                }
            ],
        }
        raw_person["resourceRef"] = "Private.Person.1:/Custom/Secret.json"
        raw_person["internalUid"] = "private-person-internal-uid"
        scene = {
            "instanceId": "bridge-instance",
            "updatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "loading": False,
            "selectedUid": "Person",
            "atoms": [
                {
                    "uid": "Asset",
                    "type": "CustomUnityAsset",
                    "selected": False,
                    "resourceRef": "Private.Asset.1:/Custom/Secret.assetbundle",
                    "cua": {
                        "loadDll": False,
                        "ready": True,
                        "isAssetLoaded": True,
                        "choiceToken": "c" * 32,
                        "choiceCount": 1,
                        "selectedIndex": 7,
                        "choices": [{"index": 7, "label": "room.prefab"}],
                        "choicesTruncated": False,
                        "internalUid": "private-cua-internal-uid",
                    },
                }
            ],
            "persons": [raw_person],
            "capabilities": [
                "person-clothing-item-toggle",
                "Private.1:/Custom/Capability",
            ],
        }
        with (
            mock.patch(
                "vampip.service.read_bridge_status",
                return_value={
                    "instanceId": "bridge-instance",
                    "state": "ok",
                    "resourceRef": "Private.Bridge.1:/Custom/Secret.json",
                },
            ),
            mock.patch("vampip.service.read_bridge_request", return_value=None),
            mock.patch("vampip.service.read_scene_status", return_value=scene),
        ):
            public = self.service.scene()

        clothing = public["persons"][0]["clothing"]
        self.assertNotIn("activeResourceRefs", clothing)
        self.assertNotIn("lockedResourceRefs", clothing)
        self.assertEqual(
            clothing["activeItems"],
            [
                {
                    "displayName": "Everyday Shirt",
                    "tags": ["Tops"],
                    "locked": True,
                }
            ],
        )
        self.assertEqual(clothing["revision"], "a" * 32)
        self.assertEqual(
            public["persons"][0]["hair"]["items"],
            [
                {
                    "displayName": "Soft Bob",
                    "tags": ["Sim"],
                    "locked": False,
                    "simulated": True,
                }
            ],
        )
        self.assertEqual(
            set(public["persons"][0]),
            {"uid", "selected", "clothing", "hair"},
        )
        self.assertEqual(
            set(public["atoms"][0]),
            {"uid", "type", "selected", "cua"},
        )
        self.assertNotIn("internalUid", public["atoms"][0]["cua"])
        self.assertEqual(
            public["capabilities"],
            ["person-clothing-item-toggle"],
        )
        self.assertNotIn("resourceRef", public["bridge"])
        self.assertNotIn("private-clothing-uid", json.dumps(public))
        self.assertNotIn("Private.Hair", json.dumps(public))
        self.assertNotIn("Private.Person", json.dumps(public))
        self.assertNotIn("Private.Asset", json.dumps(public))
        self.assertNotIn("Private.Bridge", json.dumps(public))
        self.assertNotIn("private-cua-internal-uid", json.dumps(public))

    def test_person_equipment_is_allowlisted_and_accounts_for_unknown_items(
        self,
    ) -> None:
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="equipment-female-clothing",
        )
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE catalog_resources
                SET tags_json = ?, clothing_versions_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(
                        [
                            {
                                "tagName": "Casual",
                                "tagCategory": "Style",
                            }
                        ]
                    ),
                    json.dumps(
                        [
                            {
                                "version": "1",
                                "item_type": "ClothingFemale",
                                "uid": "private-clothing-uid",
                                "display_name": "Silk Shirt",
                                "creator": "Private clothing creator",
                                "tags": ["Tops"],
                                "is_real_item": True,
                            }
                        ]
                    ),
                    resource_id,
                ),
            )
        identified_ref = f"Creator.HairPack.1:/{CLOTHING_MEMBER}"
        unidentified_ref = "Other.Unknown.7:/Custom/Clothing/Female/Other/Unknown.vam"
        roster = self.clothing_roster(
            active_refs=[identified_ref, unidentified_ref],
            locked_refs=[identified_ref],
            active_count="2",
            locked_count="2",
            active_items=[
                {
                    "resourceRef": identified_ref,
                    "displayName": "Bridge shirt name",
                    "tags": ["Bridge tag"],
                    "locked": True,
                },
                {
                    "resourceRef": unidentified_ref,
                    "displayName": "Satin Panties",
                    "tags": ["Panties", "Lingerie"],
                    "locked": True,
                    "uid": "must-not-escape",
                },
            ],
        )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=roster,
        ) as snapshot:
            result = self.service.person_equipment("Person")

        snapshot.assert_called_once_with(include_clothing_refs=True)
        self.assertEqual(
            set(result),
            {
                "available",
                "target_uid",
                "revision",
                "ready",
                "gender",
                "active_count",
                "locked_count",
                "identified_count",
                "unidentified_count",
                "truncated",
                "complete",
                "items",
            },
        )
        self.assertTrue(result["available"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["target_uid"], "Person")
        self.assertEqual(result["revision"], "a" * 32)
        self.assertEqual(result["gender"], "Female")
        self.assertEqual(result["active_count"], 2)
        self.assertEqual(result["locked_count"], 2)
        self.assertEqual(result["identified_count"], 1)
        self.assertEqual(result["unidentified_count"], 1)
        self.assertFalse(result["truncated"])
        self.assertTrue(result["complete"])
        items = result["items"]
        assert isinstance(items, list)
        self.assertEqual(len(items), 2)
        item = items[0]
        self.assertEqual(
            set(item),
            {
                "id",
                "key",
                "actionable",
                "display_name",
                "creator",
                "package",
                "resource_type",
                "tags",
                "slot",
                "locked",
                "package_version",
                "local",
                "state",
            },
        )
        self.assertEqual(item["id"], resource_id)
        self.assertEqual(item["key"], f"resource-{resource_id}")
        self.assertTrue(item["actionable"])
        self.assertEqual(item["display_name"], "Silk Shirt")
        self.assertEqual(item["creator"], "Creator")
        self.assertEqual(item["package"], "HairPack")
        self.assertEqual(item["resource_type"], "Clothing (Female)")
        self.assertEqual(item["tags"], ["Casual", "Tops"])
        self.assertEqual(item["slot"], "tops")
        self.assertTrue(item["locked"])
        self.assertEqual(item["package_version"], 1)
        self.assertFalse(item["local"])
        self.assertEqual(item["state"], "active")
        placeholder = items[1]
        self.assertIsNone(placeholder["id"])
        self.assertRegex(placeholder["key"], r"^equipment-[0-9a-f]{24}$")
        self.assertFalse(placeholder["actionable"])
        self.assertEqual(placeholder["display_name"], "Satin Panties")
        self.assertEqual(placeholder["tags"], ["Panties", "Lingerie"])
        self.assertEqual(placeholder["slot"], "panties-underwear")
        self.assertTrue(placeholder["locked"])
        self.assertEqual(placeholder["state"], "in-game")
        self.assertEqual(placeholder["creator"], "")
        self.assertEqual(placeholder["package"], "")
        serialized = json.dumps(result)
        for private_value in (
            "activeResourceRefs",
            "lockedResourceRefs",
            "resolved_resource_ref",
            "private-clothing-uid",
            "Private clothing creator",
            CLOTHING_MEMBER,
            identified_ref,
            unidentified_ref,
            "must-not-escape",
        ):
            self.assertNotIn(private_value, serialized)

    def test_person_equipment_complete_empty_set_uses_unsorted_fallback(self) -> None:
        local_member = "Custom/Clothing/Female/Example/Mystery/Mystery.vam"
        local_path = self.vam_root / local_member
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("{}", encoding="utf-8")
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', ?, '', '', '[]', ?,
                          'Untrusted BrowserAssist name', 'Person',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (
                    str(self.vam_root),
                    "local-equipment",
                    local_member,
                ),
            )
            resource_id = int(cursor.lastrowid)
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(active_refs=[local_member]),
        ):
            result = self.service.person_equipment("Person")

        self.assertTrue(result["complete"])
        self.assertEqual(result["identified_count"], 1)
        self.assertEqual(result["unidentified_count"], 0)
        item = result["items"][0]
        self.assertEqual(item["id"], resource_id)
        self.assertEqual(item["resource_type"], "Clothing (Female)")
        self.assertEqual(item["slot"], "unsorted")
        self.assertIsNone(item["package_version"])
        self.assertTrue(item["local"])
        self.assertEqual(item["state"], "local")

    def test_equipment_slot_taxonomy_uses_exact_tokens_and_specific_heels(self) -> None:
        cases = {
            "Sports Bra": "bras",
            "Lace Panties": "panties-underwear",
            "Winter Shirt": "tops",
            "Evening Dress": "full-body",
            "Denim Shorts": "bottoms",
            "Sheer Stockings": "stockings-socks",
            "Platform Boots": "shoes-boots",
            "Midnight High Heel Pumps": "high-heels",
            "Silk Gloves": "arms-hands",
            "Pearl Choker": "neck",
            "Rose Tattoo FX": "body-fx",
            "Sun Hat": "head",
            "Shoemaker Apron": "unsorted",
        }
        for display_name, expected in cases.items():
            with self.subTest(display_name=display_name):
                self.assertEqual(_equipment_slot(display_name, []), expected)

    def test_person_hair_is_bounded_read_only_and_allowlisted(self) -> None:
        roster = self.hair_roster(
            active_count="2",
            locked_count="1",
            items=[
                {
                    "displayName": "Soft Bob",
                    "tags": ["Sim", "Short", "Sim"],
                    "locked": True,
                    "simulated": True,
                    "uid": "private-hair-uid",
                    "resourceRef": (
                        "Private.Hair.1:/Custom/Hair/Secret.vam"
                    ),
                },
                {
                    "displayName": "Mesh Bangs",
                    "tags": ["Bangs"],
                    "locked": False,
                    "simulated": False,
                    "packageUid": "private-package",
                },
            ],
        )
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=roster,
        ) as snapshot:
            first = self.service.person_hair("Person")
            second = self.service.person_hair("Person")

        self.assertEqual(snapshot.call_count, 2)
        snapshot.assert_called_with(include_clothing_refs=True)
        self.assertTrue(first["available"])
        self.assertTrue(first["ready"])
        self.assertEqual(first["active_count"], 2)
        self.assertEqual(first["locked_count"], 1)
        self.assertTrue(first["complete"])
        self.assertEqual(first["items"], second["items"])
        items = first["items"]
        assert isinstance(items, list)
        self.assertEqual(len(items), 2)
        self.assertEqual(
            set(items[0]),
            {
                "key",
                "actionable",
                "display_name",
                "tags",
                "locked",
                "simulated",
                "state",
            },
        )
        self.assertRegex(items[0]["key"], r"^hair-[0-9a-f]{24}$")
        self.assertFalse(items[0]["actionable"])
        self.assertEqual(items[0]["tags"], ["Sim", "Short"])
        self.assertTrue(items[0]["locked"])
        self.assertTrue(items[0]["simulated"])
        serialized = json.dumps(first)
        for private_value in (
            "private-hair-uid",
            "Private.Hair",
            "Secret.vam",
            "private-package",
            "resourceRef",
        ):
            self.assertNotIn(private_value, serialized)

    def test_live_presentation_values_redact_paths_and_resource_refs(self) -> None:
        private_ref = "Private.Asset.1:/Custom/Clothing/Female/Secret.vam"
        clothing = self.clothing_roster(
            active_count=1,
            active_items=[
                {
                    "resourceRef": "",
                    "displayName": private_ref,
                    "tags": ["/home/private/file", "Safe tag"],
                    "locked": False,
                }
            ],
        )
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=clothing,
        ):
            equipment = self.service.person_equipment("Person")
        self.assertEqual(
            equipment["items"][0]["display_name"],
            "Unnamed clothing item",
        )
        self.assertEqual(equipment["items"][0]["tags"], ["Safe tag"])

        hair = self.hair_roster(
            items=[
                {
                    "displayName": r"C:\private\Hair.vam",
                    "tags": [private_ref, "Bangs"],
                    "locked": False,
                    "simulated": False,
                }
            ],
        )
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=hair,
        ):
            hair_result = self.service.person_hair("Person")
        self.assertEqual(
            hair_result["items"][0]["display_name"],
            "Unnamed hair item",
        )
        self.assertEqual(hair_result["items"][0]["tags"], ["Bangs"])
        serialized = json.dumps(
            {"equipment": equipment, "hair": hair_result}
        )
        self.assertNotIn("Private.Asset", serialized)
        self.assertNotIn(r"C:\\private", serialized)
        self.assertNotIn("/home/private", serialized)

    def test_person_equipment_validates_live_target_and_revision(self) -> None:
        unavailable = self.roster()
        unavailable["available"] = False
        unavailable["persons"] = []
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=unavailable,
        ):
            result = self.service.person_equipment("Person")
        self.assertFalse(result["available"])
        self.assertEqual(result["items"], [])

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(),
        ):
            with self.assertRaisesRegex(ValueError, "no longer available"):
                self.service.person_equipment("Missing Person")

        invalid_revision = self.clothing_roster(revision="not-a-revision")
        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=invalid_revision,
        ):
            with self.assertRaisesRegex(ValueError, "invalid live clothing revision"):
                self.service.person_equipment("Person")

    def test_clothing_wear_and_remove_are_desired_state_actions(self) -> None:
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="toggle-female-clothing",
        )
        resource_ref = f"Creator.HairPack.1:/{CLOTHING_MEMBER}"
        lease_result = {
            "applied": True,
            "reconcile": {"enable": 1},
        }
        with (
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value=self.clothing_roster(),
            ),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value=lease_result,
            ) as lease,
            mock.patch(
                "vampip.service.request_person_clothing",
                return_value="wear-request",
            ) as request,
        ):
            worn = self.service.set_person_clothing(
                resource_id,
                target_uid="Person",
                active=True,
                revision="a" * 32,
                days=4,
            )

        self.assertEqual(worn["bridge_request"], "wear-request")
        self.assertTrue(worn["rescan"])
        lease.assert_called_once_with(
            resource_id,
            days=4.0,
            label="Clothing: Everyday Shirt",
            apply=True,
            bridge_rescan=False,
        )
        request.assert_called_once_with(
            self.vam_root,
            target_uid="Person",
            resource_ref=resource_ref,
            active=True,
            revision="a" * 32,
            rescan=True,
        )

        with (
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value=self.clothing_roster(
                    gender="Male",
                    active_refs=[resource_ref],
                ),
            ),
            mock.patch.object(self.service, "lease_resource") as remove_lease,
            mock.patch(
                "vampip.service.request_person_clothing",
                return_value="remove-request",
            ) as remove_request,
        ):
            removed = self.service.set_person_clothing(
                resource_id,
                target_uid="Person",
                active=False,
                revision="a" * 32,
            )

        self.assertEqual(removed["bridge_request"], "remove-request")
        self.assertFalse(removed["rescan"])
        self.assertIsNone(removed["lease"])
        remove_lease.assert_not_called()
        remove_request.assert_called_once_with(
            self.vam_root,
            target_uid="Person",
            resource_ref=resource_ref,
            active=False,
            revision="a" * 32,
            rescan=False,
        )

    def test_exact_clothing_version_can_remove_older_worn_copy(self) -> None:
        make_hair_var(self.addons / "Creator.HairPack.2.var")
        make_hair_var(self.addons / "Creator.HairPack.4.var")
        with connect(self.state) as connection:
            scan(self.addons, connection)
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="versioned-remove-clothing",
        )
        search = self.service.search_resources(
            category="clothing-items-female",
        )
        selected = next(item for item in search["items"] if item["id"] == resource_id)
        self.assertEqual(selected["selected_version"], "4")

        version_two_ref = f"Creator.HairPack.2:/{CLOTHING_MEMBER}"
        with (
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value=self.clothing_roster(
                    active_refs=[version_two_ref],
                ),
            ),
            mock.patch(
                "vampip.service.request_person_clothing",
                return_value="remove-v2-request",
            ) as request,
        ):
            removed = self.service.set_person_clothing(
                resource_id,
                package_version=2,
                target_uid="Person",
                active=False,
                revision="a" * 32,
            )

        self.assertEqual(removed["selected_version"], "2")
        self.assertEqual(removed["bridge_request"], "remove-v2-request")
        request.assert_called_once_with(
            self.vam_root,
            target_uid="Person",
            resource_ref=version_two_ref,
            active=False,
            revision="a" * 32,
            rescan=False,
        )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(
                active_refs=[version_two_ref],
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "exact clothing package version is not currently worn",
            ):
                self.service.set_person_clothing(
                    resource_id,
                    package_version=4,
                    target_uid="Person",
                    active=False,
                    revision="a" * 32,
                )

    def test_clothing_enable_reserves_cross_process_mailbox_until_publish(
        self,
    ) -> None:
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="cross-process-clothing",
        )
        self.service.reconcile(apply=True, activate=True)
        self.assertFalse(self.archive.exists())
        self.pids.append(1234)
        second_service = ManagerService(
            self.addons,
            self.state.parent / "second-state",
            vam_root=self.vam_root,
            process_probe=lambda: list(self.pids),
        )
        original_lease_resource = self.service.lease_resource
        package_enabled = threading.Event()
        release_wear = threading.Event()
        external_writer_called = threading.Event()
        results: dict[str, object] = {}
        errors: dict[str, BaseException] = {}

        def blocking_lease_resource(*args: object, **kwargs: object) -> object:
            result = original_lease_resource(*args, **kwargs)
            package_enabled.set()
            if not release_wear.wait(2):
                raise TimeoutError("test did not release clothing publication")
            return result

        def external_writer() -> str:
            external_writer_called.set()
            return request_select_atom(self.vam_root, "Light")

        def wear() -> None:
            try:
                results["wear"] = self.service.set_person_clothing(
                    resource_id,
                    target_uid="Person",
                    active=True,
                    revision="a" * 32,
                )
            except BaseException as error:
                errors["wear"] = error

        def publish_external() -> None:
            try:
                results["external"] = second_service._queue_bridge_request(
                    external_writer
                )
            except BaseException as error:
                errors["external"] = error

        with (
            mock.patch.object(
                self.service,
                "_scene_snapshot",
                return_value=self.clothing_roster(),
            ),
            mock.patch.object(
                self.service,
                "lease_resource",
                side_effect=blocking_lease_resource,
            ),
        ):
            wear_thread = threading.Thread(target=wear)
            wear_thread.start()
            self.assertTrue(package_enabled.wait(2))
            external_thread = threading.Thread(target=publish_external)
            external_thread.start()
            wrote_before_wear_published = external_writer_called.wait(0.1)
            release_wear.set()
            wear_thread.join(2)
            external_thread.join(2)

        self.assertFalse(wear_thread.is_alive())
        self.assertFalse(external_thread.is_alive())
        self.assertFalse(wrote_before_wear_published)
        self.assertFalse(external_writer_called.is_set())
        self.assertNotIn("wear", errors)
        self.assertIsInstance(errors.get("external"), LiveActionBusyError)
        wear_result = results["wear"]
        assert isinstance(wear_result, dict)
        self.assertTrue(wear_result["rescan"])
        self.assertFalse(wear_result["bridge_busy"])
        request = read_bridge_request(self.vam_root)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request["requestId"], wear_result["bridge_request"])
        self.assertEqual(request["command"], "setPersonClothingResource")
        self.assertIs(request["rescan"], True)

    def test_catalog_reference_normalizes_leading_dot_archive_member(self) -> None:
        location = mock.Mock(
            resource_path=CLOTHING_MEMBER,
            archive_member=f"./{CLOTHING_MEMBER}",
            package_ref="Creator.HairPack.1",
        )

        reference = self.service._catalog_resource_reference(
            location,
            required_prefix="Custom/Clothing/Female/",
            extension=".vam",
            require_preset_basename=False,
        )

        self.assertEqual(
            reference,
            f"Creator.HairPack.1:/{CLOTHING_MEMBER}",
        )

    def test_clothing_changes_fail_closed_on_stale_gender_and_lock(self) -> None:
        resource_id = self.insert_resource(
            "Clothing (Female)",
            CLOTHING_MEMBER,
            key="guarded-female-clothing",
        )
        resource_ref = f"Creator.HairPack.1:/{CLOTHING_MEMBER}"

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "exact clothing package version is not currently worn",
            ):
                self.service.set_person_clothing(
                    resource_id,
                    package_version=1,
                    target_uid="Person",
                    active=False,
                    revision="a" * 32,
                )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(),
        ):
            with self.assertRaisesRegex(ValueError, "revision is stale"):
                self.service.set_person_clothing(
                    resource_id,
                    target_uid="Person",
                    active=True,
                    revision="b" * 32,
                )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(gender="Male"),
        ):
            with self.assertRaisesRegex(ValueError, "incompatible"):
                self.service.set_person_clothing(
                    resource_id,
                    target_uid="Person",
                    active=True,
                    revision="a" * 32,
                )

        with mock.patch.object(
            self.service,
            "_scene_snapshot",
            return_value=self.clothing_roster(
                active_refs=[resource_ref],
                locked_refs=[resource_ref],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "locked in VaM"):
                self.service.set_person_clothing(
                    resource_id,
                    target_uid="Person",
                    active=False,
                    revision="a" * 32,
                )

    def test_hidden_hair_is_leased_enabled_and_queued_as_one_composite_action(
        self,
    ) -> None:
        self.service.reconcile(apply=True, activate=True)
        self.assertFalse(self.archive.exists())
        self.assertTrue(Path(f"{self.archive}.vampip-disabled").exists())
        self.pids.append(1234)

        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_person_preset",
                return_value="person-request",
            ) as request,
            mock.patch(
                "vampip.service.request_rescan",
                side_effect=AssertionError("standalone rescan must be suppressed"),
            ),
        ):
            result = self.service.apply_person_resource(
                self.resource_id,
                target_uid="Person",
                days=3,
            )

        self.assertTrue(self.archive.exists())
        self.assertEqual(result["bridge_request"], "person-request")
        self.assertEqual(
            result["resource_ref"],
            f"Creator.HairPack.1:/{HAIR_MEMBER}",
        )
        self.assertTrue(result["lease"]["applied"])
        self.assertIsNone(result["lease"]["reconcile"]["bridge_request"])
        request.assert_called_once_with(
            self.vam_root,
            target_uid="Person",
            preset_kind="hair",
            resource_ref=f"Creator.HairPack.1:/{HAIR_MEMBER}",
            rescan=True,
            merge=False,
        )
        with connect(self.state) as connection:
            leases = list_leases(connection)
        self.assertEqual(len(leases), 1)
        self.assertEqual(leases[0]["roots"], ["Creator.HairPack.1"])

    def test_unknown_person_or_mismatched_catalog_path_is_rejected_before_lease(
        self,
    ) -> None:
        self.pids.append(1234)
        with mock.patch.object(self.service, "persons", return_value=self.roster()):
            with self.assertRaisesRegex(ValueError, "no longer available"):
                self.service.apply_person_resource(
                    self.resource_id,
                    target_uid="Deleted Person",
                )

            with connect(self.state) as connection:
                connection.execute(
                    """
                    UPDATE catalog_resources
                    SET resource_type = 'Preset Appearance'
                    WHERE id = ?
                    """,
                    (self.resource_id,),
                )
            with self.assertRaisesRegex(ValueError, "outside .*Appearance"):
                self.service.apply_person_resource(
                    self.resource_id,
                    target_uid="Person",
                    days=3,
                )

        with connect(self.state) as connection:
            self.assertEqual(list_leases(connection), [])

    def test_all_person_preset_kinds_are_catalog_mapped_and_support_merge(
        self,
    ) -> None:
        resource_ids = {"Preset Hair": self.resource_id}
        for resource_type, (_, member) in PERSON_PRESET_MEMBERS.items():
            if resource_type == "Preset Hair":
                continue
            resource_ids[resource_type] = self.insert_resource(
                resource_type,
                member,
                # Valid loose Person preset rows commonly omit presetAtomType.
                atom_type="" if resource_type == "Preset Appearance" else "Person",
            )

        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value={"applied": False},
            ),
            mock.patch(
                "vampip.service.request_person_preset",
                side_effect=lambda *args, **kwargs: f"request-{kwargs['preset_kind']}",
            ) as request,
        ):
            results = {
                resource_type: self.service.apply_person_resource(
                    resource_id,
                    target_uid="Person",
                    merge=True,
                    confirm_critical=resource_type
                    in {"Preset General", "Preset Plugins"},
                )
                for resource_type, resource_id in resource_ids.items()
            }

        self.assertEqual(request.call_count, len(PERSON_PRESET_MEMBERS))
        called_kinds = {
            call.kwargs["preset_kind"]: call.kwargs for call in request.call_args_list
        }
        for resource_type, (preset_kind, member) in PERSON_PRESET_MEMBERS.items():
            with self.subTest(resource_type=resource_type):
                self.assertIn(preset_kind, called_kinds)
                self.assertTrue(called_kinds[preset_kind]["merge"])
                self.assertEqual(
                    called_kinds[preset_kind]["resource_ref"],
                    f"Creator.HairPack.1:/{member}",
                )
                self.assertEqual(results[resource_type]["preset_kind"], preset_kind)

    def test_critical_person_presets_require_explicit_boolean_confirmation(
        self,
    ) -> None:
        general_id = self.insert_resource(
            "Preset General",
            PERSON_PRESET_MEMBERS["Preset General"][1],
        )
        plugins_id = self.insert_resource(
            "Preset Plugins",
            PERSON_PRESET_MEMBERS["Preset Plugins"][1],
        )
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value={
                    "applied": True,
                    "reconcile": {"enable": 0},
                },
            ) as lease,
            mock.patch(
                "vampip.service.request_person_preset",
                side_effect=("general-request", "plugins-request"),
            ) as request,
        ):
            for resource_id in (general_id, plugins_id):
                with self.subTest(resource_id=resource_id):
                    with self.assertRaisesRegex(ValueError, "confirm_critical"):
                        self.service.apply_resource(
                            resource_id,
                            target_uid="Person",
                        )
            with self.assertRaisesRegex(TypeError, "confirm_critical"):
                self.service.apply_resource(
                    general_id,
                    target_uid="Person",
                    confirm_critical=1,  # type: ignore[arg-type]
                )
            general = self.service.apply_resource(
                general_id,
                target_uid="Person",
                confirm_critical=True,
            )
            plugins = self.service.apply_person_resource(
                plugins_id,
                target_uid="Person",
                confirm_critical=True,
            )

        self.assertEqual(general["bridge_request"], "general-request")
        self.assertEqual(plugins["bridge_request"], "plugins-request")
        self.assertEqual(lease.call_count, 2)
        self.assertEqual(request.call_count, 2)
        self.assertTrue(
            all(not call.kwargs["rescan"] for call in request.call_args_list)
        )

    def test_each_person_preset_requires_its_kind_specific_capability(self) -> None:
        old_bridge_roster = self.roster()
        old_bridge_roster["capabilities"] = [
            "person-roster",
            "person-preset-apply",
        ]
        with (
            mock.patch.object(
                self.service,
                "persons",
                return_value=old_bridge_roster,
            ),
            mock.patch.object(self.service, "lease_resource") as lease,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "person-preset-hair",
            ):
                self.service.apply_person_resource(
                    self.resource_id,
                    target_uid="Person",
                )
        lease.assert_not_called()

    def test_active_packaged_preset_rescans_but_local_preset_does_not(
        self,
    ) -> None:
        self.service.pin(["Creator.HairPack.1"])
        self.service.reconcile(apply=True, activate=True)
        self.pids.append(1234)
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_person_preset",
                return_value="active-request",
            ) as request,
        ):
            active = self.service.apply_person_resource(
                self.resource_id,
                target_uid="Person",
            )
        self.assertEqual(active["lease"]["reconcile"]["enable"], 0)
        self.assertTrue(active["rescan"])
        self.assertTrue(request.call_args.kwargs["rescan"])

        # A loose preset has no package visibility state to refresh at all.
        local_member = "Custom/Atom/Person/Hair/Local/Preset_Local Hair.vap"
        local_path = self.vam_root / local_member
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"storables": []}', encoding="utf-8")
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', 'local-hair', '', '', '[]',
                          ?, 'Preset Hair', 'Person',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (str(self.vam_root), local_member.replace("/", "\\")),
            )
            local_id = int(cursor.lastrowid)
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_person_preset",
                return_value="local-request",
            ) as local_request,
        ):
            local = self.service.apply_person_resource(
                local_id,
                target_uid="Person",
            )
        self.assertTrue(local["lease"]["already_local"])
        self.assertFalse(local["rescan"])
        self.assertFalse(local_request.call_args.kwargs["rescan"])

    def test_workspace_registry_counts_blank_person_and_atom_preset_rows(
        self,
    ) -> None:
        appearance_id = self.insert_resource(
            "Preset Appearance",
            PERSON_PRESET_MEMBERS["Preset Appearance"][1],
            atom_type="",
        )
        self.insert_resource(
            "Preset Atom",
            "Custom/Atom/Empty/Preset_Example.vap",
            atom_type="Empty",
        )
        self.insert_resource(
            "Preset Atom",
            UNSUPPORTED_ATOM_PRESET_MEMBER,
            atom_type="PackageDefinedWidget",
        )
        self.insert_resource(
            "Custom Unity Assets",
            CUA_BUNDLE_MEMBER,
            atom_type="",
            key="cua-blank-atom-type",
        )
        self.insert_resource(
            "Custom Unity Assets",
            CUA_SCENE_MEMBER,
            atom_type="CustomUnityAsset",
            key="cua-explicit-atom-type",
        )

        document = self.service.workspace_categories()
        categories = {
            str(category["id"]): category for category in document["categories"]
        }
        self.assertEqual(categories["preset-hair"]["count"], 1)
        self.assertEqual(categories["preset-appearance"]["count"], 1)
        self.assertEqual(categories["preset-appearance"]["atom_types"], [])
        self.assertTrue(categories["preset-appearance"]["live_action"])
        self.assertTrue(categories["preset-appearance"]["merge_supported"])
        atom_category = next(
            category
            for category in document["categories"]
            if category.get("target_atom_type") == "Empty"
        )
        self.assertEqual(atom_category["resource_types"], ["Preset Atom"])
        self.assertEqual(atom_category["count"], 1)
        self.assertTrue(atom_category["live_action"])
        self.assertTrue(atom_category["create_supported"])
        self.assertEqual(atom_category["risk"], "critical")
        unsupported = next(
            category
            for category in document["categories"]
            if category.get("target_atom_type") == "PackageDefinedWidget"
        )
        self.assertFalse(unsupported["live_action"])
        self.assertFalse(unsupported["create_supported"])

        subscenes = categories["subscenes"]
        self.assertTrue(subscenes["live_action"])
        self.assertTrue(subscenes["create_supported"])
        self.assertEqual(subscenes["target_atom_type"], "SubScene")
        self.assertEqual(subscenes["risk"], "critical")

        custom_assets = categories["custom-unity-assets"]
        self.assertEqual(custom_assets["count"], 2)
        self.assertTrue(custom_assets["live_action"])
        self.assertFalse(custom_assets["merge_supported"])
        self.assertTrue(custom_assets["create_supported"])
        self.assertEqual(custom_assets["create_capability"], "atom-add")
        self.assertEqual(
            custom_assets["target_atom_type"],
            "CustomUnityAsset",
        )
        self.assertIn("DLL loading is forced off", custom_assets["risk_reason"])
        self.assertIn(
            "already-running code is not unloaded", custom_assets["risk_reason"]
        )

        search = self.service.search_resources(category="preset-appearance")
        self.assertEqual(search["category"], "preset-appearance")
        self.assertEqual(search["total"], 1)
        self.assertEqual(search["items"][0]["id"], appearance_id)

    def test_atom_preset_apply_is_catalog_derived_confirmed_and_target_safe(
        self,
    ) -> None:
        resource_id = self.insert_resource(
            "Preset Atom",
            EMPTY_PRESET_MEMBER,
            atom_type="Empty",
        )
        unsupported_id = self.insert_resource(
            "Preset Atom",
            UNSUPPORTED_ATOM_PRESET_MEMBER,
            atom_type="PackageDefinedWidget",
        )
        wrong_prefix_id = self.insert_resource(
            "Preset Atom",
            EMPTY_PRESET_MEMBER,
            atom_type="Button",
            key="button-with-empty-path",
        )
        lease_result = {
            "applied": True,
            "reconcile": {"enable": 1},
        }
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value=lease_result,
            ) as lease,
            mock.patch(
                "vampip.service.request_atom_preset",
                side_effect=("existing-request", "create-request"),
            ) as request,
        ):
            with self.assertRaisesRegex(TypeError, "create_if_missing"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="New Empty",
                    create_if_missing=1,  # type: ignore[arg-type]
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "confirm_critical"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Empty Target",
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "confirm_replace"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Empty Target",
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "no longer available"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Missing Empty",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "create_if_missing requires target_uid to be absent",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Wrong Target",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "expected Empty"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Wrong Target",
                    confirm_replace=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "create_if_missing requires target_uid to be absent",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Empty Target",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "merge is not supported when create_if_missing is true",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="New Empty",
                    merge=True,
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "merge is not supported when create_if_missing is true",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Empty Target",
                    merge=True,
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "native allowlist"):
                self.service.apply_resource(
                    unsupported_id,
                    target_uid="Missing Unsafe",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "outside Custom/Atom/Button"):
                self.service.apply_resource(
                    wrong_prefix_id,
                    target_uid="Wrong Target",
                    merge=True,
                    confirm_critical=True,
                )
            existing = self.service.apply_resource(
                resource_id,
                target_uid="Empty Target",
                confirm_replace=True,
                confirm_critical=True,
            )
            created = self.service.apply_resource(
                resource_id,
                target_uid="New Empty",
                create_if_missing=True,
                confirm_critical=True,
            )

        category_id = next(
            category["id"]
            for category in self.service.workspace_categories()["categories"]
            if category.get("target_atom_type") == "Empty"
        )
        self.assertEqual(existing["category"], category_id)
        self.assertTrue(existing["target_existed"])
        self.assertFalse(created["target_existed"])
        self.assertTrue(created["create_if_missing"])
        self.assertEqual(
            lease.call_args_list,
            [
                mock.call(
                    resource_id,
                    days=3.0,
                    label="Empty preset: Empty",
                    apply=True,
                    bridge_rescan=False,
                ),
                mock.call(
                    resource_id,
                    days=3.0,
                    label="Empty preset: Empty",
                    apply=True,
                    bridge_rescan=False,
                ),
            ],
        )
        self.assertEqual(
            request.call_args_list,
            [
                mock.call(
                    self.vam_root,
                    target_uid="Empty Target",
                    atom_type="Empty",
                    resource_ref=f"Creator.HairPack.1:/{EMPTY_PRESET_MEMBER}",
                    rescan=True,
                    merge=False,
                    create_if_missing=False,
                ),
                mock.call(
                    self.vam_root,
                    target_uid="New Empty",
                    atom_type="Empty",
                    resource_ref=f"Creator.HairPack.1:/{EMPTY_PRESET_MEMBER}",
                    rescan=True,
                    merge=False,
                    create_if_missing=True,
                ),
            ],
        )

    def test_subscene_apply_requires_critical_and_replacement_confirmation(
        self,
    ) -> None:
        resource_id = self.insert_resource(
            "SubScenes",
            SUBSCENE_MEMBER,
            atom_type="SubScene",
        )
        lease_result = {
            "applied": True,
            "reconcile": {"enable": 0},
        }
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value=lease_result,
            ) as lease,
            mock.patch(
                "vampip.service.request_subscene_load",
                side_effect=("existing-request", "create-request"),
            ) as request,
        ):
            with self.assertRaisesRegex(ValueError, "confirm_critical"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="SubScene Target",
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "confirm_replace"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="SubScene Target",
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "no longer available"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Missing SubScene",
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "create_if_missing requires target_uid to be absent",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Wrong Target",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "expected SubScene"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="Wrong Target",
                    confirm_replace=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "create_if_missing requires target_uid to be absent",
            ):
                self.service.apply_resource(
                    resource_id,
                    target_uid="SubScene Target",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "merge is not supported"):
                self.service.apply_resource(
                    resource_id,
                    target_uid="SubScene Target",
                    merge=True,
                    confirm_critical=True,
                )
            existing = self.service.apply_resource(
                resource_id,
                target_uid="SubScene Target",
                confirm_replace=True,
                confirm_critical=True,
            )
            created = self.service.apply_resource(
                resource_id,
                target_uid="New SubScene",
                create_if_missing=True,
                confirm_critical=True,
            )

        self.assertEqual(existing["category"], "subscenes")
        self.assertTrue(existing["target_existed"])
        self.assertFalse(created["target_existed"])
        self.assertFalse(existing["rescan"])
        self.assertEqual(
            lease.call_args_list,
            [
                mock.call(
                    resource_id,
                    days=3.0,
                    label="SubScene: Room",
                    apply=True,
                    bridge_rescan=False,
                ),
                mock.call(
                    resource_id,
                    days=3.0,
                    label="SubScene: Room",
                    apply=True,
                    bridge_rescan=False,
                ),
            ],
        )
        self.assertEqual(
            request.call_args_list,
            [
                mock.call(
                    self.vam_root,
                    target_uid="SubScene Target",
                    resource_ref=f"Creator.HairPack.1:/{SUBSCENE_MEMBER}",
                    rescan=False,
                    create_if_missing=False,
                ),
                mock.call(
                    self.vam_root,
                    target_uid="New SubScene",
                    resource_ref=f"Creator.HairPack.1:/{SUBSCENE_MEMBER}",
                    rescan=False,
                    create_if_missing=True,
                ),
            ],
        )

    def test_custom_unity_asset_apply_is_catalog_owned_and_safe(self) -> None:
        bundle_id = self.insert_resource(
            "Custom Unity Assets",
            CUA_BUNDLE_MEMBER,
            atom_type="",
            key="cua-bundle",
        )
        scene_id = self.insert_resource(
            "Custom Unity Assets",
            CUA_SCENE_MEMBER,
            atom_type="CustomUnityAsset",
            key="cua-scene",
        )
        invalid_atom_type_id = self.insert_resource(
            "Custom Unity Assets",
            CUA_BUNDLE_MEMBER,
            atom_type="Person",
            key="cua-invalid-atom-type",
        )
        wrong_prefix_id = self.insert_resource(
            "Custom Unity Assets",
            SCENE_MEMBER,
            atom_type="",
            key="cua-wrong-prefix",
        )
        wrong_suffix_id = self.insert_resource(
            "Custom Unity Assets",
            CUA_WRONG_SUFFIX_MEMBER,
            atom_type="",
            key="cua-wrong-suffix",
        )
        wrong_resource_type_id = self.insert_resource(
            "Plugins",
            CUA_BUNDLE_MEMBER,
            atom_type="",
            key="cua-wrong-resource-type",
        )
        wrong_case_resource_type_id = self.insert_resource(
            "custom unity assets",
            CUA_BUNDLE_MEMBER,
            atom_type="",
            key="cua-wrong-case-resource-type",
        )
        lease_results = (
            {"applied": True, "reconcile": {"enable": 1}},
            {"applied": True, "reconcile": {"enable": 0}},
        )
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                side_effect=lease_results,
            ) as lease,
            mock.patch(
                "vampip.service.request_custom_unity_asset_load",
                side_effect=("bundle-request", "scene-request"),
            ) as request,
        ):
            with self.assertRaisesRegex(ValueError, "confirm_critical"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="CUA Target",
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "confirm_replace"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "merge is not supported"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="CUA Target",
                    merge=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "no longer available"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="Missing CUA",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(
                ValueError,
                "create_if_missing requires target_uid to be absent",
            ):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="CUA Target",
                    create_if_missing=True,
                    confirm_critical=True,
                )
            with self.assertRaisesRegex(ValueError, "expected CustomUnityAsset"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="Wrong Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "invalid atom type"):
                self.service.apply_resource(
                    invalid_atom_type_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "outside Custom/Assets"):
                self.service.apply_resource(
                    wrong_prefix_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, r"\.assetbundle or \.scene"):
                self.service.apply_resource(
                    wrong_suffix_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "browse-only"):
                self.service.apply_resource(
                    wrong_resource_type_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
            with self.assertRaisesRegex(ValueError, "browse-only"):
                self.service.apply_resource(
                    wrong_case_resource_type_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )

            existing = self.service.apply_resource(
                bundle_id,
                target_uid="CUA Target",
                confirm_critical=True,
                confirm_replace=True,
            )
            created = self.service.apply_resource(
                scene_id,
                target_uid="New CUA",
                create_if_missing=True,
                confirm_critical=True,
            )

        self.assertEqual(existing["category"], "custom-unity-assets")
        self.assertEqual(existing["target_atom_type"], "CustomUnityAsset")
        self.assertTrue(existing["target_existed"])
        self.assertTrue(existing["rescan"])
        self.assertFalse(created["target_existed"])
        self.assertFalse(created["rescan"])
        self.assertEqual(
            lease.call_args_list,
            [
                mock.call(
                    bundle_id,
                    days=3.0,
                    label="Custom Unity Asset: Props",
                    apply=True,
                    bridge_rescan=False,
                ),
                mock.call(
                    scene_id,
                    days=3.0,
                    label="Custom Unity Asset: Environment",
                    apply=True,
                    bridge_rescan=False,
                ),
            ],
        )
        self.assertEqual(
            request.call_args_list,
            [
                mock.call(
                    self.vam_root,
                    target_uid="CUA Target",
                    resource_ref=f"Creator.HairPack.1:/{CUA_BUNDLE_MEMBER}",
                    rescan=True,
                    create_if_missing=False,
                ),
                mock.call(
                    self.vam_root,
                    target_uid="New CUA",
                    resource_ref=f"Creator.HairPack.1:/{CUA_SCENE_MEMBER}",
                    rescan=False,
                    create_if_missing=True,
                ),
            ],
        )

    def test_loose_custom_unity_asset_uses_the_catalog_relative_path(self) -> None:
        local_member = "Custom/Assets/Loose/Local Environment.scene"
        local_path = self.vam_root / local_member
        local_path.parent.mkdir(parents=True)
        local_path.write_bytes(b"local asset bundle")
        with connect(self.state) as connection:
            cursor = connection.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, 'browserassist', 'local-cua', '', '', '[]',
                          ?, 'Custom Unity Assets', 'CustomUnityAsset',
                          0, 0, '[]', '2026-01-01T00:00:00+00:00')
                """,
                (str(self.vam_root), local_member.replace("/", "\\")),
            )
            resource_id = int(cursor.lastrowid)

        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_custom_unity_asset_load",
                return_value="local-cua-request",
            ) as request,
        ):
            result = self.service.apply_resource(
                resource_id,
                target_uid="CUA Target",
                confirm_critical=True,
                confirm_replace=True,
            )

        self.assertEqual(result["resource_ref"], local_member)
        self.assertFalse(result["rescan"])
        self.assertTrue(result["lease"]["already_local"])
        request.assert_called_once_with(
            self.vam_root,
            target_uid="CUA Target",
            resource_ref=local_member,
            rescan=False,
            create_if_missing=False,
        )

    def test_custom_unity_asset_capability_and_choice_are_fresh_and_bounded(
        self,
    ) -> None:
        bundle_id = self.insert_resource(
            "Custom Unity Assets",
            CUA_BUNDLE_MEMBER,
            atom_type="",
            key="cua-capability",
        )
        missing_load_capability = self.roster()
        missing_load_capability["capabilities"] = [
            capability
            for capability in missing_load_capability["capabilities"]
            if capability != "custom-unity-asset-load"
        ]
        with (
            mock.patch.object(
                self.service,
                "persons",
                return_value=missing_load_capability,
            ),
            mock.patch.object(self.service, "lease_resource") as lease,
        ):
            with self.assertRaisesRegex(ValueError, "does not provide"):
                self.service.apply_resource(
                    bundle_id,
                    target_uid="CUA Target",
                    confirm_critical=True,
                    confirm_replace=True,
                )
        lease.assert_not_called()

        token = "a" * 32
        with mock.patch(
            "vampip.service.request_custom_unity_asset_choice",
            return_value="choice-request",
        ) as request:
            with self.assertRaisesRegex(ValueError, "positive integer"):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    True,  # type: ignore[arg-type]
                    token,
                )
            with self.assertRaisesRegex(ValueError, "32 hexadecimal"):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    1,
                    "not-a-token",
                )

            stale = self.roster()
            with (
                mock.patch.object(self.service, "persons", return_value=stale),
                self.assertRaisesRegex(ValueError, "stale or invalid"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    1,
                    "b" * 32,
                )

            missing_index = self.roster()
            with (
                mock.patch.object(
                    self.service,
                    "persons",
                    return_value=missing_index,
                ),
                self.assertRaisesRegex(ValueError, "not present"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    2,
                    token,
                )

            dll_on = self.roster()
            dll_atom = next(
                atom for atom in dll_on["atoms"] if atom["uid"] == "CUA Target"
            )
            dll_atom["cua"]["loadDll"] = 0
            with (
                mock.patch.object(self.service, "persons", return_value=dll_on),
                self.assertRaisesRegex(ValueError, "DLL loading is off"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    1,
                    token,
                )

            with (
                mock.patch.object(self.service, "persons", return_value=self.roster()),
                self.assertRaisesRegex(ValueError, "expected CustomUnityAsset"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "Wrong Target",
                    1,
                    token,
                )

            missing_choice_capability = self.roster()
            missing_choice_capability["capabilities"] = [
                capability
                for capability in missing_choice_capability["capabilities"]
                if capability != "custom-unity-asset-choice"
            ]
            with (
                mock.patch.object(
                    self.service,
                    "persons",
                    return_value=missing_choice_capability,
                ),
                self.assertRaisesRegex(ValueError, "does not provide"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    1,
                    token,
                )

            with (
                mock.patch.object(
                    self.service,
                    "_ensure_bridge_mailbox_idle",
                    side_effect=LiveActionBusyError("bridge busy"),
                ),
                self.assertRaisesRegex(LiveActionBusyError, "bridge busy"),
            ):
                self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    1,
                    token,
                )

            with mock.patch.object(
                self.service,
                "persons",
                return_value=self.roster(),
            ):
                selected = self.service.select_custom_unity_asset_choice(
                    "CUA Target",
                    3,
                    token,
                )

        self.assertEqual(selected["operation"], "select-custom-unity-asset-choice")
        self.assertEqual(selected["target_atom_type"], "CustomUnityAsset")
        self.assertEqual(selected["choice_index"], 3)
        self.assertEqual(selected["bridge_request"], "choice-request")
        request.assert_called_once_with(
            self.vam_root,
            target_uid="CUA Target",
            choice_index=3,
            choice_token=token,
        )

    def test_atom_add_derives_allowlisted_type_only_from_category(self) -> None:
        self.insert_resource(
            "Preset Atom",
            EMPTY_PRESET_MEMBER,
            atom_type="Empty",
        )
        self.insert_resource(
            "Preset Atom",
            UNSUPPORTED_ATOM_PRESET_MEMBER,
            atom_type="PackageDefinedWidget",
        )
        categories = self.service.workspace_categories()["categories"]
        empty_category = next(
            str(category["id"])
            for category in categories
            if category.get("target_atom_type") == "Empty"
        )
        unsupported_category = next(
            str(category["id"])
            for category in categories
            if category.get("target_atom_type") == "PackageDefinedWidget"
        )

        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_add_atom",
                side_effect=("empty-request", "subscene-request", "cua-request"),
            ) as request,
        ):
            existing = self.service.add_atom(empty_category, "Empty Target")
            created = self.service.add_atom(empty_category, "New Empty")
            subscene = self.service.add_atom("subscenes", "New SubScene")
            existing_cua = self.service.add_atom(
                "custom-unity-assets",
                "CUA Target",
            )
            created_cua = self.service.add_atom(
                "custom-unity-assets",
                "New CUA",
            )
            with self.assertRaisesRegex(ValueError, "expected Empty"):
                self.service.add_atom(empty_category, "Wrong Target")
            with self.assertRaisesRegex(ValueError, "browse-only"):
                self.service.add_atom(unsupported_category, "Unsafe")
            with self.assertRaisesRegex(ValueError, "browse-only"):
                self.service.add_atom("preset-hair", "Not A Person")
            with self.assertRaisesRegex(ValueError, "unknown workspace category"):
                self.service.add_atom("not-a-category", "Anything")

        self.assertTrue(existing["already_exists"])
        self.assertIsNone(existing["bridge_request"])
        self.assertEqual(created["target_atom_type"], "Empty")
        self.assertEqual(subscene["target_atom_type"], "SubScene")
        self.assertTrue(existing_cua["already_exists"])
        self.assertEqual(created_cua["target_atom_type"], "CustomUnityAsset")
        self.assertEqual(
            request.call_args_list,
            [
                mock.call(
                    self.vam_root,
                    atom_type="Empty",
                    target_uid="New Empty",
                ),
                mock.call(
                    self.vam_root,
                    atom_type="SubScene",
                    target_uid="New SubScene",
                ),
                mock.call(
                    self.vam_root,
                    atom_type="CustomUnityAsset",
                    target_uid="New CUA",
                ),
            ],
        )

    def test_scene_replace_requires_confirmation_but_merge_does_not(self) -> None:
        resource_id = self.insert_resource(
            "Scene",
            SCENE_MEMBER,
            atom_type="",
        )
        lease_result = {"applied": False}
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(
                self.service,
                "lease_resource",
                return_value=lease_result,
            ) as lease,
            mock.patch(
                "vampip.service.request_scene_load",
                side_effect=("merge-request", "replace-request"),
            ) as request,
        ):
            with self.assertRaisesRegex(ValueError, "confirm_replace must be true"):
                self.service.apply_resource(resource_id)
            merged = self.service.apply_resource(resource_id, merge=True)
            replaced = self.service.apply_resource(
                resource_id,
                confirm_replace=True,
            )

        self.assertEqual(lease.call_count, 2)
        self.assertEqual(merged["bridge_request"], "merge-request")
        self.assertTrue(merged["merge"])
        self.assertEqual(replaced["bridge_request"], "replace-request")
        self.assertFalse(replaced["merge"])
        self.assertEqual(
            request.call_args_list,
            [
                mock.call(
                    self.vam_root,
                    f"Creator.HairPack.1:/{SCENE_MEMBER}",
                    rescan=True,
                    merge=True,
                ),
                mock.call(
                    self.vam_root,
                    f"Creator.HairPack.1:/{SCENE_MEMBER}",
                    rescan=True,
                    merge=False,
                ),
            ],
        )

    def test_browse_only_resource_cannot_trigger_a_live_action(self) -> None:
        with connect(self.state) as connection:
            connection.execute(
                """
                UPDATE catalog_resources
                SET resource_type = 'Plugins'
                WHERE id = ?
                """,
                (self.resource_id,),
            )
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch.object(self.service, "lease_resource") as lease,
        ):
            with self.assertRaisesRegex(ValueError, "browse-only"):
                self.service.apply_resource(
                    self.resource_id,
                    target_uid="Person",
                )
        lease.assert_not_called()

    def test_add_person_and_person_or_atom_selection_are_idempotent(self) -> None:
        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.request_add_person",
                return_value="add-request",
            ) as add,
            mock.patch(
                "vampip.service.request_select_person",
                return_value="person-select-request",
            ) as select_person,
            mock.patch(
                "vampip.service.request_select_atom",
                return_value="atom-select-request",
            ) as select_atom,
        ):
            existing = self.service.add_person("Person")
            created = self.service.add_person("New Person")
            selected = self.service.select_person("Person")
            changed_person = self.service.select_person("Person 2")
            changed_atom = self.service.select_atom("Light")

        self.assertTrue(existing["already_exists"])
        self.assertIsNone(existing["bridge_request"])
        self.assertEqual(created["bridge_request"], "add-request")
        add.assert_called_once_with(self.vam_root, "New Person")
        self.assertTrue(selected["already_selected"])
        self.assertIsNone(selected["bridge_request"])
        self.assertEqual(changed_person["bridge_request"], "person-select-request")
        select_person.assert_called_once_with(self.vam_root, "Person 2")
        self.assertEqual(changed_atom["bridge_request"], "atom-select-request")
        select_atom.assert_called_once_with(self.vam_root, "Light")

    def test_an_unfinished_bridge_request_blocks_mailbox_replacement(self) -> None:
        with (
            mock.patch(
                "vampip.service.read_bridge_request",
                return_value={"requestId": "first", "command": "applyPersonPreset"},
            ),
            mock.patch(
                "vampip.service.read_bridge_status",
                return_value={"requestId": "first", "state": "applying"},
            ),
        ):
            with self.assertRaisesRegex(LiveActionBusyError, "another request"):
                self.service.apply_person_resource(
                    self.resource_id,
                    target_uid="Person",
                )
        with connect(self.state) as connection:
            self.assertEqual(list_leases(connection), [])

    def test_two_service_instances_cannot_overwrite_bridge_mailbox(self) -> None:
        second_service = ManagerService(
            self.addons,
            self.state.parent / "second-state",
            vam_root=self.vam_root,
            process_probe=lambda: list(self.pids),
        )
        first_writer_entered = threading.Event()
        release_first_writer = threading.Event()
        second_started = threading.Event()
        second_writer_called = threading.Event()
        results: dict[str, str] = {}
        errors: dict[str, BaseException] = {}

        def first_writer() -> str:
            first_writer_entered.set()
            if not release_first_writer.wait(2):
                raise TimeoutError("test did not release first mailbox writer")
            return request_select_atom(self.vam_root, "Light")

        def second_writer() -> str:
            second_writer_called.set()
            return request_select_atom(self.vam_root, "Empty Target")

        def run_first() -> None:
            try:
                results["first"] = self.service._queue_bridge_request(first_writer)
            except BaseException as error:
                errors["first"] = error

        def run_second() -> None:
            second_started.set()
            try:
                results["second"] = second_service._queue_bridge_request(second_writer)
            except BaseException as error:
                errors["second"] = error

        first_thread = threading.Thread(target=run_first)
        first_thread.start()
        self.assertTrue(first_writer_entered.wait(2))
        second_thread = threading.Thread(target=run_second)
        second_thread.start()
        self.assertTrue(second_started.wait(2))
        second_wrote_while_first_held_lock = second_writer_called.wait(0.1)
        release_first_writer.set()
        first_thread.join(2)
        second_thread.join(2)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertFalse(second_wrote_while_first_held_lock)
        self.assertFalse(second_writer_called.is_set())
        self.assertNotIn("first", errors)
        self.assertIsInstance(errors.get("second"), LiveActionBusyError)
        request = read_bridge_request(self.vam_root)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request["requestId"], results["first"])
        self.assertEqual(request["targetUid"], "Light")

    def test_mailbox_transaction_is_reentrant_without_relocking_file(
        self,
    ) -> None:
        self.assertEqual(self.service._bridge_mailbox_transaction_depth, 0)
        with self.service._bridge_mailbox_transaction(require_idle=False):
            self.assertEqual(self.service._bridge_mailbox_transaction_depth, 1)
            with self.service._bridge_mailbox_transaction(require_idle=False):
                self.assertEqual(
                    self.service._bridge_mailbox_transaction_depth,
                    2,
                )
            self.assertEqual(self.service._bridge_mailbox_transaction_depth, 1)
        self.assertEqual(self.service._bridge_mailbox_transaction_depth, 0)

    def test_reconcile_if_idle_does_not_wait_for_another_manager_mailbox(
        self,
    ) -> None:
        second_service = ManagerService(
            self.addons,
            self.state.parent / "second-state",
            vam_root=self.vam_root,
            process_probe=lambda: list(self.pids),
        )
        with (
            self.service._bridge_mailbox_transaction(require_idle=False),
            mock.patch.object(second_service, "_run_reconcile") as reconcile,
        ):
            self.assertIsNone(second_service.reconcile_if_idle(apply=True))
        reconcile.assert_not_called()

    def test_reconcile_holds_mailbox_lock_across_switch_and_request(self) -> None:
        from vampip import service as service_module

        self.service.reconcile(apply=True, activate=True)
        self.service.lease(["Creator.HairPack.1"], apply=False)
        self.pids.append(1234)

        switch_started = threading.Event()
        release_switch = threading.Event()
        select_called = threading.Event()
        original_apply_switch = service_module.apply_switch
        order: list[str] = []
        errors: list[BaseException] = []
        results: dict[str, dict[str, object]] = {}

        def blocking_apply_switch(*args: object, **kwargs: object) -> object:
            order.append("switch")
            switch_started.set()
            if not release_switch.wait(2):
                raise TimeoutError("test did not release package switch")
            return original_apply_switch(*args, **kwargs)

        def reconcile() -> None:
            try:
                results["reconcile"] = self.service.reconcile(apply=True)
            except BaseException as error:
                errors.append(error)

        def select() -> None:
            try:
                results["select"] = self.service.select_atom("Light")
            except BaseException as error:
                errors.append(error)

        def rescan_request(*args: object, **kwargs: object) -> str:
            order.append("rescan")
            return "rescan-request"

        def select_request(*args: object, **kwargs: object) -> str:
            order.append("select")
            select_called.set()
            return "select-request"

        with (
            mock.patch.object(self.service, "persons", return_value=self.roster()),
            mock.patch(
                "vampip.service.apply_switch",
                side_effect=blocking_apply_switch,
            ),
            mock.patch(
                "vampip.service.request_rescan",
                side_effect=rescan_request,
            ),
            mock.patch(
                "vampip.service.request_select_atom",
                side_effect=select_request,
            ),
        ):
            reconcile_thread = threading.Thread(target=reconcile)
            reconcile_thread.start()
            self.assertTrue(switch_started.wait(2))
            select_thread = threading.Thread(target=select)
            select_thread.start()
            self.assertFalse(select_called.wait(0.1))
            release_switch.set()
            reconcile_thread.join(2)
            select_thread.join(2)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertFalse(select_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(order, ["switch", "rescan", "select"])
        self.assertEqual(
            results["reconcile"]["bridge_request"],
            "rescan-request",
        )
        self.assertEqual(results["select"]["bridge_request"], "select-request")

    def test_external_busy_mailbox_after_switch_is_reported_not_overwritten(
        self,
    ) -> None:
        self.service.reconcile(apply=True, activate=True)
        self.service.lease(["Creator.HairPack.1"], apply=False)
        self.pids.append(1234)

        with (
            mock.patch(
                "vampip.service.read_bridge_request",
                side_effect=(
                    None,
                    {
                        "requestId": "external",
                        "command": "selectAtom",
                    },
                ),
            ),
            mock.patch(
                "vampip.service.read_bridge_status",
                return_value={
                    "requestId": "external",
                    "state": "queued",
                },
            ),
            mock.patch("vampip.service.request_rescan") as rescan,
        ):
            result = self.service.reconcile(apply=True)

        self.assertTrue(self.archive.exists())
        self.assertIsNone(result["bridge_request"])
        self.assertTrue(result["bridge_busy"])
        self.assertIn("another request", result["bridge_message"])
        rescan.assert_not_called()

    def test_existing_busy_mailbox_blocks_switch_that_needs_rescan(self) -> None:
        self.service.reconcile(apply=True, activate=True)
        self.service.lease(["Creator.HairPack.1"], apply=False)
        self.pids.append(1234)
        self.assertFalse(self.archive.exists())

        with (
            mock.patch(
                "vampip.service.read_bridge_request",
                return_value={
                    "requestId": "existing",
                    "command": "addPerson",
                },
            ),
            mock.patch(
                "vampip.service.read_bridge_status",
                return_value={
                    "requestId": "existing",
                    "state": "adding",
                },
            ),
            mock.patch("vampip.service.apply_switch") as switch,
            mock.patch("vampip.service.request_rescan") as rescan,
        ):
            with self.assertRaisesRegex(LiveActionBusyError, "another request"):
                self.service.reconcile(apply=True)

        self.assertFalse(self.archive.exists())
        self.assertTrue(Path(f"{self.archive}.vampip-disabled").exists())
        switch.assert_not_called()
        rescan.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from vampip.bridge import (
    ATOM_TYPE_ALLOWLIST,
    CUSTOM_UNITY_ASSET_RESOURCE_PREFIX,
    PERSON_PRESET_PREFIXES,
    SUBSCENE_RESOURCE_PREFIX,
    bridge_directory,
    read_bridge_request,
    read_bridge_status,
    read_scene_status,
    request_add_atom,
    request_add_person,
    request_atom_preset,
    request_custom_unity_asset_choice,
    request_custom_unity_asset_load,
    request_person_clothing,
    request_person_preset,
    request_rescan,
    request_scene_load,
    request_select_atom,
    request_select_person,
    request_subscene_load,
)


class BridgeProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vam_root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def read_request(self) -> dict[str, object]:
        return json.loads(
            (bridge_directory(self.vam_root) / "request.json").read_text(
                encoding="utf-8"
            )
        )

    def test_rescan_request_uses_protocol_two(self) -> None:
        request_id = request_rescan(self.vam_root, browser_assist="off")

        request = self.read_request()
        self.assertEqual(request["protocol"], 2)
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "rescan")
        self.assertEqual(request["browserAssist"], "off")
        self.assertIn("createdAtUtc", request)

    def test_person_hair_request_writes_allowlisted_fields(self) -> None:
        resource_ref = (
            "Author.HairPack.7:/"
            "Custom/Atom/Person/Hair/Author/Long/Preset_Long.vap"
        )
        request_id = request_person_preset(
            self.vam_root,
            "Person #2",
            "hair",
            resource_ref,
            rescan=False,
        )

        request = self.read_request()
        self.assertEqual(request["protocol"], 2)
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "applyPersonPreset")
        self.assertEqual(request["targetUid"], "Person #2")
        self.assertEqual(request["presetKind"], "hair")
        self.assertEqual(request["resourceRef"], resource_ref)
        self.assertIs(request["rescan"], False)
        self.assertIs(request["merge"], False)

    def test_all_person_preset_kinds_use_their_own_prefix(self) -> None:
        for preset_kind, prefix in PERSON_PRESET_PREFIXES.items():
            resource_ref = f"Author.Pack.1:/{prefix}Preset_Example.vap"
            with self.subTest(preset_kind=preset_kind):
                request_person_preset(
                    self.vam_root,
                    "Person",
                    preset_kind,
                    resource_ref,
                    merge=True,
                )
                request = self.read_request()
                self.assertEqual(request["presetKind"], preset_kind)
                self.assertEqual(request["resourceRef"], resource_ref)
                self.assertIs(request["merge"], True)

    def test_person_hair_request_accepts_local_ref_case_insensitively(self) -> None:
        request_person_preset(
            self.vam_root,
            "Person",
            "hair",
            "custom/atom/person/hair/Author/PRESET_Long.VAP",
        )
        self.assertEqual(self.read_request()["rescan"], True)

    def test_person_hair_request_rejects_refs_outside_allowlist(self) -> None:
        invalid_refs = (
            "",
            "/Custom/Atom/Person/Hair/Preset_Long.vap",
            r"Custom\Atom\Person\Hair\Preset_Long.vap",
            "Custom/Atom/Person/Hair/../Preset_Long.vap",
            "Custom/Atom/Person/Hair//Preset_Long.vap",
            "Custom/Atom/Person/Hair/./Preset_Long.vap",
            "Custom/Atom/Person/Appearance/Preset_Look.vap",
            "Custom/Atom/Person/Hair/Long.vap",
            "Custom/Atom/Person/Hair/Preset_Long.json",
            "file:///Custom/Atom/Person/Hair/Preset_Long.vap",
            "C:/Custom/Atom/Person/Hair/Preset_Long.vap",
            "Author.Hair:/Custom/Atom/Person/Hair/Preset_Long.vap",
            "Author..1:/Custom/Atom/Person/Hair/Preset_Long.vap",
            (
                "Author.Hair.1:/Custom/Atom/Person/Hair/"
                "Other.Thing.2:/Custom/Atom/Person/Hair/Preset_Long.vap"
            ),
        )
        for resource_ref in invalid_refs:
            with self.subTest(resource_ref=resource_ref):
                with self.assertRaises(ValueError):
                    request_person_preset(
                        self.vam_root,
                        "Person",
                        "hair",
                        resource_ref,
                    )

    def test_person_preset_request_rejects_mismatched_kind_and_bad_scalars(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            request_person_preset(
                self.vam_root,
                "Person",
                "appearance",
                "Custom/Atom/Person/Hair/Preset_Long.vap",
            )
        with self.assertRaises(ValueError):
            request_person_preset(
                self.vam_root,
                "Person",
                "unknown",
                "Custom/Atom/Person/Hair/Preset_Long.vap",
            )
        with self.assertRaises(ValueError):
            request_person_preset(
                self.vam_root,
                "\n",
                "hair",
                "Custom/Atom/Person/Hair/Preset_Long.vap",
            )
        with self.assertRaises(TypeError):
            request_person_preset(
                self.vam_root,
                "Person",
                "hair",
                "Custom/Atom/Person/Hair/Preset_Long.vap",
                rescan=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            request_person_preset(
                self.vam_root,
                "Person",
                "hair",
                "Custom/Atom/Person/Hair/Preset_Long.vap",
                merge=1,  # type: ignore[arg-type]
            )

    def test_add_and_select_requests_are_bounded(self) -> None:
        add_id = request_add_person(self.vam_root, "New Person")
        add_request = self.read_request()
        self.assertEqual(add_request["requestId"], add_id)
        self.assertEqual(add_request["command"], "addPerson")
        self.assertEqual(add_request["targetUid"], "New Person")

        select_id = request_select_person(self.vam_root, "New Person")
        select_request = self.read_request()
        self.assertEqual(select_request["requestId"], select_id)
        self.assertEqual(select_request["command"], "selectPerson")
        self.assertEqual(select_request["targetUid"], "New Person")

        atom_select_id = request_select_atom(self.vam_root, "WindowCamera")
        atom_select_request = self.read_request()
        self.assertEqual(atom_select_request["requestId"], atom_select_id)
        self.assertEqual(atom_select_request["command"], "selectAtom")
        self.assertEqual(atom_select_request["targetUid"], "WindowCamera")

        for invalid_uid in ("", "\n", "x" * 201):
            with self.subTest(invalid_uid=invalid_uid):
                with self.assertRaises(ValueError):
                    request_add_person(self.vam_root, invalid_uid)
                with self.assertRaises(ValueError):
                    request_select_atom(self.vam_root, invalid_uid)

    def test_person_clothing_request_uses_desired_state_and_exact_revision(
        self,
    ) -> None:
        revision = "A1" * 16
        local_ref = (
            "Custom/Clothing/Female/Creator/Evening Dress/Evening Dress.vam"
        )
        request_id = request_person_clothing(
            self.vam_root,
            "Person #2",
            local_ref,
            active=True,
            revision=revision,
            rescan=False,
        )

        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "setPersonClothingResource")
        self.assertEqual(request["targetUid"], "Person #2")
        self.assertEqual(request["resourceRef"], local_ref)
        self.assertEqual(request["desiredState"], "worn")
        self.assertEqual(request["revision"], revision)
        self.assertIs(request["rescan"], False)
        self.assertEqual(
            set(request) - {"protocol", "requestId", "createdAtUtc"},
            {
                "command",
                "targetUid",
                "resourceRef",
                "desiredState",
                "revision",
                "rescan",
            },
        )

        packaged_ref = (
            "Author.Menswear.3:/"
            "Custom/Clothing/Male/Author/Jacket/Jacket.VAM"
        )
        request_person_clothing(
            self.vam_root,
            "Person",
            packaged_ref,
            active=False,
            revision="0" * 32,
        )
        request = self.read_request()
        self.assertEqual(request["resourceRef"], packaged_ref)
        self.assertEqual(request["desiredState"], "removed")
        self.assertIs(request["rescan"], True)

    def test_person_clothing_request_rejects_unscoped_refs_and_bad_scalars(
        self,
    ) -> None:
        valid_ref = "Custom/Clothing/Female/Creator/Dress/Dress.vam"
        revision = "0" * 32
        for invalid_ref in (
            "",
            "/Custom/Clothing/Female/Creator/Dress/Dress.vam",
            r"Custom\Clothing\Female\Creator\Dress\Dress.vam",
            "Custom/Clothing/Creator/Dress/Dress.vam",
            "Custom/Clothing/Female/Creator/../Dress.vam",
            "Custom/Clothing/Female/Creator/Dress/Dress.vap",
            "Custom/Atom/Person/Clothing/Preset_Outfit.vap",
            "Author.Dress:/Custom/Clothing/Female/Creator/Dress/Dress.vam",
            "Author..1:/Custom/Clothing/Female/Creator/Dress/Dress.vam",
            (
                "Author.Dress.1:/Custom/Clothing/Female/"
                "Other.Dress.2:/Custom/Clothing/Female/Creator/Dress.vam"
            ),
        ):
            with self.subTest(invalid_ref=invalid_ref):
                with self.assertRaises(ValueError):
                    request_person_clothing(
                        self.vam_root,
                        "Person",
                        invalid_ref,
                        active=True,
                        revision=revision,
                    )

        for invalid_revision in (
            "",
            "0" * 31,
            "0" * 33,
            "g" * 32,
            "0" * 31 + "\n",
        ):
            with self.subTest(invalid_revision=invalid_revision):
                with self.assertRaises(ValueError):
                    request_person_clothing(
                        self.vam_root,
                        "Person",
                        valid_ref,
                        active=True,
                        revision=invalid_revision,
                    )

        with self.assertRaises(TypeError):
            request_person_clothing(
                self.vam_root,
                "Person",
                valid_ref,
                active=1,  # type: ignore[arg-type]
                revision=revision,
            )
        with self.assertRaises(TypeError):
            request_person_clothing(
                self.vam_root,
                "Person",
                valid_ref,
                active=True,
                revision=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            request_person_clothing(
                self.vam_root,
                "Person",
                valid_ref,
                active=True,
                revision=revision,
                rescan=1,  # type: ignore[arg-type]
            )

    def test_add_atom_request_uses_exact_native_allowlist(self) -> None:
        request_id = request_add_atom(
            self.vam_root,
            "WindowCamera",
            "External Camera",
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "addAtom")
        self.assertEqual(request["atomType"], "WindowCamera")
        self.assertEqual(request["targetUid"], "External Camera")
        self.assertIn("SubScene", ATOM_TYPE_ALLOWLIST)
        self.assertNotIn("Person", ATOM_TYPE_ALLOWLIST)

        for invalid_type in (
            "",
            "Person",
            "windowcamera",
            "Author.CustomAtom",
            "Button|Capsule",
            " WindowCamera",
        ):
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(ValueError):
                    request_add_atom(
                        self.vam_root,
                        invalid_type,
                        "External Camera",
                    )
        with self.assertRaises(TypeError):
            request_add_atom(
                self.vam_root,
                1,  # type: ignore[arg-type]
                "External Camera",
            )

    def test_atom_preset_request_is_type_scoped_and_bounded(self) -> None:
        local_ref = "Custom/Atom/WindowCamera/Preset_Framing.vap"
        request_id = request_atom_preset(
            self.vam_root,
            "External Camera",
            "WindowCamera",
            local_ref,
            rescan=False,
            merge=False,
            create_if_missing=True,
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "applyAtomPreset")
        self.assertEqual(request["targetUid"], "External Camera")
        self.assertEqual(request["atomType"], "WindowCamera")
        self.assertEqual(request["resourceRef"], local_ref)
        self.assertIs(request["rescan"], False)
        self.assertIs(request["merge"], False)
        self.assertIs(request["createIfMissing"], True)

        package_ref = (
            "Author.WebTools.4:/"
            "Custom/Atom/WebBrowser/Author/Preset_Search.vap"
        )
        request_atom_preset(
            self.vam_root,
            "Browser",
            "WebBrowser",
            package_ref,
        )
        self.assertEqual(self.read_request()["resourceRef"], package_ref)

        for invalid_ref in (
            "Custom/Atom/WebBrowser/Preset_Search.vap",
            "Custom/Atom/WindowCamera/Search.vap",
            "Custom/Atom/WindowCamera/Preset_Search.json",
            "Custom/Atom/WindowCamera/../Preset_Search.vap",
        ):
            with self.subTest(invalid_ref=invalid_ref):
                with self.assertRaises(ValueError):
                    request_atom_preset(
                        self.vam_root,
                        "External Camera",
                        "WindowCamera",
                        invalid_ref,
                    )
        with self.assertRaises(ValueError):
            request_atom_preset(
                self.vam_root,
                "Person",
                "Person",
                "Custom/Atom/Person/Preset_Look.vap",
            )
        with self.assertRaisesRegex(ValueError, "cannot both be true"):
            request_atom_preset(
                self.vam_root,
                "External Camera",
                "WindowCamera",
                local_ref,
                merge=True,
                create_if_missing=True,
            )
        for option in ("rescan", "merge", "create_if_missing"):
            with self.subTest(option=option):
                kwargs = {option: 1}
                with self.assertRaises(TypeError):
                    request_atom_preset(
                        self.vam_root,
                        "External Camera",
                        "WindowCamera",
                        local_ref,
                        **kwargs,  # type: ignore[arg-type]
                    )

    def test_subscene_request_accepts_only_subscene_resources(self) -> None:
        local_ref = f"{SUBSCENE_RESOURCE_PREFIX}Apartment.json"
        request_id = request_subscene_load(
            self.vam_root,
            "Apartment",
            local_ref,
            rescan=False,
            create_if_missing=True,
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "loadSubscene")
        self.assertEqual(request["targetUid"], "Apartment")
        self.assertEqual(request["resourceRef"], local_ref)
        self.assertIs(request["rescan"], False)
        self.assertIs(request["createIfMissing"], True)

        package_ref = (
            "Author.Rooms.2:/Custom/SubScene/Rooms/Apartment.JSON"
        )
        request_subscene_load(
            self.vam_root,
            "Apartment",
            package_ref,
        )
        self.assertEqual(self.read_request()["resourceRef"], package_ref)

        for invalid_ref in (
            "Saves/scene/Apartment.json",
            "Custom/SubScene/../Apartment.json",
            "Custom/SubScene/Apartment.vap",
            "Author.Rooms:/Custom/SubScene/Apartment.json",
        ):
            with self.subTest(invalid_ref=invalid_ref):
                with self.assertRaises(ValueError):
                    request_subscene_load(
                        self.vam_root,
                        "Apartment",
                        invalid_ref,
                    )
        with self.assertRaises(TypeError):
            request_subscene_load(
                self.vam_root,
                "Apartment",
                local_ref,
                rescan=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            request_subscene_load(
                self.vam_root,
                "Apartment",
                local_ref,
                create_if_missing=1,  # type: ignore[arg-type]
            )

    def test_custom_unity_asset_load_accepts_only_asset_resources(self) -> None:
        local_ref = (
            f"{CUSTOM_UNITY_ASSET_RESOURCE_PREFIX}"
            "Creator/Room.assetbundle"
        )
        request_id = request_custom_unity_asset_load(
            self.vam_root,
            "Room",
            local_ref,
            rescan=False,
            create_if_missing=True,
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "loadCustomUnityAsset")
        self.assertEqual(request["targetUid"], "Room")
        self.assertEqual(request["resourceRef"], local_ref)
        self.assertIs(request["rescan"], False)
        self.assertIs(request["createIfMissing"], True)
        self.assertNotIn("loadDll", request)
        self.assertNotIn("assetName", request)
        self.assertNotIn("atomType", request)

        package_ref = (
            "Author.Rooms.2:/Custom/Assets/Rooms/Apartment.SCENE"
        )
        request_custom_unity_asset_load(
            self.vam_root,
            "Apartment",
            package_ref,
        )
        request = self.read_request()
        self.assertEqual(request["resourceRef"], package_ref)
        self.assertIs(request["rescan"], True)
        self.assertIs(request["createIfMissing"], False)

        for invalid_ref in (
            "",
            "Custom/Assets/Room.vap",
            "Custom/Asset/Room.assetbundle",
            "Custom/Assets/../Room.assetbundle",
            r"Custom\Assets\Room.assetbundle",
            "Author.Rooms:/Custom/Assets/Room.assetbundle",
            "Author.Rooms.1:/Custom/Assets/Bad:Room.scene",
            "Saves/scene/Room.scene",
        ):
            with self.subTest(invalid_ref=invalid_ref):
                with self.assertRaises(ValueError):
                    request_custom_unity_asset_load(
                        self.vam_root,
                        "Room",
                        invalid_ref,
                    )
        with self.assertRaises(TypeError):
            request_custom_unity_asset_load(
                self.vam_root,
                "Room",
                local_ref,
                rescan=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            request_custom_unity_asset_load(
                self.vam_root,
                "Room",
                local_ref,
                create_if_missing=1,  # type: ignore[arg-type]
            )

    def test_custom_unity_asset_choice_is_token_and_index_bounded(self) -> None:
        token = "A1" * 16
        request_id = request_custom_unity_asset_choice(
            self.vam_root,
            "Room",
            7,
            token,
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(
            request["command"],
            "selectCustomUnityAssetChoice",
        )
        self.assertEqual(request["targetUid"], "Room")
        self.assertEqual(request["choiceIndex"], 7)
        self.assertEqual(request["choiceToken"], token.casefold())
        self.assertEqual(
            set(request)
            - {"protocol", "requestId", "createdAtUtc"},
            {"command", "targetUid", "choiceIndex", "choiceToken"},
        )

        for invalid_index in (True, 0, -1, 2_147_483_648, 1.5, "1"):
            with self.subTest(invalid_index=invalid_index):
                expected = TypeError if invalid_index in (True, 1.5, "1") else ValueError
                with self.assertRaises(expected):
                    request_custom_unity_asset_choice(
                        self.vam_root,
                        "Room",
                        invalid_index,  # type: ignore[arg-type]
                        token,
                    )
        for invalid_token in (
            "",
            "0" * 31,
            "0" * 33,
            "g" * 32,
            "0" * 31 + "\n",
        ):
            with self.subTest(invalid_token=invalid_token):
                with self.assertRaises(ValueError):
                    request_custom_unity_asset_choice(
                        self.vam_root,
                        "Room",
                        1,
                        invalid_token,
                    )
        with self.assertRaises(TypeError):
            request_custom_unity_asset_choice(
                self.vam_root,
                "Room",
                1,
                1,  # type: ignore[arg-type]
            )

    def test_scene_load_request_accepts_allowlisted_local_and_package_refs(
        self,
    ) -> None:
        local_ref = "Saves/scene/VAMPip/Example.JSON"
        request_id = request_scene_load(
            self.vam_root,
            local_ref,
            rescan=False,
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "loadScene")
        self.assertEqual(request["resourceRef"], local_ref)
        self.assertIs(request["rescan"], False)
        self.assertIs(request["merge"], False)

        package_ref = "Author.ScenePack.3:/Saves/scene/Example.json"
        request_scene_load(
            self.vam_root,
            package_ref,
            merge=True,
        )
        request = self.read_request()
        self.assertEqual(request["resourceRef"], package_ref)
        self.assertIs(request["rescan"], True)
        self.assertIs(request["merge"], True)

    def test_scene_load_request_rejects_refs_outside_allowlist(self) -> None:
        invalid_refs = (
            "",
            "/Saves/scene/Example.json",
            r"Saves\scene\Example.json",
            "Saves/scene/../Example.json",
            "Saves/scene//Example.json",
            "Saves/scene/./Example.json",
            "Saves/Person/Example.json",
            "Saves/scene/Example.vap",
            "file:///Saves/scene/Example.json",
            "C:/Saves/scene/Example.json",
            "Author.Scene:/Saves/scene/Example.json",
            "Author..1:/Saves/scene/Example.json",
            "Author.Scene.1:/Saves/scene/Bad:Name.json",
            (
                "Author.Scene.1:/Saves/scene/"
                "Other.Scene.2:/Saves/scene/Example.json"
            ),
        )
        for resource_ref in invalid_refs:
            with self.subTest(resource_ref=resource_ref):
                with self.assertRaises(ValueError):
                    request_scene_load(self.vam_root, resource_ref)

        with self.assertRaisesRegex(ValueError, r"\*\.json"):
            request_scene_load(
                self.vam_root,
                "Author.Scene:/Saves/scene/Example.json",
            )
        with self.assertRaises(TypeError):
            request_scene_load(
                self.vam_root,
                "Saves/scene/Example.json",
                rescan=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            request_scene_load(
                self.vam_root,
                "Saves/scene/Example.json",
                merge=1,  # type: ignore[arg-type]
            )

    def test_scene_reader_normalizes_simplejson_booleans(self) -> None:
        scene_path = bridge_directory(self.vam_root) / "scene.json"
        scene_path.parent.mkdir(parents=True)
        scene_path.write_text(
            json.dumps(
                {
                    "protocol": "2",
                    "bridgeVersion": "0.2.0",
                    "loading": "false",
                    "selectedUid": "Person",
                    "atoms": [
                        {
                            "uid": "Person",
                            "type": "Person",
                            "selected": "true",
                        },
                        {
                            "uid": "Light",
                            "type": "InvisibleLight",
                            "selected": "false",
                        },
                        {
                            "uid": "Room",
                            "type": "CustomUnityAsset",
                            "selected": "false",
                            "cua": {
                                "loadDll": "false",
                                "ready": "true",
                                "isAssetLoaded": "true",
                                "choiceToken": "1" * 32,
                                "choiceCount": 1,
                                "selectedIndex": 1,
                                "choices": [
                                    {"index": 1, "label": "assets/room.prefab"}
                                ],
                                "choicesTruncated": "false",
                            },
                        },
                    ],
                    "persons": [
                        {
                            "uid": "Person",
                            "selected": "true",
                            "clothing": {
                                "ready": "true",
                                "revision": "2" * 32,
                                "activeResourceRefs": [
                                    (
                                        "Author.Dress.1:/Custom/Clothing/"
                                        "Female/Author/Dress/Dress.vam"
                                    )
                                ],
                                "truncated": "false",
                            },
                        },
                        {"uid": "Person #2", "selected": "false"},
                    ],
                    "capabilities": [
                        "atom-roster",
                        "atom-select",
                        "scene-load",
                        "person-roster",
                        "person-preset-apply",
                        "person-add",
                        "person-select",
                    ],
                }
            ),
            encoding="utf-8",
        )

        scene = read_scene_status(self.vam_root)
        self.assertIsNotNone(scene)
        assert scene is not None
        self.assertEqual(scene["protocol"], 2)
        self.assertIs(scene["loading"], False)
        persons = scene["persons"]
        assert isinstance(persons, list)
        self.assertIs(persons[0]["selected"], True)
        self.assertIs(persons[1]["selected"], False)
        clothing = persons[0]["clothing"]
        self.assertIs(clothing["ready"], True)
        self.assertIs(clothing["truncated"], False)
        self.assertEqual(clothing["revision"], "2" * 32)
        atoms = scene["atoms"]
        assert isinstance(atoms, list)
        self.assertIs(atoms[0]["selected"], True)
        self.assertIs(atoms[1]["selected"], False)
        self.assertIs(atoms[2]["selected"], False)
        cua = atoms[2]["cua"]
        self.assertIs(cua["loadDll"], False)
        self.assertIs(cua["ready"], True)
        self.assertIs(cua["isAssetLoaded"], True)
        self.assertIs(cua["choicesTruncated"], False)

    def test_scene_and_request_readers_reject_other_protocols(self) -> None:
        directory = bridge_directory(self.vam_root)
        directory.mkdir(parents=True)
        for name in ("scene.json", "request.json"):
            (directory / name).write_text(
                json.dumps({"protocol": 1}),
                encoding="utf-8",
            )
        self.assertIsNone(read_scene_status(self.vam_root))
        self.assertIsNone(read_bridge_request(self.vam_root))

    def test_request_reader_accepts_protocol_two(self) -> None:
        request_rescan(self.vam_root)
        request = read_bridge_request(self.vam_root)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request["protocol"], 2)
        self.assertEqual(request["command"], "rescan")

    def test_status_reader_preserves_legacy_protocol_visibility(self) -> None:
        status_path = bridge_directory(self.vam_root) / "status.json"
        status_path.parent.mkdir(parents=True)
        status_path.write_text(
            json.dumps(
                {
                    "protocol": "1",
                    "state": "ready",
                    "ok": "false",
                }
            ),
            encoding="utf-8",
        )
        status = read_bridge_status(self.vam_root)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status["protocol"], 1)
        self.assertIs(status["ok"], False)


class BridgeSourceTests(unittest.TestCase):
    def test_packaged_and_documented_bridge_sources_match(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        packaged = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_bytes()
        documented = (
            repository / "bridge" / "vam" / "VAMPipBridge.cs"
        ).read_bytes()
        self.assertEqual(packaged, documented)

    def test_packaged_and_documented_bridge_readmes_match(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        packaged = (
            repository / "src" / "vampip" / "bridge_assets" / "README.md"
        ).read_bytes()
        documented = (
            repository / "bridge" / "vam" / "README.md"
        ).read_bytes()
        self.assertEqual(packaged, documented)

    def test_bridge_source_has_narrow_protocol_two_surface(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")
        self.assertIn("ProtocolVersion = 2", source)
        self.assertIn('BridgeVersion = "0.6.1"', source)
        self.assertIn("IgnoreCompletedLegacyRequest();", source)
        self.assertIn(
            "Ignored completed protocol-",
            source,
        )
        self.assertIn('"applyPersonPreset"', source)
        self.assertIn('"addAtom"', source)
        self.assertIn('"applyAtomPreset"', source)
        self.assertIn('"loadSubscene"', source)
        self.assertIn('"loadCustomUnityAsset"', source)
        self.assertIn('"selectCustomUnityAssetChoice"', source)
        self.assertIn('"setPersonClothingResource"', source)
        self.assertIn('"loadScene"', source)
        self.assertIn('"selectAtom"', source)
        self.assertIn('"atom-roster"', source)
        self.assertIn('"atom-select"', source)
        self.assertIn('"atom-add"', source)
        self.assertIn('"atom-preset-apply"', source)
        self.assertIn('"subscene-load"', source)
        self.assertIn('"custom-unity-asset-load"', source)
        self.assertIn('"custom-unity-asset-choice"', source)
        self.assertIn('"scene-load"', source)
        self.assertIn('"person-roster"', source)
        self.assertIn('"person-preset-apply"', source)
        self.assertIn('"person-clothing-item-toggle"', source)
        for capability in (
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
        ):
            self.assertIn(f'"{capability}"', source)
        self.assertIn('"person-add"', source)
        self.assertIn('"person-select"', source)
        self.assertIn('"addPerson"', source)
        self.assertIn('"selectPerson"', source)
        self.assertIn("FileManagerSecure.FileExists(request.ResourceRef)", source)
        self.assertIn('"clothing:" + normalized', source)
        self.assertIn("GetComponentsInChildren<DAZClothingItem>()", source)
        self.assertIn('if (presetKind == "hair") return "HairPresets";', source)
        self.assertIn(
            'if (presetKind == "general") return "Preset";',
            source,
        )
        self.assertIn(
            'return "Custom/Atom/Person/AnimationPresets/";',
            source,
        )
        self.assertIn('GetUrlJSONParam("presetBrowsePath")', source)
        self.assertIn("NormalizePath(", source)
        self.assertIn('"MergeLoadPreset"', source)
        self.assertIn('"LoadPreset"', source)
        self.assertIn("IsAllowedAtomType(", source)
        self.assertIn("AllowedAtomTypes", source)
        self.assertIn("atomType.IndexOf('|') < 0", source)
        self.assertIn(
            "AddAtomByType(\n                            atomType",
            source,
        )
        self.assertIn('GetStorableByID("Preset")', source)
        self.assertIn('GetStorableByID("SubScene")', source)
        self.assertIn('GetUrlJSONParam("browsePath")', source)
        self.assertIn("request.CreateIfMissing", source)
        self.assertIn(
            "request.CreateIfMissing && request.Merge",
            source,
        )
        strict_create_check = source.index("if (createIfMissing)")
        existing_type_check = source.index(
            "if (existing.type != atomType)",
            strict_create_check,
        )
        self.assertLess(strict_create_check, existing_type_check)
        strict_create_block = source[
            strict_create_check:existing_type_check
        ]
        self.assertIn(
            "createIfMissing requires targetUid to be absent",
            strict_create_block,
        )
        self.assertIn("yield break;", strict_create_block)
        self.assertIn("MaximumOperationWaitSeconds", source)
        self.assertIn("SelectController(", source)
        self.assertIn("FileManagerSecure.NormalizePath(request.ResourceRef)", source)
        self.assertIn("SuperController.singleton.LoadMerge(normalizedPath)", source)
        self.assertIn("SuperController.singleton.Load(normalizedPath)", source)
        self.assertIn('"Saves/scene/"', source)
        self.assertIn('scene["atoms"] = atoms;', source)
        self.assertIn(
            "_pendingRequest.Command == CommandRescan &&",
            source,
        )
        self.assertIn("an older pending rescan was coalesced", source)
        self.assertIn("Never collapse an atom or resource", source)
        self.assertNotIn("System.Reflection", source)
        self.assertNotIn(".GetType(", source)

    def test_bridge_source_has_bounded_tokenized_cua_surface(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        self.assertIn('parsed.AtomType = "CustomUnityAsset"', source)
        self.assertIn(
            'GetStorableByID("asset") as CustomUnityAssetLoader',
            source,
        )
        self.assertIn('GetUrlJSONParam("assetUrl")', source)
        self.assertIn('GetStringChooserJSONParam("assetName")', source)
        self.assertIn('GetBoolJSONParam("loadDll")', source)
        self.assertIn('"Custom/Assets/"', source)
        self.assertIn('".assetbundle"', source)
        self.assertIn('".scene"', source)
        self.assertIn("state.Loader.isAssetLoaded", source)
        self.assertIn("MaximumCuaChoicesPerAtom = 128", source)
        self.assertIn("MaximumCuaChoicesGlobally = 512", source)
        self.assertIn("MaximumCuaChoiceLabelLength = 256", source)
        self.assertIn("choicesTruncated", source)
        self.assertIn(
            "state.LoadDll == null || state.LoadDll.val",
            source,
        )
        self.assertIn("choiceToken", source)
        self.assertIn("choiceCount", source)
        self.assertIn("selectedIndex", source)
        self.assertIn("snapshot.PublishedIndices.Contains", source)
        self.assertIn("public List<string> ChoiceList;", source)
        self.assertIn(
            "object.ReferenceEquals(current.ChoiceList, currentChoices)",
            source,
        )
        self.assertIn("IsCurrentCuaChoiceSnapshot(", source)
        self.assertIn("BuildCuaGenerationKey(", source)
        self.assertIn("Guid.NewGuid().ToString(\"N\")", source)
        self.assertIn("object.ReferenceEquals(snapshot.Atom, target)", source)
        self.assertIn(
            "object.ReferenceEquals(snapshot.Loader, state.Loader)",
            source,
        )
        self.assertIn("SanitizeCuaChoiceLabel", source)
        self.assertIn("eligible.Count > 1", source)
        self.assertIn(
            "bundle is ready; choose one contained",
            source,
        )

        # loadDll must be the final mutation/check immediately before VaM's
        # assetUrl callback. NormalizePath and the None selection happen first.
        normalized = source.index(
            "normalizedUrl =",
            source.index("ExecuteLoadCustomUnityAsset"),
        )
        dll_off = source.index("state.LoadDll.val = false;", normalized)
        url_set = source.index("state.AssetUrl.val = normalizedUrl;", dll_off)
        safety_window = source[dll_off:url_set]
        self.assertIn("if (state.LoadDll.val)", safety_window)
        self.assertNotIn("NormalizePath", safety_window)
        self.assertNotIn("yield return", safety_window)
        self.assertNotIn('request["loadDll"]', source)
        self.assertNotIn('request["assetName"]', source)

        # The live roster publishes labels and indices, never the CUA URL.
        roster_start = source.index("private JSONClass BuildCuaStatus")
        roster_end = source.index(
            "private static JSONArray Capabilities",
            roster_start,
        )
        roster_source = source[roster_start:roster_end]
        self.assertIn('publishedChoice["index"]', roster_source)
        self.assertIn('publishedChoice["label"]', roster_source)
        self.assertNotIn('cua["assetUrl"]', roster_source)

        # Selected choice changes alone do not participate in token rotation.
        generation_start = source.index(
            "private static string BuildCuaGenerationKey"
        )
        generation_end = source.index(
            "private JSONClass BuildCuaStatus",
            generation_start,
        )
        generation_source = source[generation_start:generation_end]
        self.assertNotIn("selectedIndex", generation_source)
        self.assertNotIn("assetName.val", generation_source)
        self.assertNotIn("index < choices.Count", generation_source)
        self.assertIn("choices[originalIndex]", generation_source)


if __name__ == "__main__":
    unittest.main()

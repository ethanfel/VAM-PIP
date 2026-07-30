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
    request_sam3d_capture,
    request_subscene_load,
    request_timeline_control,
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

    def test_body_proportion_request_allows_one_atomic_sixteen_morph_fit(
        self,
    ) -> None:
        changes = [{"key": f"{index:032x}", "value": 0.1} for index in range(16)]
        request_person_body_proportions(
            self.vam_root,
            target_uid="Person",
            expected_revision="f" * 32,
            changes=changes,
        )
        self.assertEqual(len(self.read_request()["changes"]), 16)
        with self.assertRaisesRegex(ValueError, "between 1 and 16"):
            request_person_body_proportions(
                self.vam_root,
                target_uid="Person",
                expected_revision="f" * 32,
                changes=changes + [{"key": "f" * 32, "value": 0.1}],
            )

    def test_sam3d_capture_is_bound_to_the_exact_solution_file(self) -> None:
        request_id = request_sam3d_capture(
            self.vam_root,
            job_id="a" * 32,
            expected_revision="B" * 32,
            solution_sha256="C" * 64,
            camera_uid="SAM Camera",
        )
        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "captureSam3dResult")
        self.assertEqual(request["jobId"], "a" * 32)
        self.assertEqual(request["expectedRevision"], "b" * 32)
        self.assertEqual(request["solutionSha256"], "c" * 64)
        self.assertEqual(request["cameraUid"], "SAM Camera")
        with self.assertRaises(ValueError):
            request_sam3d_capture(
                self.vam_root,
                job_id="a" * 32,
                expected_revision="b" * 32,
                solution_sha256="not-a-digest",
                camera_uid="SAM Camera",
            )

    def test_timeline_control_uses_only_opaque_revision_bound_fields(self) -> None:
        request_id = request_timeline_control(
            self.vam_root,
            timeline_id="a" * 32,
            expected_revision="B" * 32,
            operation="selectClip",
            item_id="c" * 32,
        )

        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "controlTimeline")
        self.assertEqual(request["timelineId"], "a" * 32)
        self.assertEqual(request["expectedRevision"], "b" * 32)
        self.assertEqual(request["operation"], "selectClip")
        self.assertEqual(request["clipId"], "c" * 32)
        self.assertEqual(
            set(request) - {"protocol", "requestId", "createdAtUtc"},
            {
                "command",
                "timelineId",
                "expectedRevision",
                "operation",
                "clipId",
            },
        )
        serialized = json.dumps(request)
        self.assertNotIn("targetUid", serialized)
        self.assertNotIn("storable", serialized.casefold())
        self.assertNotIn("actionName", serialized)

    def test_timeline_setters_are_strictly_bounded(self) -> None:
        for operation, value in (
            ("setTime", 12.5),
            ("setSpeed", -0.5),
            ("setWeight", 0.75),
            ("setLocked", True),
        ):
            with self.subTest(operation=operation):
                request_timeline_control(
                    self.vam_root,
                    timeline_id="1" * 32,
                    expected_revision="2" * 32,
                    operation=operation,
                    value=value,
                )
                self.assertEqual(
                    self.read_request()["value"],
                    value,
                )

        invalid_cases = (
            ("setTime", -1),
            ("setTime", float("inf")),
            ("setSpeed", 6),
            ("setWeight", 1.1),
            ("setLocked", 1),
        )
        for operation, value in invalid_cases:
            with self.subTest(operation=operation, value=value):
                with self.assertRaises((TypeError, ValueError)):
                    request_timeline_control(
                        self.vam_root,
                        timeline_id="1" * 32,
                        expected_revision="2" * 32,
                        operation=operation,
                        value=value,
                    )

    def test_timeline_control_rejects_names_and_mismatched_fields(self) -> None:
        with self.assertRaises(ValueError):
            request_timeline_control(
                self.vam_root,
                timeline_id="Person",
                expected_revision="2" * 32,
                operation="play",
            )
        with self.assertRaises(ValueError):
            request_timeline_control(
                self.vam_root,
                timeline_id="1" * 32,
                expected_revision="2" * 32,
                operation="CallAction",
            )
        with self.assertRaises(ValueError):
            request_timeline_control(
                self.vam_root,
                timeline_id="1" * 32,
                expected_revision="2" * 32,
                operation="play",
                item_id="3" * 32,
            )

    def test_timeline_status_normalizes_vam_simplejson_scalars(self) -> None:
        directory = bridge_directory(self.vam_root)
        directory.mkdir(parents=True)
        (directory / "timeline.json").write_text(
            json.dumps(
                {
                    "protocol": "2",
                    "timelineProtocol": "1",
                    "loading": "false",
                    "truncated": "true",
                    "counts": {
                        "instances": "5",
                        "publishedInstances": "5",
                        "clips": "1280",
                        "publishedClips": "1024",
                    },
                    "limits": {
                        "maxInstances": "32",
                        "maxClips": "256",
                        "maxClipsGlobally": "1024",
                    },
                    "instances": [
                        {
                            "id": "1" * 32,
                            "revision": "2" * 32,
                            "enhanced": "true",
                            "ready": "true",
                            "selected": "false",
                            "playing": "true",
                            "stateSequence": "12",
                            "limits": {
                                "maxSegments": "64",
                                "maxLayers": "128",
                                "maxClips": "256",
                                "maxClipsGlobally": "1024",
                                "allocatedClips": "0",
                            },
                            "clips": [
                                {
                                    "id": "3" * 32,
                                    "selected": "true",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        document = read_timeline_status(self.vam_root)
        self.assertIsNotNone(document)
        assert document is not None
        self.assertIs(document["loading"], False)
        self.assertIs(document["truncated"], True)
        self.assertEqual(document["counts"]["publishedClips"], 1024)
        self.assertEqual(document["limits"]["maxClipsGlobally"], 1024)
        instance = document["instances"][0]
        self.assertIs(instance["enhanced"], True)
        self.assertEqual(instance["stateSequence"], 12)
        self.assertEqual(instance["limits"]["maxLayers"], 128)
        self.assertIs(instance["clips"][0]["selected"], True)

    def test_person_hair_request_writes_allowlisted_fields(self) -> None:
        resource_ref = (
            "Author.HairPack.7:/Custom/Atom/Person/Hair/Author/Long/Preset_Long.vap"
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
        local_ref = "Custom/Clothing/Female/Creator/Evening Dress/Evening Dress.vam"
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
            "Author.Menswear.3:/Custom/Clothing/Male/Author/Jacket/Jacket.VAM"
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

    def test_person_hair_request_uses_only_private_action_token(self) -> None:
        request_id = request_person_hair_item(
            self.vam_root,
            "Person #2",
            "1" * 32,
            active=False,
            revision="A2" * 16,
        )

        request = self.read_request()
        self.assertEqual(request["requestId"], request_id)
        self.assertEqual(request["command"], "setPersonHairItem")
        self.assertEqual(request["targetUid"], "Person #2")
        self.assertEqual(request["actionToken"], "1" * 32)
        self.assertEqual(request["revision"], "A2" * 16)
        self.assertEqual(request["desiredState"], "removed")
        self.assertEqual(
            set(request) - {"protocol", "requestId", "createdAtUtc"},
            {
                "command",
                "targetUid",
                "actionToken",
                "desiredState",
                "revision",
            },
        )
        serialized = json.dumps(request)
        self.assertNotIn("hairUid", serialized)
        self.assertNotIn("packageUid", serialized)
        self.assertNotIn("internalUid", serialized)
        self.assertNotIn("resourceRef", serialized)
        self.assertNotIn("Custom/", serialized)

    def test_person_hair_request_rejects_enable_and_invalid_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "only be removed"):
            request_person_hair_item(
                self.vam_root,
                "Person",
                "1" * 32,
                active=True,
                revision="2" * 32,
            )
        with self.assertRaises(TypeError):
            request_person_hair_item(
                self.vam_root,
                "Person",
                "1" * 32,
                active=0,  # type: ignore[arg-type]
                revision="2" * 32,
            )
        for token in ("", "1" * 31, "g" * 32, "1" * 33):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    request_person_hair_item(
                        self.vam_root,
                        "Person",
                        token,
                        active=False,
                        revision="2" * 32,
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
            "Author.WebTools.4:/Custom/Atom/WebBrowser/Author/Preset_Search.vap"
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

        package_ref = "Author.Rooms.2:/Custom/SubScene/Rooms/Apartment.JSON"
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
        local_ref = f"{CUSTOM_UNITY_ASSET_RESOURCE_PREFIX}Creator/Room.assetbundle"
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

        package_ref = "Author.Rooms.2:/Custom/Assets/Rooms/Apartment.SCENE"
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
            set(request) - {"protocol", "requestId", "createdAtUtc"},
            {"command", "targetUid", "choiceIndex", "choiceToken"},
        )

        for invalid_index in (True, 0, -1, 2_147_483_648, 1.5, "1"):
            with self.subTest(invalid_index=invalid_index):
                expected = (
                    TypeError if invalid_index in (True, 1.5, "1") else ValueError
                )
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
            ("Author.Scene.1:/Saves/scene/Other.Scene.2:/Saves/scene/Example.json"),
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
                                "activeCount": "1",
                                "lockedCount": "1",
                                "activeResourceRefs": [
                                    (
                                        "Author.Dress.1:/Custom/Clothing/"
                                        "Female/Author/Dress/Dress.vam"
                                    )
                                ],
                                "activeItems": [
                                    {
                                        "displayName": "Dress",
                                        "tags": ["Dresses"],
                                        "locked": "true",
                                    }
                                ],
                                "truncated": "false",
                            },
                            "hair": {
                                "ready": "true",
                                "revision": "3" * 32,
                                "activeCount": "1",
                                "lockedCount": "0",
                                "truncated": "false",
                                "items": [
                                    {
                                        "displayName": "Soft Bob",
                                        "tags": ["Sim"],
                                        "locked": "false",
                                        "simulated": "true",
                                    }
                                ],
                            },
                            "bodyProportions": {
                                "ready": "true",
                                "selectedOnly": "true",
                                "undoAvailable": "false",
                                "undoPending": "false",
                                "blockedBySam3d": "false",
                                "bodyShapeReady": "true",
                                "bodyShapePreparing": "false",
                                "morphs": [
                                    {
                                        "name": "Breasts Size",
                                        "builtIn": "true",
                                    }
                                ],
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
        self.assertEqual(clothing["activeCount"], 1)
        self.assertEqual(clothing["lockedCount"], 1)
        self.assertIs(clothing["activeItems"][0]["locked"], True)
        self.assertEqual(clothing["revision"], "2" * 32)
        hair = persons[0]["hair"]
        self.assertIs(hair["ready"], True)
        self.assertIs(hair["truncated"], False)
        self.assertEqual(hair["activeCount"], 1)
        self.assertEqual(hair["lockedCount"], 0)
        self.assertIs(hair["items"][0]["locked"], False)
        self.assertIs(hair["items"][0]["simulated"], True)
        body_proportions = persons[0]["bodyProportions"]
        self.assertIs(body_proportions["bodyShapeReady"], True)
        self.assertIs(body_proportions["bodyShapePreparing"], False)
        self.assertIs(body_proportions["undoPending"], False)
        self.assertIs(body_proportions["morphs"][0]["builtIn"], True)
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
        documented = (repository / "bridge" / "vam" / "VAMPipBridge.cs").read_bytes()
        self.assertEqual(packaged, documented)

    def test_packaged_and_documented_bridge_readmes_match(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        packaged = (
            repository / "src" / "vampip" / "bridge_assets" / "README.md"
        ).read_bytes()
        documented = (repository / "bridge" / "vam" / "README.md").read_bytes()
        self.assertEqual(packaged, documented)

    def test_bridge_source_has_narrow_protocol_two_surface(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")
        self.assertIn("ProtocolVersion = 2", source)
        self.assertIn('BridgeVersion = "1.0.0"', source)
        self.assertIn("TimelineProtocolVersion = 1", source)
        self.assertIn("MaximumTimelineClipsGlobally = 1024", source)
        self.assertIn("TimelinePublishIntervalSeconds = 1.0f", source)
        self.assertIn("List<TimelineCandidate> prioritized", source)
        self.assertIn("if (instanceClipBudget > 0)", source)
        self.assertIn('":published:" +', source)
        self.assertIn('"legacy:published:" + clipLimit', source)
        self.assertIn(
            "do not invoke the adapter's full catalog",
            source,
        )
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
        self.assertIn('"controlTimeline"', source)
        self.assertIn('"applySam3dResult"', source)
        self.assertIn('"undoSam3dResult"', source)
        self.assertIn('"captureSam3dResult"', source)
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
        self.assertIn('"timeline-roster"', source)
        self.assertIn('"timeline-transport"', source)
        self.assertIn('"timeline-animation-play"', source)
        self.assertIn('"timeline-adapter-v1"', source)
        self.assertIn('"sam3d-apply-v1"', source)
        self.assertIn('"sam3d-undo-v1"', source)
        self.assertIn('"sam3d-capture-v1"', source)
        self.assertIn('"sam3d-camera-vrfunscript-v1"', source)
        self.assertIn('"VAM-PIP External State"', source)
        self.assertIn('"VAM-PIP Execute External Command"', source)
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
        strict_create_block = source[strict_create_check:existing_type_check]
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

    def test_bridge_sam3d_surface_is_revision_bound_and_allowlisted(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        self.assertIn("Sam3dSolutionSchema = 1", source)
        self.assertIn("Sam3dControllerCount = 19", source)
        self.assertIn('"selected-person-hip-relative"', source)
        self.assertIn('Sam3dRoot + "\\\\" + request.Sam3dJobId + ".json"', source)
        self.assertIn("LoadSam3dSolution(request)", source)
        self.assertIn('request["solutionSha256"]', source)
        self.assertIn("Sha256Ascii(payload)", source)
        self.assertIn(
            "request.Sam3dSolutionSha256",
            source,
        )
        self.assertIn("IsSam3dControllerId", source)
        self.assertIn("MaximumSam3dCoordinate = 10.0f", source)
        self.assertIn("SnapshotSam3dState", source)
        self.assertIn("RestoreSam3dSnapshot", source)
        self.assertIn(
            "snapshot.CameraCreated =\n                    cameraResult.Created;",
            source,
        )
        self.assertIn("RemoveCreatedSam3dCamera(", source)
        self.assertIn(
            "SuperController.singleton.RemoveAtom(createdCamera);",
            source,
        )
        self.assertIn(
            "if (CurrentSam3dSnapshot() != null)",
            source,
        )
        self.assertIn(
            "!object.ReferenceEquals(camera, result.Atom)",
            source,
        )
        self.assertIn(
            "result.Atom = null;\n"
            "                    result.Created = false;\n"
            '                    return "";',
            source,
        )
        self.assertIn(
            '"Could not monitor the SAM3D capture: "',
            source,
        )
        self.assertIn(
            "if (status == null)",
            source,
        )
        self.assertIn(
            'rendererError == null\n                            ? ""',
            source,
        )
        self.assertIn(
            "The requested SAM3D pose and camera are not the "
            "currently applied in-memory result.",
            source,
        )
        self.assertIn(
            "object.ReferenceEquals(\n"
            "                        snapshot.Renderer,\n"
            "                        renderer)",
            source,
        )
        self.assertIn("CurrentSam3dSnapshot()", source)
        self.assertIn('scene["sam3d"] = sam3d', source)
        self.assertIn('Sam3dCaptureAction = "VAMPipCapture"', source)
        self.assertIn('"Saves/screenshots/VAMPip/"', source)
        self.assertIn('"Saves/VR_Videos_And_Funscripts/"', source)
        self.assertIn('SetSam3dChoice(renderer, "Camera Target", "None")', source)
        self.assertIn('SetSam3dChoice(renderer, "Render Mode", "Flat")', source)
        self.assertIn(
            '"Custom/Atom/Empty/Preset_VAMPipSAM3DCamera.vap"',
            source,
        )
        self.assertNotIn('request["controllerId"]', source)
        self.assertNotIn('request["actionName"]', source)
        self.assertNotIn('request["solutionPath"]', source)

    def test_bridge_body_proportions_are_tokenized_bounded_and_reversible(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        self.assertIn('"setPersonBodyProportions"', source)
        self.assertIn('"undoPersonBodyProportions"', source)
        self.assertIn("MaximumBodyProportionMorphs = 32", source)
        self.assertIn("MaximumBodyProportionChanges = 16", source)
        self.assertIn("MaximumBodyProportionDelta = 0.25f", source)
        self.assertIn('"person-body-proportions-v1"', source)
        self.assertIn('"person-body-shape-v1"', source)
        self.assertIn('result["undoRevision"]', source)
        self.assertIn(
            '"Undo the currently applied SAM3D pose before "',
            source,
        )

        apply_start = source.index("private static void SetBodyProportionMorphValue(")
        apply_end = source.index(
            "private IEnumerator ExecuteLoadScene(",
            apply_start,
        )
        apply_source = source[apply_start:apply_end]
        self.assertIn("morph.LoadDeltas();", apply_source)
        self.assertIn("morph.SetValueThreadSafe(value);", apply_source)
        self.assertIn("morph.SyncJSON();", apply_source)
        self.assertNotIn("morph.SetValue(value);", apply_source)
        self.assertLess(
            apply_source.index("morph.SetValueThreadSafe(value);"),
            apply_source.index("morph.SyncJSON();"),
        )
        self.assertIn("RestoreBodyProportionValues(", apply_source)
        self.assertIn("CurrentSam3dSnapshot() != null", apply_source)
        self.assertIn(
            "Restore it before applying another fit.",
            apply_source,
        )
        self.assertIn("undoBookkeepingChanged", apply_source)
        self.assertIn(
            "_personBodyProportionUndo[\n"
            "                            request.TargetUid] = priorUndo;",
            apply_source,
        )
        self.assertIn(
            "SuperController.singleton.ResetSimulation(",
            apply_source,
        )
        self.assertIn(
            '"Apply VAM-PIP body proportions"',
            apply_source,
        )
        self.assertIn(
            'newUndo.PostApplyGenerationKey = "";',
            apply_source,
        )
        self.assertIn(
            "newUndo.PendingStableObservations = 0;",
            apply_source,
        )
        self.assertIn(
            "newUndo.PreApplyGenerationKey =",
            apply_source,
        )
        self.assertIn(
            "newUndo.PreApplyBodyShapeChecksum =",
            apply_source,
        )
        self.assertIn(
            "newUndo.RequireBodyShapeReady =",
            apply_source,
        )
        self.assertNotIn(
            "TryBuildBodyShapeSignature(",
            apply_source,
        )
        readiness_guard = apply_source.index(
            "if (!IsValidBodyShapeSignature(\n"
            "                        snapshot.BodyShape))"
        )
        undo_branch = apply_source.index(
            "if (undo)",
            readiness_guard,
        )
        self.assertLess(readiness_guard, undo_branch)
        self.assertIn(
            '"preparation or inspect bodyShapeReason."',
            apply_source,
        )
        require_changed = apply_source.index(
            "newUndo.RequireChangedBodyShapeChecksum =\n"
            "                            true;",
            undo_branch,
        )
        saved_value = apply_source.index(
            "BodyProportionUndoValue old =",
            require_changed,
        )
        self.assertLess(require_changed, saved_value)

        catalog_start = source.index(
            "private static bool IsAllowlistedBodyProportionMorphName("
        )
        catalog_end = source.index(
            "private static string BuildPersonClothingGenerationKey(",
            catalog_start,
        )
        catalog_source = source[catalog_start:catalog_end]
        for rejection in (
            "morph.disable",
            "morph.isPoseControl",
            "morph.isDriven",
            "!morph.isLatestVersion",
            "morph.isInPackage",
            "morph.isRuntime",
            "morph.isTransient",
        ):
            self.assertIn(rejection, catalog_source)
        self.assertIn(
            "bank.GetBuiltInMorphByUid(morph.uid)",
            catalog_source,
        )
        self.assertIn(
            "HashBodyProportionBankState(",
            catalog_source,
        )
        self.assertIn(
            "morph.hasBoneModificationFormulas",
            catalog_source,
        )
        for shape_morph in (
            "Breasts Size",
            "ChestSeparateBreasts",
            "Waist Width",
            "Hip Size",
            "Glutes Size",
            "Thighs Size",
        ):
            self.assertIn(f'"{shape_morph}"', catalog_source)
        self.assertIn(
            'name != "ChestSeparateBreasts"',
            catalog_source,
        )
        self.assertIn(
            "IsBodyShapeCalibrationMorphName(entry.Name)",
            catalog_source,
        )
        self.assertIn("entry.FitKind =", catalog_source)
        self.assertIn('"structure"', catalog_source)
        self.assertIn('"shape"', catalog_source)
        self.assertIn('published["shapeRegion"]', catalog_source)
        self.assertIn('published["shapeResponses"]', catalog_source)
        self.assertIn("skin.dazMesh.morphedBaseVertices", catalog_source)
        self.assertIn("skin.dazMesh.baseTriangles", catalog_source)
        self.assertIn("DAZMorphVertex[] deltas", catalog_source)
        self.assertIn("delta.delta * step", catalog_source)
        self.assertIn("HashBodyShapeSignature(", catalog_source)
        self.assertIn("TryBodyShapeMeshChecksum(", catalog_source)
        self.assertIn("snapshot.BodyShapeMeshChecksum", catalog_source)
        self.assertIn(
            "undo.PendingStableObservations >= 2",
            catalog_source,
        )
        status_start = catalog_source.index(
            "private JSONClass BuildPersonBodyProportionStatus("
        )
        status_source = catalog_source[status_start:]
        self.assertIn(
            'result["bodyShapePreparing"].AsBool',
            status_source,
        )
        self.assertIn(
            "EnsurePersonBodyShapeBuild(",
            status_source,
        )
        self.assertIn(
            "CopyBodyShapeResponsesFromCache(",
            status_source,
        )
        self.assertNotIn(
            "TryBuildBodyShapeSignature(",
            status_source,
        )
        self.assertNotIn(
            "PopulateBodyShapeResponses(",
            status_source,
        )
        self.assertIn(
            "undo.RequireChangedBodyShapeChecksum",
            status_source,
        )
        self.assertIn(
            "undo.PreApplyBodyShapeChecksum",
            status_source,
        )
        self.assertIn(
            "undo.PreApplyGenerationKey",
            status_source,
        )
        self.assertIn(
            "undo.RequireBodyShapeReady",
            status_source,
        )
        self.assertIn(
            "waitingForChangedChecksum",
            status_source,
        )
        self.assertIn(
            "waitingForChangedGeneration",
            status_source,
        )
        coroutine_start = catalog_source.index(
            "private IEnumerator BuildPersonBodyShapeCacheCoroutine("
        )
        coroutine_end = catalog_source.index(
            "private void EnsurePersonBodyShapeBuild(",
            coroutine_start,
        )
        coroutine_source = catalog_source[coroutine_start:coroutine_end]
        self.assertIn(
            "BodyShapeBuildMaximumStepsPerFrame",
            coroutine_source,
        )
        self.assertIn("yield return null;", coroutine_source)
        self.assertIn(
            "BodyShapeBustFirstFraction = 0.58f",
            source,
        )
        self.assertIn(
            "BodyShapeBustLastFraction = 0.76f",
            source,
        )
        self.assertIn(
            "BodyShapeWaistFirstFraction = 0.34f",
            source,
        )
        self.assertIn(
            "BodyShapeSeatFirstFraction = -0.08f",
            source,
        )
        self.assertIn(
            "TryScanBodyShapeTorsoSection(",
            catalog_source,
        )
        for shape_measurement in (
            "bustGirth",
            "bustWidth",
            "bustDepth",
            "underbustGirth",
            "underbustWidth",
            "underbustDepth",
            "breastGirthExcess",
            "breastDepthExcess",
            "breastProjection",
            "waistGirth",
            "waistWidth",
            "waistDepth",
            "seatGirth",
            "seatWidth",
            "seatDepth",
            "gluteProjection",
            "upperThighGirth",
            "upperThighWidth",
            "upperThighDepth",
        ):
            self.assertIn(f'"{shape_measurement}"', catalog_source)
        for measurement in (
            "upperArm",
            "forearm",
            "thigh",
            "shin",
            "torso",
            "shoulderSpan",
            "hipSpan",
            "structuralHeight",
        ):
            self.assertIn(f'"{measurement}"', catalog_source)
        self.assertNotIn("morphedWorldPosition =", catalog_source)

    def test_bridge_sam3d_pose_changes_are_physics_safe_and_reversible(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")
        pose_start = source.index(
            "private static Sam3dUndoSnapshot SnapshotSam3dState("
        )
        pose_end = source.index(
            "private void FinishSam3dActionOk(",
            pose_start,
        )
        pose_source = source[pose_start:pose_end]
        apply_start = source.index("private IEnumerator ExecuteApplySam3dResult(")
        undo_end = source.index(
            "private static bool IsSafeSam3dOutput(",
            apply_start,
        )
        action_source = source[apply_start:undo_end]
        restore_start = pose_source.index(
            "private static bool RestoreSam3dSnapshotContents("
        )
        restore_end = pose_source.index(
            "private static void SnapSam3dControllerPhysicalPose(",
            restore_start,
        )
        restore_source = pose_source[restore_start:restore_end]
        snap_start = restore_end
        snap_end = pose_source.index(
            "private Sam3dUndoSnapshot CurrentSam3dSnapshot(",
            snap_start,
        )
        snap_source = pose_source[snap_start:snap_end]
        apply_contents_start = pose_source.index(
            "private static void ApplySam3dTransformContents("
        )
        apply_contents_end = len(pose_source)
        apply_contents_source = pose_source[apply_contents_start:apply_contents_end]
        lock_start = pose_source.index("private static void LockSam3dSavedPhysics(")
        lock_end = pose_source.index(
            "private static void CommitSam3dPoseLock(",
            lock_start,
        )
        lock_source = pose_source[lock_start:lock_end]
        commit_start = lock_end
        commit_end = pose_source.index(
            "private static void RestoreSam3dSavedPhysicsAndCollision(",
            commit_start,
        )
        commit_source = pose_source[commit_start:commit_end]
        begin_start = pose_source.index(
            "private static void BeginSam3dPoseTransaction("
        )
        begin_source = pose_source[begin_start:lock_start]
        full_lock_end = pose_source.index(
            "private static void ValidateSam3dSavedPhysics(",
            lock_start,
        )
        full_lock_source = pose_source[lock_start:full_lock_end]
        hold_start = pose_source.index(
            "private static bool IsSam3dPersistentHoldController("
        )
        reassert_start = pose_source.index(
            "private static void ReassertSam3dPersistentPoseLock(",
            hold_start,
        )
        hold_source = pose_source[hold_start:reassert_start]
        reassert_end = pose_source.index(
            "private static bool IsSam3dSavedPhysicalBodyAvailable(",
            reassert_start,
        )
        reassert_source = pose_source[reassert_start:reassert_end]
        finalize_start = pose_source.index(
            "private static void FinalizeSam3dPersistentHeadLock("
        )
        finalize_end = pose_source.index(
            "private static void ApplySam3dTransforms(",
            finalize_start,
        )
        finalize_source = pose_source[finalize_start:finalize_end]
        apply_wrapper_start = finalize_end
        apply_wrapper_end = pose_source.index(
            "private static void ApplySam3dTransformContents(",
            apply_wrapper_start,
        )
        apply_wrapper_source = pose_source[apply_wrapper_start:apply_wrapper_end]
        apply_action_end = action_source.index(
            "private IEnumerator ExecuteUndoSam3dResult("
        )
        apply_action_source = action_source[:apply_action_end]
        restore_physics_start = commit_end
        restore_physics_end = pose_source.index(
            "private static void FinishSam3dPoseTransaction(",
            restore_physics_start,
        )
        restore_physics_source = pose_source[restore_physics_start:restore_physics_end]

        self.assertIn("Sam3dPhysicsResetFrames = 5", source)
        self.assertIn("saved.Position = controller.control.position;", pose_source)
        self.assertIn("saved.Rotation = controller.control.rotation;", pose_source)
        self.assertIn("saved.PhysicsEnabled = controller.physicsEnabled;", pose_source)
        self.assertIn("saved.PhysicalBody = controller.followWhenOffRB;", pose_source)
        self.assertIn(
            "saved.PhysicalBodyWasPresent =\n"
            "                    !object.ReferenceEquals(",
            pose_source,
        )
        self.assertIn(
            "snapshot.CameraPhysicalBodyWasPresent =\n"
            "                !object.ReferenceEquals(",
            pose_source,
        )
        self.assertIn(
            "saved.PhysicalBodyKinematic =\n"
            "                        saved.PhysicalBody.isKinematic;",
            pose_source,
        )
        self.assertIn("snapshot.PersonCollisionEnabled", pose_source)
        self.assertIn(
            "snapshot.PersistentHeadLockActive = false;",
            pose_source,
        )
        self.assertIn("snapshot.Person.collisionEnabled = false;", pose_source)
        self.assertIn(
            "LockSam3dSavedPhysics(snapshot);",
            begin_source,
        )
        self.assertIn(
            "ValidateSam3dSavedPhysics(snapshot);",
            full_lock_source,
        )
        self.assertIn(
            "LockSam3dControllerPhysics(\n"
            "                    snapshot.Controllers[index]);",
            full_lock_source,
        )
        self.assertIn(
            "LockSam3dCameraPhysics(snapshot);",
            full_lock_source,
        )
        self.assertIn(
            "snapshot.Controllers.Count != Sam3dControllerCount",
            lock_source,
        )
        self.assertIn("saved.Controller.physicsEnabled = false;", lock_source)
        self.assertIn("saved.PhysicalBody.isKinematic = true;", lock_source)
        self.assertIn(
            "snapshot.CameraController.physicsEnabled = false;",
            lock_source,
        )
        self.assertIn(
            "snapshot.CameraPhysicalBody.isKinematic = true;",
            lock_source,
        )
        self.assertIn(
            "private static bool IsSam3dSavedPhysicalBodyAvailable(",
            lock_source,
        )
        self.assertIn(
            "return wasPresent\n"
            "                ? body != null\n"
            "                : object.ReferenceEquals(body, null);",
            lock_source,
        )
        self.assertGreaterEqual(
            lock_source.count("IsSam3dSavedPhysicalBodyAvailable("),
            3,
        )
        self.assertIn(
            "saved.Controller.physicsEnabled =\n"
            "                            saved.PhysicsEnabled;",
            restore_physics_source,
        )
        controller_restore_guard = (
            "saved.Controller == null ||\n"
            "                            !IsSam3dSavedPhysicalBodyAvailable(\n"
            "                                saved.PhysicalBodyWasPresent,\n"
            "                                saved.PhysicalBody) ||\n"
            "                            !object.ReferenceEquals(\n"
            "                                saved.Controller.followWhenOffRB,\n"
            "                                saved.PhysicalBody)"
        )
        self.assertIn(controller_restore_guard, restore_physics_source)
        self.assertLess(
            restore_physics_source.index(controller_restore_guard),
            restore_physics_source.index("saved.Controller.physicsEnabled ="),
        )
        self.assertIn(
            "saved.PhysicalBody.isKinematic =\n"
            "                                saved.PhysicalBodyKinematic;",
            restore_physics_source,
        )
        self.assertIn(
            "snapshot.CameraController.physicsEnabled =\n"
            "                        snapshot.CameraPhysicsEnabled;",
            restore_physics_source,
        )
        camera_restore_guard = (
            "cameraControllerAvailable &&\n"
            "                cameraPhysicalBodyAvailable &&\n"
            "                object.ReferenceEquals(\n"
            "                    snapshot.CameraController.followWhenOffRB,\n"
            "                    snapshot.CameraPhysicalBody)"
        )
        self.assertIn(camera_restore_guard, restore_physics_source)
        self.assertLess(
            restore_physics_source.index(camera_restore_guard),
            restore_physics_source.index("snapshot.CameraController.physicsEnabled ="),
        )
        self.assertIn(
            "snapshot.CameraPhysicalBody.isKinematic =\n"
            "                        snapshot.CameraPhysicalBodyKinematic;",
            restore_physics_source,
        )
        self.assertNotIn(
            "snapshot.CameraCreated",
            restore_physics_source,
        )
        self.assertIn(
            "else if (!cameraRemovedByUndo &&",
            restore_physics_source,
        )
        self.assertIn(
            "if (!cameraPhysicalBodyAvailable)\n"
            "                {\n"
            "                    if (!cameraRemovedByUndo)",
            restore_physics_source,
        )
        self.assertIn(
            "snapshot.Person.collisionEnabled =\n"
            "                    snapshot.PersonCollisionEnabled;",
            restore_physics_source,
        )
        self.assertIn(
            "snapshot.CameraController == null ||",
            pose_source[
                pose_source.index(
                    "private Sam3dUndoSnapshot CurrentSam3dSnapshot()"
                ) : pose_source.index(
                    "private void ReleaseSam3dPoseLockWithoutRestoringPose("
                )
            ],
        )
        self.assertIn("controller.control.position =", pose_source)
        self.assertIn("controller.control.rotation =", pose_source)
        self.assertNotIn("controller.transform.position =", pose_source)
        self.assertNotIn("controller.transform.rotation =", pose_source)
        self.assertIn("controller.onPositionChangeHandlers(controller);", pose_source)
        self.assertIn("controller.PauseComply();", pose_source)
        self.assertIn(
            "SnapSam3dControllerPhysicalPose(\n"
            "                    snapshot.Controllers[index].Controller);",
            restore_source,
        )
        self.assertLess(
            restore_source.index("saved.Controller.control.rotation = saved.Rotation;"),
            restore_source.index("SnapSam3dControllerPhysicalPose("),
        )
        self.assertIn(
            "Rigidbody physicalBody =\n                controller.followWhenOffRB;",
            snap_source,
        )
        self.assertIn(
            "physicalBody.position =\n                    controller.control.position;",
            snap_source,
        )
        self.assertIn(
            "physicalBody.rotation =\n                    controller.control.rotation;",
            snap_source,
        )
        self.assertIn("physicalBody.velocity = Vector3.zero;", snap_source)
        self.assertIn(
            "physicalBody.angularVelocity = Vector3.zero;",
            snap_source,
        )
        self.assertIn(
            "Transform physicalTransform =\n                controller.followWhenOff;",
            snap_source,
        )
        self.assertIn("snapshot.CameraController.followWhenOff.position", pose_source)
        self.assertLess(
            apply_contents_source.index(
                "controller.control.rotation = requestedRotation;"
            ),
            apply_contents_source.index("SnapSam3dControllerPhysicalPose(controller);"),
        )
        self.assertLess(
            apply_contents_source.index("SnapSam3dControllerPhysicalPose(controller);"),
            apply_contents_source.index(
                "FreeControllerV3 cameraController = camera.mainController;"
            ),
        )
        camera_start = apply_contents_source.index(
            "FreeControllerV3 cameraController = camera.mainController;"
        )
        camera_source = apply_contents_source[camera_start:]
        self.assertLess(
            camera_source.index("cameraController.control.rotation ="),
            camera_source.index("SnapSam3dControllerPhysicalPose(cameraController);"),
        )
        self.assertIn(
            "SuperController.singleton.ResetSimulation(",
            pose_source,
        )
        self.assertIn(
            "if (applied)\n"
            "                {\n"
            "                    CommitSam3dPoseLock(snapshot);",
            pose_source,
        )
        self.assertIn(
            "else\n                {\n                    FinishSam3dPoseTransaction(",
            pose_source,
        )
        self.assertNotIn("LockSam3dSavedPhysics(snapshot);", commit_source)
        self.assertIn(
            "RestoreSam3dControllerPhysics(saved);",
            commit_source,
        )
        self.assertNotIn(
            "IsSam3dPersistentHoldController(saved)",
            commit_source,
        )
        self.assertIn(
            "LockSam3dCameraPhysics(snapshot);",
            commit_source,
        )
        self.assertIn(
            "snapshot.Person.collisionEnabled =\n"
            "                        snapshot.PersonCollisionEnabled;",
            commit_source,
        )
        self.assertNotIn(
            "RestoreSam3dSavedPhysicsAndCollision(snapshot);",
            commit_source,
        )
        self.assertIn('return id == "headControl";', hold_source)
        self.assertNotIn("neckControl", hold_source)
        self.assertIn(
            "ValidateSam3dSavedPhysics(snapshot);",
            reassert_source,
        )
        self.assertIn(
            "snapshot.PersistentHeadLockActive &&\n"
            "                    IsSam3dPersistentHoldController(saved)",
            reassert_source,
        )
        self.assertIn(
            "LockSam3dControllerPhysics(saved);",
            reassert_source,
        )
        self.assertIn(
            "SnapSam3dControllerPhysicalPose(\n"
            "                        saved.Controller);",
            reassert_source,
        )
        self.assertIn(
            "LockSam3dCameraPhysics(snapshot);",
            reassert_source,
        )
        self.assertIn(
            "SnapSam3dControllerPhysicalPose(\n"
            "                snapshot.CameraController);",
            reassert_source,
        )
        self.assertIn(
            "CaptureSam3dRequestedHeadRotation(\n"
            "                    snapshot,\n"
            "                    controllers);",
            apply_wrapper_source,
        )
        self.assertLess(
            apply_wrapper_source.index("CaptureSam3dRequestedHeadRotation("),
            apply_wrapper_source.index("applied = true;"),
        )
        self.assertIn(
            "Vector3 settledPosition =\n                head.PhysicalBody.position;",
            finalize_source,
        )
        self.assertIn(
            "head.Controller.control.position =\n                settledPosition;",
            finalize_source,
        )
        self.assertIn(
            "head.Controller.control.rotation =\n"
            "                snapshot.HeadRequestedRotation;",
            finalize_source,
        )
        self.assertIn(
            "RecordSam3dRequestedTransform(\n"
            "                snapshot.Diagnostics,\n"
            '                "headControl",\n'
            "                settledPosition,\n"
            "                snapshot.HeadRequestedRotation);",
            finalize_source,
        )
        self.assertIn(
            "snapshot.PersistentHeadLockActive = true;",
            finalize_source,
        )
        self.assertNotIn("neckControl", finalize_source)
        self.assertLess(
            finalize_source.index("LockSam3dControllerPhysics(head);"),
            finalize_source.index("SnapSam3dControllerPhysicalPose("),
        )
        self.assertLess(
            finalize_source.index("SnapSam3dControllerPhysicalPose("),
            finalize_source.index("snapshot.PersistentHeadLockActive = true;"),
        )
        self.assertIn("RestoreSam3dSnapshot(snapshot);", action_source)
        self.assertIn(
            "bool cameraRemovedByUndo = false;",
            pose_source,
        )
        self.assertIn(
            "cameraRemovedByUndo =\n"
            "                    RestoreSam3dSnapshotContents(snapshot);",
            pose_source,
        )
        self.assertIn(
            '"Restore VAM-PIP SAM3D pose",\n                    cameraRemovedByUndo);',
            pose_source,
        )
        self.assertIn(
            "SuperController.singleton.RemoveAtom(createdCamera);\n"
            "                return true;",
            restore_source,
        )
        self.assertIn("return false;", restore_source)
        track_request = "_inFlightSam3dCameraRequest = request;"
        track_result = "_inFlightSam3dCameraResult = cameraResult;"
        ensure_camera = "yield return EnsureSam3dCamera(request, cameraResult);"
        self.assertIn(track_request, action_source)
        self.assertIn(track_result, action_source)
        self.assertLess(
            action_source.index(track_request),
            action_source.index(ensure_camera),
        )
        self.assertLess(
            action_source.index(track_result),
            action_source.index(ensure_camera),
        )
        self.assertGreaterEqual(
            action_source.count("ClearInFlightSam3dCamera("),
            3,
        )
        self.assertEqual(
            apply_action_source.count("yield return WaitForSam3dPhysicsSettlement();"),
            2,
        )
        self.assertIn(
            "private IEnumerator ExecuteUndoSam3dResult(",
            action_source,
        )
        self.assertIn(
            "CaptureSam3dSettledDiagnostics(",
            action_source,
        )
        first_settlement = apply_action_source.index(
            "yield return WaitForSam3dPhysicsSettlement();"
        )
        finalize_call = apply_action_source.index(
            "FinalizeSam3dPersistentHeadLock(snapshot);"
        )
        second_settlement = apply_action_source.index(
            "yield return WaitForSam3dPhysicsSettlement();",
            first_settlement + 1,
        )
        diagnostics_capture = apply_action_source.index(
            "CaptureSam3dSettledDiagnostics("
        )
        self.assertLess(
            apply_action_source.index("_sam3dUndoSnapshot = snapshot;"),
            first_settlement,
        )
        self.assertLess(first_settlement, finalize_call)
        self.assertLess(finalize_call, second_settlement)
        self.assertLess(second_settlement, diagnostics_capture)
        rollback_start = apply_action_source.index(
            "Could not finalize the settled SAM3D head rotation:"
        )
        rollback_source = apply_action_source[rollback_start:second_settlement]
        self.assertIn(
            "RestoreSam3dSnapshot(snapshot);",
            rollback_source,
        )
        self.assertLess(
            rollback_source.index("RestoreSam3dSnapshot(snapshot);"),
            rollback_source.index("_sam3dUndoSnapshot = null;"),
        )

    def test_bridge_sam3d_pose_lock_lifecycle_cleanup_is_no_pose_and_idempotent(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        disable = source[
            source.index("private void OnDisable()") : source.index(
                "private void OnDestroy()"
            )
        ]
        stop_start = source.index("private void StopBridgeWorkForLifecycle(")
        destroy = source[source.index("private void OnDestroy()") : stop_start]
        stop = source[stop_start : source.index("private void Update()", stop_start)]
        release_start = source.index(
            "private void ReleaseSam3dPoseLockWithoutRestoringPose("
        )
        release_end = source.index(
            "private static Sam3dApplyDiagnostics",
            release_start,
        )
        release = source[release_start:release_end]
        current_start = source.index("private Sam3dUndoSnapshot CurrentSam3dSnapshot()")
        current = source[current_start:release_start]

        for lifecycle in (disable, destroy):
            self.assertIn(
                "StopBridgeWorkForLifecycle(",
                lifecycle,
            )
        self.assertNotIn("_operational = false;", disable)
        self.assertIn("_operational = false;", destroy)
        self.assertNotIn("_operational = false;", stop)
        self.assertIn("StopAllCoroutines();", stop)
        self.assertIn("_requestInProgress = false;", stop)
        self.assertIn("_pendingRequest = null;", stop)
        self.assertIn("_skipPendingProcessing = false;", stop)
        self.assertIn('_mailboxRejectedRequestId = "";', stop)
        self.assertIn('_mailboxRejectedMessage = "";', stop)
        self.assertIn(
            "RemoveInFlightCreatedSam3dCamera();",
            stop,
        )
        self.assertIn(
            "ReleaseSam3dPoseLockWithoutRestoringPose(",
            stop,
        )
        self.assertIn("RecordSam3dAction(", stop)
        self.assertIn("FailRequest(", stop)
        self.assertLess(
            stop.index("StopAllCoroutines();"),
            stop.index("_requestInProgress = false;"),
        )
        self.assertLess(
            stop.index("_requestInProgress = false;"),
            stop.index("RemoveInFlightCreatedSam3dCamera();"),
        )
        self.assertLess(
            stop.index("RemoveInFlightCreatedSam3dCamera();"),
            stop.index("ReleaseSam3dPoseLockWithoutRestoringPose("),
        )
        self.assertLess(
            stop.index("ReleaseSam3dPoseLockWithoutRestoringPose("),
            stop.index("FailRequest("),
        )
        self.assertIn("_sam3dUndoSnapshot = null;", release)
        self.assertIn(
            "RestoreSam3dSavedPhysicsAndCollision(\n"
            "                    snapshot,\n"
            "                    false);",
            release,
        )
        self.assertNotIn("RestoreSam3dSnapshot(", release)
        self.assertNotIn("RestoreSam3dSnapshotContents(", release)
        self.assertNotIn(".control.position", release)
        self.assertNotIn(".control.rotation", release)
        self.assertNotIn("ResetSimulation(", release)
        self.assertGreaterEqual(
            current.count("ReleaseSam3dPoseLockWithoutRestoringPose("),
            5,
        )
        self.assertIn(
            "ReassertSam3dPersistentPoseLock(snapshot);",
            current,
        )
        self.assertIn(
            "_inFlightSam3dCameraRequest = null;",
            stop,
        )
        self.assertIn(
            "_inFlightSam3dCameraResult = null;",
            stop,
        )
        self.assertIn("!result.Created", stop)
        self.assertIn(
            "return RemoveCreatedSam3dCamera(request, result);",
            stop,
        )
        self.assertIn(
            "object.ReferenceEquals(\n"
            "                    _inFlightSam3dCameraRequest,\n"
            "                    request)",
            stop,
        )
        self.assertIn(
            "!object.ReferenceEquals(result.Atom, null)",
            source,
        )

    def test_bridge_sam3d_settlement_diagnostics_are_fixed_and_bounded(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        self.assertIn("Sam3dDiagnosticControllerCount = 2", source)
        self.assertIn('head.Id = "headControl";', source)
        self.assertIn('neck.Id = "neckControl";', source)
        self.assertIn(
            "snapshot.Diagnostics =\n"
            "                    NewSam3dApplyDiagnostics(request);",
            source,
        )
        self.assertIn(
            "liveSam3dSnapshot.Diagnostics",
            source,
        )
        self.assertIn('sam3d["settlement"] = settlement;', source)
        self.assertIn(
            "Rigidbody physicalBody =\n                    controller.followWhenOffRB;",
            source,
        )
        self.assertIn(
            "item.ActualPosition =\n                        physicalBody.position;",
            source,
        )
        self.assertIn(
            "item.ActualRotation =\n                        physicalBody.rotation;",
            source,
        )
        self.assertIn(
            "Transform physicalTransform =\n"
            "                    controller.followWhenOff;",
            source,
        )
        for direct_flag in (
            "controller.physicsEnabled",
            "controller.possessed",
            "controller.startedPossess",
            "controller.isGrabbing",
        ):
            self.assertIn(direct_flag, source)
        self.assertIn(
            'controller["positionErrorMeters"].AsFloat',
            source,
        )
        self.assertIn(
            'controller["rotationErrorDegrees"].AsFloat',
            source,
        )
        self.assertNotIn("System.Reflection", source)

    def test_sam3d_camera_presets_match_and_use_vendored_renderer(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        packaged = (
            repository
            / "src"
            / "vampip"
            / "bridge_assets"
            / "Preset_VAMPipSAM3DCamera.vap"
        )
        documented = repository / "bridge" / "vam" / "Preset_VAMPipSAM3DCamera.vap"
        self.assertEqual(packaged.read_bytes(), documented.read_bytes())
        preset = json.loads(packaged.read_text(encoding="utf-8"))
        plugin = preset["storables"][0]["plugins"]["plugin#0"]
        self.assertEqual(
            plugin,
            "Custom/Scripts/VAMPip/VRRendererX/Eosin_VRRenderer.cslist",
        )
        settings = preset["storables"][1]
        self.assertEqual(settings["Render Mode"], "Flat")
        self.assertEqual(settings["Camera Target"], "None")
        self.assertEqual(settings["Generate Funscripts"], "false")

    def test_bridge_source_has_bounded_clothing_and_hair_rosters(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

        self.assertIn("MaximumClothingRefsPerPerson = 256", source)
        self.assertIn("MaximumClothingRefsGlobally = 1024", source)
        self.assertIn("MaximumHairItemsPerPerson = 128", source)
        self.assertIn("MaximumHairItemsGlobally = 512", source)
        self.assertIn("MaximumRosterDisplayNameLength = 256", source)
        self.assertIn("MaximumRosterTagsPerItem = 32", source)
        self.assertIn("SanitizeRosterText", source)
        self.assertIn("SanitizeRosterTags", source)
        self.assertIn("item.displayName", source)
        self.assertIn("item.tagsArray", source)
        self.assertIn('clothing["activeItems"]', source)
        self.assertIn(
            "atom.GetComponentsInChildren<DAZHairGroup>()",
            source,
        )
        self.assertNotIn("DAZHairGroup[] items = geometry.hairItems", source)
        self.assertIn("!item.active", source)
        self.assertIn(
            "item.GetComponentInChildren<HairSimControl>() != null",
            source,
        )
        self.assertIn('"person-hair-roster"', source)
        self.assertIn('"person-hair-item-toggle"', source)
        self.assertIn('"setPersonHairItem"', source)
        self.assertIn("ValidatePersonHairRequest", source)
        self.assertIn(
            'desiredState != "removed"',
            source,
        )
        self.assertIn("snapshot.ActionTokens", source)
        self.assertIn("snapshot.PublishedCount", source)
        self.assertIn(
            "snapshot.PublishedCount != publishableCount",
            source,
        )
        self.assertIn(
            "object.ReferenceEquals(\n"
            "                            snapshot.Items[identityIndex]",
            source,
        )
        self.assertIn(
            "geometry.SetActiveHairItem(\n"
            "                    selected.Item,\n"
            "                    false,\n"
            "                    false,\n"
            "                    false);",
            source,
        )
        self.assertNotIn("selected.Item.active = false", source)

        clothing_key_start = source.index(
            "private static string BuildPersonClothingGenerationKey"
        )
        clothing_key_end = source.index(
            "private JSONClass BuildPersonClothingStatus",
            clothing_key_start,
        )
        clothing_key = source[clothing_key_start:clothing_key_end]
        self.assertIn("entry.DisplayName", clothing_key)
        self.assertIn("entry.Tags[tagIndex]", clothing_key)

        hair_status_start = source.index("private JSONClass BuildPersonHairStatus")
        hair_status_end = source.index(
            "private JSONClass BuildCuaStatus",
            hair_status_start,
        )
        hair_status = source[hair_status_start:hair_status_end]
        self.assertIn('publishedItem["displayName"]', hair_status)
        self.assertIn('publishedItem["tags"]', hair_status)
        self.assertIn('publishedItem["locked"]', hair_status)
        self.assertIn('publishedItem["simulated"]', hair_status)
        self.assertIn('publishedItem["actionToken"]', hair_status)
        for private_identity in (
            "resourceRef",
            "ResourceRef",
            "PackageUid",
            "InternalUid",
            ".Uid",
        ):
            self.assertNotIn(private_identity, hair_status)

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
        self.assertIn('Guid.NewGuid().ToString("N")', source)
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
        generation_start = source.index("private static string BuildCuaGenerationKey")
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

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from vampip.bridge import (
    PERSON_PRESET_PREFIXES,
    bridge_directory,
    read_bridge_request,
    read_bridge_status,
    read_scene_status,
    request_add_person,
    request_person_preset,
    request_rescan,
    request_scene_load,
    request_select_atom,
    request_select_person,
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
                    ],
                    "persons": [
                        {"uid": "Person", "selected": "true"},
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
        atoms = scene["atoms"]
        assert isinstance(atoms, list)
        self.assertIs(atoms[0]["selected"], True)
        self.assertIs(atoms[1]["selected"], False)

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

    def test_bridge_source_has_narrow_protocol_two_surface(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source = (
            repository / "src" / "vampip" / "bridge_assets" / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")
        self.assertIn("ProtocolVersion = 2", source)
        self.assertIn('BridgeVersion = "0.3.0"', source)
        self.assertIn('"applyPersonPreset"', source)
        self.assertIn('"loadScene"', source)
        self.assertIn('"selectAtom"', source)
        self.assertIn('"atom-roster"', source)
        self.assertIn('"atom-select"', source)
        self.assertIn('"scene-load"', source)
        self.assertIn('"person-roster"', source)
        self.assertIn('"person-preset-apply"', source)
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
        self.assertIn('AddAtomByType(\n                            "Person"', source)
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


if __name__ == "__main__":
    unittest.main()

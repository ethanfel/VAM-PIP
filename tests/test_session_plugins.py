from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from vampip.session_plugins import (
    SessionPluginPresetError,
    inspect_session_plugin_defaults,
    parse_session_plugin_preset,
)


class ParseSessionPluginPresetTests(unittest.TestCase):
    def parse(self, document: object):
        return parse_session_plugin_preset(
            json.dumps(document).encode("utf-8"),
            path="Plugins_UserDefaults.vap",
        )

    def test_maps_slots_states_packaged_and_loose_sources(self) -> None:
        preset = self.parse(
            {
                "storables": [
                    {
                        "id": "plugin#2_SecondPlugin",
                        "enabled": False,
                    },
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#2": (
                                "Creator.Second.12:/Custom/Scripts/"
                                "Second/Second.cslist"
                            ),
                            "plugin#0": "Custom/Scripts/Local/Local.cs",
                            "plugin#7": (
                                "Creator.Default.latest:\\Custom\\Scripts\\"
                                "Default.cs"
                            ),
                        },
                    },
                    {
                        "id": "plugin#0_LocalPlugin",
                        "enabled": "TRUE",
                    },
                ]
            }
        )

        self.assertTrue(preset.exists)
        self.assertEqual(
            [plugin.slot for plugin in preset.plugins],
            ["plugin#2", "plugin#0", "plugin#7"],
        )

        packaged = preset.plugins[0]
        self.assertEqual(packaged.slot_index, 2)
        self.assertEqual(packaged.package_ref, "Creator.Second.12")
        self.assertEqual(
            packaged.source_path,
            "/Custom/Scripts/Second/Second.cslist",
        )
        self.assertFalse(packaged.enabled)
        self.assertTrue(packaged.packaged)
        self.assertFalse(packaged.loose)

        loose = preset.plugins[1]
        self.assertEqual(loose.source_path, "Custom/Scripts/Local/Local.cs")
        self.assertIsNone(loose.package_ref)
        self.assertTrue(loose.enabled)
        self.assertFalse(loose.packaged)
        self.assertTrue(loose.loose)

        defaults_enabled = preset.plugins[2]
        self.assertTrue(defaults_enabled.enabled)
        self.assertEqual(
            defaults_enabled.package_ref,
            "Creator.Default.latest",
        )
        self.assertEqual(
            defaults_enabled.source_path,
            "\\Custom\\Scripts\\Default.cs",
        )

    def test_defaults_enabled_when_storable_or_enabled_field_is_absent(
        self,
    ) -> None:
        preset = self.parse(
            {
                "storables": [
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#1": "A.One.1:/Custom/Scripts/One.cs",
                            "plugin#2": "A.Two.2:/Custom/Scripts/Two.cs",
                        },
                    },
                    {"id": "plugin#1_One"},
                ]
            }
        )
        self.assertEqual(
            [plugin.enabled for plugin in preset.plugins],
            [True, True],
        )

    def test_accepts_boolean_and_case_insensitive_string_states(self) -> None:
        preset = self.parse(
            {
                "storables": [
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#0": "A.Zero.1:/zero.cs",
                            "plugin#1": "A.One.1:/one.cs",
                            "plugin#2": "A.Two.1:/two.cs",
                            "plugin#3": "A.Three.1:/three.cs",
                        },
                    },
                    {"id": "plugin#0_Zero", "enabled": True},
                    {"id": "plugin#1_One", "enabled": False},
                    {"id": "plugin#2_Two", "enabled": " true "},
                    {"id": "plugin#3_Three", "enabled": "False"},
                ]
            }
        )
        self.assertEqual(
            [plugin.enabled for plugin in preset.plugins],
            [True, False, True, False],
        )

    def test_deduplicates_package_roots_case_insensitively_in_order(
        self,
    ) -> None:
        preset = self.parse(
            {
                "storables": [
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#3": "Beta.Tool.2:/three.cs",
                            "plugin#1": "Creator.Tool.12:/one.cs",
                            "plugin#2": "creator.tool.12:/two.cs",
                            "plugin#9": "Gamma.Off.4:/off.cs",
                        },
                    },
                    {"id": "plugin#9_Off", "enabled": "false"},
                ]
            }
        )
        self.assertEqual(
            preset.package_roots,
            ("Beta.Tool.2", "Creator.Tool.12", "Gamma.Off.4"),
        )
        self.assertEqual(
            preset.enabled_package_roots,
            ("Beta.Tool.2", "Creator.Tool.12"),
        )
        self.assertEqual(
            [plugin.package_ref for plugin in preset.enabled_plugins],
            ["Beta.Tool.2", "Creator.Tool.12", "creator.tool.12"],
        )

    def test_no_plugin_manager_is_a_valid_empty_preset(self) -> None:
        preset = self.parse({"storables": [{"id": "CoreControl"}]})
        self.assertEqual(preset.plugins, ())
        self.assertEqual(preset.package_roots, ())

    def test_skips_empty_vam_plugin_slots_and_their_storable_state(self) -> None:
        preset = self.parse(
            {
                "storables": [
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#0": "Creator.Live.1:/live.cs",
                            "plugin#3": "",
                        },
                    },
                    {"id": "plugin#3_Removed", "enabled": False},
                ]
            }
        )

        self.assertEqual(
            [plugin.package_ref for plugin in preset.plugins],
            ["Creator.Live.1"],
        )
        self.assertEqual(preset.package_roots, ("Creator.Live.1",))

    def test_utf8_bom_is_accepted(self) -> None:
        preset = parse_session_plugin_preset(
            b'\xef\xbb\xbf{"storables":[]}',
            path="preset.vap",
        )
        self.assertEqual(preset.plugins, ())

    def test_rejects_invalid_json_and_duplicate_json_keys(self) -> None:
        for data in (
            b"{not JSON",
            b'{"storables": [], "storables": []}',
            b"\xff",
        ):
            with self.subTest(data=data):
                with self.assertRaises(SessionPluginPresetError):
                    parse_session_plugin_preset(data, path="bad.vap")

    def test_rejects_malformed_top_level_and_storables(self) -> None:
        malformed = (
            [],
            {},
            {"storables": {}},
            {"storables": [None]},
            {"storables": [{}]},
            {"storables": [{"id": 3}]},
            {
                "storables": [
                    {"id": "PluginManager", "plugins": {}},
                    {"id": "PluginManager", "plugins": {}},
                ]
            },
        )
        for document in malformed:
            with self.subTest(document=document):
                with self.assertRaises(SessionPluginPresetError):
                    self.parse(document)

    def test_rejects_malformed_plugin_mapping(self) -> None:
        malformed_plugins = (
            None,
            [],
            {"wrong-slot": "Creator.Tool.1:/plugin.cs"},
            {"plugin#x": "Creator.Tool.1:/plugin.cs"},
            {"plugin#1": None},
            {"plugin#1": " padded.cs "},
            {"plugin#1": "Not.A.Package:/plugin.cs"},
            {"plugin#1": "Not.A.Package:plugin.cs"},
            {
                "plugin#1": "Creator.Tool.1:/one.cs",
                "plugin#01": "Creator.Other.1:/two.cs",
            },
        )
        for plugins in malformed_plugins:
            with self.subTest(plugins=plugins):
                with self.assertRaises(SessionPluginPresetError):
                    self.parse(
                        {
                            "storables": [
                                {
                                    "id": "PluginManager",
                                    "plugins": plugins,
                                }
                            ]
                        }
                    )

    def test_rejects_invalid_or_ambiguous_enabled_states(self) -> None:
        invalid_states = (1, 0, None, "yes", "", [], {})
        for enabled in invalid_states:
            with self.subTest(enabled=enabled):
                with self.assertRaises(SessionPluginPresetError):
                    self.parse(
                        {
                            "storables": [
                                {
                                    "id": "PluginManager",
                                    "plugins": {
                                        "plugin#1": "Creator.Tool.1:/tool.cs"
                                    },
                                },
                                {
                                    "id": "plugin#1_Tool",
                                    "enabled": enabled,
                                },
                            ]
                        }
                    )

        with self.assertRaises(SessionPluginPresetError):
            self.parse(
                {
                    "storables": [
                        {
                            "id": "PluginManager",
                            "plugins": {
                                "plugin#1": "Creator.Tool.1:/tool.cs"
                            },
                        },
                        {"id": "plugin#1_First", "enabled": True},
                        {"id": "plugin#1_Second", "enabled": True},
                    ]
                }
            )


class InspectSessionPluginDefaultsTests(unittest.TestCase):
    def test_missing_preset_is_a_non_error_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_session_plugin_defaults(directory)

        self.assertFalse(result.exists)
        self.assertEqual(result.plugins, ())
        self.assertEqual(result.package_roots, ())
        self.assertEqual(result.enabled_package_roots, ())
        self.assertEqual(
            result.path,
            Path(directory)
            / "Custom/PluginPresets/Plugins_UserDefaults.vap",
        )

    def test_reads_expected_file_below_vam_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset_path = (
                root / "Custom/PluginPresets/Plugins_UserDefaults.vap"
            )
            preset_path.parent.mkdir(parents=True)
            preset_path.write_text(
                json.dumps(
                    {
                        "storables": [
                            {
                                "id": "PluginManager",
                                "plugins": {
                                    "plugin#4": (
                                        "Creator.Plugin.9:/Custom/Scripts/"
                                        "Plugin.cs"
                                    )
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = inspect_session_plugin_defaults(root)

        self.assertTrue(result.exists)
        self.assertEqual(result.enabled_package_roots, ("Creator.Plugin.9",))

    def test_read_is_bounded_by_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preset_path = root / "defaults.vap"
            preset_path.write_bytes(b"{}" * 10)
            with self.assertRaisesRegex(
                SessionPluginPresetError,
                "safety limit",
            ):
                inspect_session_plugin_defaults(
                    root,
                    preset_path="defaults.vap",
                    maximum_bytes=8,
                )


if __name__ == "__main__":
    unittest.main()

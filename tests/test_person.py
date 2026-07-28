from __future__ import annotations

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
from vampip.service import LiveActionBusyError, ManagerService


HAIR_MEMBER = "Custom/Atom/Person/Hair/Example/Preset_Soft Bob.vap"
SCENE_MEMBER = "Saves/scene/Example Scene.json"
EMPTY_PRESET_MEMBER = "Custom/Atom/Empty/Example/Preset_Empty.vap"
SUBSCENE_MEMBER = "Custom/SubScene/Example/Room.json"
UNSUPPORTED_ATOM_PRESET_MEMBER = (
    "Custom/Atom/PackageDefinedWidget/Preset_Unsafe.vap"
)
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
        self.assertTrue(all(not call.kwargs["rescan"] for call in request.call_args_list))

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

    def test_already_active_and_local_presets_skip_composite_rescan(self) -> None:
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
        self.assertFalse(active["rescan"])
        self.assertFalse(request.call_args.kwargs["rescan"])

        # A loose preset has no package visibility state to refresh at all.
        local_member = (
            "Custom/Atom/Person/Hair/Local/Preset_Local Hair.vap"
        )
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
                side_effect=("empty-request", "subscene-request"),
            ) as request,
        ):
            existing = self.service.add_atom(empty_category, "Empty Target")
            created = self.service.add_atom(empty_category, "New Empty")
            subscene = self.service.add_atom("subscenes", "New SubScene")
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
                results["second"] = second_service._queue_bridge_request(
                    second_writer
                )
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

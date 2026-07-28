from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

from vampip.catalog import import_browserassist, search_resources
from vampip.database import connect
from vampip.inventory import scan
from vampip.references import scan_package_references
from vampip.service import ManagerService

from tests.test_vampip import make_var


class ReferenceTests(unittest.TestCase):
    @staticmethod
    def insert_local_scene(
        connection: sqlite3.Connection,
        vam_root: Path,
        resource_path: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO catalog_resources (
                root, source, resource_key, creator, package_name,
                versions_json, resource_path, resource_type, atom_type,
                favorite, hidden, tags_json, imported_utc
            ) VALUES (?, 'browserassist', ?, '', '', '[]', ?, 'Scene', '',
                      0, 0, '[]', '2026-01-01T00:00:00+00:00')
            """,
            (
                str(vam_root),
                f"local-scene:{resource_path}",
                resource_path.replace("/", "\\"),
            ),
        )
        return int(cursor.lastrowid)

    def test_stream_scanner_finds_exact_and_latest_virtual_paths(self) -> None:
        payload = (
            b'{"a":"Creator.Package.12:/Saves/file.json",'
            b'"b":"Other.Asset.latest:\\\\Custom\\\\thing.vap"}'
        )
        self.assertEqual(
            scan_package_references(BytesIO(payload)),
            {"Creator.Package.12", "Other.Asset.latest"},
        )

    def test_resource_lease_includes_undeclared_scene_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            vam_root = base / "VaM"
            addons = vam_root / "AddonPackages"
            state = base / "state"
            addons.mkdir(parents=True)
            make_var(addons / "Core.Base.1.var", creator="Core", package="Base")
            make_var(
                addons / "Asset.Extra.2.var",
                creator="Asset",
                package="Extra",
            )
            scene_path = addons / "Scene.Demo.1.var"
            metadata = {
                "creatorName": "Scene",
                "packageName": "Demo",
                "dependencies": {},
            }
            with zipfile.ZipFile(
                scene_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("meta.json", json.dumps(metadata))
                archive.writestr(
                    "Saves/scene/Demo.json",
                    '{"asset":"Asset.Extra.2:/Custom/data.vam"}',
                )

            browserassist = (
                vam_root / "Saves" / "PluginData" / "JayJayWon" / "BrowserAssist"
            )
            core_file = (
                browserassist / "VARResourcesCoreData" / "VARResourcesData1.manifest"
            )
            core_file.parent.mkdir(parents=True)
            core_file.write_text(
                json.dumps(
                    {
                        "VARManifestStoreFormat": "3",
                        "resources": [
                            {
                                "creatorName": "Scene",
                                "packageName": "Demo",
                                "resourceFullFileName": "Saves\\scene\\Demo.json",
                                "resourceType": "Scene",
                                "presetAtomType": "",
                                "varVersions": ["1"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            service = ManagerService(
                addons,
                state,
                process_probe=lambda: [],
            )
            with connect(state) as connection:
                scan(addons, connection)
                import_browserassist(connection, vam_root)
                resource_id = search_resources(connection, vam_root)["items"][0]["id"]
            service.pin(["Core.Base"])
            service.reconcile(apply=True, activate=True)
            result = service.lease_resource(resource_id, apply=True)
            self.assertEqual(
                set(result["discovered_roots"]),
                {"Scene.Demo.1", "Asset.Extra.2"},
            )
            active = service.list_packages(state="active")["items"]
            self.assertEqual(
                {item["id"] for item in active},
                {"Core.Base.1", "Scene.Demo.1", "Asset.Extra.2"},
            )

    def test_local_scene_apply_enables_embedded_packages_before_bridge_load(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            vam_root = base / "VaM"
            addons = vam_root / "AddonPackages"
            state = base / "state"
            addons.mkdir(parents=True)
            make_var(addons / "Core.Base.1.var", creator="Core", package="Base")
            dependency = addons / "Asset.Extra.2.var"
            make_var(dependency, creator="Asset", package="Extra")
            hidden_dependency = Path(f"{dependency}.vampip-disabled")
            dependency.rename(hidden_dependency)

            resource_path = "Saves/scene/Local.json"
            scene_path = vam_root / resource_path
            scene_path.parent.mkdir(parents=True)
            scene_path.write_text(
                '{"asset":"Asset.Extra.2:/Custom/data.vam"}',
                encoding="utf-8",
            )
            with connect(state) as connection:
                scan(addons, connection)
                resource_id = self.insert_local_scene(
                    connection,
                    vam_root,
                    resource_path,
                )

            pids: list[int] = []
            service = ManagerService(
                addons,
                state,
                process_probe=lambda: list(pids),
            )
            service.pin(["Core.Base"])
            service.reconcile(apply=True, activate=True)
            self.assertTrue(hidden_dependency.is_file())
            self.assertFalse(dependency.exists())
            pids.append(4321)

            request_observations: list[tuple[bool, bool]] = []

            def load_scene(
                root: Path,
                resource_ref: str,
                *,
                rescan: bool,
                merge: bool,
            ) -> str:
                self.assertEqual(root, vam_root)
                self.assertEqual(resource_ref, resource_path)
                self.assertFalse(merge)
                request_observations.append((rescan, dependency.is_file()))
                return "scene-request"

            with (
                mock.patch.object(
                    service,
                    "persons",
                    return_value={
                        "vam_running": True,
                        "available": True,
                        "capabilities": ["scene-load"],
                    },
                ),
                mock.patch(
                    "vampip.service.request_scene_load",
                    side_effect=load_scene,
                ),
            ):
                result = service.apply_resource(
                    resource_id,
                    confirm_replace=True,
                )

            self.assertEqual(request_observations, [(True, True)])
            self.assertTrue(dependency.is_file())
            self.assertFalse(hidden_dependency.exists())
            self.assertTrue(result["rescan"])
            self.assertEqual(result["bridge_request"], "scene-request")
            self.assertEqual(
                result["lease"]["discovered_roots"],
                ["Asset.Extra.2"],
            )

    def test_local_scene_without_package_refs_loads_without_rescan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            vam_root = base / "VaM"
            addons = vam_root / "AddonPackages"
            state = base / "state"
            addons.mkdir(parents=True)

            resource_path = "Saves/scene/Local.json"
            scene_path = vam_root / resource_path
            scene_path.parent.mkdir(parents=True)
            scene_path.write_text('{"atoms":[]}', encoding="utf-8")
            with connect(state) as connection:
                scan(addons, connection)
                resource_id = self.insert_local_scene(
                    connection,
                    vam_root,
                    resource_path,
                )

            service = ManagerService(
                addons,
                state,
                process_probe=lambda: [],
            )
            with (
                mock.patch.object(
                    service,
                    "persons",
                    return_value={
                        "vam_running": True,
                        "available": True,
                        "capabilities": ["scene-load"],
                    },
                ),
                mock.patch.object(
                    service,
                    "reconcile",
                    side_effect=AssertionError(
                        "a no-reference local scene must not reconcile packages"
                    ),
                ),
                mock.patch(
                    "vampip.service.request_scene_load",
                    return_value="scene-request",
                ) as request,
            ):
                result = service.apply_resource(
                    resource_id,
                    confirm_replace=True,
                )

            self.assertFalse(result["rescan"])
            self.assertTrue(result["lease"]["already_local"])
            self.assertEqual(result["lease"]["roots"], [])
            request.assert_called_once_with(
                vam_root,
                resource_path,
                rescan=False,
                merge=False,
            )


if __name__ == "__main__":
    unittest.main()

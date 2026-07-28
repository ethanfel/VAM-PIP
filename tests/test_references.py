from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from vampip.catalog import import_browserassist, search_resources
from vampip.database import connect
from vampip.inventory import scan
from vampip.references import scan_package_references
from vampip.service import ManagerService

from tests.test_vampip import make_var


class ReferenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

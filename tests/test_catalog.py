from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import zipfile

from vampip.catalog import (
    CatalogImportError,
    catalog_facets,
    get_resource_thumbnail,
    import_browserassist,
    resolve_resource_archive,
    search_resources,
)
from vampip.database import connect
from vampip.inventory import scan


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def browserassist_document(
    resources: list[dict[str, object]],
    *,
    user: bool = False,
    local: bool = False,
) -> dict[str, object]:
    if local:
        format_key = "LocalUserDataStoreFormat"
    elif user:
        format_key = "VARUserDataStoreFormat"
    else:
        format_key = "VARManifestStoreFormat"
    return {
        format_key: "3",
        "BAMajorVersion": "1",
        "BAMinorVersion": "18",
        "BAFixVersion": "2",
        "resources": resources,
    }


def make_var(
    path: Path,
    *,
    creator: str,
    package: str,
    members: dict[str, bytes],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "creatorName": creator,
        "packageName": package,
        "dependencies": {},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps(metadata))
        for name, data in members.items():
            archive.writestr(name, data)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vam_root = Path(self.temporary.name) / "VaM"
        self.addons = self.vam_root / "AddonPackages"
        self.catalogue = (
            self.vam_root / "Saves" / "PluginData" / "JayJayWon" / "BrowserAssist"
        )
        self.state = Path(self.temporary.name) / "state"
        self.cache = Path(self.temporary.name) / "thumb-cache"
        self.addons.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_catalogue(
        self,
        core: list[dict[str, object]],
        *,
        user: list[dict[str, object]] | None = None,
        local: list[dict[str, object]] | None = None,
    ) -> None:
        write_json(
            self.catalogue / "VARResourcesCoreData" / "VARResourcesData1.manifest",
            browserassist_document(core),
        )
        if user is not None:
            write_json(
                self.catalogue / "VARResourcesUserData" / "VARResourcesData1.userData",
                browserassist_document(user, user=True),
            )
        if local is not None:
            write_json(
                self.catalogue
                / "LocalResourcesUserData"
                / "LocalResourcesData1.userData",
                browserassist_document(local, local=True),
            )

    def test_import_exact_user_join_search_and_facets(self) -> None:
        scene = {
            "creatorName": "Creator",
            "packageName": "Scenes",
            "resourceFullFileName": "Saves\\scene\\Demo.json",
            "resourceType": "Scene",
            "presetAtomType": "",
            "varVersions": ["2", "1"],
        }
        preset = {
            "creatorName": "Creator",
            "packageName": "Looks",
            "resourceFullFileName": (
                "Custom\\Atom\\Person\\Appearance\\Preset_Ada.vap"
            ),
            "resourceType": "Preset Appearance",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        self.write_catalogue(
            [scene, preset],
            user=[
                {
                    "creatorName": "Creator",
                    "packageName": "Scenes",
                    "resourceFullFileName": "Saves\\scene\\Demo.json",
                    "baFavourite": "Active",
                    "baHidden": "false",
                    "Tags": [
                        {"tagName": "demo", "tagCategory": "User"},
                    ],
                },
                {
                    "creatorName": "creator",
                    "packageName": "Looks",
                    "resourceFullFileName": (
                        "Custom\\Atom\\Person\\Appearance\\Preset_Ada.vap"
                    ),
                    "baFavourite": "true",
                },
            ],
            local=[
                {
                    "resourceFullFileName": "Saves\\scene\\Local.json",
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "localFileFirstScanDateTime": "2026-01-01T00:00:00Z",
                    "baHidden": "1",
                }
            ],
        )

        with connect(self.state) as database:
            result = import_browserassist(database, self.vam_root)
            self.assertEqual(result.resource_count, 3)
            self.assertEqual(result.packaged_count, 2)
            self.assertEqual(result.local_count, 1)
            self.assertEqual(result.unmatched_user_rows, 1)

            search = search_resources(
                database,
                self.vam_root,
                query="demo",
                tag="DEMO",
                favorite=True,
            )
            self.assertEqual(search["total"], 1)
            item = search["items"][0]
            self.assertEqual(item["display_name"], "Demo")
            self.assertEqual(item["versions"], ["1", "2"])
            self.assertTrue(item["favorite"])

            looks = search_resources(
                database,
                self.vam_root,
                resource_type="preset appearance",
            )
            self.assertEqual(looks["total"], 1)
            self.assertFalse(looks["items"][0]["favorite"])
            self.assertTrue(looks["items"][0]["missing"])
            self.assertEqual(looks["items"][0]["missing_reason"], "package")

            local_result = search_resources(database, self.vam_root, query="Local")
            self.assertEqual(local_result["total"], 1)
            self.assertTrue(local_result["items"][0]["hidden"])
            self.assertTrue(local_result["items"][0]["missing"])
            self.assertTrue(local_result["items"][0]["local"])

            facets = catalog_facets(database, self.vam_root)
            self.assertEqual(facets["total"], 3)
            self.assertEqual(
                facets["resource_types"][0],
                {"value": "Scene", "count": 2},
            )
            self.assertEqual(
                facets["tags"],
                [{"name": "demo", "category": "User", "count": 1}],
            )

            first_id = item["id"]
            import_browserassist(database, self.vam_root)
            refreshed = search_resources(database, self.vam_root, query="demo")
            self.assertEqual(refreshed["items"][0]["id"], first_id)

    def test_failed_refresh_preserves_last_good_generation(self) -> None:
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Scenes",
                    "resourceFullFileName": "Saves\\scene\\Good.json",
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                }
            ]
        )
        core_path = (
            self.catalogue / "VARResourcesCoreData" / "VARResourcesData1.manifest"
        )
        with connect(self.state) as database:
            imported = import_browserassist(database, self.vam_root)
            before_source = database.execute(
                """
                SELECT imported_utc, resource_count FROM catalog_sources
                WHERE root = ? AND source = 'browserassist'
                """,
                (str(self.vam_root.resolve()),),
            ).fetchone()
            core_path.write_text("{ broken", encoding="utf-8")
            with self.assertRaises(CatalogImportError):
                import_browserassist(database, self.vam_root)
            resources = search_resources(database, self.vam_root)
            self.assertEqual(resources["total"], 1)
            self.assertEqual(resources["items"][0]["display_name"], "Good")
            after_source = database.execute(
                """
                SELECT imported_utc, resource_count FROM catalog_sources
                WHERE root = ? AND source = 'browserassist'
                """,
                (str(self.vam_root.resolve()),),
            ).fetchone()
            self.assertEqual(tuple(after_source), tuple(before_source))
            self.assertEqual(imported.resource_count, 1)

            # A database failure after some upserts must also leave the
            # previous generation intact.
            self.write_catalogue(
                [
                    {
                        "creatorName": "Creator",
                        "packageName": "Scenes",
                        "resourceFullFileName": "Saves\\scene\\Good.json",
                        "resourceType": "Preset Pose",
                        "presetAtomType": "Person",
                        "varVersions": ["1"],
                    },
                    {
                        "creatorName": "Creator",
                        "packageName": "Scenes",
                        "resourceFullFileName": "Saves\\scene\\Rejected.json",
                        "resourceType": "Scene",
                        "presetAtomType": "",
                        "varVersions": ["1"],
                    },
                ]
            )
            database.execute(
                """
                CREATE TRIGGER reject_catalog_test
                BEFORE INSERT ON catalog_resources
                WHEN NEW.resource_path = 'Saves\\scene\\Rejected.json'
                BEGIN
                    SELECT RAISE(ABORT, 'test rejection');
                END
                """
            )
            with self.assertRaises(sqlite3.IntegrityError):
                import_browserassist(database, self.vam_root)
            after_database_failure = search_resources(database, self.vam_root)
            self.assertEqual(after_database_failure["total"], 1)
            self.assertEqual(
                after_database_failure["items"][0]["resource_type"], "Scene"
            )

    def test_resolver_verifies_the_member_in_an_allowed_version(self) -> None:
        resource_path = "Saves\\scene\\Versioned.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Bundle",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1", "2"],
                }
            ]
        )
        jpeg = b"\xff\xd8\xff\xe0" + b"thumbnail"
        make_var(
            self.addons / "Creator.Bundle.1.var",
            creator="Creator",
            package="Bundle",
            members={
                "Saves/scene/Versioned.json": b"{}",
                "Saves/scene/Versioned.JPG": jpeg,
            },
        )
        make_var(
            self.addons / "Creator.Bundle.2.var",
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Other.json": b"{}"},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            resource_id = search_resources(database, self.vam_root)["items"][0]["id"]
            listed = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(listed["package_ref"], "Creator.Bundle.1")
            self.assertEqual(listed["selected_version"], "1")
            self.assertTrue(listed["enabled"])
            self.assertFalse(listed["missing"])
            location = resolve_resource_archive(database, self.vam_root, resource_id)
            self.assertIsNotNone(location)
            assert location is not None
            self.assertEqual(location.version_text, "1")
            self.assertEqual(location.archive_member, "Saves/scene/Versioned.json")
            self.assertEqual(location.package_ref, "Creator.Bundle.1")

            active = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="active",
            )
            self.assertEqual(active["total"], 1)
            hidden = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="hidden",
            )
            self.assertEqual(hidden["total"], 0)
            self.assertEqual(
                database.execute(
                    "SELECT COUNT(*) FROM catalog_resource_versions"
                ).fetchone()[0],
                2,
            )

            first = get_resource_thumbnail(
                database,
                self.vam_root,
                resource_id,
                self.cache,
                max_bytes=1024,
            )
            self.assertIsNotNone(first)
            assert first is not None
            self.assertFalse(first.cache_hit)
            self.assertEqual(first.path.read_bytes(), jpeg)
            self.assertEqual(first.version_text, "1")

            with mock.patch.object(
                zipfile.ZipFile,
                "open",
                side_effect=AssertionError("cache hit read the ZIP payload"),
            ):
                second = get_resource_thumbnail(
                    database,
                    self.vam_root,
                    resource_id,
                    self.cache,
                    max_bytes=1024,
                )
            self.assertIsNotNone(second)
            assert second is not None
            self.assertTrue(second.cache_hit)
            self.assertEqual(second.etag, first.etag)

            rejected = get_resource_thumbnail(
                database,
                self.vam_root,
                resource_id,
                self.cache,
                max_bytes=4,
            )
            self.assertIsNone(rejected)


if __name__ == "__main__":
    unittest.main()

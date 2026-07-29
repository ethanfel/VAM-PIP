from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import vampip.catalog as catalog_module
from vampip.catalog import (
    CatalogImportError,
    _ResourceResolver,
    catalog_facets,
    get_resource_thumbnail,
    import_browserassist,
    package_resource_summaries,
    package_resources_for_copy,
    resolve_resource_archive,
    search_resources,
)
from vampip.database import SCHEMA_VERSION, connect
from vampip.inventory import scan
from vampip.manager_state import set_package_choice
from vampip.service import ManagerService, PackageConflictError


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

            combined = search_resources(
                database,
                self.vam_root,
                resource_types=["scene", "PRESET APPEARANCE"],
            )
            self.assertEqual(combined["total"], 3)
            person_only = search_resources(
                database,
                self.vam_root,
                resource_types=["Scene", "Preset Appearance"],
                atom_types=["person"],
            )
            self.assertEqual(person_only["total"], 1)
            self.assertEqual(
                person_only["items"][0]["resource_type"],
                "Preset Appearance",
            )

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

    def test_package_resource_summary_and_browse_are_exact_to_selected_copy(
        self,
    ) -> None:
        appearance_a = (
            "Custom\\Atom\\Person\\Appearance\\Preset_Alana.vap"
        )
        appearance_b = (
            "Custom\\Atom\\Person\\Appearance\\Preset_Beatrice.vap"
        )
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Looks",
                    "resourceFullFileName": appearance_a,
                    "resourceType": "preset appearance",
                    "presetAtomType": "Person",
                    "varVersions": ["1"],
                },
                {
                    "creatorName": "Creator",
                    "packageName": "Looks",
                    "resourceFullFileName": appearance_b,
                    "resourceType": "Preset Appearance",
                    "presetAtomType": "Person",
                    "varVersions": ["1"],
                },
                {
                    "creatorName": "Creator",
                    "packageName": "Looks",
                    "resourceFullFileName": (
                        "Custom\\Atom\\Person\\Appearance\\Preset_V2.vap"
                    ),
                    "resourceType": "Preset Appearance",
                    "presetAtomType": "Person",
                    "varVersions": ["2"],
                },
                {
                    "creatorName": "Creator",
                    "packageName": "LooksExtra",
                    "resourceFullFileName": (
                        "Custom\\Atom\\Person\\Appearance\\Preset_Extra.vap"
                    ),
                    "resourceType": "Preset Appearance",
                    "presetAtomType": "Person",
                    "varVersions": ["1"],
                },
            ]
        )
        make_var(
            self.addons / "Creator.Looks.1.var",
            creator="Creator",
            package="Looks",
            members={appearance_a: b"{}"},
        )
        make_var(
            self.addons / "Copies" / "Creator.Looks.1.var",
            creator="Creator",
            package="Looks",
            members={appearance_b: b"{}"},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            copies = list(
                database.execute(
                    """
                    SELECT * FROM package_files
                    WHERE creator = 'Creator' AND package_name = 'Looks'
                      AND version_text = '1'
                    ORDER BY relative_path
                    """
                )
            )
            self.assertEqual(len(copies), 2)
            alana_copy = next(
                row
                for row in copies
                if str(row["relative_path"]) == "Creator.Looks.1.var"
            )
            beatrice_copy = next(
                row for row in copies if row is not alana_copy
            )

            summaries = package_resource_summaries(
                database,
                self.vam_root,
                [alana_copy],
            )
            summary = summaries["creator.looks.1"]
            self.assertEqual(summary["resource_count"], 2)
            self.assertEqual(
                summary["resource_types"],
                [{"value": "Preset Appearance", "count": 2}],
            )
            self.assertEqual(len(summary["resource_previews"]), 2)
            plan = list(
                database.execute(
                    """
                    EXPLAIN QUERY PLAN
                    WITH wanted(package_id, creator, package_name) AS (
                        VALUES (?, ?, ?)
                    )
                    SELECT resource.id
                    FROM wanted
                    CROSS JOIN catalog_resources AS resource
                        INDEXED BY idx_catalog_root_source_family_nocase
                    WHERE resource.root = ?
                      AND resource.source = ?
                      AND resource.creator = wanted.creator COLLATE NOCASE
                      AND resource.package_name =
                          wanted.package_name COLLATE NOCASE
                    """,
                    (
                        "creator.looks.1",
                        "Creator",
                        "Looks",
                        str(self.vam_root.resolve()),
                        "browserassist",
                    ),
                )
            )
            plan_text = " ".join(str(row[3]) for row in plan)
            self.assertIn(
                "idx_catalog_root_source_family_nocase",
                plan_text,
            )
            self.assertIn(
                "root=? AND source=? AND creator=? AND package_name=?",
                plan_text,
            )

            first = package_resources_for_copy(
                database,
                self.vam_root,
                alana_copy,
            )
            second = package_resources_for_copy(
                database,
                self.vam_root,
                beatrice_copy,
            )
            self.assertEqual(first["total"], 1)
            self.assertEqual(second["total"], 1)
            first_states = {
                item["display_name"]: item["state"] for item in first["items"]
            }
            second_states = {
                item["display_name"]: item["state"] for item in second["items"]
            }
            self.assertEqual(
                first_states,
                {"Alana": "active"},
            )
            self.assertEqual(
                second_states,
                {"Beatrice": "active"},
            )
            only_missing = package_resources_for_copy(
                database,
                self.vam_root,
                alana_copy,
                query="Beatrice",
                resource_types=["preset appearance"],
                package_state="missing",
                limit=1,
            )
            self.assertEqual(only_missing["total"], 1)
            self.assertEqual(
                only_missing["items"][0]["display_name"],
                "Beatrice",
            )

        service = ManagerService(
            self.addons,
            self.state,
            vam_root=self.vam_root,
            process_probe=lambda: [],
        )
        with self.assertRaises(PackageConflictError) as unresolved:
            service.package_resources("Creator.Looks.1")
        self.assertEqual(unresolved.exception.code, "package_copy_conflict")
        self.assertEqual(len(unresolved.exception.conflicts), 1)
        self.assertFalse(unresolved.exception.conflicts[0]["resolved"])

        with connect(self.state) as database:
            set_package_choice(
                database,
                self.addons,
                "Creator.Looks.1",
                "1:" + ("0" * 64),
            )
        with self.assertRaises(PackageConflictError) as stale:
            service.package_resources("Creator.Looks.1")
        self.assertEqual(stale.exception.code, "package_copy_choice_stale")
        self.assertTrue(stale.exception.conflicts[0]["choice_stale"])

        with connect(self.state) as database:
            selected = database.execute(
                """
                SELECT content_sha256, relative_path
                FROM package_files
                WHERE relative_path = 'Copies/Creator.Looks.1.var'
                """
            ).fetchone()
            assert selected is not None
            set_package_choice(
                database,
                self.addons,
                "Creator.Looks.1",
                str(selected["content_sha256"]),
                preferred_logical_path=str(selected["relative_path"]),
            )
        chosen = service.package_resources("creator.looks.1")
        self.assertEqual(chosen["package"]["id"], "Creator.Looks.1")
        self.assertEqual(
            [item["display_name"] for item in chosen["items"]],
            ["Beatrice"],
        )

    def test_archive_member_index_cache_is_thread_safe_and_bounded(self) -> None:
        first = self.addons / "Creator.First.1.var"
        second = self.addons / "Creator.Second.1.var"
        make_var(
            first,
            creator="Creator",
            package="First",
            members={"Saves/scene/First.json": b"{}"},
        )
        make_var(
            second,
            creator="Creator",
            package="Second",
            members={"Saves/scene/Second.json": b"{}"},
        )
        cache = catalog_module._ArchiveMemberIndexCache(max_entries=1)
        real_zip_file = zipfile.ZipFile
        opened: list[Path] = []

        def counted_zip_file(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> zipfile.ZipFile:
            opened.append(Path(path))
            return real_zip_file(path, *args, **kwargs)

        with mock.patch(
            "vampip.catalog.zipfile.ZipFile",
            side_effect=counted_zip_file,
        ):
            with ThreadPoolExecutor(max_workers=8) as executor:
                indexed = list(executor.map(lambda _: cache.get(first), range(8)))
            self.assertIsNotNone(indexed[0])
            self.assertTrue(all(result is indexed[0] for result in indexed))
            self.assertEqual(opened, [first])

            self.assertIsNotNone(cache.get(second))
            self.assertIsNotNone(cache.get(first))

        self.assertEqual(opened, [first, second, first])

    def test_package_browse_and_thumbnails_share_archive_member_index(
        self,
    ) -> None:
        resource_path = "Saves\\scene\\Shared.json"
        thumbnail = b"\xff\xd8\xff\xe0shared-thumbnail"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Shared",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                }
            ]
        )
        archive_path = self.addons / "Creator.Shared.1.var"
        make_var(
            archive_path,
            creator="Creator",
            package="Shared",
            members={
                resource_path: b"{}",
                "Saves\\scene\\Shared.jpg": thumbnail,
            },
        )
        catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear()
        self.addCleanup(catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear)

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Shared'
                """
            ).fetchone()
            resource_id = database.execute(
                """
                SELECT id FROM catalog_resources
                WHERE creator = 'Creator' AND package_name = 'Shared'
                """
            ).fetchone()[0]
            assert package_row is not None
            real_zip_file = zipfile.ZipFile
            opened: list[Path] = []

            def counted_zip_file(
                path: Path,
                *args: object,
                **kwargs: object,
            ) -> zipfile.ZipFile:
                opened.append(Path(path))
                return real_zip_file(path, *args, **kwargs)

            with mock.patch(
                "vampip.catalog.zipfile.ZipFile",
                side_effect=counted_zip_file,
            ):
                browsed = package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )
                resolved = resolve_resource_archive(
                    database,
                    self.vam_root,
                    int(resource_id),
                )
                first = get_resource_thumbnail(
                    database,
                    self.vam_root,
                    int(resource_id),
                    self.cache,
                )
                second = get_resource_thumbnail(
                    database,
                    self.vam_root,
                    int(resource_id),
                    self.cache,
                )

        self.assertEqual(browsed["total"], 1)
        self.assertIsNotNone(resolved)
        assert first is not None
        assert second is not None
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.path.read_bytes(), thumbnail)
        # One open builds the shared index; one bounded payload read populates
        # the thumbnail cache. Resolution and the second request open no ZIP.
        self.assertEqual(opened, [archive_path, archive_path])

    def test_archive_member_index_invalidates_after_package_replacement(
        self,
    ) -> None:
        first_path = "Saves\\scene\\First.json"
        second_path = "Saves\\scene\\Second.json"
        second_thumbnail = b"\xff\xd8\xff\xe0replacement-thumbnail"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Replaceable",
                    "resourceFullFileName": first_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                },
                {
                    "creatorName": "Creator",
                    "packageName": "Replaceable",
                    "resourceFullFileName": second_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                },
            ]
        )
        archive_path = self.addons / "Creator.Replaceable.1.var"
        make_var(
            archive_path,
            creator="Creator",
            package="Replaceable",
            members={first_path: b"{}"},
        )
        replacement = self.state / "replacement.var"
        make_var(
            replacement,
            creator="Creator",
            package="Replaceable",
            members={
                second_path: b"{}",
                "Saves\\scene\\Second.jpg": second_thumbnail,
            },
        )
        catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear()
        self.addCleanup(catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear)

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Replaceable'
                """
            ).fetchone()
            second_id = database.execute(
                """
                SELECT id FROM catalog_resources
                WHERE resource_path = ?
                """,
                (second_path,),
            ).fetchone()[0]
            assert package_row is not None
            real_zip_file = zipfile.ZipFile
            opened_before_rescan: list[Path] = []

            def counted_zip_file(
                path: Path,
                *args: object,
                **kwargs: object,
            ) -> zipfile.ZipFile:
                opened_before_rescan.append(Path(path))
                return real_zip_file(path, *args, **kwargs)

            with mock.patch(
                "vampip.catalog.zipfile.ZipFile",
                side_effect=counted_zip_file,
            ):
                before = package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )
                replacement.replace(archive_path)
                with self.assertRaisesRegex(
                    ValueError,
                    "no longer matches the scanned inventory; rescan required",
                ):
                    package_resources_for_copy(
                        database,
                        self.vam_root,
                        package_row,
                    )
                self.assertIsNone(
                    get_resource_thumbnail(
                        database,
                        self.vam_root,
                        int(second_id),
                        self.cache,
                    )
                )

            scan(self.addons, database)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Replaceable'
                """
            ).fetchone()
            assert package_row is not None
            opened_after_rescan: list[Path] = []

            def counted_after_rescan(
                path: Path,
                *args: object,
                **kwargs: object,
            ) -> zipfile.ZipFile:
                opened_after_rescan.append(Path(path))
                return real_zip_file(path, *args, **kwargs)

            with mock.patch(
                "vampip.catalog.zipfile.ZipFile",
                side_effect=counted_after_rescan,
            ):
                after = package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )
                thumbnail = get_resource_thumbnail(
                    database,
                    self.vam_root,
                    int(second_id),
                    self.cache,
                )

        self.assertEqual(
            [item["display_name"] for item in before["items"]],
            ["First"],
        )
        self.assertEqual(
            [item["display_name"] for item in after["items"]],
            ["Second"],
        )
        assert thumbnail is not None
        self.assertEqual(thumbnail.path.read_bytes(), second_thumbnail)
        self.assertEqual(opened_before_rescan, [archive_path])
        self.assertEqual(opened_after_rescan, [archive_path, archive_path])

    def test_package_browse_rejects_corrupt_or_changing_selected_archive(
        self,
    ) -> None:
        resource_path = "Saves\\scene\\Demo.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Unstable",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                }
            ]
        )
        archive_path = self.addons / "Creator.Unstable.1.var"
        make_var(
            archive_path,
            creator="Creator",
            package="Unstable",
            members={resource_path: b"{}"},
        )
        catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear()
        self.addCleanup(catalog_module._ARCHIVE_MEMBER_INDEX_CACHE.clear)

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Unstable'
                """
            ).fetchone()
            assert package_row is not None

            recorded_stat = archive_path.stat()
            archive_path.write_bytes(b"x" * recorded_stat.st_size)
            os.utime(
                archive_path,
                ns=(recorded_stat.st_atime_ns, recorded_stat.st_mtime_ns),
            )
            with self.assertRaisesRegex(
                ValueError,
                "selected package archive is unreadable or changed",
            ):
                package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )

            make_var(
                archive_path,
                creator="Creator",
                package="Unstable",
                members={resource_path: b"{}"},
            )
            scan(self.addons, database)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Unstable'
                """
            ).fetchone()
            assert package_row is not None
            replacement = self.state / "changed-during-index.var"
            make_var(
                replacement,
                creator="Creator",
                package="Unstable",
                members={resource_path: b'{"replacement":true}'},
            )
            real_member_indexes = catalog_module._member_indexes

            def replace_during_index(
                archive: zipfile.ZipFile,
            ) -> catalog_module._ArchiveMemberIndexes:
                indexes = real_member_indexes(archive)
                replacement.replace(archive_path)
                return indexes

            with (
                mock.patch(
                    "vampip.catalog._member_indexes",
                    side_effect=replace_during_index,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "selected package archive is unreadable or changed",
                ),
            ):
                package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )

            with self.assertRaisesRegex(
                ValueError,
                "no longer matches the scanned inventory; rescan required",
            ):
                package_resources_for_copy(
                    database,
                    self.vam_root,
                    package_row,
                )
            scan(self.addons, database)
            refreshed_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Unstable'
                """
            ).fetchone()
            assert refreshed_row is not None
            recovered = package_resources_for_copy(
                database,
                self.vam_root,
                refreshed_row,
            )
            self.assertEqual(recovered["total"], 1)

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

    def test_search_uses_json_scalar_values_without_exposing_internal_metadata(
        self,
    ) -> None:
        resource_path = "Custom\\Clothing\\Female\\Creator\\Gala Dress\\Gala Dress.vam"
        resource = {
            "creatorName": "Creator",
            "packageName": "Wardrobe",
            "resourceFullFileName": resource_path,
            "resourceType": "Clothing (Female)",
            "presetAtomType": "Person",
            "varVersions": ["1"],
            "clothingVersions": [
                {
                    "varVersion": "1",
                    "clothing": {
                        "itemType": "ClothingFemale",
                        "uid": "Creator:Gala Dress",
                        "displayName": "Moonlit Gala",
                        "creatorName": "Creator",
                        "tags": "formal, evening",
                        "isRealItem": True,
                    },
                }
            ],
        }
        self.write_catalogue(
            [resource],
            user=[
                {
                    "creatorName": "Creator",
                    "packageName": "Wardrobe",
                    "resourceFullFileName": resource_path,
                    "Tags": [
                        {"tagName": "Keeper", "tagCategory": "User"},
                    ],
                }
            ],
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)

            for key_name in ("is_real_item", "tagName", "tagCategory"):
                with self.subTest(key_name=key_name):
                    result = search_resources(
                        database,
                        self.vam_root,
                        query=key_name,
                        include_package_state=False,
                    )
                    self.assertEqual(result["total"], 0)

            for value in ("Moonlit Gala", "evening", "Keeper", "User", "true"):
                with self.subTest(value=value):
                    result = search_resources(
                        database,
                        self.vam_root,
                        query=value,
                        include_package_state=False,
                    )
                    self.assertEqual(result["total"], 1)
                    item = result["items"][0]
                    self.assertNotIn("clothing_versions", item)
                    self.assertNotIn("clothing", item)

    def test_refresh_preserves_only_omitted_hidden_package_resources(self) -> None:
        hidden_resource = {
            "creatorName": "Creator",
            "packageName": "HiddenLook",
            "resourceFullFileName": ("Custom\\Atom\\Person\\Hair\\Preset_Hidden.vap"),
            "resourceType": "Preset Hair",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        active_resource = {
            "creatorName": "Creator",
            "packageName": "ActiveLook",
            "resourceFullFileName": ("Custom\\Atom\\Person\\Hair\\Preset_Active.vap"),
            "resourceType": "Preset Hair",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        uninstalled_resource = {
            "creatorName": "Creator",
            "packageName": "UninstalledLook",
            "resourceFullFileName": (
                "Custom\\Atom\\Person\\Hair\\Preset_Uninstalled.vap"
            ),
            "resourceType": "Preset Hair",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        local_resource = {
            "resourceFullFileName": ("Custom\\Atom\\Person\\Hair\\Preset_Local.vap"),
            "resourceType": "Preset Hair",
            "presetAtomType": "Person",
        }
        hidden_path = self.addons / "Creator.HiddenLook.1.var"
        make_var(
            hidden_path,
            creator="Creator",
            package="HiddenLook",
            members={
                "Custom/Atom/Person/Hair/Preset_Hidden.vap": b"{}",
            },
        )
        hidden_path.rename(Path(f"{hidden_path}.vampip-disabled"))
        make_var(
            self.addons / "Creator.ActiveLook.1.var",
            creator="Creator",
            package="ActiveLook",
            members={
                "Custom/Atom/Person/Hair/Preset_Active.vap": b"{}",
            },
        )
        self.write_catalogue(
            [hidden_resource, active_resource, uninstalled_resource],
            user=[
                {
                    "creatorName": "Creator",
                    "packageName": "HiddenLook",
                    "resourceFullFileName": hidden_resource["resourceFullFileName"],
                    "baFavourite": "Active",
                    "Tags": [
                        {"tagName": "keeper", "tagCategory": "User"},
                    ],
                }
            ],
            local=[local_resource],
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            initial = import_browserassist(database, self.vam_root)
            self.assertEqual(initial.resource_count, 4)
            hidden_before = search_resources(
                database,
                self.vam_root,
                query="Hidden",
            )["items"][0]
            hidden_id = hidden_before["id"]

            self.write_catalogue([], user=[], local=[])
            refreshed = import_browserassist(database, self.vam_root)

            self.assertEqual(refreshed.resource_count, 1)
            self.assertEqual(refreshed.packaged_count, 1)
            self.assertEqual(refreshed.local_count, 0)
            self.assertEqual(refreshed.preserved_hidden_count, 1)
            remaining = search_resources(database, self.vam_root)
            self.assertEqual(remaining["total"], 1)
            kept = remaining["items"][0]
            self.assertEqual(kept["id"], hidden_id)
            self.assertTrue(kept["favorite"])
            self.assertEqual(
                kept["tags"],
                [{"tagName": "keeper", "tagCategory": "User"}],
            )
            self.assertEqual(kept["versions"], ["1"])
            hidden = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="hidden",
            )
            self.assertEqual(hidden["total"], 1)
            location = resolve_resource_archive(
                database,
                self.vam_root,
                hidden_id,
                addon_root=self.addons,
            )
            self.assertIsNotNone(location)
            assert location is not None
            self.assertFalse(location.enabled)
            self.assertTrue(str(location.archive_path).endswith(".var.vampip-disabled"))
            self.assertEqual(
                [
                    row["version_text"]
                    for row in database.execute(
                        """
                        SELECT version_text
                        FROM catalog_resource_versions
                        WHERE resource_id = ?
                        """,
                        (hidden_id,),
                    )
                ],
                ["1"],
            )
            self.assertEqual(
                database.execute(
                    """
                    SELECT resource_count
                    FROM catalog_sources
                    WHERE root = ? AND source = 'browserassist'
                    """,
                    (str(self.vam_root.resolve()),),
                ).fetchone()[0],
                1,
            )

            updated_hidden = dict(hidden_resource)
            updated_hidden["resourceType"] = "Preset Appearance"
            updated_hidden["varVersions"] = ["2"]
            self.write_catalogue([updated_hidden], user=[], local=[])
            reappeared = import_browserassist(database, self.vam_root)
            self.assertEqual(reappeared.preserved_hidden_count, 0)
            updated = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(updated["id"], hidden_id)
            self.assertEqual(updated["resource_type"], "Preset Appearance")
            self.assertEqual(updated["versions"], ["2"])
            self.assertEqual(
                [
                    row["version_text"]
                    for row in database.execute(
                        """
                        SELECT version_text
                        FROM catalog_resource_versions
                        WHERE resource_id = ?
                        """,
                        (hidden_id,),
                    )
                ],
                ["2"],
            )

    def test_manager_import_uses_configured_addon_root_for_hidden_rows(self) -> None:
        alternate_addons = Path(self.temporary.name) / "AlternateAddons"
        alternate_addons.mkdir()
        hidden_path = alternate_addons / "Creator.HiddenLook.1.var"
        make_var(
            hidden_path,
            creator="Creator",
            package="HiddenLook",
            members={
                "Custom/Atom/Person/Hair/Preset_Hidden.vap": b"{}",
            },
        )
        hidden_path.rename(Path(f"{hidden_path}.vampip-disabled"))
        resource = {
            "creatorName": "Creator",
            "packageName": "HiddenLook",
            "resourceFullFileName": ("Custom\\Atom\\Person\\Hair\\Preset_Hidden.vap"),
            "resourceType": "Preset Hair",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        self.write_catalogue([resource])
        service = ManagerService(
            alternate_addons,
            self.state,
            vam_root=self.vam_root,
            process_probe=lambda: [],
        )

        initial = service.import_catalog()
        self.assertEqual(initial["resource_count"], 1)
        self.write_catalogue([])
        refreshed = service.import_catalog()
        self.assertEqual(refreshed["resource_count"], 1)
        self.assertEqual(refreshed["preserved_hidden_count"], 1)
        with connect(self.state) as database:
            result = search_resources(
                database,
                self.vam_root,
                addon_root=alternate_addons,
                package_state="hidden",
            )
        self.assertEqual(result["total"], 1)

    def test_clothing_metadata_uses_exact_installed_version_and_preserves_uid(
        self,
    ) -> None:
        resource_path = (
            "Custom\\Clothing\\Female\\Creator\\Evening Dress\\Evening Dress.vam"
        )
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Wardrobe",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Clothing (Female)",
                    "presetAtomType": "Person",
                    "varVersions": ["1", "2"],
                    "clothingVersions": [
                        {
                            "varVersion": "1",
                            "clothing": {
                                "itemType": "ClothingFemale",
                                "uid": "Creator:Evening Dress Old",
                                "displayName": "Old Dress",
                                "creatorName": "Creator",
                                "tags": "old",
                                "isRealItem": "false",
                            },
                        },
                        {
                            "varVersion": "2",
                            "clothing": {
                                "itemType": " ClothingFemale ",
                                "uid": "Creator:Evening Dress ",
                                "displayName": " Evening Dress ",
                                "creatorName": " Creator ",
                                "tags": "formal, Formal, evening",
                                "isRealItem": "true",
                            },
                        },
                    ],
                }
            ]
        )
        member = "Custom/Clothing/Female/Creator/Evening Dress/Evening Dress.vam"
        for version in ("1", "2"):
            make_var(
                self.addons / f"Creator.Wardrobe.{version}.var",
                creator="Creator",
                package="Wardrobe",
                members={f"./{member}": b"{}"},
            )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Clothing (Female)",
            )

            self.assertEqual(result["total"], 1)
            item = result["items"][0]
            self.assertEqual(item["selected_version"], "2")
            self.assertEqual(item["package_ref"], "Creator.Wardrobe.2")
            self.assertEqual(
                item["resolved_resource_ref"],
                f"Creator.Wardrobe.2:/{member}",
            )
            self.assertNotIn("clothing_versions", item)
            self.assertEqual(
                item["clothing"],
                {
                    "version": "2",
                    "item_type": "ClothingFemale",
                    "uid": "Creator:Evening Dress ",
                    "display_name": "Evening Dress",
                    "creator": "Creator",
                    "tags": ["formal", "evening"],
                    "is_real_item": True,
                },
            )

            stored = json.loads(
                database.execute(
                    """
                    SELECT clothing_versions_json
                    FROM catalog_resources
                    """
                ).fetchone()[0]
            )
            self.assertEqual(
                [entry["version"] for entry in stored],
                ["1", "2"],
            )
            self.assertEqual(stored[1]["uid"], "Creator:Evening Dress ")

    def test_clothing_metadata_does_not_fall_back_to_another_version(
        self,
    ) -> None:
        resource_path = "Custom\\Clothing\\Male\\Creator\\Jacket\\Jacket.vam"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Menswear",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Clothing (Male)",
                    "presetAtomType": "Person",
                    "varVersions": ["1", "2"],
                    "clothingVersions": [
                        {
                            "varVersion": "1",
                            "clothing": {
                                "itemType": "ClothingMale",
                                "uid": "Creator:Jacket v1",
                                "displayName": "Jacket",
                                "creatorName": "Creator",
                                "tags": "outerwear",
                                "isRealItem": True,
                            },
                        }
                    ],
                }
            ]
        )
        member = "Custom/Clothing/Male/Creator/Jacket/Jacket.vam"
        make_var(
            self.addons / "Creator.Menswear.2.var",
            creator="Creator",
            package="Menswear",
            members={member: b"{}"},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            item = search_resources(database, self.vam_root)["items"][0]

            self.assertEqual(item["selected_version"], "2")
            self.assertEqual(item["package_ref"], "Creator.Menswear.2")
            self.assertNotIn("clothing", item)
            stored = json.loads(
                database.execute(
                    """
                    SELECT clothing_versions_json
                    FROM catalog_resources
                    """
                ).fetchone()[0]
            )
            self.assertEqual(stored[0]["uid"], "Creator:Jacket v1")

    def test_package_copy_browse_keeps_clothing_metadata_and_exact_variants(
        self,
    ) -> None:
        parent = "Custom\\Clothing\\Female\\Creator\\Dress"
        clothing_path = f"{parent}\\Dress.vam"
        red_path = f"{parent}\\Dress_Red.vap"
        blue_path = f"{parent}\\Dress_Blue.vap"
        common = {
            "creatorName": "Creator",
            "packageName": "Wardrobe",
            "presetAtomType": "Person",
            "varVersions": ["1"],
        }
        self.write_catalogue(
            [
                {
                    **common,
                    "resourceFullFileName": clothing_path,
                    "resourceType": "Clothing (Female)",
                    "clothingVersions": [
                        {
                            "varVersion": "1",
                            "clothing": {
                                "itemType": "ClothingFemale",
                                "uid": "Creator:Dress",
                                "displayName": "Dress",
                                "creatorName": "Creator",
                                "tags": "formal",
                                "isRealItem": True,
                            },
                        }
                    ],
                },
                {
                    **common,
                    "resourceFullFileName": red_path,
                    "resourceType": "Clothing Item Presets",
                },
                {
                    **common,
                    "resourceFullFileName": blue_path,
                    "resourceType": "Clothing Item Presets",
                },
            ]
        )
        make_var(
            self.addons / "Creator.Wardrobe.1.var",
            creator="Creator",
            package="Wardrobe",
            members={
                clothing_path: b"{}",
                red_path: b"{}",
            },
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            package_row = database.execute(
                """
                SELECT * FROM package_files
                WHERE creator = 'Creator' AND package_name = 'Wardrobe'
                  AND version_text = '1'
                """
            ).fetchone()
            assert package_row is not None
            result = package_resources_for_copy(
                database,
                self.vam_root,
                package_row,
                resource_types=["Clothing (Female)"],
            )

        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["clothing"]["uid"], "Creator:Dress")
        self.assertNotIn("clothing_versions", item)
        self.assertEqual(
            [variant["label"] for variant in item["variants"]],
            ["Red"],
        )
        self.assertEqual(item["variant_count"], 1)
        self.assertEqual(
            item["variants"][0]["package_ref"],
            "Creator.Wardrobe.1",
        )
        self.assertFalse(item["variants"][0]["missing"])

    def test_clothing_cards_include_bounded_related_style_choices(self) -> None:
        parent = "Custom\\Clothing\\Female\\Creator\\Shared"

        def resource(
            path: str,
            resource_type: str,
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "Wardrobe",
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": (
                    "" if resource_type == "Clothing Item Presets" else "Person"
                ),
                "varVersions": ["1"],
            }

        resources = [
            resource(f"{parent}\\Dress.vam", "Clothing (Female)"),
            resource(f"{parent}\\Dress Long.vam", "Clothing (Female)"),
            *[
                resource(
                    f"{parent}\\Dress_Color{index:02d}.vap",
                    "Clothing Item Presets",
                )
                for index in range(14)
            ],
            resource(
                f"{parent}\\Dress Long_BlackLeather.vap",
                "Clothing Item Presets",
            ),
            resource(
                f"{parent}\\Unrelated_Blue.vap",
                "Clothing Item Presets",
            ),
        ]
        self.write_catalogue(resources)

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
            )

        by_name = {item["display_name"]: item for item in result["items"]}
        dress = by_name["Dress"]
        self.assertEqual(dress["variant_group"], "related-resources")
        self.assertEqual(dress["variant_count"], 14)
        self.assertEqual(len(dress["variants"]), 12)
        self.assertEqual(dress["variants"][0]["label"], "Color00")
        self.assertEqual(dress["variant_search"], "Dress")
        first_variant = dress["variants"][0]
        self.assertEqual(first_variant["resource_type"], "Clothing Item Presets")
        self.assertEqual(first_variant["creator"], "Creator")
        self.assertEqual(first_variant["package"], "Wardrobe")
        self.assertEqual(first_variant["relationship_kind"], "item-style")
        self.assertEqual(
            first_variant["relationship_confidence"],
            "name-match",
        )
        self.assertEqual(
            first_variant["relationship_reason"],
            "Same-package folder/name/version match; not semantic identity",
        )
        for private_field in (
            "path",
            "key",
            "source",
            "versions",
            "resolved_resource_ref",
            "package_ref",
        ):
            self.assertNotIn(private_field, first_variant)

        long_dress = by_name["Dress Long"]
        self.assertEqual(long_dress["variant_count"], 1)
        self.assertEqual(long_dress["variant_search"], "Dress Long")
        self.assertEqual(
            long_dress["variants"][0]["label"],
            "Black Leather",
        )
        self.assertNotIn(
            "Unrelated_Blue",
            {
                variant["display_name"]
                for item in result["items"]
                for variant in item.get("variants", [])
            },
        )

    def test_related_styles_keep_case_only_package_families_separate(
        self,
    ) -> None:
        parent = "Custom\\Clothing\\Female\\Creator\\Dress"

        def resource(
            package: str,
            path: str,
            resource_type: str,
            version: str,
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": package,
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": "Person",
                "varVersions": [version],
            }

        self.write_catalogue(
            [
                resource(
                    "Wardrobe",
                    f"{parent}\\Dress.vam",
                    "Clothing (Female)",
                    "2",
                ),
                resource(
                    "Wardrobe",
                    f"{parent}\\Dress_Black.vap",
                    "Clothing Item Presets",
                    "2",
                ),
                resource(
                    "wardrobe",
                    f"{parent}\\Dress.vam",
                    "Clothing (Female)",
                    "1",
                ),
                resource(
                    "wardrobe",
                    f"{parent}\\Dress_Red.vap",
                    "Clothing Item Presets",
                    "1",
                ),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
            )

        by_package = {item["package"]: item for item in result["items"]}
        self.assertEqual(
            [variant["label"] for variant in by_package["Wardrobe"]["variants"]],
            ["Black"],
        )
        self.assertEqual(
            [variant["label"] for variant in by_package["wardrobe"]["variants"]],
            ["Red"],
        )

    def test_related_styles_require_version_overlap_and_deduplicate_path(
        self,
    ) -> None:
        parent = "Custom\\Clothing\\Female\\Creator\\Dress"

        def resource(
            path: str,
            resource_type: str,
            version: str,
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "Wardrobe",
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": "Person",
                "varVersions": [version],
            }

        self.write_catalogue(
            [
                resource(
                    f"{parent}\\Dress.vam",
                    "Clothing (Female)",
                    "2",
                ),
                resource(
                    f"{parent}\\Dress_Black.vap",
                    "Clothing Item Presets",
                    "2",
                ),
                resource(
                    f"{parent}\\dress_black.VAP",
                    "Clothing Item Presets",
                    "2",
                ),
                resource(
                    f"{parent}\\Dress_Old.vap",
                    "Clothing Item Presets",
                    "1",
                ),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
            )

        dress = result["items"][0]
        self.assertEqual(dress["variant_count"], 1)
        self.assertEqual(
            [variant["label"] for variant in dress["variants"]],
            ["Black"],
        )

    def test_related_style_owner_is_independent_of_current_page(self) -> None:
        parent = "Custom\\Clothing\\Female\\Creator\\Shared"

        def resource(
            path: str,
            resource_type: str,
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "Wardrobe",
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": "Person",
                "varVersions": ["1"],
            }

        self.write_catalogue(
            [
                resource(
                    f"{parent}\\Dress.vam",
                    "Clothing (Female)",
                ),
                resource(
                    f"{parent}\\Dress Long.vam",
                    "Clothing (Female)",
                ),
                resource(
                    f"{parent}\\Dress_Black.vap",
                    "Clothing Item Presets",
                ),
                resource(
                    f"{parent}\\Dress Long_Black.vap",
                    "Clothing Item Presets",
                ),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
                limit=1,
                offset=1,
            )

        self.assertEqual(len(result["items"]), 1)
        dress = result["items"][0]
        self.assertEqual(dress["display_name"], "Dress")
        self.assertEqual(dress["variant_count"], 1)
        self.assertEqual(
            [variant["display_name"] for variant in dress["variants"]],
            ["Dress_Black"],
        )

    def test_related_style_query_is_batched_and_uses_family_index(self) -> None:
        resources: list[dict[str, object]] = []
        for index in range(205):
            parent = f"Custom\\Clothing\\Female\\Creator\\Indexed{index:03d}"
            common = {
                "creatorName": "Creator",
                "packageName": f"Wardrobe{index:03d}",
                "presetAtomType": "Person",
                "varVersions": ["1"],
            }
            resources.extend(
                [
                    {
                        **common,
                        "resourceFullFileName": (f"{parent}\\Dress{index:03d}.vam"),
                        "resourceType": "Clothing (Female)",
                    },
                    {
                        **common,
                        "resourceFullFileName": (
                            f"{parent}\\Dress{index:03d}_Black.vap"
                        ),
                        "resourceType": "Clothing Item Presets",
                    },
                ]
            )
        self.write_catalogue(resources)

        class RecordingConnection:
            def __init__(self, wrapped: sqlite3.Connection) -> None:
                self.wrapped = wrapped
                self.related_calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(
                self,
                sql: str,
                parameters: tuple[object, ...] | list[object] = (),
            ) -> sqlite3.Cursor:
                if "WITH wanted(source, creator, package_name" in sql:
                    self.related_calls.append((sql, tuple(parameters)))
                return self.wrapped.execute(sql, parameters)

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            recording = RecordingConnection(database)
            result = search_resources(
                recording,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
                limit=500,
            )

            self.assertEqual(len(recording.related_calls), 2)
            for sql, parameters in recording.related_calls:
                self.assertLessEqual(len(parameters), 601)
                self.assertIn(
                    "CROSS JOIN catalog_resources AS resource",
                    sql,
                )
                self.assertNotIn("path_prefix", sql)
                plan = database.execute(
                    f"EXPLAIN QUERY PLAN {sql}",
                    parameters,
                )
                self.assertTrue(
                    any(
                        "USING INDEX idx_catalog_root_family" in str(row[3])
                        for row in plan
                    )
                )

        self.assertEqual(len(result["items"]), 205)
        self.assertTrue(all(item.get("variant_count") == 1 for item in result["items"]))

    def test_related_query_fetches_nested_package_family_once(self) -> None:
        resources: list[dict[str, object]] = []
        parent = "Custom\\Clothing\\Female\\Creator"
        for index in range(220):
            parent += f"\\Nested{index:03d}"
            common = {
                "creatorName": "Creator",
                "packageName": "DeepWardrobe",
                "varVersions": ["1"],
            }
            resources.extend(
                [
                    {
                        **common,
                        "resourceFullFileName": (
                            f"{parent}\\Dress{index:03d}.vam"
                        ),
                        "resourceType": "Clothing (Female)",
                        "presetAtomType": "Person",
                    },
                    {
                        **common,
                        "resourceFullFileName": (
                            f"{parent}\\Dress{index:03d}_Black.vap"
                        ),
                        "resourceType": "Clothing Item Presets",
                        "presetAtomType": "",
                    },
                ]
            )
        self.write_catalogue(resources)

        class RecordingConnection:
            def __init__(self, wrapped: sqlite3.Connection) -> None:
                self.wrapped = wrapped
                self.related_calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(
                self,
                sql: str,
                parameters: tuple[object, ...] | list[object] = (),
            ) -> sqlite3.Cursor:
                if "WITH wanted(source, creator, package_name" in sql:
                    self.related_calls.append((sql, tuple(parameters)))
                return self.wrapped.execute(sql, parameters)

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            recording = RecordingConnection(database)
            result = search_resources(
                recording,
                self.vam_root,
                resource_type="Clothing (Female)",
                include_package_state=False,
                limit=500,
            )

        self.assertEqual(len(recording.related_calls), 1)
        related_sql, related_parameters = recording.related_calls[0]
        self.assertEqual(len(related_parameters), 4)
        self.assertNotIn("path_prefix", related_sql)
        self.assertNotIn(" LIKE ", related_sql)
        self.assertEqual(len(result["items"]), 220)
        self.assertTrue(
            all(item.get("variant_count") == 1 for item in result["items"])
        )

    def test_same_type_preset_variants_use_longest_real_base_once(self) -> None:
        parent = "Custom\\Atom\\Person\\Hair\\Creator\\Bob"

        def resource(path: str) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "HairPack",
                "resourceFullFileName": path,
                "resourceType": "Preset Hair",
                "presetAtomType": "Person",
                "varVersions": ["3"],
            }

        self.write_catalogue(
            [
                resource(f"{parent}\\Preset_Bob.vap"),
                resource(f"{parent}\\Preset_Bob_Red.vap"),
                resource(f"{parent}\\Preset_Bob-Blue.vap"),
                resource(f"{parent}\\Preset_Bob_Red_Shiny.vap"),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                resource_type="Preset Hair",
                include_package_state=False,
            )

        by_name = {item["display_name"]: item for item in result["items"]}
        bob = by_name["Bob"]
        red = by_name["Bob_Red"]
        self.assertEqual(bob["variant_group"], "related-resources")
        self.assertEqual(bob["variant_count"], 2)
        self.assertEqual(
            [variant["display_name"] for variant in bob["variants"]],
            ["Bob-Blue", "Bob_Red"],
        )
        self.assertNotIn(bob["id"], {variant["id"] for variant in bob["variants"]})
        self.assertEqual(red["variant_count"], 1)
        self.assertEqual(
            [variant["display_name"] for variant in red["variants"]],
            ["Bob_Red_Shiny"],
        )
        self.assertNotIn(
            by_name["Bob_Red_Shiny"]["id"],
            {variant["id"] for variant in bob["variants"]},
        )
        all_child_ids = [
            variant["id"]
            for item in result["items"]
            for variant in item.get("variants", [])
        ]
        self.assertEqual(len(all_child_ids), len(set(all_child_ids)))
        self.assertTrue(
            all(
                variant["relationship_kind"] == "preset-variant"
                for item in result["items"]
                for variant in item.get("variants", [])
            )
        )

    def test_preset_variants_do_not_cross_family_folder_version_or_atom(self) -> None:
        owner_path = "Custom\\Atom\\Person\\Hair\\Creator\\Shared\\Preset_Bob.vap"

        def resource(
            package: str,
            path: str,
            version: str,
            *,
            resource_type: str = "Preset Hair",
            atom_type: str = "Person",
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": package,
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": atom_type,
                "varVersions": [version],
            }

        self.write_catalogue(
            [
                resource("HairPack", owner_path, "2"),
                resource(
                    "hairpack",
                    owner_path.replace(".vap", "_PackageCase.vap"),
                    "2",
                ),
                resource(
                    "HairPack",
                    owner_path.replace("\\Shared\\", "\\Elsewhere\\").replace(
                        ".vap", "_OtherFolder.vap"
                    ),
                    "2",
                ),
                resource(
                    "HairPack",
                    owner_path.replace("\\Shared\\", "\\shared\\").replace(
                        ".vap", "_FolderCase.vap"
                    ),
                    "2",
                ),
                resource(
                    "HairPack",
                    owner_path.replace(".vap", "_OldVersion.vap"),
                    "1",
                ),
                resource(
                    "HairPack",
                    owner_path.replace(".vap", "_OtherAtom.vap"),
                    "2",
                    atom_type="Hair",
                ),
                resource(
                    "HairPack",
                    owner_path.replace("Preset_Bob", "Preset_Bobcat"),
                    "2",
                ),
                resource(
                    "HairPack",
                    owner_path.replace(".vap", "_OtherType.vap"),
                    "2",
                    resource_type="Preset Clothing",
                ),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                query="Preset_Bob.vap",
                include_package_state=False,
            )

        self.assertEqual(result["total"], 1)
        self.assertNotIn("variants", result["items"][0])

    def test_generic_variant_types_are_intentionally_narrow(self) -> None:
        def resource(
            resource_type: str,
            path: str,
        ) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "Looks",
                "resourceFullFileName": path,
                "resourceType": resource_type,
                "presetAtomType": "Person",
                "varVersions": ["1"],
            }

        self.write_catalogue(
            [
                resource(
                    "Preset Appearance",
                    "Custom\\Atom\\Person\\Appearance\\Preset_Look.vap",
                ),
                resource(
                    "Preset Appearance",
                    "Custom\\Atom\\Person\\Appearance\\Preset_Look_Red.vap",
                ),
                resource(
                    "Preset Skin",
                    "Custom\\Atom\\Person\\Skin\\Preset_Skin.vap",
                ),
                resource(
                    "Preset Skin",
                    "Custom\\Atom\\Person\\Skin\\Preset_Skin_Tan.vap",
                ),
            ]
        )

        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            result = search_resources(
                database,
                self.vam_root,
                include_package_state=False,
            )

        self.assertTrue(
            all("variants" not in item for item in result["items"])
        )

    def test_variant_package_state_is_exact_safe_and_bounded(self) -> None:
        parent = "Custom\\Atom\\Person\\Hair\\Creator\\Bob"
        base_member = f"{parent}\\Preset_Bob.vap".replace("\\", "/")
        old_child_member = f"{parent}\\Preset_Bob_Red.vap".replace("\\", "/")
        make_var(
            self.addons / "Creator.HairPack.1.var",
            creator="Creator",
            package="HairPack",
            members={
                base_member: b"{}",
                old_child_member: b"{}",
            },
        )
        make_var(
            self.addons / "Creator.HairPack.2.var",
            creator="Creator",
            package="HairPack",
            members={base_member: b"{}"},
        )

        def resource(path: str) -> dict[str, object]:
            return {
                "creatorName": "Creator",
                "packageName": "HairPack",
                "resourceFullFileName": path,
                "resourceType": "Preset Hair",
                "presetAtomType": "Person",
                "varVersions": ["1", "2"],
            }

        resources = [
            resource(f"{parent}\\Preset_Bob.vap"),
            resource(f"{parent}\\Preset_Bob_Red.vap"),
        ]
        self.write_catalogue(resources)

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            exact = search_resources(
                database,
                self.vam_root,
                resource_type="Preset Hair",
            )
            without_state = search_resources(
                database,
                self.vam_root,
                query="Preset_Bob.vap",
                include_package_state=False,
            )

        bob = next(
            item for item in exact["items"] if item["display_name"] == "Bob"
        )
        variant = bob["variants"][0]
        self.assertEqual(bob["selected_version"], "2")
        self.assertEqual(variant["selected_version"], "1")
        self.assertEqual(variant["package_ref"], "Creator.HairPack.1")
        self.assertTrue(variant["enabled"])
        self.assertFalse(variant["missing"])
        self.assertNotIn("resolved_resource_ref", variant)
        self.assertNotIn("path", variant)
        self.assertNotIn("package_ref", without_state["items"][0]["variants"][0])

        many_resources = [
            resource(f"{parent}\\Preset_Bob.vap"),
            *[
                resource(f"{parent}\\Preset_Bob_Color{index:02d}.vap")
                for index in range(14)
            ],
        ]
        self.write_catalogue(many_resources)
        with connect(self.state) as database:
            import_browserassist(database, self.vam_root)
            state = {
                "package_ref": "Creator.HairPack.1",
                "selected_version": "1",
                "enabled": True,
                "missing": False,
                "resolved_resource_ref": "private-reference",
            }
            with mock.patch(
                "vampip.catalog._ResourceResolver.resource_state",
                autospec=True,
                return_value=state,
            ) as resource_state:
                bounded = search_resources(
                    database,
                    self.vam_root,
                    query="Preset_Bob.vap",
                    limit=1,
                )

        bounded_owner = bounded["items"][0]
        self.assertEqual(bounded_owner["variant_count"], 14)
        self.assertEqual(len(bounded_owner["variants"]), 12)
        self.assertEqual(resource_state.call_count, 13)
        self.assertTrue(
            all(
                "resolved_resource_ref" not in variant
                for variant in bounded_owner["variants"]
            )
        )

    def test_connect_migrates_legacy_catalog_clothing_metadata_column(
        self,
    ) -> None:
        self.state.mkdir(parents=True)
        legacy_path = self.state / "inventory.sqlite3"
        legacy = sqlite3.connect(legacy_path)
        try:
            legacy.executescript(
                """
                CREATE TABLE schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT INTO schema_meta(key, value)
                VALUES ('schema_version', '3');

                CREATE TABLE catalog_resources (
                    id INTEGER PRIMARY KEY,
                    root TEXT NOT NULL,
                    source TEXT NOT NULL,
                    resource_key TEXT NOT NULL,
                    creator TEXT NOT NULL,
                    package_name TEXT NOT NULL,
                    versions_json TEXT NOT NULL DEFAULT '[]',
                    resource_path TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    atom_type TEXT NOT NULL DEFAULT '',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    imported_utc TEXT NOT NULL,
                    UNIQUE(root, source, resource_key)
                );
                """
            )
            legacy.execute(
                """
                INSERT INTO catalog_resources (
                    root, source, resource_key, creator, package_name,
                    versions_json, resource_path, resource_type, atom_type,
                    favorite, hidden, tags_json, imported_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(self.vam_root.resolve()),
                    "browserassist",
                    "legacy-key",
                    "Creator",
                    "Wardrobe",
                    '["1"]',
                    "Custom\\Clothing\\Female\\Creator\\Dress\\Dress.vam",
                    "Clothing (Female)",
                    "Person",
                    0,
                    0,
                    "[]",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            legacy.commit()
        finally:
            legacy.close()

        with connect(self.state) as database:
            columns = {
                row["name"]
                for row in database.execute("PRAGMA table_info(catalog_resources)")
            }
            self.assertIn("clothing_versions_json", columns)
            self.assertEqual(
                database.execute(
                    """
                    SELECT clothing_versions_json
                    FROM catalog_resources
                    WHERE resource_key = 'legacy-key'
                    """
                ).fetchone()[0],
                "[]",
            )
            self.assertEqual(
                database.execute(
                    """
                    SELECT value FROM schema_meta
                    WHERE key = 'schema_version'
                    """
                ).fetchone()[0],
                str(SCHEMA_VERSION),
            )

    def test_package_state_uses_the_version_that_contains_the_resource(self) -> None:
        versioned_path = "Saves\\scene\\Versioned.json"
        active_path = "Saves\\scene\\Active.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Bundle",
                    "resourceFullFileName": versioned_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1", "2"],
                },
                {
                    "creatorName": "Creator",
                    "packageName": "ActiveOnly",
                    "resourceFullFileName": active_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                },
            ]
        )
        hidden_path = self.addons / "Creator.Bundle.1.var"
        make_var(
            hidden_path,
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Versioned.json": b"{}"},
        )
        hidden_path.rename(Path(f"{hidden_path}.vampip-disabled"))
        make_var(
            self.addons / "Creator.Bundle.2.var",
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Other.json": b"{}"},
        )
        active_only_archive = self.addons / "Creator.ActiveOnly.1.var"
        make_var(
            active_only_archive,
            creator="Creator",
            package="ActiveOnly",
            members={"Saves/scene/Active.json": b"{}"},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)

            real_zip_file = zipfile.ZipFile
            opened_archives: list[Path] = []

            def tracking_zip_file(path, *args, **kwargs):
                opened_archives.append(Path(path))
                return real_zip_file(path, *args, **kwargs)

            with mock.patch(
                "vampip.catalog.zipfile.ZipFile",
                side_effect=tracking_zip_file,
            ):
                hidden = search_resources(
                    database,
                    self.vam_root,
                    addon_root=self.addons,
                    package_state="hidden",
                )

            self.assertEqual(hidden["total"], 1)
            hidden_item = hidden["items"][0]
            self.assertEqual(hidden_item["package_ref"], "Creator.Bundle.1")
            self.assertEqual(hidden_item["selected_version"], "1")
            self.assertFalse(hidden_item["enabled"])
            self.assertNotIn(active_only_archive, opened_archives)

            active = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="active",
            )
            self.assertEqual(active["total"], 1)
            self.assertEqual(active["items"][0]["package"], "ActiveOnly")
            self.assertTrue(active["items"][0]["enabled"])

    def test_resource_resolver_lazily_caches_only_requested_family(self) -> None:
        resource_path = "Saves\\scene\\Wanted.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Wanted",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                }
            ]
        )
        make_var(
            self.addons / "Creator.Wanted.1.var",
            creator="Creator",
            package="Wanted",
            members={"Saves/scene/Wanted.json": b"{}"},
        )
        make_var(
            self.addons / "Other.Unrelated.1.var",
            creator="Other",
            package="Unrelated",
            members={"Saves/scene/Unrelated.json": b"{}"},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            resource = database.execute(
                """
                SELECT * FROM catalog_resources
                WHERE root = ? AND resource_path = ?
                """,
                (str(self.vam_root), resource_path),
            ).fetchone()
            assert resource is not None
            resolver = _ResourceResolver(
                database,
                self.vam_root,
                addon_root=self.addons,
            )
            self.assertEqual(resolver.packages, {})

            statements: list[str] = []
            database.set_trace_callback(statements.append)
            try:
                first = resolver.candidates(resource)
                second = resolver.candidates(resource)
            finally:
                database.set_trace_callback(None)

        self.assertEqual([row["package_name"] for row in first], ["Wanted"])
        self.assertEqual([row["package_name"] for row in second], ["Wanted"])
        self.assertEqual(set(resolver.packages), {("creator", "wanted")})
        family_queries = [
            " ".join(statement.split()).casefold()
            for statement in statements
            if "from package_files" in statement.casefold()
        ]
        self.assertEqual(len(family_queries), 1)
        self.assertIn("and creator = 'creator' collate nocase", family_queries[0])
        self.assertIn(
            "and package_name = 'wanted' collate nocase",
            family_queries[0],
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
                "./Saves/scene/Versioned.json": b"{}",
                "./Saves/scene/Versioned.JPG": jpeg,
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
            self.assertEqual(location.archive_member, "./Saves/scene/Versioned.json")
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

    def test_thumbnail_can_be_pinned_to_one_exact_installed_version(self) -> None:
        resource_path = "Custom\\Atom\\Person\\Appearance\\Preset_Ada.vap"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Looks",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Preset Appearance",
                    "presetAtomType": "Person",
                    "varVersions": ["1", "2"],
                }
            ]
        )
        thumbnails = {
            "1": b"\xff\xd8\xff\xe0version-one",
            "2": b"\xff\xd8\xff\xe0version-two",
        }
        for version, thumbnail in thumbnails.items():
            make_var(
                self.addons / f"Creator.Looks.{version}.var",
                creator="Creator",
                package="Looks",
                members={
                    resource_path: b"{}",
                    resource_path.rsplit(".", 1)[0] + ".jpg": thumbnail,
                },
            )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            resource_id = int(
                search_resources(database, self.vam_root)["items"][0]["id"]
            )
            version_one = get_resource_thumbnail(
                database,
                self.vam_root,
                resource_id,
                self.cache,
                addon_root=self.addons,
                version_text="1",
            )
            version_two = get_resource_thumbnail(
                database,
                self.vam_root,
                resource_id,
                self.cache,
                addon_root=self.addons,
                version_text="2",
            )

        assert version_one is not None
        assert version_two is not None
        self.assertEqual(version_one.version_text, "1")
        self.assertEqual(version_two.version_text, "2")
        self.assertEqual(version_one.path.read_bytes(), thumbnails["1"])
        self.assertEqual(version_two.path.read_bytes(), thumbnails["2"])
        self.assertNotEqual(version_one.etag, version_two.etag)

    def test_resolver_adopts_newer_inventory_version_with_exact_member(
        self,
    ) -> None:
        resource_path = "Saves\\scene\\Versioned.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Bundle",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["1"],
                }
            ]
        )
        make_var(
            self.addons / "Creator.Bundle.1.var",
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Versioned.json": b'{"version":1}'},
        )

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            original = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(original["selected_version"], "1")
            (self.addons / "Creator.Bundle.1.var").unlink()

            make_var(
                self.addons / "Creator.Bundle.2.var",
                creator="Creator",
                package="Bundle",
                members={"Saves/scene/Versioned.json": b'{"version":2}'},
            )
            make_var(
                self.addons / "Creator.Bundle.3.var",
                creator="Creator",
                package="Bundle",
                members={"Saves/scene/Removed.json": b"{}"},
            )
            scan(self.addons, database)

            listed = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(listed["selected_version"], "2")
            self.assertEqual(listed["package_ref"], "Creator.Bundle.2")
            self.assertFalse(listed["missing"])

            active = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="active",
            )
            self.assertEqual(active["total"], 1)
            self.assertEqual(
                active["items"][0]["package_ref"],
                "Creator.Bundle.2",
            )
            missing = search_resources(
                database,
                self.vam_root,
                addon_root=self.addons,
                package_state="missing",
            )
            self.assertEqual(missing["total"], 0)

            location = resolve_resource_archive(
                database,
                self.vam_root,
                listed["id"],
            )
            self.assertIsNotNone(location)
            assert location is not None
            self.assertEqual(location.version_text, "2")
            self.assertEqual(
                location.archive_member,
                "Saves/scene/Versioned.json",
            )
            self.assertEqual(
                [
                    row["version_text"]
                    for row in database.execute(
                        """
                        SELECT version_text
                        FROM catalog_resource_versions
                        WHERE resource_id = ?
                        """,
                        (listed["id"],),
                    )
                ],
                ["1"],
            )

    def test_active_resource_advertises_hidden_newer_exact_member_update(
        self,
    ) -> None:
        resource_path = "Saves\\scene\\Versioned.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Bundle",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["2"],
                }
            ]
        )
        make_var(
            self.addons / "Creator.Bundle.2.var",
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Versioned.json": b'{"version":2}'},
        )
        update = self.addons / "Creator.Bundle.4.var"
        make_var(
            update,
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Versioned.json": b'{"version":4}'},
        )
        update.rename(Path(f"{update}.vampip-disabled"))

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)

            listed = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(listed["selected_version"], "2")
            self.assertEqual(listed["package_ref"], "Creator.Bundle.2")
            self.assertTrue(listed["enabled"])
            self.assertFalse(listed["missing"])
            self.assertTrue(listed["update_available"])
            self.assertEqual(listed["update_version"], 4)
            self.assertEqual(
                listed["update_package_ref"],
                "Creator.Bundle.4",
            )

            exact_update = resolve_resource_archive(
                database,
                self.vam_root,
                listed["id"],
                version_text="4",
            )
            self.assertIsNotNone(exact_update)
            assert exact_update is not None
            self.assertEqual(exact_update.version_text, "4")
            self.assertEqual(
                exact_update.archive_member,
                "Saves/scene/Versioned.json",
            )
            self.assertFalse(exact_update.enabled)

    def test_newer_package_without_member_is_not_a_resource_update(self) -> None:
        resource_path = "Saves\\scene\\Versioned.json"
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": "Bundle",
                    "resourceFullFileName": resource_path,
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["2"],
                }
            ]
        )
        make_var(
            self.addons / "Creator.Bundle.2.var",
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Versioned.json": b'{"version":2}'},
        )
        update = self.addons / "Creator.Bundle.4.var"
        make_var(
            update,
            creator="Creator",
            package="Bundle",
            members={"Saves/scene/Other.json": b'{"version":4}'},
        )
        update.rename(Path(f"{update}.vampip-disabled"))

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)

            listed = search_resources(database, self.vam_root)["items"][0]
            self.assertEqual(listed["selected_version"], "2")
            self.assertFalse(listed["missing"])
            self.assertFalse(listed["update_available"])
            self.assertIsNone(listed["update_version"])
            self.assertIsNone(listed["update_package_ref"])
            self.assertIsNone(
                resolve_resource_archive(
                    database,
                    self.vam_root,
                    listed["id"],
                    version_text="4",
                )
            )

    def test_ambiguous_newer_archive_member_is_not_offered_as_update(
        self,
    ) -> None:
        member = "Saves/scene/Versioned.json"
        collisions = {
            "ExactCollision": member,
            "CaseCollision": "Saves/scene/versioned.json",
            "DotCollision": f"./{member}",
        }
        self.write_catalogue(
            [
                {
                    "creatorName": "Creator",
                    "packageName": package,
                    "resourceFullFileName": member.replace("/", "\\"),
                    "resourceType": "Scene",
                    "presetAtomType": "",
                    "varVersions": ["2"],
                }
                for package in collisions
            ]
        )
        for package, collision in collisions.items():
            make_var(
                self.addons / f"Creator.{package}.2.var",
                creator="Creator",
                package=package,
                members={member: b'{"version":2}'},
            )
            update = self.addons / f"Creator.{package}.4.var"
            metadata = {
                "creatorName": "Creator",
                "packageName": package,
                "dependencies": {},
            }
            with (
                warnings.catch_warnings(),
                zipfile.ZipFile(update, "w", zipfile.ZIP_DEFLATED) as archive,
            ):
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("meta.json", json.dumps(metadata))
                archive.writestr(member, b'{"copy":1}')
                archive.writestr(collision, b'{"copy":2}')
            update.rename(Path(f"{update}.vampip-disabled"))

        with connect(self.state) as database:
            scan(self.addons, database)
            import_browserassist(database, self.vam_root)
            listed = search_resources(database, self.vam_root)["items"]
            self.assertEqual(len(listed), len(collisions))
            for item in listed:
                with self.subTest(package=item["package"]):
                    self.assertEqual(item["selected_version"], "2")
                    self.assertFalse(item["update_available"])
                    self.assertIsNone(
                        resolve_resource_archive(
                            database,
                            self.vam_root,
                            item["id"],
                            version_text="4",
                        )
                    )


if __name__ == "__main__":
    unittest.main()

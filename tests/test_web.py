from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import quote

from vampip.service import ManagerService
from vampip.web import ManagerHTTPServer

from tests.test_vampip import make_var


def write_web_session_defaults(vam_root: Path) -> Path:
    path = vam_root / "Custom" / "PluginPresets" / "Plugins_UserDefaults.vap"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "storables": [
                    {
                        "id": "PluginManager",
                        "plugins": {
                            "plugin#0": (
                                "Creator.Package.1:/Custom/Scripts/"
                                "Package/Package.cslist"
                            ),
                            "plugin#1": (
                                "Missing.Disabled.1:/Custom/Scripts/"
                                "Missing/Missing.cslist"
                            ),
                            "plugin#2": ("Custom/Scripts/Loose/Loose.cslist"),
                        },
                    },
                    {"id": "plugin#0_Package", "enabled": True},
                    {"id": "plugin#1_Missing", "enabled": False},
                    {"id": "plugin#2_Loose", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


class WebSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.vam_root = base / "VaM"
        self.addons = self.vam_root / "AddonPackages"
        self.addons.mkdir(parents=True)
        self.state = base / "state"
        make_var(
            self.addons / "Creator.Package.1.var",
            creator="Creator",
            package="Package",
        )
        service = ManagerService(
            self.addons,
            self.state,
            process_probe=lambda: [],
        )
        self.token = "test-token-that-is-long-enough-for-the-manager"
        self.server = ManagerHTTPServer(
            ("127.0.0.1", 0),
            service,
            self.token,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_address[1],
            timeout=10,
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def response_json(self, response) -> dict[str, object]:
        return json.loads(response.read().decode("utf-8"))

    def test_api_requires_token_and_accepts_authenticated_loopback(self) -> None:
        self.connection.request("GET", "/api/status")
        unauthorized = self.connection.getresponse()
        self.assertEqual(unauthorized.status, 401)
        unauthorized.read()

        self.connection.request(
            "GET",
            "/api/status",
            headers={"X-VAMPIP-Token": self.token},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        document = self.response_json(response)
        self.assertEqual(document["packages"]["total"], 1)

    def test_activity_endpoint_is_authenticated_and_reports_live_state(self) -> None:
        self.connection.request("GET", "/api/activity")
        unauthorized = self.connection.getresponse()
        self.assertEqual(unauthorized.status, 401)
        unauthorized.read()

        self.connection.request(
            "GET",
            "/api/activity",
            headers={"X-VAMPIP-Token": self.token},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        document = self.response_json(response)
        self.assertEqual(len(document["manager_instance"]), 32)
        self.assertFalse(document["vam"]["running"])
        self.assertEqual(document["vam"]["pids"], [])
        self.assertFalse(document["operation"]["busy"])
        self.assertEqual(document["operation"]["status"], "idle")

    def test_timeline_routes_are_authenticated_and_use_only_opaque_controls(
        self,
    ) -> None:
        timeline = {
            "available": True,
            "instances": [
                {
                    "id": "1" * 32,
                    "revision": "2" * 32,
                    "clips": [{"id": "3" * 32, "name": "Idle"}],
                }
            ],
        }
        control_result = {"bridge_request": "timeline-request"}
        self.server.service.timeline = mock.Mock(return_value=timeline)
        self.server.service.control_timeline = mock.Mock(
            return_value=control_result
        )

        self.connection.request("GET", "/api/vam/timeline")
        unauthorized = self.connection.getresponse()
        self.assertEqual(unauthorized.status, 401)
        unauthorized.read()

        headers = {"X-VAMPIP-Token": self.token}
        self.connection.request(
            "GET",
            "/api/vam/timeline",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), timeline)

        body = json.dumps(
            {
                "timeline_id": "1" * 32,
                "expected_revision": "2" * 32,
                "op": "selectClip",
                "clip_id": "3" * 32,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/timeline/control",
            body=body,
            headers={
                **headers,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), control_result)
        self.server.service.control_timeline.assert_called_once_with(
            timeline_id="1" * 32,
            expected_revision="2" * 32,
            operation="selectClip",
            value=None,
            clip_id="3" * 32,
            segment_id=None,
            layer_id=None,
        )

    def test_timeline_control_route_rejects_arbitrary_vam_names(self) -> None:
        self.server.service.control_timeline = mock.Mock(return_value={})
        body = json.dumps(
            {
                "timeline_id": "1" * 32,
                "expected_revision": "2" * 32,
                "op": "play",
                "storable_name": "Anything",
                "action_name": "Delete",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/timeline/control",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        payload = self.response_json(response)
        self.assertIn("unsupported Timeline control field", payload["error"])
        self.server.service.control_timeline.assert_not_called()

    def test_mutation_rejects_foreign_origin(self) -> None:
        body = json.dumps({"apply": False}).encode()
        self.connection.request(
            "POST",
            "/api/reconcile",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-VAMPIP-Token": self.token,
                "Origin": "https://example.com",
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()

    def test_static_response_has_lockdown_headers(self) -> None:
        self.connection.request("GET", "/")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.getheader("Cross-Origin-Resource-Policy"),
            "same-origin",
        )
        self.assertIn(
            "frame-ancestors 'none'", response.getheader("Content-Security-Policy")
        )
        document = response.read().decode("utf-8")
        self.assertIn("/styles.css?v=0.12.2", document)
        self.assertIn("/app.js?v=0.12.2", document)

    def test_session_plugin_endpoints_report_and_import_defaults(self) -> None:
        preset_path = write_web_session_defaults(self.vam_root)
        headers = {"X-VAMPIP-Token": self.token}

        self.connection.request(
            "GET",
            "/api/session-plugins",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        document = self.response_json(response)
        self.assertEqual(document["preset"], str(preset_path))
        self.assertTrue(document["exists"])
        self.assertEqual(
            document["enabled_packaged_roots"],
            ["Creator.Package.1"],
        )
        self.assertEqual(
            document["counts"],
            {
                "total": 3,
                "enabled": 2,
                "packaged": 2,
                "enabled_packaged": 1,
                "loose": 1,
                "already_pinned": 0,
                "missing": 0,
            },
        )

        body = json.dumps({"include_disabled": False, "apply": False}).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/session-plugins/import",
            body=body,
            headers={
                **headers,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        imported = self.response_json(response)
        self.assertEqual(imported["roots"], ["Creator.Package.1"])
        self.assertEqual(imported["pinned"], 1)
        self.assertEqual(imported["already_pinned"], 0)
        self.assertEqual(imported["resolved_packages"], 1)
        self.assertFalse(imported["applied"])

        self.connection.request("GET", "/api/status", headers=headers)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        status = self.response_json(response)
        self.assertEqual(
            [pin["root_ref"] for pin in status["pins"]],
            ["Creator.Package.1"],
        )

    def test_session_plugin_import_requires_boolean_flags(self) -> None:
        write_web_session_defaults(self.vam_root)
        body = json.dumps({"include_disabled": "false", "apply": False}).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/session-plugins/import",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )

        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("include_disabled must be a boolean", document["error"])

    def test_mutating_routes_require_strict_boolean_flags(self) -> None:
        cases = (
            (
                "/api/scan",
                {"catalog": "false"},
                "catalog",
                "scan_packages",
            ),
            (
                "/api/pins",
                {"roots": ["Creator.Package.1"], "apply": "false"},
                "apply",
                "pin",
            ),
            (
                "/api/leases",
                {"roots": ["Creator.Package.1"], "apply": "false"},
                "apply",
                "lease",
            ),
            (
                "/api/resources/1/lease",
                {"apply": "false"},
                "apply",
                "lease_resource",
            ),
            (
                "/api/reconcile",
                {"apply": "false"},
                "apply",
                "reconcile",
            ),
            (
                "/api/reconcile",
                {"activate": "false"},
                "activate",
                "reconcile",
            ),
            (
                "/api/deactivate",
                {"apply": "false"},
                "apply",
                "deactivate",
            ),
            (
                "/api/settings",
                {"auto_reconcile": "false"},
                "auto_reconcile",
                "set_auto_reconcile",
            ),
            (
                "/api/vam/launch",
                {"reconcile": "false"},
                "reconcile",
                "launch_vam",
            ),
        )
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }

        for route, document, field, service_method in cases:
            with self.subTest(route=route, field=field):
                body = json.dumps(document).encode("utf-8")
                with mock.patch.object(
                    self.server.service,
                    service_method,
                    return_value={},
                ) as operation:
                    self.connection.request(
                        "POST",
                        route,
                        body=body,
                        headers={**headers, "Content-Length": str(len(body))},
                    )
                    response = self.connection.getresponse()
                    self.assertEqual(response.status, 400)
                    payload = self.response_json(response)
                    self.assertIn(f"{field} must be a boolean", payload["error"])
                    operation.assert_not_called()

    def test_person_routes_expose_roster_and_accept_only_catalog_identity(self) -> None:
        roster = {
            "available": True,
            "persons": [{"uid": "Person", "selected": True}],
            "capabilities": ["person-roster", "person-preset-apply"],
        }
        apply_result = {
            "resource_id": 42,
            "target_uid": "Person",
            "bridge_request": "request-id",
        }
        self.server.service.persons = mock.Mock(return_value=roster)
        self.server.service.apply_person_resource = mock.Mock(return_value=apply_result)
        headers = {"X-VAMPIP-Token": self.token}

        self.connection.request("GET", "/api/vam/persons", headers=headers)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), roster)

        body = json.dumps(
            {
                "resource_id": 42,
                "target_uid": "Person",
                "days": 3,
                # A caller-supplied path is deliberately not part of the API.
                "resource_ref": "/tmp/attacker-selected.vap",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/person/apply",
            body=body,
            headers={
                **headers,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), apply_result)
        self.server.service.apply_person_resource.assert_called_once_with(
            42,
            target_uid="Person",
            days=3.0,
            merge=False,
            confirm_critical=False,
        )

    def test_person_equipment_route_authenticates_validates_and_adds_thumbnails(
        self,
    ) -> None:
        equipment = {
            "available": True,
            "target_uid": "Person 2",
            "revision": "a" * 32,
            "ready": True,
            "gender": "Female",
            "active_count": 1,
            "locked_count": 0,
            "identified_count": 1,
            "unidentified_count": 0,
            "truncated": False,
            "complete": True,
            "items": [
                {
                    "id": 42,
                    "display_name": "Shirt",
                    "creator": "Creator",
                    "package": "Clothes",
                    "resource_type": "Clothing (Female)",
                    "tags": ["Tops"],
                    "slot": "upper-body",
                    "locked": False,
                    "package_version": 2,
                    "local": False,
                    "state": "active",
                }
            ],
        }
        self.server.service.person_equipment = mock.Mock(return_value=equipment)

        self.connection.request(
            "GET",
            "/api/vam/person/equipment?target_uid=Person%202",
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 401)
        response.read()
        self.server.service.person_equipment.assert_not_called()

        headers = {"X-VAMPIP-Token": self.token}
        self.connection.request(
            "GET",
            "/api/vam/person/equipment",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        missing = self.response_json(response)
        self.assertIn("target_uid must be supplied exactly once", missing["error"])
        self.server.service.person_equipment.assert_not_called()

        self.connection.request(
            "GET",
            "/api/vam/person/equipment?target_uid=Person%202&path=%2Ftmp",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        unsupported = self.response_json(response)
        self.assertIn(
            "unsupported Person equipment query field",
            unsupported["error"],
        )
        self.server.service.person_equipment.assert_not_called()

        self.connection.request(
            "GET",
            "/api/vam/person/equipment?target_uid=Person%202",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        document = self.response_json(response)
        self.assertEqual(document["target_uid"], "Person 2")
        self.assertEqual(
            document["items"][0]["thumbnail_url"],
            f"/api/resources/42/thumbnail?token={self.token}",
        )
        self.server.service.person_equipment.assert_called_once_with("Person 2")

    def test_person_hair_route_authenticates_and_allowlists_query(self) -> None:
        hair = {
            "available": True,
            "target_uid": "Person 2",
            "revision": "b" * 32,
            "ready": True,
            "active_count": 1,
            "locked_count": 0,
            "truncated": False,
            "complete": True,
            "items": [
                {
                    "key": "hair-opaque",
                    "actionable": False,
                    "display_name": "Soft Bob",
                    "tags": ["Sim"],
                    "locked": False,
                    "simulated": True,
                    "state": "in-game",
                }
            ],
        }
        self.server.service.person_hair = mock.Mock(return_value=hair)

        self.connection.request(
            "GET",
            "/api/vam/person/hair?target_uid=Person%202",
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 401)
        response.read()
        self.server.service.person_hair.assert_not_called()

        headers = {"X-VAMPIP-Token": self.token}
        self.connection.request(
            "GET",
            "/api/vam/person/hair?target_uid=Person%202&resourceRef=secret",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("unsupported Person hair query field", document["error"])
        self.server.service.person_hair.assert_not_called()

        self.connection.request(
            "GET",
            "/api/vam/person/hair?target_uid=Person%202",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), hair)
        self.server.service.person_hair.assert_called_once_with("Person 2")

    def test_person_hair_remove_route_accepts_only_opaque_public_state(
        self,
    ) -> None:
        revision = "b" * 32
        item_key = "hair-" + "1" * 24
        result = {
            "operation": "set-person-hair",
            "target_uid": "Person 2",
            "revision": revision,
            "item_key": item_key,
            "active": False,
            "bridge_request": "hair-remove-request",
            "bridge_busy": False,
            "bridge_message": None,
        }
        self.server.service.set_person_hair = mock.Mock(return_value=result)
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        body = json.dumps(
            {
                "target_uid": "Person 2",
                "revision": revision,
                "item_key": item_key,
                "active": False,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/person/hair",
            body=body,
            headers={**headers, "Content-Length": str(len(body))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), result)
        self.server.service.set_person_hair.assert_called_once_with(
            target_uid="Person 2",
            revision=revision,
            item_key=item_key,
            active=False,
        )

        for forbidden_document, message in (
            (
                {
                    "target_uid": "Person 2",
                    "revision": revision,
                    "item_key": item_key,
                    "active": False,
                    "action_token": "f" * 32,
                },
                "unsupported Person hair field",
            ),
            (
                {
                    "target_uid": "Person 2",
                    "revision": revision,
                    "item_key": item_key,
                    "active": True,
                },
                "only be removed",
            ),
        ):
            with self.subTest(message=message):
                forbidden = json.dumps(forbidden_document).encode("utf-8")
                self.connection.request(
                    "POST",
                    "/api/vam/person/hair",
                    body=forbidden,
                    headers={
                        **headers,
                        "Content-Length": str(len(forbidden)),
                    },
                )
                response = self.connection.getresponse()
                self.assertEqual(response.status, 400)
                document = self.response_json(response)
                self.assertIn(message, document["error"])
        self.assertEqual(self.server.service.set_person_hair.call_count, 1)

    def test_clothing_route_accepts_only_opaque_catalog_state(self) -> None:
        result = {
            "resource_id": 42,
            "target_uid": "Person",
            "active": True,
            "bridge_request": "clothing-request",
        }
        self.server.service.set_person_clothing = mock.Mock(return_value=result)
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        revision = "a" * 32
        body = json.dumps(
            {
                "resource_id": 42,
                "target_uid": "Person",
                "active": True,
                "revision": revision,
                "days": 2,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/person/clothing",
            body=body,
            headers={**headers, "Content-Length": str(len(body))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), result)
        self.server.service.set_person_clothing.assert_called_once_with(
            42,
            target_uid="Person",
            active=True,
            revision=revision,
            days=2.0,
        )

        forbidden = json.dumps(
            {
                "resource_id": 42,
                "target_uid": "Person",
                "active": False,
                "revision": revision,
                "resource_ref": (
                    "Attacker.Package.1:/Custom/Clothing/Female/Attacker/Injected.vam"
                ),
                "clothing_uid": "Attacker:Injected",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/person/clothing",
            body=forbidden,
            headers={**headers, "Content-Length": str(len(forbidden))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("unsupported Person clothing field", document["error"])
        self.assertEqual(self.server.service.set_person_clothing.call_count, 1)

    def test_resource_search_forwards_only_the_selected_person_uid(self) -> None:
        self.server.service.search_resources = mock.Mock(
            return_value={"items": [], "total": 0}
        )
        headers = {"X-VAMPIP-Token": self.token}
        self.connection.request(
            "GET",
            "/api/resources?category=clothing-items-female"
            "&target_uid=Person%202&limit=20",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response)["items"], [])
        self.server.service.search_resources.assert_called_once_with(
            query="",
            resource_types=[],
            category="clothing-items-female",
            state="all",
            favorite=None,
            target_uid="Person 2",
            limit=20,
            offset=0,
        )

    def test_resource_search_adds_thumbnails_to_numeric_variants_only(self) -> None:
        special_token = "test token/+?&=#% with-special-characters"
        self.server.api_token = special_token
        self.server.service.search_resources = mock.Mock(
            return_value={
                "items": [
                    {
                        "id": 42,
                        "variants": [
                            {"id": 73, "label": "Red"},
                            {"id": True, "label": "Boolean"},
                            {"id": -4, "label": "Negative"},
                            {"id": "81", "label": "String"},
                        ],
                    },
                    {"id": 43, "variants": None},
                    {"id": 44, "variants": {"id": 74}},
                    {"id": 45, "variants": "not-a-list"},
                    {"id": 46, "variants": ({"id": 75},)},
                ],
                "total": 5,
            }
        )
        headers = {"X-VAMPIP-Token": special_token}
        self.connection.request("GET", "/api/resources", headers=headers)
        response = self.connection.getresponse()

        self.assertEqual(response.status, 200)
        document = self.response_json(response)
        item = document["items"][0]
        encoded_token = quote(special_token, safe="")
        self.assertEqual(
            item["thumbnail_url"],
            f"/api/resources/42/thumbnail?token={encoded_token}",
        )
        self.assertEqual(
            item["variants"][0]["thumbnail_url"],
            f"/api/resources/73/thumbnail?token={encoded_token}",
        )
        self.assertTrue(
            all(
                "thumbnail_url" not in variant
                for variant in item["variants"][1:]
            )
        )
        self.assertIsNone(document["items"][1]["variants"])
        self.assertNotIn("thumbnail_url", document["items"][2]["variants"])
        self.assertEqual(document["items"][3]["variants"], "not-a-list")
        self.assertNotIn(
            "thumbnail_url",
            document["items"][4]["variants"][0],
        )

    def test_workspace_scene_and_generic_live_action_routes(self) -> None:
        scene = {
            "available": True,
            "atoms": [{"uid": "Light", "type": "InvisibleLight"}],
            "persons": [],
            "capabilities": ["atom-roster", "atom-select", "scene-load"],
        }
        categories = {"categories": [{"id": "scene", "resource_types": ["Scene"]}]}
        apply_result = {
            "resource_id": 42,
            "category": "scene",
            "bridge_request": "scene-request",
        }
        self.server.service.scene = mock.Mock(return_value=scene)
        self.server.service.workspace_categories = mock.Mock(return_value=categories)
        self.server.service.apply_resource = mock.Mock(return_value=apply_result)
        headers = {"X-VAMPIP-Token": self.token}

        self.connection.request("GET", "/api/vam/scene", headers=headers)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), scene)

        self.connection.request(
            "GET",
            "/api/workspace/categories",
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), categories)

        body = json.dumps(
            {
                "resource_id": 42,
                "days": 2,
                "merge": False,
                "create_if_missing": True,
                "confirm_replace": True,
                # The server deliberately ignores caller-selected paths.
                "resource_ref": "/tmp/attacker-selected.json",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/resource/apply",
            body=body,
            headers={
                **headers,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), apply_result)
        self.server.service.apply_resource.assert_called_once_with(
            42,
            target_uid=None,
            days=2.0,
            merge=False,
            create_if_missing=True,
            confirm_replace=True,
            confirm_critical=False,
        )

    def test_resource_routes_forward_exact_package_version(self) -> None:
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        details_result = {
            "resource": {"id": 42, "selected_version": "4"},
            "dependencies": [],
            "conflicts": [],
        }
        self.server.service.resource_details = mock.Mock(
            return_value=details_result
        )
        self.connection.request(
            "GET",
            "/api/resources/42/details?package_version=4",
            headers={"X-VAMPIP-Token": self.token},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), details_result)
        self.server.service.resource_details.assert_called_once_with(
            42,
            package_version=4,
        )

        lease_result = {
            "resource_id": 42,
            "selected_version": "4",
            "lease_id": "lease-id",
        }
        self.server.service.lease_resource = mock.Mock(return_value=lease_result)
        lease_body = json.dumps(
            {
                "package_version": 4,
                "days": 2,
                "apply": False,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/resources/42/lease",
            body=lease_body,
            headers={
                **headers,
                "Content-Length": str(len(lease_body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), lease_result)
        self.server.service.lease_resource.assert_called_once_with(
            42,
            package_version=4,
            days=2.0,
            label=None,
            apply=False,
        )

        apply_result = {
            "resource_id": 42,
            "selected_version": "4",
            "bridge_request": "scene-request",
        }
        self.server.service.apply_resource = mock.Mock(return_value=apply_result)
        apply_body = json.dumps(
            {
                "resource_id": 42,
                "package_version": 4,
                "confirm_replace": True,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/resource/apply",
            body=apply_body,
            headers={
                **headers,
                "Content-Length": str(len(apply_body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), apply_result)
        self.server.service.apply_resource.assert_called_once_with(
            42,
            package_version=4,
            target_uid=None,
            days=3.0,
            merge=False,
            create_if_missing=False,
            confirm_replace=True,
            confirm_critical=False,
        )

    def test_resource_routes_reject_non_integer_package_version(self) -> None:
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        cases = (
            (
                "/api/resources/42/lease",
                {"package_version": True},
                "lease_resource",
            ),
            (
                "/api/vam/resource/apply",
                {"resource_id": 42, "package_version": "4"},
                "apply_resource",
            ),
        )
        for route, document, service_method in cases:
            with self.subTest(route=route):
                body = json.dumps(document).encode("utf-8")
                with mock.patch.object(
                    self.server.service,
                    service_method,
                    return_value={},
                ) as operation:
                    self.connection.request(
                        "POST",
                        route,
                        body=body,
                        headers={
                            **headers,
                            "Content-Length": str(len(body)),
                        },
                    )
                    response = self.connection.getresponse()
                    self.assertEqual(response.status, 400)
                    payload = self.response_json(response)
                    self.assertIn(
                        "package_version must be an integer",
                        payload["error"],
                    )
                    operation.assert_not_called()

    def test_custom_unity_asset_choice_route_is_strict_and_opaque(self) -> None:
        token = "a" * 32
        choice_result = {
            "operation": "select-custom-unity-asset-choice",
            "target_uid": "CUA Target",
            "choice_index": 3,
            "bridge_request": "choice-request",
        }
        self.server.service.select_custom_unity_asset_choice = mock.Mock(
            return_value=choice_result
        )
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }

        body = json.dumps(
            {
                "target_uid": "CUA Target",
                "choice_index": 3,
                "choice_token": token,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/custom-unity-asset/choice",
            body=body,
            headers={**headers, "Content-Length": str(len(body))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.response_json(response), choice_result)
        self.server.service.select_custom_unity_asset_choice.assert_called_once_with(
            "CUA Target",
            3,
            token,
        )

        forbidden = json.dumps(
            {
                "target_uid": "CUA Target",
                "choice_index": 3,
                "choice_token": token,
                "asset_name": "Assets/attacker.prefab",
                "loadDll": True,
                "resource_path": "/tmp/attacker.assetbundle",
                "atom_type": "Person",
                "action": "anything",
                "options": {"loadDll": True},
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/custom-unity-asset/choice",
            body=forbidden,
            headers={**headers, "Content-Length": str(len(forbidden))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        payload = self.response_json(response)
        self.assertIn("unsupported Custom Unity Asset choice field", payload["error"])
        self.assertEqual(
            self.server.service.select_custom_unity_asset_choice.call_count,
            1,
        )

    def test_custom_unity_asset_choice_route_requires_exact_field_types(self) -> None:
        self.server.service.select_custom_unity_asset_choice = mock.Mock()
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        invalid_documents = (
            (
                {
                    "target_uid": None,
                    "choice_index": 1,
                    "choice_token": "a" * 32,
                },
                "target_uid must be a string",
            ),
            (
                {
                    "target_uid": "CUA Target",
                    "choice_index": True,
                    "choice_token": "a" * 32,
                },
                "choice_index must be a positive integer",
            ),
            (
                {
                    "target_uid": "CUA Target",
                    "choice_index": 0,
                    "choice_token": "a" * 32,
                },
                "choice_index must be a positive integer",
            ),
            (
                {
                    "target_uid": "CUA Target",
                    "choice_index": 1,
                    "choice_token": None,
                },
                "choice_token must be a string",
            ),
        )
        for document, expected in invalid_documents:
            with self.subTest(document=document):
                body = json.dumps(document).encode("utf-8")
                self.connection.request(
                    "POST",
                    "/api/vam/custom-unity-asset/choice",
                    body=body,
                    headers={**headers, "Content-Length": str(len(body))},
                )
                response = self.connection.getresponse()
                self.assertEqual(response.status, 400)
                self.assertIn(expected, self.response_json(response)["error"])
        self.server.service.select_custom_unity_asset_choice.assert_not_called()

    def test_person_and_atom_lifecycle_routes(self) -> None:
        self.server.service.add_person = mock.Mock(
            return_value={"bridge_request": "add"}
        )
        self.server.service.select_person = mock.Mock(
            return_value={"bridge_request": "person-select"}
        )
        self.server.service.select_atom = mock.Mock(
            return_value={"bridge_request": "atom-select"}
        )
        self.server.service.add_atom = mock.Mock(
            return_value={"bridge_request": "atom-add"}
        )
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "application/json",
        }
        for route, method_name in (
            ("/api/vam/person/add", "add_person"),
            ("/api/vam/person/select", "select_person"),
            ("/api/vam/atom/select", "select_atom"),
        ):
            with self.subTest(route=route):
                body = json.dumps({"target_uid": "Target"}).encode("utf-8")
                self.connection.request(
                    "POST",
                    route,
                    body=body,
                    headers={**headers, "Content-Length": str(len(body))},
                )
                response = self.connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                getattr(self.server.service, method_name).assert_called_once_with(
                    "Target"
                )

        body = json.dumps(
            {
                "category_id": "preset-atom-empty-deadbeef",
                "target_uid": "Target",
                # A caller cannot substitute its own atom type.
                "atom_type": "Person",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/atom/add",
            body=body,
            headers={**headers, "Content-Length": str(len(body))},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        self.server.service.add_atom.assert_called_once_with(
            "preset-atom-empty-deadbeef",
            "Target",
        )

    def test_generic_apply_requires_strict_boolean_options(self) -> None:
        body = json.dumps(
            {
                "resource_id": 42,
                "merge": "false",
                "confirm_replace": True,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/resource/apply",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("merge must be a boolean", document["error"])

        body = json.dumps(
            {
                "resource_id": 42,
                "confirm_replace": True,
                "confirm_critical": "true",
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/resource/apply",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("confirm_critical must be a boolean", document["error"])

        body = json.dumps(
            {
                "resource_id": 42,
                "create_if_missing": "false",
                "confirm_critical": True,
            }
        ).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/resource/apply",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("create_if_missing must be a boolean", document["error"])

    def test_atom_add_requires_catalog_category_and_target_strings(self) -> None:
        for document, message in (
            ({"category_id": 7, "target_uid": "Target"}, "category_id"),
            ({"category_id": "subscenes", "target_uid": None}, "target_uid"),
        ):
            with self.subTest(document=document):
                body = json.dumps(document).encode("utf-8")
                self.connection.request(
                    "POST",
                    "/api/vam/atom/add",
                    body=body,
                    headers={
                        "X-VAMPIP-Token": self.token,
                        "Content-Type": "application/json",
                        "Content-Length": str(len(body)),
                    },
                )
                response = self.connection.getresponse()
                self.assertEqual(response.status, 400)
                payload = self.response_json(response)
                self.assertIn(message, payload["error"])

    def test_person_apply_validates_resource_identity_shape(self) -> None:
        body = json.dumps({"resource_id": True, "target_uid": "Person"}).encode("utf-8")
        self.connection.request(
            "POST",
            "/api/vam/person/apply",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        document = self.response_json(response)
        self.assertIn("positive integer", document["error"])


if __name__ == "__main__":
    unittest.main()

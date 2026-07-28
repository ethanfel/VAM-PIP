from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

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
        self.assertIn("/styles.css?v=0.4.0", document)
        self.assertIn("/app.js?v=0.4.0", document)

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
            confirm_replace=True,
            confirm_critical=False,
        )

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

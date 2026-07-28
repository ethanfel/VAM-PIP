from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from vampip.service import ManagerService
from vampip.web import ManagerHTTPServer

from tests.test_vampip import make_var


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
        response.read()


if __name__ == "__main__":
    unittest.main()

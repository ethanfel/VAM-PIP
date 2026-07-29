from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest

from vampip.service import ManagerService
from vampip.web import ManagerHTTPServer

from tests.test_sam3d import png_header


class Sam3dWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.base = base
        addons = base / "VaM" / "AddonPackages"
        addons.mkdir(parents=True)
        self.service = ManagerService(
            addons,
            base / "state",
            process_probe=lambda: [],
        )
        self.token = "sam3d-web-test-token"
        self.server = ManagerHTTPServer(
            ("127.0.0.1", 0),
            self.service,
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
        self.service.close()
        self.temporary.cleanup()

    def json(self, response) -> dict[str, object]:
        return json.loads(response.read().decode("utf-8"))

    def test_raw_image_upload_and_authenticated_job_reads(self) -> None:
        image = png_header()
        self.connection.request(
            "POST",
            "/api/sam3d/jobs?bbox=0,0,64,64&vertical_fov=55",
            body=image,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "image/png",
                "Content-Length": str(len(image)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 201)
        job = self.json(response)
        self.assertEqual(job["state"], "uploaded")
        self.assertEqual(job["source"]["width"], 64)
        self.assertIn("source", job["artifact_urls"])

        self.connection.request(
            "GET",
            f"/api/sam3d/jobs/{job['id']}",
            headers={"X-VAMPIP-Token": self.token},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.json(response)["id"], job["id"])

    def test_raw_upload_rejects_spoofed_type_and_foreign_origin(self) -> None:
        image = png_header()
        headers = {
            "X-VAMPIP-Token": self.token,
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(image)),
        }
        self.connection.request(
            "POST",
            "/api/sam3d/jobs",
            body=image,
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn("does not match", self.json(response)["error"])

        headers["Content-Type"] = "image/png"
        headers["Origin"] = "https://example.com"
        self.connection.request(
            "POST",
            "/api/sam3d/jobs",
            body=image,
            headers=headers,
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()

    def test_run_reports_unconfigured_worker_without_starting_comfy(self) -> None:
        image = png_header()
        self.connection.request(
            "POST",
            "/api/sam3d/jobs",
            body=image,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "image/png",
                "Content-Length": str(len(image)),
            },
        )
        response = self.connection.getresponse()
        job = self.json(response)
        body = b"{}"
        self.connection.request(
            "POST",
            f"/api/sam3d/jobs/{job['id']}/run",
            body=body,
            headers={
                "X-VAMPIP-Token": self.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 503)
        error = self.json(response)["error"]
        self.assertIn("not configured", error)

    def test_capture_url_and_artifact_survive_a_later_undo_action(self) -> None:
        job = self.service.create_sam3d_job(png_header(), "image/png")
        manager = self.service._sam3d()
        revision = "d" * 32
        capture_request = "e" * 32
        manager.record_vam_action(
            job["id"],
            action="capture",
            revision=revision,
            request_id=capture_request,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
            capture_extension="jpg",
            capture_content_type="image/jpeg",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=capture_request,
            state="succeeded",
            message="capture complete",
        )
        capture = (
            self.service.vam_root
            / "Saves"
            / "VR_Videos_And_Funscripts"
            / f"vampip_{capture_request}_{job['id']}.jpg"
        )
        capture.parent.mkdir(parents=True)
        capture.write_bytes(b"durable-jpeg")

        undo_request = "f" * 32
        manager.record_vam_action(
            job["id"],
            action="undo",
            revision=revision,
            request_id=undo_request,
            bridge_instance="bridge-one",
            target_uid="Person",
            camera_uid="SAM Camera",
        )
        manager.reconcile_vam_action(
            job["id"],
            request_id=undo_request,
            state="succeeded",
            message="undo complete",
        )

        self.connection.request(
            "GET",
            f"/api/sam3d/jobs/{job['id']}",
            headers={"X-VAMPIP-Token": self.token},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        document = self.json(response)
        self.assertEqual(document["last_vam_action"]["action"], "undo")
        self.assertEqual(
            document["last_capture"]["request_id"],
            capture_request,
        )
        self.assertEqual(len(document["captures"]), 1)
        capture_entry = document["captures"][0]
        self.assertEqual(capture_entry["request_id"], capture_request)
        self.assertIn("artifact_url", capture_entry)
        capture_url = document["artifact_urls"]["capture"]

        self.connection.request("GET", capture_url)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.read(), b"durable-jpeg")

        self.connection.request("GET", capture_entry["artifact_url"])
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "image/jpeg")
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(response.read(), b"durable-jpeg")

        capture_path = capture_entry["artifact_url"].split("?", 1)[0]
        self.connection.request("GET", capture_path)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 401)
        response.read()

        unknown_url = capture_entry["artifact_url"].replace(
            capture_request,
            "a" * 32,
        )
        self.connection.request("GET", unknown_url)
        response = self.connection.getresponse()
        self.assertEqual(response.status, 404)
        response.read()

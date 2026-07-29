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

    def test_raw_upload_passes_bounded_model_and_comparison_identity(self) -> None:
        image = png_header()
        comparison_id = "a" * 32
        returned = {
            "id": "b" * 32,
            "state": "uploaded",
        }
        with mock.patch.object(
            self.service,
            "create_sam3d_job",
            return_value=returned,
        ) as create:
            self.connection.request(
                "POST",
                (
                    "/api/sam3d/jobs"
                    "?model_id=vit_hmr_512_384"
                    f"&comparison_id={comparison_id}"
                ),
                body=image,
                headers={
                    "X-VAMPIP-Token": self.token,
                    "Content-Type": "image/png",
                    "Content-Length": str(len(image)),
                },
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 201)
            self.assertEqual(self.json(response)["id"], returned["id"])
        create.assert_called_once_with(
            image,
            "image/png",
            bbox=None,
            vertical_fov=None,
            model_id="vit_hmr_512_384",
            comparison_id=comparison_id,
        )

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

    def test_body_proportion_analysis_route_is_target_scoped(self) -> None:
        job_id = "a" * 32
        returned = {
            "job_id": job_id,
            "analysis_revision": "b" * 32,
            "measurements": [],
        }
        with mock.patch.object(
            self.service,
            "sam3d_body_proportions",
            return_value=returned,
        ) as analyze:
            self.connection.request(
                "GET",
                (
                    f"/api/sam3d/jobs/{job_id}/body-proportions"
                    "?target_uid=Person&person_index=1&fit_strength=0.6"
                    "&regions=arms,legs"
                    "&shape_strength=0.7&shape_regions=breasts,glutes"
                ),
                headers={"X-VAMPIP-Token": self.token},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(self.json(response), returned)
        analyze.assert_called_once_with(
            job_id,
            target_uid="Person",
            person_index=1,
            references=None,
            strength=0.6,
            regions=["arms", "legs"],
            shape_strength=0.7,
            shape_regions=["breasts", "glutes"],
        )

    def test_body_proportion_get_propagates_ordered_references(self) -> None:
        job_id = "a" * 32
        secondary_job_id = "b" * 32
        references = f"{job_id}:0,{secondary_job_id}:1"
        returned = {
            "job_id": job_id,
            "reference_count": 2,
            "analysis_revision": "c" * 32,
        }
        with mock.patch.object(
            self.service,
            "sam3d_body_proportions",
            return_value=returned,
        ) as analyze:
            self.connection.request(
                "GET",
                (
                    f"/api/sam3d/jobs/{job_id}/body-proportions"
                    "?target_uid=Person"
                    f"&references={references}"
                ),
                headers={"X-VAMPIP-Token": self.token},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(self.json(response), returned)
        analyze.assert_called_once_with(
            job_id,
            target_uid="Person",
            person_index=0,
            references=references,
            strength=0.5,
            regions=None,
        )

    def test_body_proportion_apply_route_keeps_pose_as_a_second_step(self) -> None:
        job_id = "c" * 32
        secondary_job_id = "a" * 32
        references = f"{job_id}:0,{secondary_job_id}:1"
        analysis_revision = "d" * 32
        job_revision = "e" * 32
        analysis = {
            "job_id": job_id,
            "job_revision": job_revision,
            "analysis_revision": analysis_revision,
        }
        applied = {
            "job_id": job_id,
            "bridge_request": "f" * 32,
            "action_state": "queued",
        }
        body = json.dumps(
            {
                "action": "apply",
                "expected_job_revision": job_revision,
                "expected_analysis_revision": analysis_revision,
                "target_uid": "Person",
                "person_index": 0,
                "regions": ["legs", "torso"],
                "fit_strength": 0.5,
                "shape_regions": ["breasts", "waist"],
                "shape_strength": 0.7,
                "references": references,
            }
        ).encode("utf-8")
        with (
            mock.patch.object(
                self.service,
                "sam3d_body_proportions",
                return_value=analysis,
            ) as analyze,
            mock.patch.object(
                self.service,
                "apply_sam3d_body_proportions",
                return_value=applied,
            ) as apply,
        ):
            self.connection.request(
                "POST",
                f"/api/sam3d/jobs/{job_id}/body-proportions",
                body=body,
                headers={
                    "X-VAMPIP-Token": self.token,
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 202)
            self.assertEqual(self.json(response), applied)
        analyze.assert_called_once_with(
            job_id,
            target_uid="Person",
            person_index=0,
            references=references,
            strength=0.5,
            regions=["legs", "torso"],
            shape_strength=0.7,
            shape_regions=["breasts", "waist"],
        )
        apply.assert_called_once_with(
            job_id,
            expected_job_revision=job_revision,
            expected_analysis_revision=analysis_revision,
            target_uid="Person",
            person_index=0,
            references=references,
            strength=0.5,
            regions=["legs", "torso"],
            shape_strength=0.7,
            shape_regions=["breasts", "waist"],
        )

    def test_body_proportion_post_rejects_null_shape_regions(self) -> None:
        job_id = "c" * 32
        body = json.dumps(
            {
                "action": "analyze",
                "expected_job_revision": "d" * 32,
                "target_uid": "Person",
                "shape_regions": None,
            }
        ).encode("utf-8")
        with mock.patch.object(
            self.service,
            "sam3d_body_proportions",
        ) as analyze:
            self.connection.request(
                "POST",
                f"/api/sam3d/jobs/{job_id}/body-proportions",
                body=body,
                headers={
                    "X-VAMPIP-Token": self.token,
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn(
                "shape_regions must be a list",
                json.dumps(self.json(response)),
            )
        analyze.assert_not_called()

    def test_body_proportion_apply_rejects_combined_pose_or_height_claims(
        self,
    ) -> None:
        job_id = "c" * 32
        for unsupported in ("apply_pose", "preserve_height"):
            body = json.dumps(
                {
                    "action": "apply",
                    "expected_job_revision": "d" * 32,
                    "expected_analysis_revision": "e" * 32,
                    "target_uid": "Person",
                    unsupported: True,
                }
            ).encode("utf-8")
            with self.subTest(unsupported=unsupported):
                self.connection.request(
                    "POST",
                    f"/api/sam3d/jobs/{job_id}/body-proportions",
                    body=body,
                    headers={
                        "X-VAMPIP-Token": self.token,
                        "Content-Type": "application/json",
                        "Content-Length": str(len(body)),
                    },
                )
                response = self.connection.getresponse()
                self.assertEqual(response.status, 400)
                self.assertIn(
                    unsupported,
                    json.dumps(self.json(response)),
                )

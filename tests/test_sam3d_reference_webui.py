from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "src" / "vampip" / "webui"


class Sam3dReferenceWebUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEBUI / "index.html").read_text(encoding="utf-8")
        cls.javascript = (WEBUI / "app.js").read_text(encoding="utf-8")
        cls.styles = (WEBUI / "styles.css").read_text(encoding="utf-8")

    def javascript_block(self, start: str, end: str) -> str:
        block_start = self.javascript.index(start)
        block_end = self.javascript.index(end, block_start)
        return self.javascript[block_start:block_end]

    def test_morph_and_pose_controls_expose_the_reference_flow(self) -> None:
        for control_id in (
            "sam3d-reference-panel",
            "sam3d-reference-state",
            "sam3d-reference-show",
            "sam3d-reference-hide",
            "sam3d-keep-reference",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn("Show reference in VaM", self.html)
        self.assertIn("Hide reference", self.html)
        self.assertIn("Keep reference aligned", self.html)
        self.assertIn('id="sam3d-keep-reference" type="checkbox" checked', self.html)
        self.assertIn(".sam3d-vam-reference", self.styles)
        self.assertIn(".sam3d-keep-reference", self.styles)

    def test_client_uses_revision_bound_post_and_delete_contracts(self) -> None:
        client = self.javascript_block(
            "const Sam3dClient = Object.freeze({",
            "function sam3dJobId(",
        )
        self.assertIn(
            "return `${this.job(jobId)}/reference`;",
            client,
        )
        show_start = client.index("showReference(jobId, request)")
        show_end = client.index("hideReference(", show_start)
        show = client[show_start:show_end]
        self.assertIn("method: \"POST\"", show)
        self.assertIn("body: request", show)

        hide_start = client.index("hideReference(jobId, expectedJobRevision)")
        hide_end = client.index("undo(jobId", hide_start)
        hide = client[hide_start:hide_end]
        self.assertIn("method: \"DELETE\"", hide)
        self.assertIn(
            "body: { expected_job_revision: expectedJobRevision }",
            hide,
        )

        apply_start = self.javascript.index("async function applySam3dResult(")
        apply_end = self.javascript.index(
            "async function undoSam3dApply(", apply_start
        )
        apply = self.javascript[apply_start:apply_end]
        self.assertIn("keepReference = sam3dKeepReferenceRequested();", apply)
        self.assertIn("keep_reference: keepReference", apply)

    def test_reference_actions_are_capability_gated_and_queue_checked(self) -> None:
        capability = self.javascript_block(
            "function sam3dReferenceCapabilityAvailable(",
            "function sam3dKeepReferenceRequested(",
        )
        self.assertIn('capabilities.has("sam3d-reference-v1")', capability)
        self.assertIn("...sam3dCapabilitySet()", capability)
        self.assertIn("...personCapabilities()", capability)

        show = self.javascript_block(
            "async function showSam3dReference(",
            "async function hideSam3dReference(",
        )
        hide = self.javascript_block(
            "async function hideSam3dReference(",
            "function sam3dSolutionRevision(",
        )
        self.assertIn("Sam3dClient.showReference(job.id, request)", show)
        self.assertIn('requireBridgeQueue(payload, "SAM 3D reference")', show)
        self.assertIn(
            "Sam3dClient.hideReference(job.id, job.revision)",
            hide,
        )
        self.assertIn(
            'requireBridgeQueue(payload, "Remove SAM 3D reference")',
            hide,
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_reference_normalizer_is_job_bound_and_bounded(self) -> None:
        normalizer = self.javascript_block(
            "function normalizeSam3dReference(",
            "function normalizeSam3dJob(",
        )
        script = f"""
"use strict";
const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{{32}}$/i;
const integerValue = (value) => {{
  const number = Number(value);
  return Number.isInteger(number) ? number : null;
}};
{normalizer}
const jobId = "a".repeat(32);
const active = normalizeSam3dReference({{
  visible: true,
  job_id: jobId,
  target_uid: "Person",
  camera_uid: "Camera",
  atom_uid: "Reference",
  alignment_mode: "pose-aligned",
  state: "active",
  resource_ref: "Custom/Images/VAMPip/SAM3D/source.png",
  sha256: "b".repeat(64),
  width: 1320,
  height: 1984,
}}, jobId);
const hidden = normalizeSam3dReference({{
  jobId,
  active: false,
  state: "hidden",
  sourceWidth: "900",
  sourceHeight: "1600",
}}, jobId);
const wrongJob = normalizeSam3dReference({{
  visible: true,
  job_id: "c".repeat(32),
}}, jobId);
const malformed = normalizeSam3dReference([], jobId);
process.stdout.write(JSON.stringify({{ active, hidden, wrongJob, malformed }}));
"""
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["active"]["visible"])
        self.assertEqual(result["active"]["jobId"], "a" * 32)
        self.assertEqual(result["active"]["targetUid"], "Person")
        self.assertEqual(result["active"]["cameraUid"], "Camera")
        self.assertEqual(result["active"]["atomUid"], "Reference")
        self.assertEqual(result["active"]["mode"], "pose-aligned")
        self.assertEqual(result["active"]["width"], 1320)
        self.assertEqual(result["active"]["height"], 1984)
        self.assertEqual(result["active"]["sha256"], "b" * 64)
        self.assertFalse(result["hidden"]["visible"])
        self.assertEqual(result["hidden"]["width"], 900)
        self.assertEqual(result["hidden"]["height"], 1600)
        self.assertIsNone(result["wrongJob"])
        self.assertIsNone(result["malformed"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_reference_request_uses_only_alignment_fields(self) -> None:
        placement = self.javascript_block(
            "function sam3dCameraPlacementSettings(",
            "function sam3dApplySettings(",
        )
        request = self.javascript_block(
            "function sam3dReferenceRequest(",
            "function sam3dReferenceSettingsError(",
        )
        script = f"""
"use strict";
const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{{32}}$/i;
const SAM3D_DEFAULT_CAMERA_UID = "VAMPip SAM3D Camera";
const elements = {{
  sam3dCameraFov: {{ value: "71.5" }},
  sam3dPersonHeight: {{ value: "1.72" }},
  sam3dPersonTarget: {{ value: "Person" }},
  sam3dCameraTarget: {{ value: "__create__" }},
}};
const app = {{ sam3dSelectedBodyIndex: 2, sam3dSelectedJob: null }};
{placement}
{request}
const job = {{ revision: "d".repeat(32) }};
const create = sam3dReferenceRequest(job);
elements.sam3dCameraTarget.value = "Existing Camera";
elements.sam3dCameraFov.value = "";
const existing = sam3dReferenceRequest(job);
process.stdout.write(JSON.stringify({{ create, existing }}));
"""
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(
            result["create"],
            {
                "expected_job_revision": "d" * 32,
                "target_uid": "Person",
                "person_index": 2,
                "height_m": 1.72,
                "camera_uid": "VAMPip SAM3D Camera",
                "create_camera": True,
                "horizontal_fov": 71.5,
            },
        )
        self.assertEqual(
            result["existing"],
            {
                "expected_job_revision": "d" * 32,
                "target_uid": "Person",
                "person_index": 2,
                "height_m": 1.72,
                "camera_uid": "Existing Camera",
                "create_camera": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

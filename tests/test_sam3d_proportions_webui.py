from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "src" / "vampip" / "webui"


class Sam3dBodyProportionsWebUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEBUI / "index.html").read_text(encoding="utf-8")
        cls.javascript = (WEBUI / "app.js").read_text(encoding="utf-8")
        cls.styles = (WEBUI / "styles.css").read_text(encoding="utf-8")

    def test_panel_exposes_read_only_analysis_and_explicit_mutations(self) -> None:
        for control_id in (
            "sam3d-proportions-panel",
            "sam3d-proportions-analyze",
            "sam3d-proportions-state",
            "sam3d-proportions-results",
            "sam3d-proportions-confidence",
            "sam3d-proportions-disagreement",
            "sam3d-proportions-measurements",
            "sam3d-proportions-morphs",
            "sam3d-proportions-apply",
            "sam3d-proportions-undo",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)

        analyze_start = self.javascript.index(
            "async function analyzeSam3dBodyProportions("
        )
        analyze_end = self.javascript.index(
            "async function applySam3dBodyProportions(", analyze_start
        )
        analyze = self.javascript[analyze_start:analyze_end]
        self.assertIn("SAM3D_BODY_PROPORTION_ACTIONS.analyze", analyze)
        self.assertNotIn("SAM3D_BODY_PROPORTION_ACTIONS.apply", analyze)
        self.assertNotIn("SAM3D_BODY_PROPORTION_ACTIONS.undo", analyze)

        self.assertIn("async function applySam3dBodyProportions(", self.javascript)
        self.assertIn("async function undoSam3dBodyProportions(", self.javascript)
        self.assertIn("Apply morphs", self.html)
        self.assertIn("Undo body fit", self.html)

    def test_handoff_uses_separate_morph_and_pose_tabs(self) -> None:
        for control_id in (
            "sam3d-handoff",
            "sam3d-handoff-morph-tab",
            "sam3d-handoff-pose-tab",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn('data-sam3d-handoff-tab="morph"', self.html)
        self.assertIn('data-sam3d-handoff-tab="pose"', self.html)
        self.assertIn('aria-controls="sam3d-proportions-panel"', self.html)
        self.assertIn('aria-controls="sam3d-apply-panel"', self.html)
        self.assertIn("function setSam3dHandoffTab(", self.javascript)
        self.assertIn("function renderSam3dHandoff(", self.javascript)
        self.assertIn("Apply morphs", self.html)
        self.assertIn("Apply pose + camera", self.html)

    def test_local_person_profiles_store_only_safe_preferences(self) -> None:
        for control_id in (
            "sam3d-profile-select",
            "sam3d-profile-new",
            "sam3d-profile-save",
            "sam3d-profile-delete",
            "sam3d-profile-reference-job",
            "sam3d-profile-use-reference",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn(
            'const SAM3D_BODY_PROFILE_STORAGE_KEY = '
            '"vampip-sam3d-body-profiles-v1"',
            self.javascript,
        )
        persist_start = self.javascript.index(
            "function persistSam3dBodyProfiles("
        )
        persist_end = self.javascript.index(
            "function selectedSam3dBodyProfile(", persist_start
        )
        persist = self.javascript[persist_start:persist_end]
        for safe_field in (
            "name:",
            "regions:",
            "strength:",
            "reference_job_id:",
        ):
            with self.subTest(safe_field=safe_field):
                self.assertIn(safe_field, persist)
        for unsafe_field in (
            "morphs:",
            "morph_keys:",
            "body_revision:",
            "analysis_revision:",
            "apply_revision:",
        ):
            with self.subTest(unsafe_field=unsafe_field):
                self.assertNotIn(unsafe_field, persist)
        self.assertIn("never live morph values or revisions", self.html)

    def test_fit_controls_are_bounded_and_safe_by_default(self) -> None:
        for region in ("arms", "legs", "torso", "widths"):
            with self.subTest(region=region):
                self.assertIn(
                    f'id="sam3d-region-{region}" '
                    f'type="checkbox" value="{region}" checked',
                    self.html,
                )
        self.assertNotIn("sam3d-preserve-height", self.html)
        self.assertIn("Body Scale stays untouched", self.html)
        self.assertIn("final height", self.html)
        self.assertIn(
            'id="sam3d-fit-strength" type="range" '
            'min="0" max="100" step="5" value="75"',
            self.html,
        )
        self.assertIn(
            "Arms, legs, torso, and widths are geometric fits. "
            "Soft-body physics is not inferred.",
            self.html,
        )
        self.assertIn("settings.strength / 100", self.javascript)
        self.assertNotIn("apply_pose", self.javascript)

    def test_endpoint_contract_is_centralized_and_revision_bound(self) -> None:
        client_start = self.javascript.index("const Sam3dClient = Object.freeze({")
        client_end = self.javascript.index(
            "function sam3dJobId(", client_start
        )
        client = self.javascript[client_start:client_end]
        self.assertIn("bodyProportions(jobId)", client)
        self.assertIn("/body-proportions", client)
        self.assertIn("bodyProportionsAction(jobId, action, request = {})", client)
        self.assertIn("body: { action, ...request }", client)

        request_start = self.javascript.index(
            "function sam3dBodyProportionRequest("
        )
        request_end = self.javascript.index(
            "function sam3dBodyProportionRevision(", request_start
        )
        request = self.javascript[request_start:request_end]
        for field in (
            "expected_job_revision",
            "target_uid",
            "person_index",
            "regions",
            "fit_strength",
            "expected_analysis_revision",
        ):
            with self.subTest(field=field):
                self.assertIn(field, request)
        self.assertNotIn("preserve_height", request)
        undo_start = self.javascript.index(
            "function sam3dBodyProportionUndoRequest("
        )
        undo_end = self.javascript.index(
            "function sam3dBodyProportionRevision(", undo_start
        )
        undo = self.javascript[undo_start:undo_end]
        self.assertIn("target_uid", undo)
        self.assertIn("expected_apply_revision", undo)

    def test_reports_percentages_confidence_disagreement_and_stale_state(self) -> None:
        for function_name in (
            "normalizeSam3dBodyMeasurement",
            "normalizeSam3dMorphChange",
            "normalizeSam3dBodyProportions",
            "renderSam3dBodyMeasurements",
            "renderSam3dMorphChanges",
            "markSam3dBodyProportionsDirty",
        ):
            with self.subTest(function_name=function_name):
                self.assertIn(f"function {function_name}(", self.javascript)
        self.assertIn("model_disagreement", self.javascript)
        self.assertIn("Analysis settings changed", self.javascript)
        self.assertIn("Current VaM → image target", self.html)
        self.assertIn("Proposed morph changes", self.html)

    def test_unavailable_and_error_states_are_visible(self) -> None:
        self.assertIn("error.status === 404 || error.status === 501", self.javascript)
        self.assertIn("Body-proportion fitting unavailable", self.javascript)
        self.assertIn("Body analysis could not be loaded", self.javascript)
        self.assertIn("No VaM changes were made", self.javascript)
        self.assertIn(".sam3d-proportions-state.is-error", self.styles)
        self.assertIn(".sam3d-proportions-state.is-unavailable", self.styles)

    def test_panel_is_responsive(self) -> None:
        for selector in (
            ".sam3d-proportions-layout",
            ".sam3d-region-grid",
            ".sam3d-proportions-summary",
            ".sam3d-measurement-list",
            ".sam3d-morph-change-list",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        self.assertIn("@media (max-width: 1180px)", self.styles)
        self.assertIn("@media (max-width: 760px)", self.styles)
        self.assertIn("@media (max-width: 500px)", self.styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_javascript_remains_syntactically_valid(self) -> None:
        subprocess.run(
            ["node", "--check", str(WEBUI / "app.js")],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
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
            "sam3d-shape-results",
            "sam3d-shape-confidence",
            "sam3d-shape-measurements",
            "sam3d-shape-morphs",
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
        self.assertIn("Apply body fit", self.html)
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
        self.assertIn("Apply body fit", self.html)
        self.assertIn("Apply pose + camera", self.html)

    def test_local_person_profiles_store_only_safe_preferences(self) -> None:
        for control_id in (
            "sam3d-profile-select",
            "sam3d-profile-new",
            "sam3d-profile-save",
            "sam3d-profile-delete",
            "sam3d-morph-reference-gallery",
            "sam3d-morph-reference-count",
            "sam3d-morph-reference-note",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn(
            'const SAM3D_BODY_PROFILE_STORAGE_KEY = "vampip-sam3d-body-profiles-v4"',
            self.javascript,
        )
        self.assertIn('"vampip-sam3d-body-profiles-v3"', self.javascript)
        self.assertIn('"vampip-sam3d-body-profiles-v2"', self.javascript)
        self.assertIn(
            '"vampip-sam3d-body-profiles-v1"',
            self.javascript,
        )
        persist_start = self.javascript.index("function persistSam3dBodyProfiles(")
        persist_end = self.javascript.index(
            "function selectedSam3dBodyProfile(", persist_start
        )
        persist = self.javascript[persist_start:persist_end]
        for safe_field in (
            "name:",
            "regions:",
            "strength:",
            "shape_regions:",
            "shape_strength:",
            "reference_jobs:",
            "job_id:",
            "person_index:",
            "manual_fit_mode:",
            "manual_shape:",
            "manual_reference:",
            "manual_overlay:",
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
        self.assertNotIn("reference_job_id:", persist)
        self.assertIn("JSON.stringify({ schema: 4, profiles })", persist)
        normalize_start = self.javascript.index("function normalizeSam3dBodyProfile(")
        normalize_end = self.javascript.index(
            "function loadSam3dBodyProfiles(", normalize_start
        )
        normalize = self.javascript[normalize_start:normalize_end]
        self.assertIn("raw.reference_job_id", normalize)
        self.assertIn("raw.reference_person_index", normalize)
        self.assertIn("Morph-reference preferences—never live", self.html)
        self.assertIn("morph values or revisions", self.html)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_profile_reference_migration_is_deduplicated_and_bounded(self) -> None:
        helpers_start = self.javascript.index("function normalizeSam3dBodyReference(")
        helpers_end = self.javascript.index(
            "function sam3dBodyReferenceCandidates(", helpers_start
        )
        profile_start = self.javascript.index("function normalizeSam3dBodyProfile(")
        profile_end = self.javascript.index(
            "function loadSam3dBodyProfiles(", profile_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;\n"
            "const SAM3D_BODY_REFERENCE_MAX_COUNT = 8;\n"
            'const SAM3D_BODY_PROPORTION_REGIONS = ["arms", "legs", "torso", "widths"];\n'
            'const SAM3D_BODY_SHAPE_REGIONS = ["breasts", "waist", "hips", "glutes", "thighs"];\n'
            'const SAM3D_MANUAL_SHAPE_KEYS = ["breast_size", "breast_spacing", "waist_width", "hip_width", "glute_projection", "thigh_size"];\n'
            "const asArray = (value) => Array.isArray(value) ? value : [];\n"
            "const integerValue = (value) => {\n"
            "  const number = Number(value);\n"
            "  return Number.isInteger(number) ? number : null;\n"
            "};\n"
            "const normalizeSam3dManualShape = (raw = {}) => ({ schema: 1, offsets: Object.fromEntries(SAM3D_MANUAL_SHAPE_KEYS.map((key) => [key, Math.max(-1, Math.min(1, Number(raw?.offsets?.[key]) || 0))])) });\n"
            "const sam3dManualShapeHasCorrections = (raw) => Object.values(normalizeSam3dManualShape(raw).offsets).some((value) => Math.abs(value) > 1e-6);\n"
            "const normalizeSam3dManualOverlay = (raw = {}) => ({ panX: Number(raw.pan_x ?? raw.panX) || 0, panY: Number(raw.pan_y ?? raw.panY) || 0, scale: Number(raw.scale) || 1, opacity: Number(raw.opacity) || 0.55 });\n"
            f"{self.javascript[helpers_start:helpers_end]}\n"
            f"{self.javascript[profile_start:profile_end]}\n"
            """
const legacyJobId = "a".repeat(32);
const legacy = normalizeSam3dBodyProfile({
  id: "f".repeat(32),
  name: "Legacy",
  regions: ["arms"],
  strength: 65,
  reference_job_id: legacyJobId,
  reference_person_index: 3,
});
const candidates = Array.from({ length: 10 }, (_, index) => ({
  job_id: index.toString(16).padStart(32, "0"),
  person_index: index,
}));
candidates.splice(2, 0, {
  ...candidates[0],
  person_index: 99,
});
candidates.splice(3, 0, {
  job_id: "e".repeat(32),
  person_index: -1,
});
const current = normalizeSam3dBodyProfile({
  id: "d".repeat(32),
  name: "Current",
  regions: ["legs"],
  strength: 80,
  shape_regions: ["waist", "glutes", "face"],
  shape_strength: 60,
  reference_jobs: candidates,
});
const zeroShapeStrength = normalizeSam3dBodyProfile({
  id: "c".repeat(32),
  name: "Zero shape strength",
  regions: ["torso"],
  shape_regions: ["breasts"],
  shape_strength: 0,
});
process.stdout.write(JSON.stringify({
  legacyReferences: legacy.referenceJobs,
  legacyShapeRegions: legacy.shapeRegions,
  legacyShapeStrength: legacy.shapeStrength,
  currentCount: current.referenceJobs.length,
  currentTokens: serializeSam3dBodyReferences(current.referenceJobs),
  currentShapeRegions: current.shapeRegions,
  currentShapeStrength: current.shapeStrength,
  zeroShapeStrength: zeroShapeStrength.shapeStrength,
}));
"""
        )
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
            result["legacyReferences"],
            [{"jobId": "a" * 32, "personIndex": 3}],
        )
        self.assertEqual(result["legacyShapeRegions"], [])
        self.assertEqual(result["legacyShapeStrength"], 50)
        self.assertEqual(result["currentCount"], 8)
        self.assertEqual(result["currentShapeRegions"], ["waist", "glutes"])
        self.assertEqual(result["currentShapeStrength"], 60)
        self.assertEqual(result["zeroShapeStrength"], 0)
        tokens = result["currentTokens"].split(",")
        self.assertEqual(len(tokens), 8)
        self.assertEqual(len(set(tokens)), 8)
        self.assertEqual(len({token.split(":")[0] for token in tokens}), 8)
        self.assertTrue(all(":" in token for token in tokens))

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_v2_profiles_migrate_to_v4_without_enabling_shape_or_manual_fit(self) -> None:
        profile_start = self.javascript.index("function normalizeSam3dBodyProfile(")
        profile_end = self.javascript.index(
            "function selectedSam3dBodyProfile(", profile_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;\n"
            'const SAM3D_BODY_PROPORTION_REGIONS = ["arms", "legs", "torso", "widths"];\n'
            'const SAM3D_BODY_SHAPE_REGIONS = ["breasts", "waist", "hips", "glutes", "thighs"];\n'
            'const SAM3D_MANUAL_SHAPE_KEYS = ["breast_size", "breast_spacing", "waist_width", "hip_width", "glute_projection", "thigh_size"];\n'
            'const SAM3D_BODY_PROFILE_STORAGE_KEY = "vampip-sam3d-body-profiles-v4";\n'
            'const SAM3D_BODY_PROFILE_V3_STORAGE_KEY = "vampip-sam3d-body-profiles-v3";\n'
            'const SAM3D_BODY_PROFILE_V2_STORAGE_KEY = "vampip-sam3d-body-profiles-v2";\n'
            'const SAM3D_BODY_PROFILE_V1_STORAGE_KEY = "vampip-sam3d-body-profiles-v1";\n'
            "const SAM3D_BODY_PROFILE_MAX_COUNT = 24;\n"
            "const asArray = (value) => Array.isArray(value) ? value : [];\n"
            "const normalizeSam3dBodyReferences = () => [];\n"
            "const normalizeSam3dBodyReference = () => null;\n"
            'const normalizeSam3dManualShape = () => ({ schema: 1, offsets: { breast_size: 0, breast_spacing: 0, waist_width: 0, hip_width: 0, glute_projection: 0, thigh_size: 0 } });\n'
            "const sam3dManualShapeHasCorrections = () => false;\n"
            "const normalizeSam3dManualOverlay = () => ({ panX: 0, panY: 0, scale: 1, opacity: 0.55 });\n"
            "const app = { sam3dBodyProfiles: [] };\n"
            "const writes = [];\n"
            'const legacyId = "a".repeat(32);\n'
            "const storage = new Map([[SAM3D_BODY_PROFILE_V2_STORAGE_KEY,\n"
            "  JSON.stringify({ schema: 2, profiles: [{\n"
            "    id: legacyId,\n"
            '    name: "Existing profile",\n'
            '    regions: ["arms", "torso"],\n'
            "    strength: 70,\n"
            "    updated_at: 123,\n"
            "  }] })\n"
            "]]);\n"
            "const window = { localStorage: {\n"
            "  getItem(key) { return storage.get(key) || null; },\n"
            "  setItem(key, value) { storage.set(key, value); writes.push({ key, value }); },\n"
            "} };\n"
            "const toast = () => {};\n"
            'const errorMessage = (error) => String(error?.message || error || "");\n'
            f"{self.javascript[profile_start:profile_end]}\n"
            """
loadSam3dBodyProfiles();
const migratedDocument = JSON.parse(
  storage.get(SAM3D_BODY_PROFILE_STORAGE_KEY),
);
process.stdout.write(JSON.stringify({
  profile: app.sam3dBodyProfiles[0],
  migratedDocument,
  writes,
}));
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(result["profile"]["shapeRegions"], [])
        self.assertEqual(result["profile"]["shapeStrength"], 50)
        self.assertEqual(result["profile"]["manualFitMode"], "estimator")
        self.assertEqual(
            set(result["profile"]["manualShape"]["offsets"].values()),
            {0},
        )
        self.assertEqual(result["migratedDocument"]["schema"], 4)
        self.assertEqual(
            result["migratedDocument"]["profiles"][0]["shape_regions"],
            [],
        )
        self.assertEqual(
            result["migratedDocument"]["profiles"][0]["shape_strength"],
            50,
        )
        self.assertEqual(len(result["writes"]), 1)
        self.assertEqual(
            result["writes"][0]["key"],
            "vampip-sam3d-body-profiles-v4",
        )

    def test_morph_reference_gallery_is_independent_from_pose_selection(self) -> None:
        self.assertIn(
            'id="sam3d-morph-reference-gallery"',
            self.html,
        )
        self.assertIn('aria-multiselectable="true"', self.html)
        self.assertIn("Choose up to eight completed bodies", self.html)
        for selector in (
            ".sam3d-morph-reference-picker",
            ".sam3d-morph-reference-gallery",
            ".sam3d-morph-reference-card",
            ".sam3d-morph-reference-card.is-selected",
            ".sam3d-morph-reference-card.is-solo-only",
            ".sam3d-morph-reference-compatibility",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        for function_name in (
            "normalizeSam3dBodyReferenceSupport",
            "sam3dBodyReferenceCandidates",
            "sam3dBodyReferenceSetIssue",
            "toggleSam3dBodyReference",
            "renderSam3dBodyReferenceGallery",
            "sam3dBodyProportionJob",
        ):
            with self.subTest(function_name=function_name):
                self.assertIn(f"function {function_name}(", self.javascript)
        self.assertIn("raw.body_reference_support", self.javascript)
        self.assertIn("bodyReferenceSupport,", self.javascript)
        self.assertIn("Structure · solo only", self.javascript)
        self.assertIn(
            "Legacy result is solo-only for Structure; use Body Shape only "
            "or rerun the image to combine Structure.",
            self.javascript,
        )
        self.assertIn(
            "legacy results can combine for Body Shape but remain",
            self.html,
        )

        select_job_start = self.javascript.index("async function selectSam3dJob(")
        select_job_end = self.javascript.index(
            "function sam3dFileContentType(", select_job_start
        )
        select_job = self.javascript[select_job_start:select_job_end]
        self.assertNotIn("sam3dBodyReferences", select_job)
        self.assertNotIn("resetSam3dBodyProportions", select_job)
        self.assertNotIn("loadSam3dBodyProportions", select_job)

        select_body_start = self.javascript.index("function selectSam3dBody(")
        select_body_end = self.javascript.index(
            "function normalizeSam3dBodyReference(", select_body_start
        )
        select_body = self.javascript[select_body_start:select_body_end]
        self.assertNotIn("sam3dBodyReferences", select_body)
        self.assertNotIn("resetSam3dBodyProportions", select_body)

        morph_start = self.javascript.index(
            "async function analyzeSam3dBodyProportions("
        )
        morph_end = self.javascript.index("function sam3dTargetEntries(", morph_start)
        morph_actions = self.javascript[morph_start:morph_end]
        self.assertIn("sam3dBodyProportionJob(settings)", morph_actions)

        pose_start = self.javascript.index("async function applySam3dResult(")
        pose_end = self.javascript.index("async function undoSam3dApply(", pose_start)
        pose_apply = self.javascript[pose_start:pose_end]
        self.assertIn("const job = app.sam3dSelectedJob;", pose_apply)
        self.assertIn("app.sam3dSelectedBodyIndex", pose_apply)
        self.assertNotIn("sam3dBodyReferences", pose_apply)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_legacy_morph_references_are_solo_only_for_structure(self) -> None:
        support_start = self.javascript.index(
            "function normalizeSam3dBodyReferenceSupport("
        )
        support_end = self.javascript.index(
            "function normalizeSam3dJob(", support_start
        )
        helpers_start = self.javascript.index("function normalizeSam3dBodyReference(")
        helpers_end = self.javascript.index(
            "function initializeSam3dBodyReferences(", helpers_start
        )
        toggle_start = self.javascript.index("function toggleSam3dBodyReference(")
        toggle_end = self.javascript.index(
            "function createSam3dBodyReferenceCard(", toggle_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;\n"
            "const SAM3D_BODY_PROPORTION_REGIONS = "
            '["arms", "legs", "torso", "widths"];\n'
            "const SAM3D_BODY_REFERENCE_MAX_COUNT = 8;\n"
            "const SAM3D_BODY_LEGACY_SOLO_MESSAGE = "
            '"Legacy result is solo-only for Structure; use Body Shape only '
            'or rerun the image to combine Structure.";\n'
            "const asArray = (value) => Array.isArray(value) ? value : [];\n"
            "const integerValue = (value) => {\n"
            "  const number = Number(value);\n"
            "  return Number.isInteger(number) ? number : null;\n"
            "};\n"
            "const sam3dJobSucceeded = () => true;\n"
            f"{self.javascript[support_start:support_end]}\n"
            f"{self.javascript[helpers_start:helpers_end]}\n"
            """
const legacyId = "a".repeat(32);
const firstNeutralId = "b".repeat(32);
const secondNeutralId = "c".repeat(32);
const app = {
  sam3dBodyReferences: [],
  sam3dJobs: [
    {
      id: legacyId,
      bodies: [{}, {}],
      bodyReferenceSupport: normalizeSam3dBodyReferenceSupport([
        {
          person_index: 0,
          space: "legacy-camera",
          multi_reference: false,
        },
        {
          person_index: 1,
          space: "neutral-body",
          multi_reference: true,
        },
      ]),
    },
    {
      id: firstNeutralId,
      bodies: [{}],
      bodyReferenceSupport: normalizeSam3dBodyReferenceSupport([
        {
          person_index: 0,
          space: "neutral-body",
          multi_reference: true,
        },
      ]),
    },
    {
      id: secondNeutralId,
      bodies: [{}],
      bodyReferenceSupport: normalizeSam3dBodyReferenceSupport([
        {
          person_index: 0,
          space: "neutral-body",
          multi_reference: true,
        },
      ]),
    },
  ],
};
const legacy = { jobId: legacyId, personIndex: 0 };
const replacement = { jobId: legacyId, personIndex: 1 };
const firstNeutral = { jobId: firstNeutralId, personIndex: 0 };
const secondNeutral = { jobId: secondNeutralId, personIndex: 0 };
const structureRegions = [...SAM3D_BODY_PROPORTION_REGIONS];
const shapeOnlyRegions = [];
const toasts = [];
const changes = [];
const toast = (title, message, kind) => {
  toasts.push({ title, message, kind });
};
const setSam3dBodyReferences = (references) => {
  app.sam3dBodyReferences = normalizeSam3dBodyReferences(references);
  changes.push(serializeSam3dBodyReferences(app.sam3dBodyReferences));
};
"""
            f"{self.javascript[toggle_start:toggle_end]}\n"
            """
const soloIssue = sam3dBodyReferenceSetIssue([legacy], structureRegions);
const mixedStructureIssue = sam3dBodyReferenceSetIssue(
  [legacy, firstNeutral],
  structureRegions,
);
const mixedShapeOnlyIssue = sam3dBodyReferenceSetIssue(
  [legacy, firstNeutral],
  shapeOnlyRegions,
);
const neutralIssue = sam3dBodyReferenceSetIssue(
  [firstNeutral, secondNeutral],
  structureRegions,
);

app.sam3dBodyReferences = [legacy];
toggleSam3dBodyReference(firstNeutral, structureRegions);
const structureLegacyThenNeutral = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [firstNeutral];
toggleSam3dBodyReference(legacy, structureRegions);
const structureNeutralThenLegacy = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [legacy];
toggleSam3dBodyReference(firstNeutral, shapeOnlyRegions);
const shapeOnlyLegacyThenNeutral = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [firstNeutral];
toggleSam3dBodyReference(legacy, shapeOnlyRegions);
const shapeOnlyNeutralThenLegacy = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [];
toggleSam3dBodyReference(legacy, structureRegions);
const legacyAlone = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);
toggleSam3dBodyReference(legacy, structureRegions);
const legacyRemoved = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [legacy];
toggleSam3dBodyReference(replacement, structureRegions);
const replacementToken = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

app.sam3dBodyReferences = [firstNeutral];
toggleSam3dBodyReference(secondNeutral, structureRegions);
const neutralPair = serializeSam3dBodyReferences(
  app.sam3dBodyReferences,
);

process.stdout.write(JSON.stringify({
  support: app.sam3dJobs[0].bodyReferenceSupport,
  soloIssue,
  mixedStructureIssue,
  mixedShapeOnlyIssue,
  neutralIssue,
  structureLegacyThenNeutral,
  structureNeutralThenLegacy,
  shapeOnlyLegacyThenNeutral,
  shapeOnlyNeutralThenLegacy,
  legacyAlone,
  legacyRemoved,
  replacementToken,
  neutralPair,
  toasts,
  changes,
}));
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        message = (
            "Legacy result is solo-only for Structure; use Body Shape only "
            "or rerun the image to combine Structure."
        )

        self.assertEqual(
            result["support"],
            [
                {
                    "personIndex": 0,
                    "space": "legacy-camera",
                    "multiReference": False,
                },
                {
                    "personIndex": 1,
                    "space": "neutral-body",
                    "multiReference": True,
                },
            ],
        )
        self.assertEqual(result["soloIssue"], "")
        self.assertEqual(result["mixedStructureIssue"], message)
        self.assertEqual(result["mixedShapeOnlyIssue"], "")
        self.assertEqual(result["neutralIssue"], "")
        self.assertEqual(
            result["structureLegacyThenNeutral"],
            f"{'a' * 32}:0",
        )
        self.assertEqual(
            result["structureNeutralThenLegacy"],
            f"{'b' * 32}:0",
        )
        self.assertEqual(
            result["shapeOnlyLegacyThenNeutral"],
            f"{'a' * 32}:0,{'b' * 32}:0",
        )
        self.assertEqual(
            result["shapeOnlyNeutralThenLegacy"],
            f"{'b' * 32}:0,{'a' * 32}:0",
        )
        self.assertEqual(result["legacyAlone"], f"{'a' * 32}:0")
        self.assertEqual(result["legacyRemoved"], "")
        self.assertEqual(result["replacementToken"], f"{'a' * 32}:1")
        self.assertEqual(
            result["neutralPair"],
            f"{'b' * 32}:0,{'c' * 32}:0",
        )
        self.assertEqual(len(result["toasts"]), 2)
        self.assertTrue(all(toast["message"] == message for toast in result["toasts"]))
        self.assertTrue(all(toast["kind"] == "error" for toast in result["toasts"]))

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
        for region in ("breasts", "waist", "hips", "glutes", "thighs"):
            with self.subTest(shape_region=region):
                control = (
                    f'id="sam3d-shape-region-{region}" type="checkbox" value="{region}"'
                )
                self.assertIn(control, self.html)
                self.assertNotIn(f"{control} checked", self.html)
        self.assertIn(
            'id="sam3d-shape-strength" type="range" '
            'min="0" max="100" step="5" value="50"',
            self.html,
        )
        self.assertIn(
            "Face morphs are always excluded. Breast and glute physics,",
            self.html,
        )
        self.assertIn(
            "soft-body settings, and materials are never changed.",
            self.html,
        )
        self.assertIn(
            "Structure and selected Body Shape regions are geometric fits.",
            self.html,
        )
        self.assertIn("settings.strength / 100", self.javascript)
        self.assertIn("settings.shapeStrength / 100", self.javascript)
        self.assertNotIn("apply_pose", self.javascript)
        self.assertNotIn("sam3dPreserveHeight", self.javascript)

    def test_manual_fit_uses_reference_overlay_and_bounded_semantic_controls(
        self,
    ) -> None:
        for control_id in (
            "sam3d-manual-fit",
            "sam3d-manual-fit-estimator",
            "sam3d-manual-fit-manual",
            "sam3d-manual-fit-stage",
            "sam3d-manual-fit-image",
            "sam3d-manual-fit-svg",
            "sam3d-manual-fit-silhouette",
            "sam3d-manual-reference-select",
            "sam3d-manual-auto-align",
            "sam3d-manual-overlay-reset",
            "sam3d-manual-overlay-scale",
            "sam3d-manual-overlay-opacity",
            "sam3d-manual-shape-reset",
            "sam3d-manual-fit-update",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        for name in (
            "breast-size",
            "breast-spacing",
            "waist-width",
            "hip-width",
            "glute-projection",
            "thigh-size",
        ):
            with self.subTest(manual_shape=name):
                self.assertIn(
                    f'id="sam3d-manual-shape-{name}" type="range" '
                    'min="-100" max="100" step="1" value="0"',
                    self.html,
                )
        self.assertIn(
            "Nothing changes in VaM until Apply body fit.",
            self.html,
        )
        self.assertIn("candidate?.body?.bbox || job?.bbox || job?.source?.bbox", self.javascript)
        self.assertIn("function renderSam3dManualFit(", self.javascript)
        self.assertIn("function renderSam3dManualOverlay(", self.javascript)
        self.assertIn("getScreenCTM", self.javascript)
        self.assertIn(
            "height: clamp(280px, 68vh, 760px);",
            self.styles,
        )
        self.assertIn(
            ".sam3d-manual-fit-stage > img {\n"
            "  position: absolute;\n"
            "  inset: 0;",
            self.styles,
        )
        self.assertIn("object-fit: contain;", self.styles)
        self.assertIn("object-position: center center;", self.styles)
        self.assertNotIn(
            "elements.sam3dManualFitStage.style.aspectRatio",
            self.javascript,
        )
        self.assertIn(
            "renderSam3dManualFit(app.sam3dBodyProportions)",
            self.javascript,
        )
        self.assertIn(
            "const refreshManualProposal =\n"
            "      sam3dManualShapeHasCorrections(settings.manualShape) &&\n"
            "      Boolean(job) &&\n"
            "      !app.sam3dBodyProportionsPendingAction &&\n"
            "      !retainAppliedReview;",
            self.javascript,
        )
        for selector in (
            ".sam3d-manual-fit-workspace",
            ".sam3d-manual-fit-stage",
            ".sam3d-manual-fit-stage > img",
            ".sam3d-manual-fit-stage > svg",
            ".sam3d-manual-shape-fieldset",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_manual_shape_is_canonical_bounded_and_post_only(self) -> None:
        helper_start = self.javascript.index("function emptySam3dManualShape(")
        helper_end = self.javascript.index(
            "function normalizeSam3dManualOverlay(", helper_start
        )
        request_start = self.javascript.index(
            "function sam3dBodyProportionRequest("
        )
        request_end = self.javascript.index(
            "function sam3dBodyProportionUndoRequest(", request_start
        )
        client_start = self.javascript.index("const Sam3dClient = Object.freeze({")
        client_end = self.javascript.index("function sam3dJobId(", client_start)
        client = self.javascript[client_start:client_end]
        self.assertNotIn('"manual_shape"', client)
        load_start = self.javascript.index(
            "async function loadSam3dBodyProportions("
        )
        load_end = self.javascript.index(
            "function startSam3dBodyProportionPolling(", load_start
        )
        load = self.javascript[load_start:load_end]
        self.assertIn("sam3dManualShapeHasCorrections(settings.manualShape)", load)
        self.assertIn("!app.sam3dBodyProportionsPendingAction", load)
        self.assertIn("SAM3D_BODY_PROPORTION_ACTIONS.analyze", load)
        self.assertIn("sam3dBodyProportionRequest(job)", load)
        self.assertIn("const preserveReviewedManual =", load)
        self.assertIn("const retainAppliedReview =", load)
        self.assertIn("!retainAppliedReview", load)
        self.assertIn("...reviewedAnalysis,", load)
        script = (
            '"use strict";\n'
            'const SAM3D_MANUAL_SHAPE_KEYS = ["breast_size", "breast_spacing", "waist_width", "hip_width", "glute_projection", "thigh_size"];\n'
            f"{self.javascript[helper_start:helper_end]}\n"
            "const serializeSam3dBodyReferences = () => '';\n"
            "let settings = { targetUid: 'Person', personIndex: 0, references: [], regions: [], strength: 75, shapeRegions: [], shapeStrength: 50, manualShape: emptySam3dManualShape() };\n"
            "const sam3dBodyProportionSettings = () => settings;\n"
            f"{self.javascript[request_start:request_end]}\n"
            """
const normalized = normalizeSam3dManualShape({
  schema: 99,
  offsets: {
    breast_size: 3,
    breast_spacing: -4,
    waist_width: 0.25,
    hip_width: "0.5",
    glute_projection: true,
    thigh_size: Number.NaN,
    ignored: 1,
  },
});
const zeroRequest = sam3dBodyProportionRequest({ revision: "a".repeat(32) });
settings = { ...settings, manualShape: normalized };
const correctedRequest =
  sam3dBodyProportionRequest({ revision: "a".repeat(32) });
process.stdout.write(JSON.stringify({
  normalized,
  serialized: serializeSam3dManualShape(normalized),
  zeroHasManual: Object.hasOwn(zeroRequest, "manual_shape"),
  corrected: correctedRequest.manual_shape,
}));
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["normalized"]["schema"], 1)
        self.assertEqual(
            list(result["normalized"]["offsets"]),
            [
                "breast_size",
                "breast_spacing",
                "waist_width",
                "hip_width",
                "glute_projection",
                "thigh_size",
            ],
        )
        self.assertEqual(
            result["normalized"]["offsets"],
            {
                "breast_size": 1,
                "breast_spacing": -1,
                "waist_width": 0.25,
                "hip_width": 0.5,
                "glute_projection": 0,
                "thigh_size": 0,
            },
        )
        self.assertFalse(result["zeroHasManual"])
        self.assertEqual(result["corrected"], result["normalized"])
        self.assertEqual(
            json.loads(result["serialized"]),
            result["normalized"],
        )

    def test_endpoint_contract_is_centralized_and_revision_bound(self) -> None:
        client_start = self.javascript.index("const Sam3dClient = Object.freeze({")
        client_end = self.javascript.index("function sam3dJobId(", client_start)
        client = self.javascript[client_start:client_end]
        self.assertIn("bodyProportions(", client)
        self.assertIn("/body-proportions", client)
        self.assertIn("bodyProportionsAction(jobId, action, request = {})", client)
        self.assertIn("body: { action, ...request }", client)
        self.assertIn(
            "normalizeSam3dBodyReferences(\n      references,\n"
            "      normalizedJobId,\n      normalizedPersonIndex,",
            client,
        )
        self.assertIn(
            "references: serializeSam3dBodyReferences(normalizedReferences)",
            client,
        )
        self.assertIn(
            'query.set("shape_regions", selectedShapeRegions.join(","))',
            client,
        )
        self.assertNotIn('"manual_shape"', client)

        request_start = self.javascript.index("function sam3dBodyProportionRequest(")
        request_end = self.javascript.index(
            "function sam3dBodyProportionRevision(", request_start
        )
        request = self.javascript[request_start:request_end]
        for field in (
            "expected_job_revision",
            "target_uid",
            "person_index",
            "references",
            "regions",
            "fit_strength",
            "shape_regions",
            "shape_strength",
            "manual_shape",
            "expected_analysis_revision",
        ):
            with self.subTest(field=field):
                self.assertIn(field, request)
        self.assertNotIn("preserve_height", request)
        undo_start = self.javascript.index("function sam3dBodyProportionUndoRequest(")
        undo_end = self.javascript.index(
            "function sam3dBodyProportionRevision(", undo_start
        )
        undo = self.javascript[undo_start:undo_end]
        self.assertIn("target_uid", undo)
        self.assertIn("expected_apply_revision", undo)
        self.assertNotIn("references", undo)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_async_shape_calibration_blocks_only_shape_requests(self) -> None:
        helper_start = self.javascript.index(
            "function sam3dBodyShapeCalibrationState("
        )
        helper_end = self.javascript.index(
            "function sam3dBodyReferencesReady(", helper_start
        )
        script = (
            '"use strict";\n'
            'let settings = { targetUid: "Person", shapeRegions: ["breasts"], manualShape: null };\n'
            "let persons = [{\n"
            '  uid: "Person",\n'
            "  bodyProportions: {\n"
            "    bodyShapeReady: false,\n"
            "    bodyShapePreparing: true,\n"
            "  },\n"
            "}];\n"
            "const sam3dBodyProportionSettings = () => settings;\n"
            "const sam3dManualShapeHasCorrections = (value) => Boolean(value?.active);\n"
            "const personList = () => persons;\n"
            f"{self.javascript[helper_start:helper_end]}\n"
            """
const preparing = sam3dBodyShapeCalibrationState();
settings = { targetUid: "Person", shapeRegions: [], manualShape: null };
const structureOnly = sam3dBodyShapeCalibrationState();
settings = { targetUid: "Person", shapeRegions: [], manualShape: { active: true } };
const manualOnly = sam3dBodyShapeCalibrationState();
settings = { targetUid: "Person", shapeRegions: ["waist"], manualShape: null };
persons[0].bodyProportions = {
  bodyShapeReady: true,
  bodyShapePreparing: false,
};
const ready = sam3dBodyShapeCalibrationState();
settings = { targetUid: "Person", shapeRegions: [], manualShape: null };
persons[0].bodyProportions = {
  bodyShapeReady: false,
  bodyShapePreparing: false,
  bodyShapeReason: "The neutral mesh could not be measured.",
};
const failed = sam3dBodyShapeCalibrationState();
process.stdout.write(JSON.stringify({
  preparing,
  structureOnly,
  manualOnly,
  ready,
  failed,
}));
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["preparing"]["requested"])
        self.assertFalse(result["preparing"]["ready"])
        self.assertTrue(result["preparing"]["preparing"])
        self.assertTrue(result["preparing"]["analyzeBlocked"])
        self.assertTrue(result["preparing"]["applyBlocked"])
        self.assertFalse(result["structureOnly"]["requested"])
        self.assertTrue(result["structureOnly"]["preparing"])
        self.assertFalse(result["structureOnly"]["analyzeBlocked"])
        self.assertTrue(result["structureOnly"]["applyBlocked"])
        self.assertTrue(result["manualOnly"]["requested"])
        self.assertTrue(result["manualOnly"]["analyzeBlocked"])
        self.assertTrue(result["ready"]["ready"])
        self.assertFalse(result["ready"]["preparing"])
        self.assertFalse(result["ready"]["analyzeBlocked"])
        self.assertFalse(result["ready"]["applyBlocked"])
        self.assertFalse(result["failed"]["preparing"])
        self.assertFalse(result["failed"]["analyzeBlocked"])
        self.assertTrue(result["failed"]["applyBlocked"])
        self.assertEqual(
            result["failed"]["reason"],
            "The neutral mesh could not be measured.",
        )

        render_start = self.javascript.index(
            "function renderSam3dBodyProportions("
        )
        render_end = self.javascript.index(
            "async function analyzeSam3dBodyProportions(", render_start
        )
        render = self.javascript[render_start:render_end]
        self.assertIn(
            "Preparing neutral body-shape calibration in VaM…",
            render,
        )
        self.assertIn("Neutral body-shape calibration ready", render)
        self.assertIn("bodyShapeReadinessChanged", render)
        analyze_disabled_start = render.index(
            "elements.sam3dProportionsAnalyze.disabled ="
        )
        analyze_disabled_end = render.index(
            "for (const region of SAM3D_BODY_PROPORTION_REGIONS)",
        )
        analyze_disabled = render[
            analyze_disabled_start:analyze_disabled_end
        ]
        apply_disabled_start = render.index(
            "elements.sam3dProportionsApply.disabled ="
        )
        apply_disabled_end = render.index("const undoReady =")
        apply_disabled = render[apply_disabled_start:apply_disabled_end]
        self.assertIn("bodyShapeAnalyzeBlocked", analyze_disabled)
        self.assertNotIn("bodyShapeApplyBlocked", analyze_disabled)
        self.assertIn("bodyShapeApplyBlocked", apply_disabled)

        activity_start = self.javascript.index(
            "async function loadActivity("
        )
        activity_end = self.javascript.index(
            "async function fetchLiveSceneSnapshot(", activity_start
        )
        activity = self.javascript[activity_start:activity_end]
        self.assertIn(
            "bodyShapeCalibrationPreparing",
            activity,
        )
        self.assertIn("sam3dBodyShapeCalibrationState().preparing", activity)
        self.assertIn("? SAM3D_POLL_MS", activity)
        self.assertIn("loadPersons({ quiet: true })", activity)

    def test_reports_percentages_confidence_disagreement_and_stale_state(self) -> None:
        for function_name in (
            "normalizeSam3dBodyMeasurement",
            "normalizeSam3dMorphChange",
            "normalizeSam3dBodyProportions",
            "renderSam3dBodyMeasurements",
            "renderSam3dMorphChanges",
            "renderSam3dShapeMeasurements",
            "renderSam3dShapeMorphChanges",
            "markSam3dBodyProportionsDirty",
        ):
            with self.subTest(function_name=function_name):
                self.assertIn(f"function {function_name}(", self.javascript)
        self.assertIn("reference_disagreement", self.javascript)
        self.assertIn("reference_consensus", self.javascript)
        self.assertIn("Reference disagreement", self.html)
        self.assertIn(
            "selected references or views disagree substantially",
            self.javascript,
        )
        self.assertIn("Analysis settings changed", self.javascript)
        self.assertIn("Current VaM → image target", self.html)
        self.assertIn("Proposed Structure changes", self.html)
        self.assertIn("Shape measurements", self.html)
        self.assertIn("Proposed Body Shape changes", self.html)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_shape_response_is_grouped_without_breaking_legacy_payloads(self) -> None:
        normalize_start = self.javascript.index("function sam3dBodyProportionRevision(")
        normalize_end = self.javascript.index(
            "async function loadSam3dBodyProportions(", normalize_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;\n"
            'const SAM3D_BODY_PROPORTION_REGIONS = ["arms", "legs", "torso", "widths"];\n'
            'const SAM3D_BODY_SHAPE_REGIONS = ["breasts", "waist", "hips", "glutes", "thighs"];\n'
            'const SAM3D_MANUAL_SHAPE_KEYS = ["breast_size", "breast_spacing", "waist_width", "hip_width", "glute_projection", "thigh_size"];\n'
            "const asArray = (value) => Array.isArray(value) ? value : [];\n"
            "const integerValue = (value) => {\n"
            "  const number = Number(value);\n"
            "  return Number.isInteger(number) ? number : null;\n"
            "};\n"
            "const normalizeSam3dBodyReferences = () => [];\n"
            "const normalizeSam3dManualShape = (value) => value || { schema: 1, offsets: {} };\n"
            f"{self.javascript[normalize_start:normalize_end]}\n"
            """
const analysisRevision = "a".repeat(32);
const grouped = normalizeSam3dBodyProportions({
  analysis_revision: analysisRevision,
  confidence: 0.92,
  shape_confidence: 0.81,
  measurements: [{
    id: "arm-ratio",
    region: "arms",
    current_ratio: 0.2,
    target_ratio: 0.22,
  }],
  shape_measurements: [{
    id: "bust-ratio",
    region: "breasts",
    current_ratio: 0.3,
    target_ratio: 0.36,
  }],
  proposed_morphs: [
    {
      id: "legs-length",
      region: "legs",
      current_value: 0.1,
      proposed_value: 0.2,
    },
    {
      id: "waist-width",
      region: "waist",
      fit_kind: "shape",
      current_value: 0.2,
      proposed_value: 0.15,
    },
  ],
  shape_unavailable: [{
    region: "glutes",
    control: "glute_projection",
    reason: "No verified Glutes Size morph is loaded.",
  }],
  manual_shape_changes: [{
    control: "breast_size",
    semanticOffset: 1,
    requestedOffset: 0.25,
    appliedOffset: 0.1,
    limited: true,
  }],
});
const explicit = normalizeSam3dBodyProportions({
  analysis_revision: analysisRevision,
  proposed_morphs: [{
    id: "combined-waist",
    region: "waist",
    fit_kind: "shape",
    current_value: 0,
    proposed_value: 0.1,
  }],
  shape_changes: [{
    id: "explicit-shape",
    fit_kind: "structure",
    current_value: 0,
    proposed_value: 0.25,
  }],
});
const legacy = normalizeSam3dBodyProportions({
  analysis_revision: analysisRevision,
  measurements: [{
    id: "torso-ratio",
    region: "torso",
    current_ratio: 0.4,
    target_ratio: 0.42,
  }],
  proposed_morphs: [{
    id: "torso-length",
    region: "torso",
    current_value: 0,
    proposed_value: 0.1,
  }],
});
const crowded = normalizeSam3dBodyProportions({
  analysis_revision: analysisRevision,
  shape_unavailable: [
    ...Array.from({ length: 9 }, (_, index) => ({
      region: "breasts",
      reason: `Automatic warning ${index}`,
    })),
    {
      region: "breasts",
      control: "breast_spacing",
      reason: "The exact spacing morph is unavailable.",
    },
  ],
});
process.stdout.write(JSON.stringify({
  grouped: {
    ready: grouped.ready,
    canApply: grouped.canApply,
    confidence: grouped.confidence,
    shapeConfidence: grouped.shapeConfidence,
    structureIds: grouped.morphs.map((item) => item.id),
    shapeIds: grouped.shapeMorphs.map((item) => item.id),
    allIds: grouped.allMorphs.map((item) => item.id),
    shapeMeasurementRegions:
      grouped.shapeMeasurements.map((item) => item.region),
    shapeUnavailable: grouped.shapeUnavailable,
    manualShapeChanges: grouped.manualShapeChanges,
  },
  explicit: {
    shapeIds: explicit.shapeMorphs.map((item) => item.id),
    shapeKinds: explicit.shapeMorphs.map((item) => item.fitKind),
    allIds: explicit.allMorphs.map((item) => item.id),
  },
  legacy: {
    ready: legacy.ready,
    shapeMeasurements: legacy.shapeMeasurements,
    shapeMorphs: legacy.shapeMorphs,
    shapeUnavailable: legacy.shapeUnavailable,
  },
  crowded: {
    displayedCount: crowded.shapeUnavailable.length,
    manualShapeUnavailable: crowded.manualShapeUnavailable,
  },
}));
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["grouped"]["ready"])
        self.assertTrue(result["grouped"]["canApply"])
        self.assertEqual(result["grouped"]["confidence"], 92)
        self.assertEqual(result["grouped"]["shapeConfidence"], 81)
        self.assertEqual(result["grouped"]["structureIds"], ["legs-length"])
        self.assertEqual(result["grouped"]["shapeIds"], ["waist-width"])
        self.assertEqual(
            result["grouped"]["allIds"],
            ["legs-length", "waist-width"],
        )
        self.assertEqual(
            result["grouped"]["shapeMeasurementRegions"],
            ["breasts"],
        )
        self.assertEqual(
            result["grouped"]["shapeUnavailable"],
            [
                {
                    "region": "glutes",
                    "control": "glute_projection",
                    "reason": "No verified Glutes Size morph is loaded.",
                }
            ],
        )
        self.assertEqual(
            result["grouped"]["manualShapeChanges"],
            [
                {
                    "control": "breast_size",
                    "semanticOffset": 1,
                    "requestedOffset": 0.25,
                    "appliedOffset": 0.1,
                    "limited": True,
                }
            ],
        )
        self.assertEqual(result["explicit"]["shapeIds"], ["explicit-shape"])
        self.assertEqual(result["explicit"]["shapeKinds"], ["shape"])
        self.assertEqual(result["explicit"]["allIds"], ["combined-waist"])
        self.assertTrue(result["legacy"]["ready"])
        self.assertEqual(result["legacy"]["shapeMeasurements"], [])
        self.assertEqual(result["legacy"]["shapeMorphs"], [])
        self.assertEqual(result["legacy"]["shapeUnavailable"], [])
        self.assertEqual(result["crowded"]["displayedCount"], 8)
        self.assertEqual(
            result["crowded"]["manualShapeUnavailable"],
            [
                {
                    "region": "breasts",
                    "control": "breast_spacing",
                    "reason": "The exact spacing morph is unavailable.",
                }
            ],
        )

    def test_unavailable_and_error_states_are_visible(self) -> None:
        self.assertIn("error.status === 404 || error.status === 501", self.javascript)
        self.assertIn("Body-proportion fitting unavailable", self.javascript)
        self.assertIn("Body analysis could not be loaded", self.javascript)
        self.assertIn(
            "The body-fit status could not be confirmed",
            self.javascript,
        )
        self.assertIn(
            "Body fit applied — preparing Undo…",
            self.javascript,
        )
        self.assertNotIn("No VaM changes were made", self.javascript)
        self.assertIn(".sam3d-proportions-state.is-error", self.styles)
        self.assertIn(".sam3d-proportions-state.is-unavailable", self.styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_confirmed_apply_enables_undo_after_poll(self) -> None:
        poll_start = self.javascript.index("async function pollSam3dBodyProportions(")
        poll_end = self.javascript.index(
            "function markSam3dBodyProportionsDirty(", poll_start
        )
        poll = self.javascript[poll_start:poll_end]
        self.assertIn("const bodyShapeReviewRequested =", poll)
        self.assertIn("restoredBodyShapeReady", poll)
        self.assertIn("analysis?.bodyShapeReady", poll)
        render_start = self.javascript.index("function renderSam3dBodyProportions(")
        render_end = self.javascript.index(
            "async function analyzeSam3dBodyProportions(", render_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;\n"
            'const SAM3D_BODY_PROPORTION_REGIONS = ["arms", "legs", "torso", "widths"];\n'
            'const SAM3D_BODY_SHAPE_REGIONS = ["breasts", "waist", "hips", "glutes", "thighs"];\n'
            "const SAM3D_BODY_PROPORTION_ACTIONS = Object.freeze({\n"
            '  analyze: "analyze", apply: "apply", undo: "undo",\n'
            "});\n"
            "const SAM3D_BODY_PROPORTION_POLL_ATTEMPTS = 300;\n"
            "const SAM3D_BODY_REFERENCE_MAX_COUNT = 8;\n"
            'const jobId = "a".repeat(32);\n'
            'const applyRevision = "b".repeat(32);\n'
            """
function makeElement() {
  const classes = new Set(["secondary-button"]);
  return {
    hidden: false,
    disabled: false,
    value: "",
    textContent: "",
    className: "",
    classList: {
      add(...values) { for (const value of values) classes.add(value); },
      remove(...values) { for (const value of values) classes.delete(value); },
      contains(value) { return classes.has(value); },
    },
    replaceChildren() {},
  };
}
const elements = new Proxy({}, {
  get(target, key) {
    if (!(key in target)) target[key] = makeElement();
    return target[key];
  },
});
const app = {
  view: "sam3d",
  sam3dHandoffTab: "morph",
  sam3dSelectedJobId: jobId,
  sam3dSelectedJob: { id: jobId, revision: jobId },
  sam3dJobs: [{ id: jobId, revision: jobId }],
  sam3dSelectedBodyIndex: 0,
  sam3dBodyReferences: [{ jobId, personIndex: 0 }],
  sam3dBodyProportionsJobId: jobId,
  sam3dBodyProportions: {
    available: true,
    ready: true,
    state: "queued",
    message: "Waiting for VaM confirmation.",
    targetUid: "Person",
    personIndex: 0,
    references: [{ jobId, personIndex: 0 }],
    analysisRevision: jobId,
    applyRevision: "",
    confidence: 90,
    disagreement: 2,
    measurements: [],
    morphs: [],
    shapeMeasurements: [],
    shapeMorphs: [],
    shapeUnavailable: [],
    shapeConfidence: 88,
    canApply: true,
    canUndo: false,
    applied: false,
    poseApplied: false,
  },
  sam3dBodyProportionsError: null,
  sam3dBodyProportionsInFlight: false,
  sam3dBodyProportionsDirty: false,
  sam3dBodyProportionsPendingAction:
    SAM3D_BODY_PROPORTION_ACTIONS.apply,
  sam3dBodyProportionPollTimer: null,
  sam3dBodyProportionPollAttempts: 0,
  sam3dMutationInFlight: false,
};
const toasts = [];
let rescheduled = 0;
const asArray = (value) => Array.isArray(value) ? value : [];
const sam3dJobSucceeded = () => true;
const resetSam3dBodyProportions = () => {};
const sam3dBodyProportionSettings = () => ({
  targetUid: "Person",
  personIndex: 0,
  referenceJobId: jobId,
  references: [{ jobId, personIndex: 0 }],
  regions: [...SAM3D_BODY_PROPORTION_REGIONS],
  strength: 75,
  shapeRegions: [],
  shapeStrength: 50,
});
const sam3dBodyProportionJob = () => app.sam3dSelectedJob;
const sam3dBodyShapeCalibrationState = () => ({ preparing: false });
const sam3dBodyReferencesReady = () => true;
const sam3dBodyReferenceSetIssue = () => "";
const serializeSam3dBodyReferences = (references) =>
  references.map((reference) =>
    `${reference.jobId}:${reference.personIndex}`).join(",");
const serializeSam3dManualShape = () => "";
const sam3dBodyProportionRegionControl = () => makeElement();
const sam3dBodyShapeRegionControl = () => makeElement();
const snapshotBridgeBusy = () => false;
const sam3dJobIsApplied = () => false;
const sam3dBodyConfidenceLabel = () => "90% · high";
const renderSam3dBodyMeasurements = () => {};
const renderSam3dMorphChanges = () => {};
const renderSam3dShapeMeasurements = () => {};
const renderSam3dShapeMorphChanges = () => {};
const renderSam3dManualFit = () => {};
const renderSam3dBodyProfileActionState = () => {};
const errorMessage = (error) => String(error?.message || error || "");
const toast = (title) => { toasts.push(title); };
const startSam3dBodyProportionPolling = () => { rescheduled += 1; };
const fetchLiveSceneSnapshot = async () => ({ persons: [] });
async function loadSam3dBodyProportions() {
  app.sam3dBodyProportions = {
    ...app.sam3dBodyProportions,
    state: "applied",
    message: "VaM confirmed the body morphs.",
    applyRevision,
    canUndo: true,
    applied: true,
  };
  return app.sam3dBodyProportions;
}
"""
            f"{self.javascript[poll_start:poll_end]}\n"
            f"{self.javascript[render_start:render_end]}\n"
            """
(async () => {
  renderSam3dBodyProportions();
  const queuedUndoDisabled = elements.sam3dProportionsUndo.disabled;
  await pollSam3dBodyProportions();
  process.stdout.write(JSON.stringify({
    queuedUndoDisabled,
    confirmedUndoDisabled: elements.sam3dProportionsUndo.disabled,
    confirmedUndoPrimary:
      elements.sam3dProportionsUndo.classList.contains("primary-button"),
    confirmedUndoSecondary:
      elements.sam3dProportionsUndo.classList.contains("secondary-button"),
    pendingAction: app.sam3dBodyProportionsPendingAction,
    pollAttempts: app.sam3dBodyProportionPollAttempts,
    stateTitle: elements.sam3dProportionsStateTitle.textContent,
    toasts,
    rescheduled,
  }));
})().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exitCode = 1;
});
"""
        )
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["queuedUndoDisabled"])
        self.assertFalse(result["confirmedUndoDisabled"])
        self.assertTrue(result["confirmedUndoPrimary"])
        self.assertFalse(result["confirmedUndoSecondary"])
        self.assertEqual(result["pendingAction"], "")
        self.assertEqual(result["pollAttempts"], 0)
        self.assertEqual(result["stateTitle"], "Body fit applied")
        self.assertEqual(result["toasts"], ["Body fit applied"])
        self.assertEqual(result["rescheduled"], 0)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_apply_poll_stops_on_unchanged_or_reconciliation_error(self) -> None:
        poll_start = self.javascript.index("async function pollSam3dBodyProportions(")
        poll_end = self.javascript.index(
            "function markSam3dBodyProportionsDirty(", poll_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_BODY_PROPORTION_ACTIONS = Object.freeze({\n"
            '  analyze: "analyze", apply: "apply", undo: "undo",\n'
            "});\n"
            "const SAM3D_BODY_PROPORTION_POLL_ATTEMPTS = 300;\n"
            """
const app = {
  managerAuthFailed: false,
  view: "sam3d",
  sam3dBodyProportionPollTimer: null,
  sam3dBodyProportionPollAttempts: 0,
  sam3dBodyProportionsPendingAction:
    SAM3D_BODY_PROPORTION_ACTIONS.apply,
  sam3dBodyProportionsError: null,
  sam3dBodyProportions: null,
};
let outcome = "settling";
let renders = 0;
let rescheduled = 0;
let analysisLoads = 0;
const toasts = [];
const sam3dBodyProportionJob = () => ({ id: "a".repeat(32) });
const sam3dBodyProportionSettings = () => ({
  targetUid: "Person",
  shapeRegions: [],
  manualShape: {},
});
const sam3dManualShapeHasCorrections = () => false;
const renderSam3dBodyProportions = () => { renders += 1; };
const startSam3dBodyProportionPolling = () => { rescheduled += 1; };
const toast = (title) => { toasts.push(title); };
const asArray = (value) => Array.isArray(value) ? value : [];
const fetchLiveSceneSnapshot = async () => ({
  persons: ["settling", "undo-settling", "failed-preparing"].includes(outcome)
    ? [{
        uid: "Person",
        bodyProportions: {
          undoPending: outcome === "settling",
          undoAvailable: false,
          bodyShapeReady: false,
          bodyShapePreparing: true,
        },
      }]
    : [],
});
async function loadSam3dBodyProportions() {
  analysisLoads += 1;
  if (outcome === "failed-preparing") {
    app.sam3dBodyProportionsError = null;
    app.sam3dBodyProportions = {
      ready: true,
      state: "error",
      message: "Bridge rejected the body fit.",
      applied: false,
      canApply: false,
      canUndo: false,
      applyRevision: "",
    };
    return app.sam3dBodyProportions;
  }
  if (outcome === "error") {
    app.sam3dBodyProportionsError =
      new Error("Could not read the bridge status.");
    return null;
  }
  app.sam3dBodyProportionsError = null;
  app.sam3dBodyProportions = {
    ready: true,
    state: "ok",
    message: "Body-proportion morphs applied.",
    applied: false,
    canApply: true,
    canUndo: false,
    applyRevision: "",
  };
  return app.sam3dBodyProportions;
}
"""
            f"{self.javascript[poll_start:poll_end]}\n"
            """
(async () => {
  await pollSam3dBodyProportions();
  const settling = {
    pendingAction: app.sam3dBodyProportionsPendingAction,
    state: app.sam3dBodyProportions.state,
    message: app.sam3dBodyProportions.message,
    hasError: Boolean(app.sam3dBodyProportionsError),
    analysisLoads,
    rescheduled,
  };

  outcome = "undo-settling";
  app.sam3dBodyProportionPollTimer = null;
  app.sam3dBodyProportionsPendingAction =
    SAM3D_BODY_PROPORTION_ACTIONS.undo;
  app.sam3dBodyProportionPollAttempts = 0;
  await pollSam3dBodyProportions();
  const undoSettling = {
    pendingAction: app.sam3dBodyProportionsPendingAction,
    state: app.sam3dBodyProportions.state,
    message: app.sam3dBodyProportions.message,
    analysisLoads,
    rescheduled,
  };

  outcome = "failed-preparing";
  app.sam3dBodyProportionPollTimer = null;
  app.sam3dBodyProportionsPendingAction =
    SAM3D_BODY_PROPORTION_ACTIONS.apply;
  app.sam3dBodyProportionPollAttempts = 0;
  await pollSam3dBodyProportions();
  const failedPreparing = {
    pendingAction: app.sam3dBodyProportionsPendingAction,
    error: app.sam3dBodyProportionsError?.message || "",
    analysisLoads,
    rescheduled,
  };

  outcome = "unchanged";
  app.sam3dBodyProportionPollTimer = null;
  app.sam3dBodyProportionsPendingAction =
    SAM3D_BODY_PROPORTION_ACTIONS.apply;
  app.sam3dBodyProportionPollAttempts = 0;
  app.sam3dBodyProportionsError = null;
  const unchanged = {
  };
  await pollSam3dBodyProportions();
  Object.assign(unchanged, {
    pendingAction: app.sam3dBodyProportionsPendingAction,
    pollAttempts: app.sam3dBodyProportionPollAttempts,
    state: app.sam3dBodyProportions.state,
    canApply: app.sam3dBodyProportions.canApply,
    message: app.sam3dBodyProportions.message,
    toasts: [...toasts],
    rescheduled,
  });

  outcome = "error";
  app.sam3dBodyProportionsPendingAction =
    SAM3D_BODY_PROPORTION_ACTIONS.apply;
  app.sam3dBodyProportionPollAttempts = 4;
  app.sam3dBodyProportionsError = null;
  await pollSam3dBodyProportions();
  const errored = {
    pendingAction: app.sam3dBodyProportionsPendingAction,
    pollAttempts: app.sam3dBodyProportionPollAttempts,
    error: app.sam3dBodyProportionsError.message,
    rescheduled,
  };
  process.stdout.write(JSON.stringify({
    settling,
    undoSettling,
    failedPreparing,
    unchanged,
    errored,
    renders,
    analysisLoads,
  }));
})().catch((error) => {
  process.stderr.write(String(error?.stack || error));
  process.exitCode = 1;
});
"""
        )
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
            result["settling"]["pendingAction"],
            "apply",
        )
        self.assertEqual(result["settling"]["state"], "settling")
        self.assertIn(
            "rebuilding neutral body-shape measurements",
            result["settling"]["message"],
        )
        self.assertFalse(result["settling"]["hasError"])
        self.assertEqual(result["settling"]["analysisLoads"], 0)
        self.assertEqual(result["settling"]["rescheduled"], 1)
        self.assertEqual(result["undoSettling"]["pendingAction"], "undo")
        self.assertEqual(result["undoSettling"]["state"], "reconciling")
        self.assertIn(
            "restored the morph values",
            result["undoSettling"]["message"],
        )
        self.assertEqual(result["undoSettling"]["analysisLoads"], 0)
        self.assertEqual(result["undoSettling"]["rescheduled"], 2)
        self.assertEqual(result["failedPreparing"]["pendingAction"], "")
        self.assertEqual(
            result["failedPreparing"]["error"],
            "Bridge rejected the body fit.",
        )
        self.assertEqual(result["failedPreparing"]["analysisLoads"], 1)
        self.assertEqual(result["failedPreparing"]["rescheduled"], 2)
        self.assertEqual(result["unchanged"]["pendingAction"], "")
        self.assertEqual(result["unchanged"]["pollAttempts"], 0)
        self.assertEqual(result["unchanged"]["state"], "unchanged")
        self.assertFalse(result["unchanged"]["canApply"])
        self.assertIn(
            "every requested morph was already",
            result["unchanged"]["message"],
        )
        self.assertEqual(result["unchanged"]["toasts"], ["Body fit unchanged"])
        self.assertEqual(result["unchanged"]["rescheduled"], 2)
        self.assertEqual(result["errored"]["pendingAction"], "")
        self.assertEqual(result["errored"]["pollAttempts"], 0)
        self.assertEqual(
            result["errored"]["error"],
            "Could not read the bridge status.",
        )
        self.assertEqual(result["errored"]["rescheduled"], 2)
        self.assertEqual(result["renders"], 5)
        self.assertEqual(result["analysisLoads"], 3)

    def test_panel_is_responsive(self) -> None:
        for selector in (
            ".sam3d-proportions-layout",
            ".sam3d-region-grid",
            ".sam3d-proportions-summary",
            ".sam3d-measurement-list",
            ".sam3d-morph-change-list",
            ".sam3d-shape-controls",
            ".sam3d-shape-region-grid",
            ".sam3d-shape-strength",
            ".sam3d-shape-results",
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

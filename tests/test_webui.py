from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "src" / "vampip" / "webui"


class WorkspaceWebUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEBUI / "index.html").read_text(encoding="utf-8")
        cls.javascript = (WEBUI / "app.js").read_text(encoding="utf-8")
        cls.styles = (WEBUI / "styles.css").read_text(encoding="utf-8")

    def test_workspace_is_a_top_level_asset_browser(self) -> None:
        self.assertIn('data-view="workspace"', self.html)
        self.assertNotIn('data-view="person"', self.html)
        self.assertIn('id="asset-workspace"', self.html)
        self.assertIn('id="asset-category-list"', self.html)
        self.assertIn("scenes, atoms, plugins, clothing, and Person presets", self.html)

    def test_library_uses_bounded_carousel_pages(self) -> None:
        for control_id in (
            "library-pagination",
            "page-previous",
            "page-status",
            "page-next",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertNotIn('id="load-more"', self.html)
        self.assertNotIn(">Load more<", self.html)
        self.assertIn(".library-pagination", self.styles)
        self.assertIn(".library-page-button", self.styles)

        self.assertIn("const PAGE_SIZE = 24;", self.javascript)
        self.assertIn("page: 1,", self.javascript)
        self.assertIn("function changeLibraryPage(page)", self.javascript)
        self.assertIn(
            "loadLibrary({ page: nextPage, scrollToResults: true })",
            self.javascript,
        )
        self.assertIn("offset = (resolvedPage - 1) * PAGE_SIZE;", self.javascript)
        self.assertIn('params.set("offset", String(offset));', self.javascript)
        self.assertIn("app.items = incoming;", self.javascript)
        self.assertNotIn("app.items.concat(incoming)", self.javascript)
        self.assertIn("resolvedPage > lastPage", self.javascript)
        self.assertIn("renderLibraryPagination();", self.javascript)
        self.assertIn(
            "Page ${formatNumber(app.page)} of ${formatNumber(",
            self.javascript,
        )
        self.assertIn("!pagination.hasPrevious", self.javascript)
        self.assertIn("!pagination.hasNext", self.javascript)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_library_pagination_state_clamps_boundaries(self) -> None:
        pagination_start = self.javascript.index(
            "function libraryPaginationState("
        )
        pagination_end = self.javascript.index(
            "function libraryPageCount(", pagination_start
        )
        number_start = self.javascript.index("function numberOr(")
        number_end = self.javascript.index("function formatNumber(", number_start)
        script = (
            '"use strict";\n'
            "const PAGE_SIZE = 24;\n"
            f"{self.javascript[pagination_start:pagination_end]}\n"
            f"{self.javascript[number_start:number_end]}\n"
            """
const output = {
  empty: libraryPaginationState(0, 99),
  exact: libraryPaginationState(24, 2),
  first: libraryPaginationState(100, 1),
  middle: libraryPaginationState(100, 3),
  last: libraryPaginationState(100, 99),
  malformed: libraryPaginationState(-10, "nope"),
};
process.stdout.write(JSON.stringify(output));
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
            result["empty"],
            {
                "total": 0,
                "page": 1,
                "pageCount": 1,
                "offset": 0,
                "hasPrevious": False,
                "hasNext": False,
            },
        )
        self.assertEqual(result["exact"]["page"], 1)
        self.assertEqual(result["exact"]["pageCount"], 1)
        self.assertEqual(result["first"]["offset"], 0)
        self.assertFalse(result["first"]["hasPrevious"])
        self.assertTrue(result["first"]["hasNext"])
        self.assertEqual(result["middle"]["offset"], 48)
        self.assertTrue(result["middle"]["hasPrevious"])
        self.assertTrue(result["middle"]["hasNext"])
        self.assertEqual(result["last"]["page"], 5)
        self.assertEqual(result["last"]["offset"], 96)
        self.assertTrue(result["last"]["hasPrevious"])
        self.assertFalse(result["last"]["hasNext"])
        self.assertEqual(result["malformed"], result["empty"])

    def test_person_controls_are_contextual(self) -> None:
        self.assertIn('id="person-context"', self.html)
        self.assertIn('id="person-target"', self.html)
        self.assertIn('id="select-person-button"', self.html)
        self.assertIn('id="add-person-button"', self.html)
        self.assertIn('id="atom-context"', self.html)
        self.assertIn('id="atom-target"', self.html)
        self.assertIn('id="select-atom-button"', self.html)
        self.assertIn('id="atom-target-mode"', self.html)
        self.assertIn('id="atom-mode-existing"', self.html)
        self.assertIn('id="atom-mode-create"', self.html)
        self.assertIn('id="atom-new-uid"', self.html)
        self.assertIn('id="add-atom-button"', self.html)
        self.assertIn('id="cua-choice-panel"', self.html)
        self.assertIn('id="cua-choice-select"', self.html)
        self.assertIn('id="cua-choice-button"', self.html)
        self.assertIn('id="cua-dll-state"', self.html)
        self.assertIn(
            'const PERSON_TARGET_KINDS = new Set(["person", "person-clothing-item"])',
            self.javascript,
        )
        self.assertIn("categoryUsesPersonContext(category)", self.javascript)
        self.assertIn('api("/api/vam/person/add"', self.javascript)
        self.assertIn('api("/api/vam/person/select"', self.javascript)
        self.assertIn('api("/api/vam/atom/select"', self.javascript)
        self.assertIn('api("/api/vam/atom/add"', self.javascript)
        self.assertNotIn("VaM will add and select", self.javascript)

    def test_workspace_uses_canonical_browse_and_apply_contracts(self) -> None:
        self.assertIn('api("/api/workspace/categories")', self.javascript)
        self.assertIn('api("/api/vam/scene")', self.javascript)
        self.assertIn('params.set("category", category.id)', self.javascript)
        self.assertIn('params.append("type", resourceType)', self.javascript)
        self.assertIn('api("/api/vam/resource/apply"', self.javascript)
        self.assertIn("requireBridgeQueue(result", self.javascript)
        self.assertIn("requireWorkspaceBridgeQueue(result", self.javascript)
        self.assertIn('typeof result.bridge_request === "string"', self.javascript)
        self.assertIn("result.bridge_busy !== true", self.javascript)
        self.assertIn("Required packages remain enabled", self.javascript)
        self.assertIn("snapshot.bridge_busy === true", self.javascript)
        self.assertNotIn('params.set("type", "Preset Hair")', self.javascript)
        self.assertNotIn('api("/api/vam/person/apply"', self.javascript)

    def test_individual_clothing_uses_desired_state_and_live_revision(self) -> None:
        self.assertIn(
            'category.operation === "set-person-clothing"',
            self.javascript,
        )
        self.assertIn(
            'params.set("target_uid", app.selectedPersonUid)',
            self.javascript,
        )
        block_start = self.javascript.index("async function setPersonClothing(")
        block_end = self.javascript.index(
            "function workspaceApplyAvailability(", block_start
        )
        block = self.javascript[block_start:block_end]
        self.assertIn('api("/api/vam/person/clothing"', block)
        self.assertIn("resource_id: resourceId", block)
        self.assertIn("const targetUid = app.selectedPersonUid", block)
        self.assertIn("target_uid: targetUid", block)
        self.assertIn("active: availability.desiredActive", block)
        self.assertIn("revision: availability.revision", block)
        for forbidden in (
            "resource_ref:",
            "resource_path:",
            "clothing_uid:",
            "storable:",
            "action:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)

        availability_start = self.javascript.index(
            "function clothingActionAvailability("
        )
        availability_end = self.javascript.index(
            "async function setPersonClothing(", availability_start
        )
        availability = self.javascript[availability_start:availability_end]
        for guard in (
            "category.requiredCapability",
            "!snapshot.available",
            "!liveClothing.ready",
            "item.clothing_compatible",
            "item.clothing_locked",
            "item.clothing_revision",
            "liveClothing?.revision",
            'typeof item.worn !== "boolean"',
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, availability)
        self.assertIn(
            "item.worn !== true && item.clothing_compatible !== true",
            availability,
        )
        self.assertIn("person.clothing?.revision", self.javascript)
        self.assertIn(
            "if (isIndividualClothingCategory()) {\n"
            "          await loadLibrary({ preservePage: true });",
            self.javascript,
        )

    def test_live_scene_responses_cannot_overwrite_a_newer_snapshot(self) -> None:
        self.assertIn("personRequestGeneration: 0", self.javascript)
        self.assertIn(
            "const sceneRequestGeneration = beginPersonSnapshotRequest();",
            self.javascript,
        )
        accept_start = self.javascript.index("function acceptPersonSnapshot(")
        accept_end = self.javascript.index("async function loadPersons(", accept_start)
        accept = self.javascript[accept_start:accept_end]
        self.assertIn(
            "!personSnapshotRequestIsCurrent(generation)",
            accept,
        )
        self.assertGreaterEqual(accept.count("return false;"), 2)

        load_start = self.javascript.index("async function loadPersons(")
        load_end = self.javascript.index("function renderPersonContext()", load_start)
        load = self.javascript[load_start:load_end]
        self.assertIn(
            "const requestGeneration = beginPersonSnapshotRequest();",
            load,
        )
        self.assertIn(
            "acceptPersonSnapshot(snapshot, requestGeneration)",
            load,
        )
        self.assertIn(
            "acceptPersonSnapshotError(error, requestGeneration)",
            load,
        )
        self.assertIn("if (responseAccepted) {", load)

    def test_live_scene_poll_updates_global_bridge_feedback(self) -> None:
        load_start = self.javascript.index("async function loadPersons(")
        load_end = self.javascript.index("function renderPersonContext()", load_start)
        load = self.javascript[load_start:load_end]
        self.assertIn("if (responseAccepted) {", load)
        self.assertIn(
            "await syncPersonEquipment({ quiet: true });",
            load,
        )
        self.assertIn("renderLiveState(app.status || {});", load)
        self.assertLess(
            load.index("await syncPersonEquipment({ quiet: true });"),
            load.index("renderLiveState(app.status || {});"),
        )

        render_start = self.javascript.index("function renderLiveState(")
        render_end = self.javascript.index("function renderAccess()", render_start)
        render = self.javascript[render_start:render_end]
        self.assertIn(
            "const bridge = app.person?.bridge || status.bridge;",
            render,
        )
        self.assertIn("bridge.message", render)

    def test_clothing_browse_only_cards_keep_package_access_controls(self) -> None:
        card_start = self.javascript.index("function createResourceCard(")
        card_end = self.javascript.index(
            "function appendPackageAccessActions(", card_start
        )
        card = self.javascript[card_start:card_end]
        self.assertIn("if (workspaceCategory.liveAction) {", card)
        self.assertIn("if (!availability.allowed) {", card)
        self.assertIn("appendPackageAccessActions(actions, item", card)

        access_start = card_end
        access_end = self.javascript.index(
            "function isIndividualClothingCategory(", access_start
        )
        access = self.javascript[access_start:access_end]
        self.assertIn('"Keep for 3 days"', access)
        self.assertIn('"Enable for 3 days"', access)
        self.assertIn("createThreeDayLease(", access)
        self.assertIn("addPin(root, title, pinButton)", access)

    def test_resource_updates_are_visible_and_exact_version_actions(self) -> None:
        card_start = self.javascript.index("function createResourceCard(")
        card_end = self.javascript.index(
            "function isIndividualClothingCategory(", card_start
        )
        card = self.javascript[card_start:card_end]
        self.assertIn("resourceUpdateVersion(item)", card)
        self.assertIn("v${resourceSelectedVersion(item)} → v${updateVersion}", card)
        self.assertIn("`Update to v${packageVersion}`", card)
        self.assertIn("item.update_available !== true", card)
        self.assertIn("Number.isInteger(version)", card)

        clothing_start = self.javascript.index("async function setPersonClothing(")
        clothing_end = self.javascript.index(
            "function workspaceApplyAvailability(", clothing_start
        )
        clothing = self.javascript[clothing_start:clothing_end]
        self.assertIn("requestBody.package_version = packageVersion", clothing)
        self.assertIn("requestBody.active = true", clothing)

        apply_start = self.javascript.index("async function applyWorkspaceResource(")
        apply_end = self.javascript.index("function createPackageCard(", apply_start)
        apply = self.javascript[apply_start:apply_end]
        self.assertIn("body.package_version = packageVersion", apply)

        lease_start = self.javascript.index("async function createThreeDayLease(")
        lease_end = self.javascript.index("async function addPin(", lease_start)
        lease = self.javascript[lease_start:lease_end]
        self.assertIn(
            "resourceLeaseBody.package_version = packageVersion",
            lease,
        )
        self.assertIn(".meta-pill.version-update", self.styles)
        self.assertIn(".resource-update-button", self.styles)

    def test_workspace_category_failures_retry_automatically(self) -> None:
        self.assertIn("workspaceCategoriesRetryAt: 0", self.javascript)
        activity_start = self.javascript.index("async function loadActivity(")
        activity_end = self.javascript.index(
            "async function fetchLiveSceneSnapshot()", activity_start
        )
        activity = self.javascript[activity_start:activity_end]
        self.assertIn("app.workspaceCategoriesError", activity)
        self.assertIn(
            "Date.now() - app.workspaceCategoriesRetryAt > 5000",
            activity,
        )
        self.assertIn("scheduleRefresh = true", activity)
        self.assertIn(
            "app.workspaceCategoriesRetryAt = 0",
            self.javascript,
        )

    def test_clothing_action_keeps_original_target_and_current_page(self) -> None:
        action_start = self.javascript.index("async function setPersonClothing(")
        action_end = self.javascript.index(
            "function workspaceApplyAvailability(", action_start
        )
        action = self.javascript[action_start:action_end]
        self.assertIn("const targetUid = app.selectedPersonUid;", action)
        self.assertIn("target_uid: targetUid", action)
        self.assertIn("for ${targetUid}.", action)
        self.assertNotIn("for ${app.selectedPersonUid}.", action)

        library_start = self.javascript.index("async function loadLibrary(")
        library_end = self.javascript.index("function renderStatus()", library_start)
        library = self.javascript[library_start:library_end]
        self.assertIn("preservePage = false", library)
        self.assertIn(
            "page === null ? (preservePage ? app.page : 1)",
            library,
        )
        self.assertIn("limit: String(PAGE_SIZE)", library)
        self.assertNotIn("Math.min(Math.max(PAGE_SIZE, app.items.length)", library)
        self.assertGreaterEqual(
            self.javascript.count("loadLibrary({ preservePage: true })"),
            4,
        )

    def test_scene_replace_requires_explicit_confirmation(self) -> None:
        self.assertIn("Replace current scene", self.javascript)
        self.assertIn("confirm_replace: confirmedReplace", self.javascript)
        self.assertIn("confirmSceneLoad(item, merge)", self.javascript)
        self.assertIn("merge,", self.javascript)
        self.assertIn(
            "confirmRiskyAssetLoad(item, category, merge)",
            self.javascript,
        )
        self.assertIn("confirm_critical: confirmedRisk", self.javascript)

    def test_scene_load_claims_action_and_shows_feedback_before_request(
        self,
    ) -> None:
        start = self.javascript.index("async function applyWorkspaceResource(")
        end = self.javascript.index("function createPackageCard(", start)
        action = self.javascript[start:end]

        guard = "app.applyingWorkspaceResources.has(key)"
        claim = "app.applyingWorkspaceResources.add(key);"
        confirmation = "await confirmSceneLoad(item, merge)"
        feedback = "startWorkspaceActionFeedback(item, category, key, state)"
        rerender = 'if (app.view === "workspace") renderLibrary();'
        request = 'await api("/api/vam/resource/apply"'
        for fragment in (
            guard,
            claim,
            confirmation,
            feedback,
            '"Enabling packages…"',
            "bindWorkspaceActionRequest(action, result, detail)",
            "app.applyingWorkspaceResources.delete(key)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, action)

        self.assertLess(action.index(guard), action.index(claim))
        self.assertLess(action.index(claim), action.index(confirmation))
        self.assertLess(action.index(feedback), action.index(request))
        self.assertLess(action.index(rerender), action.index(request))
        self.assertEqual(
            action.count('api("/api/vam/resource/apply"'),
            1,
        )

    def test_workspace_action_tracks_exact_bridge_request_until_terminal(
        self,
    ) -> None:
        self.assertIn("workspaceAction: null", self.javascript)
        sync_start = self.javascript.index("function syncWorkspaceActionSnapshot(")
        sync_end = self.javascript.index(
            "function finishWorkspaceActionFeedback(", sync_start
        )
        sync = self.javascript[sync_start:sync_end]
        exact_match = "observedRequestId !== action.requestId"
        self.assertIn(
            'const observedRequestId = String(bridge.requestId || "").trim()',
            sync,
        )
        self.assertIn(exact_match, sync)
        self.assertLess(
            sync.index(exact_match),
            sync.index('if (stage === "ok" || stage === "error")'),
        )
        self.assertIn('!["ok", "error"].includes(stage)', sync)

        render_start = self.javascript.index("function renderWorkspaceActionFeedback(")
        render_end = self.javascript.index(
            "function workspaceApplyAvailability(", render_start
        )
        render = self.javascript[render_start:render_end]
        for stage in (
            "enabling",
            "queued",
            "deferred-loading",
            "rescanning",
            "loading-scene",
            "ok",
            "error",
        ):
            with self.subTest(stage=stage):
                self.assertIn(f'action.stage === "{stage}"', render)

        activity_start = self.javascript.index("async function loadActivity(")
        activity_end = self.javascript.index(
            "async function fetchLiveSceneSnapshot()", activity_start
        )
        activity = self.javascript[activity_start:activity_end]
        self.assertIn("workspaceActionIsActive() ||", activity)
        self.assertIn(
            "workspaceActionIsActive() || app.pendingHairMutation ? 900 : 3000",
            activity,
        )
        self.assertIn("instanceChanged && workspaceActionIsActive()", activity)
        self.assertIn(
            'if (app.view === "workspace" && activityChanged)',
            activity,
        )
        self.assertIn("operationIsBusy(previous) !== busy", activity)

        sync_activity_start = self.javascript.index(
            "function syncWorkspaceActionActivity("
        )
        sync_activity_end = self.javascript.index(
            "function recoverWorkspaceActionFeedback(", sync_activity_start
        )
        sync_activity = self.javascript[sync_activity_start:sync_activity_end]
        self.assertIn("WORKSPACE_ACTION_STALL_MS", sync_activity)
        self.assertIn('operation.run_name !== "managed-reconcile"', sync_activity)
        self.assertIn(
            "operationId <= numberOr(action.previousOperationId, 0)",
            sync_activity,
        )
        self.assertIn("activity?.vam?.running === false", sync_activity)

        recover_start = self.javascript.index(
            "function recoverWorkspaceActionFeedback("
        )
        recover_end = self.javascript.index(
            "function syncWorkspaceActionSnapshot(", recover_start
        )
        recover = self.javascript[recover_start:recover_end]
        self.assertIn("snapshot?.vam_running !== true", recover)
        self.assertIn("snapshot?.available !== true", recover)
        self.assertIn("bridge.lastCompletedRequestId", sync)
        self.assertIn(
            "lastCompletedRequestId === action.requestId",
            sync,
        )

    def test_workspace_action_toast_is_persistent_and_visibly_busy(self) -> None:
        toast_start = self.javascript.index("function updateToast(")
        toast_end = self.javascript.index("function setButtonBusy(", toast_start)
        toast_block = self.javascript[toast_start:toast_end]
        self.assertIn("options = {}", toast_block)
        self.assertIn("if (!options.persistent)", toast_block)
        self.assertIn("return item;", toast_block)
        self.assertIn('close.hidden = kind === "busy"', toast_block)
        self.assertIn(".toast.is-busy .toast-dot", self.styles)
        self.assertIn("@keyframes action-pulse", self.styles)

    def test_atom_subscene_and_cua_apply_use_catalog_owned_actions(self) -> None:
        self.assertIn('"apply-atom-preset"', self.javascript)
        self.assertIn('"load-subscene"', self.javascript)
        self.assertIn('"load-custom-unity-asset"', self.javascript)
        self.assertIn("create_if_missing: createIfMissing", self.javascript)
        self.assertIn("entry.create_supported", self.javascript)
        self.assertIn("entry.create_capability", self.javascript)
        self.assertIn("categorySupportsTargetCreation", self.javascript)
        self.assertIn("categoryCreateCapability", self.javascript)
        self.assertIn("category_id: category.id", self.javascript)
        self.assertIn("target_uid: targetUid", self.javascript)
        self.assertIn('category.createCapability || "atom-add"', self.javascript)
        self.assertIn(
            "elements.addAtomButton.hidden = !categoryUsesManagedAtomTarget(category)",
            self.javascript,
        )
        self.assertNotIn("body.atom_type", self.javascript)
        self.assertNotIn("body.resource_path", self.javascript)
        self.assertNotIn("body.operation", self.javascript)

    def test_custom_unity_asset_load_is_typed_and_dll_safe(self) -> None:
        self.assertIn('"custom-unity-asset": "customunityasset"', self.javascript)
        self.assertIn("Create & load Unity asset", self.javascript)
        self.assertIn("Load Unity asset", self.javascript)
        self.assertIn(
            "DLL loading is forced off before this bundle loads",
            self.javascript,
        )
        self.assertIn(
            "Code already active in this VaM session cannot be unloaded",
            self.javascript,
        )
        self.assertIn(
            "Single-item bundles load automatically; multi-item bundles stay at None",
            self.javascript,
        )
        self.assertIn(
            'category.operation === "load-custom-unity-asset"',
            self.javascript,
        )

    def test_cua_choice_uses_only_live_token_and_numeric_index(self) -> None:
        block_start = self.javascript.index("async function selectCuaChoiceInVam()")
        block_end = self.javascript.index(
            "async function selectPersonInVam()", block_start
        )
        block = self.javascript[block_start:block_end]
        self.assertIn(
            'api("/api/vam/custom-unity-asset/choice"',
            block,
        )
        self.assertIn("target_uid: target.uid", block)
        self.assertIn("choice_index: choice.index", block)
        self.assertIn("choice_token: state.choiceToken", block)
        self.assertIn("integerValue(elements.cuaChoiceSelect.value)", block)
        for forbidden in (
            "asset_name:",
            "assetName:",
            "resource_path:",
            "atom_type:",
            "loadDll:",
            "load_dll:",
            "operation:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)

    def test_cua_choice_panel_consumes_bounded_bridge_state(self) -> None:
        for field in (
            "raw.loadDll",
            "raw.ready",
            "raw.choiceToken",
            "raw.choiceCount",
            "raw.selectedIndex",
            "raw.choicesTruncated",
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.javascript)
        self.assertIn("choice.index", self.javascript)
        self.assertIn("choice.label", self.javascript)
        self.assertIn("new Option(choice.label, String(choice.index))", self.javascript)
        self.assertIn('"custom-unity-asset-choice"', self.javascript)
        self.assertIn("state.loadDll !== false", self.javascript)
        self.assertIn("!state.choiceToken", self.javascript)
        self.assertIn("state.choicesTruncated", self.javascript)
        self.assertIn("Multi-item bundles stay at None", self.javascript)
        self.assertNotIn(".innerHTML", self.javascript)

    def test_cua_choice_requires_server_owned_fresh_live_context(self) -> None:
        helper_start = self.javascript.index("function cuaChoiceLiveContextReason(")
        helper_end = self.javascript.index(
            "function updateCuaChoiceButton()", helper_start
        )
        helper = self.javascript[helper_start:helper_end]
        for guard in (
            "category?.liveAction",
            'app.workspaceCategoriesSource !== "server"',
            "app.workspaceCategoriesError",
            "app.personError",
            "personVamRunning(snapshot)",
            "!snapshot.available",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, helper)

        action_start = self.javascript.index("async function selectCuaChoiceInVam()")
        action_end = self.javascript.index(
            "async function selectPersonInVam()", action_start
        )
        action = self.javascript[action_start:action_end]
        self.assertIn(
            "cuaChoiceLiveContextReason(category, snapshot)",
            action,
        )
        self.assertIn("liveContextReason ||", action)

    def test_cua_fallback_stays_browse_only(self) -> None:
        category_start = self.javascript.index('id: "custom-unity-assets"')
        category_end = self.javascript.index('id: "plugins"', category_start)
        fallback = self.javascript[category_start:category_end]
        self.assertIn('operation: "load-custom-unity-asset"', fallback)
        self.assertIn("live_action: false", fallback)

    def test_new_atom_target_cannot_request_merge(self) -> None:
        self.assertIn("const creatingManagedTarget =", self.javascript)
        self.assertIn(
            "category.mergeSupported && !creatingManagedTarget",
            self.javascript,
        )
        self.assertIn("syncWorkspaceApplyModeControls(category)", self.javascript)
        self.assertIn("BrowserAssist cannot merge", self.javascript)
        self.assertIn(
            '!createIfMissing && app.workspaceApplyMode === "merge"',
            self.javascript,
        )

    def test_fallback_covers_broad_asset_families(self) -> None:
        for resource_type in (
            "Scene",
            "SubScenes",
            "Preset Atom",
            "Custom Unity Assets",
            "Plugins",
            "Clothing (Female)",
            "Clothing (Male)",
            "Preset Appearance",
            "Preset Clothing",
            "Preset Hair",
            "Preset Morphs",
            "Preset Pose",
            "Preset Skin",
        ):
            with self.subTest(resource_type=resource_type):
                self.assertIn(f'"{resource_type}"', self.javascript)

        self.assertIn('"apply-person-preset"', self.javascript)
        self.assertIn('"person-preset-hair"', self.javascript)
        self.assertIn('"person-preset-plugins"', self.javascript)

    def test_workspace_has_responsive_category_and_context_styles(self) -> None:
        for selector in (
            ".asset-workspace",
            ".asset-category-list",
            ".asset-category-button.is-active",
            ".asset-category-panel",
            ".asset-apply-mode",
            ".target-mode",
            ".person-context",
            ".cua-choice-panel",
            ".cua-dll-state",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)

    def test_character_sheet_has_identity_shortcuts_and_multi_item_regions(
        self,
    ) -> None:
        for element_id in (
            "character-sheet",
            "character-shortcuts",
            "character-identity-name",
            "character-identity-gender",
            "character-identity-counts",
            "wardrobe-sheet",
            "equipment-slots-left",
            "equipment-slots-right",
            "equipment-slots-extra",
            "equipment-warning",
            "hair-studio",
            "hair-layer-list",
            "hair-inspector-groups",
            "hair-warning",
            "character-recipe",
            "character-recipe-scopes",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn('class="character-silhouette"', self.html)
        self.assertIn('aria-label="Person customization shortcuts"', self.html)
        for group in (
            "Appearance",
            "Wardrobe",
            "Motion",
            "Body",
            "Extensions",
        ):
            with self.subTest(group=group):
                self.assertIn(f'label: "{group}"', self.javascript)
        for category_id in (
            "preset-appearance",
            "preset-hair",
            "preset-skin",
            "preset-morphs",
            "preset-clothing",
            "clothing-item-presets",
            "preset-pose",
            "preset-animation",
            "preset-breast-physics",
            "preset-glute-physics",
            "preset-general",
            "preset-plugins",
        ):
            with self.subTest(category_id=category_id):
                self.assertIn(f'["{category_id}",', self.javascript)

        dispatch_start = self.javascript.index("function renderCharacterSheet()")
        dispatch_end = self.javascript.index(
            "async function removeEquippedItem(", dispatch_start
        )
        dispatch = self.javascript[dispatch_start:dispatch_end]
        self.assertIn('mode === "wardrobe"', dispatch)
        self.assertIn('mode === "hair"', dispatch)
        self.assertIn("renderCharacterRecipe(category)", dispatch)

        render_start = self.javascript.index(
            "function renderWardrobeCharacterSheet("
        )
        render_end = self.javascript.index(
            "function createHairLayerCard(", render_start
        )
        render = self.javascript[render_start:render_end]
        self.assertIn(
            "grouped.get(equipmentSlotForItem(item))?.push(item)",
            render,
        )
        self.assertIn("activeCount", render)
        self.assertIn("lockedCount", render)
        self.assertIn("unidentifiedCount", render)
        self.assertIn("equipment?.truncated", render)
        self.assertIn('"Unsorted"', self.javascript)
        slot_start = self.javascript.index("function equipmentSlotForItem(")
        slot_end = self.javascript.index("function resourceThumbnailUrl(", slot_start)
        slot = self.javascript[slot_start:slot_end]
        self.assertIn("resourceTitle(item)", slot)
        self.assertIn("normalizeTags(", slot)
        self.assertIn("const explicitSlot = explicitEquipmentSlot(item)", slot)
        self.assertIn("if (explicitSlot) return explicitSlot", slot)
        self.assertIn('return "unsorted"', slot)

    def test_character_sheet_equipment_fetch_is_revision_keyed_and_stale_safe(
        self,
    ) -> None:
        start = self.javascript.index("async function syncPersonEquipment(")
        end = self.javascript.index("function characterGender()", start)
        block = self.javascript[start:end]
        self.assertIn("new AbortController()", block)
        self.assertIn(
            "api(`/api/vam/person/equipment?${params.toString()}`",
            block,
        )
        self.assertIn(
            "app.personEquipmentAttemptedKey === identity.key",
            block,
        )
        self.assertIn("personEquipmentRequestIsCurrent(", block)
        self.assertIn("responseTarget !== identity.targetUid", block)
        self.assertIn("responseRevision !== identity.revision", block)
        self.assertIn(
            "app.personEquipmentAttemptedKey = identity.key",
            block,
        )
        self.assertIn(
            "refreshAll({ force: true, retryEquipment: true })",
            self.javascript,
        )
        refresh_start = self.javascript.index("async function refreshAll(")
        refresh_end = self.javascript.index(
            "function renderSessionPlugins()", refresh_start
        )
        refresh = self.javascript[refresh_start:refresh_end]
        self.assertIn(
            "retry: Boolean(options.retryEquipment)",
            refresh,
        )
        identity_start = self.javascript.index("function personEquipmentIdentity(")
        identity_end = self.javascript.index(
            "function personEquipmentRequestIsCurrent(", identity_start
        )
        identity = self.javascript[identity_start:identity_end]
        self.assertIn("clothing?.ready !== true", identity)
        self.assertIn("`${targetUid}\\u0000${revision}`", identity)

    def test_character_sheet_uses_category_specific_modes(self) -> None:
        for category_id in (
            "preset-clothing",
            "clothing-items-female",
            "clothing-items-male",
            "clothing-item-presets",
        ):
            with self.subTest(category_id=category_id):
                self.assertIn(f'"{category_id}"', self.javascript)
        self.assertIn(
            'const HAIR_CATEGORY_IDS = new Set(["preset-hair"])',
            self.javascript,
        )
        start = self.javascript.index("function characterSheetMode(")
        end = self.javascript.index("function workspaceFacetCounts(", start)
        mode = self.javascript[start:end]
        self.assertIn('return "hair"', mode)
        self.assertIn('return "wardrobe"', mode)
        self.assertIn('return "recipe"', mode)

        dispatch_start = self.javascript.index("function renderCharacterSheet()")
        dispatch_end = self.javascript.index(
            "async function removeEquippedItem(", dispatch_start
        )
        dispatch = self.javascript[dispatch_start:dispatch_end]
        self.assertIn("renderWardrobeCharacterSheet(category)", dispatch)
        self.assertIn("renderHairStudio(category)", dispatch)
        self.assertIn("renderCharacterRecipe(category)", dispatch)

    def test_wardrobe_taxonomy_is_explicit_multi_item_and_exact(self) -> None:
        for label in (
            "Tops & outerwear",
            "Bras",
            "Panties & underwear",
            "Bottoms",
            "Stockings & socks",
            "Dresses & full outfits",
            "Shoes & boots",
            "High heels",
            "Head & face",
            "Neck",
            "Arms & hands",
            "Accessories",
            "Body FX",
            "Unsorted",
        ):
            with self.subTest(label=label):
                self.assertIn(f'label: "{label}"', self.javascript)

        slot_start = self.javascript.index("function equipmentSlotForItem(")
        slot_end = self.javascript.index("function resourceThumbnailUrl(", slot_start)
        slot = self.javascript[slot_start:slot_end]
        self.assertLess(
            slot.index("if (explicitSlot) return explicitSlot"),
            slot.index("const searchable ="),
        )
        self.assertIn("slot.tags.some((tag) => terms.has(tag))", slot)
        self.assertNotIn(".includes(tag)", slot)
        self.assertLess(
            self.javascript.index('"high-heels",', self.javascript.index(
                "const CHARACTER_SLOT_CLASSIFICATION_ORDER"
            )),
            self.javascript.index('"shoes-boots",', self.javascript.index(
                "const CHARACTER_SLOT_CLASSIFICATION_ORDER"
            )),
        )

    def test_unresolved_equipment_stays_visible_but_never_actionable(self) -> None:
        normalize_start = self.javascript.index("function normalizePersonEquipment(")
        normalize_end = self.javascript.index(
            "async function syncPersonEquipment(", normalize_start
        )
        normalize = self.javascript[normalize_start:normalize_end]
        self.assertIn("id: null", normalize)
        self.assertIn("actionable: false", normalize)
        self.assertIn("presentation_key: safeOpaqueKey(", normalize)
        self.assertIn("safePresentationLabel(", normalize)

        row_start = self.javascript.index("function createEquippedItem(")
        row_end = self.javascript.index("function createEquipmentSlot(", row_start)
        row = self.javascript[row_start:row_end]
        self.assertIn("item.actionable !== false", row)
        self.assertIn('createElement("span", "equipment-in-game-badge")', row)
        self.assertIn('inGame.textContent = "In-game item"', row)
        self.assertLess(row.index("if (!actionable)"), row.index(
            "const category = clothingCategoryForItem(item)"
        ))
        self.assertLess(row.index("return row;"), row.index(
            "const category = clothingCategoryForItem(item)"
        ))

        remove_start = self.javascript.index("async function removeEquippedItem(")
        remove_end = self.javascript.index("async function loadPersons(", remove_start)
        removal = self.javascript[remove_start:remove_end]
        self.assertIn("item.actionable === false", removal)
        self.assertIn("VAM-PIP will not guess a removal action", removal)
        self.assertIn(".equipment-in-game-badge", self.styles)
        self.assertIn(".equipped-item.is-presentation-only", self.styles)

    def test_hair_studio_reads_layers_without_faking_settings(self) -> None:
        for element_id in (
            "hair-studio",
            "hair-studio-summary",
            "hair-layer-list",
            "hair-inspector-groups",
            "hair-warning",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)
        for group in (
            "Style & shape",
            "Color & materials",
            "Physics & simulation",
            "Scalp & fit",
        ):
            with self.subTest(group=group):
                self.assertIn(f'title: "{group}"', self.javascript)

        sync_start = self.javascript.index("async function syncPersonHair(")
        sync_end = self.javascript.index("function characterGender()", sync_start)
        sync = self.javascript[sync_start:sync_end]
        self.assertIn(
            "api(`/api/vam/person/hair?${params.toString()}`",
            sync,
        )
        self.assertIn("new AbortController()", sync)
        self.assertIn("personHairRequestIsCurrent(", sync)
        self.assertIn("responseTarget !== identity.targetUid", sync)
        self.assertIn("responseRevision !== identity.revision", sync)

        identity_start = self.javascript.index("function personHairIdentity()")
        identity_end = self.javascript.index(
            "function personHairRequestIsCurrent(", identity_start
        )
        identity = self.javascript[identity_start:identity_end]
        self.assertIn("const hair = selectedPersonHair()", identity)
        self.assertIn("hair?.ready !== true", identity)
        self.assertIn("`${targetUid}\\u0000${revision}`", identity)

        current_start = identity_end
        current_end = self.javascript.index(
            "function cancelPersonHairRequest(", current_start
        )
        current = self.javascript[current_start:current_end]
        self.assertIn("identity.revision === revision", current)
        self.assertNotIn("characterSheetMode()", current)

        render_start = self.javascript.index("function renderHairStudio(")
        render_end = self.javascript.index("function renderCharacterRecipe(", render_start)
        render = self.javascript[render_start:render_end]
        self.assertIn("hair?.items || []", render)
        self.assertIn("createHairLayerCard(item, index, hair)", render)
        self.assertIn("item.locked", render)
        self.assertIn("item.actionable", render)
        self.assertIn("lockedCount", render)
        self.assertIn("VAM-PIP will not guess the current preset", render)
        self.assertNotIn("type = \"range\"", render)
        self.assertNotIn("createElement(\"input\"", render)

        hair_html_start = self.html.index('class="hair-studio"')
        hair_html_end = self.html.index('class="character-recipe"', hair_html_start)
        hair_html = self.html[hair_html_start:hair_html_end]
        self.assertIn("Typed hair controls are not available yet", hair_html)
        self.assertNotIn('type="range"', hair_html)

    def test_hair_disable_is_exact_revision_keyed_and_presentation_safe(
        self,
    ) -> None:
        normalize_start = self.javascript.index("function normalizePersonHair(")
        normalize_end = self.javascript.index(
            "async function syncPersonHair(", normalize_start
        )
        normalize = self.javascript[normalize_start:normalize_end]
        self.assertIn("const seen = new Map()", normalize)
        self.assertIn("const actionKey = safeHairActionKey(key)", normalize)
        self.assertIn("Boolean(actionKey)", normalize)
        self.assertIn("const duplicate = seen.get(key)", normalize)
        self.assertIn("duplicate.actionable = false", normalize)
        self.assertIn("seen.set(key, normalizedItem)", normalize)

        card_start = self.javascript.index("function createHairLayerCard(")
        card_end = self.javascript.index(
            "function renderHairInspectorGroups(", card_start
        )
        card = self.javascript[card_start:card_end]
        self.assertIn("if (item.locked)", card)
        self.assertIn('locked.textContent = "Locked"', card)
        self.assertIn("else if (item.actionable !== true)", card)
        self.assertIn('presentation.textContent = "In-game only"', card)
        self.assertIn('button(', card)
        self.assertIn('"Disable"', card)
        self.assertIn("disable.dataset.hairDisable = item.key", card)
        self.assertLess(
            card.index("else if (item.actionable !== true)"),
            card.index("const availability = hairActionAvailability(item, hair)"),
        )

        action_start = self.javascript.index("async function disableHairLayer(")
        action_end = card_start
        action = self.javascript[action_start:action_end]
        self.assertIn('api("/api/vam/person/hair"', action)
        for field in (
            "target_uid: targetUid",
            "revision,",
            "item_key: availability.itemKey",
            "active: false",
        ):
            with self.subTest(field=field):
                self.assertIn(field, action)
        self.assertIn('result.operation !== "set-person-hair"', action)
        self.assertIn("result.active !== false", action)
        self.assertIn('requireWorkspaceBridgeQueue(result, "Hair disable")', action)
        self.assertIn("await loadPersons({ quiet: true })", action)
        self.assertIn("await syncPersonHair({ quiet: true, retry: true })", action)
        self.assertIn("/revision|stale|changed/i", action)
        self.assertNotIn("app.personHair.items", action)
        self.assertNotIn(".splice(", action)
        for forbidden in ("resource_ref", "resource_path", "hair_uid", "storable"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, action)

        availability_start = self.javascript.index(
            "function hairActionAvailability("
        )
        availability_end = self.javascript.index(
            "function pendingHairMutationFor(", availability_start
        )
        availability = self.javascript[availability_start:availability_end]
        for guard in (
            "item?.locked === true",
            "item?.actionable !== true",
            "rosterRevision !== identity.revision",
            "app.hairMutationInFlight",
            "app.pendingHairMutation",
            "snapshotBridgeBusy(snapshot)",
            "workspaceActionIsActive()",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, availability)

        workspace_start = self.javascript.index(
            "function workspaceApplyAvailability("
        )
        workspace_end = self.javascript.index(
            "async function confirmSceneLoad(", workspace_start
        )
        workspace = self.javascript[workspace_start:workspace_end]
        self.assertIn('category.id === "preset-hair"', workspace)
        self.assertIn(
            "(app.hairMutationInFlight || app.pendingHairMutation)",
            workspace,
        )
        reconcile_start = self.javascript.index(
            "function reconcilePendingHairMutation("
        )
        reconcile_end = self.javascript.index(
            "function acceptPersonSnapshot(", reconcile_start
        )
        reconcile = self.javascript[reconcile_start:reconcile_end]
        self.assertIn("revision !== pending.revision", reconcile)
        self.assertIn("app.pendingHairMutation = null", reconcile)
        accept_start = reconcile_end
        accept_end = self.javascript.index(
            "function acceptPersonSnapshotError(", accept_start
        )
        self.assertIn(
            "reconcilePendingHairMutation(snapshot)",
            self.javascript[accept_start:accept_end],
        )
        activity_start = self.javascript.index("async function loadActivity(")
        activity_end = self.javascript.index(
            "async function fetchLiveSceneSnapshot()", activity_start
        )
        activity = self.javascript[activity_start:activity_end]
        self.assertIn("Boolean(app.pendingHairMutation)", activity)
        self.assertIn(
            "workspaceActionIsActive() || app.pendingHairMutation ? 900 : 3000",
            activity,
        )
        self.assertIn(".hair-disable-button", self.styles)
        self.assertIn(".hair-layer-control.is-locked", self.styles)

    def test_other_person_categories_use_a_compact_recipe_view(self) -> None:
        for element_id in (
            "character-recipe",
            "character-recipe-person",
            "character-recipe-title",
            "character-recipe-description",
            "character-recipe-scopes",
            "character-recipe-note",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)
        start = self.javascript.index("function renderCharacterRecipe(")
        end = self.javascript.index("function renderCharacterSheet()", start)
        recipe = self.javascript[start:end]
        self.assertIn('"Appearance recipe"', recipe)
        self.assertIn("CHARACTER_RECIPE_SCOPES", recipe)
        self.assertIn("not published by VaM", recipe)
        self.assertIn("never a guessed current preset", recipe)

    def test_equipment_removal_keeps_exact_version_and_serializes_mutations(
        self,
    ) -> None:
        remove_start = self.javascript.index("async function removeEquippedItem(")
        remove_end = self.javascript.index("async function loadPersons(", remove_start)
        removal = self.javascript[remove_start:remove_end]
        self.assertIn("equipmentPackageVersion(item)", removal)
        self.assertIn(
            "setPersonClothing(\n"
            "    item,\n"
            "    category,\n"
            "    sourceButton,\n"
            "    packageVersion,\n"
            "    false,",
            removal,
        )
        self.assertIn("item.clothing_locked", self.javascript)
        self.assertIn(
            "equipmentItemKey(candidate) === itemKey",
            removal,
        )
        self.assertNotIn("Number(candidate.id)", removal)

        normalize_start = self.javascript.index("function normalizePersonEquipment(")
        normalize_end = self.javascript.index(
            "async function syncPersonEquipment(", normalize_start
        )
        normalize = self.javascript[normalize_start:normalize_end]
        self.assertIn("equipmentItemKey(normalizedItem)", normalize)
        self.assertNotIn("seen.has(resourceId)", normalize)

        key_start = self.javascript.index("function equipmentItemKey(")
        key_end = self.javascript.index("function createEquippedItem(", key_start)
        key_block = self.javascript[key_start:key_end]
        self.assertIn("equipmentPackageVersion(item)", key_block)
        self.assertIn("`resource:${resourceId}:local`", key_block)
        self.assertIn("`resource:${resourceId}:package:${", key_block)
        for forbidden in ("resource_ref", "resource_path", ".uid"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, key_block)
        self.assertIn(
            "remove.dataset.equipmentRemove = equipmentItemKey(item)",
            self.javascript,
        )
        row_start = self.javascript.index("function createEquippedItem(")
        row_end = self.javascript.index("function createEquipmentSlot(", row_start)
        row = self.javascript[row_start:row_end]
        self.assertIn(
            "!local && packageVersion !== null ? ` v${packageVersion}`",
            row,
        )
        self.assertIn("item.package || item.package_name", row)
        self.assertIn('details.textContent = detailParts.join(" · ")', row)
        self.assertIn(
            "`${resourceTitle(item)}${versionLabel} is locked in VaM`",
            row,
        )
        self.assertIn(
            "`Remove ${resourceTitle(item)}${versionLabel} from ${app.selectedPersonUid}`",
            row,
        )

        availability_start = self.javascript.index(
            "function clothingActionAvailability("
        )
        action_start = self.javascript.index(
            "async function setPersonClothing(", availability_start
        )
        availability = self.javascript[availability_start:action_start]
        self.assertIn("app.clothingMutationInFlight", availability)

        action_end = self.javascript.index(
            "function workspaceApplyAvailability(", action_start
        )
        action = self.javascript[action_start:action_end]
        self.assertIn("desiredActive = null", action)
        self.assertIn("if (app.clothingMutationInFlight) return;", action)
        self.assertIn("app.clothingMutationInFlight = true", action)
        self.assertIn("app.clothingMutationInFlight = false", action)
        self.assertIn(
            'if (typeof desiredActive === "boolean")',
            action,
        )
        self.assertIn("requestBody.active = desiredActive", action)
        self.assertIn("requestBody.package_version = packageVersion", action)
        self.assertIn("revision: availability.revision", action)

    def test_resource_detail_overlay_is_centered_and_variants_are_browse_only(
        self,
    ) -> None:
        start = self.javascript.index("function normalizedResourceState(")
        end = self.javascript.index("function clothingCategoryForItem(", start)
        block = self.javascript[start:end]
        for field in (
            'group !== "related-resources"',
            'group !== "related-clothing-styles"',
            "item?.variant_count",
            "source.display_name",
            "source.label",
            "source.favorite",
            "source.resource_type = \"Clothing Item Presets\"",
            "source.relationship_kind = \"item-style\"",
            "source.relationship_confidence",
            "source.relationship_reason",
            "equipmentPackageVersion(source)",
            "resourceUpdateVersion(source)",
            "item?.variant_search",
        ):
            with self.subTest(field=field):
                self.assertIn(field, block)
        self.assertIn('id="resource-detail-dialog"', self.html)
        self.assertIn('id="resource-detail-content"', self.html)
        self.assertIn('aria-labelledby="resource-detail-title"', self.html)
        self.assertIn("function openResourceDetailDialog(item, opener)", block)
        self.assertIn("const isNewOpen = !dialog.open", block)
        self.assertIn("dialog.showModal()", block)
        self.assertIn(
            "if (isNewOpen) {\n"
            "    window.setTimeout(() => elements.resourceDetailClose.focus(), 0);",
            block,
        )
        self.assertIn(
            'elements.resourceDetailDialog.close("backdrop")',
            block,
        )
        self.assertIn(
            'elements.resourceDetailDialog.close("browse")',
            block,
        )
        self.assertIn("app.resourceDetailOpener", block)
        self.assertIn('createElement("div", "resource-detail-preview")', block)
        self.assertIn('createElement("dl", "resource-detail-facts")', block)
        self.assertIn("appendResourceActions(actions, item, model)", block)
        self.assertIn(
            'createElement("div", "resource-detail-catalogue")',
            block,
        )
        self.assertIn(
            "renderResourceDetailDependencies(\n"
            "    catalogue,\n"
            "    item,",
            block,
        )
        self.assertIn("reusableDependencyReport", block)
        self.assertIn("{ refresh: !reusableDependencyReport }", block)
        self.assertIn("renderResourceDetailVariants(catalogue, item)", block)
        self.assertIn(
            'createElement("div", "resource-variant-gallery")',
            block,
        )
        self.assertIn(
            'createElement("article", "resource-variant-tile")',
            block,
        )
        self.assertIn('"Styles & variants"', block)
        self.assertIn('"Browse-only name matches"', block)
        self.assertIn(
            '"Matched by package, folder, and name. These are catalogue suggestions, not verified semantic variants."',
            block,
        )
        self.assertIn('"Same package/folder/name match; not semantic identity"', block)
        self.assertIn("resourceThumbnailUrl(model.id)", block)
        self.assertIn(
            ".slice(0, MAX_RENDERED_RESOURCE_VARIANTS)",
            block,
        )
        self.assertIn("const seenIds = new Set();", block)
        self.assertIn("if (seenIds.has(model.id)) return null;", block)
        self.assertIn(
            'model.relationshipConfidence === "name-match"',
            block,
        )
        self.assertIn(
            "browseRelatedResource({ ...model, browseQuery: query }, ownerSearch)",
            block,
        )
        self.assertIn(
            "{ ...(variants[0] || {}), browseQuery: ownerSearch }",
            block,
        )
        self.assertIn('"Browse style"', block)
        self.assertIn('"Browse variant"', block)
        self.assertIn('"Hidden in VaM"', block)
        self.assertIn('"Available"', block)
        self.assertIn('"Package missing"', block)
        self.assertIn('"Resource missing"', block)
        self.assertIn(
            '"The containing VAR package is not installed."',
            block,
        )
        self.assertIn(
            '"The catalogue entry exists, but its exact resource file is unavailable."',
            block,
        )
        self.assertIn("normalizedVariantCount(", block)
        self.assertIn("Number.isSafeInteger(value)", block)
        self.assertIn("value > MAX_VARIANT_MATCH_COUNT", block)
        self.assertIn("function normalizedResourceId(", block)
        self.assertIn("Number.isSafeInteger(value) && value > 0", block)
        self.assertIn(
            'String(candidateType || "").trim().toLowerCase() === normalizedType',
            block,
        )
        self.assertNotIn('"Applied"', block)
        tile_start = self.javascript.index(
            "function createRelatedResourceTile("
        )
        tile_end = self.javascript.index(
            "function renderResourceDetailVariants(", tile_start
        )
        tile = self.javascript[tile_start:tile_end]
        for forbidden in (
            '"/api/vam',
            "setPersonClothing(",
            "applyWorkspaceResource(",
            "createThreeDayLease(",
            "addPin(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, tile)
        self.assertNotIn("appendResourceVariantDrawer(", self.javascript)
        self.assertNotIn("resource-variant-drawer", self.styles)
        for selector in (
            ".resource-detail-dialog",
            ".resource-detail-layout",
            ".resource-detail-preview",
            ".resource-detail-facts",
            ".resource-detail-catalogue",
            ".resource-detail-dependencies",
            ".resource-variant-gallery",
            ".resource-variant-tile",
            ".resource-variant-visual",
            ".resource-variant-browse",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        dialog_start = self.styles.index(".resource-detail-dialog {")
        dialog_end = self.styles.index(
            ".resource-detail-dialog::backdrop", dialog_start
        )
        dialog = self.styles[dialog_start:dialog_end]
        self.assertIn("width: min(1680px, 88vw)", dialog)
        self.assertIn("height: min(900px, 88dvh)", dialog)
        self.assertIn("@media (max-width: 900px)", self.styles)
        self.assertIn("@media (max-width: 600px)", self.styles)
        self.assertIn("@media (max-width: 360px)", self.styles)
        self.assertIn("width: 100vw", self.styles)
        self.assertIn("body.resource-detail-open", self.styles)
        render_start = self.javascript.index("function renderLibrary()")
        render_end = self.javascript.index(
            "function showLoadingState()", render_start
        )
        render = self.javascript[render_start:render_end]
        self.assertIn("const detailResourceId = detailWasOpen", render)
        self.assertIn("app.items.find(", render)
        self.assertIn(
            "openResourceDetailDialog(refreshedItem, refreshedOpener)",
            render,
        )
        self.assertIn(
            'elements.resourceDetailDialog.close("library-render")',
            render,
        )
        self.assertIn(
            "elements.searchInput.focus({ preventScroll: true })",
            render,
        )

    def test_resource_detail_lazily_renders_a_paged_dependency_catalogue(
        self,
    ) -> None:
        start = self.javascript.index("function boundedDependencyText(")
        end = self.javascript.index(
            "function renderResourceDetailVariants(", start
        )
        block = self.javascript[start:end]
        self.assertIn("const DEPENDENCY_PAGE_SIZE = 8;", self.javascript)
        self.assertIn("const MAX_RENDERED_DEPENDENCIES = 2_048;", self.javascript)
        self.assertIn("function normalizeDependencyReport(payload)", block)
        self.assertIn(
            "source.dependencies || envelope.dependencies",
            block,
        )
        self.assertIn(
            "const report = normalizeDependencyReport(rawReport);",
            block,
        )
        self.assertNotIn(
            "Array.isArray(rawReport.dependencies)",
            block,
        )
        self.assertIn("entry.required_by", block)
        self.assertIn("entry.resolved_id", block)
        self.assertIn("report.truncated", block)
        self.assertIn(
            "`/api/resources/${encodeURIComponent(resourceId)}/details${versionQuery}`",
            block,
        )
        self.assertIn("resourceDetailsPackageVersion(item)", block)
        self.assertIn("?package_version=", block)
        self.assertIn("new AbortController()", block)
        self.assertIn("generation !== app.resourceDependencyGeneration", block)
        self.assertIn("if (initialPayload && !refresh)", block)
        self.assertIn(
            '"Previous dependency page"',
            block,
        )
        self.assertIn('"Next dependency page"', block)
        self.assertIn(
            "page.start + DEPENDENCY_PAGE_SIZE",
            block,
        )
        self.assertIn(
            "browseDependencyPackage(entry.packageId)",
            block,
        )
        self.assertIn(
            'setView("packages", { preserveResourceReturn: true })',
            block,
        )
        self.assertIn("elements.searchInput.value = query", block)
        self.assertIn("app.exactPackageId = query", block)
        self.assertNotIn("load-more", block.lower())
        details_version_start = self.javascript.index(
            "function resourceDetailsPackageVersion("
        )
        details_version_end = self.javascript.index(
            "function equipmentItemKey(", details_version_start
        )
        details_version = self.javascript[
            details_version_start:details_version_end
        ]
        self.assertIn('return "latest";', details_version)
        self.assertIn("item?.package_ref", details_version)
        self.assertIn("/\\.latest$/i.test(packageRef)", details_version)

        equipment_version_start = self.javascript.index(
            "function equipmentPackageVersion("
        )
        equipment_version_end = details_version_start
        equipment_version = self.javascript[
            equipment_version_start:equipment_version_end
        ]
        self.assertNotIn('"latest"', equipment_version)
        for selector in (
            ".dependency-summary",
            ".dependency-conflict-panel",
            ".dependency-copy-grid",
            ".dependency-list",
            ".dependency-page-arrow",
            ".dependency-open-package",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)

    def test_dependency_package_navigation_can_return_to_its_resource(self) -> None:
        for control_id in (
            "resource-return-context",
            "resource-return-button",
            "resource-return-title",
            "resource-return-detail",
            "resource-return-dismiss",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn(
            'aria-label="Return to the resource you were viewing"',
            self.html,
        )
        self.assertIn('aria-label="Dismiss return link"', self.html)

        browse_start = self.javascript.index(
            "function browseDependencyPackage("
        )
        browse_end = self.javascript.index(
            "function dependencyCopyFingerprint(", browse_start
        )
        browse = self.javascript[browse_start:browse_end]
        self.assertLess(
            browse.index("captureResourceReturnContext();"),
            browse.index('elements.resourceDetailDialog.close("browse")'),
        )
        self.assertIn(
            'setView("packages", { preserveResourceReturn: true })',
            browse,
        )

        return_start = self.javascript.index(
            "function resourceReturnLocationLabel("
        )
        return_end = self.javascript.index(
            "function browseDependencyPackage(", return_start
        )
        navigation = self.javascript[return_start:return_end]
        for saved_state in (
            "resourceId,",
            "view: app.view",
            "query: app.query",
            "type: app.type",
            "packageState: app.packageState",
            "page: libraryPaginationState(app.total, app.page).page",
            "selectedWorkspaceCategoryId: app.selectedWorkspaceCategoryId",
            "dependencyPage: app.resourceDependencyPage",
        ):
            with self.subTest(saved_state=saved_state):
                self.assertIn(saved_state, navigation)
        capture_start = navigation.index(
            "function captureResourceReturnContext()"
        )
        capture_end = navigation.index(
            "function resourceReturnStateMatches(", capture_start
        )
        self.assertNotIn(
            "resourceDependencyReport",
            navigation[capture_start:capture_end],
        )
        self.assertIn("deferLibraryLoad: true", navigation)
        self.assertIn(
            "const restored = await loadLibrary({ page: context.page });",
            navigation,
        )
        self.assertIn("const freshItem = app.items.find(", navigation)
        self.assertNotIn("context.item", navigation)
        self.assertNotIn("app.page === context.page", navigation)
        self.assertIn(
            "resourceCardOpener(context.resourceId) || elements.searchInput",
            navigation,
        )
        self.assertIn("app.resourceDetailRestore = {", navigation)
        self.assertIn("dependencyPage: context.dependencyPage", navigation)
        self.assertIn("app.resourceReturnContext = null", navigation)
        self.assertIn(
            "elements.resourceReturnContext?.contains(document.activeElement)",
            navigation,
        )
        self.assertIn(
            "focusTarget.focus({ preventScroll: true })",
            navigation,
        )
        missing_start = navigation.index("if (!freshItem)")
        missing_end = navigation.index(
            "const freshOpener", missing_start
        )
        self.assertIn(
            "clearResourceReturnContext();",
            navigation[missing_start:missing_end],
        )

        view_start = self.javascript.index("function setView(")
        view_end = self.javascript.index(
            "function updateWorkspaceSearchPlaceholder(", view_start
        )
        view = self.javascript[view_start:view_end]
        self.assertIn("deferLibraryLoad = false", view)
        self.assertIn("preserveResourceReturn = false", view)
        self.assertIn(
            "if (!preserveResourceReturn) clearResourceReturnContext();",
            view,
        )
        self.assertIn("if (!deferLibraryLoad) loadLibrary();", view)

        self.assertIn(".resource-return-context", self.styles)
        self.assertIn(".resource-return-button:focus-visible", self.styles)
        mobile_start = self.styles.index("@media (max-width: 600px)")
        self.assertIn(
            ".resource-return-button",
            self.styles[mobile_start:],
        )

    def test_packages_surface_their_indexed_resources_and_exact_contents(
        self,
    ) -> None:
        package_start = self.javascript.index(
            "function normalizePackageResourceTypes("
        )
        package_end = self.javascript.index(
            "function renderAccess()", package_start
        )
        package = self.javascript[package_start:package_end]
        for contract_field in (
            "item?.resource_count",
            "item?.resource_type_count",
            "item?.resource_types",
            "item?.resource_previews",
            "item?.representative_resources",
        ):
            with self.subTest(contract_field=contract_field):
                self.assertIn(contract_field, package)
        self.assertIn("MAX_PACKAGE_RESOURCE_PREVIEWS", package)
        self.assertIn("MAX_PACKAGE_RESOURCE_TYPES", package)
        self.assertIn("package-preview-grid", package)
        self.assertIn("package-resource-count", package)
        self.assertIn('"Browse contents"', package)
        self.assertIn("browsePackageContents(item)", package)
        self.assertIn(
            "const hasResourcePreview = valid && resourceCount !== 0",
            package,
        )
        self.assertIn(
            'card.classList.add("has-resource-preview")',
            package,
        )
        self.assertIn("if (hasResourcePreview)", package)
        self.assertIn("if (!hasResourcePreview)", package)
        self.assertIn("if (preview) card.append(preview)", package)
        self.assertIn('"No indexed items"', package)
        self.assertIn("BrowserAssist-indexed ${plural(", package)
        self.assertIn("verify the exact contents", package)
        self.assertIn(
            "model.thumbnail ||\n"
            "          (model.id !== null ? resourceThumbnailUrl(model.id) : \"\")",
            package,
        )

        load_start = self.javascript.index("async function loadLibrary(")
        load_end = self.javascript.index(
            "function renderStatus()", load_start
        )
        load = self.javascript[load_start:load_end]
        self.assertIn(
            "`/api/packages/${encodeURIComponent(packageContentsId)}/resources`",
            load,
        )
        self.assertIn(
            'app.view === "resources" ? app.packageContentsId : ""',
            load,
        )
        for query_contract in (
            'params.set("q", app.query)',
            'params.append("type", resourceType)',
            'params.set("state", app.packageState)',
            'limit: String(PAGE_SIZE)',
            'offset: String(offset)',
        ):
            with self.subTest(query_contract=query_contract):
                self.assertIn(query_contract, load)

        for selector in (
            ".package-preview",
            ".package-preview-grid",
            ".package-preview-cell",
            ".package-preview-hint",
            ".package-browse-button",
            ".package-resource-count",
            ".package-card.has-resource-preview",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        compact_start = self.styles.index(".package-card {")
        compact_end = self.styles.index(".package-preview {", compact_start)
        compact = self.styles[compact_start:compact_end]
        self.assertIn("min-height: 190px", compact)
        self.assertIn(".package-card.has-resource-preview", compact)
        self.assertIn("min-height: 312px", compact)

    def test_package_scope_copy_conflicts_have_a_truthful_return_state(
        self,
    ) -> None:
        error_start = self.javascript.index(
            "function packageScopeCopyConflictCode("
        )
        error_end = self.javascript.index(
            "function renderEmptyLibrary()", error_start
        )
        error_state = self.javascript[error_start:error_end]
        self.assertIn('"package_copy_conflict"', error_state)
        self.assertIn('"package_copy_choice_stale"', error_state)
        self.assertIn("numberOr(error?.status, 0) !== 409", error_state)
        self.assertIn('"Review package copy"', error_state)
        self.assertIn('"Choose package copy"', error_state)
        self.assertIn('"Back to package"', error_state)
        self.assertIn(
            'elements.emptyAction.dataset.action = "return-package"',
            error_state,
        )
        self.assertIn(
            'if (app.view === "resources" && app.packageContentsId)',
            error_state,
        )
        self.assertIn('"Could not open package contents"', error_state)
        self.assertLess(
            error_state.index("if (packageCopyConflict)"),
            error_state.index(
                'if (app.view === "resources" && app.packageContentsId)'
            ),
        )
        self.assertNotIn(
            '"The local manager did not respond"',
            error_state[
                error_state.index("if (packageCopyConflict)") :
                error_state.index(
                    'elements.emptyTitle.textContent = "The local manager did not respond"'
                )
            ],
        )

        action_start = self.javascript.index("function handleEmptyAction()")
        action_end = self.javascript.index(
            "function setConnection(", action_start
        )
        action = self.javascript[action_start:action_end]
        self.assertIn('action === "return-package"', action)
        self.assertIn("returnToResourceContext();", action)
        self.assertIn("exitPackageContentsScope();", action)

    def test_package_contents_navigation_is_a_stacked_return_context(self) -> None:
        navigation_start = self.javascript.index(
            "function resourceReturnLocationLabel("
        )
        navigation_end = self.javascript.index(
            "function browseDependencyPackage(", navigation_start
        )
        navigation = self.javascript[navigation_start:navigation_end]
        self.assertIn('context.kind === "package"', navigation)
        self.assertIn("function capturePackageReturnContext(item)", navigation)
        self.assertIn("function returnToPackageContext(context)", navigation)
        self.assertIn("function browsePackageContents(item)", navigation)
        self.assertGreaterEqual(
            navigation.count("const parentContext = app.resourceReturnContext"),
            2,
        )
        self.assertGreaterEqual(
            navigation.count(
                "app.resourceReturnContext = context.parentContext || null"
            ),
            2,
        )
        self.assertIn("packageContentsId: app.packageContentsId", navigation)
        self.assertIn(
            'setView("resources", { preserveResourceReturn: true })',
            navigation,
        )
        self.assertIn(
            'setView("packages", {\n'
            "      deferLibraryLoad: true,\n"
            "      preserveResourceReturn: true,",
            navigation,
        )
        self.assertIn("packageCard.focus({ preventScroll: true })", navigation)
        self.assertIn("packageCard.tabIndex = -1", navigation)
        self.assertIn("function exitPackageContentsScope()", navigation)
        self.assertIn("function dismissResourceReturnContext()", navigation)
        self.assertIn('app.packageContentsId = "";', navigation)

        exit_start = navigation.index("function exitPackageContentsScope()")
        exit_end = navigation.index(
            "function dismissResourceReturnContext()", exit_start
        )
        exit_scope = navigation[exit_start:exit_end]
        self.assertIn("clearResourceReturnContext();", exit_scope)
        self.assertIn('app.packageContentsId = "";', exit_scope)
        self.assertIn("configureStateFilter();", exit_scope)
        self.assertIn("loadLibrary();", exit_scope)

        clear_start = self.javascript.index("function clearFilters()")
        clear_end = self.javascript.index(
            "function updateClearFilters()", clear_start
        )
        clear = self.javascript[clear_start:clear_end]
        self.assertNotIn("packageContentsId", clear)
        self.assertNotIn("clearResourceReturnContext", clear)
        self.assertIn('app.query = "";', clear)
        self.assertIn('app.type = "";', clear)
        self.assertIn('app.packageState = "all";', clear)

        bind_start = self.javascript.index("function bindEvents()")
        bind_end = self.javascript.index("function anyModalOpen()", bind_start)
        bind = self.javascript[bind_start:bind_end]
        self.assertIn(
            'tab.dataset.view === "resources" &&\n'
            '        app.view === "resources" &&\n'
            "        app.packageContentsId",
            bind,
        )
        self.assertIn("exitPackageContentsScope();", bind)

        card_start = self.javascript.index("function createResourceCard(")
        card_end = self.javascript.index(
            "function appendResourceActions(", card_start
        )
        card = self.javascript[card_start:card_end]
        self.assertIn(
            "model.thumbnail ||\n"
            "    (model.id !== null ? resourceThumbnailUrl(model.id) : \"\")",
            card,
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_package_resource_summary_normalizer_tolerates_contract_aliases(
        self,
    ) -> None:
        start = self.javascript.index(
            "function normalizePackageResourceTypes("
        )
        end = self.javascript.index(
            "function createPackageCard(", start
        )
        helper = self.javascript[start:end]
        script = f"""
"use strict";
const MAX_PACKAGE_RESOURCE_PREVIEWS = 4;
function asArray(value) {{ return Array.isArray(value) ? value : []; }}
function numberOr(value, fallback = 0) {{
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}}
function safePresentationLabel(value, fallback) {{
  const text = String(value || "").trim().slice(0, 120);
  return text || fallback;
}}
function normalizeResourceCardModel(entry) {{
  return {{
    id: Number.isSafeInteger(entry.id) ? entry.id : null,
    title: entry.display_name || entry.name || "Contained resource",
    type: entry.resource_type || "Resource",
    thumbnail: entry.thumbnail_url || "",
  }};
}}
function resourceThumbnailUrl(id) {{ return `/thumb/${{id}}`; }}
{helper}
const item = {{
  resource_count: 9,
  resource_types: {{
    "Preset Appearance": 7,
    "Preset Clothing": 2,
  }},
  representative_resources: [
    {{ id: 1, display_name: "Alana Red", resource_type: "Preset Appearance" }},
    {{ id: 2, display_name: "Alana Blue", resource_type: "Preset Appearance" }},
  ],
}};
process.stdout.write(JSON.stringify({{
  types: normalizePackageResourceTypes({{
    ...item,
    resource_types: [
      {{ value: "Preset Appearance", count: 7 }},
      {{ value: "Preset Clothing", count: 2 }},
    ],
  }}),
  previews: normalizePackageResourcePreviews(item),
  count: packageResourceCount(item),
  typeCount: packageResourceTypeCount({{
    resource_type_count: 8,
  }}, 2),
  missingCount: packageResourceCount({{
    resource_previews: [{{ id: 3 }}],
  }}),
}}));
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
            result["types"],
            [
                {"type": "Preset Appearance", "count": 7},
                {"type": "Preset Clothing", "count": 2},
            ],
        )
        self.assertEqual(len(result["previews"]), 2)
        self.assertEqual(result["previews"][0]["thumbnail"], "/thumb/1")
        self.assertEqual(result["count"], 9)
        self.assertEqual(result["typeCount"], 8)
        self.assertIsNone(result["missingCount"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_dependency_package_navigation_filters_to_the_exact_identity(
        self,
    ) -> None:
        start = self.javascript.index("function packageItemIdentity(")
        end = self.javascript.index("function changeLibraryPage(", start)
        helper = self.javascript[start:end]
        script = f"""
"use strict";
function numberOr(value, fallback = 0) {{
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}}
const offsets = [];
async function api(path) {{
  const params = new URL(path, "http://localhost").searchParams;
  const offset = Number(params.get("offset") || 0);
  offsets.push(offset);
  if (offset === 0) {{
    return {{
      items: [
        {{ id: "Creator.Asset.10" }},
        {{ id: "Prefix.Creator.Asset.1" }},
      ],
      total: 3,
    }};
  }}
  return {{
    items: [{{ id: "Creator.Asset.1" }}],
    total: 3,
  }};
}}
{helper}
(async () => {{
  const result = await findExactPackage(
    new URLSearchParams({{ q: "Creator.Asset.1", state: "all" }}),
    "Creator.Asset.1",
    {{ signal: null }},
  );
  process.stdout.write(JSON.stringify({{ result, offsets }}));
}})();
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
            result["result"],
            {
                "items": [{"id": "Creator.Asset.1"}],
                "total": 1,
            },
        )
        self.assertEqual(result["offsets"], [0, 2])

    def test_dependency_conflicts_offer_only_server_issued_copy_choices(
        self,
    ) -> None:
        start = self.javascript.index(
            "async function chooseDependencyPackageCopy("
        )
        end = self.javascript.index(
            "function createDependencyRow(", start
        )
        block = self.javascript[start:end]
        self.assertIn('api("/api/package-copy-choice"', block)
        self.assertIn("package_id: conflict.packageId", block)
        self.assertIn("copy_id: copy.copyId", block)
        self.assertIn("conflict.reportRevision || report.reportRevision", block)
        self.assertIn('"Use this content"', block)
        self.assertIn('"Using this content"', block)
        self.assertIn("!packageCopy.copyId", block)
        for path_field in (
            "copy.relative_path",
            "copy.logical_path",
            "copy.path",
            "copy.relativePath",
        ):
            with self.subTest(path_field=path_field):
                self.assertIn(path_field, self.javascript)
        request = block[
            block.index('api("/api/package-copy-choice"') :
            block.index("});", block.index('api("/api/package-copy-choice"')) + 3
        ]
        self.assertNotIn("relative_path:", request)
        self.assertNotIn("path:", request)

    def test_package_conflict_errors_open_an_actionable_persistent_resolver(
        self,
    ) -> None:
        conflict_start = self.javascript.index(
            "function isPackageCopyConflictError("
        )
        conflict_end = self.javascript.index(
            "async function applyWorkspaceResource(", conflict_start
        )
        conflict = self.javascript[conflict_start:conflict_end]
        self.assertIn('"package_copy_conflict"', conflict)
        self.assertIn("normalizeDependencyReport(payload)", conflict)
        self.assertIn("app.pendingResourceConflict", conflict)
        self.assertIn("app.resourceDependencyFocus = true", conflict)
        self.assertIn("openResourceDetailDialog(item, opener)", conflict)
        self.assertIn("persistent: true", conflict)
        self.assertIn('actionLabel: "Review choices"', conflict)
        apply_start = self.javascript.index(
            "async function applyWorkspaceResource("
        )
        apply_end = self.javascript.index(
            "function createPackageCard(", apply_start
        )
        apply = self.javascript[apply_start:apply_end]
        self.assertIn("isPackageCopyConflictError(error)", apply)
        self.assertIn(
            "presentPackageCopyConflict(item, error, sourceButton, action)",
            apply,
        )

        api_start = self.javascript.index("async function api(path, options = {})")
        api_end = self.javascript.index("function showDialog(", api_start)
        api = self.javascript[api_start:api_end]
        self.assertIn("error.payload =", api)
        self.assertIn("error.payload.error_code", api)
        self.assertIn("payloadError.code", api)
        self.assertIn("error.code = String(", api)

        toast_start = self.javascript.index("function updateToast(")
        toast_end = self.javascript.index("function setButtonBusy(", toast_start)
        toast = self.javascript[toast_start:toast_end]
        self.assertIn("options.actionLabel", toast)
        self.assertIn("options.onAction", toast)
        self.assertIn("data-toast-action", toast)
        self.assertIn("data-toast-close", toast)
        self.assertIn(".toast .toast-action", self.styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_dependency_report_normalizer_is_bounded_and_tolerates_partial_data(
        self,
    ) -> None:
        start = self.javascript.index("function boundedDependencyText(")
        end = self.javascript.index("function dependencyStateLabel(", start)
        normalizer = self.javascript[start:end]
        script = f"""
"use strict";
const DEPENDENCY_PAGE_SIZE = 8;
const MAX_RENDERED_DEPENDENCIES = 2_048;
function asArray(value) {{ return Array.isArray(value) ? value : []; }}
function numberOr(value, fallback = 0) {{
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}}
function booleanValue(value, fallback = false) {{
  return typeof value === "boolean" ? value : fallback;
}}
function safePresentationLabel(value, fallback) {{
  const text = String(value || "").trim().slice(0, 120);
  return text || fallback;
}}
{normalizer}
const apiReport = {{
  revision: "rev-7",
  truncated: true,
  dependencies: [
    null,
    {{ requested: "Creator.Asset.latest", resolved_id: "Creator.Asset.4",
       state: "available", direct: true, required_by: "Loose scene" }},
    {{ requested: "Creator.Missing.1", state: "missing" }},
  ],
  conflicts: [{{
    package_id: "Creator.Asset.4",
    selected_content_sha256: "1:abc",
    copies: [
      {{ copy_id: "copy-a", content_sha256: "1:abc", selected: false }},
      {{ relative_path: "no-safe-id.var" }},
    ],
  }}],
}};
const report = normalizeDependencyReport(apiReport);
const renormalized = normalizeDependencyReport(report);
process.stdout.write(JSON.stringify({{
  revision: report.reportRevision,
  truncated: report.truncated,
  dependencies: report.dependencies,
  selected: report.conflicts[0].copies[0].selected,
  renormalized,
  pager: dependencyPaginationState(17, 99),
}}));
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
        self.assertEqual(result["revision"], "rev-7")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["dependencies"]), 2)
        self.assertEqual(result["dependencies"][0]["state"], "hidden")
        self.assertEqual(result["dependencies"][0]["requiredBy"], ["Loose scene"])
        self.assertTrue(result["selected"])
        self.assertEqual(result["renormalized"]["reportRevision"], "rev-7")
        self.assertEqual(
            result["renormalized"]["dependencies"],
            result["dependencies"],
        )
        self.assertEqual(
            result["renormalized"]["conflicts"][0]["packageId"],
            "Creator.Asset.4",
        )
        self.assertEqual(
            result["renormalized"]["conflicts"][0]["copies"][0]["copyId"],
            "copy-a",
        )
        self.assertEqual(
            result["renormalized"]["conflicts"][0]["copies"][0][
                "contentSha256"
            ],
            "1:abc",
        )
        self.assertEqual(
            result["pager"],
            {
                "page": 3,
                "pageCount": 3,
                "start": 16,
                "hasPrevious": True,
                "hasNext": False,
            },
        )

    def test_compact_resource_card_opens_details_with_an_explicit_button(
        self,
    ) -> None:
        start = self.javascript.index("function createResourceCard(")
        end = self.javascript.index("function appendResourceActions(", start)
        card = self.javascript[start:end]
        self.assertIn(
            '"button",\n    "card-preview resource-card-preview-button"',
            card,
        )
        self.assertIn(
            'preview.setAttribute("aria-label", `Open details for ${title}`)',
            card,
        )
        self.assertIn(
            'preview.setAttribute("aria-haspopup", "dialog")',
            card,
        )
        self.assertIn(
            'preview.setAttribute("aria-controls", "resource-detail-dialog")',
            card,
        )
        self.assertIn("openResourceDetailDialog(item, preview)", card)
        self.assertIn('"Preview & details"', card)
        self.assertNotIn("appendResourceVariantDrawer(", card)

    def test_slash_shortcut_is_blocked_by_either_modal(self) -> None:
        self.assertIn("function anyModalOpen()", self.javascript)
        self.assertIn("elements.confirmDialog?.open", self.javascript)
        self.assertIn("elements.resourceDetailDialog?.open", self.javascript)
        self.assertIn("!anyModalOpen()", self.javascript)

    def test_generic_card_model_does_not_dedupe_top_level_results(self) -> None:
        model_start = self.javascript.index("function normalizeResourceCardModel(")
        model_end = self.javascript.index(
            "function normalizeRelatedResourceVariants(", model_start
        )
        model = self.javascript[model_start:model_end]
        self.assertIn("resourceTitle(source)", model)
        self.assertIn("searchName: declaredTitle", model)
        for field in (
            "title,",
            "creator,",
            "packageRef,",
            "packageLabel,",
            "type,",
            "tags,",
            "state,",
            "selectedVersion,",
            "updateVersion:",
            "favorite:",
        ):
            with self.subTest(field=field):
                self.assertIn(field, model)

        load_start = self.javascript.index("async function loadLibrary(")
        load_end = self.javascript.index("function renderStatus()", load_start)
        load = self.javascript[load_start:load_end]
        self.assertIn("app.items = incoming;", load)
        self.assertNotIn("concat(incoming)", load)
        self.assertNotIn("new Map(", load)
        self.assertNotIn("new Set(", load)

    def test_missing_resource_reason_is_reused_by_disabled_actions(self) -> None:
        access_start = self.javascript.index(
            "function appendPackageAccessActions("
        )
        access_end = self.javascript.index(
            "function resourceUpdateVersion(",
            access_start,
        )
        access = self.javascript[access_start:access_end]
        self.assertIn("missingResourcePresentation(", access)
        self.assertIn("leaseButton.textContent = missingStatus.label", access)
        self.assertIn("leaseButton.title = missingStatus.detail", access)

        clothing_start = self.javascript.index(
            "function clothingActionAvailability("
        )
        clothing_end = self.javascript.index(
            "async function setPersonClothing(",
            clothing_start,
        )
        clothing = self.javascript[clothing_start:clothing_end]
        self.assertIn(
            "normalizedResourceState(item, { assumeHidden: true })",
            clothing,
        )
        self.assertIn("reason = missingStatus.detail", clothing)
        self.assertIn("label = missingStatus.label", clothing)

        workspace_start = self.javascript.index(
            "function workspaceApplyAvailability("
        )
        workspace_end = self.javascript.index(
            "async function applyWorkspaceResource(",
            workspace_start,
        )
        workspace = self.javascript[workspace_start:workspace_end]
        self.assertIn(
            "normalizedResourceState(item, { assumeHidden: true })",
            workspace,
        )
        self.assertIn("reason = missingStatus.detail", workspace)
        self.assertIn("label = missingStatus.label", workspace)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_variant_normalization_contract_handles_malformed_payloads(
        self,
    ) -> None:
        def javascript_block(start: str, end: str) -> str:
            start_index = self.javascript.index(start)
            end_index = self.javascript.index(end, start_index)
            return self.javascript[start_index:end_index]

        functions = "\n".join(
            (
                javascript_block(
                    "function booleanValue(",
                    "function workspaceCategoryId(",
                ),
                javascript_block(
                    "function safePresentationLabel(",
                    "function safeOpaqueKey(",
                ),
                javascript_block(
                    "function normalizedResourceState(",
                    "function workspaceCategoryForResourceType(",
                ),
                javascript_block(
                    "function workspaceCategoryForResourceType(",
                    "function browseRelatedResource(",
                ),
                javascript_block(
                    "function normalizedVariantCount(",
                    "function clothingCategoryForItem(",
                ),
                javascript_block(
                    "function equipmentPackageVersion(",
                    "function equipmentItemKey(",
                ),
                javascript_block(
                    "function resourceUpdateVersion(",
                    "function appendResourceUpdateAction(",
                ),
                javascript_block(
                    "function packageRoot(",
                    "function prettyType(",
                ),
                javascript_block(
                    "function asArray(",
                    "function numberOr(",
                ),
            )
        )
        script = (
            '"use strict";\n'
            "const MAX_VARIANT_MATCH_COUNT = 1_000_000;\n"
            "const MAX_RENDERED_RESOURCE_VARIANTS = 12;\n"
            "function ensureWorkspaceCategories() {"
            ' return [{ id: "hair", resourceTypes: ["Preset Hair"] }];'
            " }\n"
            f"{functions}\n"
            """
const common = {
  resource_type: "Preset Hair",
  relationship_kind: "preset-variant",
  relationship_confidence: "name-match",
};
const variants = normalizeRelatedResourceVariants({
  variant_group: "related-resources",
  variants: [
    null,
    true,
    "not-an-object",
    [],
    { ...common, id: true, display_name: "Boolean ID" },
    { ...common, id: "7", display_name: "String ID" },
    { ...common, id: -3, display_name: "Negative ID" },
    {
      ...common,
      id: 7,
      display_name: "Valid",
      label: "/Custom/private/path",
    },
    { ...common, id: 7, display_name: "Duplicate" },
    {
      ...common,
      id: 8,
      display_name: "/Custom/private/name",
      label: "/Custom/private/label",
    },
  ],
});
const packageMissing = normalizeResourceCardModel({
  display_name: "Package missing",
  missing: true,
  missing_reason: "package",
});
const resourceMissing = normalizeResourceCardModel({
  display_name: "Resource missing",
  missing: true,
  missing_reason: "resource",
});
const unsafeMissing = normalizeResourceCardModel({
  display_name: "Unknown missing",
  missing: true,
  missing_reason: "/Custom/private/reason",
});
const output = {
  variants: variants.map((variant) => ({
    id: variant.id,
    title: variant.title,
    label: variant.label,
    browseQuery: variant.browseQuery,
  })),
  nonArrayCount: normalizeRelatedResourceVariants({
    variant_group: "related-resources",
    variants: { id: 2 },
  }).length,
  categoryId: workspaceCategoryForResourceType("  PRESET HAIR  ")?.id || null,
  counts: {
    negative: normalizedVariantCount(-2, 4),
    boolean: normalizedVariantCount(true, 4),
    string: normalizedVariantCount("14", 4),
    huge: normalizedVariantCount(MAX_VARIANT_MATCH_COUNT + 1, 4),
    valid: normalizedVariantCount(14, 4),
  },
  states: {
    active: normalizedResourceState({ enabled: true }),
    hidden: normalizedResourceState({ enabled: false }),
    local: normalizedResourceState({ local: true }),
    missing: normalizedResourceState({ missing: true }),
    missingLocal: normalizedResourceState({
      local: true,
      missing: true,
      missing_reason: "resource",
    }),
    explicitMissingLocal: normalizedResourceState({
      local: true,
      state: "missing",
    }),
    unknown: normalizedResourceState({}),
    assumedHidden: normalizedResourceState({}, { assumeHidden: true }),
  },
  packageMissing,
  resourceMissing,
  unsafeMissing,
};
process.stdout.write(JSON.stringify(output));
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

        self.assertEqual(result["nonArrayCount"], 0)
        self.assertEqual(result["categoryId"], "hair")
        self.assertEqual(
            [variant["id"] for variant in result["variants"]],
            [None, None, None, 7, 8],
        )
        self.assertEqual(
            [variant["title"] for variant in result["variants"]],
            [
                "Boolean ID",
                "String ID",
                "Negative ID",
                "Valid",
                "Unnamed name match",
            ],
        )
        self.assertEqual(result["variants"][3]["label"], "Valid")
        self.assertEqual(result["variants"][4]["browseQuery"], "")
        self.assertEqual(
            result["counts"],
            {
                "negative": 4,
                "boolean": 4,
                "string": 4,
                "huge": 4,
                "valid": 14,
            },
        )
        self.assertEqual(
            result["states"],
            {
                "active": "active",
                "hidden": "hidden",
                "local": "local",
                "missing": "missing",
                "missingLocal": "missing",
                "explicitMissingLocal": "missing",
                "unknown": "unknown",
                "assumedHidden": "hidden",
            },
        )
        self.assertEqual(
            (
                result["packageMissing"]["stateLabel"],
                result["packageMissing"]["missingReasonCode"],
                result["packageMissing"]["missingDetail"],
            ),
            (
                "Package missing",
                "package",
                "The containing VAR package is not installed.",
            ),
        )
        self.assertEqual(
            (
                result["resourceMissing"]["stateLabel"],
                result["resourceMissing"]["missingReasonCode"],
                result["resourceMissing"]["missingDetail"],
            ),
            (
                "Resource missing",
                "resource",
                "The catalogue entry exists, but its exact resource file is unavailable.",
            ),
        )
        self.assertEqual(
            (
                result["unsafeMissing"]["stateLabel"],
                result["unsafeMissing"]["missingReasonCode"],
                result["unsafeMissing"]["missingDetail"],
            ),
            (
                "Resource unavailable",
                "unknown",
                "The catalogue could not resolve this resource.",
            ),
        )
        self.assertNotIn("/Custom/private", completed.stdout)

    def test_character_sheet_is_responsive_and_accessible(self) -> None:
        for selector in (
            ".character-sheet",
            ".character-shortcuts",
            ".character-sheet-layout",
            ".character-identity",
            ".equipment-slot",
            ".equipped-item",
            ".equipment-warning",
            ".hair-studio",
            ".hair-layer-card",
            ".hair-inspector-group",
            ".character-recipe",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        self.assertIn("@media (max-width: 1180px)", self.styles)
        self.assertIn("@media (max-width: 720px)", self.styles)
        self.assertIn("@media (max-width: 500px)", self.styles)
        self.assertIn('aria-busy="false"', self.html)
        self.assertIn('role="status"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('aria-hidden="true"', self.html)

    def test_timeline_is_a_top_level_live_workspace(self) -> None:
        self.assertIn('data-view="timeline"', self.html)
        self.assertIn('id="timeline-view"', self.html)
        self.assertIn('id="timeline-instance"', self.html)
        self.assertIn('id="timeline-segment-select"', self.html)
        self.assertIn('id="timeline-layer-select"', self.html)
        self.assertIn('id="timeline-clip-select"', self.html)
        self.assertIn('id="timeline-scrubber"', self.html)
        self.assertIn('id="timeline-speed"', self.html)
        self.assertIn('id="timeline-weight"', self.html)
        self.assertIn('id="timeline-lock"', self.html)
        for view in ('"timeline"', '"sam3d"', '"packages"', '"access"'):
            with self.subTest(view=view):
                self.assertIn(view, self.javascript)
        self.assertIn(
            "const TIMELINE_PLAYING_POLL_MS = 1000;",
            self.javascript,
        )

    def test_timeline_api_contract_is_centralized_and_revision_safe(self) -> None:
        self.assertIn('snapshotPath: "/api/vam/timeline"', self.javascript)
        self.assertIn(
            'controlPath: "/api/vam/timeline/control"',
            self.javascript,
        )
        client_start = self.javascript.index("const TimelineClient")
        client_end = self.javascript.index(
            "function timelineProperty(", client_start
        )
        client = self.javascript[client_start:client_end]
        for field in (
            "timeline_id:",
            "expected_revision:",
            "op:",
            "body.clip_id",
            "body.segment_id",
            "body.layer_id",
        ):
            with self.subTest(field=field):
                self.assertIn(field, client)
        self.assertIn("return String(value);", self.javascript)
        self.assertNotIn("parseInt(command.timelineId", client)
        self.assertNotIn("storable", client)
        self.assertNotIn("action", client)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_timeline_adapter_normalizes_live_shape_and_strict_controls(
        self,
    ) -> None:
        start = self.javascript.index("const TimelineClient")
        end = self.javascript.index("async function loadTimeline(", start)
        adapter = self.javascript[start:end]
        script = f"""
"use strict";
const MAX_TIMELINE_TRACKS = 80;
const calls = [];
async function api(path, options = {{}}) {{
  calls.push({{ path, options }});
  return {{}};
}}
{adapter}
const timelineIdValue = "1".repeat(32);
const revision = "2".repeat(32);
const segmentId = "3".repeat(32);
const layerId = "4".repeat(32);
const clipId = "5".repeat(32);
const snapshot = normalizeTimelineSnapshot({{
  available: true,
  vam_running: true,
  timeline_protocol: 1,
  capabilities: ["timeline-roster", "timeline-transport"],
  limits: {{ maxInstances: 32, maxClips: 256, maxClipsGlobally: 1024 }},
  instances: [{{
    id: timelineIdValue,
    revision,
    atomUid: "Person",
    enhanced: true,
    ready: true,
    error: {{
      code: "State_Error<script>",
      message: "Timeline catalog could not be built.",
    }},
    limits: {{
      maxSegments: 64,
      maxLayers: 128,
      maxClips: 256,
      maxClipsGlobally: 1024,
      allocatedClips: 64,
    }},
    controls: ["play", "selectClip", "setTime"],
    transport: {{
      playing: true,
      time: 99,
      clipTime: 3.25,
      duration: 12,
      speed: 1,
      weight: 0.75,
    }},
    current: {{ segmentId, layerId, clipId }},
    segments: [{{ id: segmentId, name: "Main" }}],
    layers: [{{ id: layerId, segmentId, name: "Base" }}],
    clips: [{{
      id: clipId,
      segmentId,
      layerId,
      name: "Idle",
      length: 12,
      targetCount: 7,
    }}],
    truncated: {{ segments: false, layers: false, clips: false }},
  }}],
}});
await TimelineClient.control({{
  timelineId: timelineIdValue,
  expectedRevision: revision,
  op: "selectClip",
  clipId,
  segmentId,
  layerId,
}});
process.stdout.write(JSON.stringify({{
  instance: snapshot.instances[0],
  truncated: timelineDataIsTruncated(snapshot.instances[0].truncated),
  call: calls[0],
}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        instance = result["instance"]
        self.assertEqual(instance["id"], "1" * 32)
        self.assertEqual(instance["revision"], "2" * 32)
        self.assertEqual(instance["transport"]["time"], 3.25)
        self.assertEqual(instance["clips"][0]["label"], "Idle")
        self.assertEqual(instance["clips"][0]["targetCount"], 7)
        self.assertEqual(
            instance["error"],
            {
                "code": "stateerrorscript",
                "message": "Timeline catalog could not be built.",
            },
        )
        self.assertEqual(instance["limits"]["maxClipsGlobally"], 1024)
        self.assertEqual(instance["limits"]["allocatedClips"], 64)
        self.assertFalse(result["truncated"])
        self.assertEqual(
            result["call"],
            {
                "path": "/api/vam/timeline/control",
                "options": {
                    "method": "POST",
                    "body": {
                        "timeline_id": "1" * 32,
                        "expected_revision": "2" * 32,
                        "op": "selectClip",
                        "clip_id": "5" * 32,
                    },
                },
            },
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_timeline_keeps_out_of_window_current_clip_without_guessing(
        self,
    ) -> None:
        start = self.javascript.index("const TimelineClient")
        end = self.javascript.index("async function loadTimeline(", start)
        adapter = self.javascript[start:end]
        controls_start = self.javascript.index("function timelineOpKey(", end)
        controls_end = self.javascript.index(
            "function renderTimelineTransport(",
            controls_start,
        )
        controls = self.javascript[controls_start:controls_end]
        script = f"""
"use strict";
const MAX_TIMELINE_TRACKS = 80;
const app = {{
  timeline: null,
  timelineError: null,
  timelineReceivedAt: 0,
  timelineControlInFlight: false,
  timelineSeekInFlight: false,
  selectedTimelineId: "",
  selectedTimelineSegmentId: "",
  selectedTimelineLayerId: "",
  selectedTimelineClipId: "",
}};
async function api() {{ return {{}}; }}
{adapter}
{controls}
const timelineIdValue = "1".repeat(32);
const revision = "2".repeat(32);
const publishedSegmentId = "3".repeat(32);
const publishedLayerId = "4".repeat(32);
const publishedClipId = "5".repeat(32);
function snapshotFor(name, qualified) {{
  return normalizeTimelineSnapshot({{
    available: true,
    vam_running: true,
    instances: [{{
      id: timelineIdValue,
      revision,
      enhanced: true,
      ready: true,
      current: {{
        clipId: null,
        segmentId: null,
        layerId: null,
        qualified,
        name,
        segment: "Overflow Segment",
        layer: "Overflow Layer",
      }},
      segments: [{{
        id: publishedSegmentId,
        name: "Published Segment",
      }}],
      layers: [{{
        id: publishedLayerId,
        segmentId: publishedSegmentId,
        name: "Published Layer",
      }}],
      clips: [{{
        id: publishedClipId,
        segmentId: publishedSegmentId,
        layerId: publishedLayerId,
        name: "Published Clip",
      }}],
      truncated: {{ segments: true, layers: true, clips: true }},
    }}],
  }});
}}
const first = snapshotFor(
  "Overflow Clip",
  "Overflow Segment::Overflow Layer::Overflow Clip",
);
acceptTimelineSnapshot(first);
const instance = selectedTimelineInstance();
const firstSignature = timelineCurrentSignature(instance);
const secondSignature = timelineCurrentSignature(
  snapshotFor(
    "Another Overflow Clip",
    "Overflow Segment::Overflow Layer::Another Overflow Clip",
  ).instances[0],
);
process.stdout.write(JSON.stringify({{
  current: instance.current,
  selectedSegmentId: app.selectedTimelineSegmentId,
  selectedLayerId: app.selectedTimelineLayerId,
  selectedClipId: app.selectedTimelineClipId,
  selectedClip: selectedTimelineClip(instance),
  outside: timelineCurrentOutsidePublishedWindow(instance, "clip"),
  outsideLabel: timelineOutsideOptionLabel(instance, "clip"),
  publishedTargetAllowed: timelineControlTargetIsPublished(
    instance,
    "selectClip",
    {{ clipId: publishedClipId }},
  ),
  unpublishedTargetAllowed: timelineControlTargetIsPublished(
    instance,
    "selectClip",
    {{ clipId: "9".repeat(32) }},
  ),
  signatureChanged: firstSignature !== secondSignature,
}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["current"],
            {
                "segmentId": "",
                "layerId": "",
                "clipId": "",
                "trackId": "",
                "qualified": (
                    "Overflow Segment::Overflow Layer::Overflow Clip"
                ),
                "name": "Overflow Clip",
                "segment": "Overflow Segment",
                "layer": "Overflow Layer",
            },
        )
        self.assertEqual(result["selectedSegmentId"], "")
        self.assertEqual(result["selectedLayerId"], "")
        self.assertEqual(result["selectedClipId"], "")
        self.assertIsNone(result["selectedClip"])
        self.assertTrue(result["outside"])
        self.assertEqual(
            result["outsideLabel"],
            (
                "Current · Overflow Segment::Overflow Layer::Overflow Clip "
                "· outside published window"
            ),
        )
        self.assertTrue(result["publishedTargetAllowed"])
        self.assertFalse(result["unpublishedTargetAllowed"])
        self.assertTrue(result["signatureChanged"])
        self.assertIn(
            "Current clip outside published window",
            self.javascript,
        )
        self.assertIn(
            "VAM-PIP has not selected a different clip in its place",
            self.javascript,
        )
        self.assertIn("outside.disabled = true;", self.javascript)
        self.assertIn(
            'select.value = selectedPublished ? selectedId : "";',
            self.javascript,
        )

    def test_timeline_graph_is_canvas_rendered_and_bounded(self) -> None:
        self.assertIn('id="timeline-canvas"', self.html)
        self.assertNotIn('class="timeline-keyframe"', self.html)
        self.assertIn("const MAX_TIMELINE_TRACKS = 80;", self.javascript)
        self.assertIn(
            "const MAX_TIMELINE_KEYS_PER_TRACK = 2_000;",
            self.javascript,
        )
        self.assertIn("const MAX_TIMELINE_KEYS = 10_000;", self.javascript)
        draw_start = self.javascript.index("function drawTimelineCanvas(")
        draw_end = self.javascript.index(
            "function handleTimelineCanvasClick(", draw_start
        )
        draw = self.javascript[draw_start:draw_end]
        self.assertIn("tracks.length", draw)
        self.assertIn("renderedKeys >= MAX_TIMELINE_KEYS", draw)
        self.assertIn('canvas?.getContext("2d")', self.javascript)
        self.assertIn(".timeline-canvas-scroll", self.styles)

    def test_timeline_explains_unavailable_and_stale_states(self) -> None:
        state_start = self.javascript.index("function timelineSnapshotState(")
        state_end = self.javascript.index(
            "function setTimelineStatePanel(", state_start
        )
        states = self.javascript[state_start:state_end]
        for message in (
            "Timeline support is not available yet",
            "VaM is closed",
            "Scene is loading",
            "Timeline state is stale",
            "Timeline bridge is unavailable",
            "No Timeline instance in this scene",
        ):
            with self.subTest(message=message):
                self.assertIn(message, states)
        self.assertIn("timelineControlAllowed(instance", self.javascript)
        self.assertIn("app.timeline?.stale", self.javascript)
        self.assertIn("Timeline adapter error", self.javascript)
        self.assertIn("instance.error.message", self.javascript)
        self.assertIn("Timeline catalogue is bounded", self.javascript)
        self.assertIn("maxClipsGlobally", self.javascript)

    def test_timeline_has_a_compact_popout_route(self) -> None:
        self.assertIn('params.get("popout") === "compact"', self.javascript)
        self.assertIn('document.title = "VAM-PIP Timeline"', self.javascript)
        self.assertIn('url.searchParams.set("view", "timeline")', self.javascript)
        self.assertIn('url.searchParams.set("popout", "compact")', self.javascript)
        self.assertIn('"vampip-timeline"', self.javascript)
        self.assertIn("body.timeline-popout .timeline-workbench", self.styles)
        self.assertIn("body.timeline-popout .timeline-transport", self.styles)

    def test_sam3d_is_a_top_level_standalone_workflow(self) -> None:
        self.assertIn('data-view="sam3d"', self.html)
        self.assertIn('id="sam3d-view"', self.html)
        for control_id in (
            "sam3d-file-input",
            "sam3d-source-canvas",
            "sam3d-manual-bbox",
            "sam3d-model-select",
            "sam3d-model-note",
            "sam3d-run-button",
            "sam3d-job-progress",
            "sam3d-history-list",
            "sam3d-result-model",
            "sam3d-body-select",
            "sam3d-comparison",
            "sam3d-comparison-grid",
            "sam3d-preview-source",
            "sam3d-preview-overlay",
            "sam3d-preview-result",
            "sam3d-capture-history",
            "sam3d-capture-previous",
            "sam3d-capture-history-label",
            "sam3d-capture-next",
            "sam3d-person-target",
            "sam3d-camera-target",
            "sam3d-camera-fov",
            "sam3d-person-height",
            "sam3d-aspect-ratio",
            "sam3d-output-resolution",
            "sam3d-image-format",
            "sam3d-apply-button",
            "sam3d-undo-button",
            "sam3d-capture-button",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)
        self.assertIn("standalone SAM 3D Body environment", self.html)
        self.assertIn("ComfyUI is not used or modified", self.html)
        self.assertIn("VR Video &amp; Funscript camera", self.html)
        self.assertIn(
            'worker.model || status?.model || "SAM 3D Body"',
            self.javascript,
        )

    def test_sam3d_api_contract_is_centralized_and_revision_checked(self) -> None:
        start = self.javascript.index("const Sam3dClient")
        end = self.javascript.index("const TimelineClient", start)
        client = self.javascript[start:end]
        for contract in (
            'status: "/api/sam3d/status"',
            'jobs: "/api/sam3d/jobs"',
            "/run`",
            "/apply`",
            "/undo`",
            "/capture`",
            "/artifacts/${artifactKind}",
            "SAM3D_JOB_ID_PATTERN",
            "expected_job_revision:",
            "target_uid:",
            "camera_uid:",
            "create_camera:",
            "person_index:",
            "height_m:",
            "aspect_ratio:",
            "output_resolution:",
            "image_format:",
            "horizontal_fov",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, client)
        self.assertIn("body: file", client)
        self.assertIn(
            '"Content-Type": sam3dFileContentType(file)',
            client,
        )
        self.assertIn('query.set("model_id", modelId)', client)
        self.assertIn('query.set("comparison_id", comparisonId)', client)
        self.assertIn("Sam3dClient.run(job.id)", client)
        self.assertNotIn("/select", client)
        self.assertIn("sam3dStatusError.status !== 404", client)

    def test_sam3d_model_comparison_is_grouped_and_labeled(self) -> None:
        for value in ("dinov3_vith16plus", "vit_hmr_512_384", "compare"):
            self.assertIn(f'<option value="{value}">', self.html)
        for contract in (
            "status?.worker",
            "worker.models",
            "normalizeSam3dModel",
            "sam3dSelectedModelIds",
            "newSam3dComparisonId",
            "window.crypto.getRandomValues",
            "const comparisonId = comparing ? newSam3dComparisonId()",
            "for (const [index, modelId] of modelIds.entries())",
            "comparisonId: SAM3D_JOB_ID_PATTERN.test(comparisonId)",
            "function renderSam3dComparison(",
            "candidate.comparisonId === job.comparisonId",
            "sam3dModelDisplayName(job)",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.javascript)
        for selector in (
            ".sam3d-model-runner",
            ".sam3d-model-pill",
            ".sam3d-comparison-grid",
            ".sam3d-comparison-card",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)

    def test_sam3d_custom_models_render_without_weakening_comparison(self) -> None:
        for contract in (
            'option.dataset.sam3dDynamicModel === "true"',
            "if (SAM3D_MODEL_ORDER.includes(model.id)) continue;",
            'option.dataset.sam3dDynamicModel = "true"',
            "elements.sam3dModelSelect.insertBefore(",
            '`${model.default ? " · default" : ""}`',
            "candidates.length !== SAM3D_MODEL_ORDER.length",
            "modelIds.size !== SAM3D_MODEL_ORDER.length",
            "SAM3D_MODEL_ORDER.every((modelId) => modelIds.has(modelId))",
            "candidate.model?.id === modelId",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.javascript)

    def test_sam3d_source_box_and_artifacts_are_bounded(self) -> None:
        self.assertIn(
            "const SAM3D_MAX_UPLOAD_BYTES = 32 * 1024 * 1024;",
            self.javascript,
        )
        self.assertIn("const SAM3D_MAX_HISTORY = 50;", self.javascript)
        self.assertIn("function clampSam3dBbox(", self.javascript)
        self.assertIn("function sam3dBboxPixels(", self.javascript)
        self.assertIn("1600 / Math.max(", self.javascript)
        self.assertIn(
            '"capture",\n        "manifest",\n        "overlay",\n        "source",',
            self.javascript,
        )
        self.assertIn(
            "if (url.origin !== window.location.origin)",
            self.javascript,
        )
        self.assertIn("SAM3D_MAX_HISTORY", self.javascript)

    def test_sam3d_capture_history_is_bounded_and_navigable(self) -> None:
        self.assertIn("const SAM3D_MAX_CAPTURES = 50;", self.javascript)
        self.assertIn("function normalizeSam3dCapture(", self.javascript)
        self.assertIn(
            "const captures = asArray(raw.captures || result.captures)",
            self.javascript,
        )
        self.assertIn(".slice(0, SAM3D_MAX_CAPTURES)", self.javascript)
        self.assertIn("function sam3dSelectedCapture(", self.javascript)
        self.assertIn(
            "selectedCapture?.artifactUrl",
            self.javascript,
        )
        self.assertIn(
            "function renderSam3dCaptureHistory(",
            self.javascript,
        )
        self.assertIn("function moveSam3dCapture(delta)", self.javascript)
        self.assertIn(
            "Capture ${index + 1} of ${captures.length}",
            self.javascript,
        )
        self.assertIn(".sam3d-capture-history", self.styles)
        self.assertIn(".sam3d-capture-history[hidden]", self.styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_sam3d_pending_capture_does_not_alias_an_older_image(self) -> None:
        selection_start = self.javascript.index(
            "function sam3dSelectedCapture("
        )
        selection_end = self.javascript.index(
            "function sam3dArtifactCandidate(", selection_start
        )
        move_start = self.javascript.index("function moveSam3dCapture(")
        move_end = self.javascript.index(
            "function sam3dCaptureBridgeError(", move_start
        )
        script = (
            '"use strict";\n'
            "const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/;\n"
            "const asArray = (value) => Array.isArray(value) ? value : [];\n"
            "let renders = 0;\n"
            "const renderSam3dPreview = () => { renders += 1; };\n"
            "const app = {\n"
            '  sam3dSelectedCaptureRequestId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n'
            '  sam3dPreviewKind: "result",\n'
            "  sam3dCapturePollAttempts: 7,\n"
            "};\n"
            f"{self.javascript[selection_start:selection_end]}\n"
            f"{self.javascript[move_start:move_end]}\n"
            """
const job = {
  captureRequestId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  captureRequested: true,
  captures: [
    { requestId: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", artifactUrl: "/oldest" },
    { requestId: "cccccccccccccccccccccccccccccccc", artifactUrl: "/older" },
  ],
};
app.sam3dSelectedJob = job;
const pendingSelection = sam3dSelectedCapture(job);
const navigation = sam3dCaptureNavigation(job);
moveSam3dCapture(1);
const output = {
  pendingSelection,
  navigation: navigation.map((capture) => ({
    requestId: capture.requestId,
    pending: capture.pending === true,
  })),
  selectedAfterOlder: app.sam3dSelectedCaptureRequestId,
  pollAttempts: app.sam3dCapturePollAttempts,
  renders,
};
process.stdout.write(JSON.stringify(output));
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

        self.assertIsNone(result["pendingSelection"])
        self.assertEqual(
            result["navigation"],
            [
                {
                    "requestId": "a" * 32,
                    "pending": True,
                },
                {
                    "requestId": "b" * 32,
                    "pending": False,
                },
                {
                    "requestId": "c" * 32,
                    "pending": False,
                },
            ],
        )
        self.assertEqual(result["selectedAfterOlder"], "b" * 32)
        self.assertEqual(result["pollAttempts"], 0)
        self.assertEqual(result["renders"], 1)

    def test_sam3d_apply_is_capability_and_revision_guarded(self) -> None:
        apply_start = self.javascript.index(
            "function renderSam3dApplyState("
        )
        apply_end = self.javascript.index(
            "async function applySam3dResult(", apply_start
        )
        apply_state = self.javascript[apply_start:apply_end]
        for guard in (
            "revisionReady",
            "snapshotBridgeBusy()",
            "personVamRunning()",
            "sam3dApplyCapabilityAvailable()",
            "sam3dCaptureCapabilityAvailable()",
            "sam3dJobIsApplied(job)",
            "hasAppliedCamera",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, apply_state)
        self.assertIn("sam3d-apply-v1", self.javascript)
        self.assertIn("sam3d-capture-v1", self.javascript)
        self.assertIn("sam3d-camera-vrfunscript-v1", self.javascript)
        self.assertIn(
            "const SAM3D_CAPTURE_POLL_ATTEMPTS = 310;",
            self.javascript,
        )
        self.assertIn(
            'raw.capture_requested === true || actionName === "capture"',
            self.javascript,
        )
        self.assertIn("function sam3dJobNeedsPolling(", self.javascript)
        self.assertIn("vamActionState: actionState", self.javascript)
        self.assertIn(
            "app.sam3dCaptureReadyJobs.add(job.id)",
            self.javascript,
        )
        self.assertIn("function sam3dCaptureBridgeError(", self.javascript)
        self.assertNotIn(
            'actionName === "capture" && artifactUrls.capture',
            self.javascript,
        )
        self.assertIn(
            "expected_revision: solutionRevision",
            self.javascript,
        )
        capture_start = self.javascript.index(
            "async function captureSam3dResult("
        )
        capture_end = self.javascript.index(
            "const TimelineClient", capture_start
        )
        capture = self.javascript[capture_start:capture_end]
        self.assertIn(
            'const cameraUid = String(job.cameraUid || "").trim();',
            capture,
        )
        self.assertNotIn(
            "elements.sam3dCameraTarget.value",
            capture,
        )
        targets_start = self.javascript.index(
            "function renderSam3dTargets("
        )
        targets_end = self.javascript.index(
            "function sam3dApplyCapabilityAvailable(", targets_start
        )
        targets = self.javascript[targets_start:targets_end]
        self.assertIn("fixedCameraUidExists", targets)
        self.assertIn("!alreadyApplied", targets)
        self.assertIn("One-level undo", self.javascript)
        self.assertIn("showDialog({", self.javascript)

    def test_sam3d_layout_is_responsive(self) -> None:
        for selector in (
            ".sam3d-view",
            ".sam3d-layout",
            ".sam3d-drop-zone",
            ".sam3d-source-editor",
            ".sam3d-preview-stage",
            ".sam3d-target-grid",
            ".sam3d-history-panel",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)
        self.assertIn("@media (max-width: 1180px)", self.styles)
        self.assertIn("@media (max-width: 760px)", self.styles)
        self.assertIn("@media (max-width: 500px)", self.styles)

    def test_static_assets_use_the_current_cache_version(self) -> None:
        self.assertIn("/styles.css?v=0.15.0", self.html)
        self.assertIn("/app.js?v=0.15.0", self.html)


if __name__ == "__main__":
    unittest.main()

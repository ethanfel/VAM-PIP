from __future__ import annotations

from pathlib import Path
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
        self.assertIn('category.targetKind !== "person"', self.javascript)
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
        block_start = self.javascript.index(
            "async function setPersonClothing("
        )
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
        availability = self.javascript[
            availability_start:availability_end
        ]
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
            "          await loadLibrary({ preserveCount: true });",
            self.javascript,
        )

    def test_live_scene_responses_cannot_overwrite_a_newer_snapshot(self) -> None:
        self.assertIn("personRequestGeneration: 0", self.javascript)
        self.assertIn(
            "const sceneRequestGeneration = beginPersonSnapshotRequest();",
            self.javascript,
        )
        accept_start = self.javascript.index(
            "function acceptPersonSnapshot("
        )
        accept_end = self.javascript.index(
            "async function loadPersons(", accept_start
        )
        accept = self.javascript[accept_start:accept_end]
        self.assertIn(
            "!personSnapshotRequestIsCurrent(generation)",
            accept,
        )
        self.assertGreaterEqual(accept.count("return false;"), 2)

        load_start = self.javascript.index("async function loadPersons(")
        load_end = self.javascript.index(
            "function renderPersonContext()", load_start
        )
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
        load_end = self.javascript.index(
            "function renderPersonContext()", load_start
        )
        load = self.javascript[load_start:load_end]
        self.assertIn(
            "if (responseAccepted) {\n"
            "      renderLiveState(app.status || {});",
            load,
        )

        render_start = self.javascript.index("function renderLiveState(")
        render_end = self.javascript.index(
            "function renderAccess()", render_start
        )
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

    def test_clothing_action_keeps_original_target_and_loaded_page_count(self) -> None:
        action_start = self.javascript.index(
            "async function setPersonClothing("
        )
        action_end = self.javascript.index(
            "function workspaceApplyAvailability(", action_start
        )
        action = self.javascript[action_start:action_end]
        self.assertIn("const targetUid = app.selectedPersonUid;", action)
        self.assertIn("target_uid: targetUid", action)
        self.assertIn("for ${targetUid}.", action)
        self.assertNotIn("for ${app.selectedPersonUid}.", action)

        library_start = self.javascript.index("async function loadLibrary(")
        library_end = self.javascript.index(
            "function renderStatus()", library_start
        )
        library = self.javascript[library_start:library_end]
        self.assertIn("preserveCount = false", library)
        self.assertIn(
            "Math.min(Math.max(PAGE_SIZE, app.items.length), 500)",
            library,
        )
        self.assertIn("limit: String(limit)", library)
        self.assertGreaterEqual(
            self.javascript.count("loadLibrary({ preserveCount: true })"),
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
        start = self.javascript.index(
            "async function applyWorkspaceResource("
        )
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
        sync_start = self.javascript.index(
            "function syncWorkspaceActionSnapshot("
        )
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

        render_start = self.javascript.index(
            "function renderWorkspaceActionFeedback("
        )
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

        activity_start = self.javascript.index(
            "async function loadActivity("
        )
        activity_end = self.javascript.index(
            "async function fetchLiveSceneSnapshot()", activity_start
        )
        activity = self.javascript[activity_start:activity_end]
        self.assertIn("workspaceActionIsActive() ||", activity)
        self.assertIn(
            "workspaceActionIsActive() ? 900 : 3000",
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
        sync_activity = self.javascript[
            sync_activity_start:sync_activity_end
        ]
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
        toast_end = self.javascript.index(
            "function setButtonBusy(", toast_start
        )
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
        block_start = self.javascript.index(
            "async function selectCuaChoiceInVam()"
        )
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
        self.assertIn('new Option(choice.label, String(choice.index))', self.javascript)
        self.assertIn('"custom-unity-asset-choice"', self.javascript)
        self.assertIn("state.loadDll !== false", self.javascript)
        self.assertIn("!state.choiceToken", self.javascript)
        self.assertIn("state.choicesTruncated", self.javascript)
        self.assertIn("Multi-item bundles stay at None", self.javascript)
        self.assertNotIn(".innerHTML", self.javascript)

    def test_cua_choice_requires_server_owned_fresh_live_context(self) -> None:
        helper_start = self.javascript.index(
            "function cuaChoiceLiveContextReason("
        )
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

        action_start = self.javascript.index(
            "async function selectCuaChoiceInVam()"
        )
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

    def test_static_assets_use_the_current_cache_version(self) -> None:
        self.assertIn("/styles.css?v=0.6.5", self.html)
        self.assertIn("/app.js?v=0.6.5", self.html)


if __name__ == "__main__":
    unittest.main()

"use strict";

const PAGE_SIZE = 60;
const TOKEN_KEY = "vampip-token";
const PERSON_BRIDGE_BUSY_STATES = new Set([
  "queued",
  "deferred-loading",
  "rescanning",
  "applying",
  "adding",
  "selecting",
  "loading-scene",
]);
const ATOM_TARGET_KINDS = new Set([
  "atom",
  "subscene",
  "custom-unity-asset",
  "cua",
  "plugin-target",
]);
const WORKSPACE_CATEGORY_FALLBACK = Object.freeze([
  {
    id: "scene",
    label: "Scenes",
    group: "Scenes",
    resource_types: ["Scene"],
    target_kind: "none",
    operation: "load-scene",
    required_capability: "scene-load",
    risk: "critical",
    browseable: true,
    live_action: true,
    merge_supported: true,
    noun: "scene",
    description:
      "Complete VaM scenes. Replacing the current scene is destructive and always requires confirmation.",
  },
  {
    id: "subscenes",
    label: "SubScenes",
    group: "Scenes",
    resource_types: ["SubScenes"],
    target_kind: "subscene",
    operation: "load-subscene",
    required_capability: "subscene-load",
    risk: "high",
    browseable: true,
    live_action: false,
    merge_supported: false,
    noun: "subscene",
    description:
      "Reusable groups of atoms that can be brought into a running scene.",
  },
  {
    id: "atom-presets",
    label: "Atom presets",
    group: "Atoms",
    resource_types: ["Preset Atom"],
    target_kind: "atom",
    operation: "apply-atom-preset",
    required_capability: "atom-preset-apply",
    risk: "high",
    browseable: true,
    live_action: false,
    merge_supported: true,
    noun: "atom preset",
    description:
      "Presets for Empty, UI, camera, CUA, and other atom types. Compatibility depends on a live target atom.",
  },
  {
    id: "custom-unity-assets",
    label: "Unity assets",
    group: "Atoms",
    resource_types: ["Custom Unity Assets"],
    target_kind: "custom-unity-asset",
    operation: "load-custom-unity-asset",
    required_capability: "custom-unity-asset-load",
    risk: "critical",
    browseable: true,
    live_action: false,
    merge_supported: false,
    noun: "Unity asset",
    description:
      "Custom Unity Asset bundles. Loading needs a typed CUA target and explicit bridge support.",
  },
  {
    id: "plugins",
    label: "Plugins",
    group: "Extensions",
    resource_types: ["Plugins"],
    target_kind: "plugin-target",
    operation: "load-plugin",
    required_capability: "plugin-apply",
    risk: "critical",
    browseable: true,
    live_action: false,
    merge_supported: true,
    noun: "plugin",
    description:
      "VaM scripts and plugins. Browsing is safe; loading code needs dedicated trust and target rules.",
  },
  {
    id: "preset-appearance",
    label: "Looks",
    group: "Person presets",
    resource_types: ["Preset Appearance"],
    target_kind: "person",
    noun: "look preset",
    description:
      "Full appearance presets can change morphs, skin, hair, clothing, and scale together.",
    operation: "apply-person-preset",
    required_capability: "person-preset-appearance",
    risk: "high",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-hair",
    label: "Hair",
    group: "Person presets",
    resource_types: ["Preset Hair"],
    target_kind: "person",
    noun: "hair preset",
    description:
      "Hair presets select one or more styles and can include simulation and material settings.",
    operation: "apply-person-preset",
    required_capability: "person-preset-hair",
    risk: "medium",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-skin",
    label: "Skin",
    group: "Person presets",
    resource_types: ["Preset Skin"],
    target_kind: "person",
    noun: "skin preset",
    description:
      "Skin presets bundle Person skin textures and material settings.",
    operation: "apply-person-preset",
    required_capability: "person-preset-skin",
    risk: "medium",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-morphs",
    label: "Morphs",
    group: "Person presets",
    resource_types: ["Preset Morphs"],
    target_kind: "person",
    noun: "morph preset",
    description:
      "Morph presets store groups of body or expression values. Individual live sliders require a live schema.",
    operation: "apply-person-preset",
    required_capability: "person-preset-morphs",
    risk: "high",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-clothing",
    label: "Outfits",
    group: "Clothing",
    resource_types: ["Preset Clothing"],
    target_kind: "person",
    noun: "outfit preset",
    description:
      "Clothing presets load a saved outfit. They are different from individual clothing items.",
    operation: "apply-person-preset",
    required_capability: "person-preset-clothing",
    risk: "high",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "clothing-items-female",
    label: "Female items",
    group: "Clothing",
    resource_types: ["Clothing (Female)"],
    target_kind: "person",
    noun: "clothing item",
    description:
      "Individual female clothing definitions. The catalogue can find them, but worn state comes from VaM.",
    operation: "toggle-clothing-item",
    required_capability: "person-clothing-item-toggle",
    risk: "medium",
    browseable: true,
    live_action: false,
    merge_supported: false,
  },
  {
    id: "clothing-items-male",
    label: "Male items",
    group: "Clothing",
    resource_types: ["Clothing (Male)"],
    target_kind: "person",
    noun: "clothing item",
    description:
      "Individual male clothing definitions. Target compatibility must be confirmed by the live Person.",
    operation: "toggle-clothing-item",
    required_capability: "person-clothing-item-toggle",
    risk: "medium",
    browseable: true,
    live_action: false,
    merge_supported: false,
  },
  {
    id: "clothing-item-presets",
    label: "Item styles",
    group: "Clothing",
    resource_types: ["Clothing Item Presets"],
    target_kind: "person-clothing-item",
    noun: "item style",
    description:
      "Material and physics presets for one specific clothing item, not complete outfits.",
    operation: "load-clothing-item-preset",
    required_capability: "person-clothing-item-preset",
    risk: "medium",
    browseable: true,
    live_action: false,
    merge_supported: true,
  },
  {
    id: "preset-pose",
    label: "Pose",
    group: "Person presets",
    resource_types: ["Preset Pose"],
    target_kind: "person",
    noun: "pose preset",
    description:
      "Pose presets can move many controllers at once. Loading must wait until the scene is ready.",
    operation: "apply-person-preset",
    required_capability: "person-preset-pose",
    risk: "high",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-animation",
    label: "Animation",
    group: "Person presets",
    resource_types: ["Preset Animation"],
    target_kind: "person",
    noun: "animation preset",
    description:
      "Person animation presets discovered by the catalogue. Live playback controls are a separate capability.",
    operation: "apply-person-preset",
    required_capability: "person-preset-animation",
    risk: "medium",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-breast-physics",
    label: "Breast physics",
    group: "Person presets",
    resource_types: ["Preset Breast Physics"],
    target_kind: "person",
    noun: "physics preset",
    description:
      "Saved breast-physics settings for compatible Persons.",
    operation: "apply-person-preset",
    required_capability: "person-preset-breast-physics",
    risk: "medium",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-glute-physics",
    label: "Glute physics",
    group: "Person presets",
    resource_types: ["Preset Glute Physics"],
    target_kind: "person",
    noun: "physics preset",
    description:
      "Saved glute-physics settings for compatible Persons.",
    operation: "apply-person-preset",
    required_capability: "person-preset-glute-physics",
    risk: "medium",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-general",
    label: "General",
    group: "Person presets",
    resource_types: ["Preset General"],
    target_kind: "person",
    noun: "general preset",
    description:
      "Broad Person presets that may include physical, appearance, and optional pose data.",
    operation: "apply-person-preset",
    required_capability: "person-preset-general",
    risk: "critical",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
  {
    id: "preset-plugins",
    label: "Person plugins",
    group: "Person presets",
    resource_types: ["Preset Plugins"],
    target_kind: "person",
    noun: "plugin preset",
    description:
      "Saved Person plugin configurations. External loading needs dedicated plugin safety rules.",
    operation: "apply-person-preset",
    required_capability: "person-preset-plugins",
    risk: "critical",
    browseable: true,
    live_action: true,
    merge_supported: true,
  },
]);

const app = {
  status: null,
  activity: null,
  facets: null,
  view: "resources",
  items: [],
  total: 0,
  offset: 0,
  query: "",
  type: "",
  packageState: "all",
  loading: false,
  requestController: null,
  searchTimer: null,
  token: "",
  sessionPlugins: null,
  sessionPluginsError: null,
  activityTimer: null,
  activityInFlight: false,
  activityPollFailed: false,
  activityRefreshNeeded: false,
  lastTerminalOperation: null,
  refreshing: false,
  refreshQueued: false,
  person: null,
  personError: null,
  personInFlight: false,
  personPollAt: 0,
  selectedPersonUid: "",
  selectedAtomUid: "",
  atomTargetMode: "existing",
  newAtomUid: "",
  pendingAtomUid: "",
  atomMutationInFlight: false,
  cuaChoiceInFlight: false,
  applyingWorkspaceResources: new Set(),
  workspaceCategories: [],
  workspaceCategoriesError: null,
  workspaceCategoriesSource: "fallback",
  selectedWorkspaceCategoryId: "scene",
  workspaceApplyMode: "replace",
  personMutationInFlight: false,
};

const elements = {};
const busyContents = new WeakMap();

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheElements();
  captureToken();
  bindEvents();
  configureStateFilter();
  setConnection("connecting", "Connecting");
  let activityLoaded = false;
  try {
    await loadActivity({ refreshOnTerminal: false });
    activityLoaded = true;
  } catch (_error) {
    // The full status request below will surface a useful connection error.
  }
  startActivityPolling();
  if (!activityLoaded || !operationIsBusy()) {
    await refreshAll();
    const operation = app.activity && app.activity.operation;
    if (operation && !operationIsBusy()) {
      app.lastTerminalOperation = operationKey(operation);
    }
  }
}

function cacheElements() {
  const ids = [
    "connection-chip",
    "connection-label",
    "refresh-button",
    "manager-card",
    "mode-title",
    "mode-description",
    "mode-indicator",
    "activate-button",
    "reconcile-button",
    "active-count",
    "hidden-count",
    "resource-count",
    "lease-count",
    "game-status",
    "bridge-status",
    "launch-vam-button",
    "launch-vam-label",
    "scan-button",
    "import-button",
    "session-import-button",
    "session-plugin-status",
    "auto-reconcile",
    "addon-path",
    "state-path",
    "mobile-tools-button",
    "pending-notice",
    "pending-title",
    "pending-message",
    "pending-progress",
    "pending-action",
    "resources-tab-count",
    "workspace-tab-count",
    "packages-tab-count",
    "access-tab-count",
    "library-view",
    "access-view",
    "asset-workspace",
    "person-context",
    "person-target",
    "select-person-button",
    "add-person-button",
    "person-live-state",
    "person-live-title",
    "person-live-detail",
    "atom-context",
    "atom-target",
    "atom-target-mode",
    "atom-mode-existing",
    "atom-mode-create",
    "atom-existing-controls",
    "atom-create-controls",
    "atom-new-uid",
    "add-atom-button",
    "select-atom-button",
    "cua-choice-panel",
    "cua-choice-title",
    "cua-choice-detail",
    "cua-dll-state",
    "cua-choice-select",
    "cua-choice-button",
    "atom-live-state",
    "atom-live-title",
    "atom-live-detail",
    "asset-category-list",
    "asset-category-kicker",
    "asset-category-title",
    "asset-category-description",
    "asset-category-support",
    "asset-category-note",
    "asset-apply-mode",
    "asset-mode-replace",
    "asset-mode-merge",
    "search-input",
    "type-filter-wrap",
    "type-filter",
    "state-filter",
    "result-count",
    "clear-filters",
    "loading-state",
    "empty-state",
    "empty-title",
    "empty-message",
    "empty-action",
    "card-grid",
    "load-more",
    "add-pin-button",
    "pins-count",
    "leases-count",
    "pins-list",
    "leases-list",
    "deactivate-button",
    "toast-region",
    "confirm-dialog",
    "dialog-close",
    "confirm-icon",
    "confirm-eyebrow",
    "confirm-title",
    "confirm-message",
    "plan-summary",
    "dialog-input-wrap",
    "dialog-input-label",
    "dialog-input",
    "confirm-submit",
    "empty-access-template",
  ];
  for (const id of ids) {
    elements[toCamel(id)] = document.getElementById(id);
  }
  elements.viewTabs = Array.from(document.querySelectorAll(".view-tab"));
}

function toCamel(value) {
  return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function captureToken() {
  let stored = "";
  try {
    stored = sessionStorage.getItem(TOKEN_KEY) || "";
  } catch (_error) {
    // sessionStorage can be disabled. The fragment token still works this session.
  }

  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const supplied = fragment.get("token");
  app.token = supplied || stored;

  if (supplied) {
    try {
      sessionStorage.setItem(TOKEN_KEY, supplied);
    } catch (_error) {
      // Keep the token in memory when browser storage is unavailable.
    }
    const cleanUrl = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(null, document.title, cleanUrl);
  }
}

function bindEvents() {
  elements.refreshButton.addEventListener("click", refreshAll);
  elements.scanButton.addEventListener("click", runPackageScan);
  elements.importButton.addEventListener("click", importCatalogue);
  elements.sessionImportButton.addEventListener("click", importSessionDefaults);
  elements.launchVamButton.addEventListener("click", launchVam);
  elements.activateButton.addEventListener("click", activateManagedMode);
  elements.reconcileButton.addEventListener("click", reconcileWithConfirmation);
  elements.pendingAction.addEventListener("click", reconcileWithConfirmation);
  elements.deactivateButton.addEventListener("click", deactivateManagedMode);
  elements.addPinButton.addEventListener("click", promptForPin);
  elements.dialogClose.addEventListener("click", () =>
    elements.confirmDialog.close("cancel"),
  );
  elements.autoReconcile.addEventListener("change", updateAutoReconcile);
  elements.loadMore.addEventListener("click", () => loadLibrary({ append: true }));
  elements.clearFilters.addEventListener("click", clearFilters);
  elements.emptyAction.addEventListener("click", handleEmptyAction);
  elements.personTarget.addEventListener("change", () => {
    app.selectedPersonUid = elements.personTarget.value;
    renderPersonContext();
    if (app.view === "workspace") renderLibrary();
  });
  elements.selectPersonButton.addEventListener("click", selectPersonInVam);
  elements.addPersonButton.addEventListener("click", addPersonInVam);
  elements.atomTarget.addEventListener("change", () => {
    app.selectedAtomUid = elements.atomTarget.value;
    renderAtomContext();
    if (app.view === "workspace") renderLibrary();
  });
  elements.selectAtomButton.addEventListener("click", selectAtomInVam);
  elements.addAtomButton.addEventListener("click", addAtomInVam);
  elements.cuaChoiceSelect.addEventListener("change", updateCuaChoiceButton);
  elements.cuaChoiceButton.addEventListener("click", selectCuaChoiceInVam);
  for (const modeInput of [
    elements.atomModeExisting,
    elements.atomModeCreate,
  ]) {
    modeInput.addEventListener("change", () => {
      if (!modeInput.checked || modeInput.disabled) return;
      app.atomTargetMode = modeInput.value;
      if (app.atomTargetMode === "create" && !app.newAtomUid) {
        app.newAtomUid = suggestedAtomUid(currentWorkspaceCategory());
      }
      renderAtomContext();
      if (app.view === "workspace") renderLibrary();
    });
  }
  elements.atomNewUid.addEventListener("input", () => {
    app.newAtomUid = elements.atomNewUid.value;
    renderAtomContext();
    if (app.view === "workspace") renderLibrary();
  });
  elements.assetCategoryList.addEventListener("click", (event) => {
    const categoryButton = event.target.closest("[data-workspace-category]");
    if (categoryButton) {
      setWorkspaceCategory(categoryButton.dataset.workspaceCategory);
    }
  });
  for (const modeInput of [
    elements.assetModeReplace,
    elements.assetModeMerge,
  ]) {
    modeInput.addEventListener("change", () => {
      if (!modeInput.checked || modeInput.disabled) return;
      app.workspaceApplyMode = modeInput.value;
      renderWorkspaceCategorySummary();
      if (app.view === "workspace") renderLibrary();
    });
  }

  elements.searchInput.addEventListener("input", () => {
    window.clearTimeout(app.searchTimer);
    app.searchTimer = window.setTimeout(() => {
      app.query = elements.searchInput.value.trim();
      loadLibrary();
    }, 280);
    updateClearFilters();
  });

  elements.typeFilter.addEventListener("change", () => {
    app.type = elements.typeFilter.value;
    updateClearFilters();
    loadLibrary();
  });

  elements.stateFilter.addEventListener("change", () => {
    app.packageState = elements.stateFilter.value;
    updateClearFilters();
    loadLibrary();
  });

  for (const tab of elements.viewTabs) {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  }

  elements.mobileToolsButton.addEventListener("click", () => {
    const open = document.body.classList.toggle("tools-open");
    elements.mobileToolsButton.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("click", (event) => {
    if (
      document.body.classList.contains("tools-open") &&
      window.innerWidth <= 920 &&
      !event.target.closest(".sidebar") &&
      !event.target.closest("#mobile-tools-button")
    ) {
      closeMobileTools();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (
      event.key === "/" &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      !isEditing(event.target) &&
      !elements.confirmDialog.open &&
      app.view !== "access"
    ) {
      event.preventDefault();
      elements.searchInput.focus();
    }
    if (event.key === "Escape" && document.body.classList.contains("tools-open")) {
      closeMobileTools();
    }
  });
}

function isEditing(target) {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    Boolean(target && target.isContentEditable)
  );
}

function closeMobileTools() {
  document.body.classList.remove("tools-open");
  elements.mobileToolsButton.setAttribute("aria-expanded", "false");
}

function operationIsBusy(activity = app.activity) {
  const operation = activity && activity.operation;
  if (!operation || typeof operation !== "object") return false;
  if (operation.busy !== undefined) return Boolean(operation.busy);
  return !["", "idle", "completed", "failed", "cancelled"].includes(
    String(operation.status || "").toLowerCase(),
  );
}

function operationKey(operation) {
  if (!operation || typeof operation !== "object") return "";
  if (numberOr(operation.id, 0) > 0) {
    return [
      String(operation.id),
      operation.run_name,
      operation.manifest,
    ].filter(Boolean).join(":");
  }
  return [operation.run_name, operation.manifest, operation.status]
    .filter(Boolean)
    .join(":");
}

function startActivityPolling() {
  if (app.activityTimer !== null) return;
  const tick = async () => {
    app.activityTimer = null;
    try {
      await loadActivity();
    } catch (_error) {
      app.activityPollFailed = true;
      app.activityRefreshNeeded = true;
      setConnection("error", "Unavailable");
    } finally {
      const delay = operationIsBusy() ? 650 : 1500;
      app.activityTimer = window.setTimeout(tick, delay);
    }
  };
  app.activityTimer = window.setTimeout(tick, 650);
}

async function loadActivity({ refreshOnTerminal = true } = {}) {
  if (app.activityInFlight) return app.activity;
  app.activityInFlight = true;
  const previous = app.activity;
  let scheduleRefresh = false;
  try {
    const activity = await api("/api/activity");
    app.activity = activity || {};
    const recovered = app.activityPollFailed;
    const previousInstance = previous && previous.manager_instance;
    const currentInstance = app.activity.manager_instance;
    const instanceChanged =
      Boolean(previousInstance) &&
      Boolean(currentInstance) &&
      previousInstance !== currentInstance;
    app.activityPollFailed = false;
    if (recovered || instanceChanged) {
      app.activityRefreshNeeded = true;
    }
    renderLiveState(app.status || {});
    const workspaceCategory =
      app.view === "workspace" ? currentWorkspaceCategory() : null;
    const shouldPollScene =
      snapshotBridgeBusy() ||
      Boolean(
        workspaceCategory &&
          (workspaceCategory.liveAction ||
            workspaceCategory.targetKind === "person" ||
            ATOM_TARGET_KINDS.has(workspaceCategory.targetKind)),
      );
    if (shouldPollScene && Date.now() - app.personPollAt > 3000) {
      loadPersons({ quiet: true });
    }
    setConnection("online", "Local manager");

    const operation = app.activity.operation || {};
    const key = operationKey(operation);
    const terminalStatus = ["completed", "failed", "cancelled"].includes(
      String(operation.status || "").toLowerCase(),
    );
    const busy = operationIsBusy(app.activity);
    const terminal = terminalStatus && !busy;
    const unhandledTerminal =
      terminal && Boolean(key) && app.lastTerminalOperation !== key;
    if (
      refreshOnTerminal &&
      !busy &&
      (unhandledTerminal || app.activityRefreshNeeded)
    ) {
      if (terminal) app.lastTerminalOperation = key;
      app.activityRefreshNeeded = false;
      if (
        unhandledTerminal &&
        operation.status === "failed" &&
        operation.error
      ) {
        toast("Package update failed", String(operation.error), "error");
      }
      scheduleRefresh = true;
    }
    return app.activity;
  } finally {
    app.activityInFlight = false;
    if (scheduleRefresh) {
      window.setTimeout(() => refreshAll({ force: true }), 0);
    }
  }
}

async function fetchLiveSceneSnapshot() {
  try {
    return await api("/api/vam/scene");
  } catch (error) {
    if (error.status !== 404) throw error;
    return api("/api/vam/persons");
  }
}

async function fetchWorkspaceCategories() {
  try {
    return await api("/api/workspace/categories");
  } catch (error) {
    if (error.status !== 404) throw error;
    return api("/api/person/categories");
  }
}

async function refreshAll(options = {}) {
  const force = Boolean(options && options.force);
  if (operationIsBusy() && !force) {
    await loadActivity({ refreshOnTerminal: false });
    return;
  }
  if (app.refreshing) {
    app.refreshQueued = true;
    return;
  }

  app.refreshing = true;
  setButtonBusy(elements.refreshButton, true);
  try {
    const [
      statusResult,
      facetResult,
      sessionPluginResult,
      sceneResult,
      workspaceCategoriesResult,
    ] =
      await Promise.allSettled([
        api("/api/status"),
        api("/api/catalog/facets"),
        api("/api/session-plugins"),
        fetchLiveSceneSnapshot(),
        fetchWorkspaceCategories(),
      ]);

    if (statusResult.status === "rejected") {
      throw statusResult.reason;
    }

    app.status = statusResult.value || {};
    renderStatus();
    renderAccess();
    setConnection("online", "Local manager");

    if (facetResult.status === "fulfilled") {
      app.facets = facetResult.value || {};
      renderFacets();
    }

    if (sessionPluginResult.status === "fulfilled") {
      app.sessionPlugins = sessionPluginResult.value || {};
      app.sessionPluginsError = null;
    } else {
      app.sessionPlugins = null;
      app.sessionPluginsError = sessionPluginResult.reason;
    }
    renderSessionPlugins();

    if (sceneResult.status === "fulfilled") {
      acceptPersonSnapshot(sceneResult.value || {});
    } else {
      app.personError = sceneResult.reason;
      app.personPollAt = Date.now();
    }
    if (workspaceCategoriesResult.status === "fulfilled") {
      acceptWorkspaceCategories(workspaceCategoriesResult.value);
    } else {
      app.workspaceCategoriesError = workspaceCategoriesResult.reason;
      if (!app.workspaceCategories.length) {
        app.workspaceCategories = fallbackWorkspaceCategories();
      }
    }
    renderWorkspaceCategoryNavigation();
    renderWorkspaceCategorySummary();

    if (app.view !== "access") {
      await loadLibrary();
    }
  } catch (error) {
    setConnection("error", "Unavailable");
    showErrorState(error);
    toast("Could not reach VAM-PIP", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.refreshButton, false);
    app.refreshing = false;
    const rerun = app.refreshQueued;
    app.refreshQueued = false;
    if (rerun && !operationIsBusy()) {
      window.setTimeout(() => refreshAll(), 0);
    }
  }
}

function renderSessionPlugins() {
  const snapshot = app.sessionPlugins;
  const statusElement = elements.sessionPluginStatus;
  statusElement.classList.remove("is-ready", "is-missing");

  if (!snapshot) {
    statusElement.textContent = app.sessionPluginsError
      ? "Could not check the session preset."
      : "Checking the default session preset…";
    elements.sessionImportButton.disabled = Boolean(app.sessionPluginsError);
    elements.sessionImportButton.title = app.sessionPluginsError
      ? "Refresh to check the default session preset again"
      : "";
    return;
  }

  const counts = snapshot.counts || {};
  const packaged = sessionPackagedRoots(snapshot).length;
  const loose = numberOr(counts.loose, 0);
  const alreadyPinned = Math.min(numberOr(counts.already_pinned, 0), packaged);
  const missing = Math.max(numberOr(counts.missing, 0), 0);

  if (!snapshot.exists) {
    statusElement.textContent = "No default session preset found.";
    statusElement.classList.add("is-missing");
    elements.sessionImportButton.disabled = true;
    elements.sessionImportButton.title =
      "Save a default Session Plugins preset in VaM, then refresh";
    return;
  }

  if (packaged === 0) {
    statusElement.textContent = loose
      ? `${formatNumber(loose)} enabled loose ${plural("plugin", loose)} · no pins needed`
      : "No enabled session plugins detected.";
    elements.sessionImportButton.disabled = true;
    elements.sessionImportButton.title = loose
      ? "Loose scripts stay available without package pins"
      : "There are no enabled packaged session plugins to import";
    return;
  }

  const remaining = Math.max(packaged - alreadyPinned, 0);
  const details = [
    `${formatNumber(packaged)} enabled package ${plural("root", packaged)}`,
  ];
  if (alreadyPinned) {
    details.push(`${formatNumber(alreadyPinned)} already pinned`);
  }
  if (remaining) {
    details.push(`${formatNumber(remaining)} ready to pin`);
  }
  if (loose) details.push(`${formatNumber(loose)} loose`);
  if (missing) {
    details.push(`${formatNumber(missing)} missing`);
    statusElement.classList.add("is-missing");
  }
  statusElement.textContent = details.join(" · ");
  if (remaining === 0 && missing === 0) statusElement.classList.add("is-ready");
  elements.sessionImportButton.disabled = remaining === 0 || missing > 0;
  elements.sessionImportButton.title =
    missing > 0
      ? "Install the missing session-plugin packages and dependencies first"
      : remaining === 0
      ? "Enabled packaged session plugins are already preserved"
      : `Pin ${formatNumber(remaining)} enabled package ${plural("root", remaining)}`;
}

function sessionPackagedRoots(snapshot) {
  return Array.from(
    new Set(
      asArray(snapshot && snapshot.enabled_packaged_roots)
        .map((root) => String(root || "").trim())
        .filter(Boolean),
    ),
  );
}

async function ensureSessionPlugins({ refresh = false } = {}) {
  if (app.sessionPlugins && !refresh) return app.sessionPlugins;
  try {
    app.sessionPlugins = await api("/api/session-plugins");
    app.sessionPluginsError = null;
    renderSessionPlugins();
    return app.sessionPlugins;
  } catch (error) {
    app.sessionPluginsError = error;
    renderSessionPlugins();
    throw error;
  }
}

function booleanValue(value, fallback = false) {
  if (value === undefined || value === null) return fallback;
  if (typeof value === "string") {
    const folded = value.trim().toLowerCase();
    if (["false", "0", "no", "off"].includes(folded)) return false;
    if (["true", "1", "yes", "on"].includes(folded)) return true;
  }
  return Boolean(value);
}

function workspaceCategoryId(value, index = 0) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || `category-${index + 1}`;
}

function workspaceCategoryNoun(entry, label) {
  const explicit = String(entry.noun || entry.item_name || "").trim();
  if (explicit) return explicit;
  const normalized = label.trim().toLowerCase();
  if (normalized.endsWith(" presets")) {
    return `${normalized.slice(0, -" presets".length)} preset`;
  }
  if (normalized.endsWith(" items")) {
    return normalized.slice(0, -" items".length) + " item";
  }
  if (normalized.endsWith("s") && normalized.length > 1) {
    return normalized.slice(0, -1);
  }
  return normalized || "resource";
}

function normalizeWorkspaceCategories(payload) {
  const document =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const rows = Array.isArray(payload)
    ? payload
    : asArray(document.categories || document.items);

  return rows
    .filter((entry) => entry && typeof entry === "object")
    .map((entry, index) => {
      let resourceTypes =
        entry.resource_types ??
        entry.resourceTypes ??
        entry.types ??
        entry.resource_type ??
        entry.type ??
        [];
      if (!Array.isArray(resourceTypes)) resourceTypes = [resourceTypes];
      resourceTypes = Array.from(
        new Set(
          resourceTypes
            .map((value) => String(value || "").trim())
            .filter(Boolean),
          ),
      );
      let atomTypes = entry.atom_types ?? entry.atomTypes ?? [];
      if (!Array.isArray(atomTypes)) atomTypes = [atomTypes];
      atomTypes = atomTypes
        .map((value) => String(value || "").trim())
        .filter(Boolean);

      const operation = String(
        entry.operation || entry.action_kind || "browse",
      )
        .trim()
        .toLowerCase();

      const label = String(
        entry.label || entry.title || entry.name || resourceTypes[0] || "Resources",
      ).trim();
      const countValue = entry.count ?? entry.total;
      return {
        id: workspaceCategoryId(entry.id || entry.key || label, index),
        label,
        group: prettyType(
          String(entry.group || entry.section || "Other").trim() || "Other",
        ),
        kicker: String(entry.kicker || entry.kind_label || "Catalogue resources"),
        description: String(
          entry.description ||
            `Browse ${label.toLowerCase()} from the imported local catalogue.`,
        ),
        noun: workspaceCategoryNoun(entry, label),
        resourceTypes,
        atomTypes,
        targetAtomType: String(
          entry.target_atom_type || entry.targetAtomType || atomTypes[0] || "",
        ).trim(),
        targetKind: String(entry.target_kind || entry.targetKind || "none")
          .trim()
          .toLowerCase(),
        operation,
        browseable: booleanValue(entry.browseable, resourceTypes.length > 0),
        liveAction: booleanValue(
          entry.live_action ?? entry.load_supported ?? entry.apply_supported,
          false,
        ),
        mergeSupported: booleanValue(entry.merge_supported, false),
        createSupported: booleanValue(
          entry.create_supported ?? entry.createSupported,
          false,
        ),
        createCapability: String(
          entry.create_capability || entry.createCapability || "",
        ).trim(),
        requiredCapability: String(
          entry.required_capability ||
            entry.capability ||
            "",
        ).trim(),
        risk: String(entry.risk || "low").trim().toLowerCase(),
        riskReason: String(entry.risk_reason || "").trim(),
        count:
          countValue === undefined || countValue === null
            ? null
            : Math.max(0, numberOr(countValue, 0)),
        note: String(entry.note || entry.unsupported_reason || "").trim(),
      };
    })
    .filter((category) => category.resourceTypes.length || category.id);
}

function fallbackWorkspaceCategories() {
  return normalizeWorkspaceCategories(WORKSPACE_CATEGORY_FALLBACK);
}

function acceptWorkspaceCategories(payload) {
  const published = normalizeWorkspaceCategories(payload);
  const categories = published.length ? published : fallbackWorkspaceCategories();
  app.workspaceCategories = categories;
  app.workspaceCategoriesError = null;
  app.workspaceCategoriesSource = published.length ? "server" : "fallback";

  if (
    !categories.some(
      (category) => category.id === app.selectedWorkspaceCategoryId,
    )
  ) {
    app.selectedWorkspaceCategoryId =
      categories.find((category) => category.id === "scene")?.id ||
      categories[0]?.id ||
      "";
  }
  renderWorkspaceCategoryNavigation();
  renderWorkspaceCategorySummary();
}

function ensureWorkspaceCategories() {
  if (!app.workspaceCategories.length) {
    app.workspaceCategories = fallbackWorkspaceCategories();
    app.workspaceCategoriesSource = "fallback";
  }
  return app.workspaceCategories;
}

function currentWorkspaceCategory() {
  const categories = ensureWorkspaceCategories();
  return (
    categories.find(
      (category) => category.id === app.selectedWorkspaceCategoryId,
    ) ||
    categories[0] ||
    null
  );
}

function workspaceFacetCounts() {
  const counts = new Map();
  for (const facet of normalizeFacetTypes(app.facets)) {
    counts.set(String(facet.value).toLowerCase(), facet.count);
  }
  return counts;
}

function workspaceCategoryCount(category) {
  if (category && category.count !== null) return category.count;
  const facets = workspaceFacetCounts();
  return asArray(category && category.resourceTypes).reduce(
    (total, resourceType) =>
      total + Math.max(0, numberOr(facets.get(resourceType.toLowerCase()), 0)),
    0,
  );
}

function renderWorkspaceCategoryNavigation() {
  const categories = ensureWorkspaceCategories();
  const renderKey = JSON.stringify(
    categories.map((category) => [
      category.id,
      category.label,
      category.group,
      workspaceCategoryCount(category),
      category.id === app.selectedWorkspaceCategoryId,
    ]),
  );
  if (elements.assetCategoryList.dataset.renderKey === renderKey) return;
  elements.assetCategoryList.dataset.renderKey = renderKey;
  elements.assetCategoryList.replaceChildren();

  const groups = new Map();
  for (const category of categories) {
    if (!groups.has(category.group)) groups.set(category.group, []);
    groups.get(category.group).push(category);
  }

  for (const [groupName, groupCategories] of groups) {
    const group = createElement("section", "asset-category-group");
    group.setAttribute("aria-label", groupName);
    const heading = createElement("span", "asset-category-group-label");
    heading.textContent = groupName;
    const choices = createElement("div", "asset-category-choices");
    for (const category of groupCategories) {
      const active = category.id === app.selectedWorkspaceCategoryId;
      const categoryButton = button(category.label, "asset-category-button");
      categoryButton.dataset.workspaceCategory = category.id;
      categoryButton.classList.toggle("is-active", active);
      categoryButton.setAttribute("aria-pressed", String(active));
      categoryButton.setAttribute("aria-controls", "card-grid");
      const count = createElement("span", "asset-category-count");
      count.textContent = formatCompact(workspaceCategoryCount(category));
      categoryButton.append(count);
      choices.append(categoryButton);
    }
    group.append(heading, choices);
    elements.assetCategoryList.append(group);
  }

  const uniqueTypes = new Set(
    categories.flatMap((category) => category.resourceTypes),
  );
  const facets = workspaceFacetCounts();
  const total = Array.from(uniqueTypes).reduce(
    (sum, resourceType) =>
      sum + Math.max(0, numberOr(facets.get(resourceType.toLowerCase()), 0)),
    0,
  );
  elements.workspaceTabCount.textContent = total ? formatCompact(total) : "Assets";
}

function workspaceSupportBadge(label, state) {
  return badge(label, `asset-support-badge is-${state}`);
}

function workspaceApplyModes(category) {
  if (!category || !category.liveAction) return [];
  if (
    ![
      "load-scene",
      "load-preset",
      "apply-person-preset",
      "apply-atom-preset",
      "load-subscene",
      "load-custom-unity-asset",
    ].includes(category.operation)
  ) {
    return [];
  }
  const creatingManagedTarget =
    categoryUsesManagedAtomTarget(category) &&
    app.atomTargetMode === "create";
  return category.mergeSupported && !creatingManagedTarget
    ? ["replace", "merge"]
    : ["replace"];
}

function syncWorkspaceApplyModeControls(category) {
  const supportedModes = new Set(workspaceApplyModes(category));
  const creatingManagedTarget =
    categoryUsesManagedAtomTarget(category) &&
    app.atomTargetMode === "create";
  for (const input of [
    elements.assetModeReplace,
    elements.assetModeMerge,
  ]) {
    const supported = supportedModes.has(input.value);
    input.disabled = !supported;
    input.closest("label").title = supported
      ? `${prettyType(input.value)} this ${category.noun}`
      : input.value === "merge" && creatingManagedTarget
        ? category.operation === "apply-atom-preset"
          ? "Create new uses Replace because BrowserAssist cannot merge into a target that does not exist yet"
          : "Create new uses Replace because merge requires an existing target"
        : category.liveAction
          ? `${prettyType(input.value)} is not supported for ${category.label}`
          : `${category.label} is browse-only with the current manager`;
  }
  if (!supportedModes.has(app.workspaceApplyMode)) {
    app.workspaceApplyMode = supportedModes.has("replace")
      ? "replace"
      : supportedModes.has("merge")
        ? "merge"
        : "replace";
  }
  elements.assetModeReplace.checked = app.workspaceApplyMode === "replace";
  elements.assetModeMerge.checked = app.workspaceApplyMode === "merge";
  elements.assetApplyMode.hidden = supportedModes.size === 0;
}

function renderWorkspaceCategorySummary() {
  const category = currentWorkspaceCategory();
  if (!category) return;

  elements.assetCategoryKicker.textContent = category.kicker;
  elements.assetCategoryTitle.textContent = category.label;
  elements.assetCategoryDescription.textContent = category.description;
  elements.assetCategorySupport.replaceChildren(
    workspaceSupportBadge(
      category.browseable ? "Browse · available" : "Browse · unavailable",
      category.browseable ? "ready" : "muted",
    ),
    workspaceSupportBadge(
      category.liveAction ? "Live load · supported" : "Live load · browse only",
      category.liveAction ? "ready" : "muted",
    ),
    workspaceSupportBadge(
      `${prettyType(category.risk)} risk`,
      ["high", "critical"].includes(category.risk) ? "warning" : "muted",
    ),
  );

  let note = category.note;
  if (!note && category.id === "clothing-item-presets") {
    note =
      "An item style belongs to a specific worn clothing item. VAM-PIP will not guess that relationship from its folder name.";
  } else if (!note && category.operation === "toggle-clothing-item") {
    note =
      "The offline catalogue cannot tell which items this Person is wearing. Item toggles stay disabled until VaM publishes that live state.";
  } else if (!note && !category.liveAction) {
    note =
      "This category is indexed now, but loading is intentionally disabled until the bridge validates this exact resource type.";
  } else if (!note) {
    note =
      "The manager resolves the catalogue ID and package lease; the browser never sends a filesystem path to VaM.";
  }
  if (category.riskReason) {
    note = `${note} ${category.riskReason}`;
  }
  if (app.workspaceCategoriesSource === "fallback") {
    note +=
      " The manager has not published its Workspace map, so this page is using its built-in catalogue map.";
  }
  elements.assetCategoryNote.textContent = note;

  syncWorkspaceApplyModeControls(category);
  elements.personContext.hidden = category.targetKind !== "person";
  elements.atomContext.hidden = !ATOM_TARGET_KINDS.has(category.targetKind);
  renderPersonContext();
  renderAtomContext();
}

function setWorkspaceCategory(categoryId) {
  const category = ensureWorkspaceCategories().find(
    (candidate) => candidate.id === categoryId,
  );
  if (!category || category.id === app.selectedWorkspaceCategoryId) return;
  app.selectedWorkspaceCategoryId = category.id;
  app.items = [];
  app.total = 0;
  app.offset = 0;
  prepareAtomTarget(category);
  renderWorkspaceCategoryNavigation();
  renderWorkspaceCategorySummary();
  updateWorkspaceSearchPlaceholder();
  if (
    category.liveAction ||
    category.targetKind === "person" ||
    ATOM_TARGET_KINDS.has(category.targetKind)
  ) {
    loadPersons({ quiet: true });
  }
  loadLibrary();
}

function personList(snapshot = app.person) {
  return asArray(snapshot && snapshot.persons)
    .filter((person) => person && typeof person === "object")
    .map((person) => ({
      ...person,
      uid: String(person.uid || "").trim(),
    }))
    .filter((person) => person.uid);
}

function atomList(snapshot = app.person) {
  return asArray(snapshot && snapshot.atoms)
    .filter((atom) => atom && typeof atom === "object")
    .map((atom) => ({
      ...atom,
      uid: String(atom.uid || "").trim(),
      type: String(atom.type || atom.atom_type || "").trim(),
    }))
    .filter((atom) => atom.uid);
}

function integerValue(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function cuaStateForAtom(atom) {
  const raw = atom && typeof atom.cua === "object" ? atom.cua : null;
  if (!raw || Array.isArray(raw)) return null;

  const loadDllRaw = raw.loadDll ?? raw.load_dll;
  const readyRaw = raw.ready;
  const selectedIndexRaw = raw.selectedIndex ?? raw.selected_index;
  const choiceCountRaw = raw.choiceCount ?? raw.choice_count;
  const choicesTruncatedRaw =
    raw.choicesTruncated ?? raw.choices_truncated;
  const seen = new Set();
  const choices = [];
  for (const choice of asArray(raw.choices)) {
    if (!choice || typeof choice !== "object" || Array.isArray(choice)) continue;
    const index = integerValue(choice.index);
    if (index === null || index < 1 || seen.has(index)) continue;
    seen.add(index);
    choices.push({
      index,
      label: String(choice.label || `Asset ${index}`),
    });
  }

  const selectedIndex = integerValue(selectedIndexRaw);
  const publishedCount = integerValue(choiceCountRaw);
  return {
    loadDll:
      loadDllRaw === undefined || loadDllRaw === null
        ? null
        : booleanValue(loadDllRaw),
    ready:
      readyRaw === undefined || readyRaw === null
        ? false
        : booleanValue(readyRaw),
    choiceToken: String(raw.choiceToken ?? raw.choice_token ?? "").trim(),
    choiceCount:
      publishedCount === null || publishedCount < 0
        ? choices.length
        : publishedCount,
    selectedIndex:
      selectedIndex === null || selectedIndex < 0 ? null : selectedIndex,
    choices,
    choicesTruncated:
      choicesTruncatedRaw === undefined || choicesTruncatedRaw === null
        ? false
        : booleanValue(choicesTruncatedRaw),
  };
}

function isCuaCategory(category = currentWorkspaceCategory()) {
  return category?.operation === "load-custom-unity-asset";
}

function selectedCuaTarget(category = currentWorkspaceCategory()) {
  if (
    !isCuaCategory(category) ||
    app.atomTargetMode === "create" ||
    !app.selectedAtomUid
  ) {
    return null;
  }
  return (
    atomsForCategory(category).find(
      (atom) => atom.uid === app.selectedAtomUid,
    ) || null
  );
}

function atomsForCategory(category = currentWorkspaceCategory()) {
  const atoms = atomList();
  const explicitType = String(category?.targetAtomType || "").toLowerCase();
  const impliedTypes = {
    subscene: "subscene",
    "custom-unity-asset": "customunityasset",
    cua: "customunityasset",
  };
  const expectedType = explicitType || impliedTypes[category?.targetKind] || "";
  return expectedType
    ? atoms.filter((atom) => atom.type.toLowerCase() === expectedType)
    : atoms;
}

function categoryUsesManagedAtomTarget(category = currentWorkspaceCategory()) {
  return Boolean(
    category &&
      category.liveAction &&
      [
        "apply-atom-preset",
        "load-subscene",
        "load-custom-unity-asset",
      ].includes(category.operation),
  );
}

function categorySupportsTargetCreation(
  category = currentWorkspaceCategory(),
) {
  return Boolean(
    categoryUsesManagedAtomTarget(category) && category.createSupported,
  );
}

function categoryCreateCapability(category = currentWorkspaceCategory()) {
  if (!categorySupportsTargetCreation(category)) return "";
  return String(category.createCapability || "atom-add").trim();
}

function suggestedAtomUid(category = currentWorkspaceCategory()) {
  const typeName =
    String(category?.targetAtomType || "").trim() ||
    (category?.targetKind === "subscene" ? "SubScene" : "Atom");
  const base =
    typeName
      .replace(/[^a-z0-9_-]+/gi, "")
      .replace(/^[-_]+|[-_]+$/g, "") || "Atom";
  const used = new Set(atomList().map((atom) => atom.uid.toLowerCase()));
  if (!used.has(base.toLowerCase())) return base;
  let suffix = 2;
  while (used.has(`${base}${suffix}`.toLowerCase())) suffix += 1;
  return `${base}${suffix}`;
}

function atomUidIsValid(value) {
  const uid = String(value || "").trim();
  return (
    uid.length > 0 &&
    uid.length <= 200 &&
    !Array.from(uid).some((character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127;
    })
  );
}

function activeAtomTargetUid(category = currentWorkspaceCategory()) {
  if (!categoryUsesManagedAtomTarget(category)) return app.selectedAtomUid;
  return app.atomTargetMode === "create"
    ? app.newAtomUid.trim()
    : app.selectedAtomUid;
}

function prepareAtomTarget(category = currentWorkspaceCategory()) {
  const compatible = atomsForCategory(category);
  if (compatible.length) {
    if (!compatible.some((atom) => atom.uid === app.selectedAtomUid)) {
      app.selectedAtomUid =
        compatible.find((atom) => Boolean(atom.selected))?.uid ||
        compatible[0].uid;
    }
    app.atomTargetMode = "existing";
  } else if (categorySupportsTargetCreation(category)) {
    app.atomTargetMode = "create";
  } else {
    app.atomTargetMode = "existing";
  }
  app.newAtomUid = suggestedAtomUid(category);
}

function personCapabilities(snapshot = app.person) {
  return new Set(
    asArray(snapshot && snapshot.capabilities)
      .map((capability) => String(capability || "").trim())
      .filter(Boolean),
  );
}

function personVamRunning(snapshot = app.person) {
  if (snapshot && snapshot.vam_running !== undefined) {
    return Boolean(snapshot.vam_running);
  }
  if (app.activity && app.activity.vam) {
    return Boolean(app.activity.vam.running);
  }
  return Boolean(app.status && app.status.vam && app.status.vam.running);
}

function snapshotBridgeBusy(snapshot = app.person) {
  if (snapshot && snapshot.bridge_busy === true) return true;
  const state = String(snapshot?.bridge?.state || "").toLowerCase();
  return PERSON_BRIDGE_BUSY_STATES.has(state);
}

function personControlKey() {
  const snapshot = app.person || {};
  return JSON.stringify({
    error: app.personError ? errorMessage(app.personError) : "",
    vamRunning: personVamRunning(snapshot),
    available: Boolean(snapshot.available),
    loading: Boolean(snapshot.loading),
    bridgeBusy: snapshotBridgeBusy(snapshot),
    selected: app.selectedPersonUid,
    capabilities: Array.from(personCapabilities(snapshot)).sort(),
    persons: personList(snapshot).map((person) => [
      person.uid,
      Boolean(person.selected),
    ]),
    atoms: atomList(snapshot).map((atom) => [
      atom.uid,
      atom.type,
      Boolean(atom.selected),
      atom.cua || null,
    ]),
  });
}

function acceptPersonSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") snapshot = {};
  app.person = snapshot;
  app.personError = null;
  app.personPollAt = Date.now();

  const persons = personList(snapshot);
  const known = new Set(persons.map((person) => person.uid));
  if (!known.has(app.selectedPersonUid)) {
    const requested = String(snapshot.selected_uid || "").trim();
    const selected = persons.find((person) => Boolean(person.selected));
    app.selectedPersonUid = known.has(requested)
      ? requested
      : selected
        ? selected.uid
        : persons[0]?.uid || "";
  }

  const atoms = atomList(snapshot);
  const knownAtoms = new Set(atoms.map((atom) => atom.uid));
  if (app.pendingAtomUid && knownAtoms.has(app.pendingAtomUid)) {
    app.selectedAtomUid = app.pendingAtomUid;
    app.pendingAtomUid = "";
    app.atomTargetMode = "existing";
  } else if (!knownAtoms.has(app.selectedAtomUid)) {
    const requested = String(snapshot.selected_uid || "").trim();
    const selected = atoms.find((atom) => Boolean(atom.selected));
    app.selectedAtomUid = knownAtoms.has(requested)
      ? requested
      : selected
        ? selected.uid
        : atoms[0]?.uid || "";
  }
}

async function loadPersons({ quiet = false } = {}) {
  if (app.personInFlight) return app.person;
  app.personInFlight = true;
  const previousKey = personControlKey();
  try {
    const snapshot = await fetchLiveSceneSnapshot();
    acceptPersonSnapshot(snapshot);
  } catch (error) {
    app.personError = error;
    app.personPollAt = Date.now();
    if (!quiet) {
      toast(
        "Live Person controls unavailable",
        `${errorMessage(error)} Catalogue browsing is still available.`,
        "error",
      );
    }
  } finally {
    app.personInFlight = false;
    renderPersonContext();
    renderAtomContext();
    if (app.view === "workspace" && previousKey !== personControlKey()) {
      renderLibrary();
    }
  }
  return app.person;
}

function renderPersonContext() {
  const category = currentWorkspaceCategory();
  const isPersonCategory = category && category.targetKind === "person";
  elements.personContext.hidden = !isPersonCategory;
  if (!isPersonCategory) return;

  const snapshot = app.person || {};
  const persons = personList(snapshot);
  const capabilities = personCapabilities(snapshot);
  const canApplyCategory =
    !category.requiredCapability ||
    capabilities.has(category.requiredCapability);
  const canAddPerson = capabilities.has("person-add");
  const canSelectPerson = capabilities.has("person-select");
  const gameRunning = personVamRunning(snapshot);
  const bridge = snapshot.bridge || {};
  const bridgeState = String(bridge.state || "").toLowerCase();
  const bridgeBusy = snapshotBridgeBusy(snapshot);

  elements.personTarget.replaceChildren();
  if (persons.length) {
    for (const person of persons) {
      const suffix = person.selected ? " · selected in VaM" : "";
      elements.personTarget.append(
        new Option(`${person.uid}${suffix}`, person.uid),
      );
    }
    elements.personTarget.value = app.selectedPersonUid;
  } else {
    const label = snapshot.loading
      ? "Scene is loading…"
      : gameRunning
        ? "No Person atoms found"
        : "Start VaM to choose a Person";
    elements.personTarget.append(new Option(label, ""));
    elements.personTarget.value = "";
  }
  elements.personTarget.disabled = persons.length === 0 || Boolean(snapshot.loading);
  elements.selectPersonButton.disabled =
    app.personMutationInFlight ||
    !gameRunning ||
    !snapshot.available ||
    Boolean(snapshot.loading) ||
    bridgeBusy ||
    !canSelectPerson ||
    !app.selectedPersonUid;
  elements.selectPersonButton.title = !canSelectPerson
    ? "The loaded bridge does not support selecting a Person in VaM"
    : !app.selectedPersonUid
      ? "Choose a Person target first"
      : "";
  elements.addPersonButton.disabled =
    app.personMutationInFlight ||
    !gameRunning ||
    !snapshot.available ||
    Boolean(snapshot.loading) ||
    bridgeBusy ||
    !canAddPerson;
  elements.addPersonButton.title = !canAddPerson
    ? "The loaded bridge does not support adding a Person"
    : !gameRunning
      ? "Start VaM before adding a Person"
      : "";

  const state = elements.personLiveState;
  state.classList.remove("is-ready", "is-warning", "is-error");

  let title = "Checking the Person bridge…";
  let detail =
    `${category.label} browsing remains available while the live connection is checked.`;
  if (app.personError) {
    state.classList.add("is-error");
    title = "Live Person controls unavailable";
    detail = `${errorMessage(app.personError)} You can still browse this category.`;
  } else if (!gameRunning) {
    state.classList.add("is-warning");
    title = "VaM is closed";
    detail = `Browse ${category.label.toLowerCase()} now, then launch VaM to load one onto a Person.`;
  } else if (!snapshot.available) {
    state.classList.add("is-warning");
    title = "Waiting for the live Person bridge";
    detail =
      "VaM is running, but no fresh Person roster is available yet. Reload or update the bridge if this persists.";
  } else if (!category.liveAction) {
    state.classList.add("is-warning");
    title = "This category is browse-only";
    detail =
      "You can enable its package for VaM, but VAM-PIP will not guess a live Person change that the bridge does not expose.";
  } else if (!canApplyCategory) {
    state.classList.add("is-warning");
    title = "Bridge update required";
    detail =
      `This bridge does not advertise ${category.requiredCapability || "the required action"} yet. Browsing remains available.`;
  } else if (snapshot.loading) {
    state.classList.add("is-warning");
    title = "VaM is loading the scene";
    detail = "Apply controls will resume when the scene and its Person atoms are ready.";
  } else if (!persons.length) {
    state.classList.add("is-warning");
    title = "No Person atoms are available";
    detail = canAddPerson
      ? "Use Add Person above, then choose the new target."
      : "Add a Person inside VaM, then refresh this workspace.";
  } else if (bridgeBusy) {
    const progressTitles = {
      queued: "Asset change queued",
      "deferred-loading": "Waiting for scene loading",
      rescanning: "Enabling the asset package",
      applying: `Applying ${category.noun}`,
    };
    state.classList.add("is-warning");
    title = progressTitles[bridgeState] || "Bridge action in progress";
    detail =
      String(bridge.message || "").trim() ||
      "The bridge is processing the requested asset change inside VaM.";
  } else if (bridgeState === "error") {
    state.classList.add("is-error");
    title = "The bridge reports an error";
    detail =
      String(bridge.message || "").trim() ||
      "Choose the preset again, or reload the bridge if the error persists.";
  } else {
    state.classList.add("is-ready");
    title = `Ready for ${app.selectedPersonUid}`;
    detail =
      `Choose a ${category.noun} below. Hidden packages will be enabled for three days before VaM loads it.`;
  }

  elements.personLiveTitle.textContent = title;
  elements.personLiveDetail.textContent = detail;
}

function cuaChoiceUnavailableOption(label) {
  elements.cuaChoiceSelect.replaceChildren(new Option(label, ""));
  elements.cuaChoiceSelect.value = "";
}

function cuaChoiceLiveContextReason(category, snapshot = app.person || {}) {
  if (
    !category?.liveAction ||
    app.workspaceCategoriesSource !== "server" ||
    app.workspaceCategoriesError
  ) {
    return "This category is browse-only until the manager publishes its current workspace map";
  }
  if (app.personError) {
    return "Refresh the live VaM state before choosing a contained asset";
  }
  if (!personVamRunning(snapshot)) {
    return "Start VaM before choosing a contained asset";
  }
  if (!snapshot.available) {
    return "Wait for a fresh scene snapshot from the loaded bridge";
  }
  return "";
}

function updateCuaChoiceButton() {
  const category = currentWorkspaceCategory();
  const snapshot = app.person || {};
  const target = selectedCuaTarget(category);
  const state = cuaStateForAtom(target);
  const index = integerValue(elements.cuaChoiceSelect.value);
  const choice =
    index === null
      ? null
      : state?.choices.find((entry) => entry.index === index) || null;
  const bridgeBusy = snapshotBridgeBusy(snapshot);
  const capabilities = personCapabilities(snapshot);
  const liveContextReason = cuaChoiceLiveContextReason(category, snapshot);
  let reason = "";

  if (!isCuaCategory(category)) {
    reason = "Contained choices are available only for Custom Unity Assets";
  } else if (liveContextReason) {
    reason = liveContextReason;
  } else if (app.atomTargetMode === "create") {
    reason = "Load a bundle into the new target before choosing its contents";
  } else if (!target) {
    reason = "Choose an existing CustomUnityAsset target first";
  } else if (!state) {
    reason = "Load a Unity bundle into this target first";
  } else if (state.loadDll !== false) {
    reason =
      state.loadDll === true
        ? "Choice switching is disabled while DLL loading is enabled"
        : "The bridge has not confirmed that DLL loading is off";
  } else if (!capabilities.has("custom-unity-asset-choice")) {
    reason = "Update and reload the bridge to choose contained assets";
  } else if (!state.choiceToken) {
    reason = "Waiting for a fresh contained-asset token";
  } else if (!state.choices.length) {
    reason = "This bundle has not published any selectable scenes or prefabs";
  } else if (!choice) {
    reason = "Choose a contained scene or prefab";
  } else if (state.ready && state.selectedIndex === choice.index) {
    reason = "This contained item is already loaded";
  } else if (
    app.cuaChoiceInFlight ||
    app.atomMutationInFlight ||
    app.applyingWorkspaceResources.size > 0 ||
    Boolean(snapshot.loading) ||
    bridgeBusy
  ) {
    reason = "Wait for the current VaM bridge action to finish";
  }

  elements.cuaChoiceButton.disabled = reason !== "";
  elements.cuaChoiceButton.title = reason;
}

function renderCuaChoicePanel(category = currentWorkspaceCategory()) {
  const isCua = isCuaCategory(category);
  elements.cuaChoicePanel.hidden = !isCua;
  if (!isCua) return;

  const snapshot = app.person || {};
  const creating = app.atomTargetMode === "create";
  const target = selectedCuaTarget(category);
  const state = cuaStateForAtom(target);
  const bridgeBusy = snapshotBridgeBusy(snapshot);
  const capabilities = personCapabilities(snapshot);
  const canChoose = capabilities.has("custom-unity-asset-choice");
  const liveContextReason = cuaChoiceLiveContextReason(category, snapshot);
  const previousKey = elements.cuaChoicePanel.dataset.choiceKey || "";
  const previousValue = elements.cuaChoiceSelect.value;
  const currentKey = target && state
    ? `${target.uid}\n${state.choiceToken}`
    : "";

  elements.cuaChoicePanel.classList.remove(
    "is-ready",
    "is-warning",
    "is-danger",
  );
  elements.cuaDllState.classList.remove("is-safe", "is-danger", "is-muted");

  if (liveContextReason) {
    cuaChoiceUnavailableOption("Live choices unavailable");
    elements.cuaChoiceTitle.textContent = "Contained choices are read-only";
    elements.cuaChoiceDetail.textContent = liveContextReason;
    elements.cuaDllState.textContent = "Fresh DLL state required";
    elements.cuaDllState.classList.add("is-muted");
    elements.cuaChoicePanel.classList.add("is-warning");
  } else if (creating) {
    cuaChoiceUnavailableOption("Available after the target is created");
    elements.cuaChoiceTitle.textContent = "Contained choices appear after loading";
    elements.cuaChoiceDetail.textContent =
      "Load a bundle below. Single-item bundles load automatically; multi-item bundles stay at None until you choose a scene or prefab.";
    elements.cuaDllState.textContent = "DLL loading forced off on load";
    elements.cuaDllState.classList.add("is-safe");
    elements.cuaChoicePanel.classList.add("is-warning");
  } else if (!target) {
    cuaChoiceUnavailableOption("Choose an existing target first");
    elements.cuaChoiceTitle.textContent = "No CustomUnityAsset target selected";
    elements.cuaChoiceDetail.textContent =
      "Choose an existing compatible atom, or switch to Create new.";
    elements.cuaDllState.textContent = "DLL state unavailable";
    elements.cuaDllState.classList.add("is-muted");
    elements.cuaChoicePanel.classList.add("is-warning");
  } else if (!state) {
    cuaChoiceUnavailableOption("No contained choices available");
    elements.cuaChoiceTitle.textContent = "No Unity bundle loaded";
    elements.cuaChoiceDetail.textContent =
      "Choose a bundle below. VAM-PIP forces DLL loading off before assigning it to this target.";
    elements.cuaDllState.textContent = "DLL state unavailable";
    elements.cuaDllState.classList.add("is-muted");
    elements.cuaChoicePanel.classList.add("is-warning");
  } else {
    elements.cuaChoiceSelect.replaceChildren();
    elements.cuaChoiceSelect.append(
      new Option(
        state.choices.length
          ? "Choose a contained scene or prefab…"
          : "No selectable scenes or prefabs",
        "",
      ),
    );
    for (const choice of state.choices) {
      elements.cuaChoiceSelect.append(
        new Option(choice.label, String(choice.index)),
      );
    }
    const canPreserveSelection =
      previousKey === currentKey &&
      state.choices.some(
        (choice) => String(choice.index) === previousValue,
      );
    if (canPreserveSelection) {
      elements.cuaChoiceSelect.value = previousValue;
    } else if (
      state.selectedIndex !== null &&
      state.choices.some((choice) => choice.index === state.selectedIndex)
    ) {
      elements.cuaChoiceSelect.value = String(state.selectedIndex);
    } else {
      elements.cuaChoiceSelect.value = "";
    }

    const selectedChoice =
      state.selectedIndex === null
        ? null
        : state.choices.find(
            (choice) => choice.index === state.selectedIndex,
          ) || null;
    const countText = `${formatNumber(state.choiceCount)} ${plural(
      "choice",
      state.choiceCount,
    )}`;
    const truncatedNote = state.choicesTruncated
      ? ` Showing ${formatNumber(state.choices.length)} bounded choices in this browser.`
      : "";

    if (state.loadDll === false) {
      elements.cuaDllState.textContent = "DLL loading off";
      elements.cuaDllState.classList.add("is-safe");
    } else if (state.loadDll === true) {
      elements.cuaDllState.textContent = "DLL loading enabled";
      elements.cuaDllState.classList.add("is-danger");
    } else {
      elements.cuaDllState.textContent = "DLL state unavailable";
      elements.cuaDllState.classList.add("is-muted");
    }

    if (state.loadDll === true) {
      elements.cuaChoiceTitle.textContent = "DLL loading is enabled";
      elements.cuaChoiceDetail.textContent =
        "Contained switching is disabled. Reload the bundle through VAM-PIP to force DLL loading off; code already active in this VaM session cannot be unloaded.";
      elements.cuaChoicePanel.classList.add("is-danger");
    } else if (state.loadDll !== false) {
      elements.cuaChoiceTitle.textContent = "Waiting for a safe loader state";
      elements.cuaChoiceDetail.textContent =
        "Choices remain disabled until the bridge confirms that DLL loading is off.";
      elements.cuaChoicePanel.classList.add("is-warning");
    } else if (!canChoose) {
      elements.cuaChoiceTitle.textContent = "Bridge update required";
      elements.cuaChoiceDetail.textContent =
        "The bundle state is visible, but this bridge does not advertise custom-unity-asset-choice.";
      elements.cuaChoicePanel.classList.add("is-warning");
    } else if (!state.choices.length) {
      elements.cuaChoiceTitle.textContent = "Waiting for contained assets";
      elements.cuaChoiceDetail.textContent =
        `The loader reports ${countText}, but none are currently selectable.${truncatedNote}`;
      elements.cuaChoicePanel.classList.add("is-warning");
    } else if (state.ready && selectedChoice) {
      elements.cuaChoiceTitle.textContent = "Contained item loaded";
      elements.cuaChoiceDetail.textContent =
        `${selectedChoice.label} is active · ${countText}.${truncatedNote}`;
      elements.cuaChoicePanel.classList.add("is-ready");
    } else if (state.choiceCount === 1) {
      elements.cuaChoiceTitle.textContent = "Loading the bundle’s single item";
      elements.cuaChoiceDetail.textContent =
        `Single-item bundles are selected automatically.${truncatedNote}`;
      elements.cuaChoicePanel.classList.add("is-warning");
    } else {
      elements.cuaChoiceTitle.textContent = "Choose a contained item";
      elements.cuaChoiceDetail.textContent =
        `${countText} are available. Multi-item bundles stay at None until you choose one.${truncatedNote}`;
      elements.cuaChoicePanel.classList.add("is-ready");
    }
  }

  elements.cuaChoicePanel.dataset.choiceKey = currentKey;
  elements.cuaChoiceSelect.disabled =
    Boolean(liveContextReason) ||
    creating ||
    !target ||
    !state ||
    state.loadDll !== false ||
    !canChoose ||
    !state.choiceToken ||
    !state.choices.length ||
    app.cuaChoiceInFlight ||
    app.atomMutationInFlight ||
    app.applyingWorkspaceResources.size > 0 ||
    Boolean(snapshot.loading) ||
    bridgeBusy;
  updateCuaChoiceButton();
}

function renderAtomContext() {
  const category = currentWorkspaceCategory();
  const visible = category && ATOM_TARGET_KINDS.has(category.targetKind);
  elements.atomContext.hidden = !visible;
  if (!visible) return;

  const snapshot = app.person || {};
  const capabilities = personCapabilities(snapshot);
  const atoms = atomsForCategory(category);
  const managedTarget = categoryUsesManagedAtomTarget(category);
  const creationSupported = categorySupportsTargetCreation(category);
  const createCapability = categoryCreateCapability(category);
  const known = new Set(atoms.map((atom) => atom.uid));
  if (!known.has(app.selectedAtomUid)) {
    const selected = atoms.find((atom) => Boolean(atom.selected));
    app.selectedAtomUid = selected?.uid || atoms[0]?.uid || "";
  }
  if (!managedTarget) {
    app.atomTargetMode = "existing";
  } else if (!creationSupported && app.atomTargetMode === "create") {
    app.atomTargetMode = "existing";
  } else if (
    creationSupported &&
    !atoms.length &&
    app.atomTargetMode === "existing"
  ) {
    app.atomTargetMode = "create";
  }
  if (managedTarget && !app.newAtomUid) {
    app.newAtomUid = suggestedAtomUid(category);
  }

  elements.atomTarget.replaceChildren();
  if (atoms.length) {
    for (const atom of atoms) {
      const type = atom.type ? ` · ${atom.type}` : "";
      const selected = atom.selected ? " · selected in VaM" : "";
      elements.atomTarget.append(
        new Option(`${atom.uid}${type}${selected}`, atom.uid),
      );
    }
    elements.atomTarget.value = app.selectedAtomUid;
  } else {
    const label = snapshot.loading
      ? "Scene is loading…"
      : personVamRunning(snapshot)
        ? "No compatible atoms found"
        : "Start VaM to inspect atoms";
    elements.atomTarget.append(new Option(label, ""));
  }
  const bridgeBusy = snapshotBridgeBusy(snapshot);
  const canSelect = capabilities.has("atom-select");
  const canApply =
    !category.requiredCapability ||
    capabilities.has(category.requiredCapability);
  const canAddAtom =
    categoryUsesManagedAtomTarget(category) &&
    creationSupported &&
    (!createCapability || capabilities.has(createCapability));
  const creating = managedTarget && app.atomTargetMode === "create";
  syncWorkspaceApplyModeControls(category);
  const newUid = app.newAtomUid.trim();
  const newUidValid = atomUidIsValid(newUid);
  const uidAlreadyExists = atomList(snapshot).some(
    (atom) => atom.uid.toLowerCase() === newUid.toLowerCase(),
  );
  const targetControlsBusy =
    app.atomMutationInFlight ||
    app.cuaChoiceInFlight ||
    Boolean(snapshot.loading) ||
    bridgeBusy ||
    app.applyingWorkspaceResources.size > 0;

  elements.atomTarget.disabled = !atoms.length || targetControlsBusy;
  elements.atomTargetMode.hidden = !managedTarget;
  elements.atomModeExisting.disabled = !atoms.length || targetControlsBusy;
  elements.atomModeExisting.checked = !creating;
  elements.atomModeCreate.disabled = !creationSupported || targetControlsBusy;
  elements.atomModeCreate.checked = creating;
  elements.atomExistingControls.hidden = creating;
  elements.atomCreateControls.hidden = !creating;
  if (elements.atomNewUid.value !== app.newAtomUid) {
    elements.atomNewUid.value = app.newAtomUid;
  }
  elements.atomNewUid.disabled =
    targetControlsBusy ||
    !creationSupported ||
    !personVamRunning(snapshot) ||
    !snapshot.available;

  elements.selectAtomButton.disabled =
    app.atomMutationInFlight ||
    app.cuaChoiceInFlight ||
    !personVamRunning(snapshot) ||
    !snapshot.available ||
    Boolean(snapshot.loading) ||
    bridgeBusy ||
    !canSelect ||
    !app.selectedAtomUid;
  elements.selectAtomButton.title = !canSelect
    ? "The loaded bridge does not support selecting atoms in VaM"
    : !app.selectedAtomUid
      ? "Choose a compatible atom first"
      : "";
  elements.addAtomButton.hidden = !categoryUsesManagedAtomTarget(category);
  if (elements.addAtomButton.getAttribute("aria-busy") !== "true") {
    elements.addAtomButton.textContent = category.targetAtomType
      ? `Add ${category.targetAtomType}`
      : "Add atom now";
  }
  elements.addAtomButton.disabled =
    app.atomMutationInFlight ||
    app.cuaChoiceInFlight ||
    !personVamRunning(snapshot) ||
    !snapshot.available ||
    Boolean(snapshot.loading) ||
    bridgeBusy ||
    !canAddAtom ||
    !newUidValid ||
    uidAlreadyExists;
  elements.addAtomButton.title =
    createCapability && !capabilities.has(createCapability)
      ? "The loaded bridge does not support adding this atom type"
      : !newUidValid
        ? "Enter a printable UID between 1 and 200 characters"
        : uidAlreadyExists
          ? "An atom already uses this UID"
          : "";

  renderCuaChoicePanel(category);

  const state = elements.atomLiveState;
  state.classList.remove("is-ready", "is-warning", "is-error");
  let title = "Checking the scene bridge…";
  let detail = "Catalogue browsing remains available while VaM is checked.";
  if (app.personError) {
    state.classList.add("is-error");
    title = "Live atom controls unavailable";
    detail = errorMessage(app.personError);
  } else if (!personVamRunning(snapshot)) {
    state.classList.add("is-warning");
    title = "VaM is closed";
    detail = "Start VaM to inspect and select scene atoms.";
  } else if (!snapshot.available) {
    state.classList.add("is-warning");
    title = "Waiting for the live scene bridge";
    detail = "VaM is running, but its atom roster is not fresh yet.";
  } else if (snapshot.loading || bridgeBusy) {
    state.classList.add("is-warning");
    title = snapshot.loading ? "VaM is loading the scene" : "Bridge action in progress";
    detail = String(snapshot.bridge?.message || "Atom selection will resume shortly.");
  } else if (!category.liveAction) {
    state.classList.add("is-warning");
    title = "This category is browse-only";
    detail =
      "The atom roster can help you inspect the scene, but this manager does not expose a live load for the category.";
  } else if (!canApply) {
    state.classList.add("is-warning");
    title = "Bridge update required";
    detail = `This bridge does not advertise ${category.requiredCapability}.`;
  } else if (creating && !newUidValid) {
    state.classList.add("is-warning");
    title = "Choose a new atom UID";
    detail = "The UID must contain 1 to 200 printable characters.";
  } else if (
    creating &&
    createCapability &&
    !capabilities.has(createCapability)
  ) {
    state.classList.add("is-warning");
    title = "This bridge cannot create the target";
    detail =
      `Switch to an existing compatible atom, or update the bridge for ${createCapability} support.`;
  } else if (creating && uidAlreadyExists) {
    state.classList.add("is-warning");
    title = "That UID already exists";
    detail = "Switch to Existing or choose another UID.";
  } else if (!creating && !atoms.length) {
    state.classList.add("is-warning");
    title = "No compatible target atoms";
    detail = creationSupported
      ? "Choose Create new to make the required target while loading."
      : managedTarget
        ? "This category can only load into an existing compatible atom."
        : `The current scene has no target matching ${category.label}.`;
  } else {
    state.classList.add("is-ready");
    title = creating
      ? `Ready to create ${newUid}`
      : `Ready for ${app.selectedAtomUid}`;
    detail = creating
      ? category.operation === "load-subscene"
        ? "Loading a SubScene below will create this SubScene atom and fill it."
        : category.operation === "load-custom-unity-asset"
          ? "Loading a bundle below will create this CustomUnityAsset atom with DLL loading forced off."
          : "Load a preset below to create the typed atom and apply it, or add the empty atom now."
      : category.operation === "load-custom-unity-asset"
        ? "Choose a bundle below. Multi-item bundles expose a separate contained-asset picker."
      : canSelect
        ? "Choose an asset below to load it onto this target, or select it in VaM."
        : "Choose an asset below to load it onto this target.";
  }
  elements.atomLiveTitle.textContent = title;
  elements.atomLiveDetail.textContent = detail;
}

async function selectCuaChoiceInVam() {
  const category = currentWorkspaceCategory();
  const snapshot = app.person || {};
  const target = selectedCuaTarget(category);
  const state = cuaStateForAtom(target);
  const liveContextReason = cuaChoiceLiveContextReason(category, snapshot);
  const choiceIndex = integerValue(elements.cuaChoiceSelect.value);
  const choice =
    choiceIndex === null
      ? null
      : state?.choices.find((entry) => entry.index === choiceIndex) || null;

  updateCuaChoiceButton();
  if (
    liveContextReason ||
    elements.cuaChoiceButton.disabled ||
    !target ||
    !state ||
    !choice ||
    !state.choiceToken
  ) {
    return;
  }

  app.cuaChoiceInFlight = true;
  setButtonBusy(elements.cuaChoiceButton, true, "Queuing…");
  renderAtomContext();
  try {
    const result = await api("/api/vam/custom-unity-asset/choice", {
      method: "POST",
      body: {
        target_uid: target.uid,
        choice_index: choice.index,
        choice_token: state.choiceToken,
      },
    });
    requireBridgeQueue(result, "Contained Unity asset selection");
    toast(
      "Contained asset queued",
      result.message ||
        `${choice.label} will be loaded into ${target.uid} with DLL loading kept off.`,
    );
    app.personPollAt = 0;
    await loadPersons({ quiet: true });
  } catch (error) {
    toast(
      "Could not load contained asset",
      errorMessage(error),
      "error",
    );
  } finally {
    app.cuaChoiceInFlight = false;
    setButtonBusy(elements.cuaChoiceButton, false);
    renderAtomContext();
  }
}

async function selectPersonInVam() {
  const targetUid = app.selectedPersonUid;
  if (!targetUid || app.personMutationInFlight) return;
  app.personMutationInFlight = true;
  setButtonBusy(elements.selectPersonButton, true, "Selecting…");
  renderPersonContext();
  try {
    const result = await api("/api/vam/person/select", {
      method: "POST",
      body: { target_uid: targetUid },
    });
    requireBridgeQueue(result, "Person selection");
    toast(
      "Person selected in VaM",
      result.message || `${targetUid} is now the active target.`,
    );
    await loadPersons({ quiet: true });
  } catch (error) {
    toast("Could not select Person", errorMessage(error), "error");
  } finally {
    app.personMutationInFlight = false;
    setButtonBusy(elements.selectPersonButton, false);
    renderPersonContext();
  }
}

async function selectAtomInVam() {
  const targetUid = app.selectedAtomUid;
  if (!targetUid || app.atomMutationInFlight || app.cuaChoiceInFlight) return;
  app.atomMutationInFlight = true;
  setButtonBusy(elements.selectAtomButton, true, "Selecting…");
  renderAtomContext();
  try {
    const result = await api("/api/vam/atom/select", {
      method: "POST",
      body: { target_uid: targetUid },
    });
    requireBridgeQueue(result, "Atom selection");
    toast(
      "Atom selected in VaM",
      result.message || `${targetUid} is now the active atom.`,
    );
    await loadPersons({ quiet: true });
  } catch (error) {
    toast("Could not select atom", errorMessage(error), "error");
  } finally {
    app.atomMutationInFlight = false;
    setButtonBusy(elements.selectAtomButton, false);
    renderAtomContext();
  }
}

async function addAtomInVam() {
  const category = currentWorkspaceCategory();
  const targetUid = app.newAtomUid.trim();
  const createCapability = categoryCreateCapability(category);
  if (
    !category ||
    !categoryUsesManagedAtomTarget(category) ||
    !categorySupportsTargetCreation(category) ||
    !atomUidIsValid(targetUid) ||
    atomList().some(
      (atom) => atom.uid.toLowerCase() === targetUid.toLowerCase(),
    ) ||
    (createCapability &&
      !personCapabilities().has(createCapability)) ||
    app.atomMutationInFlight ||
    app.cuaChoiceInFlight
  ) {
    return;
  }
  const confirmed = await showDialog({
    eyebrow: "Add typed atom",
    title: `Add “${targetUid}”?`,
    message: `VaM will add a ${category.targetAtomType || "compatible"} atom to the current scene. The atom remains empty until you load a preset or configure it.`,
    confirmLabel: "Add atom",
    icon: "warning",
  });
  if (!confirmed) return;

  app.atomMutationInFlight = true;
  renderAtomContext();
  setButtonBusy(elements.addAtomButton, true, "Adding…");
  try {
    const result = await api("/api/vam/atom/add", {
      method: "POST",
      body: {
        category_id: category.id,
        target_uid: targetUid,
      },
    });
    requireBridgeQueue(result, "Add atom");
    app.pendingAtomUid = String(result.target_uid || result.uid || targetUid);
    toast(
      "Atom queued",
      result.message ||
        `${app.pendingAtomUid} will be added as ${category.targetAtomType || "the category’s atom type"}.`,
    );
    await loadPersons({ quiet: true });
  } catch (error) {
    toast("Could not add atom", errorMessage(error), "error");
  } finally {
    app.atomMutationInFlight = false;
    setButtonBusy(elements.addAtomButton, false);
    renderAtomContext();
  }
}

function suggestedPersonUid() {
  const used = new Set(personList().map((person) => person.uid.toLowerCase()));
  if (!used.has("person")) return "Person";
  let suffix = 2;
  while (used.has(`person${suffix}`)) suffix += 1;
  return `Person${suffix}`;
}

async function addPersonInVam() {
  if (app.personMutationInFlight) return;
  const targetUid = await showDialog({
    eyebrow: "Add Person atom",
    title: "Choose a unique Person name",
    message:
      "VaM will add a new Person atom to the current scene. This is not saved until you save the scene.",
    confirmLabel: "Add Person",
    icon: "warning",
    input: {
      label: "Person UID",
      value: suggestedPersonUid(),
      placeholder: "Person2",
    },
  });
  if (!targetUid) return;

  app.personMutationInFlight = true;
  setButtonBusy(elements.addPersonButton, true, "Adding…");
  renderPersonContext();
  try {
    const result = await api("/api/vam/person/add", {
      method: "POST",
      body: { target_uid: targetUid },
    });
    requireBridgeQueue(result, "Add Person");
    app.selectedPersonUid = String(
      result.target_uid || result.uid || targetUid,
    );
    toast(
      "Person queued",
      result.message || `${app.selectedPersonUid} will be added to the scene.`,
    );
    await loadPersons({ quiet: true });
  } catch (error) {
    toast("Could not add Person", errorMessage(error), "error");
  } finally {
    app.personMutationInFlight = false;
    setButtonBusy(elements.addPersonButton, false);
    renderPersonContext();
  }
}

async function loadStatus() {
  if (operationIsBusy()) {
    await loadActivity({ refreshOnTerminal: false });
    return;
  }
  app.status = await api("/api/status");
  renderStatus();
  renderAccess();
  setConnection("online", "Local manager");
}

async function loadLibrary({ append = false } = {}) {
  if (app.view === "access") return;

  if (app.requestController) {
    app.requestController.abort();
  }
  const controller = new AbortController();
  app.requestController = controller;
  app.loading = true;

  const offset = append ? app.items.length : 0;
  if (!append) {
    app.items = [];
    app.offset = 0;
    showLoadingState();
  } else {
    elements.loadMore.disabled = true;
    elements.loadMore.textContent = "Loading…";
  }

  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (app.query) params.set("q", app.query);
  if (app.packageState) params.set("state", app.packageState);
  if (app.view === "resources" && app.type) params.set("type", app.type);
  if (app.view === "workspace") {
    const category = currentWorkspaceCategory();
    if (category) {
      if (app.workspaceCategoriesSource === "server") {
        params.set("category", category.id);
      } else {
        for (const resourceType of category.resourceTypes) {
          params.append("type", resourceType);
        }
      }
    }
  }

  try {
    const endpoint =
      app.view === "packages" ? "/api/packages" : "/api/resources";
    const result = await api(`${endpoint}?${params.toString()}`, {
      signal: controller.signal,
    });
    const incoming = Array.isArray(result) ? result : result.items || [];
    app.items = append ? app.items.concat(incoming) : incoming;
    app.total = numberOr(result.total, app.items.length);
    app.offset = offset;
    renderLibrary();
  } catch (error) {
    if (error.name !== "AbortError") {
      showErrorState(error);
    }
  } finally {
    if (app.requestController === controller) {
      app.loading = false;
      app.requestController = null;
      elements.loadMore.disabled = false;
      elements.loadMore.textContent = "Load more";
    }
  }
}

function renderStatus() {
  const status = app.status || {};
  const packages = status.packages || {};
  const managed = Boolean(status.managed_mode);
  const pins = asArray(status.pins);
  const leases = asArray(status.leases);
  const pending = numberOr(status.pending_disable, 0);
  const pendingEnable = numberOr(status.pending_enable, 0);
  const pendingTotal = pending + pendingEnable;

  elements.managerCard.classList.toggle("is-managed", managed);
  elements.modeTitle.textContent = managed ? "Managed mode" : "Original package set";
  elements.modeDescription.textContent = managed
    ? "Pins and active leases control which packages VaM can see."
    : "Your existing package visibility is unchanged.";
  elements.activateButton.hidden = managed;
  elements.reconcileButton.hidden = !managed || pendingTotal < 1;
  elements.reconcileButton.disabled = operationIsBusy();
  elements.reconcileButton.textContent =
    pendingTotal > 0
      ? `Apply ${formatNumber(pendingTotal)} pending`
      : "Apply pending changes";

  elements.activeCount.textContent = formatNumber(packages.active);
  elements.hiddenCount.textContent = formatNumber(packages.hidden);
  elements.resourceCount.textContent = formatNumber(status.catalog_resources);
  elements.leaseCount.textContent = formatNumber(
    leases.filter((lease) => !lease.expired).length,
  );

  elements.resourcesTabCount.textContent = formatCompact(status.catalog_resources);
  elements.packagesTabCount.textContent = formatCompact(packages.total);
  elements.accessTabCount.textContent = formatCompact(pins.length + leases.length);

  elements.addonPath.textContent = status.addon_dir || "—";
  elements.statePath.textContent = status.state_dir || "—";
  elements.autoReconcile.checked =
    status.auto_reconcile === undefined ? true : Boolean(status.auto_reconcile);
  renderLiveState(status);
}

function renderLiveState(status = app.status || {}) {
  const managed = Boolean(status.managed_mode);
  const liveVam =
    app.activity && app.activity.vam
      ? app.activity.vam
      : status.vam || {};
  const gameRunning = Boolean(liveVam.running);
  const operation =
    app.activity && app.activity.operation
      ? app.activity.operation
      : {};
  const operationStatus = String(operation.status || "").toLowerCase();
  const busy = operationIsBusy();
  const pending = numberOr(status.pending_disable, 0);

  elements.gameStatus.classList.toggle("is-running", gameRunning);
  elements.gameStatus.replaceChildren();
  elements.gameStatus.append(createElement("span", "status-dot"));
  elements.gameStatus.append(
    document.createTextNode(gameRunning ? "VaM running" : "VaM closed"),
  );

  const bridge = status.bridge;
  if (busy && !gameRunning) {
    elements.bridgeStatus.textContent =
      "VaM is closed. VAM-PIP is updating package visibility.";
  } else if (!gameRunning) {
    elements.bridgeStatus.textContent = bridge
      ? `Bridge ${bridge.state || "ready"} · waiting for VaM`
      : "The live-rescan bridge will connect when VaM starts.";
  } else if (bridge) {
    elements.bridgeStatus.textContent =
      bridge.message || `Live-rescan bridge: ${bridge.state || "connected"}.`;
  } else {
    elements.bridgeStatus.textContent =
      "VaM is open, but the live-rescan bridge has not reported yet.";
  }

  const launchBusy = elements.launchVamButton.hasAttribute("aria-busy");
  elements.launchVamButton.disabled = gameRunning || busy || launchBusy;
  elements.launchVamButton.title = gameRunning
    ? "VaM is already running"
    : busy
      ? "Wait for the package update to finish"
      : "";
  if (!launchBusy) {
    elements.launchVamLabel.textContent = busy
      ? "Updating packages…"
      : gameRunning
        ? "VaM is running"
        : "Launch VaM";
  }

  if (busy) {
    const total = numberOr(operation.total, 0);
    const completed = Math.min(numberOr(operation.completed, 0), total || Infinity);
    const enableTotal = numberOr(operation.enable_total, 0);
    const disableTotal = numberOr(operation.disable_total, 0);
    const enabled = Math.min(
      numberOr(operation.enabled, Math.min(completed, enableTotal)),
      enableTotal,
    );
    const disabled = Math.min(
      numberOr(
        operation.disabled,
        Math.max(0, completed - enableTotal),
      ),
      disableTotal,
    );

    elements.pendingNotice.hidden = false;
    if (operationStatus === "rolling-back") {
      elements.pendingTitle.textContent =
        `Restoring ${formatNumber(completed)} of ${formatNumber(total)} package changes…`;
      elements.pendingProgress.max = Math.max(total, 1);
      elements.pendingProgress.value = completed;
    } else if (enableTotal > enabled) {
      elements.pendingTitle.textContent =
        `Enabling ${formatNumber(enabled)} of ${formatNumber(enableTotal)} packages…`;
      elements.pendingProgress.max = Math.max(enableTotal, 1);
      elements.pendingProgress.value = enabled;
    } else if (disableTotal > 0) {
      elements.pendingTitle.textContent =
        `Hiding ${formatNumber(disabled)} of ${formatNumber(disableTotal)} packages…`;
      elements.pendingProgress.max = Math.max(disableTotal, 1);
      elements.pendingProgress.value = disabled;
    } else if (total > 0) {
      elements.pendingTitle.textContent =
        `Updating ${formatNumber(completed)} of ${formatNumber(total)} packages…`;
      elements.pendingProgress.max = Math.max(total, 1);
      elements.pendingProgress.value = completed;
    } else {
      elements.pendingTitle.textContent = "Preparing package changes…";
      elements.pendingProgress.max = 1;
      elements.pendingProgress.value = 0;
    }
    elements.pendingProgress.hidden = false;
    const unsafeLiveDisable =
      gameRunning &&
      disableTotal > 0 &&
      ["preparing", "applying", "finalizing"].includes(operationStatus);
    elements.pendingMessage.textContent = unsafeLiveDisable
      ? "VaM started while packages are being hidden. Close VaM now and let VAM-PIP finish safely."
      : gameRunning
        ? "VaM remains open; VAM-PIP is only making live-safe package changes."
        : "VaM is closed. Keep it closed until this package update finishes.";
    elements.pendingAction.hidden = true;
  } else if (pending > 0) {
    elements.pendingNotice.hidden = false;
    elements.pendingProgress.hidden = true;
    elements.pendingAction.hidden = false;
    elements.pendingTitle.textContent = `${formatNumber(pending)} package${
      pending === 1 ? "" : "s"
    } waiting to be hidden`;
    if (gameRunning) {
      elements.pendingMessage.textContent =
        "They remain available until VaM closes, so the current scene cannot break.";
      elements.pendingAction.textContent = "VaM is running";
      elements.pendingAction.disabled = true;
    } else {
      elements.pendingMessage.textContent =
        "VaM is closed. It is safe to apply the pending visibility changes.";
      elements.pendingAction.textContent = "Apply now";
      elements.pendingAction.disabled = false;
    }
  } else {
    elements.pendingNotice.hidden = true;
    elements.pendingProgress.hidden = true;
    elements.pendingAction.hidden = false;
  }

  elements.reconcileButton.disabled = busy;
  elements.deactivateButton.disabled = !managed || gameRunning || busy;
  elements.deactivateButton.title =
    managed && gameRunning
      ? "Close VaM before restoring the original set"
      : busy
        ? "Wait for the package update to finish"
        : "";
  if (app.view === "workspace") {
    renderPersonContext();
    renderAtomContext();
  }
}

function renderFacets() {
  const previous = elements.typeFilter.value;
  const typeValues = normalizeFacetTypes(app.facets);

  elements.typeFilter.replaceChildren();
  elements.typeFilter.append(new Option("All types", ""));
  for (const facet of typeValues) {
    const label = facet.count === null
      ? prettyType(facet.value)
      : `${prettyType(facet.value)} (${formatNumber(facet.count)})`;
    elements.typeFilter.append(new Option(label, facet.value));
  }

  const stillExists = Array.from(elements.typeFilter.options).some(
    (option) => option.value === previous,
  );
  elements.typeFilter.value = stillExists ? previous : "";
  app.type = elements.typeFilter.value;
}

function normalizeFacetTypes(facets) {
  if (!facets) return [];
  let values =
    facets.types ||
    facets.resource_types ||
    facets.type ||
    (facets.facets && (facets.facets.types || facets.facets.resource_types)) ||
    [];
  if (!Array.isArray(values) && typeof values === "object") {
    values = Object.entries(values).map(([value, count]) => ({ value, count }));
  }
  return asArray(values)
    .map((entry) => {
      if (typeof entry === "string") return { value: entry, count: null };
      return {
        value: String(entry.value ?? entry.name ?? entry.type ?? ""),
        count: entry.count === undefined ? null : numberOr(entry.count, 0),
      };
    })
    .filter((entry) => entry.value)
    .sort((a, b) => a.value.localeCompare(b.value, undefined, { sensitivity: "base" }));
}

function renderLibrary() {
  elements.loadingState.hidden = true;
  elements.cardGrid.replaceChildren();
  elements.cardGrid.hidden = app.items.length === 0;
  elements.emptyState.hidden = app.items.length !== 0;

  if (app.items.length === 0) {
    renderEmptyLibrary();
  } else {
    const fragment = document.createDocumentFragment();
    for (const item of app.items) {
      fragment.append(
        app.view === "packages" ? createPackageCard(item) : createResourceCard(item),
      );
    }
    elements.cardGrid.append(fragment);
  }

  const noun =
    app.view === "workspace"
      ? currentWorkspaceCategory()?.noun || "asset"
      : app.view === "resources"
        ? "resource"
        : "package";
  const shown = app.items.length;
  elements.resultCount.textContent =
    app.total === shown
      ? `${formatNumber(app.total)} ${plural(noun, app.total)}`
      : `Showing ${formatNumber(shown)} of ${formatNumber(app.total)} ${plural(
          noun,
          app.total,
        )}`;
  elements.loadMore.hidden = shown >= app.total || shown === 0;
  updateClearFilters();
}

function showLoadingState() {
  elements.loadingState.hidden = false;
  elements.loadingState.setAttribute("aria-busy", "true");
  elements.cardGrid.hidden = true;
  elements.emptyState.hidden = true;
  elements.loadMore.hidden = true;
  elements.resultCount.textContent =
    app.view === "workspace"
      ? `Loading ${currentWorkspaceCategory()?.label.toLowerCase() || "assets"}…`
      : app.view === "resources"
        ? "Loading resources…"
        : "Loading packages…";
}

function showErrorState(error) {
  elements.loadingState.hidden = true;
  elements.cardGrid.hidden = true;
  elements.emptyState.hidden = false;
  elements.emptyTitle.textContent = "The local manager did not respond";
  elements.emptyMessage.textContent = errorMessage(error);
  elements.emptyAction.textContent = "Try again";
  elements.emptyAction.dataset.action = "retry";
  elements.resultCount.textContent = "Could not load library";
  elements.loadMore.hidden = true;
}

function renderEmptyLibrary() {
  const noCatalogue =
    (app.view === "resources" || app.view === "workspace") &&
    numberOr(app.status && app.status.catalog_resources, 0) === 0 &&
    !hasFilters();

  if (noCatalogue) {
    elements.emptyTitle.textContent = "Import your resource catalogue";
    elements.emptyMessage.textContent =
      "VAM-PIP can browse BrowserAssist’s index while the containing VARs remain hidden.";
    elements.emptyAction.textContent = "Import catalogue";
    elements.emptyAction.dataset.action = "import";
  } else {
    elements.emptyTitle.textContent = "Nothing found";
    elements.emptyMessage.textContent = hasFilters()
      ? app.view === "workspace"
        ? "Try another name, creator, tag, or package state."
        : "Try another search, type, or package state."
      : app.view === "workspace"
        ? `No indexed ${currentWorkspaceCategory()?.label.toLowerCase() || "assets"} are available yet.`
        : `No ${app.view} are available yet.`;
    elements.emptyAction.textContent = hasFilters() ? "Clear filters" : "Refresh";
    elements.emptyAction.dataset.action = hasFilters() ? "clear" : "retry";
  }
}

function createResourceCard(item) {
  const card = createElement("article", "library-card resource-card");
  const title = resourceTitle(item);
  const root = packageRoot(item);
  const active = itemIsActive(item);
  const state = String(item.state || (active ? "active" : "hidden")).toLowerCase();
  const pinned = isPinned(root);

  const preview = createElement("div", "card-preview");
  const fallback = createElement("span", "preview-fallback");
  fallback.setAttribute("aria-hidden", "true");
  fallback.textContent = initials(title);
  preview.append(fallback);

  const thumbnail =
    item.thumbnail_url || item.thumbnail || item.thumb_url || item.preview_url || "";
  if (thumbnail) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("load", () => image.classList.add("is-loaded"));
    image.addEventListener("error", () => image.remove());
    image.src = String(thumbnail);
    preview.append(image);
  }

  const badges = createElement("div", "card-badges");
  badges.append(badge(prettyType(resourceType(item)), "type-badge"));
  const stateLabel = {
    active: "Active",
    hidden: "Available",
    missing: "Missing",
    local: "Local",
  }[state] || (active ? "Active" : "Available");
  badges.append(
    badge(
      stateLabel,
      `state-badge ${state === "active" || state === "local" ? "is-active" : "is-hidden"}`,
    ),
  );
  preview.append(badges);

  const body = createElement("div", "card-body");
  const heading = createElement("h3", "card-title");
  heading.textContent = title;
  heading.title = title;
  body.append(heading);

  const subtitle = createElement("p", "card-subtitle");
  const creator = item.creator || creatorFromRoot(root) || "Unknown creator";
  const creatorSpan = createElement("span", "creator");
  creatorSpan.textContent = String(creator);
  subtitle.append(creatorSpan);
  if (root) {
    subtitle.append(document.createTextNode(` · ${root}`));
  }
  body.append(subtitle);

  const metadata = createElement("div", "card-meta");
  const tags = normalizeTags(item.tags || item.tags_json);
  const atomType = item.atom_type || item.atomType;
  if (atomType) metadata.append(badge(String(atomType), "meta-pill"));
  for (const tag of tags.slice(0, atomType ? 2 : 3)) {
    metadata.append(badge(tag, "meta-pill"));
  }
  if (!metadata.children.length && (item.resource_path || item.path)) {
    metadata.append(badge(fileExtension(item.resource_path || item.path), "meta-pill"));
  }
  body.append(metadata);

  const actions = createElement("div", "card-actions");
  const workspaceCategory =
    app.view === "workspace" ? currentWorkspaceCategory() : null;
  if (workspaceCategory && workspaceCategory.liveAction) {
    const availability = workspaceApplyAvailability(item, workspaceCategory);
    const applyButton = button(
      availability.label,
      active || state === "local" ? "secondary-button" : "primary-button",
    );
    applyButton.disabled = !availability.allowed;
    applyButton.title = availability.reason;
    applyButton.addEventListener("click", () =>
      applyWorkspaceResource(item, workspaceCategory, applyButton),
    );
    actions.append(applyButton);
    body.append(actions);
    card.append(preview, body);
    return card;
  }

  const leaseButton = button(
    active ? "Keep for 3 days" : "Enable for 3 days",
    active ? "secondary-button" : "primary-button",
  );
  const isLocal = state === "local";
  const isMissing = state === "missing";
  if (isLocal) leaseButton.textContent = "Local · Always available";
  if (isMissing) leaseButton.textContent = "Package not installed";
  leaseButton.disabled =
    isLocal || isMissing || (!item.id && !root) || !itemIsValid(item);
  if (isLocal) {
    leaseButton.title = "Loose resources are always available";
  } else if (isMissing) {
    leaseButton.title = "The VAR containing this resource is not installed";
  } else if (root) {
    leaseButton.title = `Temporarily enable ${root} and its dependencies`;
  } else {
    leaseButton.title = "Resolve the resource’s package references";
  }
  leaseButton.addEventListener("click", () =>
    createThreeDayLease(root, title, leaseButton, item.id),
  );
  actions.append(leaseButton);

  const pinButton = button("", `secondary-button pin-button${pinned ? " is-pinned" : ""}`);
  pinButton.type = "button";
  pinButton.disabled = isMissing || !root || !itemIsValid(item);
  pinButton.setAttribute(
    "aria-label",
    pinned ? `Unpin ${root}` : `Always keep ${root} available`,
  );
  pinButton.title = pinned ? "Remove persistent pin" : "Always keep available";
  pinButton.append(pinIcon(pinned));
  pinButton.addEventListener("click", () =>
    pinned ? removePin(root, pinButton) : addPin(root, title, pinButton),
  );
  actions.append(pinButton);
  body.append(actions);

  card.append(preview, body);
  return card;
}

function workspaceApplyAvailability(item, category = currentWorkspaceCategory()) {
  const snapshot = app.person || {};
  const persons = personList(snapshot);
  const selected = app.selectedPersonUid;
  const state = String(
    item.state || (itemIsActive(item) ? "active" : "hidden"),
  ).toLowerCase();
  const resourceId = Number(item.id);
  const gameRunning = personVamRunning(snapshot);
  const key = `${category?.id || "asset"}:${resourceId}`;
  const managedAtomTarget = categoryUsesManagedAtomTarget(category);
  const creatingAtomTarget =
    managedAtomTarget && app.atomTargetMode === "create";
  const creationSupported = categorySupportsTargetCreation(category);
  const createCapability = categoryCreateCapability(category);
  const capabilities = personCapabilities(snapshot);
  const atomTargetUid = activeAtomTargetUid(category);
  const compatibleAtoms = atomsForCategory(category);
  const atomTargetExists = compatibleAtoms.some(
    (atom) => atom.uid === atomTargetUid,
  );
  const anyUidCollision = atomList(snapshot).some(
    (atom) => atom.uid.toLowerCase() === atomTargetUid.toLowerCase(),
  );
  let reason = "";

  if (state === "missing") {
    reason = "The package containing this asset is not installed";
  } else if (!itemIsValid(item) || !Number.isInteger(resourceId) || resourceId < 1) {
    reason = "This catalogue entry cannot be resolved safely";
  } else if (!category || !category.liveAction) {
    reason = "This category is browse-only with the current manager";
  } else if (app.personError) {
    reason = "The live VaM bridge is unavailable";
  } else if (!gameRunning) {
    reason = "Start VaM before loading this asset";
  } else if (!snapshot.available) {
    reason = "The bridge is not publishing a fresh scene snapshot";
  } else if (
    category.requiredCapability &&
    !capabilities.has(category.requiredCapability)
  ) {
    reason = `Update and reload the bridge to enable ${category.requiredCapability}`;
  } else if (snapshot.loading) {
    reason = "Wait for VaM to finish loading the scene";
  } else if (snapshotBridgeBusy(snapshot)) {
    reason = "Wait for the current bridge action to finish";
  } else if (app.atomMutationInFlight || app.cuaChoiceInFlight) {
    reason = "Wait for the current atom action to finish";
  } else if (
    (category.targetKind === "person" &&
      (!selected || !persons.some((person) => person.uid === selected)))
  ) {
    reason = "Choose an available Person target first";
  } else if (managedAtomTarget && !atomTargetUid) {
    reason = creatingAtomTarget
      ? "Enter a new target UID first"
      : "Choose a compatible target atom first";
  } else if (
    managedAtomTarget &&
    creatingAtomTarget &&
    !atomUidIsValid(atomTargetUid)
  ) {
    reason = "Enter a printable UID between 1 and 200 characters";
  } else if (managedAtomTarget && creatingAtomTarget && !creationSupported) {
    reason = "This category can only use an existing compatible target";
  } else if (managedAtomTarget && !creatingAtomTarget && !atomTargetExists) {
    reason = "Choose an available compatible target atom";
  } else if (managedAtomTarget && creatingAtomTarget && anyUidCollision) {
    reason = "Another atom already uses this UID";
  } else if (
    managedAtomTarget &&
    creatingAtomTarget &&
    createCapability &&
    !capabilities.has(createCapability)
  ) {
    reason = `Update the bridge for ${createCapability} support, or use an existing target`;
  } else if (app.applyingWorkspaceResources.has(key)) {
    reason = "This asset is already being queued";
  }

  let label = "Load";
  if (state === "missing") {
    label = "Package not installed";
  } else if (category?.operation === "load-scene") {
    label = app.workspaceApplyMode === "merge" ? "Merge scene" : "Replace scene";
  } else if (category?.operation === "load-subscene") {
    label = creatingAtomTarget ? "Create & load SubScene" : "Load SubScene";
  } else if (category?.operation === "load-custom-unity-asset") {
    label = creatingAtomTarget
      ? "Create & load Unity asset"
      : "Load Unity asset";
  } else if (category?.operation === "apply-atom-preset") {
    label = creatingAtomTarget
      ? "Create atom & load"
      : app.workspaceApplyMode === "merge"
        ? "Merge preset"
        : "Load preset";
  } else if (app.workspaceApplyMode === "merge") {
    label = state === "active" || state === "local" ? "Merge" : "Enable & merge";
  } else {
    label = state === "active" || state === "local" ? "Load" : "Enable & load";
  }

  return {
    allowed: reason === "",
    label,
    reason,
  };
}

async function confirmSceneLoad(item, merge) {
  const title = resourceTitle(item);
  if (merge) {
    return showDialog({
      eyebrow: "Merge scene",
      title: `Merge “${title}” into the current scene?`,
      message:
        "VaM will add the scene’s atoms to what is already loaded. Conflicting UIDs or plugins may still change the current scene.",
      confirmLabel: "Merge scene",
      icon: "warning",
    });
  }
  return showDialog({
    eyebrow: "Replace current scene",
    title: `Load “${title}”?`,
    message:
      "This discards the currently loaded scene in VaM and replaces it. Save any work you want to keep before continuing.",
    confirmLabel: "Replace scene",
    icon: "danger",
  });
}

async function confirmRiskyAssetLoad(item, category, merge) {
  const critical = category.risk === "critical";
  const managedTarget = categoryUsesManagedAtomTarget(category);
  const targetUid = managedTarget ? activeAtomTargetUid(category) : "";
  const targetNote = managedTarget
    ? app.atomTargetMode === "create"
      ? ` A new ${category.targetAtomType || "compatible"} atom named “${targetUid}” will be created.`
      : ` Existing atom “${targetUid}” will be changed.`
    : "";
  const cuaSafetyNote = isCuaCategory(category)
    ? " DLL loading is forced off before this bundle loads. Bundles that require their own DLL may be incomplete. Code already active in this VaM session cannot be unloaded. Single-item bundles load automatically; multi-item bundles stay at None until you choose a contained scene or prefab."
    : "";
  return showDialog({
    eyebrow: critical ? "Critical live action" : "High-impact live action",
    title: `Load “${resourceTitle(item)}”?`,
    message:
      `${
        category.riskReason ||
        `This ${category.noun} can make broad or executable changes to the selected target.`
      }${targetNote}${cuaSafetyNote}`,
    confirmLabel: merge ? "Merge asset" : "Load asset",
    icon: critical ? "danger" : "warning",
  });
}

async function applyWorkspaceResource(item, category, sourceButton) {
  const resourceId = Number(item.id);
  if (!Number.isInteger(resourceId) || resourceId < 1 || !category) return;

  const managedTarget = categoryUsesManagedAtomTarget(category);
  const createIfMissing =
    managedTarget && app.atomTargetMode === "create";
  const merge =
    category.mergeSupported &&
    (!createIfMissing && app.workspaceApplyMode === "merge");
  const atomTargetUid = managedTarget ? activeAtomTargetUid(category) : "";
  let confirmedReplace = false;
  let confirmedRisk = false;
  if (category.operation === "load-scene") {
    const confirmed = await confirmSceneLoad(item, merge);
    if (!confirmed) return;
    confirmedReplace = !merge;
  } else if (["high", "critical"].includes(category.risk)) {
    confirmedRisk = Boolean(
      await confirmRiskyAssetLoad(item, category, merge),
    );
    if (!confirmedRisk) return;
    confirmedReplace = managedTarget && !createIfMissing && !merge;
  }

  const key = `${category.id}:${resourceId}`;
  app.applyingWorkspaceResources.add(key);
  if (managedTarget) renderAtomContext();
  setButtonBusy(sourceButton, true, "Queuing…");
  try {
    const body = {
      resource_id: resourceId,
      merge,
      days: 3,
      confirm_critical: confirmedRisk,
      confirm_replace: confirmedReplace,
      create_if_missing: createIfMissing,
    };
    if (category.targetKind === "person") {
      body.target_uid = app.selectedPersonUid;
    } else if (managedTarget) {
      body.target_uid = atomTargetUid;
    }

    const result = await api("/api/vam/resource/apply", {
      method: "POST",
      body,
    });
    requireBridgeQueue(result, `${prettyType(category.noun)} load`);
    if (createIfMissing) app.pendingAtomUid = atomTargetUid;
    const requestId =
      result.request_id || result.action_id || result.bridge_request || "";
    const detail =
      result.message ||
      `Queued ${
        category.targetKind === "person"
          ? `for ${app.selectedPersonUid}`
          : managedTarget
            ? `for ${atomTargetUid}`
            : "for VaM"
      }. VAM-PIP will enable required packages, rescan when needed, and load the asset${
        requestId ? ` · request ${String(requestId).slice(0, 8)}` : ""
      }.`;
    toast(`${prettyType(category.noun)} queued`, detail);
    await refreshAll({ force: true });
  } catch (error) {
    toast(
      `Could not load ${resourceTitle(item)}`,
      errorMessage(error),
      "error",
    );
  } finally {
    app.applyingWorkspaceResources.delete(key);
    setButtonBusy(sourceButton, false);
    if (managedTarget) renderAtomContext();
    if (app.view === "workspace") renderLibrary();
  }
}

function createPackageCard(item) {
  const card = createElement(
    "article",
    `library-card package-card${itemIsValid(item) ? "" : " is-invalid"}`,
  );
  const id = String(item.id || item.package_id || packageRoot(item) || "Unknown package");
  const root = String(item.id || packageRoot(item) || "");
  const active = itemIsActive(item);
  const valid = itemIsValid(item);
  const pinned = isPinned(root);
  const body = createElement("div", "card-body");

  const symbol = createElement("span", "package-symbol");
  symbol.setAttribute("aria-hidden", "true");
  symbol.textContent = valid ? "VAR" : "!";
  body.append(symbol);

  const state = badge(
    valid ? (active ? "Active" : "Hidden") : "Invalid",
    `package-state state-badge ${
      valid ? (active ? "is-active" : "is-hidden") : ""
    }`,
  );
  body.append(state);

  const heading = createElement("h3", "card-title");
  heading.textContent = id;
  heading.title = id;
  body.append(heading);

  const subtitle = createElement("p", "card-subtitle");
  subtitle.textContent = valid
    ? `${item.creator || "Unknown creator"} · version ${item.version || "?"}`
    : item.error || item.relative_path || "Package metadata could not be read";
  subtitle.title = subtitle.textContent;
  body.append(subtitle);

  const metadata = createElement("div", "card-meta");
  metadata.append(badge(formatBytes(item.size), "meta-pill"));
  const dependencyCount = asArray(item.dependencies).length;
  if (dependencyCount) {
    metadata.append(
      badge(`${dependencyCount} ${plural("dependency", dependencyCount)}`, "meta-pill"),
    );
  }
  if (numberOr(item.copies, 1) > 1) {
    metadata.append(badge(`${item.copies} copies`, "meta-pill"));
  }
  body.append(metadata);

  const actions = createElement("div", "card-actions");
  const leaseButton = button(
    active ? "Keep for 3 days" : "Enable for 3 days",
    active ? "secondary-button" : "primary-button",
  );
  leaseButton.disabled = !root || !valid;
  leaseButton.addEventListener("click", () =>
    createThreeDayLease(root, id, leaseButton),
  );
  actions.append(leaseButton);

  const pinButton = button("", `secondary-button pin-button${pinned ? " is-pinned" : ""}`);
  pinButton.disabled = !root || !valid;
  pinButton.setAttribute(
    "aria-label",
    pinned ? `Unpin ${root}` : `Always keep ${root} available`,
  );
  pinButton.title = pinned ? "Remove persistent pin" : "Always keep available";
  pinButton.append(pinIcon(pinned));
  pinButton.addEventListener("click", () =>
    pinned ? removePin(root, pinButton) : addPin(root, id, pinButton),
  );
  actions.append(pinButton);
  body.append(actions);

  card.append(body);
  return card;
}

function renderAccess() {
  const status = app.status || {};
  const pins = asArray(status.pins);
  const leases = asArray(status.leases);

  elements.pinsCount.textContent = formatNumber(pins.length);
  elements.leasesCount.textContent = formatNumber(leases.length);
  elements.pinsList.replaceChildren();
  elements.leasesList.replaceChildren();

  if (!pins.length) {
    elements.pinsList.append(emptyAccess("No packages are pinned."));
  } else {
    for (const pin of pins) {
      const root = String(pin.root_ref || pin.root || pin.reference || "");
      const item = createElement("article", "access-item");
      const content = document.createElement("div");
      const title = document.createElement("h4");
      title.textContent = pin.label || root;
      title.title = title.textContent;
      const detail = document.createElement("p");
      detail.textContent = pin.label ? root : `Pinned ${formatDate(pin.created_utc)}`;
      content.append(title, detail);

      const actions = createElement("div", "access-item-actions");
      const remove = button("×", "secondary-button remove-button");
      remove.setAttribute("aria-label", `Remove pin ${root}`);
      remove.title = "Remove pin";
      remove.addEventListener("click", () => removePin(root, remove));
      actions.append(remove);
      item.append(content, actions);
      elements.pinsList.append(item);
    }
  }

  if (!leases.length) {
    elements.leasesList.append(emptyAccess("No temporary access is active."));
  } else {
    for (const lease of leases) {
      const item = createElement(
        "article",
        `access-item${lease.expired ? " is-expired" : ""}`,
      );
      const content = document.createElement("div");
      const title = document.createElement("h4");
      title.textContent =
        lease.label ||
        asArray(lease.roots).join(", ") ||
        `Lease ${String(lease.id || "").slice(0, 8)}`;
      title.title = title.textContent;
      const detail = document.createElement("p");
      const packageCount = asArray(lease.packages).length;
      detail.textContent = lease.expired
        ? `Expired · ${packageCount} ${plural("package", packageCount)} waiting for cleanup`
        : `${relativeExpiry(lease.expires_utc)} · ${packageCount} ${plural(
            "package",
            packageCount,
          )}`;
      content.append(title, detail);

      const actions = createElement("div", "access-item-actions");
      const renew = button("+3 days", "secondary-button");
      renew.addEventListener("click", () => renewLease(lease.id, renew));
      const remove = button("×", "secondary-button remove-button");
      remove.setAttribute("aria-label", `End lease ${title.textContent}`);
      remove.title = "End lease";
      remove.addEventListener("click", () => removeLease(lease, remove));
      actions.append(renew, remove);
      item.append(content, actions);
      elements.leasesList.append(item);
    }
  }
}

function emptyAccess(message) {
  const empty = createElement("div", "inline-empty");
  const paragraph = document.createElement("p");
  paragraph.textContent = message;
  empty.append(paragraph);
  return empty;
}

async function runPackageScan() {
  setButtonBusy(elements.scanButton, true, "Scanning…");
  try {
    const result = await api("/api/scan", {
      method: "POST",
      body: { catalog: false },
    });
    const scan = result.packages || result;
    const inspected = numberOr(scan.inspected, 0);
    toast(
      "Package scan complete",
      `${formatNumber(scan.found)} found · ${formatNumber(inspected)} inspected · ${formatNumber(
        scan.invalid,
      )} invalid`,
    );
    await refreshAll();
  } catch (error) {
    toast("Package scan failed", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.scanButton, false);
  }
}

async function launchVam() {
  const liveVam =
    app.activity && app.activity.vam
      ? app.activity.vam
      : app.status && app.status.vam;
  if (liveVam && liveVam.running) {
    toast("VaM is already running", "The manager will keep monitoring it.");
    return;
  }
  if (operationIsBusy()) {
    toast(
      "Package update in progress",
      "Keep VaM closed until VAM-PIP finishes updating package visibility.",
    );
    return;
  }

  const pendingEnable = numberOr(app.status && app.status.pending_enable, 0);
  const pendingDisable = numberOr(app.status && app.status.pending_disable, 0);
  if (pendingEnable || pendingDisable) {
    const confirmed = await showDialog({
      eyebrow: "Start desktop mode",
      title: "Apply the package set and launch VaM?",
      message:
        "VAM-PIP will safely reconcile pins and active leases before starting your configured Proton launcher.",
      confirmLabel: "Apply & launch",
      icon: pendingDisable ? "warning" : "safe",
      plan: [
        ["Enable", pendingEnable],
        ["Hide", pendingDisable],
        ["Launch", "Desktop"],
      ],
    });
    if (!confirmed) return;
  }

  setButtonBusy(elements.launchVamButton, true, "Launching…");
  try {
    const result = await api("/api/vam/launch", {
      method: "POST",
      body: { reconcile: true },
    });
    toast(
      "VaM launched",
      result.pid
        ? `Desktop Proton process ${result.pid} started.`
        : "The desktop Proton launcher was started.",
    );
    window.setTimeout(() => loadStatus().catch(() => {}), 1800);
  } catch (error) {
    toast("Could not launch VaM", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.launchVamButton, false);
  }
}

async function importCatalogue() {
  setButtonBusy(elements.importButton, true, "Importing…");
  try {
    const result = await api("/api/catalog/import", { method: "POST", body: {} });
    const count =
      result.resources ??
      result.resource_count ??
      result.imported ??
      result.count ??
      0;
    toast(
      "Catalogue imported",
      count ? `${formatNumber(count)} resources are ready to browse.` : "The resource index is up to date.",
    );
    const facets = await api("/api/catalog/facets");
    app.facets = facets || {};
    renderFacets();
    await loadStatus();
    if (app.view === "resources") await loadLibrary();
  } catch (error) {
    toast("Catalogue import failed", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.importButton, false);
  }
}

async function importSessionDefaults() {
  let snapshot;
  try {
    snapshot = await ensureSessionPlugins({ refresh: true });
  } catch (error) {
    toast("Could not read session defaults", errorMessage(error), "error");
    return;
  }

  if (!snapshot.exists) {
    toast(
      "No default session preset found",
      "Save your Session Plugins as the default preset in VaM, then refresh VAM-PIP.",
      "error",
    );
    return;
  }

  const roots = sessionPackagedRoots(snapshot);
  const counts = snapshot.counts || {};
  const pluginCount = numberOr(counts.enabled_packaged, roots.length);
  const loose = numberOr(counts.loose, 0);
  const missing = Math.max(numberOr(counts.missing, 0), 0);
  const alreadyPinned = Math.min(numberOr(counts.already_pinned, 0), roots.length);
  const remaining = Math.max(roots.length - alreadyPinned, 0);

  if (missing) {
    toast(
      "Session-plugin packages are missing",
      `${formatNumber(missing)} required package ${plural(
        "reference",
        missing,
      )} must be installed before these defaults can be preserved.`,
      "error",
    );
    return;
  }

  if (!roots.length) {
    toast(
      "No package pins needed",
      loose
        ? `${formatNumber(loose)} enabled loose ${plural(
            "plugin",
            loose,
          )} stay available outside the VAR package set.`
        : "The default preset has no enabled packaged session plugins.",
    );
    return;
  }

  const confirmed = await showDialog({
    eyebrow: "Preserve session plugins",
    title: "Import enabled session defaults?",
    message:
      `Your default preset has ${formatNumber(pluginCount)} enabled packaged ${plural(
        "plugin",
        pluginCount,
      )} using ${formatNumber(roots.length)} package ${plural("root", roots.length)}. ` +
      "VAM-PIP will permanently pin those package roots. " +
      (loose
        ? `${formatNumber(loose)} enabled loose ${plural(
            "plugin",
            loose,
          )} need no pins and remain available.`
        : "Loose scripts need no pins and remain available."),
    confirmLabel: remaining ? "Import pins" : "Keep pins",
    icon: "safe",
    plan: [
      ["Plugin slots", pluginCount],
      ["Package roots", roots.length],
      ["Already pinned", alreadyPinned],
      ["New pins", remaining],
    ],
  });
  if (!confirmed) return;

  setButtonBusy(elements.sessionImportButton, true, "Importing…");
  try {
    const result = await api("/api/session-plugins/import", {
      method: "POST",
      body: {
        include_disabled: false,
        apply: Boolean(app.status && app.status.managed_mode),
      },
    });
    const resultRoots = asArray(result.roots);
    const preserved = resultRoots.length;
    const detail = [
      preserved
        ? `${formatNumber(preserved)} package ${plural(
            "root",
            preserved,
          )} preserved`
        : "No packaged session roots were present when imported",
    ];
    if (loose) detail.push(`${formatNumber(loose)} loose need no pins`);
    if (result.reconcile) detail.push(planResultText(result.reconcile).replace(/\.$/, ""));
    if (result.reconcile_error) {
      detail.push(`visibility update failed: ${result.reconcile_error}`);
      toast(
        "Session pins imported; apply is pending",
        `${detail.join(" · ")}.`,
        "error",
      );
    } else {
      toast("Session defaults imported", `${detail.join(" · ")}.`);
    }
    await refreshAll();
  } catch (error) {
    toast("Session-default import failed", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.sessionImportButton, false);
    renderSessionPlugins();
  }
}

async function activateManagedMode() {
  const status = app.status || {};
  const pinCount = asArray(status.pins).length;
  const activeCount = numberOr(status.packages && status.packages.active, 0);
  let sessionPlugins;
  try {
    sessionPlugins = await ensureSessionPlugins({ refresh: true });
  } catch (error) {
    toast(
      "Could not verify session defaults",
      `VAM-PIP did not start managed mode: ${errorMessage(error)}`,
      "error",
    );
    return;
  }

  const sessionRoots = sessionPackagedRoots(sessionPlugins);
  const sessionCounts = sessionPlugins.counts || {};
  const sessionPluginCount = numberOr(
    sessionCounts.enabled_packaged,
    sessionRoots.length,
  );
  const sessionLoose = numberOr(sessionCounts.loose, 0);
  const sessionMissing = Math.max(numberOr(sessionCounts.missing, 0), 0);
  const sessionAlreadyPinned = Math.min(
    numberOr(sessionCounts.already_pinned, 0),
    sessionRoots.length,
  );
  const sessionNewPins = Math.max(sessionRoots.length - sessionAlreadyPinned, 0);
  if (sessionMissing) {
    toast(
      "Session-plugin packages are missing",
      `VAM-PIP did not start managed mode. Install the ${formatNumber(
        sessionMissing,
      )} missing package ${plural(
        "reference",
        sessionMissing,
      )} or remove it from the default Session Plugins preset.`,
      "error",
    );
    return;
  }
  let sessionMessage;
  if (!sessionPlugins.exists) {
    sessionMessage =
      "No default Session Plugins preset was found, so there are no session defaults to import automatically. ";
  } else if (sessionRoots.length) {
    sessionMessage =
      `${formatNumber(sessionPluginCount)} enabled packaged session ${plural(
        "plugin",
        sessionPluginCount,
      )} use ${formatNumber(sessionRoots.length)} package ${plural(
        "root",
        sessionRoots.length,
      )}; those roots will be automatically preserved as permanent pins. ` +
      (sessionLoose
        ? `${formatNumber(sessionLoose)} enabled loose ${plural(
            "plugin",
            sessionLoose,
          )} need no pins. `
        : "Loose plugins need no pins. ");
  } else if (sessionLoose) {
    sessionMessage =
      `${formatNumber(sessionLoose)} enabled session ${plural(
        "plugin",
        sessionLoose,
      )} are loose scripts, so they remain available without pins. `;
  } else {
    sessionMessage = "The default preset has no enabled session plugins to preserve. ";
  }

  const confirmed = await showDialog({
    eyebrow: "Managed mode",
    title: "Let VAM-PIP control package visibility?",
    message:
      `VAM-PIP will record your current ${formatNumber(activeCount)} active packages as a rollback baseline, ` +
      sessionMessage +
      `It will then keep ${formatNumber(
        pinCount + sessionNewPins,
      )} pinned root${pinCount + sessionNewPins === 1 ? "" : "s"} and their dependencies active. ` +
      (status.vam && status.vam.running
        ? "VaM is running, so packages will only be enabled now; hiding is deferred until it closes."
        : "VaM is closed, so the new package set can be applied safely."),
    confirmLabel: "Start managed mode",
    icon: "warning",
    plan: [
      ["Active now", activeCount],
      ["Session plugin slots", sessionPluginCount],
      ["Pins after import", pinCount + sessionNewPins],
      ["Rollback", "Saved"],
    ],
  });
  if (!confirmed) return;

  setButtonBusy(elements.activateButton, true, "Starting…");
  try {
    const result = await api("/api/reconcile", {
      method: "POST",
      body: { apply: true, activate: true },
    });
    toast("Managed mode is active", planResultText(result));
    await refreshAll();
  } catch (error) {
    toast("Could not start managed mode", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.activateButton, false);
  }
}

async function reconcileWithConfirmation() {
  let plan;
  try {
    plan = await api("/api/reconcile", {
      method: "POST",
      body: { apply: false, activate: false },
    });
  } catch (error) {
    toast("Could not build change plan", errorMessage(error), "error");
    return;
  }

  const enable = numberOr(plan.enable, 0);
  const disable = numberOr(plan.disable, 0);
  const pending = numberOr(plan.pending_disable, 0);
  if (enable === 0 && disable === 0 && pending === 0) {
    toast("Package set is current", "No visibility changes are needed.");
    return;
  }

  const confirmed = await showDialog({
    eyebrow: "Visibility plan",
    title: "Apply the managed package set?",
    message: plan.vam_running
      ? "VaM is running. New packages can be enabled and rescanned now; packages no longer needed will remain visible until VaM closes."
      : "VaM is closed. VAM-PIP can safely enable required packages and hide packages that are no longer selected.",
    confirmLabel: "Apply changes",
    icon: disable || pending ? "warning" : "safe",
    plan: [
      ["Enable", enable],
      ["Hide now", disable],
      ["Deferred", pending],
    ],
  });
  if (!confirmed) return;

  try {
    const result = await api("/api/reconcile", {
      method: "POST",
      body: { apply: true, activate: false },
    });
    toast("Package set updated", planResultText(result));
    await refreshAll();
  } catch (error) {
    toast("Could not apply package set", errorMessage(error), "error");
  }
}

async function deactivateManagedMode() {
  if (app.status && app.status.vam && app.status.vam.running) {
    toast(
      "Close VaM first",
      "The original package set cannot be restored while a scene may be using active packages.",
      "error",
    );
    return;
  }

  let plan;
  try {
    plan = await api("/api/deactivate", {
      method: "POST",
      body: { apply: false },
    });
  } catch (error) {
    toast("Could not build restore plan", errorMessage(error), "error");
    return;
  }

  const confirmed = await showDialog({
    eyebrow: "Restore baseline",
    title: "Leave managed mode?",
    message:
      "This restores the exact package visibility recorded when managed mode was first enabled. Your pins and leases remain in the manager database.",
    confirmLabel: "Restore original set",
    icon: "danger",
    plan: [
      ["Enable", numberOr(plan.enable, 0)],
      ["Hide", numberOr(plan.disable, 0)],
      ["Baseline", "Restore"],
    ],
  });
  if (!confirmed) return;

  setButtonBusy(elements.deactivateButton, true, "Restoring…");
  try {
    const result = await api("/api/deactivate", {
      method: "POST",
      body: { apply: true },
    });
    toast("Original package set restored", planResultText(result));
    await refreshAll();
  } catch (error) {
    toast("Could not restore package set", errorMessage(error), "error");
  } finally {
    setButtonBusy(elements.deactivateButton, false);
  }
}

async function createThreeDayLease(root, label, sourceButton, resourceId = null) {
  if (!root && !resourceId) return;
  if (!app.status || !app.status.managed_mode) {
    const shouldActivate = await showDialog({
      eyebrow: "Managed mode required",
      title: "Start managed mode first",
      message:
        "Temporary access works after VAM-PIP has recorded a rollback baseline and taken control of package visibility. Pin any always-needed plugins first.",
      confirmLabel: "Review managed mode",
      icon: "warning",
    });
    if (shouldActivate) activateManagedMode();
    return;
  }

  setButtonBusy(sourceButton, true, "Resolving…");
  try {
    const result = resourceId
      ? await api(`/api/resources/${encodeURIComponent(resourceId)}/lease`, {
          method: "POST",
          body: { days: 3, label, apply: true },
        })
      : await api("/api/leases", {
          method: "POST",
          body: { roots: [root], days: 3, label, apply: true },
        });
    if (result.already_local) {
      toast("Already available", "This is a loose local resource and does not need a package lease.");
      return;
    }
    const resolved = numberOr(result.resolved_packages, 0);
    const reconcile = result.reconcile || {};
    const pending = numberOr(reconcile.pending_disable, 0);
    toast(
      "Available for 3 days",
      `${formatNumber(resolved)} ${plural("package", resolved)} resolved${
        reconcile.bridge_request ? " · live rescan requested" : ""
      }${pending ? ` · ${pending} future disables deferred` : ""}.`,
    );
    await refreshAll();
  } catch (error) {
    toast(`Could not enable ${label}`, errorMessage(error), "error");
  } finally {
    setButtonBusy(sourceButton, false);
  }
}

async function addPin(root, label, sourceButton) {
  if (!root) return;
  setButtonBusy(sourceButton, true);
  try {
    const result = await api("/api/pins", {
      method: "POST",
      body: {
        roots: [root],
        label,
        apply: Boolean(app.status && app.status.managed_mode),
      },
    });
    toast(
      "Package pinned",
      `${root} and ${formatNumber(result.resolved_packages)} resolved ${plural(
        "package",
        numberOr(result.resolved_packages, 0),
      )} will remain available.`,
    );
    await refreshAll();
  } catch (error) {
    toast(`Could not pin ${root}`, errorMessage(error), "error");
  } finally {
    setButtonBusy(sourceButton, false);
  }
}

async function promptForPin() {
  const root = await showDialog({
    eyebrow: "Persistent access",
    title: "Add a package pin",
    message:
      "Enter an installed package family or exact package ID. Dependencies are resolved automatically.",
    confirmLabel: "Add pin",
    icon: "safe",
    input: {
      label: "Package reference",
      placeholder: "Creator.Package or Creator.Package.1",
    },
  });
  if (!root) return;
  await addPin(String(root).trim(), null, elements.addPinButton);
}

async function removePin(root, sourceButton) {
  if (!root) return;
  const confirmed = await showDialog({
    eyebrow: "Remove persistent access",
    title: `Unpin ${root}?`,
    message:
      "The package remains active if another pin or lease needs it. If VaM is open, any resulting disable is deferred.",
    confirmLabel: "Remove pin",
    icon: "warning",
  });
  if (!confirmed) return;

  setButtonBusy(sourceButton, true);
  try {
    await api(`/api/pins/${encodeURIComponent(root)}`, { method: "DELETE" });
    let reconcile = null;
    if (app.status && app.status.managed_mode) {
      reconcile = await api("/api/reconcile", {
        method: "POST",
        body: { apply: true, activate: false },
      });
    }
    toast("Pin removed", reconcile ? planResultText(reconcile) : root);
    await refreshAll();
  } catch (error) {
    toast("Could not remove pin", errorMessage(error), "error");
  } finally {
    setButtonBusy(sourceButton, false);
  }
}

async function renewLease(id, sourceButton) {
  if (!id) return;
  setButtonBusy(sourceButton, true, "Renewing…");
  try {
    const result = await api(`/api/leases/${encodeURIComponent(id)}/renew`, {
      method: "POST",
      body: { days: 3 },
    });
    toast("Lease extended", `Now available ${relativeExpiry(result.expires_utc)}.`);
    await loadStatus();
  } catch (error) {
    toast("Could not renew lease", errorMessage(error), "error");
  } finally {
    setButtonBusy(sourceButton, false);
  }
}

async function removeLease(lease, sourceButton) {
  const label =
    lease.label || asArray(lease.roots).join(", ") || String(lease.id).slice(0, 8);
  const confirmed = await showDialog({
    eyebrow: "End temporary access",
    title: `End “${label}”?`,
    message:
      "Packages used only by this lease can be hidden. If VaM is open, that cleanup waits until the game closes.",
    confirmLabel: "End lease",
    icon: "warning",
  });
  if (!confirmed) return;

  setButtonBusy(sourceButton, true);
  try {
    const result = await api(`/api/leases/${encodeURIComponent(lease.id)}`, {
      method: "DELETE",
    });
    const reconcile = result.reconcile || null;
    toast("Lease ended", reconcile ? planResultText(reconcile) : label);
    await refreshAll();
  } catch (error) {
    toast("Could not end lease", errorMessage(error), "error");
  } finally {
    setButtonBusy(sourceButton, false);
  }
}

async function updateAutoReconcile() {
  const enabled = elements.autoReconcile.checked;
  elements.autoReconcile.disabled = true;
  try {
    await api("/api/settings", {
      method: "POST",
      body: { auto_reconcile: enabled },
    });
    if (app.status) app.status.auto_reconcile = enabled;
    toast(
      enabled ? "Startup cleanup enabled" : "Startup cleanup disabled",
      enabled
        ? "Expired leases will be reconciled when it is safe."
        : "Pending package changes will wait for a manual apply.",
    );
  } catch (error) {
    elements.autoReconcile.checked = !enabled;
    toast("Could not save setting", errorMessage(error), "error");
  } finally {
    elements.autoReconcile.disabled = false;
  }
}

function setView(view) {
  if (
    !["resources", "workspace", "packages", "access"].includes(view) ||
    app.view === view
  ) {
    return;
  }
  app.view = view;

  for (const tab of elements.viewTabs) {
    const active = tab.dataset.view === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }

  const isAccess = view === "access";
  const isWorkspace = view === "workspace";
  elements.libraryView.hidden = isAccess;
  elements.accessView.hidden = !isAccess;
  elements.assetWorkspace.hidden = !isWorkspace;
  if (isAccess) {
    renderAccess();
    return;
  }

  elements.typeFilterWrap.hidden = view !== "resources";
  updateWorkspaceSearchPlaceholder();
  configureStateFilter();
  if (isWorkspace) {
    renderWorkspaceCategoryNavigation();
    renderWorkspaceCategorySummary();
    const category = currentWorkspaceCategory();
    if (
      category?.liveAction ||
      category?.targetKind === "person" ||
      ATOM_TARGET_KINDS.has(category?.targetKind)
    ) {
      loadPersons({ quiet: true });
    }
  }
  loadLibrary();
}

function updateWorkspaceSearchPlaceholder() {
  if (app.view === "workspace") {
    const category = currentWorkspaceCategory();
    elements.searchInput.placeholder = `Search ${category?.label.toLowerCase() || "assets"}, creators, tags…`;
  } else if (app.view === "resources") {
    elements.searchInput.placeholder =
      "Search scenes, looks, clothing, creators…";
  } else {
    elements.searchInput.placeholder = "Search package or creator…";
  }
}

function configureStateFilter() {
  const resourceOptions = [
    ["Any state", "all"],
    ["Active", "active"],
    ["Available", "hidden"],
    ["Missing", "missing"],
    ["Local files", "local"],
  ];
  const packageOptions = [
    ["Any state", "all"],
    ["Active", "active"],
    ["Hidden", "hidden"],
    ["Invalid", "invalid"],
  ];
  const options =
    app.view === "resources" || app.view === "workspace"
      ? resourceOptions
      : packageOptions;
  const supported = options.some(([, value]) => value === app.packageState);
  if (!supported) app.packageState = "all";
  elements.stateFilter.replaceChildren(
    ...options.map(([label, value]) => new Option(label, value)),
  );
  elements.stateFilter.value = app.packageState;
}

function clearFilters() {
  window.clearTimeout(app.searchTimer);
  app.query = "";
  app.type = "";
  app.packageState = "all";
  elements.searchInput.value = "";
  elements.typeFilter.value = "";
  elements.stateFilter.value = "all";
  updateClearFilters();
  loadLibrary();
}

function updateClearFilters() {
  elements.clearFilters.hidden = !hasFilters();
}

function hasFilters() {
  return Boolean(
    app.query ||
      app.packageState !== "all" ||
      (app.view === "resources" && app.type),
  );
}

function handleEmptyAction() {
  const action = elements.emptyAction.dataset.action;
  if (action === "import") {
    importCatalogue();
  } else if (action === "clear") {
    clearFilters();
  } else {
    refreshAll();
  }
}

function setConnection(state, text) {
  elements.connectionChip.classList.toggle("is-online", state === "online");
  elements.connectionChip.classList.toggle("is-error", state === "error");
  elements.connectionLabel.textContent = text;
}

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (app.token) {
    headers.set("X-VAMPIP-Token", app.token);
  }

  const request = {
    method,
    headers,
    credentials: "same-origin",
    cache: method === "GET" ? "no-store" : "default",
    signal: options.signal,
  };

  if (method !== "GET" && method !== "HEAD") {
    if (!app.token) {
      throw new Error(
        "This page has no write token. Reopen the URL printed by VAM-PIP (it contains #token=…).",
      );
    }
    headers.set("Content-Type", "application/json");
    request.body = JSON.stringify(options.body || {});
  }

  const response = await fetch(path, request);
  const contentType = response.headers.get("content-type") || "";
  let payload;
  if (response.status === 204) {
    payload = {};
  } else if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => ({}));
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const detail =
      (payload &&
        typeof payload === "object" &&
        (payload.error || payload.message || payload.detail)) ||
      (typeof payload === "string" && payload) ||
      `${response.status} ${response.statusText}`;
    const error = new Error(String(detail));
    error.status = response.status;
    throw error;
  }
  return payload || {};
}

function showDialog(config) {
  const dialog = elements.confirmDialog;
  elements.confirmEyebrow.textContent = config.eyebrow || "Confirm change";
  elements.confirmTitle.textContent = config.title || "Apply this change?";
  elements.confirmMessage.textContent = config.message || "";
  elements.confirmSubmit.textContent = config.confirmLabel || "Confirm";
  elements.confirmIcon.className = "dialog-icon";
  if (config.icon === "warning") elements.confirmIcon.classList.add("is-warning");
  if (config.icon === "danger") elements.confirmIcon.classList.add("is-danger");

  elements.planSummary.replaceChildren();
  if (config.plan && config.plan.length) {
    for (const [label, value] of config.plan) {
      const stat = createElement("div", "plan-stat");
      const labelElement = document.createElement("span");
      labelElement.textContent = label;
      const valueElement = document.createElement("strong");
      valueElement.textContent =
        typeof value === "number" ? formatNumber(value) : String(value);
      stat.append(labelElement, valueElement);
      elements.planSummary.append(stat);
    }
    elements.planSummary.hidden = false;
  } else {
    elements.planSummary.hidden = true;
  }

  if (config.input) {
    elements.dialogInputWrap.hidden = false;
    elements.dialogInputLabel.textContent = config.input.label || "Value";
    elements.dialogInput.placeholder = config.input.placeholder || "";
    elements.dialogInput.value = config.input.value || "";
    elements.dialogInput.required = true;
  } else {
    elements.dialogInputWrap.hidden = true;
    elements.dialogInput.required = false;
    elements.dialogInput.value = "";
  }

  dialog.returnValue = "";
  dialog.showModal();
  if (config.input) {
    window.setTimeout(() => elements.dialogInput.focus(), 30);
  }

  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => {
        if (dialog.returnValue !== "confirm") {
          resolve(false);
          return;
        }
        if (config.input) {
          const value = elements.dialogInput.value.trim();
          resolve(value || false);
        } else {
          resolve(true);
        }
      },
      { once: true },
    );
  });
}

function toast(title, message, kind = "success") {
  const item = createElement("div", `toast${kind === "error" ? " is-error" : ""}`);
  item.setAttribute("role", kind === "error" ? "alert" : "status");
  const dot = createElement("span", "toast-dot");
  dot.setAttribute("aria-hidden", "true");
  const content = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const detail = document.createElement("p");
  detail.textContent = message || "";
  content.append(heading, detail);
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "×";
  close.setAttribute("aria-label", "Dismiss notification");
  close.addEventListener("click", () => item.remove());
  item.append(dot, content, close);
  elements.toastRegion.append(item);
  window.setTimeout(() => item.remove(), kind === "error" ? 9000 : 5200);
}

function setButtonBusy(buttonElement, busy, busyLabel = "") {
  if (!buttonElement) return;
  if (busy) {
    buttonElement.disabled = true;
    buttonElement.setAttribute("aria-busy", "true");
    if (busyLabel) {
      busyContents.set(buttonElement, Array.from(buttonElement.childNodes));
      buttonElement.replaceChildren(document.createTextNode(busyLabel));
    }
    if (buttonElement === elements.refreshButton) {
      buttonElement.classList.add("is-spinning");
    }
  } else {
    buttonElement.disabled = false;
    buttonElement.removeAttribute("aria-busy");
    if (busyContents.has(buttonElement)) {
      buttonElement.replaceChildren(...busyContents.get(buttonElement));
      busyContents.delete(buttonElement);
    }
    buttonElement.classList.remove("is-spinning");
  }
}

function createElement(tag, className = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  return element;
}

function button(label, className) {
  const element = createElement("button", className);
  element.type = "button";
  element.textContent = label;
  return element;
}

function badge(label, className) {
  const element = createElement("span", className);
  element.textContent = label;
  return element;
}

function pinIcon(filled) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", filled ? "currentColor" : "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M8 4h8l-1 6 3 3H6l3-3zM12 13v7");
  svg.append(path);
  return svg;
}

function packageRoot(item) {
  const explicit =
    item.package_ref ||
    item.root_ref ||
    item.package_id ||
    item.family ||
    item.package_family;
  if (explicit) return String(explicit);
  const creator = item.creator;
  const packageName = item.package_name || item.package;
  if (creator && packageName) return `${creator}.${packageName}`;
  return "";
}

function resourceTitle(item) {
  const direct =
    item.title ||
    item.name ||
    item.display_name ||
    item.resource_name ||
    item.displayName;
  if (direct) return String(direct);
  const path = String(item.resource_path || item.path || item.resource_key || "");
  if (!path) return packageRoot(item) || "Untitled resource";
  const basename = path.split(/[\\/]/).pop() || path;
  return basename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
}

function resourceType(item) {
  return String(item.resource_type || item.type || item.category || "resource");
}

function itemIsActive(item) {
  if (item.active !== undefined) return Boolean(item.active);
  if (item.package_active !== undefined) return Boolean(item.package_active);
  if (item.enabled !== undefined) return Boolean(item.enabled);
  return String(item.state || "").toLowerCase() === "active";
}

function itemIsValid(item) {
  return item.valid === undefined ? true : Boolean(item.valid);
}

function isPinned(root) {
  if (!root || !app.status) return false;
  const target = root.toLocaleLowerCase();
  return asArray(app.status.pins).some((pin) => {
    const reference = pin.root_ref || pin.root || pin.reference || "";
    return String(reference).toLocaleLowerCase() === target;
  });
}

function creatorFromRoot(root) {
  return root ? String(root).split(".")[0] : "";
}

function normalizeTags(tags) {
  if (Array.isArray(tags)) {
    return tags
      .map((tag) => {
        if (tag && typeof tag === "object") {
          return tag.tagName || tag.name || tag.value || "";
        }
        return String(tag || "");
      })
      .filter(Boolean);
  }
  if (typeof tags !== "string" || !tags) return [];
  try {
    const parsed = JSON.parse(tags);
    if (Array.isArray(parsed)) return normalizeTags(parsed);
  } catch (_error) {
    return tags.split(",").map((tag) => tag.trim()).filter(Boolean);
  }
  return [];
}

function prettyType(value) {
  return String(value || "Resource")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function fileExtension(path) {
  const match = String(path || "").match(/\.([a-z0-9]+)$/i);
  return match ? match[1].toUpperCase() : "Resource";
}

function initials(value) {
  const words = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return "V";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

function planResultText(result) {
  const enabled = numberOr(result.enable, 0);
  const disabled = numberOr(result.disable, 0);
  const pending = numberOr(result.pending_disable, 0);
  const parts = [`${formatNumber(enabled)} enabled`, `${formatNumber(disabled)} hidden`];
  if (pending) parts.push(`${formatNumber(pending)} disables deferred`);
  if (result.bridge_request) parts.push("live rescan requested");
  return `${parts.join(" · ")}.`;
}

function requireBridgeQueue(result, actionLabel) {
  if (!result || result.bridge_busy !== true) return;
  const reason =
    result.bridge_message ||
    "another bridge action reached VaM before this request";
  const leaseNote = result.lease
    ? " Required packages remain enabled by the new lease."
    : "";
  throw new Error(
    `${actionLabel} was not queued because ${reason}.${leaseNote} Retry after the current bridge action finishes.`,
  );
}

function errorMessage(error) {
  if (!error) return "Unknown error";
  if (error instanceof TypeError && /fetch/i.test(error.message)) {
    return "The localhost service may have stopped. Restart VAM-PIP and refresh this page.";
  }
  return String(error.message || error);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function numberOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(number)
    : "—";
}

function formatCompact(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat(undefined, {
    notation: number >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(number);
}

function formatBytes(value) {
  let bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "Unknown size";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let index = 0;
  while (bytes >= 1024 && index < units.length - 1) {
    bytes /= 1024;
    index += 1;
  }
  return `${bytes.toFixed(index === 0 || bytes >= 100 ? 0 : 1)} ${units[index]}`;
}

function plural(word, amount) {
  if (Number(amount) === 1) return word;
  if (word === "dependency") return "dependencies";
  return `${word}s`;
}

function formatDate(value) {
  if (!value) return "recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(date);
}

function relativeExpiry(value) {
  const expiry = new Date(value);
  if (!value || Number.isNaN(expiry.getTime())) return "with no known expiry";
  const milliseconds = expiry.getTime() - Date.now();
  const absolute = Math.abs(milliseconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (absolute < 90 * 60 * 1000) {
    return formatter.format(Math.round(milliseconds / 60000), "minute");
  }
  if (absolute < 48 * 60 * 60 * 1000) {
    return formatter.format(Math.round(milliseconds / 3600000), "hour");
  }
  return formatter.format(Math.round(milliseconds / 86400000), "day");
}

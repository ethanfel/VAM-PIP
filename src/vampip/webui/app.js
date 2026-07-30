"use strict";

const PAGE_SIZE = 24;
const MAX_VARIANT_MATCH_COUNT = 1_000_000;
const MAX_RENDERED_RESOURCE_VARIANTS = 12;
const MAX_PACKAGE_RESOURCE_PREVIEWS = 4;
const MAX_PACKAGE_RESOURCE_TYPES = 3;
const DEPENDENCY_PAGE_SIZE = 8;
const MAX_RENDERED_DEPENDENCIES = 2_048;
const MAX_TIMELINE_TRACKS = 80;
const MAX_TIMELINE_KEYS_PER_TRACK = 2_000;
const MAX_TIMELINE_KEYS = 10_000;
const TIMELINE_PLAYING_POLL_MS = 1000;
const TIMELINE_IDLE_POLL_MS = 1_000;
const SAM3D_POLL_MS = 1_000;
// The VaM bridge allows the renderer up to five minutes to finish encoding.
// Keep checking a little longer so a valid slow capture is not abandoned.
const SAM3D_CAPTURE_POLL_ATTEMPTS = 310;
const SAM3D_MAX_UPLOAD_BYTES = 32 * 1024 * 1024;
const SAM3D_MAX_HISTORY = 50;
const SAM3D_MAX_CAPTURES = 50;
const SAM3D_DEFAULT_CAMERA_UID = "VAMPip SAM3D Camera";
const SAM3D_COMPARE_MODEL_ID = "compare";
const SAM3D_DINOV3_MODEL_ID = "dinov3_vith16plus";
const SAM3D_VITH_MODEL_ID = "vit_hmr_512_384";
const SAM3D_MODEL_ORDER = Object.freeze([
  SAM3D_DINOV3_MODEL_ID,
  SAM3D_VITH_MODEL_ID,
]);
const SAM3D_BODY_PROPORTION_REGIONS = Object.freeze([
  "arms",
  "legs",
  "torso",
  "widths",
]);
const SAM3D_BODY_SHAPE_REGIONS = Object.freeze([
  "breasts",
  "waist",
  "hips",
  "glutes",
  "thighs",
]);
const SAM3D_MANUAL_SHAPE_KEYS = Object.freeze([
  "breast_size",
  "breast_spacing",
  "waist_width",
  "hip_width",
  "glute_projection",
  "thigh_size",
]);
const SAM3D_BODY_PROPORTION_ACTIONS = Object.freeze({
  analyze: "analyze",
  apply: "apply",
  undo: "undo",
});
const SAM3D_BODY_PROPORTION_POLL_ATTEMPTS = 300;
const SAM3D_BODY_PROFILE_STORAGE_KEY = "vampip-sam3d-body-profiles-v4";
const SAM3D_BODY_PROFILE_V3_STORAGE_KEY =
  "vampip-sam3d-body-profiles-v3";
const SAM3D_BODY_PROFILE_V2_STORAGE_KEY =
  "vampip-sam3d-body-profiles-v2";
const SAM3D_BODY_PROFILE_V1_STORAGE_KEY =
  "vampip-sam3d-body-profiles-v1";
const SAM3D_BODY_PROFILE_MAX_COUNT = 24;
const SAM3D_BODY_REFERENCE_MAX_COUNT = 8;
const SAM3D_BODY_LEGACY_SOLO_MESSAGE =
  "Legacy result is solo-only for Structure; use Body Shape only or rerun the image to combine Structure.";
const SAM3D_RENDERER_RESOLUTIONS = Object.freeze({
  "36:9": Object.freeze(["1600x400", "3200x800", "6400x1600"]),
  "32:9": Object.freeze([
    "2048x576",
    "2560x720",
    "3840x1080 (DFHD)",
    "5120x1440 (DQHD)",
    "7680x2160 (DUHD)",
  ]),
  "21:9": Object.freeze([
    "2560x1080 (WFHD)",
    "3440x1440 (WQHD)",
    "5120x2160 (4K WUHD)",
  ]),
  "16:9": Object.freeze([
    "1280x720 (HD)",
    "1920x1080 (FHD)",
    "2560x1440 (QHD)",
    "3840x2160 (4K UHD)",
    "5120x2880 (5K)",
    "7680x4320 (8K UHD)",
  ]),
  "16:10": Object.freeze([
    "1280x800 (WXGA)",
    "1440x900 (WXGA+)",
    "1920x1200 (WUXGA)",
    "3840x2400 (2x WUXGA)",
  ]),
  "4:3": Object.freeze([
    "800x600 (SVGA)",
    "1024x768 (XGA)",
    "2048x1536 (2x XGA)",
    "4096x3072 (4x XGA)",
  ]),
  "2:1": Object.freeze([
    "1280x640",
    "1920x960",
    "2560x1280",
    "3840x1920 (4K)",
    "5120x2560 (5K)",
    "7680x3840 (8K)",
  ]),
  "1:1": Object.freeze([
    "256x256",
    "512x512",
    "1024x1024",
    "1920x1920",
    "2048x2048",
    "2560x2560",
    "3840x3840 (4K)",
    "4096x4096",
  ]),
});
const SAM3D_JOB_ID_PATTERN = /^[0-9a-f]{32}$/i;
const SAM3D_TERMINAL_STATES = new Set([
  "cancelled",
  "complete",
  "completed",
  "error",
  "failed",
  "interrupted",
  "ready",
  "succeeded",
]);
const SAM3D_SUCCESS_STATES = new Set([
  "complete",
  "completed",
  "ready",
  "succeeded",
]);
const SAM3D_ERROR_STATES = new Set([
  "cancelled",
  "error",
  "failed",
  "interrupted",
]);
const TOKEN_KEY = "vampip-token";
const INVALID_MANAGER_TOKEN_MESSAGE = "invalid manager token";
const WORKSPACE_ACTION_STALL_MS = 5 * 60 * 1000;
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
const PERSON_TARGET_KINDS = new Set(["person", "person-clothing-item"]);
const CHARACTER_SLOT_VISIBLE_ITEMS = 3;
const WARDROBE_CATEGORY_IDS = new Set([
  "preset-clothing",
  "clothing-items-female",
  "clothing-items-male",
  "clothing-item-presets",
]);
const HAIR_CATEGORY_IDS = new Set(["preset-hair"]);
const CHARACTER_SHEET_SLOTS = Object.freeze([
  {
    id: "head",
    label: "Head & face",
    column: "left",
    tags: [
      "head",
      "hat",
      "hats",
      "cap",
      "caps",
      "crown",
      "mask",
      "masks",
      "veil",
      "glasses",
      "eye",
      "eyes",
      "mouth",
      "teeth",
      "makeup",
      "makeups",
    ],
  },
  {
    id: "neck",
    label: "Neck",
    column: "left",
    tags: ["neck", "collar", "choker", "necklace", "scarf", "tie"],
  },
  {
    id: "tops",
    label: "Tops & outerwear",
    column: "left",
    tags: [
      "torso",
      "top",
      "tops",
      "shirt",
      "shirts",
      "blouse",
      "coat",
      "hoodie",
      "jacket",
      "sweater",
      "corset",
      "vest",
    ],
  },
  {
    id: "bras",
    label: "Bras",
    column: "left",
    tags: ["bra", "bras", "bralette", "brassiere"],
  },
  {
    id: "arms-hands",
    label: "Arms & hands",
    column: "left",
    tags: ["arm", "arms", "hand", "hands", "glove", "gloves", "mittens"],
  },
  {
    id: "dresses-outfits",
    label: "Dresses & full outfits",
    column: "left",
    tags: [
      "full body",
      "full-body",
      "bodysuit",
      "catsuit",
      "costume",
      "dress",
      "dresses",
      "gown",
      "jumpsuit",
      "outfit",
      "robe",
      "romper",
      "swimwear",
      "bikini",
    ],
  },
  {
    id: "panties-underwear",
    label: "Panties & underwear",
    column: "right",
    tags: [
      "briefs",
      "lingerie",
      "panty",
      "panties",
      "thong",
      "thongs",
      "underwear",
      "knickers",
    ],
  },
  {
    id: "bottoms",
    label: "Bottoms",
    column: "right",
    tags: [
      "bottom",
      "bottoms",
      "hip",
      "hips",
      "waist",
      "skirt",
      "skirts",
      "belt",
      "leg",
      "legs",
      "pants",
      "shorts",
      "jeans",
      "trousers",
    ],
  },
  {
    id: "stockings-socks",
    label: "Stockings & socks",
    column: "right",
    tags: [
      "stocking",
      "stockings",
      "leggings",
      "garter",
      "garters",
      "hosiery",
      "pantyhose",
      "sock",
      "socks",
      "tights",
    ],
  },
  {
    id: "high-heels",
    label: "High heels",
    column: "right",
    tags: [
      "heel",
      "heels",
      "high heel",
      "high heels",
      "high-heel",
      "high-heels",
      "pump",
      "pumps",
      "stiletto",
      "stilettos",
    ],
  },
  {
    id: "shoes-boots",
    label: "Shoes & boots",
    column: "right",
    tags: [
      "feet",
      "footwear",
      "shoe",
      "shoes",
      "boot",
      "boots",
      "sandal",
      "sandals",
      "sneaker",
      "sneakers",
    ],
  },
  {
    id: "accessories",
    label: "Accessories",
    column: "right",
    tags: [
      "accessory",
      "accessories",
      "jewelry",
      "piercing",
      "bracelet",
      "ring",
      "earring",
      "earrings",
      "chain",
    ],
  },
  {
    id: "body-fx",
    label: "Body FX",
    column: "right",
    tags: ["fx", "mark", "cum", "sperm", "pussydrip", "saliva", "tears", "wet"],
  },
  {
    id: "unsorted",
    label: "Unsorted",
    column: "extra",
    tags: [],
  },
]);
const CHARACTER_SLOT_CLASSIFICATION_ORDER = Object.freeze([
  "dresses-outfits",
  "high-heels",
  "bras",
  "panties-underwear",
  "stockings-socks",
  "head",
  "neck",
  "arms-hands",
  "shoes-boots",
  "bottoms",
  "tops",
  "accessories",
  "body-fx",
]);
const CHARACTER_SLOT_ALIASES = Object.freeze({
  "full-body": "dresses-outfits",
  "dresses-and-full-outfits": "dresses-outfits",
  outfit: "dresses-outfits",
  outfits: "dresses-outfits",
  dress: "dresses-outfits",
  "upper-body": "tops",
  "tops-and-outerwear": "tops",
  torso: "tops",
  top: "tops",
  bra: "bras",
  underwear: "panties-underwear",
  "panties-and-underwear": "panties-underwear",
  panties: "panties-underwear",
  lingerie: "panties-underwear",
  "lower-body": "bottoms",
  legs: "bottoms",
  legwear: "stockings-socks",
  "stockings-and-socks": "stockings-socks",
  hosiery: "stockings-socks",
  footwear: "shoes-boots",
  "shoes-and-boots": "shoes-boots",
  shoes: "shoes-boots",
  boots: "shoes-boots",
  heels: "high-heels",
  "high-heel": "high-heels",
  "high-heels": "high-heels",
  hands: "arms-hands",
  "arms-and-hands": "arms-hands",
  headwear: "head",
  accessories: "accessories",
  "body-fx": "body-fx",
});
const HAIR_INSPECTOR_GROUPS = Object.freeze([
  {
    title: "Style & shape",
    detail: "Style, length, width, curls, segments, and density",
  },
  {
    title: "Color & materials",
    detail: "Root, tip, specular, and material appearance",
  },
  {
    title: "Physics & simulation",
    detail: "Simulation, collisions, gravity, and spring behavior",
  },
  {
    title: "Scalp & fit",
    detail: "Scalp geometry, offsets, fit, and cap visibility",
  },
]);
const CHARACTER_RECIPE_SCOPES = Object.freeze({
  "preset-appearance": ["Morphs", "Skin", "Hair", "Clothing", "Scale"],
  "preset-skin": ["Textures", "Materials", "Tone"],
  "preset-morphs": ["Body", "Face", "Expressions"],
  "preset-pose": ["Controllers", "Pose"],
  "preset-animation": ["Motion", "Timing"],
  "preset-breast-physics": ["Breast physics"],
  "preset-glute-physics": ["Glute physics"],
  "preset-general": ["Appearance", "Physics", "Optional pose"],
  "preset-plugins": ["Person plugins"],
});
const CHARACTER_SHORTCUT_GROUPS = Object.freeze([
  {
    label: "Appearance",
    entries: [
      ["preset-appearance", "Looks"],
      ["preset-hair", "Hair"],
      ["preset-skin", "Skin"],
      ["preset-morphs", "Morphs"],
    ],
  },
  {
    label: "Wardrobe",
    entries: [
      ["preset-clothing", "Outfits"],
      ["gender-items", "Items"],
      ["clothing-item-presets", "Item styles"],
    ],
  },
  {
    label: "Motion",
    entries: [
      ["preset-pose", "Pose"],
      ["preset-animation", "Animation"],
    ],
  },
  {
    label: "Body",
    entries: [
      ["preset-breast-physics", "Breast physics"],
      ["preset-glute-physics", "Glute physics"],
      ["preset-general", "General"],
    ],
  },
  {
    label: "Extensions",
    entries: [["preset-plugins", "Person plugins"]],
  },
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
    operation: "set-person-clothing",
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
    operation: "set-person-clothing",
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
  page: 1,
  query: "",
  type: "",
  packageState: "all",
  exactPackageId: "",
  packageContentsId: "",
  loading: false,
  requestController: null,
  searchTimer: null,
  token: "",
  managerAuthFailed: false,
  managerAuthFailedToken: "",
  managerAuthGeneration: 0,
  managerAuthNoticeShown: false,
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
  personRequestGeneration: 0,
  selectedPersonUid: "",
  personEquipment: null,
  personEquipmentError: null,
  personEquipmentLoading: false,
  personEquipmentKey: "",
  personEquipmentAttemptedKey: "",
  personEquipmentRequestedKey: "",
  personEquipmentRequestGeneration: 0,
  personEquipmentRequestController: null,
  equipmentExpandedSlots: new Set(),
  resourceDetailOpener: null,
  resourceDetailItem: null,
  resourceDependencyController: null,
  resourceDependencyGeneration: 0,
  resourceDependencyPage: 1,
  resourceDependencyReport: null,
  resourceDependencyFocus: false,
  resourceDetailRestore: null,
  resourceReturnContext: null,
  resourceReturnGeneration: 0,
  resourceReturnInFlight: false,
  pendingResourceConflict: null,
  packageChoiceInFlight: new Set(),
  packageConflictToast: null,
  personHair: null,
  personHairError: null,
  personHairLoading: false,
  personHairKey: "",
  personHairAttemptedKey: "",
  personHairRequestedKey: "",
  personHairRequestGeneration: 0,
  personHairRequestController: null,
  hairMutationInFlight: false,
  pendingHairMutation: null,
  clothingMutationInFlight: false,
  selectedAtomUid: "",
  atomTargetMode: "existing",
  newAtomUid: "",
  pendingAtomUid: "",
  atomMutationInFlight: false,
  cuaChoiceInFlight: false,
  applyingWorkspaceResources: new Set(),
  workspaceAction: null,
  workspaceCategories: [],
  workspaceCategoriesError: null,
  workspaceCategoriesSource: "fallback",
  workspaceCategoriesRetryAt: 0,
  selectedWorkspaceCategoryId: "scene",
  workspaceApplyMode: "replace",
  personMutationInFlight: false,
  timeline: null,
  timelineError: null,
  timelineInFlight: false,
  timelinePollTimer: null,
  timelineReceivedAt: 0,
  timelineRenderFrame: null,
  timelineLastCanvasDrawAt: 0,
  timelineControlInFlight: false,
  timelineSeekInFlight: false,
  timelinePendingSeek: null,
  timelinePreviewTime: null,
  selectedTimelineId: "",
  selectedTimelineSegmentId: "",
  selectedTimelineLayerId: "",
  selectedTimelineClipId: "",
  timelinePopout: false,
  sam3dStatus: null,
  sam3dStatusError: null,
  sam3dStatusInFlight: false,
  sam3dJobs: [],
  sam3dJobsError: null,
  sam3dJobsInFlight: false,
  sam3dSelectedJob: null,
  sam3dSelectedJobId: "",
  sam3dSelectedBodyIndex: 0,
  sam3dJobPollTimer: null,
  sam3dJobRequestGeneration: 0,
  sam3dSourceFile: null,
  sam3dSourceUrl: "",
  sam3dSourceImage: null,
  sam3dSourceWidth: 0,
  sam3dSourceHeight: 0,
  sam3dSourceJobId: "",
  sam3dModelChoice: SAM3D_DINOV3_MODEL_ID,
  sam3dBbox: { x: 0, y: 0, width: 100, height: 100 },
  sam3dBboxDrag: null,
  sam3dPreviewKind: "source",
  sam3dMutationInFlight: false,
  sam3dAppliedRevision: "",
  sam3dAppliedJobId: "",
  sam3dCapturePollAttempts: 0,
  sam3dCaptureReadyJobs: new Set(),
  sam3dSelectedCaptureRequestId: "",
  sam3dBodyProportions: null,
  sam3dBodyProportionsError: null,
  sam3dBodyProportionsInFlight: false,
  sam3dBodyProportionsJobId: "",
  sam3dBodyProportionsDirty: false,
  sam3dBodyProportionPollTimer: null,
  sam3dBodyProportionPollAttempts: 0,
  sam3dBodyProportionsPendingAction: "",
  sam3dHandoffTab: "morph",
  sam3dBodyProfiles: [],
  sam3dSelectedBodyProfileId: "",
  sam3dBodyReferences: [],
  sam3dBodyReferencesInitialized: false,
  sam3dManualFitMode: "estimator",
  sam3dManualShape: null,
  sam3dManualReferenceToken: "",
  sam3dManualOverlay: {
    panX: 0,
    panY: 0,
    scale: 1,
    opacity: 0.55,
  },
  sam3dManualOverlayDrag: null,
};

const elements = {};
const busyContents = new WeakMap();
const toastTimers = new WeakMap();

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheElements();
  captureToken();
  loadSam3dBodyProfiles();
  bindEvents();
  applyInitialRoute();
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
  if (app.managerAuthFailed) return;
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
    "timeline-tab-count",
    "sam3d-tab-state",
    "packages-tab-count",
    "access-tab-count",
    "library-view",
    "timeline-view",
    "sam3d-view",
    "access-view",
    "sam3d-runtime-badge",
    "sam3d-runtime-label",
    "sam3d-refresh-button",
    "sam3d-runtime-panel",
    "sam3d-runtime-title",
    "sam3d-runtime-message",
    "sam3d-runtime-action",
    "sam3d-file-input",
    "sam3d-drop-zone",
    "sam3d-clear-source",
    "sam3d-source-editor",
    "sam3d-canvas-wrap",
    "sam3d-source-canvas",
    "sam3d-canvas-hint",
    "sam3d-source-name",
    "sam3d-source-meta",
    "sam3d-known-vertical-fov",
    "sam3d-manual-bbox",
    "sam3d-bbox-fields",
    "sam3d-bbox-x",
    "sam3d-bbox-y",
    "sam3d-bbox-width",
    "sam3d-bbox-height",
    "sam3d-reset-bbox",
    "sam3d-model-select",
    "sam3d-model-note",
    "sam3d-run-button",
    "sam3d-job-progress",
    "sam3d-job-stage",
    "sam3d-job-message",
    "sam3d-job-percent",
    "sam3d-job-progress-bar",
    "sam3d-job-retry",
    "sam3d-result-panel",
    "sam3d-result-model",
    "sam3d-body-select",
    "sam3d-comparison",
    "sam3d-comparison-grid",
    "sam3d-preview-source",
    "sam3d-preview-overlay",
    "sam3d-preview-result",
    "sam3d-preview-image",
    "sam3d-preview-empty",
    "sam3d-preview-empty-title",
    "sam3d-preview-empty-detail",
    "sam3d-preview-caption",
    "sam3d-capture-history",
    "sam3d-capture-previous",
    "sam3d-capture-history-label",
    "sam3d-capture-next",
    "sam3d-handoff",
    "sam3d-handoff-morph-tab",
    "sam3d-handoff-pose-tab",
    "sam3d-proportions-panel",
    "sam3d-proportions-analyze",
    "sam3d-proportions-state",
    "sam3d-proportions-state-title",
    "sam3d-proportions-state-message",
    "sam3d-proportions-retry",
    "sam3d-proportions-results",
    "sam3d-proportions-confidence",
    "sam3d-shape-confidence",
    "sam3d-proportions-disagreement",
    "sam3d-proportions-measurements",
    "sam3d-proportions-morphs",
    "sam3d-shape-results",
    "sam3d-shape-measurements",
    "sam3d-shape-morphs",
    "sam3d-proportions-note",
    "sam3d-region-arms",
    "sam3d-region-legs",
    "sam3d-region-torso",
    "sam3d-region-widths",
    "sam3d-fit-strength",
    "sam3d-fit-strength-value",
    "sam3d-shape-region-breasts",
    "sam3d-shape-region-waist",
    "sam3d-shape-region-hips",
    "sam3d-shape-region-glutes",
    "sam3d-shape-region-thighs",
    "sam3d-shape-strength",
    "sam3d-shape-strength-value",
    "sam3d-proportions-apply",
    "sam3d-proportions-undo",
    "sam3d-reference-panel",
    "sam3d-reference-state",
    "sam3d-reference-show",
    "sam3d-reference-hide",
    "sam3d-profile-select",
    "sam3d-profile-new",
    "sam3d-profile-save",
    "sam3d-profile-delete",
    "sam3d-profile-note",
    "sam3d-morph-reference-gallery",
    "sam3d-morph-reference-count",
    "sam3d-morph-reference-note",
    "sam3d-manual-fit",
    "sam3d-manual-fit-estimator",
    "sam3d-manual-fit-manual",
    "sam3d-manual-fit-stage",
    "sam3d-manual-fit-image",
    "sam3d-manual-fit-svg",
    "sam3d-manual-fit-silhouette",
    "sam3d-manual-fit-body",
    "sam3d-manual-fit-breast-left",
    "sam3d-manual-fit-breast-right",
    "sam3d-manual-fit-empty",
    "sam3d-manual-reference-select",
    "sam3d-manual-auto-align",
    "sam3d-manual-overlay-reset",
    "sam3d-manual-overlay-scale",
    "sam3d-manual-overlay-scale-value",
    "sam3d-manual-overlay-opacity",
    "sam3d-manual-overlay-opacity-value",
    "sam3d-manual-shape-breast-size",
    "sam3d-manual-shape-breast-size-value",
    "sam3d-manual-shape-breast-spacing",
    "sam3d-manual-shape-breast-spacing-value",
    "sam3d-manual-shape-waist-width",
    "sam3d-manual-shape-waist-width-value",
    "sam3d-manual-shape-hip-width",
    "sam3d-manual-shape-hip-width-value",
    "sam3d-manual-shape-glute-projection",
    "sam3d-manual-shape-glute-projection-value",
    "sam3d-manual-shape-thigh-size",
    "sam3d-manual-shape-thigh-size-value",
    "sam3d-manual-shape-reset",
    "sam3d-manual-fit-update",
    "sam3d-apply-panel",
    "sam3d-revision",
    "sam3d-person-target",
    "sam3d-camera-target",
    "sam3d-camera-fov",
    "sam3d-person-height",
    "sam3d-aspect-ratio",
    "sam3d-output-resolution",
    "sam3d-image-format",
    "sam3d-keep-reference",
    "sam3d-apply-note",
    "sam3d-apply-button",
    "sam3d-undo-button",
    "sam3d-capture-button",
    "sam3d-history-count",
    "sam3d-history-list",
    "timeline-connection-state",
    "timeline-connection-label",
    "timeline-instance",
    "timeline-popout-button",
    "timeline-state-panel",
    "timeline-state-title",
    "timeline-state-message",
    "timeline-retry-button",
    "timeline-editor",
    "timeline-segment-select",
    "timeline-layer-select",
    "timeline-clip-select",
    "timeline-revision",
    "timeline-clip-count",
    "timeline-outline-list",
    "timeline-track-summary",
    "timeline-duration-summary",
    "timeline-canvas-scroll",
    "timeline-canvas",
    "timeline-canvas-empty",
    "timeline-limit-note",
    "timeline-inspector-facts",
    "timeline-capability-list",
    "timeline-previous-frame",
    "timeline-reset",
    "timeline-play-pause",
    "timeline-stop",
    "timeline-next-frame",
    "timeline-timecode",
    "timeline-duration-timecode",
    "timeline-scrubber",
    "timeline-speed",
    "timeline-speed-value",
    "timeline-weight",
    "timeline-weight-value",
    "timeline-lock",
    "asset-workspace",
    "person-context",
    "person-target",
    "select-person-button",
    "add-person-button",
    "person-live-state",
    "person-live-title",
    "person-live-detail",
    "character-sheet",
    "character-sheet-title",
    "character-sheet-summary",
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
    "hair-studio-summary",
    "hair-layer-list",
    "hair-inspector-groups",
    "hair-warning",
    "character-recipe",
    "character-recipe-monogram",
    "character-recipe-person",
    "character-recipe-gender",
    "character-recipe-title",
    "character-recipe-description",
    "character-recipe-scopes",
    "character-recipe-note",
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
    "library-pagination",
    "page-previous",
    "page-status",
    "page-next",
    "add-pin-button",
    "pins-count",
    "leases-count",
    "pins-list",
    "leases-list",
    "deactivate-button",
    "toast-region",
    "resource-detail-dialog",
    "resource-detail-close",
    "resource-detail-eyebrow",
    "resource-detail-title",
    "resource-detail-content",
    "resource-return-context",
    "resource-return-button",
    "resource-return-title",
    "resource-return-detail",
    "resource-return-dismiss",
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
    app.managerAuthGeneration += 1;
    app.managerAuthFailed = false;
    app.managerAuthFailedToken = "";
    app.managerAuthNoticeShown = false;
    try {
      sessionStorage.setItem(TOKEN_KEY, supplied);
    } catch (_error) {
      // Keep the token in memory when browser storage is unavailable.
    }
    const cleanUrl = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState(null, document.title, cleanUrl);
  }
}

function applyInitialRoute() {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  app.timelinePopout =
    requestedView === "timeline" && params.get("popout") === "compact";
  if (app.timelinePopout) {
    document.body.classList.add("timeline-popout");
    document.title = "VAM-PIP Timeline";
  }
  if (requestedView === "timeline" || app.timelinePopout) {
    setView("timeline");
  } else if (requestedView === "sam3d") {
    setView("sam3d");
  }
}

function updateViewRoute(view) {
  const url = new URL(window.location.href);
  if (view === "timeline" || view === "sam3d") {
    url.searchParams.set("view", view);
  } else if (!app.timelinePopout) {
    url.searchParams.delete("view");
    url.searchParams.delete("popout");
  }
  window.history.replaceState(null, document.title, url);
}

function openTimelinePopout() {
  const url = new URL(window.location.href);
  url.searchParams.set("view", "timeline");
  url.searchParams.set("popout", "compact");
  if (app.token) url.hash = `token=${encodeURIComponent(app.token)}`;
  const popup = window.open(
    url,
    "vampip-timeline",
    "popup=yes,width=1180,height=440,resizable=yes,scrollbars=yes",
  );
  if (!popup) {
    toast(
      "Pop-out was blocked",
      "Allow pop-ups for this local VAM-PIP page, then try again.",
      "error",
    );
    return;
  }
  popup.focus();
}

function bindEvents() {
  elements.refreshButton.addEventListener("click", () =>
    refreshAll({ force: true, retryEquipment: true }),
  );
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
  elements.resourceDetailClose.addEventListener("click", () =>
    elements.resourceDetailDialog.close("close"),
  );
  elements.resourceDetailDialog.addEventListener(
    "click",
    handleResourceDetailBackdrop,
  );
  elements.resourceDetailDialog.addEventListener(
    "close",
    handleResourceDetailClose,
  );
  elements.resourceReturnButton.addEventListener(
    "click",
    returnToResourceContext,
  );
  elements.resourceReturnDismiss.addEventListener(
    "click",
    dismissResourceReturnContext,
  );
  elements.sam3dRefreshButton.addEventListener("click", () =>
    loadSam3dWorkspace({ force: true }),
  );
  elements.sam3dRuntimeAction.addEventListener("click", () =>
    loadSam3dWorkspace({ force: true }),
  );
  elements.sam3dFileInput.addEventListener("change", () => {
    const [file] = Array.from(elements.sam3dFileInput.files || []);
    if (file) chooseSam3dSource(file);
  });
  for (const eventName of ["dragenter", "dragover"]) {
    elements.sam3dDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.sam3dDropZone.classList.add("is-dragover");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    elements.sam3dDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.sam3dDropZone.classList.remove("is-dragover");
    });
  }
  elements.sam3dDropZone.addEventListener("drop", (event) => {
    const [file] = Array.from(event.dataTransfer?.files || []);
    if (file) chooseSam3dSource(file);
  });
  elements.sam3dClearSource.addEventListener("click", clearSam3dSource);
  elements.sam3dManualBbox.addEventListener("change", () => {
    elements.sam3dBboxFields.disabled = !elements.sam3dManualBbox.checked;
    elements.sam3dCanvasHint.hidden = !elements.sam3dManualBbox.checked;
    drawSam3dSourceCanvas();
  });
  for (const field of [
    elements.sam3dBboxX,
    elements.sam3dBboxY,
    elements.sam3dBboxWidth,
    elements.sam3dBboxHeight,
  ]) {
    field.addEventListener("input", readSam3dBboxFields);
  }
  elements.sam3dResetBbox.addEventListener("click", resetSam3dBbox);
  elements.sam3dSourceCanvas.addEventListener(
    "pointerdown",
    beginSam3dBboxDrag,
  );
  elements.sam3dSourceCanvas.addEventListener(
    "pointermove",
    continueSam3dBboxDrag,
  );
  elements.sam3dSourceCanvas.addEventListener("pointerup", finishSam3dBboxDrag);
  elements.sam3dSourceCanvas.addEventListener(
    "pointercancel",
    finishSam3dBboxDrag,
  );
  elements.sam3dRunButton.addEventListener("click", createSam3dJob);
  elements.sam3dModelSelect.addEventListener("change", () => {
    app.sam3dModelChoice = elements.sam3dModelSelect.value;
    renderSam3dRuntime();
  });
  elements.sam3dJobRetry.addEventListener("click", retrySam3dJob);
  elements.sam3dHistoryList.addEventListener("click", (event) => {
    const jobButton = event.target.closest("[data-sam3d-job-id]");
    if (jobButton) selectSam3dJob(jobButton.dataset.sam3dJobId);
  });
  elements.sam3dComparisonGrid.addEventListener("click", (event) => {
    const jobButton = event.target.closest("[data-sam3d-compare-job-id]");
    if (jobButton) {
      selectSam3dJob(jobButton.dataset.sam3dCompareJobId);
    }
  });
  elements.sam3dBodySelect.addEventListener("change", () =>
    selectSam3dBody(elements.sam3dBodySelect.value),
  );
  for (const previewButton of [
    elements.sam3dPreviewSource,
    elements.sam3dPreviewOverlay,
    elements.sam3dPreviewResult,
  ]) {
    previewButton.addEventListener("click", () =>
      setSam3dPreview(previewButton.dataset.sam3dPreview),
    );
  }
  elements.sam3dCapturePrevious.addEventListener("click", () =>
    moveSam3dCapture(-1),
  );
  elements.sam3dCaptureNext.addEventListener("click", () =>
    moveSam3dCapture(1),
  );
  for (const tab of [
    elements.sam3dHandoffMorphTab,
    elements.sam3dHandoffPoseTab,
  ]) {
    tab.addEventListener("click", () =>
      setSam3dHandoffTab(tab.dataset.sam3dHandoffTab),
    );
  }
  elements.sam3dProfileSelect.addEventListener(
    "change",
    selectSam3dBodyProfile,
  );
  elements.sam3dProfileNew.addEventListener(
    "click",
    createSam3dBodyProfile,
  );
  elements.sam3dProfileSave.addEventListener(
    "click",
    saveSam3dBodyProfile,
  );
  elements.sam3dProfileDelete.addEventListener(
    "click",
    deleteSam3dBodyProfile,
  );
  elements.sam3dMorphReferenceGallery.addEventListener(
    "click",
    (event) => {
      const candidate = event.target.closest("[data-sam3d-body-reference]");
      if (candidate && !candidate.disabled) {
        toggleSam3dBodyReference(candidate.dataset.sam3dBodyReference);
      }
    },
  );
  elements.sam3dManualFitEstimator.addEventListener("click", () =>
    setSam3dManualFitMode("estimator"),
  );
  elements.sam3dManualFitManual.addEventListener("click", () =>
    setSam3dManualFitMode("manual"),
  );
  elements.sam3dManualReferenceSelect.addEventListener("change", () => {
    app.sam3dManualReferenceToken = String(
      elements.sam3dManualReferenceSelect.value || "",
    );
    resetSam3dManualOverlay();
  });
  elements.sam3dManualAutoAlign.addEventListener(
    "click",
    autoAlignSam3dManualOverlay,
  );
  elements.sam3dManualOverlayReset.addEventListener(
    "click",
    resetSam3dManualOverlay,
  );
  elements.sam3dManualOverlayScale.addEventListener(
    "input",
    readSam3dManualOverlayControls,
  );
  elements.sam3dManualOverlayOpacity.addEventListener(
    "input",
    readSam3dManualOverlayControls,
  );
  for (const key of SAM3D_MANUAL_SHAPE_KEYS) {
    sam3dManualShapeControl(key).addEventListener(
      "input",
      handleSam3dManualShapeInput,
    );
  }
  elements.sam3dManualShapeReset.addEventListener(
    "click",
    resetSam3dManualShape,
  );
  elements.sam3dManualFitUpdate.addEventListener(
    "click",
    analyzeSam3dBodyProportions,
  );
  elements.sam3dManualFitStage.addEventListener(
    "pointerdown",
    beginSam3dManualOverlayDrag,
  );
  elements.sam3dManualFitStage.addEventListener(
    "pointermove",
    continueSam3dManualOverlayDrag,
  );
  elements.sam3dManualFitStage.addEventListener(
    "pointerup",
    finishSam3dManualOverlayDrag,
  );
  elements.sam3dManualFitStage.addEventListener(
    "pointercancel",
    finishSam3dManualOverlayDrag,
  );
  elements.sam3dManualFitStage.addEventListener(
    "keydown",
    nudgeSam3dManualOverlay,
  );
  elements.sam3dProportionsAnalyze.addEventListener(
    "click",
    analyzeSam3dBodyProportions,
  );
  elements.sam3dProportionsRetry.addEventListener(
    "click",
    analyzeSam3dBodyProportions,
  );
  for (const region of SAM3D_BODY_PROPORTION_REGIONS) {
    sam3dBodyProportionRegionControl(region).addEventListener(
      "change",
      () => {
        markSam3dBodyProportionsDirty();
        renderSam3dBodyReferenceGallery();
      },
    );
  }
  for (const region of SAM3D_BODY_SHAPE_REGIONS) {
    sam3dBodyShapeRegionControl(region).addEventListener(
      "change",
      markSam3dBodyProportionsDirty,
    );
  }
  elements.sam3dFitStrength.addEventListener("input", () => {
    elements.sam3dFitStrengthValue.value =
      `${Math.round(Number(elements.sam3dFitStrength.value) || 0)}%`;
    markSam3dBodyProportionsDirty();
  });
  elements.sam3dShapeStrength.addEventListener("input", () => {
    elements.sam3dShapeStrengthValue.value =
      `${Math.round(Number(elements.sam3dShapeStrength.value) || 0)}%`;
    markSam3dBodyProportionsDirty();
  });
  elements.sam3dProportionsApply.addEventListener(
    "click",
    applySam3dBodyProportions,
  );
  elements.sam3dProportionsUndo.addEventListener(
    "click",
    undoSam3dBodyProportions,
  );
  elements.sam3dReferenceShow.addEventListener(
    "click",
    showSam3dReference,
  );
  elements.sam3dReferenceHide.addEventListener(
    "click",
    hideSam3dReference,
  );
  for (const target of [
    elements.sam3dPersonTarget,
    elements.sam3dCameraTarget,
    elements.sam3dCameraFov,
    elements.sam3dPersonHeight,
    elements.sam3dOutputResolution,
    elements.sam3dImageFormat,
  ]) {
    target.addEventListener("change", () => {
      renderSam3dReferenceState();
      renderSam3dApplyState();
    });
  }
  elements.sam3dPersonTarget.addEventListener("change", () => {
    app.sam3dBodyProportions = null;
    app.sam3dBodyProportionsError = null;
    app.sam3dBodyProportionsDirty = false;
    renderSam3dBodyProportions();
  });
  elements.sam3dKeepReference.addEventListener("change", () => {
    renderSam3dReferenceState();
    renderSam3dApplyState();
  });
  elements.sam3dAspectRatio.addEventListener("change", () => {
    renderSam3dResolutionOptions();
    renderSam3dApplyState();
  });
  elements.sam3dApplyButton.addEventListener("click", applySam3dResult);
  elements.sam3dUndoButton.addEventListener("click", undoSam3dApply);
  elements.sam3dCaptureButton.addEventListener("click", captureSam3dResult);
  elements.timelineInstance.addEventListener(
    "change",
    handleTimelineInstanceChange,
  );
  elements.timelineSegmentSelect.addEventListener(
    "change",
    handleTimelineSegmentChange,
  );
  elements.timelineLayerSelect.addEventListener(
    "change",
    handleTimelineLayerChange,
  );
  elements.timelineClipSelect.addEventListener(
    "change",
    handleTimelineClipChange,
  );
  elements.timelinePopoutButton.addEventListener("click", openTimelinePopout);
  elements.timelineRetryButton.addEventListener("click", () =>
    loadTimeline({ force: true }),
  );
  for (const control of [
    elements.timelinePreviousFrame,
    elements.timelineReset,
    elements.timelinePlayPause,
    elements.timelineStop,
    elements.timelineNextFrame,
  ]) {
    control.addEventListener("click", () =>
      sendTimelineControl(control.dataset.timelineOp),
    );
  }
  elements.timelineScrubber.addEventListener("input", handleTimelineScrubInput);
  elements.timelineScrubber.addEventListener("change", handleTimelineScrubCommit);
  elements.timelineSpeed.addEventListener("input", () => {
    elements.timelineSpeedValue.value =
      `${numberOr(elements.timelineSpeed.value, 1).toFixed(2)}×`;
  });
  elements.timelineSpeed.addEventListener("change", () =>
    sendTimelineControl("setSpeed", {
      value: numberOr(elements.timelineSpeed.value, 1),
    }),
  );
  elements.timelineWeight.addEventListener("input", () => {
    elements.timelineWeightValue.value =
      `${Math.round(numberOr(elements.timelineWeight.value, 1) * 100)}%`;
  });
  elements.timelineWeight.addEventListener("change", () =>
    sendTimelineControl("setWeight", {
      value: numberOr(elements.timelineWeight.value, 1),
    }),
  );
  elements.timelineLock.addEventListener("change", () =>
    sendTimelineControl("setLocked", {
      value: elements.timelineLock.checked,
    }),
  );
  elements.timelineCanvas.addEventListener("click", handleTimelineCanvasClick);
  window.addEventListener("resize", () => {
    if (app.view === "timeline") drawTimelineCanvas();
    if (app.view === "sam3d") drawSam3dSourceCanvas();
  });
  elements.autoReconcile.addEventListener("change", updateAutoReconcile);
  elements.pagePrevious.addEventListener("click", () =>
    changeLibraryPage(app.page - 1),
  );
  elements.pageNext.addEventListener("click", () =>
    changeLibraryPage(app.page + 1),
  );
  elements.clearFilters.addEventListener("click", clearFilters);
  elements.emptyAction.addEventListener("click", handleEmptyAction);
  elements.personTarget.addEventListener("change", () => {
    app.selectedPersonUid = elements.personTarget.value;
    app.equipmentExpandedSlots.clear();
    syncPersonEquipment({ quiet: true });
    syncPersonHair({ quiet: true, retry: true });
    renderPersonContext();
    if (app.view === "workspace") {
      if (isIndividualClothingCategory()) {
        loadLibrary({ preservePage: true });
      } else {
        renderLibrary();
      }
    }
  });
  elements.selectPersonButton.addEventListener("click", selectPersonInVam);
  elements.addPersonButton.addEventListener("click", addPersonInVam);
  elements.characterShortcuts.addEventListener("click", (event) => {
    const shortcut = event.target.closest("[data-character-category]");
    if (!shortcut || shortcut.disabled) return;
    setWorkspaceCategory(shortcut.dataset.characterCategory);
  });
  elements.characterSheet.addEventListener("click", (event) => {
    const expandButton = event.target.closest("[data-equipment-expand]");
    if (expandButton) {
      const slotId = expandButton.dataset.equipmentExpand;
      if (app.equipmentExpandedSlots.has(slotId)) {
        app.equipmentExpandedSlots.delete(slotId);
      } else {
        app.equipmentExpandedSlots.add(slotId);
      }
      renderCharacterSheet();
      return;
    }
    const removeButton = event.target.closest("[data-equipment-remove]");
    if (removeButton && !removeButton.disabled) {
      removeEquippedItem(removeButton.dataset.equipmentRemove, removeButton);
      return;
    }
    const hairButton = event.target.closest("[data-hair-disable]");
    if (hairButton && !hairButton.disabled) {
      disableHairLayer(hairButton.dataset.hairDisable, hairButton);
    }
  });
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
    app.exactPackageId = "";
    if (app.requestController) app.requestController.abort();
    app.searchTimer = window.setTimeout(() => {
      app.query = elements.searchInput.value.trim();
      loadLibrary();
    }, 280);
    updateClearFilters();
  });

  elements.typeFilter.addEventListener("change", () => {
    app.exactPackageId = "";
    app.type = elements.typeFilter.value;
    updateClearFilters();
    loadLibrary();
  });

  elements.stateFilter.addEventListener("change", () => {
    app.exactPackageId = "";
    app.packageState = elements.stateFilter.value;
    updateClearFilters();
    loadLibrary();
  });

  for (const tab of elements.viewTabs) {
    tab.addEventListener("click", () => {
      if (
        tab.dataset.view === "resources" &&
        app.view === "resources" &&
        app.packageContentsId
      ) {
        exitPackageContentsScope();
        return;
      }
      setView(tab.dataset.view);
    });
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
      !anyModalOpen() &&
      !["access", "timeline", "sam3d"].includes(app.view)
    ) {
      event.preventDefault();
      elements.searchInput.focus();
    }
    if (event.key === "Escape" && document.body.classList.contains("tools-open")) {
      closeMobileTools();
    }
  });
}

function anyModalOpen() {
  return Boolean(
    elements.confirmDialog?.open ||
      elements.resourceDetailDialog?.open,
  );
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
  if (app.managerAuthFailed || app.activityTimer !== null) return;
  const tick = async () => {
    app.activityTimer = null;
    if (app.managerAuthFailed) return;
    try {
      await loadActivity();
    } catch (_error) {
      app.activityPollFailed = true;
      app.activityRefreshNeeded = true;
      setConnection("error", "Unavailable");
    } finally {
      const delay =
        operationIsBusy() || workspaceActionIsActive() ? 650 : 1500;
      if (!app.managerAuthFailed) {
        app.activityTimer = window.setTimeout(tick, delay);
      }
    }
  };
  app.activityTimer = window.setTimeout(tick, 650);
}

function stopActivityPolling() {
  if (app.activityTimer === null) return;
  window.clearTimeout(app.activityTimer);
  app.activityTimer = null;
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
    if (instanceChanged && workspaceActionIsActive()) {
      finishWorkspaceActionFeedback(
        app.workspaceAction,
        false,
        "The VAM-PIP manager restarted before this load finished. Retry the asset.",
      );
    } else {
      syncWorkspaceActionActivity(app.activity);
    }
    app.activityPollFailed = false;
    if (recovered || instanceChanged) {
      app.activityRefreshNeeded = true;
    }
    renderLiveState(app.status || {});
    const workspaceCategory =
      app.view === "workspace" ? currentWorkspaceCategory() : null;
    const bodyShapeCalibrationPreparing =
      app.view === "sam3d" &&
      app.sam3dHandoffTab === "morph" &&
      sam3dBodyShapeCalibrationState().preparing;
    const shouldPollScene =
      workspaceActionIsActive() ||
      Boolean(app.pendingHairMutation) ||
      snapshotBridgeBusy() ||
      bodyShapeCalibrationPreparing ||
      Boolean(
        workspaceCategory &&
          (workspaceCategory.liveAction ||
            categoryUsesPersonContext(workspaceCategory) ||
            ATOM_TARGET_KINDS.has(workspaceCategory.targetKind)),
      );
    const defaultScenePollInterval =
      workspaceActionIsActive() || app.pendingHairMutation ? 900 : 3000;
    const scenePollInterval = bodyShapeCalibrationPreparing
      ? SAM3D_POLL_MS
      : defaultScenePollInterval;
    if (
      shouldPollScene &&
      Date.now() - app.personPollAt > scenePollInterval
    ) {
      loadPersons({ quiet: true });
    }
    if (
      app.workspaceCategoriesError &&
      !app.refreshing &&
      Date.now() - app.workspaceCategoriesRetryAt > 5000
    ) {
      app.workspaceCategoriesRetryAt = Date.now();
      scheduleRefresh = true;
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
    const previousOperation = previous?.operation || {};
    const activityChanged =
      operationIsBusy(previous) !== busy ||
      operationKey(previousOperation) !== key;
    if (app.view === "workspace" && activityChanged) {
      renderLibrary();
    }
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

function beginPersonSnapshotRequest() {
  app.personRequestGeneration += 1;
  return app.personRequestGeneration;
}

function personSnapshotRequestIsCurrent(generation) {
  return generation === app.personRequestGeneration;
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
  if (app.managerAuthFailed) return;
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
  const sceneRequestGeneration = beginPersonSnapshotRequest();
  const sceneRequest = fetchLiveSceneSnapshot();
  const timelineRequest = app.timelineInFlight
    ? Promise.resolve(null)
    : TimelineClient.snapshot();
  try {
    const [
      statusResult,
      facetResult,
      sessionPluginResult,
      sceneResult,
      workspaceCategoriesResult,
      timelineResult,
    ] =
      await Promise.allSettled([
        api("/api/status"),
        api("/api/catalog/facets"),
        api("/api/session-plugins"),
        sceneRequest,
        fetchWorkspaceCategories(),
        timelineRequest,
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
      acceptPersonSnapshot(
        sceneResult.value || {},
        sceneRequestGeneration,
      );
    } else {
      acceptPersonSnapshotError(
        sceneResult.reason,
        sceneRequestGeneration,
      );
    }
    if (workspaceCategoriesResult.status === "fulfilled") {
      acceptWorkspaceCategories(workspaceCategoriesResult.value);
    } else {
      app.workspaceCategoriesError = workspaceCategoriesResult.reason;
      app.workspaceCategoriesRetryAt = Date.now();
      if (!app.workspaceCategories.length) {
        app.workspaceCategories = fallbackWorkspaceCategories();
      }
    }
    renderWorkspaceCategoryNavigation();
    renderWorkspaceCategorySummary();
    if (
      timelineResult.status === "fulfilled" &&
      timelineResult.value
    ) {
      acceptTimelineSnapshot(timelineResult.value);
      renderTimeline();
    } else {
      app.timelineError = timelineResult.reason;
      if (app.view === "timeline") renderTimeline();
    }
    await syncPersonEquipment({
      quiet: true,
      retry: Boolean(options.retryEquipment),
    });
    await syncPersonHair({
      quiet: true,
      retry: Boolean(options.retryEquipment),
    });

    if (["resources", "workspace", "packages"].includes(app.view)) {
      await loadLibrary({ preservePage: true });
    }
  } catch (error) {
    setConnection("error", "Unavailable");
    showErrorState(error);
    if (!isManagerAuthFailure(error)) {
      toast("Could not reach VAM-PIP", errorMessage(error), "error");
    }
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
  app.workspaceCategoriesRetryAt = 0;
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

function categoryUsesPersonContext(category = currentWorkspaceCategory()) {
  return Boolean(category && PERSON_TARGET_KINDS.has(category.targetKind));
}

function characterSheetMode(category = currentWorkspaceCategory()) {
  if (!categoryUsesPersonContext(category)) return "hidden";
  if (HAIR_CATEGORY_IDS.has(category.id)) return "hair";
  if (WARDROBE_CATEGORY_IDS.has(category.id)) return "wardrobe";
  return "recipe";
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
  } else if (!note && category.operation === "set-person-clothing") {
    note =
      "Wear and remove actions use this Person’s revisioned live clothing state; locked items remain controlled by VaM.";
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
  elements.personContext.hidden = !categoryUsesPersonContext(category);
  elements.atomContext.hidden = !ATOM_TARGET_KINDS.has(category.targetKind);
  renderPersonContext();
  renderAtomContext();
}

function setWorkspaceCategory(categoryId) {
  const category = ensureWorkspaceCategories().find(
    (candidate) => candidate.id === categoryId,
  );
  if (!category || category.id === app.selectedWorkspaceCategoryId) return;
  if (elements.resourceDetailDialog?.open) {
    elements.resourceDetailDialog.close("category-change");
  }
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
    categoryUsesPersonContext(category) ||
    ATOM_TARGET_KINDS.has(category.targetKind)
  ) {
    loadPersons({ quiet: true });
    if (categoryUsesPersonContext(category)) {
      syncPersonEquipment({ quiet: true });
      syncPersonHair({ quiet: true });
    }
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
      Boolean(person.clothing?.ready),
      person.clothing?.revision || "",
      person.clothing?.gender || "",
      numberOr(person.clothing?.activeCount, 0),
      numberOr(person.clothing?.lockedCount, 0),
      Boolean(person.clothing?.truncated),
      Boolean(person.hair?.ready),
      person.hair?.revision || "",
      numberOr(person.hair?.activeCount, 0),
      numberOr(person.hair?.lockedCount, 0),
      Boolean(person.hair?.truncated),
    ]),
    atoms: atomList(snapshot).map((atom) => [
      atom.uid,
      atom.type,
      Boolean(atom.selected),
      atom.cua || null,
    ]),
    bridge: [
      snapshot.bridge?.requestId || "",
      snapshot.bridge?.state || "",
      snapshot.bridge?.message || "",
    ],
  });
}

function reconcilePendingHairMutation(snapshot = app.person || {}) {
  const pending = app.pendingHairMutation;
  if (!pending) return false;
  const person = personList(snapshot).find(
    (candidate) => candidate.uid === pending.targetUid,
  );
  if (snapshot.available && !person) {
    app.pendingHairMutation = null;
    return true;
  }
  const revision = String(person?.hair?.revision || "").trim().toLowerCase();
  if (
    person?.hair?.ready === true &&
    /^[0-9a-f]{32}$/.test(revision) &&
    revision !== pending.revision
  ) {
    app.pendingHairMutation = null;
    return true;
  }
  const bridgeState = String(snapshot?.bridge?.state || "").toLowerCase();
  const bridgeRequest = String(
    snapshot?.bridge?.requestId || snapshot?.bridge?.request_id || "",
  ).trim();
  if (
    bridgeState === "error" &&
    Boolean(pending.requestId) &&
    bridgeRequest === pending.requestId
  ) {
    app.pendingHairMutation = null;
    return true;
  }
  return false;
}

function acceptPersonSnapshot(snapshot, generation) {
  if (
    generation !== undefined &&
    !personSnapshotRequestIsCurrent(generation)
  ) {
    return false;
  }
  if (!snapshot || typeof snapshot !== "object") snapshot = {};
  app.person = snapshot;
  app.personError = null;
  app.personPollAt = Date.now();
  syncWorkspaceActionSnapshot(snapshot);

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
  reconcilePendingHairMutation(snapshot);

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
  return true;
}

function acceptPersonSnapshotError(error, generation) {
  if (
    generation !== undefined &&
    !personSnapshotRequestIsCurrent(generation)
  ) {
    return false;
  }
  app.personError = error;
  app.personPollAt = Date.now();
  return true;
}

function selectedPersonClothing(snapshot = app.person || {}) {
  const person = selectedPersonSnapshot(snapshot);
  return person?.clothing && typeof person.clothing === "object"
    ? person.clothing
    : null;
}

function selectedPersonHair(snapshot = app.person || {}) {
  const person = selectedPersonSnapshot(snapshot);
  return person?.hair && typeof person.hair === "object"
    ? person.hair
    : null;
}

function personEquipmentIdentity(snapshot = app.person || {}) {
  const targetUid = String(app.selectedPersonUid || "").trim();
  const clothing = selectedPersonClothing(snapshot);
  const revision = String(clothing?.revision || "").trim().toLowerCase();
  if (
    !targetUid ||
    clothing?.ready !== true ||
    !/^[0-9a-f]{32}$/.test(revision)
  ) {
    return null;
  }
  return {
    targetUid,
    revision,
    key: `${targetUid}\u0000${revision}`,
  };
}

function personEquipmentRequestIsCurrent(
  generation,
  targetUid,
  revision,
) {
  const identity = personEquipmentIdentity();
  return Boolean(
    generation === app.personEquipmentRequestGeneration &&
      identity &&
      identity.targetUid === targetUid &&
      identity.revision === revision,
  );
}

function cancelPersonEquipmentRequest() {
  if (app.personEquipmentRequestController) {
    app.personEquipmentRequestController.abort();
    app.personEquipmentRequestController = null;
  }
  app.personEquipmentRequestGeneration += 1;
  app.personEquipmentLoading = false;
  app.personEquipmentRequestedKey = "";
}

function clearPersonEquipment() {
  cancelPersonEquipmentRequest();
  app.personEquipment = null;
  app.personEquipmentError = null;
  app.personEquipmentKey = "";
  app.personEquipmentAttemptedKey = "";
  renderCharacterSheet();
}

function safePresentationLabel(value, fallback) {
  const label = String(value || "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
  if (
    !label ||
    /^[a-z]:[\\/]/i.test(label) ||
    /^[/\\]/.test(label) ||
    /(?:^|[\\/])(?:Custom|AddonPackages)(?:[\\/]|$)/i.test(label) ||
    /\.var(?::|[\\/]|$)/i.test(label)
  ) {
    return fallback;
  }
  return label;
}

function safeOpaqueKey(value, fallback) {
  const key = String(value || "").trim();
  return /^[a-z0-9_-]{1,128}$/i.test(key) ? key : fallback;
}

function safeHairActionKey(value) {
  const key = String(value || "").trim();
  return /^hair-[0-9a-f]{24}$/.test(key) ? key : "";
}

function normalizePersonEquipment(payload, targetUid, revision) {
  const document =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const items = [];
  const seen = new Set();
  for (const rawItem of asArray(document.items)) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const resourceId = integerValue(rawItem.id ?? rawItem.resource_id);
    const identified = resourceId !== null && resourceId > 0;
    const actionable =
      identified && booleanValue(rawItem.actionable, true);
    const presentationIndex = items.length + 1;
    const normalizedItem = identified
      ? {
          ...rawItem,
          id: resourceId,
          actionable,
          worn: true,
          clothing_locked: booleanValue(
            rawItem.clothing_locked ?? rawItem.locked,
            false,
          ),
          clothing_compatible: true,
          clothing_revision: String(
            rawItem.clothing_revision || document.revision || revision,
          ).toLowerCase(),
        }
      : {
          id: null,
          actionable: false,
          presentation_key: safeOpaqueKey(
            rawItem.key ?? rawItem.presentation_key,
            `item-${presentationIndex}`,
          ),
          display_name: safePresentationLabel(
            rawItem.display_name ?? rawItem.name,
            `In-game clothing ${presentationIndex}`,
          ),
          tags: normalizeTags(rawItem.tags).slice(0, 16),
          equipment_slot: String(
            rawItem.equipment_slot ?? rawItem.slot ?? "",
          ).slice(0, 64),
          worn: true,
          clothing_locked: booleanValue(
            rawItem.clothing_locked ?? rawItem.locked,
            false,
          ),
          clothing_compatible: true,
          clothing_revision: String(
            document.revision || revision,
          ).toLowerCase(),
        };
    const itemKey = equipmentItemKey(normalizedItem);
    if (!itemKey || seen.has(itemKey)) continue;
    seen.add(itemKey);
    items.push(normalizedItem);
  }

  const activeCount = Math.max(
    0,
    numberOr(document.active_count ?? document.activeCount, items.length),
  );
  const lockedCount = Math.max(
    0,
    numberOr(
      document.locked_count ?? document.lockedCount,
      items.filter((item) => item.clothing_locked).length,
    ),
  );
  const identifiedItems = items.filter(
    (item) => integerValue(item.id) !== null,
  ).length;
  const identifiedCount = Math.max(
    identifiedItems,
    numberOr(
      document.identified_count ?? document.identifiedCount,
      identifiedItems,
    ),
  );
  const unidentifiedCount = Math.max(
    0,
    numberOr(
      document.unidentified_count ??
        document.unidentifiedCount ??
        document.unmatched_count ??
        document.unmatchedCount,
      activeCount - identifiedCount,
    ),
  );
  return {
    targetUid,
    revision,
    ready: booleanValue(document.ready, true),
    gender: String(document.gender || "Unknown"),
    activeCount,
    lockedCount,
    identifiedCount,
    unidentifiedCount,
    truncated: booleanValue(document.truncated, false),
    items,
  };
}

async function syncPersonEquipment({ quiet = true, retry = false } = {}) {
  if (
    app.view !== "workspace" ||
    characterSheetMode() !== "wardrobe"
  ) {
    return app.personEquipment;
  }

  const identity = personEquipmentIdentity();
  if (!identity) {
    if (
      app.personEquipment ||
      app.personEquipmentError ||
      app.personEquipmentLoading ||
      app.personEquipmentAttemptedKey
    ) {
      clearPersonEquipment();
    } else {
      renderCharacterSheet();
    }
    return null;
  }
  if (
    app.personEquipmentAttemptedKey &&
    app.personEquipmentAttemptedKey !== identity.key
  ) {
    app.personEquipmentAttemptedKey = "";
  }
  if (
    !retry &&
    app.personEquipmentAttemptedKey === identity.key
  ) {
    return app.personEquipment;
  }
  if (
    app.personEquipmentLoading &&
    app.personEquipmentRequestedKey === identity.key
  ) {
    return null;
  }

  if (app.personEquipmentRequestController) {
    app.personEquipmentRequestController.abort();
  }
  const controller = new AbortController();
  const generation = app.personEquipmentRequestGeneration + 1;
  app.personEquipmentRequestGeneration = generation;
  app.personEquipmentRequestController = controller;
  app.personEquipmentRequestedKey = identity.key;
  app.personEquipmentLoading = true;
  app.personEquipmentError = null;
  if (app.personEquipmentKey !== identity.key) {
    app.personEquipment = null;
    app.personEquipmentKey = "";
  }
  renderCharacterSheet();

  try {
    const params = new URLSearchParams({ target_uid: identity.targetUid });
    const result = await api(`/api/vam/person/equipment?${params.toString()}`, {
      signal: controller.signal,
    });
    const responseTarget = String(result.target_uid || "").trim();
    const responseRevision = String(result.revision || "").trim().toLowerCase();
    if (
      !personEquipmentRequestIsCurrent(
        generation,
        identity.targetUid,
        identity.revision,
      ) ||
      responseTarget !== identity.targetUid ||
      responseRevision !== identity.revision
    ) {
      return null;
    }
    app.personEquipment = normalizePersonEquipment(
      result,
      identity.targetUid,
      identity.revision,
    );
    app.personEquipmentKey = identity.key;
    app.personEquipmentError = null;
    return app.personEquipment;
  } catch (error) {
    if (
      error?.name !== "AbortError" &&
      personEquipmentRequestIsCurrent(
        generation,
        identity.targetUid,
        identity.revision,
      )
    ) {
      app.personEquipmentError = error;
      if (!quiet) {
        toast(
          "Could not load the character sheet",
          errorMessage(error),
          "error",
        );
      }
    }
    return null;
  } finally {
    if (generation === app.personEquipmentRequestGeneration) {
      app.personEquipmentAttemptedKey = identity.key;
      app.personEquipmentLoading = false;
      app.personEquipmentRequestedKey = "";
      app.personEquipmentRequestController = null;
      renderCharacterSheet();
    }
  }
}

function personHairIdentity() {
  const targetUid = String(app.selectedPersonUid || "").trim();
  const hair = selectedPersonHair();
  const revision = String(hair?.revision || "").trim().toLowerCase();
  if (
    !targetUid ||
    hair?.ready !== true ||
    !/^[0-9a-f]{32}$/.test(revision)
  ) {
    return null;
  }
  return {
    targetUid,
    revision,
    key: `${targetUid}\u0000${revision}`,
  };
}

function personHairRequestIsCurrent(generation, targetUid, revision) {
  const identity = personHairIdentity();
  return Boolean(
    generation === app.personHairRequestGeneration &&
      identity &&
      identity.targetUid === targetUid &&
      identity.revision === revision,
  );
}

function cancelPersonHairRequest() {
  if (app.personHairRequestController) {
    app.personHairRequestController.abort();
    app.personHairRequestController = null;
  }
  app.personHairRequestGeneration += 1;
  app.personHairLoading = false;
  app.personHairRequestedKey = "";
}

function clearPersonHair() {
  cancelPersonHairRequest();
  app.personHair = null;
  app.personHairError = null;
  app.personHairKey = "";
  app.personHairAttemptedKey = "";
  renderCharacterSheet();
}

function normalizePersonHair(payload, targetUid) {
  const document =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const items = [];
  const seen = new Map();
  for (const rawItem of asArray(document.items)) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const index = items.length + 1;
    const key = safeOpaqueKey(rawItem.key, `layer-${index}`);
    const actionKey = safeHairActionKey(key);
    const duplicate = seen.get(key);
    if (duplicate) {
      duplicate.actionable = false;
      continue;
    }
    const tags = normalizeTags(rawItem.tags)
      .map((tag) => safePresentationLabel(tag, ""))
      .filter(Boolean)
      .slice(0, 8);
    const locked = booleanValue(rawItem.locked, false);
    const normalizedItem = {
      key,
      displayName: safePresentationLabel(
        rawItem.display_name,
        `Hair layer ${index}`,
      ),
      tags,
      locked,
      actionable:
        booleanValue(rawItem.actionable, false) &&
        !locked &&
        Boolean(actionKey),
      simulated: booleanValue(rawItem.simulated, false),
    };
    seen.set(key, normalizedItem);
    items.push(normalizedItem);
  }
  return {
    available: booleanValue(document.available, false),
    targetUid,
    revision: String(document.revision || "").trim().toLowerCase().slice(0, 128),
    ready: booleanValue(document.ready, false),
    activeCount: Math.max(
      0,
      numberOr(document.active_count ?? document.activeCount, items.length),
    ),
    simCount: Math.max(
      0,
      numberOr(
        document.sim_count ?? document.simCount,
        items.filter((item) => item.simulated).length,
      ),
    ),
    lockedCount: Math.max(
      0,
      numberOr(
        document.locked_count ?? document.lockedCount,
        items.filter((item) => item.locked).length,
      ),
    ),
    truncated: booleanValue(document.truncated, false),
    items,
  };
}

async function syncPersonHair({ quiet = true, retry = false } = {}) {
  if (app.view !== "workspace" || characterSheetMode() !== "hair") {
    return app.personHair;
  }

  const identity = personHairIdentity();
  if (!identity) {
    if (
      app.personHair ||
      app.personHairError ||
      app.personHairLoading ||
      app.personHairAttemptedKey
    ) {
      clearPersonHair();
    } else {
      renderCharacterSheet();
    }
    return null;
  }
  if (
    app.personHairAttemptedKey &&
    app.personHairAttemptedKey !== identity.key
  ) {
    app.personHairAttemptedKey = "";
  }
  if (!retry && app.personHairAttemptedKey === identity.key) {
    return app.personHair;
  }
  if (
    app.personHairLoading &&
    app.personHairRequestedKey === identity.key
  ) {
    return null;
  }

  if (app.personHairRequestController) {
    app.personHairRequestController.abort();
  }
  const controller = new AbortController();
  const generation = app.personHairRequestGeneration + 1;
  app.personHairRequestGeneration = generation;
  app.personHairRequestController = controller;
  app.personHairRequestedKey = identity.key;
  app.personHairLoading = true;
  app.personHairError = null;
  if (app.personHairKey !== identity.key) {
    app.personHair = null;
    app.personHairKey = "";
  }
  renderCharacterSheet();

  try {
    const params = new URLSearchParams({ target_uid: identity.targetUid });
    const result = await api(`/api/vam/person/hair?${params.toString()}`, {
      signal: controller.signal,
    });
    const responseTarget = String(result.target_uid || "").trim();
    const responseRevision = String(result.revision || "").trim().toLowerCase();
    if (
      !personHairRequestIsCurrent(
        generation,
        identity.targetUid,
        identity.revision,
      ) ||
      responseTarget !== identity.targetUid ||
      responseRevision !== identity.revision
    ) {
      return null;
    }
    app.personHair = normalizePersonHair(result, identity.targetUid);
    app.personHairKey = identity.key;
    app.personHairError = null;
    return app.personHair;
  } catch (error) {
    if (
      error?.name !== "AbortError" &&
      personHairRequestIsCurrent(
        generation,
        identity.targetUid,
        identity.revision,
      )
    ) {
      app.personHairError = error;
      if (!quiet) {
        toast("Could not load Hair Studio", errorMessage(error), "error");
      }
    }
    return null;
  } finally {
    if (generation === app.personHairRequestGeneration) {
      app.personHairAttemptedKey = identity.key;
      app.personHairLoading = false;
      app.personHairRequestedKey = "";
      app.personHairRequestController = null;
      renderCharacterSheet();
    }
  }
}

function characterGender() {
  const equipment = app.personEquipment;
  const clothing = selectedPersonClothing();
  return String(equipment?.gender || clothing?.gender || "Unknown").trim() || "Unknown";
}

function genderItemCategoryIds(gender = characterGender()) {
  const normalized = String(gender || "").trim().toLowerCase();
  if (normalized === "female") return ["clothing-items-female"];
  if (normalized === "male") return ["clothing-items-male"];
  if (normalized === "both") {
    return ["clothing-items-female", "clothing-items-male"];
  }
  return [];
}

function renderCharacterShortcuts() {
  const category = currentWorkspaceCategory();
  const categories = new Map(
    ensureWorkspaceCategories().map((entry) => [entry.id, entry]),
  );
  const renderKey = JSON.stringify([
    category?.id || "",
    characterGender(),
    Array.from(categories.keys()),
  ]);
  if (elements.characterShortcuts.dataset.renderKey === renderKey) return;
  elements.characterShortcuts.dataset.renderKey = renderKey;
  elements.characterShortcuts.replaceChildren();

  for (const groupDefinition of CHARACTER_SHORTCUT_GROUPS) {
    const group = createElement("section", "character-shortcut-group");
    group.setAttribute("aria-label", groupDefinition.label);
    const heading = createElement("span", "character-shortcut-label");
    heading.textContent = groupDefinition.label;
    const choices = createElement("div", "character-shortcut-choices");

    for (const [entryId, entryLabel] of groupDefinition.entries) {
      const genderCategoryIds =
        entryId === "gender-items" ? genderItemCategoryIds() : [];
      const resolvedEntries =
        entryId === "gender-items"
          ? genderCategoryIds.map((id) => [
              id,
              genderCategoryIds.length > 1
                ? id.endsWith("female")
                  ? "Female items"
                  : "Male items"
                : entryLabel,
            ])
          : [[entryId, entryLabel]];
      if (entryId === "gender-items" && !resolvedEntries.length) {
        const unavailable = button(entryLabel, "character-shortcut");
        unavailable.disabled = true;
        unavailable.title =
          "Choose a live Person with a known gender to browse compatible items";
        choices.append(unavailable);
        continue;
      }
      for (const [resolvedId, resolvedLabel] of resolvedEntries) {
        const descriptor = categories.get(resolvedId);
        if (!descriptor) continue;
        const active = descriptor.id === category?.id;
        const shortcut = button(resolvedLabel, "character-shortcut");
        shortcut.dataset.characterCategory = descriptor.id;
        shortcut.classList.toggle("is-active", active);
        shortcut.setAttribute("aria-pressed", String(active));
        shortcut.setAttribute("aria-controls", "card-grid");
        shortcut.title = `Browse ${descriptor.label}`;
        choices.append(shortcut);
      }
    }
    if (choices.children.length) {
      group.append(heading, choices);
      elements.characterShortcuts.append(group);
    }
  }
}

function explicitEquipmentSlot(item) {
  const candidates = [
    item.equipment_slot,
    item.slot,
    ...asArray(item.slots),
  ]
    .map((value) =>
      String(value || "")
        .trim()
        .toLowerCase()
        .replace(/&/g, " and ")
        .replace(/[\s_]+/g, "-")
        .replace(/-+/g, "-"),
    )
    .filter(Boolean);
  for (const candidate of candidates) {
    if (CHARACTER_SLOT_ALIASES[candidate]) {
      return CHARACTER_SLOT_ALIASES[candidate];
    }
    if (CHARACTER_SHEET_SLOTS.some((slot) => slot.id === candidate)) {
      return candidate;
    }
  }
  return "";
}

function equipmentSlotForItem(item) {
  const explicitSlot = explicitEquipmentSlot(item);
  if (explicitSlot) return explicitSlot;
  const searchable = [
    ...normalizeTags(item.clothing?.tags || item.tags || item.tags_json),
    resourceTitle(item),
  ];
  const terms = new Set();
  for (const value of searchable) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) continue;
    terms.add(normalized);
    for (const word of normalized.match(/[a-z0-9]+/g) || []) {
      terms.add(word);
    }
  }
  for (const slotId of CHARACTER_SLOT_CLASSIFICATION_ORDER) {
    const slot = CHARACTER_SHEET_SLOTS.find((entry) => entry.id === slotId);
    if (
      slot &&
      slot.tags.some((tag) => terms.has(tag))
    ) {
      return slot.id;
    }
  }
  return "unsorted";
}

function resourceThumbnailUrl(resourceId) {
  const path = `/api/resources/${encodeURIComponent(resourceId)}/thumbnail`;
  return app.token
    ? `${path}?token=${encodeURIComponent(app.token)}`
    : path;
}

function normalizedResourceState(item, { assumeHidden = false } = {}) {
  const missingReason =
    typeof item?.missing_reason === "string"
      ? item.missing_reason.trim()
      : "";
  const explicit = String(item?.state || "").trim().toLowerCase();
  if (
    booleanValue(item?.missing, false) ||
    missingReason ||
    ["missing", "unavailable"].includes(explicit)
  ) {
    return "missing";
  }
  if (
    booleanValue(item?.local, false) ||
    ["local", "loose"].includes(explicit)
  ) {
    return "local";
  }
  if (["active", "enabled"].includes(explicit)) return "active";
  if (["hidden", "disabled", "inactive", "available"].includes(explicit)) {
    return "hidden";
  }

  for (const key of ["active", "package_active", "enabled"]) {
    if (Object.prototype.hasOwnProperty.call(item || {}, key)) {
      return booleanValue(item[key], false) ? "active" : "hidden";
    }
  }
  return assumeHidden ? "hidden" : "unknown";
}

function normalizedResourceId(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function missingResourcePresentation(reason, isMissing = false) {
  const code =
    typeof reason === "string" ? reason.trim().toLowerCase() : "";
  if (code === "package") {
    return {
      code,
      label: "Package missing",
      detail: "The containing VAR package is not installed.",
    };
  }
  if (code === "resource") {
    return {
      code,
      label: "Resource missing",
      detail:
        "The catalogue entry exists, but its exact resource file is unavailable.",
    };
  }
  if (!isMissing) {
    return { code: "", label: "", detail: "" };
  }
  return {
    code: "unknown",
    label: "Resource unavailable",
    detail: "The catalogue could not resolve this resource.",
  };
}

function normalizeResourceCardModel(item, options = {}) {
  const source =
    item && typeof item === "object" && !Array.isArray(item) ? item : {};
  const id = normalizedResourceId(source.id ?? source.resource_id);
  const packageRef = String(packageRoot(source) || "").trim();
  const safePackageRef = safePresentationLabel(packageRef, "");
  const declaredTitle = safePresentationLabel(
    source.display_name ||
      source.title ||
      source.name ||
      source.resource_name ||
    source.displayName,
    "",
  );
  const title = safePresentationLabel(
    resourceTitle(source),
    options.fallbackTitle || "Untitled resource",
  );
  const label = safePresentationLabel(source.label, title);
  const creator = safePresentationLabel(
    source.creator || creatorFromRoot(packageRef),
    "Unknown creator",
  );
  const packageLabel = safePresentationLabel(
    source.package || source.package_name || safePackageRef,
    safePackageRef,
  );
  const type = safePresentationLabel(resourceType(source), "Resource");
  const tags = Array.from(
    new Set(
      normalizeTags(
        source.clothing?.tags || source.tags || source.tags_json,
      )
        .map((tag) => safePresentationLabel(tag, ""))
        .filter(Boolean),
    ),
  );
  const state = normalizedResourceState(source, options);
  const missingStatus = missingResourcePresentation(
    source.missing_reason,
    state === "missing",
  );
  const selectedVersion = equipmentPackageVersion(source);
  const selectedVersionLabel =
    selectedVersion === null ? resourceSelectedVersion(source) : String(selectedVersion);
  const thumbnail = String(
    source.thumbnail_url ||
      source.thumbnail ||
      source.thumb_url ||
      source.preview_url ||
      "",
  ).trim();
  const relationshipKind = String(source.relationship_kind || "")
    .trim()
    .toLowerCase();
  const relationshipConfidence = String(
    source.relationship_confidence || "",
  )
    .trim()
    .toLowerCase();

  return {
    id,
    hasDeclaredTitle: Boolean(declaredTitle),
    searchName: declaredTitle,
    title,
    label,
    creator,
    packageRef,
    packageLabel,
    type,
    tags,
    state,
    stateLabel:
      state === "missing"
        ? missingStatus.label
        : {
            active: "Active",
            hidden: "Available",
            local: "Local",
            unknown: "State unknown",
          }[state] || "State unknown",
    active: state === "active",
    local: state === "local",
    missing: state === "missing",
    valid: itemIsValid(source),
    favorite: booleanValue(source.favorite, false),
    thumbnail,
    selectedVersion,
    selectedVersionLabel,
    updateVersion: resourceUpdateVersion(source),
    relationshipKind,
    relationshipConfidence,
    relationshipReason: safePresentationLabel(
      source.relationship_reason,
      "Same package/folder/name match; not semantic identity",
    ),
    missingReasonCode: missingStatus.code,
    missingDetail: missingStatus.detail,
  };
}

function normalizeRelatedResourceVariants(item) {
  const group = String(item?.variant_group || "").trim().toLowerCase();
  if (
    group !== "related-resources" &&
    group !== "related-clothing-styles"
  ) {
    return [];
  }
  const legacyClothingStyles = group === "related-clothing-styles";
  const seenIds = new Set();
  return asArray(item?.variants)
    .slice(0, MAX_RENDERED_RESOURCE_VARIANTS)
    .filter(
      (rawVariant) =>
        rawVariant &&
        typeof rawVariant === "object" &&
        !Array.isArray(rawVariant),
    )
    .map((rawVariant) => {
      const source = { ...rawVariant };
      if (legacyClothingStyles && !source.resource_type) {
        source.resource_type = "Clothing Item Presets";
      }
      if (legacyClothingStyles && !source.relationship_kind) {
        source.relationship_kind = "item-style";
      }
      const model = normalizeResourceCardModel(source, {
        fallbackTitle: "Unnamed name match",
      });
      if (model.id !== null) {
        if (seenIds.has(model.id)) return null;
        seenIds.add(model.id);
      }
      return {
        ...model,
        browseQuery: model.searchName,
        relationshipMetadataComplete:
          model.hasDeclaredTitle &&
          model.id !== null &&
          model.valid &&
          model.relationshipConfidence === "name-match",
      };
    })
    .filter(Boolean);
}

function workspaceCategoryForResourceType(type) {
  const normalizedType = String(type || "").trim().toLowerCase();
  if (!normalizedType) return null;
  return (
    ensureWorkspaceCategories().find((category) =>
      asArray(category.resourceTypes).some(
        (candidateType) =>
          String(candidateType || "").trim().toLowerCase() === normalizedType,
      ),
    ) || null
  );
}

function browseRelatedResource(model, fallbackQuery = "") {
  const query = safePresentationLabel(
    model?.browseQuery || model?.title || fallbackQuery,
    "",
  );
  if (!query) {
    toast(
      "Name match unavailable",
      "This catalogue row does not contain a safe searchable name.",
      "error",
    );
    return;
  }

  if (elements.resourceDetailDialog?.open) {
    elements.resourceDetailDialog.close("browse");
  }
  const category = workspaceCategoryForResourceType(model?.type);
  app.exactPackageId = "";
  app.query = query;
  app.packageState = "all";
  elements.searchInput.value = query;
  elements.stateFilter.value = "all";

  if (category) {
    const viewChanged = app.view !== "workspace";
    if (viewChanged) setView("workspace");
    const categoryChanged =
      app.selectedWorkspaceCategoryId !== category.id;
    if (categoryChanged) {
      setWorkspaceCategory(category.id);
    } else if (!viewChanged) {
      loadLibrary();
    }
  } else {
    const viewChanged = app.view !== "resources";
    app.type = "";
    elements.typeFilter.value = "";
    if (viewChanged) {
      setView("resources");
    } else {
      loadLibrary();
    }
  }
  elements.searchInput.focus({ preventScroll: true });
}

function browseRelatedClothingStyles(query) {
  browseRelatedResource(
    {
      browseQuery: query,
      type: "Clothing Item Presets",
    },
    query,
  );
}

function relatedResourceKindLabel(model) {
  if (model.relationshipKind === "item-style") return "Item style name match";
  if (model.relationshipKind === "preset-variant") {
    return "Preset name match";
  }
  return "Name match";
}

function relatedResourceStateLabel(model) {
  return (
    {
      active: "Available",
      local: "Available",
      hidden: "Hidden in VaM",
      missing: model.stateLabel,
      unknown: "State unknown",
    }[model.state] || "State unknown"
  );
}

function createRelatedResourceTile(model, ownerSearch) {
  const row = createElement("article", "resource-variant-tile");
  const visual = createElement("span", "resource-variant-visual");
  const fallback = createElement("span", "resource-variant-fallback");
  fallback.textContent = initials(model.label);
  fallback.setAttribute("aria-hidden", "true");
  visual.append(fallback);
  if (model.id !== null) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => image.remove());
    image.src = resourceThumbnailUrl(model.id);
    visual.append(image);
  }

  const copy = createElement("div", "resource-variant-copy");
  const heading = createElement("strong", "resource-variant-name");
  heading.textContent = model.label;
  heading.title = model.label;
  copy.append(heading);
  if (model.title !== model.label) {
    const catalogueName = createElement("span", "resource-variant-catalogue-name");
    catalogueName.textContent = model.title;
    catalogueName.title = model.title;
    copy.append(catalogueName);
  }

  const provenance = createElement("span", "resource-variant-provenance");
  provenance.textContent = [model.creator, model.packageLabel]
    .filter(Boolean)
    .join(" · ");
  copy.append(provenance);

  const metadata = createElement("span", "resource-variant-meta");
  metadata.append(badge(prettyType(model.type), "meta-pill"));
  metadata.append(
    badge(
      relatedResourceStateLabel(model),
      `meta-pill variant-state is-${model.state}`,
    ),
  );
  if (model.updateVersion !== null) {
    metadata.append(
      badge(
        `v${model.selectedVersionLabel} → v${model.updateVersion} available`,
        "meta-pill version-update",
      ),
    );
  } else if (
    model.selectedVersion !== null ||
    model.selectedVersionLabel !== "?"
  ) {
    metadata.append(
      badge(`v${model.selectedVersionLabel}`, "meta-pill"),
    );
  }
  for (const tag of model.tags.slice(0, 2)) {
    metadata.append(badge(tag, "meta-pill"));
  }
  if (model.favorite) {
    metadata.append(badge("★ Favorite", "meta-pill variant-favorite"));
  }
  copy.append(metadata);

  const relationship = createElement("span", "resource-variant-relationship");
  relationship.textContent = `${relatedResourceKindLabel(model)} · ${
    model.relationshipReason
  }`;
  copy.append(relationship);
  if (model.missingDetail) {
    const missing = createElement("span", "resource-variant-missing");
    missing.textContent = model.missingDetail;
    copy.append(missing);
  }

  const browse = button(
    model.relationshipKind === "item-style"
      ? "Browse style"
      : "Browse variant",
    "secondary-button resource-variant-browse",
  );
  const query = model.browseQuery || ownerSearch;
  browse.disabled = !query;
  browse.title = model.relationshipMetadataComplete
    ? `Browse catalogue matches for ${query}; name matches do not perform live actions`
    : "Browse catalogue name matches; relationship metadata is incomplete and no live action is available";
  browse.addEventListener("click", () =>
    browseRelatedResource({ ...model, browseQuery: query }, ownerSearch),
  );

  row.append(visual, copy, browse);
  return row;
}

function boundedDependencyText(value, fallback = "", limit = 240) {
  const text = String(value ?? "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text ? text.slice(0, limit) : fallback;
}

function dependencyIdentifier(value, fallback = "") {
  if (!["string", "number"].includes(typeof value)) return fallback;
  const identifier = boundedDependencyText(value, "", 500);
  if (
    !identifier ||
    /^[a-z]:[\\/]/i.test(identifier) ||
    /^[/\\]/.test(identifier) ||
    /(?:^|[\\/])(?:Custom|AddonPackages)(?:[\\/]|$)/i.test(identifier) ||
    /\.var(?::|[\\/]|$)/i.test(identifier)
  ) {
    return fallback;
  }
  return identifier;
}

function normalizeDependencyState(value) {
  const state = String(value || "").trim().toLowerCase();
  if (["enabled", "available", "local"].includes(state)) {
    if (state === "enabled") return "active";
    if (state === "available") return "hidden";
    return "local";
  }
  if (["disabled", "inactive"].includes(state)) return "hidden";
  if (state === "choice-stale") return "stale";
  if (
    ["active", "hidden", "missing", "conflict", "stale", "unknown"].includes(
      state,
    )
  ) {
    return state;
  }
  return "unknown";
}

function normalizeDependencyReport(payload) {
  const envelope =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const source =
    [envelope.details, envelope.report, envelope.dependency_report].find(
      (candidate) =>
        candidate &&
        typeof candidate === "object" &&
        !Array.isArray(candidate),
    ) || envelope;
  const rawConflicts = asArray(source.conflicts || envelope.conflicts);
  const conflicts = rawConflicts
    .slice(0, MAX_RENDERED_DEPENDENCIES)
    .filter(
      (entry) =>
        entry && typeof entry === "object" && !Array.isArray(entry),
    )
    .map((entry) => {
      const packageId = dependencyIdentifier(
        entry.package_id || entry.packageId || entry.id || entry.requested,
        "Unknown package",
      );
      const selectedContentSha256 = boundedDependencyText(
        entry.selected_content_sha256 ||
          entry.selectedContentSha256 ||
          entry.selected_digest,
        "",
        160,
      );
      const copies = asArray(entry.copies)
        .slice(0, 100)
        .filter(
          (copy) =>
            copy && typeof copy === "object" && !Array.isArray(copy),
        )
        .map((copy) => {
          const contentSha256 = boundedDependencyText(
            copy.content_sha256 ||
              copy.contentSha256 ||
              copy.content_digest ||
              copy.sha256,
            "",
            160,
          );
          const selected =
            booleanValue(copy.selected, false) ||
            Boolean(
              selectedContentSha256 &&
                contentSha256 &&
                selectedContentSha256 === contentSha256,
            );
          return {
            copyId: dependencyIdentifier(
              copy.copy_id || copy.copyId || copy.id,
              "",
            ),
            relativePath: boundedDependencyText(
              copy.relative_path ||
                copy.logical_path ||
                copy.path ||
                copy.relativePath,
              "Package path unavailable",
              360,
            ),
            size: numberOr(copy.size, -1),
            enabled: booleanValue(
              copy.enabled,
              booleanValue(copy.active, false),
            ),
            contentSha256,
            selected,
            dependencies: asArray(copy.dependencies)
              .slice(0, 40)
              .map((dependency) =>
                dependencyIdentifier(
                  typeof dependency === "object" && dependency
                    ? dependency.requested ||
                        dependency.package_id ||
                        dependency.id
                    : dependency,
                  "",
                ),
              )
              .filter(Boolean),
          };
        });
      return {
        packageId,
        reportRevision: boundedDependencyText(
          entry.report_revision || entry.reportRevision,
          "",
          160,
        ),
        selectedContentSha256,
        choiceStale: booleanValue(
          entry.choice_stale,
          booleanValue(entry.choiceStale, false),
        ),
        resolved: booleanValue(entry.resolved, Boolean(selectedContentSha256)),
        requiresVamClose: booleanValue(
          entry.requires_vam_close,
          booleanValue(entry.requiresVamClose, false),
        ),
        copies,
      };
    });
  const unresolvedConflictIds = new Set(
    conflicts
      .filter((entry) => !entry.resolved || entry.choiceStale)
      .map((entry) => entry.packageId.toLowerCase()),
  );
  const dependencies = asArray(source.dependencies || envelope.dependencies)
    .slice(0, MAX_RENDERED_DEPENDENCIES)
    .filter(
      (entry) =>
        entry && typeof entry === "object" && !Array.isArray(entry),
    )
    .map((entry) => {
      const requested = dependencyIdentifier(
        entry.requested ||
          entry.package_ref ||
          entry.reference ||
          entry.package_id ||
          entry.packageId,
        "Unknown package",
      );
      const resolvedId = dependencyIdentifier(
        entry.resolved_id ||
          entry.resolvedId ||
          entry.resolved ||
          entry.package_id ||
          entry.identity,
        "",
      );
      const packageId = resolvedId || requested;
      let state = normalizeDependencyState(entry.state || entry.status);
      if (
        booleanValue(
          entry.choice_stale,
          booleanValue(entry.choiceStale, false),
        ) ||
        state === "stale"
      ) {
        state = "stale";
      } else if (
        (booleanValue(entry.conflict, false) &&
          !booleanValue(
            entry.conflict_resolved,
            booleanValue(entry.conflictResolved, false),
          )) ||
        unresolvedConflictIds.has(packageId.toLowerCase())
      ) {
        state = "conflict";
      }
      const rawRequiredBy = Array.isArray(entry.required_by)
        ? entry.required_by
        : entry.required_by
          ? [entry.required_by]
          : Array.isArray(entry.requiredBy)
            ? entry.requiredBy
            : entry.requiredBy
              ? [entry.requiredBy]
              : [];
      return {
        requested,
        resolvedId,
        packageId,
        state,
        direct:
          booleanValue(entry.direct, false) ||
          numberOr(entry.depth, -1) === 0,
        requiredBy: rawRequiredBy
          .slice(0, 8)
          .map((value) => dependencyIdentifier(value, ""))
          .filter(Boolean),
      };
    })
    .sort((left, right) => {
      const stateOrder = {
        conflict: 0,
        missing: 1,
        stale: 2,
        active: 3,
        local: 4,
        hidden: 5,
        unknown: 6,
      };
      return (
        Number(right.direct) - Number(left.direct) ||
        (stateOrder[left.state] ?? 9) - (stateOrder[right.state] ?? 9) ||
        left.packageId.localeCompare(right.packageId, undefined, {
          sensitivity: "base",
        })
      );
    });
  const suppliedCounts =
    source.counts &&
    typeof source.counts === "object" &&
    !Array.isArray(source.counts)
      ? source.counts
      : {};
  const direct = dependencies.filter((entry) => entry.direct).length;
  const missing = dependencies.filter((entry) =>
    ["missing", "stale"].includes(entry.state),
  ).length;
  const counts = {
    total: Math.max(
      0,
      Math.floor(numberOr(suppliedCounts.total, dependencies.length)),
    ),
    direct: Math.max(
      0,
      Math.floor(numberOr(suppliedCounts.direct, direct)),
    ),
    transitive: Math.max(
      0,
      Math.floor(
        numberOr(
          suppliedCounts.transitive,
          Math.max(0, dependencies.length - direct),
        ),
      ),
    ),
    missing: Math.max(
      0,
      Math.floor(numberOr(suppliedCounts.missing, missing)),
    ),
    conflicts: Math.max(
      0,
      Math.floor(
        numberOr(
          suppliedCounts.conflicts ?? suppliedCounts.conflict,
          conflicts.length,
        ),
      ),
    ),
  };
  return {
    resource:
      source.resource &&
      typeof source.resource === "object" &&
      !Array.isArray(source.resource)
        ? source.resource
        : {},
    reportRevision: boundedDependencyText(
      source.report_revision ||
        source.reportRevision ||
        source.revision ||
        envelope.report_revision ||
        envelope.reportRevision ||
        envelope.revision,
      "",
      160,
    ),
    counts,
    dependencies,
    conflicts,
    truncated: booleanValue(source.truncated ?? envelope.truncated, false),
  };
}

function dependencyPaginationState(total, page) {
  const safeTotal = Math.max(0, Math.floor(numberOr(total, 0)));
  const pageCount = Math.max(
    1,
    Math.ceil(safeTotal / DEPENDENCY_PAGE_SIZE),
  );
  const safePage = Math.min(
    pageCount,
    Math.max(1, Math.floor(numberOr(page, 1))),
  );
  return {
    page: safePage,
    pageCount,
    start: (safePage - 1) * DEPENDENCY_PAGE_SIZE,
    hasPrevious: safePage > 1,
    hasNext: safePage < pageCount,
  };
}

function dependencyStateLabel(state) {
  return (
    {
      active: "Active",
      local: "Local",
      hidden: "Available",
      missing: "Missing",
      stale: "Choice missing",
      conflict: "Needs a choice",
      unknown: "Unknown",
    }[state] || "Unknown"
  );
}

function resourceReturnLocationLabel(context) {
  if (context.kind === "package") return "Packages";
  if (context.view === "workspace") {
    return context.workspaceCategoryLabel || "Workspace";
  }
  return context.view === "resources" ? "Resources" : "Library";
}

function renderResourceReturnContext() {
  const context = app.resourceReturnContext;
  elements.resourceReturnContext.hidden = !context;
  if (!context) return;

  const title = safePresentationLabel(context.title, "resource");
  elements.resourceReturnTitle.textContent = `Back to “${title}”`;
  elements.resourceReturnButton.setAttribute(
    "aria-label",
    `Back to ${title} and restore its previous library view`,
  );
  const details = [resourceReturnLocationLabel(context)];
  if (context.query) {
    details.push(
      `search “${boundedDependencyText(context.query, "", 64)}”`,
    );
  }
  if (context.type) details.push(prettyType(context.type));
  if (context.packageState !== "all") {
    details.push(dependencyStateLabel(context.packageState));
  }
  details.push(`page ${formatNumber(context.page)}`);
  elements.resourceReturnDetail.textContent = details.join(" · ");
}

function clearResourceReturnContext() {
  const restoreFocus = Boolean(
    elements.resourceReturnContext?.contains(document.activeElement),
  );
  app.resourceReturnGeneration += 1;
  if (app.resourceReturnInFlight && app.requestController) {
    app.requestController.abort();
  }
  app.resourceReturnInFlight = false;
  app.resourceReturnContext = null;
  setButtonBusy(elements.resourceReturnButton, false);
  renderResourceReturnContext();
  if (restoreFocus) {
    window.setTimeout(() => {
      const activeTab = elements.viewTabs.find((tab) =>
        tab.classList.contains("active"),
      );
      const focusTarget =
        !elements.libraryView.hidden &&
        !["access", "timeline"].includes(app.view)
          ? elements.searchInput
          : activeTab;
      if (focusTarget instanceof HTMLElement && focusTarget.isConnected) {
        focusTarget.focus({ preventScroll: true });
      }
    }, 0);
  }
}

function exitPackageContentsScope() {
  if (app.view !== "resources" || !app.packageContentsId) return false;
  clearResourceReturnContext();
  window.clearTimeout(app.searchTimer);
  app.packageContentsId = "";
  app.query = "";
  app.type = "";
  app.packageState = "all";
  elements.searchInput.value = "";
  elements.typeFilter.value = "";
  elements.stateFilter.value = "all";
  configureStateFilter();
  updateWorkspaceSearchPlaceholder();
  updateClearFilters();
  loadLibrary();
  return true;
}

function dismissResourceReturnContext() {
  if (exitPackageContentsScope()) return;
  clearResourceReturnContext();
}

function captureResourceReturnContext() {
  const item = app.resourceDetailItem;
  const resourceId = normalizedResourceId(
    Number(item?.id ?? item?.resource_id),
  );
  if (
    resourceId === null ||
    !["resources", "workspace"].includes(app.view)
  ) {
    return;
  }
  const model = normalizeResourceCardModel(item, { assumeHidden: true });
  const category =
    app.view === "workspace" ? currentWorkspaceCategory() : null;
  const parentContext = app.resourceReturnContext;
  app.resourceReturnGeneration += 1;
  app.resourceReturnInFlight = false;
  app.resourceReturnContext = {
    kind: "resource",
    parentContext,
    resourceId,
    title: model.title,
    view: app.view,
    query: app.query,
    type: app.type,
    packageState: app.packageState,
    exactPackageId: app.exactPackageId,
    packageContentsId: app.packageContentsId,
    page: libraryPaginationState(app.total, app.page).page,
    selectedWorkspaceCategoryId: app.selectedWorkspaceCategoryId,
    workspaceCategoryLabel: category?.label || "",
    dependencyPage: app.resourceDependencyPage,
    detailScrollTop: Math.max(
      0,
      Math.trunc(numberOr(elements.resourceDetailContent?.scrollTop, 0)),
    ),
  };
  setButtonBusy(elements.resourceReturnButton, false);
  renderResourceReturnContext();
}

function resourceReturnStateMatches(context) {
  return (
    app.view === context.view &&
    app.query === context.query &&
    app.type === context.type &&
    app.packageState === context.packageState &&
    app.exactPackageId === context.exactPackageId &&
    app.packageContentsId === (context.packageContentsId || "") &&
    elements.searchInput.value.trim() === context.query &&
    (context.view !== "workspace" ||
      app.selectedWorkspaceCategoryId ===
        context.selectedWorkspaceCategoryId)
  );
}

async function returnToResourceContext() {
  const context = app.resourceReturnContext;
  if (!context || app.resourceReturnInFlight) return;
  if (context.kind === "package") {
    await returnToPackageContext(context);
    return;
  }
  const generation = ++app.resourceReturnGeneration;
  app.resourceReturnInFlight = true;
  setButtonBusy(elements.resourceReturnButton, true, "Restoring resource…");

  try {
    app.selectedWorkspaceCategoryId =
      context.selectedWorkspaceCategoryId;
    app.query = context.query;
    app.type = context.type;
    app.packageState = context.packageState;
    app.exactPackageId = context.exactPackageId;
    app.packageContentsId = context.packageContentsId || "";
    setView(context.view, {
      deferLibraryLoad: true,
      preserveResourceReturn: true,
    });
    configureStateFilter();
    updateWorkspaceSearchPlaceholder();
    elements.searchInput.value = context.query;
    elements.typeFilter.value = context.type;
    elements.stateFilter.value = context.packageState;
    updateClearFilters();

    const restored = await loadLibrary({ page: context.page });
    if (
      restored !== true ||
      generation !== app.resourceReturnGeneration ||
      app.resourceReturnContext !== context ||
      !resourceReturnStateMatches(context)
    ) {
      return;
    }

    const freshItem = app.items.find(
      (item) =>
        normalizedResourceId(
          Number(item?.id ?? item?.resource_id),
        ) === context.resourceId,
    );
    if (!freshItem) {
      clearResourceReturnContext();
      toast(
        "Could not reopen resource",
        "The previous library view was restored, but this resource is no longer on that catalogue page.",
        "error",
      );
      return;
    }
    const freshOpener =
      resourceCardOpener(context.resourceId) || elements.searchInput;
    app.resourceDetailRestore = {
      resourceId: context.resourceId,
      dependencyPage: context.dependencyPage,
      scrollTop: context.detailScrollTop,
    };
    openResourceDetailDialog(freshItem, freshOpener);
    app.resourceReturnContext = context.parentContext || null;
    renderResourceReturnContext();
  } finally {
    if (generation === app.resourceReturnGeneration) {
      app.resourceReturnInFlight = false;
      setButtonBusy(elements.resourceReturnButton, false);
    }
  }
}

function capturePackageReturnContext(item) {
  if (app.view !== "packages") return false;
  const packageId = packageItemIdentity(item);
  if (!packageId) return false;
  const parentContext = app.resourceReturnContext;
  app.resourceReturnGeneration += 1;
  app.resourceReturnInFlight = false;
  app.resourceReturnContext = {
    kind: "package",
    parentContext,
    packageId,
    title: packageId,
    view: "packages",
    query: app.query,
    type: app.type,
    packageState: app.packageState,
    exactPackageId: app.exactPackageId,
    packageContentsId: "",
    page: libraryPaginationState(app.total, app.page).page,
    selectedWorkspaceCategoryId: app.selectedWorkspaceCategoryId,
    workspaceCategoryLabel: "",
  };
  setButtonBusy(elements.resourceReturnButton, false);
  renderResourceReturnContext();
  return true;
}

async function returnToPackageContext(context) {
  if (
    !context ||
    context.kind !== "package" ||
    app.resourceReturnInFlight
  ) {
    return;
  }
  const generation = ++app.resourceReturnGeneration;
  app.resourceReturnInFlight = true;
  setButtonBusy(elements.resourceReturnButton, true, "Restoring package…");

  try {
    app.query = context.query;
    app.type = context.type;
    app.packageState = context.packageState;
    app.exactPackageId = context.exactPackageId;
    app.packageContentsId = "";
    setView("packages", {
      deferLibraryLoad: true,
      preserveResourceReturn: true,
    });
    configureStateFilter();
    updateWorkspaceSearchPlaceholder();
    elements.searchInput.value = context.query;
    elements.typeFilter.value = context.type;
    elements.stateFilter.value = context.packageState;
    updateClearFilters();

    const restored = await loadLibrary({ page: context.page });
    if (
      restored !== true ||
      generation !== app.resourceReturnGeneration ||
      app.resourceReturnContext !== context ||
      !resourceReturnStateMatches(context)
    ) {
      return;
    }

    const packageCard = packageCardOpener(context.packageId);
    if (!packageCard) {
      clearResourceReturnContext();
      toast(
        "Could not return to package",
        "The previous package view was restored, but that exact package is no longer on the catalogue page.",
        "error",
      );
      return;
    }
    app.resourceReturnContext = context.parentContext || null;
    renderResourceReturnContext();
    packageCard.tabIndex = -1;
    packageCard.focus({ preventScroll: true });
    packageCard.scrollIntoView({ block: "nearest" });
  } finally {
    if (generation === app.resourceReturnGeneration) {
      app.resourceReturnInFlight = false;
      setButtonBusy(elements.resourceReturnButton, false);
    }
  }
}

function browsePackageContents(item) {
  const packageId = packageItemIdentity(item);
  if (!packageId) {
    toast(
      "Package identity unavailable",
      "This package does not contain a safe exact identity.",
      "error",
    );
    return;
  }
  if (!capturePackageReturnContext(item)) return;

  window.clearTimeout(app.searchTimer);
  app.packageContentsId = packageId;
  app.exactPackageId = "";
  app.query = "";
  app.type = "";
  app.packageState = "all";
  elements.searchInput.value = "";
  elements.typeFilter.value = "";
  elements.stateFilter.value = "all";
  setView("resources", { preserveResourceReturn: true });
  updateWorkspaceSearchPlaceholder();
  elements.searchInput.focus({ preventScroll: true });
}

function browseDependencyPackage(packageId) {
  const query = dependencyIdentifier(packageId, "");
  if (!query) {
    toast(
      "Package identity unavailable",
      "This dependency does not contain a safe package identity.",
      "error",
    );
    return;
  }
  captureResourceReturnContext();
  window.clearTimeout(app.searchTimer);
  if (elements.resourceDetailDialog?.open) {
    elements.resourceDetailDialog.close("browse");
  }
  app.exactPackageId = query;
  app.query = query;
  app.type = "";
  app.packageState = "all";
  elements.searchInput.value = query;
  elements.typeFilter.value = "";
  elements.stateFilter.value = "all";
  if (app.view !== "packages") {
    setView("packages", { preserveResourceReturn: true });
  } else {
    loadLibrary();
  }
  elements.searchInput.focus({ preventScroll: true });
}

function dependencyCopyFingerprint(value) {
  const fingerprint = boundedDependencyText(value, "");
  if (!fingerprint) return "Fingerprint unavailable";
  const withoutPrefix = fingerprint.replace(/^[^:]+:/, "");
  return withoutPrefix.length > 18
    ? `${withoutPrefix.slice(0, 12)}…${withoutPrefix.slice(-6)}`
    : withoutPrefix;
}

function reportHasUnresolvedConflicts(report) {
  return asArray(report?.conflicts).some(
    (conflict) => !asArray(conflict.copies).some((copy) => copy.selected),
  );
}

async function chooseDependencyPackageCopy(
  report,
  conflict,
  copy,
  sourceButton,
  section,
  item,
) {
  if (!conflict.packageId || !copy.copyId) return;
  const key = `${conflict.packageId.toLowerCase()}:${copy.copyId}`;
  if (app.packageChoiceInFlight.has(key)) return;
  app.packageChoiceInFlight.add(key);
  setButtonBusy(sourceButton, true, "Saving choice…");
  try {
    const result = await api("/api/package-copy-choice", {
      method: "POST",
      body: {
        package_id: conflict.packageId,
        copy_id: copy.copyId,
        report_revision:
          conflict.reportRevision || report.reportRevision || "",
      },
    });
    const responseHasReport = Boolean(
      result &&
        typeof result === "object" &&
        (Array.isArray(result.dependencies) ||
          Array.isArray(result.conflicts) ||
          result.details ||
          result.report),
    );
    if (responseHasReport) {
      const updated = normalizeDependencyReport(result);
      app.resourceDependencyReport = updated;
      renderResourceDependencyReport(section, item, updated);
      if (!reportHasUnresolvedConflicts(updated)) {
        dismissToast(app.packageConflictToast);
        app.packageConflictToast = null;
      }
    } else {
      await loadResourceDependencyDetails(section, item);
      if (!reportHasUnresolvedConflicts(app.resourceDependencyReport)) {
        dismissToast(app.packageConflictToast);
        app.packageConflictToast = null;
      }
    }
    const requiresVamClose = booleanValue(
      result?.requires_vam_close || result?.conflict?.requires_vam_close,
      false,
    );
    toast(
      requiresVamClose
        ? "Package choice saved — close VaM"
        : "Package copy selected",
      requiresVamClose
        ? `VAM-PIP saved the choice for ${conflict.packageId}, but another copy is already active. Close VaM so it can safely switch content, then retry the asset.`
        : `VAM-PIP will use this content for ${conflict.packageId}. Retry the asset after resolving every flagged package.`,
      requiresVamClose ? "error" : "success",
      { persistent: requiresVamClose },
    );
  } catch (error) {
    const errorReport = normalizeDependencyReport(error?.payload);
    if (errorReport.conflicts.length || errorReport.dependencies.length) {
      app.resourceDependencyReport = errorReport;
      renderResourceDependencyReport(section, item, errorReport);
    }
    toast(
      "Could not save package choice",
      errorMessage(error),
      "error",
      { persistent: true },
    );
  } finally {
    app.packageChoiceInFlight.delete(key);
    setButtonBusy(sourceButton, false);
  }
}

function createDependencyConflictPanel(
  report,
  conflict,
  section,
  item,
) {
  const panel = createElement("article", "dependency-conflict-panel");
  panel.tabIndex = -1;
  const header = createElement("div", "dependency-conflict-header");
  const copy = document.createElement("div");
  const title = document.createElement("h4");
  title.textContent = conflict.packageId;
  const description = document.createElement("p");
  description.textContent =
    conflict.resolved && !conflict.choiceStale
      ? "These files use the same package ID but contain different data. A saved content choice is active; review or change it below."
      : "Installed files use the same package ID but contain different data. Choose the content this installation should use.";
  copy.append(title, description);
  const openPackage = button(
    "Open package",
    "quiet-button dependency-open-package",
  );
  openPackage.addEventListener("click", () =>
    browseDependencyPackage(conflict.packageId),
  );
  header.append(copy, openPackage);
  panel.append(header);
  if (conflict.requiresVamClose) {
    const closeWarning = createElement(
      "p",
      "dependency-conflict-close-warning",
    );
    closeWarning.textContent =
      "A different copy is already active in VaM. This choice is saved, but VaM must close before VAM-PIP can safely switch the package.";
    panel.append(closeWarning);
  } else if (conflict.choiceStale) {
    const staleWarning = createElement(
      "p",
      "dependency-conflict-close-warning",
    );
    staleWarning.textContent =
      "The previously selected content is no longer installed. Choose an available copy before loading this asset.";
    panel.append(staleWarning);
  }

  const choices = createElement("div", "dependency-copy-grid");
  if (!conflict.copies.length) {
    const empty = createElement("p", "dependency-copy-empty");
    empty.textContent =
      "The manager reported a conflict but did not provide safe copy identifiers. Rescan packages and reopen this detail.";
    choices.append(empty);
  }
  for (const packageCopy of conflict.copies) {
    const selected = packageCopy.selected;
    const choice = createElement(
      "div",
      `dependency-copy-card${selected ? " is-selected" : ""}`,
    );
    const choiceHeading = createElement("div", "dependency-copy-heading");
    const state = badge(
      selected
        ? "Selected"
        : packageCopy.enabled
          ? "Active copy"
          : "Hidden copy",
      `dependency-copy-state${selected ? " is-selected" : ""}`,
    );
    const size = createElement("span", "dependency-copy-size");
    size.textContent =
      packageCopy.size >= 0 ? formatBytes(packageCopy.size) : "Unknown size";
    choiceHeading.append(state, size);

    const path = createElement("p", "dependency-copy-path");
    path.textContent = packageCopy.relativePath;
    path.title = packageCopy.relativePath;
    const fingerprint = createElement("p", "dependency-copy-fingerprint");
    fingerprint.textContent = `Content ${dependencyCopyFingerprint(
      packageCopy.contentSha256,
    )}`;
    fingerprint.title =
      packageCopy.contentSha256 || "Fingerprint unavailable";

    const dependencySummary = createElement(
      "div",
      "dependency-copy-dependencies",
    );
    const dependencyLabel = document.createElement("span");
    dependencyLabel.textContent = packageCopy.dependencies.length
      ? `Declares ${formatNumber(packageCopy.dependencies.length)} ${plural(
          "dependency",
          packageCopy.dependencies.length,
        )}`
      : "Declares no dependencies";
    dependencySummary.append(dependencyLabel);
    if (packageCopy.dependencies.length) {
      const declared = document.createElement("div");
      for (const dependency of packageCopy.dependencies.slice(0, 6)) {
        declared.append(badge(dependency, "meta-pill"));
      }
      if (packageCopy.dependencies.length > 6) {
        declared.append(
          badge(
            `+${formatNumber(packageCopy.dependencies.length - 6)} more`,
            "meta-pill",
          ),
        );
      }
      dependencySummary.append(declared);
    }

    const choose = button(
      selected ? "Using this content" : "Use this content",
      selected
        ? "secondary-button dependency-copy-select is-selected"
        : "primary-button dependency-copy-select",
    );
    choose.disabled = selected || !packageCopy.copyId;
    choose.title = !packageCopy.copyId
      ? "This report did not include a safe copy identifier"
      : selected
        ? "This is the persistent package choice"
        : `Use this content whenever ${conflict.packageId} is requested`;
    choose.addEventListener("click", () =>
      chooseDependencyPackageCopy(
        report,
        conflict,
        packageCopy,
        choose,
        section,
        item,
      ),
    );
    choice.append(
      choiceHeading,
      path,
      fingerprint,
      dependencySummary,
      choose,
    );
    choices.append(choice);
  }
  panel.append(choices);
  return panel;
}

function createDependencyRow(entry) {
  const row = createElement(
    "li",
    `dependency-row is-${entry.state}`,
  );
  const identity = createElement("div", "dependency-identity");
  const heading = document.createElement("strong");
  heading.textContent = entry.resolvedId || entry.requested;
  heading.title = entry.resolvedId || entry.requested;
  identity.append(heading);
  if (entry.resolvedId && entry.requested !== entry.resolvedId) {
    const requested = document.createElement("span");
    requested.textContent = `${entry.requested} → ${entry.resolvedId}`;
    requested.title = `${entry.requested} resolves to ${entry.resolvedId}`;
    identity.append(requested);
  }
  if (entry.requiredBy.length) {
    const requiredBy = document.createElement("span");
    requiredBy.textContent = `Required by ${entry.requiredBy.join(", ")}`;
    requiredBy.title = requiredBy.textContent;
    identity.append(requiredBy);
  }

  const metadata = createElement("div", "dependency-row-meta");
  metadata.append(
    badge(
      entry.direct ? "Direct" : "Transitive",
      `dependency-depth${entry.direct ? " is-direct" : ""}`,
    ),
  );
  metadata.append(
    badge(
      dependencyStateLabel(entry.state),
      `dependency-state is-${entry.state}`,
    ),
  );
  const browse = button(
    "Open package",
    "quiet-button dependency-open-package",
  );
  browse.addEventListener("click", () =>
    browseDependencyPackage(entry.packageId),
  );
  row.append(identity, metadata, browse);
  return row;
}

function renderResourceDependencyReport(section, item, rawReport) {
  const report = normalizeDependencyReport(rawReport);
  app.resourceDependencyReport = report;
  const header = createElement("div", "resource-detail-section-heading");
  const headingCopy = document.createElement("div");
  const kicker = createElement("p", "eyebrow");
  kicker.textContent = "Detected package graph";
  const heading = document.createElement("h3");
  heading.id = "resource-detail-dependencies-title";
  heading.textContent = "Dependencies";
  const explanation = document.createElement("p");
  explanation.textContent =
    "References detected in this resource plus their package dependencies. Package choices are global, persistent, and reversible.";
  headingCopy.append(kicker, heading, explanation);
  const count = createElement("span", "resource-detail-variant-count");
  count.textContent = formatNumber(report.counts.total);
  count.setAttribute(
    "aria-label",
    `${formatNumber(report.counts.total)} detected ${plural(
      "dependency",
      report.counts.total,
    )}`,
  );
  header.append(headingCopy, count);

  const summary = createElement("div", "dependency-summary");
  for (const [label, value, kind] of [
    ["Direct", report.counts.direct, "direct"],
    ["Transitive", report.counts.transitive, "transitive"],
    ["Missing", report.counts.missing, "missing"],
    ["Conflicts", report.counts.conflicts, "conflict"],
  ]) {
    const stat = createElement("div", `dependency-stat is-${kind}`);
    const statValue = document.createElement("strong");
    statValue.textContent = formatNumber(value);
    const statLabel = document.createElement("span");
    statLabel.textContent = label;
    stat.append(statValue, statLabel);
    summary.append(stat);
  }

  const content = document.createDocumentFragment();
  content.append(header, summary);
  if (report.conflicts.length) {
    const conflictRegion = createElement("div", "dependency-conflicts");
    const warning = createElement("p", "dependency-conflict-warning");
    warning.textContent = reportHasUnresolvedConflicts(report)
      ? "Resolve each unselected package below before retrying the scene. VAM-PIP stores a content choice, not a fragile file path."
      : "Every same-ID conflict has a saved content choice. You can review or change those choices below.";
    conflictRegion.append(warning);
    for (const conflict of report.conflicts) {
      conflictRegion.append(
        createDependencyConflictPanel(report, conflict, section, item),
      );
    }
    content.append(conflictRegion);
  }

  if (report.dependencies.length) {
    const page = dependencyPaginationState(
      report.dependencies.length,
      app.resourceDependencyPage,
    );
    app.resourceDependencyPage = page.page;
    const listHeader = createElement("div", "dependency-list-header");
    const pageLabel = document.createElement("strong");
    pageLabel.textContent = `Packages ${formatNumber(
      page.start + 1,
    )}–${formatNumber(
      Math.min(
        report.dependencies.length,
        page.start + DEPENDENCY_PAGE_SIZE,
      ),
    )} of ${formatNumber(report.dependencies.length)}`;
    const pager = createElement("div", "dependency-pager");
    const previous = button("←", "dependency-page-arrow");
    previous.setAttribute("aria-label", "Previous dependency page");
    previous.disabled = !page.hasPrevious;
    const status = document.createElement("span");
    status.textContent = `${formatNumber(page.page)} / ${formatNumber(
      page.pageCount,
    )}`;
    status.setAttribute("aria-live", "polite");
    const next = button("→", "dependency-page-arrow");
    next.setAttribute("aria-label", "Next dependency page");
    next.disabled = !page.hasNext;
    previous.addEventListener("click", () => {
      app.resourceDependencyPage = page.page - 1;
      renderResourceDependencyReport(section, item, report);
    });
    next.addEventListener("click", () => {
      app.resourceDependencyPage = page.page + 1;
      renderResourceDependencyReport(section, item, report);
    });
    pager.append(previous, status, next);
    listHeader.append(pageLabel, pager);
    const list = createElement("ul", "dependency-list");
    for (const dependency of report.dependencies.slice(
      page.start,
      page.start + DEPENDENCY_PAGE_SIZE,
    )) {
      list.append(createDependencyRow(dependency));
    }
    content.append(listHeader, list);
  } else if (!report.conflicts.length) {
    const empty = createElement("div", "dependency-empty");
    const emptyTitle = document.createElement("strong");
    emptyTitle.textContent = "No package references detected";
    const emptyCopy = document.createElement("p");
    emptyCopy.textContent =
      "Loose or self-contained resources may not need any external VAR packages.";
    empty.append(emptyTitle, emptyCopy);
    content.append(empty);
  }
  if (report.truncated) {
    const truncated = createElement("p", "dependency-truncated");
    truncated.textContent =
      "This graph reached its safety limit. The load check may discover additional transitive packages.";
    content.append(truncated);
  }
  section.replaceChildren(content);
  restoreResourceDetailPosition();
  if (app.resourceDependencyFocus && report.conflicts.length) {
    app.resourceDependencyFocus = false;
    window.setTimeout(
      () =>
        section
          .querySelector(".dependency-conflict-panel")
          ?.focus({ preventScroll: false }),
      0,
    );
  }
}

function restoreResourceDetailPosition() {
  const restore = app.resourceDetailRestore;
  const resourceId = normalizedResourceId(
    Number(elements.resourceDetailDialog?.dataset.resourceId),
  );
  if (!restore || restore.resourceId !== resourceId) return;
  app.resourceDetailRestore = null;
  const scrollTop = Math.max(
    0,
    Math.trunc(numberOr(restore.scrollTop, 0)),
  );
  window.requestAnimationFrame(() => {
    if (
      elements.resourceDetailDialog?.open &&
      normalizedResourceId(
        Number(elements.resourceDetailDialog.dataset.resourceId),
      ) === resourceId
    ) {
      elements.resourceDetailContent.scrollTop = scrollTop;
    }
  });
}

function renderResourceDependencyLoading(section) {
  const header = createElement("div", "resource-detail-section-heading");
  const headingCopy = document.createElement("div");
  const kicker = createElement("p", "eyebrow");
  kicker.textContent = "Detected package graph";
  const heading = document.createElement("h3");
  heading.id = "resource-detail-dependencies-title";
  heading.textContent = "Dependencies";
  const explanation = document.createElement("p");
  explanation.textContent =
    "Tracing direct references and their transitive packages…";
  headingCopy.append(kicker, heading, explanation);
  header.append(headingCopy);
  const loading = createElement("div", "dependency-loading");
  loading.setAttribute("role", "status");
  loading.textContent = "Reading this resource’s package graph…";
  section.replaceChildren(header, loading);
}

function renderResourceDependencyError(section, error) {
  const state = createElement("div", "dependency-error");
  const title = document.createElement("strong");
  title.textContent = "Dependency details unavailable";
  const detail = document.createElement("p");
  detail.textContent = errorMessage(error);
  const retry = button("Retry", "secondary-button");
  retry.addEventListener("click", () =>
    loadResourceDependencyDetails(section, app.resourceDetailItem),
  );
  state.append(title, detail, retry);
  section.replaceChildren(state);
}

async function loadResourceDependencyDetails(
  section,
  item,
  initialPayload = null,
) {
  const resourceId = normalizedResourceId(
    Number(item?.id ?? item?.resource_id),
  );
  if (resourceId === null) {
    renderResourceDependencyReport(section, item, {});
    return;
  }
  if (app.resourceDependencyController) {
    app.resourceDependencyController.abort();
  }
  const controller = new AbortController();
  app.resourceDependencyController = controller;
  const generation = ++app.resourceDependencyGeneration;
  if (initialPayload) {
    renderResourceDependencyReport(section, item, initialPayload);
  } else {
    renderResourceDependencyLoading(section);
  }
  try {
    const packageVersion = resourceDetailsPackageVersion(item);
    const versionQuery =
      packageVersion === null
        ? ""
        : `?package_version=${encodeURIComponent(packageVersion)}`;
    const result = await api(
      `/api/resources/${encodeURIComponent(resourceId)}/details${versionQuery}`,
      { signal: controller.signal },
    );
    if (
      generation !== app.resourceDependencyGeneration ||
      Number(elements.resourceDetailDialog?.dataset.resourceId) !==
        resourceId
    ) {
      return;
    }
    renderResourceDependencyReport(section, item, result);
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (
      generation !== app.resourceDependencyGeneration ||
      Number(elements.resourceDetailDialog?.dataset.resourceId) !==
        resourceId
    ) {
      return;
    }
    if (!initialPayload) {
      renderResourceDependencyError(section, error);
    }
  } finally {
    if (app.resourceDependencyController === controller) {
      app.resourceDependencyController = null;
    }
  }
}

function renderResourceDetailDependencies(
  container,
  item,
  initialPayload = null,
  { refresh = true } = {},
) {
  const section = createElement("section", "resource-detail-dependencies");
  section.setAttribute(
    "aria-labelledby",
    "resource-detail-dependencies-title",
  );
  container.append(section);
  if (initialPayload && !refresh) {
    renderResourceDependencyReport(section, item, initialPayload);
  } else {
    loadResourceDependencyDetails(section, item, initialPayload);
  }
}

function renderResourceDetailVariants(container, item) {
  const variants = normalizeRelatedResourceVariants(item);
  const variantCount = normalizedVariantCount(
    item?.variant_count,
    variants.length,
  );
  const section = createElement("section", "resource-detail-variants");
  section.setAttribute("aria-labelledby", "resource-detail-variants-title");
  const header = createElement("div", "resource-detail-section-heading");
  const headingCopy = document.createElement("div");
  const kicker = createElement("p", "eyebrow");
  kicker.textContent = "Browse-only name matches";
  const heading = document.createElement("h3");
  heading.id = "resource-detail-variants-title";
  heading.textContent = "Styles & variants";
  const explanation = document.createElement("p");
  explanation.textContent =
    "Matched by package, folder, and name. These are catalogue suggestions, not verified semantic variants.";
  headingCopy.append(kicker, heading, explanation);
  const count = createElement("span", "resource-detail-variant-count");
  count.textContent = formatNumber(variantCount);
  count.setAttribute(
    "aria-label",
    `${formatNumber(variantCount)} name ${plural("match", variantCount)}`,
  );
  header.append(headingCopy, count);
  section.append(header);

  if (!variantCount) {
    const empty = createElement("div", "resource-detail-variant-empty");
    const emptyTitle = document.createElement("strong");
    emptyTitle.textContent = "No name-matched variants";
    const emptyCopy = document.createElement("p");
    emptyCopy.textContent =
      "This resource remains fully usable; VAM-PIP did not find related presets in the same package and folder.";
    empty.append(emptyTitle, emptyCopy);
    section.append(empty);
    container.append(section);
    return;
  }

  const ownerTitle = safePresentationLabel(resourceTitle(item), "Resource");
  const ownerSearch = safePresentationLabel(
    item?.variant_search,
    ownerTitle,
  );
  const displayedVariants = variants.slice(
    0,
    MAX_RENDERED_RESOURCE_VARIANTS,
  );
  const gallery = createElement("div", "resource-variant-gallery");
  for (const variant of displayedVariants) {
    gallery.append(createRelatedResourceTile(variant, ownerSearch));
  }
  if (displayedVariants.length) {
    section.append(gallery);
  } else {
    const unavailable = createElement(
      "div",
      "resource-detail-variant-empty",
    );
    const unavailableTitle = document.createElement("strong");
    unavailableTitle.textContent = "Variant details unavailable";
    const unavailableCopy = document.createElement("p");
    unavailableCopy.textContent =
      "The catalogue reports name matches, but none included safe display metadata. Search the owner name to inspect the raw results.";
    const searchMatches = button(
      "Search name matches",
      "secondary-button resource-variant-search-owner",
    );
    const ownerType = String(resourceType(item) || "");
    const browseType = ["clothing female", "clothing male"].includes(
      ownerType.trim().toLowerCase(),
    )
      ? "Clothing Item Presets"
      : ownerType;
    searchMatches.addEventListener("click", () =>
      browseRelatedResource(
        { browseQuery: ownerSearch, type: browseType },
        ownerSearch,
      ),
    );
    unavailable.append(
      unavailableTitle,
      unavailableCopy,
      searchMatches,
    );
    section.append(unavailable);
  }
  if (variantCount > displayedVariants.length) {
    const footer = createElement("div", "resource-variant-footer");
    const showing = createElement("span");
    showing.textContent = `Showing ${formatNumber(
      displayedVariants.length,
    )} of ${formatNumber(variantCount)}`;
    const viewAll = button(
      "View all name matches",
      "quiet-button resource-variant-view-all",
    );
    viewAll.addEventListener("click", () =>
      browseRelatedResource(
        { ...(variants[0] || {}), browseQuery: ownerSearch },
        ownerSearch,
      ),
    );
    footer.append(showing, viewAll);
    section.append(footer);
  }
  container.append(section);
}

function appendResourceDetailFact(list, label, value) {
  const safeValue = safePresentationLabel(value, "");
  if (!safeValue) return;
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = safeValue;
  detail.title = safeValue;
  list.append(term, detail);
}

function openResourceDetailDialog(item, opener) {
  const dialog = elements.resourceDetailDialog;
  const isNewOpen = !dialog.open;
  const model = normalizeResourceCardModel(item, { assumeHidden: true });
  const detailRestore =
    app.resourceDetailRestore?.resourceId === model.id
      ? app.resourceDetailRestore
      : null;
  if (app.resourceDetailRestore && !detailRestore) {
    app.resourceDetailRestore = null;
  }
  const previousResourceId = normalizedResourceId(
    Number(dialog.dataset.resourceId),
  );
  if (previousResourceId !== model.id) {
    app.resourceDependencyPage = detailRestore
      ? Math.max(
          1,
          Math.trunc(numberOr(detailRestore.dependencyPage, 1)),
        )
      : 1;
  }
  dialog.dataset.resourceId =
    model.id === null ? "" : String(model.id);
  app.resourceDetailItem = item;
  app.resourceDetailOpener =
    opener instanceof HTMLElement ? opener : document.activeElement;
  elements.resourceDetailEyebrow.textContent = prettyType(model.type);
  elements.resourceDetailTitle.textContent = model.title;

  const layout = createElement("div", "resource-detail-layout");
  const overview = createElement("section", "resource-detail-overview");
  overview.setAttribute("aria-label", "Resource overview");
  const preview = createElement("div", "resource-detail-preview");
  const fallback = createElement("span", "resource-detail-preview-fallback");
  fallback.textContent = initials(model.title);
  fallback.setAttribute("aria-hidden", "true");
  preview.append(fallback);
  const thumbnail =
    model.thumbnail ||
    (model.id !== null ? resourceThumbnailUrl(model.id) : "");
  if (thumbnail) {
    const image = document.createElement("img");
    image.alt = `Preview of ${model.title}`;
    image.decoding = "async";
    image.addEventListener("load", () => image.classList.add("is-loaded"));
    image.addEventListener("error", () => image.remove());
    image.src = thumbnail;
    preview.append(image);
  }
  const previewBadges = createElement("div", "resource-detail-preview-badges");
  previewBadges.append(
    badge(
      model.stateLabel,
      `state-badge ${
        model.state === "active" || model.state === "local"
          ? "is-active"
          : "is-hidden"
      }`,
    ),
  );
  if (model.favorite) {
    previewBadges.append(badge("★ Favorite", "type-badge is-favorite"));
  }
  preview.append(previewBadges);
  overview.append(preview);

  const summary = createElement("div", "resource-detail-summary");
  const subtitle = document.createElement("p");
  subtitle.textContent = [model.creator, model.packageLabel]
    .filter(Boolean)
    .join(" · ");
  summary.append(subtitle);
  const metadata = createElement("div", "resource-detail-meta");
  metadata.append(badge(prettyType(model.type), "meta-pill"));
  if (model.updateVersion !== null) {
    metadata.append(
      badge(
        `v${model.selectedVersionLabel} → v${model.updateVersion} available`,
        "meta-pill version-update",
      ),
    );
  } else if (
    model.selectedVersion !== null ||
    model.selectedVersionLabel !== "?"
  ) {
    metadata.append(badge(`v${model.selectedVersionLabel}`, "meta-pill"));
  }
  if (item.atom_type || item.atomType) {
    metadata.append(
      badge(
        safePresentationLabel(item.atom_type || item.atomType, "Atom"),
        "meta-pill",
      ),
    );
  }
  summary.append(metadata);
  if (model.missingDetail) {
    const missing = createElement("p", "resource-detail-missing");
    missing.textContent = model.missingDetail;
    summary.append(missing);
  }

  const facts = createElement("dl", "resource-detail-facts");
  appendResourceDetailFact(facts, "Creator", model.creator);
  appendResourceDetailFact(facts, "Package", model.packageLabel);
  appendResourceDetailFact(facts, "Resource type", prettyType(model.type));
  appendResourceDetailFact(
    facts,
    "Selected version",
    model.selectedVersionLabel === "?"
      ? ""
      : `v${model.selectedVersionLabel}`,
  );
  appendResourceDetailFact(
    facts,
    "Package state",
    model.stateLabel,
  );
  summary.append(facts);

  if (model.tags.length) {
    const tagGroup = createElement("div", "resource-detail-tags");
    const tagTitle = document.createElement("strong");
    tagTitle.textContent = "Tags";
    const tags = document.createElement("div");
    for (const tag of model.tags.slice(0, 12)) {
      tags.append(badge(tag, "meta-pill"));
    }
    if (model.tags.length > 12) {
      tags.append(
        badge(
          `+${formatNumber(model.tags.length - 12)} more`,
          "meta-pill",
        ),
      );
    }
    tagGroup.append(tagTitle, tags);
    summary.append(tagGroup);
  }

  const actions = createElement(
    "div",
    "resource-detail-actions card-actions",
  );
  appendResourceActions(actions, item, model);
  if (actions.children.length) summary.append(actions);
  overview.append(summary);
  const catalogue = createElement("div", "resource-detail-catalogue");
  layout.append(overview, catalogue);
  const pendingConflict =
    app.pendingResourceConflict &&
    app.pendingResourceConflict.resourceId === model.id
      ? app.pendingResourceConflict
      : null;
  const reusableDependencyReport =
    !pendingConflict &&
    previousResourceId === model.id &&
    app.resourceDependencyReport
      ? app.resourceDependencyReport
      : null;
  if (pendingConflict) app.pendingResourceConflict = null;
  renderResourceDetailDependencies(
    catalogue,
    item,
    pendingConflict?.payload || reusableDependencyReport,
    { refresh: !reusableDependencyReport },
  );
  renderResourceDetailVariants(catalogue, item);
  elements.resourceDetailContent.replaceChildren(layout);

  if (isNewOpen) {
    dialog.returnValue = "";
    dialog.showModal();
  }
  document.body.classList.add("resource-detail-open");
  if (isNewOpen) {
    window.setTimeout(() => elements.resourceDetailClose.focus(), 0);
  }
}

function handleResourceDetailBackdrop(event) {
  if (
    event.target === elements.resourceDetailDialog &&
    elements.resourceDetailDialog.open
  ) {
    elements.resourceDetailDialog.close("backdrop");
  }
}

function handleResourceDetailClose() {
  if (app.resourceDependencyController) {
    app.resourceDependencyController.abort();
    app.resourceDependencyController = null;
  }
  app.resourceDependencyGeneration += 1;
  app.resourceDependencyReport = null;
  app.resourceDependencyFocus = false;
  app.resourceDetailRestore = null;
  app.resourceDetailItem = null;
  app.pendingResourceConflict = null;
  document.body.classList.remove("resource-detail-open");
  elements.resourceDetailContent.replaceChildren();
  const opener = app.resourceDetailOpener;
  app.resourceDetailOpener = null;
  delete elements.resourceDetailDialog.dataset.resourceId;
  const suppressRestore = [
    "browse",
    "category-change",
    "library-render",
    "view-change",
  ].includes(elements.resourceDetailDialog.returnValue);
  if (
    !suppressRestore &&
    opener instanceof HTMLElement &&
    opener.isConnected
  ) {
    opener.focus({ preventScroll: true });
  }
}

function normalizedVariantCount(value, loadedCount) {
  const safeLoadedCount =
    Number.isSafeInteger(loadedCount) && loadedCount >= 0
      ? loadedCount
      : 0;
  if (
    !Number.isSafeInteger(value) ||
    value < safeLoadedCount ||
    value > MAX_VARIANT_MATCH_COUNT
  ) {
    return safeLoadedCount;
  }
  return value;
}

function clothingCategoryForItem(item) {
  const type = resourceType(item).trim().toLowerCase();
  const categoryId =
    type === "clothing (male)"
      ? "clothing-items-male"
      : type === "clothing (female)"
        ? "clothing-items-female"
        : genderItemCategoryIds()[0] || "";
  return (
    ensureWorkspaceCategories().find(
      (category) => category.id === categoryId,
    ) || null
  );
}

function equipmentPackageVersion(item) {
  const value = item.package_version ?? item.selected_version;
  if (
    Number.isInteger(value) &&
    value >= 0 &&
    value <= 2_147_483_647
  ) {
    return value;
  }
  if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    const parsed = Number(value);
    if (Number.isSafeInteger(parsed) && parsed <= 2_147_483_647) return parsed;
  }
  return null;
}

function resourceDetailsPackageVersion(item) {
  const numericVersion = equipmentPackageVersion(item);
  if (numericVersion !== null) return numericVersion;
  const value = item?.package_version ?? item?.selected_version;
  if (
    typeof value === "string" &&
    value.trim().toLowerCase() === "latest"
  ) {
    return "latest";
  }
  const packageRef = String(
    item?.package_ref ?? item?.packageRef ?? "",
  ).trim();
  return /\.latest$/i.test(packageRef) ? "latest" : null;
}

function equipmentItemKey(item) {
  const resourceId = integerValue(item?.id ?? item?.resource_id);
  if (resourceId === null || resourceId < 1) {
    if (item?.actionable !== false) return "";
    const presentationKey = safeOpaqueKey(item.presentation_key, "");
    return presentationKey ? `presentation:${presentationKey}` : "";
  }
  if (booleanValue(item?.local, false)) {
    return `resource:${resourceId}:local`;
  }
  const packageVersion = equipmentPackageVersion(item);
  return `resource:${resourceId}:package:${
    packageVersion === null ? "unknown" : packageVersion
  }`;
}

function createEquippedItem(item) {
  const resourceId = integerValue(item.id ?? item.resource_id);
  const actionable =
    item.actionable !== false && resourceId !== null && resourceId > 0;
  const row = createElement(
    "article",
    `equipped-item${item.clothing_locked ? " is-locked" : ""}${
      actionable ? "" : " is-presentation-only"
    }`,
  );
  const visual = createElement("span", "equipped-item-visual");
  const fallback = createElement("span", "equipped-item-fallback");
  fallback.textContent = initials(resourceTitle(item));
  fallback.setAttribute("aria-hidden", "true");
  visual.append(fallback);
  if (actionable) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => image.remove());
    image.src = item.thumbnail_url || resourceThumbnailUrl(resourceId);
    visual.append(image);
  }

  const packageVersion = equipmentPackageVersion(item);
  const local = booleanValue(item.local, false);
  const versionLabel =
    !local && packageVersion !== null ? ` v${packageVersion}` : "";
  const copy = createElement("span", "equipped-item-copy");
  const name = createElement("strong");
  name.textContent = resourceTitle(item);
  name.title = name.textContent;
  const details = createElement("span");
  const detailParts = actionable
    ? [
        String(
          item.creator ||
            creatorFromRoot(packageRoot(item)) ||
            "Unknown creator",
        ),
      ]
    : ["In-game item", item.clothing_locked ? "Locked in VaM" : "Managed in VaM"];
  const packageName = actionable
    ? String(item.package || item.package_name || "").trim()
    : "";
  if (packageName) detailParts.push(packageName);
  if (actionable && versionLabel) detailParts.push(versionLabel.trim());
  details.textContent = detailParts.join(" · ");
  copy.append(name, details);

  if (!actionable) {
    const inGame = createElement("span", "equipment-in-game-badge");
    inGame.textContent = "In-game item";
    inGame.title =
      "This live item is not safely matched to the catalogue; manage it inside VaM";
    row.append(visual, copy, inGame);
    return row;
  }

  const category = clothingCategoryForItem(item);
  const availability = clothingActionAvailability(item, category);
  const requiresPackageVersion = !local;
  const remove = button(
    item.clothing_locked ? "Locked" : "Remove",
    "secondary-button equipment-remove",
  );
  const versionUnavailable =
    requiresPackageVersion && packageVersion === null;
  remove.disabled =
    !availability.allowed ||
    versionUnavailable ||
    app.clothingMutationInFlight;
  remove.dataset.equipmentRemove = equipmentItemKey(item);
  remove.setAttribute(
    "aria-label",
    item.clothing_locked
      ? `${resourceTitle(item)}${versionLabel} is locked in VaM`
      : `Remove ${resourceTitle(item)}${versionLabel} from ${app.selectedPersonUid}`,
  );
  remove.title = versionUnavailable
    ? "The exact package version is unavailable; refresh the live loadout"
    : availability.reason ||
      `Remove ${resourceTitle(item)}${versionLabel} from the live loadout`;
  row.append(visual, copy, remove);
  return row;
}

function createEquipmentSlot(slot, items, { loading = false } = {}) {
  const section = createElement("section", "equipment-slot");
  section.dataset.equipmentSlot = slot.id;
  const heading = createElement("div", "equipment-slot-heading");
  const label = createElement("strong");
  label.textContent = slot.label;
  const count = badge(
    loading ? "…" : String(items.length),
    "equipment-slot-count",
  );
  heading.append(label, count);

  const body = createElement("div", "equipment-slot-items");
  if (loading) {
    const loadingMessage = createElement("span", "equipment-slot-empty");
    loadingMessage.textContent = "Reading live items…";
    body.append(loadingMessage);
  } else if (!items.length) {
    const empty = createElement("span", "equipment-slot-empty");
    empty.textContent = "No active items";
    body.append(empty);
  } else {
    const expanded = app.equipmentExpandedSlots.has(slot.id);
    const visibleItems = expanded
      ? items
      : items.slice(0, CHARACTER_SLOT_VISIBLE_ITEMS);
    for (const item of visibleItems) body.append(createEquippedItem(item));
    if (items.length > CHARACTER_SLOT_VISIBLE_ITEMS) {
      const remaining = items.length - CHARACTER_SLOT_VISIBLE_ITEMS;
      const expand = button(
        expanded ? "Show less" : `+${remaining} more`,
        "quiet-button equipment-expand",
      );
      expand.dataset.equipmentExpand = slot.id;
      expand.setAttribute("aria-expanded", String(expanded));
      body.append(expand);
    }
  }
  section.append(heading, body);
  return section;
}

function renderWardrobeCharacterSheet(category) {
  const identity = personEquipmentIdentity();
  const equipment =
    identity &&
    app.personEquipmentKey === identity.key &&
    app.personEquipment
      ? app.personEquipment
      : null;
  const clothing = selectedPersonClothing();
  const activeCount = Math.max(
    0,
    numberOr(equipment?.activeCount ?? clothing?.activeCount, 0),
  );
  const lockedCount = Math.max(
    0,
    numberOr(equipment?.lockedCount ?? clothing?.lockedCount, 0),
  );
  const gender = String(equipment?.gender || clothing?.gender || "Unknown");
  const loading = Boolean(identity && app.personEquipmentLoading && !equipment);
  const items = equipment?.items || [];
  const grouped = new Map(
    CHARACTER_SHEET_SLOTS.map((slot) => [slot.id, []]),
  );
  for (const item of items) {
    grouped.get(equipmentSlotForItem(item))?.push(item);
  }
  for (const slotItems of grouped.values()) {
    slotItems.sort((left, right) =>
      resourceTitle(left).localeCompare(resourceTitle(right), undefined, {
        sensitivity: "base",
      }),
    );
  }

  const renderKey = JSON.stringify({
    category: category?.id || "",
    target: app.selectedPersonUid,
    revision: identity?.revision || "",
    loading,
    error: app.personEquipmentError
      ? errorMessage(app.personEquipmentError)
      : "",
    activeCount,
    lockedCount,
    gender,
    truncated: Boolean(equipment?.truncated ?? clothing?.truncated),
    unidentified: numberOr(equipment?.unidentifiedCount, 0),
    expanded: Array.from(app.equipmentExpandedSlots).sort(),
    mutating: app.clothingMutationInFlight,
    items: items.map((item) => [
      item.id,
      item.presentation_key || "",
      item.actionable !== false,
      resourceTitle(item),
      item.creator || "",
      Boolean(item.clothing_locked),
      item.clothing_revision || "",
      item.package_version ?? item.selected_version ?? null,
      equipmentSlotForItem(item),
    ]),
  });
  if (elements.characterSheet.dataset.renderKey === renderKey) return;
  elements.characterSheet.dataset.renderKey = renderKey;
  elements.characterSheet.setAttribute("aria-busy", String(loading));
  elements.wardrobeSheet.hidden = false;
  elements.hairStudio.hidden = true;
  elements.characterRecipe.hidden = true;

  elements.characterSheetTitle.textContent = "Character loadout";
  elements.characterSheetSummary.textContent =
    "Live clothing is organized into explicit multi-item sections, including underwear, stockings, shoes, and heels.";
  elements.characterIdentityName.textContent =
    app.selectedPersonUid || "No Person selected";
  elements.characterIdentityGender.textContent =
    gender && gender !== "None" ? gender : "Gender unavailable";
  elements.characterIdentityCounts.textContent =
    `${formatNumber(activeCount)} worn · ${formatNumber(lockedCount)} locked`;

  elements.equipmentSlotsLeft.replaceChildren();
  elements.equipmentSlotsRight.replaceChildren();
  elements.equipmentSlotsExtra.replaceChildren();
  for (const slot of CHARACTER_SHEET_SLOTS) {
    const slotElement = createEquipmentSlot(
      slot,
      grouped.get(slot.id) || [],
      { loading },
    );
    if (slot.column === "left") {
      elements.equipmentSlotsLeft.append(slotElement);
    } else if (slot.column === "right") {
      elements.equipmentSlotsRight.append(slotElement);
    } else {
      elements.equipmentSlotsExtra.append(slotElement);
    }
  }

  const warnings = [];
  if (app.personEquipmentError) {
    warnings.push(`Loadout unavailable: ${errorMessage(app.personEquipmentError)}`);
  } else if (!identity && personVamRunning() && selectedPersonSnapshot()) {
    warnings.push(
      "The live bridge is not publishing a revisioned clothing roster for this Person.",
    );
  }
  const unidentifiedCount = Math.max(
    0,
    numberOr(
      equipment?.unidentifiedCount,
      items.filter((item) => item.actionable === false).length +
        Math.max(0, activeCount - items.length),
    ),
  );
  if (unidentifiedCount) {
    warnings.push(
      `${formatNumber(unidentifiedCount)} active ${plural(
        "item",
        unidentifiedCount,
      )} could not be matched to the local catalogue. They remain visible as read-only in-game items.`,
    );
  }
  if (booleanValue(equipment?.truncated ?? clothing?.truncated, false)) {
    warnings.push(
      "The bridge truncated this roster; unidentified items remain active in VaM.",
    );
  }
  elements.equipmentWarning.hidden = warnings.length === 0;
  elements.equipmentWarning.textContent = warnings.join(" ");
}

function hairActionAvailability(item, hair = app.personHair) {
  const snapshot = app.person || {};
  const identity = personHairIdentity();
  const itemKey = safeHairActionKey(item?.key);
  const rosterRevision = String(hair?.revision || "").trim().toLowerCase();
  let reason = "";

  if (item?.locked === true) {
    reason = "This hair layer is locked in VaM";
  } else if (item?.actionable !== true) {
    reason =
      "This layer is presentation-only and must be managed inside VaM";
  } else if (!itemKey) {
    reason = "This hair layer has no safe action key";
  } else if (characterSheetMode() !== "hair") {
    reason = "Open Hair Studio before changing a hair layer";
  } else if (app.personError) {
    reason = "The live VaM bridge is unavailable";
  } else if (!personVamRunning(snapshot)) {
    reason = "Start VaM before changing hair";
  } else if (!snapshot.available) {
    reason = "The bridge is not publishing a fresh scene snapshot";
  } else if (snapshot.loading) {
    reason = "Wait for VaM to finish loading the scene";
  } else if (
    !identity ||
    !hair ||
    hair.available !== true ||
    hair.ready !== true ||
    app.personHairKey !== identity.key
  ) {
    reason = "Refresh the active hair roster before changing it";
  } else if (
    !/^[0-9a-f]{32}$/.test(rosterRevision) ||
    rosterRevision !== identity.revision
  ) {
    reason = "The hair state changed; wait for this roster to refresh";
  } else if (app.hairMutationInFlight) {
    reason = "Wait for the current hair change to be queued";
  } else if (app.pendingHairMutation) {
    reason = "Wait for the pending hair change to finish in VaM";
  } else if (snapshotBridgeBusy(snapshot)) {
    reason = "Wait for the current bridge action to finish";
  } else if (workspaceActionIsActive()) {
    reason = "Wait for the current Hair preset load to finish";
  } else if (operationIsBusy()) {
    reason = "Wait for the current package update to finish";
  }

  return {
    allowed: reason === "",
    reason,
    itemKey,
    revision: rosterRevision,
  };
}

function pendingHairMutationFor(item, hair) {
  const pending = app.pendingHairMutation;
  return Boolean(
    pending &&
      pending.targetUid === app.selectedPersonUid &&
      pending.revision === String(hair?.revision || "").trim().toLowerCase() &&
      pending.itemKey === item?.key,
  )
    ? pending
    : null;
}

async function disableHairLayer(itemKeyValue, sourceButton) {
  if (app.hairMutationInFlight || app.pendingHairMutation) return;
  const identity = personHairIdentity();
  const hair =
    identity && app.personHairKey === identity.key ? app.personHair : null;
  const itemKey = safeHairActionKey(itemKeyValue);
  const item = asArray(hair?.items).find(
    (candidate) => candidate.key === itemKey,
  );
  if (!item) {
    toast(
      "Hair roster changed",
      "This layer is no longer in the selected Person’s active hair roster.",
      "error",
    );
    await syncPersonHair({ quiet: true, retry: true });
    return;
  }
  const availability = hairActionAvailability(item, hair);
  if (!availability.allowed) {
    toast("Hair state changed", availability.reason, "error");
    return;
  }

  const targetUid = identity.targetUid;
  const revision = availability.revision;
  const displayName = item.displayName;
  const pending = {
    targetUid,
    revision,
    itemKey: availability.itemKey,
    displayName,
    state: "sending",
    requestId: "",
  };
  app.hairMutationInFlight = true;
  app.pendingHairMutation = pending;
  renderCharacterSheet();
  if (app.view === "workspace") renderLibrary();

  try {
    const result = await api("/api/vam/person/hair", {
      method: "POST",
      body: {
        target_uid: targetUid,
        revision,
        item_key: availability.itemKey,
        active: false,
      },
    });
    requireWorkspaceBridgeQueue(result, "Hair disable");
    const responseRevision = String(result.revision || "").trim().toLowerCase();
    if (
      result.operation !== "set-person-hair" ||
      String(result.target_uid || "") !== targetUid ||
      responseRevision !== revision ||
      String(result.item_key || "") !== availability.itemKey ||
      result.active !== false
    ) {
      throw new Error(
        "Hair disable returned a mismatched response; the live roster was not assumed to have changed.",
      );
    }
    pending.state = "queued";
    pending.requestId = String(result.bridge_request || "").trim();
    toast(
      "Hair disable queued",
      result.bridge_message ||
        `“${displayName}” will be disabled for ${targetUid}.`,
    );
    app.personPollAt = 0;
    await loadPersons({ quiet: true });
    await syncPersonHair({ quiet: true, retry: true });
  } catch (error) {
    if (app.pendingHairMutation === pending) {
      app.pendingHairMutation = null;
    }
    toast(
      `Could not disable ${displayName}`,
      errorMessage(error),
      "error",
    );
    if (/revision|stale|changed/i.test(errorMessage(error))) {
      app.personPollAt = 0;
      await loadPersons({ quiet: true });
      await syncPersonHair({ quiet: true, retry: true });
    }
  } finally {
    app.hairMutationInFlight = false;
    if (
      app.pendingHairMutation === pending &&
      pending.state === "sending"
    ) {
      app.pendingHairMutation = null;
    }
    setButtonBusy(sourceButton, false);
    renderCharacterSheet();
    if (app.view === "workspace") renderLibrary();
  }
}

function createHairLayerCard(item, index, hair) {
  const card = createElement("article", "hair-layer-card");
  card.classList.toggle("is-locked", item.locked);
  card.classList.toggle("is-presentation-only", item.actionable !== true);
  const visual = createElement("span", "hair-layer-visual");
  visual.textContent = String(index + 1);
  visual.setAttribute("aria-hidden", "true");
  const copy = createElement("div", "hair-layer-copy");
  const name = createElement("strong");
  name.textContent = item.displayName;
  name.title = item.displayName;
  const tags = createElement("div", "hair-layer-tags");
  if (item.tags.length) {
    for (const tag of item.tags) {
      const tagElement = createElement("span");
      tagElement.textContent = tag;
      tags.append(tagElement);
    }
  } else {
    const noTags = createElement("span", "hair-layer-no-tags");
    noTags.textContent = "No public tags";
    tags.append(noTags);
  }
  copy.append(name, tags);
  const status = badge(
    item.simulated ? "Simulated" : "Mesh / legacy",
    `hair-simulation-state${item.simulated ? " is-simulated" : ""}`,
  );
  const actions = createElement("div", "hair-layer-actions");
  actions.append(status);
  if (item.locked) {
    const locked = createElement("span", "hair-layer-control is-locked");
    locked.textContent = "Locked";
    locked.title = "Unlock this layer inside VaM before disabling it";
    actions.append(locked);
  } else if (item.actionable !== true) {
    const presentation = createElement(
      "span",
      "hair-layer-control is-presentation-only",
    );
    presentation.textContent = "In-game only";
    presentation.title =
      "The bridge did not provide a safe action for this layer";
    actions.append(presentation);
  } else {
    const availability = hairActionAvailability(item, hair);
    const pending = pendingHairMutationFor(item, hair);
    const disable = button(
      pending
        ? pending.state === "sending"
          ? "Disabling…"
          : "Waiting for VaM…"
        : "Disable",
      "secondary-button hair-disable-button",
    );
    disable.disabled = !availability.allowed || Boolean(pending);
    disable.dataset.hairDisable = item.key;
    disable.setAttribute(
      "aria-label",
      `Disable ${item.displayName} for ${app.selectedPersonUid}`,
    );
    disable.title = pending
      ? "This hair change is queued in VaM"
      : availability.reason ||
        `Disable ${item.displayName} without changing other active layers`;
    actions.append(disable);
  }
  card.append(visual, copy, actions);
  return card;
}

function renderHairInspectorGroups() {
  elements.hairInspectorGroups.replaceChildren();
  for (const definition of HAIR_INSPECTOR_GROUPS) {
    const group = createElement("section", "hair-inspector-group");
    const copy = createElement("div");
    const title = createElement("strong");
    title.textContent = definition.title;
    const detail = createElement("p");
    detail.textContent = definition.detail;
    copy.append(title, detail);
    const state = createElement("span", "hair-detail-state");
    state.textContent = "Details in VaM";
    group.append(copy, state);
    elements.hairInspectorGroups.append(group);
  }
}

function renderHairStudio(category) {
  const identity = personHairIdentity();
  const hair =
    identity && app.personHairKey === identity.key ? app.personHair : null;
  const loading = Boolean(
    identity && app.personHairLoading && !hair,
  );
  const items = hair?.items || [];
  const activeCount = Math.max(0, numberOr(hair?.activeCount, items.length));
  const simCount = Math.max(
    0,
    numberOr(
      hair?.simCount,
      items.filter((item) => item.simulated).length,
    ),
  );
  const lockedCount = Math.max(
    0,
    numberOr(
      hair?.lockedCount,
      items.filter((item) => item.locked).length,
    ),
  );
  const renderKey = JSON.stringify({
    mode: "hair",
    category: category?.id || "",
    target: app.selectedPersonUid,
    loading,
    error: app.personHairError ? errorMessage(app.personHairError) : "",
    available: Boolean(hair?.available),
    ready: Boolean(hair?.ready),
    revision: hair?.revision || "",
    activeCount,
    simCount,
    lockedCount,
    truncated: Boolean(hair?.truncated),
    mutating: app.hairMutationInFlight,
    pending: app.pendingHairMutation
      ? [
          app.pendingHairMutation.targetUid,
          app.pendingHairMutation.revision,
          app.pendingHairMutation.itemKey,
          app.pendingHairMutation.state,
        ]
      : null,
    items: items.map((item) => [
      item.key,
      item.displayName,
      item.tags,
      item.locked,
      item.actionable,
      item.simulated,
    ]),
  });
  if (elements.characterSheet.dataset.renderKey === renderKey) return;
  elements.characterSheet.dataset.renderKey = renderKey;
  elements.characterSheet.setAttribute("aria-busy", String(loading));
  elements.wardrobeSheet.hidden = true;
  elements.equipmentWarning.hidden = true;
  elements.hairStudio.hidden = false;
  elements.characterRecipe.hidden = true;

  elements.characterSheetTitle.textContent = "Hair Studio";
  elements.characterSheetSummary.textContent =
    "Inspect every active hair layer. Presets remain in the library below; typed setting controls will arrive separately.";
  if (loading) {
    elements.hairStudioSummary.textContent =
      "Reading active hair layers from VaM…";
  } else if (hair?.available && hair.ready) {
    elements.hairStudioSummary.textContent =
      `${formatNumber(activeCount)} active ${plural(
        "layer",
        activeCount,
      )} · ${formatNumber(simCount)} simulated · ${formatNumber(
        lockedCount,
      )} locked`;
  } else {
    elements.hairStudioSummary.textContent =
      "Live hair details are not available for this Person yet.";
  }

  elements.hairLayerList.replaceChildren();
  if (loading) {
    const state = createElement("p", "hair-layer-empty");
    state.textContent = "Reading live hair layers…";
    elements.hairLayerList.append(state);
  } else if (app.personHairError) {
    const state = createElement("p", "hair-layer-empty");
    state.textContent =
      "The live roster could not be read. Hair presets are still browseable below.";
    elements.hairLayerList.append(state);
  } else if (!hair?.available || !hair.ready) {
    const state = createElement("p", "hair-layer-empty");
    state.textContent =
      "The bridge has not published a typed hair roster. VAM-PIP will not guess the current preset.";
    elements.hairLayerList.append(state);
  } else if (!items.length) {
    const state = createElement("p", "hair-layer-empty");
    state.textContent = "No active hair layers were reported for this Person.";
    elements.hairLayerList.append(state);
  } else {
    items.forEach((item, index) =>
      elements.hairLayerList.append(createHairLayerCard(item, index, hair)),
    );
  }
  renderHairInspectorGroups();

  const warnings = [];
  if (app.personHairError) {
    warnings.push(`Hair roster unavailable: ${errorMessage(app.personHairError)}`);
  } else if (hair && !hair.available) {
    warnings.push(
      "The loaded bridge does not expose live hair details. The library below remains available.",
    );
  } else if (hair?.available && !hair.ready) {
    warnings.push(
      "VaM has not finished publishing this Person’s hair roster.",
    );
  }
  if (activeCount > items.length) {
    const missingCount = activeCount - items.length;
    warnings.push(
      `${formatNumber(missingCount)} active ${plural(
        "layer",
        missingCount,
      )} could not be described safely.`,
    );
  }
  if (hair?.truncated) {
    warnings.push("The bridge truncated the active hair roster.");
  }
  elements.hairWarning.hidden = warnings.length === 0;
  elements.hairWarning.textContent = warnings.join(" ");
}

function renderCharacterRecipe(category) {
  const clothing = selectedPersonClothing();
  const gender = String(clothing?.gender || "Unknown");
  const scopes =
    CHARACTER_RECIPE_SCOPES[category?.id] || [category?.label || "Person"];
  const appearanceCategory = [
    "preset-appearance",
    "preset-skin",
    "preset-morphs",
  ].includes(category?.id);
  const title = appearanceCategory
    ? "Appearance recipe"
    : `${category?.label || "Person"} recipe`;
  const renderKey = JSON.stringify({
    mode: "recipe",
    category: category?.id || "",
    target: app.selectedPersonUid,
    gender,
    scopes,
    liveAction: Boolean(category?.liveAction),
  });
  if (elements.characterSheet.dataset.renderKey === renderKey) return;
  elements.characterSheet.dataset.renderKey = renderKey;
  elements.characterSheet.setAttribute("aria-busy", "false");
  elements.wardrobeSheet.hidden = true;
  elements.equipmentWarning.hidden = true;
  elements.hairStudio.hidden = true;
  elements.hairWarning.hidden = true;
  elements.characterRecipe.hidden = false;

  elements.characterSheetTitle.textContent = title;
  elements.characterSheetSummary.textContent =
    "A compact, category-specific view of what the selected preset can change—never a guessed current preset.";
  elements.characterRecipeMonogram.textContent = app.selectedPersonUid
    ? initials(app.selectedPersonUid)
    : "?";
  elements.characterRecipePerson.textContent =
    app.selectedPersonUid || "No Person selected";
  elements.characterRecipeGender.textContent =
    gender && gender !== "None" ? gender : "Gender unavailable";
  elements.characterRecipeTitle.textContent = `${category?.label || "Person"} scope`;
  elements.characterRecipeDescription.textContent =
    category?.description ||
    "Choose a card below to use this Person resource family.";
  elements.characterRecipeScopes.replaceChildren();
  for (const scope of scopes) {
    elements.characterRecipeScopes.append(
      badge(scope, "character-recipe-scope"),
    );
  }
  elements.characterRecipeNote.textContent = category?.liveAction
    ? `Current ${category.noun || "preset"}: not published by VaM. Choose a card below to apply one to the selected Person.`
    : `Current ${category?.noun || "state"}: not published by VaM. This category remains browse-only.`;
}

function renderCharacterSheet() {
  const category = currentWorkspaceCategory();
  const mode = characterSheetMode(category);
  const visible = mode !== "hidden";
  elements.characterSheet.hidden = !visible;
  if (!visible) return;

  elements.characterSheet.dataset.mode = mode;
  renderCharacterShortcuts();
  if (mode === "wardrobe") {
    renderWardrobeCharacterSheet(category);
  } else if (mode === "hair") {
    renderHairStudio(category);
  } else {
    renderCharacterRecipe(category);
  }
}

async function removeEquippedItem(itemKeyValue, sourceButton) {
  if (app.clothingMutationInFlight) return;
  const itemKey = String(itemKeyValue || "");
  const item = asArray(app.personEquipment?.items).find(
    (candidate) => equipmentItemKey(candidate) === itemKey,
  );
  if (!item) {
    toast(
      "Loadout changed",
      "This item is no longer in the selected Person’s live loadout.",
      "error",
    );
    await syncPersonEquipment({ quiet: true, retry: true });
    return;
  }
  if (
    item.actionable === false ||
    integerValue(item.id ?? item.resource_id) === null
  ) {
    toast(
      "Managed inside VaM",
      "This in-game item is not safely matched to the catalogue, so VAM-PIP will not guess a removal action.",
      "error",
    );
    return;
  }
  const category = clothingCategoryForItem(item);
  if (!category) {
    toast(
      "Clothing category unavailable",
      "Refresh the Workspace category map before removing this item.",
      "error",
    );
    return;
  }
  const packageVersion = equipmentPackageVersion(item);
  if (
    !booleanValue(item.local, false) &&
    packageVersion === null
  ) {
    toast(
      "Exact package version unavailable",
      "Refresh the live loadout before removing this item.",
      "error",
    );
    return;
  }
  await setPersonClothing(
    item,
    category,
    sourceButton,
    packageVersion,
    false,
  );
}

async function loadPersons({ quiet = false } = {}) {
  if (app.personInFlight) return app.person;
  app.personInFlight = true;
  const previousKey = personControlKey();
  const requestGeneration = beginPersonSnapshotRequest();
  let responseAccepted = false;
  try {
    const snapshot = await fetchLiveSceneSnapshot();
    responseAccepted = acceptPersonSnapshot(snapshot, requestGeneration);
  } catch (error) {
    responseAccepted = acceptPersonSnapshotError(error, requestGeneration);
    if (responseAccepted && !quiet) {
      toast(
        "Live Person controls unavailable",
        `${errorMessage(error)} Catalogue browsing is still available.`,
        "error",
      );
    }
  } finally {
    app.personInFlight = false;
    if (responseAccepted) {
      await syncPersonEquipment({ quiet: true });
      await syncPersonHair({ quiet: true });
      renderLiveState(app.status || {});
      renderPersonContext();
      renderAtomContext();
      if (app.view === "sam3d") {
        renderSam3dTargets();
        renderSam3dReferenceState();
        renderSam3dBodyProportions();
        renderSam3dApplyState();
      }
      if (app.view === "workspace" && previousKey !== personControlKey()) {
        if (isIndividualClothingCategory()) {
          await loadLibrary({ preservePage: true });
        } else {
          renderLibrary();
        }
      }
    }
  }
  return app.person;
}

function renderPersonContext() {
  const category = currentWorkspaceCategory();
  const isPersonCategory = categoryUsesPersonContext(category);
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
  renderCharacterSheet();
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

const Sam3dClient = Object.freeze({
  paths: Object.freeze({
    status: "/api/sam3d/status",
    jobs: "/api/sam3d/jobs",
    job(jobId) {
      return `/api/sam3d/jobs/${encodeURIComponent(sam3dJobId(jobId))}`;
    },
    run(jobId) {
      return `${this.job(jobId)}/run`;
    },
    apply(jobId) {
      return `${this.job(jobId)}/apply`;
    },
    undo(jobId) {
      return `${this.job(jobId)}/undo`;
    },
    capture(jobId) {
      return `${this.job(jobId)}/capture`;
    },
    bodyProportions(jobId) {
      return `${this.job(jobId)}/body-proportions`;
    },
    reference(jobId) {
      return `${this.job(jobId)}/reference`;
    },
    artifact(jobId, kind) {
      const allowed = new Set([
        "capture",
        "manifest",
        "overlay",
        "source",
      ]);
      const artifactKind = String(kind || "").toLowerCase();
      if (!allowed.has(artifactKind)) {
        throw new Error("Unsupported SAM 3D artifact");
      }
      return `${this.job(jobId)}/artifacts/${artifactKind}`;
    },
  }),

  status(signal) {
    return api(this.paths.status, { signal });
  },

  listJobs(signal) {
    return api(`${this.paths.jobs}?limit=30&offset=0`, { signal });
  },

  job(jobId, signal) {
    return api(this.paths.job(jobId), { signal });
  },

  create(
    file,
    bbox,
    verticalFov = null,
    modelId = "",
    comparisonId = "",
  ) {
    const query = new URLSearchParams();
    if (bbox) {
      query.set("bbox", bbox.map((value) => Math.round(value)).join(","));
    }
    if (verticalFov !== null) {
      query.set("vertical_fov", String(verticalFov));
    }
    if (modelId) query.set("model_id", modelId);
    if (comparisonId) query.set("comparison_id", comparisonId);
    return sam3dRawApi(`${this.paths.jobs}?${query}`, file);
  },

  run(jobId) {
    return api(this.paths.run(jobId), {
      method: "POST",
      body: {},
    });
  },

  apply(jobId, request) {
    return api(this.paths.apply(jobId), {
      method: "POST",
      body: request,
    });
  },

  showReference(jobId, request) {
    return api(this.paths.reference(jobId), {
      method: "POST",
      body: request,
    });
  },

  hideReference(jobId, expectedJobRevision) {
    return api(this.paths.reference(jobId), {
      method: "DELETE",
      body: { expected_job_revision: expectedJobRevision },
    });
  },

  undo(jobId, expectedRevision) {
    return api(this.paths.undo(jobId), {
      method: "POST",
      body: { expected_revision: expectedRevision },
    });
  },

  capture(jobId, request) {
    return api(this.paths.capture(jobId), {
      method: "POST",
      body: request,
    });
  },

  bodyProportions(
    jobId,
    {
      targetUid = "",
      personIndex = 0,
      strength = 50,
      regions = SAM3D_BODY_PROPORTION_REGIONS,
      shapeStrength = 50,
      shapeRegions = [],
      references = [],
    } = {},
    signal,
  ) {
    const normalizedJobId = sam3dJobId(jobId);
    const normalizedPersonIndex = Math.max(
      0,
      integerValue(personIndex) || 0,
    );
    const normalizedReferences = normalizeSam3dBodyReferences(
      references,
      normalizedJobId,
      normalizedPersonIndex,
    );
    const query = new URLSearchParams({
      person_index: String(normalizedPersonIndex),
      fit_strength: String(
        Math.max(0, Math.min(100, Number(strength) || 0)) / 100,
      ),
      shape_strength: String(
        Math.max(0, Math.min(100, Number(shapeStrength) || 0)) / 100,
      ),
      references: serializeSam3dBodyReferences(normalizedReferences),
    });
    if (targetUid) query.set("target_uid", targetUid);
    const selectedRegions = asArray(regions).filter((region) =>
      SAM3D_BODY_PROPORTION_REGIONS.includes(region),
    );
    if (selectedRegions.length) {
      query.set("regions", selectedRegions.join(","));
    }
    const selectedShapeRegions = asArray(shapeRegions).filter((region) =>
      SAM3D_BODY_SHAPE_REGIONS.includes(region),
    );
    // Keep the opt-in explicit even when no Shape region is selected. This
    // prevents a newer manager default from silently turning shape fitting on.
    query.set("shape_regions", selectedShapeRegions.join(","));
    return api(`${this.paths.bodyProportions(normalizedJobId)}?${query}`, {
      signal,
    });
  },

  bodyProportionsAction(jobId, action, request = {}) {
    const allowed = new Set(Object.values(SAM3D_BODY_PROPORTION_ACTIONS));
    if (!allowed.has(action)) {
      throw new Error("Unsupported body-proportion action");
    }
    return api(this.paths.bodyProportions(jobId), {
      method: "POST",
      body: { action, ...request },
    });
  },

  artifactUrl(jobId, kind) {
    return sam3dAuthenticatedUrl(this.paths.artifact(jobId, kind));
  },
});

function sam3dJobId(value) {
  const jobId = String(value || "").trim().toLowerCase();
  if (!SAM3D_JOB_ID_PATTERN.test(jobId)) {
    throw new Error("Invalid SAM 3D job identifier");
  }
  return jobId;
}

function sam3dAuthenticatedUrl(path) {
  const url = new URL(path, window.location.href);
  if (url.origin !== window.location.origin) return "";
  if (app.token) url.searchParams.set("token", app.token);
  return `${url.pathname}${url.search}`;
}

async function sam3dRawApi(path, file) {
  if (app.managerAuthFailed) {
    throw managerAuthBlockedError();
  }
  const requestToken = app.token;
  const requestAuthGeneration = app.managerAuthGeneration;
  if (!requestToken) {
    throw new Error(
      "This page has no write token. Reopen the URL printed by VAM-PIP (it contains #token=…).",
    );
  }
  const headers = new Headers({
    Accept: "application/json",
    "Content-Type": sam3dFileContentType(file),
    "X-VAMPIP-Token": requestToken,
  });
  const response = await fetch(path, {
    method: "POST",
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: file,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => ({}))
    : await response.text();
  if (!response.ok) {
    const detail =
      (payload &&
        typeof payload === "object" &&
        (payload.error || payload.message || payload.detail)) ||
      (typeof payload === "string" && payload) ||
      `${response.status} ${response.statusText}`;
    const error = new Error(String(detail));
    error.status = response.status;
    error.payload =
      payload && typeof payload === "object" ? payload : { detail };
    throw handleManagerAuthFailure(
      error,
      requestToken,
      requestAuthGeneration,
    );
  }
  return payload || {};
}

function sam3dCapabilitySet(status = app.sam3dStatus) {
  const values = [
    ...asArray(status?.capabilities),
    ...asArray(status?.worker?.capabilities),
    ...asArray(status?.vam?.capabilities),
    ...asArray(status?.bridge?.capabilities),
  ];
  return new Set(
    values
      .map((value) => String(value || "").trim().toLowerCase())
      .filter(Boolean),
  );
}

function normalizeSam3dModel(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const id = String(raw.id || raw.model_id || "")
    .trim()
    .toLowerCase();
  if (!/^[a-z0-9][a-z0-9_.+-]{0,63}$/.test(id)) return null;
  const errors = asArray(raw.errors)
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  return {
    id,
    name: String(raw.model || raw.name || id).trim() || id,
    backbone: String(raw.backbone || "").trim(),
    configured: raw.configured !== false && errors.length === 0,
    default: raw.default === true,
    errors,
  };
}

function sam3dWorkerModels(status = app.sam3dStatus) {
  const worker =
    status?.worker && typeof status.worker === "object" ? status.worker : {};
  const models = asArray(worker.models)
    .map(normalizeSam3dModel)
    .filter(Boolean);
  if (models.length) return models;

  const backbone = String(worker.backbone || "").trim().toLowerCase();
  const id = backbone.startsWith("dinov3_")
    ? SAM3D_DINOV3_MODEL_ID
    : backbone.startsWith("vit_hmr")
      ? SAM3D_VITH_MODEL_ID
      : "default";
  const legacyName = String(
    worker.model || status?.model || "SAM 3D Body",
  ).trim();
  if (!legacyName && !sam3dStatusReady(status, { ignoreModels: true })) {
    return [];
  }
  return [
    {
      id,
      name: legacyName || "SAM 3D Body",
      backbone,
      configured: sam3dStatusReady(status, { ignoreModels: true }),
      default: true,
      errors: asArray(worker.errors),
    },
  ];
}

function sam3dModelById(modelId, status = app.sam3dStatus) {
  return (
    sam3dWorkerModels(status).find((model) => model.id === modelId) || null
  );
}

function sam3dSelectedModelIds() {
  if (app.sam3dModelChoice === SAM3D_COMPARE_MODEL_ID) {
    return SAM3D_MODEL_ORDER.filter(
      (modelId) => sam3dModelById(modelId)?.configured,
    );
  }
  const selected = sam3dModelById(app.sam3dModelChoice);
  return selected?.configured ? [selected.id] : [];
}

function newSam3dComparisonId() {
  const bytes = new Uint8Array(16);
  if (!window.crypto?.getRandomValues) {
    throw new Error("This browser cannot create a secure comparison identifier.");
  }
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join(
    "",
  );
}

function sam3dStatusReady(
  status = app.sam3dStatus,
  { ignoreModels = false } = {},
) {
  if (!status || typeof status !== "object") return false;
  const worker =
    status.worker && typeof status.worker === "object" ? status.worker : {};
  if (!ignoreModels && Array.isArray(worker.models)) {
    return worker.models
      .map(normalizeSam3dModel)
      .filter(Boolean)
      .some((model) => model.configured);
  }
  if (status.ready !== undefined) return Boolean(status.ready);
  if (worker.ready !== undefined) return Boolean(worker.ready);
  if (status.available !== undefined) return Boolean(status.available);
  return false;
}

function sam3dRawJobs(payload) {
  if (Array.isArray(payload)) return payload;
  return asArray(
    payload?.jobs ||
      payload?.items ||
      payload?.results ||
      payload?.history,
  );
}

function sam3dJobState(job) {
  return String(job?.status || job?.state || "unknown")
    .trim()
    .toLowerCase();
}

function sam3dJobIsTerminal(job) {
  return SAM3D_TERMINAL_STATES.has(sam3dJobState(job));
}

function sam3dJobIsActive(job) {
  return ["queued", "running"].includes(sam3dJobState(job));
}

function sam3dVamActionState(job) {
  return String(job?.vamActionState || job?.action_state || "")
    .trim()
    .toLowerCase();
}

function sam3dJobNeedsPolling(job) {
  return (
    sam3dJobIsActive(job) ||
    ["queued", "running"].includes(sam3dVamActionState(job))
  );
}

function sam3dJobSucceeded(job) {
  return SAM3D_SUCCESS_STATES.has(sam3dJobState(job));
}

function sam3dJobFailed(job) {
  return SAM3D_ERROR_STATES.has(sam3dJobState(job));
}

function sam3dJobProgress(raw) {
  let progress = Number(
    raw?.progress_percent ??
      raw?.percent ??
      raw?.progress?.percent ??
      raw?.progress ??
      0,
  );
  if (!Number.isFinite(progress)) progress = 0;
  if (progress > 0 && progress <= 1) progress *= 100;
  return Math.max(0, Math.min(100, progress));
}

function normalizeSam3dCapture(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const requestId = String(raw.request_id || raw.requestId || "")
    .trim()
    .toLowerCase();
  if (!SAM3D_JOB_ID_PATTERN.test(requestId)) return null;
  const extension = String(raw.extension || "").trim().toLowerCase();
  const contentType = String(
    raw.content_type || raw.contentType || "",
  ).trim().toLowerCase();
  if (
    !(
      (extension === "jpg" && contentType === "image/jpeg") ||
      (extension === "png" && contentType === "image/png")
    )
  ) {
    return null;
  }
  return {
    ...raw,
    requestId,
    extension,
    contentType,
    capturedAt: String(
      raw.captured_at_utc || raw.capturedAt || "",
    ).trim(),
    artifactUrl: String(
      raw.artifact_url || raw.artifactUrl || raw.url || "",
    ).trim(),
  };
}

function normalizeSam3dBodyReferenceSupport(raw) {
  const seen = new Set();
  return asArray(raw)
    .map((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return null;
      }
      const personIndex = integerValue(
        item.person_index ?? item.personIndex,
      );
      if (
        personIndex === null ||
        personIndex < 0 ||
        seen.has(personIndex)
      ) {
        return null;
      }
      seen.add(personIndex);
      const space = String(item.space || "legacy")
        .trim()
        .toLowerCase()
        .slice(0, 48);
      return {
        personIndex,
        space: space || "legacy",
        multiReference:
          item.multi_reference === true ||
          item.multiReference === true,
      };
    })
    .filter(Boolean)
    .slice(0, 32);
}

function normalizeSam3dReference(raw, expectedJobId = "") {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const fallbackJobId = String(expectedJobId || "").trim().toLowerCase();
  const declaredJobId = String(
    raw.job_id || raw.jobId || fallbackJobId,
  ).trim().toLowerCase();
  if (
    !SAM3D_JOB_ID_PATTERN.test(declaredJobId) ||
    (
      SAM3D_JOB_ID_PATTERN.test(fallbackJobId) &&
      declaredJobId !== fallbackJobId
    )
  ) {
    return null;
  }
  const state = String(raw.state || raw.status || "")
    .trim()
    .toLowerCase()
    .slice(0, 32);
  const mode = String(
    raw.mode || raw.alignment_mode || raw.alignmentMode || "",
  )
    .trim()
    .toLowerCase();
  const visible = Boolean(
    raw.visible === true ||
      raw.active === true ||
      raw.shown === true ||
      ["active", "body-fit", "pose-aligned", "visible"].includes(state),
  );
  const width = Math.max(
    0,
    integerValue(raw.width ?? raw.source_width ?? raw.sourceWidth) || 0,
  );
  const height = Math.max(
    0,
    integerValue(raw.height ?? raw.source_height ?? raw.sourceHeight) || 0,
  );
  const sha256 = String(raw.sha256 || raw.digest || "").trim().toLowerCase();
  return {
    visible,
    jobId: declaredJobId,
    targetUid: String(raw.target_uid || raw.targetUid || "").trim(),
    cameraUid: String(raw.camera_uid || raw.cameraUid || "").trim(),
    atomUid: String(raw.atom_uid || raw.atomUid || "").trim(),
    mode: ["body-fit", "pose-aligned"].includes(mode) ? mode : "",
    state,
    message: String(raw.message || raw.detail || "").trim().slice(0, 500),
    resourceRef: String(
      raw.resource_ref || raw.resourceRef || "",
    ).trim(),
    sha256: /^[0-9a-f]{64}$/.test(sha256) ? sha256 : "",
    width,
    height,
  };
}

function normalizeSam3dJob(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  let id;
  try {
    id = sam3dJobId(raw.id || raw.job_id || raw.jobId);
  } catch (_error) {
    return null;
  }
  const result =
    raw.result && typeof raw.result === "object" ? raw.result : {};
  const source =
    raw.source && typeof raw.source === "object" ? raw.source : {};
  const camera =
    (result.camera && typeof result.camera === "object" && result.camera) ||
    (raw.camera && typeof raw.camera === "object" && raw.camera) ||
    {};
  const rawModel =
    raw.model && typeof raw.model === "object" && !Array.isArray(raw.model)
      ? raw.model
      : {};
  const modelId = String(
    rawModel.id || raw.model_id || result.model_id || "",
  )
    .trim()
    .toLowerCase();
  const modelName = String(
    rawModel.name ||
      rawModel.model ||
      raw.model_name ||
      result.model_name ||
      (modelId === SAM3D_DINOV3_MODEL_ID
        ? "SAM 3D Body DINOv3-H+"
        : modelId === SAM3D_VITH_MODEL_ID
          ? "SAM 3D Body ViT-H"
          : "Model not recorded"),
  ).trim();
  const comparisonId = String(
    raw.comparison_id || raw.comparisonId || result.comparison_id || "",
  )
    .trim()
    .toLowerCase();
  let bodies = asArray(
    result.bodies ||
      raw.bodies ||
      result.people ||
      raw.people,
  ).filter((body) => body && typeof body === "object");
  if (!bodies.length) {
    const personCount = Math.max(
      0,
      Math.min(
        32,
        integerValue(raw.person_count ?? result.person_count) || 0,
      ),
    );
    bodies = Array.from({ length: personCount }, () => ({}));
  }
  const selectedBodyIndex = Math.max(
    0,
    integerValue(
      raw.selected_body_index ??
        raw.selected_person_index ??
        raw.body_index ??
        result.selected_body_index ??
        0,
    ) || 0,
  );
  const bodyReferenceSupport = normalizeSam3dBodyReferenceSupport(
    raw.body_reference_support ||
      raw.bodyReferenceSupport ||
      result.body_reference_support ||
      result.bodyReferenceSupport,
  );
  const revision = String(
    raw.revision ||
      result.revision ||
      raw.result_revision ||
      "",
  ).trim().toLowerCase();
  const width = Math.max(
    0,
    integerValue(
      source.width ??
        raw.source_width ??
        result.source_width ??
        raw.width,
    ) || 0,
  );
  const height = Math.max(
    0,
    integerValue(
      source.height ??
        raw.source_height ??
        result.source_height ??
        raw.height,
    ) || 0,
  );
  const lastAction =
    raw.last_vam_action &&
    typeof raw.last_vam_action === "object" &&
    !Array.isArray(raw.last_vam_action)
      ? raw.last_vam_action
      : {};
  const actionName = String(lastAction.action || "").toLowerCase();
  const solutionRevision = String(
    raw.solution_revision || lastAction.revision || "",
  )
    .trim()
    .toLowerCase();
  const actionState = String(
    raw.action_state || lastAction.state || "",
  ).trim().toLowerCase();
  const actionMessage = String(
    raw.action_message || lastAction.message || "",
  ).trim();
  const artifactUrls =
    raw.artifact_urls &&
    typeof raw.artifact_urls === "object" &&
    !Array.isArray(raw.artifact_urls)
      ? raw.artifact_urls
      : {};
  const captureIds = new Set();
  const captures = asArray(raw.captures || result.captures)
    .map(normalizeSam3dCapture)
    .filter((capture) => {
      if (!capture || captureIds.has(capture.requestId)) return false;
      captureIds.add(capture.requestId);
      return true;
    })
    .slice(0, SAM3D_MAX_CAPTURES);
  const reference = normalizeSam3dReference(
    raw.reference ||
      raw.sam3d_reference ||
      raw.sam3dReference ||
      result.reference ||
      result.sam3d_reference ||
      result.sam3dReference,
    id,
  );
  return {
    ...raw,
    id,
    status: sam3dJobState(raw),
    progressPercent: sam3dJobProgress(raw),
    stage: String(
      raw.stage ||
        raw.progress?.stage ||
        (sam3dJobSucceeded(raw) ? "Reconstruction ready" : raw.status || "Queued"),
    ),
    message: String(
      raw.message ||
        raw.progress?.message ||
        raw.error?.message ||
        raw.error ||
        "",
    ),
    revision,
    bodies,
    bodyReferenceSupport,
    selectedBodyIndex,
    model: {
      id: /^[a-z0-9][a-z0-9_.+-]{0,63}$/.test(modelId) ? modelId : "",
      name: modelName || "Model not recorded",
      backbone: String(
        rawModel.backbone || raw.model_backbone || result.model_backbone || "",
      ).trim(),
    },
    comparisonId: SAM3D_JOB_ID_PATTERN.test(comparisonId)
      ? comparisonId
      : "",
    sourceName: String(
      source.name ||
        source.filename ||
        raw.source_name ||
        raw.filename ||
        "Source image",
    ),
    sourceWidth: width,
    sourceHeight: height,
    createdAt:
      raw.created_at_utc ||
      raw.created_at ||
      raw.createdAt ||
      raw.started_at ||
      raw.updated_at ||
      "",
    updatedAt:
      raw.updated_at_utc ||
      raw.updated_at ||
      raw.updatedAt ||
      "",
    camera: {
      horizontalFov: numberOr(
        camera.horizontal_fov ??
          camera.horizontalFov ??
          camera.fov ??
          result.horizontal_fov,
        60,
      ),
    },
    solutionRevision: SAM3D_JOB_ID_PATTERN.test(solutionRevision)
      ? solutionRevision
      : "",
    targetUid: String(raw.target_uid || lastAction.target_uid || ""),
    cameraUid: String(raw.camera_uid || lastAction.camera_uid || ""),
    lastActionName: actionName,
    vamActionState: actionState,
    vamActionMessage: actionMessage,
    captureRequested:
      raw.capture_requested === true || actionName === "capture",
    captureRequestId: String(
      lastAction.request_id || lastAction.requestId || "",
    ).trim(),
    canUndo: Boolean(
      raw.can_undo ?? raw.canUndo ?? result.can_undo ?? false,
    ),
    applied: Boolean(raw.applied ?? result.applied ?? false),
    // The capture artifact URL is minted when the bridge request is queued,
    // before the renderer has produced a readable image. Only an explicit
    // ready flag or a successful browser image load counts as captured.
    captured:
      raw.captured === true ||
      result.captured === true ||
      captures.length > 0 ||
      app.sam3dCaptureReadyJobs.has(id),
    captures,
    reference,
    artifactUrls,
    rawResult: result,
  };
}

function normalizeSam3dJobs(payload) {
  const seen = new Set();
  return sam3dRawJobs(payload)
    .map(normalizeSam3dJob)
    .filter((job) => {
      if (!job || seen.has(job.id)) return false;
      seen.add(job.id);
      return true;
    })
    .slice(0, SAM3D_MAX_HISTORY);
}

function mergeSam3dJob(job) {
  if (!job) return;
  const existingIndex = app.sam3dJobs.findIndex(
    (candidate) => candidate.id === job.id,
  );
  if (existingIndex >= 0) {
    app.sam3dJobs.splice(existingIndex, 1, job);
  } else {
    app.sam3dJobs.unshift(job);
    if (app.sam3dJobs.length > SAM3D_MAX_HISTORY) {
      app.sam3dJobs.length = SAM3D_MAX_HISTORY;
    }
  }
  if (app.sam3dSelectedJobId === job.id) {
    app.sam3dSelectedJob = job;
    const selectedCaptureStillExists = job.captures.some(
      (capture) =>
        capture.requestId === app.sam3dSelectedCaptureRequestId,
    );
    const selectedCaptureIsPending =
      job.captureRequestId &&
      job.captureRequestId === app.sam3dSelectedCaptureRequestId;
    if (!selectedCaptureStillExists && !selectedCaptureIsPending) {
      app.sam3dSelectedCaptureRequestId =
        job.captures[0]?.requestId || "";
    }
    app.sam3dSelectedBodyIndex = Math.min(
      job.selectedBodyIndex,
      Math.max(0, job.bodies.length - 1),
    );
    if (job.applied && job.solutionRevision) {
      app.sam3dAppliedJobId = job.id;
      app.sam3dAppliedRevision = job.solutionRevision;
    } else if (app.sam3dAppliedJobId === job.id && !job.applied) {
      app.sam3dAppliedJobId = "";
      app.sam3dAppliedRevision = "";
    }
  }
}

async function loadSam3dWorkspace({ force = false, quiet = false } = {}) {
  if (app.sam3dStatusInFlight || app.sam3dJobsInFlight) {
    return;
  }
  app.sam3dStatusInFlight = true;
  app.sam3dJobsInFlight = true;
  setButtonBusy(elements.sam3dRefreshButton, true);
  renderSam3dRuntime();
  const sceneGeneration = beginPersonSnapshotRequest();
  const [statusResult, jobsResult, sceneResult] = await Promise.allSettled([
    Sam3dClient.status(),
    Sam3dClient.listJobs(),
    fetchLiveSceneSnapshot(),
  ]);
  if (statusResult.status === "fulfilled") {
    app.sam3dStatus = statusResult.value || {};
    app.sam3dStatusError = null;
  } else {
    app.sam3dStatus = null;
    app.sam3dStatusError = statusResult.reason;
  }
  if (jobsResult.status === "fulfilled") {
    app.sam3dJobs = normalizeSam3dJobs(jobsResult.value);
    app.sam3dJobsError = null;
  } else {
    app.sam3dJobsError = jobsResult.reason;
  }
  if (sceneResult.status === "fulfilled") {
    acceptPersonSnapshot(sceneResult.value || {}, sceneGeneration);
  } else {
    acceptPersonSnapshotError(sceneResult.reason, sceneGeneration);
  }
  app.sam3dStatusInFlight = false;
  app.sam3dJobsInFlight = false;
  setButtonBusy(elements.sam3dRefreshButton, false);

  if (
    app.sam3dSelectedJobId &&
    !app.sam3dJobs.some((job) => job.id === app.sam3dSelectedJobId)
  ) {
    app.sam3dSelectedJobId = "";
    app.sam3dSelectedJob = null;
    app.sam3dSelectedCaptureRequestId = "";
  }
  if (!app.sam3dSelectedJobId && app.sam3dJobs.length) {
    app.sam3dSelectedJobId = app.sam3dJobs[0].id;
    app.sam3dSelectedJob = app.sam3dJobs[0];
  } else if (app.sam3dSelectedJobId) {
    app.sam3dSelectedJob =
      app.sam3dJobs.find(
        (job) => job.id === app.sam3dSelectedJobId,
      ) || app.sam3dSelectedJob;
  }

  initializeSam3dBodyReferences();
  renderSam3dWorkspace();
  if (app.sam3dSelectedJobId) {
    await loadSam3dJob(app.sam3dSelectedJobId, {
      quiet: true,
    });
  }
  const morphJob = sam3dBodyProportionJob();
  if (morphJob) {
    await loadSam3dBodyProportions(morphJob.id, {
      quiet: true,
    });
  }
  if (app.sam3dJobs.some(sam3dJobNeedsPolling)) {
    startSam3dPolling();
  } else {
    stopSam3dPolling();
  }
  if (
    !quiet &&
    app.sam3dStatusError &&
    app.sam3dStatusError.status !== 404 &&
    !isManagerAuthFailure(app.sam3dStatusError)
  ) {
    toast(
      "SAM 3D worker unavailable",
      errorMessage(app.sam3dStatusError),
      "error",
    );
  }
}

async function loadSam3dJob(jobId, { quiet = false } = {}) {
  let normalizedId;
  try {
    normalizedId = sam3dJobId(jobId);
  } catch (error) {
    if (!quiet) toast("Could not load job", errorMessage(error), "error");
    return null;
  }
  const generation = ++app.sam3dJobRequestGeneration;
  try {
    const payload = await Sam3dClient.job(normalizedId);
    if (
      generation !== app.sam3dJobRequestGeneration ||
      app.sam3dSelectedJobId !== normalizedId
    ) {
      return null;
    }
    const job = normalizeSam3dJob(payload.job || payload);
    if (!job) throw new Error("The manager returned an invalid SAM 3D job.");
    mergeSam3dJob(job);
    renderSam3dWorkspace();
    if (sam3dJobNeedsPolling(job)) startSam3dPolling();
    return job;
  } catch (error) {
    if (!quiet) {
      toast("Could not load SAM 3D job", errorMessage(error), "error");
    }
    return null;
  }
}

async function refreshSam3dComparisonJobs(comparisonId) {
  if (!SAM3D_JOB_ID_PATTERN.test(String(comparisonId || ""))) return;
  const siblingIds = app.sam3dJobs
    .filter(
      (job) =>
        job.comparisonId === comparisonId &&
        job.id !== app.sam3dSelectedJobId,
    )
    .map((job) => job.id);
  if (!siblingIds.length) return;
  const results = await Promise.allSettled(
    siblingIds.map((jobId) => Sam3dClient.job(jobId)),
  );
  for (const result of results) {
    if (result.status !== "fulfilled") continue;
    const job = normalizeSam3dJob(result.value.job || result.value);
    if (job) mergeSam3dJob(job);
  }
  renderSam3dWorkspace();
}

function startSam3dPolling() {
  if (
    app.managerAuthFailed ||
    app.sam3dJobPollTimer !== null ||
    app.view !== "sam3d"
  ) {
    return;
  }
  app.sam3dJobPollTimer = window.setTimeout(pollSam3dJob, SAM3D_POLL_MS);
}

function stopSam3dPolling() {
  if (app.sam3dJobPollTimer !== null) {
    window.clearTimeout(app.sam3dJobPollTimer);
    app.sam3dJobPollTimer = null;
  }
}

async function pollSam3dJob() {
  app.sam3dJobPollTimer = null;
  if (app.managerAuthFailed || app.view !== "sam3d") return;
  const jobId = app.sam3dSelectedJobId;
  if (!jobId) return;
  const previousActionState = sam3dVamActionState(
    app.sam3dSelectedJob,
  );
  const job = await loadSam3dJob(jobId, { quiet: true });
  await refreshSam3dComparisonJobs(job?.comparisonId || "");
  const actionState = sam3dVamActionState(job);
  if (
    ["queued", "running"].includes(previousActionState) &&
    ["succeeded", "failed", "stale"].includes(actionState)
  ) {
    await loadPersons({ quiet: true });
    if (
      job &&
      sam3dJobSucceeded(job) &&
      !app.sam3dBodyProportionsPendingAction
    ) {
      const morphJob = sam3dBodyProportionJob();
      if (morphJob) {
        await loadSam3dBodyProportions(morphJob.id, { quiet: true });
      }
    }
    if (actionState === "succeeded") {
      toast(
        "VaM action completed",
        job?.vamActionMessage || "VaM confirmed the requested SAM 3D change.",
      );
    } else {
      toast(
        actionState === "stale"
          ? "VaM action was not confirmed"
          : "VaM action failed",
        job?.vamActionMessage ||
          "The bridge did not complete the requested SAM 3D change.",
        "error",
      );
    }
  }
  const monitoredJobs = job?.comparisonId
    ? app.sam3dJobs.filter(
        (candidate) => candidate.comparisonId === job.comparisonId,
      )
    : [job].filter(Boolean);
  if (monitoredJobs.some(sam3dJobNeedsPolling)) {
    app.sam3dJobPollTimer = window.setTimeout(
      pollSam3dJob,
      SAM3D_POLL_MS,
    );
  }
}

function renderSam3dWorkspace() {
  renderSam3dRuntime();
  renderSam3dSource();
  renderSam3dHistory();
  renderSam3dJob();
  renderSam3dBodyProfiles();
  renderSam3dResolutionOptions();
  renderSam3dTargets();
  renderSam3dReferenceState();
  renderSam3dBodyProportions();
  renderSam3dApplyState();
  renderSam3dHandoff();
}

function sam3dModelDisplayName(value) {
  const model =
    value?.model && typeof value.model === "object" ? value.model : value;
  const name = String(model?.name || model?.model || "Model not recorded").trim();
  return name.replace(/^SAM 3D Body\s+/i, "") || "Model not recorded";
}

function renderSam3dModelOptions(models) {
  const byId = new Map(models.map((model) => [model.id, model]));
  for (const option of Array.from(elements.sam3dModelSelect.options)) {
    if (option.dataset.sam3dDynamicModel === "true") option.remove();
  }
  for (const modelId of SAM3D_MODEL_ORDER) {
    const option = Array.from(elements.sam3dModelSelect.options).find(
      (candidate) => candidate.value === modelId,
    );
    if (!option) continue;
    const model = byId.get(modelId);
    const fallbackName =
      modelId === SAM3D_DINOV3_MODEL_ID ? "DINOv3-H+" : "ViT-H";
    const name = model ? sam3dModelDisplayName(model) : fallbackName;
    option.disabled = !model?.configured;
    option.textContent =
      `${name}${modelId === SAM3D_DINOV3_MODEL_ID ? " · recommended" : ""}` +
      `${model?.configured ? "" : " · unavailable"}`;
  }

  const comparisonOption = Array.from(
    elements.sam3dModelSelect.options,
  ).find((candidate) => candidate.value === SAM3D_COMPARE_MODEL_ID);
  for (const model of byId.values()) {
    if (SAM3D_MODEL_ORDER.includes(model.id)) continue;
    const option = new Option(
      `${sam3dModelDisplayName(model)}` +
        `${model.default ? " · default" : ""}` +
        `${model.configured ? "" : " · unavailable"}`,
      model.id,
    );
    option.disabled = !model.configured;
    option.dataset.sam3dDynamicModel = "true";
    elements.sam3dModelSelect.insertBefore(
      option,
      comparisonOption || null,
    );
  }
  const comparisonReady = SAM3D_MODEL_ORDER.every(
    (modelId) => byId.get(modelId)?.configured,
  );
  if (comparisonOption) {
    comparisonOption.disabled = !comparisonReady;
    comparisonOption.textContent = comparisonReady
      ? "Compare both · DINOv3-H+ + ViT-H"
      : "Compare both · requires both models";
  }

  const selectedOption = Array.from(
    elements.sam3dModelSelect.options,
  ).find((candidate) => candidate.value === app.sam3dModelChoice);
  if (!selectedOption || selectedOption.disabled) {
    const fallback =
      models.find((model) => model.default && model.configured) ||
      models.find((model) => model.configured);
    app.sam3dModelChoice = fallback?.id || "";
  }
  elements.sam3dModelSelect.value = app.sam3dModelChoice;
  elements.sam3dModelSelect.disabled =
    app.sam3dMutationInFlight || !models.some((model) => model.configured);

  if (app.sam3dModelChoice === SAM3D_COMPARE_MODEL_ID) {
    elements.sam3dModelNote.textContent =
      "Runs DINOv3-H+ and ViT-H from the same source, box, and FOV. Jobs are queued one at a time and grouped for comparison.";
  } else {
    const selected = byId.get(app.sam3dModelChoice);
    const backbone = selected?.backbone ? ` · ${selected.backbone}` : "";
    elements.sam3dModelNote.textContent = selected
      ? `${sam3dModelDisplayName(selected)} selected${backbone}. The job keeps this model identity in history.`
      : "No configured SAM 3D model is available.";
  }
  if (!app.sam3dMutationInFlight) {
    elements.sam3dRunButton.textContent =
      app.sam3dModelChoice === SAM3D_COMPARE_MODEL_ID
        ? "Run both models"
        : "Run SAM 3D Body";
  }
}

function renderSam3dRuntime() {
  const status = app.sam3dStatus;
  const error = app.sam3dStatusError;
  const checking = app.sam3dStatusInFlight;
  const ready = sam3dStatusReady(status);
  const worker =
    status?.worker && typeof status.worker === "object"
      ? status.worker
      : {};
  const models = sam3dWorkerModels(status);
  renderSam3dModelOptions(models);

  elements.sam3dRuntimeBadge.classList.toggle("is-ready", ready);
  elements.sam3dRuntimeBadge.classList.toggle("is-error", Boolean(error));
  elements.sam3dRuntimePanel.classList.toggle("is-ready", ready);
  elements.sam3dRuntimePanel.classList.toggle("is-error", Boolean(error));
  elements.sam3dRuntimeAction.hidden = !error;

  if (checking) {
    elements.sam3dRuntimeLabel.textContent = "Checking…";
    elements.sam3dRuntimeTitle.textContent = "Checking the standalone worker";
    elements.sam3dRuntimeMessage.textContent =
      "Reading model, GPU, VaM bridge, and camera-plugin capabilities.";
    elements.sam3dTabState.textContent = "…";
  } else if (error) {
    const missing = error.status === 404;
    elements.sam3dRuntimeLabel.textContent = missing
      ? "Not installed"
      : "Unavailable";
    elements.sam3dRuntimeTitle.textContent = missing
      ? "SAM 3D support is not installed in this manager build"
      : "The standalone SAM 3D worker is unavailable";
    elements.sam3dRuntimeMessage.textContent = missing
      ? "The rest of VAM-PIP remains usable. Update the manager to enable this workspace."
      : errorMessage(error);
    elements.sam3dTabState.textContent = "Offline";
  } else if (ready) {
    const model = String(worker.model || status?.model || "SAM 3D Body");
    const configuredModels = models.filter(
      (candidate) => candidate.configured,
    );
    const runtime = worker.environment
      ? `Conda environment ${worker.environment}`
      : worker.launcher === "dedicated-python"
        ? "dedicated Python environment"
        : "isolated worker environment";
    elements.sam3dRuntimeLabel.textContent = "Worker ready";
    elements.sam3dRuntimeTitle.textContent = configuredModels.length > 1
      ? `${configuredModels.length} SAM 3D models are ready`
      : `${model} worker is ready`;
    elements.sam3dRuntimeMessage.textContent =
      configuredModels.length > 1
        ? `${configuredModels
            .map(sam3dModelDisplayName)
            .join(" and ")} use the same ${runtime}. Inference runs serially and unloads before VaM capture.`
        : `Using ${runtime}. Inference unloads before VaM capture.`;
    elements.sam3dTabState.textContent =
      configuredModels.length > 1
        ? "2 models"
        : "Ready";
  } else if (status) {
    elements.sam3dRuntimeLabel.textContent = "Setup required";
    elements.sam3dRuntimeTitle.textContent = String(
      status.title ||
        worker.title ||
        "The standalone worker needs setup",
    );
    elements.sam3dRuntimeMessage.textContent = String(
      status.message ||
        worker.message ||
        status.reason ||
        asArray(worker.errors).join(" · ") ||
        "Install or select the official SAM 3D Body checkpoint before running a job.",
    );
    elements.sam3dTabState.textContent = "Setup";
  } else {
    elements.sam3dRuntimeLabel.textContent = "Not checked";
    elements.sam3dRuntimeTitle.textContent =
      "Open or refresh this tab to check the worker";
    elements.sam3dRuntimeMessage.textContent =
      "ComfyUI is not used or modified by this workspace.";
    elements.sam3dTabState.textContent = "—";
  }
  const selectedModelIds = sam3dSelectedModelIds();
  const modelChoiceReady =
    app.sam3dModelChoice === SAM3D_COMPARE_MODEL_ID
      ? selectedModelIds.length === SAM3D_MODEL_ORDER.length
      : selectedModelIds.length === 1;
  elements.sam3dRunButton.disabled =
    !ready ||
    !modelChoiceReady ||
    !app.sam3dSourceFile ||
    app.sam3dMutationInFlight;
}

function sam3dHistoryStateClass(job) {
  if (sam3dJobFailed(job)) return "is-error";
  if (sam3dJobSucceeded(job)) return "is-complete";
  if (!sam3dJobIsTerminal(job)) return "is-running";
  return "";
}

function sam3dJobDisplayDate(job) {
  const value = job.updatedAt || job.createdAt;
  const model = sam3dModelDisplayName(job);
  if (!value) return `${model} · ${sam3dJobState(job)}`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return `${model} · ${sam3dJobState(job)}`;
  }
  return `${model} · ${sam3dJobState(job)} · ${date.toLocaleString()}`;
}

function renderSam3dHistory() {
  elements.sam3dHistoryCount.textContent = formatNumber(
    app.sam3dJobs.length,
  );
  elements.sam3dHistoryList.replaceChildren();
  if (!app.sam3dJobs.length) {
    const empty = createElement("div", "inline-empty");
    const message = document.createElement("p");
    message.textContent = app.sam3dJobsError
      ? "Job history is currently unavailable."
      : "No reconstruction jobs yet.";
    empty.append(message);
    elements.sam3dHistoryList.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const job of app.sam3dJobs) {
    const item = button("", "sam3d-history-item");
    item.dataset.sam3dJobId = job.id;
    item.classList.toggle(
      "active",
      job.id === app.sam3dSelectedJobId,
    );
    const thumb = createElement("span", "sam3d-history-thumb");
    thumb.textContent = "3D";
    const sourceUrl = sam3dArtifactUrl(job, "source");
    if (sourceUrl) {
      const image = document.createElement("img");
      image.alt = "";
      image.loading = "lazy";
      image.addEventListener("error", () => image.remove());
      image.src = sourceUrl;
      thumb.append(image);
    }
    const copy = createElement("span", "sam3d-history-copy");
    const title = document.createElement("strong");
    title.textContent = job.sourceName;
    const detail = document.createElement("span");
    detail.textContent = sam3dJobDisplayDate(job);
    copy.append(title, detail);
    const state = createElement(
      "span",
      `sam3d-history-state ${sam3dHistoryStateClass(job)}`.trim(),
    );
    state.setAttribute("aria-label", sam3dJobState(job));
    item.append(thumb, copy, state);
    fragment.append(item);
  }
  elements.sam3dHistoryList.append(fragment);
}

async function selectSam3dJob(jobId) {
  let normalizedId;
  try {
    normalizedId = sam3dJobId(jobId);
  } catch (_error) {
    return;
  }
  if (app.sam3dSelectedJobId === normalizedId) return;
  app.sam3dSelectedJobId = normalizedId;
  app.sam3dSelectedJob =
    app.sam3dJobs.find((job) => job.id === normalizedId) || null;
  app.sam3dSelectedCaptureRequestId =
    app.sam3dSelectedJob?.captures[0]?.requestId || "";
  app.sam3dSelectedBodyIndex =
    app.sam3dSelectedJob?.selectedBodyIndex || 0;
  app.sam3dAppliedJobId = app.sam3dSelectedJob?.applied
    ? normalizedId
    : "";
  app.sam3dAppliedRevision =
    app.sam3dSelectedJob?.applied
      ? app.sam3dSelectedJob.solutionRevision
      : "";
  app.sam3dPreviewKind = sam3dJobSucceeded(app.sam3dSelectedJob)
    ? "overlay"
    : "source";
  renderSam3dWorkspace();
  const job = await loadSam3dJob(normalizedId);
  if (sam3dJobSucceeded(job)) renderSam3dBodyReferenceGallery();
}

function sam3dFileContentType(file) {
  const type = String(file?.type || "").toLowerCase();
  if (["image/jpeg", "image/png", "image/webp"].includes(type)) return type;
  const name = String(file?.name || "");
  if (/\.jpe?g$/i.test(name)) return "image/jpeg";
  if (/\.png$/i.test(name)) return "image/png";
  if (/\.webp$/i.test(name)) return "image/webp";
  return "";
}

function sam3dFileTypeAllowed(file) {
  return Boolean(sam3dFileContentType(file));
}

async function chooseSam3dSource(file) {
  if (!(file instanceof File)) return;
  if (!sam3dFileTypeAllowed(file)) {
    toast(
      "Unsupported source image",
      "Choose a JPEG, PNG, or WebP image.",
      "error",
    );
    elements.sam3dFileInput.value = "";
    return;
  }
  if (file.size <= 0 || file.size > SAM3D_MAX_UPLOAD_BYTES) {
    toast(
      "Source image is too large",
      `Choose an image smaller than ${formatBytes(SAM3D_MAX_UPLOAD_BYTES)}.`,
      "error",
    );
    elements.sam3dFileInput.value = "";
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  const image = new Image();
  try {
    await new Promise((resolve, reject) => {
      image.addEventListener("load", resolve, { once: true });
      image.addEventListener(
        "error",
        () => reject(new Error("The browser could not decode this image.")),
        { once: true },
      );
      image.src = objectUrl;
    });
  } catch (error) {
    URL.revokeObjectURL(objectUrl);
    elements.sam3dFileInput.value = "";
    toast("Could not read source image", errorMessage(error), "error");
    return;
  }

  if (app.sam3dSourceUrl) URL.revokeObjectURL(app.sam3dSourceUrl);
  app.sam3dSourceFile = file;
  app.sam3dSourceUrl = objectUrl;
  app.sam3dSourceImage = image;
  app.sam3dSourceWidth = image.naturalWidth;
  app.sam3dSourceHeight = image.naturalHeight;
  app.sam3dSourceJobId = "";
  app.sam3dBbox = { x: 0, y: 0, width: 100, height: 100 };
  elements.sam3dManualBbox.checked = false;
  elements.sam3dBboxFields.disabled = true;
  syncSam3dBboxFields();
  renderSam3dSource();
  renderSam3dRuntime();
  drawSam3dSourceCanvas();
}

function clearSam3dSource() {
  if (app.sam3dSourceUrl) URL.revokeObjectURL(app.sam3dSourceUrl);
  app.sam3dSourceFile = null;
  app.sam3dSourceUrl = "";
  app.sam3dSourceImage = null;
  app.sam3dSourceWidth = 0;
  app.sam3dSourceHeight = 0;
  app.sam3dSourceJobId = "";
  app.sam3dBbox = { x: 0, y: 0, width: 100, height: 100 };
  app.sam3dBboxDrag = null;
  elements.sam3dFileInput.value = "";
  elements.sam3dManualBbox.checked = false;
  elements.sam3dBboxFields.disabled = true;
  syncSam3dBboxFields();
  renderSam3dSource();
  renderSam3dRuntime();
  renderSam3dPreview();
}

function renderSam3dSource() {
  const hasSource = Boolean(
    app.sam3dSourceFile && app.sam3dSourceImage,
  );
  elements.sam3dDropZone.hidden = hasSource;
  elements.sam3dSourceEditor.hidden = !hasSource;
  elements.sam3dClearSource.hidden = !hasSource;
  elements.sam3dCanvasHint.hidden =
    !hasSource || !elements.sam3dManualBbox.checked;
  if (!hasSource) return;
  elements.sam3dSourceName.textContent = app.sam3dSourceFile.name;
  elements.sam3dSourceMeta.textContent =
    `${formatNumber(app.sam3dSourceWidth)} × ${formatNumber(
      app.sam3dSourceHeight,
    )} · ${formatBytes(app.sam3dSourceFile.size)}`;
  window.requestAnimationFrame(drawSam3dSourceCanvas);
}

function clampSam3dBbox(bbox) {
  const x = Math.max(0, Math.min(99.9, numberOr(bbox.x, 0)));
  const y = Math.max(0, Math.min(99.9, numberOr(bbox.y, 0)));
  const width = Math.max(
    0.1,
    Math.min(100 - x, numberOr(bbox.width, 100 - x)),
  );
  const height = Math.max(
    0.1,
    Math.min(100 - y, numberOr(bbox.height, 100 - y)),
  );
  return { x, y, width, height };
}

function syncSam3dBboxFields() {
  const bbox = clampSam3dBbox(app.sam3dBbox);
  app.sam3dBbox = bbox;
  elements.sam3dBboxX.value = bbox.x.toFixed(1);
  elements.sam3dBboxY.value = bbox.y.toFixed(1);
  elements.sam3dBboxWidth.value = bbox.width.toFixed(1);
  elements.sam3dBboxHeight.value = bbox.height.toFixed(1);
}

function readSam3dBboxFields() {
  app.sam3dBbox = clampSam3dBbox({
    x: elements.sam3dBboxX.value,
    y: elements.sam3dBboxY.value,
    width: elements.sam3dBboxWidth.value,
    height: elements.sam3dBboxHeight.value,
  });
  drawSam3dSourceCanvas();
}

function resetSam3dBbox() {
  app.sam3dBbox = { x: 0, y: 0, width: 100, height: 100 };
  syncSam3dBboxFields();
  drawSam3dSourceCanvas();
}

function sam3dCanvasPoint(event) {
  const canvas = elements.sam3dSourceCanvas;
  const bounds = canvas.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return null;
  return {
    x: Math.max(
      0,
      Math.min(
        100,
        ((event.clientX - bounds.left) / bounds.width) * 100,
      ),
    ),
    y: Math.max(
      0,
      Math.min(
        100,
        ((event.clientY - bounds.top) / bounds.height) * 100,
      ),
    ),
  };
}

function beginSam3dBboxDrag(event) {
  if (
    !elements.sam3dManualBbox.checked ||
    !app.sam3dSourceImage ||
    event.button !== 0
  ) {
    return;
  }
  const point = sam3dCanvasPoint(event);
  if (!point) return;
  event.preventDefault();
  elements.sam3dSourceCanvas.setPointerCapture(event.pointerId);
  app.sam3dBboxDrag = { pointerId: event.pointerId, start: point };
  app.sam3dBbox = {
    x: point.x,
    y: point.y,
    width: 0.1,
    height: 0.1,
  };
  syncSam3dBboxFields();
  drawSam3dSourceCanvas();
}

function continueSam3dBboxDrag(event) {
  const drag = app.sam3dBboxDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const point = sam3dCanvasPoint(event);
  if (!point) return;
  const left = Math.min(drag.start.x, point.x);
  const top = Math.min(drag.start.y, point.y);
  app.sam3dBbox = clampSam3dBbox({
    x: left,
    y: top,
    width: Math.abs(point.x - drag.start.x),
    height: Math.abs(point.y - drag.start.y),
  });
  syncSam3dBboxFields();
  drawSam3dSourceCanvas();
}

function finishSam3dBboxDrag(event) {
  const drag = app.sam3dBboxDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  continueSam3dBboxDrag(event);
  app.sam3dBboxDrag = null;
  if (elements.sam3dSourceCanvas.hasPointerCapture(event.pointerId)) {
    elements.sam3dSourceCanvas.releasePointerCapture(event.pointerId);
  }
}

function drawSam3dSourceCanvas() {
  const canvas = elements.sam3dSourceCanvas;
  const context = canvas?.getContext("2d");
  const image = app.sam3dSourceImage;
  if (!context || !image) return;
  const scale = Math.min(
    1,
    1600 / Math.max(image.naturalWidth, image.naturalHeight),
  );
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  canvas.style.aspectRatio = `${width} / ${height}`;
  context.clearRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);
  if (!elements.sam3dManualBbox.checked) return;

  const bbox = clampSam3dBbox(app.sam3dBbox);
  const x = (bbox.x / 100) * width;
  const y = (bbox.y / 100) * height;
  const boxWidth = (bbox.width / 100) * width;
  const boxHeight = (bbox.height / 100) * height;
  context.save();
  context.fillStyle = "rgba(5, 8, 12, 0.48)";
  context.beginPath();
  context.rect(0, 0, width, height);
  context.rect(x, y, boxWidth, boxHeight);
  context.fill("evenodd");
  context.strokeStyle = "#86e6b0";
  context.lineWidth = Math.max(2, Math.min(width, height) / 300);
  context.setLineDash([
    Math.max(5, width / 150),
    Math.max(4, width / 220),
  ]);
  context.strokeRect(x, y, boxWidth, boxHeight);
  context.setLineDash([]);
  context.fillStyle = "#86e6b0";
  const handle = Math.max(6, Math.min(width, height) / 90);
  for (const [handleX, handleY] of [
    [x, y],
    [x + boxWidth, y],
    [x, y + boxHeight],
    [x + boxWidth, y + boxHeight],
  ]) {
    context.fillRect(
      handleX - handle / 2,
      handleY - handle / 2,
      handle,
      handle,
    );
  }
  context.restore();
}

function sam3dBboxPixels() {
  if (!elements.sam3dManualBbox.checked) return null;
  const bbox = clampSam3dBbox(app.sam3dBbox);
  return [
    (bbox.x / 100) * app.sam3dSourceWidth,
    (bbox.y / 100) * app.sam3dSourceHeight,
    ((bbox.x + bbox.width) / 100) * app.sam3dSourceWidth,
    ((bbox.y + bbox.height) / 100) * app.sam3dSourceHeight,
  ];
}

function sam3dKnownVerticalFov() {
  const raw = String(elements.sam3dKnownVerticalFov.value || "").trim();
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 5 || value > 170) {
    throw new Error("Known vertical FOV must be between 5° and 170°.");
  }
  return value;
}

async function createSam3dJob() {
  if (
    app.sam3dMutationInFlight ||
    !app.sam3dSourceFile ||
    !sam3dStatusReady()
  ) {
    return;
  }
  const modelIds = sam3dSelectedModelIds();
  const comparing = app.sam3dModelChoice === SAM3D_COMPARE_MODEL_ID;
  if (
    !modelIds.length ||
    (comparing && modelIds.length !== SAM3D_MODEL_ORDER.length)
  ) {
    toast(
      "Model unavailable",
      comparing
        ? "Both DINOv3-H+ and ViT-H must be configured before comparing them."
        : "Choose a configured SAM 3D model.",
      "error",
    );
    return;
  }
  app.sam3dMutationInFlight = true;
  setButtonBusy(
    elements.sam3dRunButton,
    true,
    comparing ? "Creating comparison…" : "Uploading…",
  );
  elements.sam3dJobProgress.hidden = false;
  elements.sam3dJobProgress.className =
    "sam3d-job-progress is-running";
  elements.sam3dJobStage.textContent = "Uploading source image…";
  elements.sam3dJobMessage.textContent =
    "The image is being copied into VAM-PIP’s managed job storage.";
  elements.sam3dJobPercent.textContent = "0%";
  elements.sam3dJobProgressBar.value = 0;
  elements.sam3dJobRetry.hidden = true;
  let uploadedJob = null;
  try {
    const comparisonId = comparing ? newSam3dComparisonId() : "";
    const bbox = sam3dBboxPixels();
    const verticalFov = sam3dKnownVerticalFov();
    const uploadedJobs = [];
    for (const [index, modelId] of modelIds.entries()) {
      const model = sam3dModelById(modelId);
      elements.sam3dJobStage.textContent = comparing
        ? `Uploading ${sam3dModelDisplayName(model)} · ${index + 1} of ${modelIds.length}`
        : "Uploading source image…";
      const uploadPayload = await Sam3dClient.create(
        app.sam3dSourceFile,
        bbox,
        verticalFov,
        modelId,
        comparisonId,
      );
      uploadedJob = normalizeSam3dJob(
        uploadPayload.job || uploadPayload,
      );
      if (!uploadedJob) {
        throw new Error("The manager did not return a valid SAM 3D job.");
      }
      uploadedJobs.push(uploadedJob);
      mergeSam3dJob(uploadedJob);
    }

    const primaryJob = uploadedJobs[0];
    app.sam3dSelectedJobId = primaryJob.id;
    app.sam3dSelectedJob = primaryJob;
    app.sam3dSelectedBodyIndex = primaryJob.selectedBodyIndex;
    app.sam3dSelectedCaptureRequestId = "";
    app.sam3dSourceJobId = primaryJob.id;
    app.sam3dPreviewKind = "source";
    elements.sam3dJobStage.textContent = "Starting isolated worker…";
    elements.sam3dJobMessage.textContent =
      comparing
        ? "Both sources are stored. VAM-PIP is queueing DINOv3-H+ and ViT-H inference in sequence."
        : "The source is stored. VAM-PIP is queueing native SAM 3D Body inference.";
    renderSam3dWorkspace();

    for (const job of uploadedJobs) {
      const runPayload = await Sam3dClient.run(job.id);
      const queuedJob = normalizeSam3dJob(
        runPayload.job || runPayload,
      );
      if (!queuedJob) {
        throw new Error("The manager did not confirm the queued job.");
      }
      mergeSam3dJob(queuedJob);
    }
    renderSam3dWorkspace();
    startSam3dPolling();
    toast(
      comparing ? "Model comparison started" : "SAM 3D job started",
      comparing
        ? "DINOv3-H+ and ViT-H are queued from the same input. Their overlays will appear together."
        : "The standalone worker is reconstructing the pose and camera.",
    );
  } catch (error) {
    elements.sam3dJobProgress.className =
      "sam3d-job-progress is-error";
    elements.sam3dJobStage.textContent = "Could not start the job";
    elements.sam3dJobMessage.textContent = errorMessage(error);
    elements.sam3dJobRetry.hidden = !uploadedJob;
    toast("Could not start SAM 3D", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dRunButton, false);
    renderSam3dRuntime();
    renderSam3dHistory();
  }
}

async function retrySam3dJob() {
  const job = app.sam3dSelectedJob;
  if (
    app.sam3dMutationInFlight ||
    !job ||
    !["uploaded", "failed", "interrupted", "cancelled"].includes(
      sam3dJobState(job),
    )
  ) {
    return;
  }
  app.sam3dMutationInFlight = true;
  setButtonBusy(elements.sam3dJobRetry, true, "Queueing…");
  try {
    const payload = await Sam3dClient.run(job.id);
    const queued = normalizeSam3dJob(payload.job || payload);
    if (!queued) throw new Error("The manager did not confirm the queued job.");
    mergeSam3dJob(queued);
    renderSam3dWorkspace();
    startSam3dPolling();
    toast("SAM 3D job restarted", "The isolated worker accepted the job.");
  } catch (error) {
    toast("Could not restart SAM 3D", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dJobRetry, false);
    renderSam3dWorkspace();
  }
}

function sam3dSelectedCapture(job) {
  const captures = asArray(job?.captures);
  if (app.sam3dSelectedCaptureRequestId) {
    return (
      captures.find(
        (capture) =>
          capture.requestId === app.sam3dSelectedCaptureRequestId,
      ) || null
    );
  }
  return captures[0] || null;
}

function sam3dCaptureNavigation(job) {
  const captures = asArray(job?.captures);
  const pendingRequestId = String(job?.captureRequestId || "")
    .trim()
    .toLowerCase();
  const hasPendingEntry =
    SAM3D_JOB_ID_PATTERN.test(pendingRequestId) &&
    job?.captureRequested === true &&
    !captures.some(
      (capture) => capture.requestId === pendingRequestId,
    );
  return (
    hasPendingEntry
      ? [
          {
            requestId: pendingRequestId,
            capturedAt: "",
            pending: true,
          },
          ...captures,
        ]
      : captures
  );
}

function sam3dArtifactCandidate(job, kind) {
  const result = job?.rawResult || {};
  const selectedCapture = sam3dSelectedCapture(job);
  const artifacts =
    job?.artifacts && typeof job.artifacts === "object"
      ? job.artifacts
      : {};
  const resultArtifacts =
    result.artifacts && typeof result.artifacts === "object"
      ? result.artifacts
      : {};
  const artifactUrls =
    job?.artifactUrls && typeof job.artifactUrls === "object"
      ? job.artifactUrls
      : {};
  const aliases = {
    source: [
      artifactUrls.source,
      artifacts.source,
      resultArtifacts.source,
      job?.source_url,
      job?.sourceUrl,
      result.source_url,
    ],
    overlay: [
      artifactUrls.overlay,
      artifacts.overlay,
      resultArtifacts.overlay,
      job?.overlay_url,
      job?.overlayUrl,
      result.overlay_url,
    ],
    result: [
      selectedCapture?.artifactUrl,
      artifactUrls.capture,
      artifacts.result,
      resultArtifacts.result,
      job?.result_url,
      result.result_url,
    ],
    capture: [
      selectedCapture?.artifactUrl,
      artifactUrls.capture,
      artifacts.capture,
      resultArtifacts.capture,
      job?.capture_url,
      job?.captureUrl,
      result.capture_url,
    ],
  };
  for (const candidate of aliases[kind] || []) {
    const value =
      candidate && typeof candidate === "object"
        ? candidate.url || candidate.href
        : candidate;
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function sam3dSafeArtifactUrl(candidate) {
  if (!candidate) return "";
  try {
    const url = new URL(candidate, window.location.href);
    if (url.origin !== window.location.origin) return "";
    if (!url.pathname.startsWith("/api/sam3d/")) return "";
    if (app.token && !url.searchParams.has("token")) {
      url.searchParams.set("token", app.token);
    }
    return `${url.pathname}${url.search}`;
  } catch (_error) {
    return "";
  }
}

function sam3dArtifactUrl(job, kind) {
  if (!job?.id) return "";
  if (
    kind === "source" &&
    job.id === app.sam3dSourceJobId &&
    app.sam3dSourceUrl
  ) {
    return app.sam3dSourceUrl;
  }
  if (
    ["capture", "result"].includes(kind) &&
    app.sam3dSelectedCaptureRequestId &&
    !sam3dSelectedCapture(job)
  ) {
    return "";
  }
  const supplied = sam3dSafeArtifactUrl(
    sam3dArtifactCandidate(job, kind),
  );
  if (supplied) return supplied;
  try {
    const fallbackKind = kind === "result" ? "capture" : kind;
    return Sam3dClient.artifactUrl(job.id, fallbackKind);
  } catch (_error) {
    return "";
  }
}

function sam3dModelPillClass(job) {
  if (job?.model?.id === SAM3D_DINOV3_MODEL_ID) return " is-dinov3";
  if (job?.model?.id === SAM3D_VITH_MODEL_ID) return " is-vith";
  return "";
}

function sam3dComparisonJobs(job) {
  if (!SAM3D_JOB_ID_PATTERN.test(String(job?.comparisonId || ""))) return [];
  const candidates = app.sam3dJobs.filter(
    (candidate) => candidate.comparisonId === job.comparisonId,
  );
  const modelIds = new Set(
    candidates.map((candidate) => candidate.model?.id || ""),
  );
  if (
    candidates.length !== SAM3D_MODEL_ORDER.length ||
    modelIds.size !== SAM3D_MODEL_ORDER.length ||
    !SAM3D_MODEL_ORDER.every((modelId) => modelIds.has(modelId))
  ) {
    return [];
  }
  return SAM3D_MODEL_ORDER.map((modelId) =>
    candidates.find((candidate) => candidate.model?.id === modelId),
  ).filter(Boolean);
}

function renderSam3dComparison(job) {
  const jobs = sam3dComparisonJobs(job);
  const visible = jobs.length === SAM3D_MODEL_ORDER.length;
  elements.sam3dComparison.hidden = !visible;
  elements.sam3dComparisonGrid.replaceChildren();
  if (!visible) return;

  const fragment = document.createDocumentFragment();
  for (const candidate of jobs) {
    const card = createElement("article", "sam3d-comparison-card");
    card.classList.toggle("active", candidate.id === app.sam3dSelectedJobId);

    const heading = createElement("header", "sam3d-comparison-card-heading");
    const model = createElement(
      "span",
      `sam3d-model-pill${sam3dModelPillClass(candidate)}`,
    );
    model.textContent = sam3dModelDisplayName(candidate);
    const state = createElement(
      "span",
      `sam3d-comparison-state ${sam3dHistoryStateClass(candidate)}`.trim(),
    );
    state.textContent = sam3dJobState(candidate);
    heading.append(model, state);

    const media = createElement("div", "sam3d-comparison-media");
    if (sam3dJobSucceeded(candidate)) {
      const image = document.createElement("img");
      image.alt = `${sam3dModelDisplayName(candidate)} joint overlay`;
      image.loading = "lazy";
      image.addEventListener("error", () => {
        const empty = createElement("span", "sam3d-comparison-empty");
        empty.textContent = "Overlay unavailable";
        media.replaceChildren(empty);
      });
      image.src = sam3dArtifactUrl(candidate, "overlay");
      media.append(image);
    } else {
      const empty = createElement("span", "sam3d-comparison-empty");
      empty.textContent = sam3dJobFailed(candidate)
        ? candidate.message || "Inference failed"
        : `${Math.round(candidate.progressPercent)}% · ${candidate.stage}`;
      media.append(empty);
    }

    const footer = createElement("footer", "sam3d-comparison-card-footer");
    const detail = document.createElement("span");
    detail.textContent = sam3dJobSucceeded(candidate)
      ? "Joint overlay ready"
      : sam3dJobState(candidate);
    const select = button(
      candidate.id === app.sam3dSelectedJobId
        ? "Selected"
        : sam3dJobSucceeded(candidate)
          ? "Review & apply"
          : "View job",
      "secondary-button small",
    );
    select.dataset.sam3dCompareJobId = candidate.id;
    select.disabled = candidate.id === app.sam3dSelectedJobId;
    footer.append(detail, select);
    card.append(heading, media, footer);
    fragment.append(card);
  }
  elements.sam3dComparisonGrid.append(fragment);
}

function sam3dBodyLabel(body, index) {
  const score = Number(
    body?.score ?? body?.confidence ?? body?.detection_score,
  );
  const scoreLabel = Number.isFinite(score)
    ? ` · ${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`
    : "";
  return String(
    body?.label ||
      body?.name ||
      `Body ${index + 1}${scoreLabel}`,
  );
}

function renderSam3dJob() {
  const job = app.sam3dSelectedJob;
  const hasJob = Boolean(job);
  elements.sam3dJobProgress.hidden = !hasJob;
  elements.sam3dResultPanel.hidden =
    !hasJob || !sam3dJobSucceeded(job);
  elements.sam3dHandoff.hidden =
    !hasJob || !sam3dJobSucceeded(job);
  if (!job) {
    elements.sam3dComparison.hidden = true;
    elements.sam3dComparisonGrid.replaceChildren();
    return;
  }

  elements.sam3dResultModel.className =
    `sam3d-model-pill${sam3dModelPillClass(job)}`;
  elements.sam3dResultModel.textContent = sam3dModelDisplayName(job);
  elements.sam3dResultModel.title = job.model?.backbone || "";
  renderSam3dComparison(job);

  const succeeded = sam3dJobSucceeded(job);
  const failed = sam3dJobFailed(job);
  const running = sam3dJobIsActive(job);
  elements.sam3dJobProgress.className =
    `sam3d-job-progress ${
      failed ? "is-error" : succeeded ? "is-complete" : running ? "is-running" : ""
    }`;
  const progress = succeeded ? 100 : job.progressPercent;
  elements.sam3dJobProgressBar.value = progress;
  elements.sam3dJobPercent.textContent = `${Math.round(progress)}%`;
  elements.sam3dJobStage.textContent = failed
    ? "Reconstruction failed"
    : job.stage || (running ? "Reconstructing…" : "Job finished");
  elements.sam3dJobMessage.textContent =
    job.message ||
    (succeeded
      ? "Pose and camera reconstruction are ready for review."
      : running
        ? "The standalone worker is processing this image."
        : sam3dJobState(job) === "uploaded"
          ? "The source is stored. Start the worker to run inference."
          : "The job ended without a reconstruction.");
  elements.sam3dJobRetry.hidden =
    !["uploaded", "failed", "interrupted", "cancelled"].includes(
      sam3dJobState(job),
    );

  if (!succeeded) return;
  const bodies = job.bodies.length ? job.bodies : [{}];
  app.sam3dSelectedBodyIndex = Math.max(
    0,
    Math.min(app.sam3dSelectedBodyIndex, bodies.length - 1),
  );
  elements.sam3dBodySelect.replaceChildren(
    ...bodies.map(
      (body, index) =>
        new Option(sam3dBodyLabel(body, index), String(index)),
    ),
  );
  elements.sam3dBodySelect.value = String(
    app.sam3dSelectedBodyIndex,
  );
  elements.sam3dBodySelect.disabled =
    bodies.length <= 1 || app.sam3dMutationInFlight;
  elements.sam3dRevision.textContent = job.revision
    ? `Revision ${job.revision}`
    : "Revision unavailable";

  if (elements.sam3dApplyPanel.dataset.jobId !== job.id) {
    elements.sam3dApplyPanel.dataset.jobId = job.id;
    elements.sam3dCameraFov.value = "";
    elements.sam3dPersonHeight.value = "1.65";
    elements.sam3dAspectRatio.value = "16:9";
    renderSam3dResolutionOptions("1920x1080 (FHD)");
    elements.sam3dImageFormat.value = "jpeg";
    elements.sam3dKeepReference.checked = true;
  }
  renderSam3dPreview();
}

function setSam3dPreview(kind) {
  if (!["source", "overlay", "result"].includes(kind)) return;
  app.sam3dPreviewKind = kind;
  if (
    kind === "result" &&
    !app.sam3dSelectedCaptureRequestId
  ) {
    app.sam3dSelectedCaptureRequestId =
      app.sam3dSelectedJob?.captures[0]?.requestId || "";
  }
  if (kind === "result") app.sam3dCapturePollAttempts = 0;
  renderSam3dPreview();
}

function sam3dCaptureDisplayDate(capture) {
  if (!capture?.capturedAt) return "Saved capture";
  const date = new Date(capture.capturedAt);
  return Number.isNaN(date.getTime())
    ? "Saved capture"
    : date.toLocaleString();
}

function renderSam3dCaptureHistory(job, kind) {
  const captures = sam3dCaptureNavigation(job);
  const visible = kind === "result" && captures.length > 0;
  elements.sam3dCaptureHistory.hidden = !visible;
  if (!visible) return;

  let index = captures.findIndex(
    (capture) =>
      capture.requestId === app.sam3dSelectedCaptureRequestId,
  );
  if (index < 0) {
    index = 0;
    app.sam3dSelectedCaptureRequestId = captures[0].requestId;
  }
  const capture = captures[index];
  const actionState = sam3dVamActionState(job);
  const pendingLabel = ["failed", "stale"].includes(actionState)
    ? "New capture failed"
    : actionState === "succeeded"
      ? "New capture finishing"
      : "New capture rendering";
  elements.sam3dCaptureHistoryLabel.textContent =
    capture.pending === true
      ? `${pendingLabel} · ${captures.length - 1} saved`
      : `Capture ${index + 1} of ${captures.length} · ` +
        sam3dCaptureDisplayDate(capture);
  elements.sam3dCapturePrevious.disabled =
    index <= 0 || app.sam3dMutationInFlight;
  elements.sam3dCaptureNext.disabled =
    index >= captures.length - 1 || app.sam3dMutationInFlight;
}

function moveSam3dCapture(delta) {
  const job = app.sam3dSelectedJob;
  const captures = sam3dCaptureNavigation(job);
  if (!captures.length || app.sam3dPreviewKind !== "result") return;
  const current = Math.max(
    0,
    captures.findIndex(
      (capture) =>
        capture.requestId === app.sam3dSelectedCaptureRequestId,
    ),
  );
  const next = Math.max(
    0,
    Math.min(captures.length - 1, current + delta),
  );
  if (next === current) return;
  app.sam3dSelectedCaptureRequestId = captures[next].requestId;
  app.sam3dCapturePollAttempts = 0;
  renderSam3dPreview();
}

function sam3dCaptureBridgeError(job) {
  if (!job?.captureRequestId) return "";
  if (
    app.sam3dSelectedCaptureRequestId &&
    app.sam3dSelectedCaptureRequestId !== job.captureRequestId
  ) {
    return "";
  }
  if (["failed", "stale"].includes(sam3dVamActionState(job))) {
    return (
      job.vamActionMessage ||
      "The VaM bridge did not complete the capture request."
    );
  }
  const bridge =
    app.person?.bridge && typeof app.person.bridge === "object"
      ? app.person.bridge
      : {};
  const requestId = String(
    bridge.requestId || bridge.request_id || "",
  ).trim();
  const state = String(bridge.state || "").trim().toLowerCase();
  if (requestId !== job.captureRequestId || state !== "error") return "";
  return (
    String(bridge.message || "").trim() ||
    "The VaM bridge reported that the capture failed."
  );
}

function setSam3dPreviewEmpty(title, detail, visible) {
  elements.sam3dPreviewEmptyTitle.textContent = title;
  elements.sam3dPreviewEmptyDetail.textContent = detail;
  elements.sam3dPreviewEmpty.hidden = !visible;
}

function renderSam3dPreview() {
  const job = app.sam3dSelectedJob;
  const kind = app.sam3dPreviewKind;
  renderSam3dCaptureHistory(job, kind);
  for (const buttonElement of [
    elements.sam3dPreviewSource,
    elements.sam3dPreviewOverlay,
    elements.sam3dPreviewResult,
  ]) {
    const active = buttonElement.dataset.sam3dPreview === kind;
    buttonElement.classList.toggle("active", active);
    buttonElement.setAttribute("aria-selected", String(active));
  }
  if (!job) {
    elements.sam3dPreviewImage.removeAttribute("src");
    setSam3dPreviewEmpty(
      "No reconstruction selected",
      "Choose a completed job from the history.",
      true,
    );
    return;
  }
  const artifactKind = kind === "result" ? "capture" : kind;
  const selectedCapture =
    kind === "result" ? sam3dSelectedCapture(job) : null;
  const hasExplicitCaptureSelection = Boolean(
    app.sam3dSelectedCaptureRequestId,
  );
  const captureReady =
    Boolean(selectedCapture) ||
    (!hasExplicitCaptureSelection &&
      (job.captured || app.sam3dCaptureReadyJobs.has(job.id)));
  const captureRequested =
    Boolean(selectedCapture) ||
    (hasExplicitCaptureSelection
      ? app.sam3dSelectedCaptureRequestId === job.captureRequestId
      : job.captureRequested || captureReady);
  const captureError =
    kind === "result" ? sam3dCaptureBridgeError(job) : "";
  const captureTimedOut =
    kind === "result" &&
    captureRequested &&
    !captureReady &&
    app.sam3dCapturePollAttempts >= SAM3D_CAPTURE_POLL_ATTEMPTS;
  const knownMissing = kind === "result" && !captureRequested;
  const url = knownMissing ? "" : sam3dArtifactUrl(job, artifactKind);
  const captions = {
    source: "Original source image",
    overlay: `Detected joints · body ${app.sam3dSelectedBodyIndex + 1}`,
    result: captureReady
      ? "VaM capture ready · VR Video & Funscript Exporter"
      : captureRequested
        ? "Waiting for VaM capture · VR Video & Funscript Exporter"
        : "VaM screenshot from VR Video & Funscript Exporter",
  };
  elements.sam3dPreviewCaption.textContent = captions[kind];
  if (kind === "result") {
    if (captureError) {
      setSam3dPreviewEmpty("VaM capture failed", captureError, true);
    } else if (captureTimedOut) {
      setSam3dPreviewEmpty(
        "Capture is still unavailable",
        "The five-minute render window elapsed without a readable image. Check VaM, then request the capture again.",
        true,
      );
    } else if (captureRequested && !captureReady) {
      setSam3dPreviewEmpty(
        "VaM capture is rendering",
        "The VR Video & Funscript exporter may need up to five minutes to render and encode this image.",
        true,
      );
    } else if (!captureRequested) {
      setSam3dPreviewEmpty(
        "No VaM capture yet",
        "Apply the result and capture through the VR Video & Funscript camera.",
        true,
      );
    } else {
      setSam3dPreviewEmpty("", "", false);
    }
  } else {
    setSam3dPreviewEmpty(
      "Preview unavailable",
      "This reconstruction artifact could not be loaded.",
      !url,
    );
  }
  if (!url) {
    elements.sam3dPreviewImage.removeAttribute("src");
    return;
  }
  elements.sam3dPreviewImage.alt = captions[kind];
  elements.sam3dPreviewImage.onload = () => {
    app.sam3dCapturePollAttempts = 0;
    if (kind === "result") {
      const firstReady =
        !job.captured && !app.sam3dCaptureReadyJobs.has(job.id);
      app.sam3dCaptureReadyJobs.add(job.id);
      job.captured = true;
      elements.sam3dPreviewCaption.textContent =
        "VaM capture ready · VR Video & Funscript Exporter";
      if (firstReady) {
        toast(
          "VaM capture ready",
          "The rendered image is now available in VAM-PIP.",
        );
      }
    }
    setSam3dPreviewEmpty("", "", false);
  };
  elements.sam3dPreviewImage.onerror = () => {
    elements.sam3dPreviewImage.removeAttribute("src");
    if (kind !== "result") {
      setSam3dPreviewEmpty(
        "Preview unavailable",
        "This reconstruction artifact could not be loaded.",
        true,
      );
    }
    if (
      kind === "result" &&
      captureRequested &&
      !captureError &&
      app.view === "sam3d" &&
      app.sam3dSelectedJobId === job.id &&
      app.sam3dCapturePollAttempts < SAM3D_CAPTURE_POLL_ATTEMPTS
    ) {
      app.sam3dCapturePollAttempts += 1;
      window.setTimeout(() => {
        if (
          app.view === "sam3d" &&
          app.sam3dPreviewKind === "result" &&
          app.sam3dSelectedJobId === job.id
        ) {
          renderSam3dPreview();
        }
      }, 1_000);
    }
  };
  elements.sam3dPreviewImage.src = url;
}

function selectSam3dBody(value) {
  const job = app.sam3dSelectedJob;
  const bodyIndex = integerValue(value);
  if (
    !job ||
    bodyIndex === null ||
    bodyIndex < 0 ||
    bodyIndex >= Math.max(1, job.bodies.length) ||
    bodyIndex === app.sam3dSelectedBodyIndex
  ) {
    return;
  }
  app.sam3dSelectedBodyIndex = bodyIndex;
  app.sam3dPreviewKind = "overlay";
  renderSam3dJob();
  renderSam3dApplyState();
}

function normalizeSam3dBodyReference(raw) {
  let document = raw;
  if (typeof raw === "string") {
    const value = raw.trim().toLowerCase();
    const tokenMatch = value.match(/^([0-9a-f]{32}):([0-9]+)$/);
    document = tokenMatch
      ? { job_id: tokenMatch[1], person_index: tokenMatch[2] }
      : { job_id: value, person_index: 0 };
  }
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    return null;
  }
  const jobId = String(
    document.job_id ||
      document.jobId ||
      document.reference_job_id ||
      document.referenceJobId ||
      "",
  )
    .trim()
    .toLowerCase();
  const personIndex = integerValue(
    document.person_index ??
      document.personIndex ??
      document.reference_person_index ??
      document.referencePersonIndex ??
      0,
  );
  if (
    !SAM3D_JOB_ID_PATTERN.test(jobId) ||
    personIndex === null ||
    personIndex < 0
  ) {
    return null;
  }
  return { jobId, personIndex };
}

function normalizeSam3dBodyReferences(
  raw,
  legacyReferenceJobId = "",
  legacyPersonIndex = 0,
) {
  let candidates = raw;
  if (typeof raw === "string") {
    candidates = raw
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }
  candidates = asArray(candidates);
  if (!candidates.length && legacyReferenceJobId) {
    candidates = [
      {
        job_id: legacyReferenceJobId,
        person_index: legacyPersonIndex,
      },
    ];
  }
  const seen = new Set();
  const references = [];
  for (const candidate of candidates) {
    const reference = normalizeSam3dBodyReference(candidate);
    if (!reference) continue;
    if (seen.has(reference.jobId)) continue;
    seen.add(reference.jobId);
    references.push(reference);
    if (references.length >= SAM3D_BODY_REFERENCE_MAX_COUNT) break;
  }
  return references;
}

function sam3dBodyReferenceToken(reference) {
  const normalized = normalizeSam3dBodyReference(reference);
  return normalized
    ? `${normalized.jobId}:${normalized.personIndex}`
    : "";
}

function serializeSam3dBodyReferences(references) {
  return normalizeSam3dBodyReferences(references)
    .map(sam3dBodyReferenceToken)
    .filter(Boolean)
    .join(",");
}

function sam3dBodyReferenceSupport(job, personIndex) {
  return (
    asArray(job?.bodyReferenceSupport).find(
      (support) => support.personIndex === personIndex,
    ) || {
      personIndex,
      space: "legacy",
      multiReference: false,
    }
  );
}

function sam3dBodyReferenceCandidates() {
  const candidates = [];
  for (const job of app.sam3dJobs.filter(sam3dJobSucceeded)) {
    const bodies = job.bodies.length ? job.bodies : [{}];
    for (let personIndex = 0; personIndex < bodies.length; personIndex += 1) {
      candidates.push({
        job,
        body: bodies[personIndex],
        support: sam3dBodyReferenceSupport(job, personIndex),
        reference: { jobId: job.id, personIndex },
      });
    }
  }
  return candidates;
}

function sam3dBodyReferenceCandidate(reference) {
  const token = sam3dBodyReferenceToken(reference);
  return (
    sam3dBodyReferenceCandidates().find(
      (candidate) => sam3dBodyReferenceToken(candidate.reference) === token,
    ) || null
  );
}

function sam3dBodyReferenceAvailable(reference) {
  return Boolean(sam3dBodyReferenceCandidate(reference));
}

function sam3dBodyReferenceSetIssue(
  references,
  structureRegions = SAM3D_BODY_PROPORTION_REGIONS,
) {
  const structureSelected = asArray(structureRegions).some((region) =>
    SAM3D_BODY_PROPORTION_REGIONS.includes(region),
  );
  if (!structureSelected) return "";
  const normalized = normalizeSam3dBodyReferences(references);
  if (normalized.length < 2) return "";
  const soloOnly = normalized.some((reference) => {
    const candidate = sam3dBodyReferenceCandidate(reference);
    return candidate && candidate.support.multiReference !== true;
  });
  return soloOnly ? SAM3D_BODY_LEGACY_SOLO_MESSAGE : "";
}

function initializeSam3dBodyReferences() {
  if (app.sam3dBodyReferencesInitialized) return;
  const job =
    app.sam3dSelectedJob && sam3dJobSucceeded(app.sam3dSelectedJob)
      ? app.sam3dSelectedJob
      : app.sam3dJobs.find(sam3dJobSucceeded);
  if (!job) return;
  app.sam3dBodyReferences = normalizeSam3dBodyReferences([
    {
      jobId: job.id,
      personIndex:
        job.id === app.sam3dSelectedJobId
          ? app.sam3dSelectedBodyIndex
          : job.selectedBodyIndex,
    },
  ]);
  app.sam3dBodyReferencesInitialized = true;
}

function setSam3dBodyReferences(references, { dirty = true } = {}) {
  const previous = normalizeSam3dBodyReferences(app.sam3dBodyReferences);
  const next = normalizeSam3dBodyReferences(references);
  const previousTokens = serializeSam3dBodyReferences(previous);
  const nextTokens = serializeSam3dBodyReferences(next);
  app.sam3dBodyReferences = next;
  app.sam3dBodyReferencesInitialized = true;
  if (previousTokens === nextTokens) return false;
  const previousJobId = previous[0]?.jobId || "";
  const nextJobId = next[0]?.jobId || "";
  if (previousJobId !== nextJobId) {
    resetSam3dBodyProportions(nextJobId);
  } else if (dirty) {
    markSam3dBodyProportionsDirty();
  }
  renderSam3dBodyReferenceGallery();
  renderSam3dBodyProfileActionState();
  renderSam3dBodyProportions();
  return true;
}

function toggleSam3dBodyReference(
  value,
  structureRegions = sam3dBodyProportionSettings().regions,
) {
  const reference = normalizeSam3dBodyReference(value);
  if (!reference) return;
  const token = sam3dBodyReferenceToken(reference);
  const current = normalizeSam3dBodyReferences(app.sam3dBodyReferences);
  const index = current.findIndex(
    (candidate) => sam3dBodyReferenceToken(candidate) === token,
  );
  if (index >= 0) {
    current.splice(index, 1);
    setSam3dBodyReferences(current);
    return;
  }
  const referenceCandidate = sam3dBodyReferenceCandidate(reference);
  if (!referenceCandidate) return;
  const sameJobIndex = current.findIndex(
    (candidate) => candidate.jobId === reference.jobId,
  );
  if (sameJobIndex >= 0) {
    const replacement = [...current];
    replacement.splice(sameJobIndex, 1, reference);
    if (sam3dBodyReferenceSetIssue(replacement, structureRegions)) {
      toast(
        "Cannot combine this Morph reference",
        SAM3D_BODY_LEGACY_SOLO_MESSAGE,
        "error",
      );
      return;
    }
    setSam3dBodyReferences(replacement);
    return;
  }
  if (
    current.length &&
    sam3dBodyReferenceSetIssue(
      [...current, reference],
      structureRegions,
    )
  ) {
    toast(
      "Cannot combine this Morph reference",
      SAM3D_BODY_LEGACY_SOLO_MESSAGE,
      "error",
    );
    return;
  }
  if (current.length >= SAM3D_BODY_REFERENCE_MAX_COUNT) {
    toast(
      "Morph reference limit reached",
      `Choose at most ${SAM3D_BODY_REFERENCE_MAX_COUNT} completed bodies.`,
      "error",
    );
    return;
  }
  current.push(reference);
  setSam3dBodyReferences(current);
}

function createSam3dBodyReferenceCard(
  reference,
  { job = null, body = null, support = null, missing = false } = {},
) {
  const token = sam3dBodyReferenceToken(reference);
  const selected = app.sam3dBodyReferences.some(
    (candidate) => sam3dBodyReferenceToken(candidate) === token,
  );
  const atLimit =
    app.sam3dBodyReferences.length >= SAM3D_BODY_REFERENCE_MAX_COUNT;
  const replacesSelectedJob = app.sam3dBodyReferences.some(
    (candidate) => candidate.jobId === reference.jobId,
  );
  const card = button(
    "",
    `sam3d-morph-reference-card${selected ? " is-selected" : ""}${
      missing ? " is-missing" : ""
    }${
      !missing && support?.multiReference !== true
        ? " is-solo-only"
        : ""
    }`,
  );
  card.dataset.sam3dBodyReference = token;
  card.setAttribute("role", "option");
  card.setAttribute("aria-selected", String(selected));
  card.disabled =
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    Boolean(app.sam3dBodyProportions?.applied) ||
    (!selected && atLimit && !replacesSelectedJob);

  if (!missing) {
    const thumb = createElement("span", "sam3d-morph-reference-thumb");
    const sourceUrl = sam3dArtifactUrl(job, "source");
    if (sourceUrl) {
      const image = document.createElement("img");
      image.alt = "";
      image.loading = "lazy";
      image.addEventListener("error", () => image.remove());
      image.src = sourceUrl;
      thumb.append(image);
    } else {
      thumb.textContent = "3D";
    }
    card.append(thumb);
  }

  const copy = createElement("span", "sam3d-morph-reference-copy");
  const title = document.createElement("strong");
  title.textContent = missing
    ? `Saved job ${reference.jobId.slice(0, 8)}…`
    : job.sourceName;
  const detail = document.createElement("span");
  detail.textContent = missing
    ? `Body ${reference.personIndex + 1} · not in recent completed jobs`
    : `${sam3dModelDisplayName(job)} · ${sam3dBodyLabel(
        body,
        reference.personIndex,
      )}`;
  copy.append(title, detail);
  if (!missing && support?.multiReference !== true) {
    const compatibility = createElement(
      "span",
      "sam3d-morph-reference-compatibility",
    );
    compatibility.textContent = "Structure · solo only";
    compatibility.title = SAM3D_BODY_LEGACY_SOLO_MESSAGE;
    copy.append(compatibility);
  }
  const state = createElement("span", "sam3d-morph-reference-state");
  state.textContent = selected ? "✓" : "+";
  card.append(copy, state);
  return card;
}

function renderSam3dBodyReferenceGallery() {
  initializeSam3dBodyReferences();
  app.sam3dBodyReferences = normalizeSam3dBodyReferences(
    app.sam3dBodyReferences,
  );
  elements.sam3dMorphReferenceGallery.replaceChildren();
  const fragment = document.createDocumentFragment();
  const availableTokens = new Set();
  for (const candidate of sam3dBodyReferenceCandidates()) {
    availableTokens.add(sam3dBodyReferenceToken(candidate.reference));
    fragment.append(
      createSam3dBodyReferenceCard(candidate.reference, candidate),
    );
  }
  for (const reference of app.sam3dBodyReferences) {
    if (!availableTokens.has(sam3dBodyReferenceToken(reference))) {
      fragment.append(
        createSam3dBodyReferenceCard(reference, { missing: true }),
      );
    }
  }
  if (!fragment.childNodes.length) {
    const empty = createElement("div", "inline-empty");
    const message = document.createElement("p");
    message.textContent = "No completed reconstruction bodies yet.";
    empty.append(message);
    fragment.append(empty);
  }
  elements.sam3dMorphReferenceGallery.append(fragment);
  elements.sam3dMorphReferenceCount.value =
    `${app.sam3dBodyReferences.length} / ${SAM3D_BODY_REFERENCE_MAX_COUNT}`;
  elements.sam3dMorphReferenceCount.textContent =
    elements.sam3dMorphReferenceCount.value;
  const missingCount = app.sam3dBodyReferences.filter(
    (reference) => !availableTokens.has(sam3dBodyReferenceToken(reference)),
  ).length;
  const structureRegions = sam3dBodyProportionSettings().regions;
  const combinationIssue = sam3dBodyReferenceSetIssue(
    app.sam3dBodyReferences,
    structureRegions,
  );
  const singleCandidate =
    app.sam3dBodyReferences.length === 1
      ? sam3dBodyReferenceCandidate(app.sam3dBodyReferences[0])
      : null;
  const soloLegacy =
    structureRegions.length > 0 &&
    singleCandidate &&
    singleCandidate.support.multiReference !== true;
  elements.sam3dMorphReferenceNote.classList.toggle(
    "is-error",
    missingCount > 0 ||
      Boolean(combinationIssue) ||
      !app.sam3dBodyReferences.length,
  );
  elements.sam3dMorphReferenceNote.classList.toggle(
    "is-warning",
    Boolean(soloLegacy) && !missingCount && !combinationIssue,
  );
  elements.sam3dMorphReferenceNote.textContent = missingCount
    ? `${missingCount} saved reference${
        missingCount === 1 ? " is" : "s are"
      } unavailable. Remove or replace ${
        missingCount === 1 ? "it" : "them"
      } before analyzing.`
    : combinationIssue
      ? combinationIssue
      : soloLegacy
        ? `${SAM3D_BODY_LEGACY_SOLO_MESSAGE} It remains usable alone.`
        : app.sam3dBodyReferences.length
          ? "These bodies drive only Morph analysis. Pose + camera stays bound to the separately selected current job."
          : "Select at least one completed body for Morph analysis.";
}

function emptySam3dManualShape() {
  return {
    schema: 1,
    offsets: Object.fromEntries(
      SAM3D_MANUAL_SHAPE_KEYS.map((key) => [key, 0]),
    ),
  };
}

function normalizeSam3dManualShape(raw) {
  const document =
    raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const rawOffsets =
    document.offsets &&
    typeof document.offsets === "object" &&
    !Array.isArray(document.offsets)
      ? document.offsets
      : document;
  const offsets = {};
  for (const key of SAM3D_MANUAL_SHAPE_KEYS) {
    const rawValue = rawOffsets[key];
    const number =
      typeof rawValue === "boolean" ? 0 : Number(rawValue);
    offsets[key] = Number.isFinite(number)
      ? Math.max(-1, Math.min(1, number))
      : 0;
  }
  return { schema: 1, offsets };
}

function sam3dManualShapeHasCorrections(value) {
  const normalized = normalizeSam3dManualShape(value);
  return SAM3D_MANUAL_SHAPE_KEYS.some(
    (key) => Math.abs(normalized.offsets[key]) > 1e-6,
  );
}

function serializeSam3dManualShape(value) {
  const normalized = normalizeSam3dManualShape(value);
  return JSON.stringify({
    schema: 1,
    offsets: Object.fromEntries(
      SAM3D_MANUAL_SHAPE_KEYS.map((key) => [
        key,
        normalized.offsets[key],
      ]),
    ),
  });
}

function normalizeSam3dManualOverlay(raw) {
  const document =
    raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const finite = (value, fallback) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  };
  return {
    panX: Math.max(
      -0.5,
      Math.min(0.5, finite(document.pan_x ?? document.panX, 0)),
    ),
    panY: Math.max(
      -0.5,
      Math.min(0.5, finite(document.pan_y ?? document.panY, 0)),
    ),
    scale: Math.max(
      0.5,
      Math.min(1.8, finite(document.scale, 1)),
    ),
    opacity: Math.max(
      0.1,
      Math.min(1, finite(document.opacity, 0.55)),
    ),
  };
}

function sam3dManualShapeControl(key) {
  const controls = {
    breast_size: elements.sam3dManualShapeBreastSize,
    breast_spacing: elements.sam3dManualShapeBreastSpacing,
    waist_width: elements.sam3dManualShapeWaistWidth,
    hip_width: elements.sam3dManualShapeHipWidth,
    glute_projection: elements.sam3dManualShapeGluteProjection,
    thigh_size: elements.sam3dManualShapeThighSize,
  };
  return controls[key] || null;
}

function sam3dManualShapeOutput(key) {
  const outputs = {
    breast_size: elements.sam3dManualShapeBreastSizeValue,
    breast_spacing: elements.sam3dManualShapeBreastSpacingValue,
    waist_width: elements.sam3dManualShapeWaistWidthValue,
    hip_width: elements.sam3dManualShapeHipWidthValue,
    glute_projection: elements.sam3dManualShapeGluteProjectionValue,
    thigh_size: elements.sam3dManualShapeThighSizeValue,
  };
  return outputs[key] || null;
}

function sam3dManualShapeRegion(key) {
  return {
    breast_size: "breasts",
    breast_spacing: "breasts",
    waist_width: "waist",
    hip_width: "hips",
    glute_projection: "glutes",
    thigh_size: "thighs",
  }[key] || "";
}

function effectiveSam3dManualShape() {
  return app.sam3dManualFitMode === "manual"
    ? normalizeSam3dManualShape(app.sam3dManualShape)
    : emptySam3dManualShape();
}

function setSam3dManualFitMode(mode) {
  if (!["estimator", "manual"].includes(mode)) return;
  const previous = serializeSam3dManualShape(effectiveSam3dManualShape());
  app.sam3dManualFitMode = mode;
  app.sam3dManualShape = normalizeSam3dManualShape(app.sam3dManualShape);
  const next = serializeSam3dManualShape(effectiveSam3dManualShape());
  if (previous !== next) {
    markSam3dBodyProportionsDirty();
  } else {
    renderSam3dBodyProportions();
  }
}

function handleSam3dManualShapeInput(event) {
  const key = SAM3D_MANUAL_SHAPE_KEYS.find(
    (candidate) => sam3dManualShapeControl(candidate) === event.currentTarget,
  );
  if (!key) return;
  const next = normalizeSam3dManualShape(app.sam3dManualShape);
  next.offsets[key] = Math.max(
    -1,
    Math.min(1, (Number(event.currentTarget.value) || 0) / 100),
  );
  app.sam3dManualShape = next;
  app.sam3dManualFitMode = "manual";
  markSam3dBodyProportionsDirty();
}

function resetSam3dManualShape() {
  const previous = serializeSam3dManualShape(effectiveSam3dManualShape());
  app.sam3dManualShape = emptySam3dManualShape();
  app.sam3dManualFitMode = "manual";
  const next = serializeSam3dManualShape(effectiveSam3dManualShape());
  if (previous !== next) {
    markSam3dBodyProportionsDirty();
  } else {
    renderSam3dBodyProportions();
  }
}

function sam3dManualReferenceCandidates(
  references = app.sam3dBodyReferences,
) {
  return normalizeSam3dBodyReferences(references)
    .map(sam3dBodyReferenceCandidate)
    .filter(Boolean);
}

function selectedSam3dManualReferenceCandidate() {
  const candidates = sam3dManualReferenceCandidates();
  const previousToken = app.sam3dManualReferenceToken;
  let selected = candidates.find(
    (candidate) =>
      sam3dBodyReferenceToken(candidate.reference) ===
      app.sam3dManualReferenceToken,
  );
  if (!selected) {
    selected = candidates[0] || null;
    app.sam3dManualReferenceToken = selected
      ? sam3dBodyReferenceToken(selected.reference)
      : "";
    if (
      previousToken &&
      previousToken !== app.sam3dManualReferenceToken
    ) {
      app.sam3dManualOverlay = normalizeSam3dManualOverlay({});
    }
  }
  return selected;
}

function sam3dManualReferenceGeometry(candidate) {
  const job = candidate?.job;
  const raw = asArray(
    candidate?.body?.bbox || job?.bbox || job?.source?.bbox,
  );
  const sourceUrl = sam3dArtifactUrl(job, "source");
  const image = elements.sam3dManualFitImage;
  const imageMatches =
    sourceUrl && image?.dataset.source === sourceUrl;
  const width = Math.max(
    1,
    Number(job?.sourceWidth) ||
      (imageMatches ? Number(image.naturalWidth) : 0) ||
      Number(raw[2]) ||
      100,
  );
  const height = Math.max(
    1,
    Number(job?.sourceHeight) ||
      (imageMatches ? Number(image.naturalHeight) : 0) ||
      Number(raw[3]) ||
      160,
  );
  let left = Number(raw[0]);
  let top = Number(raw[1]);
  let right = Number(raw[2]);
  let bottom = Number(raw[3]);
  if (
    raw.length !== 4 ||
    ![left, top, right, bottom].every(Number.isFinite) ||
    right <= left ||
    bottom <= top
  ) {
    [left, top, right, bottom] = [0, 0, width, height];
  }
  left = Math.max(0, Math.min(width, left));
  top = Math.max(0, Math.min(height, top));
  right = Math.max(left + 1, Math.min(width, right));
  bottom = Math.max(top + 1, Math.min(height, bottom));
  return {
    width,
    height,
    left,
    top,
    right,
    bottom,
    centerX: (left + right) / 2,
    centerY: (top + bottom) / 2,
    boxWidth: right - left,
    boxHeight: bottom - top,
  };
}

function autoAlignSam3dManualOverlay() {
  const current = normalizeSam3dManualOverlay(app.sam3dManualOverlay);
  app.sam3dManualOverlay = {
    ...current,
    panX: 0,
    panY: 0,
    scale: 1,
  };
  renderSam3dManualFit(app.sam3dBodyProportions);
}

function resetSam3dManualOverlay() {
  app.sam3dManualOverlay = normalizeSam3dManualOverlay({});
  renderSam3dManualFit(app.sam3dBodyProportions);
}

function readSam3dManualOverlayControls() {
  const current = normalizeSam3dManualOverlay(app.sam3dManualOverlay);
  app.sam3dManualOverlay = normalizeSam3dManualOverlay({
    ...current,
    scale: (Number(elements.sam3dManualOverlayScale.value) || 100) / 100,
    opacity:
      (Number(elements.sam3dManualOverlayOpacity.value) || 55) / 100,
  });
  renderSam3dManualOverlay(app.sam3dBodyProportions);
}

function sam3dManualStagePoint(event) {
  const svg = elements.sam3dManualFitSvg;
  try {
    const matrix = svg?.getScreenCTM?.();
    const viewBox = svg?.viewBox?.baseVal;
    if (
      matrix &&
      viewBox &&
      viewBox.width > 0 &&
      viewBox.height > 0
    ) {
      const point = svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const mapped = point.matrixTransform(matrix.inverse());
      return {
        x: (mapped.x - viewBox.x) / viewBox.width,
        y: (mapped.y - viewBox.y) / viewBox.height,
      };
    }
  } catch (_error) {
    // Fall back to stage-relative movement on older embedded browsers.
  }
  const bounds = elements.sam3dManualFitStage.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return null;
  return {
    x: (event.clientX - bounds.left) / bounds.width,
    y: (event.clientY - bounds.top) / bounds.height,
  };
}

function beginSam3dManualOverlayDrag(event) {
  if (event.button !== 0 || !selectedSam3dManualReferenceCandidate()) {
    return;
  }
  const point = sam3dManualStagePoint(event);
  if (!point) return;
  event.preventDefault();
  elements.sam3dManualFitStage.setPointerCapture(event.pointerId);
  app.sam3dManualOverlayDrag = {
    pointerId: event.pointerId,
    start: point,
    overlay: normalizeSam3dManualOverlay(app.sam3dManualOverlay),
  };
  elements.sam3dManualFitStage.classList.add("is-dragging");
}

function continueSam3dManualOverlayDrag(event) {
  const drag = app.sam3dManualOverlayDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const point = sam3dManualStagePoint(event);
  if (!point) return;
  app.sam3dManualOverlay = normalizeSam3dManualOverlay({
    ...drag.overlay,
    panX: drag.overlay.panX + point.x - drag.start.x,
    panY: drag.overlay.panY + point.y - drag.start.y,
  });
  renderSam3dManualOverlay(app.sam3dBodyProportions);
}

function finishSam3dManualOverlayDrag(event) {
  const drag = app.sam3dManualOverlayDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  continueSam3dManualOverlayDrag(event);
  app.sam3dManualOverlayDrag = null;
  elements.sam3dManualFitStage.classList.remove("is-dragging");
  if (elements.sam3dManualFitStage.hasPointerCapture(event.pointerId)) {
    elements.sam3dManualFitStage.releasePointerCapture(event.pointerId);
  }
}

function nudgeSam3dManualOverlay(event) {
  const movement = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }[event.key];
  if (!movement) return;
  event.preventDefault();
  const step = event.shiftKey ? 0.02 : 0.005;
  const current = normalizeSam3dManualOverlay(app.sam3dManualOverlay);
  app.sam3dManualOverlay = normalizeSam3dManualOverlay({
    ...current,
    panX: current.panX + movement[0] * step,
    panY: current.panY + movement[1] * step,
  });
  renderSam3dManualOverlay(app.sam3dBodyProportions);
}

function sam3dManualMeasurementTarget(analysis, id, fallback) {
  const measurement = [
    ...asArray(analysis?.measurements),
    ...asArray(analysis?.shapeMeasurements),
  ].find((candidate) => candidate.id === id);
  return Number.isFinite(measurement?.target)
    ? measurement.target
    : fallback;
}

function sam3dManualShapePreview(analysis) {
  const requested = effectiveSam3dManualShape();
  if (
    app.sam3dBodyProportionsDirty ||
    !analysis?.ready ||
    serializeSam3dManualShape(analysis.manualShape) !==
      serializeSam3dManualShape(requested)
  ) {
    return requested;
  }
  const result = normalizeSam3dManualShape(requested);
  const changes = new Map(
    asArray(analysis.manualShapeChanges).map((change) => [
      change.control,
      change,
    ]),
  );
  const unavailable = new Set(
    asArray(
      analysis.manualShapeUnavailable || analysis.shapeUnavailable,
    )
      .map((item) => item.control)
      .filter(Boolean),
  );
  for (const key of SAM3D_MANUAL_SHAPE_KEYS) {
    const semanticOffset = requested.offsets[key];
    const change = changes.get(key);
    if (
      change &&
      Math.abs(change.requestedOffset) > 1e-9 &&
      Number.isFinite(change.appliedOffset)
    ) {
      result.offsets[key] = Math.max(
        -1,
        Math.min(
          1,
          semanticOffset *
            (change.appliedOffset / change.requestedOffset),
        ),
      );
    } else if (unavailable.has(key)) {
      result.offsets[key] = 0;
    }
  }
  return result;
}

function sam3dManualShapeFeedback(analysis, key) {
  if (
    app.sam3dBodyProportionsDirty ||
    serializeSam3dManualShape(analysis?.manualShape) !==
      serializeSam3dManualShape(effectiveSam3dManualShape())
  ) {
    return "";
  }
  if (
    asArray(
      analysis?.manualShapeUnavailable ||
        analysis?.shapeUnavailable,
    ).some(
      (item) => item.control === key,
    )
  ) {
    return "unavailable";
  }
  return asArray(analysis?.manualShapeChanges).some(
    (change) => change.control === key && change.limited,
  )
    ? "capped"
    : "";
}

function sam3dManualSilhouetteGeometry(analysis) {
  const offsets = sam3dManualShapePreview(analysis).offsets;
  const structuralScale = 1.6;
  const shoulder = Math.max(
    30,
    Math.min(
      55,
      sam3dManualMeasurementTarget(
        analysis,
        "shoulderSpan",
        27,
      ) * structuralScale,
    ),
  );
  const bust = Math.max(
    30,
    Math.min(
      58,
      sam3dManualMeasurementTarget(analysis, "bustWidth", 26) *
        structuralScale *
        (1 + offsets.breast_size * 0.22),
    ),
  );
  const waist = Math.max(
    22,
    Math.min(
      52,
      sam3dManualMeasurementTarget(analysis, "waistWidth", 20) *
        structuralScale *
        (1 + offsets.waist_width * 0.3),
    ),
  );
  const hips = Math.max(
    30,
    Math.min(
      62,
      sam3dManualMeasurementTarget(analysis, "seatWidth", 27) *
        structuralScale *
        (1 + offsets.hip_width * 0.3) *
        (1 + offsets.glute_projection * 0.08),
    ),
  );
  const thigh = Math.max(
    11,
    Math.min(
      27,
      sam3dManualMeasurementTarget(
        analysis,
        "upperThighWidth",
        12,
      ) *
        structuralScale *
        (1 + offsets.thigh_size * 0.35),
    ),
  );
  const breastRadius = Math.max(4, 8 * (1 + offsets.breast_size * 0.55));
  const breastSpacing = Math.max(
    breastRadius * 0.62,
    9.5 * (1 + offsets.breast_spacing * 0.7),
  );
  return {
    shoulder,
    bust,
    waist,
    hips,
    thigh,
    breastRadius,
    breastSpacing,
  };
}

function renderSam3dManualOverlay(analysis) {
  const candidate = selectedSam3dManualReferenceCandidate();
  if (!candidate) return;
  const reference = sam3dManualReferenceGeometry(candidate);
  const overlay = normalizeSam3dManualOverlay(app.sam3dManualOverlay);
  const shape = sam3dManualSilhouetteGeometry(analysis);
  const left = (width) => 50 - width / 2;
  const right = (width) => 50 + width / 2;
  elements.sam3dManualFitBody.setAttribute(
    "d",
    [
      "M 43 18",
      "C 42 10 44 4 50 4",
      "C 56 4 58 10 57 18",
      `L ${right(shape.shoulder).toFixed(2)} 28`,
      `C ${right(shape.shoulder + 3).toFixed(2)} 36 ${right(shape.bust).toFixed(2)} 46 ${right(shape.bust).toFixed(2)} 59`,
      `C ${right(shape.bust).toFixed(2)} 69 ${right(shape.waist).toFixed(2)} 77 ${right(shape.waist).toFixed(2)} 88`,
      `C ${right(shape.waist).toFixed(2)} 99 ${right(shape.hips).toFixed(2)} 101 ${right(shape.hips).toFixed(2)} 112`,
      `C ${right(shape.hips).toFixed(2)} 122 ${right(shape.thigh * 2).toFixed(2)} 126 ${right(shape.thigh * 2).toFixed(2)} 135`,
      `L ${right(shape.thigh).toFixed(2)} 155`,
      "L 52 155",
      "L 50 132",
      "L 48 155",
      `L ${left(shape.thigh).toFixed(2)} 155`,
      `L ${left(shape.thigh * 2).toFixed(2)} 135`,
      `C ${left(shape.thigh * 2).toFixed(2)} 126 ${left(shape.hips).toFixed(2)} 122 ${left(shape.hips).toFixed(2)} 112`,
      `C ${left(shape.hips).toFixed(2)} 101 ${left(shape.waist).toFixed(2)} 99 ${left(shape.waist).toFixed(2)} 88`,
      `C ${left(shape.waist).toFixed(2)} 77 ${left(shape.bust).toFixed(2)} 69 ${left(shape.bust).toFixed(2)} 59`,
      `C ${left(shape.bust).toFixed(2)} 46 ${left(shape.shoulder + 3).toFixed(2)} 36 ${left(shape.shoulder).toFixed(2)} 28`,
      "L 43 18 Z",
    ].join(" "),
  );
  for (const [element, direction] of [
    [elements.sam3dManualFitBreastLeft, -1],
    [elements.sam3dManualFitBreastRight, 1],
  ]) {
    element.setAttribute(
      "cx",
      String(50 + direction * shape.breastSpacing),
    );
    element.setAttribute("cy", "59");
    element.setAttribute("rx", String(shape.breastRadius));
    element.setAttribute(
      "ry",
      String(shape.breastRadius * (1 + offsetsForProjection(analysis))),
    );
  }
  const baseScale = 0.9 * Math.min(
    reference.boxWidth / 100,
    reference.boxHeight / 160,
  );
  const centerX = reference.centerX + overlay.panX * reference.width;
  const centerY = reference.centerY + overlay.panY * reference.height;
  elements.sam3dManualFitSilhouette.setAttribute(
    "transform",
    `translate(${centerX} ${centerY}) scale(${baseScale * overlay.scale}) translate(-50 -80)`,
  );
  elements.sam3dManualFitSilhouette.style.opacity =
    String(overlay.opacity);
  elements.sam3dManualOverlayScale.value =
    String(Math.round(overlay.scale * 100));
  elements.sam3dManualOverlayScaleValue.value =
    `${Math.round(overlay.scale * 100)}%`;
  elements.sam3dManualOverlayScaleValue.textContent =
    elements.sam3dManualOverlayScaleValue.value;
  elements.sam3dManualOverlayOpacity.value =
    String(Math.round(overlay.opacity * 100));
  elements.sam3dManualOverlayOpacityValue.value =
    `${Math.round(overlay.opacity * 100)}%`;
  elements.sam3dManualOverlayOpacityValue.textContent =
    elements.sam3dManualOverlayOpacityValue.value;
}

function offsetsForProjection(analysis) {
  return sam3dManualShapePreview(analysis).offsets.breast_size * 0.22;
}

function renderSam3dManualFit(analysis) {
  const analyzed = Boolean(analysis?.ready);
  elements.sam3dManualFit.hidden = !analyzed;
  if (!analyzed) return;
  app.sam3dManualShape = normalizeSam3dManualShape(app.sam3dManualShape);
  app.sam3dManualOverlay = normalizeSam3dManualOverlay(
    app.sam3dManualOverlay,
  );
  const manual = app.sam3dManualFitMode === "manual";
  const busy =
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    app.sam3dMutationInFlight ||
    snapshotBridgeBusy();
  elements.sam3dManualFit.classList.toggle("is-estimator", !manual);
  elements.sam3dManualFitEstimator.classList.toggle("active", !manual);
  elements.sam3dManualFitManual.classList.toggle("active", manual);
  elements.sam3dManualFitEstimator.setAttribute(
    "aria-pressed",
    String(!manual),
  );
  elements.sam3dManualFitManual.setAttribute(
    "aria-pressed",
    String(manual),
  );
  elements.sam3dManualFitEstimator.disabled = busy;
  elements.sam3dManualFitManual.disabled = busy;

  const candidates = sam3dManualReferenceCandidates();
  const selected = selectedSam3dManualReferenceCandidate();
  elements.sam3dManualReferenceSelect.replaceChildren(
    ...candidates.map((candidate) => {
      const token = sam3dBodyReferenceToken(candidate.reference);
      return new Option(
        `${candidate.job.sourceName} · ${sam3dBodyLabel(
          candidate.body,
          candidate.reference.personIndex,
        )}`,
        token,
      );
    }),
  );
  elements.sam3dManualReferenceSelect.value =
    app.sam3dManualReferenceToken;
  elements.sam3dManualReferenceSelect.disabled =
    busy || candidates.length < 2;
  elements.sam3dManualAutoAlign.disabled = busy || !selected;
  elements.sam3dManualOverlayReset.disabled = busy || !selected;
  elements.sam3dManualOverlayScale.disabled = busy || !selected;
  elements.sam3dManualOverlayOpacity.disabled = busy || !selected;

  const sourceUrl = selected
    ? sam3dArtifactUrl(selected.job, "source")
    : "";
  const geometry = selected
    ? sam3dManualReferenceGeometry(selected)
    : null;
  elements.sam3dManualFitEmpty.hidden = Boolean(sourceUrl);
  elements.sam3dManualFitSvg.hidden = !sourceUrl;
  elements.sam3dManualFitImage.hidden = !sourceUrl;
  if (sourceUrl && elements.sam3dManualFitImage.dataset.source !== sourceUrl) {
    elements.sam3dManualFitImage.dataset.source = sourceUrl;
    elements.sam3dManualFitImage.alt = "";
    elements.sam3dManualFitImage.onerror = () => {
      elements.sam3dManualFitImage.dataset.source = "";
      elements.sam3dManualFitEmpty.hidden = false;
      elements.sam3dManualFitSvg.hidden = true;
      elements.sam3dManualFitImage.hidden = true;
    };
    elements.sam3dManualFitImage.onload = () => {
      elements.sam3dManualFitEmpty.hidden = true;
      elements.sam3dManualFitSvg.hidden = false;
      elements.sam3dManualFitImage.hidden = false;
      renderSam3dManualFit(app.sam3dBodyProportions);
    };
    elements.sam3dManualFitImage.src = sourceUrl;
  }
  if (geometry) {
    elements.sam3dManualFitSvg.setAttribute(
      "viewBox",
      `0 0 ${geometry.width} ${geometry.height}`,
    );
  }

  for (const key of SAM3D_MANUAL_SHAPE_KEYS) {
    const control = sam3dManualShapeControl(key);
    const output = sam3dManualShapeOutput(key);
    const value = app.sam3dManualShape.offsets[key];
    control.value = String(Math.round(value * 100));
    control.disabled = busy || !manual;
    const label =
      Math.abs(value) <= 1e-6
        ? "Estimator"
        : `${value > 0 ? "+" : ""}${Math.round(value * 100)}%`;
    const feedback = sam3dManualShapeFeedback(analysis, key);
    const presented = feedback ? `${label} · ${feedback}` : label;
    output.value = presented;
    output.textContent = presented;
    output.title =
      feedback === "capped"
        ? "VaM's native range or the safe 0.25 step capped this correction."
        : feedback === "unavailable"
          ? "The exact verified built-in VaM morph is unavailable or disabled."
          : "";
  }
  elements.sam3dManualShapeReset.disabled =
    busy || !manual || !sam3dManualShapeHasCorrections(app.sam3dManualShape);
  elements.sam3dManualFitUpdate.disabled =
    busy ||
    !manual ||
    !app.sam3dBodyProportionsDirty ||
    elements.sam3dProportionsAnalyze.disabled;
  renderSam3dManualOverlay(analysis);
}

function normalizeSam3dBodyProfile(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const id = String(raw.id || "").trim().toLowerCase();
  if (!SAM3D_JOB_ID_PATTERN.test(id)) return null;
  const name = String(raw.name || "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
  if (!name) return null;
  const regions = SAM3D_BODY_PROPORTION_REGIONS.filter((region) =>
    asArray(raw.regions).includes(region),
  );
  const strength = Math.max(
    0,
    Math.min(100, Math.round(Number(raw.strength) || 0)),
  );
  const shapeRegions = SAM3D_BODY_SHAPE_REGIONS.filter((region) =>
    asArray(raw.shape_regions || raw.shapeRegions).includes(region),
  );
  const rawShapeStrength = Number(
    raw.shape_strength ?? raw.shapeStrength ?? 50,
  );
  const shapeStrength = Math.max(
    0,
    Math.min(
      100,
      Math.round(Number.isFinite(rawShapeStrength) ? rawShapeStrength : 50),
    ),
  );
  const referenceJobs = normalizeSam3dBodyReferences(
    raw.reference_jobs || raw.referenceJobs,
    raw.reference_job_id || raw.referenceJobId,
    raw.reference_person_index ?? raw.referencePersonIndex ?? 0,
  );
  const manualShape = normalizeSam3dManualShape(
    raw.manual_shape || raw.manualShape,
  );
  const rawManualMode = String(
    raw.manual_fit_mode || raw.manualFitMode || "",
  ).trim().toLowerCase();
  const manualFitMode =
    rawManualMode === "manual" ||
    (!rawManualMode && sam3dManualShapeHasCorrections(manualShape))
      ? "manual"
      : "estimator";
  const manualReference = normalizeSam3dBodyReference(
    raw.manual_reference || raw.manualReference,
  );
  const manualOverlay = normalizeSam3dManualOverlay(
    raw.manual_overlay || raw.manualOverlay,
  );
  return {
    id,
    name,
    regions: regions.length
      ? regions
      : [...SAM3D_BODY_PROPORTION_REGIONS],
    strength,
    // Missing Shape fields identify a v1/v2 profile. Keep Shape opt-in so
    // upgrading cannot silently alter breasts, waist, hips, glutes, or thighs.
    shapeRegions,
    shapeStrength,
    referenceJobs,
    manualFitMode,
    manualShape,
    manualReference,
    manualOverlay,
    updatedAt: Math.max(0, Number(raw.updated_at || raw.updatedAt) || 0),
  };
}

function loadSam3dBodyProfiles() {
  let parsed = [];
  let importedLegacyProfiles = false;
  try {
    let stored = window.localStorage.getItem(SAM3D_BODY_PROFILE_STORAGE_KEY);
    if (!stored) {
      stored = window.localStorage.getItem(
        SAM3D_BODY_PROFILE_V3_STORAGE_KEY,
      );
      if (!stored) {
        stored = window.localStorage.getItem(SAM3D_BODY_PROFILE_V2_STORAGE_KEY);
        if (!stored) {
          stored = window.localStorage.getItem(
            SAM3D_BODY_PROFILE_V1_STORAGE_KEY,
          );
        }
      }
      importedLegacyProfiles = Boolean(stored);
    }
    if (stored) {
      const document = JSON.parse(stored);
      parsed = Array.isArray(document)
        ? document
        : asArray(document?.profiles);
    }
  } catch (_error) {
    parsed = [];
  }
  const seen = new Set();
  app.sam3dBodyProfiles = parsed
    .map(normalizeSam3dBodyProfile)
    .filter((profile) => {
      if (!profile || seen.has(profile.id)) return false;
      seen.add(profile.id);
      return true;
    })
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, SAM3D_BODY_PROFILE_MAX_COUNT);
  if (importedLegacyProfiles && app.sam3dBodyProfiles.length) {
    persistSam3dBodyProfiles();
  }
}

function persistSam3dBodyProfiles() {
  const profiles = app.sam3dBodyProfiles
    .map(normalizeSam3dBodyProfile)
    .filter(Boolean)
    .slice(0, SAM3D_BODY_PROFILE_MAX_COUNT)
    .map((profile) => ({
      id: profile.id,
      name: profile.name,
      regions: profile.regions,
      strength: profile.strength,
      shape_regions: profile.shapeRegions,
      shape_strength: profile.shapeStrength,
      reference_jobs: profile.referenceJobs.map((reference) => ({
        job_id: reference.jobId,
        person_index: reference.personIndex,
      })),
      manual_fit_mode: profile.manualFitMode,
      manual_shape: profile.manualShape,
      manual_reference: profile.manualReference
        ? {
            job_id: profile.manualReference.jobId,
            person_index: profile.manualReference.personIndex,
          }
        : null,
      manual_overlay: {
        pan_x: profile.manualOverlay.panX,
        pan_y: profile.manualOverlay.panY,
        scale: profile.manualOverlay.scale,
        opacity: profile.manualOverlay.opacity,
      },
      updated_at: profile.updatedAt,
    }));
  app.sam3dBodyProfiles = profiles
    .map(normalizeSam3dBodyProfile)
    .filter(Boolean);
  try {
    window.localStorage.setItem(
      SAM3D_BODY_PROFILE_STORAGE_KEY,
      JSON.stringify({ schema: 4, profiles }),
    );
    return true;
  } catch (error) {
    toast(
      "Could not save local Person profile",
      errorMessage(error),
      "error",
    );
    return false;
  }
}

function selectedSam3dBodyProfile() {
  return (
    app.sam3dBodyProfiles.find(
      (profile) => profile.id === app.sam3dSelectedBodyProfileId,
    ) || null
  );
}

function currentSam3dBodyProfilePreferences() {
  const settings = sam3dBodyProportionSettings();
  return {
    regions: settings.regions,
    strength: settings.strength,
    shapeRegions: settings.shapeRegions,
    shapeStrength: settings.shapeStrength,
    referenceJobs: normalizeSam3dBodyReferences(settings.references),
    manualFitMode: app.sam3dManualFitMode,
    manualShape: normalizeSam3dManualShape(app.sam3dManualShape),
    manualReference: normalizeSam3dBodyReference(
      app.sam3dManualReferenceToken,
    ),
    manualOverlay: normalizeSam3dManualOverlay(app.sam3dManualOverlay),
  };
}

function renderSam3dBodyProfileActionState() {
  const profile = selectedSam3dBodyProfile();
  const locked =
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    Boolean(app.sam3dBodyProportions?.applied);
  elements.sam3dProfileSelect.disabled = locked;
  elements.sam3dProfileNew.disabled = locked;
  elements.sam3dProfileSave.disabled = locked || !profile;
  elements.sam3dProfileDelete.disabled = locked || !profile;
  const referenceCount = app.sam3dBodyReferences.length;
  if (profile) {
    elements.sam3dProfileNote.textContent =
      `“${profile.name}” is local to this browser. Save updates Structure, Body Shape, Manual Fit corrections and overlay, both strengths, and ${referenceCount} Morph reference${
        referenceCount === 1 ? "" : "s"
      }—never morph values or revisions.`;
  } else {
    elements.sam3dProfileNote.textContent =
      "Profiles stay in this browser and store Structure, Body Shape, Manual Fit, overlay, and up to eight Morph references—never live morph values or revisions.";
  }
}

function renderSam3dBodyProfiles() {
  const selectedId = selectedSam3dBodyProfile()?.id || "";
  elements.sam3dProfileSelect.replaceChildren(
    new Option("No profile · current controls", ""),
    ...app.sam3dBodyProfiles.map(
      (profile) => new Option(profile.name, profile.id),
    ),
  );
  elements.sam3dProfileSelect.value = selectedId;
  renderSam3dBodyReferenceGallery();
  renderSam3dBodyProfileActionState();
}

function selectSam3dBodyProfile() {
  const profileId = String(elements.sam3dProfileSelect.value || "");
  const profile =
    app.sam3dBodyProfiles.find((candidate) => candidate.id === profileId) ||
    null;
  app.sam3dSelectedBodyProfileId = profile?.id || "";
  if (!profile) {
    renderSam3dBodyProfiles();
    return;
  }
  for (const region of SAM3D_BODY_PROPORTION_REGIONS) {
    sam3dBodyProportionRegionControl(region).checked =
      profile.regions.includes(region);
  }
  for (const region of SAM3D_BODY_SHAPE_REGIONS) {
    sam3dBodyShapeRegionControl(region).checked =
      profile.shapeRegions.includes(region);
  }
  elements.sam3dFitStrength.value = String(profile.strength);
  elements.sam3dFitStrengthValue.value = `${profile.strength}%`;
  elements.sam3dShapeStrength.value = String(profile.shapeStrength);
  elements.sam3dShapeStrengthValue.value = `${profile.shapeStrength}%`;
  app.sam3dManualFitMode = profile.manualFitMode;
  app.sam3dManualShape = normalizeSam3dManualShape(profile.manualShape);
  app.sam3dManualReferenceToken = profile.manualReference
    ? sam3dBodyReferenceToken(profile.manualReference)
    : "";
  app.sam3dManualOverlay = normalizeSam3dManualOverlay(
    profile.manualOverlay,
  );
  setSam3dBodyReferences(profile.referenceJobs);
  markSam3dBodyProportionsDirty();
  renderSam3dBodyProfiles();
}

async function createSam3dBodyProfile() {
  if (app.sam3dBodyProfiles.length >= SAM3D_BODY_PROFILE_MAX_COUNT) {
    toast(
      "Person profile limit reached",
      `Delete a profile before creating more than ${SAM3D_BODY_PROFILE_MAX_COUNT}.`,
      "error",
    );
    return;
  }
  const name = await showDialog({
    eyebrow: "New local Person profile",
    title: "Name these fitting preferences",
    message:
      "This profile stores the selected Structure, Body Shape, Manual Fit corrections, and local overlay controls in this browser. It never stores VaM morph values, morph identifiers, or revision tokens.",
    confirmLabel: "Create profile",
    input: {
      label: "Profile name",
      value: "",
      placeholder: "Tall athletic",
    },
  });
  if (!name) return;
  const safeName = String(name)
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
  if (!safeName) return;
  const preferences = currentSam3dBodyProfilePreferences();
  const profile = normalizeSam3dBodyProfile({
    id: newSam3dComparisonId(),
    name: safeName,
    ...preferences,
    updatedAt: Date.now(),
  });
  if (!profile) return;
  app.sam3dBodyProfiles.unshift(profile);
  app.sam3dSelectedBodyProfileId = profile.id;
  if (persistSam3dBodyProfiles()) {
    toast("Person profile created", `${profile.name} was saved locally.`);
  }
  renderSam3dBodyProfiles();
}

function saveSam3dBodyProfile() {
  const profile = selectedSam3dBodyProfile();
  if (!profile) return;
  const preferences = currentSam3dBodyProfilePreferences();
  const updated = normalizeSam3dBodyProfile({
    ...profile,
    ...preferences,
    updatedAt: Date.now(),
  });
  if (!updated) return;
  const index = app.sam3dBodyProfiles.findIndex(
    (candidate) => candidate.id === profile.id,
  );
  if (index >= 0) app.sam3dBodyProfiles.splice(index, 1, updated);
  if (persistSam3dBodyProfiles()) {
    toast("Person profile updated", `${updated.name} was saved locally.`);
  }
  renderSam3dBodyProfiles();
}

async function deleteSam3dBodyProfile() {
  const profile = selectedSam3dBodyProfile();
  if (!profile) return;
  const confirmed = await showDialog({
    eyebrow: "Delete local Person profile",
    title: `Delete “${profile.name}”?`,
    message:
      "Only the local fitting preferences will be removed. VaM and reconstruction jobs are unchanged.",
    confirmLabel: "Delete profile",
    icon: "warning",
  });
  if (!confirmed) return;
  app.sam3dBodyProfiles = app.sam3dBodyProfiles.filter(
    (candidate) => candidate.id !== profile.id,
  );
  app.sam3dSelectedBodyProfileId = "";
  persistSam3dBodyProfiles();
  renderSam3dBodyProfiles();
  toast("Person profile deleted", `${profile.name} was removed locally.`);
}

function setSam3dHandoffTab(tab) {
  if (!["morph", "pose"].includes(tab)) return;
  if (tab === "morph" && !app.sam3dJobs.some(sam3dJobSucceeded)) return;
  if (
    tab === "pose" &&
    !(
      app.sam3dSelectedJob &&
      sam3dJobSucceeded(app.sam3dSelectedJob)
    )
  ) {
    return;
  }
  app.sam3dHandoffTab = tab;
  renderSam3dHandoff();
  if (tab === "morph") renderSam3dBodyProportions();
  if (tab === "pose") renderSam3dApplyState();
}

function renderSam3dHandoff() {
  const morphAvailable = app.sam3dJobs.some(sam3dJobSucceeded);
  const poseAvailable = Boolean(
    app.sam3dSelectedJob && sam3dJobSucceeded(app.sam3dSelectedJob),
  );
  const visible = morphAvailable || poseAvailable;
  elements.sam3dHandoff.hidden = !visible;
  if (!visible) return;
  if (app.sam3dHandoffTab === "pose" && !poseAvailable) {
    app.sam3dHandoffTab = "morph";
  }
  const morphActive = app.sam3dHandoffTab === "morph";
  elements.sam3dHandoffMorphTab.disabled = !morphAvailable;
  elements.sam3dHandoffPoseTab.disabled = !poseAvailable;
  elements.sam3dHandoffMorphTab.classList.toggle("active", morphActive);
  elements.sam3dHandoffMorphTab.setAttribute(
    "aria-selected",
    String(morphActive),
  );
  elements.sam3dHandoffPoseTab.classList.toggle("active", !morphActive);
  elements.sam3dHandoffPoseTab.setAttribute(
    "aria-selected",
    String(!morphActive),
  );
  elements.sam3dProportionsPanel.hidden = !morphActive;
  elements.sam3dApplyPanel.hidden = morphActive;
}

function sam3dBodyProportionRegionControl(region) {
  const controls = {
    arms: elements.sam3dRegionArms,
    legs: elements.sam3dRegionLegs,
    torso: elements.sam3dRegionTorso,
    widths: elements.sam3dRegionWidths,
  };
  return controls[region] || null;
}

function sam3dBodyShapeRegionControl(region) {
  const controls = {
    breasts: elements.sam3dShapeRegionBreasts,
    waist: elements.sam3dShapeRegionWaist,
    hips: elements.sam3dShapeRegionHips,
    glutes: elements.sam3dShapeRegionGlutes,
    thighs: elements.sam3dShapeRegionThighs,
  };
  return controls[region] || null;
}

function resetSam3dBodyProportions(jobId = "") {
  stopSam3dBodyProportionPolling();
  app.sam3dBodyProportions = null;
  app.sam3dBodyProportionsError = null;
  app.sam3dBodyProportionsInFlight = false;
  app.sam3dBodyProportionsJobId = String(jobId || "");
  app.sam3dBodyProportionsDirty = false;
  app.sam3dBodyProportionPollAttempts = 0;
  app.sam3dBodyProportionsPendingAction = "";
}

function sam3dBodyProportionSettings() {
  initializeSam3dBodyReferences();
  const regions = SAM3D_BODY_PROPORTION_REGIONS.filter(
    (region) => sam3dBodyProportionRegionControl(region)?.checked,
  );
  const strength = Math.max(
    0,
    Math.min(100, Math.round(Number(elements.sam3dFitStrength.value) || 0)),
  );
  const shapeRegions = SAM3D_BODY_SHAPE_REGIONS.filter(
    (region) => sam3dBodyShapeRegionControl(region)?.checked,
  );
  const shapeStrength = Math.max(
    0,
    Math.min(
      100,
      Math.round(Number(elements.sam3dShapeStrength.value) || 0),
    ),
  );
  const references = normalizeSam3dBodyReferences(
    app.sam3dBodyReferences,
  );
  const primaryReference = references[0] || null;
  const manualShape = effectiveSam3dManualShape();
  return {
    targetUid: String(elements.sam3dPersonTarget.value || "").trim(),
    personIndex: primaryReference?.personIndex || 0,
    referenceJobId: primaryReference?.jobId || "",
    references,
    regions,
    strength,
    shapeRegions,
    shapeStrength,
    manualShape,
  };
}

function sam3dBodyProportionJob(settings = sam3dBodyProportionSettings()) {
  const job = app.sam3dJobs.find(
    (candidate) =>
      candidate.id === settings.referenceJobId &&
      sam3dJobSucceeded(candidate),
  );
  if (job) return job;
  if (
    app.sam3dSelectedJob?.id === settings.referenceJobId &&
    sam3dJobSucceeded(app.sam3dSelectedJob)
  ) {
    return app.sam3dSelectedJob;
  }
  return null;
}

function sam3dBodyShapeCalibrationState(
  settings = sam3dBodyProportionSettings(),
) {
  const shapeRequested =
    settings.shapeRegions.length > 0 ||
    sam3dManualShapeHasCorrections(settings.manualShape);
  const target = personList().find(
    (person) => person.uid === settings.targetUid,
  );
  const status =
    target?.bodyProportions && typeof target.bodyProportions === "object"
      ? target.bodyProportions
      : target?.body_proportions &&
          typeof target.body_proportions === "object"
        ? target.body_proportions
        : null;
  const ready =
    status?.bodyShapeReady ?? status?.body_shape_ready;
  const preparing =
    status?.bodyShapePreparing ?? status?.body_shape_preparing;
  const calibrationPreparing =
    ready === false &&
    preparing === true;
  return {
    requested: shapeRequested,
    ready: ready === true,
    preparing: calibrationPreparing,
    analyzeBlocked: shapeRequested && calibrationPreparing,
    applyBlocked: ready !== true,
    reason: String(
      status?.bodyShapeReason ?? status?.body_shape_reason ?? "",
    ).trim(),
  };
}

function sam3dBodyReferencesReady(references) {
  const normalized = normalizeSam3dBodyReferences(references);
  return (
    normalized.length > 0 &&
    normalized.every(sam3dBodyReferenceAvailable)
  );
}

function sam3dBodyProportionRequest(
  job,
  {
    analysisRevision = "",
  } = {},
) {
  const settings = sam3dBodyProportionSettings();
  const request = {
    expected_job_revision: job.revision,
    target_uid: settings.targetUid,
    person_index: settings.personIndex,
    references: serializeSam3dBodyReferences(settings.references),
    regions: settings.regions,
    fit_strength: settings.strength / 100,
    shape_regions: settings.shapeRegions,
    shape_strength: settings.shapeStrength / 100,
  };
  if (sam3dManualShapeHasCorrections(settings.manualShape)) {
    request.manual_shape = normalizeSam3dManualShape(
      settings.manualShape,
    );
  }
  if (analysisRevision) {
    request.expected_analysis_revision = analysisRevision;
  }
  return request;
}

function sam3dBodyProportionUndoRequest(targetUid, applyRevision) {
  return {
    target_uid: String(targetUid || "").trim(),
    expected_apply_revision: applyRevision,
  };
}

function sam3dBodyProportionRevision(value) {
  const revision = String(value || "").trim();
  return SAM3D_JOB_ID_PATTERN.test(revision) ? revision : "";
}

function sam3dBodyProportionPercent(value, { ratio = false } = {}) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return ratio ? number * 100 : number;
}

function sam3dBodyProportionMetricPercent(
  raw,
  percentKeys,
  ratioKeys,
  fallbackKeys = [],
) {
  for (const key of percentKeys) {
    if (raw?.[key] !== undefined) {
      return sam3dBodyProportionPercent(raw[key]);
    }
  }
  for (const key of ratioKeys) {
    if (raw?.[key] !== undefined) {
      return sam3dBodyProportionPercent(raw[key], { ratio: true });
    }
  }
  for (const key of fallbackKeys) {
    const value = Number(raw?.[key]);
    if (!Number.isFinite(value)) continue;
    return Math.abs(value) <= 4 ? value * 100 : value;
  }
  return null;
}

function sam3dBodyProportionConfidence(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Math.max(0, Math.min(100, number <= 1 ? number * 100 : number));
}

function normalizeSam3dBodyMeasurement(
  raw,
  fallbackId = "",
  allowedRegions = SAM3D_BODY_PROPORTION_REGIONS,
) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const id = String(
    raw.id || raw.key || raw.measurement || fallbackId,
  ).trim();
  const region = String(raw.region || "").trim().toLowerCase();
  const current = sam3dBodyProportionMetricPercent(
    raw,
    [
      "current_percent",
      "currentPercent",
      "current_pct",
      "vam_percent",
      "vamPercent",
      "vam_pct",
    ],
    ["current_ratio", "currentRatio", "vam_ratio", "vamRatio"],
    ["current", "vam"],
  );
  const target = sam3dBodyProportionMetricPercent(
    raw,
    [
      "target_percent",
      "targetPercent",
      "target_pct",
      "image_percent",
      "imagePercent",
      "image_pct",
    ],
    ["target_ratio", "targetRatio", "image_ratio", "imageRatio"],
    ["target", "image"],
  );
  let delta = sam3dBodyProportionMetricPercent(
    raw,
    ["delta_percent", "deltaPercent", "delta_pct"],
    ["delta_ratio", "deltaRatio"],
    ["delta"],
  );
  if (delta === null && current !== null && target !== null) {
    delta = target - current;
  }
  if (current === null && target === null) return null;
  return {
    id: id || `measurement-${fallbackId}`,
    label: String(
      raw.label || raw.name || id || "Body proportion",
    ).trim(),
    region: allowedRegions.includes(region) ? region : "",
    current,
    target,
    delta,
    confidence: sam3dBodyProportionConfidence(
      raw.confidence ?? raw.score,
    ),
    disagreement: sam3dBodyProportionConfidence(
      raw.reference_disagreement ??
        raw.referenceDisagreement ??
        raw.model_disagreement ??
        raw.model_disagreement_percent ??
        raw.disagreement,
    ),
  };
}

function normalizeSam3dMorphChange(raw, fallbackId = "") {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const id = String(raw.id || raw.key || raw.uid || fallbackId).trim();
  const region = String(raw.region || "").trim().toLowerCase();
  const current = Number(
    raw.current_value ?? raw.current ?? raw.from ?? 0,
  );
  let target = Number(
    raw.proposed_value ?? raw.target_value ?? raw.target ?? raw.value,
  );
  let delta = Number(raw.delta ?? raw.change);
  if (!Number.isFinite(target) && Number.isFinite(delta)) {
    target = current + delta;
  }
  if (!Number.isFinite(delta) && Number.isFinite(target)) {
    delta = target - current;
  }
  if (!Number.isFinite(target) && !Number.isFinite(delta)) return null;
  const declaredFitKind = String(
    raw.fit_kind || raw.fitKind || "",
  ).trim().toLowerCase();
  const fitKind =
    declaredFitKind === "shape" || SAM3D_BODY_SHAPE_REGIONS.includes(region)
      ? "shape"
      : "structure";
  const supportedRegions = [
    ...SAM3D_BODY_PROPORTION_REGIONS,
    ...SAM3D_BODY_SHAPE_REGIONS,
  ];
  return {
    id: id || `morph-${fallbackId}`,
    label: String(
      raw.display_name || raw.displayName || raw.label || raw.name || id,
    ).trim() || "VaM morph",
    region: supportedRegions.includes(region) ? region : "",
    fitKind,
    current: Number.isFinite(current) ? current : 0,
    target: Number.isFinite(target) ? target : null,
    delta: Number.isFinite(delta) ? delta : null,
    min: Number.isFinite(Number(raw.min)) ? Number(raw.min) : null,
    max: Number.isFinite(Number(raw.max)) ? Number(raw.max) : null,
    unit: String(raw.unit || "").trim(),
    available: raw.available !== false,
    reason: String(raw.reason || raw.message || "").trim(),
  };
}

function sam3dBodyProportionArray(raw) {
  if (Array.isArray(raw)) {
    return raw.map((value, index) => [String(index), value]);
  }
  if (raw && typeof raw === "object") return Object.entries(raw);
  return [];
}

function normalizeSam3dBodyProportions(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return {
      available: false,
      message: "The manager returned an invalid body-proportion response.",
      measurements: [],
      morphs: [],
      shapeMeasurements: [],
      shapeMorphs: [],
      shapeUnavailable: [],
    };
  }
  const nested =
    (payload.body_proportions &&
      typeof payload.body_proportions === "object" &&
      payload.body_proportions) ||
    (payload.analysis &&
      typeof payload.analysis === "object" &&
      payload.analysis) ||
    (payload.result &&
      typeof payload.result === "object" &&
      payload.result) ||
    {};
  const document = { ...payload, ...nested };
  const measurements = sam3dBodyProportionArray(
    document.measurements || document.proportions || document.metrics,
  )
    .map(([id, value]) => normalizeSam3dBodyMeasurement(value, id))
    .filter(Boolean);
  const shapeMeasurements = sam3dBodyProportionArray(
    document.shape_measurements || document.shapeMeasurements,
  )
    .map(([id, value]) =>
      normalizeSam3dBodyMeasurement(
        value,
        id,
        SAM3D_BODY_SHAPE_REGIONS,
      ),
    )
    .filter(Boolean);
  const combinedMorphs = sam3dBodyProportionArray(
    document.proposed_morphs ||
      document.morph_changes ||
      document.morphs ||
      document.changes,
  )
    .map(([id, value]) => normalizeSam3dMorphChange(value, id))
    .filter(Boolean)
    .slice(0, 32);
  const explicitShapeMorphs = sam3dBodyProportionArray(
    document.shape_changes || document.shapeChanges,
  )
    .map(([id, value]) =>
      normalizeSam3dMorphChange(
        {
          ...(value && typeof value === "object" && !Array.isArray(value)
            ? value
            : {}),
          fit_kind: "shape",
          fitKind: "shape",
        },
        id,
      ),
    )
    .filter(Boolean)
    .slice(0, 32);
  const morphs = combinedMorphs.filter(
    (morph) => morph.fitKind !== "shape",
  );
  const shapeMorphs = explicitShapeMorphs.length
    ? explicitShapeMorphs
    : combinedMorphs.filter((morph) => morph.fitKind === "shape");
  const normalizeUnavailable = (raw) => asArray(raw)
    .filter(
      (item) =>
        item && typeof item === "object" && !Array.isArray(item),
    )
    .map((item) => {
      const control = String(item.control || "").trim();
      return {
        region: String(item.region || "body").trim().toLowerCase(),
        control: SAM3D_MANUAL_SHAPE_KEYS.includes(control)
          ? control
          : "",
        reason: String(
          item.reason || item.message || "No safe morph is available.",
        ).trim(),
      };
    });
  const manualShapeChanges = asArray(
    document.manual_shape_changes || document.manualShapeChanges,
  )
    .filter(
      (item) =>
        item && typeof item === "object" && !Array.isArray(item),
    )
    .map((item) => {
      const control = String(item.control || "").trim();
      const semanticOffset = Number(
        item.semanticOffset ?? item.semantic_offset,
      );
      const requestedOffset = Number(
        item.requestedOffset ?? item.requested_offset,
      );
      const appliedOffset = Number(
        item.appliedOffset ?? item.applied_offset,
      );
      if (
        !SAM3D_MANUAL_SHAPE_KEYS.includes(control) ||
        !Number.isFinite(semanticOffset) ||
        !Number.isFinite(requestedOffset) ||
        !Number.isFinite(appliedOffset)
      ) {
        return null;
      }
      return {
        control,
        semanticOffset,
        requestedOffset,
        appliedOffset,
        limited: item.limited === true,
      };
    })
    .filter(Boolean)
    .slice(0, SAM3D_MANUAL_SHAPE_KEYS.length);
  const combinedUnavailable = normalizeUnavailable(document.unavailable);
  const explicitShapeUnavailable = normalizeUnavailable(
    document.shape_unavailable || document.shapeUnavailable,
  );
  const unavailableRegions = combinedUnavailable
    .filter((item) => !SAM3D_BODY_SHAPE_REGIONS.includes(item.region))
    .slice(0, 8);
  const allShapeUnavailable = (
    explicitShapeUnavailable.length
      ? explicitShapeUnavailable
      : combinedUnavailable.filter((item) =>
        SAM3D_BODY_SHAPE_REGIONS.includes(item.region))
  );
  const manualShapeUnavailable = allShapeUnavailable
    .filter((item) => item.control)
    .slice(0, SAM3D_MANUAL_SHAPE_KEYS.length);
  const shapeUnavailable = allShapeUnavailable.slice(0, 8);
  const analysisRevision = sam3dBodyProportionRevision(
    document.analysis_revision ||
      document.analysisRevision ||
      document.body_revision ||
      document.bodyRevision ||
      document.revision,
  );
  const applyRevision = sam3dBodyProportionRevision(
    document.apply_revision ||
      document.applyRevision ||
      document.applied_revision ||
      document.appliedRevision ||
      document.undo_revision ||
      document.undoRevision,
  );
  const state = String(
    document.state || document.status || "",
  ).trim().toLowerCase();
  const references = normalizeSam3dBodyReferences(
    document.reference_jobs ||
      document.referenceJobs ||
      document.references,
    document.reference_job_id || document.referenceJobId,
    document.person_index ?? document.personIndex ?? 0,
  );
  const unavailable =
    document.available === false ||
    ["unavailable", "unsupported", "disabled"].includes(state);
  return {
    raw: payload,
    available: !unavailable,
    ready: Boolean(
      document.ready ??
        document.analyzed ??
        Boolean(
          analysisRevision ||
          measurements.length ||
          morphs.length ||
          shapeMeasurements.length ||
          shapeMorphs.length,
        ),
    ),
    state,
    message: String(
      document.message ||
        document.detail ||
        document.reason ||
        document.apply_blocked_reason ||
        document.applyBlockedReason ||
        document.warning ||
        "",
    ).trim(),
    blockedReason: String(
      document.apply_blocked_reason ||
        document.applyBlockedReason ||
        "",
    ).trim(),
    targetUid: String(
      document.target_uid || document.targetUid || "",
    ).trim(),
    references,
    personIndex: Math.max(
      0,
      integerValue(document.person_index ?? document.personIndex) || 0,
    ),
    analysisRevision,
    applyRevision,
    confidence: sam3dBodyProportionConfidence(
      document.confidence ??
        document.analysis_confidence ??
        document.analysisConfidence ??
        document.target?.overallConfidence,
    ),
    disagreement: sam3dBodyProportionConfidence(
      document.reference_disagreement ??
        document.referenceDisagreement ??
        document.model_disagreement ??
        document.model_disagreement_percent ??
        document.disagreement,
    ),
    referenceConsensus:
      document.reference_consensus &&
      typeof document.reference_consensus === "object" &&
      !Array.isArray(document.reference_consensus)
        ? document.reference_consensus
        : null,
    measurements,
    morphs,
    allMorphs: combinedMorphs.length
      ? combinedMorphs
      : [...morphs, ...shapeMorphs],
    shapeMeasurements,
    shapeMorphs,
    shapeUnavailable,
    manualShapeUnavailable,
    manualShape: normalizeSam3dManualShape(
      document.manual_shape || document.manualShape,
    ),
    manualShapeChanges,
    shapeConfidence: sam3dBodyProportionConfidence(
      document.shape_confidence ??
        document.shapeConfidence ??
        document.shape_target?.overallConfidence ??
        document.shapeTarget?.overallConfidence,
    ),
    unavailable: unavailableRegions,
    canApply: Boolean(
      document.can_apply ??
        document.canApply ??
        (
          analysisRevision &&
          [...morphs, ...shapeMorphs].some((morph) => morph.available)
        ),
    ),
    canUndo: Boolean(
      document.can_undo ??
        document.canUndo ??
        document.undo_available ??
        document.undoAvailable ??
        applyRevision,
    ),
    applied: Boolean(document.applied ?? applyRevision),
    bodyShapeReady: Boolean(
      document.body_shape_ready ?? document.bodyShapeReady,
    ),
    bodyShapePreparing: Boolean(
      document.body_shape_preparing ?? document.bodyShapePreparing,
    ),
    poseApplied: Boolean(
      document.pose_applied ?? document.poseApplied ?? false,
    ),
  };
}

async function loadSam3dBodyProportions(
  jobId,
  { quiet = false } = {},
) {
  let normalizedId;
  try {
    normalizedId = sam3dJobId(jobId);
  } catch (error) {
    if (!quiet) {
      toast("Could not load body proportions", errorMessage(error), "error");
    }
    return null;
  }
  if (app.sam3dBodyProportionsInFlight) return null;
  const settings = sam3dBodyProportionSettings();
  const job = sam3dBodyProportionJob(settings);
  const referenceSignature = serializeSam3dBodyReferences(
    settings.references,
  );
  const manualShapeSignature = serializeSam3dManualShape(
    settings.manualShape,
  );
  const requestStillCurrent = () => {
    const current = sam3dBodyProportionSettings();
    return (
      current.referenceJobId === normalizedId &&
      serializeSam3dBodyReferences(current.references) ===
        referenceSignature &&
      serializeSam3dManualShape(current.manualShape) ===
        manualShapeSignature
    );
  };
  if (
    settings.referenceJobId !== normalizedId ||
    !sam3dBodyReferencesReady(settings.references) ||
    sam3dBodyReferenceSetIssue(settings.references, settings.regions)
  ) {
    return null;
  }
  const targetUid = settings.targetUid;
  if (!targetUid) {
    app.sam3dBodyProportions = null;
    app.sam3dBodyProportionsError = null;
    app.sam3dBodyProportionsJobId = normalizedId;
    renderSam3dBodyProportions();
    return null;
  }
  app.sam3dBodyProportionsInFlight = true;
  app.sam3dBodyProportionsError = null;
  app.sam3dBodyProportionsJobId = normalizedId;
  renderSam3dBodyProportions();
  try {
    const reviewedAnalysis = app.sam3dBodyProportions;
    const reviewedManualMatches =
      reviewedAnalysis?.ready &&
      reviewedAnalysis.targetUid === targetUid &&
      serializeSam3dBodyReferences(reviewedAnalysis.references) ===
        referenceSignature &&
      serializeSam3dManualShape(reviewedAnalysis.manualShape) ===
        manualShapeSignature;
    const retainAppliedReview =
      !app.sam3dBodyProportionsDirty &&
      reviewedManualMatches &&
      Boolean(
        reviewedAnalysis.applied ||
        reviewedAnalysis.canUndo ||
        reviewedAnalysis.applyRevision,
      );
    // GET cannot reproduce request-specific manual corrections. Recompute
    // them through read-only Analyze unless Apply/Undo is already pending.
    // Polling and applied-state refreshes merge only live status into the
    // reviewed proposal; only explicit Analyze may replace an applied review.
    const refreshManualProposal =
      sam3dManualShapeHasCorrections(settings.manualShape) &&
      Boolean(job) &&
      !app.sam3dBodyProportionsPendingAction &&
      !retainAppliedReview;
    const payload = refreshManualProposal
      ? await Sam3dClient.bodyProportionsAction(
          normalizedId,
          SAM3D_BODY_PROPORTION_ACTIONS.analyze,
          sam3dBodyProportionRequest(job),
        )
      : await Sam3dClient.bodyProportions(
          normalizedId,
          {
            targetUid,
            personIndex: settings.personIndex,
            strength: settings.strength,
            regions: settings.regions,
            shapeStrength: settings.shapeStrength,
            shapeRegions: settings.shapeRegions,
            references: settings.references,
          },
        );
    if (!requestStillCurrent()) return null;
    const loadedAnalysis = normalizeSam3dBodyProportions(payload);
    const preserveReviewedManual =
      (
        Boolean(app.sam3dBodyProportionsPendingAction) ||
        retainAppliedReview
      ) &&
      sam3dManualShapeHasCorrections(settings.manualShape) &&
      reviewedManualMatches;
    app.sam3dBodyProportions = preserveReviewedManual
      ? {
          ...reviewedAnalysis,
          raw: loadedAnalysis.raw,
          available: loadedAnalysis.available,
          state: loadedAnalysis.state,
          message: loadedAnalysis.message,
          blockedReason: loadedAnalysis.blockedReason,
          applyRevision: loadedAnalysis.applyRevision,
          canApply: loadedAnalysis.canApply,
          canUndo: loadedAnalysis.canUndo,
          applied: loadedAnalysis.applied,
          bodyShapeReady: loadedAnalysis.bodyShapeReady,
          bodyShapePreparing: loadedAnalysis.bodyShapePreparing,
          poseApplied: loadedAnalysis.poseApplied,
        }
      : loadedAnalysis;
    app.sam3dBodyProportions.references = settings.references;
    app.sam3dBodyProportions.personIndex = settings.personIndex;
    app.sam3dBodyProportionsDirty = false;
    return app.sam3dBodyProportions;
  } catch (error) {
    if (!requestStillCurrent()) return null;
    if (error.status === 404 || error.status === 501) {
      app.sam3dBodyProportions = {
        available: false,
        ready: false,
        message:
          "Body-proportion fitting is not available in this manager build.",
        measurements: [],
        morphs: [],
        shapeMeasurements: [],
        shapeMorphs: [],
        shapeUnavailable: [],
        canApply: false,
        canUndo: false,
      };
    } else {
      app.sam3dBodyProportionsError = error;
      if (!quiet) {
        toast("Could not load body proportions", errorMessage(error), "error");
      }
    }
    return null;
  } finally {
    app.sam3dBodyProportionsInFlight = false;
    renderSam3dBodyProportions();
  }
}

function startSam3dBodyProportionPolling() {
  if (
    app.managerAuthFailed ||
    app.sam3dBodyProportionPollTimer !== null ||
    !app.sam3dBodyProportionsPendingAction ||
    app.view !== "sam3d"
  ) {
    return;
  }
  app.sam3dBodyProportionPollTimer = window.setTimeout(
    pollSam3dBodyProportions,
    SAM3D_POLL_MS,
  );
}

function stopSam3dBodyProportionPolling() {
  if (app.sam3dBodyProportionPollTimer !== null) {
    window.clearTimeout(app.sam3dBodyProportionPollTimer);
    app.sam3dBodyProportionPollTimer = null;
  }
}

async function pollSam3dBodyProportions() {
  app.sam3dBodyProportionPollTimer = null;
  if (app.managerAuthFailed) return;
  const action = app.sam3dBodyProportionsPendingAction;
  const jobId = sam3dBodyProportionJob()?.id || "";
  if (!action || !jobId || app.view !== "sam3d") return;
  app.sam3dBodyProportionPollAttempts += 1;
  const settings = sam3dBodyProportionSettings();
  const bodyShapeReviewRequested =
    action === SAM3D_BODY_PROPORTION_ACTIONS.undo &&
    (
      settings.shapeRegions.length > 0 ||
      sam3dManualShapeHasCorrections(settings.manualShape)
    );
  let liveBodyStatus = null;
  try {
    const snapshot = await fetchLiveSceneSnapshot();
    const target = asArray(snapshot?.persons).find(
      (person) =>
        person &&
        typeof person === "object" &&
        String(person.uid || "").trim() === settings.targetUid,
    );
    const rawStatus =
      target?.bodyProportions &&
      typeof target.bodyProportions === "object"
        ? target.bodyProportions
        : target?.body_proportions &&
            typeof target.body_proportions === "object"
          ? target.body_proportions
          : null;
    if (rawStatus) {
      liveBodyStatus = {
        undoPending: Boolean(
          rawStatus.undoPending ?? rawStatus.undo_pending,
        ),
        bodyShapePreparing: Boolean(
          rawStatus.bodyShapePreparing ??
            rawStatus.body_shape_preparing,
        ),
      };
    }
  } catch {
    // The full reconciliation request below owns connection/error reporting.
  }
  const waitingForLiveSettlement =
    Boolean(liveBodyStatus?.undoPending) ||
    Boolean(liveBodyStatus?.bodyShapePreparing);
  if (waitingForLiveSettlement) {
    const appliedAndPreparingUndo =
      action === SAM3D_BODY_PROPORTION_ACTIONS.apply &&
      Boolean(liveBodyStatus?.undoPending);
    app.sam3dBodyProportionsError = null;
    app.sam3dBodyProportions = {
      ...app.sam3dBodyProportions,
      state: appliedAndPreparingUndo ? "settling" : "reconciling",
      message:
        appliedAndPreparingUndo
          ? "VaM changed the morph values and is rebuilding neutral body-shape measurements before publishing the exact undo revision."
          : action === SAM3D_BODY_PROPORTION_ACTIONS.undo
            ? "VaM restored the morph values and is rebuilding neutral body-shape measurements."
            : "VaM is rebuilding neutral body-shape measurements before confirming whether any morph values changed.",
    };
    if (
      app.sam3dBodyProportionPollAttempts >=
      SAM3D_BODY_PROPORTION_POLL_ATTEMPTS
    ) {
      app.sam3dBodyProportionsPendingAction = "";
      app.sam3dBodyProportionsError = new Error(
        "VaM did not finish rebuilding the body-shape measurements before the five-minute timeout.",
      );
      renderSam3dBodyProportions();
      return;
    }
    renderSam3dBodyProportions();
    startSam3dBodyProportionPolling();
    return;
  }
  const analysis = await loadSam3dBodyProportions(jobId, { quiet: true });
  if (
    action !== app.sam3dBodyProportionsPendingAction ||
    jobId !== sam3dBodyProportionJob()?.id
  ) {
    return;
  }
  const failed = ["error", "failed", "stale"].includes(
    String(analysis?.state || "").toLowerCase(),
  );
  const succeeded = [
    "ok",
    "success",
    "succeeded",
    "complete",
    "completed",
  ].includes(String(analysis?.state || "").toLowerCase());
  const restoredBodyShapeReady =
    !bodyShapeReviewRequested || Boolean(analysis?.bodyShapeReady);
  const complete =
    action === SAM3D_BODY_PROPORTION_ACTIONS.apply
      ? Boolean(analysis?.canUndo && analysis?.applyRevision)
      : Boolean(
          analysis?.ready &&
          !analysis?.canUndo &&
          restoredBodyShapeReady,
        );
  const unchanged =
    action === SAM3D_BODY_PROPORTION_ACTIONS.apply &&
    succeeded &&
    Boolean(analysis?.ready) &&
    !analysis?.applied &&
    !analysis?.canUndo &&
    !analysis?.applyRevision;
  if (!analysis && app.sam3dBodyProportionsError) {
    app.sam3dBodyProportionsPendingAction = "";
    app.sam3dBodyProportionPollAttempts = 0;
    renderSam3dBodyProportions();
    return;
  }
  if (failed) {
    app.sam3dBodyProportionsPendingAction = "";
    app.sam3dBodyProportionsError = new Error(
      analysis?.message ||
        `VaM could not complete the body-proportion ${action}.`,
    );
    renderSam3dBodyProportions();
    return;
  }
  if (unchanged) {
    app.sam3dBodyProportionsPendingAction = "";
    app.sam3dBodyProportionPollAttempts = 0;
    app.sam3dBodyProportions = {
      ...analysis,
      state: "unchanged",
      message:
        "VaM completed the request, but every requested morph was already at its proposed value. Analyze again before retrying.",
      canApply: false,
      canUndo: false,
      applied: false,
    };
    toast(
      "Body fit unchanged",
      "No morph values changed, so VaM did not create an undo revision.",
    );
    renderSam3dBodyProportions();
    return;
  }
  if (complete) {
    app.sam3dBodyProportionsPendingAction = "";
    app.sam3dBodyProportionPollAttempts = 0;
    if (action === SAM3D_BODY_PROPORTION_ACTIONS.apply) {
      toast(
        "Body fit applied",
        "VaM confirmed the exact Structure and Body Shape revision. Apply pose + camera below to refit the controllers.",
      );
    } else {
      if (
        sam3dManualShapeHasCorrections(
          sam3dBodyProportionSettings().manualShape,
        )
      ) {
        await loadSam3dBodyProportions(jobId, { quiet: true });
      }
      toast(
        "Body fit restored",
        "VaM confirmed that the previous morph values were restored.",
      );
    }
    renderSam3dBodyProportions();
    return;
  }
  if (
    app.sam3dBodyProportionPollAttempts >=
    SAM3D_BODY_PROPORTION_POLL_ATTEMPTS
  ) {
    app.sam3dBodyProportionsPendingAction = "";
    app.sam3dBodyProportionsError = new Error(
      "VaM did not confirm the body-proportion change before the five-minute timeout.",
    );
    renderSam3dBodyProportions();
    return;
  }
  startSam3dBodyProportionPolling();
}

function markSam3dBodyProportionsDirty() {
  if (app.sam3dBodyProportions?.ready) {
    app.sam3dBodyProportionsDirty = true;
  }
  renderSam3dBodyProportions();
}

function formatSam3dBodyPercent(value, { signed = false } = {}) {
  if (!Number.isFinite(value)) return "—";
  const rounded =
    Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1);
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${rounded.replace(/\.0$/, "")}%`;
}

function formatSam3dMorphValue(value, unit = "") {
  if (!Number.isFinite(value)) return "—";
  if (unit === "%") return formatSam3dBodyPercent(value);
  const digits = Math.abs(value) >= 10 ? 2 : 3;
  const formatted = value.toFixed(digits).replace(/\.?0+$/, "");
  return `${formatted}${unit ? ` ${unit}` : ""}`;
}

function sam3dBodyConfidenceLabel(value) {
  if (!Number.isFinite(value)) return "Not reported";
  const level = value >= 80 ? "high" : value >= 55 ? "medium" : "low";
  return `${Math.round(value)}% · ${level}`;
}

function renderSam3dMeasurementList(target, measurements, emptyMessage) {
  target.replaceChildren();
  if (!measurements.length) {
    const empty = createElement("div", "inline-empty");
    const message = document.createElement("p");
    message.textContent = emptyMessage;
    empty.append(message);
    target.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const measurement of measurements) {
    const item = createElement("article", "sam3d-measurement-item");
    const heading = createElement("div", "sam3d-measurement-heading");
    const name = document.createElement("strong");
    name.textContent = measurement.label;
    const region = document.createElement("span");
    region.textContent = measurement.region || "body";
    heading.append(name, region);
    const values = createElement("div", "sam3d-measurement-values");
    const comparison = document.createElement("strong");
    comparison.textContent =
      `${formatSam3dBodyPercent(measurement.current)} → ` +
      formatSam3dBodyPercent(measurement.target);
    const delta = document.createElement("span");
    delta.textContent = formatSam3dBodyPercent(measurement.delta, {
      signed: true,
    });
    delta.classList.toggle(
      "is-positive",
      Number.isFinite(measurement.delta) && measurement.delta > 0,
    );
    delta.classList.toggle(
      "is-negative",
      Number.isFinite(measurement.delta) && measurement.delta < 0,
    );
    values.append(comparison, delta);
    const meta = document.createElement("small");
    const confidence = Number.isFinite(measurement.confidence)
      ? `Confidence ${Math.round(measurement.confidence)}%`
      : "Confidence not reported";
    const disagreement = Number.isFinite(measurement.disagreement)
      ? ` · references differ ${Math.round(measurement.disagreement)}%`
      : "";
    meta.textContent = `${confidence}${disagreement}`;
    item.append(heading, values, meta);
    fragment.append(item);
  }
  target.append(fragment);
}

function renderSam3dBodyMeasurements(analysis) {
  renderSam3dMeasurementList(
    elements.sam3dProportionsMeasurements,
    analysis.measurements,
    "No Structure measurements were returned.",
  );
}

function renderSam3dShapeMeasurements(analysis) {
  renderSam3dMeasurementList(
    elements.sam3dShapeMeasurements,
    asArray(analysis.shapeMeasurements),
    "No Body Shape measurements were returned for the selected regions.",
  );
}

function renderSam3dMorphChangeList(
  target,
  morphs,
  unavailable,
  emptyMessage,
) {
  target.replaceChildren();
  if (!morphs.length && !unavailable.length) {
    const empty = createElement("div", "inline-empty");
    const message = document.createElement("p");
    message.textContent = emptyMessage;
    empty.append(message);
    target.append(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const morph of morphs) {
    const item = createElement(
      "article",
      `sam3d-morph-change${morph.available ? "" : " is-unavailable"}`,
    );
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = morph.label;
    const detail = document.createElement("small");
    detail.textContent =
      morph.reason ||
      `${morph.region || "body"} · bounded VaM morph`;
    copy.append(name, detail);
    const values = createElement("div", "sam3d-morph-values");
    const comparison = document.createElement("span");
    comparison.textContent =
      `${formatSam3dMorphValue(morph.current, morph.unit)} → ` +
      formatSam3dMorphValue(morph.target, morph.unit);
    const delta = document.createElement("strong");
    const deltaPrefix =
      Number.isFinite(morph.delta) && morph.delta > 0 ? "+" : "";
    delta.textContent =
      `${deltaPrefix}${formatSam3dMorphValue(morph.delta, morph.unit)}`;
    values.append(comparison, delta);
    item.append(copy, values);
    fragment.append(item);
  }
  for (const unavailableRegion of unavailable) {
    const item = createElement(
      "article",
      "sam3d-morph-change is-unavailable",
    );
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    const region = String(unavailableRegion.region || "body");
    name.textContent =
      `${region.charAt(0).toUpperCase()}${region.slice(1)} fit unavailable`;
    const detail = document.createElement("small");
    detail.textContent =
      unavailableRegion.reason || "No verified VaM morph is loaded.";
    copy.append(name, detail);
    const values = createElement("div", "sam3d-morph-values");
    const status = document.createElement("strong");
    status.textContent = "Not applied";
    values.append(status);
    item.append(copy, values);
    fragment.append(item);
  }
  target.append(fragment);
}

function renderSam3dMorphChanges(analysis) {
  renderSam3dMorphChangeList(
    elements.sam3dProportionsMorphs,
    analysis.morphs,
    asArray(analysis.unavailable),
    "No safe VaM Structure changes are available for this fit.",
  );
}

function renderSam3dShapeMorphChanges(analysis) {
  renderSam3dMorphChangeList(
    elements.sam3dShapeMorphs,
    asArray(analysis.shapeMorphs),
    asArray(analysis.shapeUnavailable),
    "No safe VaM Body Shape changes are available for the selected regions.",
  );
}

function renderSam3dBodyProportions() {
  const settings = sam3dBodyProportionSettings();
  const job = sam3dBodyProportionJob(settings);
  const visible = Boolean(
    job || app.sam3dJobs.some(sam3dJobSucceeded),
  );
  elements.sam3dProportionsPanel.hidden =
    !visible || app.sam3dHandoffTab !== "morph";
  if (!visible) return;
  if (job && app.sam3dBodyProportionsJobId !== job.id) {
    resetSam3dBodyProportions(job.id);
  }

  const analysis = app.sam3dBodyProportions;
  const error = app.sam3dBodyProportionsError;
  const busy =
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    app.sam3dMutationInFlight ||
    snapshotBridgeBusy();
  renderSam3dBodyProfileActionState();
  const referencesReady = sam3dBodyReferencesReady(settings.references);
  const referenceCombinationIssue = sam3dBodyReferenceSetIssue(
    settings.references,
    settings.regions,
  );
  const revisionReady = Boolean(
    job && SAM3D_JOB_ID_PATTERN.test(job.revision),
  );
  const targetReady = Boolean(settings.targetUid);
  const regionsReady =
    settings.regions.length > 0 ||
    settings.shapeRegions.length > 0 ||
    sam3dManualShapeHasCorrections(settings.manualShape);
  const bodyShapeCalibration =
    sam3dBodyShapeCalibrationState(settings);
  const bodyShapeAnalyzeBlocked =
    bodyShapeCalibration.analyzeBlocked;
  const bodyShapeApplyBlocked =
    bodyShapeCalibration.applyBlocked;
  const unavailable = analysis?.available === false;
  const analyzed = Boolean(analysis?.ready);
  const poseApplied =
    sam3dJobIsApplied(app.sam3dSelectedJob) ||
    Boolean(analysis?.poseApplied);
  const targetChanged =
    analyzed &&
    Boolean(analysis.targetUid) &&
    analysis.targetUid !== settings.targetUid;
  const analyzedReferenceSignature = serializeSam3dBodyReferences(
    analysis?.references,
  );
  const referenceChanged =
    analyzed &&
    (analyzedReferenceSignature
      ? analyzedReferenceSignature !==
        serializeSam3dBodyReferences(settings.references)
      : Number.isFinite(analysis.personIndex) &&
        analysis.personIndex !== settings.personIndex);
  const bodyShapeReadinessChanged =
    analyzed &&
    analysis.bodyShapeReady !== bodyShapeCalibration.ready;
  const manualShapeChanged =
    analyzed &&
    serializeSam3dManualShape(analysis.manualShape) !==
      serializeSam3dManualShape(settings.manualShape);
  const dirty =
    analyzed &&
    (app.sam3dBodyProportionsDirty ||
      targetChanged ||
      referenceChanged ||
      manualShapeChanged ||
      bodyShapeReadinessChanged);

  elements.sam3dFitStrengthValue.value = `${settings.strength}%`;
  elements.sam3dShapeStrengthValue.value = `${settings.shapeStrength}%`;
  elements.sam3dProportionsState.className =
    `sam3d-proportions-state${
      app.sam3dBodyProportionsInFlight ||
      app.sam3dBodyProportionsPendingAction ||
      bodyShapeAnalyzeBlocked
        ? " is-running"
        : error
          ? " is-error"
          : unavailable
            ? " is-unavailable"
            : analyzed && !dirty
              ? " is-ready"
              : ""
    }`;
  elements.sam3dProportionsRetry.hidden = !error;
  elements.sam3dProportionsAnalyze.disabled =
    busy ||
    unavailable ||
    !referencesReady ||
    Boolean(referenceCombinationIssue) ||
    !revisionReady ||
    !targetReady ||
    !regionsReady ||
    bodyShapeAnalyzeBlocked;

  for (const region of SAM3D_BODY_PROPORTION_REGIONS) {
    sam3dBodyProportionRegionControl(region).disabled = busy;
  }
  for (const region of SAM3D_BODY_SHAPE_REGIONS) {
    sam3dBodyShapeRegionControl(region).disabled = busy;
  }
  elements.sam3dFitStrength.disabled = busy;
  elements.sam3dShapeStrength.disabled = busy;
  for (const card of Array.from(
    elements.sam3dMorphReferenceGallery.querySelectorAll?.(
      "[data-sam3d-body-reference]",
    ) || [],
  )) {
    const selected = card.getAttribute("aria-selected") === "true";
    const reference = normalizeSam3dBodyReference(
      card.dataset.sam3dBodyReference,
    );
    const replacesSelectedJob = settings.references.some(
      (candidate) => candidate.jobId === reference?.jobId,
    );
    card.disabled =
      busy ||
      Boolean(analysis?.applied) ||
      (!selected &&
        settings.references.length >=
          SAM3D_BODY_REFERENCE_MAX_COUNT &&
        !replacesSelectedJob);
  }

  if (app.sam3dBodyProportionsPendingAction) {
    const undoing =
      app.sam3dBodyProportionsPendingAction ===
      SAM3D_BODY_PROPORTION_ACTIONS.undo;
    elements.sam3dProportionsStateTitle.textContent =
      analysis?.state === "settling" && !undoing
        ? "Body fit applied — preparing Undo…"
        : undoing
          ? "Restoring the previous body…"
          : "Applying the combined body fit…";
    elements.sam3dProportionsStateMessage.textContent =
      analysis?.message ||
      "Waiting for VaM to publish the exact post-change morph revision.";
  } else if (app.sam3dBodyProportionsInFlight) {
    elements.sam3dProportionsStateTitle.textContent =
      "Analyzing Structure and Body Shape…";
    elements.sam3dProportionsStateMessage.textContent =
      "Reading the selected Person and comparing it with the canonical SAM 3D body. VaM is not being changed.";
  } else if (error) {
    elements.sam3dProportionsStateTitle.textContent =
      "Body analysis could not be loaded";
    elements.sam3dProportionsStateMessage.textContent = errorMessage(error);
  } else if (unavailable) {
    elements.sam3dProportionsStateTitle.textContent =
      "Body-proportion fitting unavailable";
    elements.sam3dProportionsStateMessage.textContent =
      analysis.message ||
      "Install the manager and bridge version that supports bounded body morph fitting.";
  } else if (!settings.references.length) {
    elements.sam3dProportionsStateTitle.textContent =
      "Choose Morph references";
    elements.sam3dProportionsStateMessage.textContent =
      "Select at least one completed body in the reference gallery.";
  } else if (!referencesReady) {
    elements.sam3dProportionsStateTitle.textContent =
      "A Morph reference is unavailable";
    elements.sam3dProportionsStateMessage.textContent =
      "Remove or replace references that are no longer in completed job history.";
  } else if (referenceCombinationIssue) {
    elements.sam3dProportionsStateTitle.textContent =
      "Legacy reference cannot be combined";
    elements.sam3dProportionsStateMessage.textContent =
      referenceCombinationIssue;
  } else if (!targetReady) {
    elements.sam3dProportionsStateTitle.textContent =
      "Choose a target Person";
    elements.sam3dProportionsStateMessage.textContent =
      "Start VaM or add a Person atom, then refresh the scene targets.";
  } else if (!regionsReady) {
    elements.sam3dProportionsStateTitle.textContent =
      "Choose at least one body region";
    elements.sam3dProportionsStateMessage.textContent =
      "Select a Structure or automatic Body Shape region, or add a Manual Fit correction.";
  } else if (bodyShapeAnalyzeBlocked) {
    elements.sam3dProportionsStateTitle.textContent =
      "Preparing neutral body-shape calibration in VaM…";
    elements.sam3dProportionsStateMessage.textContent =
      "VaM is measuring the selected Person’s neutral mesh. Analyze and Apply will unlock automatically when it is ready; clear all Body Shape regions to continue with Structure only.";
  } else if (bodyShapeReadinessChanged) {
    elements.sam3dProportionsStateTitle.textContent =
      bodyShapeCalibration.ready
        ? "Neutral body-shape calibration ready"
        : "Neutral body-shape calibration changed";
    elements.sam3dProportionsStateMessage.textContent =
      "Run Analyze again to bind the proposal to VaM’s current stable body revision before applying it.";
  } else if (analysis?.state === "unchanged") {
    elements.sam3dProportionsStateTitle.textContent =
      "Body fit made no changes";
    elements.sam3dProportionsStateMessage.textContent =
      analysis.message ||
      "Every requested morph was already at its proposed value.";
  } else if (dirty) {
    elements.sam3dProportionsStateTitle.textContent =
      "Analysis settings changed";
    elements.sam3dProportionsStateMessage.textContent =
      "Run Analyze again to recalculate the proposal before applying it.";
  } else if (analyzed) {
    elements.sam3dProportionsStateTitle.textContent =
      analysis.applied ? "Body fit applied" : "Body fit proposal ready";
    elements.sam3dProportionsStateMessage.textContent =
      analysis.blockedReason ||
      analysis.message ||
      "Review every Structure and Body Shape change before applying the combined fit.";
  } else {
    elements.sam3dProportionsStateTitle.textContent =
      "Analyze before changing VaM";
    elements.sam3dProportionsStateMessage.textContent =
      "Compare Structure and selected Body Shape regions with the Person. Analysis is read-only.";
  }

  elements.sam3dProportionsResults.hidden = !analyzed;
  if (analyzed) {
    elements.sam3dProportionsConfidence.textContent =
      sam3dBodyConfidenceLabel(analysis.confidence);
    elements.sam3dShapeConfidence.textContent =
      sam3dBodyConfidenceLabel(analysis.shapeConfidence);
    elements.sam3dProportionsDisagreement.textContent =
      Number.isFinite(analysis.disagreement)
        ? `${Math.round(analysis.disagreement)}%`
        : "Not compared";
    renderSam3dBodyMeasurements(analysis);
    renderSam3dMorphChanges(analysis);
    renderSam3dShapeMeasurements(analysis);
    renderSam3dShapeMorphChanges(analysis);
  } else {
    elements.sam3dProportionsMeasurements.replaceChildren();
    elements.sam3dProportionsMorphs.replaceChildren();
    elements.sam3dShapeMeasurements.replaceChildren();
    elements.sam3dShapeMorphs.replaceChildren();
  }
  renderSam3dManualFit(analysis);

  elements.sam3dProportionsApply.disabled =
    busy ||
    !analyzed ||
    dirty ||
    analysis.applied ||
    !analysis.canApply ||
    !analysis.analysisRevision ||
    !referencesReady ||
    Boolean(referenceCombinationIssue) ||
    !targetReady ||
    !regionsReady ||
    bodyShapeApplyBlocked;
  const undoReady =
    !busy &&
    analyzed &&
    analysis.canUndo &&
    analysis.applyRevision &&
    !poseApplied &&
    targetReady;
  elements.sam3dProportionsUndo.disabled = !undoReady;
  if (undoReady) {
    elements.sam3dProportionsUndo.classList.remove("secondary-button");
    elements.sam3dProportionsUndo.classList.add("primary-button");
  } else {
    elements.sam3dProportionsUndo.classList.remove("primary-button");
    elements.sam3dProportionsUndo.classList.add("secondary-button");
  }

  elements.sam3dProportionsNote.classList.remove("is-error");
  let note =
    `${settings.references.length} Morph reference${
      settings.references.length === 1 ? "" : "s"
    } selected. Structure and ${settings.shapeRegions.length} Body Shape region${
      settings.shapeRegions.length === 1 ? "" : "s"
    } will be fitted together. Face morphs and soft-body physics are excluded.`;
  if (!settings.references.length) {
    note = "Select one to eight completed bodies before analyzing.";
    elements.sam3dProportionsNote.classList.add("is-error");
  } else if (!referencesReady) {
    note =
      "Every Morph reference must still be available in completed job history.";
    elements.sam3dProportionsNote.classList.add("is-error");
  } else if (referenceCombinationIssue) {
    note = referenceCombinationIssue;
    elements.sam3dProportionsNote.classList.add("is-error");
  } else if (!revisionReady) {
    note = "The reconstruction revision is invalid. Refresh this job before analysis.";
    elements.sam3dProportionsNote.classList.add("is-error");
  } else if (error) {
    note =
      errorMessage(error) ||
      "The body-fit status could not be confirmed. Retry the read-only analysis.";
    elements.sam3dProportionsNote.classList.add("is-error");
  } else if (bodyShapeCalibration.preparing) {
    note = settings.shapeRegions.length
      ? "Preparing neutral body-shape calibration in VaM… Structure-only analysis remains available when all Body Shape regions are cleared."
      : "VaM is preparing its neutral body-shape calibration. Structure analysis and review are available now; Apply will unlock when the stable cache is ready.";
  } else if (bodyShapeApplyBlocked) {
    note =
      "Apply requires a valid neutral body-shape calibration from VaM." +
      (bodyShapeCalibration.reason
        ? ` ${bodyShapeCalibration.reason}`
        : "");
  } else if (bodyShapeReadinessChanged) {
    note =
      "VaM’s neutral body-shape calibration changed after this proposal was analyzed. Run Analyze again before applying.";
  } else if (analysis?.state === "unchanged") {
    note =
      "VaM made no morph changes and created no undo revision. Run Analyze again before retrying Apply body fit.";
  } else if (dirty) {
    note =
      "This proposal is stale because a region, fit strength, or Manual Fit correction changed.";
  } else if (analysis?.applied && poseApplied) {
    note =
      "Undo pose + camera in step 5 before restoring the previous body morphs.";
  } else if (analysis?.blockedReason) {
    note = analysis.blockedReason;
  } else if (
    analyzed &&
    !analysis.morphs.length &&
    !asArray(analysis.shapeMorphs).length
  ) {
    note =
      "Measurements are available, but no allowlisted morph change can be applied safely.";
  } else if (analysis?.applied) {
    note =
      "This Person has a one-level body-fit snapshot, shared across reconstruction jobs. Restore it before applying another fit, or use Apply pose + camera to refit the controllers.";
  } else if (
    Number.isFinite(analysis?.disagreement) &&
    analysis.disagreement >= 15
  ) {
    note =
      "The selected references or views disagree substantially. Consider a lower fit strength or exclude the uncertain region.";
  }
  elements.sam3dProportionsNote.textContent = note;
}

async function analyzeSam3dBodyProportions() {
  const settings = sam3dBodyProportionSettings();
  const job = sam3dBodyProportionJob(settings);
  if (!job || elements.sam3dProportionsAnalyze.disabled) return;
  const referenceSignature = serializeSam3dBodyReferences(
    settings.references,
  );
  const manualShapeSignature = serializeSam3dManualShape(
    settings.manualShape,
  );
  app.sam3dBodyProportionsInFlight = true;
  app.sam3dBodyProportionsError = null;
  setButtonBusy(
    elements.sam3dProportionsAnalyze,
    true,
    "Analyzing…",
  );
  renderSam3dBodyProportions();
  try {
    const payload = await Sam3dClient.bodyProportionsAction(
      job.id,
      SAM3D_BODY_PROPORTION_ACTIONS.analyze,
      sam3dBodyProportionRequest(job),
    );
    const currentSettings = sam3dBodyProportionSettings();
    if (
      currentSettings.referenceJobId !== job.id ||
      serializeSam3dBodyReferences(currentSettings.references) !==
        referenceSignature ||
      serializeSam3dManualShape(currentSettings.manualShape) !==
        manualShapeSignature
    ) {
      return;
    }
    const analysis = normalizeSam3dBodyProportions(payload);
    if (!analysis.ready) {
      throw new Error(
        analysis.message || "The manager did not return a body-fit proposal.",
      );
    }
    app.sam3dBodyProportions = analysis;
    app.sam3dBodyProportions.targetUid = settings.targetUid;
    app.sam3dBodyProportions.personIndex = settings.personIndex;
    app.sam3dBodyProportions.references = settings.references;
    app.sam3dBodyProportionsDirty = false;
    const proposedCount =
      analysis.morphs.length + asArray(analysis.shapeMorphs).length;
    toast(
      "Body analysis ready",
      `${analysis.measurements.length + asArray(analysis.shapeMeasurements).length} measurements and ${proposedCount} bounded changes were proposed for ${settings.targetUid}.`,
    );
  } catch (error) {
    app.sam3dBodyProportionsError = error;
    toast("Could not analyze body proportions", errorMessage(error), "error");
  } finally {
    app.sam3dBodyProportionsInFlight = false;
    setButtonBusy(elements.sam3dProportionsAnalyze, false);
    renderSam3dBodyProportions();
  }
}

async function applySam3dBodyProportions() {
  const settings = sam3dBodyProportionSettings();
  const job = sam3dBodyProportionJob(settings);
  const analysis = app.sam3dBodyProportions;
  if (!job || !analysis || elements.sam3dProportionsApply.disabled) return;
  const confirmed = await showDialog({
    eyebrow: "Apply combined body fit",
    title: "Apply Structure and Body Shape to this Person?",
    message:
      "The reviewed Structure and Body Shape morphs are applied atomically with one exact undo. Face morphs and breast/glute physics settings stay untouched. After VaM confirms the revision, apply pose + camera in step 5.",
    confirmLabel: "Apply body fit",
    icon: "warning",
    plan: [
      ["Person", settings.targetUid],
      ["Morph references", String(settings.references.length)],
      [
        "Structure",
        settings.regions.length
          ? `${settings.regions.join(", ")} · ${settings.strength}%`
          : "Not selected",
      ],
      [
        "Body Shape",
        settings.shapeRegions.length
          ? `${settings.shapeRegions.join(", ")} · ${settings.shapeStrength}%`
          : "Not selected",
      ],
      [
        "Manual Fit",
        sam3dManualShapeHasCorrections(settings.manualShape)
          ? "Estimator corrections included"
          : "Estimator target",
      ],
      [
        "Reviewed changes",
        String(analysis.morphs.length + asArray(analysis.shapeMorphs).length),
      ],
      ["Scale", "Body Scale unchanged; final height may change"],
    ],
  });
  if (!confirmed) return;

  app.sam3dBodyProportionsInFlight = true;
  setButtonBusy(elements.sam3dProportionsApply, true, "Applying…");
  renderSam3dBodyProportions();
  try {
    const payload = await Sam3dClient.bodyProportionsAction(
      job.id,
      SAM3D_BODY_PROPORTION_ACTIONS.apply,
      sam3dBodyProportionRequest(job, {
        analysisRevision: analysis.analysisRevision,
      }),
    );
    app.sam3dBodyProportions = {
      ...analysis,
      state: "queued",
      message: String(
        payload.message ||
          "Waiting for VaM to confirm the body-proportion revision.",
      ),
      targetUid: settings.targetUid,
      personIndex: settings.personIndex,
      references: settings.references,
      applyRevision: "",
      canUndo: false,
      applied: false,
    };
    app.sam3dBodyProportionsPendingAction =
      SAM3D_BODY_PROPORTION_ACTIONS.apply;
    app.sam3dBodyProportionPollAttempts = 0;
    app.sam3dBodyProportionsDirty = false;
    toast(
      "Body fit queued",
      payload.message ||
        "The bridge is applying the combined bounded body fit.",
    );
    await loadPersons({ quiet: true });
    app.sam3dBodyProportionsInFlight = false;
    startSam3dBodyProportionPolling();
  } catch (error) {
    app.sam3dBodyProportionsError = error;
    toast("Could not apply body proportions", errorMessage(error), "error");
  } finally {
    app.sam3dBodyProportionsInFlight = false;
    setButtonBusy(elements.sam3dProportionsApply, false);
    renderSam3dWorkspace();
  }
}

async function undoSam3dBodyProportions() {
  const settings = sam3dBodyProportionSettings();
  const job = sam3dBodyProportionJob(settings);
  const analysis = app.sam3dBodyProportions;
  if (!job || !analysis || elements.sam3dProportionsUndo.disabled) return;
  app.sam3dBodyProportionsInFlight = true;
  setButtonBusy(elements.sam3dProportionsUndo, true, "Restoring…");
  renderSam3dBodyProportions();
  try {
    const payload = await Sam3dClient.bodyProportionsAction(
      job.id,
      SAM3D_BODY_PROPORTION_ACTIONS.undo,
      sam3dBodyProportionUndoRequest(
        settings.targetUid,
        analysis.applyRevision,
      ),
    );
    app.sam3dBodyProportions = {
      ...analysis,
      state: "queued",
      message: String(
        payload.message ||
          "Waiting for VaM to confirm the restored morph revision.",
      ),
    };
    app.sam3dBodyProportionsPendingAction =
      SAM3D_BODY_PROPORTION_ACTIONS.undo;
    app.sam3dBodyProportionPollAttempts = 0;
    toast(
      "Body fit queued for restore",
      payload.message ||
        "The bridge is restoring the previous body-proportion morph values.",
    );
    await loadPersons({ quiet: true });
    app.sam3dBodyProportionsInFlight = false;
    startSam3dBodyProportionPolling();
  } catch (error) {
    app.sam3dBodyProportionsError = error;
    toast("Could not undo body fit", errorMessage(error), "error");
  } finally {
    app.sam3dBodyProportionsInFlight = false;
    setButtonBusy(elements.sam3dProportionsUndo, false);
    renderSam3dWorkspace();
  }
}

function sam3dTargetEntries(kind) {
  const status = app.sam3dStatus || {};
  const vam =
    status.vam && typeof status.vam === "object" ? status.vam : {};
  const targets =
    status.targets && typeof status.targets === "object"
      ? status.targets
      : {};
  const vamTargets =
    vam.targets && typeof vam.targets === "object" ? vam.targets : {};
  const keys =
    kind === "person"
      ? ["persons", "people", "person_targets"]
      : ["cameras", "camera_targets", "vr_funscript_cameras"];
  let raw = [];
  for (const container of [targets, vamTargets, vam, status]) {
    for (const key of keys) {
      if (Array.isArray(container[key])) {
        raw = container[key];
        break;
      }
    }
    if (raw.length) break;
  }
  return raw
    .map((entry) => {
      if (typeof entry === "string") {
        return { uid: entry, label: entry, selected: false };
      }
      if (!entry || typeof entry !== "object") return null;
      const uid = String(
        entry.uid || entry.id || entry.target_uid || "",
      ).trim();
      if (!uid) return null;
      return {
        uid,
        label: String(entry.label || entry.name || uid),
        selected: Boolean(entry.selected),
      };
    })
    .filter(Boolean);
}

function sam3dCameraAtomIsVerified(atom) {
  if (!atom || atom.type.toLowerCase() !== "empty") return false;
  const cameraStatus =
    atom.sam3dCamera && typeof atom.sam3dCamera === "object"
      ? atom.sam3dCamera
      : atom.sam3d_camera;
  if (
    atom.sam3d_camera === true ||
    atom.vr_funscript_camera === true ||
    atom.camera_ready === true ||
    cameraStatus?.compatible === true
  ) {
    return true;
  }
  const marker = JSON.stringify([
    atom.camera,
    atom.sam3dCamera,
    atom.sam3d_camera,
    atom.renderer,
    atom.plugins,
    atom.plugin,
  ]).toLowerCase();
  return (
    marker.includes("vrvideoandfunscript") ||
    marker.includes("vr video & funscript") ||
    marker.includes("vamrobot_vrvideoandfunscriptexporter")
  );
}

function renderSam3dTargets() {
  const previousPerson = elements.sam3dPersonTarget.value;
  const previousCamera = elements.sam3dCameraTarget.value;
  const selectedJob = app.sam3dSelectedJob;
  const alreadyApplied = sam3dJobIsApplied(selectedJob);
  const appliedCameraUid = alreadyApplied
    ? String(selectedJob?.cameraUid || "").trim()
    : "";
  let persons = sam3dTargetEntries("person");
  if (!persons.length) {
    persons = personList().map((person) => ({
      uid: person.uid,
      label: person.uid,
      selected: Boolean(person.selected),
    }));
  }
  let cameras = sam3dTargetEntries("camera");
  if (!cameras.length) {
    cameras = atomList()
      .filter(sam3dCameraAtomIsVerified)
      .map((atom) => ({
        uid: atom.uid,
        label: `${atom.uid} · VR + Funscript`,
        selected: Boolean(atom.selected),
      }));
  }

  elements.sam3dPersonTarget.replaceChildren();
  if (persons.length) {
    for (const person of persons) {
      const suffix = person.selected ? " · selected in VaM" : "";
      elements.sam3dPersonTarget.append(
        new Option(`${person.label}${suffix}`, person.uid),
      );
    }
    const preferred =
      persons.find((person) => person.uid === previousPerson)?.uid ||
      persons.find((person) => person.uid === app.selectedPersonUid)?.uid ||
      persons.find((person) => person.selected)?.uid ||
      persons[0].uid;
    elements.sam3dPersonTarget.value = preferred;
  } else {
    elements.sam3dPersonTarget.append(
      new Option(
        personVamRunning() ? "No Person atoms found" : "Start VaM first",
        "",
      ),
    );
  }

  elements.sam3dCameraTarget.replaceChildren();
  if (cameras.length) {
    for (const camera of cameras) {
      const suffix = camera.selected ? " · selected in VaM" : "";
      elements.sam3dCameraTarget.append(
        new Option(`${camera.label}${suffix}`, camera.uid),
      );
    }
  }
  const capabilities = sam3dCapabilitySet();
  const fixedCameraUidExists = atomList().some(
    (atom) => atom.uid === SAM3D_DEFAULT_CAMERA_UID,
  );
  if (
    !alreadyApplied &&
    !fixedCameraUidExists &&
    (
      capabilities.has("sam3d-camera-create-v1") ||
      capabilities.has("sam3d-camera-create") ||
      sam3dApplyCapabilityAvailable() ||
      sam3dReferenceCapabilityAvailable()
    )
  ) {
    elements.sam3dCameraTarget.append(
      new Option("Create VAM-PIP camera · Empty + VR/Funscript", "__create__"),
    );
  }
  if (elements.sam3dCameraTarget.options.length) {
    const knownPrevious = Array.from(
      elements.sam3dCameraTarget.options,
    ).some(
      (option) =>
        option.value === previousCamera &&
        !(
          previousCamera === "__create__" &&
          cameras.some(
            (camera) => camera.uid === SAM3D_DEFAULT_CAMERA_UID,
          )
        ),
    );
    elements.sam3dCameraTarget.value = knownPrevious
      ? appliedCameraUid || previousCamera
      : cameras.find((camera) => camera.uid === appliedCameraUid)?.uid ||
        cameras.find(
          (camera) => camera.uid === SAM3D_DEFAULT_CAMERA_UID,
        )?.uid ||
        cameras.find((camera) => camera.selected)?.uid ||
        cameras[0]?.uid ||
        "__create__";
  } else {
    elements.sam3dCameraTarget.append(
      new Option(
        personVamRunning()
          ? "No verified VR/Funscript camera"
          : "Start VaM first",
        "",
      ),
    );
  }
  elements.sam3dPersonTarget.disabled =
    !persons.length ||
    app.sam3dMutationInFlight ||
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    alreadyApplied;
  elements.sam3dCameraTarget.disabled =
    !elements.sam3dCameraTarget.value ||
    app.sam3dMutationInFlight ||
    alreadyApplied;
}

function sam3dApplyCapabilityAvailable() {
  const capabilities = new Set([
    ...sam3dCapabilitySet(),
    ...personCapabilities(),
  ]);
  return (
    capabilities.has("sam3d-apply-v1") &&
    capabilities.has("sam3d-camera-vrfunscript-v1")
  );
}

function sam3dCaptureCapabilityAvailable() {
  const capabilities = new Set([
    ...sam3dCapabilitySet(),
    ...personCapabilities(),
  ]);
  return (
    capabilities.has("sam3d-capture-v1") &&
    capabilities.has("sam3d-camera-vrfunscript-v1")
  );
}

function sam3dReferenceCapabilityAvailable() {
  const capabilities = new Set([
    ...sam3dCapabilitySet(),
    ...personCapabilities(),
  ]);
  return capabilities.has("sam3d-reference-v1");
}

function sam3dKeepReferenceRequested() {
  return Boolean(
    elements.sam3dKeepReference.checked &&
      sam3dReferenceCapabilityAvailable(),
  );
}

function renderSam3dResolutionOptions(preferred = "") {
  const aspectValues = Object.keys(SAM3D_RENDERER_RESOLUTIONS);
  if (elements.sam3dAspectRatio.options.length !== aspectValues.length) {
    const current = elements.sam3dAspectRatio.value;
    elements.sam3dAspectRatio.replaceChildren(
      ...aspectValues.map((value) => new Option(value, value)),
    );
    elements.sam3dAspectRatio.value = aspectValues.includes(current)
      ? current
      : "16:9";
  }
  const aspect = elements.sam3dAspectRatio.value || "16:9";
  const choices = SAM3D_RENDERER_RESOLUTIONS[aspect] || [];
  const current = preferred || elements.sam3dOutputResolution.value;
  elements.sam3dOutputResolution.replaceChildren(
    ...choices.map((value) => new Option(value, value)),
  );
  elements.sam3dOutputResolution.value = choices.includes(current)
    ? current
    : aspect === "16:9" && choices.includes("1920x1080 (FHD)")
      ? "1920x1080 (FHD)"
      : choices[0] || "";
}

function sam3dCameraPlacementSettings() {
  const fovRaw = String(elements.sam3dCameraFov.value || "").trim();
  const horizontalFov = fovRaw ? Number(fovRaw) : null;
  if (
    horizontalFov !== null &&
    (!Number.isFinite(horizontalFov) ||
      horizontalFov < 5 ||
      horizontalFov > 170)
  ) {
    throw new Error("Horizontal FOV override must be between 5° and 170°.");
  }
  const heightM = Number(elements.sam3dPersonHeight.value);
  if (!Number.isFinite(heightM) || heightM < 0.5 || heightM > 3) {
    throw new Error("Estimated body height must be between 0.5 m and 3 m.");
  }
  return { horizontalFov, heightM };
}

function sam3dApplySettings() {
  const { horizontalFov, heightM } = sam3dCameraPlacementSettings();
  const aspectRatio = elements.sam3dAspectRatio.value;
  const outputResolution = elements.sam3dOutputResolution.value;
  const choices = SAM3D_RENDERER_RESOLUTIONS[aspectRatio];
  if (!choices || !choices.includes(outputResolution)) {
    throw new Error("Choose a supported VRRendererX output resolution.");
  }
  const imageFormat = elements.sam3dImageFormat.value;
  if (!["jpeg", "png"].includes(imageFormat)) {
    throw new Error("Choose JPEG or PNG capture.");
  }
  return {
    horizontalFov,
    heightM,
    aspectRatio,
    outputResolution,
    imageFormat,
  };
}

function sam3dReferenceRequest(job = app.sam3dSelectedJob) {
  if (!job || !SAM3D_JOB_ID_PATTERN.test(String(job.revision || ""))) {
    throw new Error("The current SAM 3D job has no valid revision.");
  }
  const targetUid = String(elements.sam3dPersonTarget.value || "").trim();
  if (!targetUid) {
    throw new Error("Choose a target Person before showing the reference.");
  }
  const cameraValue = String(elements.sam3dCameraTarget.value || "").trim();
  if (!cameraValue) {
    throw new Error(
      "Choose or create a VR Video & Funscript camera for the reference view.",
    );
  }
  const createCamera = cameraValue === "__create__";
  const settings = sam3dCameraPlacementSettings();
  const request = {
    expected_job_revision: job.revision,
    target_uid: targetUid,
    person_index: app.sam3dSelectedBodyIndex,
    height_m: settings.heightM,
    camera_uid: createCamera ? SAM3D_DEFAULT_CAMERA_UID : cameraValue,
    create_camera: createCamera,
  };
  if (settings.horizontalFov !== null) {
    request.horizontal_fov = settings.horizontalFov;
  }
  return request;
}

function sam3dReferenceSettingsError() {
  try {
    sam3dReferenceRequest();
    return "";
  } catch (error) {
    return errorMessage(error);
  }
}

function renderSam3dReferenceState() {
  const job = app.sam3dSelectedJob;
  const reference = job?.reference;
  const active = Boolean(reference?.visible);
  const capability = sam3dReferenceCapabilityAvailable();
  const bridgeBusy = snapshotBridgeBusy();
  const vamReady =
    personVamRunning() &&
    Boolean(app.person?.available) &&
    !Boolean(app.person?.loading);
  const busy =
    app.sam3dMutationInFlight ||
    app.sam3dBodyProportionsInFlight ||
    Boolean(app.sam3dBodyProportionsPendingAction) ||
    bridgeBusy;
  const revisionReady = Boolean(
    job && SAM3D_JOB_ID_PATTERN.test(String(job.revision || "")),
  );
  const settingsError =
    job && sam3dJobSucceeded(job) ? sam3dReferenceSettingsError() : "";

  if (!app.sam3dMutationInFlight) {
    elements.sam3dReferenceShow.textContent = active
      ? "Update reference in VaM"
      : "Show reference in VaM";
  }
  elements.sam3dReferenceShow.disabled =
    busy ||
    !job ||
    !sam3dJobSucceeded(job) ||
    !revisionReady ||
    !vamReady ||
    !capability ||
    Boolean(settingsError);
  elements.sam3dReferenceHide.disabled =
    busy ||
    !job ||
    !revisionReady ||
    !vamReady ||
    !capability ||
    !active;

  elements.sam3dReferenceState.classList.remove("is-active", "is-error");
  let message =
    "Show the current pose job’s full source image behind the Person before applying the body fit.";
  if (!job || !sam3dJobSucceeded(job)) {
    message = "Select a completed reconstruction to place its source image in VaM.";
  } else if (!personVamRunning()) {
    message = "Start VaM before placing the reference image.";
  } else if (!app.person?.available || app.person?.loading) {
    message = "Waiting for a fresh VaM scene snapshot.";
  } else if (!capability) {
    message =
      "Reload the updated VAM-PIP bridge to enable the in-scene reference.";
  } else if (bridgeBusy) {
    message =
      String(app.person?.bridge?.message || "").trim() ||
      "The VaM bridge is processing another request.";
  } else if (reference?.state === "queued" || reference?.state === "running") {
    message =
      reference.message ||
      "The bridge is updating the reference image inside VaM.";
  } else if (active) {
    const target = reference.targetUid || "the Person";
    const alignment =
      reference.mode === "pose-aligned"
        ? "aligned with the reconstructed pose and camera"
        : "placed for body fitting";
    message =
      `The full source image is ${alignment} behind ${target}. ` +
      (
        sam3dKeepReferenceRequested()
          ? "Pose + camera will keep it aligned."
          : "Enable Keep reference aligned before applying the pose."
      );
    elements.sam3dReferenceState.classList.add("is-active");
  } else if (settingsError) {
    message = settingsError;
    elements.sam3dReferenceState.classList.add("is-error");
  } else {
    message =
      `Show the full ${job.sourceName || "source image"} behind ` +
      `${elements.sam3dPersonTarget.value || "the selected Person"}.`;
  }
  elements.sam3dReferenceState.textContent = message;

  const lockKeepReference =
    !capability || busy || sam3dJobIsApplied(job);
  elements.sam3dKeepReference.disabled = lockKeepReference;
  elements.sam3dKeepReference.title = capability
    ? ""
    : "Reload the updated VAM-PIP bridge to enable reference alignment.";
}

async function showSam3dReference() {
  const job = app.sam3dSelectedJob;
  if (!job || elements.sam3dReferenceShow.disabled) return;
  const updating = Boolean(job.reference?.visible);
  app.sam3dMutationInFlight = true;
  setButtonBusy(
    elements.sam3dReferenceShow,
    true,
    updating ? "Updating…" : "Showing…",
  );
  renderSam3dReferenceState();
  renderSam3dApplyState();
  try {
    const request = sam3dReferenceRequest(job);
    const payload = await Sam3dClient.showReference(job.id, request);
    requireBridgeQueue(payload, "SAM 3D reference");
    const responseReference = normalizeSam3dReference(
      payload.reference,
      job.id,
    );
    mergeSam3dJob({
      ...job,
      reference: responseReference
        ? {
            ...responseReference,
            state: "queued",
            message: String(payload.message || ""),
          }
        : job.reference,
      vamActionState: String(payload.action_state || "queued"),
      vamActionMessage: String(
        payload.message ||
          "Waiting for VaM to place the full reference image.",
      ),
    });
    toast(
      updating ? "Reference update queued" : "Reference queued",
      payload.message ||
        "The bridge is placing the full source image behind the Person.",
    );
    await loadPersons({ quiet: true });
    await loadSam3dJob(job.id, { quiet: true });
    startSam3dPolling();
  } catch (error) {
    toast("Could not show reference in VaM", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dReferenceShow, false);
    renderSam3dWorkspace();
  }
}

async function hideSam3dReference() {
  const job = app.sam3dSelectedJob;
  if (!job || elements.sam3dReferenceHide.disabled) return;
  app.sam3dMutationInFlight = true;
  setButtonBusy(elements.sam3dReferenceHide, true, "Hiding…");
  renderSam3dReferenceState();
  renderSam3dApplyState();
  try {
    const payload = await Sam3dClient.hideReference(job.id, job.revision);
    requireBridgeQueue(payload, "Remove SAM 3D reference");
    mergeSam3dJob({
      ...job,
      reference: job.reference
        ? {
            ...job.reference,
            state: "queued",
            message: String(payload.message || ""),
          }
        : null,
      vamActionState: String(payload.action_state || "queued"),
      vamActionMessage: String(
        payload.message ||
          "Waiting for VaM to remove the reference image.",
      ),
    });
    toast(
      "Reference removal queued",
      payload.message ||
        "The bridge is removing the VAM-PIP reference from the scene.",
    );
    await loadPersons({ quiet: true });
    await loadSam3dJob(job.id, { quiet: true });
    startSam3dPolling();
  } catch (error) {
    toast("Could not hide reference in VaM", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dReferenceHide, false);
    renderSam3dWorkspace();
  }
}

function sam3dSolutionRevision(job = app.sam3dSelectedJob) {
  if (!job) return "";
  if (
    app.sam3dAppliedJobId === job.id &&
    SAM3D_JOB_ID_PATTERN.test(app.sam3dAppliedRevision)
  ) {
    return app.sam3dAppliedRevision;
  }
  return SAM3D_JOB_ID_PATTERN.test(job.solutionRevision)
    ? job.solutionRevision
    : "";
}

function sam3dJobIsApplied(job = app.sam3dSelectedJob) {
  return Boolean(
    job &&
      (
        job.applied ||
        (
          app.sam3dAppliedJobId === job.id &&
          SAM3D_JOB_ID_PATTERN.test(app.sam3dAppliedRevision)
        )
      ),
  );
}

function sam3dApplySettingsError() {
  try {
    sam3dApplySettings();
    return "";
  } catch (error) {
    return errorMessage(error);
  }
}

function setSam3dApplyControlsDisabled(disabled) {
  for (const control of [
    elements.sam3dCameraFov,
    elements.sam3dPersonHeight,
    elements.sam3dAspectRatio,
    elements.sam3dOutputResolution,
    elements.sam3dImageFormat,
  ]) {
    control.disabled = disabled;
  }
}

function renderSam3dApplyState() {
  const job = app.sam3dSelectedJob;
  if (!job || !sam3dJobSucceeded(job)) return;
  const revisionReady = SAM3D_JOB_ID_PATTERN.test(job.revision);
  const solutionRevision = sam3dSolutionRevision(job);
  const hasPerson = Boolean(elements.sam3dPersonTarget.value);
  const hasCamera = Boolean(elements.sam3dCameraTarget.value);
  const alreadyApplied = sam3dJobIsApplied(job);
  const appliedCameraUid = String(job.cameraUid || "").trim();
  const hasAppliedCamera =
    alreadyApplied &&
    Boolean(appliedCameraUid) &&
    Array.from(elements.sam3dCameraTarget.options).some(
      (option) =>
        option.value === appliedCameraUid &&
        option.value !== "__create__",
    );
  const bridgeBusy = snapshotBridgeBusy();
  const vamReady =
    personVamRunning() &&
    Boolean(app.person?.available) &&
    !Boolean(app.person?.loading);
  const canApply = sam3dApplyCapabilityAvailable();
  const canCapture = sam3dCaptureCapabilityAvailable();
  const busy = app.sam3dMutationInFlight || bridgeBusy;
  const settingsError = sam3dApplySettingsError();
  const actionState = sam3dVamActionState(job);

  setSam3dApplyControlsDisabled(busy || alreadyApplied);
  elements.sam3dApplyButton.disabled =
    busy ||
    alreadyApplied ||
    !revisionReady ||
    !hasPerson ||
    !hasCamera ||
    !vamReady ||
    !canApply ||
    Boolean(settingsError);
  elements.sam3dUndoButton.disabled =
    busy ||
    !solutionRevision ||
    !(job.canUndo || app.sam3dAppliedRevision);
  elements.sam3dCaptureButton.disabled =
    busy ||
    !solutionRevision ||
    !hasAppliedCamera ||
    !vamReady ||
    !canCapture ||
    !(job.applied || app.sam3dAppliedRevision);

  elements.sam3dApplyNote.classList.remove("is-error");
  let note =
    "Auto FOV uses SAM intrinsics. Pose and camera are applied as one revision-checked bridge request.";
  if (!revisionReady) {
    note = "The result has no valid job revision. Refresh it before applying.";
    elements.sam3dApplyNote.classList.add("is-error");
  } else if (settingsError) {
    note = settingsError;
    elements.sam3dApplyNote.classList.add("is-error");
  } else if (!personVamRunning()) {
    note = "Start VaM before applying this reconstruction.";
  } else if (!app.person?.available) {
    note = "Waiting for a fresh scene snapshot from the VAM-PIP bridge.";
  } else if (app.person?.loading) {
    note = "VaM is loading the scene. Apply controls will resume when it is ready.";
  } else if (bridgeBusy) {
    note =
      String(app.person?.bridge?.message || "").trim() ||
      "The VaM bridge is processing another request.";
  } else if (["failed", "stale"].includes(actionState)) {
    note =
      job.vamActionMessage ||
      (actionState === "stale"
        ? "VaM restarted before the previous SAM 3D action was confirmed."
        : "The previous SAM 3D action failed inside VaM.");
    elements.sam3dApplyNote.classList.add("is-error");
  } else if (!canApply) {
    note = "Reload the updated VAM-PIP bridge to enable SAM 3D pose + VR/Funscript camera apply.";
  } else if (!hasPerson) {
    note = "Add or select a Person atom in VaM.";
  } else if (!hasCamera) {
    note =
      "Add an Empty atom with VR Video & Funscript Exporter, or enable camera creation.";
  } else if (!canCapture) {
    note =
      "Pose + camera can be applied. Screenshot capture needs the updated VR Video & Funscript plugin.";
  } else if (alreadyApplied && !hasAppliedCamera) {
    note =
      "The applied camera is no longer available in the current VaM scene. Undo or restore that camera before capturing.";
    elements.sam3dApplyNote.classList.add("is-error");
  } else if (alreadyApplied) {
    note =
      `Applied to ${job.targetUid || "the Person"} with ${appliedCameraUid}. ` +
      "Capture uses that exact camera; undo before changing targets or settings.";
  }
  elements.sam3dApplyNote.textContent = note;
}

async function applySam3dResult() {
  const job = app.sam3dSelectedJob;
  if (!job || elements.sam3dApplyButton.disabled) return;
  const personUid = elements.sam3dPersonTarget.value;
  const cameraValue = elements.sam3dCameraTarget.value;
  const createCamera = cameraValue === "__create__";
  const settings = sam3dApplySettings();
  const keepReference = sam3dKeepReferenceRequested();
  const confirmed = await showDialog({
    eyebrow: "Apply SAM 3D reconstruction",
    title: "Replace this Person’s pose and move the camera?",
    message:
      "VAM-PIP will change the mapped Person controllers and the VR Video & Funscript camera together. One-level undo is kept for this apply." +
      (
        keepReference
          ? " The full source image will stay aligned behind the posed Person."
          : ""
      ),
    confirmLabel: "Apply pose + camera",
    icon: "warning",
    plan: [
      ["Person", personUid],
      ["Camera", createCamera ? "Create camera" : cameraValue],
      ["Body", app.sam3dSelectedBodyIndex + 1],
      ["Reference", keepReference ? "Keep aligned" : "Do not align"],
    ],
  });
  if (!confirmed) return;

  app.sam3dMutationInFlight = true;
  setButtonBusy(elements.sam3dApplyButton, true, "Applying…");
  renderSam3dApplyState();
  try {
    const request = {
      expected_job_revision: job.revision,
      target_uid: personUid,
      camera_uid: createCamera ? SAM3D_DEFAULT_CAMERA_UID : cameraValue,
      create_camera: createCamera,
      person_index: app.sam3dSelectedBodyIndex,
      height_m: settings.heightM,
      aspect_ratio: settings.aspectRatio,
      output_resolution: settings.outputResolution,
      image_format: settings.imageFormat,
      keep_reference: keepReference,
    };
    if (settings.horizontalFov !== null) {
      request.horizontal_fov = settings.horizontalFov;
    }
    const payload = await Sam3dClient.apply(job.id, request);
    const solutionRevision = String(
      payload.solution_revision || "",
    ).toLowerCase();
    if (!SAM3D_JOB_ID_PATTERN.test(solutionRevision)) {
      throw new Error("The manager returned an invalid solution revision.");
    }
    app.sam3dCaptureReadyJobs.delete(job.id);
    mergeSam3dJob({
      ...job,
      applied: false,
      canUndo: false,
      captured: false,
      captureRequested: false,
      captureRequestId: "",
      solutionRevision,
      cameraUid: String(payload.camera_uid || request.camera_uid),
      vamActionState: "queued",
      vamActionMessage:
        "Waiting for the VaM bridge to apply the reconstruction.",
    });
    toast(
      "Pose and camera queued",
      "The bridge is applying the reconstruction inside VaM.",
    );
    await loadPersons({ quiet: true });
    await loadSam3dJob(job.id, { quiet: true });
  } catch (error) {
    toast("Could not apply SAM 3D result", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dApplyButton, false);
    renderSam3dWorkspace();
  }
}

async function undoSam3dApply() {
  const job = app.sam3dSelectedJob;
  const solutionRevision = sam3dSolutionRevision(job);
  if (!job || !solutionRevision || elements.sam3dUndoButton.disabled) return;
  app.sam3dMutationInFlight = true;
  setButtonBusy(elements.sam3dUndoButton, true, "Restoring…");
  renderSam3dApplyState();
  try {
    const payload = await Sam3dClient.undo(job.id, solutionRevision);
    mergeSam3dJob({
      ...job,
      vamActionState: String(payload.action_state || "queued"),
      vamActionMessage:
        "Waiting for the VaM bridge to restore the previous state.",
    });
    toast(
      "Previous pose queued for restore",
      "The bridge is restoring its one-level SAM 3D snapshot.",
    );
    await loadPersons({ quiet: true });
    await loadSam3dJob(job.id, { quiet: true });
  } catch (error) {
    toast("Could not undo SAM 3D apply", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dUndoButton, false);
    renderSam3dWorkspace();
  }
}

async function captureSam3dResult() {
  const job = app.sam3dSelectedJob;
  const solutionRevision = sam3dSolutionRevision(job);
  if (!job || !solutionRevision || elements.sam3dCaptureButton.disabled) return;
  const cameraUid = String(job.cameraUid || "").trim();
  if (!cameraUid) {
    toast(
      "Could not capture VaM screenshot",
      "The applied SAM 3D camera identity is unavailable. Refresh the job and scene state.",
      "error",
    );
    return;
  }
  app.sam3dMutationInFlight = true;
  setButtonBusy(elements.sam3dCaptureButton, true, "Capturing…");
  renderSam3dApplyState();
  try {
    const payload = await Sam3dClient.capture(job.id, {
      expected_revision: solutionRevision,
      camera_uid: cameraUid,
    });
    const captureRequestId = String(
      payload.bridge_request || "",
    ).trim();
    app.sam3dSelectedCaptureRequestId = captureRequestId;
    app.sam3dCaptureReadyJobs.delete(job.id);
    mergeSam3dJob({
      ...job,
      applied: true,
      captured: false,
      captureRequested: true,
      captureRequestId,
      solutionRevision,
      cameraUid,
      vamActionState: String(payload.action_state || "queued"),
      vamActionMessage:
        "Waiting for the VaM bridge and renderer to finish the capture.",
    });
    app.sam3dPreviewKind = "result";
    app.sam3dCapturePollAttempts = 0;
    await loadPersons({ quiet: true });
    await loadSam3dJob(job.id, { quiet: true });
    renderSam3dWorkspace();
    toast(
      "VaM screenshot requested",
      "VR Video & Funscript Exporter is rendering the selected frame.",
    );
  } catch (error) {
    toast("Could not capture VaM screenshot", errorMessage(error), "error");
  } finally {
    app.sam3dMutationInFlight = false;
    setButtonBusy(elements.sam3dCaptureButton, false);
    renderSam3dWorkspace();
  }
}

/*
 * Keep the SAM 3D contract above separate from Timeline. Both are live VaM
 * surfaces, but their revision domains and bridge commands are independent.
 */

const TimelineClient = Object.freeze({
  snapshotPath: "/api/vam/timeline",
  controlPath: "/api/vam/timeline/control",

  async snapshot(signal) {
    const payload = await api(this.snapshotPath, { signal });
    return normalizeTimelineSnapshot(payload);
  },

  async control(command) {
    const body = {
      timeline_id: String(command.timelineId),
      expected_revision: String(command.expectedRevision),
      op: String(command.op),
    };
    if (Object.hasOwn(command, "value")) body.value = command.value;
    if (command.op === "selectClip" || command.op === "playClip") {
      if (command.clipId) body.clip_id = String(command.clipId);
    } else if (command.op === "selectSegment") {
      if (command.segmentId) body.segment_id = String(command.segmentId);
    } else if (command.op === "selectLayer") {
      if (command.layerId) body.layer_id = String(command.layerId);
    }
    return api(this.controlPath, { method: "POST", body });
  },
});

function timelineProperty(object, ...names) {
  if (!object || typeof object !== "object") return undefined;
  for (const name of names) {
    if (Object.hasOwn(object, name)) return object[name];
  }
  return undefined;
}

function timelineBoolean(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "true") return true;
  if (value === 0 || value === "0" || value === "false") return false;
  return fallback;
}

function timelineNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function timelineBoundedCount(value, maximum) {
  return Math.min(
    maximum,
    Math.max(0, Math.trunc(timelineNumber(value, 0))),
  );
}

function timelineId(value) {
  if (value === undefined || value === null) return "";
  return String(value);
}

function timelineText(value) {
  if (value === undefined || value === null) return "";
  return String(value);
}

function timelineCollection(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).map(([id, entry]) =>
    entry && typeof entry === "object" ? { id, ...entry } : { id, label: entry },
  );
}

function timelineDataIsTruncated(value) {
  if (value && typeof value === "object") {
    return Object.values(value).some((entry) => timelineBoolean(entry, false));
  }
  return timelineBoolean(value, false);
}

function normalizeTimelineLimits(value, root = false) {
  const source = value && typeof value === "object" ? value : {};
  if (root) {
    return {
      maxInstances: timelineBoundedCount(source.maxInstances, 32),
      maxClips: timelineBoundedCount(source.maxClips, 256),
      maxClipsGlobally: timelineBoundedCount(
        source.maxClipsGlobally,
        1024,
      ),
    };
  }
  return {
    maxSegments: timelineBoundedCount(source.maxSegments, 64),
    maxLayers: timelineBoundedCount(source.maxLayers, 128),
    maxClips: timelineBoundedCount(source.maxClips, 256),
    maxClipsGlobally: timelineBoundedCount(
      source.maxClipsGlobally,
      1024,
    ),
    allocatedClips: timelineBoundedCount(source.allocatedClips, 256),
  };
}

function normalizeTimelineAdapterError(value) {
  if (!value || typeof value !== "object") return null;
  const code = timelineText(value.code)
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "")
    .slice(0, 64);
  const message = timelineText(value.message).slice(0, 500);
  if (!code && !message) return null;
  return {
    code: code || "adapter-error",
    message: message || "Timeline adapter reported an error.",
  };
}

function normalizeTimelineCapabilities(value) {
  const capabilities = new Set();
  if (Array.isArray(value)) {
    for (const entry of value) {
      if (typeof entry === "string" && entry.trim()) {
        capabilities.add(entry.trim());
      } else if (entry && typeof entry === "object") {
        const name = timelineProperty(entry, "id", "name", "capability");
        if (name && timelineBoolean(entry.available, true)) {
          capabilities.add(String(name));
        }
      }
    }
  } else if (value && typeof value === "object") {
    for (const [name, available] of Object.entries(value)) {
      if (timelineBoolean(available, false)) capabilities.add(name);
    }
  } else if (typeof value === "string") {
    for (const name of value.split(",")) {
      if (name.trim()) capabilities.add(name.trim());
    }
  }
  return capabilities;
}

function normalizeTimelineControls(value) {
  const controls = new Set();
  if (Array.isArray(value)) {
    for (const entry of value) {
      const name =
        typeof entry === "string"
          ? entry
          : timelineProperty(entry, "op", "id", "name");
      if (name) controls.add(String(name));
    }
  } else if (value && typeof value === "object") {
    for (const [name, enabled] of Object.entries(value)) {
      if (timelineBoolean(enabled, false)) controls.add(name);
    }
  }
  return controls;
}

function normalizeTimelineNode(entry, index, kind) {
  const source = entry && typeof entry === "object" ? entry : {};
  const id = timelineId(
    timelineProperty(
      source,
      "id",
      `${kind}Id`,
      `${kind}_id`,
      "uid",
      "key",
    ) ?? `${kind}-${index}`,
  );
  return {
    ...source,
    id,
    index: timelineNumber(source.index, index),
    label: String(
      timelineProperty(source, "label", "name", "animation", "displayName") ||
        `${kind[0].toUpperCase()}${kind.slice(1)} ${index + 1}`,
    ),
    segmentId: timelineId(
      timelineProperty(source, "segmentId", "segment_id", "segment"),
    ),
    layerId: timelineId(
      timelineProperty(source, "layerId", "layer_id", "layer"),
    ),
    duration: Math.max(
      0,
      timelineNumber(
        timelineProperty(source, "duration", "length", "clipLength"),
        0,
      ),
    ),
    playing: timelineBoolean(
      timelineProperty(source, "playing", "isPlaying", "is_playing"),
      false,
    ),
    tracks: timelineCollection(
      timelineProperty(source, "tracks", "targets", "graph"),
    ),
  };
}

function normalizeTimelineInstance(entry, index, rootCapabilities) {
  const source = entry && typeof entry === "object" ? entry : {};
  const transport =
    timelineProperty(source, "transport", "playback") || {};
  const current =
    timelineProperty(source, "current", "selection", "selected") || {};
  const atomValue = timelineProperty(source, "atom", "atomUid", "atom_uid");
  const atom =
    atomValue && typeof atomValue === "object"
      ? atomValue
      : { uid: timelineId(atomValue) };
  const id = timelineId(
    timelineProperty(source, "id", "timelineId", "timeline_id", "instanceId") ||
      `${timelineProperty(atom, "uid", "id", "name") || "timeline"}-${index}`,
  );
  const capabilities = new Set(rootCapabilities);
  for (const capability of normalizeTimelineCapabilities(source.capabilities)) {
    capabilities.add(capability);
  }
  const controls = normalizeTimelineControls(source.controls);
  const enhanced = timelineBoolean(
    timelineProperty(source, "enhanced", "adapterAvailable", "adapter_available"),
    false,
  );
  const ready = timelineBoolean(source.ready, enhanced || controls.size > 0);
  if (controls.size > 0) capabilities.add("timeline-transport");
  if (enhanced) {
    capabilities.add("timeline-model-read");
    capabilities.add("timeline-selection");
  }

  const time = Math.max(
    0,
    timelineNumber(
      timelineProperty(transport, "clipTime", "clip_time") ??
        timelineProperty(current, "clipTime", "clip_time") ??
        timelineProperty(transport, "time", "currentTime", "current_time") ??
        timelineProperty(current, "time", "currentTime", "current_time"),
      0,
    ),
  );
  const duration = Math.max(
    0,
    timelineNumber(
      timelineProperty(transport, "clipDuration", "clip_duration") ??
        timelineProperty(current, "clipDuration", "clip_duration") ??
        timelineProperty(transport, "duration", "length") ??
        timelineProperty(current, "duration", "length"),
      0,
    ),
  );
  return {
    raw: source,
    id,
    revision: timelineId(
      timelineProperty(
        source,
        "revision",
        "catalogRevision",
        "catalog_revision",
      ),
    ),
    stateSequence: timelineId(
      timelineProperty(source, "stateSequence", "state_sequence"),
    ),
    atomUid: timelineId(
      timelineProperty(atom, "uid", "id", "name") ||
        timelineProperty(source, "atomUid", "atom_uid"),
    ),
    label: String(
      source.label ||
        timelineProperty(atom, "label", "uid", "name") ||
        `Timeline ${index + 1}`,
    ),
    selected: timelineBoolean(source.selected, false),
    enhanced,
    ready,
    adapterVersion: String(
      timelineProperty(source, "adapterVersion", "adapter_version") || "",
    ),
    error: normalizeTimelineAdapterError(source.error),
    capabilities,
    controls,
    current: {
      segmentId: timelineId(
        timelineProperty(current, "segmentId", "segment_id"),
      ),
      layerId: timelineId(
        timelineProperty(current, "layerId", "layer_id"),
      ),
      clipId: timelineId(
        timelineProperty(
          current,
          "clipId",
          "clip_id",
          "animationId",
          "animation_id",
        ),
      ),
      trackId: timelineId(
        timelineProperty(current, "trackId", "track_id", "targetId", "target_id"),
      ),
      qualified: timelineText(
        timelineProperty(
          current,
          "qualified",
          "qualifiedName",
          "qualified_name",
        ),
      ),
      name: timelineText(
        timelineProperty(current, "name", "clipName", "clip_name", "animation"),
      ),
      segment: timelineText(
        timelineProperty(current, "segment", "segmentName", "segment_name"),
      ),
      layer: timelineText(
        timelineProperty(current, "layer", "layerName", "layer_name"),
      ),
    },
    transport: {
      playing: timelineBoolean(
        timelineProperty(transport, "playing", "isPlaying", "is_playing"),
        false,
      ),
      paused: timelineBoolean(transport.paused, false),
      locked: timelineBoolean(
        timelineProperty(transport, "locked", "isLocked", "is_locked"),
        false,
      ),
      time: Math.min(time, duration || time),
      duration,
      speed: timelineNumber(transport.speed, 1),
      weight: Math.min(1, Math.max(0, timelineNumber(transport.weight, 1))),
    },
    segments: timelineCollection(source.segments).map((item, itemIndex) =>
      normalizeTimelineNode(item, itemIndex, "segment"),
    ),
    layers: timelineCollection(source.layers).map((item, itemIndex) =>
      normalizeTimelineNode(item, itemIndex, "layer"),
    ),
    clips: timelineCollection(
      timelineProperty(source, "clips", "animations"),
    ).map((item, itemIndex) => normalizeTimelineNode(item, itemIndex, "clip")),
    tracks: timelineCollection(
      timelineProperty(source, "tracks", "targets", "graph"),
    ),
    counts:
      source.counts && typeof source.counts === "object" ? source.counts : {},
    limits: normalizeTimelineLimits(source.limits),
    truncated: timelineProperty(source, "truncated", "isTruncated") || false,
  };
}

function normalizeTimelineSnapshot(payload) {
  const source =
    payload?.timeline && typeof payload.timeline === "object"
      ? payload.timeline
      : payload || {};
  const capabilities = normalizeTimelineCapabilities(source.capabilities);
  const bridge =
    source.bridge && typeof source.bridge === "object" ? source.bridge : {};
  const instances = timelineCollection(source.instances).map((entry, index) =>
    normalizeTimelineInstance(entry, index, capabilities),
  );
  return {
    raw: source,
    available: timelineBoolean(source.available, instances.length > 0),
    vamRunning: timelineBoolean(
      timelineProperty(source, "vam_running", "vamRunning"),
      true,
    ),
    loading: timelineBoolean(source.loading, false),
    stale: timelineBoolean(
      source.stale ?? timelineProperty(bridge, "stale", "is_stale"),
      false,
    ),
    protocol: String(
      timelineProperty(source, "timeline_protocol", "timelineProtocol", "protocol") ||
        "",
    ),
    instances,
    truncated: timelineProperty(source, "truncated", "isTruncated") || false,
    counts:
      source.counts && typeof source.counts === "object" ? source.counts : {},
    limits: normalizeTimelineLimits(source.limits, true),
    capabilities,
    bridge,
    updatedAt: String(
      timelineProperty(source, "updated_at_utc", "updatedAtUtc", "updated_at") ||
        "",
    ),
  };
}

function timelineCurrentSignature(instance) {
  if (!instance) return "";
  return [
    instance.current.segmentId,
    instance.current.layerId,
    instance.current.clipId,
    instance.current.segment,
    instance.current.layer,
    instance.current.name,
    instance.current.qualified,
  ].join(":");
}

function timelineCurrentIdentity(instance, kind) {
  const current = instance?.current;
  if (!current) return { id: "", label: "" };
  if (kind === "segment") {
    return {
      id: current.segmentId,
      label: current.segment,
    };
  }
  if (kind === "layer") {
    return {
      id: current.layerId,
      label: [current.segment, current.layer].filter(Boolean).join(" · "),
    };
  }
  return {
    id: current.clipId,
    label:
      current.qualified ||
      [current.segment, current.layer, current.name]
        .filter(Boolean)
        .join(" · "),
  };
}

function timelineCollectionForKind(instance, kind) {
  if (!instance) return [];
  if (kind === "segment") return instance.segments;
  if (kind === "layer") return instance.layers;
  return instance.clips;
}

function timelineCurrentOutsidePublishedWindow(instance, kind = "clip") {
  const identity = timelineCurrentIdentity(instance, kind);
  if (!identity.id && !identity.label) return false;
  return !timelineCollectionForKind(instance, kind).some(
    (item) => identity.id && item.id === identity.id,
  );
}

function timelineSelectionFromCurrent(instance, kind, items) {
  const identity = timelineCurrentIdentity(instance, kind);
  if (identity.id && items.some((item) => item.id === identity.id)) {
    return identity.id;
  }
  if (identity.id || identity.label) return "";
  return items[0]?.id || "";
}

function timelineOutsideOptionLabel(instance, kind) {
  const label = timelineCurrentIdentity(instance, kind).label || "unnamed";
  return `Current · ${label} · outside published window`;
}

function selectedTimelineInstance() {
  const instances = app.timeline?.instances || [];
  return (
    instances.find((instance) => instance.id === app.selectedTimelineId) ||
    instances.find((instance) => instance.selected) ||
    instances[0] ||
    null
  );
}

function selectedTimelineClip(instance = selectedTimelineInstance()) {
  if (!instance) return null;
  const clips = timelineClipsForSelection(instance);
  if (app.selectedTimelineClipId) {
    return (
      clips.find(
        (clip) => clip.id === app.selectedTimelineClipId,
      ) || null
    );
  }
  const current = clips.find(
    (clip) => clip.id === instance.current.clipId,
  );
  if (current) return current;
  if (timelineCurrentOutsidePublishedWindow(instance, "clip")) return null;
  return clips[0] || null;
}

function acceptTimelineSnapshot(snapshot) {
  const previous = selectedTimelineInstance();
  const previousSignature = timelineCurrentSignature(previous);
  app.timeline = snapshot;
  app.timelineError = null;
  app.timelineReceivedAt = performance.now();

  const instances = snapshot.instances;
  let instance = instances.find(
    (candidate) => candidate.id === app.selectedTimelineId,
  );
  if (!instance) {
    instance = instances.find((candidate) => candidate.selected) || instances[0];
    app.selectedTimelineId = instance?.id || "";
    syncTimelineSelectionFromInstance(instance);
  } else if (
    previous &&
    timelineCurrentSignature(instance) !== previousSignature &&
    !app.timelineControlInFlight &&
    !app.timelineSeekInFlight
  ) {
    syncTimelineSelectionFromInstance(instance);
  } else {
    ensureTimelineSelectionExists(instance);
  }
}

function syncTimelineSelectionFromInstance(instance) {
  if (!instance) {
    app.selectedTimelineSegmentId = "";
    app.selectedTimelineLayerId = "";
    app.selectedTimelineClipId = "";
    return;
  }
  app.selectedTimelineSegmentId = timelineSelectionFromCurrent(
    instance,
    "segment",
    instance.segments,
  );
  const layers = timelineLayersForSegment(instance);
  app.selectedTimelineLayerId = timelineSelectionFromCurrent(
    instance,
    "layer",
    layers,
  );
  app.selectedTimelineClipId = timelineSelectionFromCurrent(
    instance,
    "clip",
    timelineClipsForSelection(instance),
  );
}

function ensureTimelineSelectionExists(instance) {
  if (!instance) {
    syncTimelineSelectionFromInstance(null);
    return;
  }
  if (
    !instance.segments.some(
      (segment) => segment.id === app.selectedTimelineSegmentId,
    )
  ) {
    app.selectedTimelineSegmentId = timelineSelectionFromCurrent(
      instance,
      "segment",
      instance.segments,
    );
  }
  const layers = timelineLayersForSegment(instance);
  if (
    !layers.some((layer) => layer.id === app.selectedTimelineLayerId)
  ) {
    app.selectedTimelineLayerId = timelineSelectionFromCurrent(
      instance,
      "layer",
      layers,
    );
  }
  const clips = timelineClipsForSelection(instance);
  if (!clips.some((clip) => clip.id === app.selectedTimelineClipId)) {
    app.selectedTimelineClipId = timelineSelectionFromCurrent(
      instance,
      "clip",
      clips,
    );
  }
}

function timelineLayersForSegment(instance) {
  if (!instance) return [];
  const selected = app.selectedTimelineSegmentId;
  const filtered = instance.layers.filter(
    (layer) => !selected || !layer.segmentId || layer.segmentId === selected,
  );
  return selected ? filtered : instance.layers;
}

function timelineClipsForSelection(instance) {
  if (!instance) return [];
  const segmentId = app.selectedTimelineSegmentId;
  const layerId = app.selectedTimelineLayerId;
  const filtered = instance.clips.filter(
    (clip) =>
      (!segmentId || !clip.segmentId || clip.segmentId === segmentId) &&
      (!layerId || !clip.layerId || clip.layerId === layerId),
  );
  return segmentId || layerId ? filtered : instance.clips;
}

function timelineTracksForSelection(instance = selectedTimelineInstance()) {
  if (!instance) return [];
  const clip = selectedTimelineClip(instance);
  const source = clip?.tracks.length
    ? clip.tracks
    : timelineCollection(
        timelineProperty(instance.raw.current, "tracks", "targets", "graph"),
      ).length
      ? timelineCollection(
          timelineProperty(instance.raw.current, "tracks", "targets", "graph"),
        )
      : instance.tracks;
  return source.slice(0, MAX_TIMELINE_TRACKS);
}

async function loadTimeline({ quiet = false } = {}) {
  if (app.timelineInFlight) return app.timeline;
  app.timelineInFlight = true;
  if (!quiet && !app.timeline) {
    app.timelineError = null;
    renderTimeline();
  }
  try {
    const snapshot = await TimelineClient.snapshot();
    acceptTimelineSnapshot(snapshot);
    renderTimeline();
    return snapshot;
  } catch (error) {
    app.timelineError = error;
    if (app.timeline) app.timeline.stale = true;
    renderTimeline();
    return null;
  } finally {
    app.timelineInFlight = false;
    scheduleTimelinePoll();
  }
}

function startTimelinePolling() {
  if (app.managerAuthFailed || app.view !== "timeline") return;
  scheduleTimelinePoll(50);
}

function stopTimelinePolling() {
  if (app.timelinePollTimer !== null) {
    window.clearTimeout(app.timelinePollTimer);
    app.timelinePollTimer = null;
  }
  if (app.timelineRenderFrame !== null) {
    window.cancelAnimationFrame(app.timelineRenderFrame);
    app.timelineRenderFrame = null;
  }
}

function scheduleTimelinePoll(delay = null) {
  if (app.managerAuthFailed || app.view !== "timeline") return;
  if (app.timelinePollTimer !== null) {
    window.clearTimeout(app.timelinePollTimer);
  }
  const instance = selectedTimelineInstance();
  const pollDelay =
    delay ??
    (instance?.transport.playing && !instance.transport.paused
      ? TIMELINE_PLAYING_POLL_MS
      : TIMELINE_IDLE_POLL_MS);
  app.timelinePollTimer = window.setTimeout(() => {
    app.timelinePollTimer = null;
    loadTimeline({ quiet: true });
  }, pollDelay);
}

function timelineSnapshotState(snapshot = app.timeline) {
  if (app.timelineError && !snapshot) {
    return {
      kind: "error",
      title:
        app.timelineError.status === 404
          ? "Timeline support is not available yet"
          : "Could not read Timeline",
      message:
        app.timelineError.status === 404
          ? "Update the VAM-PIP manager and bridge together, then reload this page."
          : errorMessage(app.timelineError),
    };
  }
  if (!snapshot) {
    return {
      kind: "loading",
      title: "Connecting to Timeline",
      message: "Waiting for the VAM-PIP bridge to publish the current scene.",
    };
  }
  if (!snapshot.vamRunning) {
    return {
      kind: "empty",
      title: "VaM is closed",
      message: "Start VaM and load a scene to discover its Timeline instances.",
    };
  }
  if (snapshot.loading) {
    return {
      kind: "loading",
      title: "Scene is loading",
      message: "Timeline controls will unlock when VaM publishes the new scene.",
    };
  }
  if (snapshot.stale) {
    return {
      kind: "warning",
      title: "Timeline state is stale",
      message:
        "The bridge has stopped updating. Controls are disabled until a fresh scene snapshot arrives.",
    };
  }
  if (!snapshot.available) {
    return {
      kind: "warning",
      title: "Timeline bridge is unavailable",
      message:
        timelineProperty(snapshot.bridge, "message", "detail") ||
        "Reload the VAM-PIP session bridge in VaM, then retry.",
    };
  }
  if (!snapshot.instances.length) {
    return {
      kind: "empty",
      title: "No Timeline instance in this scene",
      message:
        "Add VamTimeline.AtomPlugin to an atom in VaM. It will appear here automatically.",
    };
  }
  return null;
}

function setTimelineStatePanel(state) {
  const panel = elements.timelineStatePanel;
  panel.classList.remove("is-error", "is-warning", "is-empty", "is-loading");
  if (!state) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.classList.add(`is-${state.kind}`);
  elements.timelineStateTitle.textContent = state.title;
  elements.timelineStateMessage.textContent = state.message;
  elements.timelineRetryButton.hidden = state.kind === "loading";
}

function renderTimeline() {
  const snapshot = app.timeline;
  const state = timelineSnapshotState(snapshot);
  const instance = selectedTimelineInstance();
  const usableEditor = Boolean(instance);

  elements.timelineTabCount.textContent = snapshot
    ? formatCompact(snapshot.instances.length)
    : "—";
  elements.timelineInstance.replaceChildren();
  if (snapshot?.instances.length) {
    for (const candidate of snapshot.instances) {
      const suffix = candidate.enhanced ? "" : " · transport only";
      elements.timelineInstance.append(
        new Option(
          `${candidate.label}${candidate.atomUid ? ` · ${candidate.atomUid}` : ""}${suffix}`,
          candidate.id,
        ),
      );
    }
    elements.timelineInstance.value = instance?.id || "";
  } else {
    elements.timelineInstance.append(
      new Option(
        app.timelineInFlight ? "Checking the scene…" : "No Timeline instances",
        "",
      ),
    );
  }
  elements.timelineInstance.disabled =
    !snapshot || snapshot.stale || snapshot.instances.length < 2;

  const connected =
    Boolean(snapshot?.available) &&
    Boolean(snapshot?.vamRunning) &&
    !snapshot?.stale;
  elements.timelineConnectionState.classList.toggle(
    "is-connected",
    connected,
  );
  elements.timelineConnectionState.classList.toggle(
    "is-error",
    Boolean(app.timelineError),
  );
  elements.timelineConnectionLabel.textContent = app.timelineError
    ? "Timeline unavailable"
    : !snapshot
      ? "Checking Timeline…"
      : connected
      ? `${snapshot.instances.length} live instance${snapshot.instances.length === 1 ? "" : "s"}`
      : snapshot?.vamRunning
        ? "Waiting for Timeline"
        : "VaM closed";

  setTimelineStatePanel(state);
  elements.timelineEditor.hidden = !usableEditor;
  if (!usableEditor) return;

  renderTimelineSelectors(instance);
  renderTimelineOutline(instance);
  renderTimelineInspector(instance);
  renderTimelineTransport(instance);
  drawTimelineCanvas();
  if (instance.transport.playing && !instance.transport.paused) {
    startTimelineRenderLoop();
  }

  if (instance.error && !state) {
    setTimelineStatePanel({
      kind: "error",
      title: `Timeline adapter error · ${instance.error.code}`,
      message: instance.error.message,
    });
  } else if (!instance.enhanced && !state) {
    setTimelineStatePanel({
      kind: "warning",
      title: "Transport-only Timeline",
      message:
        "Playback controls are available. Install and load the enhanced Timeline adapter for exact selections and graph data.",
    });
  } else if (!instance.ready && !state) {
    setTimelineStatePanel({
      kind: "warning",
      title: "Timeline adapter is initializing",
      message:
        "The instance was found, but its external state is not ready. Controls remain disabled for now.",
    });
  } else if (
    timelineCurrentOutsidePublishedWindow(instance, "clip") &&
    !state
  ) {
    const currentLabel =
      timelineCurrentIdentity(instance, "clip").label || "Unnamed clip";
    setTimelineStatePanel({
      kind: "warning",
      title: "Current clip outside published window",
      message:
        `VaM is currently on “${currentLabel}”, which is beyond this bounded catalogue. ` +
        "VAM-PIP has not selected a different clip in its place; choose a published clip explicitly to switch.",
    });
  } else if (
    timelineDataIsTruncated(instance.truncated) &&
    !state
  ) {
    const totalClips = timelineBoundedCount(
      instance.counts.clips,
      1_000_000,
    );
    const publishedClips = instance.clips.length;
    const globalLimit =
      instance.limits.maxClipsGlobally ||
      app.timeline?.limits?.maxClipsGlobally ||
      1024;
    setTimelineStatePanel({
      kind: "warning",
      title: "Timeline catalogue is bounded",
      message:
        `${formatNumber(publishedClips)} of ${formatNumber(totalClips)} clips are published for this instance. ` +
        `The shared catalogue limit is ${formatNumber(globalLimit)} clips; playback data and controls remain live.`,
    });
  }
}

function renderTimelineSelectors(instance) {
  const segmentOutside = timelineCurrentOutsidePublishedWindow(
    instance,
    "segment",
  );
  fillTimelineSelect(
    elements.timelineSegmentSelect,
    instance.segments,
    app.selectedTimelineSegmentId,
    "No segments published",
    instance.current.segmentId,
    segmentOutside
      ? timelineOutsideOptionLabel(instance, "segment")
      : "",
    "Choose a published segment",
  );
  const layers = timelineLayersForSegment(instance);
  const layerOutside = timelineCurrentOutsidePublishedWindow(instance, "layer");
  fillTimelineSelect(
    elements.timelineLayerSelect,
    layers,
    app.selectedTimelineLayerId,
    "No layers published",
    instance.current.layerId,
    layerOutside ? timelineOutsideOptionLabel(instance, "layer") : "",
    "Choose a published layer",
  );
  const clips = timelineClipsForSelection(instance);
  const clipOutside = timelineCurrentOutsidePublishedWindow(instance, "clip");
  fillTimelineSelect(
    elements.timelineClipSelect,
    clips,
    app.selectedTimelineClipId,
    "No clips published",
    instance.current.clipId,
    clipOutside ? timelineOutsideOptionLabel(instance, "clip") : "",
    "Choose a published clip",
  );
  const revision = instance.revision || "legacy";
  elements.timelineRevision.textContent =
    revision.length > 14
      ? `${revision.slice(0, 8)}…${revision.slice(-4)}`
      : revision;
  elements.timelineRevision.title =
    revision === "legacy" ? "No revision published" : revision;

  const stale = Boolean(app.timeline?.stale);
  const segmentSelected = instance.segments.some(
    (segment) => segment.id === app.selectedTimelineSegmentId,
  );
  const layerSelected = layers.some(
    (layer) => layer.id === app.selectedTimelineLayerId,
  );
  const clipSelected = clips.some(
    (clip) => clip.id === app.selectedTimelineClipId,
  );
  elements.timelineSegmentSelect.disabled =
    stale ||
    app.timelineControlInFlight ||
    instance.segments.length === 0 ||
    (!segmentOutside && segmentSelected && instance.segments.length < 2);
  elements.timelineLayerSelect.disabled =
    stale ||
    app.timelineControlInFlight ||
    layers.length === 0 ||
    (!layerOutside && layerSelected && layers.length < 2);
  elements.timelineClipSelect.disabled =
    stale ||
    app.timelineControlInFlight ||
    clips.length === 0 ||
    (!clipOutside && clipSelected && clips.length < 2);
}

function fillTimelineSelect(
  select,
  items,
  selectedId,
  emptyLabel,
  liveId,
  outsideLabel = "",
  unselectedLabel = "Choose a published item",
) {
  select.replaceChildren();
  const selectedPublished = items.some((item) => item.id === selectedId);
  if (outsideLabel) {
    const outside = new Option(outsideLabel, "");
    outside.disabled = true;
    select.append(outside);
  } else if (items.length && !selectedPublished) {
    const unselected = new Option(unselectedLabel, "");
    unselected.disabled = true;
    select.append(unselected);
  }
  if (!items.length) {
    if (!outsideLabel) select.append(new Option(emptyLabel, ""));
    select.value = "";
    return;
  }
  for (const item of items) {
    const live = item.id === liveId ? " · live" : "";
    select.append(new Option(`${item.label}${live}`, item.id));
  }
  select.value = selectedPublished ? selectedId : "";
}

function renderTimelineOutline(instance) {
  const clips = timelineClipsForSelection(instance);
  elements.timelineClipCount.textContent = formatCompact(clips.length);
  elements.timelineOutlineList.replaceChildren();
  if (!clips.length) {
    const empty = createElement("p", "timeline-inline-empty");
    empty.textContent = instance.enhanced
      ? "This selection has no clips."
      : "Clip catalogue needs the enhanced adapter.";
    elements.timelineOutlineList.append(empty);
    return;
  }

  const grouped = new Map();
  for (const clip of clips) {
    const layer =
      instance.layers.find((candidate) => candidate.id === clip.layerId) || null;
    const key = layer?.id || "unassigned";
    if (!grouped.has(key)) grouped.set(key, { layer, clips: [] });
    grouped.get(key).clips.push(clip);
  }
  for (const { layer, clips: layerClips } of grouped.values()) {
    const group = createElement("section", "timeline-outline-group");
    const heading = createElement("div", "timeline-outline-group-heading");
    const name = document.createElement("strong");
    name.textContent = layer?.label || "Animation clips";
    const count = document.createElement("span");
    count.textContent = formatCompact(layerClips.length);
    heading.append(name, count);
    group.append(heading);
    for (const clip of layerClips.slice(0, 120)) {
      const clipButton = button(clip.label, "timeline-outline-clip");
      clipButton.dataset.timelineClipId = clip.id;
      clipButton.classList.toggle(
        "is-selected",
        clip.id === app.selectedTimelineClipId,
      );
      clipButton.classList.toggle("is-live", clip.id === instance.current.clipId);
      const duration = createElement("small");
      duration.textContent = formatTimelineTime(
        clip.duration || instance.transport.duration,
      );
      clipButton.append(duration);
      clipButton.addEventListener("click", () =>
        selectTimelineClip(clip.id, { notifyVam: true }),
      );
      group.append(clipButton);
    }
    if (layerClips.length > 120) {
      const limited = createElement("p", "timeline-outline-limit");
      limited.textContent = `${formatNumber(layerClips.length - 120)} more clips are hidden in this bounded view.`;
      group.append(limited);
    }
    elements.timelineOutlineList.append(group);
  }
}

function renderTimelineInspector(instance) {
  const clip = selectedTimelineClip(instance);
  const clipOutside = timelineCurrentOutsidePublishedWindow(instance, "clip");
  const outsideLabel = timelineCurrentIdentity(instance, "clip").label;
  const tracks = timelineTracksForSelection(instance);
  const publishedTrackCount = Math.max(
    tracks.length,
    timelineNumber(
      timelineProperty(clip, "targetCount", "target_count", "trackCount"),
      0,
    ),
  );
  const facts = [
    ["Atom", instance.atomUid || "Unknown"],
    [
      "Clip",
      clip?.label ||
        (clipOutside && outsideLabel
          ? `${outsideLabel} · outside published window`
          : "No clip selected"),
    ],
    ["Duration", formatTimelineTime(clip?.duration || instance.transport.duration)],
    ["Targets", formatNumber(publishedTrackCount)],
    [
      "Catalogue",
      `${formatNumber(instance.clips.length)} of ${formatNumber(
        timelineBoundedCount(instance.counts.clips, 1_000_000),
      )} clips`,
    ],
    ["Adapter", instance.enhanced ? instance.adapterVersion || "Enhanced" : "Legacy"],
  ];
  elements.timelineInspectorFacts.replaceChildren();
  for (const [label, value] of facts) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    elements.timelineInspectorFacts.append(term, description);
  }

  const capabilities = [
    ["Transport", timelineControlAllowed(instance, "play")],
    ["Exact selection", timelineControlAllowed(instance, "selectClip")],
    ["Graph overview", tracks.length > 0],
    [
      "Keyframe editing",
      instance.capabilities.has("timeline-model-edit"),
    ],
  ];
  elements.timelineCapabilityList.replaceChildren();
  for (const [label, available] of capabilities) {
    const row = createElement(
      "span",
      `timeline-capability ${available ? "is-available" : ""}`,
    );
    row.append(createElement("i"));
    row.append(document.createTextNode(label));
    elements.timelineCapabilityList.append(row);
  }
}

function timelineOpKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function timelineControlAllowed(instance, op) {
  if (
    !instance ||
    !instance.ready ||
    !instance.revision ||
    app.timeline?.stale ||
    app.timeline?.loading ||
    !app.timeline?.vamRunning
  ) {
    return false;
  }
  const requested = timelineOpKey(op);
  if (instance.controls.size) {
    return Array.from(instance.controls).some(
      (candidate) => timelineOpKey(candidate) === requested,
    );
  }
  const selectionOps = new Set([
    "selectsegment",
    "selectlayer",
    "selectclip",
  ]);
  if (selectionOps.has(requested)) {
    return instance.enhanced || instance.capabilities.has("timeline-selection");
  }
  return instance.capabilities.has("timeline-transport");
}

function timelineControlTargetIsPublished(instance, op, fields = {}) {
  const requested = timelineOpKey(op);
  if (requested === "selectclip" || requested === "playclip") {
    const clipId = timelineId(fields.clipId);
    return Boolean(
      clipId && instance?.clips.some((clip) => clip.id === clipId),
    );
  }
  if (requested === "selectsegment") {
    const segmentId = timelineId(fields.segmentId);
    return Boolean(
      segmentId &&
        instance?.segments.some((segment) => segment.id === segmentId),
    );
  }
  if (requested === "selectlayer") {
    const layerId = timelineId(fields.layerId);
    return Boolean(
      layerId && instance?.layers.some((layer) => layer.id === layerId),
    );
  }
  return true;
}

function renderTimelineTransport(instance) {
  const time = currentTimelineTime(instance);
  const clip = selectedTimelineClip(instance);
  const duration = Math.max(
    clip?.duration || 0,
    instance.transport.duration || 0,
    0.001,
  );
  const playing = instance.transport.playing && !instance.transport.paused;

  elements.timelinePlayPause.dataset.timelineOp = playing ? "pause" : "play";
  elements.timelinePlayPause.classList.toggle("is-playing", playing);
  elements.timelinePlayPause.setAttribute(
    "aria-label",
    playing ? "Pause" : "Play",
  );
  elements.timelinePlayPause.title = playing ? "Pause" : "Play";

  const controlMap = [
    [elements.timelinePreviousFrame, "previousFrame"],
    [elements.timelineReset, "reset"],
    [elements.timelinePlayPause, playing ? "pause" : "play"],
    [elements.timelineStop, "stop"],
    [elements.timelineNextFrame, "nextFrame"],
  ];
  for (const [control, operation] of controlMap) {
    control.disabled =
      app.timelineControlInFlight ||
      !timelineControlAllowed(instance, operation);
  }

  if (
    document.activeElement !== elements.timelineScrubber ||
    app.timelinePreviewTime === null
  ) {
    elements.timelineScrubber.value = String(Math.min(time, duration));
  }
  elements.timelineScrubber.max = String(duration);
  elements.timelineScrubber.disabled =
    !timelineControlAllowed(instance, "setTime");
  elements.timelineTimecode.value = formatTimelineTime(
    app.timelinePreviewTime ?? time,
  );
  elements.timelineDurationTimecode.textContent =
    `/ ${formatTimelineTime(duration)}`;

  elements.timelineSpeed.value = String(instance.transport.speed);
  elements.timelineSpeedValue.value = `${instance.transport.speed.toFixed(2)}×`;
  elements.timelineSpeed.disabled =
    app.timelineControlInFlight ||
    !timelineControlAllowed(instance, "setSpeed");
  elements.timelineWeight.value = String(instance.transport.weight);
  elements.timelineWeightValue.value =
    `${Math.round(instance.transport.weight * 100)}%`;
  elements.timelineWeight.disabled =
    app.timelineControlInFlight ||
    !timelineControlAllowed(instance, "setWeight");
  elements.timelineLock.checked = instance.transport.locked;
  elements.timelineLock.disabled =
    app.timelineControlInFlight ||
    !timelineControlAllowed(instance, "setLocked");
}

function currentTimelineTime(instance = selectedTimelineInstance()) {
  if (!instance) return 0;
  if (app.timelinePreviewTime !== null) return app.timelinePreviewTime;
  let time = instance.transport.time;
  if (instance.transport.playing && !instance.transport.paused) {
    const elapsed = Math.max(0, performance.now() - app.timelineReceivedAt) / 1000;
    time += elapsed * instance.transport.speed;
  }
  const clip = selectedTimelineClip(instance);
  const duration = clip?.duration || instance.transport.duration;
  return duration > 0
    ? Math.min(duration, Math.max(0, time))
    : Math.max(0, time);
}

function formatTimelineTime(value) {
  const seconds = Math.max(0, timelineNumber(value, 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder
    .toFixed(3)
    .padStart(6, "0")}`;
}

function startTimelineRenderLoop() {
  if (app.timelineRenderFrame !== null || app.view !== "timeline") return;
  const tick = (timestamp) => {
    app.timelineRenderFrame = null;
    if (app.view !== "timeline") return;
    const instance = selectedTimelineInstance();
    let keepRendering = false;
    if (instance && app.timelinePreviewTime === null) {
      const time = currentTimelineTime(instance);
      const duration =
        selectedTimelineClip(instance)?.duration ||
        instance.transport.duration ||
        0.001;
      elements.timelineTimecode.value = formatTimelineTime(time);
      if (document.activeElement !== elements.timelineScrubber) {
        elements.timelineScrubber.value = String(
          Math.min(duration, Math.max(0, time)),
        );
      }
      if (
        instance.transport.playing &&
        !instance.transport.paused &&
        timestamp - app.timelineLastCanvasDrawAt >= 33
      ) {
        keepRendering = true;
        app.timelineLastCanvasDrawAt = timestamp;
        drawTimelineCanvas(time);
      } else if (instance.transport.playing && !instance.transport.paused) {
        keepRendering = true;
      }
    }
    if (keepRendering) {
      app.timelineRenderFrame = window.requestAnimationFrame(tick);
    }
  };
  app.timelineRenderFrame = window.requestAnimationFrame(tick);
}

function timelineTrackKeys(track) {
  const keys = timelineProperty(
    track,
    "keyframes",
    "keys",
    "frames",
    "points",
  );
  return timelineCollection(keys);
}

function timelineKeyTime(key, index) {
  if (Array.isArray(key)) return Math.max(0, timelineNumber(key[0], 0));
  if (typeof key === "number") return Math.max(0, key);
  return Math.max(
    0,
    timelineNumber(
      timelineProperty(key, "time", "t", "x", "seconds", "position"),
      index,
    ),
  );
}

function timelineTrackLabel(track, index) {
  return String(
    timelineProperty(
      track,
      "label",
      "name",
      "target",
      "storable",
      "property",
      "id",
    ) || `Track ${index + 1}`,
  );
}

function drawTimelineCanvas(playhead = null) {
  const canvas = elements.timelineCanvas;
  const scroll = elements.timelineCanvasScroll;
  const context = canvas?.getContext("2d");
  const instance = selectedTimelineInstance();
  if (!canvas || !scroll || !context || !instance) return;

  const tracks = timelineTracksForSelection(instance);
  const clip = selectedTimelineClip(instance);
  const duration = Math.max(
    clip?.duration || 0,
    instance.transport.duration || 0,
    0.001,
  );
  const rowHeight = 31;
  const rulerHeight = 29;
  const cssWidth = Math.max(640, Math.floor(scroll.clientWidth || 960));
  const cssHeight = Math.max(
    220,
    rulerHeight + Math.max(1, tracks.length) * rowHeight,
  );
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.floor(cssWidth * ratio);
  const pixelHeight = Math.floor(cssHeight * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, cssWidth, cssHeight);

  const labelWidth = Math.min(205, Math.max(145, cssWidth * 0.24));
  const graphWidth = Math.max(1, cssWidth - labelWidth);
  context.fillStyle = "#111419";
  context.fillRect(0, 0, cssWidth, cssHeight);
  context.fillStyle = "#171b20";
  context.fillRect(0, 0, labelWidth, cssHeight);
  context.fillStyle = "#1d2228";
  context.fillRect(labelWidth, 0, graphWidth, rulerHeight);

  const majorTicks = Math.max(2, Math.min(12, Math.floor(graphWidth / 90)));
  context.font =
    '10px ui-monospace, "SFMono-Regular", Consolas, monospace';
  context.textBaseline = "middle";
  for (let tick = 0; tick <= majorTicks; tick += 1) {
    const fraction = tick / majorTicks;
    const x = labelWidth + graphWidth * fraction;
    context.strokeStyle = tick === 0 ? "#39424c" : "#252b32";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(Math.round(x) + 0.5, 0);
    context.lineTo(Math.round(x) + 0.5, cssHeight);
    context.stroke();
    context.fillStyle = "#8d98a3";
    context.textAlign =
      tick === 0 ? "left" : tick === majorTicks ? "right" : "center";
    context.fillText(
      formatTimelineTime(duration * fraction),
      tick === 0 ? x + 5 : tick === majorTicks ? cssWidth - 6 : x,
      rulerHeight / 2,
    );
  }
  context.textAlign = "left";

  let renderedKeys = 0;
  let clippedKeys = false;
  for (let trackIndex = 0; trackIndex < tracks.length; trackIndex += 1) {
    const track = tracks[trackIndex];
    const top = rulerHeight + trackIndex * rowHeight;
    if (trackIndex % 2 === 1) {
      context.fillStyle = "rgba(255, 255, 255, 0.014)";
      context.fillRect(0, top, cssWidth, rowHeight);
    }
    context.strokeStyle = "#20262d";
    context.beginPath();
    context.moveTo(0, top + rowHeight + 0.5);
    context.lineTo(cssWidth, top + rowHeight + 0.5);
    context.stroke();
    context.fillStyle = "#a6afb9";
    context.font = '11px Inter, ui-sans-serif, system-ui, sans-serif';
    context.fillText(
      timelineTrackLabel(track, trackIndex),
      12,
      top + rowHeight / 2,
      labelWidth - 24,
    );

    const allKeys = timelineTrackKeys(track);
    const trackKeys = allKeys.slice(0, MAX_TIMELINE_KEYS_PER_TRACK);
    if (allKeys.length > trackKeys.length) clippedKeys = true;
    for (let keyIndex = 0; keyIndex < trackKeys.length; keyIndex += 1) {
      if (renderedKeys >= MAX_TIMELINE_KEYS) {
        clippedKeys = true;
        break;
      }
      const time = timelineKeyTime(trackKeys[keyIndex], keyIndex);
      const x =
        labelWidth + Math.min(1, Math.max(0, time / duration)) * graphWidth;
      const y = top + rowHeight / 2;
      context.save();
      context.translate(Math.round(x), Math.round(y));
      context.rotate(Math.PI / 4);
      context.fillStyle = "#86e6b0";
      context.fillRect(-3, -3, 6, 6);
      context.restore();
      renderedKeys += 1;
    }
    if (renderedKeys >= MAX_TIMELINE_KEYS) break;
  }

  const current = playhead ?? currentTimelineTime(instance);
  const playheadX =
    labelWidth +
    Math.min(1, Math.max(0, current / duration)) * graphWidth;
  context.strokeStyle = "#ff858d";
  context.lineWidth = 1.5;
  context.beginPath();
  context.moveTo(playheadX, 0);
  context.lineTo(playheadX, cssHeight);
  context.stroke();
  context.fillStyle = "#ff858d";
  context.beginPath();
  context.moveTo(playheadX - 5, 0);
  context.lineTo(playheadX + 5, 0);
  context.lineTo(playheadX, 8);
  context.closePath();
  context.fill();

  elements.timelineCanvasEmpty.hidden = tracks.length > 0;
  elements.timelineTrackSummary.textContent = tracks.length
    ? `${formatNumber(tracks.length)} ${plural("track", tracks.length)} · ${formatNumber(renderedKeys)} ${plural("key", renderedKeys)}`
    : "No tracks";
  elements.timelineDurationSummary.textContent = formatTimelineTime(duration);
  const trackSourceCount = Math.max(
    instance.tracks.length,
    clip?.tracks.length || 0,
    timelineNumber(instance.counts.tracks, 0),
  );
  const limited =
    timelineDataIsTruncated(instance.truncated) ||
    timelineDataIsTruncated(app.timeline?.truncated) ||
    trackSourceCount > tracks.length ||
    clippedKeys;
  elements.timelineLimitNote.hidden = !limited;
  elements.timelineLimitNote.textContent = limited
    ? `This overview is bounded to ${MAX_TIMELINE_TRACKS} tracks and ${formatNumber(MAX_TIMELINE_KEYS)} keys; the Timeline data in VaM is unchanged.`
    : "";
}

function handleTimelineCanvasClick(event) {
  const instance = selectedTimelineInstance();
  if (!timelineControlAllowed(instance, "setTime")) return;
  const canvas = elements.timelineCanvas;
  const bounds = canvas.getBoundingClientRect();
  const cssWidth = bounds.width;
  const labelWidth = Math.min(205, Math.max(145, cssWidth * 0.24));
  const x = event.clientX - bounds.left;
  if (x < labelWidth) return;
  const duration =
    selectedTimelineClip(instance)?.duration ||
    instance.transport.duration ||
    0;
  const value =
    ((x - labelWidth) / Math.max(1, cssWidth - labelWidth)) * duration;
  elements.timelineScrubber.value = String(value);
  handleTimelineScrubInput();
  handleTimelineScrubCommit();
}

function handleTimelineScrubInput() {
  const value = Math.max(0, timelineNumber(elements.timelineScrubber.value, 0));
  app.timelinePreviewTime = value;
  elements.timelineTimecode.value = formatTimelineTime(value);
  drawTimelineCanvas(value);
}

function handleTimelineScrubCommit() {
  const value = Math.max(0, timelineNumber(elements.timelineScrubber.value, 0));
  queueTimelineSeek(value);
}

async function queueTimelineSeek(value) {
  const instance = selectedTimelineInstance();
  if (!timelineControlAllowed(instance, "setTime")) return;
  if (app.timelineSeekInFlight) {
    app.timelinePendingSeek = value;
    return;
  }
  app.timelineSeekInFlight = true;
  app.timelinePendingSeek = null;
  try {
    await TimelineClient.control({
      timelineId: instance.id,
      expectedRevision: instance.revision,
      op: "setTime",
      value,
    });
    instance.transport.time = value;
    app.timelineReceivedAt = performance.now();
  } catch (error) {
    toast("Could not seek Timeline", errorMessage(error), "error");
  } finally {
    app.timelineSeekInFlight = false;
    const pending = app.timelinePendingSeek;
    app.timelinePendingSeek = null;
    if (pending !== null) {
      queueTimelineSeek(pending);
    } else {
      app.timelinePreviewTime = null;
      scheduleTimelinePoll(80);
    }
  }
}

async function sendTimelineControl(op, fields = {}) {
  const instance = selectedTimelineInstance();
  if (!timelineControlTargetIsPublished(instance, op, fields)) {
    toast(
      "Selection is outside the published window",
      "Choose an item that is present in the bounded Timeline catalogue before sending this control.",
      "error",
    );
    return;
  }
  if (!timelineControlAllowed(instance, op) || app.timelineControlInFlight) {
    if (!timelineControlAllowed(instance, op)) {
      toast(
        "Control is unavailable",
        "This Timeline instance does not publish that external control.",
        "error",
      );
    }
    return;
  }
  app.timelineControlInFlight = true;
  renderTimelineSelectors(instance);
  renderTimelineTransport(instance);
  try {
    const result = await TimelineClient.control({
      timelineId: instance.id,
      expectedRevision: instance.revision,
      op,
      ...fields,
    });
    if (
      result &&
      typeof result === "object" &&
      (result.instances || result.timeline?.instances)
    ) {
      acceptTimelineSnapshot(normalizeTimelineSnapshot(result));
      renderTimeline();
    } else {
      await loadTimeline({ quiet: true, force: true });
    }
  } catch (error) {
    toast("Timeline control failed", errorMessage(error), "error");
    await loadTimeline({ quiet: true, force: true });
  } finally {
    app.timelineControlInFlight = false;
    const refreshed = selectedTimelineInstance();
    if (refreshed) renderTimeline();
    scheduleTimelinePoll(150);
  }
}

function handleTimelineInstanceChange() {
  app.selectedTimelineId = elements.timelineInstance.value;
  syncTimelineSelectionFromInstance(selectedTimelineInstance());
  app.timelinePreviewTime = null;
  renderTimeline();
}

function handleTimelineSegmentChange() {
  const instance = selectedTimelineInstance();
  const segmentId = timelineId(elements.timelineSegmentSelect.value);
  if (!instance?.segments.some((segment) => segment.id === segmentId)) {
    renderTimeline();
    return;
  }
  app.selectedTimelineSegmentId = segmentId;
  const layers = timelineLayersForSegment(instance);
  app.selectedTimelineLayerId = layers.some(
    (layer) => layer.id === instance.current.layerId,
  )
    ? instance.current.layerId
    : "";
  const clips = timelineClipsForSelection(instance);
  app.selectedTimelineClipId = clips.some(
    (clip) => clip.id === instance.current.clipId,
  )
    ? instance.current.clipId
    : "";
  renderTimeline();
  if (
    app.selectedTimelineSegmentId &&
    timelineControlAllowed(instance, "selectSegment")
  ) {
    sendTimelineControl("selectSegment", {
      segmentId: app.selectedTimelineSegmentId,
    });
  }
}

function handleTimelineLayerChange() {
  const instance = selectedTimelineInstance();
  const layerId = timelineId(elements.timelineLayerSelect.value);
  if (!instance?.layers.some((layer) => layer.id === layerId)) {
    renderTimeline();
    return;
  }
  app.selectedTimelineLayerId = layerId;
  const clips = timelineClipsForSelection(instance);
  app.selectedTimelineClipId = clips.some(
    (clip) => clip.id === instance.current.clipId,
  )
    ? instance.current.clipId
    : "";
  renderTimeline();
  if (
    app.selectedTimelineLayerId &&
    timelineControlAllowed(instance, "selectLayer")
  ) {
    sendTimelineControl("selectLayer", {
      layerId: app.selectedTimelineLayerId,
    });
  }
}

function handleTimelineClipChange() {
  selectTimelineClip(elements.timelineClipSelect.value, { notifyVam: true });
}

function selectTimelineClip(clipId, { notifyVam = false } = {}) {
  const instance = selectedTimelineInstance();
  const requestedId = timelineId(clipId);
  if (!instance?.clips.some((clip) => clip.id === requestedId)) {
    renderTimeline();
    return;
  }
  app.selectedTimelineClipId = requestedId;
  app.timelinePreviewTime = null;
  renderTimeline();
  if (
    notifyVam &&
    app.selectedTimelineClipId &&
    timelineControlAllowed(instance, "selectClip")
  ) {
    sendTimelineControl("selectClip", {
      clipId: app.selectedTimelineClipId,
    });
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

function libraryPaginationState(total, page) {
  const normalizedTotal = Math.max(0, Math.trunc(numberOr(total, 0)));
  const pageCount = Math.max(1, Math.ceil(normalizedTotal / PAGE_SIZE));
  const normalizedPage = Math.min(
    pageCount,
    Math.max(1, Math.trunc(numberOr(page, 1))),
  );
  return {
    total: normalizedTotal,
    page: normalizedPage,
    pageCount,
    offset: (normalizedPage - 1) * PAGE_SIZE,
    hasPrevious: normalizedPage > 1,
    hasNext: normalizedPage < pageCount,
  };
}

function libraryPageCount(total = app.total) {
  return libraryPaginationState(total, 1).pageCount;
}

function packageItemIdentity(item) {
  return String(
    item?.id ??
      item?.package_id ??
      item?.packageId ??
      item?.root ??
      "",
  ).trim();
}

async function findExactPackage(
  params,
  exactPackageId,
  controller,
) {
  const exactKey = String(exactPackageId || "").trim().toLowerCase();
  if (!exactKey) return { items: [], total: 0 };

  const pageParams = new URLSearchParams(params);
  const batchSize = 500;
  let offset = 0;
  let total = 0;
  pageParams.set("limit", String(batchSize));
  pageParams.set("offset", "0");

  do {
    const result = await api(`/api/packages?${pageParams.toString()}`, {
      signal: controller.signal,
    });
    const incoming = Array.isArray(result) ? result : result.items || [];
    total = Math.max(
      0,
      Math.trunc(numberOr(result.total, incoming.length)),
    );
    const exact = incoming.find(
      (item) => packageItemIdentity(item).toLowerCase() === exactKey,
    );
    if (exact) return { items: [exact], total: 1 };
    if (!incoming.length) break;
    offset += incoming.length;
    pageParams.set("offset", String(offset));
  } while (offset < total);

  return { items: [], total: 0 };
}

function changeLibraryPage(page) {
  if (
    app.loading ||
    !["resources", "workspace", "packages"].includes(app.view)
  ) {
    return;
  }
  const nextPage = libraryPaginationState(app.total, page).page;
  if (nextPage === app.page) return;
  loadLibrary({ page: nextPage, scrollToResults: true });
}

function scrollLibraryToStart() {
  const reduceMotion = Boolean(
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  window.requestAnimationFrame(() => {
    elements.resultCount.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "start",
    });
  });
}

async function loadLibrary({
  page = null,
  preservePage = false,
  scrollToResults = false,
} = {}) {
  if (app.view === "access") return;

  if (app.requestController) {
    app.requestController.abort();
  }
  const controller = new AbortController();
  app.requestController = controller;
  app.loading = true;

  const requestedPage =
    page === null ? (preservePage ? app.page : 1) : numberOr(page, 1);
  let resolvedPage = Math.max(1, Math.trunc(requestedPage));
  let offset = (resolvedPage - 1) * PAGE_SIZE;
  app.page = resolvedPage;
  app.offset = offset;
  app.items = [];
  showLoadingState();

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
      if (
        category.operation === "set-person-clothing" &&
        app.selectedPersonUid
      ) {
        params.set("target_uid", app.selectedPersonUid);
      }
    }
  }

  try {
    const packageContentsId =
      app.view === "resources" ? app.packageContentsId : "";
    const endpoint =
      app.view === "packages"
        ? "/api/packages"
        : packageContentsId
          ? `/api/packages/${encodeURIComponent(packageContentsId)}/resources`
          : "/api/resources";
    const exactPackageId =
      app.view === "packages" ? app.exactPackageId : "";
    let incoming;
    let total;
    if (exactPackageId) {
      const exactResult = await findExactPackage(
        params,
        exactPackageId,
        controller,
      );
      if (
        app.view !== "packages" ||
        app.exactPackageId.toLowerCase() !==
          exactPackageId.toLowerCase()
      ) {
        return false;
      }
      incoming = exactResult.items;
      total = exactResult.total;
      resolvedPage = 1;
      offset = 0;
    } else {
      let result = await api(`${endpoint}?${params.toString()}`, {
        signal: controller.signal,
      });
      if (
        app.view === "resources" &&
        app.packageContentsId !== packageContentsId
      ) {
        return false;
      }
      incoming = Array.isArray(result) ? result : result.items || [];
      total = Math.max(
        0,
        Math.trunc(numberOr(result.total, incoming.length)),
      );
      const lastPage = libraryPageCount(total);

      if (total > 0 && resolvedPage > lastPage) {
        resolvedPage = lastPage;
        offset = (resolvedPage - 1) * PAGE_SIZE;
        params.set("offset", String(offset));
        result = await api(`${endpoint}?${params.toString()}`, {
          signal: controller.signal,
        });
        if (
          app.view === "resources" &&
          app.packageContentsId !== packageContentsId
        ) {
          return false;
        }
        incoming = Array.isArray(result) ? result : result.items || [];
        total = Math.max(
          0,
          Math.trunc(numberOr(result.total, incoming.length)),
        );
      } else if (total === 0) {
        resolvedPage = 1;
        offset = 0;
      }
    }

    app.items = incoming;
    app.total = total;
    app.page = resolvedPage;
    app.offset = offset;
    renderLibrary();
    if (scrollToResults) scrollLibraryToStart();
    return true;
  } catch (error) {
    if (error.name !== "AbortError") {
      showErrorState(error);
    }
    return false;
  } finally {
    if (app.requestController === controller) {
      app.loading = false;
      app.requestController = null;
      renderLibraryPagination();
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

  const bridge = app.person?.bridge || status.bridge;
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

function renderLibraryPagination() {
  const pagination = libraryPaginationState(app.total, app.page);
  const hasPages = app.total > PAGE_SIZE && app.items.length > 0;
  elements.libraryPagination.hidden = !hasPages;
  elements.pageStatus.textContent = `Page ${formatNumber(app.page)} of ${formatNumber(
    pagination.pageCount,
  )}`;
  elements.pagePrevious.disabled = app.loading || !pagination.hasPrevious;
  elements.pageNext.disabled = app.loading || !pagination.hasNext;
}

function resourceCardOpener(resourceId) {
  const normalizedId = normalizedResourceId(Number(resourceId));
  if (normalizedId === null) return null;
  return (
    Array.from(
      elements.cardGrid.querySelectorAll(
        ".resource-card-preview-button[data-resource-id]",
      ),
    ).find(
      (candidate) =>
        Number(candidate.dataset.resourceId) === normalizedId,
    ) || null
  );
}

function packageCardOpener(packageId) {
  const normalizedId = String(packageId || "").trim().toLowerCase();
  if (!normalizedId) return null;
  return (
    Array.from(
      elements.cardGrid.querySelectorAll(".package-card[data-package-id]"),
    ).find(
      (candidate) =>
        String(candidate.dataset.packageId || "").trim().toLowerCase() ===
        normalizedId,
    ) || null
  );
}

function renderLibrary() {
  const detailWasOpen = Boolean(elements.resourceDetailDialog?.open);
  const detailResourceId = detailWasOpen
    ? normalizedResourceId(
        Number(elements.resourceDetailDialog.dataset.resourceId),
      )
    : null;
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
    if (app.view === "packages" && app.exactPackageId) {
      const exactKey = app.exactPackageId.toLowerCase();
      const exactCard = Array.from(
        elements.cardGrid.querySelectorAll(".package-card"),
      ).find(
        (candidate) =>
          String(candidate.dataset.packageId || "").toLowerCase() ===
          exactKey,
      );
      if (exactCard) {
        exactCard.tabIndex = -1;
        window.requestAnimationFrame(() => {
          if (
            exactCard.isConnected &&
            app.view === "packages" &&
            app.exactPackageId.toLowerCase() === exactKey
          ) {
            exactCard.focus({ preventScroll: true });
          }
        });
      }
    }
  }

  if (detailWasOpen) {
    const refreshedItem =
      detailResourceId === null
        ? null
        : app.items.find(
            (item) =>
              normalizedResourceId(item?.id ?? item?.resource_id) ===
              detailResourceId,
          );
    const refreshedOpener = resourceCardOpener(detailResourceId);
    if (refreshedItem && refreshedOpener && app.view !== "packages") {
      openResourceDetailDialog(refreshedItem, refreshedOpener);
    } else {
      elements.resourceDetailDialog.close("library-render");
      window.setTimeout(
        () => elements.searchInput.focus({ preventScroll: true }),
        0,
      );
    }
  }

  const noun =
    app.view === "workspace"
      ? currentWorkspaceCategory()?.noun || "asset"
      : app.view === "resources"
        ? "resource"
        : "package";
  const shown = app.items.length;
  const rangeStart = shown > 0 ? app.offset + 1 : 0;
  const rangeEnd = shown > 0 ? Math.min(app.total, app.offset + shown) : 0;
  elements.resultCount.textContent =
    app.offset === 0 && app.total === shown
      ? `${formatNumber(app.total)} ${plural(noun, app.total)}`
      : `Showing ${formatNumber(rangeStart)}–${formatNumber(
          rangeEnd,
        )} of ${formatNumber(app.total)} ${plural(noun, app.total)}`;
  if (app.view === "resources" && app.packageContentsId) {
    elements.resultCount.textContent += ` in “${safePresentationLabel(
      app.packageContentsId,
      "package",
    )}”`;
  }
  renderLibraryPagination();
  updateClearFilters();
}

function showLoadingState() {
  elements.loadingState.hidden = false;
  elements.loadingState.setAttribute("aria-busy", "true");
  elements.cardGrid.hidden = true;
  elements.emptyState.hidden = true;
  elements.libraryPagination.hidden = true;
  elements.pagePrevious.disabled = true;
  elements.pageNext.disabled = true;
  elements.resultCount.textContent =
    app.view === "workspace"
      ? `Loading ${currentWorkspaceCategory()?.label.toLowerCase() || "assets"}…`
      : app.view === "resources"
        ? "Loading resources…"
        : "Loading packages…";
}

function packageScopeCopyConflictCode(error) {
  if (
    app.view !== "resources" ||
    !app.packageContentsId ||
    numberOr(error?.status, 0) !== 409
  ) {
    return "";
  }
  const payload =
    error?.payload &&
    typeof error.payload === "object" &&
    !Array.isArray(error.payload)
      ? error.payload
      : {};
  const code = String(
    error?.code || payload.code || payload.error_code || "",
  )
    .trim()
    .toLowerCase();
  return [
    "package_copy_conflict",
    "package_copy_choice_stale",
  ].includes(code)
    ? code
    : "";
}

function showErrorState(error) {
  elements.loadingState.hidden = true;
  elements.cardGrid.hidden = true;
  elements.emptyState.hidden = false;
  const packageCopyConflict = packageScopeCopyConflictCode(error);
  if (packageCopyConflict) {
    elements.emptyTitle.textContent =
      packageCopyConflict === "package_copy_choice_stale"
        ? "Review package copy"
        : "Choose package copy";
    elements.emptyMessage.textContent =
      `${errorMessage(error)} Choose the copy from a resource’s Dependencies panel, then retry. Use the return bar to go back through the package to the originating resource.`;
    elements.emptyAction.textContent = "Back to package";
    elements.emptyAction.dataset.action = "return-package";
    elements.resultCount.textContent = "Package copy needs attention";
    elements.libraryPagination.hidden = true;
    elements.pagePrevious.disabled = true;
    elements.pageNext.disabled = true;
    return;
  }
  if (app.view === "resources" && app.packageContentsId) {
    elements.emptyTitle.textContent = "Could not open package contents";
    elements.emptyMessage.textContent = errorMessage(error);
    elements.emptyAction.textContent = "Back to package";
    elements.emptyAction.dataset.action = "return-package";
    elements.resultCount.textContent = "Could not open package contents";
    elements.libraryPagination.hidden = true;
    elements.pagePrevious.disabled = true;
    elements.pageNext.disabled = true;
    return;
  }
  elements.emptyTitle.textContent = "The local manager did not respond";
  elements.emptyMessage.textContent = errorMessage(error);
  elements.emptyAction.textContent = "Try again";
  elements.emptyAction.dataset.action = "retry";
  elements.resultCount.textContent = "Could not load library";
  elements.libraryPagination.hidden = true;
  elements.pagePrevious.disabled = true;
  elements.pageNext.disabled = true;
}

function renderEmptyLibrary() {
  const noCatalogue =
    (app.view === "resources" || app.view === "workspace") &&
    !app.packageContentsId &&
    numberOr(app.status && app.status.catalog_resources, 0) === 0 &&
    !hasFilters();

  if (noCatalogue) {
    elements.emptyTitle.textContent = "Import your resource catalogue";
    elements.emptyMessage.textContent =
      "VAM-PIP can browse BrowserAssist’s index while the containing VARs remain hidden.";
    elements.emptyAction.textContent = "Import catalogue";
    elements.emptyAction.dataset.action = "import";
  } else if (
    app.view === "resources" &&
    app.packageContentsId &&
    !hasFilters()
  ) {
    elements.emptyTitle.textContent = "No indexed resources in this package";
    elements.emptyMessage.textContent =
      `The package “${safePresentationLabel(
        app.packageContentsId,
        "package",
      )}” is installed, but its contents did not match any imported catalogue rows.`;
    elements.emptyAction.textContent = "Back to package";
    elements.emptyAction.dataset.action = "return-package";
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
  const model = normalizeResourceCardModel(item, { assumeHidden: true });
  const title = model.title;
  const root = model.packageRef;
  const active = model.active;
  const state = model.state;
  const pinned = isPinned(root);

  const preview = createElement(
    "button",
    "card-preview resource-card-preview-button",
  );
  preview.type = "button";
  preview.setAttribute("aria-label", `Open details for ${title}`);
  preview.setAttribute("aria-haspopup", "dialog");
  preview.setAttribute("aria-controls", "resource-detail-dialog");
  if (model.id !== null) {
    preview.dataset.resourceId = String(model.id);
  }
  preview.title = `Preview ${title}`;
  preview.addEventListener("click", () =>
    openResourceDetailDialog(item, preview),
  );
  const fallback = createElement("span", "preview-fallback");
  fallback.setAttribute("aria-hidden", "true");
  fallback.textContent = initials(title);
  preview.append(fallback);

  const thumbnail =
    model.thumbnail ||
    (model.id !== null ? resourceThumbnailUrl(model.id) : "");
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

  const badges = createElement("span", "card-badges");
  badges.append(badge(prettyType(model.type), "type-badge"));
  const stateLabel = model.stateLabel;
  badges.append(
    badge(
      stateLabel,
      `state-badge ${state === "active" || state === "local" ? "is-active" : "is-hidden"}`,
    ),
  );
  if (
    app.view === "workspace" &&
    isIndividualClothingCategory() &&
    typeof item.worn === "boolean"
  ) {
    badges.append(
      badge(
        item.worn ? "Worn" : "Not worn",
        `state-badge ${item.worn ? "is-active" : "is-hidden"}`,
      ),
    );
  }
  preview.append(badges);
  const openHint = createElement("span", "resource-card-open-hint");
  openHint.textContent = "Preview & details";
  preview.append(openHint);

  const body = createElement("div", "card-body");
  const heading = createElement("h3", "card-title");
  heading.textContent = title;
  heading.title = title;
  body.append(heading);

  const subtitle = createElement("p", "card-subtitle");
  const creatorSpan = createElement("span", "creator");
  creatorSpan.textContent = model.creator;
  subtitle.append(creatorSpan);
  if (model.packageLabel) {
    subtitle.append(document.createTextNode(` · ${model.packageLabel}`));
  }
  body.append(subtitle);

  const metadata = createElement("div", "card-meta");
  const updateVersion = resourceUpdateVersion(item);
  if (updateVersion !== null) {
    metadata.append(
      badge(
        `v${resourceSelectedVersion(item)} → v${updateVersion}`,
        "meta-pill version-update",
      ),
    );
  } else if (
    model.selectedVersion !== null ||
    model.selectedVersionLabel !== "?"
  ) {
    metadata.append(
      badge(`v${model.selectedVersionLabel}`, "meta-pill"),
    );
  }
  if (model.favorite) {
    metadata.append(badge("★ Favorite", "meta-pill variant-favorite"));
  }
  const tags = model.tags;
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
  appendResourceActions(actions, item, model);
  if (actions.children.length) body.append(actions);

  if (preview) card.append(preview);
  card.append(body);
  return card;
}

function appendResourceActions(
  actions,
  item,
  model = normalizeResourceCardModel(item, { assumeHidden: true }),
) {
  const title = model.title;
  const root = model.packageRef;
  const active = model.active;
  const state = model.state;
  const pinned = isPinned(root);
  const workspaceCategory =
    app.view === "workspace" ? currentWorkspaceCategory() : null;
  if (
    workspaceCategory?.operation === "set-person-clothing"
  ) {
    const availability = clothingActionAvailability(item, workspaceCategory);
    if (workspaceCategory.liveAction) {
      const clothingButton = button(
        availability.label,
        item.worn === true ? "secondary-button" : "primary-button",
      );
      clothingButton.disabled = !availability.allowed;
      clothingButton.title = availability.reason;
      clothingButton.addEventListener("click", () =>
        setPersonClothing(item, workspaceCategory, clothingButton),
      );
      actions.append(clothingButton);
      appendResourceUpdateAction(actions, item, {
        disabled: !availability.allowed,
        reason: availability.reason,
        onUpdate: (updateButton, packageVersion) =>
          setPersonClothing(
            item,
            workspaceCategory,
            updateButton,
            packageVersion,
          ),
      });
    }
    if (!availability.allowed) {
      appendPackageAccessActions(actions, item, {
        active,
        state,
        root,
        title,
        pinned,
        includeUpdate: !workspaceCategory.liveAction,
      });
    }
    return;
  }
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
    appendResourceUpdateAction(actions, item, {
      disabled: !availability.allowed,
      reason: availability.reason,
      onUpdate: (updateButton, packageVersion) =>
        applyWorkspaceResource(
          item,
          workspaceCategory,
          updateButton,
          packageVersion,
        ),
    });
    return;
  }

  appendPackageAccessActions(actions, item, {
    active,
    state,
    root,
    title,
    pinned,
  });
}

function appendPackageAccessActions(
  actions,
  item,
  { active, state, root, title, pinned, includeUpdate = true },
) {
  const leaseButton = button(
    active ? "Keep for 3 days" : "Enable for 3 days",
    active ? "secondary-button" : "primary-button",
  );
  const isLocal = state === "local";
  const isMissing = state === "missing";
  const missingStatus = missingResourcePresentation(
    item?.missing_reason,
    isMissing,
  );
  if (isLocal) leaseButton.textContent = "Local · Always available";
  if (isMissing) leaseButton.textContent = missingStatus.label;
  leaseButton.disabled =
    isLocal || isMissing || (!item.id && !root) || !itemIsValid(item);
  if (isLocal) {
    leaseButton.title = "Loose resources are always available";
  } else if (isMissing) {
    leaseButton.title = missingStatus.detail;
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

  if (includeUpdate) {
    appendResourceUpdateAction(actions, item, {
      disabled:
        isLocal ||
        isMissing ||
        (!item.id && !root) ||
        !itemIsValid(item),
      reason: isMissing
        ? missingStatus.detail
        : "Temporarily enable this exact newer version and its dependencies",
      onUpdate: (updateButton, packageVersion) =>
        createThreeDayLease(
          root,
          title,
          updateButton,
          item.id,
          packageVersion,
        ),
    });
  }
}

function resourceUpdateVersion(item) {
  if (!item || item.update_available !== true) return null;
  const version = item.update_version;
  if (
    !Number.isInteger(version) ||
    version < 0 ||
    version > 2_147_483_647
  ) {
    return null;
  }
  return version;
}

function resourceSelectedVersion(item) {
  const selected = item && item.selected_version;
  if (selected !== null && selected !== undefined) {
    const normalized = String(selected).trim();
    if (normalized) return normalized;
  }
  const match = packageRoot(item || {}).match(/\.([0-9]+)$/);
  return match ? match[1] : "?";
}

function appendResourceUpdateAction(
  actions,
  item,
  { onUpdate, disabled = false, reason = "" },
) {
  const packageVersion = resourceUpdateVersion(item);
  if (packageVersion === null || typeof onUpdate !== "function") return null;

  actions.classList.add("has-resource-update");
  const updateButton = button(
    `Update to v${packageVersion}`,
    "secondary-button resource-update-button",
  );
  updateButton.disabled = disabled;
  updateButton.title =
    reason ||
    `Use installed v${packageVersion}; the current version remains available while another lease still needs it`;
  updateButton.addEventListener("click", () =>
    onUpdate(updateButton, packageVersion),
  );
  actions.append(updateButton);
  return updateButton;
}

function isIndividualClothingCategory(
  category = currentWorkspaceCategory(),
) {
  return category?.operation === "set-person-clothing";
}

function selectedPersonSnapshot(snapshot = app.person || {}) {
  return (
    personList(snapshot).find(
      (person) => person.uid === app.selectedPersonUid,
    ) || null
  );
}

function clothingActionAvailability(
  item,
  category = currentWorkspaceCategory(),
) {
  const snapshot = app.person || {};
  const person = selectedPersonSnapshot(snapshot);
  const liveClothing =
    person?.clothing && typeof person.clothing === "object"
      ? person.clothing
      : null;
  const capabilities = personCapabilities(snapshot);
  const resourceId = Number(item.id);
  const itemRevision = String(item.clothing_revision || "");
  const liveRevision = String(liveClothing?.revision || "");
  const key = `${category?.id || "clothing"}:${resourceId}`;
  const state = normalizedResourceState(item, { assumeHidden: true });
  const missingStatus = missingResourcePresentation(
    item?.missing_reason,
    state === "missing",
  );
  let reason = "";

  if (!category || category.operation !== "set-person-clothing") {
    reason = "This is not an individual clothing category";
  } else if (
    app.workspaceCategoriesSource !== "server" ||
    app.workspaceCategoriesError
  ) {
    reason = "Wait for the manager’s current clothing capability map";
  } else if (!category.liveAction) {
    reason = "This manager exposes clothing as browse-only";
  } else if (state === "missing") {
    reason = missingStatus.detail;
  } else if (
    !itemIsValid(item) ||
    !Number.isInteger(resourceId) ||
    resourceId < 1
  ) {
    reason = "This catalogue entry cannot be resolved safely";
  } else if (app.personError) {
    reason = "The live VaM bridge is unavailable";
  } else if (!personVamRunning(snapshot)) {
    reason = "Start VaM before changing clothing";
  } else if (!snapshot.available) {
    reason = "The bridge is not publishing a fresh scene snapshot";
  } else if (!person || !app.selectedPersonUid) {
    reason = "Choose an available Person target first";
  } else if (
    category.requiredCapability &&
    !capabilities.has(category.requiredCapability)
  ) {
    reason = `Update and reload the bridge to enable ${category.requiredCapability}`;
  } else if (snapshot.loading) {
    reason = "Wait for VaM to finish loading the scene";
  } else if (snapshotBridgeBusy(snapshot)) {
    reason = "Wait for the current bridge action to finish";
  } else if (!liveClothing || !liveClothing.ready) {
    reason = "The selected Person has no ready clothing state";
  } else if (item.worn !== true && item.clothing_compatible !== true) {
    reason = "This item is incompatible with the Person’s current gender";
  } else if (typeof item.worn !== "boolean") {
    reason = "The worn-item snapshot is incomplete; refresh before changing it";
  } else if (
    !/^[0-9a-f]{32}$/i.test(itemRevision) ||
    itemRevision !== liveRevision
  ) {
    reason = "The clothing state changed; wait for this card to refresh";
  } else if (item.worn === true && item.clothing_locked === true) {
    reason = "This item is locked in VaM";
  } else if (app.clothingMutationInFlight) {
    reason = "Wait for the current clothing change to finish";
  } else if (app.applyingWorkspaceResources.has(key)) {
    reason = "This clothing change is already being queued";
  }

  let label = item.worn === true
    ? "Remove"
    : state === "active" || state === "local"
      ? "Wear"
      : "Enable & wear";
  if (state === "missing") {
    label = missingStatus.label;
  } else if (item.worn === true && item.clothing_locked === true) {
    label = "Locked in VaM";
  } else if (typeof item.worn !== "boolean") {
    label = "State unavailable";
  }
  return {
    allowed: reason === "",
    label,
    reason,
    revision: itemRevision,
    desiredActive: item.worn !== true,
  };
}

async function setPersonClothing(
  item,
  category,
  sourceButton,
  packageVersion = null,
  desiredActive = null,
) {
  if (app.clothingMutationInFlight) return;
  const availability = clothingActionAvailability(item, category);
  if (!availability.allowed) {
    if (availability.reason) {
      toast("Clothing state changed", availability.reason, "error");
    }
    return;
  }
  const resourceId = Number(item.id);
  const targetUid = app.selectedPersonUid;
  const key = `${category.id}:${resourceId}`;
  const requestedActive =
    typeof desiredActive === "boolean"
      ? desiredActive
      : packageVersion !== null
        ? true
        : availability.desiredActive;
  app.clothingMutationInFlight = true;
  app.applyingWorkspaceResources.add(key);
  setButtonBusy(
    sourceButton,
    true,
    packageVersion !== null && requestedActive
      ? `Updating to v${packageVersion}…`
      : requestedActive
        ? "Wearing…"
        : "Removing…",
  );
  renderCharacterSheet();
  if (app.view === "workspace") renderLibrary();
  try {
    const requestBody = {
      resource_id: resourceId,
      target_uid: targetUid,
      active: availability.desiredActive,
      revision: availability.revision,
      days: 3,
    };
    if (typeof desiredActive === "boolean") {
      requestBody.active = desiredActive;
    } else if (packageVersion !== null) {
      requestBody.active = true;
    }
    if (packageVersion !== null) {
      requestBody.package_version = packageVersion;
    }
    const result = await api("/api/vam/person/clothing", {
      method: "POST",
      body: requestBody,
    });
    requireBridgeQueue(result, "Clothing change");
    toast(
      packageVersion !== null && requestedActive
        ? `Clothing v${packageVersion} queued`
        : requestedActive
          ? "Clothing queued"
          : "Removal queued",
      `${
        requestedActive ? "Wear" : "Remove"
      } “${resourceTitle(item)}” for ${targetUid}.`,
    );
    await refreshAll({ force: true });
  } catch (error) {
    toast(
      `Could not change ${resourceTitle(item)}`,
      errorMessage(error),
      "error",
    );
    if (/revision|stale/i.test(errorMessage(error))) {
      await loadPersons({ quiet: true });
      await loadLibrary({ preservePage: true });
    }
  } finally {
    app.clothingMutationInFlight = false;
    app.applyingWorkspaceResources.delete(key);
    setButtonBusy(sourceButton, false);
    renderCharacterSheet();
    if (app.view === "workspace") renderLibrary();
  }
}

function workspaceActionIsActive(action = app.workspaceAction) {
  return Boolean(action && !action.terminal);
}

function workspaceActionTarget(action) {
  if (!action || action.recovered || !action.title) return "";
  return ` “${action.title}”`;
}

function startWorkspaceActionFeedback(item, category, key, state) {
  const title = resourceTitle(item);
  const noun = prettyType(category.noun);
  const needsPackageEnable = !["active", "local"].includes(state);
  const now = Date.now();
  const action = {
    key,
    resourceId: Number(item.id),
    categoryId: category.id,
    operation: category.operation,
    title,
    noun,
    packageVersion: null,
    needsPackageEnable,
    requestId: "",
    stage: "preparing",
    message: needsPackageEnable
      ? `Resolving dependencies and enabling hidden packages for “${title}”.`
      : `Preparing “${title}” for VaM.`,
    managerProgress: null,
    result: null,
    terminal: false,
    recovered: false,
    toast: null,
    dismissTimer: null,
    startedAt: now,
    lastProgressAt: now,
    previousOperationId: numberOr(app.activity?.operation?.id, 0),
  };
  app.workspaceAction = action;
  action.toast = toast(
    `Preparing ${noun.toLowerCase()}`,
    action.message,
    "busy",
    { persistent: true },
  );
  renderWorkspaceActionFeedback();
  return action;
}

function bindWorkspaceActionRequest(action, result, detail) {
  if (app.workspaceAction !== action || action.terminal) return;
  action.requestId = String(result.bridge_request || "").trim();
  action.result = result;
  action.stage = "queued";
  action.message = detail;
  action.managerProgress = null;
  action.lastProgressAt = Date.now();
  renderWorkspaceActionFeedback();
}

function syncWorkspaceActionActivity(activity = app.activity) {
  const action = app.workspaceAction;
  if (!workspaceActionIsActive(action)) return;
  if (
    Date.now() - numberOr(action.lastProgressAt, action.startedAt) >
    WORKSPACE_ACTION_STALL_MS
  ) {
    finishWorkspaceActionFeedback(
      action,
      false,
      "No progress was reported for five minutes. Check VaM and retry the asset.",
    );
    return;
  }
  if (action.requestId && activity?.vam?.running === false) {
    finishWorkspaceActionFeedback(
      action,
      false,
      "VaM closed before this load finished. Start VaM and retry the asset.",
    );
    return;
  }
  if (action.requestId) return;
  const operation = activity?.operation || {};
  if (!operationIsBusy(activity)) {
    renderWorkspaceActionFeedback();
    return;
  }

  const operationId = numberOr(operation.id, 0);
  if (
    operationId <= numberOr(action.previousOperationId, 0) ||
    operation.run_name !== "managed-reconcile"
  ) {
    renderWorkspaceActionFeedback();
    return;
  }
  const status = String(operation.status || "").toLowerCase();
  const enableTotal = numberOr(operation.enable_total, 0);
  const enabled = Math.min(numberOr(operation.enabled, 0), enableTotal);
  const previousProgress = action.managerProgress || {};
  if (
    previousProgress.status !== status ||
    previousProgress.enableTotal !== enableTotal ||
    previousProgress.enabled !== enabled
  ) {
    action.lastProgressAt = Date.now();
  }
  action.managerProgress = { status, enableTotal, enabled };
  if (enableTotal > enabled) {
    action.stage = "enabling";
  } else if (status === "finalizing") {
    action.stage = "finalizing";
  }
  renderWorkspaceActionFeedback();
}

function recoverWorkspaceActionFeedback(snapshot) {
  const bridge = snapshot?.bridge || {};
  const stage = String(bridge.state || "").toLowerCase();
  const requestId = String(bridge.requestId || "").trim();
  if (
    app.workspaceAction ||
    snapshot?.vam_running !== true ||
    snapshot?.available !== true ||
    !requestId ||
    !PERSON_BRIDGE_BUSY_STATES.has(stage)
  ) {
    return;
  }

  const now = Date.now();
  const action = {
    key: "",
    resourceId: null,
    categoryId: "",
    operation: "",
    title: "",
    noun: "VaM action",
    needsPackageEnable: stage === "rescanning",
    requestId,
    stage,
    message: String(bridge.message || "").trim(),
    managerProgress: null,
    result: null,
    terminal: false,
    recovered: true,
    toast: null,
    dismissTimer: null,
    startedAt: now,
    lastProgressAt: now,
    previousOperationId: numberOr(app.activity?.operation?.id, 0),
  };
  app.workspaceAction = action;
  action.toast = toast(
    "VaM action in progress",
    action.message || "The bridge is processing an earlier request.",
    "busy",
    { persistent: true },
  );
}

function syncWorkspaceActionSnapshot(snapshot = app.person) {
  recoverWorkspaceActionFeedback(snapshot);
  const action = app.workspaceAction;
  if (!workspaceActionIsActive(action) || !action.requestId) return;
  if (snapshot?.vam_running === false) {
    finishWorkspaceActionFeedback(
      action,
      false,
      "VaM closed before this load finished. Start VaM and retry the asset.",
    );
    return;
  }

  const bridge = snapshot?.bridge || {};
  const observedRequestId = String(bridge.requestId || "").trim();
  const lastCompletedRequestId = String(
    bridge.lastCompletedRequestId || "",
  ).trim();
  const stage = String(bridge.state || "").toLowerCase();
  if (observedRequestId !== action.requestId) {
    if (lastCompletedRequestId === action.requestId) {
      finishWorkspaceActionFeedback(
        action,
        true,
        "The action completed in VaM; the bridge has already moved to a newer request.",
      );
      return;
    }
    if (
      observedRequestId &&
      PERSON_BRIDGE_BUSY_STATES.has(stage)
    ) {
      finishWorkspaceActionFeedback(
        action,
        false,
        "The bridge moved to another request before VAM-PIP saw this load finish. Check VaM before retrying; this result is unknown.",
      );
    }
    return;
  }

  if (
    !PERSON_BRIDGE_BUSY_STATES.has(stage) &&
    !["ok", "error"].includes(stage)
  ) {
    return;
  }
  const message = String(bridge.message || "").trim();
  if (action.stage !== stage || action.message !== message) {
    action.lastProgressAt = Date.now();
  }
  action.stage = stage;
  action.message = message;
  if (stage === "ok" || stage === "error") {
    finishWorkspaceActionFeedback(
      action,
      stage === "ok",
      action.message,
    );
    return;
  }
  renderWorkspaceActionFeedback();
}

function finishWorkspaceActionFeedback(action, ok, message) {
  if (!action || app.workspaceAction !== action || action.terminal) return;
  action.terminal = true;
  action.stage = ok ? "ok" : "error";
  action.message = message || (
    ok
      ? `${action.noun}${workspaceActionTarget(action)} finished in VaM.`
      : `${action.noun}${workspaceActionTarget(action)} could not be loaded.`
  );
  renderWorkspaceActionFeedback();
  const dismissAfter = ok ? 5200 : 9000;
  action.dismissTimer = window.setTimeout(() => {
    dismissToast(action.toast);
    if (app.workspaceAction === action) {
      app.workspaceAction = null;
      if (app.view === "workspace") renderLibrary();
    }
  }, dismissAfter);
}

function renderWorkspaceActionFeedback() {
  const action = app.workspaceAction;
  if (!action || !action.toast) return;

  const target = workspaceActionTarget(action);
  let title = `Preparing ${action.noun.toLowerCase()}`;
  let detail = action.message;
  let kind = "busy";
  if (action.stage === "enabling") {
    const progress = action.managerProgress || {};
    title = "Enabling required packages";
    detail = progress.enableTotal
      ? `Enabled ${formatNumber(progress.enabled)} of ${formatNumber(
          progress.enableTotal,
        )} required packages for${target || " the requested asset"}.`
      : `Enabling hidden packages for${target || " the requested asset"}.`;
  } else if (action.stage === "finalizing") {
    title = "Refreshing the package catalogue";
    detail =
      `The required packages are enabled. Preparing${target || " the asset"} for VaM.`;
  } else if (action.stage === "queued") {
    title = `${action.noun} queued`;
    detail =
      action.message ||
      `Waiting for VaM to accept${target || " the requested asset"}.`;
  } else if (action.stage === "deferred-loading") {
    title = "Waiting for VaM";
    detail =
      action.message ||
      "The current scene must finish loading before this request can continue.";
  } else if (action.stage === "rescanning") {
    title = "Registering enabled packages in VaM";
    detail =
      action.message ||
      `VaM is rescanning before it loads${target || " the requested asset"}.`;
  } else if (action.stage === "loading-scene") {
    title = action.recovered
      ? "Loading scene in VaM"
      : `Loading “${action.title}” in VaM`;
    detail = action.message || "VaM is replacing the current scene.";
  } else if (["applying", "adding", "selecting"].includes(action.stage)) {
    title = `${prettyType(action.stage)} ${action.noun.toLowerCase()}`;
    detail =
      action.message ||
      `VaM is processing${target || " the requested asset"}.`;
  } else if (action.stage === "ok") {
    title = action.recovered
      ? "VaM action finished"
      : `${action.noun}${target} loaded`;
    detail = action.message;
    kind = "success";
  } else if (action.stage === "error") {
    title = action.recovered
      ? "VaM action failed"
      : `Could not load${target || ` ${action.noun.toLowerCase()}`}`;
    detail = action.message;
    kind = "error";
  }
  updateToast(action.toast, title, detail, kind);
}

function workspaceApplyAvailability(item, category = currentWorkspaceCategory()) {
  const snapshot = app.person || {};
  const persons = personList(snapshot);
  const selected = app.selectedPersonUid;
  const state = normalizedResourceState(item, { assumeHidden: true });
  const missingStatus = missingResourcePresentation(
    item?.missing_reason,
    state === "missing",
  );
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
    reason = missingStatus.detail;
  } else if (!itemIsValid(item) || !Number.isInteger(resourceId) || resourceId < 1) {
    reason = "This catalogue entry cannot be resolved safely";
  } else if (!category || !category.liveAction) {
    reason = "This category is browse-only with the current manager";
  } else if (
    category.id === "preset-hair" &&
    (app.hairMutationInFlight || app.pendingHairMutation)
  ) {
    reason = "Wait for the pending hair disable to finish in VaM";
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
  } else if (workspaceActionIsActive()) {
    reason = "Wait for the current asset load to finish";
  } else if (operationIsBusy()) {
    reason = "Wait for the current package update to finish";
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
    label = missingStatus.label;
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
  const trackedAction = app.workspaceAction;
  if (
    workspaceActionIsActive(trackedAction) &&
    trackedAction.key === key
  ) {
    if (trackedAction.stage === "enabling") {
      label = "Enabling packages…";
    } else if (trackedAction.stage === "rescanning") {
      label = "Rescanning VaM…";
    } else if (
      ["queued", "deferred-loading"].includes(trackedAction.stage)
    ) {
      label = "Waiting for VaM…";
    } else if (trackedAction.stage === "loading-scene") {
      label = "Loading in VaM…";
    } else {
      label = "Preparing…";
    }
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

function isPackageCopyConflictError(error) {
  const payload =
    error?.payload &&
    typeof error.payload === "object" &&
    !Array.isArray(error.payload)
      ? error.payload
      : {};
  const code = String(
    error?.code || payload.code || payload.error_code || "",
  )
    .trim()
    .toLowerCase();
  const report = normalizeDependencyReport(payload);
  return (
    [
      "package_copy_conflict",
      "package_conflict",
      "same_id_package_conflict",
    ].includes(code) ||
    (numberOr(error?.status, 0) === 409 && report.conflicts.length > 0)
  );
}

function presentPackageCopyConflict(
  item,
  error,
  opener,
  workspaceAction = null,
) {
  const resourceId = normalizedResourceId(
    Number(item?.id ?? item?.resource_id),
  );
  const payload =
    error?.payload &&
    typeof error.payload === "object" &&
    !Array.isArray(error.payload)
      ? error.payload
      : {};
  const report = normalizeDependencyReport(payload);
  if (workspaceAction) {
    if (workspaceAction.dismissTimer) {
      window.clearTimeout(workspaceAction.dismissTimer);
    }
    dismissToast(workspaceAction.toast);
    if (app.workspaceAction === workspaceAction) {
      app.workspaceAction = null;
    }
  }
  app.pendingResourceConflict = { resourceId, payload };
  app.resourceDependencyFocus = true;
  openResourceDetailDialog(item, opener);

  dismissToast(app.packageConflictToast);
  const conflictCount = Math.max(
    1,
    report.conflicts.length,
    report.counts.conflicts,
  );
  const message = `${errorMessage(error)} Choose the correct content below; the choice is global and reversible, then retry the asset.`;
  app.packageConflictToast = toast(
    conflictCount === 1
      ? "Choose a package copy"
      : `Resolve ${formatNumber(conflictCount)} package conflicts`,
    message,
    "error",
    {
      persistent: true,
      actionLabel: "Review choices",
      onAction: () => {
        app.pendingResourceConflict = { resourceId, payload };
        app.resourceDependencyFocus = true;
        openResourceDetailDialog(item, opener);
      },
    },
  );
}

async function applyWorkspaceResource(
  item,
  category,
  sourceButton,
  packageVersion = null,
) {
  const resourceId = Number(item.id);
  if (!Number.isInteger(resourceId) || resourceId < 1 || !category) return;
  if (
    category.id === "preset-hair" &&
    (app.hairMutationInFlight || app.pendingHairMutation)
  ) {
    return;
  }

  const key = `${category.id}:${resourceId}`;
  if (
    app.applyingWorkspaceResources.has(key) ||
    workspaceActionIsActive() ||
    operationIsBusy()
  ) {
    return;
  }
  app.applyingWorkspaceResources.add(key);

  const managedTarget = categoryUsesManagedAtomTarget(category);
  const createIfMissing =
    managedTarget && app.atomTargetMode === "create";
  const merge =
    category.mergeSupported &&
    (!createIfMissing && app.workspaceApplyMode === "merge");
  const atomTargetUid = managedTarget ? activeAtomTargetUid(category) : "";
  let confirmedReplace = false;
  let confirmedRisk = false;
  let action = null;
  try {
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

    const state = String(
      item.state || (itemIsActive(item) ? "active" : "hidden"),
    ).toLowerCase();
    action = startWorkspaceActionFeedback(item, category, key, state);
    if (packageVersion !== null) {
      action.packageVersion = packageVersion;
      action.needsPackageEnable = true;
      action.message =
        `Resolving dependencies and enabling v${packageVersion} of “${action.title}”.`;
      updateToast(
        action.toast,
        `Preparing ${action.noun.toLowerCase()}`,
        action.message,
        "busy",
      );
    }
    if (managedTarget) renderAtomContext();
    setButtonBusy(
      sourceButton,
      true,
      action.needsPackageEnable
        ? "Enabling packages…"
        : category.operation === "load-scene"
          ? "Preparing scene…"
          : "Preparing…",
    );
    if (app.view === "workspace") renderLibrary();

    const body = {
      resource_id: resourceId,
      merge,
      days: 3,
      confirm_critical: confirmedRisk,
      confirm_replace: confirmedReplace,
      create_if_missing: createIfMissing,
    };
    if (packageVersion !== null) {
      body.package_version = packageVersion;
    }
    if (category.targetKind === "person") {
      body.target_uid = app.selectedPersonUid;
    } else if (managedTarget) {
      body.target_uid = atomTargetUid;
    }

    const result = await api("/api/vam/resource/apply", {
      method: "POST",
      body,
    });
    requireWorkspaceBridgeQueue(result, `${prettyType(category.noun)} load`);
    if (createIfMissing) app.pendingAtomUid = atomTargetUid;
    const requestId = result.bridge_request;
    const reconcile = result.lease?.reconcile || {};
    const enabled = numberOr(reconcile.enable, 0);
    const pendingDisable = numberOr(reconcile.pending_disable, 0);
    const packageDetail = [
      enabled
        ? `${formatNumber(enabled)} required ${plural("package", enabled)} enabled`
        : "",
      pendingDisable
        ? `${formatNumber(pendingDisable)} unused ${plural(
            "package",
            pendingDisable,
          )} will stay available until VaM closes`
        : "",
    ].filter(Boolean).join(" · ");
    const detail =
      result.message ||
      `${packageDetail ? `${packageDetail}. ` : ""}Queued ${
        category.targetKind === "person"
          ? `for ${app.selectedPersonUid}`
          : managedTarget
            ? `for ${atomTargetUid}`
            : "for VaM"
      }. VAM-PIP will enable required packages, rescan when needed, and load the asset${
        requestId ? ` · request ${String(requestId).slice(0, 8)}` : ""
      }.`;
    bindWorkspaceActionRequest(action, result, detail);
    await refreshAll({ force: true });
  } catch (error) {
    if (isPackageCopyConflictError(error)) {
      presentPackageCopyConflict(item, error, sourceButton, action);
    } else if (action && !action.requestId) {
      finishWorkspaceActionFeedback(action, false, errorMessage(error));
    } else {
      toast(
        packageVersion !== null
          ? `Could not update ${resourceTitle(item)} to v${packageVersion}`
          : `Could not refresh ${resourceTitle(item)}`,
        errorMessage(error),
        "error",
      );
    }
  } finally {
    app.applyingWorkspaceResources.delete(key);
    setButtonBusy(sourceButton, false);
    if (managedTarget) renderAtomContext();
    if (app.view === "workspace") renderLibrary();
  }
}

function normalizePackageResourceTypes(item) {
  const raw =
    item?.resource_types ??
    item?.resourceTypes ??
    item?.resource_type_counts ??
    [];
  const values =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? Object.entries(raw).map(([type, count]) => ({ type, count }))
      : asArray(raw);
  const seen = new Set();
  const normalized = [];
  for (const entry of values) {
    const type = safePresentationLabel(
      typeof entry === "string"
        ? entry
        : entry?.resource_type ??
            entry?.type ??
            entry?.value ??
            entry?.name,
      "",
    );
    const key = type.toLowerCase();
    if (!type || seen.has(key)) continue;
    seen.add(key);
    const rawCount =
      typeof entry === "object" && entry !== null
        ? entry.count ?? entry.resource_count
        : null;
    const count =
      rawCount === null || rawCount === undefined
        ? null
        : Math.max(0, Math.trunc(numberOr(rawCount, 0)));
    normalized.push({ type, count });
  }
  return normalized;
}

function normalizePackageResourcePreviews(item) {
  const raw =
    item?.resource_previews ??
    item?.representative_resources ??
    item?.representativeResources ??
    item?.preview_resources ??
    [];
  return asArray(raw)
    .filter(
      (entry) =>
        entry &&
        typeof entry === "object" &&
        !Array.isArray(entry),
    )
    .slice(0, MAX_PACKAGE_RESOURCE_PREVIEWS)
    .map((entry) => {
      const model = normalizeResourceCardModel(entry, {
        assumeHidden: true,
        fallbackTitle: "Contained resource",
      });
      return {
        id: model.id,
        title: model.title,
        type: model.type,
        thumbnail:
          model.thumbnail ||
          (model.id !== null ? resourceThumbnailUrl(model.id) : ""),
      };
    });
}

function packageResourceCount(item) {
  const value =
    item?.resource_count ??
    item?.resourceCount ??
    item?.resources_count;
  if (value === null || value === undefined || value === "") return null;
  const count = Number(value);
  if (!Number.isFinite(count)) return null;
  return Math.max(0, Math.trunc(count));
}

function packageResourceTypeCount(item, loadedCount = 0) {
  const value =
    item?.resource_type_count ??
    item?.resourceTypeCount ??
    item?.resources_type_count;
  const safeLoadedCount = Math.max(
    0,
    Math.trunc(numberOr(loadedCount, 0)),
  );
  if (value === null || value === undefined || value === "") {
    return safeLoadedCount;
  }
  return Math.max(
    safeLoadedCount,
    Math.max(0, Math.trunc(numberOr(value, safeLoadedCount))),
  );
}

function createPackageCard(item) {
  const card = createElement(
    "article",
    `library-card package-card${itemIsValid(item) ? "" : " is-invalid"}`,
  );
  const id = String(item.id || item.package_id || packageRoot(item) || "Unknown package");
  card.dataset.packageId = id;
  const root = String(item.id || packageRoot(item) || "");
  const active = itemIsActive(item);
  const valid = itemIsValid(item);
  const pinned = isPinned(root);
  const resourcePreviews = normalizePackageResourcePreviews(item);
  const resourceTypes = normalizePackageResourceTypes(item);
  const resourceCount = packageResourceCount(item);
  const resourceTypeCount = packageResourceTypeCount(
    item,
    resourceTypes.length,
  );
  const hasResourcePreview = valid && resourceCount !== 0;
  if (hasResourcePreview) card.classList.add("has-resource-preview");
  const state = badge(
    valid ? (active ? "Active" : "Hidden") : "Invalid",
    `package-state state-badge ${
      valid ? (active ? "is-active" : "is-hidden") : ""
    }`,
  );

  let preview = null;
  if (hasResourcePreview) {
    preview = button("", "package-preview");
    preview.setAttribute(
      "aria-label",
      resourceCount === null
        ? `Verify and browse the exact contents of ${id}`
        : `Browse ${formatNumber(resourceCount)} BrowserAssist-indexed ${plural(
            "item",
            resourceCount,
          )} in ${id}; exact package contents are verified when opened`,
    );
    preview.title =
      `Browse BrowserAssist’s index, then verify the exact contents of ${id}`;
    preview.disabled = !root;
    if (root) {
      preview.addEventListener("click", () => browsePackageContents(item));
    }

    const previewGrid = createElement(
      "span",
      `package-preview-grid package-preview-count-${Math.max(
        1,
        resourcePreviews.length,
      )}`,
    );
    if (resourcePreviews.length) {
      for (const resource of resourcePreviews) {
        const visual = createElement("span", "package-preview-cell");
        visual.title = `${resource.title} · ${prettyType(resource.type)}`;
        const fallback = createElement("span", "package-preview-initials");
        fallback.setAttribute("aria-hidden", "true");
        fallback.textContent = initials(resource.title);
        visual.append(fallback);
        if (resource.thumbnail) {
          const image = document.createElement("img");
          image.alt = "";
          image.loading = "lazy";
          image.decoding = "async";
          image.addEventListener("load", () =>
            image.classList.add("is-loaded"),
          );
          image.addEventListener("error", () => image.remove());
          image.src = resource.thumbnail;
          visual.append(image);
        }
        previewGrid.append(visual);
      }
    } else {
      const empty = createElement("span", "package-preview-empty");
      const symbol = createElement("strong", "package-symbol");
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = "VAR";
      const message = createElement("span", "package-preview-empty-copy");
      message.textContent = "Indexed candidate previews unavailable";
      empty.append(symbol, message);
      previewGrid.append(empty);
    }
    preview.append(previewGrid, state);

    const previewHint = createElement("span", "package-preview-hint");
    previewHint.textContent =
      resourceCount === null
        ? "Browse exact contents"
        : `${formatNumber(resourceCount)} indexed`;
    preview.append(previewHint);
  }

  const body = createElement("div", "card-body");
  if (!hasResourcePreview) {
    const symbol = createElement("span", "package-symbol");
    symbol.setAttribute("aria-hidden", "true");
    symbol.textContent = valid ? "VAR" : "!";
    body.append(symbol, state);
  }

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
  if (resourceCount !== null) {
    metadata.append(
      badge(
        resourceCount === 0
          ? "No indexed items"
          : `${formatNumber(resourceCount)} indexed`,
        "meta-pill package-resource-count",
      ),
    );
  }
  for (const resourceType of resourceTypes.slice(
    0,
    MAX_PACKAGE_RESOURCE_TYPES,
  )) {
    metadata.append(
      badge(
        `${
          resourceType.count === null
            ? ""
            : `${formatNumber(resourceType.count)} `
        }${prettyType(resourceType.type)}`,
        "meta-pill package-resource-type",
      ),
    );
  }
  if (resourceTypeCount > MAX_PACKAGE_RESOURCE_TYPES) {
    metadata.append(
      badge(
        `+${formatNumber(
          resourceTypeCount - MAX_PACKAGE_RESOURCE_TYPES,
        )} indexed types`,
        "meta-pill package-resource-type",
      ),
    );
  }
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
  actions.classList.add("package-actions");
  if (hasResourcePreview) {
    const browseButton = button(
      "Browse contents",
      "secondary-button package-browse-button",
    );
    browseButton.disabled = !valid || !root;
    browseButton.title =
      `Browse BrowserAssist’s index, then verify the exact contents of ${id}`;
    browseButton.addEventListener("click", () =>
      browsePackageContents(item),
    );
    actions.append(browseButton);
  }
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

  if (preview) card.append(preview);
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

async function createThreeDayLease(
  root,
  label,
  sourceButton,
  resourceId = null,
  packageVersion = null,
) {
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

  setButtonBusy(
    sourceButton,
    true,
    packageVersion === null ? "Resolving…" : `Updating to v${packageVersion}…`,
  );
  try {
    const resourceLeaseBody = { days: 3, label, apply: true };
    if (packageVersion !== null) {
      resourceLeaseBody.package_version = packageVersion;
    }
    const result = resourceId
      ? await api(`/api/resources/${encodeURIComponent(resourceId)}/lease`, {
          method: "POST",
          body: resourceLeaseBody,
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
      packageVersion === null
        ? "Available for 3 days"
        : `v${packageVersion} available for 3 days`,
      `${formatNumber(resolved)} ${plural("package", resolved)} resolved${
        reconcile.bridge_request ? " · live rescan requested" : ""
      }${pending ? ` · ${pending} future disables deferred` : ""}.`,
    );
    await refreshAll();
  } catch (error) {
    toast(
      packageVersion === null
        ? `Could not enable ${label}`
        : `Could not update ${label} to v${packageVersion}`,
      errorMessage(error),
      "error",
    );
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

function setView(
  view,
  {
    deferLibraryLoad = false,
    preserveResourceReturn = false,
  } = {},
) {
  if (
    ![
      "resources",
      "workspace",
      "timeline",
      "sam3d",
      "packages",
      "access",
    ].includes(view) ||
    app.view === view
  ) {
    return;
  }
  if (!preserveResourceReturn) clearResourceReturnContext();
  if (view !== "packages") app.exactPackageId = "";
  if (view !== "resources") app.packageContentsId = "";
  if (elements.resourceDetailDialog?.open) {
    elements.resourceDetailDialog.close("view-change");
  }
  app.view = view;

  for (const tab of elements.viewTabs) {
    const active = tab.dataset.view === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }

  const isAccess = view === "access";
  const isWorkspace = view === "workspace";
  const isTimeline = view === "timeline";
  const isSam3d = view === "sam3d";
  elements.libraryView.hidden = isAccess || isTimeline || isSam3d;
  elements.accessView.hidden = !isAccess;
  elements.timelineView.hidden = !isTimeline;
  elements.sam3dView.hidden = !isSam3d;
  elements.assetWorkspace.hidden = !isWorkspace;
  updateViewRoute(view);
  if (isAccess) {
    stopTimelinePolling();
    stopSam3dPolling();
    stopSam3dBodyProportionPolling();
    renderAccess();
    return;
  }
  if (isTimeline) {
    stopSam3dPolling();
    stopSam3dBodyProportionPolling();
    renderTimeline();
    startTimelinePolling();
    startTimelineRenderLoop();
    loadTimeline({ quiet: Boolean(app.timeline) });
    return;
  }
  if (isSam3d) {
    stopTimelinePolling();
    renderSam3dWorkspace();
    startSam3dBodyProportionPolling();
    loadSam3dWorkspace({ quiet: Boolean(app.sam3dStatus) });
    return;
  }

  stopTimelinePolling();
  stopSam3dPolling();
  stopSam3dBodyProportionPolling();
  elements.typeFilterWrap.hidden = view !== "resources";
  updateWorkspaceSearchPlaceholder();
  configureStateFilter();
  if (isWorkspace) {
    renderWorkspaceCategoryNavigation();
    renderWorkspaceCategorySummary();
    const category = currentWorkspaceCategory();
    if (
      category?.liveAction ||
      categoryUsesPersonContext(category) ||
      ATOM_TARGET_KINDS.has(category?.targetKind)
    ) {
      loadPersons({ quiet: true });
    }
  }
  if (!deferLibraryLoad) loadLibrary();
}

function updateWorkspaceSearchPlaceholder() {
  if (app.view === "workspace") {
    const category = currentWorkspaceCategory();
    elements.searchInput.placeholder = `Search ${category?.label.toLowerCase() || "assets"}, creators, tags…`;
  } else if (app.view === "resources") {
    elements.searchInput.placeholder = app.packageContentsId
      ? `Search inside ${safePresentationLabel(
          app.packageContentsId,
          "package",
        )}…`
      : "Search scenes, looks, clothing, creators…";
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
  ];
  if (!app.packageContentsId) {
    resourceOptions.push(["Local files", "local"]);
  }
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
  app.exactPackageId = "";
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
  } else if (action === "return-package") {
    if (app.resourceReturnContext) {
      returnToResourceContext();
    } else {
      exitPackageContentsScope();
    }
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

function managerAuthBlockedError() {
  const error = new Error(INVALID_MANAGER_TOKEN_MESSAGE);
  error.status = 401;
  error.payload = {
    error: INVALID_MANAGER_TOKEN_MESSAGE,
    status: 401,
  };
  error.managerAuthFailure = true;
  return error;
}

function isInvalidManagerTokenError(error) {
  return (
    Number(error?.status) === 401 &&
    String(error?.message || "")
      .trim()
      .toLowerCase() === INVALID_MANAGER_TOKEN_MESSAGE
  );
}

function isManagerAuthFailure(error) {
  return Boolean(error?.managerAuthFailure);
}

function clearMatchingStoredManagerToken(requestToken) {
  try {
    if (sessionStorage.getItem(TOKEN_KEY) === requestToken) {
      sessionStorage.removeItem(TOKEN_KEY);
    }
  } catch (_error) {
    // A storage-disabled browser can still recover from a fresh fragment token.
  }
}

function stopManagerPollingForAuthFailure() {
  stopActivityPolling();
  stopTimelinePolling();
  stopSam3dPolling();
  stopSam3dBodyProportionPolling();
}

function handleManagerAuthFailure(
  error,
  requestToken,
  requestAuthGeneration,
) {
  if (!isInvalidManagerTokenError(error)) return error;
  error.managerAuthFailure = true;
  const rejectedCurrentToken =
    requestToken === app.token &&
    requestAuthGeneration === app.managerAuthGeneration;
  if (!rejectedCurrentToken) return error;

  clearMatchingStoredManagerToken(requestToken);
  app.token = "";
  app.managerAuthFailed = true;
  app.managerAuthFailedToken = requestToken;
  stopManagerPollingForAuthFailure();
  if (!app.managerAuthNoticeShown) {
    app.managerAuthNoticeShown = true;
    toast(
      "VAM-PIP access expired",
      "The saved browser token no longer matches this manager. Reopen the exact WebUI URL printed by VAM-PIP; its #token=… fragment will reconnect this tab.",
      "error",
      { persistent: true },
    );
  }
  return error;
}

async function api(path, options = {}) {
  if (app.managerAuthFailed) {
    throw managerAuthBlockedError();
  }
  const requestToken = app.token;
  const requestAuthGeneration = app.managerAuthGeneration;
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (requestToken) {
    headers.set("X-VAMPIP-Token", requestToken);
  }

  const request = {
    method,
    headers,
    credentials: "same-origin",
    cache: method === "GET" ? "no-store" : "default",
    signal: options.signal,
  };

  if (method !== "GET" && method !== "HEAD") {
    if (!requestToken) {
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
    error.payload =
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? payload
        : { detail: String(detail) };
    const payloadError =
      error.payload.error &&
      typeof error.payload.error === "object" &&
      !Array.isArray(error.payload.error)
        ? error.payload.error
        : {};
    error.code = String(
      error.payload.code ||
        error.payload.error_code ||
        payloadError.code ||
        "",
    ).trim();
    throw handleManagerAuthFailure(
      error,
      requestToken,
      requestAuthGeneration,
    );
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

function dismissToast(item) {
  if (!item) return;
  const timer = toastTimers.get(item);
  if (timer !== undefined) window.clearTimeout(timer);
  toastTimers.delete(item);
  item.remove();
}

function updateToast(item, title, message, kind = "success") {
  if (!item) return;
  if (
    kind === "error" &&
    String(message || "").trim().toLowerCase() ===
      INVALID_MANAGER_TOKEN_MESSAGE
  ) {
    dismissToast(item);
    return;
  }
  item.classList.toggle("is-error", kind === "error");
  item.classList.toggle("is-busy", kind === "busy");
  item.setAttribute("role", kind === "error" ? "alert" : "status");
  const heading = item.querySelector("strong");
  const detail = item.querySelector("p");
  const close = item.querySelector("[data-toast-close]");
  const action = item.querySelector("[data-toast-action]");
  if (heading) heading.textContent = title;
  if (detail) detail.textContent = message || "";
  if (close) close.hidden = kind === "busy";
  if (action) action.hidden = kind === "busy";
}

function toast(title, message, kind = "success", options = {}) {
  if (
    kind === "error" &&
    String(message || "").trim().toLowerCase() ===
      INVALID_MANAGER_TOKEN_MESSAGE
  ) {
    return null;
  }
  const item = createElement("div", "toast");
  const dot = createElement("span", "toast-dot");
  dot.setAttribute("aria-hidden", "true");
  const content = document.createElement("div");
  const heading = document.createElement("strong");
  const detail = document.createElement("p");
  content.append(heading, detail);
  if (
    safePresentationLabel(options.actionLabel, "") &&
    typeof options.onAction === "function"
  ) {
    const action = button(
      safePresentationLabel(options.actionLabel, "Review"),
      "toast-action",
    );
    action.dataset.toastAction = "true";
    action.addEventListener("click", () => options.onAction(item));
    content.append(action);
  }
  const close = document.createElement("button");
  close.type = "button";
  close.dataset.toastClose = "true";
  close.textContent = "×";
  close.setAttribute("aria-label", "Dismiss notification");
  close.addEventListener("click", () => dismissToast(item));
  item.append(dot, content, close);
  updateToast(item, title, message, kind);
  elements.toastRegion.append(item);
  if (!options.persistent) {
    const timer = window.setTimeout(
      () => dismissToast(item),
      kind === "error" ? 9000 : 5200,
    );
    toastTimers.set(item, timer);
  }
  return item;
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
  const clothingName =
    item.clothing &&
    typeof item.clothing === "object" &&
    item.clothing.display_name;
  if (clothingName) return String(clothingName);
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

function requireWorkspaceBridgeQueue(result, actionLabel) {
  requireBridgeQueue(result, actionLabel);
  if (
    result &&
    typeof result.bridge_request === "string" &&
    result.bridge_request.trim()
  ) {
    return;
  }
  const reason =
    result?.bridge_message ||
    "the manager did not publish a bridge request";
  const leaseNote = result?.lease
    ? " Required packages remain enabled by the new lease."
    : "";
  throw new Error(
    `${actionLabel} was not queued because ${reason}.${leaseNote} Retry after VaM and the bridge are ready.`,
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

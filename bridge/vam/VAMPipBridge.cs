using System;
using System.Collections;
using System.Collections.Generic;
using MVR.FileManagementSecure;
using SimpleJSON;
using UnityEngine;

namespace VAMPip
{
    /// <summary>
    /// Narrow session-plugin bridge between VAM-PIP and VaM.
    ///
    /// The manager owns package and dependency changes. The bridge accepts a
    /// package rescan, one allowlisted resource load, or one bounded atom
    /// action at a time.
    /// </summary>
    public class VAMPipBridge : MVRScript
    {
        private const int ProtocolVersion = 2;
        private const string BridgeVersion = "1.0.0";
        private const int TimelineProtocolVersion = 1;
        private const int Sam3dSolutionSchema = 1;

        private const string PluginDataRoot = "Saves\\PluginData";
        private const string DataRoot = "Saves\\PluginData\\VAMPip";
        private const string BridgeRoot = DataRoot + "\\Bridge";
        private const string RequestPath = BridgeRoot + "\\request.json";
        private const string StatusPath = BridgeRoot + "\\status.json";
        private const string ScenePath = BridgeRoot + "\\scene.json";
        private const string TimelinePath = BridgeRoot + "\\timeline.json";
        private const string Sam3dRoot = DataRoot + "\\SAM3D";
        private const string Sam3dCameraPreset =
            "Custom/Atom/Empty/Preset_VAMPipSAM3DCamera.vap";

        private const int MaximumResourceRefLength = 1000;
        private const int MaximumCuaChoicesPerAtom = 128;
        private const int MaximumCuaChoicesGlobally = 512;
        private const int MaximumCuaChoiceLabelLength = 256;
        private const int MaximumClothingRefsPerPerson = 256;
        private const int MaximumClothingRefsGlobally = 1024;
        private const int MaximumHairItemsPerPerson = 128;
        private const int MaximumHairItemsGlobally = 512;
        private const int MaximumRosterDisplayNameLength = 256;
        private const int MaximumRosterTagLength = 100;
        private const int MaximumRosterTagsPerItem = 32;
        private const int MaximumTimelineInstances = 32;
        private const int MaximumTimelineSegments = 64;
        private const int MaximumTimelineLayers = 128;
        private const int MaximumTimelineClips = 256;
        private const int MaximumTimelineClipsGlobally = 1024;
        private const int MaximumTimelineLabelLength = 256;
        private const int MaximumTimelineQualifiedLength = 512;
        private const int Sam3dControllerCount = 19;
        private const int Sam3dDiagnosticControllerCount = 2;
        private const int Sam3dDiagnosticSchema = 1;
        private const int Sam3dPhysicsResetFrames = 5;
        private const float MaximumSam3dCoordinate = 10.0f;
        private const float Sam3dCaptureWaitSeconds = 300.0f;
        private const float PollIntervalSeconds = 0.5f;
        private const float ScenePublishIntervalSeconds = 1.0f;
        private const float TimelinePublishIntervalSeconds = 1.0f;
        private const float MinimumRescanIntervalSeconds = 5.0f;
        private const float MaximumOperationWaitSeconds = 120.0f;

        private const string CommandRescan = "rescan";
        private const string CommandApplyPersonPreset = "applyPersonPreset";
        private const string CommandAddPerson = "addPerson";
        private const string CommandAddAtom = "addAtom";
        private const string CommandApplyAtomPreset = "applyAtomPreset";
        private const string CommandLoadSubscene = "loadSubscene";
        private const string CommandLoadCustomUnityAsset =
            "loadCustomUnityAsset";
        private const string CommandSelectCustomUnityAssetChoice =
            "selectCustomUnityAssetChoice";
        private const string CommandSetPersonClothingResource =
            "setPersonClothingResource";
        private const string CommandSetPersonHairItem =
            "setPersonHairItem";
        private const string CommandSelectPerson = "selectPerson";
        private const string CommandSelectAtom = "selectAtom";
        private const string CommandLoadScene = "loadScene";
        private const string CommandControlTimeline = "controlTimeline";
        private const string CommandApplySam3dResult = "applySam3dResult";
        private const string CommandUndoSam3dResult = "undoSam3dResult";
        private const string CommandCaptureSam3dResult =
            "captureSam3dResult";
        private const string Sam3dCoordinateSpace =
            "selected-person-hip-relative";
        private const string Sam3dRendererSuffix = "_Eosin.VRRenderer";
        private const string Sam3dCaptureAction = "VAMPipCapture";
        private const string Sam3dRequestIdParam = "VAMPipRequestId";
        private const string Sam3dBaseFilenameParam =
            "VAMPipBaseFilename";
        private const string Sam3dStatusParam = "VAMPipStatus";
        private const string Sam3dLastOutputParam = "VAMPipLastOutput";
        private const string Sam3dErrorParam = "VAMPipError";
        private const string TimelineExternalState =
            "VAM-PIP External State";
        private const string TimelineExternalCommand =
            "VAM-PIP External Command";
        private const string TimelineExternalResult =
            "VAM-PIP External Result";
        private const string TimelineRefreshExternalState =
            "VAM-PIP Refresh External State";
        private const string TimelineExecuteExternalCommand =
            "VAM-PIP Execute External Command";
        private const string StateQueued = "queued";
        private const string StateDeferredLoading = "deferred-loading";
        private const string StateRescanning = "rescanning";
        private const string StateApplying = "applying";
        private const string StateAdding = "adding";
        private const string StateSelecting = "selecting";
        private const string StateLoadingScene = "loading-scene";
        private const string StateApplyingSam3d = "applying-sam3d";
        private const string StateCapturingSam3d = "capturing-sam3d";
        private const string StateOk = "ok";
        private const string StateError = "error";

        // VaM 1.22 native non-Person atom types, audited against
        // BrowserAssist 39's static native-type registry. Custom/package atom
        // types are intentionally browse-only: this must not become an
        // arbitrary AddAtomByType surface.
        private const string AllowedAtomTypes =
            "|AnimationPattern|AnimationStep|AptBook01|AptBook02|" +
            "AptBookShelf|AptChair|AptCoffeeTable|AptJacuzzi|" +
            "AptJacuzziProp|AptJacuzziRailing|AptLamp|AptOutdoorLight|" +
            "AptPatioChair|AptPicture01|AptPicture02|AptPlant|AptPlanter|" +
            "AptRug|AptSmartTV|AptSmartWebTV|AptSofa|AptSpeaker|AptTVStand|" +
            "AudioSource|Button|Capsule|CityScape|CityScapeNight|" +
            "ClothGrabSphere|CollisionTrigger|Crypt|Cube|CustomUnityAsset|" +
            "CyberpunkApartment|CyberpunkApartmentDecor|CyberpunkBed|" +
            "CyberpunkBedPillow01|CyberpunkBedPillow02|" +
            "CyberpunkBedPillow03|CyberpunkChair|CyberpunkCoffeeTable|" +
            "CyberpunkComputer|CyberpunkComputerChair|" +
            "CyberpunkControlScreen|CyberpunkDresser01|" +
            "CyberpunkDresser02|CyberpunkKeyboard|CyberpunkLaptop|" +
            "CyberpunkLight|CyberpunkMouse|CyberpunkMousepad|" +
            "CyberpunkRemote|CyberpunkSofa|CyberpunkSofaCushion01|" +
            "CyberpunkSofaCushion02|CyberpunkTable|CyberpunkTablet|" +
            "CyberpunkWallLight01|CyberpunkWallLight02|CycleForce|" +
            "DecoDowntimeChair|DecoDowntimeCoffeeTable|" +
            "DecoDowntimeSideTable|DecoDowntimeStand|Dildo|DreamHomeTV|" +
            "DreamHomeWebTV|DreamStreetBedroom|DSBR_2TierTable|DSBR_Bed|" +
            "DSBR_BedPillow|DSBR_Bench|DSBR_BuiltInShelves|DSBR_Chair|" +
            "DSBR_DecorativePillow|DSBR_Ottoman|DSBR_Shelf|" +
            "DSBR_ThrowPillow|Empty|Glass|Glass-Stained|GrabPoint|" +
            "ImagePanel|ImagePanelEmissive|ImagePanelTransparent|" +
            "ImagePanelTransparentEmissive|InvisibleLight|InvisiblePanel|" +
            "ISCapsule|ISCone|ISCube|ISCylinder|IslBench|IslFencePost|" +
            "IslFenceSection|IslOverlook|IslPatioChair|IslPlantWFlowers|" +
            "IslPotA|IslPotB|IslPotSmall|IslRailingGlass|IslStool|" +
            "IslTerrain|IslTopiary|IslTree|IslTreePlanter|IslWallPost|" +
            "IslWallSection|ISSphere|ISTube|LookAtTrigger|LoungeChair|" +
            "ModernRoomBed|ModernRoomLargeLamp|OldStyleBed|OldStyleChair|" +
            "OldStylePillow01|OldStylePillow02|OldStyleRoom|" +
            "OldStyleSideTable|OldStyleVanityStool|Paddle|" +
            "PlayerNavigationPanel|ReflectiveSlate|ReflectiveWoodPanel|" +
            "RhythmAudioSource|RhythmForce|SimpleSign|SimSheet|" +
            "SkullQueenSword|Slate|SpaceBox|Sphere|SubScene|SyncForce|" +
            "TechnoDancePole|TechnoGirder|TechnoLight|TechnoLightBar|" +
            "TechnoLightBar+Light|TechnoNeonCircle|" +
            "TechnoNeonCircle+Light|TechnoNeonHeart|" +
            "TechnoNeonHeart+Light|TechnoNeonSquare|" +
            "TechnoNeonSquare+Light|TechnoNeonTriangle|" +
            "TechnoNeonTriangle+Light|TechnoRingLight|" +
            "TechnoRingLight+Light|TechnoRoom|TechnoRoundCage|" +
            "TechnoRoundPlatform|TechnoThrone|Torch|ToyAH|ToyBP|UIButton|" +
            "UISlider|UIText|UIToggle|VaMLogo|VaMSign|VariableTrigger|" +
            "Wall|WebBrowser|WebPanel|WebPanelEmissive|WindowCamera|" +
            "WoodPanel|";

        private sealed class BridgeRequest
        {
            public string RequestId;
            public string Command;
            public string BrowserAssistMode;
            public string TargetUid;
            public string AtomType;
            public string PresetKind;
            public string ResourceRef;
            public bool RescanRequired;
            public bool Merge;
            public bool CreateIfMissing;
            public int ChoiceIndex;
            public string ChoiceToken;
            public bool ClothingActive;
            public string ClothingRevision;
            public string HairRevision;
            public string HairActionToken;
            public string TimelineId;
            public string TimelineRevision;
            public string TimelineOperation;
            public string TimelineItemToken;
            public float TimelineNumberValue;
            public bool TimelineBoolValue;
            public bool HasTimelineValue;
            public string Sam3dJobId;
            public string Sam3dRevision;
            public string Sam3dSolutionSha256;
            public string Sam3dCameraUid;
            public bool Sam3dCreateCamera;
        }

        private sealed class Sam3dControllerSolution
        {
            public string Id;
            public Vector3 Position;
            public Quaternion Rotation;
        }

        private sealed class Sam3dCameraSolution
        {
            public Vector3 Position;
            public Quaternion Rotation;
            public float FlatHorizontalFov;
            public string AspectRatio;
            public string OutputResolution;
            public string ImageFormat;
            public string BaseFilename;
        }

        private sealed class Sam3dSolution
        {
            public string JobId;
            public string Revision;
            public List<Sam3dControllerSolution> Controllers;
            public Sam3dCameraSolution Camera;
        }

        private sealed class Sam3dControllerDiagnostic
        {
            public string Id;
            public bool RequestedCaptured;
            public Vector3 RequestedPosition;
            public Quaternion RequestedRotation;
            public bool ActualCaptured;
            public Vector3 ActualPosition;
            public Quaternion ActualRotation;
            public FreeControllerV3.PositionState PositionState;
            public FreeControllerV3.RotationState RotationState;
            public bool PhysicsEnabled;
            public bool Possessed;
            public bool StartedPossess;
            public bool IsGrabbing;
        }

        private sealed class Sam3dApplyDiagnostics
        {
            public string RequestId;
            public string CapturedAtUtc;
            public string Error;
            public List<Sam3dControllerDiagnostic> Controllers;
        }

        private sealed class Sam3dControllerUndo
        {
            public FreeControllerV3 Controller;
            public Vector3 Position;
            public Quaternion Rotation;
            public FreeControllerV3.PositionState PositionState;
            public FreeControllerV3.RotationState RotationState;
            public bool PhysicsEnabled;
        }

        private sealed class Sam3dUndoSnapshot
        {
            public string JobId;
            public string Revision;
            public string TargetUid;
            public string CameraUid;
            public bool CameraCreated;
            public Atom Person;
            public bool PersonCollisionEnabled;
            public List<Sam3dControllerUndo> Controllers;
            public FreeControllerV3 CameraController;
            public Vector3 CameraPosition;
            public Quaternion CameraRotation;
            public FreeControllerV3.PositionState CameraPositionState;
            public FreeControllerV3.RotationState CameraRotationState;
            public bool CameraPhysicsEnabled;
            public MVRScript Renderer;
            public float FlatHorizontalFov;
            public string CameraTarget;
            public string AspectRatio;
            public string OutputResolution;
            public string RenderMode;
            public string ImageFormat;
            public bool GenerateFunscripts;
            public Sam3dApplyDiagnostics Diagnostics;
        }

        private sealed class Sam3dCameraResult
        {
            public Atom Atom;
            public bool Created;
            public string Error;
        }

        private sealed class AtomCreationResult
        {
            public Atom Atom;
            public bool Created;
            public string Error;
        }

        private sealed class LoadingWaitResult
        {
            public string Error;
        }

        private sealed class CuaChoiceSnapshot
        {
            public Atom Atom;
            public CustomUnityAssetLoader Loader;
            public List<string> ChoiceList;
            public string GenerationKey;
            public string ChoiceToken;
            public List<int> PublishedIndices;
        }

        private sealed class CuaLoaderState
        {
            public CustomUnityAssetLoader Loader;
            public JSONStorableUrl AssetUrl;
            public JSONStorableStringChooser AssetName;
            public JSONStorableBool LoadDll;
            public string Error;
        }

        private sealed class ActiveClothingEntry
        {
            public DAZClothingItem Item;
            public string ResourceRef;
            public string Uid;
            public string InternalUid;
            public string PackageUid;
            public string DisplayName;
            public string[] Tags;
            public bool Locked;
        }

        private sealed class ActiveHairEntry
        {
            public DAZHairGroup Item;
            public string Uid;
            public string InternalUid;
            public string PackageUid;
            public string DisplayName;
            public string[] Tags;
            public bool Locked;
            public bool Simulated;
        }

        private sealed class PersonClothingSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
        }

        private sealed class PersonHairSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
            public List<DAZHairGroup> Items;
            public List<string> ActionTokens;
            public int PublishedCount;
        }

        private sealed class TimelineItemSnapshot
        {
            public string Token;
            public int AdapterId;
            public int AdapterSegmentId;
            public int AdapterLayerId;
            public string Name;
            public string RawName;
            public string Qualified;
            public float Length;
            public float Time;
            public float Speed;
            public float Weight;
            public int TargetCount;
            public bool Loop;
            public bool Playing;
            public bool Main;
            public bool Selected;
        }

        private sealed class TimelineSnapshot
        {
            public Atom Atom;
            public MVRScript Plugin;
            public string StorableId;
            public string TimelineId;
            public string Revision;
            public string GenerationKey;
            public bool Enhanced;
            public int CatalogRevision;
            public List<TimelineItemSnapshot> Segments;
            public List<TimelineItemSnapshot> Layers;
            public List<TimelineItemSnapshot> Clips;
        }

        private sealed class TimelineCandidate
        {
            public int ScanIndex;
            public string Key;
            public Atom Atom;
            public MVRScript Plugin;
            public string StorableId;
            public bool Selected;
            public bool Playing;
            public bool AdapterAvailable;
            public JSONStorableString AdapterState;
            public JSONStorableAction AdapterRefresh;
            public JSONClass Result;
        }

        private bool _operational;
        private bool _requestInProgress;
        private bool _skipPendingProcessing;
        private float _nextPollAt;
        private float _nextScenePublishAt;
        private float _nextTimelinePublishAt;
        private float _nextAllowedRescanAt;
        private string _instanceId = "";
        private string _lastRequestPayload;
        private string _lastHandledRequestId = "";
        private string _lastCompletedRequestId = "";
        private string _lastPublishedStatusSignature = "";
        private string _mailboxRejectedRequestId = "";
        private string _mailboxRejectedMessage = "";
        private BridgeRequest _pendingRequest;
        private readonly Dictionary<string, CuaChoiceSnapshot>
            _cuaChoiceSnapshots =
                new Dictionary<string, CuaChoiceSnapshot>();
        private readonly Dictionary<string, PersonClothingSnapshot>
            _personClothingSnapshots =
                new Dictionary<string, PersonClothingSnapshot>();
        private readonly Dictionary<string, PersonHairSnapshot>
            _personHairSnapshots =
                new Dictionary<string, PersonHairSnapshot>();
        private readonly Dictionary<string, TimelineSnapshot>
            _timelineSnapshots =
                new Dictionary<string, TimelineSnapshot>();
        private Sam3dUndoSnapshot _sam3dUndoSnapshot;
        private string _lastSam3dRequestId = "";
        private string _lastSam3dCommand = "";
        private string _lastSam3dJobId = "";
        private string _lastSam3dRevision = "";
        private string _lastSam3dCameraUid = "";
        private string _lastSam3dState = "";
        private string _lastSam3dMessage = "";

        public override void Init()
        {
            try
            {
                _instanceId = Guid.NewGuid().ToString("N");
                EnsureBridgeDirectory();
                RecoverLastCompletedRequest();
                IgnoreCompletedLegacyRequest();

                if (containingAtom == null ||
                    containingAtom.name != "CoreControl" ||
                    containingAtom.type != "SessionPluginManager")
                {
                    const string message =
                        "VAM-PIP Bridge must be loaded from VaM's Session Plugins screen.";
                    PublishStatus(StateError, "", "", UtcNow(), "", message);
                    SuperController.LogError("[VAM-PIP Bridge] " + message);
                    return;
                }

                _operational = true;
                _nextPollAt = Time.realtimeSinceStartup + 0.25f;
                _nextScenePublishAt = Time.realtimeSinceStartup;
                _nextTimelinePublishAt = Time.realtimeSinceStartup;
                PublishStatus(
                    StateOk,
                    _lastCompletedRequestId,
                    "",
                    "",
                    "",
                    "Bridge ready.");
                PublishSceneStatus();
                PublishTimelineStatus();
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Ready. Watching " + RequestPath + ".");
            }
            catch (Exception exception)
            {
                _operational = false;
                string message = "Initialization failed: " + DescribeException(exception);
                PublishStatus(StateError, "", "", UtcNow(), "", message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
        }

        private void Update()
        {
            if (!_operational)
            {
                return;
            }

            float now = Time.realtimeSinceStartup;
            if (now >= _nextScenePublishAt)
            {
                _nextScenePublishAt = now + ScenePublishIntervalSeconds;
                PublishSceneStatus();
            }
            if (now >= _nextTimelinePublishAt)
            {
                _nextTimelinePublishAt =
                    now + TimelinePublishIntervalSeconds;
                PublishTimelineStatus();
            }

            if (now < _nextPollAt)
            {
                return;
            }

            _nextPollAt = now + PollIntervalSeconds;
            _skipPendingProcessing = false;

            try
            {
                PollRequestFile();
                if (!_skipPendingProcessing)
                {
                    ProcessPendingRequest(now);
                }
                RestoreMailboxRejectionStatus();
            }
            catch (Exception exception)
            {
                string requestId =
                    _pendingRequest == null ? "" : _pendingRequest.RequestId;
                string message = "Bridge update failed: " + DescribeException(exception);
                PublishStatus(StateError, requestId, "", UtcNow(), "", message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
        }

        private static string UtcNow()
        {
            return DateTime.UtcNow.ToString("O");
        }

        private static void EnsureDirectory(string path)
        {
            if (!FileManagerSecure.DirectoryExists(path))
            {
                FileManagerSecure.CreateDirectory(path);
            }
        }

        private static void EnsureBridgeDirectory()
        {
            EnsureDirectory(PluginDataRoot);
            EnsureDirectory(DataRoot);
            EnsureDirectory(BridgeRoot);
        }

        private void RecoverLastCompletedRequest()
        {
            if (!FileManagerSecure.FileExists(StatusPath))
            {
                return;
            }

            try
            {
                JSONClass status =
                    JSON.Parse(FileManagerSecure.ReadAllText(StatusPath)).AsObject;
                if (status == null || status["protocol"].AsInt != ProtocolVersion)
                {
                    return;
                }

                string requestId =
                    ((string)status["lastCompletedRequestId"] ?? "").Trim();
                if (requestId.Length == 0 &&
                    (string)status["state"] == StateOk)
                {
                    requestId = ((string)status["requestId"] ?? "").Trim();
                }
                if (requestId.Length == 0)
                {
                    return;
                }

                _lastHandledRequestId = requestId;
                _lastCompletedRequestId = requestId;
            }
            catch
            {
                // The external reader and this recovery path both retry after
                // a transient partial status write.
            }
        }

        private void IgnoreCompletedLegacyRequest()
        {
            if (!FileManagerSecure.FileExists(RequestPath) ||
                !FileManagerSecure.FileExists(StatusPath))
            {
                return;
            }

            try
            {
                string payload = FileManagerSecure.ReadAllText(RequestPath);
                JSONClass request = JSON.Parse(payload).AsObject;
                JSONClass status =
                    JSON.Parse(FileManagerSecure.ReadAllText(StatusPath)).AsObject;
                if (request == null || status == null)
                {
                    return;
                }

                int requestProtocol = request["protocol"].AsInt;
                if (requestProtocol <= 0 ||
                    requestProtocol >= ProtocolVersion ||
                    status["protocol"].AsInt != requestProtocol)
                {
                    return;
                }

                string requestId =
                    ((string)request["requestId"] ?? "").Trim();
                string completedRequestId =
                    ((string)status["lastCompletedRequestId"] ?? "").Trim();
                if (requestId.Length == 0 ||
                    !string.Equals(
                        requestId,
                        completedRequestId,
                        StringComparison.Ordinal))
                {
                    return;
                }

                // A completed request from an older bridge is historical
                // mailbox state, not work for this protocol generation.
                // Remember its exact payload so the first poll does not turn
                // a successful bridge upgrade into a spurious error.
                _lastRequestPayload = payload;
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Ignored completed protocol-" +
                    requestProtocol +
                    " mailbox request after upgrade.");
            }
            catch
            {
                // PollRequestFile will validate and report a malformed or
                // partially-written request once the bridge is operational.
            }
        }

        private void PollRequestFile()
        {
            if (!FileManagerSecure.FileExists(RequestPath))
            {
                return;
            }

            string payload = FileManagerSecure.ReadAllText(RequestPath);
            if (payload == _lastRequestPayload)
            {
                return;
            }
            _lastRequestPayload = payload;
            _mailboxRejectedRequestId = "";
            _mailboxRejectedMessage = "";

            string requestId = "";
            try
            {
                JSONClass request = JSON.Parse(payload).AsObject;
                if (request == null)
                {
                    RejectRequest("", "Request is not a JSON object.");
                    return;
                }

                requestId = ((string)request["requestId"] ?? "").Trim();
                if (request["protocol"].AsInt != ProtocolVersion)
                {
                    RejectRequest(requestId, "Unsupported bridge protocol.");
                    return;
                }
                if (requestId.Length == 0 || requestId.Length > 200)
                {
                    RejectRequest(
                        requestId,
                        "requestId must contain 1 to 200 characters.");
                    return;
                }

                if (_pendingRequest == null &&
                    requestId == _lastHandledRequestId)
                {
                    return;
                }

                string command = ((string)request["command"] ?? "").Trim();
                BridgeRequest parsed = new BridgeRequest();
                parsed.RequestId = requestId;
                parsed.Command = command;
                parsed.BrowserAssistMode = "auto";
                parsed.TargetUid = "";
                parsed.AtomType = "";
                parsed.PresetKind = "";
                parsed.ResourceRef = "";
                parsed.Merge = false;
                parsed.CreateIfMissing = false;
                parsed.ChoiceIndex = -1;
                parsed.ChoiceToken = "";
                parsed.ClothingActive = false;
                parsed.ClothingRevision = "";
                parsed.HairRevision = "";
                parsed.HairActionToken = "";
                parsed.TimelineId = "";
                parsed.TimelineRevision = "";
                parsed.TimelineOperation = "";
                parsed.TimelineItemToken = "";
                parsed.Sam3dJobId = "";
                parsed.Sam3dRevision = "";
                parsed.Sam3dCameraUid = "";
                parsed.Sam3dCreateCamera = false;

                if (command == CommandRescan)
                {
                    string browserAssistMode =
                        ((string)request["browserAssist"] ?? "auto")
                        .Trim()
                        .ToLowerInvariant();
                    if (browserAssistMode.Length == 0)
                    {
                        browserAssistMode = "auto";
                    }
                    if (browserAssistMode != "auto" &&
                        browserAssistMode != "off")
                    {
                        RejectRequest(
                            requestId,
                            "browserAssist must be either 'auto' or 'off'.");
                        return;
                    }
                    parsed.BrowserAssistMode = browserAssistMode;
                    parsed.RescanRequired = true;
                }
                else if (command == CommandApplyPersonPreset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.PresetKind =
                        ((string)request["presetKind"] ?? "").Trim();
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;

                    string validationError = ValidateApplyRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandAddPerson ||
                         command == CommandSelectPerson ||
                         command == CommandSelectAtom)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    string validationError =
                        ValidateTargetUid(parsed.TargetUid);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                    parsed.RescanRequired = false;
                }
                else if (command == CommandAddAtom)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType =
                        (string)request["atomType"] ?? "";
                    string validationError =
                        ValidateAddAtomRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                    parsed.RescanRequired = false;
                }
                else if (command == CommandApplyAtomPreset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType =
                        (string)request["atomType"] ?? "";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateAtomPresetRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadSubscene)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "SubScene";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateSubsceneRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadCustomUnityAsset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "CustomUnityAsset";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateCustomUnityAssetRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSelectCustomUnityAssetChoice)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "CustomUnityAsset";
                    parsed.ChoiceIndex = request["choiceIndex"].AsInt;
                    parsed.ChoiceToken =
                        (string)request["choiceToken"] ?? "";
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateCustomUnityAssetChoiceRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSetPersonClothingResource)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.ClothingRevision =
                        (string)request["revision"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    string desiredState =
                        (string)request["desiredState"] ?? "";
                    if (desiredState == "worn")
                    {
                        parsed.ClothingActive = true;
                    }
                    else if (desiredState == "removed")
                    {
                        parsed.ClothingActive = false;
                    }
                    else
                    {
                        RejectRequest(
                            requestId,
                            "desiredState must be exactly 'worn' or 'removed'.");
                        return;
                    }

                    string validationError =
                        ValidatePersonClothingRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSetPersonHairItem)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.HairRevision =
                        (string)request["revision"] ?? "";
                    parsed.HairActionToken =
                        (string)request["actionToken"] ?? "";
                    parsed.RescanRequired = false;
                    string desiredState =
                        (string)request["desiredState"] ?? "";
                    if (desiredState != "removed")
                    {
                        RejectRequest(
                            requestId,
                            "Hair desiredState must be exactly 'removed'.");
                        return;
                    }

                    string validationError =
                        ValidatePersonHairRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadScene)
                {
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;

                    string validationError =
                        ValidateSceneRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandControlTimeline)
                {
                    parsed.TimelineId =
                        ((string)request["timelineId"] ?? "").Trim();
                    parsed.TimelineRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.TimelineOperation =
                        ((string)request["operation"] ?? "").Trim();
                    parsed.RescanRequired = false;
                    parsed.HasTimelineValue = request.HasKey("value");

                    string itemField =
                        TimelineItemField(parsed.TimelineOperation);
                    if (itemField.Length != 0)
                    {
                        parsed.TimelineItemToken =
                            ((string)request[itemField] ?? "").Trim();
                    }
                    if (parsed.TimelineOperation == "setLocked")
                    {
                        parsed.TimelineBoolValue =
                            request["value"].AsBool;
                    }
                    else if (
                        parsed.TimelineOperation == "setTime" ||
                        parsed.TimelineOperation == "setSpeed" ||
                        parsed.TimelineOperation == "setWeight")
                    {
                        parsed.TimelineNumberValue =
                            request["value"].AsFloat;
                    }

                    string validationError =
                        ValidateTimelineRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandApplySam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.Sam3dSolutionSha256 =
                        ((string)request["solutionSha256"] ?? "").Trim();
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.Sam3dCameraUid =
                        ((string)request["cameraUid"] ?? "").Trim();
                    parsed.Sam3dCreateCamera =
                        request["createCamera"].AsBool;
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dApplyRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandUndoSam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dIdentity(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandCaptureSam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.Sam3dSolutionSha256 =
                        ((string)request["solutionSha256"] ?? "").Trim();
                    parsed.Sam3dCameraUid =
                        ((string)request["cameraUid"] ?? "").Trim();
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dCaptureRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else
                {
                    RejectRequest(
                        requestId,
                        "Unsupported command. Accepted commands are 'rescan' " +
                        "'applyPersonPreset', 'addPerson', 'addAtom', " +
                        "'applyAtomPreset', 'loadSubscene', " +
                        "'loadCustomUnityAsset', " +
                        "'selectCustomUnityAssetChoice', " +
                        "'setPersonClothingResource', 'setPersonHairItem', " +
                        "'selectPerson', 'selectAtom', 'loadScene', " +
                        "'controlTimeline', 'applySam3dResult', " +
                        "'undoSam3dResult', and 'captureSam3dResult'.");
                    return;
                }

                if (_pendingRequest != null)
                {
                    if (requestId == _pendingRequest.RequestId)
                    {
                        return;
                    }

                    // Repeated package switches can safely collapse pending
                    // rescan-only requests. Never collapse an atom or resource
                    // action: each one names a distinct target or resource.
                    if (_pendingRequest.Command == CommandRescan &&
                        parsed.Command == CommandRescan)
                    {
                        _pendingRequest = parsed;
                        PublishStatus(
                            StateQueued,
                            requestId,
                            "",
                            "",
                            "",
                            "Rescan request queued; an older pending rescan was coalesced.");
                        return;
                    }

                    _skipPendingProcessing = true;
                    RejectRequest(
                        requestId,
                        "Bridge is busy with request " +
                        _pendingRequest.RequestId +
                        ". Submit this request again after it completes.");
                    return;
                }

                _pendingRequest = parsed;
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Request queued.");
            }
            catch (Exception exception)
            {
                RejectRequest(
                    requestId,
                    "Could not parse request: " + DescribeException(exception));
            }
        }

        private static string ValidateApplyRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string requiredPrefix = GetPresetPrefix(request.PresetKind);
            if (requiredPrefix.Length == 0)
            {
                return "Unsupported presetKind.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                requiredPrefix,
                ".vap",
                true,
                "presets of this kind");
        }

        private static string ValidateSceneRequest(BridgeRequest request)
        {
            return ValidateResourceRef(
                request.ResourceRef,
                "Saves/scene/",
                ".json",
                false,
                "scenes");
        }

        private static string ValidateAddAtomRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            return ValidateAtomType(request.AtomType);
        }

        private static string ValidateAtomPresetRequest(BridgeRequest request)
        {
            string addError = ValidateAddAtomRequest(request);
            if (addError.Length != 0)
            {
                return addError;
            }
            if (request.CreateIfMissing && request.Merge)
            {
                return "createIfMissing and merge cannot both be true.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/Atom/" + request.AtomType + "/",
                ".vap",
                true,
                "presets for atom type " + request.AtomType);
        }

        private static string ValidateSubsceneRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/SubScene/",
                ".json",
                false,
                "SubScenes");
        }

        private static string ValidateCustomUnityAssetRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string extension = "";
            if (request.ResourceRef != null &&
                request.ResourceRef.EndsWith(
                    ".assetbundle",
                    StringComparison.OrdinalIgnoreCase))
            {
                extension = ".assetbundle";
            }
            else if (request.ResourceRef != null &&
                     request.ResourceRef.EndsWith(
                         ".scene",
                         StringComparison.OrdinalIgnoreCase))
            {
                extension = ".scene";
            }
            if (extension.Length == 0)
            {
                return "resourceRef must name a .assetbundle or .scene resource.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/Assets/",
                extension,
                false,
                "Custom Unity Assets");
        }

        private static string ValidateCustomUnityAssetChoiceRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (request.ChoiceIndex <= 0)
            {
                return "choiceIndex must be a positive chooser index.";
            }
            if (!IsHexToken(request.ChoiceToken))
            {
                return "choiceToken must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string ValidatePersonClothingRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (!IsHexToken(request.ClothingRevision))
            {
                return "revision must contain exactly 32 hexadecimal characters.";
            }

            string resourceRef = request.ResourceRef ?? "";
            string prefix = GetClothingResourcePrefix(resourceRef);
            if (prefix.Length == 0)
            {
                return "Clothing resources must be below " +
                    "Custom/Clothing/Female/ or Custom/Clothing/Male/.";
            }
            return ValidateResourceRef(
                resourceRef,
                prefix,
                ".vam",
                false,
                "clothing items");
        }

        private static string ValidatePersonHairRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (!IsHexToken(request.HairRevision))
            {
                return "revision must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.HairActionToken))
            {
                return "actionToken must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string GetClothingResourcePrefix(string resourceRef)
        {
            if (resourceRef == null)
            {
                return "";
            }
            int packageSeparator =
                resourceRef.IndexOf(":/", StringComparison.Ordinal);
            string member =
                packageSeparator >= 0
                ? resourceRef.Substring(packageSeparator + 2)
                : resourceRef;
            if (member.StartsWith(
                    "Custom/Clothing/Female/",
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Custom/Clothing/Female/";
            }
            if (member.StartsWith(
                    "Custom/Clothing/Male/",
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Custom/Clothing/Male/";
            }
            return "";
        }

        private static bool IsHexToken(string value)
        {
            if (value == null || value.Length != 32)
            {
                return false;
            }
            int index;
            for (index = 0; index < value.Length; index++)
            {
                char character = value[index];
                bool digit = character >= '0' && character <= '9';
                bool lower = character >= 'a' && character <= 'f';
                bool upper = character >= 'A' && character <= 'F';
                if (!digit && !lower && !upper)
                {
                    return false;
                }
            }
            return true;
        }

        private static bool IsSha256Token(string value)
        {
            if (value == null || value.Length != 64)
            {
                return false;
            }
            int index;
            for (index = 0; index < value.Length; index++)
            {
                char character = value[index];
                bool digit = character >= '0' && character <= '9';
                bool lower = character >= 'a' && character <= 'f';
                bool upper = character >= 'A' && character <= 'F';
                if (!digit && !lower && !upper)
                {
                    return false;
                }
            }
            return true;
        }

        private static string TimelineItemField(string operation)
        {
            if (operation == "selectClip" || operation == "playClip")
            {
                return "clipId";
            }
            if (operation == "selectSegment")
            {
                return "segmentId";
            }
            if (operation == "selectLayer")
            {
                return "layerId";
            }
            return "";
        }

        private static bool IsTimelineOperation(string operation)
        {
            return
                operation == "play" ||
                operation == "pause" ||
                operation == "stop" ||
                operation == "reset" ||
                operation == "nextFrame" ||
                operation == "previousFrame" ||
                operation == "selectClip" ||
                operation == "playClip" ||
                operation == "selectSegment" ||
                operation == "selectLayer" ||
                operation == "setTime" ||
                operation == "setSpeed" ||
                operation == "setWeight" ||
                operation == "setLocked";
        }

        private static string ValidateTimelineRequest(
            BridgeRequest request)
        {
            if (!IsHexToken(request.TimelineId))
            {
                return "timelineId must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.TimelineRevision))
            {
                return "expectedRevision must contain exactly 32 hexadecimal characters.";
            }
            if (!IsTimelineOperation(request.TimelineOperation))
            {
                return "operation is not an allowlisted Timeline control.";
            }
            if (TimelineItemField(request.TimelineOperation).Length != 0 &&
                !IsHexToken(request.TimelineItemToken))
            {
                return "Timeline item ID must contain exactly 32 hexadecimal characters.";
            }
            if ((request.TimelineOperation == "setTime" ||
                 request.TimelineOperation == "setSpeed" ||
                 request.TimelineOperation == "setWeight" ||
                 request.TimelineOperation == "setLocked") &&
                !request.HasTimelineValue)
            {
                return "Timeline setter operation requires value.";
            }
            float value = request.TimelineNumberValue;
            if (request.TimelineOperation == "setTime" &&
                (!IsFinite(value) || value < 0f || value > 86400f))
            {
                return "setTime value must be between 0 and 86400.";
            }
            if (request.TimelineOperation == "setSpeed" &&
                (!IsFinite(value) || value < -1f || value > 5f))
            {
                return "setSpeed value must be between -1 and 5.";
            }
            if (request.TimelineOperation == "setWeight" &&
                (!IsFinite(value) || value < 0f || value > 1f))
            {
                return "setWeight value must be between 0 and 1.";
            }
            return "";
        }

        private static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }

        private static string ValidateSam3dIdentity(
            BridgeRequest request)
        {
            if (!IsHexToken(request.Sam3dJobId))
            {
                return "jobId must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.Sam3dRevision))
            {
                return "expectedRevision must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string ValidateSam3dApplyRequest(
            BridgeRequest request)
        {
            string identityError = ValidateSam3dIdentity(request);
            if (identityError.Length != 0)
            {
                return identityError;
            }
            if (!IsSha256Token(request.Sam3dSolutionSha256))
            {
                return
                    "solutionSha256 must contain exactly 64 hexadecimal characters.";
            }
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string cameraError =
                ValidateTargetUid(request.Sam3dCameraUid);
            if (cameraError.Length != 0)
            {
                return "cameraUid " + cameraError;
            }
            return "";
        }

        private static string ValidateSam3dCaptureRequest(
            BridgeRequest request)
        {
            string identityError = ValidateSam3dIdentity(request);
            if (identityError.Length != 0)
            {
                return identityError;
            }
            if (!IsSha256Token(request.Sam3dSolutionSha256))
            {
                return
                    "solutionSha256 must contain exactly 64 hexadecimal characters.";
            }
            string cameraError =
                ValidateTargetUid(request.Sam3dCameraUid);
            if (cameraError.Length != 0)
            {
                return "cameraUid " + cameraError;
            }
            return "";
        }

        private static string ValidateTargetUid(string targetUid)
        {
            if (targetUid == null ||
                targetUid.Length == 0 ||
                targetUid.Length > 200)
            {
                return "targetUid must contain 1 to 200 characters.";
            }
            if (ContainsControlCharacter(targetUid))
            {
                return "targetUid must not contain control characters.";
            }
            return "";
        }

        private static string ValidateAtomType(string atomType)
        {
            if (!IsAllowedAtomType(atomType))
            {
                return "atomType is not an allowlisted VaM 1.22 native atom type.";
            }
            return "";
        }

        private static bool IsAllowedAtomType(string atomType)
        {
            return atomType != null &&
                atomType.IndexOf('|') < 0 &&
                AllowedAtomTypes.IndexOf(
                    "|" + atomType + "|",
                    StringComparison.Ordinal) >= 0;
        }

        private static string GetPresetPrefix(string presetKind)
        {
            if (presetKind == "appearance")
                return "Custom/Atom/Person/Appearance/";
            if (presetKind == "animation")
                return "Custom/Atom/Person/AnimationPresets/";
            if (presetKind == "breastPhysics")
                return "Custom/Atom/Person/BreastPhysics/";
            if (presetKind == "clothing")
                return "Custom/Atom/Person/Clothing/";
            if (presetKind == "general")
                return "Custom/Atom/Person/General/";
            if (presetKind == "glutePhysics")
                return "Custom/Atom/Person/GlutePhysics/";
            if (presetKind == "hair")
                return "Custom/Atom/Person/Hair/";
            if (presetKind == "morphs")
                return "Custom/Atom/Person/Morphs/";
            if (presetKind == "plugins")
                return "Custom/Atom/Person/Plugins/";
            if (presetKind == "pose")
                return "Custom/Atom/Person/Pose/";
            if (presetKind == "skin")
                return "Custom/Atom/Person/Skin/";
            return "";
        }

        private static string GetPresetStorableId(string presetKind)
        {
            if (presetKind == "appearance") return "AppearancePresets";
            if (presetKind == "animation") return "AnimationPresets";
            if (presetKind == "breastPhysics")
                return "FemaleBreastPhysicsPresets";
            if (presetKind == "clothing") return "ClothingPresets";
            if (presetKind == "general") return "Preset";
            if (presetKind == "glutePhysics")
                return "FemaleGlutePhysicsPresets";
            if (presetKind == "hair") return "HairPresets";
            if (presetKind == "morphs") return "MorphPresets";
            if (presetKind == "plugins") return "PluginPresets";
            if (presetKind == "pose") return "PosePresets";
            if (presetKind == "skin") return "SkinPresets";
            return "";
        }

        private static string ValidateResourceRef(
            string resourceRef,
            string requiredPrefix,
            string extension,
            bool requirePresetBasename,
            string resourceDescription)
        {
            if (resourceRef == null ||
                resourceRef.Length == 0 ||
                resourceRef.Length > MaximumResourceRefLength)
            {
                return "resourceRef must contain 1 to " +
                    MaximumResourceRefLength +
                    " characters.";
            }
            if (resourceRef != resourceRef.Trim())
            {
                return "resourceRef must not have leading or trailing whitespace.";
            }
            if (resourceRef[0] == '/' ||
                resourceRef.IndexOf('\\') >= 0 ||
                resourceRef.IndexOf("://", StringComparison.Ordinal) >= 0)
            {
                return "resourceRef must be a relative VaM resource reference.";
            }
            if (ContainsControlCharacter(resourceRef))
            {
                return "resourceRef must not contain control characters.";
            }
            if (!resourceRef.EndsWith(
                extension,
                StringComparison.OrdinalIgnoreCase))
            {
                return "resourceRef must name a " + extension + " resource.";
            }
            if (requirePresetBasename)
            {
                int lastSlash = resourceRef.LastIndexOf('/');
                string basename = resourceRef.Substring(lastSlash + 1);
                if (!basename.StartsWith(
                    "Preset_",
                    StringComparison.OrdinalIgnoreCase))
                {
                    return "resourceRef basename must begin with Preset_.";
                }
            }

            string[] pathSegments = resourceRef.Split('/');
            int pathIndex;
            for (pathIndex = 0; pathIndex < pathSegments.Length; pathIndex++)
            {
                if (pathSegments[pathIndex].Length == 0 ||
                    pathSegments[pathIndex] == "." ||
                    pathSegments[pathIndex] == "..")
                {
                    return "resourceRef must not contain empty, '.' or '..' " +
                        "path segments.";
                }
            }

            int packageSeparator =
                resourceRef.IndexOf(":/", StringComparison.Ordinal);
            if (packageSeparator < 0)
            {
                if (resourceRef.IndexOf(':') >= 0 ||
                    !resourceRef.StartsWith(
                        requiredPrefix,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return "Local " + resourceDescription + " must be below " +
                        requiredPrefix +
                        ".";
                }
                return "";
            }

            string packageRef = resourceRef.Substring(0, packageSeparator);
            string packageMember = resourceRef.Substring(packageSeparator + 2);
            if (packageRef.IndexOf(':') >= 0 ||
                packageRef.IndexOf('/') >= 0 ||
                packageMember.IndexOf(':') >= 0 ||
                resourceRef.IndexOf(
                    ":/",
                    packageSeparator + 2,
                    StringComparison.Ordinal) >= 0 ||
                !packageMember.StartsWith(
                    requiredPrefix,
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Packaged " + resourceDescription + " must use " +
                    "creator.package.version:/" +
                    requiredPrefix +
                    "*" +
                    extension +
                    ".";
            }

            string[] packageParts = packageRef.Split('.');
            if (packageParts.Length < 3)
            {
                return "Packaged resourceRef must include creator, package, and version.";
            }
            for (pathIndex = 0; pathIndex < packageParts.Length; pathIndex++)
            {
                if (packageParts[pathIndex].Length == 0)
                {
                    return "Packaged resourceRef has an empty identity component.";
                }
            }
            return "";
        }

        private static bool ContainsControlCharacter(string value)
        {
            int index;
            for (index = 0; index < value.Length; index++)
            {
                if (value[index] < ' ' || value[index] == '\u007f')
                {
                    return true;
                }
            }
            return false;
        }

        private void RejectRequest(string requestId, string message)
        {
            if (_pendingRequest != null &&
                requestId != _pendingRequest.RequestId)
            {
                _skipPendingProcessing = true;
                _mailboxRejectedRequestId = requestId ?? "";
                _mailboxRejectedMessage = message ?? "";
            }
            PublishStatus(StateError, requestId, "", UtcNow(), "", message);
            SuperController.LogError("[VAM-PIP Bridge] " + message);
        }

        private void RestoreMailboxRejectionStatus()
        {
            if (_mailboxRejectedMessage.Length == 0)
            {
                return;
            }
            PublishStatus(
                StateError,
                _mailboxRejectedRequestId,
                "",
                UtcNow(),
                "",
                _mailboxRejectedMessage);
        }

        private void ProcessPendingRequest(float now)
        {
            if (_pendingRequest == null || _requestInProgress)
            {
                return;
            }

            string requestId = _pendingRequest.RequestId;
            if (SuperController.singleton == null)
            {
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Waiting for VaM to finish initializing.");
                return;
            }
            if (SuperController.singleton.isLoading)
            {
                PublishStatus(
                    StateDeferredLoading,
                    requestId,
                    "",
                    "",
                    "",
                    "Waiting for scene loading to finish.");
                return;
            }
            if (_pendingRequest.RescanRequired && now < _nextAllowedRescanAt)
            {
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Request queued by the rescan rate limiter.");
                return;
            }

            BridgeRequest request = _pendingRequest;
            if (request.Command == CommandAddPerson ||
                request.Command == CommandAddAtom)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(
                        ExecuteAddAtom(
                            request,
                            request.Command == CommandAddPerson
                            ? "Person"
                            : request.AtomType));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start atom creation: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandApplyAtomPreset ||
                request.Command == CommandLoadSubscene ||
                request.Command == CommandLoadCustomUnityAsset ||
                request.Command == CommandSelectCustomUnityAssetChoice)
            {
                _requestInProgress = true;
                try
                {
                    if (request.Command == CommandApplyAtomPreset)
                    {
                        StartCoroutine(ExecuteApplyAtomPreset(request));
                    }
                    else if (request.Command == CommandLoadSubscene)
                    {
                        StartCoroutine(ExecuteLoadSubscene(request));
                    }
                    else if (request.Command == CommandLoadCustomUnityAsset)
                    {
                        StartCoroutine(ExecuteLoadCustomUnityAsset(request));
                    }
                    else
                    {
                        StartCoroutine(
                            ExecuteSelectCustomUnityAssetChoice(request));
                    }
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start atom resource action: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandLoadScene)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(ExecuteLoadScene(request));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start scene loading: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandApplySam3dResult ||
                request.Command == CommandUndoSam3dResult ||
                request.Command == CommandCaptureSam3dResult)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(
                        request.Command == CommandApplySam3dResult
                        ? ExecuteApplySam3dResult(request)
                        : request.Command == CommandUndoSam3dResult
                        ? ExecuteUndoSam3dResult(request)
                        : ExecuteCaptureSam3dResult(request));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start the SAM3D action: " +
                        DescribeException(exception));
                }
                return;
            }

            _pendingRequest = null;
            if (request.Command == CommandRescan)
            {
                ExecuteRescan(request);
            }
            else if (request.Command == CommandApplyPersonPreset)
            {
                ExecuteApplyPersonPreset(request);
            }
            else if (request.Command == CommandSetPersonClothingResource)
            {
                ExecuteSetPersonClothingResource(request);
            }
            else if (request.Command == CommandSetPersonHairItem)
            {
                ExecuteSetPersonHairItem(request);
            }
            else if (request.Command == CommandControlTimeline)
            {
                ExecuteTimelineControl(request);
            }
            else
            {
                ExecuteSelectAtom(
                    request,
                    request.Command == CommandSelectPerson);
            }
        }

        private void ExecuteRescan(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            PublishStatus(
                StateRescanning,
                request.RequestId,
                startedAt,
                "",
                "",
                "Rescanning VaM packages.");

            try
            {
                SuperController.singleton.RescanPackages();
                backend = "vam";
                string message =
                    request.BrowserAssistMode == "off"
                    ? "Core VaM package rescan completed."
                    : "Core VaM package rescan completed. Reload BrowserAssist " +
                      "if it must see newly enabled packages.";
                CompleteRequest(request.RequestId);
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Request " +
                    request.RequestId +
                    " completed using vam.");
            }
            catch (Exception exception)
            {
                _lastHandledRequestId = request.RequestId;
                string message =
                    "Package rescan failed: " + DescribeException(exception);
                PublishStatus(
                    StateError,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
            finally
            {
                _nextAllowedRescanAt =
                    Time.realtimeSinceStartup + MinimumRescanIntervalSeconds;
            }
        }

        private void ExecuteApplyPersonPreset(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            bool rescanAttempted = false;

            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before applying the Person preset.");
                    SuperController.singleton.RescanPackages();
                    backend = "vam";
                }

                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    backend,
                    "Applying Person " + request.PresetKind + " preset.");

                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated preset does not exist or is not visible to VaM.");
                }

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the current scene.");
                }

                string storableId =
                    GetPresetStorableId(request.PresetKind);
                JSONStorable presetStorable =
                    person.GetStorableByID(storableId);
                if (presetStorable == null)
                {
                    throw new Exception(
                        "The target Person does not expose " +
                        storableId +
                        ".");
                }
                JSONStorableUrl presetBrowsePath =
                    presetStorable.GetUrlJSONParam("presetBrowsePath");
                if (presetBrowsePath == null)
                {
                    throw new Exception(
                        "The target Person preset storable has no presetBrowsePath.");
                }

                JSONStorableBool loadPresetOnSelect =
                    presetStorable.GetBoolJSONParam("loadPresetOnSelect");
                bool previousLoadPresetOnSelect = false;
                if (loadPresetOnSelect != null)
                {
                    previousLoadPresetOnSelect = loadPresetOnSelect.val;
                    loadPresetOnSelect.val = false;
                }
                try
                {
                    presetBrowsePath.val =
                        SuperController.singleton.NormalizePath(
                            request.ResourceRef);
                    presetStorable.CallAction(
                        request.Merge
                        ? "MergeLoadPreset"
                        : "LoadPreset");
                }
                finally
                {
                    if (loadPresetOnSelect != null)
                    {
                        loadPresetOnSelect.val = previousLoadPresetOnSelect;
                    }
                }
                backend = "vam";
                CompleteRequest(request.RequestId);
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    "Person " +
                    request.PresetKind +
                    (request.Merge ? " preset merged." : " preset applied."));
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Applied " +
                    request.PresetKind +
                    " preset to " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                _lastHandledRequestId = request.RequestId;
                string message =
                    "Person preset request failed: " +
                    DescribeException(exception);
                PublishStatus(
                    StateError,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private void ExecuteSetPersonClothingResource(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            bool rescanAttempted = false;
            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before changing clothing.");
                    SuperController.singleton.RescanPackages();
                    backend = "vam";
                }

                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    backend,
                    request.ClothingActive
                    ? "Putting on an individual clothing item."
                    : "Removing an individual clothing item.");

                if (request.ClothingActive &&
                    !FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated clothing item does not exist or is not " +
                        "visible to VaM.");
                }

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the " +
                        "current scene.");
                }
                DAZCharacterSelector geometry =
                    person.GetStorableByID("geometry")
                    as DAZCharacterSelector;
                if (geometry == null)
                {
                    throw new Exception(
                        "The target Person does not expose native geometry.");
                }

                PersonClothingSnapshot snapshot = null;
                if (!_personClothingSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, person) ||
                    !object.ReferenceEquals(snapshot.Geometry, geometry) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.ClothingRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The Person clothing revision is stale; refresh the " +
                        "live roster.");
                }
                List<ActiveClothingEntry> entries =
                    GetActiveClothingEntries(person, geometry);
                string currentGeneration =
                    BuildPersonClothingGenerationKey(geometry, entries);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "The Person's clothing or gender changed; refresh the " +
                        "live roster.");
                }

                string prefix =
                    GetClothingResourcePrefix(request.ResourceRef);
                string gender = geometry.gender.ToString();
                bool genderCompatible =
                    prefix == "Custom/Clothing/Female/"
                    ? gender.Equals(
                        "Female",
                        StringComparison.OrdinalIgnoreCase) ||
                      gender.Equals(
                        "Both",
                        StringComparison.OrdinalIgnoreCase)
                    : gender.Equals(
                        "Male",
                        StringComparison.OrdinalIgnoreCase) ||
                      gender.Equals(
                        "Both",
                        StringComparison.OrdinalIgnoreCase);
                if (request.ClothingActive && !genderCompatible)
                {
                    throw new Exception(
                        "The clothing item is incompatible with the Person's " +
                        "current gender.");
                }

                string normalized =
                    FileManagerSecure.NormalizePath(request.ResourceRef);
                DAZClothingItem resolvedItem =
                    geometry.GetClothingItem(normalized);
                bool locked =
                    resolvedItem != null && resolvedItem.locked;
                bool observedWorn = false;
                int entryIndex;
                for (entryIndex = 0;
                     entryIndex < entries.Count;
                     entryIndex++)
                {
                    ActiveClothingEntry entry = entries[entryIndex];
                    if (entry.ResourceRef.Length != 0 &&
                        entry.ResourceRef.Equals(
                            normalized,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        observedWorn = true;
                        if (entry.Locked)
                        {
                            locked = true;
                        }
                    }
                }
                JSONStorableBool active =
                    geometry.GetBoolJSONParam("clothing:" + normalized);
                bool alreadyRemoved =
                    active == null &&
                    !request.ClothingActive &&
                    !observedWorn;
                if (active == null && !alreadyRemoved)
                {
                    throw new Exception(
                        "VaM did not register the exact clothing item on this " +
                        "Person after the package rescan.");
                }
                if (!alreadyRemoved &&
                    active.val != request.ClothingActive &&
                    locked)
                {
                    throw new Exception(
                        "The clothing item is locked in VaM; unlock it before " +
                        "changing it externally.");
                }

                if (!alreadyRemoved)
                {
                    active.val = request.ClothingActive;
                    if (active.val != request.ClothingActive)
                    {
                        throw new Exception(
                            "VaM refused the requested clothing state.");
                    }
                }

                backend = "vam";
                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    request.ClothingActive
                    ? "Clothing item is worn."
                    : alreadyRemoved
                      ? "Clothing item was already removed."
                      : "Clothing item was removed.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Clothing state changed for " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Person clothing request failed: " +
                    DescribeException(exception));
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private void ExecuteSetPersonHairItem(BridgeRequest request)
        {
            string startedAt = UtcNow();
            try
            {
                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    "",
                    "Removing one active Hair layer.");

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the " +
                        "current scene.");
                }
                DAZCharacterSelector geometry =
                    person.GetStorableByID("geometry")
                    as DAZCharacterSelector;
                if (geometry == null)
                {
                    throw new Exception(
                        "The target Person does not expose native geometry.");
                }

                PersonHairSnapshot snapshot = null;
                if (!_personHairSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, person) ||
                    !object.ReferenceEquals(snapshot.Geometry, geometry) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.HairRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The Person Hair revision is stale; refresh the live " +
                        "roster.");
                }

                List<ActiveHairEntry> entries =
                    GetActiveHairEntries(person, geometry);
                string currentGeneration =
                    BuildPersonHairGenerationKey(geometry, entries);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal) ||
                    snapshot.Items == null ||
                    snapshot.ActionTokens == null ||
                    snapshot.Items.Count != entries.Count ||
                    snapshot.ActionTokens.Count != entries.Count ||
                    snapshot.PublishedCount < 0 ||
                    snapshot.PublishedCount > entries.Count)
                {
                    throw new Exception(
                        "The Person's Hair changed; refresh the live roster.");
                }

                ActiveHairEntry selected = null;
                int selectedIndex = -1;
                int tokenMatches = 0;
                int entryIndex;
                for (entryIndex = 0;
                     entryIndex < entries.Count;
                     entryIndex++)
                {
                    if (!object.ReferenceEquals(
                            snapshot.Items[entryIndex],
                            entries[entryIndex].Item))
                    {
                        throw new Exception(
                            "The Person's Hair identity changed; refresh the " +
                            "live roster.");
                    }
                    if (snapshot.ActionTokens[entryIndex].Equals(
                            request.HairActionToken,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        tokenMatches++;
                        selected = entries[entryIndex];
                        selectedIndex = entryIndex;
                    }
                }
                if (tokenMatches != 1 ||
                    selected == null ||
                    selectedIndex < 0 ||
                    selectedIndex >= snapshot.PublishedCount)
                {
                    throw new Exception(
                        "The Hair action token is stale or ambiguous; refresh " +
                        "the live roster.");
                }
                if (selected.Locked || selected.Item.locked)
                {
                    throw new Exception(
                        "The Hair layer is locked in VaM; unlock it before " +
                        "removing it externally.");
                }
                if (!selected.Item.active)
                {
                    throw new Exception(
                        "The Hair layer is no longer active; refresh the live " +
                        "roster.");
                }

                geometry.SetActiveHairItem(
                    selected.Item,
                    false,
                    false,
                    false);
                if (selected.Item.active)
                {
                    throw new Exception(
                        "VaM refused to disable the selected Hair layer.");
                }

                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    "vam",
                    "Hair layer was removed.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Hair layer removed from " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Person Hair request failed: " +
                    DescribeException(exception));
            }
        }

        private IEnumerator ExecuteLoadScene(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError = "";
            bool rescanAttempted = false;

            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before loading the scene.");
                    SuperController.singleton.RescanPackages();
                }

                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated scene does not exist or is not visible to VaM.");
                }
            }
            catch (Exception exception)
            {
                prepareError =
                    "Scene load request failed: " +
                    DescribeException(exception);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }

            if (prepareError.Length != 0)
            {
                FinishSceneLoadError(request, startedAt, prepareError);
                yield break;
            }

            PublishStatus(
                StateLoadingScene,
                request.RequestId,
                startedAt,
                "",
                "vam",
                request.Merge
                ? "Merging scene."
                : "Loading scene.");

            string loadError = "";
            try
            {
                string normalizedPath =
                    FileManagerSecure.NormalizePath(request.ResourceRef);
                if (request.Merge)
                {
                    SuperController.singleton.LoadMerge(normalizedPath);
                }
                else
                {
                    SuperController.singleton.Load(normalizedPath);
                }
            }
            catch (Exception exception)
            {
                loadError =
                    "Could not dispatch scene load: " +
                    DescribeException(exception);
            }
            if (loadError.Length != 0)
            {
                FinishSceneLoadError(request, startedAt, loadError);
                yield break;
            }

            // VaM raises isLoading asynchronously, so always cross a frame
            // boundary before deciding that the operation has completed.
            yield return new WaitForEndOfFrame();

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (SuperController.singleton != null &&
                   SuperController.singleton.isLoading &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            if (SuperController.singleton == null)
            {
                FinishSceneLoadError(
                    request,
                    startedAt,
                    "VaM's scene controller became unavailable while loading.");
                yield break;
            }
            if (SuperController.singleton.isLoading)
            {
                FinishSceneLoadError(
                    request,
                    startedAt,
                    "Scene loading did not finish within 120 seconds.");
                yield break;
            }

            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam",
                request.Merge
                ? "Scene merged."
                : "Scene loaded.");
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " +
                (request.Merge ? "Merged " : "Loaded ") +
                request.ResourceRef +
                ".");
        }

        private void FinishSceneLoadError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private IEnumerator ExecuteAddAtom(
            BridgeRequest request,
            string atomType)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateAdding,
                request.RequestId,
                startedAt,
                "",
                "",
                "Adding " + atomType + " " + request.TargetUid + ".");

            Atom existing = null;
            IEnumerator addRoutine = null;
            string addError = "";
            try
            {
                existing =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (existing == null)
                {
                    addRoutine =
                        SuperController.singleton.AddAtomByType(
                            atomType,
                            request.TargetUid,
                            true);
                    if (addRoutine == null)
                    {
                        throw new Exception(
                            "VaM did not provide an atom creation routine.");
                    }
                }
            }
            catch (Exception exception)
            {
                addError =
                    "Could not add " + atomType + ": " +
                    DescribeException(exception);
            }
            if (addError.Length != 0)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    addError);
                yield break;
            }

            if (existing != null)
            {
                if (existing.type != atomType)
                {
                    FinishAtomActionError(
                        request,
                        startedAt,
                        "targetUid is already used by an atom of type " +
                        existing.type +
                        ", not " +
                        atomType +
                        ".");
                    yield break;
                }
                FinishAtomActionOk(
                    request,
                    startedAt,
                    atomType +
                    " already exists; no scene change was needed.");
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                string iterationError = "";
                if (Time.realtimeSinceStartup >= deadline)
                {
                    iterationError =
                        atomType + " creation did not finish within 120 seconds.";
                }
                else
                {
                    try
                    {
                        hasNext = addRoutine.MoveNext();
                        if (hasNext)
                        {
                            current = addRoutine.Current;
                        }
                    }
                    catch (Exception exception)
                    {
                        iterationError =
                            atomType + " creation failed: " +
                            DescribeException(exception);
                    }
                }
                if (iterationError.Length != 0)
                {
                    FinishAtomActionError(
                        request,
                        startedAt,
                        iterationError);
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }

            yield return new WaitForEndOfFrame();

            try
            {
                Atom created =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (created == null || created.type != atomType)
                {
                    throw new Exception(
                        "VaM completed creation without the requested " +
                        atomType +
                        " atom.");
                }
                FinishAtomActionOk(
                    request,
                    startedAt,
                    atomType + " added.");
            }
            catch (Exception exception)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    "Could not verify the added " +
                    atomType +
                    ": " +
                    DescribeException(exception));
            }
        }

        private void FinishAtomActionOk(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam",
                message);
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " + message);
        }

        private void FinishAtomActionError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private static bool IsSam3dControllerId(string id)
        {
            const string allowed =
                "|hipControl|lThighControl|rThighControl|" +
                "lKneeControl|rKneeControl|lFootControl|rFootControl|" +
                "abdomen2Control|chestControl|neckControl|headControl|" +
                "lShoulderControl|rShoulderControl|" +
                "lArmControl|rArmControl|lElbowControl|rElbowControl|" +
                "lHandControl|rHandControl|";
            return id != null &&
                id.IndexOf('|') < 0 &&
                allowed.IndexOf(
                    "|" + id + "|",
                    StringComparison.Ordinal) >= 0;
        }

        private static Vector3 ParseSam3dVector(
            JSONNode node,
            string label)
        {
            JSONArray values = node == null ? null : node.AsArray;
            if (values == null || values.Count != 3)
            {
                throw new Exception(label + " must contain three numbers.");
            }
            float x = values[0].AsFloat;
            float y = values[1].AsFloat;
            float z = values[2].AsFloat;
            if (!IsFinite(x) || !IsFinite(y) || !IsFinite(z) ||
                Mathf.Abs(x) > MaximumSam3dCoordinate ||
                Mathf.Abs(y) > MaximumSam3dCoordinate ||
                Mathf.Abs(z) > MaximumSam3dCoordinate)
            {
                throw new Exception(
                    label + " contains a non-finite or out-of-range coordinate.");
            }
            return new Vector3(x, y, z);
        }

        private static Quaternion ParseSam3dQuaternion(
            JSONNode node,
            string label)
        {
            JSONArray values = node == null ? null : node.AsArray;
            if (values == null || values.Count != 4)
            {
                throw new Exception(label + " must contain four numbers.");
            }
            float x = values[0].AsFloat;
            float y = values[1].AsFloat;
            float z = values[2].AsFloat;
            float w = values[3].AsFloat;
            if (!IsFinite(x) || !IsFinite(y) ||
                !IsFinite(z) || !IsFinite(w))
            {
                throw new Exception(label + " contains a non-finite value.");
            }
            float magnitude =
                Mathf.Sqrt(x * x + y * y + z * z + w * w);
            if (!IsFinite(magnitude) ||
                magnitude < 0.5f ||
                magnitude > 1.5f)
            {
                throw new Exception(
                    label + " is not a bounded unit quaternion.");
            }
            return new Quaternion(
                x / magnitude,
                y / magnitude,
                z / magnitude,
                w / magnitude);
        }

        private static string Sam3dText(
            JSONNode node,
            string label,
            int maximumLength)
        {
            string value = ((string)node ?? "").Trim();
            if (value.Length == 0 || value.Length > maximumLength ||
                ContainsControlCharacter(value))
            {
                throw new Exception(
                    label + " must contain 1 to " +
                    maximumLength +
                    " printable characters.");
            }
            return value;
        }

        private static uint Sha256RotateRight(uint value, int count)
        {
            return (value >> count) | (value << (32 - count));
        }

        private static string Sha256Ascii(string value)
        {
            if (value == null)
            {
                throw new Exception("Cannot hash a null SAM3D solution.");
            }
            byte[] input = new byte[value.Length];
            int index;
            for (index = 0; index < value.Length; index++)
            {
                if (value[index] > 127)
                {
                    throw new Exception(
                        "The SAM3D solution must use ASCII JSON encoding.");
                }
                input[index] = (byte)value[index];
            }

            int paddedLength =
                ((input.Length + 9 + 63) / 64) * 64;
            byte[] message = new byte[paddedLength];
            Array.Copy(input, message, input.Length);
            message[input.Length] = 0x80;
            ulong bitLength = (ulong)input.Length * 8UL;
            for (index = 0; index < 8; index++)
            {
                message[paddedLength - 1 - index] =
                    (byte)(bitLength >> (index * 8));
            }

            uint[] constants = new uint[] {
                0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
                0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
                0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
                0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
                0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
                0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
                0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
                0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
                0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
                0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
                0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
                0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
                0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
                0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
                0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
                0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
            };
            uint[] hash = new uint[] {
                0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
            };
            uint[] schedule = new uint[64];
            unchecked
            {
                int offset;
                for (offset = 0; offset < message.Length; offset += 64)
                {
                    for (index = 0; index < 16; index++)
                    {
                        int cursor = offset + index * 4;
                        schedule[index] =
                            ((uint)message[cursor] << 24) |
                            ((uint)message[cursor + 1] << 16) |
                            ((uint)message[cursor + 2] << 8) |
                            message[cursor + 3];
                    }
                    for (index = 16; index < 64; index++)
                    {
                        uint before15 = schedule[index - 15];
                        uint before2 = schedule[index - 2];
                        uint sigma0 =
                            Sha256RotateRight(before15, 7) ^
                            Sha256RotateRight(before15, 18) ^
                            (before15 >> 3);
                        uint sigma1 =
                            Sha256RotateRight(before2, 17) ^
                            Sha256RotateRight(before2, 19) ^
                            (before2 >> 10);
                        schedule[index] =
                            schedule[index - 16] +
                            sigma0 +
                            schedule[index - 7] +
                            sigma1;
                    }

                    uint a = hash[0];
                    uint b = hash[1];
                    uint c = hash[2];
                    uint d = hash[3];
                    uint e = hash[4];
                    uint f = hash[5];
                    uint g = hash[6];
                    uint h = hash[7];
                    for (index = 0; index < 64; index++)
                    {
                        uint sum1 =
                            Sha256RotateRight(e, 6) ^
                            Sha256RotateRight(e, 11) ^
                            Sha256RotateRight(e, 25);
                        uint choose = (e & f) ^ ((~e) & g);
                        uint temporary1 =
                            h +
                            sum1 +
                            choose +
                            constants[index] +
                            schedule[index];
                        uint sum0 =
                            Sha256RotateRight(a, 2) ^
                            Sha256RotateRight(a, 13) ^
                            Sha256RotateRight(a, 22);
                        uint majority =
                            (a & b) ^ (a & c) ^ (b & c);
                        uint temporary2 = sum0 + majority;
                        h = g;
                        g = f;
                        f = e;
                        e = d + temporary1;
                        d = c;
                        c = b;
                        b = a;
                        a = temporary1 + temporary2;
                    }
                    hash[0] += a;
                    hash[1] += b;
                    hash[2] += c;
                    hash[3] += d;
                    hash[4] += e;
                    hash[5] += f;
                    hash[6] += g;
                    hash[7] += h;
                }
            }

            const string hexadecimal = "0123456789abcdef";
            char[] result = new char[64];
            for (index = 0; index < hash.Length; index++)
            {
                int digit;
                for (digit = 0; digit < 8; digit++)
                {
                    int shift = 28 - digit * 4;
                    result[index * 8 + digit] =
                        hexadecimal[
                            (int)((hash[index] >> shift) & 0x0fu)];
                }
            }
            return new string(result);
        }

        private static Sam3dSolution LoadSam3dSolution(
            BridgeRequest request)
        {
            string path =
                Sam3dRoot + "\\" + request.Sam3dJobId + ".json";
            if (!FileManagerSecure.FileExists(path))
            {
                throw new Exception(
                    "The requested SAM3D solution is not available.");
            }
            string payload = FileManagerSecure.ReadAllText(path);
            if (payload == null || payload.Length == 0 ||
                payload.Length > 131072)
            {
                throw new Exception(
                    "The SAM3D solution is empty or exceeds 128 KiB.");
            }
            if (!string.Equals(
                    Sha256Ascii(payload),
                    request.Sam3dSolutionSha256,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception(
                    "The SAM3D solution file digest no longer matches the request.");
            }
            JSONClass document = JSON.Parse(payload).AsObject;
            if (document == null ||
                document["schema"].AsInt != Sam3dSolutionSchema)
            {
                throw new Exception(
                    "The SAM3D solution schema is unsupported.");
            }

            Sam3dSolution solution = new Sam3dSolution();
            solution.JobId =
                ((string)document["jobId"] ?? "").Trim().ToLowerInvariant();
            solution.Revision =
                ((string)document["revision"] ?? "").Trim().ToLowerInvariant();
            if (!string.Equals(
                    solution.JobId,
                    request.Sam3dJobId,
                    StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(
                    solution.Revision,
                    request.Sam3dRevision,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception(
                    "The SAM3D solution no longer matches the requested revision.");
            }
            if ((string)document["coordinateSpace"] !=
                Sam3dCoordinateSpace)
            {
                throw new Exception(
                    "The SAM3D solution coordinate space is unsupported.");
            }

            JSONArray controllers = document["controllers"].AsArray;
            if (controllers == null ||
                controllers.Count != Sam3dControllerCount)
            {
                throw new Exception(
                    "The SAM3D solution must contain exactly 19 controllers.");
            }
            solution.Controllers =
                new List<Sam3dControllerSolution>();
            HashSet<string> seen = new HashSet<string>();
            int controllerIndex;
            for (controllerIndex = 0;
                 controllerIndex < controllers.Count;
                 controllerIndex++)
            {
                JSONClass value = controllers[controllerIndex].AsObject;
                string id =
                    value == null
                    ? ""
                    : ((string)value["id"] ?? "").Trim();
                if (!IsSam3dControllerId(id) || seen.Contains(id))
                {
                    throw new Exception(
                        "The SAM3D solution contains an unknown or duplicate controller.");
                }
                seen.Add(id);
                Sam3dControllerSolution controller =
                    new Sam3dControllerSolution();
                controller.Id = id;
                controller.Position =
                    ParseSam3dVector(
                        value["position"],
                        id + " position");
                controller.Rotation =
                    ParseSam3dQuaternion(
                        value["rotation"],
                        id + " rotation");
                solution.Controllers.Add(controller);
            }

            JSONClass camera = document["camera"].AsObject;
            if (camera == null)
            {
                throw new Exception(
                    "The SAM3D solution has no camera.");
            }
            solution.Camera = new Sam3dCameraSolution();
            solution.Camera.Position =
                ParseSam3dVector(camera["position"], "camera position");
            solution.Camera.Rotation =
                ParseSam3dQuaternion(camera["rotation"], "camera rotation");
            solution.Camera.FlatHorizontalFov =
                camera["flatHorizontalFov"].AsFloat;
            if (!IsFinite(solution.Camera.FlatHorizontalFov) ||
                solution.Camera.FlatHorizontalFov < 0.1f ||
                solution.Camera.FlatHorizontalFov > 179.9f)
            {
                throw new Exception(
                    "camera flatHorizontalFov must be between 0.1 and 179.9.");
            }
            solution.Camera.AspectRatio =
                Sam3dText(camera["aspectRatio"], "camera aspectRatio", 16);
            solution.Camera.OutputResolution =
                Sam3dText(
                    camera["outputResolution"],
                    "camera outputResolution",
                    64);
            solution.Camera.ImageFormat =
                Sam3dText(camera["imageFormat"], "camera imageFormat", 128);
            solution.Camera.BaseFilename =
                Sam3dText(camera["basename"], "camera basename", 64);
            if (solution.Camera.BaseFilename != solution.JobId)
            {
                throw new Exception(
                    "camera basename does not match the immutable job ID.");
            }
            return solution;
        }

        private static MVRScript FindSam3dRenderer(Atom camera)
        {
            if (camera == null || camera.type != "Empty")
            {
                return null;
            }
            List<string> storableIds = camera.GetStorableIDs();
            if (storableIds == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < storableIds.Count; index++)
            {
                string storableId = storableIds[index] ?? "";
                if (!storableId.EndsWith(
                        Sam3dRendererSuffix,
                        StringComparison.Ordinal))
                {
                    continue;
                }
                MVRScript renderer =
                    camera.GetStorableByID(storableId) as MVRScript;
                if (renderer == null ||
                    renderer.GetAction(Sam3dCaptureAction) == null ||
                    renderer.GetStringJSONParam(Sam3dRequestIdParam) == null ||
                    renderer.GetStringJSONParam(Sam3dBaseFilenameParam) == null ||
                    renderer.GetStringJSONParam(Sam3dStatusParam) == null ||
                    renderer.GetStringJSONParam(Sam3dLastOutputParam) == null ||
                    renderer.GetStringJSONParam(Sam3dErrorParam) == null)
                {
                    continue;
                }
                return renderer;
            }
            return null;
        }

        private static JSONStorableStringChooser RequireSam3dChooser(
            MVRScript renderer,
            string name)
        {
            JSONStorableStringChooser chooser =
                renderer.GetStringChooserJSONParam(name);
            if (chooser == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer has no " +
                    name +
                    " chooser.");
            }
            return chooser;
        }

        private static void SetSam3dChoice(
            MVRScript renderer,
            string name,
            string value)
        {
            JSONStorableStringChooser chooser =
                RequireSam3dChooser(renderer, name);
            if (chooser.choices == null ||
                !chooser.choices.Contains(value))
            {
                throw new Exception(
                    "The VR-and-Funscript renderer does not support " +
                    name +
                    " value " +
                    value +
                    ".");
            }
            chooser.val = value;
        }

        private static string Sam3dImageFormatLabel(string key)
        {
            if (key == "jpeg")
            {
                return "JPEG (Lossy, Small & Fast)\nNo Transparency";
            }
            if (key == "png")
            {
                return "PNG (Lossless, Big & Slow)\nTransparency Support";
            }
            throw new Exception(
                "camera imageFormat must be either jpeg or png.");
        }

        private static void ConfigureSam3dRenderer(
            MVRScript renderer,
            Sam3dCameraSolution camera)
        {
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            JSONStorableBool funscripts =
                renderer.GetBoolJSONParam("Generate Funscripts");
            if (fov == null || funscripts == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer is missing required flat-render controls.");
            }
            SetSam3dChoice(renderer, "Camera Target", "None");
            SetSam3dChoice(renderer, "Render Mode", "Flat");
            SetSam3dChoice(
                renderer,
                "Aspect Ratio",
                camera.AspectRatio);
            SetSam3dChoice(
                renderer,
                "Output Resolution",
                camera.OutputResolution);
            SetSam3dChoice(
                renderer,
                "Image Format",
                Sam3dImageFormatLabel(camera.ImageFormat));
            fov.val = camera.FlatHorizontalFov;
            funscripts.val = false;
        }

        private static Dictionary<string, FreeControllerV3>
            Sam3dPersonControllers(Atom person)
        {
            Dictionary<string, FreeControllerV3> result =
                new Dictionary<string, FreeControllerV3>();
            FreeControllerV3[] controllers =
                person.GetComponentsInChildren<FreeControllerV3>(true);
            int index;
            for (index = 0; index < controllers.Length; index++)
            {
                FreeControllerV3 controller = controllers[index];
                if (controller != null &&
                    IsSam3dControllerId(controller.name) &&
                    !result.ContainsKey(controller.name))
                {
                    result.Add(controller.name, controller);
                }
            }
            return result;
        }

        private static Sam3dUndoSnapshot SnapshotSam3dState(
            BridgeRequest request,
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers)
        {
            Sam3dUndoSnapshot snapshot = new Sam3dUndoSnapshot();
            snapshot.JobId = solution.JobId;
            snapshot.Revision = solution.Revision;
            snapshot.TargetUid = request.TargetUid;
            snapshot.CameraUid = request.Sam3dCameraUid;
            snapshot.Person = person;
            snapshot.PersonCollisionEnabled = person.collisionEnabled;
            snapshot.Controllers = new List<Sam3dControllerUndo>();
            int index;
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Sam3dControllerSolution target =
                    solution.Controllers[index];
                FreeControllerV3 controller;
                if (!controllers.TryGetValue(target.Id, out controller) ||
                    controller == null)
                {
                    throw new Exception(
                        "Person is missing required controller " +
                        target.Id +
                        ".");
                }
                Sam3dControllerUndo saved =
                    new Sam3dControllerUndo();
                saved.Controller = controller;
                if (controller.control == null)
                {
                    throw new Exception(
                        "Person controller " +
                        target.Id +
                        " has no authoritative control transform.");
                }
                saved.Position = controller.control.position;
                saved.Rotation = controller.control.rotation;
                saved.PositionState = controller.currentPositionState;
                saved.RotationState = controller.currentRotationState;
                saved.PhysicsEnabled = controller.physicsEnabled;
                snapshot.Controllers.Add(saved);
            }

            snapshot.CameraController = camera.mainController;
            if (snapshot.CameraController == null)
            {
                throw new Exception(
                    "The camera Empty has no main controller.");
            }
            if (snapshot.CameraController.control == null)
            {
                throw new Exception(
                    "The camera Empty has no main control transform.");
            }
            snapshot.CameraPosition =
                snapshot.CameraController.control.position;
            snapshot.CameraRotation =
                snapshot.CameraController.control.rotation;
            snapshot.CameraPositionState =
                snapshot.CameraController.currentPositionState;
            snapshot.CameraRotationState =
                snapshot.CameraController.currentRotationState;
            snapshot.CameraPhysicsEnabled =
                snapshot.CameraController.physicsEnabled;
            snapshot.Renderer = renderer;
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            JSONStorableBool funscripts =
                renderer.GetBoolJSONParam("Generate Funscripts");
            if (fov == null || funscripts == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer has incomplete settings.");
            }
            snapshot.FlatHorizontalFov = fov.val;
            snapshot.CameraTarget =
                RequireSam3dChooser(renderer, "Camera Target").val;
            snapshot.AspectRatio =
                RequireSam3dChooser(renderer, "Aspect Ratio").val;
            snapshot.OutputResolution =
                RequireSam3dChooser(renderer, "Output Resolution").val;
            snapshot.RenderMode =
                RequireSam3dChooser(renderer, "Render Mode").val;
            snapshot.ImageFormat =
                RequireSam3dChooser(renderer, "Image Format").val;
            snapshot.GenerateFunscripts = funscripts.val;
            return snapshot;
        }

        private static void BeginSam3dPoseTransaction(
            Sam3dUndoSnapshot snapshot)
        {
            if (snapshot == null ||
                snapshot.Person == null)
            {
                throw new Exception(
                    "The saved SAM3D Person is no longer available.");
            }
            snapshot.Person.collisionEnabled = false;
            try
            {
                int index;
                for (index = 0;
                     index < snapshot.Controllers.Count;
                     index++)
                {
                    Sam3dControllerUndo saved =
                        snapshot.Controllers[index];
                    if (saved.Controller == null)
                    {
                        throw new Exception(
                            "A saved Person controller is no longer available.");
                    }
                    saved.Controller.physicsEnabled = false;
                }
                if (snapshot.CameraController == null)
                {
                    throw new Exception(
                        "The saved SAM3D camera is no longer available.");
                }
                snapshot.CameraController.physicsEnabled = false;
            }
            catch
            {
                FinishSam3dPoseTransaction(
                    snapshot,
                    "Cancel VAM-PIP SAM3D pose");
                throw;
            }
        }

        private static void FinishSam3dPoseTransaction(
            Sam3dUndoSnapshot snapshot,
            string reason)
        {
            if (snapshot == null ||
                snapshot.Person == null)
            {
                throw new Exception(
                    "The saved SAM3D Person is no longer available.");
            }
            try
            {
                int index;
                for (index = 0;
                     index < snapshot.Controllers.Count;
                     index++)
                {
                    Sam3dControllerUndo saved =
                        snapshot.Controllers[index];
                    if (saved.Controller != null)
                    {
                        saved.Controller.physicsEnabled =
                            saved.PhysicsEnabled;
                    }
                }
                if (snapshot.CameraController != null)
                {
                    snapshot.CameraController.physicsEnabled =
                        snapshot.CameraPhysicsEnabled;
                }
            }
            finally
            {
                try
                {
                    snapshot.Person.collisionEnabled =
                        snapshot.PersonCollisionEnabled;
                }
                finally
                {
                    SuperController.singleton.ResetSimulation(
                        Sam3dPhysicsResetFrames,
                        reason,
                        true);
                }
            }
        }

        private static void RestoreSam3dSnapshot(
            Sam3dUndoSnapshot snapshot)
        {
            if (snapshot == null)
            {
                throw new Exception("No SAM3D undo snapshot is available.");
            }
            BeginSam3dPoseTransaction(snapshot);
            try
            {
                RestoreSam3dSnapshotContents(snapshot);
            }
            finally
            {
                FinishSam3dPoseTransaction(
                    snapshot,
                    "Restore VAM-PIP SAM3D pose");
            }
        }

        private static void RestoreSam3dSnapshotContents(
            Sam3dUndoSnapshot snapshot)
        {
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (saved.Controller == null ||
                    saved.Controller.control == null)
                {
                    throw new Exception(
                        "A saved Person controller is no longer available.");
                }
                saved.Controller.currentPositionState =
                    saved.PositionState;
                saved.Controller.currentRotationState =
                    saved.RotationState;
                saved.Controller.control.position = saved.Position;
                saved.Controller.control.rotation = saved.Rotation;
                if (saved.Controller.onPositionChangeHandlers != null)
                {
                    saved.Controller.onPositionChangeHandlers(
                        saved.Controller);
                }
                if (saved.Controller.followWhenOff != null)
                {
                    saved.Controller.followWhenOff.position =
                        saved.Position;
                    saved.Controller.followWhenOff.rotation =
                        saved.Rotation;
                }
                if (saved.PositionState ==
                        FreeControllerV3.PositionState.Comply ||
                    saved.RotationState ==
                        FreeControllerV3.RotationState.Comply)
                {
                    saved.Controller.PauseComply();
                }
            }
            if (snapshot.CameraCreated)
            {
                Atom createdCamera =
                    SuperController.singleton.GetAtomByUid(
                        snapshot.CameraUid);
                if (createdCamera == null ||
                    createdCamera.type != "Empty" ||
                    !object.ReferenceEquals(
                        createdCamera.mainController,
                        snapshot.CameraController) ||
                    !object.ReferenceEquals(
                        FindSam3dRenderer(createdCamera),
                        snapshot.Renderer))
                {
                    throw new Exception(
                        "The generated SAM3D camera is no longer available.");
                }
                SuperController.singleton.RemoveAtom(createdCamera);
                return;
            }
            if (snapshot.CameraController == null ||
                snapshot.CameraController.control == null ||
                snapshot.Renderer == null)
            {
                throw new Exception(
                    "The saved SAM3D camera is no longer available.");
            }
            snapshot.CameraController.currentPositionState =
                snapshot.CameraPositionState;
            snapshot.CameraController.currentRotationState =
                snapshot.CameraRotationState;
            snapshot.CameraController.control.position =
                snapshot.CameraPosition;
            snapshot.CameraController.control.rotation =
                snapshot.CameraRotation;
            if (snapshot.CameraController.onPositionChangeHandlers != null)
            {
                snapshot.CameraController.onPositionChangeHandlers(
                    snapshot.CameraController);
            }
            if (snapshot.CameraController.followWhenOff != null)
            {
                snapshot.CameraController.followWhenOff.position =
                    snapshot.CameraPosition;
                snapshot.CameraController.followWhenOff.rotation =
                    snapshot.CameraRotation;
            }
            if (snapshot.CameraPositionState ==
                    FreeControllerV3.PositionState.Comply ||
                snapshot.CameraRotationState ==
                    FreeControllerV3.RotationState.Comply)
            {
                snapshot.CameraController.PauseComply();
            }
            snapshot.Renderer.GetFloatJSONParam(
                "Flat Horizontal FOV").val =
                snapshot.FlatHorizontalFov;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Camera Target").val =
                snapshot.CameraTarget;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Aspect Ratio").val =
                snapshot.AspectRatio;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Output Resolution").val =
                snapshot.OutputResolution;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Render Mode").val =
                snapshot.RenderMode;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Image Format").val =
                snapshot.ImageFormat;
            snapshot.Renderer.GetBoolJSONParam(
                "Generate Funscripts").val =
                snapshot.GenerateFunscripts;
        }

        private Sam3dUndoSnapshot CurrentSam3dSnapshot()
        {
            Sam3dUndoSnapshot snapshot = _sam3dUndoSnapshot;
            if (snapshot == null ||
                SuperController.singleton == null)
            {
                _sam3dUndoSnapshot = null;
                return null;
            }
            Atom person =
                SuperController.singleton.GetAtomByUid(
                    snapshot.TargetUid);
            Atom camera =
                SuperController.singleton.GetAtomByUid(
                    snapshot.CameraUid);
            if (person == null ||
                person.type != "Person" ||
                !object.ReferenceEquals(
                    person,
                    snapshot.Person) ||
                camera == null ||
                camera.type != "Empty" ||
                !object.ReferenceEquals(
                    camera.mainController,
                    snapshot.CameraController) ||
                !object.ReferenceEquals(
                    FindSam3dRenderer(camera),
                    snapshot.Renderer))
            {
                _sam3dUndoSnapshot = null;
                return null;
            }
            Dictionary<string, FreeControllerV3> controllers =
                Sam3dPersonControllers(person);
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                FreeControllerV3 current;
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (saved.Controller == null ||
                    !controllers.TryGetValue(
                        saved.Controller.name,
                        out current) ||
                    !object.ReferenceEquals(
                        current,
                        saved.Controller))
                {
                    _sam3dUndoSnapshot = null;
                    return null;
                }
            }
            return snapshot;
        }

        private static Quaternion Sam3dAnchorRotation(Atom person)
        {
            Transform anchor =
                person.mainController == null
                ? null
                : person.mainController.control;
            if (anchor == null)
            {
                throw new Exception(
                    "The target Person has no main controller.");
            }
            Vector3 forward = anchor.forward;
            forward.y = 0f;
            if (forward.sqrMagnitude < 0.0001f)
            {
                forward = Vector3.forward;
            }
            return Quaternion.LookRotation(
                forward.normalized,
                Vector3.up);
        }

        private static Sam3dApplyDiagnostics NewSam3dApplyDiagnostics(
            BridgeRequest request)
        {
            Sam3dApplyDiagnostics diagnostics =
                new Sam3dApplyDiagnostics();
            diagnostics.RequestId = request.RequestId ?? "";
            diagnostics.CapturedAtUtc = "";
            diagnostics.Error = "";
            diagnostics.Controllers =
                new List<Sam3dControllerDiagnostic>();
            Sam3dControllerDiagnostic head =
                new Sam3dControllerDiagnostic();
            head.Id = "headControl";
            diagnostics.Controllers.Add(head);
            Sam3dControllerDiagnostic neck =
                new Sam3dControllerDiagnostic();
            neck.Id = "neckControl";
            diagnostics.Controllers.Add(neck);
            return diagnostics;
        }

        private static void RecordSam3dRequestedTransform(
            Sam3dApplyDiagnostics diagnostics,
            string id,
            Vector3 position,
            Quaternion rotation)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null)
            {
                return;
            }
            int index;
            for (index = 0;
                 index < diagnostics.Controllers.Count &&
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                if (item != null && item.Id == id)
                {
                    item.RequestedPosition = position;
                    item.RequestedRotation = rotation;
                    item.RequestedCaptured = true;
                    return;
                }
            }
        }

        private static void CaptureSam3dSettledDiagnostics(
            Sam3dApplyDiagnostics diagnostics,
            Dictionary<string, FreeControllerV3> controllers)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null ||
                diagnostics.Controllers.Count !=
                    Sam3dDiagnosticControllerCount)
            {
                throw new Exception(
                    "The fixed SAM3D controller diagnostic set is incomplete.");
            }
            int index;
            for (index = 0;
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                FreeControllerV3 controller;
                if (item == null ||
                    !item.RequestedCaptured ||
                    controllers == null ||
                    !controllers.TryGetValue(item.Id, out controller) ||
                    controller == null ||
                    controller.control == null)
                {
                    throw new Exception(
                        "Could not inspect settled " +
                        (item == null ? "SAM3D controller" : item.Id) +
                        ".");
                }
                item.ActualPosition = controller.control.position;
                item.ActualRotation = controller.control.rotation;
                item.PositionState = controller.currentPositionState;
                item.RotationState = controller.currentRotationState;
                item.PhysicsEnabled = controller.physicsEnabled;
                item.Possessed = controller.possessed;
                item.StartedPossess = controller.startedPossess;
                item.IsGrabbing = controller.isGrabbing;
                item.ActualCaptured = true;
            }
            diagnostics.CapturedAtUtc = UtcNow();
        }

        private static void ApplySam3dTransforms(
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers,
            Sam3dUndoSnapshot snapshot,
            Sam3dApplyDiagnostics diagnostics)
        {
            BeginSam3dPoseTransaction(snapshot);
            try
            {
                ApplySam3dTransformContents(
                    solution,
                    person,
                    camera,
                    renderer,
                    controllers,
                    diagnostics);
            }
            finally
            {
                FinishSam3dPoseTransaction(
                    snapshot,
                    "Apply VAM-PIP SAM3D pose");
            }
        }

        private static void ApplySam3dTransformContents(
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers,
            Sam3dApplyDiagnostics diagnostics)
        {
            FreeControllerV3 hip;
            if (!controllers.TryGetValue("hipControl", out hip) ||
                hip == null)
            {
                throw new Exception(
                    "The target Person has no hipControl.");
            }
            if (hip.control == null)
            {
                throw new Exception(
                    "The target Person hipControl has no authoritative control transform.");
            }
            Vector3 anchorPosition = hip.control.position;
            Quaternion anchorRotation = Sam3dAnchorRotation(person);
            int index;
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Sam3dControllerSolution target =
                    solution.Controllers[index];
                FreeControllerV3 controller =
                    controllers[target.Id];
                if (controller.control == null)
                {
                    throw new Exception(
                        "Person controller " +
                        target.Id +
                        " has no authoritative control transform.");
                }
                if (controller.currentPositionState ==
                        FreeControllerV3.PositionState.Comply ||
                    controller.currentRotationState ==
                        FreeControllerV3.RotationState.Comply)
                {
                    controller.PauseComply();
                }
                controller.currentPositionState =
                    FreeControllerV3.PositionState.On;
                controller.currentRotationState =
                    FreeControllerV3.RotationState.On;
                Vector3 requestedPosition =
                    anchorPosition +
                    anchorRotation * target.Position;
                Quaternion requestedRotation =
                    anchorRotation * target.Rotation;
                RecordSam3dRequestedTransform(
                    diagnostics,
                    target.Id,
                    requestedPosition,
                    requestedRotation);
                controller.control.position = requestedPosition;
                controller.control.rotation = requestedRotation;
                if (controller.onPositionChangeHandlers != null)
                {
                    controller.onPositionChangeHandlers(controller);
                }
            }

            FreeControllerV3 cameraController = camera.mainController;
            if (cameraController == null ||
                cameraController.control == null)
            {
                throw new Exception(
                    "The camera Empty has no main control transform.");
            }
            cameraController.currentPositionState =
                FreeControllerV3.PositionState.On;
            cameraController.currentRotationState =
                FreeControllerV3.RotationState.On;
            cameraController.control.position =
                anchorPosition +
                anchorRotation * solution.Camera.Position;
            cameraController.control.rotation =
                anchorRotation * solution.Camera.Rotation;
            if (cameraController.onPositionChangeHandlers != null)
            {
                cameraController.onPositionChangeHandlers(
                    cameraController);
            }
            ConfigureSam3dRenderer(renderer, solution.Camera);
        }

        private void FinishSam3dActionOk(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            RecordSam3dAction(request, StateOk, message);
            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam-sam3d",
                message);
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " + message);
        }

        private void FinishSam3dActionError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            RecordSam3dAction(request, StateError, message);
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private static IEnumerator WaitForSam3dPhysicsSettlement()
        {
            int frame;
            for (frame = 0;
                 frame < Sam3dPhysicsResetFrames;
                 frame++)
            {
                yield return new WaitForFixedUpdate();
            }
            yield return new WaitForEndOfFrame();
        }

        private static JSONClass Sam3dDiagnosticVector(Vector3 value)
        {
            JSONClass result = new JSONClass();
            result["x"].AsFloat = value.x;
            result["y"].AsFloat = value.y;
            result["z"].AsFloat = value.z;
            return result;
        }

        private static JSONClass Sam3dDiagnosticQuaternion(
            Quaternion value)
        {
            JSONClass result = new JSONClass();
            result["x"].AsFloat = value.x;
            result["y"].AsFloat = value.y;
            result["z"].AsFloat = value.z;
            result["w"].AsFloat = value.w;
            return result;
        }

        private static JSONClass BuildSam3dSettlementStatus(
            Sam3dApplyDiagnostics diagnostics)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null)
            {
                return null;
            }
            JSONClass result = new JSONClass();
            result["schema"].AsInt = Sam3dDiagnosticSchema;
            result["requestId"] = diagnostics.RequestId ?? "";
            result["capturedAtUtc"] =
                diagnostics.CapturedAtUtc ?? "";
            result["settleFrames"].AsInt =
                Sam3dPhysicsResetFrames;
            result["controllerLimit"].AsInt =
                Sam3dDiagnosticControllerCount;
            result["error"] = diagnostics.Error ?? "";
            bool available =
                (diagnostics.Error ?? "").Length == 0 &&
                diagnostics.Controllers.Count ==
                    Sam3dDiagnosticControllerCount;
            JSONArray controllerResults = new JSONArray();
            int index;
            for (index = 0;
                 index < diagnostics.Controllers.Count &&
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                if (item == null)
                {
                    available = false;
                    continue;
                }
                JSONClass controller = new JSONClass();
                controller["id"] = item.Id ?? "";
                if (item.RequestedCaptured)
                {
                    JSONClass requested = new JSONClass();
                    requested["position"] =
                        Sam3dDiagnosticVector(
                            item.RequestedPosition);
                    requested["rotation"] =
                        Sam3dDiagnosticQuaternion(
                            item.RequestedRotation);
                    controller["requested"] = requested;
                }
                if (item.ActualCaptured)
                {
                    JSONClass actual = new JSONClass();
                    actual["position"] =
                        Sam3dDiagnosticVector(
                            item.ActualPosition);
                    actual["rotation"] =
                        Sam3dDiagnosticQuaternion(
                            item.ActualRotation);
                    controller["actual"] = actual;
                    controller["positionErrorMeters"].AsFloat =
                        Vector3.Distance(
                            item.RequestedPosition,
                            item.ActualPosition);
                    controller["rotationErrorDegrees"].AsFloat =
                        Quaternion.Angle(
                            item.RequestedRotation,
                            item.ActualRotation);
                    JSONClass state = new JSONClass();
                    state["position"] =
                        item.PositionState.ToString();
                    state["rotation"] =
                        item.RotationState.ToString();
                    state["physicsEnabled"].AsBool =
                        item.PhysicsEnabled;
                    state["possessed"].AsBool =
                        item.Possessed;
                    state["startedPossess"].AsBool =
                        item.StartedPossess;
                    state["isGrabbing"].AsBool =
                        item.IsGrabbing;
                    controller["state"] = state;
                }
                else
                {
                    available = false;
                }
                controllerResults.Add(controller);
            }
            result["available"].AsBool = available;
            result["controllers"] = controllerResults;
            return result;
        }

        private static string RemoveCreatedSam3dCamera(
            BridgeRequest request,
            Sam3dCameraResult result)
        {
            if (result == null || !result.Created)
            {
                return "";
            }
            try
            {
                Atom camera =
                    SuperController.singleton == null
                    ? null
                    : SuperController.singleton.GetAtomByUid(
                        request.Sam3dCameraUid);
                if (camera == null)
                {
                    result.Atom = null;
                    result.Created = false;
                    return "";
                }
                if (
                    result.Atom != null &&
                    !object.ReferenceEquals(camera, result.Atom))
                {
                    throw new Exception(
                        "the generated camera identity changed");
                }
                if (camera.type != "Empty" ||
                    !string.Equals(
                        camera.uid,
                        request.Sam3dCameraUid,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "the generated camera identity changed");
                }
                SuperController.singleton.RemoveAtom(camera);
                result.Atom = null;
                result.Created = false;
                return "";
            }
            catch (Exception exception)
            {
                return
                    " Could not remove the generated SAM3D camera: " +
                    DescribeException(exception);
            }
        }

        private void RecordSam3dAction(
            BridgeRequest request,
            string state,
            string message)
        {
            if (request == null)
            {
                return;
            }
            _lastSam3dRequestId = request.RequestId ?? "";
            _lastSam3dCommand = request.Command ?? "";
            _lastSam3dJobId = request.Sam3dJobId ?? "";
            _lastSam3dRevision = request.Sam3dRevision ?? "";
            _lastSam3dCameraUid = request.Sam3dCameraUid ?? "";
            _lastSam3dState = state ?? "";
            _lastSam3dMessage = message ?? "";
            if (_lastSam3dMessage.Length > 1000)
            {
                _lastSam3dMessage =
                    _lastSam3dMessage.Substring(0, 1000);
            }
        }

        private IEnumerator EnsureSam3dCamera(
            BridgeRequest request,
            Sam3dCameraResult result)
        {
            result.Atom = null;
            result.Created = false;
            result.Error = "";
            Atom camera =
                SuperController.singleton.GetAtomByUid(
                    request.Sam3dCameraUid);
            if (camera != null)
            {
                if (camera.type != "Empty")
                {
                    result.Error =
                        "cameraUid is already used by an atom of type " +
                        camera.type +
                        ", not Empty.";
                    yield break;
                }
                if (FindSam3dRenderer(camera) == null)
                {
                    result.Error =
                        "The selected Empty does not contain the VAM-PIP-enabled " +
                        "VR Video and Funscript Exporter.";
                    yield break;
                }
                result.Atom = camera;
                yield break;
            }
            if (!request.Sam3dCreateCamera)
            {
                result.Error =
                    "cameraUid does not identify an existing compatible Empty.";
                yield break;
            }
            if (!FileManagerSecure.FileExists(Sam3dCameraPreset))
            {
                result.Error =
                    "The fixed VAM-PIP SAM3D camera preset is not installed.";
                yield break;
            }

            IEnumerator addRoutine = null;
            try
            {
                PublishStatus(
                    StateAdding,
                    request.RequestId,
                    "",
                    "",
                    "vam",
                    "Adding SAM3D VR-and-Funscript camera " +
                    request.Sam3dCameraUid +
                    ".");
                addRoutine =
                    SuperController.singleton.AddAtomByType(
                        "Empty",
                        request.Sam3dCameraUid,
                        true);
                if (addRoutine == null)
                {
                    throw new Exception(
                        "VaM did not provide an Empty creation routine.");
                }
                // From this point onward the fixed UID belongs to this
                // transaction, even if VaM fails part-way through creation.
                result.Created = true;
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not create the SAM3D camera: " +
                    DescribeException(exception);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                try
                {
                    if (Time.realtimeSinceStartup >= deadline)
                    {
                        throw new Exception(
                            "Empty creation did not finish within 120 seconds.");
                    }
                    hasNext = addRoutine.MoveNext();
                    if (hasNext)
                    {
                        current = addRoutine.Current;
                    }
                }
                catch (Exception exception)
                {
                    result.Error =
                        "Could not create the SAM3D camera: " +
                        DescribeException(exception);
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }
            yield return new WaitForEndOfFrame();

            camera =
                SuperController.singleton.GetAtomByUid(
                    request.Sam3dCameraUid);
            if (camera == null || camera.type != "Empty")
            {
                result.Error =
                    "VaM completed creation without the requested Empty.";
                yield break;
            }

            try
            {
                JSONStorable preset =
                    camera.GetStorableByID("Preset");
                JSONStorableUrl browsePath =
                    preset == null
                    ? null
                    : preset.GetUrlJSONParam("presetBrowsePath");
                if (preset == null || browsePath == null)
                {
                    throw new Exception(
                        "The camera Empty does not expose preset loading.");
                }
                JSONStorableBool loadOnSelect =
                    preset.GetBoolJSONParam("loadPresetOnSelect");
                bool previous =
                    loadOnSelect != null && loadOnSelect.val;
                if (loadOnSelect != null)
                {
                    loadOnSelect.val = false;
                }
                try
                {
                    browsePath.val =
                        SuperController.singleton.NormalizePath(
                            Sam3dCameraPreset);
                    preset.CallAction("LoadPreset");
                }
                finally
                {
                    if (loadOnSelect != null)
                    {
                        loadOnSelect.val = previous;
                    }
                }
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not load the fixed SAM3D camera preset: " +
                    DescribeException(exception);
                yield break;
            }

            LoadingWaitResult loading = new LoadingWaitResult();
            yield return WaitForVaMLoading(
                "SAM3D camera preset loading",
                loading);
            if (loading.Error.Length != 0)
            {
                result.Error = loading.Error;
                yield break;
            }

            deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (FindSam3dRenderer(camera) == null &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }
            if (FindSam3dRenderer(camera) == null)
            {
                result.Error =
                    "The VAM-PIP-enabled VR Video and Funscript Exporter " +
                    "did not become ready within 120 seconds.";
                yield break;
            }
            result.Atom = camera;
        }

        private IEnumerator ExecuteApplySam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Validating the SAM3D pose and camera solution.");

            Sam3dSolution solution = null;
            Atom person = null;
            string preparationError = "";
            try
            {
                if (CurrentSam3dSnapshot() != null)
                {
                    throw new Exception(
                        "Undo the currently applied SAM3D result before applying another.");
                }
                solution = LoadSam3dSolution(request);
                person =
                    SuperController.singleton.GetAtomByUid(
                        request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify an existing Person.");
                }
            }
            catch (Exception exception)
            {
                preparationError =
                    "Could not prepare the SAM3D result: " +
                    DescribeException(exception);
            }
            if (preparationError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    preparationError);
                yield break;
            }

            Sam3dCameraResult cameraResult =
                new Sam3dCameraResult();
            yield return EnsureSam3dCamera(request, cameraResult);
            if (cameraResult.Error.Length != 0)
            {
                cameraResult.Error +=
                    RemoveCreatedSam3dCamera(
                        request,
                        cameraResult);
                FinishSam3dActionError(
                    request,
                    startedAt,
                    cameraResult.Error);
                yield break;
            }

            Sam3dUndoSnapshot snapshot = null;
            string applyError = "";
            try
            {
                MVRScript renderer =
                    FindSam3dRenderer(cameraResult.Atom);
                if (renderer == null)
                {
                    throw new Exception(
                        "The selected camera has no compatible renderer.");
                }
                Dictionary<string, FreeControllerV3> controllers =
                    Sam3dPersonControllers(person);
                snapshot =
                    SnapshotSam3dState(
                        request,
                        solution,
                        person,
                        cameraResult.Atom,
                        renderer,
                        controllers);
                snapshot.Diagnostics =
                    NewSam3dApplyDiagnostics(request);
                snapshot.CameraCreated =
                    cameraResult.Created;
                ApplySam3dTransforms(
                    solution,
                    person,
                    cameraResult.Atom,
                    renderer,
                    controllers,
                    snapshot,
                    snapshot.Diagnostics);
                _sam3dUndoSnapshot = snapshot;
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not apply the SAM3D result: " +
                    DescribeException(exception);
                if (snapshot != null)
                {
                    try
                    {
                        RestoreSam3dSnapshot(snapshot);
                    }
                    catch (Exception restoreException)
                    {
                        applyError +=
                            " Automatic rollback also failed: " +
                            DescribeException(restoreException);
                    }
                }
                applyError +=
                    RemoveCreatedSam3dCamera(
                        request,
                        cameraResult);
            }
            if (snapshot != null)
            {
                yield return WaitForSam3dPhysicsSettlement();
            }
            if (applyError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    applyError);
                yield break;
            }
            try
            {
                CaptureSam3dSettledDiagnostics(
                    snapshot.Diagnostics,
                    Sam3dPersonControllers(person));
            }
            catch (Exception exception)
            {
                snapshot.Diagnostics.Error =
                    DescribeException(exception);
                snapshot.Diagnostics.CapturedAtUtc = UtcNow();
            }

            FinishSam3dActionOk(
                request,
                startedAt,
                "SAM3D pose and VR-and-Funscript camera applied. Undo is available.");
        }

        private IEnumerator ExecuteUndoSam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Restoring the previous Person and camera state.");
            bool restoreAttempted = false;
            string restoreError = "";
            try
            {
                Sam3dUndoSnapshot snapshot =
                    CurrentSam3dSnapshot();
                if (snapshot == null ||
                    !string.Equals(
                        snapshot.JobId,
                        request.Sam3dJobId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.Sam3dRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "No matching in-memory SAM3D undo snapshot is available.");
                }
                restoreAttempted = true;
                RestoreSam3dSnapshot(snapshot);
                _sam3dUndoSnapshot = null;
            }
            catch (Exception exception)
            {
                restoreError =
                    "Could not undo the SAM3D result: " +
                    DescribeException(exception);
            }
            if (restoreAttempted)
            {
                yield return WaitForSam3dPhysicsSettlement();
            }
            if (restoreError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    restoreError);
                yield break;
            }
            FinishSam3dActionOk(
                request,
                startedAt,
                "Previous Person and camera state restored.");
        }

        private static bool IsSafeSam3dOutput(
            string path,
            string requestId,
            string baseFilename)
        {
            if (path == null)
            {
                return false;
            }
            string normalized = path.Replace('\\', '/');
            const string screenshotPrefix =
                "Saves/screenshots/VAMPip/";
            const string legacyPrefix =
                "Saves/VR_Videos_And_Funscripts/";
            string prefix = "";
            if (normalized.StartsWith(
                    screenshotPrefix,
                    StringComparison.Ordinal))
            {
                prefix = screenshotPrefix;
            }
            else if (normalized.StartsWith(
                         legacyPrefix,
                         StringComparison.Ordinal))
            {
                prefix = legacyPrefix;
            }
            if (prefix.Length == 0 ||
                normalized.IndexOf("..", StringComparison.Ordinal) >= 0)
            {
                return false;
            }
            string expected =
                prefix +
                "vampip_" +
                requestId +
                "_" +
                baseFilename;
            return string.Equals(
                    normalized,
                    expected + ".jpg",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(
                    normalized,
                    expected + ".png",
                    StringComparison.OrdinalIgnoreCase);
        }

        private IEnumerator ExecuteCaptureSam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateCapturingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Starting the VR-and-Funscript camera capture.");
            Sam3dSolution solution = null;
            MVRScript renderer = null;
            string setupError = "";
            try
            {
                solution = LoadSam3dSolution(request);
                Atom camera =
                    SuperController.singleton.GetAtomByUid(
                        request.Sam3dCameraUid);
                renderer = FindSam3dRenderer(camera);
                if (renderer == null)
                {
                    throw new Exception(
                        "cameraUid does not identify a compatible renderer Empty.");
                }
                Sam3dUndoSnapshot snapshot =
                    CurrentSam3dSnapshot();
                if (snapshot == null ||
                    !string.Equals(
                        snapshot.JobId,
                        request.Sam3dJobId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.Sam3dRevision,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.CameraUid,
                        request.Sam3dCameraUid,
                        StringComparison.Ordinal) ||
                    !object.ReferenceEquals(
                        snapshot.Renderer,
                        renderer))
                {
                    throw new Exception(
                        "The requested SAM3D pose and camera are not the currently applied in-memory result.");
                }
                ConfigureSam3dRenderer(renderer, solution.Camera);
                JSONStorableString requestId =
                    renderer.GetStringJSONParam(
                        Sam3dRequestIdParam);
                JSONStorableString baseFilename =
                    renderer.GetStringJSONParam(
                        Sam3dBaseFilenameParam);
                JSONStorableAction action =
                    renderer.GetAction(Sam3dCaptureAction);
                if (requestId == null ||
                    baseFilename == null ||
                    action == null ||
                    action.actionCallback == null)
                {
                    throw new Exception(
                        "The renderer's VAM-PIP capture interface is incomplete.");
                }
                requestId.val = request.RequestId;
                baseFilename.val = solution.Camera.BaseFilename;
                action.actionCallback();
            }
            catch (Exception exception)
            {
                setupError =
                    "Could not start the SAM3D capture: " +
                    DescribeException(exception);
            }
            if (setupError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    setupError);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + Sam3dCaptureWaitSeconds;
            while (Time.realtimeSinceStartup < deadline)
            {
                string state = "";
                string output = "";
                string error = "";
                string pollError = "";
                try
                {
                    if (renderer == null)
                    {
                        throw new Exception(
                            "The capture renderer is no longer available.");
                    }
                    JSONStorableString status =
                        renderer.GetStringJSONParam(
                            Sam3dStatusParam);
                    if (status == null)
                    {
                        throw new Exception(
                            "The renderer's capture status is no longer available.");
                    }
                    state =
                        (status.val ?? "").Trim().ToLowerInvariant();
                    if (state == "succeeded")
                    {
                        JSONStorableString lastOutput =
                            renderer.GetStringJSONParam(
                                Sam3dLastOutputParam);
                        if (lastOutput == null)
                        {
                            throw new Exception(
                                "The renderer's capture output is unavailable.");
                        }
                        output = lastOutput.val;
                    }
                    else if (state == "failed")
                    {
                        JSONStorableString rendererError =
                            renderer.GetStringJSONParam(
                                Sam3dErrorParam);
                        error =
                            rendererError == null
                            ? ""
                            : rendererError.val;
                    }
                }
                catch (Exception exception)
                {
                    pollError =
                        "Could not monitor the SAM3D capture: " +
                        DescribeException(exception);
                }
                if (pollError.Length != 0)
                {
                    FinishSam3dActionError(
                        request,
                        startedAt,
                        pollError);
                    yield break;
                }
                if (state == "succeeded")
                {
                    if (!IsSafeSam3dOutput(
                            output,
                            request.RequestId,
                            solution.Camera.BaseFilename))
                    {
                        FinishSam3dActionError(
                            request,
                            startedAt,
                            "The renderer returned an invalid capture path.");
                        yield break;
                    }
                    FinishSam3dActionOk(
                        request,
                        startedAt,
                        "SAM3D capture saved to " +
                        output.Replace('\\', '/') +
                        ".");
                    yield break;
                }
                if (state == "failed")
                {
                    if (error == null ||
                        error.Trim().Length == 0)
                    {
                        error = "The renderer reported a capture failure.";
                    }
                    if (error.Length > 500)
                    {
                        error = error.Substring(0, 500);
                    }
                    FinishSam3dActionError(
                        request,
                        startedAt,
                        error);
                    yield break;
                }
                yield return null;
            }

            FinishSam3dActionError(
                request,
                startedAt,
                "VR-and-Funscript capture did not finish within 300 seconds.");
        }

        private string PrepareAtomResourceRequest(
            BridgeRequest request,
            string startedAt,
            string actionDescription)
        {
            bool rescanAttempted = false;
            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before " +
                        actionDescription +
                        ".");
                    SuperController.singleton.RescanPackages();
                }
                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated resource does not exist or is not visible to VaM.");
                }
                return "";
            }
            catch (Exception exception)
            {
                return "Could not prepare " +
                    actionDescription +
                    ": " +
                    DescribeException(exception);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private IEnumerator EnsureTargetAtom(
            BridgeRequest request,
            string atomType,
            bool createIfMissing,
            AtomCreationResult result)
        {
            result.Atom = null;
            result.Created = false;
            result.Error = "";

            Atom existing = null;
            IEnumerator addRoutine = null;
            try
            {
                if (SuperController.singleton == null)
                {
                    throw new Exception("VaM's scene controller is unavailable.");
                }
                existing =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (existing == null && createIfMissing)
                {
                    PublishStatus(
                        StateAdding,
                        request.RequestId,
                        "",
                        "",
                        "vam",
                        "Adding " + atomType + " " + request.TargetUid + ".");
                    addRoutine =
                        SuperController.singleton.AddAtomByType(
                            atomType,
                            request.TargetUid,
                            true);
                    if (addRoutine == null)
                    {
                        throw new Exception(
                            "VaM did not provide an atom creation routine.");
                    }
                }
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not resolve target atom: " +
                    DescribeException(exception);
            }
            if (result.Error.Length != 0)
            {
                yield break;
            }

            if (existing != null)
            {
                if (createIfMissing)
                {
                    result.Error =
                        "createIfMissing requires targetUid to be absent " +
                        "when the request executes.";
                    yield break;
                }
                if (existing.type != atomType)
                {
                    result.Error =
                        "targetUid is already used by an atom of type " +
                        existing.type +
                        ", not " +
                        atomType +
                        ".";
                    yield break;
                }
                result.Atom = existing;
                yield break;
            }
            if (!createIfMissing)
            {
                result.Error =
                    "targetUid does not identify an existing " +
                    atomType +
                    " atom and createIfMissing is false.";
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                string iterationError = "";
                if (Time.realtimeSinceStartup >= deadline)
                {
                    iterationError =
                        atomType + " creation did not finish within 120 seconds.";
                }
                else
                {
                    try
                    {
                        hasNext = addRoutine.MoveNext();
                        if (hasNext)
                        {
                            current = addRoutine.Current;
                        }
                    }
                    catch (Exception exception)
                    {
                        iterationError =
                            atomType + " creation failed: " +
                            DescribeException(exception);
                    }
                }
                if (iterationError.Length != 0)
                {
                    result.Error = iterationError;
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }

            yield return new WaitForEndOfFrame();
            try
            {
                if (SuperController.singleton == null)
                {
                    throw new Exception(
                        "VaM's scene controller became unavailable.");
                }
                Atom created =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (created == null || created.type != atomType)
                {
                    throw new Exception(
                        "VaM completed creation without the requested " +
                        atomType +
                        " atom.");
                }
                result.Atom = created;
                result.Created = true;
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not verify the added " +
                    atomType +
                    ": " +
                    DescribeException(exception);
            }
        }

        private IEnumerator WaitForVaMLoading(
            string actionDescription,
            LoadingWaitResult result)
        {
            result.Error = "";

            // Preset and SubScene assignments can raise isLoading
            // asynchronously, so always cross a frame boundary first.
            yield return new WaitForEndOfFrame();

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (SuperController.singleton != null &&
                   SuperController.singleton.isLoading &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            if (SuperController.singleton == null)
            {
                result.Error =
                    "VaM's scene controller became unavailable while " +
                    actionDescription +
                    ".";
            }
            else if (SuperController.singleton.isLoading)
            {
                result.Error =
                    actionDescription +
                    " did not finish within 120 seconds.";
            }
        }

        private IEnumerator ExecuteApplyAtomPreset(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "applying the atom preset");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                request.AtomType,
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Applying " + request.AtomType + " atom preset.");

            string applyError = "";
            try
            {
                JSONStorable presetStorable =
                    target.Atom.GetStorableByID("Preset");
                if (presetStorable == null)
                {
                    throw new Exception(
                        "The target atom does not expose the Preset storable.");
                }
                JSONStorableUrl presetBrowsePath =
                    presetStorable.GetUrlJSONParam("presetBrowsePath");
                if (presetBrowsePath == null)
                {
                    throw new Exception(
                        "The target atom Preset storable has no presetBrowsePath.");
                }

                JSONStorableBool loadPresetOnSelect =
                    presetStorable.GetBoolJSONParam("loadPresetOnSelect");
                bool previousLoadPresetOnSelect = false;
                if (loadPresetOnSelect != null)
                {
                    previousLoadPresetOnSelect = loadPresetOnSelect.val;
                    loadPresetOnSelect.val = false;
                }
                try
                {
                    presetBrowsePath.val =
                        SuperController.singleton.NormalizePath(
                            request.ResourceRef);
                    presetStorable.CallAction(
                        request.Merge
                        ? "MergeLoadPreset"
                        : "LoadPreset");
                }
                finally
                {
                    if (loadPresetOnSelect != null)
                    {
                        loadPresetOnSelect.val = previousLoadPresetOnSelect;
                    }
                }
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not apply atom preset: " +
                    DescribeException(exception);
            }
            if (applyError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, applyError);
                yield break;
            }

            LoadingWaitResult wait = new LoadingWaitResult();
            yield return WaitForVaMLoading("atom preset loading", wait);
            if (wait.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, wait.Error);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                request.AtomType +
                (request.Merge ? " atom preset merged." : " atom preset applied."));
        }

        private IEnumerator ExecuteLoadSubscene(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "loading the SubScene");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                "SubScene",
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Loading SubScene.");

            string loadError = "";
            try
            {
                JSONStorable subsceneStorable =
                    target.Atom.GetStorableByID("SubScene");
                if (subsceneStorable == null)
                {
                    throw new Exception(
                        "The target atom does not expose the SubScene storable.");
                }
                JSONStorableUrl browsePath =
                    subsceneStorable.GetUrlJSONParam("browsePath");
                if (browsePath == null)
                {
                    throw new Exception(
                        "The target SubScene storable has no browsePath.");
                }
                browsePath.val =
                    SuperController.singleton.NormalizePath(
                        request.ResourceRef);
            }
            catch (Exception exception)
            {
                loadError =
                    "Could not load SubScene: " +
                    DescribeException(exception);
            }
            if (loadError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, loadError);
                yield break;
            }

            LoadingWaitResult wait = new LoadingWaitResult();
            yield return WaitForVaMLoading("SubScene loading", wait);
            if (wait.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, wait.Error);
                yield break;
            }

            FinishAtomActionOk(request, startedAt, "SubScene loaded.");
        }

        private static void ResolveCuaLoader(
            Atom atom,
            CuaLoaderState state)
        {
            state.Loader = null;
            state.AssetUrl = null;
            state.AssetName = null;
            state.LoadDll = null;
            state.Error = "";
            if (atom == null || atom.type != "CustomUnityAsset")
            {
                state.Error =
                    "targetUid does not identify a CustomUnityAsset atom.";
                return;
            }
            state.Loader =
                atom.GetStorableByID("asset") as CustomUnityAssetLoader;
            if (state.Loader == null)
            {
                state.Error =
                    "The target CustomUnityAsset has no native asset loader.";
                return;
            }
            state.AssetUrl = state.Loader.GetUrlJSONParam("assetUrl");
            state.AssetName =
                state.Loader.GetStringChooserJSONParam("assetName");
            state.LoadDll = state.Loader.GetBoolJSONParam("loadDll");
            if (state.AssetUrl == null ||
                state.AssetName == null ||
                state.LoadDll == null)
            {
                state.Error =
                    "The target CustomUnityAsset loader is missing a required " +
                    "assetUrl, assetName, or loadDll parameter.";
            }
        }

        private static bool IsEligibleCuaChoice(string choice)
        {
            return choice != null &&
                choice.Trim().Length != 0 &&
                !choice.Trim().Equals(
                    "None",
                    StringComparison.OrdinalIgnoreCase) &&
                SanitizeCuaChoiceLabel(choice).Length != 0;
        }

        private static string GetCuaNoneChoice(
            JSONStorableStringChooser assetName)
        {
            if (assetName != null && assetName.choices != null)
            {
                int index;
                for (index = 0; index < assetName.choices.Count; index++)
                {
                    string choice = assetName.choices[index];
                    if (choice != null &&
                        choice.Trim().Equals(
                            "None",
                            StringComparison.OrdinalIgnoreCase))
                    {
                        return choice;
                    }
                }
            }
            return "None";
        }

        private static List<int> GetEligibleCuaChoiceIndices(
            JSONStorableStringChooser assetName)
        {
            List<int> result = new List<int>();
            if (assetName == null || assetName.choices == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < assetName.choices.Count; index++)
            {
                if (IsEligibleCuaChoice(assetName.choices[index]))
                {
                    result.Add(index);
                }
            }
            return result;
        }

        private static void AbortUnsafeCuaLoad(CuaLoaderState state)
        {
            if (state == null || state.LoadDll == null)
            {
                return;
            }
            try
            {
                state.LoadDll.val = false;
                if (state.AssetName != null)
                {
                    state.AssetName.val = GetCuaNoneChoice(state.AssetName);
                }
                state.LoadDll.val = false;
                if (state.AssetUrl != null)
                {
                    state.AssetUrl.val = "";
                }
                state.LoadDll.val = false;
            }
            catch
            {
                // This is a best-effort abort after the safety invariant was
                // violated. The failure status still tells the caller that
                // the target must be inspected before another load.
            }
        }

        private static string ValidateLiveCuaOperation(
            BridgeRequest request,
            Atom expectedAtom,
            CustomUnityAssetLoader expectedLoader,
            string expectedUrl,
            CuaLoaderState state)
        {
            if (SuperController.singleton == null)
            {
                return "VaM's scene controller became unavailable.";
            }
            Atom current =
                SuperController.singleton.GetAtomByUid(request.TargetUid);
            if (current == null ||
                current.type != "CustomUnityAsset" ||
                !object.ReferenceEquals(current, expectedAtom))
            {
                return "The CustomUnityAsset target changed while loading.";
            }
            ResolveCuaLoader(current, state);
            if (state.Error.Length != 0)
            {
                return state.Error;
            }
            if (!object.ReferenceEquals(state.Loader, expectedLoader))
            {
                return "The CustomUnityAsset loader changed while loading.";
            }
            if (state.LoadDll.val)
            {
                AbortUnsafeCuaLoad(state);
                return "The CUA load was aborted because loadDll became enabled.";
            }
            if (expectedUrl != null &&
                !string.Equals(
                    state.AssetUrl.val,
                    expectedUrl,
                    StringComparison.Ordinal))
            {
                return "The CustomUnityAsset bundle changed while loading.";
            }
            return "";
        }

        private bool IsCurrentCuaChoiceSnapshot(
            string targetUid,
            CuaChoiceSnapshot expected,
            string choiceToken,
            List<string> currentChoices)
        {
            CuaChoiceSnapshot current = null;
            return expected != null &&
                _cuaChoiceSnapshots.TryGetValue(targetUid, out current) &&
                object.ReferenceEquals(current, expected) &&
                object.ReferenceEquals(current.ChoiceList, currentChoices) &&
                string.Equals(
                    current.ChoiceToken,
                    choiceToken,
                    StringComparison.OrdinalIgnoreCase);
        }

        private IEnumerator ExecuteLoadCustomUnityAsset(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "loading the Custom Unity Asset");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                "CustomUnityAsset",
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Loading Custom Unity Asset bundle with DLL loading disabled.");

            CuaLoaderState state = new CuaLoaderState();
            string normalizedUrl = "";
            string startError = "";
            try
            {
                ResolveCuaLoader(target.Atom, state);
                if (state.Error.Length != 0)
                {
                    throw new Exception(state.Error);
                }

                normalizedUrl =
                    SuperController.singleton.NormalizePath(
                        request.ResourceRef);
                state.AssetName.val = GetCuaNoneChoice(state.AssetName);

                // VaM samples loadDll synchronously from the assetUrl callback.
                // Keep these statements adjacent: changing loadDll afterwards
                // cannot unload an assembly that already executed.
                state.LoadDll.val = false;
                if (state.LoadDll.val)
                {
                    throw new Exception(
                        "The target refused to disable loadDll.");
                }
                state.AssetUrl.val = normalizedUrl;
            }
            catch (Exception exception)
            {
                startError =
                    "Could not start Custom Unity Asset loading: " +
                    DescribeException(exception);
            }
            if (startError.Length != 0)
            {
                if (state.LoadDll != null && state.LoadDll.val)
                {
                    AbortUnsafeCuaLoad(state);
                }
                FinishAtomActionError(request, startedAt, startError);
                yield break;
            }

            // A concurrent native loader rejects the new URL and restores its
            // in-flight value. Cross a frame and verify what the storable kept.
            yield return new WaitForEndOfFrame();

            string liveError =
                ValidateLiveCuaOperation(
                    request,
                    target.Atom,
                    state.Loader,
                    normalizedUrl,
                    state);
            if (liveError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, liveError);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            List<int> eligible = GetEligibleCuaChoiceIndices(state.AssetName);
            while (eligible.Count == 0 &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
                liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target.Atom,
                        state.Loader,
                        normalizedUrl,
                        state);
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                eligible = GetEligibleCuaChoiceIndices(state.AssetName);
            }
            if (eligible.Count == 0)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    "The bundle exposed no scene or prefab choice within 120 seconds.");
                yield break;
            }

            if (eligible.Count > 1)
            {
                FinishAtomActionOk(
                    request,
                    startedAt,
                    "Custom Unity Asset bundle is ready; choose one contained " +
                    "scene or prefab from the picker.");
                yield break;
            }

            int selectedIndex = eligible[0];
            string selectedChoice = state.AssetName.choices[selectedIndex];
            string selectionError = "";
            try
            {
                state.AssetName.val = selectedChoice;
            }
            catch (Exception exception)
            {
                selectionError =
                    "Could not select the bundle's only asset: " +
                    DescribeException(exception);
            }
            if (selectionError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, selectionError);
                yield break;
            }

            yield return new WaitForEndOfFrame();
            while (!state.Loader.isAssetLoaded &&
                   Time.realtimeSinceStartup < deadline)
            {
                liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target.Atom,
                        state.Loader,
                        normalizedUrl,
                        state);
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                yield return null;
            }

            liveError =
                ValidateLiveCuaOperation(
                    request,
                    target.Atom,
                    state.Loader,
                    normalizedUrl,
                    state);
            if (liveError.Length == 0 &&
                (!state.Loader.isAssetLoaded ||
                 !string.Equals(
                     state.AssetName.val,
                     selectedChoice,
                     StringComparison.Ordinal)))
            {
                liveError =
                    "The contained asset did not finish loading within 120 seconds.";
            }
            if (liveError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, liveError);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                "Custom Unity Asset bundle and its only contained asset loaded.");
        }

        private IEnumerator ExecuteSelectCustomUnityAssetChoice(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Selecting a published Custom Unity Asset choice.");

            Atom target = null;
            CuaLoaderState state = new CuaLoaderState();
            CuaChoiceSnapshot snapshot = null;
            string selectedChoice = "";
            string selectedUrl = "";
            string validationError = "";
            try
            {
                target =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (target == null || target.type != "CustomUnityAsset")
                {
                    throw new Exception(
                        "targetUid does not identify a CustomUnityAsset atom.");
                }
                ResolveCuaLoader(target, state);
                if (state.Error.Length != 0)
                {
                    throw new Exception(state.Error);
                }
                if (state.LoadDll.val)
                {
                    throw new Exception(
                        "The target has loadDll enabled; disable it before " +
                        "selecting an asset.");
                }
                if (!_cuaChoiceSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, target) ||
                    !object.ReferenceEquals(snapshot.Loader, state.Loader) ||
                    !object.ReferenceEquals(
                        snapshot.ChoiceList,
                        state.AssetName.choices) ||
                    !string.Equals(
                        snapshot.ChoiceToken,
                        request.ChoiceToken,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The CUA choice token is stale; refresh the live roster.");
                }
                string currentGeneration =
                    BuildCuaGenerationKey(
                        state.AssetUrl,
                        state.AssetName,
                        snapshot.PublishedIndices);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "The CUA bundle choices changed; refresh the live roster.");
                }
                if (!snapshot.PublishedIndices.Contains(request.ChoiceIndex) ||
                    state.AssetName.choices == null ||
                    request.ChoiceIndex >= state.AssetName.choices.Count ||
                    !IsEligibleCuaChoice(
                        state.AssetName.choices[request.ChoiceIndex]))
                {
                    throw new Exception(
                        "choiceIndex was not present in the published CUA choices.");
                }
                selectedChoice =
                    state.AssetName.choices[request.ChoiceIndex];
                selectedUrl = state.AssetUrl.val;
                state.AssetName.val = selectedChoice;
            }
            catch (Exception exception)
            {
                validationError =
                    "Could not select Custom Unity Asset choice: " +
                    DescribeException(exception);
            }
            if (validationError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, validationError);
                yield break;
            }

            yield return new WaitForEndOfFrame();
            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (!state.Loader.isAssetLoaded &&
                   Time.realtimeSinceStartup < deadline)
            {
                CuaLoaderState currentState = new CuaLoaderState();
                string liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target,
                        state.Loader,
                        selectedUrl,
                        currentState);
                if (liveError.Length == 0)
                {
                    if (!IsCurrentCuaChoiceSnapshot(
                            request.TargetUid,
                            snapshot,
                            request.ChoiceToken,
                            currentState.AssetName.choices))
                    {
                        liveError =
                            "The CUA choice token became stale while selecting.";
                    }
                }
                if (liveError.Length == 0)
                {
                    string currentGeneration =
                        BuildCuaGenerationKey(
                            currentState.AssetUrl,
                            currentState.AssetName,
                            snapshot.PublishedIndices);
                    if (!string.Equals(
                            snapshot.GenerationKey,
                            currentGeneration,
                            StringComparison.Ordinal))
                    {
                        liveError =
                            "The CUA bundle choices changed while selecting.";
                    }
                }
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                yield return null;
            }

            string finishError = "";
            CuaLoaderState finalState = new CuaLoaderState();
            finishError =
                ValidateLiveCuaOperation(
                    request,
                    target,
                    state.Loader,
                    selectedUrl,
                    finalState);
            if (finishError.Length == 0)
            {
                if (!IsCurrentCuaChoiceSnapshot(
                        request.TargetUid,
                        snapshot,
                        request.ChoiceToken,
                        finalState.AssetName.choices))
                {
                    finishError =
                        "The CUA choice token became stale while selecting.";
                }
            }
            if (finishError.Length == 0)
            {
                string currentGeneration =
                    BuildCuaGenerationKey(
                        finalState.AssetUrl,
                        finalState.AssetName,
                        snapshot.PublishedIndices);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    finishError =
                        "The CUA bundle choices changed while selecting.";
                }
                else if (!finalState.Loader.isAssetLoaded ||
                         !string.Equals(
                             finalState.AssetName.val,
                             selectedChoice,
                             StringComparison.Ordinal))
                {
                    finishError =
                        "The selected CUA asset did not finish loading within " +
                        "120 seconds.";
                }
            }
            if (finishError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, finishError);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                "Custom Unity Asset choice loaded.");
        }

        private TimelineSnapshot FindTimelineSnapshot(string timelineId)
        {
            foreach (
                KeyValuePair<string, TimelineSnapshot> entry
                in _timelineSnapshots)
            {
                TimelineSnapshot snapshot = entry.Value;
                if (snapshot != null &&
                    string.Equals(
                        snapshot.TimelineId,
                        timelineId,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return snapshot;
                }
            }
            return null;
        }

        private static TimelineItemSnapshot FindTimelineItem(
            List<TimelineItemSnapshot> items,
            string token)
        {
            if (items == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < items.Count; index++)
            {
                TimelineItemSnapshot item = items[index];
                if (item != null &&
                    string.Equals(
                        item.Token,
                        token,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return item;
                }
            }
            return null;
        }

        private void ExecuteTimelineControl(BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "",
                "Applying an allowlisted Timeline control.");
            try
            {
                TimelineSnapshot snapshot =
                    FindTimelineSnapshot(request.TimelineId);
                if (snapshot == null ||
                    snapshot.Atom == null ||
                    snapshot.Plugin == null)
                {
                    throw new Exception(
                        "Timeline instance is no longer available.");
                }
                if (!string.Equals(
                        snapshot.Revision,
                        request.TimelineRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "Timeline catalog changed; refresh before controlling it.");
                }
                JSONStorable live =
                    snapshot.Atom.GetStorableByID(snapshot.StorableId);
                if (!object.ReferenceEquals(live, snapshot.Plugin))
                {
                    throw new Exception(
                        "Timeline plugin instance changed; refresh the roster.");
                }

                if (snapshot.Enhanced)
                {
                    ExecuteEnhancedTimelineControl(snapshot, request);
                }
                else
                {
                    ExecuteBasicTimelineControl(snapshot, request);
                }

                CompleteRequest(request.RequestId);
                PublishTimelineStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    snapshot.Enhanced
                    ? "timeline-adapter-v1"
                    : "timeline-storables",
                    "Timeline control applied.");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Could not control Timeline: " +
                    DescribeException(exception));
            }
        }

        private static void ExecuteEnhancedTimelineControl(
            TimelineSnapshot snapshot,
            BridgeRequest request)
        {
            JSONStorableString commandParam =
                snapshot.Plugin.GetStringJSONParam(
                    TimelineExternalCommand);
            JSONStorableString resultParam =
                snapshot.Plugin.GetStringJSONParam(
                    TimelineExternalResult);
            JSONStorableAction execute =
                snapshot.Plugin.GetAction(
                    TimelineExecuteExternalCommand);
            if (commandParam == null ||
                resultParam == null ||
                execute == null ||
                execute.actionCallback == null)
            {
                throw new Exception(
                    "Timeline external adapter controls are unavailable.");
            }

            JSONClass command = new JSONClass();
            command["protocol"].AsInt = TimelineProtocolVersion;
            command["requestId"] = request.RequestId;
            command["expectedCatalogRevision"].AsInt =
                snapshot.CatalogRevision;
            command["op"] = request.TimelineOperation;

            TimelineItemSnapshot item = null;
            if (request.TimelineOperation == "selectClip" ||
                request.TimelineOperation == "playClip")
            {
                item = FindTimelineItem(
                    snapshot.Clips,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Clip ID was not published for this revision.");
                }
                command["clipId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "selectSegment")
            {
                item = FindTimelineItem(
                    snapshot.Segments,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Segment ID was not published for this revision.");
                }
                command["segmentId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "selectLayer")
            {
                item = FindTimelineItem(
                    snapshot.Layers,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Layer ID was not published for this revision.");
                }
                command["layerId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "setLocked")
            {
                command["value"].AsBool =
                    request.TimelineBoolValue;
            }
            else if (
                request.TimelineOperation == "setTime" ||
                request.TimelineOperation == "setSpeed" ||
                request.TimelineOperation == "setWeight")
            {
                command["value"].AsFloat =
                    request.TimelineNumberValue;
            }

            commandParam.val = command.ToString();
            execute.actionCallback();

            JSONClass result =
                JSON.Parse(resultParam.val ?? "").AsObject;
            if (result == null ||
                result["protocol"].AsInt != TimelineProtocolVersion ||
                !string.Equals(
                    ((string)result["requestId"] ?? "").Trim(),
                    request.RequestId,
                    StringComparison.Ordinal))
            {
                throw new Exception(
                    "Timeline adapter returned no matching result.");
            }
            if (!result["ok"].AsBool)
            {
                string code = SanitizeTimelineText(
                    (string)result["code"],
                    64);
                string message = SanitizeTimelineText(
                    (string)result["message"],
                    500);
                throw new Exception(
                    "Timeline adapter rejected the command" +
                    (code.Length == 0 ? "" : " (" + code + ")") +
                    (message.Length == 0 ? "." : ": " + message));
            }
        }

        private static void InvokeTimelineAction(
            MVRScript plugin,
            string actionName)
        {
            if (actionName != "Play If Not Playing" &&
                actionName != "Stop If Playing" &&
                actionName != "Stop And Reset" &&
                actionName != "Next Frame" &&
                actionName != "Previous Frame" &&
                actionName != "Play Current Clip")
            {
                throw new Exception(
                    "Timeline action is not allowlisted.");
            }
            JSONStorableAction action = plugin.GetAction(actionName);
            if (action == null || action.actionCallback == null)
            {
                throw new Exception(
                    "Timeline does not provide the requested control.");
            }
            action.actionCallback();
        }

        private static void ExecuteBasicTimelineControl(
            TimelineSnapshot snapshot,
            BridgeRequest request)
        {
            MVRScript plugin = snapshot.Plugin;
            string operation = request.TimelineOperation;
            if (operation == "play")
            {
                JSONStorableBool paused =
                    plugin.GetBoolJSONParam("Paused");
                if (paused != null)
                {
                    paused.val = false;
                }
                InvokeTimelineAction(plugin, "Play If Not Playing");
                return;
            }
            if (operation == "pause")
            {
                JSONStorableBool paused =
                    plugin.GetBoolJSONParam("Paused");
                if (paused == null)
                {
                    throw new Exception(
                        "Timeline pause control is unavailable.");
                }
                paused.val = true;
                return;
            }
            if (operation == "stop")
            {
                InvokeTimelineAction(plugin, "Stop If Playing");
                return;
            }
            if (operation == "reset")
            {
                InvokeTimelineAction(plugin, "Stop And Reset");
                return;
            }
            if (operation == "nextFrame")
            {
                InvokeTimelineAction(plugin, "Next Frame");
                return;
            }
            if (operation == "previousFrame")
            {
                InvokeTimelineAction(plugin, "Previous Frame");
                return;
            }
            if (operation == "selectClip" || operation == "playClip")
            {
                TimelineItemSnapshot item =
                    FindTimelineItem(
                        snapshot.Clips,
                        request.TimelineItemToken);
                JSONStorableStringChooser chooser =
                    plugin.GetStringChooserJSONParam("Animation");
                if (item == null ||
                    chooser == null ||
                    chooser.choices == null ||
                    item.AdapterId < 0 ||
                    item.AdapterId >= chooser.choices.Count ||
                    !string.Equals(
                        chooser.choices[item.AdapterId],
                        item.RawName,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "Timeline clip list changed; refresh the roster.");
                }
                chooser.val = item.RawName;
                if (operation == "playClip")
                {
                    InvokeTimelineAction(plugin, "Play Current Clip");
                }
                return;
            }
            if (operation == "selectSegment" ||
                operation == "selectLayer")
            {
                throw new Exception(
                    "This Timeline version needs the VAM-PIP adapter " +
                    "for segment and layer selection.");
            }
            if (operation == "setTime")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Set Time");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline time control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setSpeed")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Speed");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline speed control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setWeight")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Weight");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline weight control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setLocked")
            {
                JSONStorableBool parameter =
                    plugin.GetBoolJSONParam("Locked");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline lock control is unavailable.");
                }
                parameter.val = request.TimelineBoolValue;
                return;
            }
            throw new Exception("Unsupported Timeline control.");
        }

        private void ExecuteSelectAtom(
            BridgeRequest request,
            bool requirePerson)
        {
            string startedAt = UtcNow();
            string targetDescription =
                requirePerson ? "Person" : "atom";
            PublishStatus(
                StateSelecting,
                request.RequestId,
                startedAt,
                "",
                "",
                "Selecting " +
                targetDescription +
                " " +
                request.TargetUid +
                ".");
            try
            {
                Atom atom =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (atom == null)
                {
                    throw new Exception(
                        "targetUid does not identify an atom in the current scene.");
                }
                if (requirePerson && atom.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the current scene.");
                }
                if (atom.mainController == null)
                {
                    throw new Exception(
                        "The target " +
                        targetDescription +
                        " has no main controller.");
                }

                Atom selected = SuperController.singleton.GetSelectedAtom();
                if (selected == null || selected.uid != atom.uid)
                {
                    SuperController.singleton.SelectController(
                        atom.mainController,
                        false,
                        false,
                        true);
                }
                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    "vam",
                    requirePerson
                    ? "Person selected."
                    : "Atom selected.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Selected " +
                    targetDescription +
                    " " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Could not select " +
                    targetDescription +
                    ": " +
                    DescribeException(exception));
            }
        }

        private void FailRequest(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _lastHandledRequestId = request.RequestId;
            PublishStatus(
                StateError,
                request.RequestId,
                startedAt,
                UtcNow(),
                "",
                message);
            SuperController.LogError("[VAM-PIP Bridge] " + message);
        }

        private void CompleteRequest(string requestId)
        {
            _lastHandledRequestId = requestId;
            _lastCompletedRequestId = requestId;
        }

        private static string SanitizeCuaChoiceLabel(string value)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' || characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > MaximumCuaChoiceLabelLength)
            {
                result = result.Substring(0, MaximumCuaChoiceLabelLength);
            }
            return result;
        }

        private static void HashCuaText(
            ref ulong first,
            ref ulong second,
            string value)
        {
            unchecked
            {
                if (value == null)
                {
                    first = (first ^ 0xffffffffUL) * 1099511628211UL;
                    second = (second ^ 0xfffffffeUL) * 14029467366897019727UL;
                    return;
                }
                first = (first ^ (ulong)value.Length) * 1099511628211UL;
                second =
                    (second ^ ((ulong)value.Length + 0x9e3779b97f4a7c15UL)) *
                    14029467366897019727UL;
                int index;
                for (index = 0; index < value.Length; index++)
                {
                    ulong character = value[index];
                    first = (first ^ character) * 1099511628211UL;
                    second =
                        (second ^ (character + 0x517cc1b727220a95UL)) *
                        14029467366897019727UL;
                }
                first = (first ^ 0xffUL) * 1099511628211UL;
                second = (second ^ 0xfeUL) * 14029467366897019727UL;
            }
        }

        private static string BuildCuaGenerationKey(
            JSONStorableUrl assetUrl,
            JSONStorableStringChooser assetName,
            List<int> publishedIndices)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                assetUrl == null ? null : assetUrl.val);

            List<string> choices =
                assetName == null ? null : assetName.choices;
            HashCuaText(
                ref first,
                ref second,
                choices == null ? "-1" : choices.Count.ToString());

            int publishedCount =
                publishedIndices == null ? 0 : publishedIndices.Count;
            HashCuaText(
                ref first,
                ref second,
                publishedCount.ToString());
            if (publishedIndices != null)
            {
                int publishedOffset;
                for (publishedOffset = 0;
                     publishedOffset < publishedIndices.Count;
                     publishedOffset++)
                {
                    int originalIndex = publishedIndices[publishedOffset];
                    HashCuaText(
                        ref first,
                        ref second,
                        originalIndex.ToString());
                    string raw =
                        choices != null &&
                        originalIndex >= 0 &&
                        originalIndex < choices.Count
                        ? choices[originalIndex]
                        : null;
                    HashCuaText(
                        ref first,
                        ref second,
                        raw);
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private static int CompareActiveClothingEntries(
            ActiveClothingEntry left,
            ActiveClothingEntry right)
        {
            int resourceOrder = string.Compare(
                left == null ? "" : left.ResourceRef,
                right == null ? "" : right.ResourceRef,
                StringComparison.OrdinalIgnoreCase);
            if (resourceOrder != 0)
            {
                return resourceOrder;
            }
            int packageOrder = string.Compare(
                left == null ? "" : left.PackageUid,
                right == null ? "" : right.PackageUid,
                StringComparison.Ordinal);
            if (packageOrder != 0)
            {
                return packageOrder;
            }
            return string.Compare(
                left == null ? "" : left.InternalUid,
                right == null ? "" : right.InternalUid,
                StringComparison.Ordinal);
        }

        private static string SanitizeRosterText(
            string value,
            int maximumLength)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' || characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > maximumLength)
            {
                result = result.Substring(0, maximumLength);
            }
            return result;
        }

        private static string[] SanitizeRosterTags(string[] values)
        {
            List<string> result = new List<string>();
            HashSet<string> seen =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (values == null)
            {
                return result.ToArray();
            }
            int index;
            for (index = 0;
                 index < values.Length &&
                 result.Count < MaximumRosterTagsPerItem;
                 index++)
            {
                string tag = SanitizeRosterText(
                    values[index],
                    MaximumRosterTagLength);
                if (tag.Length == 0 || !seen.Add(tag))
                {
                    continue;
                }
                result.Add(tag);
            }
            return result.ToArray();
        }

        private static JSONArray BuildRosterTags(string[] tags)
        {
            JSONArray result = new JSONArray();
            if (tags == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < tags.Length; index++)
            {
                result.Add(tags[index]);
            }
            return result;
        }

        private static List<ActiveClothingEntry> GetActiveClothingEntries(
            Atom atom,
            DAZCharacterSelector geometry)
        {
            List<ActiveClothingEntry> result =
                new List<ActiveClothingEntry>();
            if (atom == null || geometry == null || atom.type != "Person")
            {
                return result;
            }
            DAZClothingItem[] items =
                atom.GetComponentsInChildren<DAZClothingItem>();
            if (items == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < items.Length; index++)
            {
                DAZClothingItem item = items[index];
                if (item == null || !item.active)
                {
                    continue;
                }
                string rawResourceRef =
                    item.dynamicRuntimeLoadPath ?? "";
                if (rawResourceRef.Length == 0)
                {
                    // VaM serializes the exact clothing resource as the item
                    // id. Built-in items also use uid, but they fail the
                    // scoped resource validation below and remain private.
                    rawResourceRef = item.uid ?? "";
                }
                string resourceRef = "";
                if (rawResourceRef.Length != 0)
                {
                    try
                    {
                        resourceRef =
                            FileManagerSecure.NormalizePath(rawResourceRef);
                        string prefix =
                            GetClothingResourcePrefix(resourceRef);
                        if (prefix.Length == 0 ||
                            ValidateResourceRef(
                                resourceRef,
                                prefix,
                                ".vam",
                                false,
                                "clothing items").Length != 0)
                        {
                            resourceRef = "";
                        }
                    }
                    catch
                    {
                        resourceRef = "";
                    }
                }
                ActiveClothingEntry entry = new ActiveClothingEntry();
                entry.Item = item;
                entry.ResourceRef = resourceRef;
                entry.Uid = item.uid ?? "";
                entry.InternalUid = item.internalUid ?? "";
                entry.PackageUid = item.packageUid ?? "";
                entry.DisplayName = SanitizeRosterText(
                    item.displayName,
                    MaximumRosterDisplayNameLength);
                if (entry.DisplayName.Length == 0)
                {
                    entry.DisplayName = "Unnamed clothing item";
                }
                entry.Tags = SanitizeRosterTags(item.tagsArray);
                entry.Locked = item.locked;
                result.Add(entry);
            }
            result.Sort(CompareActiveClothingEntries);
            return result;
        }

        private static string BuildPersonClothingGenerationKey(
            DAZCharacterSelector geometry,
            List<ActiveClothingEntry> entries)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                geometry == null ? "" : geometry.gender.ToString());
            HashCuaText(
                ref first,
                ref second,
                entries == null ? "-1" : entries.Count.ToString());
            if (entries != null)
            {
                int index;
                for (index = 0; index < entries.Count; index++)
                {
                    ActiveClothingEntry entry = entries[index];
                    if (entry.ResourceRef.Length != 0)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.ResourceRef);
                    }
                    else
                    {
                        HashCuaText(ref first, ref second, entry.Uid);
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.InternalUid);
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.PackageUid);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.DisplayName);
                    int tagIndex;
                    for (tagIndex = 0;
                         tagIndex < entry.Tags.Length;
                         tagIndex++)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.Tags[tagIndex]);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Locked ? "locked" : "unlocked");
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private JSONClass BuildPersonClothingStatus(
            Atom atom,
            ref int globalResourceBudget)
        {
            JSONClass clothing = new JSONClass();
            DAZCharacterSelector geometry =
                atom == null
                ? null
                : atom.GetStorableByID("geometry") as DAZCharacterSelector;
            clothing["ready"].AsBool = geometry != null;
            clothing["gender"] =
                geometry == null ? "None" : geometry.gender.ToString();
            JSONArray activeRefs = new JSONArray();
            JSONArray lockedRefs = new JSONArray();
            JSONArray activeItems = new JSONArray();
            clothing["activeResourceRefs"] = activeRefs;
            clothing["lockedResourceRefs"] = lockedRefs;
            clothing["activeItems"] = activeItems;
            clothing["activeCount"].AsInt = 0;
            clothing["lockedCount"].AsInt = 0;
            clothing["truncated"].AsBool = false;
            clothing["revision"] = "";
            if (geometry == null)
            {
                _personClothingSnapshots.Remove(atom.uid);
                return clothing;
            }

            List<ActiveClothingEntry> entries =
                GetActiveClothingEntries(atom, geometry);
            string generationKey =
                BuildPersonClothingGenerationKey(geometry, entries);
            PersonClothingSnapshot snapshot = null;
            bool reuse =
                _personClothingSnapshots.TryGetValue(
                    atom.uid,
                    out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Geometry, geometry) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (!reuse)
            {
                snapshot = new PersonClothingSnapshot();
                snapshot.Revision = Guid.NewGuid().ToString("N");
            }
            snapshot.Atom = atom;
            snapshot.Geometry = geometry;
            snapshot.GenerationKey = generationKey;
            _personClothingSnapshots[atom.uid] = snapshot;

            HashSet<string> published =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int publishedItemCount = 0;
            int lockedCount = 0;
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < entries.Count;
                 entryIndex++)
            {
                ActiveClothingEntry entry = entries[entryIndex];
                if (entry.Locked)
                {
                    lockedCount++;
                }
                if (
                    publishedItemCount >= MaximumClothingRefsPerPerson ||
                    globalResourceBudget <= 0)
                {
                    continue;
                }
                JSONClass activeItem = new JSONClass();
                activeItem["displayName"] = entry.DisplayName;
                activeItem["tags"] = BuildRosterTags(entry.Tags);
                activeItem["locked"].AsBool = entry.Locked;
                activeItem["resourceRef"] = entry.ResourceRef;
                activeItems.Add(activeItem);
                publishedItemCount++;
                globalResourceBudget--;
                if (entry.ResourceRef.Length == 0 ||
                    !published.Add(entry.ResourceRef))
                {
                    continue;
                }
                activeRefs.Add(entry.ResourceRef);
                if (entry.Locked)
                {
                    lockedRefs.Add(entry.ResourceRef);
                }
            }
            clothing["activeCount"].AsInt = entries.Count;
            clothing["lockedCount"].AsInt = lockedCount;
            clothing["truncated"].AsBool =
                entries.Count > publishedItemCount;
            clothing["revision"] = snapshot.Revision;
            return clothing;
        }

        private static int CompareActiveHairEntries(
            ActiveHairEntry left,
            ActiveHairEntry right)
        {
            int displayOrder = string.Compare(
                left == null ? "" : left.DisplayName,
                right == null ? "" : right.DisplayName,
                StringComparison.OrdinalIgnoreCase);
            if (displayOrder != 0)
            {
                return displayOrder;
            }
            int packageOrder = string.Compare(
                left == null ? "" : left.PackageUid,
                right == null ? "" : right.PackageUid,
                StringComparison.Ordinal);
            if (packageOrder != 0)
            {
                return packageOrder;
            }
            return string.Compare(
                left == null ? "" : left.InternalUid,
                right == null ? "" : right.InternalUid,
                StringComparison.Ordinal);
        }

        private static List<ActiveHairEntry> GetActiveHairEntries(
            Atom atom,
            DAZCharacterSelector geometry)
        {
            List<ActiveHairEntry> result = new List<ActiveHairEntry>();
            if (atom == null || geometry == null || atom.type != "Person")
            {
                return result;
            }
            DAZHairGroup[] items =
                atom.GetComponentsInChildren<DAZHairGroup>();
            if (items == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < items.Length; index++)
            {
                DAZHairGroup item = items[index];
                if (item == null || !item.active)
                {
                    continue;
                }
                ActiveHairEntry entry = new ActiveHairEntry();
                entry.Item = item;
                entry.Uid = item.uid ?? "";
                entry.InternalUid = item.internalUid ?? "";
                entry.PackageUid = item.packageUid ?? "";
                entry.DisplayName = SanitizeRosterText(
                    item.displayName,
                    MaximumRosterDisplayNameLength);
                if (entry.DisplayName.Length == 0)
                {
                    entry.DisplayName = "Unnamed hair item";
                }
                entry.Tags = SanitizeRosterTags(item.tagsArray);
                entry.Locked = item.locked;
                entry.Simulated =
                    item.GetComponentInChildren<HairSimControl>() != null;
                result.Add(entry);
            }
            result.Sort(CompareActiveHairEntries);
            return result;
        }

        private static string BuildPersonHairGenerationKey(
            DAZCharacterSelector geometry,
            List<ActiveHairEntry> entries)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                geometry == null ? "" : geometry.gender.ToString());
            HashCuaText(
                ref first,
                ref second,
                entries == null ? "-1" : entries.Count.ToString());
            if (entries != null)
            {
                int index;
                for (index = 0; index < entries.Count; index++)
                {
                    ActiveHairEntry entry = entries[index];
                    HashCuaText(ref first, ref second, entry.Uid);
                    HashCuaText(ref first, ref second, entry.InternalUid);
                    HashCuaText(ref first, ref second, entry.PackageUid);
                    HashCuaText(ref first, ref second, entry.DisplayName);
                    int tagIndex;
                    for (tagIndex = 0;
                         tagIndex < entry.Tags.Length;
                         tagIndex++)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.Tags[tagIndex]);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Locked ? "locked" : "unlocked");
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Simulated ? "simulated" : "mesh");
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private JSONClass BuildPersonHairStatus(
            Atom atom,
            ref int globalItemBudget)
        {
            JSONClass hair = new JSONClass();
            DAZCharacterSelector geometry =
                atom == null
                ? null
                : atom.GetStorableByID("geometry") as DAZCharacterSelector;
            hair["ready"].AsBool = geometry != null;
            hair["activeCount"].AsInt = 0;
            hair["lockedCount"].AsInt = 0;
            hair["truncated"].AsBool = false;
            hair["revision"] = "";
            JSONArray publishedItems = new JSONArray();
            hair["items"] = publishedItems;
            if (geometry == null)
            {
                _personHairSnapshots.Remove(atom.uid);
                return hair;
            }

            List<ActiveHairEntry> entries =
                GetActiveHairEntries(atom, geometry);
            string generationKey =
                BuildPersonHairGenerationKey(geometry, entries);
            int publishableCount = Math.Min(
                entries.Count,
                Math.Min(
                    MaximumHairItemsPerPerson,
                    Math.Max(0, globalItemBudget)));
            PersonHairSnapshot snapshot = null;
            bool reuse =
                _personHairSnapshots.TryGetValue(
                    atom.uid,
                    out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Geometry, geometry) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (reuse &&
                (snapshot.Items == null ||
                 snapshot.ActionTokens == null ||
                 snapshot.Items.Count != entries.Count ||
                 snapshot.ActionTokens.Count != entries.Count ||
                 snapshot.PublishedCount != publishableCount))
            {
                reuse = false;
            }
            if (reuse)
            {
                int identityIndex;
                for (identityIndex = 0;
                     identityIndex < entries.Count;
                     identityIndex++)
                {
                    if (!object.ReferenceEquals(
                            snapshot.Items[identityIndex],
                            entries[identityIndex].Item))
                    {
                        reuse = false;
                        break;
                    }
                }
            }
            if (!reuse)
            {
                snapshot = new PersonHairSnapshot();
                snapshot.Revision = Guid.NewGuid().ToString("N");
                snapshot.Items = new List<DAZHairGroup>();
                snapshot.ActionTokens = new List<string>();
                snapshot.PublishedCount = publishableCount;
                int tokenIndex;
                for (tokenIndex = 0;
                     tokenIndex < entries.Count;
                     tokenIndex++)
                {
                    snapshot.Items.Add(entries[tokenIndex].Item);
                    snapshot.ActionTokens.Add(
                        Guid.NewGuid().ToString("N"));
                }
            }
            snapshot.Atom = atom;
            snapshot.Geometry = geometry;
            snapshot.GenerationKey = generationKey;
            _personHairSnapshots[atom.uid] = snapshot;

            int lockedCount = 0;
            int publishedCount = 0;
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < entries.Count;
                 entryIndex++)
            {
                ActiveHairEntry entry = entries[entryIndex];
                if (entry.Locked)
                {
                    lockedCount++;
                }
                if (
                    entryIndex >= snapshot.PublishedCount)
                {
                    continue;
                }
                JSONClass publishedItem = new JSONClass();
                publishedItem["displayName"] = entry.DisplayName;
                publishedItem["tags"] = BuildRosterTags(entry.Tags);
                publishedItem["locked"].AsBool = entry.Locked;
                publishedItem["simulated"].AsBool = entry.Simulated;
                publishedItem["actionToken"] =
                    snapshot.ActionTokens[entryIndex];
                publishedItems.Add(publishedItem);
                publishedCount++;
                globalItemBudget--;
            }
            hair["activeCount"].AsInt = entries.Count;
            hair["lockedCount"].AsInt = lockedCount;
            hair["truncated"].AsBool = entries.Count > publishedCount;
            hair["revision"] = snapshot.Revision;
            return hair;
        }

        private JSONClass BuildCuaStatus(
            Atom atom,
            ref int globalChoiceBudget)
        {
            CuaLoaderState state = new CuaLoaderState();
            ResolveCuaLoader(atom, state);

            JSONArray publishedChoices = new JSONArray();
            List<int> publishedIndices = new List<int>();
            int eligibleCount = 0;
            int selectedIndex = -1;
            if (state.AssetName != null && state.AssetName.choices != null)
            {
                int index;
                for (index = 0;
                     index < state.AssetName.choices.Count;
                     index++)
                {
                    string rawChoice = state.AssetName.choices[index];
                    if (selectedIndex < 0 &&
                        string.Equals(
                            state.AssetName.val,
                            rawChoice,
                            StringComparison.Ordinal))
                    {
                        selectedIndex = index;
                    }
                    if (!IsEligibleCuaChoice(rawChoice))
                    {
                        continue;
                    }
                    eligibleCount++;
                    if (publishedIndices.Count >= MaximumCuaChoicesPerAtom ||
                        globalChoiceBudget <= 0)
                    {
                        continue;
                    }

                    JSONClass publishedChoice = new JSONClass();
                    publishedChoice["index"].AsInt = index;
                    publishedChoice["label"] =
                        SanitizeCuaChoiceLabel(rawChoice);
                    publishedChoices.Add(publishedChoice);
                    publishedIndices.Add(index);
                    globalChoiceBudget--;
                }
            }

            string generationKey =
                BuildCuaGenerationKey(
                    state.AssetUrl,
                    state.AssetName,
                    publishedIndices);
            CuaChoiceSnapshot snapshot = null;
            bool reuse =
                _cuaChoiceSnapshots.TryGetValue(atom.uid, out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Loader, state.Loader) &&
                object.ReferenceEquals(
                    snapshot.ChoiceList,
                    state.AssetName == null
                    ? null
                    : state.AssetName.choices) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (!reuse)
            {
                snapshot = new CuaChoiceSnapshot();
                snapshot.ChoiceToken = Guid.NewGuid().ToString("N");
            }
            snapshot.Atom = atom;
            snapshot.Loader = state.Loader;
            snapshot.ChoiceList =
                state.AssetName == null ? null : state.AssetName.choices;
            snapshot.GenerationKey = generationKey;
            snapshot.PublishedIndices = publishedIndices;
            _cuaChoiceSnapshots[atom.uid] = snapshot;

            bool ready =
                state.Loader != null &&
                state.Error.Length == 0 &&
                state.Loader.isAssetLoaded;
            JSONClass cua = new JSONClass();
            cua["loadDll"].AsBool =
                state.LoadDll == null || state.LoadDll.val;
            cua["ready"].AsBool = ready;
            cua["isAssetLoaded"].AsBool = ready;
            cua["choiceToken"] = snapshot.ChoiceToken;
            cua["choiceCount"].AsInt = eligibleCount;
            cua["selectedIndex"].AsInt = selectedIndex;
            cua["choices"] = publishedChoices;
            cua["choicesTruncated"].AsBool =
                eligibleCount > publishedIndices.Count;
            return cua;
        }

        private static string SanitizeTimelineText(
            string value,
            int maximumLength)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' ||
                    characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > maximumLength)
            {
                result = result.Substring(0, maximumLength);
            }
            return result;
        }

        private static float BoundedTimelineFloat(
            float value,
            float minimum,
            float maximum,
            float fallback)
        {
            if (!IsFinite(value))
            {
                return fallback;
            }
            return Mathf.Clamp(value, minimum, maximum);
        }

        private static TimelineItemSnapshot FindTimelineItemByAdapterId(
            List<TimelineItemSnapshot> items,
            int adapterId)
        {
            if (items == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < items.Count; index++)
            {
                TimelineItemSnapshot item = items[index];
                if (item != null && item.AdapterId == adapterId)
                {
                    return item;
                }
            }
            return null;
        }

        private static string TimelineTokenForAdapterId(
            List<TimelineItemSnapshot> items,
            int adapterId)
        {
            TimelineItemSnapshot item =
                FindTimelineItemByAdapterId(items, adapterId);
            return item == null ? "" : item.Token;
        }

        private static string ReuseTimelineItemToken(
            List<TimelineItemSnapshot> previousItems,
            int adapterId)
        {
            TimelineItemSnapshot previous =
                FindTimelineItemByAdapterId(previousItems, adapterId);
            return previous == null
                ? Guid.NewGuid().ToString("N")
                : previous.Token;
        }

        private static JSONArray TimelineControls(bool enhanced)
        {
            JSONArray controls = new JSONArray();
            controls.Add("play");
            controls.Add("pause");
            controls.Add("stop");
            controls.Add("reset");
            controls.Add("nextFrame");
            controls.Add("previousFrame");
            controls.Add("selectClip");
            controls.Add("playClip");
            if (enhanced)
            {
                controls.Add("selectSegment");
                controls.Add("selectLayer");
            }
            controls.Add("setTime");
            controls.Add("setSpeed");
            controls.Add("setWeight");
            controls.Add("setLocked");
            return controls;
        }

        private static JSONArray BasicTimelineControls(
            MVRScript plugin,
            bool hasPublishedClips)
        {
            JSONArray controls = new JSONArray();
            if (plugin.GetAction("Play If Not Playing") != null)
                controls.Add("play");
            if (plugin.GetBoolJSONParam("Paused") != null)
                controls.Add("pause");
            if (plugin.GetAction("Stop If Playing") != null)
                controls.Add("stop");
            if (plugin.GetAction("Stop And Reset") != null)
                controls.Add("reset");
            if (plugin.GetAction("Next Frame") != null)
                controls.Add("nextFrame");
            if (plugin.GetAction("Previous Frame") != null)
                controls.Add("previousFrame");
            if (hasPublishedClips)
            {
                controls.Add("selectClip");
                if (plugin.GetAction("Play Current Clip") != null)
                    controls.Add("playClip");
            }
            if (plugin.GetFloatJSONParam("Set Time") != null)
                controls.Add("setTime");
            if (plugin.GetFloatJSONParam("Speed") != null)
                controls.Add("setSpeed");
            if (plugin.GetFloatJSONParam("Weight") != null)
                controls.Add("setWeight");
            if (plugin.GetBoolJSONParam("Locked") != null)
                controls.Add("setLocked");
            return controls;
        }

        private TimelineSnapshot CreateTimelineSnapshot(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            string generationKey,
            bool enhanced,
            int catalogRevision,
            out TimelineSnapshot previousForTokens)
        {
            TimelineSnapshot previous = null;
            _timelineSnapshots.TryGetValue(key, out previous);
            bool sameIdentity =
                previous != null &&
                object.ReferenceEquals(previous.Atom, atom) &&
                object.ReferenceEquals(previous.Plugin, plugin);
            bool sameGeneration =
                sameIdentity &&
                string.Equals(
                    previous.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            previousForTokens = sameGeneration ? previous : null;

            TimelineSnapshot snapshot = new TimelineSnapshot();
            snapshot.Atom = atom;
            snapshot.Plugin = plugin;
            snapshot.StorableId = storableId;
            snapshot.TimelineId =
                sameIdentity
                ? previous.TimelineId
                : Guid.NewGuid().ToString("N");
            snapshot.Revision =
                sameGeneration
                ? previous.Revision
                : Guid.NewGuid().ToString("N");
            snapshot.GenerationKey = generationKey;
            snapshot.Enhanced = enhanced;
            snapshot.CatalogRevision = catalogRevision;
            snapshot.Segments = new List<TimelineItemSnapshot>();
            snapshot.Layers = new List<TimelineItemSnapshot>();
            snapshot.Clips = new List<TimelineItemSnapshot>();
            _timelineSnapshots[key] = snapshot;
            return snapshot;
        }

        private static JSONClass TimelineItemJson(
            TimelineItemSnapshot item,
            string segmentToken,
            string layerToken,
            bool includeClipDetails)
        {
            JSONClass result = new JSONClass();
            result["id"] = item.Token;
            result["name"] = item.Name;
            result["selected"].AsBool = item.Selected;
            if (segmentToken.Length != 0)
            {
                result["segmentId"] = segmentToken;
            }
            if (includeClipDetails)
            {
                if (layerToken.Length != 0)
                {
                    result["layerId"] = layerToken;
                }
                result["qualified"] = item.Qualified;
                result["length"].AsFloat = item.Length;
                result["loop"].AsBool = item.Loop;
                result["playing"].AsBool = item.Playing;
                result["main"].AsBool = item.Main;
                result["time"].AsFloat = item.Time;
                result["speed"].AsFloat = item.Speed;
                result["weight"].AsFloat = item.Weight;
                result["targetCount"].AsInt = item.TargetCount;
            }
            return result;
        }

        private static int BoundedTimelineCount(int value)
        {
            if (value < 0)
            {
                return 0;
            }
            return Math.Min(value, 1000000);
        }

        private static int TimelineStateCount(
            JSONClass state,
            string key,
            int fallback)
        {
            JSONClass counts =
                state == null ? null : state["counts"].AsObject;
            if (counts == null || !counts.HasKey(key))
            {
                return BoundedTimelineCount(fallback);
            }
            return BoundedTimelineCount(counts[key].AsInt);
        }

        private static int TimelineStateLimit(
            JSONClass state,
            string key,
            int fallback)
        {
            JSONClass limits =
                state == null ? null : state["limits"].AsObject;
            int value =
                limits == null || !limits.HasKey(key)
                ? fallback
                : BoundedTimelineCount(limits[key].AsInt);
            if (value <= 0)
            {
                value = fallback;
            }
            return Math.Min(value, fallback);
        }

        private static JSONClass TimelineLimitsJson(
            JSONClass state,
            int allocatedClips)
        {
            JSONClass limits = new JSONClass();
            limits["maxSegments"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxSegments",
                    MaximumTimelineSegments);
            limits["maxLayers"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxLayers",
                    MaximumTimelineLayers);
            limits["maxClips"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxClips",
                    MaximumTimelineClips);
            limits["maxClipsGlobally"].AsInt =
                MaximumTimelineClipsGlobally;
            limits["allocatedClips"].AsInt =
                Math.Max(
                    0,
                    Math.Min(
                        allocatedClips,
                        MaximumTimelineClips));
            return limits;
        }

        private static string SanitizeTimelineErrorCode(string value)
        {
            value = (value ?? "").Trim().ToLowerInvariant();
            string result = "";
            int index;
            for (index = 0;
                 index < value.Length && result.Length < 64;
                 index++)
            {
                char character = value[index];
                if ((character >= 'a' && character <= 'z') ||
                    (character >= '0' && character <= '9') ||
                    character == '-')
                {
                    result += character;
                }
            }
            return result;
        }

        private static JSONClass TimelineAdapterErrorJson(
            JSONClass state)
        {
            JSONClass source =
                state == null ? null : state["error"].AsObject;
            if (source == null)
            {
                return null;
            }
            string code =
                SanitizeTimelineErrorCode((string)source["code"]);
            string message =
                SanitizeTimelineText(
                    (string)source["message"],
                    500);
            if (code.Length == 0 && message.Length == 0)
            {
                return null;
            }
            JSONClass error = new JSONClass();
            error["code"] =
                code.Length == 0 ? "adapter-error" : code;
            error["message"] =
                message.Length == 0
                ? "Timeline adapter reported an error."
                : message;
            return error;
        }

        private static JSONClass TimelineAdapterErrorJson(
            string code,
            string message)
        {
            JSONClass state = new JSONClass();
            JSONClass error = new JSONClass();
            error["code"] = code;
            error["message"] = message;
            state["error"] = error;
            return TimelineAdapterErrorJson(state);
        }

        private JSONClass BuildEnhancedTimelineStatus(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            JSONClass state,
            bool selected,
            int clipBudget)
        {
            int catalogRevision =
                Math.Max(0, state["catalogRevision"].AsInt);
            JSONArray rawSegments = state["segments"].AsArray;
            JSONArray rawLayers = state["layers"].AsArray;
            JSONArray rawClips = state["clips"].AsArray;
            int clipLimit =
                rawClips == null
                ? 0
                : Math.Min(
                    rawClips.Count,
                    Math.Min(
                        MaximumTimelineClips,
                        Math.Max(0, clipBudget)));
            string generationKey =
                "adapter:" +
                catalogRevision +
                ":" +
                (rawSegments == null ? 0 : rawSegments.Count) +
                ":" +
                (rawLayers == null ? 0 : rawLayers.Count) +
                ":" +
                (rawClips == null ? 0 : rawClips.Count) +
                ":published:" +
                clipLimit;
            TimelineSnapshot previous;
            TimelineSnapshot snapshot =
                CreateTimelineSnapshot(
                    key,
                    atom,
                    plugin,
                    storableId,
                    generationKey,
                    true,
                    catalogRevision,
                    out previous);

            int index;
            int segmentLimit =
                rawSegments == null
                ? 0
                : Math.Min(rawSegments.Count, MaximumTimelineSegments);
            for (index = 0; index < segmentLimit; index++)
            {
                JSONClass source = rawSegments[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        adapterId) != null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Segments,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = adapterId;
                item.AdapterLayerId = -1;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                snapshot.Segments.Add(item);
            }

            int layerLimit =
                rawLayers == null
                ? 0
                : Math.Min(rawLayers.Count, MaximumTimelineLayers);
            for (index = 0; index < layerLimit; index++)
            {
                JSONClass source = rawLayers[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id") ||
                    !source.HasKey("segmentId"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                int segmentId = source["segmentId"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Layers,
                        adapterId) != null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        segmentId) == null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Layers,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = segmentId;
                item.AdapterLayerId = adapterId;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                snapshot.Layers.Add(item);
            }

            for (index = 0; index < clipLimit; index++)
            {
                JSONClass source = rawClips[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id") ||
                    !source.HasKey("segmentId") ||
                    !source.HasKey("layerId"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                int segmentId = source["segmentId"].AsInt;
                int layerId = source["layerId"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Clips,
                        adapterId) != null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        segmentId) == null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Layers,
                        layerId) == null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Clips,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = segmentId;
                item.AdapterLayerId = layerId;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                item.Qualified = SanitizeTimelineText(
                    (string)source["qualified"],
                    MaximumTimelineQualifiedLength);
                item.Length = BoundedTimelineFloat(
                    source["length"].AsFloat,
                    0f,
                    86400f,
                    0f);
                item.Time = BoundedTimelineFloat(
                    source["time"].AsFloat,
                    0f,
                    86400f,
                    0f);
                item.Speed = BoundedTimelineFloat(
                    source["speed"].AsFloat,
                    -1f,
                    5f,
                    1f);
                item.Weight = BoundedTimelineFloat(
                    source["weight"].AsFloat,
                    0f,
                    1f,
                    1f);
                item.TargetCount =
                    BoundedTimelineCount(
                        source["targetCount"].AsInt);
                item.Loop = source["loop"].AsBool;
                item.Playing = source["playing"].AsBool;
                item.Main = source["main"].AsBool;
                item.Selected = source["selected"].AsBool;
                snapshot.Clips.Add(item);
            }

            JSONClass currentSource = state["current"].AsObject;
            int currentClipId =
                currentSource == null
                ? -1
                : currentSource["clipId"].AsInt;
            int currentSegmentId =
                currentSource == null
                ? -1
                : currentSource["segmentId"].AsInt;
            int currentLayerId =
                currentSource == null
                ? -1
                : currentSource["layerId"].AsInt;
            TimelineItemSnapshot currentClip =
                FindTimelineItemByAdapterId(
                    snapshot.Clips,
                    currentClipId);
            TimelineItemSnapshot currentSegment =
                FindTimelineItemByAdapterId(
                    snapshot.Segments,
                    currentSegmentId);
            TimelineItemSnapshot currentLayer =
                FindTimelineItemByAdapterId(
                    snapshot.Layers,
                    currentLayerId);
            if (currentClip != null)
            {
                currentClip.Selected = true;
            }
            if (currentSegment != null)
            {
                currentSegment.Selected = true;
            }
            if (currentLayer != null)
            {
                currentLayer.Selected = true;
            }

            JSONClass result = new JSONClass();
            result["id"] = snapshot.TimelineId;
            result["revision"] = snapshot.Revision;
            result["atomUid"] =
                SanitizeTimelineText(atom.uid, 200);
            string customLabel = "";
            if (plugin.pluginLabelJSON != null)
            {
                customLabel = SanitizeTimelineText(
                    plugin.pluginLabelJSON.val,
                    MaximumTimelineLabelLength);
            }
            result["label"] =
                customLabel.Length == 0
                ? SanitizeTimelineText(
                    atom.name,
                    MaximumTimelineLabelLength)
                : SanitizeTimelineText(
                    atom.name + ": " + customLabel,
                    MaximumTimelineLabelLength);
            result["enhanced"].AsBool = true;
            result["adapterVersion"] = SanitizeTimelineText(
                (string)state["adapterVersion"],
                64);
            JSONClass adapterError =
                TimelineAdapterErrorJson(state);
            result["ready"].AsBool =
                state["ready"].AsBool && adapterError == null;
            result["selected"].AsBool = selected;
            result["stateSequence"].AsInt =
                BoundedTimelineCount(
                    state["stateSequence"].AsInt);

            JSONClass transportSource =
                state["transport"].AsObject;
            JSONClass transport = new JSONClass();
            if (transportSource != null)
            {
                transport["playing"].AsBool =
                    transportSource["playing"].AsBool;
                transport["paused"].AsBool =
                    transportSource["paused"].AsBool;
                transport["time"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["time"].AsFloat,
                        0f,
                        86400f,
                        0f);
                transport["clipTime"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["clipTime"].AsFloat,
                        0f,
                        86400f,
                        0f);
                transport["speed"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["speed"].AsFloat,
                        -1f,
                        5f,
                        1f);
                transport["weight"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["weight"].AsFloat,
                        0f,
                        1f,
                        1f);
                transport["locked"].AsBool =
                    transportSource["locked"].AsBool;
            }
            JSONStorableFloat legacyScrubber =
                plugin.GetFloatJSONParam("Scrubber");
            transport["duration"].AsFloat =
                currentClip != null
                ? currentClip.Length
                : legacyScrubber == null
                    ? 0f
                    : BoundedTimelineFloat(
                        legacyScrubber.max,
                        0f,
                        86400f,
                        0f);
            result["transport"] = transport;

            JSONClass current = new JSONClass();
            current["clipId"] =
                currentClip == null ? "" : currentClip.Token;
            current["segmentId"] =
                currentSegment == null ? "" : currentSegment.Token;
            current["layerId"] =
                currentLayer == null ? "" : currentLayer.Token;
            current["qualified"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["qualified"],
                MaximumTimelineQualifiedLength);
            current["name"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["name"],
                MaximumTimelineLabelLength);
            current["segment"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["segment"],
                MaximumTimelineLabelLength);
            current["layer"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["layer"],
                MaximumTimelineLabelLength);
            result["current"] = current;

            JSONArray segments = new JSONArray();
            for (index = 0; index < snapshot.Segments.Count; index++)
            {
                segments.Add(
                    TimelineItemJson(
                        snapshot.Segments[index],
                        "",
                        "",
                        false));
            }
            JSONArray layers = new JSONArray();
            for (index = 0; index < snapshot.Layers.Count; index++)
            {
                TimelineItemSnapshot item = snapshot.Layers[index];
                layers.Add(
                    TimelineItemJson(
                        item,
                        TimelineTokenForAdapterId(
                            snapshot.Segments,
                            item.AdapterSegmentId),
                        "",
                        false));
            }
            JSONArray clips = new JSONArray();
            for (index = 0; index < snapshot.Clips.Count; index++)
            {
                TimelineItemSnapshot item = snapshot.Clips[index];
                clips.Add(
                    TimelineItemJson(
                        item,
                        TimelineTokenForAdapterId(
                            snapshot.Segments,
                            item.AdapterSegmentId),
                        TimelineTokenForAdapterId(
                            snapshot.Layers,
                            item.AdapterLayerId),
                        true));
            }
            result["segments"] = segments;
            result["layers"] = layers;
            result["clips"] = clips;

            JSONClass countsSource = state["counts"].AsObject;
            JSONClass counts = new JSONClass();
            counts["segments"].AsInt =
                countsSource == null
                ? snapshot.Segments.Count
                : BoundedTimelineCount(
                    countsSource["segments"].AsInt);
            counts["layers"].AsInt =
                countsSource == null
                ? snapshot.Layers.Count
                : BoundedTimelineCount(
                    countsSource["layers"].AsInt);
            counts["clips"].AsInt =
                countsSource == null
                ? snapshot.Clips.Count
                : BoundedTimelineCount(
                    countsSource["clips"].AsInt);
            counts["publishedSegments"].AsInt =
                snapshot.Segments.Count;
            counts["publishedLayers"].AsInt =
                snapshot.Layers.Count;
            counts["publishedClips"].AsInt =
                snapshot.Clips.Count;
            result["counts"] = counts;
            result["limits"] =
                TimelineLimitsJson(state, clipLimit);

            JSONClass truncatedSource =
                state["truncated"].AsObject;
            JSONClass truncated = new JSONClass();
            truncated["segments"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["segments"].AsBool) ||
                (rawSegments != null &&
                 rawSegments.Count > MaximumTimelineSegments);
            truncated["layers"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["layers"].AsBool) ||
                (rawLayers != null &&
                 rawLayers.Count > MaximumTimelineLayers);
            truncated["clips"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["clips"].AsBool) ||
                (rawClips != null &&
                 rawClips.Count > snapshot.Clips.Count) ||
                counts["clips"].AsInt >
                    snapshot.Clips.Count;
            result["truncated"] = truncated;
            if (adapterError != null)
            {
                result["error"] = adapterError;
            }
            result["controls"] =
                state["ready"].AsBool && adapterError == null
                ? TimelineControls(true)
                : new JSONArray();
            return result;
        }

        private JSONClass BuildBasicTimelineStatus(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            bool selected,
            int clipBudget,
            bool adapterAvailable,
            JSONClass adapterState,
            JSONClass adapterError)
        {
            JSONStorableStringChooser animations =
                plugin.GetStringChooserJSONParam("Animation");
            JSONStorableStringChooser segmentsParam =
                plugin.GetStringChooserJSONParam("Segment");
            List<string> rawAnimations =
                animations == null ? null : animations.choices;
            List<string> rawSegments =
                segmentsParam == null ? null : segmentsParam.choices;
            int clipLimit =
                rawAnimations == null
                ? 0
                : Math.Min(
                    rawAnimations.Count,
                    Math.Min(
                        MaximumTimelineClips,
                        Math.Max(0, clipBudget)));
            string generationKey =
                "legacy:published:" + clipLimit;
            int index;
            if (rawAnimations != null)
            {
                int limit = Math.Min(
                    rawAnimations.Count,
                    MaximumTimelineClips);
                for (index = 0; index < limit; index++)
                {
                    string name =
                        SanitizeTimelineText(
                            rawAnimations[index],
                            MaximumTimelineQualifiedLength);
                    generationKey += "|c:" +
                        name.Length +
                        ":" +
                        name;
                }
            }
            if (rawSegments != null)
            {
                int limit = Math.Min(
                    rawSegments.Count,
                    MaximumTimelineSegments);
                for (index = 0; index < limit; index++)
                {
                    string name =
                        SanitizeTimelineText(
                            rawSegments[index],
                            MaximumTimelineQualifiedLength);
                    generationKey += "|s:" +
                        name.Length +
                        ":" +
                        name;
                }
            }

            TimelineSnapshot previous;
            TimelineSnapshot snapshot =
                CreateTimelineSnapshot(
                    key,
                    atom,
                    plugin,
                    storableId,
                    generationKey,
                    false,
                    0,
                    out previous);

            if (rawSegments != null)
            {
                int limit = Math.Min(
                    rawSegments.Count,
                    MaximumTimelineSegments);
                for (index = 0; index < limit; index++)
                {
                    string rawName = rawSegments[index] ?? "";
                    if (rawName.Length > MaximumTimelineQualifiedLength ||
                        ContainsControlCharacter(rawName))
                    {
                        continue;
                    }
                    TimelineItemSnapshot item =
                        new TimelineItemSnapshot();
                    item.Token = ReuseTimelineItemToken(
                        previous == null ? null : previous.Segments,
                        index);
                    item.AdapterId = index;
                    item.AdapterSegmentId = index;
                    item.AdapterLayerId = -1;
                    item.RawName = rawName;
                    item.Name = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineLabelLength);
                    item.Selected =
                        segmentsParam != null &&
                        string.Equals(
                            segmentsParam.val,
                            rawName,
                            StringComparison.Ordinal);
                    snapshot.Segments.Add(item);
                }
            }
            if (rawAnimations != null)
            {
                int limit = clipLimit;
                for (index = 0; index < limit; index++)
                {
                    string rawName = rawAnimations[index] ?? "";
                    if (rawName.Length > MaximumTimelineQualifiedLength ||
                        ContainsControlCharacter(rawName))
                    {
                        continue;
                    }
                    TimelineItemSnapshot item =
                        new TimelineItemSnapshot();
                    item.Token = ReuseTimelineItemToken(
                        previous == null ? null : previous.Clips,
                        index);
                    item.AdapterId = index;
                    item.AdapterSegmentId = -1;
                    item.AdapterLayerId = -1;
                    item.RawName = rawName;
                    item.Name = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineLabelLength);
                    item.Qualified = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineQualifiedLength);
                    item.Speed = 1f;
                    item.Weight = 1f;
                    item.Selected =
                        animations != null &&
                        string.Equals(
                            animations.val,
                            rawName,
                            StringComparison.Ordinal);
                    snapshot.Clips.Add(item);
                }
            }

            JSONStorableBool isPlaying =
                plugin.GetBoolJSONParam("Is Playing");
            JSONStorableBool paused =
                plugin.GetBoolJSONParam("Paused");
            JSONStorableBool locked =
                plugin.GetBoolJSONParam("Locked");
            JSONStorableFloat time =
                plugin.GetFloatJSONParam("Set Time");
            JSONStorableFloat scrubber =
                plugin.GetFloatJSONParam("Scrubber");
            JSONStorableFloat speed =
                plugin.GetFloatJSONParam("Speed");
            JSONStorableFloat weight =
                plugin.GetFloatJSONParam("Weight");
            bool ready =
                plugin.isActiveAndEnabled &&
                animations != null &&
                isPlaying != null &&
                time != null &&
                plugin.GetAction("Play If Not Playing") != null &&
                plugin.GetAction("Stop If Playing") != null;

            JSONClass result = new JSONClass();
            result["id"] = snapshot.TimelineId;
            result["revision"] = snapshot.Revision;
            result["atomUid"] =
                SanitizeTimelineText(atom.uid, 200);
            string customLabel = "";
            if (plugin.pluginLabelJSON != null)
            {
                customLabel = SanitizeTimelineText(
                    plugin.pluginLabelJSON.val,
                    MaximumTimelineLabelLength);
            }
            result["label"] =
                customLabel.Length == 0
                ? SanitizeTimelineText(
                    atom.name,
                    MaximumTimelineLabelLength)
                : SanitizeTimelineText(
                    atom.name + ": " + customLabel,
                    MaximumTimelineLabelLength);
            result["enhanced"].AsBool = adapterAvailable;
            result["adapterVersion"] =
                adapterAvailable
                ? SanitizeTimelineText(
                    adapterState == null
                    ? ""
                    : (string)adapterState["adapterVersion"],
                    64)
                : "";
            result["ready"].AsBool = ready;
            result["selected"].AsBool = selected;
            result["stateSequence"].AsInt =
                adapterState == null
                ? 0
                : BoundedTimelineCount(
                    adapterState["stateSequence"].AsInt);

            JSONClass transport = new JSONClass();
            transport["playing"].AsBool =
                isPlaying != null && isPlaying.val;
            transport["paused"].AsBool =
                paused != null && paused.val;
            transport["time"].AsFloat =
                time == null
                ? 0f
                : BoundedTimelineFloat(
                    time.val,
                    0f,
                    86400f,
                    0f);
            transport["clipTime"].AsFloat =
                scrubber == null
                ? 0f
                : BoundedTimelineFloat(
                    scrubber.val,
                    0f,
                    86400f,
                    0f);
            transport["duration"].AsFloat =
                scrubber == null
                ? 0f
                : BoundedTimelineFloat(
                    scrubber.max,
                    0f,
                    86400f,
                    0f);
            transport["speed"].AsFloat =
                speed == null
                ? 1f
                : BoundedTimelineFloat(
                    speed.val,
                    -1f,
                    5f,
                    1f);
            transport["weight"].AsFloat =
                weight == null
                ? 1f
                : BoundedTimelineFloat(
                    weight.val,
                    0f,
                    1f,
                    1f);
            transport["locked"].AsBool =
                locked != null && locked.val;
            result["transport"] = transport;

            JSONClass current = new JSONClass();
            string currentClipToken = "";
            for (index = 0;
                 index < snapshot.Clips.Count;
                 index++)
            {
                if (snapshot.Clips[index].Selected)
                {
                    currentClipToken =
                        snapshot.Clips[index].Token;
                    break;
                }
            }
            current["clipId"] = currentClipToken;
            string currentSegmentToken = "";
            for (index = 0;
                 index < snapshot.Segments.Count;
                 index++)
            {
                if (snapshot.Segments[index].Selected)
                {
                    currentSegmentToken =
                        snapshot.Segments[index].Token;
                    break;
                }
            }
            current["segmentId"] = currentSegmentToken;
            current["layerId"] = "";
            JSONClass adapterCurrent =
                adapterState == null
                ? null
                : adapterState["current"].AsObject;
            string legacyAnimation =
                animations == null
                ? ""
                : SanitizeTimelineText(
                    animations.val,
                    MaximumTimelineQualifiedLength);
            string adapterQualified =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["qualified"],
                    MaximumTimelineQualifiedLength);
            string adapterName =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["name"],
                    MaximumTimelineLabelLength);
            string adapterSegment =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["segment"],
                    MaximumTimelineLabelLength);
            string adapterLayer =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["layer"],
                    MaximumTimelineLabelLength);
            current["qualified"] =
                adapterQualified.Length != 0
                ? adapterQualified
                : legacyAnimation;
            current["name"] =
                adapterName.Length != 0
                ? adapterName
                : SanitizeTimelineText(
                    animations == null ? "" : animations.val,
                    MaximumTimelineLabelLength);
            current["segment"] =
                adapterSegment.Length != 0
                ? adapterSegment
                : segmentsParam == null
                    ? ""
                    : SanitizeTimelineText(
                        segmentsParam.val,
                        MaximumTimelineLabelLength);
            current["layer"] = adapterLayer;
            result["current"] = current;

            JSONArray segments = new JSONArray();
            for (index = 0; index < snapshot.Segments.Count; index++)
            {
                segments.Add(
                    TimelineItemJson(
                        snapshot.Segments[index],
                        "",
                        "",
                        false));
            }
            JSONArray clips = new JSONArray();
            for (index = 0; index < snapshot.Clips.Count; index++)
            {
                clips.Add(
                    TimelineItemJson(
                        snapshot.Clips[index],
                        "",
                        "",
                        true));
            }
            result["segments"] = segments;
            result["layers"] = new JSONArray();
            result["clips"] = clips;

            int segmentCount =
                Math.Max(
                    rawSegments == null ? 0 : rawSegments.Count,
                    TimelineStateCount(
                        adapterState,
                        "segments",
                        rawSegments == null ? 0 : rawSegments.Count));
            int layerCount =
                TimelineStateCount(adapterState, "layers", 0);
            int clipCount =
                Math.Max(
                    rawAnimations == null ? 0 : rawAnimations.Count,
                    TimelineStateCount(
                        adapterState,
                        "clips",
                        rawAnimations == null ? 0 : rawAnimations.Count));
            JSONClass counts = new JSONClass();
            counts["segments"].AsInt =
                BoundedTimelineCount(segmentCount);
            counts["layers"].AsInt =
                BoundedTimelineCount(layerCount);
            counts["clips"].AsInt =
                BoundedTimelineCount(clipCount);
            counts["publishedSegments"].AsInt =
                snapshot.Segments.Count;
            counts["publishedLayers"].AsInt = 0;
            counts["publishedClips"].AsInt =
                snapshot.Clips.Count;
            result["counts"] = counts;
            result["limits"] =
                TimelineLimitsJson(
                    adapterState,
                    snapshot.Clips.Count);

            JSONClass truncated = new JSONClass();
            truncated["segments"].AsBool =
                segmentCount > snapshot.Segments.Count;
            truncated["layers"].AsBool =
                layerCount > 0;
            truncated["clips"].AsBool =
                clipCount > snapshot.Clips.Count;
            result["truncated"] = truncated;
            if (adapterError != null)
            {
                result["error"] = adapterError;
            }
            result["controls"] =
                ready
                ? BasicTimelineControls(
                    plugin,
                    snapshot.Clips.Count != 0)
                : new JSONArray();
            return result;
        }

        private static JSONClass BuildSam3dCameraStatus(Atom atom)
        {
            MVRScript renderer = FindSam3dRenderer(atom);
            if (renderer == null)
            {
                return null;
            }
            JSONClass result = new JSONClass();
            result["compatible"].AsBool = true;
            string status =
                (renderer.GetStringJSONParam(
                    Sam3dStatusParam).val ?? "")
                .Trim()
                .ToLowerInvariant();
            if (status != "idle" &&
                status != "rendering" &&
                status != "encoding" &&
                status != "succeeded" &&
                status != "failed")
            {
                status = "unknown";
            }
            result["status"] = status;
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            if (fov != null && IsFinite(fov.val))
            {
                result["flatHorizontalFov"].AsFloat = fov.val;
            }
            JSONStorableStringChooser aspect =
                renderer.GetStringChooserJSONParam("Aspect Ratio");
            JSONStorableStringChooser resolution =
                renderer.GetStringChooserJSONParam("Output Resolution");
            result["aspectRatio"] =
                aspect == null ? "" : aspect.val ?? "";
            result["outputResolution"] =
                resolution == null ? "" : resolution.val ?? "";
            return result;
        }

        private static JSONArray Capabilities()
        {
            JSONArray capabilities = new JSONArray();
            capabilities.Add("atom-roster");
            capabilities.Add("atom-select");
            capabilities.Add("atom-add");
            capabilities.Add("atom-preset-apply");
            capabilities.Add("subscene-load");
            capabilities.Add("custom-unity-asset-load");
            capabilities.Add("custom-unity-asset-choice");
            capabilities.Add("scene-load");
            capabilities.Add("person-roster");
            capabilities.Add("person-preset-apply");
            capabilities.Add("person-preset-appearance");
            capabilities.Add("person-preset-animation");
            capabilities.Add("person-preset-breast-physics");
            capabilities.Add("person-preset-clothing");
            capabilities.Add("person-preset-general");
            capabilities.Add("person-preset-glute-physics");
            capabilities.Add("person-preset-hair");
            capabilities.Add("person-preset-morphs");
            capabilities.Add("person-preset-plugins");
            capabilities.Add("person-preset-pose");
            capabilities.Add("person-preset-skin");
            capabilities.Add("person-clothing-item-toggle");
            capabilities.Add("person-hair-roster");
            capabilities.Add("person-hair-item-toggle");
            capabilities.Add("person-add");
            capabilities.Add("person-select");
            capabilities.Add("timeline-roster");
            capabilities.Add("timeline-transport");
            capabilities.Add("timeline-animation-play");
            capabilities.Add("timeline-adapter-v1");
            capabilities.Add("sam3d-apply-v1");
            capabilities.Add("sam3d-undo-v1");
            capabilities.Add("sam3d-capture-v1");
            capabilities.Add("sam3d-camera-vrfunscript-v1");
            return capabilities;
        }

        private void PublishTimelineStatus()
        {
            try
            {
                JSONClass document = new JSONClass();
                document["protocol"].AsInt = ProtocolVersion;
                document["timelineProtocol"].AsInt =
                    TimelineProtocolVersion;
                document["bridgeVersion"] = BridgeVersion;
                document["instanceId"] = _instanceId;
                document["updatedAtUtc"] = UtcNow();

                SuperController controller = SuperController.singleton;
                bool loading = controller == null || controller.isLoading;
                document["loading"].AsBool = loading;
                Atom selected =
                    controller == null
                    ? null
                    : controller.GetSelectedAtom();

                List<TimelineCandidate> candidates =
                    new List<TimelineCandidate>();
                HashSet<string> liveKeys = new HashSet<string>();
                int discoveredCount = 0;
                if (controller != null)
                {
                    foreach (Atom atom in controller.GetAtoms())
                    {
                        if (atom == null)
                        {
                            continue;
                        }
                        List<string> storableIds =
                            atom.GetStorableIDs();
                        if (storableIds == null)
                        {
                            continue;
                        }
                        int idIndex;
                        for (idIndex = 0;
                             idIndex < storableIds.Count;
                             idIndex++)
                        {
                            string storableId =
                                storableIds[idIndex] ?? "";
                            if (!storableId.EndsWith(
                                    "VamTimeline.AtomPlugin",
                                    StringComparison.Ordinal))
                            {
                                continue;
                            }
                            MVRScript plugin =
                                atom.GetStorableByID(storableId)
                                as MVRScript;
                            if (plugin == null)
                            {
                                continue;
                            }
                            discoveredCount++;
                            if (candidates.Count >=
                                MaximumTimelineInstances)
                            {
                                continue;
                            }

                            string key =
                                (atom.uid ?? "") +
                                "\n" +
                                storableId;
                            liveKeys.Add(key);
                            bool isSelected =
                                selected != null &&
                                object.ReferenceEquals(selected, atom);
                            JSONStorableString adapterState =
                                plugin.GetStringJSONParam(
                                    TimelineExternalState);
                            JSONStorableAction refresh =
                                plugin.GetAction(
                                    TimelineRefreshExternalState);
                            JSONStorableString adapterCommand =
                                plugin.GetStringJSONParam(
                                    TimelineExternalCommand);
                            JSONStorableString adapterResult =
                                plugin.GetStringJSONParam(
                                    TimelineExternalResult);
                            JSONStorableAction execute =
                                plugin.GetAction(
                                    TimelineExecuteExternalCommand);

                            TimelineCandidate candidate =
                                new TimelineCandidate();
                            candidate.ScanIndex = candidates.Count;
                            candidate.Key = key;
                            candidate.Atom = atom;
                            candidate.Plugin = plugin;
                            candidate.StorableId = storableId;
                            candidate.Selected = isSelected;
                            JSONStorableBool isPlaying =
                                plugin.GetBoolJSONParam("Is Playing");
                            candidate.Playing =
                                isPlaying != null && isPlaying.val;
                            candidate.AdapterAvailable =
                                adapterState != null &&
                                refresh != null &&
                                refresh.actionCallback != null &&
                                adapterCommand != null &&
                                adapterResult != null &&
                                execute != null &&
                                execute.actionCallback != null;
                            candidate.AdapterState = adapterState;
                            candidate.AdapterRefresh = refresh;
                            candidates.Add(candidate);
                        }
                    }
                }

                List<TimelineCandidate> prioritized =
                    new List<TimelineCandidate>(candidates);
                prioritized.Sort(
                    delegate(
                        TimelineCandidate left,
                        TimelineCandidate right)
                    {
                        if (left.Selected != right.Selected)
                        {
                            return left.Selected ? -1 : 1;
                        }
                        if (left.Playing != right.Playing)
                        {
                            return left.Playing ? -1 : 1;
                        }
                        return left.ScanIndex.CompareTo(
                            right.ScanIndex);
                    });

                int globalClipBudget =
                    MaximumTimelineClipsGlobally;
                int totalClipCount = 0;
                int publishedClipCount = 0;
                bool enhancedFound = false;
                int candidateIndex;
                for (candidateIndex = 0;
                     candidateIndex < prioritized.Count;
                     candidateIndex++)
                {
                    TimelineCandidate candidate =
                        prioritized[candidateIndex];
                    int instanceClipBudget =
                        Math.Min(
                            globalClipBudget,
                            MaximumTimelineClips);
                    JSONClass instance = null;
                    JSONClass adapterState = null;
                    JSONClass adapterError = null;

                    if (candidate.AdapterAvailable)
                    {
                        enhancedFound = true;
                        if (instanceClipBudget > 0)
                        {
                            try
                            {
                                candidate.AdapterRefresh.actionCallback();
                                adapterState =
                                    JSON.Parse(
                                        candidate.AdapterState.val ?? "")
                                    .AsObject;
                                if (adapterState != null &&
                                    adapterState["protocol"].AsInt ==
                                        TimelineProtocolVersion)
                                {
                                    instance =
                                        BuildEnhancedTimelineStatus(
                                            candidate.Key,
                                            candidate.Atom,
                                            candidate.Plugin,
                                            candidate.StorableId,
                                            adapterState,
                                            candidate.Selected,
                                            instanceClipBudget);
                                }
                                else
                                {
                                    adapterError =
                                        TimelineAdapterErrorJson(
                                            "invalid-state",
                                            "Timeline returned an invalid external state.");
                                }
                            }
                            catch (Exception exception)
                            {
                                adapterError =
                                    TimelineAdapterErrorJson(
                                        "refresh-failed",
                                        "Timeline could not refresh its external state: " +
                                        DescribeException(exception));
                            }
                        }
                        else
                        {
                            // Reuse metadata already published by Timeline,
                            // but do not invoke the adapter's full catalog
                            // rebuild once the global clip budget is spent.
                            try
                            {
                                adapterState =
                                    JSON.Parse(
                                        candidate.AdapterState.val ?? "")
                                    .AsObject;
                                if (adapterState == null ||
                                    adapterState["protocol"].AsInt !=
                                        TimelineProtocolVersion)
                                {
                                    adapterState = null;
                                }
                            }
                            catch
                            {
                                adapterState = null;
                            }
                            adapterError =
                                TimelineAdapterErrorJson(adapterState);
                        }
                    }

                    if (instance == null)
                    {
                        instance =
                            BuildBasicTimelineStatus(
                                candidate.Key,
                                candidate.Atom,
                                candidate.Plugin,
                                candidate.StorableId,
                                candidate.Selected,
                                instanceClipBudget,
                                candidate.AdapterAvailable,
                                adapterState,
                                adapterError);
                    }
                    candidate.Result = instance;

                    JSONClass instanceCounts =
                        instance["counts"].AsObject;
                    int instanceTotal =
                        instanceCounts == null
                        ? 0
                        : BoundedTimelineCount(
                            instanceCounts["clips"].AsInt);
                    int instancePublished =
                        instanceCounts == null
                        ? 0
                        : BoundedTimelineCount(
                            instanceCounts[
                                "publishedClips"].AsInt);
                    totalClipCount += instanceTotal;
                    publishedClipCount += instancePublished;
                    globalClipBudget =
                        Math.Max(
                            0,
                            globalClipBudget -
                                instancePublished);
                }

                JSONArray instances = new JSONArray();
                for (candidateIndex = 0;
                     candidateIndex < candidates.Count;
                     candidateIndex++)
                {
                    instances.Add(candidates[candidateIndex].Result);
                }

                List<string> removedKeys = new List<string>();
                foreach (
                    KeyValuePair<string, TimelineSnapshot> entry
                    in _timelineSnapshots)
                {
                    if (!liveKeys.Contains(entry.Key))
                    {
                        removedKeys.Add(entry.Key);
                    }
                }
                int removedIndex;
                for (removedIndex = 0;
                     removedIndex < removedKeys.Count;
                     removedIndex++)
                {
                    _timelineSnapshots.Remove(removedKeys[removedIndex]);
                }

                JSONArray capabilities = new JSONArray();
                capabilities.Add("timeline-roster");
                capabilities.Add("timeline-transport");
                capabilities.Add("timeline-animation-play");
                if (enhancedFound)
                {
                    capabilities.Add("timeline-adapter-v1");
                }
                document["instances"] = instances;
                document["truncated"].AsBool =
                    discoveredCount > MaximumTimelineInstances ||
                    totalClipCount > publishedClipCount;
                JSONClass counts = new JSONClass();
                counts["instances"].AsInt =
                    BoundedTimelineCount(discoveredCount);
                counts["publishedInstances"].AsInt =
                    candidates.Count;
                counts["clips"].AsInt =
                    BoundedTimelineCount(totalClipCount);
                counts["publishedClips"].AsInt =
                    BoundedTimelineCount(publishedClipCount);
                document["counts"] = counts;
                JSONClass limits = new JSONClass();
                limits["maxInstances"].AsInt =
                    MaximumTimelineInstances;
                limits["maxClips"].AsInt =
                    MaximumTimelineClips;
                limits["maxClipsGlobally"].AsInt =
                    MaximumTimelineClipsGlobally;
                document["limits"] = limits;
                document["capabilities"] = capabilities;
                FileManagerSecure.WriteAllText(
                    TimelinePath,
                    document.ToString());
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write Timeline status: " +
                    DescribeException(exception));
            }
        }

        private void PublishSceneStatus()
        {
            try
            {
                JSONClass scene = new JSONClass();
                scene["protocol"].AsInt = ProtocolVersion;
                scene["bridgeVersion"] = BridgeVersion;
                scene["instanceId"] = _instanceId;
                scene["updatedAtUtc"] = UtcNow();

                SuperController controller = SuperController.singleton;
                bool loading = controller == null || controller.isLoading;
                scene["loading"].AsBool = loading;

                Atom selected = null;
                if (controller != null)
                {
                    selected = controller.GetSelectedAtom();
                }
                string selectedUid =
                    selected != null
                    ? selected.uid ?? ""
                    : "";
                scene["selectedUid"] = selectedUid;

                JSONArray atoms = new JSONArray();
                JSONArray persons = new JSONArray();
                int globalCuaChoiceBudget = MaximumCuaChoicesGlobally;
                int globalClothingResourceBudget =
                    MaximumClothingRefsGlobally;
                int globalHairItemBudget =
                    MaximumHairItemsGlobally;
                HashSet<string> liveCuaUids = new HashSet<string>();
                HashSet<string> livePersonUids = new HashSet<string>();
                if (controller != null)
                {
                    foreach (Atom atom in controller.GetAtoms())
                    {
                        if (atom == null)
                        {
                            continue;
                        }
                        bool isSelected =
                            selectedUid.Length != 0 &&
                            atom.uid == selectedUid;
                        JSONClass atomStatus = new JSONClass();
                        atomStatus["uid"] = atom.uid ?? "";
                        atomStatus["type"] = atom.type ?? "";
                        atomStatus["selected"].AsBool = isSelected;
                        if (atom.type == "CustomUnityAsset")
                        {
                            liveCuaUids.Add(atom.uid);
                            atomStatus["cua"] =
                                BuildCuaStatus(
                                    atom,
                                    ref globalCuaChoiceBudget);
                        }
                        if (atom.type == "Empty")
                        {
                            JSONClass sam3dCamera =
                                BuildSam3dCameraStatus(atom);
                            if (sam3dCamera != null)
                            {
                                atomStatus["sam3dCamera"] =
                                    sam3dCamera;
                            }
                        }
                        atoms.Add(atomStatus);

                        if (atom.type != "Person")
                        {
                            continue;
                        }
                        JSONClass person = new JSONClass();
                        person["uid"] = atom.uid ?? "";
                        person["selected"].AsBool = isSelected;
                        livePersonUids.Add(atom.uid);
                        person["clothing"] =
                            BuildPersonClothingStatus(
                                atom,
                                ref globalClothingResourceBudget);
                        person["hair"] =
                            BuildPersonHairStatus(
                                atom,
                                ref globalHairItemBudget);
                        persons.Add(person);
                    }
                }
                List<string> removedCuaUids = new List<string>();
                foreach (
                    KeyValuePair<string, CuaChoiceSnapshot> entry
                    in _cuaChoiceSnapshots)
                {
                    if (!liveCuaUids.Contains(entry.Key))
                    {
                        removedCuaUids.Add(entry.Key);
                    }
                }
                int removedOffset;
                for (removedOffset = 0;
                     removedOffset < removedCuaUids.Count;
                     removedOffset++)
                {
                    _cuaChoiceSnapshots.Remove(
                        removedCuaUids[removedOffset]);
                }
                List<string> removedPersonUids = new List<string>();
                foreach (
                    KeyValuePair<string, PersonClothingSnapshot> entry
                    in _personClothingSnapshots)
                {
                    if (!livePersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                for (removedOffset = 0;
                     removedOffset < removedPersonUids.Count;
                     removedOffset++)
                {
                    _personClothingSnapshots.Remove(
                        removedPersonUids[removedOffset]);
                }
                removedPersonUids.Clear();
                foreach (
                    KeyValuePair<string, PersonHairSnapshot> entry
                    in _personHairSnapshots)
                {
                    if (!livePersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                for (removedOffset = 0;
                     removedOffset < removedPersonUids.Count;
                     removedOffset++)
                {
                    _personHairSnapshots.Remove(
                        removedPersonUids[removedOffset]);
                }
                scene["atoms"] = atoms;
                scene["persons"] = persons;
                JSONClass sam3d = new JSONClass();
                Sam3dUndoSnapshot liveSam3dSnapshot =
                    loading
                    ? null
                    : CurrentSam3dSnapshot();
                bool sam3dApplied = liveSam3dSnapshot != null;
                sam3d["applied"].AsBool = sam3dApplied;
                sam3d["undoAvailable"].AsBool = sam3dApplied;
                if (sam3dApplied)
                {
                    sam3d["jobId"] =
                        liveSam3dSnapshot.JobId ?? "";
                    sam3d["revision"] =
                        liveSam3dSnapshot.Revision ?? "";
                    sam3d["targetUid"] =
                        liveSam3dSnapshot.TargetUid ?? "";
                    sam3d["cameraUid"] =
                        liveSam3dSnapshot.CameraUid ?? "";
                    JSONClass settlement =
                        BuildSam3dSettlementStatus(
                            liveSam3dSnapshot.Diagnostics);
                    if (settlement != null)
                    {
                        sam3d["settlement"] = settlement;
                    }
                }
                if (_lastSam3dRequestId.Length != 0)
                {
                    JSONClass lastAction = new JSONClass();
                    lastAction["requestId"] =
                        _lastSam3dRequestId;
                    lastAction["command"] =
                        _lastSam3dCommand;
                    lastAction["jobId"] =
                        _lastSam3dJobId;
                    lastAction["revision"] =
                        _lastSam3dRevision;
                    lastAction["cameraUid"] =
                        _lastSam3dCameraUid;
                    lastAction["state"] =
                        _lastSam3dState;
                    lastAction["message"] =
                        _lastSam3dMessage;
                    sam3d["lastAction"] = lastAction;
                }
                scene["sam3d"] = sam3d;
                scene["capabilities"] = Capabilities();
                FileManagerSecure.WriteAllText(ScenePath, scene.ToString());
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write scene status: " +
                    DescribeException(exception));
            }
        }

        private void PublishStatus(
            string state,
            string requestId,
            string startedAtUtc,
            string finishedAtUtc,
            string backend,
            string message)
        {
            string signature =
                state + "\n" +
                requestId + "\n" +
                startedAtUtc + "\n" +
                finishedAtUtc + "\n" +
                backend + "\n" +
                message + "\n" +
                _lastCompletedRequestId;
            if (signature == _lastPublishedStatusSignature)
            {
                return;
            }

            try
            {
                JSONClass status = new JSONClass();
                status["protocol"].AsInt = ProtocolVersion;
                status["bridgeVersion"] = BridgeVersion;
                status["instanceId"] = _instanceId;
                status["requestId"] = requestId ?? "";
                status["lastCompletedRequestId"] = _lastCompletedRequestId;
                status["state"] = state;
                status["ok"].AsBool = state == StateOk;
                status["updatedAtUtc"] = UtcNow();
                status["startedAtUtc"] = startedAtUtc ?? "";
                status["finishedAtUtc"] = finishedAtUtc ?? "";
                status["backend"] = backend ?? "";
                status["message"] = message ?? "";
                status["capabilities"] = Capabilities();

                FileManagerSecure.WriteAllText(StatusPath, status.ToString());
                _lastPublishedStatusSignature = signature;
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write status: " +
                    DescribeException(exception));
            }
        }

        private static string DescribeException(Exception exception)
        {
            if (exception == null)
            {
                return "Unknown error.";
            }

            // Runtime type inspection in diagnostics emits a prohibited
            // metadata call on VaM's legacy Mono runtime.
            string message = exception.Message ?? "";
            message = message.Replace("\r", " ").Replace("\n", " ").Trim();
            if (message.Length == 0)
            {
                message = "Unspecified error.";
            }
            if (message.Length > 1000)
            {
                message = message.Substring(0, 1000);
            }
            return message;
        }
    }
}

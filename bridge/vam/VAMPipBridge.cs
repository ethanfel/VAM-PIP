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
        private const string BridgeVersion = "0.6.0";

        private const string PluginDataRoot = "Saves\\PluginData";
        private const string DataRoot = "Saves\\PluginData\\VAMPip";
        private const string BridgeRoot = DataRoot + "\\Bridge";
        private const string RequestPath = BridgeRoot + "\\request.json";
        private const string StatusPath = BridgeRoot + "\\status.json";
        private const string ScenePath = BridgeRoot + "\\scene.json";

        private const int MaximumResourceRefLength = 1000;
        private const int MaximumCuaChoicesPerAtom = 128;
        private const int MaximumCuaChoicesGlobally = 512;
        private const int MaximumCuaChoiceLabelLength = 256;
        private const int MaximumClothingRefsPerPerson = 256;
        private const int MaximumClothingRefsGlobally = 1024;
        private const float PollIntervalSeconds = 0.5f;
        private const float ScenePublishIntervalSeconds = 1.0f;
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
        private const string CommandSelectPerson = "selectPerson";
        private const string CommandSelectAtom = "selectAtom";
        private const string CommandLoadScene = "loadScene";
        private const string StateQueued = "queued";
        private const string StateDeferredLoading = "deferred-loading";
        private const string StateRescanning = "rescanning";
        private const string StateApplying = "applying";
        private const string StateAdding = "adding";
        private const string StateSelecting = "selecting";
        private const string StateLoadingScene = "loading-scene";
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
            public bool Locked;
        }

        private sealed class PersonClothingSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
        }

        private bool _operational;
        private bool _requestInProgress;
        private bool _skipPendingProcessing;
        private float _nextPollAt;
        private float _nextScenePublishAt;
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

        public override void Init()
        {
            try
            {
                _instanceId = Guid.NewGuid().ToString("N");
                EnsureBridgeDirectory();
                RecoverLastCompletedRequest();

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
                PublishStatus(
                    StateOk,
                    _lastCompletedRequestId,
                    "",
                    "",
                    "",
                    "Bridge ready.");
                PublishSceneStatus();
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
                else
                {
                    RejectRequest(
                        requestId,
                        "Unsupported command. Accepted commands are 'rescan' " +
                        "'applyPersonPreset', 'addPerson', 'addAtom', " +
                        "'applyAtomPreset', 'loadSubscene', " +
                        "'loadCustomUnityAsset', " +
                        "'selectCustomUnityAssetChoice', " +
                        "'setPersonClothingResource', 'selectPerson', " +
                        "'selectAtom', and 'loadScene'.");
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
                if (item == null)
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
            clothing["activeResourceRefs"] = activeRefs;
            clothing["lockedResourceRefs"] = lockedRefs;
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
            int resourceCount = 0;
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
                if (entry.ResourceRef.Length == 0 ||
                    published.Contains(entry.ResourceRef))
                {
                    continue;
                }
                resourceCount++;
                if (published.Count >= MaximumClothingRefsPerPerson ||
                    globalResourceBudget <= 0)
                {
                    continue;
                }
                published.Add(entry.ResourceRef);
                activeRefs.Add(entry.ResourceRef);
                if (entry.Locked)
                {
                    lockedRefs.Add(entry.ResourceRef);
                }
                globalResourceBudget--;
            }
            clothing["activeCount"].AsInt = entries.Count;
            clothing["lockedCount"].AsInt = lockedCount;
            clothing["truncated"].AsBool =
                resourceCount > published.Count;
            clothing["revision"] = snapshot.Revision;
            return clothing;
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
            capabilities.Add("person-add");
            capabilities.Add("person-select");
            return capabilities;
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
                scene["atoms"] = atoms;
                scene["persons"] = persons;
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

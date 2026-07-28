using System;
using System.Collections;
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
        private const string BridgeVersion = "0.3.0";

        private const string PluginDataRoot = "Saves\\PluginData";
        private const string DataRoot = "Saves\\PluginData\\VAMPip";
        private const string BridgeRoot = DataRoot + "\\Bridge";
        private const string RequestPath = BridgeRoot + "\\request.json";
        private const string StatusPath = BridgeRoot + "\\status.json";
        private const string ScenePath = BridgeRoot + "\\scene.json";

        private const int MaximumResourceRefLength = 1000;
        private const float PollIntervalSeconds = 0.5f;
        private const float ScenePublishIntervalSeconds = 1.0f;
        private const float MinimumRescanIntervalSeconds = 5.0f;
        private const float MaximumSceneLoadWaitSeconds = 120.0f;

        private const string CommandRescan = "rescan";
        private const string CommandApplyPersonPreset = "applyPersonPreset";
        private const string CommandAddPerson = "addPerson";
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

        private sealed class BridgeRequest
        {
            public string RequestId;
            public string Command;
            public string BrowserAssistMode;
            public string TargetUid;
            public string PresetKind;
            public string ResourceRef;
            public bool RescanRequired;
            public bool Merge;
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
                parsed.PresetKind = "";
                parsed.ResourceRef = "";
                parsed.Merge = false;

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
                        "'applyPersonPreset', 'addPerson', 'selectPerson', " +
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
            if (request.Command == CommandAddPerson)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(ExecuteAddPerson(request));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start Person creation: " +
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
                Time.realtimeSinceStartup + MaximumSceneLoadWaitSeconds;
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

        private IEnumerator ExecuteAddPerson(BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateAdding,
                request.RequestId,
                startedAt,
                "",
                "",
                "Adding Person " + request.TargetUid + ".");

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
                            "Person",
                            request.TargetUid,
                            true);
                    if (addRoutine == null)
                    {
                        throw new Exception(
                            "VaM did not provide a Person creation routine.");
                    }
                }
            }
            catch (Exception exception)
            {
                addError =
                    "Could not add Person: " +
                    DescribeException(exception);
            }
            if (addError.Length != 0)
            {
                FinishAddPersonError(
                    request,
                    startedAt,
                    addError);
                yield break;
            }

            if (existing != null)
            {
                if (existing.type != "Person")
                {
                    FinishAddPersonError(
                        request,
                        startedAt,
                        "targetUid is already used by a non-Person atom.");
                    yield break;
                }
                FinishAddPersonOk(
                    request,
                    startedAt,
                    "Person already exists; no scene change was needed.");
                yield break;
            }

            while (true)
            {
                bool hasNext = false;
                object current = null;
                string iterationError = "";
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
                        "Person creation failed: " +
                        DescribeException(exception);
                }
                if (iterationError.Length != 0)
                {
                    FinishAddPersonError(
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
                if (created == null || created.type != "Person")
                {
                    throw new Exception(
                        "VaM completed creation without the requested Person.");
                }
                FinishAddPersonOk(
                    request,
                    startedAt,
                    "Person added.");
            }
            catch (Exception exception)
            {
                FinishAddPersonError(
                    request,
                    startedAt,
                    "Could not verify the added Person: " +
                    DescribeException(exception));
            }
        }

        private void FinishAddPersonOk(
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

        private void FinishAddPersonError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
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

        private static JSONArray Capabilities()
        {
            JSONArray capabilities = new JSONArray();
            capabilities.Add("atom-roster");
            capabilities.Add("atom-select");
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
                        atoms.Add(atomStatus);

                        if (atom.type != "Person")
                        {
                            continue;
                        }
                        JSONClass person = new JSONClass();
                        person["uid"] = atom.uid ?? "";
                        person["selected"].AsBool = isSelected;
                        persons.Add(person);
                    }
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

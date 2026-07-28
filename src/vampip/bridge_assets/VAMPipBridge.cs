using System;
using System.Reflection;
using MVR.FileManagementSecure;
using SimpleJSON;
using UnityEngine;

namespace VAMPip
{
    /// <summary>
    /// Small session-plugin bridge between the external VAM-PIP manager and VaM.
    ///
    /// The external manager owns package selection, dependency resolution, and
    /// filesystem changes. This bridge deliberately accepts only a rescan command.
    /// </summary>
    public class VAMPipBridge : MVRScript
    {
        private const int ProtocolVersion = 1;
        private const string BridgeVersion = "0.1.1";

        private const string PluginDataRoot = "Saves\\PluginData";
        private const string DataRoot = "Saves\\PluginData\\VAMPip";
        private const string BridgeRoot = DataRoot + "\\Bridge";
        private const string RequestPath = BridgeRoot + "\\request.json";
        private const string StatusPath = BridgeRoot + "\\status.json";

        private const float PollIntervalSeconds = 0.5f;
        private const float MinimumRescanIntervalSeconds = 5.0f;

        private const string StateReady = "ready";
        private const string StateDeferredLoading = "deferred-loading";
        private const string StateRescanning = "rescanning";
        private const string StateOk = "ok";
        private const string StateError = "error";

        private sealed class BridgeRequest
        {
            public string RequestId;
            public string BrowserAssistMode;
        }

        private bool _operational;
        private float _nextPollAt;
        private float _nextAllowedRescanAt;
        private string _instanceId = "";
        private string _lastRequestPayload;
        private string _lastHandledRequestId = "";
        private string _lastCompletedRequestId = "";
        private string _lastPublishedStatusSignature = "";
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
                PublishStatus(
                    StateReady,
                    _lastCompletedRequestId,
                    "",
                    "",
                    "",
                    "Bridge ready.");
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
            if (now < _nextPollAt)
            {
                return;
            }

            _nextPollAt = now + PollIntervalSeconds;

            try
            {
                PollRequestFile();
                ProcessPendingRequest(now);
            }
            catch (Exception exception)
            {
                string requestId =
                    _pendingRequest == null ? "" : _pendingRequest.RequestId;
                string message = "Bridge update failed: " + DescribeException(exception);
                PublishStatus(
                    StateError,
                    requestId,
                    "",
                    UtcNow(),
                    "",
                    message);
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
                string payload = FileManagerSecure.ReadAllText(StatusPath);
                JSONClass status = JSON.Parse(payload).AsObject;
                if (status == null ||
                    status["protocol"].AsInt != ProtocolVersion)
                {
                    return;
                }

                // `lastCompletedRequestId` is carried into later ready/error
                // statuses, but it is assigned only after an ok rescan.
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
                // A status write is intentionally allowed to be non-atomic.
                // The external manager and this recovery path both retry later.
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
                    RejectRequest(requestId, "requestId must contain 1 to 200 characters.");
                    return;
                }

                string command = ((string)request["command"] ?? "").Trim();
                if (command != "rescan")
                {
                    RejectRequest(requestId, "Unsupported command. Only 'rescan' is accepted.");
                    return;
                }

                string browserAssistMode =
                    ((string)request["browserAssist"] ?? "auto").Trim().ToLowerInvariant();
                if (browserAssistMode.Length == 0)
                {
                    browserAssistMode = "auto";
                }

                if (browserAssistMode != "auto" && browserAssistMode != "off")
                {
                    RejectRequest(
                        requestId,
                        "browserAssist must be either 'auto' or 'off'.");
                    return;
                }

                if (requestId == _lastHandledRequestId)
                {
                    _pendingRequest = null;
                    return;
                }

                // This is a latest-desired-state mailbox. Replacing a queued
                // request coalesces several manager operations into one scan.
                _pendingRequest = new BridgeRequest();
                _pendingRequest.RequestId = requestId;
                _pendingRequest.BrowserAssistMode = browserAssistMode;
            }
            catch (Exception exception)
            {
                RejectRequest(
                    requestId,
                    "Could not parse request: " + DescribeException(exception));
            }
        }

        private void RejectRequest(string requestId, string message)
        {
            _pendingRequest = null;
            PublishStatus(
                StateError,
                requestId,
                "",
                UtcNow(),
                "",
                message);
            SuperController.LogError("[VAM-PIP Bridge] " + message);
        }

        private void ProcessPendingRequest(float now)
        {
            if (_pendingRequest == null)
            {
                return;
            }

            string requestId = _pendingRequest.RequestId;

            if (SuperController.singleton == null)
            {
                PublishStatus(
                    StateReady,
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

            if (now < _nextAllowedRescanAt)
            {
                PublishStatus(
                    StateReady,
                    requestId,
                    "",
                    "",
                    "",
                    "Rescan queued by the rate limiter.");
                return;
            }

            BridgeRequest request = _pendingRequest;
            _pendingRequest = null;
            ExecuteRescan(request);
        }

        private void ExecuteRescan(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            string message = "";

            PublishStatus(
                StateRescanning,
                request.RequestId,
                startedAt,
                "",
                "",
                "Rescanning VaM packages.");

            try
            {
                bool browserAssistCompleted = false;
                string browserAssistResult = "";

                if (request.BrowserAssistMode == "auto")
                {
                    browserAssistCompleted =
                        TryRescanWithBrowserAssist(out browserAssistResult);
                }

                if (browserAssistCompleted)
                {
                    backend = "browserassist";
                    message = browserAssistResult;
                }
                else
                {
                    // BrowserAssist is optional. Its method calls the core VaM
                    // rescan itself, so this fallback runs only when that path
                    // was unavailable or reported failure.
                    SuperController.singleton.RescanPackages();
                    backend = "vam";

                    if (request.BrowserAssistMode == "off")
                    {
                        message = "Core VaM package rescan completed.";
                    }
                    else if (browserAssistResult.Length == 0)
                    {
                        message =
                            "Core VaM package rescan completed; BrowserAssist was unavailable.";
                    }
                    else
                    {
                        message =
                            "Core VaM package rescan completed after BrowserAssist fallback: " +
                            browserAssistResult;
                    }
                }

                _lastHandledRequestId = request.RequestId;
                _lastCompletedRequestId = request.RequestId;
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Request " + request.RequestId +
                    " completed using " + backend + ".");
            }
            catch (Exception exception)
            {
                // Do not retry continuously inside one VaM session. The manager
                // can submit a new ID; after a bridge restart, a non-ok request
                // is attempted once again.
                _lastHandledRequestId = request.RequestId;
                message = "Package rescan failed: " + DescribeException(exception);
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

        private bool TryRescanWithBrowserAssist(out string result)
        {
            result = "";

            try
            {
                MVRScript browserAssist = FindBrowserAssist();
                if (browserAssist == null)
                {
                    result = "BrowserAssist is not loaded and enabled.";
                    return false;
                }

                Assembly assembly = browserAssist.GetType().Assembly;
                // MVRScript inherits JSONStorable.Type, which shadows
                // System.Type in VaM's legacy compiler. Keep reflection types
                // fully qualified throughout this class.
                System.Type manifestType =
                    assembly.GetType("JayJayWon.VARPackageManifest", false);
                if (manifestType == null)
                {
                    result = "Compatible BrowserAssist manifest API was not found.";
                    return false;
                }

                MethodInfo rescanMethod = manifestType.GetMethod(
                    "RescanPackages",
                    BindingFlags.Public | BindingFlags.Static,
                    null,
                    System.Type.EmptyTypes,
                    null);
                if (rescanMethod == null)
                {
                    result = "Compatible BrowserAssist rescan method was not found.";
                    return false;
                }

                // This BrowserAssist method performs the core VaM rescan and
                // then updates BrowserAssist's own package/resource manifests.
                rescanMethod.Invoke(null, null);

                string uiWarning;
                if (TryRefreshVisibleBrowserAssistUI(assembly, out uiWarning))
                {
                    result = "VaM and BrowserAssist package data were refreshed.";
                }
                else if (uiWarning.Length == 0)
                {
                    result =
                        "VaM and BrowserAssist package data were refreshed; " +
                        "the BrowserAssist UI was closed.";
                }
                else
                {
                    result =
                        "VaM and BrowserAssist package data were refreshed; " +
                        "UI refresh warning: " + uiWarning;
                }

                return true;
            }
            catch (Exception exception)
            {
                // A BrowserAssist failure is best-effort. The caller performs
                // the reliable core rescan. This can rarely duplicate core work
                // if BrowserAssist threw after entering its own rescan method.
                result = DescribeException(exception);
                SuperController.LogError(
                    "[VAM-PIP Bridge] BrowserAssist refresh failed; " +
                    "using core fallback. " + result);
                return false;
            }
        }

        private MVRScript FindBrowserAssist()
        {
            if (manager == null || manager.gameObject == null)
            {
                return null;
            }

            Transform pluginsRoot = manager.gameObject.transform.Find("Plugins");
            if (pluginsRoot == null)
            {
                return null;
            }

            foreach (Transform child in pluginsRoot)
            {
                MVRScript script = child.gameObject.GetComponent<MVRScript>();
                if (script != null &&
                    script.enabled &&
                    script.name.EndsWith(
                        "_JayJayWon.BrowserAssist",
                        StringComparison.Ordinal))
                {
                    return script;
                }
            }

            return null;
        }

        private static bool TryRefreshVisibleBrowserAssistUI(
            Assembly assembly,
            out string warning)
        {
            warning = "";

            try
            {
                System.Type browserAssistType =
                    assembly.GetType("JayJayWon.BrowserAssist", false);
                if (browserAssistType == null)
                {
                    warning = "BrowserAssist type was not found.";
                    return false;
                }

                PropertyInfo mainBrowserProperty = browserAssistType.GetProperty(
                    "mainBrowserUI",
                    BindingFlags.Public | BindingFlags.Static);
                if (mainBrowserProperty == null)
                {
                    warning = "BrowserAssist main UI property was not found.";
                    return false;
                }

                object mainBrowser = mainBrowserProperty.GetValue(null, null);
                if (mainBrowser == null)
                {
                    return false;
                }

                System.Type mainBrowserType = mainBrowser.GetType();
                PropertyInfo isActiveProperty = mainBrowserType.GetProperty(
                    "isActive",
                    BindingFlags.Public | BindingFlags.Instance);
                if (isActiveProperty != null)
                {
                    object isActiveValue = isActiveProperty.GetValue(mainBrowser, null);
                    if (isActiveValue is bool && !(bool)isActiveValue)
                    {
                        return false;
                    }
                }

                MethodInfo refreshMethod = mainBrowserType.GetMethod(
                    "RefreshFilterResults",
                    BindingFlags.Public | BindingFlags.Instance,
                    null,
                    new System.Type[] { typeof(bool) },
                    null);
                if (refreshMethod == null)
                {
                    warning = "BrowserAssist UI refresh method was not found.";
                    return false;
                }

                refreshMethod.Invoke(mainBrowser, new object[] { true });
                return true;
            }
            catch (Exception exception)
            {
                warning = DescribeException(exception);
                return false;
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

            while (exception is TargetInvocationException &&
                   exception.InnerException != null)
            {
                exception = exception.InnerException;
            }

            string message =
                exception.GetType().Name + ": " + (exception.Message ?? "");
            message = message.Replace("\r", " ").Replace("\n", " ").Trim();
            if (message.Length > 1000)
            {
                message = message.Substring(0, 1000);
            }

            return message;
        }
    }
}

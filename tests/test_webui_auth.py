from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
JAVASCRIPT = (ROOT / "src" / "vampip" / "webui" / "app.js").read_text(encoding="utf-8")


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class WebUIManagerAuthTests(unittest.TestCase):
    def run_javascript(self, script: str) -> dict[str, object]:
        completed = subprocess.run(
            ["node", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        return json.loads(completed.stdout)

    def javascript_block(self, start: str, end: str) -> str:
        block_start = JAVASCRIPT.index(start)
        block_end = JAVASCRIPT.index(end, block_start)
        return JAVASCRIPT[block_start:block_end]

    def auth_api_block(self) -> str:
        return self.javascript_block(
            "function managerAuthBlockedError(",
            "function showDialog(",
        )

    def capture_token_block(self) -> str:
        return self.javascript_block(
            "function captureToken(",
            "function applyInitialRoute(",
        )

    def test_exact_fragment_overrides_stale_session_and_rearms_auth(self) -> None:
        capture_token = self.capture_token_block()
        result = self.run_javascript(
            f"""
"use strict";
const TOKEN_KEY = "vampip-token";
const storage = new Map([[TOKEN_KEY, "stale-token"]]);
const sessionStorage = {{
  getItem(key) {{ return storage.get(key) ?? null; }},
  setItem(key, value) {{ storage.set(key, value); }},
  removeItem(key) {{ storage.delete(key); }},
}};
const replacements = [];
const window = {{
  location: {{
    hash: "#token=fresh-token",
    pathname: "/",
    search: "?view=sam3d",
  }},
  history: {{
    replaceState(_state, _title, url) {{ replacements.push(url); }},
  }},
}};
const document = {{ title: "VAM-PIP" }};
const app = {{
  token: "",
  managerAuthFailed: true,
  managerAuthFailedToken: "stale-token",
  managerAuthGeneration: 8,
  managerAuthNoticeShown: true,
}};
{capture_token}
captureToken();
process.stdout.write(JSON.stringify({{
  app,
  stored: storage.get(TOKEN_KEY) ?? null,
  replacements,
}}));
"""
        )

        self.assertEqual(result["app"]["token"], "fresh-token")
        self.assertFalse(result["app"]["managerAuthFailed"])
        self.assertEqual(result["app"]["managerAuthFailedToken"], "")
        self.assertEqual(result["app"]["managerAuthGeneration"], 9)
        self.assertFalse(result["app"]["managerAuthNoticeShown"])
        self.assertEqual(result["stored"], "fresh-token")
        self.assertEqual(result["replacements"], ["/?view=sam3d"])

    def test_parallel_invalid_tokens_latch_once_and_short_circuit(self) -> None:
        auth_api = self.auth_api_block()
        result = self.run_javascript(
            f"""
"use strict";
const TOKEN_KEY = "vampip-token";
const INVALID_MANAGER_TOKEN_MESSAGE = "invalid manager token";
const storage = new Map([[TOKEN_KEY, "stale-token"]]);
const sessionStorage = {{
  getItem(key) {{ return storage.get(key) ?? null; }},
  setItem(key, value) {{ storage.set(key, value); }},
  removeItem(key) {{ storage.delete(key); }},
}};
const app = {{
  token: "stale-token",
  managerAuthFailed: false,
  managerAuthFailedToken: "",
  managerAuthGeneration: 3,
  managerAuthNoticeShown: false,
}};
const notices = [];
const stops = [];
const toast = (title, message, kind, options) => {{
  notices.push({{ title, message, kind, options }});
}};
const stopActivityPolling = () => stops.push("activity");
const stopTimelinePolling = () => stops.push("timeline");
const stopSam3dPolling = () => stops.push("sam3d");
const stopSam3dBodyProportionPolling = () => stops.push("body");
let fetchCalls = 0;
const fetch = async () => {{
  fetchCalls += 1;
  return new Response(
    JSON.stringify({{ error: INVALID_MANAGER_TOKEN_MESSAGE, status: 401 }}),
    {{
      status: 401,
      headers: {{ "content-type": "application/json" }},
    }},
  );
}};
{auth_api}
(async () => {{
  const first = api("/api/status").catch((error) => error);
  const second = api("/api/activity").catch((error) => error);
  const errors = await Promise.all([first, second]);
  const blocked = await api("/api/status").catch((error) => error);
  process.stdout.write(JSON.stringify({{
    fetchCalls,
    authFlags: errors.map((error) => error.managerAuthFailure === true),
    blockedAuth: blocked.managerAuthFailure === true,
    blockedStatus: blocked.status,
    app,
    stored: storage.get(TOKEN_KEY) ?? null,
    notices,
    stops,
  }}));
}})();
"""
        )

        self.assertEqual(result["fetchCalls"], 2)
        self.assertEqual(result["authFlags"], [True, True])
        self.assertTrue(result["blockedAuth"])
        self.assertEqual(result["blockedStatus"], 401)
        self.assertTrue(result["app"]["managerAuthFailed"])
        self.assertEqual(result["app"]["managerAuthFailedToken"], "stale-token")
        self.assertEqual(result["app"]["token"], "")
        self.assertIsNone(result["stored"])
        self.assertEqual(len(result["notices"]), 1)
        self.assertEqual(result["notices"][0]["title"], "VAM-PIP access expired")
        self.assertEqual(result["notices"][0]["kind"], "error")
        self.assertTrue(result["notices"][0]["options"]["persistent"])
        self.assertEqual(
            result["stops"],
            ["activity", "timeline", "sam3d", "body"],
        )

    def test_invalid_response_preserves_a_newer_stored_token(self) -> None:
        auth_api = self.auth_api_block()
        result = self.run_javascript(
            f"""
"use strict";
const TOKEN_KEY = "vampip-token";
const INVALID_MANAGER_TOKEN_MESSAGE = "invalid manager token";
const storage = new Map([[TOKEN_KEY, "stale-token"]]);
const sessionStorage = {{
  getItem(key) {{ return storage.get(key) ?? null; }},
  setItem(key, value) {{ storage.set(key, value); }},
  removeItem(key) {{ storage.delete(key); }},
}};
const app = {{
  token: "stale-token",
  managerAuthFailed: false,
  managerAuthFailedToken: "",
  managerAuthGeneration: 1,
  managerAuthNoticeShown: false,
}};
const notices = [];
const toast = (...args) => notices.push(args);
const stopActivityPolling = () => {{}};
const stopTimelinePolling = () => {{}};
const stopSam3dPolling = () => {{}};
const stopSam3dBodyProportionPolling = () => {{}};
let resolveFetch;
const fetch = () => new Promise((resolve) => {{ resolveFetch = resolve; }});
{auth_api}
(async () => {{
  const pending = api("/api/status").catch((error) => error);
  storage.set(TOKEN_KEY, "fresh-token");
  resolveFetch(new Response(
    JSON.stringify({{ error: INVALID_MANAGER_TOKEN_MESSAGE, status: 401 }}),
    {{
      status: 401,
      headers: {{ "content-type": "application/json" }},
    }},
  ));
  const error = await pending;
  process.stdout.write(JSON.stringify({{
    authFailure: error.managerAuthFailure === true,
    app,
    stored: storage.get(TOKEN_KEY) ?? null,
    noticeCount: notices.length,
  }}));
}})();
"""
        )

        self.assertTrue(result["authFailure"])
        self.assertTrue(result["app"]["managerAuthFailed"])
        self.assertEqual(result["app"]["token"], "")
        self.assertEqual(result["stored"], "fresh-token")
        self.assertEqual(result["noticeCount"], 1)

    def test_old_response_cannot_poison_same_token_fragment_recovery(self) -> None:
        capture_token = self.capture_token_block()
        auth_api = self.auth_api_block()
        result = self.run_javascript(
            f"""
"use strict";
const TOKEN_KEY = "vampip-token";
const INVALID_MANAGER_TOKEN_MESSAGE = "invalid manager token";
const storage = new Map([[TOKEN_KEY, "same-token"]]);
const sessionStorage = {{
  getItem(key) {{ return storage.get(key) ?? null; }},
  setItem(key, value) {{ storage.set(key, value); }},
  removeItem(key) {{ storage.delete(key); }},
}};
const window = {{
  location: {{
    hash: "#token=same-token",
    pathname: "/",
    search: "?view=sam3d",
  }},
  history: {{ replaceState() {{}} }},
}};
const document = {{ title: "VAM-PIP" }};
const app = {{
  token: "same-token",
  managerAuthFailed: false,
  managerAuthFailedToken: "",
  managerAuthGeneration: 4,
  managerAuthNoticeShown: false,
}};
const notices = [];
const toast = (...args) => notices.push(args);
const stopActivityPolling = () => {{}};
const stopTimelinePolling = () => {{}};
const stopSam3dPolling = () => {{}};
const stopSam3dBodyProportionPolling = () => {{}};
let resolveFetch;
const fetch = () => new Promise((resolve) => {{ resolveFetch = resolve; }});
{capture_token}
{auth_api}
(async () => {{
  const pending = api("/api/status").catch((error) => error);
  captureToken();
  resolveFetch(new Response(
    JSON.stringify({{ error: INVALID_MANAGER_TOKEN_MESSAGE, status: 401 }}),
    {{
      status: 401,
      headers: {{ "content-type": "application/json" }},
    }},
  ));
  const error = await pending;
  process.stdout.write(JSON.stringify({{
    authFailure: error.managerAuthFailure === true,
    app,
    stored: storage.get(TOKEN_KEY) ?? null,
    noticeCount: notices.length,
  }}));
}})();
"""
        )

        self.assertTrue(result["authFailure"])
        self.assertFalse(result["app"]["managerAuthFailed"])
        self.assertEqual(result["app"]["token"], "same-token")
        self.assertEqual(result["app"]["managerAuthGeneration"], 5)
        self.assertEqual(result["stored"], "same-token")
        self.assertEqual(result["noticeCount"], 0)

    def test_auth_latch_blocks_and_stops_all_poll_schedulers(self) -> None:
        activity = self.javascript_block(
            "function startActivityPolling(",
            "async function loadActivity(",
        )
        sam3d = self.javascript_block(
            "function startSam3dPolling(",
            "function stopSam3dPolling(",
        )
        body = self.javascript_block(
            "function startSam3dBodyProportionPolling(",
            "function stopSam3dBodyProportionPolling(",
        )
        timeline_start = self.javascript_block(
            "function startTimelinePolling(",
            "function stopTimelinePolling(",
        )
        timeline_schedule = self.javascript_block(
            "function scheduleTimelinePoll(",
            "function timelineSnapshotState(",
        )
        result = self.run_javascript(
            f"""
"use strict";
let nextTimer = 1;
const scheduled = [];
const cleared = [];
const window = {{
  setTimeout(callback, delay) {{
    const id = nextTimer++;
    scheduled.push({{ id, callback, delay }});
    return id;
  }},
  clearTimeout(id) {{ cleared.push(id); }},
}};
const app = {{
  managerAuthFailed: true,
  activityTimer: null,
  activityPollFailed: false,
  activityRefreshNeeded: false,
  view: "sam3d",
  sam3dJobPollTimer: null,
  sam3dBodyProportionPollTimer: null,
  sam3dBodyProportionsPendingAction: "apply",
  timelinePollTimer: null,
}};
const SAM3D_POLL_MS = 1000;
const pollSam3dJob = () => {{}};
const pollSam3dBodyProportions = () => {{}};
const loadTimeline = () => {{}};
const selectedTimelineInstance = () => null;
const operationIsBusy = () => false;
const workspaceActionIsActive = () => false;
const setConnection = () => {{}};
let activityCalls = 0;
const loadActivity = async () => {{
  activityCalls += 1;
  app.managerAuthFailed = true;
  throw new Error("invalid manager token");
}};
{activity}
{sam3d}
{body}
{timeline_start}
{timeline_schedule}
startActivityPolling();
startSam3dPolling();
startSam3dBodyProportionPolling();
app.view = "timeline";
startTimelinePolling();
scheduleTimelinePoll();
const blockedScheduleCount = scheduled.length;

app.managerAuthFailed = false;
app.view = "resources";
startActivityPolling();
const tick = scheduled.shift().callback;
(async () => {{
  await tick();
  process.stdout.write(JSON.stringify({{
    blockedScheduleCount,
    totalSchedules: scheduled.length + 1,
    activityCalls,
    activityTimer: app.activityTimer,
    authFailed: app.managerAuthFailed,
    cleared,
  }}));
}})();
"""
        )

        self.assertEqual(result["blockedScheduleCount"], 0)
        self.assertEqual(result["totalSchedules"], 1)
        self.assertEqual(result["activityCalls"], 1)
        self.assertIsNone(result["activityTimer"])
        self.assertTrue(result["authFailed"])

    def test_raw_sam_api_and_generic_toasts_share_auth_handling(self) -> None:
        raw_api = self.javascript_block(
            "async function sam3dRawApi(",
            "function sam3dCapabilitySet(",
        )
        toast = self.javascript_block(
            "function toast(",
            "function setButtonBusy(",
        )
        update_toast = self.javascript_block(
            "function updateToast(",
            "function toast(",
        )

        self.assertIn("managerAuthBlockedError()", raw_api)
        self.assertIn("const requestToken = app.token;", raw_api)
        self.assertIn("const requestAuthGeneration", raw_api)
        self.assertIn("handleManagerAuthFailure(", raw_api)
        self.assertIn("INVALID_MANAGER_TOKEN_MESSAGE", toast)
        self.assertIn("INVALID_MANAGER_TOKEN_MESSAGE", update_toast)

        result = self.run_javascript(
            f"""
"use strict";
const INVALID_MANAGER_TOKEN_MESSAGE = "invalid manager token";
let createCalls = 0;
const dismissed = [];
const dismissToast = (item) => dismissed.push(item.id);
const createElement = () => {{
  createCalls += 1;
  return {{}};
}};
const item = {{ id: "busy-toast" }};
{update_toast}
{toast}
const result = toast(
  "Could not reach VAM-PIP",
  INVALID_MANAGER_TOKEN_MESSAGE,
  "error",
);
updateToast(
  item,
  "SAM 3D worker unavailable",
  INVALID_MANAGER_TOKEN_MESSAGE,
  "error",
);
process.stdout.write(JSON.stringify({{
  result,
  createCalls,
  dismissed,
}}));
"""
        )
        self.assertIsNone(result["result"])
        self.assertEqual(result["createCalls"], 0)
        self.assertEqual(result["dismissed"], ["busy-toast"])


if __name__ == "__main__":
    unittest.main()

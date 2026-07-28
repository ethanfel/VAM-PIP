# VAM-PIP VaM bridge

This is a deliberately small VaM **session plugin**. The external VAM-PIP
manager enables packages and resolves dependencies; this bridge only asks VaM
to rescan packages on its Unity main thread.

## Install

Copy this directory to:

```text
<VaM>/Custom/Scripts/VAMPip/Bridge/
```

In VaM, open **Session Plugins**, add
`Custom/Scripts/VAMPip/Bridge/VAMPipBridge.cslist`, and save it in the default
session-plugin preset. Keep the bridge enabled in every VAM-PIP profile.

The bridge is compatible with VaM 1.22's Unity 2018.1 / legacy Mono runtime and
uses C# 6 or older syntax.

## Mailbox protocol

VaM sees the mailbox at:

```text
Saves\PluginData\VAMPip\Bridge
```

The corresponding Linux path is:

```text
<VaM>/Saves/PluginData/VAMPip/Bridge
```

After all package enables have completed, the manager atomically replaces
`request.json` with:

```json
{
  "protocol": 1,
  "requestId": "a-new-unique-id",
  "command": "rescan",
  "createdAtUtc": "2026-07-28T12:00:00.0000000Z",
  "browserAssist": "auto"
}
```

`browserAssist` may be:

- `auto`: use the installed BrowserAssist refresh API when available, otherwise
  fall back to VaM's core package rescan.
- `off`: use VaM's core package rescan directly.

The bridge writes `status.json`:

```json
{
  "protocol": 1,
  "bridgeVersion": "0.1.0",
  "instanceId": "id-created-when-the-plugin-started",
  "requestId": "a-new-unique-id",
  "lastCompletedRequestId": "a-new-unique-id",
  "state": "ok",
  "ok": true,
  "updatedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "startedAtUtc": "2026-07-28T12:00:01.0000000Z",
  "finishedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "backend": "browserassist",
  "message": "VaM and BrowserAssist package data were refreshed."
}
```

Valid states are `ready`, `deferred-loading`, `rescanning`, `ok`, and `error`.
Status writes are not guaranteed to be atomic, so readers should retry a
transient JSON parse failure.

Requests are a latest-desired-state mailbox: overwriting a queued request
coalesces several package operations into one rescan. IDs are processed once
per plugin session. An `ok` ID is recovered after a plugin restart; an
interrupted or failed request is retried once after restart.

## Safety contract

- Write `request.json` only after all same-filesystem
  `.var.vampip-disabled -> .var` renames and manager state updates complete.
- Live enabling is supported. Never disable or rename an active `.var` away
  while VaM is running; defer expiry and disable operations until VaM exits.
- The bridge accepts no paths, package names, deletes, shell commands, or
  network requests.
- Rescans are synchronous and may briefly freeze VaM. Requests are deferred
  while a scene is loading, coalesced, and rate-limited to one every five
  seconds.
- Keep the mailbox directory private to the current Linux user and expose any
  manager web interface only on `127.0.0.1`.

BrowserAssist integration is best-effort and currently targets its public
`JayJayWon.VARPackageManifest.RescanPackages()` method. VaM's core
`SuperController.singleton.RescanPackages()` remains the fallback. The bridge
never invokes BrowserAssist's expensive full-resource rescan.

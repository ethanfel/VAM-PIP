# VAM-PIP VaM bridge

This is a deliberately small VaM **session plugin**. The external VAM-PIP
manager enables packages and resolves dependencies. The bridge asks VaM to
rescan packages, publishes bounded atom and Person rosters, and can load an
allowlisted scene, apply one allowlisted Person preset, add one Person, or
select one existing atom on VaM's Unity main thread.

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
`request.json`. A package rescan request is:

```json
{
  "protocol": 2,
  "requestId": "a-new-unique-id",
  "command": "rescan",
  "createdAtUtc": "2026-07-28T12:00:00.0000000Z",
  "browserAssist": "auto"
}
```

`browserAssist` may be:

- `auto`: use VaM's core package rescan and remind the caller that BrowserAssist
  may need to be reloaded before it sees newly enabled packages.
- `off`: use the same core package rescan without that reminder.

VaM's loose-script sandbox blocks reflection, and BrowserAssist does not expose
a sandbox-safe rescan action to other plugins.

A Person preset request is:

```json
{
  "protocol": 2,
  "requestId": "a-new-unique-id",
  "command": "applyPersonPreset",
  "createdAtUtc": "2026-07-28T12:00:00.0000000Z",
  "targetUid": "Person",
  "presetKind": "hair",
  "resourceRef": "creator.package.1:/Custom/Atom/Person/Hair/Preset_Long.vap",
  "rescan": true,
  "merge": false
}
```

Each kind has one fixed VaM directory and storable:

| `presetKind` | Required member prefix | VaM storable |
| --- | --- | --- |
| `appearance` | `Custom/Atom/Person/Appearance/` | `AppearancePresets` |
| `animation` | `Custom/Atom/Person/AnimationPresets/` | `AnimationPresets` |
| `breastPhysics` | `Custom/Atom/Person/BreastPhysics/` | `FemaleBreastPhysicsPresets` |
| `clothing` | `Custom/Atom/Person/Clothing/` | `ClothingPresets` |
| `general` | `Custom/Atom/Person/General/` | `Preset` |
| `glutePhysics` | `Custom/Atom/Person/GlutePhysics/` | `FemaleGlutePhysicsPresets` |
| `hair` | `Custom/Atom/Person/Hair/` | `HairPresets` |
| `morphs` | `Custom/Atom/Person/Morphs/` | `MorphPresets` |
| `plugins` | `Custom/Atom/Person/Plugins/` | `PluginPresets` |
| `pose` | `Custom/Atom/Person/Pose/` | `PosePresets` |
| `skin` | `Custom/Atom/Person/Skin/` | `SkinPresets` |

`resourceRef` must be either below the kind's local prefix or a VaM package
reference whose member is below it. Its basename must start with `Preset_` and
end in `.vap`. The bridge checks it with `FileManagerSecure.FileExists`, sets
only the mapped storable's `presetBrowsePath`, and calls `LoadPreset` or
`MergeLoadPreset`. With `rescan: true`, the package rescan completes first.

Person creation and selection are separate bounded commands:

```json
{"protocol": 2, "requestId": "unique-1", "command": "addPerson", "targetUid": "Person#2"}
```

```json
{"protocol": 2, "requestId": "unique-2", "command": "selectPerson", "targetUid": "Person#2"}
```

`addPerson` is idempotent: an existing Person with that exact UID succeeds
without adding another atom; a non-Person collision is an error. Creation runs
as a coroutine and is not complete until VaM exposes the new Person.
`selectPerson` selects the target's main controller and is also idempotent.
The more general alias selects any existing roster atom by exact UID:

```json
{"protocol": 2, "requestId": "unique-3", "command": "selectAtom", "targetUid": "InvisibleLight#1"}
```

It does not expose arbitrary storables or actions.

Scene loading accepts only a local or packaged member below `Saves/scene/`
whose name ends in `.json`:

```json
{
  "protocol": 2,
  "requestId": "unique-4",
  "command": "loadScene",
  "resourceRef": "creator.scenes.1:/Saves/scene/Example.json",
  "rescan": true,
  "merge": false
}
```

The bridge optionally rescans, verifies the scene through
`FileManagerSecure.FileExists`, normalizes the resource reference, and calls
VaM's `Load` or `LoadMerge`. It remains busy until VaM reports that loading
finished, with a 120-second upper bound. A full load replaces the current
scene and can discard unsaved scene work; the external client must require a
clear confirmation before sending it. Merge is also a large, non-idempotent
scene mutation.

The bridge writes `status.json`:

```json
{
  "protocol": 2,
  "bridgeVersion": "0.3.0",
  "instanceId": "id-created-when-the-plugin-started",
  "requestId": "a-new-unique-id",
  "lastCompletedRequestId": "a-new-unique-id",
  "state": "ok",
  "ok": true,
  "updatedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "startedAtUtc": "2026-07-28T12:00:01.0000000Z",
  "finishedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "backend": "vam",
  "message": "Core VaM package rescan completed. Reload BrowserAssist if it must see newly enabled packages.",
  "capabilities": [
    "atom-roster",
    "atom-select",
    "scene-load",
    "person-roster",
    "person-preset-apply",
    "person-preset-appearance",
    "person-preset-animation",
    "person-preset-breast-physics",
    "person-preset-clothing",
    "person-preset-general",
    "person-preset-glute-physics",
    "person-preset-hair",
    "person-preset-morphs",
    "person-preset-plugins",
    "person-preset-pose",
    "person-preset-skin",
    "person-add",
    "person-select"
  ]
}
```

Valid request stages are `queued`, `deferred-loading`, `rescanning`,
`applying`, `adding`, `selecting`, `loading-scene`, `ok`, and `error`.
Status writes are not guaranteed to be atomic, so readers should retry a
transient JSON parse failure.

The mailbox holds one request. Pending rescan-only requests may safely coalesce
to the newest rescan. An overwrite involving any atom or resource action is
rejected as busy because those actions are ordered and must never coalesce.
Callers must wait until the matching status is `ok` or `error` before
submitting another action. Full preset loads and add/select commands are safe
to retry. Preset merges and scene merges are non-idempotent and are processed
only once per request ID in a plugin session. An `ok` ID is recovered after a
plugin restart; an interrupted or failed request is eligible to run after a
restart, so a client must reconcile state before restarting around a merge.

The bridge refreshes `scene.json` once per second:

```json
{
  "protocol": 2,
  "bridgeVersion": "0.3.0",
  "instanceId": "id-created-when-the-plugin-started",
  "updatedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "loading": false,
  "selectedUid": "Person",
  "atoms": [
    {"uid": "Person", "type": "Person", "selected": true},
    {"uid": "InvisibleLight#1", "type": "InvisibleLight", "selected": false}
  ],
  "persons": [
    {"uid": "Person", "selected": true},
    {"uid": "Person#2", "selected": false}
  ],
  "capabilities": [
    "atom-roster",
    "atom-select",
    "scene-load",
    "person-roster",
    "person-preset-apply",
    "person-preset-appearance",
    "person-preset-animation",
    "person-preset-breast-physics",
    "person-preset-clothing",
    "person-preset-general",
    "person-preset-glute-physics",
    "person-preset-hair",
    "person-preset-morphs",
    "person-preset-plugins",
    "person-preset-pose",
    "person-preset-skin",
    "person-add",
    "person-select"
  ]
}
```

The heartbeat lets the manager distinguish a live bridge from a stale roster.
`person-preset-apply` is retained as a compatibility marker. Clients must use
the matching `person-preset-<kind>` capability before exposing a specific
preset action; an older bridge that advertises only the generic marker does
not establish support for every preset kind.

## Safety contract

- Write `request.json` only after all same-filesystem
  `.var.vampip-disabled -> .var` renames and manager state updates complete.
- Live enabling is supported. Never disable or rename an active `.var` away
  while VaM is running; defer expiry and disable operations until VaM exits.
- The bridge accepts no filesystem paths, deletes, shell commands, network
  requests, arbitrary storable IDs, or arbitrary action names. Resource inputs
  are tightly constrained VaM `.vap` references in the mapped Person preset
  directories or `.json` references below `Saves/scene/`.
- Rescans are synchronous and may briefly freeze VaM. Requests are deferred
  while a scene is loading and rate-limited to one every five seconds.
- `loadScene` is intentionally a separate high-impact capability. Replacing a
  scene needs an external unsaved-work confirmation; merging needs an equally
  explicit warning that retrying can duplicate atoms.
- Keep the mailbox directory private to the current Linux user and expose any
  manager web interface only on `127.0.0.1`.

The bridge calls VaM's public `SuperController` and `FileManagerSecure` APIs.
It does not access BrowserAssist internals: those require reflection, which
VaM prohibits for loose plugins. Reload BrowserAssist, or restart VaM, when
BrowserAssist must rebuild its own package/resource manifest.

The bridge also avoids runtime type inspection in error messages. On VaM's
legacy Mono runtime, even `Exception.GetType().Name` emits a reference through
the prohibited reflection namespace.

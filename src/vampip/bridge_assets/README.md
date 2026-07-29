# VAM-PIP VaM bridge

This is a deliberately small VaM **session plugin**. The external VAM-PIP
manager enables packages and resolves dependencies. The bridge asks VaM to
rescan packages, publishes bounded atom and Person rosters, and can load an
allowlisted scene or SubScene, apply one allowlisted Person or generic atom
preset, safely load one Custom Unity Asset, add one allowlisted native atom,
wear or remove one exact clothing item, or select one existing atom on VaM's
Unity main thread.

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

An individual clothing request is:

```json
{
  "protocol": 2,
  "requestId": "unique-clothing-1",
  "command": "setPersonClothingResource",
  "targetUid": "Person",
  "resourceRef": "creator.clothes.3:/Custom/Clothing/Female/Dress.vam",
  "desiredState": "worn",
  "revision": "0123456789abcdef0123456789abcdef",
  "rescan": true
}
```

`desiredState` must be exactly `worn` or `removed`; this is a desired-state
operation, not a toggle. The revision is the 32-hex value published for that
Person's clothing snapshot in `scene.json`. The manager derives `resourceRef`
from a numeric catalogue ID. For packaged clothing it remains the exact
package-qualified
`creator.package.version:/Custom/Clothing/Female-or-Male/item.vam`
identity—not BrowserAssist's clothing UID, a display name, or a client-supplied
path. Local references below the same female/male directories are also valid.

The bridge independently requires an exact `.vam` reference below
`Custom/Clothing/Female/` or `Custom/Clothing/Male/`, an exact Person target,
the same native `geometry` instance, and a current revision. It rejects wear
when the resource category is incompatible with the Person's current gender,
and rejects a state change when the item is locked. A rescan, when needed,
finishes before the checks and assignment.

One active, unlocked Hair layer can be removed with the private token from the
same revision of `scene.json`:

```json
{
  "protocol": 2,
  "requestId": "unique-hair-1",
  "command": "setPersonHairItem",
  "targetUid": "Person",
  "actionToken": "abcdef0123456789abcdef0123456789",
  "desiredState": "removed",
  "revision": "fedcba9876543210fedcba9876543210"
}
```

Only `removed` is accepted. The manager maps its public revision-scoped item
key to this private token; neither the token nor any Hair UID or runtime path
is exposed through the public API. The bridge revalidates the exact Person,
geometry, revision, active `DAZHairGroup` object, unique token, and current
lock state before calling VaM's exact-object `SetActiveHairItem` overload.

Generic non-Person atom creation uses an exact, case-sensitive static allowlist
of atom types verified against VaM 1.22. Packaged/custom atom types remain
browse-only. A request is:

```json
{
  "protocol": 2,
  "requestId": "unique-4",
  "command": "addAtom",
  "atomType": "WindowCamera",
  "targetUid": "External Camera"
}
```

`addAtom` is idempotent. An existing atom succeeds only when both its UID and
type match; a same-UID atom of another type is rejected.

A generic atom preset uses that same type allowlist:

```json
{
  "protocol": 2,
  "requestId": "unique-5",
  "command": "applyAtomPreset",
  "targetUid": "External Camera",
  "atomType": "WindowCamera",
  "resourceRef": "creator.cameras.1:/Custom/Atom/WindowCamera/Preset_Framing.vap",
  "rescan": true,
  "merge": false,
  "createIfMissing": true
}
```

The reference must be below `Custom/Atom/<atomType>/`, its basename must start
with `Preset_`, and it must end in `.vap`. The bridge verifies the target's
exact type and uses only the fixed `Preset` storable, `presetBrowsePath`, and
`LoadPreset`/`MergeLoadPreset` actions. The modes are strict and mutually
exclusive: with `createIfMissing: false`, the correctly typed target must
already exist; with `createIfMissing: true`, the UID must be absent when the
request executes. An existing UID—even with the requested type—makes create
mode fail without applying the preset. Successful creation and application
remain one single-flight request. `merge` and `createIfMissing` cannot both be
true.

A SubScene load is similarly bounded:

```json
{
  "protocol": 2,
  "requestId": "unique-6",
  "command": "loadSubscene",
  "targetUid": "Apartment",
  "resourceRef": "creator.rooms.2:/Custom/SubScene/Apartment.json",
  "rescan": true,
  "createIfMissing": true
}
```

Only local or packaged `.json` members below `Custom/SubScene/` are accepted.
The target must be a `SubScene` atom. The bridge uses only its fixed `SubScene`
storable and `browsePath`. With `createIfMissing: false`, the SubScene atom must
already exist; with `createIfMissing: true`, its UID must be absent at
execution. An existing UID fails create mode without loading. Atom creation,
generic preset loading, and SubScene loading have a 120-second upper bound.

Generic atom presets and SubScenes can themselves contain plugin
configurations or plugin-bearing atoms. The bridge validates the resource
identity and fixed VaM API surface, but cannot inspect or approve the semantic
contents of a `.vap` or SubScene `.json`. The external client must surface that
risk and require confirmation for unknown or untrusted content.

A Custom Unity Asset load uses only a fixed `CustomUnityAsset` target and
VaM's native `asset` storable:

```json
{
  "protocol": 2,
  "requestId": "unique-7",
  "command": "loadCustomUnityAsset",
  "targetUid": "Apartment asset",
  "resourceRef": "creator.rooms.2:/Custom/Assets/Apartment.assetbundle",
  "rescan": true,
  "createIfMissing": true
}
```

Only local or packaged `.assetbundle` and legacy `.scene` members below
`Custom/Assets/` are accepted. Target mode is strict: with
`createIfMissing: false`, the exact `CustomUnityAsset` must exist; with
`createIfMissing: true`, the UID must be absent at execution.

The request intentionally has no DLL, asset-name, light-map, probe, or canvas
options. The bridge resolves and normalizes the catalog-selected bundle, sets
the loader's `assetName` to its `None` sentinel, then sets and verifies
`loadDll: false` immediately before assigning `assetUrl`. It checks the flag
throughout the bounded load and makes a best-effort clear if the flag becomes
true. VaM samples `loadDll` during the URL callback, so setting it false later
would be too late. A DLL that has already executed in VaM's process cannot be
unloaded; the bridge can prevent a new bridge-initiated DLL load, not undo an
earlier VaM or plugin load.

After the bundle is ready, the bridge excludes blank and `None` entries. If
there is exactly one eligible scene or prefab, it selects it and waits for
VaM's native `isAssetLoaded` completion flag. If there are several, it leaves
the loader at `None`, completes successfully, and publishes a bounded picker
in `scene.json`. It does not assume VaM's first scene-first bundle entry is the
user's intended asset.

A picker selection is a separate command:

```json
{
  "protocol": 2,
  "requestId": "unique-8",
  "command": "selectCustomUnityAssetChoice",
  "targetUid": "Apartment asset",
  "choiceIndex": 7,
  "choiceToken": "0123456789abcdef0123456789abcdef"
}
```

The index is VaM's original chooser index, not the row's position in the
published subset. The 32-hex token binds the exact atom and loader instances,
the current raw bundle URL and choice generation, and the exact subset that
was published. It rotates when any of those change, but not merely when the
selected index changes. The bridge rechecks the live generation, requires
that the original index was actually published, derives the raw choice from
VaM rather than accepting a path or name from the client, requires
`loadDll: false`, and waits for `isAssetLoaded`. Stale tokens fail without
selecting anything.

Each CUA roster entry reports the actual `loadDll` flag, native ready state,
eligible `choiceCount`, original `selectedIndex`, token, and sanitized
`{index,label}` choices. Labels are limited to 256 characters. Publication is
limited to 128 choices per CUA atom and 512 across the roster; the total count
and `choicesTruncated` reveal omitted choices. The raw `assetUrl` is never
published.

Scene loading accepts only a local or packaged member below `Saves/scene/`
whose name ends in `.json`:

```json
{
  "protocol": 2,
  "requestId": "unique-9",
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
  "bridgeVersion": "0.8.1",
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
    "atom-add",
    "atom-preset-apply",
    "subscene-load",
    "custom-unity-asset-load",
    "custom-unity-asset-choice",
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
    "person-clothing-item-toggle",
    "person-hair-roster",
    "person-hair-item-toggle",
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
submitting another action. Add/select commands are safe to retry. Preset
merges and scene merges are non-idempotent and are processed only once per
request ID in a plugin session. Full preset and SubScene reloads are normally
state-setting operations, but their semantic contents can include plugins; a
client must not assume they are harmless. An `ok` ID is recovered after a
plugin restart; an interrupted or failed request is eligible to run after a
restart, so a client must reconcile state before restarting around a merge.

The bridge refreshes `scene.json` once per second:

```json
{
  "protocol": 2,
  "bridgeVersion": "0.8.1",
  "instanceId": "id-created-when-the-plugin-started",
  "updatedAtUtc": "2026-07-28T12:00:02.0000000Z",
  "loading": false,
  "selectedUid": "Person",
  "atoms": [
    {"uid": "Person", "type": "Person", "selected": true},
    {"uid": "InvisibleLight#1", "type": "InvisibleLight", "selected": false},
    {
      "uid": "Apartment asset",
      "type": "CustomUnityAsset",
      "selected": false,
      "cua": {
        "loadDll": false,
        "ready": false,
        "isAssetLoaded": false,
        "choiceToken": "0123456789abcdef0123456789abcdef",
        "choiceCount": 2,
        "selectedIndex": 0,
        "choices": [
          {"index": 1, "label": "assets/room.prefab"},
          {"index": 7, "label": "assets/props/chair.prefab"}
        ],
        "choicesTruncated": false
      }
    }
  ],
  "persons": [
    {
      "uid": "Person",
      "selected": true,
      "clothing": {
        "ready": true,
        "gender": "Female",
        "activeResourceRefs": [
          "creator.clothes.3:/Custom/Clothing/Female/Dress.vam"
        ],
        "lockedResourceRefs": [],
        "activeItems": [
          {
            "displayName": "Dress",
            "tags": ["Dresses"],
            "locked": false,
            "resourceRef": "creator.clothes.3:/Custom/Clothing/Female/Dress.vam"
          },
          {
            "displayName": "Built-in shoes",
            "tags": ["Shoes"],
            "locked": false,
            "resourceRef": ""
          }
        ],
        "activeCount": 2,
        "lockedCount": 0,
        "truncated": false,
        "revision": "0123456789abcdef0123456789abcdef"
      },
      "hair": {
        "ready": true,
        "activeCount": 2,
        "lockedCount": 0,
        "truncated": false,
        "revision": "fedcba9876543210fedcba9876543210",
        "items": [
          {
            "displayName": "Long Hair",
            "tags": ["Long"],
            "locked": false,
            "simulated": true,
            "actionToken": "abcdef0123456789abcdef0123456789"
          },
          {
            "displayName": "Side Bangs",
            "tags": ["Bangs"],
            "locked": false,
            "simulated": false,
            "actionToken": "0123456789abcdef0123456789abcdef"
          }
        ]
      }
    },
    {"uid": "Person#2", "selected": false}
  ],
  "capabilities": [
    "atom-roster",
    "atom-select",
    "atom-add",
    "atom-preset-apply",
    "subscene-load",
    "custom-unity-asset-load",
    "custom-unity-asset-choice",
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
    "person-clothing-item-toggle",
    "person-hair-roster",
    "person-hair-item-toggle",
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

Clothing publication is bounded to 256 presentation entries per Person and
1,024 across the roster. Every published active item has a sanitized display
name, at most 32 sanitized tags, and its lock state. Its private
`resourceRef` is empty for built-in or otherwise opaque entries. `activeCount`,
`lockedCount`, and `truncated` make omissions visible. The external manager
strips every raw reference from its public scene API after joining validated
references to catalogue rows. Opaque rows remain visible but non-actionable.
If `truncated` is true, an unpublished item is unknown, not evidence that it
was removed.

The clothing revision is bound to the exact Person and `geometry` instances
and their semantic clothing, lock, and gender state. A stale write fails before
VaM changes the clothing boolean.

Hair publication is bounded to 128 active layers per Person and 512 across the
roster. It exposes sanitized labels and tags, lock state, whether each layer
has a `HairSimControl`, and a private random action token; it publishes no
runtime path, package UID, internal UID, or writable storable. The manager
strips the private token from public scene and Hair APIs. Its separate revision
and tokens rotate when the active layer roster or published subset changes.
The only write is removal of one exact active, unlocked layer using its current
revision and unique private token.

## Safety contract

- Write `request.json` only after all same-filesystem
  `.var.vampip-disabled -> .var` renames and manager state updates complete.
- Live enabling is supported. Never disable or rename an active `.var` away
  while VaM is running; defer expiry and disable operations until VaM exits.
- The bridge accepts no filesystem paths, deletes, shell commands, network
  requests, arbitrary storable IDs, or arbitrary action names. Resource inputs
  are tightly constrained VaM `.vap` references in mapped Person preset
  directories or `Custom/Atom/<allowlisted-type>/`, and `.json` references
  below `Custom/SubScene/` or `Saves/scene/`. CUA inputs are only
  `.assetbundle` or `.scene` references below `Custom/Assets/`. Clothing
  inputs are exact `.vam` references below `Custom/Clothing/Female/` or
  `Custom/Clothing/Male/`.
- Clothing changes require a current, target-specific snapshot revision.
  Gender-incompatible wear and locked changes fail closed. The external
  workspace also disables an action when bounded-publication truncation leaves
  that item's current state unknown.
- Hair removal requires the current target-specific Hair revision and a unique
  private action token from a complete published roster. Stale, truncated,
  locked, inactive, missing, and ambiguous targets fail closed.
- The generic atom and SubScene resource containers can include plugin
  configurations. Path/type validation does not establish that their semantic
  contents are trusted or side-effect free.
- CUA loading is a critical operation even with DLL loading forced off. Unity
  content can instantiate components already available in VaM and can expose
  canvases or other active objects. The external client must require explicit
  confirmation for untrusted bundles. Never represent `loadDll: false` as a
  guarantee that the bundle is inert.
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

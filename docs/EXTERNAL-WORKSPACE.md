# External VaM workspace

The long-term VAM-PIP UI is not a remote copy of one VaM panel. It is a
capability-driven companion for the parts of VaM that are useful on a desktop
and have a stable, bounded API.

There are three different levels:

- **browse**: searchable from BrowserAssist's last-good catalogue with VaM
  closed;
- **load**: VAM-PIP can resolve the selected catalogue ID, enable its package
  closure, rescan, and ask VaM to perform one allowlisted operation;
- **edit live**: the bridge must publish current runtime state and a typed
  control schema before the browser can safely change individual values.

The UI should show these levels explicitly. “Browse only” is a real
capability, not an error.

## Asset and action map

| Workspace | Catalogue data in this installation | Exact VaM operation | Risk and implementation status |
| --- | ---: | --- | --- |
| Scenes | 5,376 `Scene` entries | `SuperController.Load` or `LoadMerge` on a validated `Saves/scene/*.json` reference | Bounded and useful now. Replace needs a strong unsaved-work warning; merge is still a large scene mutation. |
| SubScenes | 2,549 `SubScenes` entries | Target an existing `SubScene` or create one only while its requested UID remains unused, then set `SubScene.browsePath` | Implemented for existing and newly created targets. Loading requires critical confirmation because a SubScene can contain plugin atoms. Optional placement remains in VaM. |
| Atom presets | 2,513 `Preset Atom` entries across multiple atom types | Target an existing exact type or create it only while its requested UID remains unused, then use its `Preset` manager with replace/merge | Implemented when the catalogue-derived type is in the shared native allowlist. Other types stay browse-only. All loads require critical confirmation because generic presets can contain `PluginManager` state. |
| Custom Unity Assets | 4,800 `Custom Unity Assets` entries | Target or create `CustomUnityAsset`, then set `CustomUnityAssetLoader.assetUrl` | Feasible, but the loader also exposes asset choice, light maps/probes, canvases, and DLL loading. DLL loading must never be silently enabled. |
| Plugins | 12,933 indexed files | Merge a synthetic PluginManager preset into a chosen atom, Scene Plugins, or Session Plugins | Feasible but executes code. The catalogue contains helper `.cs` files as well as entry `.cslist` files, so entry-point classification and explicit confirmation are required first. |
| Clothing | 9,863 raw female/male items and 30,914 item-style presets | Toggle the target Person's exact `geometry` clothing boolean; item styles use that item's preset manager | Feasible after preserving BrowserAssist's per-version clothing UID metadata and publishing worn state. |
| Person presets and controls | Appearance, hair, skin, clothing, morphs, pose, physics, animation, general, and Person-plugin presets | Use static preset-kind to path/storable mappings; later publish typed live controls | The broad preset pipeline is the first Person module. See [PERSON-WORKSPACE.md](PERSON-WORKSPACE.md). |

Counts come from the current last-good BrowserAssist import and are not
hard-coded product limits.

## Safe command families

The bridge should grow as a registry of small commands, not as a generic RPC
layer:

```text
scene-load
atom-list / atom-select / atom-add
atom-preset-apply
subscene-load
cua-load
person-preset-apply
person-item-toggle
typed-control-read / typed-control-write
```

Each resource command starts from a numeric VAM-PIP catalogue ID. The manager,
not JavaScript, derives the resource type, exact package version, archive
member, dependencies, and full VaM reference. The bridge independently checks
the expected directory, extension, target atom type, and advertised
capability.

Commands that create atoms carry a caller-chosen UID. If an atom of the
expected type already has that UID, the retry succeeds as “already present”;
if another type owns it, the command fails. That gives creation an idempotent
contract without a general durable command queue.

## Live scene model

File metadata alone cannot drive the whole VaM UI. A later bridge snapshot
should expose a bounded live scene document:

```text
scene revision
  atoms: uid, type, selected, capabilities
    resource targets: active clothing/hair/CUA/subscene
    controls: stable id, kind, value, bounds/choices, revision
```

Writes must include the atom UID, stable control ID, and revision observed by
the client. Stale writes are rejected and the UI refreshes. This is suitable
for morph sliders, transforms, material choices, CUA asset selection, and
curated physics controls. It is not permission to enumerate and invoke every
JSONStorable action.

## Operations that need extra friction

- Replacing a scene can discard unsaved work.
- Appearance and General presets can change far more than their names imply.
- Pose presets can change controllers, locks, and physics.
- Person Plugin presets, generic atom presets, SubScenes, and raw plugins can
  execute third-party code.
- CUA bundles may offer DLL loading.
- Removing or renaming atoms can break references from plugins and other
  atoms.
- Saving or overwriting scenes and presets mutates user content.

These operations need precise summaries and explicit confirmation at the
point of action. Delete, rename, arbitrary storable mutation, arbitrary plugin
actions, and user-supplied filesystem paths remain outside the generic
protocol.

The API independently enforces confirmation for Scene replacement and for
critical General/Person Plugin presets, non-Person atom presets, and
SubScenes; the browser dialog is not the only guard.
Create-new requests also fail if another atom claims the requested UID before
the bridge executes them, so that mode cannot silently become replacement.

## Practical build order

1. Completed: global category registry and honest browse/load/live labels.
2. Completed: Scene replace/merge plus the broad Person-preset module.
3. Completed: all-atom roster/select and idempotent Person creation.
4. Completed: typed native-atom creation, atom presets, and SubScenes.
5. Next: CUA loading with DLL loading off by default and typed loader options.
6. Clothing and other item-level state.
7. Revisioned live controls.
8. Explicit code-loading and save/export workflows.

This order produces useful external control early while preserving a protocol
that can be reasoned about and tested.

# External Person workspace

VAM-PIP treats external Person editing as two related systems:

1. an offline catalogue, which can search resources even while VaM is closed;
2. a narrow live bridge, which performs allowlisted operations inside VaM.

The catalogue is not a live model of a Person. BrowserAssist describes files
and packages, while VaM owns the atoms, storables, morph values, selected
clothing, and runtime material state. The web UI therefore labels each
category as browseable, loadable, or live-editable instead of assuming that
every resource can be applied in the same way.

## Capability map

| Area | Offline catalogue | Safe live operation | Current direction |
| --- | --- | --- | --- |
| Person roster | No | List and select existing Person atoms | Bridge scene snapshot |
| Add Person | No | Add with a caller-chosen unique ID; repeating the same request is harmless | Allowlisted bridge command |
| Appearance / look | `Preset Appearance` | Replace or merge through `AppearancePresets` | Generic preset pipeline |
| Animation | `Preset Animation` | Replace or merge through `AnimationPresets` | Generic preset pipeline |
| Breast physics | `Preset Breast Physics` | Replace or merge through `FemaleBreastPhysicsPresets` | Generic preset pipeline |
| Clothing outfits | `Preset Clothing` | Replace or merge through `ClothingPresets` | Generic preset pipeline |
| General | `Preset General` | Replace or merge through `Preset` | Generic preset pipeline; broad side effects are called out |
| Glute physics | `Preset Glute Physics` | Replace or merge through `FemaleGlutePhysicsPresets` | Generic preset pipeline |
| Hair presets | `Preset Hair` | Replace or merge through `HairPresets` | Generic preset pipeline |
| Morph presets | `Preset Morphs` | Replace or merge through `MorphPresets` | Generic preset pipeline |
| Person plugins | `Preset Plugins` | Replace or merge through `PluginPresets` | Generic preset pipeline; scripts may have their own dependencies |
| Pose | `Preset Pose` | Replace or merge through `PosePresets` | Generic preset pipeline |
| Skin | `Preset Skin` | Replace or merge through `SkinPresets` | Generic preset pipeline |
| Individual clothing | `Clothing (Female)` and `Clothing (Male)` | Toggle `geometry`'s exact `clothing:<resource>` boolean | Requires per-version clothing UID metadata in VAM-PIP's catalogue |
| Clothing item styles | `Clothing Item Presets` | Load an active item's own preset manager | Requires a reliable clothing-item relationship and separate material/physics options |
| Worn hair and clothing | Not represented reliably by the offline catalogue | Publish bounded state from the target Person's `geometry` | Later live-state schema |
| Individual morph sliders | Preset files only | Publish UID, label, region, current value, and min/max; set a bounded numeric value | Later revisioned live-control schema |
| Materials, pose, and physics controls | Preset files only | Publish an allowlisted typed control schema | Later; do not expose arbitrary storables |

Preset loading uses VaM's own preset managers. VAM-PIP sets the validated
`presetBrowsePath`, temporarily disables load-on-selection, invokes
`LoadPreset` or `MergeLoadPreset`, and restores the previous setting. The
manager resolves a numeric catalogue ID to an exact installed local or
package-qualified resource; the browser never supplies a path or storable
name.

## Why there is no generic “call VaM” endpoint

An endpoint accepting arbitrary atom IDs, storable IDs, parameters, or action
names would be easy to build but difficult to secure and impossible to keep
stable across old VaM plugins. The bridge instead advertises small
capabilities and validates every command against static mappings. New live
controls should follow the same pattern:

- publish typed data with explicit bounds;
- include a scene or control revision to reject stale writes;
- accept stable IDs, never array positions;
- make retries idempotent where possible;
- serialize mutations and return their terminal status;
- restore temporary VaM settings in `finally` blocks;
- never accept an operating-system path, command, or reflection target.

Deletion, atom renaming, arbitrary plugin calls, and unrestricted JSONStorable
mutation are deliberately outside the initial external workspace.

## Expansion order

The useful order is:

1. broad preset browsing and loading plus Person add/select;
2. preserve BrowserAssist clothing metadata and add individual clothing
   wear/remove with live worn-state reporting;
3. expose individual morphs through a bounded, revisioned schema;
4. add curated material, pose, and physics controls based on observed VaM
   storables;
5. add save/export workflows only after their overwrite and screenshot
   semantics are explicit.

This keeps the first workspace broadly useful without locking the protocol to
the shape of one example such as Hair.

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
| Individual clothing | `Clothing (Female)` and `Clothing (Male)` | Set `geometry`'s exact `clothing:<resource>` boolean to worn or removed | Implemented with catalogue-derived package-qualified resource identity and revisioned live state |
| Clothing item styles | `Clothing Item Presets` | Load an active item's own preset manager | Conservative same-folder style suggestions are browseable; live apply still requires a reliable exact clothing-item relationship |
| Worn clothing | Not represented reliably by the offline catalogue | Publish a bounded presentation roster plus private validated worn and locked references from the target Person's `geometry` | Implemented as a complete character-sheet projection; opaque or built-in rows remain read-only |
| Worn hair | Not represented reliably by the offline catalogue | Publish bounded active layer labels, tags, lock state, and simulation kind from the target Person's `geometry` | Implemented as a read-only Hair Studio roster; typed settings remain later work |
| Individual morph sliders | Preset files only | Publish UID, label, region, current value, and min/max; set a bounded numeric value | Later revisioned live-control schema |
| Materials, pose, and physics controls | Preset files only | Publish an allowlisted typed control schema | Later; do not expose arbitrary storables |

Preset loading uses VaM's own preset managers. VAM-PIP sets the validated
`presetBrowsePath`, temporarily disables load-on-selection, invokes
`LoadPreset` or `MergeLoadPreset`, and restores the previous setting. The
manager resolves a numeric catalogue ID to an exact installed local or
package-qualified resource; the browser never supplies a path or storable
name.

Individual clothing follows the same ownership boundary. BrowserAssist's
per-version clothing metadata supplies useful labels, creators, tags, and
item-type information, but its clothing UID is not globally unique and is not
the action identity. VAM-PIP instead preserves and resolves the exact
installed `.vam` resource. For packaged clothing that identity remains the
full `creator.package.version:/Custom/Clothing/Female-or-Male/item.vam`
reference through the manager and bridge.

The browser asks for the desired state, `Wear` or `Remove`; it does not ask
VaM to invert whatever state happens to exist at execution time. Each Person
snapshot includes a clothing revision, gender, a bounded presentation row for
each published active item, private validated worn and locked references, and a
truncation marker. The manager exposes only bounded labels, tags, and lock
state for entries that cannot be joined to the catalogue. Those entries remain
visible but non-actionable; their UID, package UID, and runtime path never
leave the private bridge join.

Both the manager and bridge validate the revision against the same target
Person and native `geometry`. Wear fails when the item's female/male category
is incompatible with the current gender. Any state-changing request for a
locked item fails. When publication is truncated, the browser treats an absent
item as unknown rather than incorrectly presenting it as not worn.

## Character-sheet presentation

The browser projects the selected Person's bounded live clothing roster into a
character sheet. Its tops, bras, panties and underwear, dresses and outfits,
bottoms, stockings and socks, shoes and boots, high heels, and other body
regions are organizational trays, not exclusive equipment sockets: every
region may contain zero, one, or many worn items. Items that cannot be
classified safely remain visible under **Unsorted**. Locked items are labelled
and cannot be removed. An active item without a validated catalogue identity
gets a read-only **In-game item** card instead of disappearing, while truncated
rows are still counted explicitly.

The sheet changes with the selected Person category. Clothing categories show
the live wardrobe. Hair shows a bounded multi-layer roster and a read-only
inspector organized as **Style & shape**, **Color & materials**, **Physics &
simulation**, and **Scalp & fit**. Actual Hair settings stay in VaM until each
control has a typed, bounded, revisioned protocol. Appearance, skin, morph,
pose, animation, physics, general, and Person-plugin presets use compact recipe
views. They can change overlapping state, so the sheet never claims that one
is the authoritative current preset.

For clothing cards, VAM-PIP may present same-package, same-folder item presets
whose filenames clearly share the clothing item's basename as **Related
styles**. This bounded relationship helps find color and material choices but
is deliberately navigation-only. BrowserAssist does not publish a trustworthy
target-clothing identity for these presets, and filename conventions are not
sufficient authority for a live action.

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

1. completed: broad preset browsing and loading plus Person add/select;
2. completed: individual clothing wear/remove with exact resource identity,
   revisioned worn state, lock reporting, and gender checks;
3. completed: complete clothing presentation for opaque/built-in items,
   adaptive Person sheets, and a bounded read-only Hair layer roster;
4. next: classify trusted raw plugin entry points and add an explicitly
   confirmed code-loading workflow;
5. add save/export workflows after their overwrite and screenshot semantics
   are explicit;
6. later: expose Hair settings, individual morphs, and curated material, pose,
   and physics controls through bounded, revisioned schemas.

This keeps the first workspace broadly useful without locking the protocol to
the shape of one example such as Hair.

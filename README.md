# VAM-PIP

[![Tests](https://github.com/ethanfel/VAM-PIP/actions/workflows/tests.yml/badge.svg)](https://github.com/ethanfel/VAM-PIP/actions/workflows/tests.yml)

VAM-PIP is a Linux-first package manager for large Virt-A-Mate libraries. It
keeps the complete `.var` collection on disk while exposing a much smaller,
dependency-closed set to VaM.

The main interface is a local web app where you can browse the catalogue built
by BrowserAssist, pin packages that must always remain available, and enable a
scene or preset temporarily—three days by default.

VAM-PIP does not delete or repack archives. Managed mode changes visibility
with same-directory renames:

```text
Creator.Package.1.var
Creator.Package.1.var.vampip-disabled
```

Every switch is journalled, the pre-manager state is saved as a baseline, and
leaving managed mode restores that baseline.

## Current status

Version 0.17.0 is functional but should still be treated as an early release.
Package switching is deliberately conservative:

- entering managed mode requires explicit confirmation;
- invalid archives are reported and left untouched;
- packages are never disabled while VaM is running;
- package-backed live loads rescan VaM before resolving their virtual paths;
- ambiguous same-ID copies are compared by logical archive contents, so harmless
  ZIP repacks are accepted while conflicting member data is refused;
- a failed multi-file switch rolls back completed renames automatically;
- every applied switch has a recovery manifest.

A backup of an important VaM installation is still recommended.

## Requirements

- Linux
- Python 3.10 or newer
- a local filesystem supporting Linux `renameat2(RENAME_NOREPLACE)`
- a VaM installation with an `AddonPackages` directory
- [BrowserAssist](https://hub.virtamate.com/resources/browserassist-free.20134/)
  for in-game-style resource browsing (optional)
- Proton only if you want VAM-PIP to invoke a Proton launch script

The manager itself has no third-party Python dependencies.

## Quick start

Run directly from the checkout:

```bash
./vampip manager configure /path/to/VaM/AddonPackages
./vampip manager scan
./vampip-manager
```

`vampip-manager` opens a browser on a private loopback URL. The URL contains a
per-install write token in its fragment; keep the terminal running while using
the interface.

Package management works without BrowserAssist. To add the searchable
scene/preset/item catalogue, install BrowserAssist, let it build or refresh its
local data, then run:

```bash
./vampip manager catalog import
```

If no supported BrowserAssist data is available, the import command reports
that explicitly and leaves the package inventory usable.

Package cards use BrowserAssist's indexed resource associations for their
preview collage, count, and type summary. Opening **Browse contents** then
checks those entries against the selected physical `.var`, so stale catalogue
rows and resources belonging only to another same-ID copy are not presented as
installed contents.

Alternatively, install both command-line entry points:

```bash
python3 -m pip install -e .
vampip-manager
```

The checked-in launchers store their state in this repository's ignored
`.vampip/` directory. An installed command defaults to
`${XDG_STATE_HOME:-~/.local/state}/vampip`. Override either form with:

```bash
export VAMPIP_ADDON_DIR=/path/to/VaM/AddonPackages
export VAMPIP_STATE_DIR=/path/to/vampip-state
```

## Recommended first use

1. Scan packages and, if BrowserAssist is installed, import its catalogue.
2. Review the detected default session plugins in the web app or with
   `./vampip manager session-plugins list`.
3. Pin any additional package that every session needs but that is not in
   VaM's default Session Plugins preset.
4. Review the managed-mode confirmation carefully.
5. Start managed mode. VAM-PIP records the exact current enabled/disabled state
   before applying the smaller set.
6. Find a scene or preset and select **Enable for 3 days**.
7. Launch VaM, or load the resource in an already-running VaM after the bridge
   reports a successful rescan.

VAM-PIP reads
`<VaM>/Custom/PluginPresets/Plugins_UserDefaults.vap`. On the first applied
managed-mode activation, every enabled packaged plugin in that preset is
resolved with its dependencies and saved as a permanent pin. Enabled loose
scripts already live outside `AddonPackages`, so they remain available without
a package pin. A missing preset is treated as an empty default; a malformed
preset or an enabled packaged reference that cannot resolve blocks activation
before package visibility changes.

Selecting a packaged resource creates a lease containing its archive, declared
`.var` dependencies, and package references found in supported scene/preset
text. The lease stores exact resolved package versions, so a later catalogue
change does not silently alter an active lease. It also records the exact
catalogue resource and archive member. VAM-PIP will not change a same-ID
content choice used by an active resource lease, because package-only
dependency data cannot prove that another fork contains every referenced
member. Release the lease, choose the content, and load the resource again.

When BrowserAssist refreshes while managed packages are hidden, its new
snapshot omits many resources it cannot currently see. VAM-PIP preserves the
last-good catalogue rows for exact installed hidden package versions, while
still removing stale local, uninstalled, invalid, and active-package entries.
This keeps hidden looks and hair searchable without treating every old row as
permanent.

The running manager fingerprints the package directory recursively. Adding,
replacing, renaming, or removing a `.var` causes the next status refresh or
15-second monitor pass to run the incremental inventory scanner; an unchanged
library does not trigger a full scan. If VaM is open and a newly discovered
archive is already enabled, the bridge receives one core package rescan.

For an already indexed BrowserAssist resource, VAM-PIP can resolve a newer
installed package version even while BrowserAssist's version list is stale. It
opens candidate archives and accepts the newer version only when the exact
resource member is present. The resource card then shows the selected and newer
versions, such as **v2 → v4**, and provides an explicit **Update to v4**
action. Ordinary Load continues to use the displayed current version; Update
pins dependency discovery, the lease, and any live bridge action to the exact
newer version. Entirely new resources still require BrowserAssist to rebuild
its manifest before VAM-PIP can import their metadata.

No dependency scanner can identify packages loaded dynamically by every
third-party script. Pin known runtime plugins that a collection always needs.

## Live changes and the VaM bridge

VAM-PIP can enable packages while VaM is open, but it never hides an archive
that the process may still be using. Lease expiry and unpin operations therefore
show as pending disables until VaM exits.

The web app polls a lightweight live-activity endpoint independently of the
inventory lock. When VaM closes and automatic reconciliation begins, the
banner changes to **Hiding X of Y packages**, shows progress, keeps the real
VaM process badge current, and disables launch until the switch finishes.

Install the optional session bridge:

```bash
./vampip manager bridge install
```

To replace an older VAM-PIP bridge with protocol 2:

```bash
./vampip manager bridge install --force
```

Then, once in VaM:

1. open **Session Plugins**;
2. add `Custom/Scripts/VAMPip/Bridge/VAMPipBridge.cslist`;
3. save it in the default session-plugin preset.

The bridge is a loose script, so VAM-PIP detects it in that preset but does not
create a package pin for it.

The bridge polls a local mailbox, coalesces compatible rescan requests,
serializes live actions, waits while VaM is loading, and invokes VaM's core
package rescan. BrowserAssist must be reloaded when it needs to rebuild its
private package/resource manifest. The bridge cannot rename files, run
commands, accept operating-system paths, or invoke arbitrary VaM storables.

## Timeline workspace

The **Timeline** tab discovers every `VamTimeline.AtomPlugin` in the current
scene and provides a large transport workspace plus a compact detachable
controller. Unmodified Timeline instances support a fixed legacy subset: play,
pause, stop/reset, frame stepping, animation choice, seek, speed, weight, and
lock where those storables are present.

The
[enhanced Timeline interoperability branch](https://github.com/ethanfel/vam-timeline/tree/vampip-interop)
adds protocol 1 state for exact segment, layer, and clip synchronization. Its
audited drop-in workflow keeps each original
`AcidBubbles.Timeline.<version>` filename, script path, plugin class, and scene
slot, so existing embedded Timeline data loads normally without migration or
scene rewriting. It publishes bounded catalogues with separate catalog and
live-state revisions; the browser receives only bridge-minted opaque IDs. Every
command is checked against the observed revision and a fixed operation
allowlist. Atom UIDs, plugin IDs, animation labels, and VaM storable/action
names never cross the browser control boundary.

With VaM and the VAM-PIP manager stopped, install the enhanced adapter from a
checkout beside VAM-PIP:

```bash
git clone --branch vampip-interop https://github.com/ethanfel/vam-timeline.git
cd vam-timeline
./timeline-dropin.sh status
./timeline-dropin.sh install
```

The installer accepts only audited whole-archive hashes, backs up each original
outside `AddonPackages`, preserves active/hidden filenames, and refuses unknown
or modified builds. To restore the byte-identical originals while VaM and the
manager are stopped:

```bash
./timeline-dropin.sh restore
```

Timeline state normally refreshes once per second and immediately after a
control. Clip catalogues share a 1,024-entry global budget, prioritized for
the selected atom and then playing instances. Transport stays live even when
an instance receives no catalogue allocation, while published counts, limits,
truncation flags, and sanitized adapter errors explain the bounded state.

The full view includes selectors, clip structure, inspector, interpolated
playhead, and a bounded canvas dope-sheet foundation. Track/keyframe rendering
activates when a future adapter version publishes graph data; keyframe
mutation is intentionally not part of protocol 1. The compact route is:

```text
/?view=timeline&popout=compact
```

Its title is `VAM-PIP Timeline`, which can be matched by a desktop-compositor
“keep above” rule. A browser popup cannot enforce always-on-top by itself.

## SAM 3D workspace

The **SAM 3D** tab accepts one image and an explicit person bounding box, then
runs Meta's native SAM 3D Body code in a dedicated Python 3.11 worker. The
result can be retargeted onto an existing VaM Person, applied with one-step
undo, and captured through a compatible VRRenderer camera atom.

Pose application and undo run as reversible VaM physics transactions. The 19
driven Person controllers and camera are frozen for the authoritative write.
All Person controllers then regain their saved physics state for an initial
settlement window, after which only `headControl` is held kinematic at its
settled position with the requested head rotation; the camera remains locked.
Person collision is restored immediately after the write. Undo restores the
saved transforms and physics settings, while failed Apply and bridge unload
restore every saved physics state. Captures are kept as a bounded per-job
history; existing VAM-PIP images in the legacy renderer directory are
backfilled automatically.

The workspace exposes both official DINOv3-H+ and original ViT-H checkpoints.
A run records its immutable model identity, and **Compare both** creates a
linked pair from the same source inputs. The single GPU queue loads them
serially in separate worker processes, so they never occupy VRAM together.
DINOv3-H+ remains the default and uses a pinned local DINOv3 source checkout.
The worker is isolated from ComfyUI, and bridge installation includes the
fixed camera preset and renderer scripts needed by that workflow. See the
[standalone SAM 3D Body setup](docs/SAM3D_SETUP.md) for environment, model,
and configuration instructions.

Completed reconstructions now use two independent workspaces. **Morph** owns an
ordered reference gallery of up to eight completed bodies, combines their
neutral skeleton measurements with bounded outlier rejection, and proposes
built-in morph changes for the selected VaM Person. **Pose + camera** keeps its
own current reconstruction and body selection, so choosing another pose image
does not replace, reset, or re-analyze the Morph reference set. Applying a body
fit creates one exact Person-wide undo snapshot; another fit cannot replace
that snapshot until it is restored. Body Scale, face morphs, and soft-body
physics are not changed. Leg and torso length morphs can still alter final
height.

Named Person profiles stay in browser-local storage. They remember selected
regions, fit strength, and the independent Morph reference set, but never store
live VaM morph identifiers, values, or revision tokens. Existing one-reference
profiles are imported into the new format automatically. Reopening a profile
therefore always requires a fresh read-only analysis against the current
Person before **Apply morphs** becomes available.

Jobs created before neutral-body signatures were added remain valid as a
single Morph reference and are marked **Legacy · solo only**. Rerun an older
image with the current worker before combining it with other views.

## External workspace

The **Workspace** tab is a capability-driven companion to VaM's asset UI. It
organizes the complete imported catalogue into Scenes, SubScenes, atom
presets, Custom Unity Assets, plugins, clothing, and all Person preset
families. Every category says whether it is:

- browseable from the offline catalogue;
- loadable through the current bridge;
- waiting for a typed live-state implementation.

This version can load or merge a Scene; list, select, and create allowlisted
native atoms; replace or merge matching non-Person atom presets; and load a
SubScene into a matching existing or newly created `SubScene` atom. It can
also load raw Custom Unity Asset bundles into an existing or new
`CustomUnityAsset`, expose VaM's bounded contained-asset choices, add/select a
Person, and replace or merge all eleven native Person preset families:
Appearance, Animation, Breast Physics, Clothing, General, Glute Physics, Hair,
Morphs, Person Plugins, Pose, and Skin. It can also wear or remove individual
female and male clothing items on a selected Person. The Person workspace
presents that live wardrobe as a character sheet with explicit multi-item
sections for tops, bras, panties and underwear, full outfits, bottoms,
stockings, shoes, high heels, accessories, and other regions. The sections
organize the display but never impose one-item equipment slots. Clothing that
VaM reports without a safe catalogue identity remains visible as a read-only
in-game item instead of disappearing.

The Hair category swaps the wardrobe for a Hair Studio showing every bounded
active layer and whether it uses VaM hair simulation. Exact unlocked layers
can be disabled individually; locked, ambiguous, and truncated state fails
closed instead of guessing. The inspector groups future Hair controls into
style, material, simulation, and scalp areas without inventing current values.
Other preset families use compact recipe views, because VaM does not publish a
reliable single “currently equipped preset” for them.

Replacing a Scene requires explicit confirmation in both the browser and API.
General and Person Plugin presets, non-Person atom presets, SubScenes, and raw
Custom Unity Asset bundles also require a separate critical-action
confirmation because their contents can replace broad state or carry
executable or otherwise active Unity content.

For every live resource action VAM-PIP:

1. resolves the numeric catalogue ID to an exact installed resource;
2. creates a three-day dependency-closed lease;
3. enables required packages without hiding anything from the running game;
4. asks VaM to rescan and performs one statically allowlisted operation.

The browser never submits a resource path, storable name, atom type, or action
name. It submits the server-owned category ID for standalone atom creation and
a numeric resource ID for every load. Preset categories whose atom type is not
in the audited native allowlist remain browse-only.

“Create new” is also enforced inside the VaM bridge: if that UID becomes
occupied before the request executes, the load fails instead of changing the
newly appeared atom.

For direct Custom Unity Asset loads, the bridge forces VaM's `loadDll` option
off immediately before assigning the bundle URL and never accepts that option
from the browser. This prevents a new sibling DLL from being loaded by the
operation, but cannot unload code already active in the VaM session.
Single-choice bundles load immediately; multi-choice bundles expose a
bridge-issued, stale-safe numeric picker without accepting a raw asset name.

Individual clothing uses an equally narrow desired-state contract. The
browser submits only a numeric catalogue ID, target Person UID, `Wear` or
`Remove`, the revision it observed, and an optional lease duration. The
manager resolves the catalogue ID to the exact installed, package-qualified
`.vam` resource reference; a BrowserAssist clothing UID is display metadata,
not action identity. VaM publishes a bounded presentation roster, validated
worn and locked references, and the Person's current gender. Only validated
references become actionable catalogue cards; opaque or built-in items never
gain a guessed removal action. The manager and bridge reject stale revisions,
incompatible wear requests, and locked changes. If bounded publication is
truncated, the workspace treats an unpublished item's state as unknown and
disables its action.

Selecting a resource card preview opens a centered inspector with a larger
preview, package and version details, the same owner actions as the compact
card, a lazy **Dependencies** catalogue, and a bounded **Styles & variants**
gallery. Dependency details scan the selected resource for direct package
references, follow installed `meta.json` dependencies transitively, label
active, hidden, and missing packages, and paginate the result inside the
inspector. **Open package** moves to the exact package in the Packages view.
The graph is bounded and cycle-safe; it is loaded only when the inspector
opens, so ordinary catalogue pages remain inexpensive.

When physical VARs share an exact ID but contain different logical data, the
inspector compares their relative locations, logical fingerprints, active
state, and declared dependencies. VAM-PIP never guesses which fork is correct.
**Use this content** stores an explicit choice by logical digest, then applies
that choice consistently to dependency resolution, archive previews,
thumbnails, activation, and loading. The choice survives path moves and
enabled/hidden suffix changes. If another fork is already active while VaM is
running, the choice is saved but the switch waits until VaM closes.

The styles release covers
clothing items with same-package `Clothing Item Presets`, plus same-type
`Preset Hair`, `Preset Clothing`, and `Clothing Item Presets` families. A
relationship requires the exact creator, package, case-sensitive folder,
overlapping declared versions, and an actual base filename followed by a clear
separator. Same-type families require that separator and an exact atom type.
Clothing-to-item-preset matching deliberately also accepts an exact stem and
ignores atom type because the different resource types establish the roles
while BrowserAssist normally leaves the preset atom type empty. The longest
matching base owns each option. Numeric IDs and case-insensitive logical paths
are deduplicated before the inspector reports the full option count and
returns at most twelve previews. These are explicitly filename-based browsing
hints, not semantic or action identities. Child tiles show their own version
and package state, but remain browse-only until VAM-PIP can resolve a safe
target-specific action.

Raw plugins remain browseable but action-disabled. They execute code, and the
BrowserAssist catalogue mixes entry scripts with helper source files. Trusted
plugin entry-point classification and explicit code-loading confirmation are
the next workspace target, followed by save/export workflows and then bounded
live controls.

See [the external workspace map](docs/EXTERNAL-WORKSPACE.md) and the
[Person-specific capability map](docs/PERSON-WORKSPACE.md) for the exact
implemented and planned surfaces.

See [bridge/vam/README.md](bridge/vam/README.md) for the protocol and manual
installation layout.

## Proton launch integration

The **Launch VaM** button and this command:

```bash
./vampip manager launch
```

use `launch-vam-desktop-proton.sh` from the VaM root. When managed mode is
active, VAM-PIP reconciles the current pin and lease set before starting it.
The launcher must be executable and must remain inside the VaM directory.
Output is written to `VaM/logs/vampip-launch.log`.

VAM-PIP intentionally does not guess global Proton, Gamescope, Wayland, or
resolution options. Keep those settings in the VaM-scoped launch script.

## Manager CLI

The browser uses the same service exposed by `vampip manager`:

```bash
# State and inventory
./vampip manager status
./vampip manager scan
./vampip manager packages Timeline --state active

# BrowserAssist catalogue
./vampip manager catalog import
./vampip manager resources "my scene" --type Scene --state hidden

# Permanent base set
./vampip manager pin AcidBubbles.Timeline
./vampip manager unpin AcidBubbles.Timeline

# VaM default Session Plugins preset
./vampip manager session-plugins list
./vampip manager session-plugins import
./vampip manager session-plugins import --include-disabled

# Temporary package access
./vampip manager lease Creator.Scene.4 --days 3
./vampip manager renew LEASE_ID --days 3
./vampip manager release LEASE_ID

# Preview first, then apply
./vampip manager reconcile
./vampip manager reconcile --apply --activate

# Restore the exact state captured before activation
./vampip manager deactivate
./vampip manager deactivate --apply
```

Mutating CLI commands either require `--apply` or clearly identify themselves
as immediate pin/lease changes. Run `./vampip manager --help` for the complete
command tree.

`session-plugins import` immediately creates any missing pins. By default it
imports only enabled packaged defaults; `--include-disabled` is the explicit
opt-in for disabled entries. Add `--apply` to reconcile the enlarged pin set
immediately when managed mode is already active. Pin creation and reconciliation
share the manager lock; if reconciliation fails, the result reports
`reconcile_error` and leaves the successfully imported pins in place for a
later retry (the CLI also exits nonzero). The web app exposes the same
enabled-only operation as **Import session defaults** and performs equivalent
preservation automatically as part of first activation.

## Audit and maintenance commands

The original conservative package-maintenance CLI remains available alongside
the manager:

```bash
./vampip scan
./vampip stats
./vampip doctor
./vampip duplicates --verify
./vampip prune
./vampip content-audit --min-mib 1 --verbose
```

`prune` is a dry run unless `--apply` is supplied, and applied candidates move
to a timestamped quarantine rather than being deleted. Old versions are
reported but are not automatically discarded because scenes and plugins can
pin an exact version.

`scan` also rejects ZIP entries whose version-required high byte is nonzero.
Python can read those entries, but VaM's old SharpZipLib reports the combined
value (for example, `788` for `0x0314`) as unsupported. Run
`./vampip doctor --refresh` to identify the archive and entry before loading it
in VaM.

Profiles are still useful for fixed, named package sets:

```bash
./vampip profile create my-scene Creator.Scene.4 AcidBubbles.Timeline
./vampip profile show my-scene --packages
./vampip profile activate my-scene
./vampip profile activate my-scene --apply
```

## Recovery

The safest normal recovery is:

```bash
./vampip manager deactivate
./vampip manager deactivate --apply
```

This restores each package to the enabled state recorded before managed mode.
It also preserves packages that were already disabled.

Each applied manager switch writes JSON under:

```text
<state-dir>/manager-runs/
```

To inspect and reverse one specific switch:

```bash
./vampip manager rollback /path/to/manager-runs/MANIFEST.json
./vampip manager rollback /path/to/manager-runs/MANIFEST.json --apply
```

The first command is read-only and reports the recorded state against the
actual source/target paths. New format-2 switches use a small append-only
progress sidecar, so a large package set no longer rewrites a multi-megabyte
manifest after every filename change. Rollback preflights every archive and
uses atomic no-clobber renames.

Do not rename the same managed archives manually while applying or rolling back
a switch. VAM-PIP refuses to overwrite an existing target.

## Architecture and security

The manager is daemon-optional: the CLI and loopback web server call the same
service layer and SQLite state. Package inventory scans are incremental, so
unchanged archives are not reopened. The BrowserAssist import is transactional;
a failed refresh retains the last usable generation.

The web server binds only to `127.0.0.1`/`localhost`, authenticates API access,
checks mutation origins and Host headers, and serves no third-party assets.

More detail:

- [Architecture](docs/ARCHITECTURE.md)
- [Safety and recovery](docs/SAFETY.md)
- [Contributing](CONTRIBUTING.md)

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest -v
node --check src/vampip/webui/app.js
```

The package data configuration includes the web UI and bridge source in wheels
and editable installs.

## License

MIT

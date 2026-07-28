# VAM-PIP safety model

VAM-PIP's managed mode changes package visibility, not package contents. Its
primary rule is:

> Enabling an additional package is allowed while VaM runs. Hiding a package
> is deferred until VaM is confirmed closed.

This document states the implemented invariants, recovery limits, and threat
model. See [ARCHITECTURE.md](ARCHITECTURE.md) for component and data-flow
details.

## Safety goals

Managed mode is designed to:

- preserve every `.var` archive in place;
- journal ordinary enable/disable operations so completed moves can be
  reversed;
- persist the pre-manager visibility set as a baseline;
- refuse incomplete dependency closures and detected same-ID content
  conflicts;
- avoid hiding packages from a live VaM process;
- constrain the web service to an authenticated loopback interface;
- give the VaM bridge no authority beyond requesting a package rescan.

It is not a sandbox, package-signature system, malware scanner, or defense
against a malicious process already running as the same Linux user.

## Core invariants

### 1. Managed visibility is suffix-only

The managed switcher changes:

```text
*.var <-> *.var.vampip-disabled
```

It does not rewrite ZIP contents, extract archives, or delete archive files.
Destinations are derived from the source path rather than accepted from an API
caller.

### 2. Switch paths stay below AddonPackages

Before applying a switch, `apply_switch()`:

- resolves the configured `AddonPackages` root;
- verifies every source resolves below that root;
- verifies each source is a file;
- rejects an existing destination;
- derives the destination by adding or removing the exact disabled suffix.

Rollback independently validates the manifest format, action/path
relationship, parent containment, and recorded device, inode, size, and
modification time.

### 3. Invalid packages are not automatically hidden

An archive recorded with no trustworthy package identity is excluded from
managed enable/disable planning. It remains visible or hidden exactly as found.
Consequently, VaM's active archive count can be larger than the desired package
count. Encrypted ZIP members and some unsupported compression errors can abort
inventory scanning instead of being recorded as an invalid row. The known case
where a ZIP entry has a nonzero version-required high byte is detected during
inspection and recorded as invalid because VaM's old SharpZipLib cannot extract
it.

### 4. Desired packages and session defaults must resolve completely

Pins must have a complete current dependency closure. Leases store an exact
closure only after successful resolution. Reconciliation stops when a pin is
missing, an exact leased ID has disappeared, or desired same-ID copies have
differing sizes or known SHA-256 digests. Hash calculation skips files that
raise `OSError`; a group of same-size copies whose hashes all remain unknown is
not rejected by this check.

On first managed-mode activation, VAM-PIP also reads
`Custom/PluginPresets/Plugins_UserDefaults.vap` and adds its enabled packaged
plugins to resolution. A missing preset is an empty default. A malformed preset
or unresolved enabled package reference refuses activation before any archive
visibility change; VAM-PIP does not fall back to hiding the unverified plugin.
Enabled loose scripts need no pin because package switching cannot hide them.
Disabled preset entries are ignored unless the user explicitly imports them.

### 5. Enables happen before disables

A switch exposes every desired package before hiding anything else. After a
caught switch failure, automatic rollback is attempted in reverse order when
the journal remains writable. This biases ordinary failure toward extra visible
content rather than a missing dependency, but is not a power-loss guarantee.

### 6. VaM-running reconciliation is enable-only

When VaM is detected:

- desired hidden packages may be renamed back to `.var`;
- undesired active packages remain active;
- the full removal count is reported as `pending_disable`;
- a bridge rescan request is sent only when at least one package was enabled.

Lease release and expiry follow the same rule. The automatic reconciler applies
pending disables only after process detection reports that VaM has exited.

### 7. Managed mode has an explicit baseline

The first activation records enabled/hidden state by logical relative path for
every valid known archive. Existing baseline rows are never updated during
normal reconciliation. Newly discovered valid paths are added with the state
seen at their first subsequent applied reconciliation; a scan or preview alone
does not add a baseline row.

A successful deactivation requires VaM to be closed, restores matching paths
from the baseline, and only then clears the baseline and managed-mode flag.
Those filesystem and SQLite steps are ordered but are not one transaction.

### 8. Mutations are journalled before the first rename

Each managed switch gets a JSON manifest under
`<state-dir>/manager-runs/`. The plan is written before filesystem mutation and
an update is attempted after every completed move. Manifest updates use a
temporary file and `os.replace()`, but neither manifest files nor containing
directories are `fsync`ed. Caught failures record their error and automatic
rollback outcome only while journal I/O remains available.

### 9. Normal manager switches are serialized

Service operations that can rename archives hold an advisory Linux `fcntl`
lock at `<state-dir>/manager.lock`. SQLite also uses WAL and a busy timeout.

The lock is advisory: other programs can still rename files. The standalone
manual rollback command is a recovery tool and must be run with the manager
server stopped.

### 10. The bridge cannot manage files

The bridge protocol accepts one operation: `rescan`. It accepts no paths,
package IDs, delete requests, process commands, or network connections.

The Linux manager completes archive renames and its inventory update before
publishing `request.json`. The C# plugin performs the rescan synchronously on
Unity's main thread, defers during scene loading, coalesces requests, suppresses
duplicate IDs, and rate-limits work.

## Safe behavior by VaM state

| Operation | VaM closed | VaM running |
| --- | --- | --- |
| Preview reconcile | Safe, no mutation | Safe, no mutation |
| Enable desired packages | Applied | Applied |
| Hide undesired packages | Applied | Deferred |
| Release/expire a lease | Reconciled fully | Removal deferred |
| Apply managed-mode deactivation | Allowed | Refused |
| Apply manual switch rollback | Run only while closed | Refused by CLI |
| Apply one-shot profile activation | Allowed | Refused by CLI |

Process state is sampled, not locked. VaM starting immediately after the sample
is a residual race; use VAM-PIP's launch command when possible so
reconciliation happens before launch.

## Baseline and lease semantics

### Baseline limitations

The baseline is keyed by logical relative path, not archive hash. It restores
visibility for currently present paths:

- a package removed after activation cannot be restored;
- a different file later placed at the same logical path inherits that path's
  baseline visibility;
- exact Linux path casing is preferred and preserves distinct paths; if a path
  has changed casing and multiple baseline paths are then possible
  case-insensitive matches, the ambiguous fallback is skipped;
- invalid archives are outside baseline management;
- packages first discovered during managed mode receive a baseline at their
  first subsequent applied reconciliation, not at the original activation
  time.

Back up the state directory before relying on managed mode for a large
collection. Losing `inventory.sqlite3` loses the baseline, pins, leases, token,
and settings even though the archives themselves remain intact.

### Lease limitations

Leases freeze exact package IDs at creation. They do not promise that those
files will remain installed. If a leased package disappears, reconciliation
fails rather than silently substituting another version.

Expired leases are ignored immediately. Their rows remain during previews and
while VaM runs, then are removed after a successful applied reconciliation
while VaM is closed; manual release can remove them sooner. Overlapping leases
keep a package desired until the last applicable expiry.

Resource leases inspect supported text resources for undeclared VaM package
paths, but reference discovery is necessarily heuristic. It only recognizes
quoted exact/`latest` virtual paths within a bounded stream window. Dynamically
constructed names, binary references, or nonstandard syntax may be missed.

## Crash consistency and recovery

An individual adjacent `os.replace()` is atomic from the running process's
perspective, but a multi-file switch is not one filesystem transaction. The
implementation does not `fsync` manifests or the directories containing
manifest and archive renames.

### Handled exceptions with a writable journal

If Python raises after some moves and the journal remains writable, VAM-PIP
attempts this flow:

1. the manifest enters `rolling-back`;
2. completed moves are reversed in reverse order;
3. each result is journalled;
4. the manifest ends as `rolled-back` or `rollback-failed`;
5. the original exception is re-raised.

If writing `rolling-back` or a later manifest update itself fails, the
exception path can stop before rollback begins or finishes. Inspect disk state
manually in that case.

### Process termination

`SIGKILL` or a process crash can occur between an archive rename and the
following manifest update. The filesystem may then be one move ahead of the
journal. Automatic recovery cannot prove which side is authoritative.

### Power loss or storage failure

Because there is no file or directory `fsync`, a power loss can persist
manifest and archive renames in an order different from the program order, or
lose recent updates. Recovery must treat both the manifest and filesystem as
evidence to compare, not assume either is durable ground truth.

### SQLite and filesystem gaps

SQLite mode/baseline changes and archive renames are also separate:

- every applied reconciliation commits new baseline rows before switching;
- activation then commits its session-default pins and
  `managed_mode = true`; a caught failure attempts manifest rollback;
- deactivation restores archives before clearing the baseline and mode flag;

A crash can therefore leave managed suffix changes while the mode flag is
false, or a restored baseline while the flag is still true. In the latter
case, restarting automatic reconciliation can reapply the managed package set.

Use this recovery sequence:

1. Stop VaM and stop the VAM-PIP web server.
2. Back up `AddonPackages`, the state directory, and the affected manifest
   before changing anything else.
3. Record `managed_mode`, `baseline_count`, and `auto_reconcile` from manager
   status before resuming automated work.
4. Run a fresh package scan to observe actual suffix state.
5. Inspect the newest file under `<state-dir>/manager-runs/`.
6. Compare every incomplete entry's `source` and `target` paths on disk.
7. Use `vampip manager rollback <manifest> --apply` only when entries marked
   `complete` accurately describe the filesystem.
8. Reconcile or deactivate only after the manifest/filesystem mismatch is
   resolved, and do not restart the web server until the intended suffix state,
   baseline, and mode flag agree.

`rollback_switch()` reverses only entries marked `complete`. It deliberately
does not guess about `planned`, `rollback-failed`, missing, or conflicting
paths.

### Baseline recovery

When the journal is consistent and the baseline is intact, the supported
high-level exit is:

```bash
vampip manager deactivate
vampip manager deactivate --apply
```

VaM must be closed. The first command previews the restore; the second applies
it and leaves pins and leases stored for later use.

### Catalog recovery

BrowserAssist import parses and validates a stable snapshot before mutation,
then uses a SQLite savepoint. A failed import leaves the previous catalog
generation intact. Fix or finish the BrowserAssist write and import again; do
not delete the last-good rows as a first response.

### Bridge recovery

`status.json` is intentionally treated as best-effort because the C# plugin
writes it non-atomically. A transient parse failure appears as unavailable
status, not a failed archive switch.

Match status by both protocol and `requestId`. If a request was interrupted,
submit a new manager operation or a new request ID. Do not repeatedly rewrite
one ID: the bridge suppresses the last handled ID. A rescan is idempotent but
can freeze VaM briefly.

## Threat model

### Protected assets

- archive contents and visibility;
- the managed-mode baseline;
- pins and active lease intent;
- switch manifests;
- the local API token;
- BrowserAssist and local resource metadata;
- the integrity of the configured VaM launch path.

### Trust boundaries

1. Browser JavaScript to the loopback HTTP server.
2. Manager process to SQLite and the VaM filesystem.
3. BrowserAssist snapshot files to the catalog importer.
4. Untrusted `.var` ZIPs to inventory/resource readers.
5. Linux manager to the Proton-hosted C# bridge through mailbox files.

### Threats and controls

| Threat | Implemented control | Residual risk |
| --- | --- | --- |
| Remote access | Server binds only to `127.0.0.1` or `localhost` | A local same-user process can still connect |
| DNS rebinding / hostile Host header | API requires a loopback Host name | Local proxies or unusual browser setups may need explicit review |
| Cross-site mutation | Mutations require a loopback Origin when Origin is present | Clients without an Origin still rely on token secrecy |
| Unauthorized API use | All API routes require a random token; comparison uses `hmac.compare_digest`; state permissions are hardened where supported | Token is bearer authority and is stored unencrypted in SQLite; mounted Windows filesystems may ignore Unix modes |
| Browser injection/framing | Fixed static-file allowlist, CSP, `nosniff`, same-origin resource policy, no-referrer policy, `frame-ancestors 'none'` | Imported names and tags remain untrusted display data; UI must continue using text-safe DOM APIs |
| Oversized HTTP request | JSON body is limited to 1 MiB and requires Content-Length/type | Slow local clients can still consume server threads |
| Path traversal in local resources | Absolute paths, `..`, colon components, and resolved escapes are rejected | Symlink behavior depends on the resolved filesystem at access time |
| Ambiguous ZIP member casing | Case-insensitive fallback is accepted only for one unique member | Malformed archives may still be expensive to inspect |
| Same-ID copy ambiguity | Different sizes or known SHA-256 digests are rejected | If hashing every same-size copy raises `OSError`, their content remains unverified |
| Concurrent manager mutation | Advisory manager lock, destination preflight, SQLite WAL | Non-cooperating tools and manual renames bypass the lock |
| Partial multi-file switch | Prewritten manifest, per-move updates, best-effort reverse rollback | SIGKILL can leave a rename ahead of the journal; journal I/O failure can interrupt rollback; no `fsync` ordering is guaranteed after power loss |
| SQLite/filesystem split state | Baseline and mode updates are deliberately ordered around switches | No transaction spans SQLite and archive renames; a crash requires checking both |
| Live package removal | Running VaM gets enable-only plans | A false-negative process probe can make an unsafe disable possible |
| Bridge abuse | Rescan-only schema, duplicate suppression, loading deferral, five-second rate limit | A same-user process or VaM plugin can still cause periodic rescan stalls |
| BrowserAssist volatility | Pre-read 64 MiB size check, before/after fingerprint snapshot, schema validation, savepoint | A concurrently growing file is read before rejection and can exceed 64 MiB in memory; catalog can remain stale until imported again |
| Malformed session defaults | Fixed preset path, 16 MiB read bound, strict JSON/slot/reference validation, complete package resolution before activation | The preset expresses availability intent only; VaM remains responsible for executing the selected plugins |
| Malicious package payload | No archive extraction; targeted bounded thumbnail/reference reads | VaM itself executes plugins; VAM-PIP does not establish package trust |
| Launch command injection | Script must be executable below VaM root and is passed without a shell | A malicious configured script file still executes with the user's authority |

## Web token handling

The manager prints a URL with the token in the fragment:

```text
http://127.0.0.1:8787/#token=...
```

Fragments are not sent in the HTTP request. The bundled UI stores the token in
`sessionStorage`, removes the fragment from the visible URL, and sends the
token in `X-VAMPIP-Token` for API calls.

The API also accepts a `token` query parameter. Thumbnail URLs currently use
that form. The bundled server redacts token query values from error logs and
suppresses successful access logs, but browser diagnostics or external local
HTTP instrumentation can still expose the complete URL. Keep the manager
terminal output and diagnostics private. VAM-PIP attempts to set the state
directory to mode `0700` and `inventory.sqlite3` to `0600`; filesystems without
Unix mode support may ignore that hardening. The bridge mailbox does not receive
an explicit mode, so protect it with user-only filesystem permissions.

The token grants all manager API authority. Regenerate it by stopping the
server, removing only the `api_token` setting with an appropriate SQLite
administrative procedure, and restarting. Do not publish it in bug reports.

## Process-detection risk

Runtime safety depends on detecting VaM as `vam` or `vam.exe` in `/proc` using
the process `comm` or first command-line basename. This avoids false positives
from arbitrary command-line mentions, but a nonstandard launcher or renamed
binary can create a false negative.

Before enabling automatic reconciliation:

1. start VaM through the actual Proton workflow;
2. verify `vampip manager status` reports `"vam": {"running": true, ...}`;
3. confirm a reconcile preview reports `vam_running: true`;
4. disable auto-reconcile if detection is unreliable.

Do not assume that the presence of Wine or Proton alone counts as VaM.

## Untrusted archive and catalog input

VAM-PIP parses archive filenames, ZIP metadata, root `meta.json`, selected
resource text, sibling JPEG thumbnails, and VaM's default Session Plugins
preset. Catalog manifests have a 64 MiB pre-read size check, session defaults
have a 16 MiB limit, text reference scans are bounded at 256 MiB, and
thumbnails are bounded at 16 MiB by default. A manifest that grows after its
size check is read before the changed fingerprint is rejected.

The root `meta.json` reader is not a general malware sandbox and does not
currently impose an explicit decompressed-byte limit. Encrypted members and
unsupported compression can also abort a scan instead of becoming an invalid
inventory row. Use VAM-PIP only on collections trusted enough to present to
VaM, and do not treat a successful scan as a security endorsement.

Thumbnail bytes are cached and served as `image/jpeg` without image decoding or
content validation by VAM-PIP. Browser and OS image libraries remain part of
the attack surface.

## Operational checklist

Before first activation:

- Back up the state directory and any irreplaceable archive collection.
- Install and load the loose VAM-PIP session bridge if live enables are needed.
- Inspect `vampip manager session-plugins list`; enabled packaged defaults are
  auto-pinned on first activation, while loose scripts need no package pin.
- Pin any other always-required package that is absent from the default preset.
- Import disabled defaults only when deliberately needed, with
  `vampip manager session-plugins import --include-disabled`.
- Scan and resolve all pins successfully.
- Verify VaM process detection with the real launcher.
- Preview activation, preferably with VaM closed.

During normal operation:

- Review `pending_enable` and `pending_disable` before applying.
- Wait for matching bridge `ok` status before loading newly enabled content
  when confirmation matters.
- Let lease expiry remain pending until VaM exits.
- Keep one manager server per state directory and AddonPackages root.
- Do not run one-shot profiles or manual suffix renames concurrently.

Before deactivation or rollback:

- Close VaM.
- Stop the automatic manager when doing manual recovery.
- Preview deactivation where supported.
- Back up the affected manifest and state database.
- Never overwrite an existing rollback target to “make it work.”

## Non-goals and known limitations

- No cryptographic package signatures or publisher trust.
- No sandbox for VaM plugins or archive parsing.
- No protection from a malicious same-user process.
- No distributed or multi-host coordination.
- No atomic transaction spanning SQLite, every archive rename, and bridge
  status.
- No live refresh of BrowserAssist's private package/resource manifest. VaM's
  loose-plugin sandbox prohibits reflection and BrowserAssist exposes no public
  rescan action, so reload BrowserAssist or restart VaM when needed.
- No automatic resolution of a crash-window mismatch between disk and journal.
- No guarantee that heuristic scene reference scanning finds every runtime
  dependency.

When reporting a safety issue, include the manifest state and redacted paths,
but never include the API token or private catalog content.

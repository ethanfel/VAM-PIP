# Contributing to VAM-PIP

VAM-PIP manages a collection that may represent hundreds of gigabytes of
user-owned content. Contributions should keep operations conservative,
recoverable, and useful without a daemon or network connection.

## Local setup

VAM-PIP supports Python 3.10 and newer and has no third-party runtime
dependencies. An isolated editable install is the most convenient setup:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
vampip --help
```

The source tree can also be exercised without installing it:

```bash
PYTHONPATH=src python -m vampip --help
```

Do not point development tests at a real VaM library. Use temporary directories
and small synthetic `.var` archives.

## Tests

Run the standard-library test suite from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test*.py" -v
```

Some web tests bind a temporary loopback socket. They do not require internet
access, but a restrictive sandbox may need to permit localhost sockets.

If Node.js is installed, check browser code syntax as well:

```bash
node --check src/vampip/webui/app.js
```

The GitHub workflow runs the Python suite on Python 3.10 through 3.13 and
performs the JavaScript check whenever Node.js is available.

## Safety requirements

Changes that touch packages or manager state should preserve these invariants:

- Inspection, cleanup, activation, and uninstall commands are dry runs unless
  the user explicitly applies them.
- Package data is quarantined or reversibly renamed, never permanently deleted.
- A recovery journal or manifest is durable before the first filesystem
  mutation.
- Multi-file operations either complete coherently or can restore the exact
  prior paths and enabled state.
- Mutation targets are resolved beneath the selected `AddonPackages` or state
  directory; do not trust unchecked archive paths, globs, or environment
  expansion.
- Existing user files and unrelated worktree changes are preserved.
- Disabling packages while VaM is running remains deferred; safe live enabling
  must not broaden into live removal.
- Malformed JSON, invalid ZIPs, path traversal, duplicate ZIP members, and
  oversized compressed content fail safely and with bounded reads.
- Local HTTP endpoints remain loopback-only, authenticated, and protected
  against foreign mutation origins.

Any deliberate exception needs a focused explanation, an explicit user-facing
confirmation, and tests proving the recovery behavior.

## Code and database changes

- Keep runtime functionality in the Python standard library unless a dependency
  is discussed and accepted first.
- Use Python 3.10-compatible syntax and type hints.
- Keep filesystem mutation logic separate from planning and reporting.
- Treat archive and BrowserAssist metadata as untrusted input.
- Make SQLite migrations additive and repeatable, increment the schema version,
  and test both a fresh database and an older supported schema.
- Keep service methods usable without the web UI so command-line recovery
  remains possible.

## Pull requests

A useful pull request includes:

- A concise description of the user-visible outcome.
- Tests for normal behavior, refusal paths, and rollback where state changes.
- Confirmation that the full `unittest` suite passes.
- Any compatibility, migration, or recovery notes a user would need.

Avoid bundling unrelated formatting or generated files with a functional
change.

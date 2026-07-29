# Security policy

VAM-PIP mutates package visibility and exposes a loopback-only control surface,
so reports involving data loss, archive-path validation, authentication, or
unexpected VaM actions should not begin in a public issue.

Use GitHub's **Report a vulnerability** form for this repository. Include:

- the VAM-PIP version or commit;
- the smallest safe reproduction;
- the expected and observed behavior;
- whether package files, manager state, or a running VaM process were affected.

Do not attach private VaM libraries, BrowserAssist databases, manager state
directories, API tokens, or proprietary package contents. Synthetic filenames
and minimal test archives are preferred.

Ordinary bugs and feature requests can use the public issue tracker.

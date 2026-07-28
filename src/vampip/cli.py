from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from vampip import __version__
from vampip.analysis import (
    duplicate_candidate_rows,
    family_id,
    identity_conflicts,
    missing_dependencies,
    package_id,
    verified_duplicate_groups,
    version_families,
)
from vampip.database import connect
from vampip.bridge import install_bridge
from vampip.content_audit import audit_contents
from vampip.inventory import rows_for_root, scan
from vampip.models import parse_var_filename
from vampip.runtime import atomic_write_text, derive_vam_root, find_vam_processes
from vampip.service import ManagerService
from vampip.switching import manager_lock, rollback_switch
from vampip.operations import (
    MoveCandidate,
    candidates_from_duplicates,
    install_archive,
    quarantine_candidates,
    restore_manifest,
    reverse_dependency_blockers,
    select_packages,
)
from vampip.profiles import (
    activation_plan,
    apply_activation,
    list_profiles,
    load_profile,
    profile_path,
    resolve as resolve_profile,
    rollback_activation,
    save_profile,
)


def format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{value} B"
        amount /= 1024
    return f"{value} B"


def default_state_dir() -> Path:
    configured = os.environ.get("VAMPIP_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    base = Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()
    return base / "vampip"


def resolve_addon_dir(value: str | None, state_dir: Path | None = None) -> Path:
    configured = value or os.environ.get("VAMPIP_ADDON_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if state_dir is not None:
        config_file = state_dir.expanduser() / "addon-dir"
        if config_file.is_file():
            configured = config_file.read_text(encoding="utf-8").strip()
            if configured:
                return Path(configured).expanduser().resolve()
    cwd = Path.cwd()
    if cwd.name.casefold() == "addonpackages":
        return cwd.resolve()
    candidate = cwd / "AddonPackages"
    if candidate.is_dir():
        return candidate.resolve()
    sibling = cwd.parent / "AddonPackages"
    if sibling.is_dir():
        return sibling.resolve()
    raise ValueError(
        "AddonPackages path is required; pass --addon-dir or set VAMPIP_ADDON_DIR"
    )


def _scan_and_print(root: Path, connection: sqlite3.Connection) -> None:
    result = scan(root, connection)
    print(
        f"Scanned {result.found:,} packages in {result.elapsed:.2f}s: "
        f"{result.inspected:,} inspected, {result.unchanged:,} cached, "
        f"{result.invalid:,} invalid, {result.removed:,} vanished."
    )


def _require_vam_closed(action: str) -> None:
    pids = find_vam_processes()
    if pids:
        raise ValueError(
            f"close VaM before {action}; detected process IDs "
            + ", ".join(map(str, pids))
        )


def _load_rows(
    root: Path, connection: sqlite3.Connection, *, refresh: bool = False
) -> list[sqlite3.Row]:
    rows = rows_for_root(connection, root)
    if refresh or not rows:
        _scan_and_print(root, connection)
        rows = rows_for_root(connection, root)
    return rows


def cmd_scan(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        _scan_and_print(root, connection)
        rows = rows_for_root(connection, root)
        if args.verify_duplicates:
            groups, calculated = verified_duplicate_groups(connection, rows)
            print(
                f"Verified {len(groups):,} duplicate groups "
                f"({calculated:,} new SHA-256 hashes)."
            )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=args.refresh)
    valid = [row for row in rows if row["valid"]]
    active = [row for row in rows if row["enabled"]]
    families = {family_id(row).casefold() for row in valid}
    nested = [row for row in rows if len(Path(row["relative_path"]).parts) > 1]
    candidates = duplicate_candidate_rows(rows)
    print(f"AddonPackages: {root}")
    print(
        f"Archives:      {len(rows):,} ({format_bytes(sum(r['size'] for r in rows))})"
    )
    print(f"Valid:         {len(valid):,}")
    print(f"Invalid:       {len(rows) - len(valid):,}")
    print(f"Active for VaM: {len(active):,}")
    print(f"Profile-hidden: {len(rows) - len(active):,}")
    print(f"Families:      {len(families):,}")
    print(f"Nested:        {len(nested):,}")
    print(f"Hash candidates (same ID and size): {len(candidates):,}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=args.refresh)
    pattern = args.pattern.casefold() if args.pattern else None
    shown = 0
    for row in rows:
        identity = package_id(row) if row["valid"] else row["basename"]
        if pattern and pattern not in identity.casefold():
            continue
        status = (
            "invalid"
            if not row["valid"]
            else ("active" if row["enabled"] else "hidden")
        )
        print(
            f"{identity:<55} {format_bytes(row['size']):>10} "
            f"{status:<7} {row['relative_path']}"
        )
        shown += 1
        if args.limit and shown >= args.limit:
            break
    print(f"{shown:,} shown.")
    return 0


def _print_duplicate_group(group, *, verbose: bool) -> None:
    print(
        f"{group.package_id}: {len(group.redundant)} redundant, "
        f"{format_bytes(group.physical_bytes)} reclaimable"
    )
    if verbose:
        print(f"  keep  {group.keeper['relative_path']}")
        for row in group.redundant:
            print(f"  extra {row['relative_path']}")


def cmd_duplicates(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=args.refresh)
        candidates = duplicate_candidate_rows(rows)
        print(
            f"Possible duplicate files: {len(candidates):,} "
            "(same package ID, version, and size)."
        )
        groups = []
        if args.verify:
            groups, calculated = verified_duplicate_groups(connection, rows)
            rows = rows_for_root(connection, root)
            reclaim = sum(group.physical_bytes for group in groups)
            redundant = sum(len(group.redundant) for group in groups)
            print(
                f"Verified byte-identical: {redundant:,} files in "
                f"{len(groups):,} groups; {format_bytes(reclaim)} reclaimable "
                f"({calculated:,} hashes calculated)."
            )
            for group in groups[: args.limit or None]:
                _print_duplicate_group(group, verbose=args.verbose)

        conflicts = identity_conflicts(rows)
        print(f"Same-ID content/size conflicts: {len(conflicts):,}.")
        for identity, conflict_rows in conflicts[: args.limit or None]:
            sizes = ", ".join(
                f"{format_bytes(row['size'])} at {row['relative_path']}"
                for row in conflict_rows
            )
            print(f"  {identity}: {sizes}")

        families = version_families(rows)
        older_files = sum(item.file_count - 1 for item in families)
        print(
            f"Multiple-version families: {len(families):,} "
            f"({older_files:,} non-latest file slots; not auto-pruned)."
        )
        for item in families[: args.limit or None]:
            pins = (
                f"; exact pins: {', '.join(map(str, item.exactly_pinned))}"
                if item.exactly_pinned
                else ""
            )
            print(f"  {item.family}: {', '.join(map(str, item.versions))}{pins}")
    return 0


def cmd_content_audit(args: argparse.Namespace) -> int:
    if args.min_mib <= 0:
        raise ValueError("--min-mib must be greater than zero")
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=args.refresh)
        groups, calculated = verified_duplicate_groups(
            connection, rows, calculate=args.verify_archives
        )
        skipped_paths = {row["path"] for group in groups for row in group.redundant}
        minimum_size = int(args.min_mib * 1024 * 1024)
        result = audit_contents(
            rows,
            minimum_size=minimum_size,
            skip_paths=skipped_paths,
        )

    print(
        f"Scanned {result.archives_scanned:,} distinct archives; "
        f"skipped {result.archives_skipped:,} verified whole-archive copies; "
        f"{result.unreadable_archives:,} unreadable."
    )
    print(
        f"Considered {result.entries_considered:,} ZIP entries of at least "
        f"{args.min_mib:g} MiB."
    )
    print(
        f"Likely repeated payloads across archives: "
        f"{len(result.cross_archive_groups):,} groups, approximately "
        f"{format_bytes(result.cross_archive_estimate)} compressed."
    )
    print(
        f"Likely repeated payloads within one archive: "
        f"{len(result.intra_archive_groups):,} groups, approximately "
        f"{format_bytes(result.intra_archive_estimate)} compressed."
    )
    print(
        "These are CRC32+size candidates, not safe prune targets; package paths "
        "and metadata can still require every entry."
    )
    if calculated:
        print(f"Calculated {calculated:,} whole-archive hashes first.")

    if result.cross_archive_groups:
        print("Largest cross-archive candidates:")
        for group in result.cross_archive_groups[: args.limit]:
            print(
                f"  {format_bytes(group.estimated_redundant_compressed_bytes)} "
                f"across {group.archive_count} archives "
                f"(payload {format_bytes(group.uncompressed_size)}, "
                f"CRC {group.crc32:08x})"
            )
            if args.verbose:
                for sample in group.samples:
                    print(f"    {sample.archive_relative} :: {sample.entry_name}")
    if result.intra_archive_groups:
        print("Largest within-archive candidates:")
        for group in result.intra_archive_groups[: args.limit]:
            print(
                f"  {format_bytes(group.estimated_redundant_compressed_bytes)} "
                f"in {group.archive_relative} ({group.extra_entries} extra paths)"
            )
            if args.verbose:
                for entry_name in group.entry_names:
                    print(f"    {entry_name}")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=True)
        groups, calculated = verified_duplicate_groups(connection, rows)
        candidates = candidates_from_duplicates(groups)
        reclaim = sum(group.physical_bytes for group in groups)
        print(
            f"Plan: quarantine {len(candidates):,} byte-identical duplicate files "
            f"from {len(groups):,} package IDs; up to {format_bytes(reclaim)} "
            f"reclaimable ({calculated:,} hashes calculated)."
        )
        shown_groups = groups if args.verbose else groups[:20]
        for group in shown_groups:
            _print_duplicate_group(group, verbose=args.verbose)
        if len(groups) > len(shown_groups):
            print(f"... {len(groups) - len(shown_groups):,} more groups")

        if not args.apply:
            print("Dry run only. Re-run with --apply to move these files.")
            return 0
        if not candidates:
            print("Nothing to quarantine.")
            return 0
        _require_vam_closed("quarantining packages")
        base = (
            args.quarantine.resolve()
            if args.quarantine
            else root.parent / f"{root.name}.vampip-quarantine"
        )
        manifest = quarantine_candidates(root, candidates, base)
        scan(root, connection)
        print(f"Quarantined {len(candidates):,} files. Restore manifest: {manifest}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=args.refresh)
    checked = rows if args.all else [row for row in rows if row["enabled"]]
    invalid = [row for row in checked if not row["valid"]]
    missing = missing_dependencies(checked)
    conflicts = identity_conflicts(checked)
    nested = [row for row in checked if len(Path(row["relative_path"]).parts) > 1]
    suffixed = [
        row
        for row in checked
        if (parsed := parse_var_filename(row["basename"])) and parsed.copy_suffix
    ]
    print(f"Scope: {('all managed archives' if args.all else 'active archives only')}")
    print(f"Invalid archives/names:       {len(invalid):,}")
    print(f"Missing dependency references: {len(missing):,}")
    print(f"Same-ID conflicts:             {len(conflicts):,}")
    print(f"Nested archives:               {len(nested):,}")
    print(f"Copy-suffixed filenames:       {len(suffixed):,}")
    for row in invalid[: args.limit]:
        print(f"  invalid {row['relative_path']}: {row['error']}")
    for owner, dependency in missing[: args.limit]:
        print(f"  missing {dependency} (required by {owner})")
    for identity, group in conflicts[: args.limit]:
        print(f"  conflict {identity} ({len(group)} files)")
    if any((invalid, missing, conflicts)):
        return 1
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    failures = 0
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=True)
        for source_text in args.archives:
            source = Path(source_text).expanduser()
            try:
                status, destination = install_archive(
                    source,
                    root,
                    rows,
                    hardlink=args.link,
                    dry_run=args.dry_run,
                )
                print(f"{status}: {source} -> {destination}")
                if status == "installed":
                    _scan_and_print(root, connection)
                    rows = rows_for_root(connection, root)
            except (OSError, ValueError) as exc:
                failures += 1
                print(f"error: {exc}", file=sys.stderr)
        if not args.dry_run and not failures:
            missing = missing_dependencies(rows)
            if missing:
                print(
                    f"Warning: the active library has {len(missing):,} "
                    "missing dependency references; run `vampip doctor`."
                )
    return 1 if failures else 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=True)
        selected = select_packages(rows, args.selector)
        if not selected:
            print(f"No installed package matches {args.selector!r}.", file=sys.stderr)
            return 1
        blockers = reverse_dependency_blockers(rows, selected)
        if blockers and not args.force:
            print("Refusing removal; these installed packages depend on it:")
            for owner, dependency in blockers[:20]:
                print(f"  {owner} -> {dependency}")
            print("Use --force only if you accept broken references.")
            return 1
        print(f"Plan: quarantine {len(selected):,} file(s):")
        for row in selected[:30]:
            print(f"  {row['relative_path']}")
        if not args.yes:
            print("Dry run only. Re-run with --yes to proceed.")
            return 0
        _require_vam_closed("uninstalling packages")
        base = (
            args.quarantine.resolve()
            if args.quarantine
            else root.parent / f"{root.name}.vampip-quarantine"
        )
        candidates = [
            MoveCandidate(
                row=row, reason=f"uninstall {args.selector}", sha256=row["sha256"]
            )
            for row in selected
        ]
        manifest = quarantine_candidates(root, candidates, base)
        scan(root, connection)
        print(f"Quarantined {len(selected):,} files. Restore manifest: {manifest}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    if not args.yes:
        print(f"Dry run only. Re-run with --yes to restore {args.manifest}.")
        return 0
    _require_vam_closed("restoring quarantined packages")
    count = restore_manifest(args.manifest.resolve())
    print(f"Restored {count:,} files.")
    return 0


def cmd_profile_create(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    destination = profile_path(args.state_dir, args.name)
    if destination.exists() and not args.replace:
        print(
            f"Profile {args.name!r} already exists; use --replace to update it.",
            file=sys.stderr,
        )
        return 1
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=True)
        resolution = resolve_profile(args.packages, rows)
    print(
        f"Resolved {len(args.packages):,} roots to "
        f"{len(resolution.selected):,} exact package archives."
    )
    if resolution.missing:
        print(f"Unresolved references: {len(resolution.missing):,}")
        for owner, reference in resolution.missing[:30]:
            print(f"  {owner} -> {reference}")
        if not args.allow_missing:
            print("Profile not saved. Use --allow-missing to accept broken references.")
            return 1
    path = save_profile(args.state_dir, args.name, args.packages, resolution)
    print(f"Saved profile {args.name!r}: {path}")
    return 0


def cmd_profile_list(args: argparse.Namespace) -> int:
    profiles = list_profiles(args.state_dir)
    if not profiles:
        print("No profiles.")
        return 0
    for profile in profiles:
        missing = profile.get("missing", [])
        print(
            f"{profile['name']:<24} {len(profile['packages']):>5} packages  "
            f"{len(profile['roots']):>3} roots  {len(missing):>3} unresolved"
        )
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = load_profile(args.state_dir, args.name)
    print(f"Profile: {profile['name']}")
    print(f"Created: {profile.get('created_utc', 'unknown')}")
    print("Roots:")
    for root in profile["roots"]:
        print(f"  {root}")
    print(f"Resolved packages: {len(profile['packages']):,}")
    if args.packages:
        for identity in profile["packages"]:
            print(f"  {identity}")
    missing = profile.get("missing", [])
    if missing:
        print(f"Unresolved references: {len(missing):,}")
        for item in missing:
            print(f"  {item['required_by']} -> {item['reference']}")
    return 0


def cmd_profile_activate(args: argparse.Namespace) -> int:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    profile = load_profile(args.state_dir, args.name)
    with connect(args.state_dir) as connection:
        rows = _load_rows(root, connection, refresh=True)
        plan = activation_plan(args.name, profile["packages"], rows)
        print(
            f"Profile {args.name!r}: {plan.active_after:,} active archives after "
            f"activation; enable {len(plan.to_enable):,}, "
            f"hide {len(plan.to_disable):,}."
        )
        if args.verbose:
            for row in plan.to_enable:
                print(f"  enable {row['relative_path']}")
            for row in plan.to_disable:
                print(f"  hide   {row['relative_path']}")
        if not args.apply:
            print("Dry run only. Close VaM, then re-run with --apply.")
            return 0
        if not plan.to_enable and not plan.to_disable:
            print("Profile is already active.")
            return 0
        _require_vam_closed("activating a package profile")
        manifest = apply_activation(args.state_dir, root, plan)
        _scan_and_print(root, connection)
        print(f"Profile activated. Rollback manifest: {manifest}")
    return 0


def cmd_profile_rollback(args: argparse.Namespace) -> int:
    if not args.apply:
        print(f"Dry run only. Re-run with --apply to roll back {args.manifest}.")
        return 0
    _require_vam_closed("rolling back a package profile")
    count = rollback_activation(args.manifest.resolve())
    print(f"Rolled back {count:,} profile rename operations.")
    return 0


def _print_json(document: object) -> None:
    print(json.dumps(document, indent=2, ensure_ascii=False))


def _manager_service(args: argparse.Namespace) -> ManagerService:
    root = resolve_addon_dir(args.addon_dir, args.state_dir)
    return ManagerService(root, args.state_dir)


def cmd_manager_configure(args: argparse.Namespace) -> int:
    addon_dir = args.path.expanduser().resolve()
    if not addon_dir.is_dir():
        raise FileNotFoundError(addon_dir)
    derive_vam_root(addon_dir)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.state_dir / "addon-dir", f"{addon_dir}\n")
    _print_json(
        {
            "configured": True,
            "addon_dir": str(addon_dir),
            "state_dir": str(args.state_dir),
        }
    )
    return 0


def cmd_manager_status(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).status())
    return 0


def cmd_manager_scan(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).scan_packages())
    return 0


def cmd_manager_catalog_import(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).import_catalog())
    return 0


def cmd_manager_catalog_facets(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).catalog_facets())
    return 0


def cmd_manager_session_plugins_list(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).session_plugins())
    return 0


def cmd_manager_session_plugins_import(args: argparse.Namespace) -> int:
    result = _manager_service(args).import_session_plugins(
        include_disabled=args.include_disabled,
        apply=args.apply,
    )
    _print_json(result)
    return 2 if result.get("reconcile_error") else 0


def cmd_manager_packages(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).list_packages(
            query=args.query,
            state=args.state,
            limit=args.limit,
            offset=args.offset,
        )
    )
    return 0


def cmd_manager_resources(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).search_resources(
            query=args.query,
            resource_type=args.type,
            state=args.state,
            favorite=args.favorite,
            limit=args.limit,
            offset=args.offset,
        )
    )
    return 0


def cmd_manager_pin(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).pin(
            args.packages,
            label=args.label,
            apply=args.apply,
        )
    )
    return 0


def cmd_manager_unpin(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).unpin(args.package, apply=args.apply))
    return 0


def cmd_manager_lease(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).lease(
            args.packages,
            days=args.days,
            label=args.label,
            apply=not args.no_apply,
        )
    )
    return 0


def cmd_manager_renew(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).renew(args.lease_id, days=args.days))
    return 0


def cmd_manager_release(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).release(
            args.lease_id,
            apply=not args.no_apply,
        )
    )
    return 0


def cmd_manager_reconcile(args: argparse.Namespace) -> int:
    _print_json(
        _manager_service(args).reconcile(
            apply=args.apply,
            activate=args.activate,
        )
    )
    return 0


def cmd_manager_deactivate(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).deactivate(apply=args.apply))
    return 0


def cmd_manager_rollback(args: argparse.Namespace) -> int:
    if not args.apply:
        _print_json(
            {
                "dry_run": True,
                "manifest": str(args.manifest.resolve()),
            }
        )
        return 0
    _require_vam_closed("rolling back a manager package switch")
    service = _manager_service(args)
    manifest = args.manifest.resolve()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_root = document.get("addon_dir")
    if not isinstance(manifest_root, str):
        raise ValueError("manager switch manifest has no AddonPackages root")
    if Path(manifest_root).resolve() != service.addon_dir:
        raise ValueError(
            "manager switch manifest belongs to a different AddonPackages directory"
        )
    with manager_lock(args.state_dir):
        restored = rollback_switch(manifest)
        with connect(args.state_dir) as connection:
            scan(service.addon_dir, connection)
    _print_json({"rolled_back": restored, "manifest": str(manifest)})
    return 0


def cmd_manager_bridge_install(args: argparse.Namespace) -> int:
    service = _manager_service(args)
    installed = install_bridge(service.vam_root, force=args.force)
    _print_json(
        {
            "installed": [str(path) for path in installed],
            "next_step": (
                "Add VAMPipBridge.cslist in VaM's Session Plugins screen "
                "and save the session defaults."
            ),
        }
    )
    return 0


def cmd_manager_launch(args: argparse.Namespace) -> int:
    _print_json(_manager_service(args).launch_vam(reconcile=not args.no_reconcile))
    return 0


def cmd_manager_serve(args: argparse.Namespace) -> int:
    from vampip.web import serve_manager

    service = _manager_service(args)
    serve_manager(
        service,
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vampip",
        description="Safe local package management for Virt-A-Mate .var archives.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--addon-dir",
        help="VaM AddonPackages directory (or set VAMPIP_ADDON_DIR)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(),
        help="inventory/cache directory (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="refresh the cached inventory")
    scan_parser.add_argument(
        "--verify-duplicates",
        action="store_true",
        help="SHA-256 hash only same-ID/same-size candidates",
    )
    scan_parser.set_defaults(func=cmd_scan)

    stats_parser = subparsers.add_parser("stats", help="show library size and counts")
    stats_parser.add_argument("--refresh", action="store_true")
    stats_parser.set_defaults(func=cmd_stats)

    list_parser = subparsers.add_parser("list", help="list indexed packages")
    list_parser.add_argument("pattern", nargs="?")
    list_parser.add_argument("--limit", type=int, default=0)
    list_parser.add_argument("--refresh", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    duplicate_parser = subparsers.add_parser(
        "duplicates", help="find exact copies, conflicts, and multiple versions"
    )
    duplicate_parser.add_argument("--verify", action="store_true")
    duplicate_parser.add_argument("--refresh", action="store_true")
    duplicate_parser.add_argument("--verbose", action="store_true")
    duplicate_parser.add_argument("--limit", type=int, default=20)
    duplicate_parser.set_defaults(func=cmd_duplicates)

    content_parser = subparsers.add_parser(
        "content-audit",
        help="estimate repeated large payloads inside distinct .var archives",
    )
    content_parser.add_argument(
        "--min-mib",
        type=float,
        default=1.0,
        help="minimum uncompressed entry size (default: %(default)s)",
    )
    content_parser.add_argument("--limit", type=int, default=20)
    content_parser.add_argument("--verbose", action="store_true")
    content_parser.add_argument("--refresh", action="store_true")
    content_parser.add_argument(
        "--verify-archives",
        action="store_true",
        help="hash likely whole-archive duplicates before excluding them",
    )
    content_parser.set_defaults(func=cmd_content_audit)

    prune_parser = subparsers.add_parser(
        "prune", help="quarantine verified byte-identical copies"
    )
    prune_parser.add_argument("--apply", action="store_true")
    prune_parser.add_argument("--quarantine", type=Path)
    prune_parser.add_argument("--verbose", action="store_true")
    prune_parser.set_defaults(func=cmd_prune)

    doctor_parser = subparsers.add_parser(
        "doctor", help="check archives, conflicts, and dependencies"
    )
    doctor_parser.add_argument("--refresh", action="store_true")
    doctor_parser.add_argument("--limit", type=int, default=20)
    doctor_parser.add_argument(
        "--all", action="store_true", help="check hidden packages too"
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    install_parser = subparsers.add_parser(
        "install", help="install local .var archives without duplicating IDs"
    )
    install_parser.add_argument("archives", nargs="+")
    install_parser.add_argument(
        "--link", action="store_true", help="hard-link, not copy"
    )
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    uninstall_parser = subparsers.add_parser(
        "uninstall", help="quarantine a package family or exact package ID"
    )
    uninstall_parser.add_argument("selector", help="creator.package[.version]")
    uninstall_parser.add_argument("--yes", action="store_true")
    uninstall_parser.add_argument("--force", action="store_true")
    uninstall_parser.add_argument("--quarantine", type=Path)
    uninstall_parser.set_defaults(func=cmd_uninstall)

    restore_parser = subparsers.add_parser(
        "restore", help="restore files from a quarantine manifest"
    )
    restore_parser.add_argument("manifest", type=Path)
    restore_parser.add_argument("--yes", action="store_true")
    restore_parser.set_defaults(func=cmd_restore)

    profile_parser = subparsers.add_parser(
        "profile", help="manage small, dependency-closed active package sets"
    )
    profile_commands = profile_parser.add_subparsers(
        dest="profile_command", required=True
    )
    profile_create = profile_commands.add_parser(
        "create", help="resolve roots and save an exact package profile"
    )
    profile_create.add_argument("name")
    profile_create.add_argument("packages", nargs="+", help="root package selectors")
    profile_create.add_argument("--replace", action="store_true")
    profile_create.add_argument("--allow-missing", action="store_true")
    profile_create.set_defaults(func=cmd_profile_create)

    profile_list = profile_commands.add_parser("list", help="list saved profiles")
    profile_list.set_defaults(func=cmd_profile_list)

    profile_show = profile_commands.add_parser("show", help="show a saved profile")
    profile_show.add_argument("name")
    profile_show.add_argument("--packages", action="store_true")
    profile_show.set_defaults(func=cmd_profile_show)

    profile_activate = profile_commands.add_parser(
        "activate", help="hide everything outside a profile dependency closure"
    )
    profile_activate.add_argument("name")
    profile_activate.add_argument("--apply", action="store_true")
    profile_activate.add_argument("--verbose", action="store_true")
    profile_activate.set_defaults(func=cmd_profile_activate)

    profile_rollback = profile_commands.add_parser(
        "rollback", help="undo one profile activation manifest"
    )
    profile_rollback.add_argument("manifest", type=Path)
    profile_rollback.add_argument("--apply", action="store_true")
    profile_rollback.set_defaults(func=cmd_profile_rollback)

    manager_parser = subparsers.add_parser(
        "manager",
        help="run the Linux package browser, leases, and managed active set",
    )
    manager_commands = manager_parser.add_subparsers(
        dest="manager_command", required=True
    )

    manager_configure = manager_commands.add_parser(
        "configure", help="remember the VaM AddonPackages directory"
    )
    manager_configure.add_argument("path", type=Path)
    manager_configure.set_defaults(func=cmd_manager_configure)

    manager_status = manager_commands.add_parser(
        "status", help="show manager, VaM, package, pin, and lease state"
    )
    manager_status.set_defaults(func=cmd_manager_status)

    manager_scan = manager_commands.add_parser(
        "scan", help="refresh the package inventory"
    )
    manager_scan.set_defaults(func=cmd_manager_scan)

    manager_catalog = manager_commands.add_parser(
        "catalog", help="import and inspect the external resource catalogue"
    )
    manager_catalog_commands = manager_catalog.add_subparsers(
        dest="manager_catalog_command", required=True
    )
    manager_catalog_import = manager_catalog_commands.add_parser(
        "import", help="import BrowserAssist resources and annotations"
    )
    manager_catalog_import.set_defaults(func=cmd_manager_catalog_import)
    manager_catalog_facets = manager_catalog_commands.add_parser(
        "facets", help="show resource types, creators, and tags"
    )
    manager_catalog_facets.set_defaults(func=cmd_manager_catalog_facets)

    manager_session_plugins = manager_commands.add_parser(
        "session-plugins",
        help="inspect or pin VaM's default Session Plugins preset",
    )
    manager_session_plugin_commands = manager_session_plugins.add_subparsers(
        dest="manager_session_plugin_command",
        required=True,
    )
    manager_session_plugins_list = manager_session_plugin_commands.add_parser(
        "list",
        help="show default session plugins and their package state",
    )
    manager_session_plugins_list.set_defaults(
        func=cmd_manager_session_plugins_list
    )
    manager_session_plugins_import = (
        manager_session_plugin_commands.add_parser(
            "import",
            help="pin packaged plugins from the default session preset",
        )
    )
    manager_session_plugins_import.add_argument(
        "--include-disabled",
        action="store_true",
        help="also pin session-plugin slots disabled in the preset",
    )
    manager_session_plugins_import.add_argument(
        "--apply",
        action="store_true",
        help="reconcile immediately when managed mode is active",
    )
    manager_session_plugins_import.set_defaults(
        func=cmd_manager_session_plugins_import
    )

    manager_packages = manager_commands.add_parser(
        "packages", help="search indexed package archives"
    )
    manager_packages.add_argument("query", nargs="?", default="")
    manager_packages.add_argument(
        "--state",
        choices=("all", "active", "hidden", "invalid"),
        default="all",
    )
    manager_packages.add_argument("--limit", type=int, default=100)
    manager_packages.add_argument("--offset", type=int, default=0)
    manager_packages.set_defaults(func=cmd_manager_packages)

    manager_resources = manager_commands.add_parser(
        "resources", help="search BrowserAssist scenes, presets, and assets"
    )
    manager_resources.add_argument("query", nargs="?", default="")
    manager_resources.add_argument("--type", default="")
    manager_resources.add_argument(
        "--state",
        choices=("all", "active", "hidden", "missing", "local"),
        default="all",
    )
    manager_resources.add_argument(
        "--favorite",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    manager_resources.add_argument("--limit", type=int, default=100)
    manager_resources.add_argument("--offset", type=int, default=0)
    manager_resources.set_defaults(func=cmd_manager_resources)

    manager_pin = manager_commands.add_parser(
        "pin", help="add package roots to the permanent base set"
    )
    manager_pin.add_argument("packages", nargs="+")
    manager_pin.add_argument("--label")
    manager_pin.add_argument("--apply", action="store_true")
    manager_pin.set_defaults(func=cmd_manager_pin)

    manager_unpin = manager_commands.add_parser(
        "unpin", help="remove one package root from the permanent base set"
    )
    manager_unpin.add_argument("package")
    manager_unpin.add_argument("--apply", action="store_true")
    manager_unpin.set_defaults(func=cmd_manager_unpin)

    manager_lease = manager_commands.add_parser(
        "lease", help="enable package roots and their dependencies temporarily"
    )
    manager_lease.add_argument("packages", nargs="+")
    manager_lease.add_argument("--days", type=float, default=3.0)
    manager_lease.add_argument("--label")
    manager_lease.add_argument(
        "--no-apply",
        action="store_true",
        help="save the lease without changing packages yet",
    )
    manager_lease.set_defaults(func=cmd_manager_lease)

    manager_renew = manager_commands.add_parser(
        "renew", help="extend a lease from its current expiry"
    )
    manager_renew.add_argument("lease_id")
    manager_renew.add_argument("--days", type=float, default=3.0)
    manager_renew.set_defaults(func=cmd_manager_renew)

    manager_release = manager_commands.add_parser(
        "release", help="remove a lease and reconcile when safe"
    )
    manager_release.add_argument("lease_id")
    manager_release.add_argument("--no-apply", action="store_true")
    manager_release.set_defaults(func=cmd_manager_release)

    manager_reconcile = manager_commands.add_parser(
        "reconcile", help="preview or apply the pinned + leased active set"
    )
    manager_reconcile.add_argument("--apply", action="store_true")
    manager_reconcile.add_argument(
        "--activate",
        action="store_true",
        help="capture the current baseline and enter managed mode",
    )
    manager_reconcile.set_defaults(func=cmd_manager_reconcile)

    manager_deactivate = manager_commands.add_parser(
        "deactivate", help="restore the exact package state from before managed mode"
    )
    manager_deactivate.add_argument("--apply", action="store_true")
    manager_deactivate.set_defaults(func=cmd_manager_deactivate)

    manager_rollback = manager_commands.add_parser(
        "rollback", help="undo one journalled manager switch"
    )
    manager_rollback.add_argument("manifest", type=Path)
    manager_rollback.add_argument("--apply", action="store_true")
    manager_rollback.set_defaults(func=cmd_manager_rollback)

    manager_bridge = manager_commands.add_parser(
        "bridge", help="install the optional live-rescan VaM session plugin"
    )
    manager_bridge_commands = manager_bridge.add_subparsers(
        dest="manager_bridge_command", required=True
    )
    manager_bridge_install = manager_bridge_commands.add_parser(
        "install", help="copy the loose bridge source into VaM"
    )
    manager_bridge_install.add_argument("--force", action="store_true")
    manager_bridge_install.set_defaults(func=cmd_manager_bridge_install)

    manager_launch = manager_commands.add_parser(
        "launch", help="reconcile the managed set and start VaM through Proton"
    )
    manager_launch.add_argument(
        "--no-reconcile",
        action="store_true",
        help="launch without first applying the current managed set",
    )
    manager_launch.set_defaults(func=cmd_manager_launch)

    manager_serve = manager_commands.add_parser(
        "serve", help="start the local package-manager web interface"
    )
    manager_serve.add_argument("--host", default="127.0.0.1")
    manager_serve.add_argument("--port", type=int, default=8787)
    manager_serve.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="open the manager in the default browser",
    )
    manager_serve.set_defaults(func=cmd_manager_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.state_dir = args.state_dir.expanduser().resolve()
    try:
        if args.command == "manager":
            return int(args.func(args))
        with manager_lock(args.state_dir):
            return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

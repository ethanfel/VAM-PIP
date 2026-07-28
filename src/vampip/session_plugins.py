from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from vampip.models import parse_dependency_ref


DEFAULT_SESSION_PLUGIN_PRESET = Path(
    "Custom/PluginPresets/Plugins_UserDefaults.vap"
)
MAX_SESSION_PLUGIN_PRESET_BYTES = 16 * 1024 * 1024

_PLUGIN_SLOT = re.compile(r"^plugin#(?P<index>[0-9]+)$")
_PLUGIN_STORABLE = re.compile(r"^plugin#(?P<index>[0-9]+)(?:_|$)")


class SessionPluginPresetError(ValueError):
    """Raised when a session-plugin preset cannot be trusted."""


@dataclass(frozen=True)
class SessionPlugin:
    """One PluginManager slot from VaM's session-plugin defaults."""

    slot: str
    slot_index: int
    source: str
    source_path: str
    package_ref: str | None
    enabled: bool
    packaged: bool
    loose: bool

    def __post_init__(self) -> None:
        if self.packaged == self.loose:
            raise ValueError("a session plugin must be either packaged or loose")


@dataclass(frozen=True)
class SessionPluginPreset:
    """A validated snapshot of VaM's default session plugins."""

    path: Path
    exists: bool
    plugins: tuple[SessionPlugin, ...]
    package_roots: tuple[str, ...]
    enabled_package_roots: tuple[str, ...]

    @property
    def enabled_plugins(self) -> tuple[SessionPlugin, ...]:
        return tuple(plugin for plugin in self.plugins if plugin.enabled)

    @property
    def loose_plugins(self) -> tuple[SessionPlugin, ...]:
        return tuple(plugin for plugin in self.plugins if plugin.loose)


def _error(path: Path, detail: str) -> SessionPluginPresetError:
    return SessionPluginPresetError(f"{path}: {detail}")


def _unique_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SessionPluginPresetError(
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _decode_json(data: bytes, path: Path) -> Any:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _error(path, f"preset is not valid UTF-8: {exc}") from exc

    try:
        return json.loads(text, object_pairs_hook=_unique_json_object)
    except SessionPluginPresetError as exc:
        raise _error(path, str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise _error(
            path,
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}",
        ) from exc


def _enabled_value(value: Any, path: Path, storable_id: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise _error(
        path,
        f"storable {storable_id!r} has an invalid enabled value; "
        "expected true or false",
    )


def _split_plugin_source(
    source: str,
    path: Path,
    slot: str,
) -> tuple[str, str | None]:
    if not source or source != source.strip():
        raise _error(path, f"{slot!r} has an empty or padded source path")
    if "\x00" in source or "\r" in source or "\n" in source:
        raise _error(path, f"{slot!r} has an invalid source path")

    separator = -1
    for candidate in (":/", ":\\"):
        index = source.find(candidate)
        if index >= 0 and (separator < 0 or index < separator):
            separator = index

    if separator < 0:
        if ":" in source:
            raise _error(
                path,
                f"{slot!r} has a malformed packaged source reference",
            )
        return source, None

    root_text = source[:separator]
    dependency = parse_dependency_ref(root_text)
    if dependency is None:
        raise _error(
            path,
            f"{slot!r} has an invalid package reference {root_text!r}",
        )
    source_path = source[separator + 1 :]
    if len(source_path) < 2:
        raise _error(path, f"{slot!r} has an empty packaged source path")
    return source_path, dependency.full_id


def _deduplicate_package_roots(
    plugins: tuple[SessionPlugin, ...],
    *,
    enabled_only: bool,
) -> tuple[str, ...]:
    roots: dict[str, str] = {}
    for plugin in plugins:
        if plugin.package_ref is None:
            continue
        if enabled_only and not plugin.enabled:
            continue
        roots.setdefault(plugin.package_ref.casefold(), plugin.package_ref)
    return tuple(roots.values())


def parse_session_plugin_preset(
    data: bytes,
    *,
    path: str | Path = DEFAULT_SESSION_PLUGIN_PRESET,
) -> SessionPluginPreset:
    """Parse and validate the bytes of a VaM session-plugin preset.

    The returned plugin order matches the order in PluginManager.plugins.
    A plugin with no corresponding storable defaults to enabled, as VaM does.
    """

    source_path = Path(path)
    if len(data) > MAX_SESSION_PLUGIN_PRESET_BYTES:
        raise _error(
            source_path,
            "preset exceeds the "
            f"{MAX_SESSION_PLUGIN_PRESET_BYTES // (1024 * 1024)} MiB "
            "safety limit",
        )

    document = _decode_json(data, source_path)
    if not isinstance(document, dict):
        raise _error(source_path, "top-level JSON value must be an object")

    storables = document.get("storables")
    if not isinstance(storables, list):
        raise _error(source_path, "'storables' must be an array")

    plugin_manager: dict[str, Any] | None = None
    enabled_by_index: dict[int, bool] = {}
    for position, storable in enumerate(storables):
        if not isinstance(storable, dict):
            raise _error(
                source_path,
                f"storable at index {position} must be an object",
            )
        storable_id = storable.get("id")
        if not isinstance(storable_id, str) or not storable_id:
            raise _error(
                source_path,
                f"storable at index {position} must have a non-empty string id",
            )

        if storable_id == "PluginManager":
            if plugin_manager is not None:
                raise _error(
                    source_path,
                    "preset contains more than one PluginManager storable",
                )
            plugin_manager = storable
            continue

        match = _PLUGIN_STORABLE.match(storable_id)
        if match is None or "enabled" not in storable:
            continue
        index = int(match.group("index"))
        if index in enabled_by_index:
            raise _error(
                source_path,
                f"more than one enabled state exists for plugin#{index}",
            )
        enabled_by_index[index] = _enabled_value(
            storable["enabled"],
            source_path,
            storable_id,
        )

    if plugin_manager is None:
        parsed_plugins: tuple[SessionPlugin, ...] = ()
    else:
        plugin_mapping = plugin_manager.get("plugins")
        if not isinstance(plugin_mapping, dict):
            raise _error(
                source_path,
                "PluginManager.plugins must be an object",
            )

        plugins: list[SessionPlugin] = []
        seen_indices: set[int] = set()
        for slot, source in plugin_mapping.items():
            match = _PLUGIN_SLOT.match(slot)
            if match is None:
                raise _error(
                    source_path,
                    f"invalid PluginManager plugin slot {slot!r}",
                )
            index = int(match.group("index"))
            if index in seen_indices:
                raise _error(
                    source_path,
                    f"duplicate PluginManager slot number {index}",
                )
            seen_indices.add(index)

            if not isinstance(source, str):
                raise _error(
                    source_path,
                    f"{slot!r} source must be a string",
                )
            # VaM can retain a numbered, exactly empty slot after a plugin is
            # removed. It is not a plugin and any leftover storable state for
            # that slot has no package availability meaning.
            if source == "":
                continue
            plugin_path, package_ref = _split_plugin_source(
                source,
                source_path,
                slot,
            )
            packaged = package_ref is not None
            plugins.append(
                SessionPlugin(
                    slot=slot,
                    slot_index=index,
                    source=source,
                    source_path=plugin_path,
                    package_ref=package_ref,
                    enabled=enabled_by_index.get(index, True),
                    packaged=packaged,
                    loose=not packaged,
                )
            )
        parsed_plugins = tuple(plugins)

    return SessionPluginPreset(
        path=source_path,
        exists=True,
        plugins=parsed_plugins,
        package_roots=_deduplicate_package_roots(
            parsed_plugins,
            enabled_only=False,
        ),
        enabled_package_roots=_deduplicate_package_roots(
            parsed_plugins,
            enabled_only=True,
        ),
    )


def inspect_session_plugin_defaults(
    vam_root: str | Path,
    *,
    preset_path: str | Path = DEFAULT_SESSION_PLUGIN_PRESET,
    maximum_bytes: int = MAX_SESSION_PLUGIN_PRESET_BYTES,
) -> SessionPluginPreset:
    """Inspect Plugins_UserDefaults.vap below ``vam_root``.

    A missing preset is a valid empty result. Other I/O and validation failures
    are reported as SessionPluginPresetError so callers never need to handle
    implementation-specific JSON or Unicode exceptions.
    """

    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive")

    root = Path(vam_root)
    relative_path = Path(preset_path)
    path = relative_path if relative_path.is_absolute() else root / relative_path
    try:
        with path.open("rb") as handle:
            data = handle.read(maximum_bytes + 1)
    except FileNotFoundError:
        return SessionPluginPreset(
            path=path,
            exists=False,
            plugins=(),
            package_roots=(),
            enabled_package_roots=(),
        )
    except OSError as exc:
        raise _error(path, f"could not read preset: {exc}") from exc

    if len(data) > maximum_bytes:
        raise _error(
            path,
            f"preset exceeds the {maximum_bytes}-byte safety limit",
        )
    return parse_session_plugin_preset(data, path=path)


# The shorter name is convenient for manager-service callers.
load_session_plugin_defaults = inspect_session_plugin_defaults

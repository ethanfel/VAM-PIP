from __future__ import annotations

import os
from pathlib import Path


_VAM_PROCESS_NAMES = {
    "vam.exe",
    "vam",
}


def _windows_basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def find_vam_processes(proc_root: Path = Path("/proc")) -> list[int]:
    """Return VaM process IDs without matching arbitrary command-line text."""

    found: list[int] = []
    if not proc_root.is_dir():
        return found
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (
                (entry / "comm")
                .read_text(encoding="utf-8", errors="replace")
                .strip()
                .casefold()
            )
            raw_cmdline = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        arguments = [
            item.decode("utf-8", errors="replace")
            for item in raw_cmdline.split(b"\0")
            if item
        ]
        first_argument = _windows_basename(arguments[0]) if arguments else ""
        if comm in _VAM_PROCESS_NAMES or first_argument in _VAM_PROCESS_NAMES:
            found.append(int(entry.name))
    return sorted(found)


def vam_is_running(proc_root: Path = Path("/proc")) -> bool:
    return bool(find_vam_processes(proc_root))


def derive_vam_root(addon_dir: Path) -> Path:
    resolved = addon_dir.resolve()
    if resolved.name.casefold() != "addonpackages":
        raise ValueError(
            "the managed directory must be the VaM AddonPackages directory"
        )
    return resolved.parent


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)

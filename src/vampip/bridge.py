from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources
import json
import os
from pathlib import Path
import uuid

from vampip.runtime import atomic_write_text


PROTOCOL_VERSION = 1
BRIDGE_RELATIVE_DIR = Path("Saves") / "PluginData" / "VAMPip" / "Bridge"


def bridge_directory(vam_root: Path) -> Path:
    return vam_root.resolve() / BRIDGE_RELATIVE_DIR


def request_rescan(
    vam_root: Path,
    *,
    browser_assist: str = "auto",
) -> str:
    if browser_assist not in {"auto", "off"}:
        raise ValueError("browser_assist must be 'auto' or 'off'")
    request_id = uuid.uuid4().hex
    document = {
        "protocol": PROTOCOL_VERSION,
        "requestId": request_id,
        "command": "rescan",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "browserAssist": browser_assist,
    }
    path = bridge_directory(vam_root) / "request.json"
    atomic_write_text(
        path,
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
    )
    return request_id


def read_bridge_status(vam_root: Path) -> dict[str, object] | None:
    path = bridge_directory(vam_root) / "status.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or document.get("protocol") != PROTOCOL_VERSION:
        return None
    return document


def install_bridge(vam_root: Path, *, force: bool = False) -> list[Path]:
    destination = vam_root.resolve() / "Custom" / "Scripts" / "VAMPip" / "Bridge"
    destination.mkdir(parents=True, exist_ok=True)
    source_root = resources.files("vampip").joinpath("bridge_assets")
    installed: list[Path] = []
    for name in ("VAMPipBridge.cs", "VAMPipBridge.cslist"):
        payload = source_root.joinpath(name).read_bytes()
        target = destination / name
        if target.exists():
            current = target.read_bytes()
            if current == payload:
                installed.append(target)
                continue
            if not force:
                raise FileExistsError(
                    f"bridge file differs and will not be overwritten: {target}"
                )
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
        installed.append(target)
    return installed

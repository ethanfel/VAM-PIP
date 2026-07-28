from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path


_VAR_NAME = re.compile(
    r"^(?P<creator>[^.]+)\.(?P<package>.+)\."
    r"(?P<version>[0-9]+|latest)(?P<copy>_[0-9]+| \([0-9]+\))?\.var$",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"^(?P<creator>[^.]+)\.(?P<package>.+)\.(?P<version>[0-9]+|latest)$",
    re.IGNORECASE,
)
DISABLED_SUFFIX = ".vampip-disabled"


@dataclass(frozen=True)
class PackageName:
    creator: str
    package: str
    version: int | None
    version_text: str
    copy_suffix: str | None = None

    @property
    def family(self) -> str:
        return f"{self.creator}.{self.package}"

    @property
    def family_key(self) -> str:
        return self.family.casefold()

    @property
    def full_id(self) -> str:
        return f"{self.family}.{self.version_text}"

    @property
    def full_key(self) -> str:
        return self.full_id.casefold()

    @property
    def canonical_filename(self) -> str:
        return f"{self.full_id}.var"


@dataclass(frozen=True)
class DependencyRef:
    creator: str
    package: str
    version: int | None
    version_text: str

    @property
    def family(self) -> str:
        return f"{self.creator}.{self.package}"

    @property
    def family_key(self) -> str:
        return self.family.casefold()

    @property
    def full_id(self) -> str:
        return f"{self.family}.{self.version_text}"

    @property
    def full_key(self) -> str:
        return self.full_id.casefold()

    @property
    def is_latest(self) -> bool:
        return self.version is None


def parse_var_filename(path: str | Path) -> PackageName | None:
    name = Path(path).name
    if name.casefold().endswith(DISABLED_SUFFIX):
        name = name[: -len(DISABLED_SUFFIX)]
    match = _VAR_NAME.match(name)
    if not match:
        return None
    text = match.group("version")
    version = None if text.casefold() == "latest" else int(text)
    return PackageName(
        creator=match.group("creator"),
        package=match.group("package"),
        version=version,
        version_text="latest" if version is None else str(version),
        copy_suffix=match.group("copy"),
    )


def parse_dependency_ref(value: str) -> DependencyRef | None:
    match = _REFERENCE.match(value)
    if not match:
        return None
    text = match.group("version")
    version = None if text.casefold() == "latest" else int(text)
    return DependencyRef(
        creator=match.group("creator"),
        package=match.group("package"),
        version=version,
        version_text="latest" if version is None else str(version),
    )

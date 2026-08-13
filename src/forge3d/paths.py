from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import Forge3DError

_SAFE_NAME = re.compile(r"[^a-z0-9]+")
_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_WSL_UNC = re.compile(
    r"^\\\\wsl(?:\.localhost)?\\([^\\]+)\\(.*)$", re.IGNORECASE
)


def toolkit_root() -> Path:
    configured = os.environ.get("FORGE3D_TOOLKIT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def workspace_root(start: Path | None = None) -> Path:
    configured = os.environ.get("FORGE3D_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def output_root(root: Path | None = None) -> Path:
    configured = os.environ.get("FORGE3D_OUTPUT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (root or workspace_root()) / "output"


def slugify(value: str, fallback: str = "asset") -> str:
    slug = _SAFE_NAME.sub("-", value.strip().lower()).strip("-")
    return (slug or fallback)[:80]


def manual_windows_to_wsl(path: Path | str, distro: str | None = None) -> str:
    raw = str(path)
    if raw.startswith("/"):
        return raw

    unc = _WSL_UNC.match(raw)
    if unc:
        unc_distro, tail = unc.groups()
        if distro and unc_distro.casefold() != distro.casefold():
            raise Forge3DError(
                f"Path belongs to WSL distribution {unc_distro!r}, not {distro!r}"
            )
        return "/" + tail.replace("\\", "/").lstrip("/")

    match = _WINDOWS_DRIVE.match(raw)
    if match:
        drive, tail = match.groups()
        return f"/mnt/{drive.lower()}/{tail.replace(chr(92), '/')}"

    if raw.startswith("\\\\"):
        raise Forge3DError(
            "Network paths cannot be mapped safely into WSL; copy the file into "
            "the workspace first"
        )
    return raw.replace("\\", "/")


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

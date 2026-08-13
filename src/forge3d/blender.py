from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .errors import Forge3DError, ToolNotFoundError
from .paths import toolkit_root
from .process import CommandResult, CommandRunner

SUPPORTED_TASKS = frozenset(
    {
        "inspect",
        "validate",
        "normalize",
        "repair",
        "unwrap",
        "material",
        "lods",
        "collision",
        "turntable",
        "save",
        "export-glb",
        "procedural",
        "rig-humanoid",
        "rig-validate",
        "animation-validate",
        "retarget",
    }
)


def find_blender() -> Path | None:
    configured = os.environ.get("BLENDER_EXECUTABLE")
    if configured:
        candidate = Path(configured).expanduser()
        return candidate.resolve() if candidate.is_file() else None

    discovered = shutil.which("blender")
    if discovered:
        return Path(discovered).resolve()

    patterns = [
        r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(Path(path) for path in glob.glob(pattern))
    candidates.extend(_steam_blender_candidates())
    return sorted(candidates, key=lambda path: path.parent.name)[-1] if candidates else None


def _steam_blender_candidates() -> list[Path]:
    """Find Blender in every Steam library without requiring Steam on PATH."""
    steam_roots = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    library_files = [root / "steamapps" / "libraryfolders.vdf" for root in steam_roots]
    libraries = list(steam_roots)
    path_pattern = re.compile(r'^\s*"path"\s+"([^"]+)"', re.MULTILINE)
    for library_file in library_files:
        if not library_file.is_file():
            continue
        try:
            text = library_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libraries.extend(Path(value.replace(r"\\", "\\")) for value in path_pattern.findall(text))

    candidates: list[Path] = []
    seen: set[Path] = set()
    for library in libraries:
        candidate = library / "steamapps" / "common" / "Blender" / "blender.exe"
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved not in seen:
            candidates.append(resolved)
            seen.add(resolved)
    return candidates


class Blender:
    def __init__(
        self,
        *,
        root: Path | None = None,
        executable: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.root = (root or toolkit_root()).resolve()
        self.executable = executable or find_blender()
        self.runner = runner or CommandRunner()
        if not self.executable:
            raise ToolNotFoundError(
                "Blender was not found. Set BLENDER_EXECUTABLE to blender.exe."
            )

    @property
    def dispatcher(self) -> Path:
        return self.root / "blender" / "forge3d_task.py"

    def version(self) -> str:
        result = self.runner.run([str(self.executable), "--version"], check=False)
        line = (result.stdout or result.stderr).splitlines()
        return line[0].strip() if line else "unknown"

    def task(
        self,
        name: str,
        args: dict[str, Any],
        *,
        timeout: float | None = 1_800,
    ) -> CommandResult:
        if name not in SUPPORTED_TASKS:
            raise Forge3DError(f"Unsupported Blender task: {name}")
        if not self.dispatcher.is_file():
            raise ToolNotFoundError(
                f"Forge3D Blender task dispatcher is missing: {self.dispatcher}"
            )

        request = {"task": name, "args": _json_safe(args)}
        request_dir = _request_directory(args)
        request_dir.mkdir(parents=True, exist_ok=True)
        handle, request_name = tempfile.mkstemp(
            prefix=f".{name}-", suffix=".json", dir=request_dir
        )
        request_path = Path(request_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(request, stream, indent=2)
            command = [
                str(self.executable),
                "--background",
                "--python",
                str(self.dispatcher),
                "--",
                "--request",
                str(request_path),
            ]
            return self.runner.run(command, timeout=timeout)
        finally:
            request_path.unlink(missing_ok=True)

    def open(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        if resolved.is_dir():
            blend = resolved / "source.blend"
            if not blend.is_file():
                choices = sorted(resolved.glob("*.blend"))
                if not choices:
                    raise Forge3DError(f"No .blend file found in {resolved}")
                blend = choices[-1]
            resolved = blend
        if not resolved.is_file():
            raise Forge3DError(f"Asset does not exist: {resolved}")
        if resolved.suffix.casefold() != ".blend":
            raise Forge3DError(
                "Open expects a .blend file or a run folder. Process imported "
                "meshes first so the canonical source.blend exists."
            )
        try:
            subprocess.Popen(
                [str(self.executable), str(resolved)],
                cwd=resolved.parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise Forge3DError(f"Could not launch Blender: {exc}") from exc


def _request_directory(args: dict[str, Any]) -> Path:
    for key in ("output", "report", "input"):
        value = args.get(key)
        if value:
            candidate = Path(str(value)).expanduser().resolve()
            return candidate if candidate.is_dir() else candidate.parent
    return Path(tempfile.gettempdir())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value.resolve())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

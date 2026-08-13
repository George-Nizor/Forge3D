from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from typing import Any

from .blender import find_blender
from .paths import toolkit_root, workspace_root
from .process import CommandRunner, WSL


def find_godot() -> Path | None:
    configured = os.environ.get("GODOT_EXECUTABLE")
    if configured:
        candidate = Path(configured).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    patterns = [
        r"C:\Users\*\Godot Projects\Godot_v*-stable*_win64\*console.exe",
        r"C:\Program Files\Godot\godot*.exe",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(Path(path) for path in glob.glob(pattern))
    return sorted(candidates)[-1] if candidates else None


def check_environment(root: Path | None = None) -> dict[str, Any]:
    root = (root or workspace_root()).resolve()
    toolkit = toolkit_root()
    runner = CommandRunner()
    checks: list[dict[str, Any]] = []

    blender = find_blender()
    checks.append(
        _executable_check(
            "blender",
            blender,
            runner,
            ["--version"],
            required=True,
            fix="Install Blender 5.x (standalone or Steam), or set BLENDER_EXECUTABLE.",
        )
    )
    godot = find_godot()
    checks.append(
        _executable_check(
            "godot",
            godot,
            runner,
            ["--version"],
            required=True,
            fix="Set GODOT_EXECUTABLE to the Godot 4.6 console executable.",
        )
    )
    node = shutil.which("node")
    checks.append(
        _executable_check(
            "node",
            Path(node) if node else None,
            runner,
            ["--version"],
            required=True,
            fix="Install Node.js 22 or later.",
        )
    )
    nvidia = shutil.which("nvidia-smi")
    checks.append(
        _executable_check(
            "nvidia",
            Path(nvidia) if nvidia else None,
            runner,
            ["--query-gpu=name,memory.total", "--format=csv,noheader"],
            required=False,
            fix="Install/update the NVIDIA driver if local AI inference is needed.",
        )
    )

    try:
        wsl = WSL(runner=runner)
        version = wsl.run(["sh", "-lc", "printf '%s' \"$WSL_DISTRO_NAME\""], check=False)
        cuda = wsl.shell("nvidia-smi -L", check=False)
        checks.append(
            {
                "name": "wsl",
                "ok": version.returncode == 0 and cuda.returncode == 0,
                "required": False,
                "path": wsl.executable,
                "version": version.stdout.strip() or wsl.distro,
                "detail": cuda.stdout.strip() if cuda.returncode == 0 else cuda.stderr.strip(),
                "fix": "Install Ubuntu under WSL2 and enable NVIDIA CUDA passthrough.",
            }
        )
    except Exception as exc:
        checks.append(
            {
                "name": "wsl",
                "ok": False,
                "required": False,
                "detail": str(exc),
                "fix": "Install Ubuntu under WSL2 for local AI models.",
            }
        )

    file_checks = [
        (
            "blender-task-library",
            toolkit / "blender" / "forge3d_task.py",
            True,
        ),
        (
            "codex-plugin",
            toolkit / "plugins" / "forge3d" / ".codex-plugin" / "plugin.json",
            True,
        ),
        ("codex-mcp-config", toolkit / ".codex" / "config.toml", True),
    ]
    for name, path, required in file_checks:
        checks.append(
            {
                "name": name,
                "ok": path.is_file(),
                "required": required,
                "path": str(path),
                "fix": f"Run the repository setup for missing {name}.",
            }
        )
    required_ok = all(item["ok"] for item in checks if item["required"])
    return {
        "ok": required_ok,
        "root": str(root),
        "toolkit_root": str(toolkit),
        "checks": checks,
    }


def _executable_check(
    name: str,
    path: Path | None,
    runner: CommandRunner,
    version_args: list[str],
    *,
    required: bool,
    fix: str,
) -> dict[str, Any]:
    if path is None:
        return {
            "name": name,
            "ok": False,
            "required": required,
            "detail": "not found",
            "fix": fix,
        }
    result = runner.run([str(path), *version_args], check=False)
    output = (result.stdout or result.stderr).strip().splitlines()
    return {
        "name": name,
        "ok": result.returncode == 0,
        "required": required,
        "path": str(path),
        "version": output[0] if output else "unknown",
        "detail": result.stderr.strip() if result.returncode else "",
        "fix": fix,
    }

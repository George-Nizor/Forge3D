from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import CommandError, ToolNotFoundError
from .paths import manual_windows_to_wsl


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def run(
        self,
        command: Sequence[str | os.PathLike[str]],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        check: bool = True,
    ) -> CommandResult:
        args = [os.fspath(item) for item in command]
        try:
            completed = subprocess.run(
                args,
                cwd=cwd,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ToolNotFoundError(f"Executable not found: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_timeout_output(exc.stdout)
            stderr = _decode_timeout_output(exc.stderr)
            raise CommandError(args, 124, stdout, f"Timed out. {stderr}".strip()) from exc

        result = CommandResult(
            command=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode:
            raise CommandError(
                args, result.returncode, result.stdout, result.stderr
            )
        return result


def _decode_timeout_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def executable(name: str) -> str | None:
    return shutil.which(name)


class WSL:
    def __init__(
        self,
        distro: str | None = None,
        runner: CommandRunner | None = None,
        executable_path: str | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self.executable = (
            executable_path
            or os.environ.get("FORGE3D_WSL_EXECUTABLE")
            or executable("wsl.exe")
            or executable("wsl")
        )
        if not self.executable:
            raise ToolNotFoundError(
                "WSL was not found. Install WSL2 with Ubuntu before installing "
                "local AI models."
            )
        self.distro = (
            distro
            or os.environ.get("FORGE3D_WSL_DISTRO")
            or self.detect_default_distro()
        )

    def detect_default_distro(self) -> str:
        result = _clean_wsl_result(
            self.runner.run([self.executable, "--list", "--quiet"], check=False)
        )
        names = [
            line.replace("\x00", "").strip()
            for line in result.stdout.splitlines()
            if line.replace("\x00", "").strip()
        ]
        preferred = [
            name
            for name in names
            if "ubuntu" in name.casefold()
            and "docker" not in name.casefold()
        ]
        viable = [
            name for name in names if "docker" not in name.casefold()
        ]
        candidates = preferred or viable
        if not candidates:
            detail = result.stderr.strip() or "no distributions were returned"
            raise ToolNotFoundError(
                "No usable WSL distribution was found. Install Ubuntu in WSL2 "
                f"and retry ({detail})."
            )
        return candidates[0]

    def command(self, argv: Sequence[str]) -> list[str]:
        return [self.executable, "--distribution", self.distro, "--exec", *argv]

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        check: bool = True,
    ) -> CommandResult:
        if cwd is None and not env:
            return _checked_wsl_result(
                self.runner.run(
                    self.command(argv), timeout=timeout, check=False
                ),
                check=check,
            )

        fragments: list[str] = ["set -e"]
        if cwd:
            fragments.append(f"cd {shlex.quote(cwd)}")
        if env:
            assignments = " ".join(
                f"{key}={shlex.quote(value)}" for key, value in env.items()
            )
            fragments.append(f"export {assignments}")
        fragments.append(shlex.join(list(argv)))
        return self.shell(" && ".join(fragments), timeout=timeout, check=check)

    def shell(
        self,
        script: str,
        *,
        timeout: float | None = None,
        check: bool = True,
    ) -> CommandResult:
        return _checked_wsl_result(
            self.runner.run(
                self.command(["bash", "-lc", script]),
                timeout=timeout,
                check=False,
            ),
            check=check,
        )

    def path(self, path: Path | str) -> str:
        raw = str(path)
        result = self.run(["wslpath", "-a", "-u", raw], check=False)
        converted = result.stdout.strip()
        if result.returncode == 0 and converted:
            return converted
        return manual_windows_to_wsl(raw, self.distro)


def _clean_wsl_result(result: CommandResult) -> CommandResult:
    # Windows emits some WSL service failures as UTF-16-like text even when the
    # child process pipe is configured for UTF-8. Removing NUL separators keeps
    # diagnostics readable without altering normal Linux command output.
    return CommandResult(
        command=result.command,
        returncode=result.returncode,
        stdout=result.stdout.replace("\x00", ""),
        stderr=result.stderr.replace("\x00", ""),
    )


def _checked_wsl_result(result: CommandResult, *, check: bool) -> CommandResult:
    cleaned = _clean_wsl_result(result)
    if check and cleaned.returncode:
        raise CommandError(
            list(cleaned.command),
            cleaned.returncode,
            cleaned.stdout,
            cleaned.stderr,
        )
    return cleaned

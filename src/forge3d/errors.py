from __future__ import annotations


class Forge3DError(RuntimeError):
    """Expected user-facing failure."""


class ToolNotFoundError(Forge3DError):
    """A required executable or integration is unavailable."""


class CommandError(Forge3DError):
    """A child process returned a non-zero status."""

    def __init__(
        self,
        command: list[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        summary = stderr.strip() or stdout.strip() or "no process output"
        if len(summary) > 2_000:
            summary = summary[-2_000:]
        rendered = " ".join(_display_arg(item) for item in command)
        super().__init__(
            f"Command failed with exit code {returncode}: {rendered}\n{summary}"
        )


def _display_arg(value: str) -> str:
    if not value or any(char.isspace() for char in value):
        return repr(value)
    return value

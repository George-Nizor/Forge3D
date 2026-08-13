from __future__ import annotations

import sys
import unittest

from forge3d.errors import CommandError
from forge3d.process import CommandRunner, WSL


class StubRunner:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr

    def run(self, command: list[str], **_: object):
        from forge3d.process import CommandResult

        return CommandResult(tuple(command), self.returncode, self.stdout, self.stderr)


class ProcessTests(unittest.TestCase):
    def test_wsl_prefers_ubuntu_and_removes_utf16_nulls(self) -> None:
        runner = StubRunner("docker-desktop\x00\nUbuntu-24.04\x00\n")
        bridge = WSL(runner=runner, executable_path="wsl.exe")  # type: ignore[arg-type]
        self.assertEqual(bridge.distro, "Ubuntu-24.04")

    def test_command_error_includes_stderr_and_exit_code(self) -> None:
        with self.assertRaises(CommandError) as caught:
            CommandRunner().run(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('bad', file=sys.stderr); raise SystemExit(7)",
                ]
            )
        self.assertEqual(caught.exception.returncode, 7)
        self.assertIn("bad", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

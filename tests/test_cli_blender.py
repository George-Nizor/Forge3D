from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge3d.blender import Blender
from forge3d.process import CommandResult


class CapturingRunner:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None
        self.command: list[str] | None = None

    def run(self, command: list[str], **_: object) -> CommandResult:
        self.command = command
        request_path = Path(command[-1])
        self.request = json.loads(request_path.read_text(encoding="utf-8"))
        return CommandResult(tuple(command), 0, "ok", "")


class BlenderBridgeTests(unittest.TestCase):
    def test_task_uses_dispatcher_request_contract_and_cleans_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dispatcher = root / "blender" / "forge3d_task.py"
            dispatcher.parent.mkdir()
            dispatcher.write_text("# task", encoding="utf-8")
            executable = root / "blender.exe"
            executable.write_bytes(b"binary")
            output = root / "run" / "source.blend"
            runner = CapturingRunner()
            bridge = Blender(
                root=root,
                executable=executable,
                runner=runner,  # type: ignore[arg-type]
            )
            bridge.task(
                "normalize",
                {"input": root / "input.glb", "output": output, "force": True},
            )
            self.assertEqual(runner.request["task"], "normalize")  # type: ignore[index]
            args = runner.request["args"]  # type: ignore[index]
            self.assertEqual(args["output"], str(output.resolve()))  # type: ignore[index]
            self.assertIn("--request", runner.command)
            self.assertFalse(Path(runner.command[-1]).exists())


if __name__ == "__main__":
    unittest.main()

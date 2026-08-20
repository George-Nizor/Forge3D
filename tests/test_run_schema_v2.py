from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge3d.errors import Forge3DError
from forge3d.runs import Run


class RunSchemaV2Tests(unittest.TestCase):
    def test_new_run_records_relative_previewable_artifacts_and_codex_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = Run.create(name="Robot", command="make", base=root / "runs")
            preview = run.directory / "preview.gif"
            preview.write_bytes(b"GIF89a")
            step = run.start_step("render")
            run.finish_step(step, outputs={"preview": preview})
            run.record_codex_turn("thread-1", "turn-1")

            saved = json.loads(run.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], 2)
            self.assertEqual(saved["outputs"]["preview"], "preview.gif")
            self.assertEqual(saved["artifacts"][0]["media_type"], "image/gif")
            self.assertEqual(saved["artifacts"][0]["preview_role"], "animation")
            self.assertEqual(saved["codex"]["thread_id"], "thread-1")
            self.assertEqual(saved["codex"]["turn_ids"], ["turn-1"])

    def test_schema_v1_remains_readable_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "legacy"
            directory.mkdir()
            manifest = {
                "schema_version": 1,
                "run_id": "legacy-run",
                "name": "legacy",
                "status": "completed",
                "outputs": {"preview": str(directory / "preview.png")},
            }
            (directory / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
            loaded = Run.load(directory)
            self.assertEqual(loaded.manifest, manifest)

    def test_artifacts_cannot_escape_the_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.glb"
            outside.write_bytes(b"glTF")
            run = Run.create(name="Contained", command="process", base=root / "runs")
            step = run.start_step("export")
            with self.assertRaisesRegex(Forge3DError, "inside the run directory"):
                run.finish_step(step, outputs={"model": outside})

    def test_unknown_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "run.json").write_text(
                json.dumps({"schema_version": 99, "run_id": "future"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Forge3DError, "Unsupported run schema"):
                Run.load(directory)


if __name__ == "__main__":
    unittest.main()
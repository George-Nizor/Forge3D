from __future__ import annotations

import json
import os
import runpy
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from forge3d.cli import main
from forge3d.models import ModelRunResult, run_tripo_cloud
from forge3d.paths import slugify
from forge3d.runs import Run, file_hash
from forge3d.workflows import (
    prepare_animation_request,
    make_asset,
    process_asset,
    retarget_animation,
    rig_asset,
)


class FakeBlender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def version(self) -> str:
        return "Blender 5.0.0"

    def task(self, name: str, args: dict[str, object], **_: object) -> None:
        self.calls.append((name, args))
        output = args.get("output")
        report = args.get("report")
        if output:
            target = Path(str(output))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"{name}\n".encode())
        if report:
            target = Path(str(report))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps({"ok": True, "task": name}), encoding="utf-8"
            )


class RunTests(unittest.TestCase):
    def test_slugify_is_stable_and_safe(self) -> None:
        self.assertEqual(slugify(" Sci-Fi  Scanner!! "), "sci-fi-scanner")
        self.assertEqual(slugify(""), "asset")

    def test_run_directories_are_versioned_and_inputs_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source.png"
            source.write_bytes(b"reference")
            first = Run.create(
                name="Medical Scanner",
                command="make",
                prompt="scanner",
                inputs=[source],
                base=base / "output",
            )
            second = Run.create(
                name="Medical Scanner",
                command="make",
                inputs=[source],
                base=base / "output",
            )
            self.assertEqual(first.directory.name, "medical-scanner")
            self.assertEqual(second.directory.name, "medical-scanner-v002")
            self.assertEqual(
                first.manifest["inputs"][0]["sha256"], file_hash(source)
            )
            persisted = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["run_id"], first.manifest["run_id"])

    def test_process_creates_canonical_outputs_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "input.glb"
            source.write_bytes(b"mesh")
            blender = FakeBlender()
            run = process_asset(
                source=source,
                output_base=base / "output",
                blender=blender,  # type: ignore[arg-type]
                steps=("normalize", "repair", "unwrap"),
                render_preview=True,
            )
            self.assertEqual(run.manifest["status"], "completed")
            self.assertTrue((run.directory / "source.blend").is_file())
            self.assertTrue((run.directory / "model.glb").is_file())
            self.assertTrue((run.directory / "preview.png").is_file())
            self.assertTrue((run.directory / "validation.json").is_file())
            self.assertFalse((run.directory / ".working").exists())
            self.assertEqual(
                [name for name, _ in blender.calls],
                [
                    "normalize",
                    "repair",
                    "unwrap",
                    "save",
                    "export-glb",
                    "validate",
                    "turntable",
                ],
            )

    def test_image_to_mesh_stops_at_visual_review_gate(self) -> None:
        class FakeModelManager:
            def run_image(
                self,
                model: object,
                image: Path,
                output: Path,
                **_: object,
            ) -> ModelRunResult:
                output.mkdir(parents=True)
                artifact = output / "draft.glb"
                artifact.write_bytes(b"glTF")
                return ModelRunResult(
                    model="spar3d",
                    revision="test-revision",
                    artifact=artifact,
                    command=("spar3d", str(image)),
                    stdout="",
                    stderr="",
                )

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            reference = base / "reference.png"
            reference.write_bytes(b"image")
            run = make_asset(
                prompt="a hard-surface equipment case",
                name="case-draft",
                reference=reference,
                backend="spar3d",
                output_base=base / "output",
                manager=FakeModelManager(),  # type: ignore[arg-type]
                blender=FakeBlender(),  # type: ignore[arg-type]
            )

            self.assertEqual(run.manifest["status"], "awaiting_blender_review")
            self.assertTrue(run.manifest["quality_gate"]["visual_review_required"])
            self.assertTrue(
                run.manifest["quality_gate"]["orientation_review_required"]
            )
            self.assertIn("hard-surface", run.manifest["next_step"])

    def test_procedural_recipe_parameters_reach_blender(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            blender = FakeBlender()
            run = make_asset(
                prompt="a wide medical equipment case",
                name="medical-case",
                recipe="medical-case",
                recipe_params={"width": 1.2, "height": 0.55},
                output_base=base / "output",
                blender=blender,  # type: ignore[arg-type]
            )

            self.assertEqual(run.manifest["status"], "completed")
            task, args = blender.calls[0]
            self.assertEqual(task, "procedural")
            params = json.loads(str(args["params"]))
            self.assertEqual(params["width"], 1.2)
            self.assertEqual(params["height"], 0.55)
            self.assertIn("wide medical", params["prompt"])

    def test_animation_command_prepares_codex_request_without_claiming_completion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "character.blend"
            source.write_bytes(b"blend")
            run = prepare_animation_request(
                source=source,
                prompt="a relaxed idle loop",
                output_base=base / "output",
            )
            self.assertEqual(run.manifest["status"], "awaiting_codex")
            request = json.loads(
                (run.directory / "codex-animation-request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(request["prompt"], "a relaxed idle loop")

    def test_blender_rigify_is_the_direct_target_only_rig_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "humanoid.glb"
            source.write_bytes(b"mesh")
            blender = FakeBlender()
            run = rig_asset(
                source=source,
                output_base=base / "output",
                blender=blender,  # type: ignore[arg-type]
            )
            self.assertEqual(run.manifest["status"], "completed")
            self.assertEqual(run.manifest["settings"]["backend"], "blender")
            self.assertEqual(
                [name for name, _ in blender.calls],
                ["rig-humanoid", "rig-validate", "export-glb", "turntable"],
            )
            rig_args = blender.calls[0][1]
            self.assertEqual(rig_args["rig_name"], "Forge3D_Rig")
            validation_args = blender.calls[1][1]
            self.assertEqual(validation_args["objects"], "Forge3D_Rig")
            export_args = blender.calls[2][1]
            self.assertEqual(export_args["armature"], "Forge3D_Rig")
            self.assertTrue(export_args["deform_bones_only"])
            preview_args = blender.calls[3][1]
            self.assertEqual(preview_args["armature"], "Forge3D_Rig")

    def test_retarget_exports_and_previews_only_the_target_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "two-rigs.blend"
            source.write_bytes(b"blend")
            bone_map = base / "bone-map.json"
            bone_map.write_text('{"root": "root"}', encoding="utf-8")
            blender = FakeBlender()
            run = retarget_animation(
                source=source,
                source_armature="SourceRig",
                target_armature="TargetRig",
                bone_map=bone_map,
                output_base=base / "output",
                blender=blender,  # type: ignore[arg-type]
            )

            self.assertEqual(run.manifest["status"], "completed")
            self.assertEqual(
                [name for name, _ in blender.calls],
                [
                    "retarget",
                    "animation-validate",
                    "export-glb",
                    "turntable",
                ],
            )
            action = run.manifest["settings"]["action_name"]
            retarget_args = blender.calls[0][1]
            self.assertTrue(retarget_args["clear_constraints"])
            self.assertEqual(retarget_args["action_name"], action)
            validation_args = blender.calls[1][1]
            self.assertEqual(validation_args["actions"], action)
            export_args = blender.calls[2][1]
            self.assertEqual(export_args["armature"], "TargetRig")
            self.assertEqual(export_args["actions"], action)
            preview_args = blender.calls[3][1]
            self.assertEqual(preview_args["armature"], "TargetRig")


class CLITests(unittest.TestCase):
    def test_models_list_is_available_without_wsl(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            status = main(["models", "list"])
        self.assertEqual(status, 0)
        self.assertIn("triposg", output.getvalue())
        self.assertIn("skintokens", output.getvalue())

    def test_cloud_estimate_never_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "reference.png"
            source.write_bytes(b"image")
            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["models", "cloud-estimate", "tripo", str(source)]
                )
            self.assertEqual(status, 0)
            estimate = json.loads(output.getvalue())
            self.assertTrue(estimate["approval_required"])
            self.assertFalse(estimate["upload_performed"])
            self.assertIn("cloud-run", estimate["next_step"])

    def test_cloud_run_refuses_without_per_job_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "reference.png"
            destination = Path(temporary) / "cloud"
            source.write_bytes(b"image")
            error = StringIO()
            with patch.dict(
                os.environ, {"TRIPO_API_KEY": "not-used"}, clear=False
            ):
                with redirect_stderr(error):
                    status = main(
                        [
                            "models",
                            "cloud-run",
                            "tripo",
                            str(source),
                            "--output-dir",
                            str(destination),
                        ]
                    )
            self.assertEqual(status, 2)
            self.assertIn("--approve-upload", error.getvalue())
            self.assertFalse(destination.exists())

    def test_cloud_run_refuses_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "reference.png"
            destination = Path(temporary) / "cloud"
            source.write_bytes(b"image")
            error = StringIO()
            with patch.dict(os.environ, {"TRIPO_API_KEY": ""}, clear=False):
                with redirect_stderr(error):
                    status = main(
                        [
                            "models",
                            "cloud-run",
                            "tripo",
                            str(source),
                            "--output-dir",
                            str(destination),
                            "--approve-upload",
                        ]
                    )
            self.assertEqual(status, 2)
            self.assertIn("TRIPO_API_KEY", error.getvalue())
            self.assertFalse(destination.exists())

    def test_cloud_script_has_an_independent_approval_gate(self) -> None:
        script = Path(__file__).parents[1] / "scripts" / "tripo_cloud.py"
        cloud_main = runpy.run_path(str(script))["main"]
        error = StringIO()
        with patch.dict(
            os.environ, {"TRIPO_API_KEY": "not-used"}, clear=False
        ):
            with redirect_stderr(error):
                status = cloud_main(
                    [
                        "not-uploaded.png",
                        "--output-dir",
                        "not-created",
                    ]
                )
        self.assertEqual(status, 2)
        self.assertIn("--approve-upload", error.getvalue())

    def test_cloud_runner_pins_sdk_and_never_places_key_in_command(self) -> None:
        class FakeRunner:
            def __init__(self) -> None:
                self.command: tuple[str, ...] = ()

            def run(self, command: list[str], **_: object) -> None:
                self.command = tuple(command)
                output = Path(command[command.index("--output-dir") + 1])
                output.mkdir()
                (output / "model.glb").write_bytes(b"glTF")
                (output / "cloud-result.json").write_text(
                    json.dumps(
                        {
                            "status": "success",
                            "files": {"model": str(output / "model.glb")},
                        }
                    ),
                    encoding="utf-8",
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reference.png"
            source.write_bytes(b"image")
            fake = FakeRunner()
            with patch.dict(
                os.environ, {"TRIPO_API_KEY": "secret-test-key"}, clear=False
            ):
                result = run_tripo_cloud(
                    source,
                    root / "cloud",
                    approve_upload=True,
                    model_version="P1-20260311",
                    faces=12_000,
                    runner=fake,  # type: ignore[arg-type]
                    uv_executable="uv",
                )
            self.assertEqual(result["status"], "success")
            self.assertIn("tripo3d==0.4.2", fake.command)
            self.assertIn("--approve-upload", fake.command)
            self.assertIn("--faces", fake.command)
            self.assertNotIn("secret-test-key", fake.command)

    def test_expected_errors_have_nonzero_status(self) -> None:
        error = StringIO()
        with redirect_stderr(error):
            status = main(["validate", "does-not-exist.glb"])
        self.assertEqual(status, 2)
        self.assertIn("does not exist", error.getvalue())

    def test_free_form_make_never_silently_builds_a_crate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            error = StringIO()
            with patch.dict(os.environ, {"FORGE3D_ROOT": str(root)}, clear=False):
                with redirect_stderr(error):
                    status = main(["make", "a medieval lantern"])
            self.assertEqual(status, 2)
            self.assertIn("free-form prompt", error.getvalue())
            self.assertFalse((root / "output").exists())

    def test_image_to_mesh_auto_requires_an_explicit_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.png"
            reference.write_bytes(b"image")
            output = root / "output"
            error = StringIO()
            with redirect_stderr(error):
                status = main(
                    [
                        "make",
                        "an organic prop",
                        "--reference",
                        str(reference),
                        "--output-dir",
                        str(output),
                    ]
                )
            self.assertEqual(status, 2)
            self.assertIn(
                "Automatic image-to-mesh selection is disabled",
                error.getvalue(),
            )
            self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()

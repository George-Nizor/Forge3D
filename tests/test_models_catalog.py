from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from forge3d.errors import Forge3DError
from forge3d.models import (
    MODELS,
    ModelManager,
    _image_command,
    cloud_estimate,
    get_model,
)
from forge3d.paths import manual_windows_to_wsl
from forge3d.process import CommandResult


class FakeWSL:
    distro = "Ubuntu-24.04"
    executable = "wsl.exe"

    def __init__(self) -> None:
        self.scripts: list[str] = []

    def run(self, argv: list[str], **_: object) -> CommandResult:
        if argv[:2] == ["printenv", "HOME"]:
            return CommandResult(tuple(argv), 0, "/home/george\n", "")
        if argv[:2] == ["test", "-x"]:
            return CommandResult(tuple(argv), 1, "", "")
        return CommandResult(tuple(argv), 0, "", "")

    def shell(self, script: str, **_: object) -> CommandResult:
        self.scripts.append(script)
        return CommandResult(("bash", "-lc", script), 0, "abc123\n", "")

    def path(self, path: Path) -> str:
        return "/mnt/c/workspace/" + path.name


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_contains_only_intentional_core_and_optional_models(self) -> None:
        self.assertEqual(
            set(MODELS),
            {
                "triposplat",
                "triposg",
                "spar3d",
                "partcrafter",
                "skintokens",
                "unirig",
            },
        )
        self.assertTrue(get_model("triposg").acceptance_required)
        self.assertTrue(get_model("spar3d").acceptance_required)
        self.assertTrue(get_model("partcrafter").acceptance_required)

    def test_spar3d_license_gate_is_enforced_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake = FakeWSL()
            manager = ModelManager(root=Path(temporary), wsl=fake)  # type: ignore[arg-type]
            with self.assertRaisesRegex(Forge3DError, "explicit acceptance"):
                manager.install(get_model("spar3d"))
            self.assertEqual(fake.scripts, [])

            manager.install(get_model("spar3d"), accept_license=True)
            record = (
                Path(temporary) / ".forge3d" / "licenses" / "spar3d.json"
            )
            self.assertTrue(record.is_file())
            self.assertEqual(json.loads(record.read_text())["model"], "spar3d")

    def test_acceptance_record_must_match_current_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = ModelManager(
                root=Path(temporary), wsl=FakeWSL()  # type: ignore[arg-type]
            )
            model = get_model("triposg")
            manager.record_license_acceptance(model)
            self.assertTrue(manager.license_accepted(model))
            changed = replace(model, license_name=model.license_name + " updated")
            self.assertFalse(manager.license_accepted(changed))

    def test_restricted_model_cannot_run_without_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.png"
            image.write_bytes(b"image")
            manager = ModelManager(
                root=root, wsl=FakeWSL()  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(Forge3DError, "explicit acceptance"):
                manager.run_image(
                    get_model("triposg"),
                    image,
                    root / "output",
                )

    def test_triposplat_rejects_invalid_density_before_starting_wsl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "reference.png"
            image.write_bytes(b"image")
            manager = ModelManager(
                root=root, wsl=FakeWSL()  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(Forge3DError, "multiple of 32"):
                manager.run_image(
                    get_model("triposplat"),
                    image,
                    root / "output",
                    gaussians=100_001,
                )
            self.assertFalse((root / "output").exists())

    def test_install_plan_is_explicit_and_non_destructive(self) -> None:
        fake = FakeWSL()
        manager = ModelManager(root=Path.cwd(), wsl=fake)  # type: ignore[arg-type]
        script = manager.install_plan(get_model("triposg"), "main")
        self.assertIn("github.com/VAST-AI-Research/TripoSG.git", script)
        self.assertIn("uv venv --python 3.10", script)
        self.assertIn("diso_shim.py", script)
        self.assertIn("triposg-constraints.txt", script)
        self.assertIn("VAST-AI/TripoSG", script)
        self.assertIn("briaai/RMBG-1.4", script)
        self.assertNotIn(
            "uv pip install --python .venv/bin/python -r requirements.txt",
            script,
        )
        self.assertNotIn("rm -r", script)

        splat_script = manager.install_plan(get_model("triposplat"), "main")
        self.assertIn("/models/TripoSplat", splat_script)
        self.assertIn(".forge3d_run.py", splat_script)
        self.assertIn("VAST-AI/TripoSplat", splat_script)
        self.assertIn(".forge3d-install-complete", splat_script)

    def test_unsafe_revision_is_rejected(self) -> None:
        manager = ModelManager(root=Path.cwd(), wsl=FakeWSL())  # type: ignore[arg-type]
        with self.assertRaisesRegex(Forge3DError, "Unsafe git revision"):
            manager.install_plan(get_model("triposplat"), "main; touch /tmp/no")

    def test_image_commands_match_upstream_interfaces(self) -> None:
        command, expected = _image_command(
            get_model("triposg"),
            model_dir="/models/triposg",
            image="/mnt/c/ref.png",
            output="/mnt/c/out",
            tag="asset",
            faces=50_000,
            parts=4,
            low_vram=False,
            gaussians=262_144,
        )
        self.assertEqual(command[:4], [".venv/bin/python", "-m", "scripts.inference_triposg", "--image-input"])
        self.assertIn("--faces", command)
        self.assertEqual(expected, Path("candidate.glb"))

        command, _ = _image_command(
            get_model("spar3d"),
            model_dir="/models/spar3d",
            image="/mnt/c/ref.png",
            output="/mnt/c/out",
            tag="asset",
            faces=None,
            parts=4,
            low_vram=True,
            gaussians=262_144,
        )
        self.assertIn("--low-vram-mode", command)

        command, expected = _image_command(
            get_model("triposplat"),
            model_dir="/models/TripoSplat",
            image="/mnt/c/ref.png",
            output="/mnt/c/out",
            tag="asset",
            faces=None,
            parts=4,
            low_vram=False,
            gaussians=131_072,
        )
        self.assertIn("--gaussians", command)
        self.assertIn("131072", command)
        self.assertEqual(expected, Path("candidate.ply"))

    def test_manual_windows_and_wsl_unc_conversion(self) -> None:
        self.assertEqual(
            manual_windows_to_wsl(r"C:\Users\George\file.glb"),
            "/mnt/c/Users/George/file.glb",
        )
        self.assertEqual(
            manual_windows_to_wsl(
                r"\\wsl.localhost\Ubuntu-24.04\home\george\file.glb",
                "Ubuntu-24.04",
            ),
            "/home/george/file.glb",
        )
        with self.assertRaises(Forge3DError):
            manual_windows_to_wsl(r"\\server\share\file.glb")

    def test_cloud_estimate_has_no_network_or_submission_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "image.png"
            source.write_bytes(b"x")
            with patch("urllib.request.urlopen") as network:
                estimate = cloud_estimate("meshy", [source])
            network.assert_not_called()
            self.assertFalse(estimate["upload_performed"])
            self.assertTrue(estimate["approval_required"])


if __name__ == "__main__":
    unittest.main()

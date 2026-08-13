from __future__ import annotations

import base64
import glob
import json
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = ROOT / "godot"


def find_godot() -> Path | None:
    configured = os.environ.get("GODOT_EXECUTABLE")
    if configured and Path(configured).is_file():
        return Path(configured)
    candidates: list[Path] = []
    for pattern in (
        r"C:\Users\*\Godot Projects\Godot_v*-stable*_win64\*console.exe",
        r"C:\Program Files\Godot\godot*.exe",
    ):
        candidates.extend(Path(value) for value in glob.glob(pattern))
    return sorted(candidates)[-1] if candidates else None


def write_animated_skinned_gltf(path: Path) -> None:
    positions = struct.pack(
        "<9f",
        -0.5,
        0.0,
        0.0,
        0.5,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
    )
    joints = struct.pack("<12H", *(0 for _ in range(12)))
    weights = struct.pack(
        "<12f",
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
    )
    times = struct.pack("<2f", 0.0, 1.0)
    translations = struct.pack("<6f", 0.0, 0.0, 0.0, 0.0, 0.1, 0.0)
    binary = positions + joints + weights + times + translations
    encoded = base64.b64encode(binary).decode("ascii")
    document = {
        "asset": {"version": "2.0", "generator": "Forge3D review test"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": "CharacterMesh", "mesh": 0, "skin": 0},
            {"name": "RootBone"},
        ],
        "skins": [{"name": "Armature", "joints": [1], "skeleton": 1}],
        "meshes": [
            {
                "name": "Character",
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "JOINTS_0": 1,
                            "WEIGHTS_0": 2,
                        },
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "TestMaterial",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.7, 0.7, 0.8, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.8,
                },
            }
        ],
        "animations": [
            {
                "name": "Walk",
                "samplers": [
                    {"input": 3, "output": 4, "interpolation": "LINEAR"}
                ],
                "channels": [
                    {
                        "sampler": 0,
                        "target": {"node": 1, "path": "translation"},
                    }
                ],
            }
        ],
        "buffers": [
            {
                "byteLength": len(binary),
                "uri": f"data:application/octet-stream;base64,{encoded}",
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36, "target": 34962},
            {"buffer": 0, "byteOffset": 36, "byteLength": 24, "target": 34962},
            {"buffer": 0, "byteOffset": 60, "byteLength": 48, "target": 34962},
            {"buffer": 0, "byteOffset": 108, "byteLength": 8},
            {"buffer": 0, "byteOffset": 116, "byteLength": 24},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [-0.5, 0.0, 0.0],
                "max": [0.5, 1.0, 0.0],
            },
            {
                "bufferView": 1,
                "componentType": 5123,
                "count": 3,
                "type": "VEC4",
            },
            {
                "bufferView": 2,
                "componentType": 5126,
                "count": 3,
                "type": "VEC4",
            },
            {
                "bufferView": 3,
                "componentType": 5126,
                "count": 2,
                "type": "SCALAR",
                "min": [0.0],
                "max": [1.0],
            },
            {
                "bufferView": 4,
                "componentType": 5126,
                "count": 2,
                "type": "VEC3",
            },
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


@unittest.skipUnless(find_godot(), "Godot console executable is unavailable")
class GodotReviewExpectationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.godot = find_godot()

    def run_review(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        assert self.godot is not None
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asset = directory / "animated.gltf"
            report = directory / "review.json"
            log = directory / "godot.log"
            write_animated_skinned_gltf(asset)
            command = [
                str(self.godot),
                "--headless",
                "--log-file",
                str(log),
                "--path",
                str(GODOT_PROJECT),
                "--",
                f"--asset={asset}",
                f"--report={report}",
                "--quit-after-report",
                *arguments,
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertTrue(
                report.is_file(),
                msg=f"Godot did not write a report.\n{completed.stdout}\n{completed.stderr}",
            )
            return completed, json.loads(report.read_text(encoding="utf-8"))

    def test_matching_expectations_pass_and_select_expected_animation(self) -> None:
        completed, report = self.run_review(
            "--expect-animation=Walk", "--expect-skeletons=1"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(report["status"], ("pass", "warn"))
        self.assertEqual(report["selected_animation"], "Walk")
        self.assertTrue(report["expectations"]["expected_animation_found"])
        self.assertTrue(report["expectations"]["skeleton_count_matches"])

    def test_missing_expected_animation_fails(self) -> None:
        completed, report = self.run_review("--expect-animation=Run")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["selected_animation"], "")
        self.assertTrue(
            any("Expected animation `Run` was not found" in item for item in report["errors"])
        )

    def test_skeleton_count_mismatch_fails(self) -> None:
        completed, report = self.run_review("--expect-skeletons=2")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(
            any("Expected 2 Skeleton3D node(s), found 1" in item for item in report["errors"])
        )
        self.assertFalse(report["expectations"]["skeleton_count_matches"])

    def test_missing_explicit_animation_does_not_fall_back(self) -> None:
        completed, report = self.run_review("--animation=Missing")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["selected_animation"], "")
        self.assertTrue(
            any("no fallback animation was selected" in item for item in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()

"""Create a small, manifold humanoid-proxy mesh for Rigify smoke tests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = arguments()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=16,
        location=(0.0, 0.0, 1.0),
    )
    body = bpy.context.object
    body.name = "HumanoidBody"
    body.data.name = "HumanoidBody_Mesh"
    body.scale = (0.79, 0.285, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for polygon in body.data.polygons:
        polygon.use_smooth = True

    bpy.ops.wm.save_as_mainfile(
        filepath=str(output),
        check_existing=False,
        compress=True,
    )


if __name__ == "__main__":
    main()

"""Create a tiny deterministic Blender 5 rig/action fixture for smoke tests."""

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


def clear_scene() -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def create_armature(name: str, x_offset: float) -> bpy.types.Object:
    data = bpy.data.armatures.new(f"{name}_Data")
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location.x = x_offset
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = data.edit_bones.new("root")
    root.head = (0, 0, 0)
    root.tail = (0, 0, 1)
    spine = data.edit_bones.new("spine")
    spine.head = (0, 0, 1)
    spine.tail = (0, 0, 2)
    spine.parent = root
    spine.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    return obj


def create_bound_mesh(armature: bpy.types.Object) -> bpy.types.Object:
    vertices = [
        (-0.25, -0.25, 0.0),
        (0.25, -0.25, 0.0),
        (0.25, 0.25, 0.0),
        (-0.25, 0.25, 0.0),
        (-0.25, -0.25, 2.0),
        (0.25, -0.25, 2.0),
        (0.25, 0.25, 2.0),
        (-0.25, 0.25, 2.0),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new("TargetBody_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new("TargetBody", mesh)
    bpy.context.collection.objects.link(obj)
    obj.location.x = armature.location.x
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    group = obj.vertex_groups.new(name="root")
    group.add(list(range(len(vertices))), 1.0, "REPLACE")
    return obj


def animate_source(source: bpy.types.Object) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 10
    pose = source.pose.bones["spine"]
    pose.rotation_mode = "XYZ"
    scene.frame_set(1)
    pose.rotation_euler.z = 0.0
    pose.keyframe_insert("rotation_euler", frame=1, group="spine")
    scene.frame_set(5)
    pose.rotation_euler.z = 0.35
    pose.keyframe_insert("rotation_euler", frame=5, group="spine")
    scene.frame_set(10)
    pose.rotation_euler.z = 0.0
    pose.keyframe_insert("rotation_euler", frame=10, group="spine")
    source.animation_data.action.name = "SourceWave"
    scene.frame_set(1)


def main() -> None:
    args = arguments()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    source = create_armature("SourceRig", -1.0)
    target = create_armature("TargetRig", 1.0)
    artist_constraint = target.pose.bones["spine"].constraints.new("LIMIT_ROTATION")
    artist_constraint.name = "ArtistLimit"
    artist_constraint.mute = True
    create_bound_mesh(target)
    animate_source(source)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(output),
        check_existing=False,
        compress=True,
    )


if __name__ == "__main__":
    main()

"""Import a KIRI-compatible Gaussian PLY and save a versioned Blender source."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments() -> tuple[Path, Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    if len(argv) != 3:
        raise SystemExit("usage: import_kiri_splat.py INPUT.ply OUTPUT.blend REPORT.json")
    return tuple(Path(value).resolve() for value in argv)  # type: ignore[return-value]


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    source, blend_path, report_path = arguments()
    if not source.is_file():
        raise FileNotFoundError(source)
    for path in (blend_path, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    module_name = "bl_ext.user_default.dgs_render_by_kiri_engine"
    if module_name not in bpy.context.preferences.addons:
        result = bpy.ops.preferences.addon_enable(module=module_name)
        if "FINISHED" not in result:
            raise RuntimeError(f"Could not enable {module_name}: {result}")

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.sna_dgs_scene_properties.import_face_vert = "Verts"
    scene.sna_dgs_scene_properties.import_uv = False
    scene.sna_dgs_scene_properties.import_proxy = False

    result = bpy.ops.sna.dgs_render_import_ply_e0a3a(filepath=str(source))
    if "FINISHED" not in result:
        raise RuntimeError(f"KIRI import failed: {result}")

    splat = bpy.context.active_object
    if splat is None or splat.type != "MESH":
        raise RuntimeError("KIRI import did not leave an active mesh object")
    splat_count = len(splat.data.vertices)
    if splat_count < 1:
        raise RuntimeError("KIRI imported no Gaussian splats")

    required = {
        "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
        "scale_0", "scale_1", "scale_2",
        "rot_0", "rot_1", "rot_2", "rot_3", "f_rest_0",
    }
    missing = sorted(required.difference(splat.data.attributes.keys()))
    if missing:
        raise RuntimeError(f"Imported splat is missing attributes: {missing}")

    asset_name = re.sub(r"[^A-Za-z0-9]+", "_", source.stem).strip("_")
    splat.name = f"{asset_name}_TripoSplat"
    splat.data.name = f"{asset_name}_TripoSplat_Data"
    # Match the OpenCV-to-OpenGL flip used by the verified Spark viewer.
    splat.rotation_mode = "XYZ"
    splat.rotation_euler = (math.pi, 0.0, 0.0)
    splat["forge3d_source"] = str(source)
    splat["forge3d_representation"] = "gaussian_splat_not_polygon_mesh"
    splat["forge3d_splat_count"] = splat_count

    camera_data = bpy.data.cameras.new("Review_Camera")
    camera = bpy.data.objects.new("Review_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (2.0, -2.2, 1.45)
    direction = Vector((0.0, 0.0, 0.0)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 55
    scene.camera = camera

    bpy.ops.object.select_all(action="DESELECT")
    splat.select_set(True)
    bpy.context.view_layer.objects.active = splat

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)

    report = {
        "blend": str(blend_path),
        "source_ply": str(source),
        "representation": "Gaussian splat stored as KIRI mesh attributes and Geometry Nodes",
        "splat_count": splat_count,
        "object": splat.name,
        "rotation_euler_degrees": [180.0, 0.0, 0.0],
        "attributes": sorted(splat.data.attributes.keys()),
        "modifiers": [modifier.name for modifier in splat.modifiers],
        "materials": [slot.material.name if slot.material else None for slot in splat.material_slots],
        "blender_version": bpy.app.version_string,
        "kiri_module": module_name,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE3D_KIRI_IMPORT=" + json.dumps(report))


if __name__ == "__main__":
    main()

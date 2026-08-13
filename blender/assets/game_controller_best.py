"""Build an original, editable, game-ready controller prop.

The generated reference at references/game-controller-v001/reference.png guides
the visual language.  Geometry is authored independently so the result remains
clean, editable, conventionally renderable, and suitable for GLB/Godot.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


ASSET_NAME = "Aster_Game_Controller"
WIDTH = 0.188
DEPTH = 0.140
HEIGHT = 0.074


def arguments() -> Path:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit("usage: blender --background --python SCRIPT -- OUTPUT_DIR")
    return Path(argv[0]).resolve()


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.35,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        emission_input = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
        if emission_input:
            emission_input.default_value = emission
        strength_input = shader.inputs.get("Emission Strength")
        if strength_input:
            strength_input.default_value = emission_strength
    return mat


def move_to(obj: bpy.types.Object, collection: bpy.types.Collection) -> bpy.types.Object:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> bpy.types.Object:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def bevel(obj: bpy.types.Object, width: float, segments: int = 3, angle: float = 24.0) -> None:
    smallest = min((abs(value) for value in obj.dimensions if abs(value) > 1.0e-7), default=0.0)
    safe = min(width, smallest * 0.42)
    if safe <= 1.0e-7:
        return
    modifier = obj.modifiers.new("Controlled_Bevel", "BEVEL")
    modifier.width = safe
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    modifier.angle_limit = math.radians(angle)
    modifier.harden_normals = True
    modifier.use_clamp_overlap = True


def rounded_box(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    bevel_width: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    segments: int = 3,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to(obj, collection)
    assign(obj, mat)
    bevel(obj, bevel_width, segments)
    return obj


def prism_z(
    collection: bpy.types.Collection,
    name: str,
    coordinates: list[tuple[float, float]],
    z: float,
    thickness: float,
    mat: bpy.types.Material,
    *,
    bevel_width: float,
    segments: int = 3,
) -> bpy.types.Object:
    count = len(coordinates)
    vertices = [(x, y, z - thickness * 0.5) for x, y in coordinates]
    vertices += [(x, y, z + thickness * 0.5) for x, y in coordinates]
    faces: list[tuple[int, ...]] = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign(obj, mat)
    bevel(obj, bevel_width, segments)
    return obj


def cylinder(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    *,
    vertices: int = 32,
    bevel_width: float = 0.001,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    move_to(obj, collection)
    assign(obj, mat)
    bevel(obj, bevel_width, 2)
    return obj


def torus(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=32,
        minor_segments=8,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    move_to(obj, collection)
    assign(obj, mat)
    return obj


def sphere(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to(obj, collection)
    assign(obj, mat)
    return obj


def apply_and_unwrap(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.type != "MESH":
            continue
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            negligible = [face for face in bm.faces if face.calc_area() <= 1.0e-10]
            if negligible:
                bmesh.ops.delete(bm, geom=negligible, context="FACES")
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        try:
            obj.data.set_sharp_from_angle(angle=math.radians(50))
        except (AttributeError, TypeError):
            pass
        if obj.data.polygons:
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            try:
                bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.018)
            except RuntimeError:
                pass
            bpy.ops.object.mode_set(mode="OBJECT")


def controller_outline(scale: float = 1.0) -> list[tuple[float, float]]:
    points = [
        (-0.026, 0.052), (-0.052, 0.057), (-0.075, 0.054), (-0.088, 0.043),
        (-0.094, 0.026), (-0.093, 0.006), (-0.089, -0.018), (-0.083, -0.043),
        (-0.075, -0.061), (-0.066, -0.070), (-0.056, -0.068), (-0.048, -0.057),
        (-0.041, -0.041), (-0.033, -0.027), (0.033, -0.027), (0.041, -0.041),
        (0.048, -0.057), (0.056, -0.068), (0.066, -0.070), (0.075, -0.061),
        (0.083, -0.043), (0.089, -0.018), (0.093, 0.006), (0.094, 0.026),
        (0.088, 0.043), (0.075, 0.054), (0.052, 0.057), (0.026, 0.052),
    ]
    return [(x * scale, y * scale) for x, y in points]


def build_asset() -> tuple[list[bpy.types.Object], dict[str, bpy.types.Material]]:
    collection = bpy.data.collections.new("ASTER_CONTROLLER_ASSET")
    bpy.context.scene.collection.children.link(collection)
    mats = {
        "graphite": material("Controller_Graphite", (0.027, 0.032, 0.038, 1), roughness=0.29),
        "graphite_soft": material("Controller_Rubber", (0.008, 0.011, 0.014, 1), roughness=0.48),
        "edge": material("Controller_Edge", (0.075, 0.085, 0.095, 1), metallic=0.18, roughness=0.26),
        "teal": material("Controller_Teal", (0.028, 0.24, 0.27, 1), metallic=0.08, roughness=0.3),
        "teal_dark": material("Controller_Teal_Dark", (0.018, 0.10, 0.12, 1), metallic=0.12, roughness=0.34),
        "amber": material("Controller_Amber", (1.0, 0.24, 0.015, 1), roughness=0.2, emission=(1.0, 0.08, 0.004, 1), emission_strength=3.4),
        "blue": material("Controller_Blue", (0.02, 0.35, 0.95, 1), roughness=0.24, emission=(0.01, 0.12, 1.0, 1), emission_strength=1.3),
        "red": material("Controller_Red", (0.9, 0.035, 0.055, 1), roughness=0.24, emission=(1.0, 0.01, 0.02, 1), emission_strength=1.1),
        "green": material("Controller_Green", (0.08, 0.72, 0.18, 1), roughness=0.24, emission=(0.02, 0.7, 0.04, 1), emission_strength=0.9),
        "yellow": material("Controller_Yellow", (0.95, 0.58, 0.02, 1), roughness=0.24, emission=(1.0, 0.33, 0.01, 1), emission_strength=1.0),
        "metal": material("Controller_Hardware", (0.17, 0.19, 0.21, 1), metallic=0.82, roughness=0.22),
    }
    objects: list[bpy.types.Object] = []
    add = objects.append

    # Layered manufactured shell. The non-convex outline creates the handle gap
    # and tapered grips as real geometry rather than a rectangular proxy.
    add(prism_z(collection, "Shell_Lower", controller_outline(0.985), 0.018, 0.031, mats["edge"], bevel_width=0.0052, segments=5))
    add(prism_z(collection, "Shell_Upper", controller_outline(), 0.034, 0.025, mats["graphite"], bevel_width=0.0050, segments=5))
    add(prism_z(collection, "Shell_Seam_Band", controller_outline(0.972), 0.024, 0.004, mats["teal_dark"], bevel_width=0.0012, segments=2))

    # Central inset and grip inlays follow the reference's layered panel logic.
    central = [(-0.031, 0.042), (-0.021, 0.019), (-0.028, -0.013), (-0.019, -0.031),
               (0.019, -0.031), (0.028, -0.013), (0.021, 0.019), (0.031, 0.042)]
    add(prism_z(collection, "Central_Teal_Deck", central, 0.049, 0.006, mats["teal"], bevel_width=0.0022, segments=3))
    for side in (-1.0, 1.0):
        add(rounded_box(
            collection, f"Grip_Inlay_{'L' if side < 0 else 'R'}",
            (side * 0.067, -0.034, 0.049), (0.033, 0.052, 0.006), mats["graphite_soft"],
            bevel_width=0.008, rotation=(0.0, 0.0, side * math.radians(9)), segments=5,
        ))
        add(rounded_box(
            collection, f"Grip_Teal_Rail_{'L' if side < 0 else 'R'}",
            (side * 0.083, -0.027, 0.0505), (0.0045, 0.055, 0.004), mats["teal"],
            bevel_width=0.0015, rotation=(0.0, 0.0, side * math.radians(9)), segments=3,
        ))

    # Recessed control wells.
    for name, x, y in (("DPad_Well", -0.058, 0.022), ("Face_Well", 0.058, 0.022),
                       ("Stick_Well_L", -0.032, -0.012), ("Stick_Well_R", 0.032, -0.012)):
        radius = 0.020 if "Well" in name and "Stick" not in name else 0.016
        add(cylinder(collection, name, (x, y, 0.0505), radius, 0.005, mats["teal_dark"], vertices=48, bevel_width=0.0016))

    # Analog sticks: base ring, stem, cap, and a fine highlight rim.
    for side, x in (("L", -0.032), ("R", 0.032)):
        add(torus(collection, f"Stick_Base_Ring_{side}", (x, -0.012, 0.055), 0.0112, 0.0022, mats["edge"]))
        add(cylinder(collection, f"Stick_Stem_{side}", (x, -0.012, 0.061), 0.0062, 0.011, mats["graphite_soft"], vertices=32, bevel_width=0.001))
        add(sphere(collection, f"Stick_Cap_{side}", (x, -0.012, 0.069), (0.0118, 0.0118, 0.0043), mats["graphite_soft"]))
        add(torus(collection, f"Stick_Cap_Rim_{side}", (x, -0.012, 0.0722), 0.0077, 0.00075, mats["edge"]))

    # D-pad is separate editable geometry with a central pivot cap.
    add(rounded_box(collection, "DPad_Horizontal", (-0.058, 0.022, 0.057), (0.031, 0.0105, 0.006), mats["graphite_soft"], bevel_width=0.003, segments=4))
    add(rounded_box(collection, "DPad_Vertical", (-0.058, 0.022, 0.0575), (0.0105, 0.031, 0.007), mats["graphite_soft"], bevel_width=0.003, segments=4))
    add(cylinder(collection, "DPad_Pivot", (-0.058, 0.022, 0.0615), 0.0062, 0.0025, mats["edge"], vertices=32, bevel_width=0.0007))

    # Four face buttons and individually editable illuminated accent rings.
    button_specs = [
        ("North", 0.058, 0.036, mats["yellow"]), ("East", 0.072, 0.022, mats["red"]),
        ("South", 0.058, 0.008, mats["green"]), ("West", 0.044, 0.022, mats["blue"]),
    ]
    for name, x, y, accent in button_specs:
        add(cylinder(collection, f"Face_Button_{name}", (x, y, 0.058), 0.0072, 0.0085, mats["graphite_soft"], vertices=36, bevel_width=0.0018))
        add(torus(collection, f"Face_Button_Ring_{name}", (x, y, 0.063), 0.0055, 0.00085, accent))

    # Menu buttons, speaker holes, and status light.
    for index, x in enumerate((-0.0105, 0.0105)):
        add(rounded_box(collection, f"Menu_Button_{index}", (x, 0.009, 0.055), (0.013, 0.007, 0.005), mats["graphite_soft"], bevel_width=0.0023, segments=3))
        for stripe in (-0.0020, 0.0020):
            add(rounded_box(collection, f"Menu_Detail_{index}_{stripe:+.3f}", (x, 0.009 + stripe, 0.058), (0.006, 0.0007, 0.0008), mats["edge"], bevel_width=0.0002, segments=2))
    speaker_points = [(-0.009, -0.002), (0.0, -0.002), (0.009, -0.002), (-0.0135, -0.009), (-0.0045, -0.009), (0.0045, -0.009), (0.0135, -0.009)]
    for index, (x, y) in enumerate(speaker_points):
        add(cylinder(collection, f"Speaker_Hole_{index}", (x, y, 0.0535), 0.00135, 0.004, mats["graphite_soft"], vertices=16, bevel_width=0.0003))
    add(rounded_box(collection, "Status_Light", (0.0, -0.023, 0.056), (0.016, 0.0036, 0.003), mats["amber"], bevel_width=0.0015, segments=4))

    # Shoulder buttons, analogue triggers, USB port, and rear shell details.
    for side in (-1.0, 1.0):
        tag = "L" if side < 0 else "R"
        add(rounded_box(collection, f"Shoulder_{tag}", (side * 0.061, 0.057, 0.039), (0.049, 0.014, 0.016), mats["edge"], bevel_width=0.004, rotation=(0, 0, -side * math.radians(3)), segments=4))
        add(rounded_box(collection, f"Trigger_{tag}", (side * 0.061, 0.064, 0.025), (0.036, 0.013, 0.020), mats["graphite_soft"], bevel_width=0.004, rotation=(side * math.radians(7), 0, 0), segments=4))
    add(rounded_box(collection, "USB_C_Port", (0.0, 0.0588, 0.032), (0.014, 0.004, 0.0055), mats["graphite_soft"], bevel_width=0.0018, segments=4))
    add(rounded_box(collection, "Rear_Service_Panel", (0.0, 0.044, 0.012), (0.048, 0.020, 0.004), mats["graphite_soft"], bevel_width=0.003, segments=3))

    # Underside fasteners make the opposite-side review meaningful.
    for index, (x, y) in enumerate(((-0.058, 0.020), (0.058, 0.020), (-0.052, -0.042), (0.052, -0.042))):
        screw = cylinder(collection, f"Underside_Screw_{index}", (x, y, 0.001), 0.0022, 0.0022, mats["metal"], vertices=20, bevel_width=0.00035)
        screw.rotation_euler.x = math.pi
        add(rounded_box(collection, f"Underside_Slot_{index}", (x, y, -0.0003), (0.0026, 0.00055, 0.0007), mats["graphite_soft"], bevel_width=0.00015))

    # Three simple convex collision parts avoid the concave handle gap becoming
    # an oversized gameplay collider.
    collision_specs = [
        ("Controller_Centre-convcolonly", (0, 0.010, 0.026), (0.105, 0.078, 0.048), 0.010, 0.0),
        ("Controller_Grip_L-convcolonly", (-0.066, -0.029, 0.022), (0.044, 0.084, 0.041), 0.013, math.radians(9)),
        ("Controller_Grip_R-convcolonly", (0.066, -0.029, 0.022), (0.044, 0.084, 0.041), 0.013, -math.radians(9)),
    ]
    for name, location, dimensions, bevel_width, rotation_z in collision_specs:
        obj = rounded_box(collection, name, location, dimensions, mats["graphite_soft"], bevel_width=bevel_width, rotation=(0, 0, rotation_z), segments=2)
        obj.hide_render = True
        obj.display_type = "WIRE"
        obj["forge3d_role"] = "convex_collision_helper"
        add(obj)

    for obj in objects:
        obj["forge3d_asset"] = ASSET_NAME
        obj["forge3d_units"] = "meters"
    return objects, mats


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def build_review_scene() -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    review: list[bpy.types.Object] = []
    floor_mat = material("Review_Floor_MAT", (0.012, 0.018, 0.026, 1), roughness=0.34)
    floor = rounded_box(bpy.context.scene.collection, "Review_Floor", (0, 0, -0.018), (1.4, 1.4, 0.025), floor_mat, bevel_width=0.005)
    review.append(floor)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1152
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.006, 0.010, 0.018)
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.65
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    bpy.ops.object.camera_add(location=(0.235, -0.285, 0.185))
    camera = bpy.context.object
    camera.name = "Review_Camera"
    camera.data.lens = 58
    look_at(camera, (0, -0.004, 0.031))
    scene.camera = camera
    review.append(camera)
    lights = [
        ("Key_Light", (-0.20, -0.25, 0.34), 34, (0.92, 0.76, 0.58), 0.25),
        ("Fill_Light", (0.24, -0.08, 0.22), 18, (0.34, 0.62, 1.0), 0.22),
        ("Rim_Light", (0.05, 0.26, 0.27), 28, (0.18, 0.82, 0.9), 0.18),
    ]
    for name, location, energy, color, size in lights:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.color = color
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, (0, 0, 0.025))
        review.append(light)
    return camera, review


def render(camera: bpy.types.Object, path: Path, location: tuple[float, float, float], target: tuple[float, float, float]) -> None:
    camera.location = location
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    output_dir = arguments()
    version = output_dir.name
    outputs = {
        "blend": output_dir / f"{version}.blend",
        "glb": output_dir / f"{version}.glb",
        "front": output_dir / "preview-front.png",
        "back": output_dir / "preview-back.png",
        "top": output_dir / "preview-top.png",
        "report": output_dir / "build-report.json",
    }
    existing = [str(path) for path in outputs.values() if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing outputs: {existing}")
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)

    objects, mats = build_asset()
    apply_and_unwrap(objects)
    camera, _review = build_review_scene()
    render(camera, outputs["front"], (0.235, -0.285, 0.185), (0, -0.004, 0.031))
    render(camera, outputs["back"], (-0.225, 0.285, 0.155), (0, 0.0, 0.025))
    render(camera, outputs["top"], (0.015, -0.235, 0.315), (0, -0.004, 0.027))
    camera.location = (0.235, -0.285, 0.185)
    look_at(camera, (0, -0.004, 0.031))
    bpy.ops.wm.save_as_mainfile(filepath=str(outputs["blend"]))

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(outputs["glb"]), export_format="GLB", use_selection=True,
        export_apply=True, export_cameras=False, export_lights=False,
    )

    meshes = [obj for obj in objects if obj.type == "MESH"]
    report = {
        "asset": ASSET_NAME,
        "reference": "references/game-controller-v001/reference.png",
        "representation": "conventional editable polygon meshes",
        "dimensions_m": {"width": WIDTH, "depth": DEPTH, "height": HEIGHT},
        "objects": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "polygons": sum(len(obj.data.polygons) for obj in meshes),
        "triangles": sum(sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons) for obj in meshes),
        "materials": sorted(mat.name for mat in mats.values()),
        "collision_helpers": [obj.name for obj in objects if obj.name.endswith("-convcolonly")],
        "uv_meshes": sum(1 for obj in meshes if obj.data.uv_layers),
        "outputs": {key: str(path) for key, path in outputs.items()},
        "limitations": [
            "Materials use authored PBR values rather than a unique baked microtexture atlas.",
            "Buttons and sticks are separate editable objects but no interaction rig or animation is included.",
        ],
    }
    outputs["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

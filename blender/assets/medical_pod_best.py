"""Build a production-oriented hard-surface medical supply pod.

The preserved concept at references/medical-pod-v001/reference.png is
authoritative. TripoSplat is retained as the separate high-fidelity static
visual master; this script provides the clean editable/animated mesh route.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


ASSET_NAME = "Medical_Pod"
WIDTH = 1.25
DEPTH = 0.78
BODY_BOTTOM = 0.075
BODY_TOP = 0.535
LID_TOP = 0.705


def arguments() -> Path:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit("usage: blender --background --python SCRIPT -- OUTPUT_DIR")
    return Path(argv[0]).resolve()


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float,
    roughness: float,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    if emission:
        emission_input = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
        strength_input = principled.inputs.get("Emission Strength")
        if emission_input:
            emission_input.default_value = emission
        if strength_input:
            strength_input.default_value = emission_strength
    return mat


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def add_bevel(obj: bpy.types.Object, width: float, segments: int = 3) -> None:
    if width <= 0:
        return
    smallest_dimension = min(abs(value) for value in obj.dimensions)
    safe_width = min(width, smallest_dimension * 0.45)
    if safe_width <= 0:
        return
    bevel = obj.modifiers.new("Controlled_Bevel", "BEVEL")
    bevel.width = safe_width
    bevel.segments = segments
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(25)
    bevel.harden_normals = True
    bevel.use_clamp_overlap = True


def rounded_box(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    bevel: float,
    rotation: tuple[float, float, float] = (0, 0, 0),
    segments: int = 3,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(obj, collection)
    assign_material(obj, mat)
    add_bevel(obj, bevel, segments)
    return obj


def cylinder(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    axis: str,
    mat: bpy.types.Material,
    *,
    vertices: int = 32,
    bevel: float = 0.004,
) -> bpy.types.Object:
    rotation = (0.0, 0.0, 0.0)
    if axis == "Y":
        rotation = (math.pi * 0.5, 0.0, 0.0)
    elif axis == "X":
        rotation = (0.0, math.pi * 0.5, 0.0)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    assign_material(obj, mat)
    add_bevel(obj, bevel, 2)
    return obj


def prism_y(
    collection: bpy.types.Collection,
    name: str,
    coordinates: list[tuple[float, float]],
    y: float,
    thickness: float,
    mat: bpy.types.Material,
    *,
    bevel: float,
) -> bpy.types.Object:
    count = len(coordinates)
    vertices = [(x, y - thickness * 0.5, z) for x, z in coordinates]
    vertices += [(x, y + thickness * 0.5, z) for x, z in coordinates]
    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    add_bevel(obj, bevel, 3)
    return obj


def prism_x(
    collection: bpy.types.Collection,
    name: str,
    coordinates: list[tuple[float, float]],
    x: float,
    thickness: float,
    mat: bpy.types.Material,
    *,
    bevel: float,
) -> bpy.types.Object:
    count = len(coordinates)
    vertices = [(x - thickness * 0.5, y, z) for y, z in coordinates]
    vertices += [(x + thickness * 0.5, y, z) for y, z in coordinates]
    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    assign_material(obj, mat)
    add_bevel(obj, bevel, 3)
    return obj


def torus_rib(
    collection: bpy.types.Collection,
    name: str,
    location: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_segments=20,
        minor_segments=6,
        location=location,
        rotation=(math.pi * 0.5, 0, 0),
        major_radius=major_radius,
        minor_radius=minor_radius,
    )
    obj = bpy.context.object
    obj.name = name
    move_to_collection(obj, collection)
    assign_material(obj, mat)
    return obj


def text_mesh(
    collection: bpy.types.Collection,
    name: str,
    body: str,
    location: tuple[float, float, float],
    size: float,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.object.text_add(location=location, rotation=(math.pi * 0.5, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.0018
    obj.data.bevel_depth = 0.0007
    move_to_collection(obj, collection)
    assign_material(obj, mat)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    return bpy.context.object


def apply_modifiers_and_uv(objects: list[bpy.types.Object]) -> None:
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
            if obj.name == "Front_Label" and bm.faces:
                bmesh.ops.triangulate(bm, faces=list(bm.faces))
            negligible = [face for face in bm.faces if face.calc_area() <= 1.0e-8]
            if negligible:
                bmesh.ops.delete(bm, geom=negligible, context="FACES")
            bm.to_mesh(obj.data)
        finally:
            bm.free()
        obj.data.update()
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        try:
            obj.data.set_sharp_from_angle(angle=math.radians(48))
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


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def build_asset(output_dir: Path) -> tuple[list[bpy.types.Object], bpy.types.Collection, dict[str, bpy.types.Material]]:
    asset = bpy.data.collections.new("MEDICAL_POD_ASSET")
    bpy.context.scene.collection.children.link(asset)

    mats = {
        "ivory": material("Pod_Ivory_Polymer", (0.72, 0.69, 0.60, 1), metallic=0.0, roughness=0.34),
        "ivory_light": material("Pod_Ivory_Highlight", (0.88, 0.85, 0.75, 1), metallic=0.0, roughness=0.29),
        "teal": material("Pod_Teal_Armor", (0.035, 0.29, 0.30, 1), metallic=0.08, roughness=0.32),
        "dark": material("Pod_Graphite_Rubber", (0.018, 0.025, 0.028, 1), metallic=0.15, roughness=0.43),
        "metal": material("Pod_Brushed_Hardware", (0.13, 0.16, 0.17, 1), metallic=0.78, roughness=0.25),
        "orange": material(
            "Pod_Amber_Indicator",
            (1.0, 0.19, 0.015, 1),
            metallic=0.0,
            roughness=0.18,
            emission=(1.0, 0.08, 0.005, 1),
            emission_strength=4.0,
        ),
        "white": material("Pod_Medical_Marking", (0.92, 0.98, 0.96, 1), metallic=0.0, roughness=0.28),
    }

    objects: list[bpy.types.Object] = []
    add = objects.append

    # Primary layered shell: wide and low, matching the authoritative concept.
    add(rounded_box(asset, "Shell_Lower", (0, 0, 0.305), (1.18, 0.72, 0.46), mats["ivory"], bevel=0.072, segments=5))
    add(rounded_box(asset, "Lid_Main", (0, 0, 0.615), (1.22, 0.74, 0.17), mats["ivory_light"], bevel=0.065, segments=5))
    add(rounded_box(asset, "Base_Skirt", (0, 0, 0.105), (1.13, 0.68, 0.09), mats["dark"], bevel=0.028, segments=4))

    # Lid seam and vertical impact rails.
    for y in (-0.374, 0.374):
        add(rounded_box(asset, f"Seal_{'Front' if y < 0 else 'Back'}", (0, y, 0.535), (1.08, 0.028, 0.035), mats["dark"], bevel=0.012))
    for x in (-0.604, 0.604):
        add(rounded_box(asset, f"Seal_{'Left' if x < 0 else 'Right'}", (x, 0, 0.535), (0.028, 0.66, 0.035), mats["dark"], bevel=0.012))
    for x_index, x in enumerate((-0.47, 0.47)):
        for y_index, y in enumerate((-0.386, 0.386)):
            add(rounded_box(asset, f"Impact_Rail_{x_index}_{y_index}", (x, y, 0.52), (0.046, 0.026, 0.28), mats["dark"], bevel=0.013))
        add(rounded_box(asset, f"Top_Rail_{x_index}", (x, 0, 0.704), (0.046, 0.60, 0.024), mats["dark"], bevel=0.011))

    # Large top inset and unambiguous medical marking.
    add(rounded_box(asset, "Top_Teal_Inset", (0, 0, 0.708), (0.50, 0.31, 0.025), mats["teal"], bevel=0.027, segments=4))
    add(rounded_box(asset, "Top_Cross_H", (0, 0, 0.726), (0.19, 0.054, 0.013), mats["white"], bevel=0.012))
    add(rounded_box(asset, "Top_Cross_V", (0, 0, 0.726), (0.054, 0.19, 0.013), mats["white"], bevel=0.012))

    # Front frame and deliberately shaped access panel.
    front_y = -0.382
    frame_coords = [(-0.50, 0.17), (-0.45, 0.12), (0.45, 0.12), (0.50, 0.17), (0.50, 0.48), (0.44, 0.52), (-0.44, 0.52), (-0.50, 0.48)]
    panel_coords = [(-0.445, 0.18), (-0.405, 0.145), (0.405, 0.145), (0.445, 0.18), (0.445, 0.445), (0.34, 0.445), (0.29, 0.485), (-0.29, 0.485), (-0.34, 0.445), (-0.445, 0.445)]
    add(prism_y(asset, "Front_Graphite_Frame", frame_coords, front_y - 0.010, 0.032, mats["dark"], bevel=0.014))
    add(prism_y(asset, "Front_Access_Panel", panel_coords, front_y - 0.032, 0.026, mats["ivory_light"], bevel=0.016))
    left_accent = [(-0.40, 0.19), (-0.28, 0.19), (-0.28, 0.37), (-0.36, 0.43), (-0.42, 0.43), (-0.42, 0.22)]
    right_accent = [(-x, z) for x, z in reversed(left_accent)]
    add(prism_y(asset, "Front_Accent_Left", left_accent, front_y - 0.052, 0.018, mats["teal"], bevel=0.011))
    add(prism_y(asset, "Front_Accent_Right", right_accent, front_y - 0.052, 0.018, mats["teal"], bevel=0.011))

    # Central layered status indicator.
    add(cylinder(asset, "Indicator_Outer", (0, front_y - 0.058, 0.315), 0.094, 0.028, "Y", mats["dark"], vertices=48, bevel=0.006))
    add(cylinder(asset, "Indicator_Teal_Ring", (0, front_y - 0.077, 0.315), 0.073, 0.026, "Y", mats["teal"], vertices=48, bevel=0.005))
    add(cylinder(asset, "Indicator_Metal_Ring", (0, front_y - 0.094, 0.315), 0.049, 0.023, "Y", mats["metal"], vertices=40, bevel=0.004))
    add(cylinder(asset, "Indicator_Amber_Lens", (0, front_y - 0.111, 0.315), 0.031, 0.020, "Y", mats["orange"], vertices=40, bevel=0.006))

    # Latches and fasteners give the face believable assembly logic.
    for index, x in enumerate((-0.30, 0.30)):
        add(rounded_box(asset, f"Front_Latch_{index}", (x, front_y - 0.071, 0.495), (0.09, 0.045, 0.055), mats["metal"], bevel=0.009))
        add(rounded_box(asset, f"Front_Latch_Tab_{index}", (x, front_y - 0.097, 0.472), (0.055, 0.022, 0.035), mats["teal"], bevel=0.006))
    for index, (x, z) in enumerate(((-0.455, 0.205), (0.455, 0.205), (-0.455, 0.455), (0.455, 0.455))):
        add(cylinder(asset, f"Front_Fastener_{index}", (x, front_y - 0.068, z), 0.009, 0.012, "Y", mats["metal"], vertices=16, bevel=0.0015))
    add(text_mesh(asset, "Front_Label", "MEDICAL  //  SUPPLY", (0, front_y - 0.071, 0.205), 0.032, mats["dark"]))

    # Rear service panel, hinges, vents and warning marking.
    back_y = 0.382
    back_frame = [(-0.49, 0.17), (-0.44, 0.13), (0.44, 0.13), (0.49, 0.17), (0.49, 0.46), (0.44, 0.50), (-0.44, 0.50), (-0.49, 0.46)]
    back_panel = [(-0.43, 0.19), (-0.39, 0.16), (0.39, 0.16), (0.43, 0.19), (0.43, 0.44), (0.39, 0.47), (-0.39, 0.47), (-0.43, 0.44)]
    add(prism_y(asset, "Rear_Graphite_Frame", back_frame, back_y + 0.010, 0.030, mats["dark"], bevel=0.013))
    add(prism_y(asset, "Rear_Service_Panel", back_panel, back_y + 0.032, 0.025, mats["ivory"], bevel=0.014))
    for index, x in enumerate((-0.29, 0.29)):
        add(rounded_box(asset, f"Rear_Hinge_{index}", (x, back_y + 0.061, 0.49), (0.15, 0.052, 0.050), mats["metal"], bevel=0.008))
    for index, x in enumerate((-0.16, -0.08, 0.0, 0.08, 0.16)):
        add(rounded_box(asset, f"Rear_Vent_{index}", (x, back_y + 0.060, 0.265), (0.048, 0.016, 0.12), mats["dark"], bevel=0.008))

    # Side access panels and matching deployable carry handles.
    side_panel_coords = [(-0.245, 0.18), (-0.205, 0.145), (0.205, 0.145), (0.245, 0.18), (0.245, 0.43), (0.205, 0.47), (-0.205, 0.47), (-0.245, 0.43)]
    for side_index, side in enumerate((-1.0, 1.0)):
        x_shell = side * 0.605
        x_frame = side * 0.618
        x_panel = side * 0.636
        add(prism_x(asset, f"Side_Frame_{side_index}", side_panel_coords, x_frame, 0.030, mats["dark"], bevel=0.012))
        inner = [(y * 0.86, 0.18 + (z - 0.18) * 0.88) for y, z in side_panel_coords]
        add(prism_x(asset, f"Side_Panel_{side_index}", inner, x_panel, 0.024, mats["ivory_light"], bevel=0.011))

        outside_x = side * 0.755
        for mount_index, y in enumerate((-0.22, 0.22)):
            add(rounded_box(asset, f"Handle_Mount_{side_index}_{mount_index}", (side * 0.642, y, 0.34), (0.065, 0.11, 0.13), mats["teal"], bevel=0.016))
            add(rounded_box(
                asset,
                f"Handle_Strut_{side_index}_{mount_index}",
                (side * 0.695, y, 0.335),
                (0.13, 0.065, 0.065),
                mats["teal"],
                bevel=0.014,
                rotation=(0, side * math.radians(12), 0),
            ))
        add(cylinder(asset, f"Handle_Grip_{side_index}", (outside_x, 0, 0.315), 0.044, 0.36, "Y", mats["dark"], vertices=28, bevel=0.005))
        for rib_index, y in enumerate((-0.15, -0.12, -0.09, -0.06, -0.03, 0.0, 0.03, 0.06, 0.09, 0.12, 0.15)):
            add(torus_rib(asset, f"Grip_Rib_{side_index}_{rib_index}", (outside_x, y, 0.315), 0.044, 0.0042, mats["metal"]))

    # Feet and dark soles establish a believable grounded silhouette.
    for x_index, x in enumerate((-0.45, 0.45)):
        for y_index, y in enumerate((-0.27, 0.27)):
            add(rounded_box(asset, f"Foot_{x_index}_{y_index}", (x, y, 0.055), (0.17, 0.15, 0.11), mats["teal"], bevel=0.022, rotation=(0, math.copysign(math.radians(4), x), 0), segments=4))
            add(rounded_box(asset, f"Foot_Sole_{x_index}_{y_index}", (x, y, 0.011), (0.15, 0.13, 0.022), mats["dark"], bevel=0.009))

    # Small corner lamps/sensors provide readable secondary detail.
    for index, x in enumerate((-0.52, 0.52)):
        add(rounded_box(asset, f"Top_Sensor_Housing_{index}", (x, -0.235, 0.695), (0.11, 0.085, 0.042), mats["teal"], bevel=0.014))
        add(cylinder(asset, f"Top_Sensor_Lens_{index}", (x, -0.285, 0.695), 0.018, 0.018, "Y", mats["orange"], vertices=24, bevel=0.003))

    # Collision source follows Godot's import naming convention.
    collision = rounded_box(
        asset,
        "Medical_Pod-convcolonly",
        (0, 0, 0.365),
        (1.18, 0.72, 0.65),
        mats["dark"],
        bevel=0.045,
        segments=2,
    )
    collision.hide_render = True
    collision.display_type = "WIRE"
    collision["forge3d_role"] = "convex_collision_helper"
    objects.append(collision)

    for obj in objects:
        obj["forge3d_asset"] = ASSET_NAME
        obj["forge3d_units"] = "meters"
    return objects, asset, mats


def build_review_scene(asset_objects: list[bpy.types.Object], mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    review_objects: list[bpy.types.Object] = []
    floor = rounded_box(
        bpy.context.scene.collection,
        "Review_Floor",
        (0, 0, -0.045),
        (6, 6, 0.08),
        material("Review_Floor_MAT", (0.018, 0.025, 0.032, 1), metallic=0.0, roughness=0.42),
        bevel=0.02,
    )
    review_objects.append(floor)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1152
    scene.render.resolution_y = 1152
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.012, 0.018, 0.026)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    bpy.ops.object.camera_add(location=(2.15, -2.65, 1.58))
    camera = bpy.context.object
    camera.name = "Review_Camera"
    camera.data.lens = 58
    look_at(camera, (0, 0, 0.34))
    scene.camera = camera
    review_objects.append(camera)

    light_specs = [
        ("Key_Light", (-2.1, -2.8, 3.2), 1350, (1.0, 0.76, 0.58), 3.2),
        ("Fill_Light", (2.8, -0.9, 1.8), 950, (0.32, 0.62, 1.0), 2.8),
        ("Rim_Light", (0.6, 2.6, 2.6), 1200, (0.2, 0.85, 0.9), 2.4),
    ]
    for name, location, energy, color, size in light_specs:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.color = color
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, (0, 0, 0.34))
        review_objects.append(light)
    return camera, review_objects


def render(camera: bpy.types.Object, output: Path, location: tuple[float, float, float], target: tuple[float, float, float]) -> None:
    camera.location = location
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    output_dir = arguments()
    version_name = output_dir.name
    outputs = {
        "blend": output_dir / f"{version_name}.blend",
        "glb": output_dir / f"{version_name}.glb",
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

    objects, asset_collection, mats = build_asset(output_dir)
    apply_modifiers_and_uv(objects)
    camera, review_objects = build_review_scene(objects, mats)

    render(camera, outputs["front"], (2.15, -2.65, 1.58), (0, 0, 0.34))
    render(camera, outputs["back"], (-2.15, 2.65, 1.48), (0, 0, 0.34))
    render(camera, outputs["top"], (1.65, -1.75, 2.65), (0, 0, 0.34))
    camera.location = (2.15, -2.65, 1.58)
    look_at(camera, (0, 0, 0.34))

    # Save the editable source with review lighting and camera intact.
    bpy.ops.wm.save_as_mainfile(filepath=str(outputs["blend"]))

    # Export only asset geometry; review lights and floor stay in the .blend.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = next(obj for obj in objects if obj.type == "MESH")
    bpy.ops.export_scene.gltf(
        filepath=str(outputs["glb"]),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
    )

    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    report = {
        "asset": ASSET_NAME,
        "source_of_truth": "authoritative concept image; splat used only as material/detail reference",
        "dimensions_m": {"width_without_handles": WIDTH, "depth": DEPTH, "height": LID_TOP},
        "objects": len(mesh_objects),
        "vertices": sum(len(obj.data.vertices) for obj in mesh_objects),
        "polygons": sum(len(obj.data.polygons) for obj in mesh_objects),
        "triangles": sum(sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons) for obj in mesh_objects),
        "materials": sorted(mat.name for mat in mats.values()),
        "collision_helpers": [obj.name for obj in objects if obj.name.endswith("-convcolonly")],
        "uv_meshes": sum(1 for obj in mesh_objects if obj.data.uv_layers),
        "outputs": {key: str(path) for key, path in outputs.items()},
        "limitations": [
            "Materials are authored PBR values and geometry detail; no unique baked wear atlas yet.",
            "Static hard-surface prop; no opening-lid rig or interior has been authored.",
        ],
    }
    outputs["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

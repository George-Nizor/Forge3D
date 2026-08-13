"""Build a consistent Blender review scene for splat-to-mesh methods."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector


METHODS = (
    {
        "name": "Voxel_Smooth",
        "label": "VOXEL SMOOTH  |  25.5K tris",
        "path": "voxel-smooth.collision.glb",
        "color": (0.08, 0.34, 0.72, 1.0),
        "slot": -1.25,
        "smooth": True,
    },
    {
        "name": "Voxel_Faces",
        "label": "VOXEL FACES  |  37.9K tris",
        "path": "voxel-faces.collision.glb",
        "color": (0.82, 0.22, 0.055, 1.0),
        "slot": 0.0,
        "smooth": False,
    },
    {
        "name": "Oriented_Poisson",
        "label": "ORIENTED POISSON  |  893K tris",
        "path": "oriented-poisson-depth9.ply",
        "color": (0.08, 0.52, 0.27, 1.0),
        "slot": 1.25,
        "smooth": True,
    },
)


def arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 2:
        raise SystemExit("usage: blender --background --python SCRIPT -- ASSET_DIR OUTPUT_DIR")
    return Path(argv[0]).resolve(), Path(argv[1]).resolve()


def refuse_overwrite(paths: list[Path]) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing files: {existing}")


def make_material(name: str, color: tuple[float, float, float, float], metallic: float = 0.05) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = 0.32
    return material


def imported_meshes(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]


def import_method(path: Path) -> bpy.types.Object:
    before = {obj.name for obj in bpy.data.objects}
    if path.suffix.lower() == ".glb":
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif path.suffix.lower() == ".ply":
        bpy.ops.wm.ply_import(filepath=str(path))
    else:
        raise ValueError(f"Unsupported method input: {path}")
    objects = imported_meshes(before)
    if not objects:
        raise RuntimeError(f"No mesh was imported from {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(tuple(min(c[i] for c in corners) for i in range(3))),
        Vector(tuple(max(c[i] for c in corners) for i in range(3))),
    )


def orient_and_place(obj: bpy.types.Object, x_slot: float) -> None:
    # TripoSplat's tallest source dimension is Z. Some GLB exporters declare
    # Y-up, so orient by the dominant dimension before comparing silhouettes.
    lower, upper = world_bounds(obj)
    dominant = max(range(3), key=lambda index: upper[index] - lower[index])
    if dominant == 0:
        obj.data.transform(Matrix.Rotation(math.radians(90), 4, "Y"))
    elif dominant == 1:
        obj.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
    obj.data.transform(Matrix.Rotation(math.pi, 4, "X"))
    obj.data.update()
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    lower, upper = world_bounds(obj)
    centre = (lower + upper) * 0.5
    obj.location = (x_slot - centre.x, -centre.y, -lower.z)
    bpy.context.view_layer.update()


def topology(obj: bpy.types.Object) -> dict[str, object]:
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    boundary = sum(1 for edge in bm.edges if edge.is_boundary)
    non_manifold = sum(1 for edge in bm.edges if not edge.is_manifold)
    components = 0
    unseen = set(bm.verts)
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in unseen:
                    unseen.remove(other)
                    stack.append(other)
    bm.free()
    lower, upper = world_bounds(obj)
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "triangles": sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons),
        "boundary_edges": boundary,
        "non_manifold_edges": non_manifold,
        "connected_components": components,
        "bounds_min": list(lower),
        "bounds_max": list(upper),
        "dimensions": list(upper - lower),
    }


def add_label(text: str, x: float) -> None:
    bpy.ops.object.text_add(location=(x - 0.49, -0.43, 1.12), rotation=(math.radians(90), 0, 0))
    label = bpy.context.object
    label.name = f"Label_{text.split('|', 1)[0].strip().title().replace(' ', '_')}"
    label.data.body = text
    label.data.align_x = "LEFT"
    label.data.size = 0.075
    label.data.extrude = 0.002
    label.data.materials.append(bpy.data.materials["Label_Material"])


def look_at(obj: bpy.types.Object, point: tuple[float, float, float]) -> None:
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_view(camera: bpy.types.Object, path: Path, location: tuple[float, float, float], target: tuple[float, float, float]) -> None:
    camera.location = location
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    asset_dir, output_dir = arguments()
    output_dir.mkdir(parents=True, exist_ok=True)
    blend_path = output_dir / "medical-pod-mesh-methods-v002.blend"
    report_path = output_dir / "comparison-report-v002.json"
    front_path = output_dir / "comparison-front-v002.png"
    back_path = output_dir / "comparison-back-v002.png"
    side_path = output_dir / "comparison-side-v002.png"
    poisson_glb = output_dir / "oriented-poisson-depth9.glb"
    refuse_overwrite([blend_path, report_path, front_path, back_path, side_path])

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.025, 0.03, 0.045)

    label_material = make_material("Label_Material", (0.8, 0.86, 0.96, 1.0), metallic=0.0)
    reports: dict[str, object] = {}
    imported: list[bpy.types.Object] = []
    for method in METHODS:
        source = asset_dir / method["path"]
        obj = import_method(source)
        obj.name = method["name"]
        orient_and_place(obj, float(method["slot"]))
        obj.data.materials.clear()
        obj.data.materials.append(make_material(f"{method['name']}_Material", method["color"]))
        for polygon in obj.data.polygons:
            polygon.use_smooth = bool(method["smooth"])
        reports[method["name"]] = {"source": str(source), **topology(obj)}
        add_label(str(method["label"]), float(method["slot"]))
        imported.append(obj)

    # Export the raw Poisson result once as a conventional game-readable GLB.
    if not poisson_glb.exists():
        bpy.ops.object.select_all(action="DESELECT")
        poisson = bpy.data.objects["Oriented_Poisson"]
        poisson.select_set(True)
        bpy.context.view_layer.objects.active = poisson
        bpy.ops.export_scene.gltf(
            filepath=str(poisson_glb),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
        )

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.015))
    floor = bpy.context.object
    floor.name = "Review_Ground"
    floor.data.materials.append(make_material("Ground_Material", (0.018, 0.024, 0.036, 1.0), metallic=0.0))

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "Comparison_Camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4.25
    scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.4, 4.2))
    key = bpy.context.object
    key.name = "Key_Light"
    key.data.energy = 1050
    key.data.shape = "DISK"
    key.data.size = 4.0
    look_at(key, (0, 0, 0.55))
    bpy.ops.object.light_add(type="AREA", location=(3.2, 1.8, 2.4))
    fill = bpy.context.object
    fill.name = "Fill_Light"
    fill.data.energy = 800
    fill.data.color = (0.35, 0.52, 1.0)
    fill.data.size = 3.0
    look_at(fill, (0, 0, 0.45))
    bpy.ops.object.light_add(type="AREA", location=(0, 2.5, 4.0))
    rim = bpy.context.object
    rim.name = "Rim_Light"
    rim.data.energy = 900
    rim.data.color = (1.0, 0.38, 0.16)
    rim.data.size = 2.5
    look_at(rim, (0, 0, 0.6))

    render_view(camera, front_path, (4.0, -7.0, 2.55), (0, 0, 0.48))
    render_view(camera, back_path, (-4.0, 7.0, 2.55), (0, 0, 0.48))

    # A side camera looks down the comparison row, so temporarily arrange the
    # meshes along Y and hide front-facing labels to keep all silhouettes clear.
    original_locations = {obj.name: obj.location.copy() for obj in imported}
    labels = [obj for obj in scene.objects if obj.name.startswith("Label_")]
    for obj, method in zip(imported, METHODS, strict=True):
        lower, upper = world_bounds(obj)
        obj.location.x -= (lower.x + upper.x) * 0.5
        obj.location.y += float(method["slot"]) - (lower.y + upper.y) * 0.5
    for label in labels:
        label.hide_render = True
    render_view(camera, side_path, (7.0, 0, 1.75), (0, 0, 0.48))
    for obj in imported:
        obj.location = original_locations[obj.name]
    for label in labels:
        label.hide_render = False

    report = {
        "purpose": "Gaussian-splat-to-mesh method comparison",
        "source_splat": str(asset_dir.parent / "triposplat-medical-pod-v001" / "medical-pod-262144.ply"),
        "methods": reports,
        "renders": [str(front_path), str(back_path), str(side_path)],
        "poisson_glb": str(poisson_glb),
        "notes": [
            "All models are shown at source scale with their lowest point on the ground plane.",
            "Flat comparison materials deliberately expose surface quality rather than hiding it with the splat colours.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

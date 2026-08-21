"""Forge3D's Blender 5 task runner.

Run with:

    blender --background --python blender/forge3d_task.py -- <task> [options]

The module deliberately depends only on Blender's Python distribution and the
standard library.  Each task emits one machine-readable ``FORGE3D_RESULT`` line
and can also write the same report to ``--report``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import random
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector


TOOL_VERSION = "0.2.1"
REPORT_PREFIX = "FORGE3D_RESULT="
GENERATED_BY_KEY = "forge3d_generated_by"
EPSILON = 1.0e-8
SUPPORTED_INPUT_SUFFIXES = {
    ".blend",
    ".glb",
    ".gltf",
    ".fbx",
    ".obj",
    ".stl",
    ".usd",
    ".usda",
    ".usdc",
}


class TaskError(RuntimeError):
    """An expected task failure with a user-actionable message."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_safe(value: Any) -> Any:
    """Convert common Blender/mathutils values to JSON-compatible values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (Vector, Matrix)):
        if isinstance(value, Matrix):
            return [[json_safe(component) for component in row] for row in value]
        return [json_safe(component) for component in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "to_list"):
        return json_safe(value.to_list())
    return str(value)


def new_report(task: str, argv: Sequence[str]) -> dict[str, Any]:
    return {
        "schema": "forge3d.blender.report.v1",
        "tool_version": TOOL_VERSION,
        "blender_version": bpy.app.version_string,
        "task": task,
        "status": "running",
        "started_at": utc_now(),
        "argv": list(argv),
        "warnings": [],
        "errors": [],
        "changes": [],
        "metrics": {},
        "outputs": {},
    }


def warn(report: dict[str, Any], message: str, **details: Any) -> None:
    item = {"message": message}
    item.update(json_safe(details))
    report["warnings"].append(item)


def change(report: dict[str, Any], message: str, **details: Any) -> None:
    item = {"message": message}
    item.update(json_safe(details))
    report["changes"].append(item)


def issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    *,
    object_name: str | None = None,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if object_name is not None:
        item["object"] = object_name
    item.update(json_safe(details))
    issues.append(item)


def path_from_user(
    raw_path: str,
    *,
    kind: str,
    must_exist: bool = False,
    allowed_suffixes: set[str] | None = None,
) -> Path:
    if "\x00" in raw_path:
        raise TaskError(f"{kind} contains a NUL byte")
    path = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    try:
        path = path.resolve(strict=must_exist)
    except (FileNotFoundError, OSError) as exc:
        raise TaskError(f"{kind} is not accessible: {path}: {exc}") from exc
    if must_exist and not path.exists():
        raise TaskError(f"{kind} does not exist: {path}")
    if must_exist and not path.is_file():
        raise TaskError(f"{kind} is not a file: {path}")
    if allowed_suffixes is not None and path.suffix.lower() not in allowed_suffixes:
        expected = ", ".join(sorted(allowed_suffixes))
        raise TaskError(f"{kind} must use one of [{expected}]: {path}")
    return path


def prepare_output_file(
    raw_path: str,
    *,
    kind: str,
    force: bool,
    allowed_suffixes: set[str] | None = None,
    input_path: Path | None = None,
) -> Path:
    path = path_from_user(
        raw_path,
        kind=kind,
        must_exist=False,
        allowed_suffixes=allowed_suffixes,
    )
    if input_path is not None and path == input_path and not force:
        raise TaskError(
            f"{kind} resolves to the input file; pass --force to overwrite it: {path}"
        )
    if path.exists() and not force:
        raise TaskError(f"{kind} already exists; pass --force to overwrite it: {path}")
    if path.exists() and not path.is_file():
        raise TaskError(f"{kind} is not a regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def parse_patterns(raw_patterns: str | None) -> list[str]:
    if not raw_patterns:
        return []
    return [part.strip() for part in raw_patterns.split(",") if part.strip()]


def matches_patterns(name: str, patterns: Sequence[str]) -> bool:
    return not patterns or any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def target_objects(
    args: argparse.Namespace,
    *,
    types: set[str] | None = None,
    include_hidden: bool = True,
) -> list[bpy.types.Object]:
    patterns = parse_patterns(getattr(args, "objects", None))
    collection_name = getattr(args, "collection", None)
    if collection_name:
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            raise TaskError(f"Collection does not exist: {collection_name}")
        candidates = list(collection.all_objects)
    else:
        candidates = list(bpy.context.scene.objects)
    results = []
    for obj in candidates:
        if types is not None and obj.type not in types:
            continue
        if not include_hidden and obj.hide_get():
            continue
        if matches_patterns(obj.name, patterns):
            results.append(obj)
    return sorted(results, key=lambda item: item.name.casefold())


def ensure_object_mode() -> None:
    obj = bpy.context.object
    if obj is not None and obj.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError as exc:
            raise TaskError(f"Could not leave {obj.mode} mode: {exc}") from exc


def deselect_all() -> None:
    ensure_object_mode()
    for obj in bpy.context.selected_objects:
        obj.select_set(False)


def activate_only(obj: bpy.types.Object) -> None:
    deselect_all()
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def clear_scene() -> None:
    """Clear only the current in-memory scene before importing an external file."""
    ensure_object_mode()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def load_input(args: argparse.Namespace, report: dict[str, Any]) -> Path | None:
    raw_input = getattr(args, "input", None)
    if not raw_input:
        report["source"] = bpy.data.filepath or "<current-memory-scene>"
        return None
    input_path = path_from_user(
        raw_input,
        kind="input",
        must_exist=True,
        allowed_suffixes=SUPPORTED_INPUT_SUFFIXES,
    )
    suffix = input_path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(input_path), load_ui=False)
    else:
        clear_scene()
        if suffix in {".glb", ".gltf"}:
            bpy.ops.import_scene.gltf(filepath=str(input_path))
        elif suffix == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(input_path))
        elif suffix == ".obj":
            bpy.ops.wm.obj_import(filepath=str(input_path))
        elif suffix == ".stl":
            bpy.ops.wm.stl_import(filepath=str(input_path))
        elif suffix in {".usd", ".usda", ".usdc"}:
            bpy.ops.wm.usd_import(filepath=str(input_path))
        else:  # Kept defensive even though the suffix was checked above.
            raise TaskError(f"Unsupported input format: {suffix}")
    report["source"] = str(input_path)
    report["metrics"]["loaded_objects"] = len(bpy.context.scene.objects)
    return input_path


def save_blend(
    raw_output: str,
    *,
    force: bool,
    input_path: Path | None,
    report: dict[str, Any],
    pack_resources: bool = False,
    compress: bool = True,
) -> Path:
    output_path = prepare_output_file(
        raw_output,
        kind="blend output",
        force=force,
        allowed_suffixes={".blend"},
        input_path=input_path,
    )
    if pack_resources:
        try:
            bpy.ops.file.pack_all()
            change(report, "Packed external resources into the Blend file")
        except RuntimeError as exc:
            warn(report, "Some resources could not be packed", detail=str(exc))
    scene = bpy.context.scene
    scene[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    scene["forge3d_saved_at"] = utc_now()
    bpy.ops.wm.save_as_mainfile(
        filepath=str(output_path),
        check_existing=False,
        compress=compress,
        relative_remap=False,
    )
    report["outputs"]["blend"] = str(output_path)
    return output_path


def save_optional_output(
    args: argparse.Namespace,
    report: dict[str, Any],
    input_path: Path | None,
) -> Path | None:
    raw_output = getattr(args, "output", None)
    if not raw_output:
        warn(
            report,
            "No --output was supplied; changes exist only in this Blender process",
        )
        return None
    return save_blend(
        raw_output,
        force=args.force,
        input_path=input_path,
        report=report,
        pack_resources=getattr(args, "pack_resources", False),
        compress=not getattr(args, "no_compress", False),
    )


def object_world_bounds(
    objects: Iterable[bpy.types.Object],
) -> tuple[Vector, Vector] | None:
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    found = False
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], point[axis])
                maximum[axis] = max(maximum[axis], point[axis])
            found = True
    return (minimum, maximum) if found else None


def mesh_triangle_count(mesh: bpy.types.Mesh) -> int:
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj: bpy.types.Object) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def material_names(obj: bpy.types.Object) -> list[str | None]:
    if obj.type != "MESH":
        return []
    return [slot.material.name if slot.material else None for slot in obj.material_slots]


def iter_action_fcurves(action: bpy.types.Action) -> Iterator[bpy.types.FCurve]:
    """Yield legacy or Blender 5 slotted-action FCurves without duplication."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        yield from legacy
        return
    seen: set[int] = set()
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                for fcurve in channelbag.fcurves:
                    pointer = fcurve.as_pointer()
                    if pointer not in seen:
                        seen.add(pointer)
                        yield fcurve


def action_summary(action: bpy.types.Action) -> dict[str, Any]:
    fcurves = list(iter_action_fcurves(action))
    keyframe_count = sum(len(curve.keyframe_points) for curve in fcurves)
    slots = []
    for slot in getattr(action, "slots", []):
        slots.append(
            {
                "identifier": slot.identifier,
                "display_name": slot.name_display,
                "target_id_type": slot.target_id_type,
                "user_count": len(slot.users()),
            }
        )
    return {
        "name": action.name,
        "frame_range": [float(value) for value in action.frame_range],
        "fcurves": len(fcurves),
        "keyframes": keyframe_count,
        "slots": slots,
    }


def object_summary(obj: bpy.types.Object, *, evaluated: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "matrix_world": obj.matrix_world,
        "dimensions": list(obj.dimensions),
        "hidden_viewport": obj.hide_get(),
        "hidden_render": obj.hide_render,
        "collections": [collection.name for collection in obj.users_collection],
        "custom_properties": {
            key: json_safe(obj[key]) for key in obj.keys() if key != "_RNA_UI"
        },
    }
    if obj.type == "MESH":
        mesh = obj.data
        summary.update(
            {
                "mesh": mesh.name,
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
                "triangles": mesh_triangle_count(mesh),
                "evaluated_triangles": (
                    evaluated_triangle_count(obj) if evaluated else None
                ),
                "uv_layers": [layer.name for layer in mesh.uv_layers],
                "color_attributes": [attribute.name for attribute in mesh.color_attributes],
                "materials": material_names(obj),
                "shape_keys": (
                    [block.name for block in mesh.shape_keys.key_blocks]
                    if mesh.shape_keys
                    else []
                ),
                "modifiers": [
                    {"name": modifier.name, "type": modifier.type}
                    for modifier in obj.modifiers
                ],
            }
        )
    elif obj.type == "ARMATURE":
        armature = obj.data
        summary.update(
            {
                "armature": armature.name,
                "bones": len(armature.bones),
                "deform_bones": sum(1 for bone in armature.bones if bone.use_deform),
                "root_bones": [
                    bone.name for bone in armature.bones if bone.parent is None
                ],
            }
        )
    if obj.animation_data and obj.animation_data.action:
        summary["active_action"] = obj.animation_data.action.name
    return json_safe(summary)


def task_inspect(args: argparse.Namespace, report: dict[str, Any]) -> None:
    load_input(args, report)
    objects = target_objects(args)
    bounds = object_world_bounds(objects)
    scene = bpy.context.scene
    report["scene"] = {
        "name": scene.name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
        "unit_system": scene.unit_settings.system,
        "unit_scale": scene.unit_settings.scale_length,
        "render_engine": scene.render.engine,
        "collections": sorted(collection.name for collection in bpy.data.collections),
        "object_count": len(objects),
        "world_bounds": (
            {"min": bounds[0], "max": bounds[1], "size": bounds[1] - bounds[0]}
            if bounds
            else None
        ),
    }
    report["objects"] = [
        object_summary(obj, evaluated=args.evaluated) for obj in objects
    ]
    report["actions"] = [action_summary(action) for action in bpy.data.actions]
    missing_images = []
    for image in bpy.data.images:
        if image.source != "FILE" or image.packed_file:
            continue
        path = Path(bpy.path.abspath(image.filepath))
        if not path.exists():
            missing_images.append({"image": image.name, "path": str(path)})
    report["dependencies"] = {
        "images": len(bpy.data.images),
        "missing_images": missing_images,
        "libraries": [
            {"name": library.name, "path": bpy.path.abspath(library.filepath)}
            for library in bpy.data.libraries
        ],
    }
    report["metrics"].update(
        {
            "objects": len(objects),
            "meshes": sum(1 for obj in objects if obj.type == "MESH"),
            "armatures": sum(1 for obj in objects if obj.type == "ARMATURE"),
            "actions": len(bpy.data.actions),
            "triangles": sum(
                mesh_triangle_count(obj.data) for obj in objects if obj.type == "MESH"
            ),
        }
    )


def validate_mesh_object(
    obj: bpy.types.Object,
    args: argparse.Namespace,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    mesh = obj.data
    metric: dict[str, Any] = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "triangles": mesh_triangle_count(mesh),
        "materials": len(obj.material_slots),
        "uv_layers": len(mesh.uv_layers),
    }
    non_finite_vertices = sum(
        1
        for vertex in mesh.vertices
        if any(not math.isfinite(component) for component in vertex.co)
    )
    degenerate_faces = sum(1 for polygon in mesh.polygons if polygon.area <= args.epsilon)
    face_signatures: set[tuple[int, ...]] = set()
    duplicate_faces = 0
    for polygon in mesh.polygons:
        signature = tuple(sorted(polygon.vertices))
        if signature in face_signatures:
            duplicate_faces += 1
        else:
            face_signatures.add(signature)
    invalid_material_faces = sum(
        1
        for polygon in mesh.polygons
        if obj.material_slots and polygon.material_index >= len(obj.material_slots)
    )

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        topology_vertices_before_weld = len(bm.verts)
        if bm.verts:
            bmesh.ops.remove_doubles(
                bm,
                verts=list(bm.verts),
                dist=args.epsilon,
            )
        topology_welded_vertices = topology_vertices_before_weld - len(bm.verts)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose_vertices = sum(1 for vertex in bm.verts if not vertex.link_edges)
        loose_edges = sum(1 for edge in bm.edges if not edge.link_faces)
        boundary_edges = sum(1 for edge in bm.edges if edge.is_boundary)
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
    finally:
        bm.free()

    metric.update(
        {
            "non_finite_vertices": non_finite_vertices,
            "degenerate_faces": degenerate_faces,
            "duplicate_faces": duplicate_faces,
            "loose_vertices": loose_vertices,
            "loose_edges": loose_edges,
            "boundary_edges": boundary_edges,
            "non_manifold_edges": non_manifold_edges,
            "topology_welded_vertices": topology_welded_vertices,
            "negative_world_determinant": obj.matrix_world.to_3x3().determinant() < 0,
        }
    )

    if non_finite_vertices:
        issue(
            issues,
            "error",
            "mesh.non_finite_vertex",
            f"{non_finite_vertices} vertices contain NaN or infinite coordinates",
            object_name=obj.name,
            count=non_finite_vertices,
        )
    if degenerate_faces:
        issue(
            issues,
            "error",
            "mesh.degenerate_faces",
            f"{degenerate_faces} faces have negligible area",
            object_name=obj.name,
            count=degenerate_faces,
        )
    if duplicate_faces:
        issue(
            issues,
            "error",
            "mesh.duplicate_faces",
            f"{duplicate_faces} faces reuse the same vertices",
            object_name=obj.name,
            count=duplicate_faces,
        )
    if loose_vertices or loose_edges:
        issue(
            issues,
            "warning",
            "mesh.loose_geometry",
            "Mesh contains loose geometry",
            object_name=obj.name,
            loose_vertices=loose_vertices,
            loose_edges=loose_edges,
        )
    if non_manifold_edges:
        severity = "error" if args.strict_manifold else "warning"
        issue(
            issues,
            severity,
            "mesh.non_manifold_edges",
            f"{non_manifold_edges} edges are not manifold",
            object_name=obj.name,
            count=non_manifold_edges,
            boundary_edges=boundary_edges,
        )
    if invalid_material_faces:
        issue(
            issues,
            "error",
            "mesh.invalid_material_index",
            "Faces reference material slots that do not exist",
            object_name=obj.name,
            count=invalid_material_faces,
        )
    if metric["triangles"] > args.max_triangles:
        issue(
            issues,
            "error",
            "budget.triangles",
            f"Triangle count exceeds the {args.max_triangles} budget",
            object_name=obj.name,
            actual=metric["triangles"],
            budget=args.max_triangles,
        )
    if len(obj.material_slots) > args.max_materials:
        issue(
            issues,
            "error",
            "budget.materials",
            f"Material count exceeds the {args.max_materials} budget",
            object_name=obj.name,
            actual=len(obj.material_slots),
            budget=args.max_materials,
        )
    if any(abs(value) <= args.epsilon for value in obj.scale):
        issue(
            issues,
            "error",
            "transform.zero_scale",
            "Object has a zero scale axis",
            object_name=obj.name,
            scale=list(obj.scale),
        )
    elif any(abs(value - 1.0) > args.transform_tolerance for value in obj.scale):
        issue(
            issues,
            "warning",
            "transform.unapplied_scale",
            "Object scale is not applied",
            object_name=obj.name,
            scale=list(obj.scale),
        )
    if any(abs(value) > args.transform_tolerance for value in obj.rotation_euler):
        issue(
            issues,
            "warning",
            "transform.unapplied_rotation",
            "Object rotation is not applied",
            object_name=obj.name,
            rotation_euler=list(obj.rotation_euler),
        )
    if obj.matrix_world.to_3x3().determinant() < 0:
        issue(
            issues,
            "warning",
            "transform.negative_determinant",
            "World transform mirrors the mesh and may flip winding",
            object_name=obj.name,
        )

    is_collision = bool(obj.get("forge3d_collision")) or obj.name.endswith(
        (
            "-col",
            "-colonly",
            "-convcol",
            "-convcolonly",
            "_COL",
            "_collision",
        )
    )
    metric["collision_mesh"] = is_collision
    if not mesh.uv_layers and not is_collision:
        severity = "error" if args.require_uv else "warning"
        issue(
            issues,
            severity,
            "uv.missing",
            "Mesh has no UV layer",
            object_name=obj.name,
        )
    elif mesh.uv_layers:
        active_uv = mesh.uv_layers.active
        invalid_uv = 0
        outside_uv = 0
        if active_uv is not None:
            for datum in active_uv.data:
                u, v = datum.uv
                if not math.isfinite(u) or not math.isfinite(v):
                    invalid_uv += 1
                if u < -args.uv_tolerance or u > 1 + args.uv_tolerance:
                    outside_uv += 1
                if v < -args.uv_tolerance or v > 1 + args.uv_tolerance:
                    outside_uv += 1
        metric["invalid_uv_loops"] = invalid_uv
        metric["uv_components_outside_zero_one"] = outside_uv
        if invalid_uv:
            issue(
                issues,
                "error",
                "uv.non_finite",
                "UV map contains NaN or infinite values",
                object_name=obj.name,
                count=invalid_uv,
            )
        if outside_uv and not args.allow_tiled_uv:
            issue(
                issues,
                "warning",
                "uv.outside_zero_one",
                "UV coordinates extend outside the 0–1 tile",
                object_name=obj.name,
                component_count=outside_uv,
            )

    armature = obj.find_armature()
    if armature:
        bone_names = {bone.name for bone in armature.data.bones if bone.use_deform}
        bone_group_indices = {
            group.index for group in obj.vertex_groups if group.name in bone_names
        }
        unweighted = 0
        over_influence = 0
        bad_weight_sum = 0
        max_influences = 0
        for vertex in mesh.vertices:
            weights = [
                element.weight
                for element in vertex.groups
                if element.group in bone_group_indices
                and element.weight > args.weight_epsilon
            ]
            max_influences = max(max_influences, len(weights))
            if not weights:
                unweighted += 1
            if len(weights) > args.max_influences:
                over_influence += 1
            if weights and abs(sum(weights) - 1.0) > args.weight_tolerance:
                bad_weight_sum += 1
        metric.update(
            {
                "armature": armature.name,
                "unweighted_vertices": unweighted,
                "vertices_over_influence_limit": over_influence,
                "vertices_with_bad_weight_sum": bad_weight_sum,
                "maximum_influences": max_influences,
            }
        )
        if unweighted:
            issue(
                issues,
                "error",
                "rig.unweighted_vertices",
                f"{unweighted} vertices have no deform-bone weights",
                object_name=obj.name,
                count=unweighted,
            )
        if over_influence:
            issue(
                issues,
                "error",
                "rig.too_many_influences",
                f"{over_influence} vertices exceed {args.max_influences} influences",
                object_name=obj.name,
                count=over_influence,
                maximum=max_influences,
            )
        if bad_weight_sum:
            issue(
                issues,
                "error",
                "rig.weight_sum",
                f"{bad_weight_sum} vertices have non-normalized deform weights",
                object_name=obj.name,
                count=bad_weight_sum,
                tolerance=args.weight_tolerance,
            )
    return metric


def validate_armature_object(
    obj: bpy.types.Object,
    args: argparse.Namespace,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    bones = obj.data.bones
    deform_bones = [bone for bone in bones if bone.use_deform]
    roots = [bone for bone in bones if bone.parent is None]
    zero_length = [
        bone.name for bone in bones if (bone.tail_local - bone.head_local).length <= args.epsilon
    ]
    duplicate_deform_names = len({bone.name.casefold() for bone in deform_bones}) != len(
        deform_bones
    )
    metric = {
        "bones": len(bones),
        "deform_bones": len(deform_bones),
        "root_bones": [bone.name for bone in roots],
        "zero_length_bones": zero_length,
    }
    if len(deform_bones) > args.max_bones:
        issue(
            issues,
            "error",
            "budget.bones",
            f"Deform bone count exceeds the {args.max_bones} budget",
            object_name=obj.name,
            actual=len(deform_bones),
            budget=args.max_bones,
        )
    if not roots:
        issue(
            issues,
            "error",
            "rig.no_root",
            "Armature has no root bone",
            object_name=obj.name,
        )
    elif len(roots) > 1:
        issue(
            issues,
            "warning",
            "rig.multiple_roots",
            "Armature has multiple root bones",
            object_name=obj.name,
            roots=[bone.name for bone in roots],
        )
    if zero_length:
        issue(
            issues,
            "error",
            "rig.zero_length_bone",
            "Armature contains zero-length bones",
            object_name=obj.name,
            bones=zero_length,
        )
    if duplicate_deform_names:
        issue(
            issues,
            "error",
            "rig.case_collision",
            "Deform bone names collide when compared case-insensitively",
            object_name=obj.name,
        )
    return metric


def validate_animation_data(
    args: argparse.Namespace,
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for action in bpy.data.actions:
        summary = action_summary(action)
        fcurves = list(iter_action_fcurves(action))
        invalid_keys = 0
        duplicate_channels = 0
        channel_ids: set[tuple[str, int]] = set()
        for fcurve in fcurves:
            channel_id = (fcurve.data_path, fcurve.array_index)
            if channel_id in channel_ids:
                duplicate_channels += 1
            channel_ids.add(channel_id)
            for keyframe in fcurve.keyframe_points:
                if any(not math.isfinite(value) for value in keyframe.co):
                    invalid_keys += 1
        summary.update(
            {
                "invalid_keyframes": invalid_keys,
                "duplicate_channels": duplicate_channels,
            }
        )
        metrics.append(summary)
        if not fcurves:
            issue(
                issues,
                "warning",
                "animation.empty_action",
                f"Action {action.name!r} has no F-Curves",
            )
        if invalid_keys:
            issue(
                issues,
                "error",
                "animation.non_finite_keyframe",
                f"Action {action.name!r} contains non-finite keyframes",
                count=invalid_keys,
            )
        if duplicate_channels:
            issue(
                issues,
                "warning",
                "animation.duplicate_channels",
                f"Action {action.name!r} contains duplicate data-path channels",
                count=duplicate_channels,
            )
        start, end = action.frame_range
        if end < start:
            issue(
                issues,
                "error",
                "animation.invalid_range",
                f"Action {action.name!r} has an invalid frame range",
                frame_range=[start, end],
            )
        if args.max_animation_frames and (end - start) > args.max_animation_frames:
            issue(
                issues,
                "warning",
                "animation.long_clip",
                f"Action {action.name!r} exceeds the preferred clip length",
                frames=end - start,
                preferred_max=args.max_animation_frames,
            )
    return metrics


def task_validate(args: argparse.Namespace, report: dict[str, Any]) -> None:
    load_input(args, report)
    objects = target_objects(args)
    issues: list[dict[str, Any]] = []
    mesh_metrics = {}
    armature_metrics = {}
    for obj in objects:
        if obj.type == "MESH":
            mesh_metrics[obj.name] = validate_mesh_object(obj, args, issues)
        elif obj.type == "ARMATURE":
            armature_metrics[obj.name] = validate_armature_object(obj, args, issues)

    for image in bpy.data.images:
        if image.source == "FILE" and image.packed_file is None:
            image_path = Path(bpy.path.abspath(image.filepath))
            if not image_path.is_file():
                issue(
                    issues,
                    "error",
                    "dependency.missing_image",
                    f"Image file is missing: {image.name}",
                    path=str(image_path),
                )

    animation_metrics = (
        validate_animation_data(args, issues) if args.include_animation else []
    )
    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    report["issues"] = issues
    report["passed"] = not errors
    report["metrics"].update(
        {
            "objects_checked": len(objects),
            "mesh_metrics": mesh_metrics,
            "armature_metrics": armature_metrics,
            "animation_metrics": animation_metrics,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }
    )
    report["warnings"].extend(warnings)
    report["errors"].extend(errors)
    if errors and args.no_fail:
        warn(report, "Validation errors were ignored because --no-fail was supplied")


def apply_transforms(
    objects: Sequence[bpy.types.Object],
    *,
    location: bool,
    rotation: bool,
    scale: bool,
) -> None:
    if not objects:
        return
    ensure_object_mode()
    deselect_all()
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    try:
        bpy.ops.object.transform_apply(
            location=location,
            rotation=rotation,
            scale=scale,
            properties=False,
        )
    except RuntimeError as exc:
        raise TaskError(f"Could not apply transforms: {exc}") from exc
    finally:
        deselect_all()


def root_objects(objects: Sequence[bpy.types.Object]) -> list[bpy.types.Object]:
    object_set = set(objects)
    return [obj for obj in objects if obj.parent not in object_set]


def set_object_origin(
    obj: bpy.types.Object,
    mode: str,
    report: dict[str, Any],
) -> None:
    if obj.type != "MESH":
        return
    activate_only(obj)
    if mode == "geometry":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="MEDIAN")
    elif mode == "bounds":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    elif mode == "base":
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        minimum_z = min(point.z for point in corners)
        center = sum(corners, Vector()) / len(corners)
        previous_cursor = bpy.context.scene.cursor.location.copy()
        try:
            bpy.context.scene.cursor.location = (center.x, center.y, minimum_z)
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
        finally:
            bpy.context.scene.cursor.location = previous_cursor
    else:
        return
    change(report, "Set object origin", object=obj.name, mode=mode)


def task_normalize(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    objects = target_objects(
        args,
        types={"MESH", "CURVE", "SURFACE", "FONT", "ARMATURE", "EMPTY"},
    )
    if not objects:
        raise TaskError("No supported objects matched the normalization target")
    scene = bpy.context.scene
    if args.metric:
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        scene.unit_settings.length_unit = "METERS"
        change(report, "Configured the scene for metric units")

    apply_transforms(
        objects,
        location=args.apply_location,
        rotation=args.apply_rotation,
        scale=args.apply_scale,
    )
    if args.apply_location or args.apply_rotation or args.apply_scale:
        change(
            report,
            "Applied object transforms",
            objects=[obj.name for obj in objects],
            location=args.apply_location,
            rotation=args.apply_rotation,
            scale=args.apply_scale,
        )

    if args.target_size is not None:
        if args.target_size <= 0:
            raise TaskError("--target-size must be greater than zero")
        bounds = object_world_bounds(objects)
        if bounds is None:
            raise TaskError("Target objects have no measurable bounds")
        current_size = max(bounds[1] - bounds[0])
        if current_size <= EPSILON:
            raise TaskError("Target objects have zero world-space size")
        factor = args.target_size / current_size
        roots = root_objects(objects)
        for obj in roots:
            obj.scale = tuple(component * factor for component in obj.scale)
        if args.apply_scale:
            apply_transforms(objects, location=False, rotation=False, scale=True)
        change(
            report,
            "Scaled target objects to the requested maximum dimension",
            old_size=current_size,
            new_size=args.target_size,
            factor=factor,
        )

    if args.ground:
        bounds = object_world_bounds(objects)
        if bounds is None:
            raise TaskError("Target objects have no measurable bounds")
        offset = -bounds[0].z
        for obj in root_objects(objects):
            obj.location.z += offset
        change(report, "Grounded objects at Z=0", z_offset=offset)

    if args.origin != "keep":
        for obj in objects:
            set_object_origin(obj, args.origin, report)

    final_bounds = object_world_bounds(objects)
    report["metrics"].update(
        {
            "objects_normalized": len(objects),
            "final_bounds": (
                {
                    "min": final_bounds[0],
                    "max": final_bounds[1],
                    "size": final_bounds[1] - final_bounds[0],
                }
                if final_bounds
                else None
            ),
        }
    )
    save_optional_output(args, report, input_path)


def apply_all_modifiers(obj: bpy.types.Object, report: dict[str, Any]) -> int:
    applied = 0
    for modifier in list(obj.modifiers):
        activate_only(obj)
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError as exc:
            warn(
                report,
                "Modifier could not be applied",
                object=obj.name,
                modifier=modifier.name,
                detail=str(exc),
            )
            continue
        applied += 1
    return applied


def repair_mesh(
    obj: bpy.types.Object,
    args: argparse.Namespace,
) -> dict[str, int]:
    mesh = obj.data
    before = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
    }
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        if args.merge_distance > 0 and bm.verts:
            if args.merge_across_islands:
                components = [list(bm.verts)]
            else:
                remaining = set(bm.verts)
                components = []
                while remaining:
                    seed = remaining.pop()
                    component = [seed]
                    stack = [seed]
                    while stack:
                        vertex = stack.pop()
                        for edge in vertex.link_edges:
                            neighbour = edge.other_vert(vertex)
                            if neighbour in remaining:
                                remaining.remove(neighbour)
                                component.append(neighbour)
                                stack.append(neighbour)
                    components.append(component)
            for component in components:
                bmesh.ops.remove_doubles(
                    bm,
                    verts=component,
                    dist=args.merge_distance,
                )
        if args.degenerate_distance > 0 and bm.edges:
            bmesh.ops.dissolve_degenerate(
                bm,
                edges=list(bm.edges),
                dist=args.degenerate_distance,
            )
            negligible_faces = [
                face
                for face in bm.faces
                if face.calc_area() <= args.degenerate_distance
            ]
            if negligible_faces:
                bmesh.ops.delete(
                    bm,
                    geom=negligible_faces,
                    context="FACES",
                )
        if args.delete_loose:
            loose_edges = [edge for edge in bm.edges if not edge.link_faces]
            if loose_edges:
                bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
            loose_vertices = [vertex for vertex in bm.verts if not vertex.link_edges]
            if loose_vertices:
                bmesh.ops.delete(bm, geom=loose_vertices, context="VERTS")
        if args.fill_holes:
            boundary_edges = [edge for edge in bm.edges if edge.is_boundary]
            if boundary_edges:
                bmesh.ops.holes_fill(
                    bm,
                    edges=boundary_edges,
                    sides=args.max_hole_sides,
                )
        if args.recalculate_normals and bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update(calc_edges=True, calc_edges_loose=True)
    after = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
    }
    return {
        "vertices_removed": before["vertices"] - after["vertices"],
        "edges_removed": before["edges"] - after["edges"],
        "polygons_removed": before["polygons"] - after["polygons"],
        **{f"final_{key}": value for key, value in after.items()},
    }


def task_repair(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    objects = target_objects(args, types={"MESH"})
    if not objects:
        raise TaskError("No mesh objects matched the repair target")
    metrics = {}
    total_modifiers = 0
    for obj in objects:
        if args.apply_modifiers:
            total_modifiers += apply_all_modifiers(obj, report)
        metrics[obj.name] = repair_mesh(obj, args)
        change(report, "Repaired mesh", object=obj.name, **metrics[obj.name])
    report["metrics"].update(
        {
            "objects_repaired": len(objects),
            "modifiers_applied": total_modifiers,
            "per_object": metrics,
        }
    )
    save_optional_output(args, report, input_path)


def unwrap_object(obj: bpy.types.Object, args: argparse.Namespace) -> None:
    activate_only(obj)
    if not obj.data.polygons:
        return
    if args.replace_uv and obj.data.uv_layers.get(args.uv_name):
        obj.data.uv_layers.remove(obj.data.uv_layers[args.uv_name])
    layer = obj.data.uv_layers.get(args.uv_name)
    if layer is None:
        layer = obj.data.uv_layers.new(name=args.uv_name)
    obj.data.uv_layers.active = layer
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        if args.method == "smart":
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(args.angle_limit),
                island_margin=args.island_margin,
                area_weight=args.area_weight,
                correct_aspect=True,
                scale_to_bounds=True,
            )
        elif args.method == "lightmap":
            bpy.ops.uv.lightmap_pack(
                PREF_CONTEXT="ALL_FACES",
                PREF_PACK_IN_ONE=True,
                PREF_NEW_UVLAYER=False,
                PREF_BOX_DIV=args.box_divisions,
                PREF_MARGIN_DIV=args.margin_divisions,
            )
        elif args.method == "cube":
            bpy.ops.uv.cube_project(
                cube_size=args.cube_size,
                correct_aspect=True,
                clip_to_bounds=False,
                scale_to_bounds=True,
            )
        elif args.method == "cylinder":
            bpy.ops.uv.cylinder_project(
                direction="ALIGN_TO_OBJECT",
                align="POLAR_ZX",
                radius=1.0,
                correct_aspect=True,
                clip_to_bounds=False,
                scale_to_bounds=True,
            )
        else:
            raise TaskError(f"Unknown unwrap method: {args.method}")
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def task_unwrap(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    objects = target_objects(args, types={"MESH"})
    if not objects:
        raise TaskError("No mesh objects matched the unwrap target")
    metrics = {}
    for obj in objects:
        unwrap_object(obj, args)
        metrics[obj.name] = {
            "uv_layer": obj.data.uv_layers.active.name,
            "uv_loops": len(obj.data.uv_layers.active.data),
            "method": args.method,
        }
        change(
            report,
            "Generated UV layout",
            object=obj.name,
            method=args.method,
            uv_layer=obj.data.uv_layers.active.name,
        )
    report["metrics"]["per_object"] = metrics
    save_optional_output(args, report, input_path)


def parse_color(raw: str) -> tuple[float, float, float, float]:
    try:
        values = [float(part.strip()) for part in raw.split(",")]
    except ValueError as exc:
        raise TaskError(f"Invalid colour value: {raw}") from exc
    if len(values) == 3:
        values.append(1.0)
    if len(values) != 4 or any(not math.isfinite(value) for value in values):
        raise TaskError("Colour must contain three or four finite comma-separated values")
    return tuple(max(0.0, min(1.0, value)) for value in values)  # type: ignore[return-value]


def node_input(node: bpy.types.Node, *names: str) -> bpy.types.NodeSocket:
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    raise TaskError(
        f"Node {node.bl_idname} does not expose any expected input: {', '.join(names)}"
    )


def load_texture(raw_path: str, *, non_color: bool) -> bpy.types.Image:
    path = path_from_user(raw_path, kind="texture", must_exist=True)
    image = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        try:
            image.colorspace_settings.name = "Non-Color"
        except TypeError:
            image.colorspace_settings.name = "Linear"
    else:
        try:
            image.colorspace_settings.name = "sRGB"
        except TypeError:
            pass
    return image


def create_pbr_material(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> bpy.types.Material:
    if not 0.0 <= args.metallic <= 1.0:
        raise TaskError("--metallic must be between zero and one")
    if not 0.0 <= args.roughness <= 1.0:
        raise TaskError("--roughness must be between zero and one")
    if args.normal_strength < 0 or args.emission_strength < 0:
        raise TaskError("Normal and emission strengths must not be negative")
    existing = bpy.data.materials.get(args.material_name)
    if existing and not args.replace_existing:
        raise TaskError(
            f"Material {args.material_name!r} already exists; "
            "pass --replace-existing to rebuild it"
        )
    if existing:
        bpy.data.materials.remove(existing, do_unlink=True)
    material = bpy.data.materials.new(args.material_name)
    material[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    material.use_nodes = True
    material.diffuse_color = parse_color(args.base_color)
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.name = "Material Output"
    output.location = (700, 0)
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "Principled BSDF"
    principled.location = (400, 0)
    node_input(principled, "Base Color").default_value = material.diffuse_color
    node_input(principled, "Metallic").default_value = args.metallic
    node_input(principled, "Roughness").default_value = args.roughness
    node_input(principled, "Alpha").default_value = material.diffuse_color[3]
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    texture_nodes: dict[str, bpy.types.Node] = {}

    def add_image_node(
        role: str,
        raw_path: str | None,
        *,
        non_color: bool,
        location: tuple[int, int],
    ) -> bpy.types.Node | None:
        if not raw_path:
            return None
        node = tree.nodes.new("ShaderNodeTexImage")
        node.name = f"{role.title()} Texture"
        node.label = role.replace("_", " ").title()
        node.location = location
        node.image = load_texture(raw_path, non_color=non_color)
        texture_nodes[role] = node
        return node

    base = add_image_node(
        "base_color", args.base_color_map, non_color=False, location=(-600, 250)
    )
    ao = add_image_node("ao", args.ao_map, non_color=True, location=(-600, 0))
    if base and ao:
        multiply = tree.nodes.new("ShaderNodeMixRGB")
        multiply.name = "Base Color x AO"
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1.0
        multiply.location = (100, 250)
        tree.links.new(base.outputs["Color"], multiply.inputs[1])
        tree.links.new(ao.outputs["Color"], multiply.inputs[2])
        tree.links.new(multiply.outputs["Color"], node_input(principled, "Base Color"))
    elif base:
        tree.links.new(base.outputs["Color"], node_input(principled, "Base Color"))
    elif ao:
        multiply = tree.nodes.new("ShaderNodeMixRGB")
        multiply.name = "Base Color x AO"
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1.0
        multiply.inputs[1].default_value = material.diffuse_color
        multiply.location = (100, 250)
        tree.links.new(ao.outputs["Color"], multiply.inputs[2])
        tree.links.new(multiply.outputs["Color"], node_input(principled, "Base Color"))
    if base and args.use_texture_alpha:
        tree.links.new(base.outputs["Alpha"], node_input(principled, "Alpha"))

    roughness = add_image_node(
        "roughness", args.roughness_map, non_color=True, location=(-600, -150)
    )
    if roughness:
        tree.links.new(roughness.outputs["Color"], node_input(principled, "Roughness"))
    metallic = add_image_node(
        "metallic", args.metallic_map, non_color=True, location=(-600, -300)
    )
    if metallic:
        tree.links.new(metallic.outputs["Color"], node_input(principled, "Metallic"))
    normal = add_image_node(
        "normal", args.normal_map, non_color=True, location=(-600, -450)
    )
    if normal:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        normal_map.name = "Normal Map"
        normal_map.inputs["Strength"].default_value = args.normal_strength
        normal_map.location = (100, -350)
        tree.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        tree.links.new(normal_map.outputs["Normal"], node_input(principled, "Normal"))
    emission = add_image_node(
        "emission", args.emission_map, non_color=False, location=(-600, -600)
    )
    if emission:
        tree.links.new(
            emission.outputs["Color"],
            node_input(principled, "Emission Color", "Emission"),
        )
        emission_strength = principled.inputs.get("Emission Strength")
        if emission_strength:
            emission_strength.default_value = args.emission_strength

    report["metrics"]["material"] = {
        "name": material.name,
        "textures": {
            role: bpy.path.abspath(node.image.filepath)
            for role, node in texture_nodes.items()
        },
    }
    return material


def task_material(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    objects = target_objects(args, types={"MESH"})
    if not objects:
        raise TaskError("No mesh objects matched the material target")
    material = create_pbr_material(args, report)
    for obj in objects:
        if args.replace_materials:
            obj.data.materials.clear()
        if obj.data.materials.get(material.name) is None:
            obj.data.materials.append(material)
        slot_index = list(obj.data.materials).index(material)
        for polygon in obj.data.polygons:
            polygon.material_index = slot_index
        change(report, "Assigned PBR material", object=obj.name, material=material.name)
    save_optional_output(args, report, input_path)


def ensure_tool_collection(
    name: str,
    *,
    replace_existing: bool,
) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
        collection[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
        return collection
    owner = collection.get(GENERATED_BY_KEY)
    if owner is None:
        raise TaskError(
            f"Collection {name!r} already exists and is not owned by Forge3D"
        )
    if replace_existing:
        objects = list(collection.objects)
        unowned = [obj.name for obj in objects if not obj.get(GENERATED_BY_KEY)]
        if unowned:
            raise TaskError(
                f"Refusing to clear {name!r}; it contains non-Forge3D objects: "
                + ", ".join(unowned)
            )
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    return collection


def link_object_only_to(
    obj: bpy.types.Object,
    collection: bpy.types.Collection,
) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def parse_ratios(raw: str) -> list[float]:
    try:
        ratios = [float(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise TaskError(f"Invalid LOD ratios: {raw}") from exc
    if not ratios:
        raise TaskError("At least one LOD ratio is required")
    if len(ratios) > 8:
        raise TaskError("At most eight LOD ratios may be generated in one task")
    if any(not math.isfinite(ratio) or ratio <= 0 or ratio >= 1 for ratio in ratios):
        raise TaskError("Every LOD ratio must be finite and between zero and one")
    if ratios != sorted(ratios, reverse=True):
        raise TaskError("LOD ratios must be supplied in descending order")
    return ratios


def task_lods(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    sources = [
        obj
        for obj in target_objects(args, types={"MESH"})
        if not obj.get("forge3d_lod_level")
        and not obj.name.rsplit(".", 1)[0].endswith(tuple(f"_LOD{i}" for i in range(9)))
    ]
    if not sources:
        raise TaskError("No base mesh objects matched the LOD target")
    ratios = parse_ratios(args.ratios)
    collection = ensure_tool_collection(
        args.lod_collection,
        replace_existing=args.replace_existing,
    )
    per_object: dict[str, Any] = {}
    for source in sources:
        source_triangles = mesh_triangle_count(source.data)
        lod_metrics = []
        for level, ratio in enumerate(ratios, start=1):
            name = f"{source.name}_LOD{level}"
            if bpy.data.objects.get(name) is not None:
                raise TaskError(
                    f"LOD object {name!r} already exists; use --replace-existing "
                    "to rebuild the generated LOD collection"
                )
            duplicate = source.copy()
            duplicate.data = source.data.copy()
            duplicate.name = name
            duplicate.data.name = f"{name}_Mesh"
            collection.objects.link(duplicate)
            duplicate[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
            duplicate["forge3d_lod_level"] = level
            duplicate["forge3d_lod_ratio"] = ratio
            duplicate["forge3d_source_only"] = True
            duplicate.hide_render = True
            decimate = duplicate.modifiers.new("Forge3D Decimate", "DECIMATE")
            decimate.decimate_type = "COLLAPSE"
            decimate.ratio = ratio
            decimate.use_collapse_triangulate = args.triangulate
            activate_only(duplicate)
            try:
                bpy.ops.object.modifier_apply(modifier=decimate.name)
            except RuntimeError as exc:
                bpy.data.objects.remove(duplicate, do_unlink=True)
                raise TaskError(f"Could not generate {name}: {exc}") from exc
            corrected = duplicate.data.validate(clean_customdata=False)
            duplicate.data.update(calc_edges=True, calc_edges_loose=True)
            if corrected:
                warn(
                    report,
                    "Blender corrected invalid topology produced by Decimate",
                    object=name,
                )
            final_triangles = mesh_triangle_count(duplicate.data)
            lod_metrics.append(
                {
                    "name": name,
                    "level": level,
                    "ratio": ratio,
                    "triangles": final_triangles,
                    "mesh_corrected": corrected,
                    "actual_ratio": (
                        final_triangles / source_triangles if source_triangles else 0
                    ),
                }
            )
            change(
                report,
                "Generated LOD",
                source=source.name,
                lod=name,
                requested_ratio=ratio,
                triangles=final_triangles,
            )
        per_object[source.name] = {
            "source_triangles": source_triangles,
            "lods": lod_metrics,
        }
    report["metrics"].update(
        {
            "sources": len(sources),
            "generated_lods": len(sources) * len(ratios),
            "per_object": per_object,
        }
    )
    save_optional_output(args, report, input_path)


def box_mesh_from_bound_box(
    source: bpy.types.Object,
    name: str,
) -> bpy.types.Mesh:
    vertices = [tuple(corner) for corner in source.bound_box]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    return mesh


def convex_hull_mesh(
    source: bpy.types.Object,
    name: str,
) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for vertex in source.data.vertices:
            bm.verts.new(vertex.co)
        bm.verts.ensure_lookup_table()
        if len(bm.verts) < 4:
            raise TaskError(
                f"Mesh {source.name!r} needs at least four vertices for a convex hull"
            )
        result = bmesh.ops.convex_hull(
            bm,
            input=list(bm.verts),
            use_existing_faces=False,
        )
        # Blender can return the same element in both result sets.  Passing the
        # duplicate through to bmesh.ops.delete raises a ValueError in 5.0.
        removable = list(
            {
                element
                for key in ("geom_interior", "geom_unused")
                for element in result.get(key, [])
            }
        )
        if removable:
            bmesh.ops.delete(bm, geom=removable, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update(calc_edges=True)
    return mesh


def collision_mesh_copy(
    source: bpy.types.Object,
    name: str,
    ratio: float,
) -> bpy.types.Object:
    duplicate = source.copy()
    duplicate.data = source.data.copy()
    duplicate.name = name
    duplicate.data.name = f"{name}_Mesh"
    if ratio < 1:
        decimate = duplicate.modifiers.new("Forge3D Collision Decimate", "DECIMATE")
        decimate.ratio = ratio
    return duplicate


def task_collision(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    sources = [
        obj
        for obj in target_objects(args, types={"MESH"})
        if not obj.get("forge3d_collision")
        and not obj.name.endswith(
            (
                "-col",
                "-colonly",
                "-convcol",
                "-convcolonly",
                "_COL",
                "_collision",
            )
        )
        and (args.include_lods or not obj.get("forge3d_lod_level"))
    ]
    if not sources:
        raise TaskError("No source meshes matched the collision target")
    if args.ratio <= 0 or args.ratio > 1:
        raise TaskError("--ratio must be greater than zero and at most one")
    collection = ensure_tool_collection(
        args.collision_collection,
        replace_existing=args.replace_existing,
    )
    metrics = {}
    for source in sources:
        suffix = "-colonly" if args.mode == "mesh" else "-convcolonly"
        name = f"{source.name}{suffix}"
        if bpy.data.objects.get(name) is not None:
            raise TaskError(
                f"Collision object {name!r} already exists; pass --replace-existing"
            )
        if args.mode == "box":
            mesh = box_mesh_from_bound_box(source, f"{name}_Mesh")
            collision = bpy.data.objects.new(name, mesh)
            collision.matrix_world = source.matrix_world.copy()
        elif args.mode == "convex":
            mesh = convex_hull_mesh(source, f"{name}_Mesh")
            collision = bpy.data.objects.new(name, mesh)
            collision.matrix_world = source.matrix_world.copy()
        elif args.mode == "mesh":
            collision = collision_mesh_copy(source, name, args.ratio)
        else:
            raise TaskError(f"Unsupported collision mode: {args.mode}")
        if not collision.users_collection:
            collection.objects.link(collision)
        collision.data.validate(clean_customdata=False)
        collision.data.update(calc_edges=True, calc_edges_loose=True)
        collision.display_type = "WIRE"
        collision.hide_render = True
        collision[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
        collision["forge3d_collision"] = True
        collision["forge3d_collision_mode"] = args.mode
        if args.mode == "mesh" and args.ratio < 1:
            activate_only(collision)
            bpy.ops.object.modifier_apply(modifier="Forge3D Collision Decimate")
        metrics[source.name] = {
            "collision": collision.name,
            "mode": args.mode,
            "triangles": mesh_triangle_count(collision.data),
        }
        change(
            report,
            "Generated collision geometry",
            source=source.name,
            collision=collision.name,
            mode=args.mode,
        )
    report["metrics"]["per_object"] = metrics
    save_optional_output(args, report, input_path)


def remove_tool_collection_objects(collection: bpy.types.Collection) -> None:
    for obj in list(collection.objects):
        if obj.get(GENERATED_BY_KEY):
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            raise TaskError(
                f"Review collection contains a non-Forge3D object: {obj.name}"
            )


def create_review_camera(
    collection: bpy.types.Collection,
    center: Vector,
    radius: float,
    lens: float,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("Forge3D_ReviewCamera")
    camera_data.lens = lens
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new("Forge3D_ReviewCamera", camera_data)
    camera[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection.objects.link(camera)
    distance = max(radius * 3.0, 0.5)
    camera.location = center + Vector((distance, -distance, distance * 0.65))
    look_at(camera, center)
    bpy.context.scene.camera = camera
    return camera


def create_area_light(
    collection: bpy.types.Collection,
    name: str,
    center: Vector,
    offset: Vector,
    *,
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> bpy.types.Object:
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection.objects.link(obj)
    obj.location = center + offset
    look_at(obj, center)
    return obj


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    if direction.length <= EPSILON:
        direction = Vector((0, 0, -1))
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_review_world(scene: bpy.types.Scene, strength: float) -> None:
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("Forge3D_ReviewWorld")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.035, 0.045, 0.06, 1.0)
        background.inputs["Strength"].default_value = strength


def turntable_output_paths(
    raw_output: str,
    frames: int,
    *,
    force: bool,
) -> list[Path]:
    base = path_from_user(raw_output, kind="render output", must_exist=False)
    if frames == 1:
        if base.suffix.lower() != ".png":
            raise TaskError("A single-frame turntable output must end in .png")
        outputs = [base]
    elif base.suffix:
        if base.suffix.lower() != ".png":
            raise TaskError("Turntable image paths must use the .png extension")
        outputs = [
            base.with_name(f"{base.stem}_{frame:03d}.png")
            for frame in range(1, frames + 1)
        ]
    else:
        outputs = [base / f"turntable_{frame:03d}.png" for frame in range(1, frames + 1)]
    collisions = [path for path in outputs if path.exists()]
    if collisions and not force:
        raise TaskError(
            f"{len(collisions)} render outputs already exist; pass --force to overwrite"
        )
    for path in outputs:
        if path.exists() and not path.is_file():
            raise TaskError(f"Render output is not a regular file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    return outputs


def task_turntable(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    renderable_types = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
    if args.armature:
        armature = get_armature(args.armature)
        objects = [
            obj
            for obj in armature_export_objects(armature)
            if obj.type in renderable_types
        ]
    else:
        objects = target_objects(
            args,
            types=renderable_types,
            include_hidden=False,
        )
    if not objects:
        raise TaskError("No renderable objects matched the turntable target")
    if args.frames < 1 or args.frames > 72:
        raise TaskError("--frames must be between 1 and 72")
    if args.resolution < 64 or args.resolution > 4096:
        raise TaskError("--resolution must be between 64 and 4096")
    if args.lens <= 1 or args.distance_multiplier <= 0:
        raise TaskError("Camera lens and distance multiplier must be positive")
    if not -89.0 <= args.elevation <= 89.0:
        raise TaskError("--elevation must be between -89 and 89 degrees")
    if args.world_strength < 0:
        raise TaskError("--world-strength must not be negative")
    output_paths = turntable_output_paths(args.output, args.frames, force=args.force)
    bounds = object_world_bounds(objects)
    if bounds is None:
        raise TaskError("Target objects have no measurable bounds")
    center = (bounds[0] + bounds[1]) * 0.5
    radius = max((bounds[1] - bounds[0]).length * 0.5, 0.1)
    collection = ensure_tool_collection(
        args.review_collection,
        replace_existing=False,
    )
    remove_tool_collection_objects(collection)
    camera = create_review_camera(collection, center, radius, args.lens)
    light_scale = max(radius, 0.5)
    create_area_light(
        collection,
        "Forge3D_KeyLight",
        center,
        Vector((2.5, -3.0, 3.0)) * light_scale,
        energy=700 * light_scale * light_scale,
        size=2.0 * light_scale,
        color=(1.0, 0.84, 0.68),
    )
    create_area_light(
        collection,
        "Forge3D_FillLight",
        center,
        Vector((-3.0, -1.0, 1.5)) * light_scale,
        energy=350 * light_scale * light_scale,
        size=2.5 * light_scale,
        color=(0.55, 0.72, 1.0),
    )
    create_area_light(
        collection,
        "Forge3D_RimLight",
        center,
        Vector((0.5, 3.0, 2.5)) * light_scale,
        energy=500 * light_scale * light_scale,
        size=1.5 * light_scale,
        color=(0.75, 0.85, 1.0),
    )
    scene = bpy.context.scene
    set_review_world(scene, args.world_strength)
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:
            warn(report, "Eevee was unavailable; using the current render engine")
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = args.transparent
    scene.render.use_file_extension = True
    distance = max(radius * args.distance_multiplier, 0.5)
    elevation = math.radians(args.elevation)
    horizontal = distance * math.cos(elevation)
    for index, output_path in enumerate(output_paths):
        angle = math.radians(args.start_angle) + (2.0 * math.pi * index / args.frames)
        camera.location = center + Vector(
            (
                horizontal * math.cos(angle),
                horizontal * math.sin(angle),
                distance * math.sin(elevation),
            )
        )
        look_at(camera, center)
        scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)
    report["outputs"]["images"] = [str(path) for path in output_paths]
    report["metrics"].update(
        {
            "frames_rendered": len(output_paths),
            "resolution": [args.resolution, args.resolution],
            "bounds": {"min": bounds[0], "max": bounds[1]},
        }
    )
    change(report, "Rendered turntable", frames=len(output_paths))
    if args.save_blend:
        save_blend(
            args.save_blend,
            force=args.force,
            input_path=input_path,
            report=report,
            pack_resources=args.pack_resources,
        )


def add_box_to_bmesh(
    bm: bmesh.types.BMesh,
    center: Sequence[float],
    size: Sequence[float],
) -> None:
    sx, sy, sz = (float(value) for value in size)
    cx, cy, cz = (float(value) for value in center)
    result = bmesh.ops.create_cube(bm, size=1.0)
    matrix = Matrix.Translation((cx, cy, cz)) @ Matrix.Diagonal(
        Vector((sx, sy, sz, 1.0))
    )
    bmesh.ops.transform(bm, matrix=matrix, verts=result["verts"])


def add_cylinder_to_bmesh(
    bm: bmesh.types.BMesh,
    center: Sequence[float],
    *,
    radius: float,
    depth: float,
    axis: str = "Z",
    segments: int = 24,
) -> None:
    result = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    rotation = Matrix.Identity(4)
    if axis == "X":
        rotation = Matrix.Rotation(math.radians(90), 4, "Y")
    elif axis == "Y":
        rotation = Matrix.Rotation(math.radians(90), 4, "X")
    elif axis != "Z":
        raise TaskError(f"Unsupported cylinder axis: {axis}")
    matrix = Matrix.Translation(tuple(float(value) for value in center)) @ rotation
    bmesh.ops.transform(bm, matrix=matrix, verts=result["verts"])


def bmesh_object(
    name: str,
    collection: bpy.types.Collection,
    build: Any,
) -> bpy.types.Object:
    if bpy.data.objects.get(name):
        raise TaskError(f"Object {name!r} already exists")
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm = bmesh.new()
    try:
        build(bm)
        if bm.faces:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    obj[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection.objects.link(obj)
    return obj


def add_bevel_modifier(
    obj: bpy.types.Object,
    width: float,
    segments: int,
) -> None:
    if width <= 0:
        return
    bevel = obj.modifiers.new("Forge3D Bevel", "BEVEL")
    bevel.width = width
    bevel.segments = segments
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(30)


def positive_param(
    params: dict[str, Any],
    name: str,
    default: float,
    *,
    maximum: float = 10000.0,
) -> float:
    try:
        value = float(params.get(name, default))
    except (TypeError, ValueError) as exc:
        raise TaskError(f"Parameter {name!r} must be numeric") from exc
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise TaskError(f"Parameter {name!r} must be in (0, {maximum}]")
    return value


def integer_param(
    params: dict[str, Any],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(params.get(name, default))
    except (TypeError, ValueError) as exc:
        raise TaskError(f"Parameter {name!r} must be an integer") from exc
    if value < minimum or value > maximum:
        raise TaskError(
            f"Parameter {name!r} must be between {minimum} and {maximum}"
        )
    return value


def float_param(
    params: dict[str, Any],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(params.get(name, default))
    except (TypeError, ValueError) as exc:
        raise TaskError(f"Parameter {name!r} must be numeric") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise TaskError(
            f"Parameter {name!r} must be between {minimum} and {maximum}"
        )
    return value


def color_param(
    params: dict[str, Any],
    name: str,
    default: str,
) -> tuple[float, float, float, float]:
    raw = params.get(name, default)
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(component) for component in raw)
    if not isinstance(raw, str):
        raise TaskError(
            f"Parameter {name!r} must be a comma-separated colour or RGB(A) list"
        )
    return parse_color(raw)


def procedural_pbr_material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float,
    roughness: float,
) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is not None and not material.get(GENERATED_BY_KEY):
        raise TaskError(
            f"Material {name!r} already exists and is not owned by Forge3D"
        )
    if material is None:
        material = bpy.data.materials.new(name)
    material[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    material.use_nodes = True
    material.diffuse_color = color
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (320, 0)
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    node_input(principled, "Base Color").default_value = color
    node_input(principled, "Metallic").default_value = metallic
    node_input(principled, "Roughness").default_value = roughness
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return material


def finish_hard_surface_component(
    obj: bpy.types.Object,
    material: bpy.types.Material,
    *,
    bevel: float,
    bevel_segments: int,
    role: str,
) -> None:
    obj["forge3d_role"] = role
    obj["forge3d_units"] = "meters"
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
        polygon.use_smooth = True
    add_bevel_modifier(obj, bevel, bevel_segments)
    bevel_modifier = obj.modifiers.get("Forge3D Bevel")
    if bevel_modifier is not None:
        bevel_modifier.harden_normals = True
        if hasattr(bevel_modifier, "miter_outer"):
            bevel_modifier.miter_outer = "MITER_ARC"
    weighted = obj.modifiers.new("Forge3D Weighted Normals", "WEIGHTED_NORMAL")
    weighted.keep_sharp = True
    weighted.weight = 50




def procedural_equipment_case(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    """Build a wide, low hard-surface equipment pod from authored primitives."""

    width = positive_param(params, "width", 1.05, maximum=10.0)
    depth = positive_param(params, "depth", 0.68, maximum=10.0)
    height = positive_param(params, "height", 0.56, maximum=10.0)
    if width < 0.45 or depth < 0.30 or height < 0.28:
        raise TaskError(
            "equipment-case requires width >= 0.45 m, depth >= 0.30 m, "
            "and shell height >= 0.28 m"
        )
    if width <= height * 1.35:
        raise TaskError(
            "equipment-case is a horizontal pod; width must exceed shell "
            "height by at least 35%"
        )
    name = str(params.get("name", "Forge3D_MedicalPod")).strip()
    if not name:
        raise TaskError("Parameter 'name' must not be empty")

    smallest = min(width, depth, height)
    shell_bevel = float_param(
        params,
        "shell_bevel",
        min(0.044, smallest * 0.08),
        minimum=0.0,
        maximum=smallest * 0.17,
    )
    detail_bevel = float_param(
        params,
        "detail_bevel",
        min(0.012, smallest * 0.035),
        minimum=0.0,
        maximum=smallest * 0.08,
    )
    bevel_segments = integer_param(
        params, "bevel_segments", 3, minimum=1, maximum=8
    )
    foot_height = float_param(
        params,
        "foot_height",
        0.065,
        minimum=0.025,
        maximum=height * 0.24,
    )
    lid_height = float_param(
        params,
        "lid_height",
        height * 0.19,
        minimum=height * 0.1,
        maximum=height * 0.32,
    )
    corner_size = float_param(
        params,
        "corner_size",
        min(width, depth) * 0.22,
        minimum=0.06,
        maximum=min(width, depth) * 0.31,
    )
    frame_width = float_param(
        params,
        "frame_width",
        min(width, height) * 0.075,
        minimum=0.018,
        maximum=min(width, height) * 0.13,
    )
    handle_span = float_param(
        params,
        "handle_span",
        depth * 0.45,
        minimum=depth * 0.25,
        maximum=depth * 0.68,
    )
    handle_extension = float_param(
        params,
        "handle_extension",
        width * 0.12,
        minimum=0.045,
        maximum=width * 0.2,
    )

    panel_width = width - 2.0 * (corner_size * 0.62 + frame_width)
    panel_height = height * 0.46
    if panel_width <= frame_width * 5 or panel_height <= frame_width * 3:
        raise TaskError(
            "Corner and frame dimensions leave no usable wide front panel; "
            "reduce corner_size or frame_width"
        )

    shell_material = procedural_pbr_material(
        f"{name}_Shell_MAT",
        color_param(params, "case_color", "0.62,0.59,0.50,1"),
        metallic=0.0,
        roughness=0.42,
    )
    protector_material = procedural_pbr_material(
        f"{name}_Protector_MAT",
        color_param(params, "protector_color", "0.025,0.032,0.034,1"),
        metallic=0.2,
        roughness=0.4,
    )
    accent_material = procedural_pbr_material(
        f"{name}_Accent_MAT",
        color_param(params, "accent_color", "0.055,0.27,0.29,1"),
        metallic=0.08,
        roughness=0.36,
    )
    hardware_material = procedural_pbr_material(
        f"{name}_Hardware_MAT",
        color_param(params, "hardware_color", "0.12,0.14,0.145,1"),
        metallic=0.62,
        roughness=0.3,
    )
    indicator_material = procedural_pbr_material(
        f"{name}_Indicator_MAT",
        color_param(params, "indicator_color", "1.0,0.27,0.015,1"),
        metallic=0.0,
        roughness=0.25,
    )

    projection = min(0.007, depth * 0.014)
    shell_bottom = foot_height
    shell_top = shell_bottom + height
    body_height = height - lid_height
    front_y = -depth * 0.5
    fascia_depth = min(0.018, depth * 0.035)
    panel_center_z = shell_bottom + height * 0.42

    shell_boxes = [
        (
            (0.0, 0.0, shell_bottom + body_height * 0.5),
            (width, depth, body_height),
        ),
        (
            (0.0, 0.0, shell_bottom + body_height + lid_height * 0.5),
            (width * 0.985, depth * 0.985, lid_height),
        ),
        (
            (
                0.0,
                front_y - fascia_depth * 0.5 - projection,
                panel_center_z,
            ),
            (panel_width, fascia_depth, panel_height),
        ),
    ]
    shell = bmesh_object(
        f"{name}_Shell",
        collection,
        lambda bm: [
            add_box_to_bmesh(bm, center, size) for center, size in shell_boxes
        ],
    )
    finish_hard_surface_component(
        shell,
        shell_material,
        bevel=shell_bevel,
        bevel_segments=bevel_segments + 1,
        role="primary_shell_lid_fascia",
    )

    frame_depth = min(0.027, depth * 0.05)
    frame_y = front_y - fascia_depth - frame_depth * 0.5 - projection
    # Keep the four decorative frame bars as distinct closed components. If
    # their corners meet at exactly coincident edges, Blender 5.2's bevel output
    # can collapse those seams during topology validation into an edge shared by
    # more than two faces. A sub-millimetre relief is visually invisible at this
    # scale and preserves manifold components through export.
    frame_relief = min(0.0002, frame_width * 0.01)
    protector_boxes: list[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ] = [
        (
            (-(panel_width + frame_width) * 0.5, frame_y, panel_center_z),
            (frame_width, frame_depth, panel_height + frame_width * 2.0),
        ),
        (
            ((panel_width + frame_width) * 0.5, frame_y, panel_center_z),
            (frame_width, frame_depth, panel_height + frame_width * 2.0),
        ),
        (
            (0.0, frame_y, panel_center_z - (panel_height + frame_width) * 0.5),
            (panel_width - frame_relief * 2.0, frame_depth, frame_width),
        ),
        (
            (0.0, frame_y, panel_center_z + (panel_height + frame_width) * 0.5),
            (panel_width - frame_relief * 2.0, frame_depth, frame_width),
        ),
    ]
    seam_z = shell_bottom + body_height
    trim_depth = max(0.022, frame_depth * 0.85)
    protector_boxes.extend(
        [
            (
                (0.0, -depth * 0.5 - projection, seam_z),
                (width - corner_size * 0.7, trim_depth, 0.028),
            ),
            (
                (0.0, depth * 0.5 + projection, seam_z),
                (width - corner_size * 0.7, trim_depth, 0.028),
            ),
            (
                (-width * 0.5 - projection, 0.0, seam_z),
                (trim_depth, depth - corner_size * 0.55, 0.028),
            ),
            (
                (width * 0.5 + projection, 0.0, seam_z),
                (trim_depth, depth - corner_size * 0.55, 0.028),
            ),
        ]
    )
    top_panel_width = width * 0.43
    top_panel_depth = depth * 0.38
    strap_x = top_panel_width * 0.5 + frame_width * 0.62
    for x in (-strap_x, strap_x):
        protector_boxes.append(
            (
                (x, 0.0, shell_top + 0.007),
                (frame_width * 0.72, depth * 0.7, 0.022),
            )
        )
    side_mount_height = height * 0.27
    for x in (-width * 0.5 - projection, width * 0.5 + projection):
        protector_boxes.append(
            (
                (x, 0.0, shell_bottom + height * 0.43),
                (trim_depth, handle_span + frame_width * 1.8, side_mount_height),
            )
        )
    protectors = bmesh_object(
        f"{name}_Protectors",
        collection,
        lambda bm: [
            add_box_to_bmesh(bm, center, size)
            for center, size in protector_boxes
        ],
    )
    finish_hard_surface_component(
        protectors,
        protector_material,
        bevel=min(detail_bevel, frame_depth * 0.28),
        bevel_segments=bevel_segments,
        role="front_frame_lid_seam_protectors",
    )

    foot_width = min(0.16, width * 0.16)
    foot_depth = min(0.15, depth * 0.25)
    accent_boxes: list[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ] = []
    for x in (-width * 0.35, width * 0.35):
        for y in (-depth * 0.34, depth * 0.34):
            accent_boxes.append(
                (
                    (x, y, foot_height * 0.5),
                    (foot_width, foot_depth, foot_height),
                )
            )
    top_panel_thickness = min(0.02, lid_height * 0.2)
    accent_boxes.append(
        (
            (0.0, 0.0, shell_top + top_panel_thickness * 0.5 + projection),
            (top_panel_width, top_panel_depth, top_panel_thickness),
        )
    )
    front_accent_width = min(0.13, panel_width * 0.19)
    front_accent_height = panel_height * 0.74
    front_accent_y = frame_y - frame_depth * 0.5 - 0.006
    for x in (-panel_width * 0.38, panel_width * 0.38):
        accent_boxes.append(
            (
                (x, front_accent_y, panel_center_z),
                (front_accent_width, 0.018, front_accent_height),
            )
        )
    handle_z = shell_bottom + height * 0.41
    handle_rail = min(0.065, depth * 0.1)
    for side in (-1.0, 1.0):
        for y in (-handle_span * 0.5, handle_span * 0.5):
            accent_boxes.append(
                (
                    (
                        side * (width * 0.5 + handle_extension * 0.5),
                        y,
                        handle_z,
                    ),
                    (handle_extension, handle_rail, handle_rail),
                )
            )
    accents = bmesh_object(
        f"{name}_Accents",
        collection,
        lambda bm: [
            add_box_to_bmesh(bm, center, size) for center, size in accent_boxes
        ],
    )
    finish_hard_surface_component(
        accents,
        accent_material,
        bevel=min(detail_bevel, foot_height * 0.2),
        bevel_segments=bevel_segments,
        role="top_panel_front_insets_feet_handle_brackets",
    )

    indicator_radius = min(panel_height * 0.29, panel_width * 0.1)
    ring_depth = min(0.028, depth * 0.05)
    ring_y = front_accent_y - ring_depth * 0.5 - 0.004
    latch_width = min(0.075, panel_width * 0.11)
    latch_height = min(0.055, panel_height * 0.22)
    latch_z = panel_center_z + panel_height * 0.48
    hardware_boxes: list[
        tuple[tuple[float, float, float], tuple[float, float, float]]
    ] = []
    for x in (-panel_width * 0.28, panel_width * 0.28):
        hardware_boxes.append(
            (
                (x, frame_y - frame_depth * 0.5 - 0.01, latch_z),
                (latch_width, 0.025, latch_height),
            )
        )
    hinge_depth = min(0.026, depth * 0.05)
    for x in (-width * 0.28, width * 0.28):
        hardware_boxes.append(
            (
                (x, depth * 0.5 + hinge_depth * 0.5 + projection, seam_z),
                (width * 0.13, hinge_depth, 0.04),
            )
        )
    grip_depth = handle_span + handle_rail
    grip_width = min(0.07, handle_extension * 0.55)
    for side in (-1.0, 1.0):
        hardware_boxes.append(
            (
                (
                    side
                    * (width * 0.5 + handle_extension + grip_width * 0.35),
                    0.0,
                    handle_z,
                ),
                (grip_width, grip_depth, handle_rail * 1.05),
            )
        )

    def build_hardware(bm: bmesh.types.BMesh) -> None:
        for center, size in hardware_boxes:
            add_box_to_bmesh(bm, center, size)
        add_cylinder_to_bmesh(
            bm,
            (0.0, ring_y, panel_center_z),
            radius=indicator_radius,
            depth=ring_depth,
            axis="Y",
            segments=32,
        )

    hardware = bmesh_object(f"{name}_Hardware", collection, build_hardware)
    finish_hard_surface_component(
        hardware,
        hardware_material,
        bevel=min(detail_bevel, 0.007),
        bevel_segments=max(2, bevel_segments - 1),
        role="latches_hinges_side_grips_indicator_bezel",
    )

    indicator_depth = min(0.018, ring_depth * 0.75)
    indicator = bmesh_object(
        f"{name}_Indicator",
        collection,
        lambda bm: add_cylinder_to_bmesh(
            bm,
            (0.0, ring_y - ring_depth * 0.5 - indicator_depth * 0.5 - 0.003, panel_center_z),
            radius=indicator_radius * 0.48,
            depth=indicator_depth,
            axis="Y",
            segments=32,
        ),
    )
    finish_hard_surface_component(
        indicator,
        indicator_material,
        bevel=min(detail_bevel, indicator_depth * 0.24),
        bevel_segments=bevel_segments,
        role="status_indicator",
    )

    objects = [shell, protectors, accents, hardware, indicator]
    for obj in objects:
        obj["forge3d_dimensions"] = json.dumps(
            {
                "width": width,
                "depth": depth,
                "shell_height": height,
                "foot_height": foot_height,
            },
            sort_keys=True,
        )
    return objects


def procedural_box(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    width = positive_param(params, "width", 1.0)
    depth = positive_param(params, "depth", 1.0)
    height = positive_param(params, "height", 1.0)
    name = str(params.get("name", "Forge3D_Box"))
    obj = bmesh_object(
        name,
        collection,
        lambda bm: add_box_to_bmesh(bm, (0, 0, height * 0.5), (width, depth, height)),
    )
    add_bevel_modifier(
        obj,
        float_param(
            params,
            "bevel",
            min(width, depth, height) * 0.04,
            minimum=0.0,
            maximum=min(width, depth, height) * 0.45,
        ),
        integer_param(params, "bevel_segments", 3, minimum=1, maximum=12),
    )
    return [obj]


def procedural_crate(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    width = positive_param(params, "width", 1.2)
    depth = positive_param(params, "depth", 1.0)
    height = positive_param(params, "height", 0.9)
    frame = float_param(
        params,
        "frame",
        min(width, depth, height) * 0.1,
        minimum=0.01,
        maximum=min(width, depth, height) * 0.25,
    )
    panel = float_param(
        params,
        "panel",
        frame * 0.55,
        minimum=0.005,
        maximum=min(width, depth) * 0.2,
    )
    name = str(params.get("name", "Forge3D_Crate"))

    def build(bm: bmesh.types.BMesh) -> None:
        add_box_to_bmesh(
            bm,
            (0, 0, height * 0.5),
            (width - 2 * frame, depth - 2 * frame, height - 2 * frame),
        )
        for x in (-width * 0.5 + frame * 0.5, width * 0.5 - frame * 0.5):
            for y in (-depth * 0.5 + frame * 0.5, depth * 0.5 - frame * 0.5):
                add_box_to_bmesh(bm, (x, y, height * 0.5), (frame, frame, height))
        for z in (frame * 0.5, height - frame * 0.5):
            add_box_to_bmesh(bm, (0, -depth * 0.5 + panel * 0.5, z), (width, panel, frame))
            add_box_to_bmesh(bm, (0, depth * 0.5 - panel * 0.5, z), (width, panel, frame))
            add_box_to_bmesh(bm, (-width * 0.5 + panel * 0.5, 0, z), (panel, depth, frame))
            add_box_to_bmesh(bm, (width * 0.5 - panel * 0.5, 0, z), (panel, depth, frame))

    obj = bmesh_object(name, collection, build)
    add_bevel_modifier(
        obj,
        float_param(
            params,
            "bevel",
            frame * 0.12,
            minimum=0.0,
            maximum=frame * 0.4,
        ),
        integer_param(params, "bevel_segments", 2, minimum=1, maximum=8),
    )
    return [obj]


def procedural_stairs(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    steps = integer_param(params, "steps", 8, minimum=1, maximum=256)
    width = positive_param(params, "width", 1.5)
    run = positive_param(params, "run", 2.4)
    rise = positive_param(params, "rise", 1.6)
    name = str(params.get("name", "Forge3D_Stairs"))
    tread = run / steps
    riser = rise / steps

    def build(bm: bmesh.types.BMesh) -> None:
        for index in range(steps):
            step_depth = tread
            step_height = riser * (index + 1)
            y = -run * 0.5 + tread * (index + 0.5)
            add_box_to_bmesh(
                bm,
                (0, y, step_height * 0.5),
                (width, step_depth, step_height),
            )

    obj = bmesh_object(name, collection, build)
    add_bevel_modifier(
        obj,
        float_param(
            params,
            "bevel",
            min(tread, riser) * 0.04,
            minimum=0.0,
            maximum=min(tread, riser) * 0.25,
        ),
        integer_param(params, "bevel_segments", 2, minimum=1, maximum=8),
    )
    return [obj]


def procedural_room(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    width = positive_param(params, "width", 6.0)
    depth = positive_param(params, "depth", 5.0)
    height = positive_param(params, "height", 3.0)
    thickness = float_param(
        params,
        "thickness",
        0.15,
        minimum=0.02,
        maximum=min(width, depth) * 0.2,
    )
    door_width = float_param(
        params,
        "door_width",
        1.0,
        minimum=0.0,
        maximum=max(0.0, width - 2 * thickness),
    )
    door_height = float_param(
        params,
        "door_height",
        2.1,
        minimum=0.0,
        maximum=height,
    )
    name = str(params.get("name", "Forge3D_Room"))

    def build(bm: bmesh.types.BMesh) -> None:
        add_box_to_bmesh(
            bm,
            (0, 0, -thickness * 0.5),
            (width, depth, thickness),
        )
        add_box_to_bmesh(
            bm,
            (-width * 0.5 + thickness * 0.5, 0, height * 0.5),
            (thickness, depth, height),
        )
        add_box_to_bmesh(
            bm,
            (width * 0.5 - thickness * 0.5, 0, height * 0.5),
            (thickness, depth, height),
        )
        add_box_to_bmesh(
            bm,
            (0, depth * 0.5 - thickness * 0.5, height * 0.5),
            (width, thickness, height),
        )
        if door_width <= 0 or door_height <= 0:
            add_box_to_bmesh(
                bm,
                (0, -depth * 0.5 + thickness * 0.5, height * 0.5),
                (width, thickness, height),
            )
        else:
            side_width = (width - door_width) * 0.5
            for x in (
                -width * 0.5 + side_width * 0.5,
                width * 0.5 - side_width * 0.5,
            ):
                add_box_to_bmesh(
                    bm,
                    (x, -depth * 0.5 + thickness * 0.5, height * 0.5),
                    (side_width, thickness, height),
                )
            header_height = height - door_height
            if header_height > EPSILON:
                add_box_to_bmesh(
                    bm,
                    (
                        0,
                        -depth * 0.5 + thickness * 0.5,
                        door_height + header_height * 0.5,
                    ),
                    (door_width, thickness, header_height),
                )

    obj = bmesh_object(name, collection, build)
    return [obj]


def procedural_fence(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    length = positive_param(params, "length", 5.0)
    height = positive_param(params, "height", 1.2)
    posts = integer_param(params, "posts", 6, minimum=2, maximum=256)
    post_size = float_param(
        params,
        "post_size",
        0.1,
        minimum=0.01,
        maximum=min(length / posts, height) * 0.8,
    )
    rail_size = float_param(
        params,
        "rail_size",
        0.08,
        minimum=0.01,
        maximum=height * 0.25,
    )
    name = str(params.get("name", "Forge3D_Fence"))

    def build(bm: bmesh.types.BMesh) -> None:
        for index in range(posts):
            x = -length * 0.5 + length * index / (posts - 1)
            add_box_to_bmesh(
                bm,
                (x, 0, height * 0.5),
                (post_size, post_size, height),
            )
        for fraction in (0.33, 0.72):
            add_box_to_bmesh(
                bm,
                (0, 0, height * fraction),
                (length, rail_size, rail_size),
            )

    obj = bmesh_object(name, collection, build)
    add_bevel_modifier(
        obj,
        float_param(
            params,
            "bevel",
            min(post_size, rail_size) * 0.1,
            minimum=0.0,
            maximum=min(post_size, rail_size) * 0.4,
        ),
        integer_param(params, "bevel_segments", 2, minimum=1, maximum=8),
    )
    return [obj]


def procedural_terrain(
    params: dict[str, Any],
    collection: bpy.types.Collection,
    *,
    seed: int,
) -> list[bpy.types.Object]:
    width = positive_param(params, "width", 10.0)
    depth = positive_param(params, "depth", 10.0)
    resolution = integer_param(params, "resolution", 32, minimum=2, maximum=256)
    amplitude = float_param(
        params,
        "amplitude",
        1.0,
        minimum=0.0,
        maximum=max(width, depth),
    )
    frequency = positive_param(params, "frequency", 0.35)
    noise = float_param(
        params,
        "noise",
        0.12,
        minimum=0.0,
        maximum=max(width, depth),
    )
    name = str(params.get("name", "Forge3D_Terrain"))
    generator = random.Random(seed)

    def build(bm: bmesh.types.BMesh) -> None:
        grid: list[list[bmesh.types.BMVert]] = []
        for y_index in range(resolution):
            row = []
            y = -depth * 0.5 + depth * y_index / (resolution - 1)
            for x_index in range(resolution):
                x = -width * 0.5 + width * x_index / (resolution - 1)
                falloff_x = math.sin(math.pi * x_index / (resolution - 1))
                falloff_y = math.sin(math.pi * y_index / (resolution - 1))
                z = (
                    math.sin(x * frequency)
                    * math.cos(y * frequency)
                    * amplitude
                    + generator.uniform(-noise, noise)
                ) * falloff_x * falloff_y
                row.append(bm.verts.new((x, y, z)))
            grid.append(row)
        for y_index in range(resolution - 1):
            for x_index in range(resolution - 1):
                bm.faces.new(
                    (
                        grid[y_index][x_index],
                        grid[y_index][x_index + 1],
                        grid[y_index + 1][x_index + 1],
                        grid[y_index + 1][x_index],
                    )
                )

    obj = bmesh_object(name, collection, build)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return [obj]


def procedural_pipe(
    params: dict[str, Any],
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    name = str(params.get("name", "Forge3D_Pipe"))
    radius = positive_param(params, "radius", 0.1)
    bevel_resolution = integer_param(
        params, "bevel_resolution", 4, minimum=0, maximum=12
    )
    resolution = integer_param(params, "resolution", 16, minimum=1, maximum=64)
    raw_points = params.get(
        "points",
        [[0, 0, 0.1], [0, 0, 1.0], [1.0, 0, 1.0], [1.0, 1.0, 1.5]],
    )
    if not isinstance(raw_points, list) or len(raw_points) < 2 or len(raw_points) > 256:
        raise TaskError("Pipe points must be a list containing 2–256 XYZ points")
    points: list[tuple[float, float, float]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 3:
            raise TaskError("Every pipe point must contain exactly three coordinates")
        point = tuple(float(value) for value in raw_point)
        if any(not math.isfinite(value) for value in point):
            raise TaskError("Pipe points must be finite")
        points.append(point)  # type: ignore[arg-type]
    if bpy.data.objects.get(name):
        raise TaskError(f"Object {name!r} already exists")
    curve = bpy.data.curves.new(f"{name}_Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = bevel_resolution
    curve.resolution_u = resolution
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, bezier in zip(points, spline.bezier_points):
        bezier.co = point
        bezier.handle_left_type = "AUTO"
        bezier.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    obj[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection.objects.link(obj)
    return [obj]


PROCEDURAL_RECIPES = {
    "box": procedural_box,
    "crate": procedural_crate,
    "equipment-case": procedural_equipment_case,
    "stairs": procedural_stairs,
    "medical-case": procedural_equipment_case,
    "room": procedural_room,
    "fence": procedural_fence,
    "pipe": procedural_pipe,
}


def load_json_object(raw: str, *, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaskError(f"{kind} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TaskError(f"{kind} must be a JSON object")
    return value


def load_parameters(args: argparse.Namespace) -> dict[str, Any]:
    if args.params and args.params_file:
        raise TaskError("Use either --params or --params-file, not both")
    if args.params_file:
        path = path_from_user(args.params_file, kind="parameter file", must_exist=True)
        return load_json_object(path.read_text(encoding="utf-8"), kind="parameter file")
    return load_json_object(args.params or "{}", kind="--params")


def task_procedural(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    params = load_parameters(args)
    if args.clear_scene and input_path is None and not bpy.data.filepath:
        clear_scene()
        change(report, "Cleared the in-memory scene before procedural generation")
    collection = ensure_tool_collection(
        args.asset_collection,
        replace_existing=args.replace_existing,
    )
    random.seed(args.seed)
    if args.recipe == "terrain":
        objects = procedural_terrain(params, collection, seed=args.seed)
    else:
        builder = PROCEDURAL_RECIPES.get(args.recipe)
        if builder is None:
            raise TaskError(
                f"Unknown recipe {args.recipe!r}; choose from "
                + ", ".join(sorted([*PROCEDURAL_RECIPES, "terrain"]))
            )
        objects = builder(params, collection)
    for obj in objects:
        obj["forge3d_recipe"] = args.recipe
        obj["forge3d_seed"] = args.seed
        obj["forge3d_parameters"] = json.dumps(params, sort_keys=True)
    bounds = object_world_bounds(objects)
    report["metrics"].update(
        {
            "recipe": args.recipe,
            "seed": args.seed,
            "parameters": params,
            "objects": [object_summary(obj, evaluated=False) for obj in objects],
            "bounds": (
                {"min": bounds[0], "max": bounds[1], "size": bounds[1] - bounds[0]}
                if bounds
                else None
            ),
        }
    )
    change(
        report,
        "Generated procedural asset",
        recipe=args.recipe,
        objects=[obj.name for obj in objects],
    )
    save_optional_output(args, report, input_path)


def task_save(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    report["metrics"]["objects"] = len(bpy.context.scene.objects)
    save_blend(
        args.output,
        force=args.force,
        input_path=input_path,
        report=report,
        pack_resources=args.pack_resources,
        compress=not args.no_compress,
    )


def supported_operator_kwargs(operator: Any, values: dict[str, Any]) -> dict[str, Any]:
    properties = {
        prop.identifier for prop in operator.get_rna_type().properties if not prop.is_readonly
    }
    return {key: value for key, value in values.items() if key in properties}


def object_has_ancestor(
    obj: bpy.types.Object,
    ancestor: bpy.types.Object,
) -> bool:
    parent = obj.parent
    while parent is not None:
        if parent == ancestor:
            return True
        parent = parent.parent
    return False


def armature_export_objects(armature: bpy.types.Object) -> list[bpy.types.Object]:
    result = []
    for obj in bpy.context.scene.objects:
        if obj.get("forge3d_source_only"):
            continue
        if (
            obj == armature
            or obj.find_armature() == armature
            or object_has_ancestor(obj, armature)
        ):
            result.append(obj)
    return result


def task_export_glb(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    output_path = prepare_output_file(
        args.output,
        kind="GLB output",
        force=args.force,
        allowed_suffixes={".glb"},
        input_path=input_path,
    )
    patterns = parse_patterns(args.objects)
    if args.armature and (patterns or args.collection):
        raise TaskError(
            "Use --armature or --objects/--collection for export, not both"
        )
    if args.armature:
        armature = get_armature(args.armature)
        objects = armature_export_objects(armature)
        if not objects:
            raise TaskError(
                f"No exportable objects are attached to armature {args.armature!r}"
            )
        deselect_all()
        for obj in objects:
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = armature
        use_selection = True
        report["metrics"]["export_armature"] = armature.name
    elif patterns or args.collection:
        objects = target_objects(args)
        if not objects:
            raise TaskError("No objects matched the GLB export target")
        deselect_all()
        for obj in objects:
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        use_selection = True
    else:
        scene_objects = list(bpy.context.scene.objects)
        excluded_source_lods = [
            obj for obj in scene_objects if obj.get("forge3d_source_only")
        ]
        objects = [
            obj for obj in scene_objects if not obj.get("forge3d_source_only")
        ]
        if excluded_source_lods:
            deselect_all()
            for obj in objects:
                obj.hide_set(False)
                obj.select_set(True)
            if objects:
                bpy.context.view_layer.objects.active = objects[0]
            use_selection = True
            report["metrics"]["source_only_lods_excluded"] = [
                obj.name for obj in excluded_source_lods
            ]
        else:
            use_selection = False
    if not any(obj.type == "MESH" for obj in objects):
        warn(report, "GLB export contains no mesh objects")

    action_patterns = parse_patterns(args.actions)
    if action_patterns:
        kept_actions = [
            action
            for action in bpy.data.actions
            if matches_patterns(action.name, action_patterns)
        ]
        if not kept_actions:
            raise TaskError("No animation actions matched the export filter")
        removed_actions = [
            action.name
            for action in bpy.data.actions
            if action not in kept_actions
        ]
        for action in list(bpy.data.actions):
            if action not in kept_actions:
                bpy.data.actions.remove(action)
        report["metrics"]["actions_kept"] = [
            action.name for action in kept_actions
        ]
        report["metrics"]["actions_excluded"] = removed_actions

    options = supported_operator_kwargs(
        bpy.ops.export_scene.gltf,
        {
            "filepath": str(output_path),
            "check_existing": False,
            "export_format": "GLB",
            "use_selection": use_selection,
            "export_apply": args.apply_modifiers,
            "export_yup": True,
            "export_texcoords": True,
            "export_normals": True,
            "export_tangents": args.tangents,
            "export_materials": "EXPORT",
            "export_attributes": True,
            "export_extras": True,
            "export_cameras": args.cameras,
            "export_lights": args.lights,
            "export_animations": not args.no_animations,
            "export_frame_range": True,
            "export_force_sampling": args.force_sampling,
            "export_def_bones": args.deform_bones_only,
            "export_skins": True,
            "export_all_influences": False,
            "export_morph": True,
            "export_morph_normal": True,
            "export_morph_tangent": False,
            "export_gpu_instances": args.gpu_instances,
            "will_save_settings": False,
        },
    )
    try:
        result = bpy.ops.export_scene.gltf(**options)
    except Exception as exc:
        raise TaskError(f"GLB export failed: {exc}") from exc
    if "FINISHED" not in result:
        raise TaskError(f"GLB exporter did not finish: {result}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise TaskError("GLB exporter reported success but produced no output")
    report["outputs"]["glb"] = str(output_path)
    report["metrics"].update(
        {
            "objects_considered": len(objects),
            "file_size_bytes": output_path.stat().st_size,
            "animations": 0 if args.no_animations else len(bpy.data.actions),
            "export_options": options,
        }
    )
    change(report, "Exported GLB", path=str(output_path))


def enable_rigify() -> None:
    """Enable Blender's bundled Rigify add-on for this process."""
    try:
        result = bpy.ops.preferences.addon_enable(module="rigify")
    except Exception as exc:
        raise TaskError(
            "Blender's bundled Rigify add-on could not be enabled. "
            "Install or enable Rigify in Blender Preferences."
        ) from exc
    if "FINISHED" not in result:
        raise TaskError(f"Rigify add-on enable did not finish: {result}")
    if not hasattr(bpy.ops.object, "armature_human_metarig_add"):
        raise TaskError("Rigify enabled but its human metarig operator is unavailable")


def fit_object_to_world_bounds(
    obj: bpy.types.Object,
    target_minimum: Vector,
    target_maximum: Vector,
) -> dict[str, list[float]]:
    """Non-uniformly fit an object's bounds to the supplied world bounds."""
    def bounds() -> tuple[Vector, Vector]:
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return (
            Vector(min(point[axis] for point in points) for axis in range(3)),
            Vector(max(point[axis] for point in points) for axis in range(3)),
        )

    source_minimum, source_maximum = bounds()
    source_dimensions = source_maximum - source_minimum
    target_dimensions = target_maximum - target_minimum
    if any(dimension <= EPSILON for dimension in target_dimensions):
        raise TaskError(
            "The humanoid mesh must have non-zero width, depth, and height"
        )
    if any(dimension <= EPSILON for dimension in source_dimensions):
        raise TaskError("Rigify's human metarig has invalid source bounds")

    scale = Vector(
        target_dimensions[index] / source_dimensions[index] for index in range(3)
    )
    obj.scale = scale
    bpy.context.view_layer.update()
    scaled_minimum, scaled_maximum = bounds()
    obj.location += (
        (target_minimum + target_maximum) * 0.5
        - (scaled_minimum + scaled_maximum) * 0.5
    )
    activate_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    return {
        "target_minimum": list(target_minimum),
        "target_maximum": list(target_maximum),
        "scale": list(scale),
    }


def generated_rigify_armature(
    metarig: bpy.types.Object,
) -> bpy.types.Object:
    before = set(bpy.data.objects)
    activate_only(metarig)
    try:
        result = bpy.ops.pose.rigify_generate()
    except Exception as exc:
        raise TaskError(f"Rigify could not generate the control rig: {exc}") from exc
    if "FINISHED" not in result:
        raise TaskError(f"Rigify generation did not finish: {result}")
    created = [
        obj
        for obj in bpy.data.objects
        if obj not in before and obj.type == "ARMATURE"
    ]
    active = bpy.context.view_layer.objects.active
    if active is not None and active.type == "ARMATURE" and active in created:
        return active
    if len(created) != 1:
        names = [obj.name for obj in created]
        raise TaskError(
            "Rigify did not create exactly one armature "
            f"(created armatures: {names})"
        )
    return created[0]


def bind_meshes_with_automatic_weights(
    rig: bpy.types.Object,
    meshes: Sequence[bpy.types.Object],
) -> dict[str, dict[str, int]]:
    deselect_all()
    for mesh in meshes:
        mesh.hide_set(False)
        mesh.hide_viewport = False
        mesh.select_set(True)
    rig.hide_set(False)
    rig.hide_viewport = False
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        result = bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)
    except Exception as exc:
        raise TaskError(
            "Blender automatic weights could not bind the humanoid mesh: "
            f"{exc}. Inspect topology and use a neutral T/A pose."
        ) from exc
    if "FINISHED" not in result:
        raise TaskError(f"Automatic-weight parenting did not finish: {result}")

    deform_names = {bone.name for bone in rig.data.bones if bone.use_deform}
    metrics: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for mesh in meshes:
        activate_only(mesh)
        try:
            bpy.ops.object.vertex_group_limit_total(
                group_select_mode="BONE_DEFORM",
                limit=4,
            )
            bpy.ops.object.vertex_group_normalize_all(
                group_select_mode="BONE_DEFORM",
                lock_active=False,
            )
        except Exception as exc:
            raise TaskError(
                f"Could not normalize game-ready weights on {mesh.name!r}: {exc}"
            ) from exc
        matching_group_indices = {
            group.index
            for group in mesh.vertex_groups
            if group.name in deform_names
        }
        maximum_influences = 0
        unweighted = sum(
            1
            for vertex in mesh.data.vertices
            if not any(
                membership.group in matching_group_indices
                and membership.weight > 1.0e-6
                for membership in vertex.groups
            )
        )
        for vertex in mesh.data.vertices:
            maximum_influences = max(
                maximum_influences,
                sum(
                    1
                    for membership in vertex.groups
                    if membership.group in matching_group_indices
                    and membership.weight > 1.0e-6
                ),
            )
        bound = mesh.find_armature() == rig
        metrics[mesh.name] = {
            "vertices": len(mesh.data.vertices),
            "deform_groups": len(matching_group_indices),
            "unweighted_vertices": unweighted,
            "maximum_influences": maximum_influences,
        }
        if (
            not bound
            or not matching_group_indices
            or unweighted
            or maximum_influences > 4
        ):
            failures.append(
                f"{mesh.name} (bound={bound}, deform groups="
                f"{len(matching_group_indices)}, unweighted={unweighted}, "
                f"max influences={maximum_influences})"
            )
    if failures:
        raise TaskError(
            "Automatic-weight verification failed for: " + "; ".join(failures)
        )
    return metrics


def mark_rigify_helpers(
    metarig: bpy.types.Object,
    *,
    helper_collection_name: str,
    collections_before_generation: set[bpy.types.Collection],
) -> list[str]:
    collection = bpy.data.collections.get(helper_collection_name)
    if collection is not None:
        raise TaskError(f"Rig helper collection already exists: {helper_collection_name}")
    collection = bpy.data.collections.new(helper_collection_name)
    bpy.context.scene.collection.children.link(collection)
    collection[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection["forge3d_source_only"] = True
    collection.hide_render = True
    collection.hide_viewport = True
    link_object_only_to(metarig, collection)
    metarig[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    metarig["forge3d_source_only"] = True
    metarig.hide_render = True
    metarig.hide_set(True)

    helper_names = [collection.name]
    for candidate in bpy.data.collections:
        if candidate in collections_before_generation:
            continue
        helper_objects = list(candidate.all_objects)
        candidate[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
        candidate["forge3d_source_only"] = True
        candidate.hide_render = True
        candidate.hide_viewport = True
        helper_names.append(candidate.name)
        for obj in helper_objects:
            obj[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
            obj["forge3d_source_only"] = True
            obj.hide_render = True
            obj.hide_viewport = True
    return sorted(set(helper_names), key=str.casefold)


def task_rig_humanoid(args: argparse.Namespace, report: dict[str, Any]) -> None:
    """Fit Rigify's human metarig, generate controls, and auto-weight meshes."""
    input_path = load_input(args, report)
    if not args.rig_name.strip() or not args.helper_collection.strip():
        raise TaskError("Rig and helper collection names must not be empty")
    meshes = [
        obj
        for obj in target_objects(args, types={"MESH"})
        if not obj.get("forge3d_source_only")
    ]
    if not meshes:
        raise TaskError("No mesh objects matched the humanoid rig target")
    reserved_objects = [args.rig_name, f"{args.rig_name}_Metarig"]
    collisions = [
        name for name in reserved_objects if bpy.data.objects.get(name) is not None
    ]
    if collisions:
        raise TaskError("Rig objects already exist: " + ", ".join(collisions))
    if bpy.data.collections.get(args.helper_collection) is not None:
        raise TaskError(
            f"Rig helper collection already exists: {args.helper_collection}"
        )
    bounds = object_world_bounds(meshes)
    if bounds is None:
        raise TaskError("Could not measure the humanoid mesh bounds")
    minimum, maximum = bounds

    enable_rigify()
    try:
        result = bpy.ops.object.armature_human_metarig_add()
    except Exception as exc:
        raise TaskError(f"Rigify could not add a human metarig: {exc}") from exc
    if "FINISHED" not in result or bpy.context.object is None:
        raise TaskError(f"Rigify human metarig creation did not finish: {result}")
    metarig = bpy.context.object
    metarig.name = f"{args.rig_name}_Metarig"
    metarig.data.name = f"{args.rig_name}_MetarigData"
    fit_metrics = fit_object_to_world_bounds(metarig, minimum, maximum)

    collections_before_generation = set(bpy.data.collections)
    rig = generated_rigify_armature(metarig)
    rig.name = args.rig_name
    rig.data.name = f"{args.rig_name}_Armature"
    rig[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    rig["forge3d_rig_backend"] = "rigify"
    rig["forge3d_fit_assumption"] = "upright neutral T/A pose"
    rig.show_in_front = True
    binding_metrics = bind_meshes_with_automatic_weights(rig, meshes)
    helper_names = mark_rigify_helpers(
        metarig,
        helper_collection_name=args.helper_collection,
        collections_before_generation=collections_before_generation,
    )

    report["metrics"].update(
        {
            "rig": rig.name,
            "metarig": metarig.name,
            "mesh_bounds": fit_metrics,
            "bound_meshes": binding_metrics,
            "deform_bones": sum(1 for bone in rig.data.bones if bone.use_deform),
            "helper_collections": helper_names,
            "assumptions": {
                "pose": "upright neutral T-pose or A-pose",
                "up_axis": "Z",
                "forward_axis": "-Y (Rigify default)",
                "fit": "non-uniform world-bounds fit; inspect joints before animation",
            },
        }
    )
    change(
        report,
        "Generated and automatically weighted Rigify humanoid",
        rig=rig.name,
        meshes=[mesh.name for mesh in meshes],
    )
    save_optional_output(args, report, input_path)


def rig_metrics(
    armature: bpy.types.Object,
    mesh_objects: Sequence[bpy.types.Object],
    args: argparse.Namespace,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    armature_metric = validate_armature_object(armature, args, issues)
    bound_meshes = [
        mesh for mesh in mesh_objects if mesh.find_armature() == armature
    ]
    if not bound_meshes:
        issue(
            issues,
            "error",
            "rig.no_bound_meshes",
            "Armature has no bound mesh objects",
            object_name=armature.name,
        )
    mesh_metrics = {
        mesh.name: validate_mesh_object(mesh, args, issues) for mesh in bound_meshes
    }
    pose_constraint_count = sum(
        len(pose_bone.constraints) for pose_bone in armature.pose.bones
    )
    orphan_groups: dict[str, list[str]] = {}
    bone_names = {bone.name for bone in armature.data.bones}
    for mesh in bound_meshes:
        names = [
            group.name for group in mesh.vertex_groups if group.name not in bone_names
        ]
        if names:
            orphan_groups[mesh.name] = names
            issue(
                issues,
                "warning",
                "rig.orphan_vertex_groups",
                "Mesh contains vertex groups that do not match armature bones",
                object_name=mesh.name,
                groups=names,
            )
    action_names = []
    if armature.animation_data and armature.animation_data.action:
        action_names.append(armature.animation_data.action.name)
    for track in armature.animation_data.nla_tracks if armature.animation_data else []:
        for strip in track.strips:
            if strip.action and strip.action.name not in action_names:
                action_names.append(strip.action.name)
    return {
        "armature": armature_metric,
        "bound_meshes": mesh_metrics,
        "pose_constraints": pose_constraint_count,
        "orphan_vertex_groups": orphan_groups,
        "assigned_actions": action_names,
    }


def task_rig_validate(args: argparse.Namespace, report: dict[str, Any]) -> None:
    load_input(args, report)
    armatures = target_objects(args, types={"ARMATURE"})
    if not armatures:
        raise TaskError("No armatures matched the rig validation target")
    meshes = list(bpy.context.scene.objects)
    meshes = [obj for obj in meshes if obj.type == "MESH"]
    issues: list[dict[str, Any]] = []
    metrics = {
        armature.name: rig_metrics(armature, meshes, args, issues)
        for armature in armatures
    }
    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    report["issues"] = issues
    report["errors"].extend(errors)
    report["warnings"].extend(warnings)
    report["passed"] = not errors
    report["metrics"].update(
        {
            "armatures_checked": len(armatures),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "per_armature": metrics,
        }
    )
    if errors and args.no_fail:
        warn(report, "Rig errors were ignored because --no-fail was supplied")


def endpoint_delta(
    fcurve: bpy.types.FCurve,
    start: float,
    end: float,
) -> float:
    return abs(float(fcurve.evaluate(end)) - float(fcurve.evaluate(start)))


def task_animation_validate(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> None:
    load_input(args, report)
    issues: list[dict[str, Any]] = []
    metrics = validate_animation_data(args, issues)
    action_filter = parse_patterns(args.actions)
    if action_filter:
        metrics = [
            metric
            for metric in metrics
            if matches_patterns(metric["name"], action_filter)
        ]
    if not metrics:
        issue(
            issues,
            "error",
            "animation.no_actions",
            "No animation actions matched the requested target",
        )
    loop_metrics = {}
    for action in bpy.data.actions:
        if action_filter and not matches_patterns(action.name, action_filter):
            continue
        start, end = action.frame_range
        channel_deltas = []
        for fcurve in iter_action_fcurves(action):
            delta = endpoint_delta(fcurve, start, end)
            channel_deltas.append(
                {
                    "data_path": fcurve.data_path,
                    "array_index": fcurve.array_index,
                    "endpoint_delta": delta,
                }
            )
            if args.require_loop and delta > args.loop_tolerance:
                issue(
                    issues,
                    "error",
                    "animation.loop_seam",
                    f"Action {action.name!r} does not loop within tolerance",
                    data_path=fcurve.data_path,
                    array_index=fcurve.array_index,
                    endpoint_delta=delta,
                    tolerance=args.loop_tolerance,
                )
        loop_metrics[action.name] = channel_deltas
    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    report["issues"] = issues
    report["errors"].extend(errors)
    report["warnings"].extend(warnings)
    report["passed"] = not errors
    report["metrics"].update(
        {
            "actions": metrics,
            "loop_channels": loop_metrics,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }
    )
    if errors and args.no_fail:
        warn(report, "Animation errors were ignored because --no-fail was supplied")


def load_bone_map(args: argparse.Namespace) -> dict[str, str]:
    if args.bone_map and args.bone_map_json:
        raise TaskError("Use either --bone-map or --bone-map-json, not both")
    if args.bone_map:
        path = path_from_user(args.bone_map, kind="bone map", must_exist=True)
        data = load_json_object(path.read_text(encoding="utf-8"), kind="bone map")
    elif args.bone_map_json:
        data = load_json_object(args.bone_map_json, kind="--bone-map-json")
    else:
        raise TaskError("Retargeting requires --bone-map or --bone-map-json")
    mapping = data.get("source_to_target", data)
    if not isinstance(mapping, dict) or not mapping:
        raise TaskError("Bone map must contain a non-empty source_to_target object")
    result: dict[str, str] = {}
    for source, target in mapping.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise TaskError("Every bone-map key and value must be a string")
        if not source.strip() or not target.strip():
            raise TaskError("Bone-map names must not be empty")
        result[source] = target
    if len(set(result.values())) != len(result):
        raise TaskError("Multiple source bones map to the same target bone")
    return result


def get_armature(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise TaskError(f"Armature object does not exist: {name}")
    if obj.type != "ARMATURE":
        raise TaskError(f"Object is not an armature: {name}")
    return obj


def remove_retarget_constraints(armature: bpy.types.Object) -> int:
    removed = 0
    for pose_bone in armature.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name.startswith("FORGE3D_RETARGET_"):
                pose_bone.constraints.remove(constraint)
                removed += 1
    return removed


def add_retarget_constraints(
    source: bpy.types.Object,
    target: bpy.types.Object,
    mapping: dict[str, str],
    *,
    copy_root_location: bool,
    root_source: str | None,
    root_target: str | None,
    influence: float,
) -> int:
    count = 0
    for source_bone_name, target_bone_name in mapping.items():
        target_pose_bone = target.pose.bones[target_bone_name]
        constraint = target_pose_bone.constraints.new("COPY_ROTATION")
        constraint.name = f"FORGE3D_RETARGET_ROT_{source_bone_name}"
        constraint.target = source
        constraint.subtarget = source_bone_name
        constraint.target_space = "LOCAL"
        constraint.owner_space = "LOCAL"
        constraint.mix_mode = "REPLACE"
        constraint.influence = influence
        count += 1
    if copy_root_location:
        if not root_source or not root_target:
            raise TaskError(
                "--copy-root-location requires --root-source and --root-target"
            )
        constraint = target.pose.bones[root_target].constraints.new("COPY_LOCATION")
        constraint.name = f"FORGE3D_RETARGET_LOC_{root_source}"
        constraint.target = source
        constraint.subtarget = root_source
        constraint.target_space = "POSE"
        constraint.owner_space = "POSE"
        constraint.influence = influence
        count += 1
    return count


def bake_retarget(
    target: bpy.types.Object,
    mapped_target_bones: Sequence[str],
    *,
    frame_start: int,
    frame_end: int,
    step: int,
) -> None:
    ensure_object_mode()
    deselect_all()
    target.hide_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.mode_set(mode="POSE")
    try:
        bpy.ops.pose.select_all(action="DESELECT")
        for bone_name in mapped_target_bones:
            target.pose.bones[bone_name].select = True
        result = bpy.ops.nla.bake(
            frame_start=frame_start,
            frame_end=frame_end,
            step=step,
            only_selected=True,
            visual_keying=True,
            # Never let Blender clear every constraint on the selected bones.
            # Artist constraints may coexist with the temporary Forge3D ones;
            # those are removed by name after baking when requested.
            clear_constraints=False,
            clear_parents=False,
            use_current_action=True,
            clean_curves=True,
            bake_types={"POSE"},
            channel_types={
                "LOCATION",
                "ROTATION",
                "SCALE",
                "BBONE",
                "PROPS",
            },
        )
        if "FINISHED" not in result:
            raise TaskError(f"NLA bake did not finish: {result}")
    except RuntimeError as exc:
        raise TaskError(f"Retarget bake failed: {exc}") from exc
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def load_humanoid_profile(args: argparse.Namespace) -> dict[str, Any]:
    path = path_from_user(args.profile, kind="humanoid profile", must_exist=True)
    profile = load_json_object(path.read_text(encoding="utf-8"), kind="humanoid profile")
    if profile.get("schema") != "forge3d.humanoid-retarget-profile.v1":
        raise TaskError(
            "Humanoid profile schema must be forge3d.humanoid-retarget-profile.v1"
        )
    for key in ("source_armature", "target_armature"):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise TaskError(f"Humanoid profile requires a non-empty {key}")
    mapping = profile.get("source_to_target")
    if not isinstance(mapping, dict) or not mapping:
        raise TaskError("Humanoid profile requires a non-empty source_to_target object")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in mapping.items()):
        raise TaskError("Humanoid profile bone-map keys and values must be strings")
    if len(set(mapping.values())) != len(mapping):
        raise TaskError("Humanoid profile maps multiple source bones to one target bone")
    chains = profile.get("chains", {})
    if not isinstance(chains, dict):
        raise TaskError("Humanoid profile chains must be an object")
    for name, bones in chains.items():
        if not isinstance(name, str) or not isinstance(bones, list) or len(bones) < 2:
            raise TaskError("Every humanoid chain must name at least two target bones")
        if any(not isinstance(bone, str) or not bone for bone in bones):
            raise TaskError("Humanoid chain bone names must be non-empty strings")
    return profile


def set_fractional_frame(scene: bpy.types.Scene, frame: float) -> None:
    whole = math.floor(frame)
    scene.frame_set(whole, subframe=frame - whole)


def normalized_rotation(matrix: Matrix) -> Matrix:
    return matrix.to_3x3().normalized()


def parse_axis(value: str) -> Vector:
    axes = {
        "X": Vector((1.0, 0.0, 0.0)),
        "+X": Vector((1.0, 0.0, 0.0)),
        "-X": Vector((-1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "+Y": Vector((0.0, 1.0, 0.0)),
        "-Y": Vector((0.0, -1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
        "+Z": Vector((0.0, 0.0, 1.0)),
        "-Z": Vector((0.0, 0.0, -1.0)),
    }
    try:
        return axes[value.strip().upper()].copy()
    except (AttributeError, KeyError) as exc:
        raise TaskError(f"Unsupported humanoid axis {value!r}; use +/-X, +/-Y, or +/-Z") from exc


def humanoid_source_frames(
    profile: dict[str, Any], action: bpy.types.Action
) -> list[float]:
    configured = profile.get("source_frames")
    if configured is not None:
        if not isinstance(configured, list) or len(configured) < 2:
            raise TaskError("source_frames must contain at least two numbers")
        if any(not isinstance(value, (int, float)) for value in configured):
            raise TaskError("source_frames values must be numbers")
        return [float(value) for value in configured]
    count = profile.get("sample_count", 8)
    if not isinstance(count, int) or count < 2 or count > 120:
        raise TaskError("sample_count must be an integer between 2 and 120")
    start, end = (float(value) for value in action.frame_range)
    if end <= start:
        raise TaskError("Source action has no usable frame range")
    exclude_endpoint = bool(profile.get("exclude_loop_endpoint", True))
    divisor = count if exclude_endpoint else count - 1
    step = (end - start) / divisor
    return [start + index * step for index in range(count)]


def import_humanoid_source(
    raw_path: str | None,
    source_name: str,
) -> tuple[bpy.types.Object, list[bpy.types.Object], list[bpy.types.Action]]:
    if not raw_path:
        return get_armature(source_name), [], []
    path = path_from_user(
        raw_path,
        kind="source animation",
        must_exist=True,
        allowed_suffixes={".glb", ".gltf", ".fbx"},
    )
    before_objects = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    if path.suffix.lower() in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        bpy.ops.import_scene.fbx(filepath=str(path))
    imported_objects = [obj for obj in bpy.data.objects if obj not in before_objects]
    imported_actions = [action for action in bpy.data.actions if action not in before_actions]
    armatures = [obj for obj in imported_objects if obj.type == "ARMATURE"]
    exact = next((obj for obj in armatures if obj.name == source_name), None)
    if exact is not None:
        source = exact
    elif len(armatures) == 1:
        source = armatures[0]
    else:
        raise TaskError(
            f"Could not resolve source armature {source_name!r} among imported armatures "
            f"{[obj.name for obj in armatures]}"
        )
    return source, imported_objects, imported_actions


def evaluated_object_center(name: str, depsgraph: bpy.types.Depsgraph) -> Vector:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        raise TaskError(f"Facing marker must be an existing mesh object: {name}")
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if not mesh.vertices:
            raise TaskError(f"Facing marker mesh has no vertices: {name}")
        return sum(
            (evaluated.matrix_world @ vertex.co for vertex in mesh.vertices),
            Vector(),
        ) / len(mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def object_bound_to_bone(
    obj: bpy.types.Object,
    armature: bpy.types.Object,
    bone_name: str,
) -> bool:
    if obj.parent == armature and obj.parent_type == "BONE" and obj.parent_bone == bone_name:
        return True
    if obj.vertex_groups.get(bone_name) is None:
        return False
    return any(
        modifier.type == "ARMATURE" and modifier.object == armature
        for modifier in obj.modifiers
    )


def render_humanoid_review(
    armature: bpy.types.Object,
    frames: Sequence[float],
    output_dir: Path,
    prefix: str,
    *,
    resolution: int,
    forward_axis: Vector,
) -> list[str]:
    renderable = [
        obj
        for obj in armature_export_objects(armature)
        if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
    ]
    bounds = object_world_bounds(renderable)
    if not renderable or bounds is None:
        raise TaskError(f"No renderable meshes are attached to {armature.name}")
    minimum, maximum = bounds
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    radius = max(size.length * 0.5, 0.5)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    old_camera = scene.camera
    old_engine = scene.render.engine
    old_resolution = (scene.render.resolution_x, scene.render.resolution_y)
    old_percentage = scene.render.resolution_percentage
    old_transparent = scene.render.film_transparent
    hidden = {obj: obj.hide_render for obj in scene.objects}
    collection = bpy.data.collections.new(f"Forge3D_{prefix}_Review")
    scene.collection.children.link(collection)
    camera_data = bpy.data.cameras.new(f"Forge3D_{prefix}_ReviewCamera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(size.x, size.y, size.z) * 1.28
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    camera[GENERATED_BY_KEY] = f"Forge3D {TOOL_VERSION}"
    collection.objects.link(camera)
    light_scale = max(radius, 0.5)
    key = create_area_light(
        collection,
        f"Forge3D_{prefix}_Key",
        center,
        Vector((-2.0, -2.5, 3.0)) * light_scale,
        energy=850.0,
        size=light_scale * 2.0,
        color=(1.0, 0.93, 0.82),
    )
    fill = create_area_light(
        collection,
        f"Forge3D_{prefix}_Fill",
        center,
        Vector((2.5, -1.0, 1.5)) * light_scale,
        energy=450.0,
        size=light_scale * 2.0,
        color=(0.72, 0.84, 1.0),
    )
    generated = {camera, key, fill}
    for obj in scene.objects:
        obj.hide_render = obj not in renderable and obj not in generated

    side_axis = Vector((-1.0, 0.0, 0.0))
    if abs(forward_axis.dot(side_axis)) > 0.9:
        side_axis = Vector((0.0, -1.0, 0.0))
    views = {
        "front": forward_axis.normalized(),
        "side": side_axis,
        "isometric": (forward_axis + side_axis + Vector((0.0, 0.0, 0.72))).normalized(),
    }
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    outputs: list[str] = []
    try:
        for view_name, direction in views.items():
            camera.location = center + direction * max(radius * 3.0, 2.0)
            look_at(camera, center)
            for index, frame in enumerate(frames, start=1):
                set_fractional_frame(scene, frame)
                path = output_dir / f"{prefix}_{view_name}_{index:03d}.png"
                scene.render.filepath = str(path)
                bpy.ops.render.render(write_still=True)
                outputs.append(str(path))
    finally:
        for obj, state in hidden.items():
            if obj.name in bpy.data.objects:
                obj.hide_render = state
        scene.camera = old_camera
        scene.render.engine = old_engine
        scene.render.resolution_x, scene.render.resolution_y = old_resolution
        scene.render.resolution_percentage = old_percentage
        scene.render.film_transparent = old_transparent
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
    return outputs


def task_humanoid_retarget(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    profile = load_humanoid_profile(args)
    mapping: dict[str, str] = profile["source_to_target"]
    target = get_armature(profile["target_armature"])
    output_fps = profile.get("output_fps", 10)
    source_fps = profile.get("source_fps", 24)
    if not isinstance(output_fps, int) or not 1 <= output_fps <= 240:
        raise TaskError("output_fps must be an integer from 1 to 240")
    if not isinstance(source_fps, int) or not 1 <= source_fps <= 240:
        raise TaskError("source_fps must be an integer from 1 to 240")
    scene = bpy.context.scene
    scene.render.fps = source_fps
    source, imported_objects, imported_actions = import_humanoid_source(
        args.source_animation,
        profile["source_armature"],
    )
    if source == target:
        raise TaskError("Source and target armatures must be different")
    missing_source = [name for name in mapping if source.pose.bones.get(name) is None]
    missing_target = [name for name in mapping.values() if target.pose.bones.get(name) is None]
    if missing_source or missing_target:
        raise TaskError(
            "Humanoid map references missing bones: "
            f"source={missing_source}, target={missing_target}"
        )
    configured_source_action = profile.get("source_action")
    if configured_source_action is not None:
        if not isinstance(configured_source_action, str) or not configured_source_action:
            raise TaskError("source_action must be a non-empty string")
        selected_action = bpy.data.actions.get(configured_source_action)
        if selected_action is None:
            available = sorted(action.name for action in bpy.data.actions)
            raise TaskError(
                f"Source action {configured_source_action!r} does not exist; "
                f"available actions={available}"
            )
        source.animation_data_create()
        source.animation_data.action = selected_action
    if source.animation_data is None or source.animation_data.action is None:
        raise TaskError(f"Source armature {source.name!r} has no active action")
    source_action = source.animation_data.action
    resolved_source_name = source.name
    source_action_name = source_action.name
    source_frames = humanoid_source_frames(profile, source_action)
    yaw = math.radians(float(profile.get("source_to_target_yaw_degrees", 0.0)))
    alignment = Matrix.Rotation(yaw, 3, "Z")
    alignment_inverse = alignment.inverted()
    source_world_rotation = normalized_rotation(source.matrix_world)
    target_world_rotation = normalized_rotation(target.matrix_world)
    target_world_inverse = target_world_rotation.inverted()

    rest_metrics: dict[str, Any] = {}
    source_rest_rotations: dict[str, Matrix] = {}
    target_rest_rotations: dict[str, Matrix] = {}
    target_rest_directions: dict[str, Vector] = {}
    minimum_rest_dot = float(profile.get("minimum_rest_direction_dot", 0.5))
    issues: list[dict[str, Any]] = []
    for source_name, target_name in mapping.items():
        source_bone = source.data.bones[source_name]
        target_bone = target.data.bones[target_name]
        source_rest_rotation = alignment @ source_world_rotation @ normalized_rotation(source_bone.matrix_local)
        target_rest_rotation = target_world_rotation @ normalized_rotation(target_bone.matrix_local)
        source_rest_rotations[source_name] = source_rest_rotation
        target_rest_rotations[target_name] = target_rest_rotation
        source_direction = (alignment @ source_world_rotation @ (source_bone.tail_local-source_bone.head_local)).normalized()
        target_direction = (target_world_rotation @ (target_bone.tail_local-target_bone.head_local)).normalized()
        target_rest_directions[target_name] = target_direction
        dot = source_direction.dot(target_direction)
        rest_metrics[source_name] = {"target": target_name, "direction_dot": dot}
        if dot < minimum_rest_dot:
            issue(
                issues,
                "error",
                "humanoid.rest_direction_mismatch",
                f"Rest directions disagree for {source_name!r} -> {target_name!r}",
                source_bone=source_name,
                target_bone=target_name,
                direction_dot=dot,
                minimum=minimum_rest_dot,
            )

    samples: list[dict[str, Any]] = []
    first_positions: dict[str, Vector] = {}
    for index, source_frame in enumerate(source_frames):
        set_fractional_frame(scene, source_frame)
        bpy.context.view_layer.update()
        deltas: dict[str, Matrix] = {}
        directions: dict[str, Vector] = {}
        pose_rotations: dict[str, Matrix] = {}
        positions: dict[str, Vector] = {}
        for source_name in mapping:
            pose = source.pose.bones[source_name]
            pose_world_rotation = alignment @ source_world_rotation @ normalized_rotation(pose.matrix)
            pose_rotations[source_name] = pose_world_rotation
            deltas[source_name] = (
                pose_world_rotation
                @ source_rest_rotations[source_name].inverted()
            )
            direction = alignment @ source_world_rotation @ (pose.tail-pose.head)
            directions[source_name] = direction.normalized()
            position = alignment @ source_world_rotation @ pose.head
            positions[source_name] = position
            if index == 0:
                first_positions[source_name] = position.copy()
        samples.append(
            {
                "source_frame": source_frame,
                "deltas": deltas,
                "directions": directions,
                "pose_rotations": pose_rotations,
                "positions": positions,
            }
        )

    forward_axis = parse_axis(str(profile.get("forward_axis", "-Y")))
    review_outputs: list[str] = []
    if args.review_dir:
        review_dir = path_from_user(args.review_dir, kind="review directory")
        if review_dir.exists() and any(review_dir.iterdir()) and not args.force:
            raise TaskError(f"Review directory is not empty; pass --force: {review_dir}")
        resolution = int(profile.get("review_resolution", 256))
        if not 64 <= resolution <= 2048:
            raise TaskError("review_resolution must be from 64 to 2048")
        review_outputs.extend(
            render_humanoid_review(
                source,
                source_frames,
                review_dir,
                "control",
                resolution=resolution,
                forward_axis=(alignment @ forward_axis).normalized(),
            )
        )

    old_target_action = target.animation_data.action if target.animation_data else None
    target.animation_data_create()
    action_name = args.action_name or str(profile.get("action_name", "HumanoidRetarget"))
    if bpy.data.actions.get(action_name):
        action_name = bpy.data.actions.new(action_name).name
    else:
        bpy.data.actions.new(action_name)
    target_action = bpy.data.actions[action_name]
    target.animation_data.action = target_action
    remove_retarget_constraints(target)
    target.data.pose_position = "POSE"
    scene.render.fps = output_fps
    scene.frame_start = 1
    scene.frame_end = len(samples)
    translation_scales = profile.get("translation_scales", {})
    if not isinstance(translation_scales, dict):
        raise TaskError("translation_scales must be an object keyed by source bone")
    mapped_targets = set(mapping.values())
    absolute_orientation_bones = profile.get("absolute_orientation_bones", [])
    if not isinstance(absolute_orientation_bones, list) or any(
        not isinstance(name, str) or name not in mapping
        for name in absolute_orientation_bones
    ):
        raise TaskError(
            "absolute_orientation_bones must list source bones present in source_to_target"
        )
    absolute_orientation_set = set(absolute_orientation_bones)
    ordered_mapping = sorted(
        mapping.items(),
        key=lambda item: len(target.data.bones[item[1]].parent_recursive),
    )
    for output_frame, sample in enumerate(samples, start=1):
        scene.frame_set(output_frame)
        for source_name, target_name in ordered_mapping:
            pose = target.pose.bones[target_name]
            pose.rotation_mode = "QUATERNION"
            if source_name in absolute_orientation_set:
                desired_world_rotation = sample["pose_rotations"][source_name]
            else:
                desired_world_rotation = sample["deltas"][source_name] @ target_rest_rotations[target_name]
            desired_local_rotation = target_world_inverse @ desired_world_rotation
            desired = Matrix.Identity(4)
            for row in range(3):
                for column in range(3):
                    desired[row][column] = desired_local_rotation[row][column]
            scale = translation_scales.get(source_name)
            if scale is not None:
                if not isinstance(scale, (int, float)):
                    raise TaskError(f"Translation scale for {source_name} must be numeric")
                world_delta = sample["positions"][source_name] - first_positions[source_name]
                desired.translation = (
                    target.data.bones[target_name].head_local
                    + target_world_inverse @ (world_delta * float(scale))
                )
            elif pose.parent is not None and pose.parent.name in mapped_targets:
                desired.translation = pose.parent.tail.copy()
            else:
                desired.translation = target.data.bones[target_name].head_local.copy()
            pose.matrix = desired
            pose.keyframe_insert("location", frame=output_frame, group=target_name)
            pose.keyframe_insert("rotation_quaternion", frame=output_frame, group=target_name)
            pose.keyframe_insert("scale", frame=output_frame, group=target_name)
            bpy.context.view_layer.update()
    for curve in iter_action_fcurves(target_action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"

    # Remove the source control only after the control proof and target bake.
    source_closure = set(armature_export_objects(source))
    for obj in list(source_closure | set(imported_objects)):
        if obj != target and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for action in imported_actions:
        if action != target_action and action.name in bpy.data.actions and action.users == 0:
            bpy.data.actions.remove(action)
    if old_target_action and old_target_action != target_action and old_target_action.users == 0:
        bpy.data.actions.remove(old_target_action)

    chains: dict[str, list[str]] = profile.get("chains", {})
    leg_chains = profile.get("leg_chains", [])
    if not isinstance(leg_chains, list) or any(name not in chains for name in leg_chains):
        raise TaskError("leg_chains must list names defined in chains")
    inverse_mapping = {target_name: source_name for source_name, target_name in mapping.items()}
    maximum_gap = float(profile.get("maximum_chain_gap", 1.0e-5))
    maximum_angle_delta = float(profile.get("maximum_joint_angle_delta_degrees", 2.0))
    minimum_pose_dot = float(profile.get("minimum_pose_direction_dot", 0.999))
    target_frames: list[dict[str, Any]] = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    target_world_rotation = normalized_rotation(target.matrix_world)
    for output_frame, sample in enumerate(samples, start=1):
        scene.frame_set(output_frame)
        bpy.context.view_layer.update()
        frame_metrics: dict[str, Any] = {"frame": output_frame, "chains": {}}
        for source_name, target_name in mapping.items():
            pose = target.pose.bones[target_name]
            actual = (target_world_rotation @ (pose.tail-pose.head)).normalized()
            if source_name in absolute_orientation_set:
                expected = sample["directions"][source_name]
            else:
                expected = (sample["deltas"][source_name] @ target_rest_directions[target_name]).normalized()
            dot = actual.dot(expected)
            if dot < minimum_pose_dot:
                issue(
                    issues,
                    "error",
                    "humanoid.pose_direction_mismatch",
                    f"Target bone {target_name!r} diverges from the transferred source motion",
                    target_bone=target_name,
                    frame=output_frame,
                    direction_dot=dot,
                    minimum=minimum_pose_dot,
                )
        for chain_name, bone_names in chains.items():
            poses = [target.pose.bones[name] for name in bone_names]
            gaps = [(poses[i].tail-poses[i+1].head).length for i in range(len(poses)-1)]
            target_angles = [
                math.degrees((poses[i].tail-poses[i].head).angle(poses[i+1].tail-poses[i+1].head))
                for i in range(len(poses)-1)
            ]
            source_names = [inverse_mapping.get(name) for name in bone_names]
            source_angles: list[float] = []
            angle_deltas: list[float] = []
            if all(source_names):
                source_directions = [sample["directions"][name] for name in source_names]
                source_angles = [
                    math.degrees(source_directions[i].angle(source_directions[i+1]))
                    for i in range(len(source_directions)-1)
                ]
                angle_deltas = [abs(a-b) for a, b in zip(target_angles, source_angles)]
            frame_metrics["chains"][chain_name] = {
                "gaps": gaps,
                "target_angles": target_angles,
                "source_angles": source_angles,
                "angle_deltas": angle_deltas,
            }
            if gaps and max(gaps) > maximum_gap:
                issue(
                    issues,
                    "error",
                    "humanoid.chain_gap",
                    f"Target chain {chain_name!r} is disconnected",
                    frame=output_frame,
                    maximum_gap=max(gaps),
                    tolerance=maximum_gap,
                )
            if angle_deltas and max(angle_deltas) > maximum_angle_delta:
                issue(
                    issues,
                    "error",
                    "humanoid.joint_angle_mismatch",
                    f"Target chain {chain_name!r} no longer matches the human control",
                    frame=output_frame,
                    maximum_delta=max(angle_deltas),
                    tolerance=maximum_angle_delta,
                )
            if chain_name in leg_chains:
                hip = target.matrix_world @ poses[0].head
                knee = target.matrix_world @ poses[0].tail
                ankle = target.matrix_world @ poses[1].tail
                ordering = hip.z > knee.z > ankle.z
                frame_metrics["chains"][chain_name]["hip_knee_ankle_ordered"] = ordering
                if not ordering:
                    issue(
                        issues,
                        "error",
                        "humanoid.leg_ordering",
                        f"Target leg {chain_name!r} does not read hip > knee > ankle",
                        frame=output_frame,
                        hip_z=hip.z,
                        knee_z=knee.z,
                        ankle_z=ankle.z,
                    )
        facing = profile.get("facing")
        if facing is not None:
            if not isinstance(facing, dict):
                raise TaskError("facing must be an object")
            origin = evaluated_object_center(str(facing.get("origin_object", "")), depsgraph)
            front = evaluated_object_center(str(facing.get("front_object", "")), depsgraph)
            declared = parse_axis(str(facing.get("axis", profile.get("forward_axis", "-Y"))))
            declared_world = (target_world_rotation @ declared).normalized()
            actual = (front-origin).normalized()
            facing_dot = actual.dot(declared_world)
            frame_metrics["facing_dot"] = facing_dot
            minimum_facing = float(facing.get("minimum_dot", 0.75))
            if facing_dot < minimum_facing:
                issue(
                    issues,
                    "error",
                    "humanoid.facing_mismatch",
                    "Deformed facing markers disagree with declared character forward",
                    frame=output_frame,
                    facing_dot=facing_dot,
                    minimum=minimum_facing,
                )
        target_frames.append(frame_metrics)

    attachments = profile.get("attachments", [])
    if not isinstance(attachments, list):
        raise TaskError("attachments must be a list")
    attachment_metrics = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise TaskError("Each attachment must be an object")
        pattern = str(attachment.get("object_pattern", ""))
        bone_name = str(attachment.get("bone", ""))
        matches = [obj for obj in bpy.context.scene.objects if fnmatch.fnmatchcase(obj.name, pattern)]
        valid = [obj.name for obj in matches if object_bound_to_bone(obj, target, bone_name)]
        attachment_metrics.append(
            {"pattern": pattern, "bone": bone_name, "matched": [obj.name for obj in matches], "valid": valid}
        )
        if not matches or len(valid) != len(matches):
            issue(
                issues,
                "error",
                "humanoid.attachment_mismatch",
                f"Attachment pattern {pattern!r} is not fully bound to {bone_name!r}",
                matched=[obj.name for obj in matches],
                valid=valid,
            )

    if args.review_dir:
        review_outputs.extend(
            render_humanoid_review(
                target,
                list(range(1, len(samples)+1)),
                path_from_user(args.review_dir, kind="review directory"),
                "target",
                resolution=int(profile.get("review_resolution", 256)),
                forward_axis=forward_axis,
            )
        )
        report["outputs"]["review_frames"] = review_outputs

    report["issues"] = issues
    report["errors"].extend(item for item in issues if item["severity"] == "error")
    report["warnings"].extend(item for item in issues if item["severity"] == "warning")
    report["passed"] = not any(item["severity"] == "error" for item in issues)
    report["metrics"].update(
        {
            "method": "rest-relative-global",
            "absolute_orientation_bones": sorted(absolute_orientation_set),
            "source_armature": resolved_source_name,
            "target_armature": target.name,
            "source_action": source_action_name,
            "target_action": target_action.name,
            "source_fps": source_fps,
            "output_fps": output_fps,
            "source_frames": source_frames,
            "output_frames": list(range(1, len(samples)+1)),
            "rest_alignment": rest_metrics,
            "target_frames": target_frames,
            "attachments": attachment_metrics,
            "error_count": len(report["errors"]),
            "warning_count": len(report["warnings"]),
        }
    )
    change(
        report,
        "Baked rest-relative global humanoid retarget with semantic proof",
        mapped_bones=len(mapping),
        sampled_frames=len(samples),
    )
    save_optional_output(args, report, input_path)


def task_retarget(args: argparse.Namespace, report: dict[str, Any]) -> None:
    input_path = load_input(args, report)
    source = get_armature(args.source_armature)
    target = get_armature(args.target_armature)
    if source == target:
        raise TaskError("Source and target armatures must be different objects")
    if not 0.0 <= args.influence <= 1.0:
        raise TaskError("--influence must be between zero and one")
    if args.step < 1:
        raise TaskError("--step must be at least one")
    mapping = load_bone_map(args)
    missing_source = [
        name for name in mapping if source.pose.bones.get(name) is None
    ]
    missing_target = [
        name for name in mapping.values() if target.pose.bones.get(name) is None
    ]
    if missing_source or missing_target:
        raise TaskError(
            "Bone map references missing bones: "
            f"source={missing_source}, target={missing_target}"
        )
    if args.root_source and source.pose.bones.get(args.root_source) is None:
        raise TaskError(f"Source root bone does not exist: {args.root_source}")
    if args.root_target and target.pose.bones.get(args.root_target) is None:
        raise TaskError(f"Target root bone does not exist: {args.root_target}")
    existing = sum(
        1
        for pose_bone in target.pose.bones
        for constraint in pose_bone.constraints
        if constraint.name.startswith("FORGE3D_RETARGET_")
    )
    if existing and not args.replace_existing:
        raise TaskError(
            f"Target already has {existing} Forge3D retarget constraints; "
            "pass --replace-existing to rebuild them"
        )
    removed = remove_retarget_constraints(target) if existing else 0
    created = add_retarget_constraints(
        source,
        target,
        mapping,
        copy_root_location=args.copy_root_location,
        root_source=args.root_source,
        root_target=args.root_target,
        influence=args.influence,
    )
    frame_start = (
        args.frame_start if args.frame_start is not None else bpy.context.scene.frame_start
    )
    frame_end = (
        args.frame_end if args.frame_end is not None else bpy.context.scene.frame_end
    )
    if frame_end < frame_start:
        raise TaskError("Retarget frame end must not precede frame start")
    if args.bake:
        mapped_target_bones = list(mapping.values())
        if args.copy_root_location and args.root_target not in mapped_target_bones:
            mapped_target_bones.append(args.root_target)
        bake_retarget(
            target,
            mapped_target_bones,
            frame_start=frame_start,
            frame_end=frame_end,
            step=args.step,
        )
        if args.clear_constraints:
            removed += remove_retarget_constraints(target)
        if (
            target.animation_data
            and target.animation_data.action
            and args.action_name
        ):
            target.animation_data.action.name = args.action_name
    report["metrics"].update(
        {
            "source_armature": source.name,
            "target_armature": target.name,
            "bone_map": mapping,
            "constraints_removed": removed,
            "constraints_created": created,
            "constraints_remaining": sum(
                1
                for pose_bone in target.pose.bones
                for constraint in pose_bone.constraints
                if constraint.name.startswith("FORGE3D_RETARGET_")
            ),
            "baked": args.bake,
            "frame_range": [frame_start, frame_end],
            "action": (
                target.animation_data.action.name
                if target.animation_data and target.animation_data.action
                else None
            ),
        }
    )
    change(
        report,
        "Created retarget mapping" + (" and baked it" if args.bake else ""),
        source=source.name,
        target=target.name,
        mapped_bones=len(mapping),
    )
    save_optional_output(args, report, input_path)


def add_target_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--objects",
        help="Comma-separated, case-sensitive object-name globs (default: all)",
    )
    parser.add_argument(
        "--collection",
        help="Restrict targets to this collection and its children",
    )


def add_report_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report", help="Write the JSON task report to this path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permit replacement of the specifically named output file",
    )


def add_input_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        help="Input .blend, .glb/.gltf, .fbx, .obj, .stl, or USD file",
    )
    add_target_flags(parser)
    add_report_flags(parser)


def add_mutation_flags(parser: argparse.ArgumentParser) -> None:
    add_input_flags(parser)
    parser.add_argument(
        "--output",
        "--output-blend",
        dest="output",
        help="Save the resulting editable scene to this .blend path",
    )
    parser.add_argument(
        "--pack-resources",
        action="store_true",
        help="Pack external resources before saving",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable .blend compression",
    )


def add_validation_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-triangles", type=int, default=250_000)
    parser.add_argument("--max-materials", type=int, default=16)
    parser.add_argument("--max-bones", type=int, default=256)
    parser.add_argument("--max-influences", type=int, default=4)
    parser.add_argument("--epsilon", type=float, default=1.0e-8)
    parser.add_argument("--weight-epsilon", type=float, default=1.0e-6)
    parser.add_argument("--weight-tolerance", type=float, default=1.0e-3)
    parser.add_argument("--transform-tolerance", type=float, default=1.0e-5)
    parser.add_argument("--uv-tolerance", type=float, default=1.0e-5)
    parser.add_argument(
        "--strict-manifold",
        action="store_true",
        help="Treat open/boundary/non-manifold geometry as an error",
    )
    parser.add_argument(
        "--require-uv",
        action="store_true",
        help="Treat missing UVs as an error",
    )
    parser.add_argument(
        "--allow-tiled-uv",
        action="store_true",
        help="Do not warn about UVs outside the 0–1 tile",
    )
    parser.add_argument("--max-animation-frames", type=float, default=0)
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Return success even when validation reports errors",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge3d_task.py",
        description=(
            "Composable Forge3D tasks for Blender 5. Invoke through Blender after `--`."
        ),
    )
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    subparsers = parser.add_subparsers(dest="task", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inventory scene objects, geometry, rigs, actions, and dependencies"
    )
    add_input_flags(inspect_parser)
    inspect_parser.add_argument(
        "--evaluated",
        action="store_true",
        help="Also count evaluated triangles after modifiers",
    )
    inspect_parser.set_defaults(handler=task_inspect)

    validate_parser = subparsers.add_parser(
        "validate", help="Run geometry, transform, UV, dependency, rig, and animation QA"
    )
    add_input_flags(validate_parser)
    add_validation_flags(validate_parser)
    validate_parser.add_argument(
        "--no-animation",
        dest="include_animation",
        action="store_false",
        help="Skip action validation",
    )
    validate_parser.set_defaults(handler=task_validate, include_animation=True)

    normalize_parser = subparsers.add_parser(
        "normalize", help="Normalize units, transforms, size, ground contact, and origins"
    )
    add_mutation_flags(normalize_parser)
    normalize_parser.add_argument(
        "--no-metric",
        dest="metric",
        action="store_false",
        help="Leave scene units unchanged",
    )
    normalize_parser.add_argument(
        "--apply-location",
        action="store_true",
        help="Apply object locations as well as rotation and scale",
    )
    normalize_parser.add_argument(
        "--no-apply-rotation",
        dest="apply_rotation",
        action="store_false",
    )
    normalize_parser.add_argument(
        "--no-apply-scale",
        dest="apply_scale",
        action="store_false",
    )
    normalize_parser.add_argument(
        "--target-size",
        type=float,
        help="Scale the selection's maximum world dimension to this many metres",
    )
    normalize_parser.add_argument(
        "--ground",
        action="store_true",
        help="Move target roots so the lowest world-space point is at Z=0",
    )
    normalize_parser.add_argument(
        "--origin",
        choices=["keep", "geometry", "bounds", "base"],
        default="keep",
    )
    normalize_parser.set_defaults(
        handler=task_normalize,
        metric=True,
        apply_rotation=True,
        apply_scale=True,
    )

    repair_parser = subparsers.add_parser(
        "repair",
        aliases=["clean"],
        help="Repair duplicate, degenerate, loose, normal, and optional hole problems",
    )
    add_mutation_flags(repair_parser)
    repair_parser.add_argument("--merge-distance", type=float, default=1.0e-5)
    repair_parser.add_argument(
        "--merge-across-islands",
        action="store_true",
        help=(
            "Allow duplicate merging between disconnected mesh islands; "
            "off by default to preserve intentional overlapping parts"
        ),
    )
    repair_parser.add_argument("--degenerate-distance", type=float, default=1.0e-8)
    repair_parser.add_argument(
        "--keep-loose",
        dest="delete_loose",
        action="store_false",
    )
    repair_parser.add_argument(
        "--keep-normals",
        dest="recalculate_normals",
        action="store_false",
    )
    repair_parser.add_argument("--fill-holes", action="store_true")
    repair_parser.add_argument("--max-hole-sides", type=int, default=8)
    repair_parser.add_argument("--apply-modifiers", action="store_true")
    repair_parser.set_defaults(
        handler=task_repair,
        delete_loose=True,
        recalculate_normals=True,
    )

    unwrap_parser = subparsers.add_parser(
        "unwrap",
        aliases=["uv-unwrap"],
        help="Create a reusable UV layer with a deterministic unwrap profile",
    )
    add_mutation_flags(unwrap_parser)
    unwrap_parser.add_argument(
        "--method",
        choices=["smart", "lightmap", "cube", "cylinder"],
        default="smart",
    )
    unwrap_parser.add_argument("--uv-name", default="UVMap")
    unwrap_parser.add_argument("--replace-uv", action="store_true")
    unwrap_parser.add_argument("--angle-limit", type=float, default=66.0)
    unwrap_parser.add_argument("--island-margin", type=float, default=0.02)
    unwrap_parser.add_argument("--area-weight", type=float, default=0.0)
    unwrap_parser.add_argument("--box-divisions", type=int, default=12)
    unwrap_parser.add_argument("--margin-divisions", type=float, default=0.1)
    unwrap_parser.add_argument("--cube-size", type=float, default=1.0)
    unwrap_parser.set_defaults(handler=task_unwrap)

    material_parser = subparsers.add_parser(
        "material",
        aliases=["pbr"],
        help="Build and assign a Principled PBR material",
    )
    add_mutation_flags(material_parser)
    material_parser.add_argument("--material-name", default="Forge3D_Material")
    material_parser.add_argument("--base-color", default="0.5,0.5,0.5,1")
    material_parser.add_argument("--metallic", type=float, default=0.0)
    material_parser.add_argument("--roughness", type=float, default=0.5)
    material_parser.add_argument("--base-color-map")
    material_parser.add_argument("--normal-map")
    material_parser.add_argument("--roughness-map")
    material_parser.add_argument("--metallic-map")
    material_parser.add_argument("--ao-map")
    material_parser.add_argument("--emission-map")
    material_parser.add_argument("--normal-strength", type=float, default=1.0)
    material_parser.add_argument("--emission-strength", type=float, default=1.0)
    material_parser.add_argument("--use-texture-alpha", action="store_true")
    material_parser.add_argument("--replace-materials", action="store_true")
    material_parser.add_argument("--replace-existing", action="store_true")
    material_parser.set_defaults(handler=task_material)

    lod_parser = subparsers.add_parser(
        "lods",
        help="Generate source-only decimated LOD meshes for Blender review",
    )
    add_mutation_flags(lod_parser)
    lod_parser.add_argument("--ratios", default="0.5,0.2")
    lod_parser.add_argument("--lod-collection", default="Forge3D_LODs")
    lod_parser.add_argument("--triangulate", action="store_true")
    lod_parser.add_argument("--replace-existing", action="store_true")
    lod_parser.set_defaults(handler=task_lods)

    collision_parser = subparsers.add_parser(
        "collision",
        help="Generate Godot-friendly -colonly or -convcolonly helpers",
    )
    add_mutation_flags(collision_parser)
    collision_parser.add_argument(
        "--mode",
        choices=["box", "convex", "mesh"],
        default="convex",
    )
    collision_parser.add_argument("--ratio", type=float, default=0.2)
    collision_parser.add_argument(
        "--include-lods",
        action="store_true",
        help="Generate separate collision meshes for generated LOD objects too",
    )
    collision_parser.add_argument(
        "--collision-collection",
        default="Forge3D_Collision",
    )
    collision_parser.add_argument("--replace-existing", action="store_true")
    collision_parser.set_defaults(handler=task_collision)

    turntable_parser = subparsers.add_parser(
        "turntable", help="Render a lit, auto-framed PNG preview or turntable"
    )
    add_input_flags(turntable_parser)
    turntable_parser.add_argument(
        "--output",
        required=True,
        help="PNG path for one frame, or directory/stem for multiple frames",
    )
    turntable_parser.add_argument("--frames", type=int, default=1)
    turntable_parser.add_argument("--resolution", type=int, default=512)
    turntable_parser.add_argument("--lens", type=float, default=55.0)
    turntable_parser.add_argument("--elevation", type=float, default=20.0)
    turntable_parser.add_argument("--start-angle", type=float, default=-45.0)
    turntable_parser.add_argument("--distance-multiplier", type=float, default=2.7)
    turntable_parser.add_argument("--world-strength", type=float, default=0.3)
    turntable_parser.add_argument("--transparent", action="store_true")
    turntable_parser.add_argument(
        "--armature",
        help="Frame only renderable objects bound or parented to this armature.",
    )
    turntable_parser.add_argument(
        "--review-collection",
        default="Forge3D_Review",
    )
    turntable_parser.add_argument("--save-blend")
    turntable_parser.add_argument("--pack-resources", action="store_true")
    turntable_parser.set_defaults(handler=task_turntable)

    save_parser = subparsers.add_parser(
        "save", help="Save a guarded canonical .blend copy"
    )
    add_input_flags(save_parser)
    save_parser.add_argument(
        "--output",
        "--output-blend",
        dest="output",
        required=True,
    )
    save_parser.add_argument("--pack-resources", action="store_true")
    save_parser.add_argument("--no-compress", action="store_true")
    save_parser.set_defaults(handler=task_save)

    export_parser = subparsers.add_parser(
        "export-glb", help="Export a Godot-ready binary glTF"
    )
    add_input_flags(export_parser)
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--apply-modifiers", action="store_true")
    export_parser.add_argument("--tangents", action="store_true")
    export_parser.add_argument("--cameras", action="store_true")
    export_parser.add_argument("--lights", action="store_true")
    export_parser.add_argument("--no-animations", action="store_true")
    export_parser.add_argument(
        "--armature",
        help="Export one armature and its bound or parented dependency closure.",
    )
    export_parser.add_argument(
        "--actions",
        help="Comma-separated action-name globs; unmatched actions are excluded.",
    )
    export_parser.add_argument("--force-sampling", action="store_true")
    export_parser.add_argument("--deform-bones-only", action="store_true")
    export_parser.add_argument("--gpu-instances", action="store_true")
    export_parser.set_defaults(handler=task_export_glb)

    procedural_parser = subparsers.add_parser(
        "procedural",
        help=(
            "Generate deterministic game geometry, including hard-surface "
            "equipment/medical cases"
        ),
    )
    add_mutation_flags(procedural_parser)
    procedural_parser.add_argument(
        "--recipe",
        required=True,
        choices=sorted([*PROCEDURAL_RECIPES, "terrain"]),
    )
    procedural_parser.add_argument("--params")
    procedural_parser.add_argument("--params-file")
    procedural_parser.add_argument("--seed", type=int, default=0)
    procedural_parser.add_argument(
        "--asset-collection",
        default="Forge3D_Asset",
    )
    procedural_parser.add_argument(
        "--keep-scene",
        dest="clear_scene",
        action="store_false",
        help="Add the generated asset to the loaded scene instead of starting clean",
    )
    procedural_parser.add_argument("--replace-existing", action="store_true")
    procedural_parser.set_defaults(handler=task_procedural, clear_scene=True)

    rig_humanoid_parser = subparsers.add_parser(
        "rig-humanoid",
        help=(
            "Fit Blender's bundled Rigify human metarig and bind matched meshes "
            "with automatic weights"
        ),
    )
    add_mutation_flags(rig_humanoid_parser)
    rig_humanoid_parser.add_argument("--rig-name", default="Forge3D_Rig")
    rig_humanoid_parser.add_argument(
        "--helper-collection",
        default="Forge3D_RigHelpers",
    )
    rig_humanoid_parser.set_defaults(handler=task_rig_humanoid)

    rig_parser = subparsers.add_parser(
        "rig-validate",
        help="Validate armatures, deform bones, skin weights, and rig attachments",
    )
    add_input_flags(rig_parser)
    add_validation_flags(rig_parser)
    rig_parser.set_defaults(handler=task_rig_validate)

    animation_parser = subparsers.add_parser(
        "animation-validate",
        help="Validate Blender 5 slotted actions, keyframes, ranges, and loop seams",
    )
    add_input_flags(animation_parser)
    animation_parser.add_argument(
        "--actions",
        help="Comma-separated, case-sensitive action-name globs",
    )
    animation_parser.add_argument("--require-loop", action="store_true")
    animation_parser.add_argument("--loop-tolerance", type=float, default=1.0e-3)
    animation_parser.add_argument("--max-animation-frames", type=float, default=0)
    animation_parser.add_argument("--no-fail", action="store_true")
    animation_parser.set_defaults(handler=task_animation_validate)

    retarget_parser = subparsers.add_parser(
        "retarget",
        help=(
            "Create source-to-target pose constraints and optionally bake them. "
            "This is a transparent scaffold for inspected retarget profiles."
        ),
    )
    add_mutation_flags(retarget_parser)
    retarget_parser.add_argument("--source-armature", required=True)
    retarget_parser.add_argument("--target-armature", required=True)
    retarget_parser.add_argument("--bone-map")
    retarget_parser.add_argument("--bone-map-json")
    retarget_parser.add_argument("--copy-root-location", action="store_true")
    retarget_parser.add_argument("--root-source")
    retarget_parser.add_argument("--root-target")
    retarget_parser.add_argument("--influence", type=float, default=1.0)
    retarget_parser.add_argument("--frame-start", type=int)
    retarget_parser.add_argument("--frame-end", type=int)
    retarget_parser.add_argument("--step", type=int, default=1)
    retarget_parser.add_argument("--bake", action="store_true")
    retarget_parser.add_argument(
        "--clear-constraints",
        action="store_true",
        help="Remove temporary constraints as part of baking",
    )
    retarget_parser.add_argument("--action-name")
    retarget_parser.add_argument("--replace-existing", action="store_true")
    retarget_parser.set_defaults(handler=task_retarget)

    humanoid_retarget_parser = subparsers.add_parser(
        "humanoid-retarget",
        help=(
            "Bake profile-driven rest-relative global humanoid motion and "
            "prove chains, joint angles, facing, and attachments"
        ),
    )
    add_mutation_flags(humanoid_retarget_parser)
    humanoid_retarget_parser.add_argument(
        "--source-animation",
        help="External .glb/.gltf/.fbx control animation; omit when the source rig is already in --input",
    )
    humanoid_retarget_parser.add_argument("--profile", required=True)
    humanoid_retarget_parser.add_argument("--action-name")
    humanoid_retarget_parser.add_argument(
        "--review-dir",
        help="Render front, side, and isometric control/target PNG sequences",
    )
    humanoid_retarget_parser.set_defaults(handler=task_humanoid_retarget)

    return parser


REQUEST_KEY_ALIASES = {
    "operation": "task",
    "input_blend": "input",
    "output_blend": "output",
    "output_glb": "output",
}
FALSE_FLAG_KEYS = {
    "metric": "no-metric",
    "apply_rotation": "no-apply-rotation",
    "apply_scale": "no-apply-scale",
    "include_animation": "no-animation",
}


def request_to_argv(path_raw: str) -> list[str]:
    path = path_from_user(path_raw, kind="request file", must_exist=True)
    payload = load_json_object(path.read_text(encoding="utf-8"), kind="request file")
    task = payload.get("task", payload.get("operation"))
    if not isinstance(task, str) or not task:
        raise TaskError("Request file must contain a non-empty task or operation")
    raw_args = payload.get("args", {})
    if not isinstance(raw_args, dict):
        raise TaskError("Request file args must be a JSON object")
    argv = [task]
    for raw_key, value in raw_args.items():
        key = REQUEST_KEY_ALIASES.get(str(raw_key), str(raw_key))
        key = key.replace("_", "-")
        if key == "task":
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                argv.append(f"--{key}")
            elif key.replace("-", "_") in FALSE_FLAG_KEYS:
                argv.append(f"--{FALSE_FLAG_KEYS[key.replace('-', '_')]}")
            continue
        if key == "bone-map" and isinstance(value, dict):
            argv.extend(["--bone-map-json", json.dumps(value)])
            continue
        if key == "objects" and isinstance(value, list):
            argv.extend(["--objects", ",".join(str(item) for item in value)])
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        argv.extend([f"--{key}", str(value)])
    return argv


def blender_argv() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def write_report_file(
    raw_path: str,
    report: dict[str, Any],
    *,
    force: bool,
) -> Path:
    path = prepare_output_file(
        raw_path,
        kind="JSON report",
        force=force,
        allowed_suffixes={".json"},
    )
    path.write_text(
        json.dumps(json_safe(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    raw_argv = blender_argv()
    if raw_argv[:1] == ["--request"]:
        if len(raw_argv) != 2:
            print("--request requires exactly one JSON file path", file=sys.stderr)
            return 2
        try:
            argv = request_to_argv(raw_argv[1])
        except TaskError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        argv = raw_argv
    parser = build_parser()
    args = parser.parse_args(argv)
    report = new_report(args.task, argv)
    exit_code = 0
    try:
        args.handler(args, report)
        validation_failed = report.get("passed") is False and not getattr(
            args, "no_fail", False
        )
        if validation_failed:
            report["status"] = "failed"
            exit_code = 3
        else:
            report["status"] = "success"
    except TaskError as exc:
        report["status"] = "failed"
        report["errors"].append(
            {"severity": "error", "code": "task.error", "message": str(exc)}
        )
        exit_code = 2
    except Exception as exc:  # Ensure unexpected Blender failures still produce JSON.
        report["status"] = "failed"
        report["errors"].append(
            {
                "severity": "error",
                "code": "task.unexpected_exception",
                "message": str(exc),
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
        )
        exit_code = 1
    report["finished_at"] = utc_now()
    if getattr(args, "report", None):
        try:
            report_path = write_report_file(args.report, report, force=args.force)
            report["outputs"]["report"] = str(report_path)
            # Rewrite once so the persisted report includes its own path.
            report_path.write_text(
                json.dumps(json_safe(report), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            report["status"] = "failed"
            report["errors"].append(
                {
                    "severity": "error",
                    "code": "report.write_failed",
                    "message": str(exc),
                }
            )
            if exit_code == 0:
                exit_code = 2
    print(REPORT_PREFIX + json.dumps(json_safe(report), sort_keys=True), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

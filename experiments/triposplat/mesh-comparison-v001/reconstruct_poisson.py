"""Reconstruct a polygon surface from an oriented Gaussian-splat point cloud.

The smallest principal axis of each anisotropic Gaussian is treated as its
surface normal.  Screened Poisson reconstruction then fits a connected surface
through those oriented samples.  This is intentionally separate from the
voxel-opacity method used by SplatTransform so the comparison is meaningful.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pymeshlab


DC_COEFFICIENT = 0.28209479177387814


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--depth", type=int, default=9)
    parser.add_argument("--opacity", type=float, default=0.05)
    return parser.parse_args()


def read_gaussians(path: Path) -> tuple[np.ndarray, list[str]]:
    with path.open("rb") as stream:
        prefix = stream.read(16384)
    marker = b"end_header"
    marker_at = prefix.find(marker)
    if marker_at < 0:
        raise ValueError("PLY end_header marker was not found")
    newline_at = prefix.find(b"\n", marker_at)
    header_end = len(prefix) if newline_at < 0 else newline_at + 1
    header = prefix[:header_end].decode("ascii")
    if "format binary_little_endian 1.0" not in header:
        raise ValueError("Only binary_little_endian PLY is supported")

    match = re.search(r"^element vertex (\d+)$", header, re.MULTILINE)
    if not match:
        raise ValueError("PLY vertex count was not found")
    count = int(match.group(1))
    section = header.split("element vertex", 1)[1].split("end_header", 1)[0]
    properties = [
        line.removeprefix("property float ")
        for line in section.splitlines()
        if line.startswith("property float ")
    ]
    required = {
        "x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
        "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
    }
    missing = required.difference(properties)
    if missing:
        raise ValueError(f"Missing Gaussian properties: {sorted(missing)}")

    dtype = np.dtype([(name, "<f4") for name in properties])
    expected = header_end + count * dtype.itemsize
    if path.stat().st_size != expected:
        raise ValueError(f"Unexpected PLY size: expected {expected}, got {path.stat().st_size}")
    return np.memmap(path, dtype=dtype, mode="r", offset=header_end, shape=(count,)), properties


def gaussian_normals(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    positions = np.column_stack((rows["x"], rows["y"], rows["z"])).astype(np.float64)
    scales = np.column_stack((rows["scale_0"], rows["scale_1"], rows["scale_2"]))
    axis = np.argmin(scales, axis=1)

    quaternion = np.column_stack((rows["rot_0"], rows["rot_1"], rows["rot_2"], rows["rot_3"])).astype(np.float64)
    quaternion /= np.maximum(np.linalg.norm(quaternion, axis=1, keepdims=True), 1e-12)
    w, x, y, z = quaternion.T
    columns = np.empty((len(rows), 3, 3), dtype=np.float64)
    columns[:, :, 0] = np.column_stack((1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)))
    columns[:, :, 1] = np.column_stack((2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)))
    columns[:, :, 2] = np.column_stack((2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)))
    normals = columns[np.arange(len(rows)), :, axis]
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    opacity = 1.0 / (1.0 + np.exp(-np.clip(rows["opacity"].astype(np.float64), -30.0, 30.0)))
    center = np.average(positions, axis=0, weights=np.maximum(opacity, 1e-6))
    inward = np.einsum("ij,ij->i", normals, positions - center) < 0
    normals[inward] *= -1.0

    rgb = 0.5 + DC_COEFFICIENT * np.column_stack((rows["f_dc_0"], rows["f_dc_1"], rows["f_dc_2"]))
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float64)
    return positions, normals, rgb, opacity


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    report_path = args.report.resolve()
    if destination.exists() or report_path.exists():
        raise FileExistsError("Refusing to overwrite an existing reconstruction output")
    if not 0.0 < args.opacity < 1.0:
        raise ValueError("--opacity must be between zero and one")

    rows, properties = read_gaussians(source)
    positions, normals, rgb, opacity = gaussian_normals(rows)
    finite = np.isfinite(positions).all(axis=1) & np.isfinite(normals).all(axis=1)
    keep = finite & (opacity >= args.opacity)
    positions = positions[keep]
    normals = normals[keep]
    colors = np.column_stack((rgb[keep], np.ones(np.count_nonzero(keep))))

    samples = pymeshlab.Mesh(
        vertex_matrix=positions,
        v_normals_matrix=normals,
        v_color_matrix=colors,
    )
    meshes = pymeshlab.MeshSet()
    meshes.add_mesh(samples, "Oriented Gaussian samples")
    meshes.apply_filter(
        "generate_surface_reconstruction_screened_poisson",
        depth=args.depth,
        fulldepth=min(6, args.depth),
        samplespernode=2.0,
        pointweight=4.0,
        iters=8,
        confidence=False,
        preclean=True,
        threads=16,
    )
    meshes.apply_filter(
        "meshing_remove_connected_component_by_face_number",
        mincomponentsize=100,
        removeunref=True,
    )
    reconstructed = meshes.current_mesh()
    destination.parent.mkdir(parents=True, exist_ok=True)
    meshes.save_current_mesh(str(destination), save_vertex_color=True)

    vertices = reconstructed.vertex_matrix()
    report = {
        "method": "screened_poisson_from_gaussian_orientation",
        "source": str(source),
        "destination": str(destination),
        "source_gaussians": int(len(rows)),
        "retained_samples": int(np.count_nonzero(keep)),
        "opacity_threshold": args.opacity,
        "poisson_depth": args.depth,
        "vertices": int(reconstructed.vertex_number()),
        "faces": int(reconstructed.face_number()),
        "bounds_min": vertices.min(axis=0).tolist(),
        "bounds_max": vertices.max(axis=0).tolist(),
        "properties": properties,
        "normal_assumption": "smallest Gaussian principal axis, oriented away from weighted centre",
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

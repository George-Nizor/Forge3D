# TripoSplat mesh comparison

Local comparison of three surface-reconstruction routes using the same
262,144-Gaussian medical pod:

1. PlayCanvas SplatTransform smooth collision surface at 1 cm voxels.
2. PlayCanvas SplatTransform watertight-style voxel faces at 1 cm voxels.
3. Screened Poisson reconstruction using the smallest oriented Gaussian axis
   as each point's estimated surface normal.

The deterministic scripts are:

- `reconstruct_poisson.py` — converts the Gaussian PLY into a dense Poisson mesh.
- `build_comparison_scene.py` — imports all outputs, measures their topology,
  produces consistent Blender renders, exports GLB, and saves a review `.blend`.

Pinned experiment dependencies are SplatTransform 2.1.0 and PyMeshLab 2025.7.
They are isolated under `tooling/` and `.venv/`; neither changes Blender's
embedded Python or Forge3D's host environment.

The generated comparison outputs remain local under
`output/triposplat-mesh-comparison-v001/` and are intentionally ignored by
Git. Recreate the isolated dependencies from the lock files when repeating the
experiment; virtual environments and `node_modules` are not repository data.

**Conclusion:** none of these routes is an acceptable visual conversion of a
splat into a conventional game mesh. Poisson retains approximate volume but
produces bumpy geometry, poor topology, and no faithful texture solution.
Voxel Faces is useful only as a lightweight collision/proxy source. Preserve
the splat for rendering, or author a separate clean Blender mesh.

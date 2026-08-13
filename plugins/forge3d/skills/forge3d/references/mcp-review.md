# MCP review

## Blender MCP

Before changing a scene:

1. Confirm the Blender MCP add-on is running on `127.0.0.1:9876`.
2. Inspect scene/object structure and verify the intended working `.blend`.
3. Save a versioned working copy if the open scene is valuable or unrelated.

After each major build or repair pass:

- Inspect object names, collections, transforms, modifiers, meshes, materials, armatures, and actions relevant to the request.
- Capture the viewport from a useful three-quarter view. Add front/back/side or deformation poses when one view cannot reveal likely defects.
- Compare the visible result with the prompt and references; correct defects before export.
- Use the task runner for repeatable edits. Reserve arbitrary MCP Python execution for small, scoped gaps and save first.

Do not enable Poly Haven, Sketchfab, Rodin, Hunyuan, or other network-backed Blender MCP operations implicitly.

## Godot MCP

The review project is the repository `godot` directory and contains the pinned Godot MCP Toolkit add-on. `scripts/setup.ps1` opens it headlessly once on a fresh checkout so Godot builds its ignored script-class cache and registers the MCP project.

For deterministic validation, invoke:

```text
godot --path <repo>/godot -- --asset=<absolute.glb> --report=<absolute.json> --quit-after-report
```

The harness imports the GLB with `GLTFDocument`, computes bounds and mesh/material/rig/animation statistics, auto-frames its camera, selects an animation, writes JSON, and prints a line beginning with `FORGE3D_REVIEW_JSON=`.

For visual engine review:

1. Open the same review project with `FORGE3D_ASSET` set to the absolute GLB path, or pass `--asset=<absolute.glb>` after Godot's `--` separator.
2. Use Godot MCP to verify the editor connection, inspect the running scene, start the project, and capture a screenshot.
3. Read debugger/import errors and the emitted review JSON.
4. Return material, transform, rig, or animation defects to Blender; re-export and repeat.

Do not report Godot validation as successful based only on Blender playback or a syntactically valid GLB.

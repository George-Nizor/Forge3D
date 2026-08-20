# Workflow routing

## Choose the production route

| Request | Primary route | Required review |
|---|---|---|
| Static background or non-deforming prop where image fidelity dominates | TripoSplat visual master plus the simplest useful authored collision/interaction proxy | Blender KIRI visual review; Godot splat-renderer and proxy validation before game use |
| Hard-surface prop, modular kit, architecture, terrain, road, fence, pipe | Author a targeted Blender Python build; use a fixed Forge3D recipe only when its geometry genuinely matches | Blender MCP structure + turntable, then Godot MCP |
| Organic prop, statue, creature, concept-led object | Generate or prepare clean multi-angle references, then `forge3d make` with the best installed local model | Blender MCP silhouette/seam inspection, cleanup, then Godot MCP |
| Existing mesh cleanup, UVs, materials, LOD, collision | `forge3d process` with explicit operations | Before/after Blender MCP evidence, then Godot MCP |
| Neutral T/A-pose humanoid rig | Prepare topology/rest pose, use the default local `forge3d rig` Rigify path, then correct fitted joints or weights | Blender MCP bind and extreme poses, then Godot MCP |
| Quadruped or non-standard rig | Author or adapt the armature in Blender; use an explicit specialist backend only when its assumptions match | Blender MCP bind and extreme poses, then Godot MCP |
| Retargeted animation | `forge3d retarget` with the nearest profile or a generated bone map | Blender MCP playback/foot checks, then Godot MCP |
| Stylized/chibi/rigid-piece humanoid using a tested human clip | `forge3d humanoid-retarget` with a versioned humanoid profile and human-control review | Control and naked-proxy front/side evidence, semantic proof report, then Blender MCP playback |
| Mechanical, camera, or authored keyframe animation | `forge3d animate` plus Blender tasks | Blender MCP playback from useful angles, then Godot MCP |

Run the selected command with `--help` when its exact flags are not already known. Supply absolute paths and a concise prompt; do not generate shell strings from untrusted filenames.

The `forge3d make --recipe` generators are explicit primitives, not a
text-to-CAD system. Never map an arbitrary hard-surface prompt to the default
crate or another vaguely similar recipe. For a custom prompt, write a scoped
Blender Python build, execute it through the reviewed task bridge or Blender
MCP, and retain the script with the run.

## Reference-image guidance

- Reuse user-supplied references when they clearly express the target.
- For reconstruction, prefer an isolated object, neutral lighting, simple background, no text or watermark, and orthographic-like front/side/back views with consistent proportions.
- A single oblique view cannot establish hidden shape or semantic up/front. Record the intended orientation explicitly and reject any reconstruction that changes the reference proportions.
- Use the image-generation capability only when a reference materially improves modelling. Preserve the image prompt and source paths in the run output.
- Avoid image-to-mesh for simple forms that Blender can build accurately in less time.
- For TripoSplat, supply one complete isolated subject with a sharp silhouette,
  orthographic-like three-quarter framing, neutral diffuse lighting, no text,
  no foreground occlusion, and about 10-15% margin. Prefer real alpha; otherwise
  its BiRefNet pass removes the background. Inspect `prepared-input.webp`, which
  is the exact centered 1024x1024 black-background composite used by the model.
- TripoSplat synthesizes hidden views from one image. Treat them as plausible
  geometry, not measured multiview evidence, and review the complete orbit.

## Blender refinement loop

1. Import the generated or supplied mesh into the versioned working `.blend`.
2. Normalize units and transforms without destroying intentional pivots.
3. Inspect silhouette and hidden sides before retopology.
4. Repair normals, holes, disconnected fragments, shading, and intersections.
5. Add intentional bevels/details; then unwrap, texture, bake, and create materials.
6. Add LODs, collision, anchors, rig, or actions only when the request needs them.
7. Use Blender MCP for visual inspection after meaningful stages, not as a substitute for repeatable task scripts.

Forge3D's decimated `_LOD#` objects are Blender source/reference meshes and are
excluded from default GLB export; Godot does not interpret that suffix as a
runtime LOD group. Enable and inspect Godot's mesh LOD generation during engine
import instead. Collision helpers use `-convcolonly` or `-colonly` so the Godot
editor importer creates physics without duplicate visible meshes.

## Completion

A game-facing result is complete only when the editable `.blend`, exported `.glb`, relevant textures, preview, and Godot validation JSON all exist. Rigged work also needs deformation evidence; animation work needs playback evidence and loop/root-motion checks.

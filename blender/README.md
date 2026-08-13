# Forge3D Blender tasks

`forge3d_task.py` is the reproducible Blender side of Forge3D. It runs with
Blender 5.0's bundled Python and has no third-party Python dependencies.

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" `
  --background --factory-startup `
  --python .\blender\forge3d_task.py -- `
  procedural --recipe crate --output .\output\crate\source.blend
```

Every invocation prints exactly one machine-readable line beginning with
`FORGE3D_RESULT=`. Add `--report path.json` to persist the full report.

## Task surface

| Task | Purpose |
| --- | --- |
| `inspect` | Inventory objects, geometry, modifiers, materials, dependencies, rigs, and Blender 5 slotted Actions. |
| `validate` | Check geometry, transforms, UVs, dependencies, skin weights, rigs, and actions. |
| `normalize` | Set metric units, apply transforms, fit size, ground geometry, and set origins. |
| `repair` / `clean` | Merge close vertices, remove degenerates/loose geometry, recalculate normals, and optionally fill holes or apply modifiers. |
| `unwrap` | Smart, lightmap, cube, or cylindrical UV generation. |
| `material` / `pbr` | Build and assign a Principled PBR material from scalar values and optional texture maps. |
| `lods` | Generate guarded, source-only Decimate-based LOD copies for Blender review; default GLB export excludes them so Godot can generate runtime LODs. |
| `collision` | Generate Godot `-convcolonly` box/convex or `-colonly` reduced-mesh collision helpers. |
| `turntable` | Auto-frame and render one PNG or a lit multi-angle turntable. |
| `save` | Save a guarded canonical `.blend`. |
| `export-glb` | Export Godot-ready binary glTF with extras, UVs, skins, morphs, and optional animation. |
| `procedural` | Generate deterministic `box`, `crate`, `stairs`, `room`, `fence`, `pipe`, or `terrain` assets. |
| `rig-validate` | Audit bone structure, attachments, deform weights, influence limits, and assigned actions. |
| `animation-validate` | Audit slotted Actions, channels, keyframes, clip ranges, and optional loop seams. |
| `retarget` | Build an inspectable local-space bone mapping and optionally visually bake it to a target armature. |

Run `... -- <task> --help` for the authoritative flags.

## A typical asset pass

Tasks are deliberately composable. Each mutation writes a new `.blend`; inputs
are not replaced unless `--force` explicitly names that same path.

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
$task = ".\blender\forge3d_task.py"

& $blender --background --factory-startup --python $task -- `
  procedural --recipe crate --seed 42 --output .\work\01_generated.blend

& $blender --background --factory-startup --python $task -- `
  repair --input .\work\01_generated.blend --apply-modifiers `
  --output .\work\02_repaired.blend

& $blender --background --factory-startup --python $task -- `
  unwrap --input .\work\02_repaired.blend --method smart `
  --output .\work\03_unwrapped.blend

& $blender --background --factory-startup --python $task -- `
  material --input .\work\03_unwrapped.blend `
  --material-name CratePBR --base-color "0.18,0.32,0.55,1" `
  --roughness 0.38 --output .\work\source.blend

& $blender --background --factory-startup --python $task -- `
  turntable --input .\work\source.blend --objects "Forge3D_Crate" `
  --output .\work\preview.png

& $blender --background --factory-startup --python $task -- `
  export-glb --input .\work\source.blend --output .\work\model.glb
```

Texture flags are `--base-color-map`, `--normal-map`, `--roughness-map`,
`--metallic-map`, `--ao-map`, and `--emission-map`. Data maps are loaded as
non-colour data; the base-colour and emission maps use sRGB.

Procedural parameters can be passed as `--params` JSON or, on Windows where
native argument quoting can be awkward, as `--params-file params.json`.
Reasonable bounds guard all repetition and terrain-resolution parameters.

## JSON request bridge

Codex and the host CLI can avoid shell-quoting problems by providing a request
file:

```json
{
  "task": "procedural",
  "args": {
    "recipe": "crate",
    "seed": 42,
    "params": {
      "name": "MedicalCrate",
      "width": 1.2,
      "depth": 1.0,
      "height": 0.9
    },
    "output": "C:/absolute/output/MedicalCrate/source.blend",
    "report": "C:/absolute/output/MedicalCrate/blender-report.json"
  }
}
```

```powershell
& $blender --background --factory-startup --python $task -- `
  --request C:\absolute\request.json
```

The payload accepts `task` (or `operation`) and an `args` object. Snake-case
argument names are converted to CLI flags. `input_blend`, `output_blend`, and
`output_glb` are accepted as convenience aliases.

## Retarget contract

Bone-map JSON uses explicit source-to-target names:

```json
{
  "source_to_target": {
    "mixamorig:Hips": "root",
    "mixamorig:Spine": "spine"
  }
}
```

The base scaffold copies local rotations with transparent named constraints.
This works directly for rigs with compatible rest orientations. Rigs with
different rest poses must first be aligned or use a calibrated mapping prepared
and visually inspected in Blender. `--bake --clear-constraints` bakes visual
pose transforms and removes the temporary constraints. Root translation is
separate and requires `--copy-root-location --root-source ... --root-target ...`.

## Safety

- Existing output files are refused unless `--force` is present.
- An input file is never overwritten implicitly.
- Generated collections carry a Forge3D ownership marker. A same-named,
  artist-owned collection is not deleted or reused.
- Scene clearing occurs only for a new procedural build in an unsaved in-memory
  scene. `--input` and already-open `.blend` scenes are preserved.
- Reports contain paths and reproducibility metadata, but no credentials.
- Retarget constraints are prefixed `FORGE3D_RETARGET_` and only those
  constraints are removed by the task.

## Smoke tests

The PowerShell smoke suite runs the complete static-asset path plus a real
two-armature Blender 5 animation bake:

```powershell
powershell -ExecutionPolicy Bypass -File .\blender\tests\smoke.ps1
```

Use `-KeepArtifacts` to retain the temporary `.blend`, `.glb`, PNG, and JSON
evidence.

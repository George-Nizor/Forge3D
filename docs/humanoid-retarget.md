# Humanoid retarget proof workflow

`forge3d humanoid-retarget` productizes the approval-gated workflow for moving a tested human animation onto a stylized, chibi, rigid-piece, or pixel-rendered humanoid.

## Command

```powershell
forge3d humanoid-retarget `
  C:\absolute\target-tpose.blend `
  C:\absolute\human-control.glb `
  --profile C:\absolute\humanoid-profile.json `
  --output-dir C:\absolute\output
```

The command creates a versioned run containing:

- `source.blend`: editable target with one baked retarget action;
- `humanoid-retarget.json`: rest compatibility and semantic animation QA;
- `review/control_*.png`: untouched human-control frames from front, side, and isometric views;
- `review/target_*.png`: the target at the same sampled phases;
- rig and animation validation reports;
- `model.glb` and a static preview.

Use `--no-review` only for automation where review images are produced elsewhere.

## Why this differs from local constraint copying

The task transfers each source bone's evaluated global **rest-relative delta** onto the target bone's own rest orientation by default. This keeps target axial twist, including its head/visor forward convention. A profile may list anatomically aligned body or limb bones under `absolute_orientation_bones` when they must reproduce the human control's exact global joint angles. Child bone heads remain attached to their target parent joints. Optional translation scales transfer controlled pelvis bob without copying incompatible source proportions.

The source animation is imported at `source_fps` before its `source_frames` are sampled. Forge3D changes to `output_fps` only after the source motion is captured, avoiding Blender's import-time action rescaling trap.

## Profile contract

Start from [`blender/profiles/segmented-humanoid-walk.example.json`](../blender/profiles/segmented-humanoid-walk.example.json). Required fields are:

- `schema`: `forge3d.humanoid-retarget-profile.v1`;
- `source_armature` and `target_armature`;
- `source_to_target`: one-to-one bone map.

Important optional fields:

- `source_frames`, or `sample_count` plus `exclude_loop_endpoint`;
- `source_action`, required when an imported library contains multiple actions;
- `source_fps` and `output_fps`;
- `source_to_target_yaw_degrees`;
- `translation_scales`, normally a small pelvis scale;
- `absolute_orientation_bones` for source bones whose global rest axes were proven compatible; omit twist-sensitive bones such as the head unless their rendered forward direction is also verified;
- `chains` and `leg_chains` for joint comparison and hip > knee > ankle checks;
- `forward_axis`;
- `facing.origin_object`, `facing.front_object`, `facing.axis`, and `facing.minimum_dot` to measure the deformed helmet/face rather than object rest coordinates;
- `attachments[]` entries with `object_pattern` and `bone` for backpacks or permanent equipment;
- rest, pose-direction, chain-gap, and joint-angle tolerances;
- `review_resolution`.

Example facing and attachment additions:

```json
{
  "facing": {
    "origin_object": "HelmetShell",
    "front_object": "VisorGlass",
    "axis": "-Y",
    "minimum_dot": 0.75
  },
  "attachments": [
    {"object_pattern": "Backpack*", "bone": "upper_chest"}
  ]
}
```

## Required modeling gate

The target must begin in a proper anatomical T- or A-pose. Its visible shoulder, elbow, wrist, hip, knee, ankle, ball, and toe pivots must be placed on the matching target bones before retargeting. For segmented characters, bind each rigid piece to exactly one bone. Keep the boot shaft on the shin, hindfoot on the foot bone, and forefoot on a connected toe bone; overlap costume geometry around the ankle and ball so rigid pieces do not open visually.

First approve the untouched human-control review, then the naked target-proportion proxy, then the finished shell. Do not fan one action into eight directions until the single-direction target passes played-motion review.

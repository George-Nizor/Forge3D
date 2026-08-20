# Stylized humanoid retarget

Use this workflow for chibi, segmented, rigid-piece, pixel-rendered, or heavily proportion-shifted humanoids that should inherit a conventional human animation.

## Approval-gated route

1. Render the untouched source human animation from front and side. Reject the source if contacts, alternating limbs, knee direction, or loop behavior are already wrong.
2. Author the target skeleton in a proper anatomical T- or A-pose. Place shoulder, elbow, wrist, hip, knee, ankle, ball, and toe pivots before binding costume geometry.
3. Animate a plain target-proportion proxy first. Require human joint ordering and source/target joint-angle agreement before attaching the final shell.
4. For rigid-piece characters, use one-bone weights. Keep the boot shaft on the shin, hindfoot on the foot, and forefoot on a connected toe bone. Overlap costume geometry around the ankle and ball.
5. Copy and edit the bundled `blender/profiles/segmented-humanoid-walk.example.json` profile. Record source-native frames/FPS, output FPS, one-to-one bone map, pelvis translation scale, chains, forward axis, facing markers, and permanent equipment attachments.
6. Run:

   ```text
   forge3d humanoid-retarget <target-tpose.blend> <human-control.glb> --profile <profile.json> --output-dir <new-folder>
   ```

7. Inspect both `review/control_*.png` and `review/target_*.png`, then play the baked action through Blender MCP. Structural success is not visual approval.
8. Correct the target model/profile and rerun in a new versioned folder. Do not manually repair eight directional copies.
9. Only after one direction passes, keep the camera fixed and rotate the character root through exact 45-degree steps for eight-direction rendering.

## What the command guarantees

The Blender task imports the source at `source_fps`, selects `source_action`, samples the declared source frames, and only then switches to `output_fps`. It applies each source bone's evaluated global rest-relative delta to the target bone's own rest orientation by default. A profile may opt proven-compatible body or limb bones into `absolute_orientation_bones` to reproduce exact human-control joint angles while leaving twist-sensitive bones such as the head rest-relative. Child heads remain attached to target parent joints.

The task fails on:

- incompatible source/target rest directions;
- mapped pose-direction divergence;
- disconnected target chains;
- source/target joint-angle drift beyond the profile tolerance;
- hip/knee/ankle ordering failures in declared leg chains;
- evaluated facing-marker disagreement after deformation;
- missing or incorrectly bound permanent attachments.

The versioned run includes the editable Blend, GLB, semantic report, rig and animation reports, control/target review sequences, and static preview.

## Profile notes

- Use the source clip's native timing. For a loop with a duplicated endpoint, omit the duplicate from `source_frames`.
- Select `source_action` explicitly when the imported file is an animation library.
- Use `source_to_target_yaw_degrees` only to reconcile declared forward conventions.
- Put a bone in `absolute_orientation_bones` only after its source and target global rest axes pass the profile's compatibility threshold. Keep the head rest-relative unless evaluated facing markers prove its twist.
- Keep `translation_scales` sparse; normally transfer only restrained pelvis bob.
- Define `facing.origin_object` as a central head/helmet shell and `facing.front_object` as the face/visor marker. Rest-pose object locations are insufficient because a bone can twist the rendered front backwards.
- Define backpacks, tanks, capes, or other permanent equipment under `attachments` with an object glob and required target bone.

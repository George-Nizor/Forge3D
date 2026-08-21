# Forge3D brand identity

## Topology Loop

Forge3D's primary mark is the **Topology Loop**: an asymmetric open loop whose wireframe control
cage resolves into a finished curved surface. It represents Forge3D's actual work—moving from an
instruction and editable topology to a reviewable spatial result—without using a literal cube,
anvil, hammer, flame, or abbreviated `F3` badge.

The mark must retain:

- The open negative space through the center.
- A visible transition from connected vertices and triangular edges into a solid surface.
- An oblique, sculptural perspective rather than a flat geometric ring.
- Copper/orange material over graphite or transparent backgrounds.
- A simple silhouette that remains legible at Windows app-icon size.

Canonical assets are `desktop/assets/icon.svg`, its deterministic packaged PNG counterpart, and
Instrumenta's `brand/artwork/forge3d-app-art.svg`. The renderer contains the same vector geometry
inline so it is available during the first frame without a network or asset request.

## Colour and type

The desktop palette is graphite black, copper-orange, warm bone, restrained neutral lines, and sparse
green for successful local-toolchain state. Red is reserved for failures and destructive actions.

Space Grotesk 500/600 is the Forge3D wordmark and display face. The exact Fontsource 5.3.0 package is
bundled under the SIL Open Font License 1.1. Controls and supporting copy use Segoe UI Variable with
Segoe UI and system fallbacks, matching Instrumenta and its Windows desktop products.

## Interface expression

Forge3D uses the **Spatial Canvas** composition:

- A top command ribbon contains identity, the prompt, attachments, advanced controls, and Forge.
- The central region belongs to the result preview; it is not divided into permanent dashboard cards.
- Run history and detailed steps/artifacts/validation/logs are temporary edge drawers.
- A bottom production rail exposes Plan, Build, Check, and Output continuity plus artifact thumbnails.
- External dependencies collapse into one quiet local-toolchain status. Individual Codex, Blender,
  Godot, and WSL pills are not part of the interface.
- Corners are mostly square, separators are fine, and glow is limited to operational focus and status.

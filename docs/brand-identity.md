# Forge3D brand identity

## Topology Loop — approved Logo A

Forge3D's primary mark is the approved **Topology Loop** render selected during the 0.2.2 identity
review. It is a copper-orange continuous loop whose left side transitions visibly from connected
vertices and triangular topology into a smooth finished surface. It represents the path from an
editable 3D structure to a finished spatial result.

The generated Logo A render is the sole geometry reference. Do not redraw or simplify it. The mark
must retain:

- The exact oblique loop silhouette and large open negative space.
- The irregular node-and-triangle cage on the left.
- The gradual mesh-to-surface transition and translucent intermediate faces.
- The sculpted copper material, highlights, and dark inner surface.
- No cube, anvil, hammer, flame, letter `F`, number `3`, or substitute outline treatment.

Canonical assets are `desktop/assets/forge3d-mark.png`, the square
`desktop/assets/icon.png`, the bundled renderer copy at
`desktop/src/renderer/forge3d-mark.png`, and Instrumenta's
`brand/artwork/forge3d-app-art.png`. The SVG files are compatibility wrappers around those PNGs;
they are not alternate drawings.

## Colour and type

The desktop palette is cool graphite, blue-black viewport space, restrained neutral separators, and
copper-orange focus. Green is reserved for ready/success states and red for failures or destructive
actions.

Space Grotesk 500/600 is the Forge3D wordmark and display face. The exact Fontsource 5.3.0 package is
bundled under the SIL Open Font License 1.1. Controls use Segoe UI Variable with Segoe UI and system
fallbacks, matching Instrumenta and its other Windows products.

## Interface expression — approved UI B

Forge3D follows the **viewport-first workstation** composition captured in
the approved alignment reference
(`Instrumenta/docs/design-references/forge3d-ui-claude-alignment-reference.png`):

- One application bar holding the Logo A wordmark, a wide prompt omnibox, Attach, run settings,
  and a single orange Run action. On Windows the native caption is hidden and the system window
  controls are drawn over the reserved inset at the right of that bar.
- A full-bleed viewport underneath it. With no output it shows a studio backdrop with a receding
  ground grid and the mark as a watermark.
- A floating viewport tool rail on the left: orbit, pan, frame, ground grid, the three shading
  modes, capture, and fullscreen.
- Floating dark panels on the right for the run library and the Steps / Files / Checks / Logs
  inspector. Both collapse to vertical edge tabs so the viewport can run edge to edge.
- A production dock across the bottom: the Plan, Build, Check, Output pipeline derived from real
  run state, and a filmstrip of the run's outputs.
- One hairline status bar for toolchain, Codex, Blender, Godot, and WSL readiness.
- Rounded but restrained corners, hairline borders, compact uppercase display labels, and copper
  orange reserved for the primary action, the active tool, and the running stage. No dashboard
  cards, numbered stages, marketing subtitle, or explanatory copy beneath every control.

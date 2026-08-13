# Forge3D

Prompt-first 3D asset tooling for Codex, Blender 5, and Godot 4. Forge3D is a
personal workflow kit rather than a standalone generative application: ask
Codex for an asset, and it selects a practical production route, leaves an
editable Blender source where appropriate, and validates game-facing output in
Godot.

![Generated controller reference](docs/images/controller-reference.webp)

## What works today

| Route | Best for | Output | Current state |
|---|---|---|---|
| **TripoSplat** | Static props and background objects where image fidelity matters most | Gaussian `.ply` + `.splat`, optional KIRI `.blend` | Local RTX inference works; Blender viewing works; Godot rendering works through pinned GDGS 3.3.0 |
| **Authored Blender modelling** | Hard-surface props, architecture, editable parts, conventional game assets | Editable `.blend` + validated `.glb` | Procedural Blender Python builds, materials, UVs, collision helpers, previews, and Godot validation work |
| **Rigging** | Neutral humanoid meshes | Rigify armature + skinned `.blend`/GLB | Local Rigify path exists; every result still needs deformation review |
| **Animation and retargeting** | Mechanical animation and transferring clips between compatible rigs | Baked Blender actions + GLB | Task and retarget pipelines exist; foot contact, bone maps, loops, and root motion need per-asset review |
| **Cloud fallback** | A conventional image-derived mesh when local routes are unsuitable | Provider mesh followed by Blender cleanup | Tripo pay-per-use integration exists, but every upload requires explicit per-job approval |

This is not a universal “prompt to perfect mesh” system. It deliberately uses
two different primary representations:

- A **Gaussian splat** preserves the look of one reference extremely well, but
  it is not polygon geometry and cannot be conventionally rigged or edited.
- An **authored Blender model** is clean, editable, animatable geometry, but its
  final quality depends on the modelling script and refinement rather than
  automatic photoreal reconstruction.

## Same asset, both routes

The controller below demonstrates the distinction. Both began from the same
generated concept above.

### Image-faithful TripoSplat, running in Godot

![Controller TripoSplat rendered in Godot](docs/images/controller-splat-godot.webp)

The local TripoSplat worker produced 262,144 Gaussians. Godot imports the
`.splat` through the vendored MIT-licensed GDGS 3.3.0 add-on and renders it with
the Forward+ compute backend. Forge3D adds a simple authored collision proxy;
the splat itself remains visual data.

### Clean authored Blender model

![Authored polygon controller](docs/images/controller-authored.webp)

The authored version is a conventional 22,060-triangle asset made from 58
separate editable objects, with UVs, PBR materials, and three convex collision
helpers. It is less photographic than the splat, but can be edited, animated,
exported to GLB, and used by ordinary engine tooling.

## Does the Blender modeller use MCP?

Yes, but MCP is the **review and supervised-editing layer**, not the main
geometry algorithm.

For a custom hard-surface request, Codex normally:

1. Writes a scoped Blender Python build under `blender/`.
2. Runs Blender headlessly to create geometry, modifiers, materials, UVs,
   collision helpers, renders, the editable `.blend`, and a GLB export.
3. Opens the real `.blend` through Blender MCP on `127.0.0.1:9876`.
4. Inspects scene structure and useful viewport angles, then performs small,
   supervised corrections when necessary.
5. Runs validation and uses Godot MCP to inspect the imported result in-engine.

This split is intentional. Deterministic scripts make builds repeatable and
reviewable; Blender MCP supplies visual judgment and interactive access. MCP
can execute scoped Blender Python, but using arbitrary MCP calls as the only
source of an asset would make the result difficult to reproduce.

Fixed CLI recipes such as `crate`, `room`, or `terrain` are useful primitives,
not a text-to-CAD model. Arbitrary props receive their own targeted build script
instead of being forced into the nearest recipe.

## Installation

The current setup is Windows-first and expects:

- Blender 5.x (standalone or Steam; currently tested with Steam Blender 5.2 LTS)
- Godot 4.6
- Python 3.11+
- Node.js 22+
- `uv`
- WSL2 Ubuntu with NVIDIA CUDA access for local TripoSplat inference
- An NVIDIA GPU with at least 8 GB VRAM for TripoSplat; this project was tested
  on an RTX 4080 SUPER with 16 GB

From PowerShell:

```powershell
.\scripts\setup.ps1 -InstallModels -InstallPersonalPlugin
forge3d doctor
```

The setup script installs the editable CLI, the pinned Blender MCP add-on and
server, initializes the Godot review project, optionally installs TripoSplat in
an isolated WSL environment, and installs the personal Codex plugin. Restart
Codex after setup so it reloads `.codex/config.toml` and the plugin.

The repository currently contains machine-specific paths for George's local
Blender, Godot, `uv`, Codex plugin, and MCP setup. Override the executable paths
with `BLENDER_EXECUTABLE` and `GODOT_EXECUTABLE`, or adapt the PowerShell setup
scripts before using another Windows account. Portable setup discovery is the
largest remaining packaging task.

## Usage

The intended interface is a natural-language request in Codex:

> Use Forge3D to create a game-ready industrial generator. Keep an editable
> Blender source, add collision and LODs, inspect it through Blender MCP, and
> validate the GLB in Godot.

> Use Forge3D to turn this isolated prop image into a TripoSplat background
> asset, add a box collider, and prove it renders correctly in Godot.

The thin CLI can also be called directly:

```powershell
forge3d doctor
forge3d models list
forge3d models status

# Local static visual reconstruction; the output folder must be new.
forge3d models run triposplat C:\path\to\reference.png `
  --output-dir C:\path\to\output\prop-splat-v001 `
  --gaussians 262144

# Fixed procedural primitives.
forge3d make "equipment case" --recipe equipment-case `
  --output-dir C:\path\to\output\case-v001

forge3d process --help
forge3d rig --help
forge3d retarget --help
forge3d validate --help
```

Start Blender with its local MCP bridge when an interactive review is needed:

```powershell
.\scripts\start-blender-mcp.ps1

# Or open a particular working file:
.\scripts\start-blender-mcp.ps1 -BlendFile C:\path\to\asset-v001.blend

# If Blender is not discoverable automatically:
.\scripts\start-blender-mcp.ps1 -Blender C:\path\to\blender.exe
```

Every meaningful output is versioned. Generated runs live under `output/`,
which is intentionally ignored by Git.

## TripoSplat guidance

TripoSplat accepts one image and invents unseen views. Give it one complete,
isolated subject with:

- a sharp silhouette and roughly 10–15% margin;
- orthographic-like three-quarter framing;
- neutral diffuse lighting;
- no text, watermark, foreground occlusion, or crop;
- a clean alpha channel where possible; and
- at least 1024 pixels on the shortest source dimension.

Always inspect `prepared-input.webp`, then orbit the complete result. The side
shown in the input can be extremely faithful; the unseen rear is plausible
synthesis rather than measured geometry.

The accepted local baseline uses 20 steps, guidance 3.0, shift 3.0, alpha
erosion radius 1, and 262,144 Gaussians. In Godot, GDGS imports `.splat`, `.ply`,
`.compressed.ply`, and `.sog`; Forge3D currently validates the controller path
with desktop Forward+ compute rendering.

## Representation and model policy

- `.blend` is the editable source of truth for conventional assets.
- GLB is the game-facing polygon export.
- PLY/SPLAT is the visual master for Gaussian assets.
- TripoSplat never masquerades as a polygon mesh.
- Converting splats through Poisson or voxel reconstruction was tested and
  rejected as a visual-asset route: it produced bumpy geometry, poor topology,
  and no faithful texture solution. Those methods remain useful only for rough
  collision/proxy generation.
- TripoSR is unsupported because the tested result had melted edges, repeated
  surface striations, incorrect proportions, and severe non-manifold geometry.
- SPAR3D is the preferred optional local textured image-to-mesh candidate only
  after its current Stability Community License, gated access, registration,
  revenue condition, attribution, and AUP requirements are confirmed.
- TripoSG and PartCrafter are restricted to explicit evaluation because their
  published inference paths include BRIA RMBG-1.4 non-commercial terms.
- Cloud providers never receive an input without explicit approval for that
  exact job.

See `forge3d models info <name>` for recorded capabilities and license links.

## Repository layout

```text
blender/       Repeatable Blender tasks and authored asset build scripts
docs/images/   Compact, real showcase images used by this README
experiments/   Technology-grouped demonstrations and evaluated prototypes
godot/         GLB review harness, Godot MCP toolkit, and GDGS splat renderer
plugins/       Personal Codex plugin and Forge3D skill
references/    Selected modelling/reconstruction references and prompts
scripts/       Setup, MCP launchers, cloud adapter, and WSL inference worker
src/forge3d/   Dependency-light host CLI
tests/         Python integration and policy tests
vendor/        Small pinned third-party source required by setup
```

The production tool is deliberately separated from demonstrations:

- `src/forge3d/`, `blender/`, and `godot/` are the working asset pipeline.
- `plugins/forge3d/` exposes that pipeline to Codex and ChatGPT.
- `experiments/threejs/` contains procedural web-3D demonstrations.
- `experiments/triposplat/` contains splat viewing and conversion research.
- `output/` is ignored working data and is never part of a commit.

No daemon, database, web UI, queue, or generic workflow framework is required.

## Validation

Before handoff:

```powershell
forge3d doctor --json
uv run --with pytest pytest -q
.\blender\tests\smoke.ps1
```

The Godot harness is also run headlessly against an exported GLB, followed by
a Godot MCP runtime screenshot/debugger check for game-facing work. Splat assets
must additionally be inspected through the GDGS scene with their collision
proxy enabled.

## Known limitations

- Installation paths are not yet portable across Windows accounts.
- The clean modeller is procedural authoring assisted by an LLM, not a trained
  universal text-to-mesh model; organic characters still need an appropriate
  source mesh or explicitly selected reconstruction backend.
- Rigging and retargeting are implemented but require more production examples
  and asset-specific deformation correction before they should be considered
  push-button workflows.
- Gaussian splats are best treated as static visual props. They do not provide
  normal polygon editing, skeletal deformation, or ordinary GLB export.
- The bundled controller `.splat` is an 8 MB demonstration asset. Larger
  generated assets belong in ignored `output/` storage or Git LFS, not normal
  repository history.

## License

Forge3D is MIT licensed. Bundled integrations retain their own notices; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

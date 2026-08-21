![Forge3D banner](docs/images/forge3d-banner.png)

# Forge3D

Forge3D turns a prompt into a versioned local 3D run. The Windows desktop drives the user's Codex App
Server, calls the Forge3D skill, keeps the transcript, and previews the result. Blender, Godot, WSL,
CUDA, and large models remain separate installations.

Current source and desktop version: **0.2.2**.

## Start here

The ordinary launch path is the Forge3D card in Instrumenta. Instrumenta installs the managed bundle,
checks its hash, keeps the previous version for rollback, and opens `Forge3D.exe`.

For a source checkout:

```powershell
.\scripts\setup.ps1 -InstallModels -InstallPersonalPlugin
forge3d doctor --json
cd desktop
npm install
npm start
```

Restart Codex after installing or repairing the personal plugin so its skill catalogue is refreshed.

## Pick the right asset route

| Route | Good fit | Main output |
| --- | --- | --- |
| Authored Blender | Editable props, buildings, rigs, animation, collision, LODs | `.blend` source and a validated `.glb` |
| TripoSplat | Static props where the reference image matters more than mesh editing | Gaussian `.splat` or `.ply` data with a collision proxy |

The Blender route makes conventional geometry. The TripoSplat route makes a Gaussian visual asset
whose unseen surfaces are inferred from one image. A splat is not a polygon mesh. Renaming the file
will not persuade Blender otherwise.

## The desktop

The interface is a viewport-first workstation:

- The top bar holds the prompt, attachments, run settings, and Run.
- A full-bleed viewport carries the current image, model, animation, or splat.
- The left rail contains orbit, pan, framing, shading, capture, and fullscreen tools.
- Run history and the Steps / Files / Checks / Logs inspector float on the right and can collapse.
- The bottom dock shows Plan, Build, Check, Output, and a filmstrip of artifacts.
- One thin status bar reports Codex and external-tool readiness.

One job runs at a time. You can steer or cancel it while the streamed transcript and workflow state
are written to disk. Interrupted jobs remain in the library and keep their Codex thread IDs for an
explicit continuation.

Forge3D automatically accepts contained local commands, run-file edits, and local Blender or Godot
tool calls for the active session. Network requests, writes outside the run directory, and remote
provider actions still ask. Cloud access starts off and must be approved for each job.

## Preview support

The desktop routes artifacts by type:

- PNG, JPEG, WebP, and GIF render directly.
- Ordered image folders play as 12 fps sequences.
- GLB and glTF models use bundled Three.js controls, animation playback, and automatic framing.
- PLY, SPLAT, and SOG assets use bundled SparkJS with the tested TripoSplat coordinate conversion.
- Validation JSON, text files, and logs render in the inspector.
- An unsupported file still shows metadata and keeps its Reveal and Open actions.

A splat preview is interactive: orbit, pan, and inspect the coloured Gaussian result inside Forge3D.
This is the useful bit. A screenshot alone rather defeats the point of having spatial data.

## Runs and files

Every job gets a self-contained folder:

```text
%USERPROFILE%\Documents\Forge3D\runs\<timestamp>-<slug>-<id>
```

Attachments are copied into that folder before Codex starts. `run.json` records the prompt, route,
settings, steps, relative artifacts, validation, timestamps, transcript, and Codex thread/turn IDs.
Schema v1 remains readable; new runs use schema v2.

Generated review assets, logs, configuration, and caches live under:

```text
%LOCALAPPDATA%\Instrumenta\Forge3D
```

The file menu exposes run-scoped actions: reveal, open, open in Blender, review in Godot, copy path,
duplicate, archive, and Recycle Bin trash. Paths are checked against the run root before use.

## Prompt examples

An editable prop:

> Build an industrial generator in Blender. Keep the `.blend`, add collision and two LODs, export a
> GLB, then validate the import in Godot.

An image-faithful static prop:

> Turn this isolated prop image into a TripoSplat asset. Add a simple collision proxy and verify the
> splat in the interactive preview.

A clean source image has one complete subject, a little margin, diffuse light, and no foreground
occlusion. Check `prepared-input.webp` before blaming the model for a crop it was given.

## Command line

The desktop is the normal interface. The CLI is useful for diagnostics and repeatable jobs:

```powershell
forge3d doctor
forge3d models list
forge3d models status
forge3d process --help
forge3d rig --help
forge3d animate --help
forge3d retarget --help
forge3d humanoid-retarget --help
forge3d validate --help
```

A local TripoSplat run looks like this:

```powershell
forge3d models run triposplat C:\path\to\reference.png `
  --output-dir C:\path\to\output\prop-splat-v001 `
  --gaussians 262144
```

Forge3D never replaces an existing asset output. Use a new versioned folder.

## External tools

The tested Windows x64 setup uses Blender 5.x, Godot 4.6, Python 3.11 or newer, Node.js 22 or newer,
`uv`, and the installed Codex CLI. TripoSplat also needs WSL2 Ubuntu, NVIDIA CUDA access, and an NVIDIA
GPU with at least 8 GB of VRAM.

Launch Blender with the local bridge when an interactive scene review is needed:

```powershell
.\scripts\start-blender-mcp.ps1
.\scripts\start-blender-mcp.ps1 -BlendFile C:\path\to\asset-v001.blend
```

## Model and upload policy

TripoSplat is the accepted local route for image-faithful static visuals. Other providers keep their
recorded licence and capability limits in `forge3d models info <name>` and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Model weights are not committed or bundled.

No cloud provider receives a file unless the job has cloud consent and the remote action is approved.
Provider charges remain visible.

## Repository map

```text
blender/       reviewed Blender tasks and asset builders
desktop/       Electron client, previews, tests, and Windows package
docs/          architecture, schema, brand, release, and workflow notes
godot/         GLB and Gaussian review project
plugins/       Forge3D Codex plugin and skill
scripts/       setup, packaging, launchers, and WSL workers
src/forge3d/   dependency-light host CLI
tests/         Python integration and policy tests
```

Useful reading:

- [Desktop process, security, approvals, and preview routing](docs/desktop-architecture.md)
- [Run schema and crash recovery](docs/run-schema-v2.md)
- [Humanoid retarget workflow](docs/humanoid-retarget.md)
- [Windows packaging and troubleshooting](docs/releasing.md)
- [Brand identity](docs/brand-identity.md)
- [Publication audit](docs/publication-audit.md)

## Verify a change

```powershell
uv run --with pytest pytest -q
npm --prefix desktop test
npm --prefix desktop run build
.\blender\tests\smoke.ps1
```

Blender and Godot headless checks need those applications installed. Game-facing assets should finish
with an engine import/runtime review.

Forge3D is MIT licensed. Bundled integrations keep their own notices.

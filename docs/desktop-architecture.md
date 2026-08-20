# Forge3D desktop architecture

## Scope

Forge3D 0.2.0 adds a local Electron rich client around the existing prompt-first toolkit. It is not
a hosted web application, daemon, database, arbitrary file manager, or replacement for Blender,
Godot, WSL/CUDA, or large model installations. It runs one Codex job at a time and stores each job as
a self-contained directory under `%USERPROFILE%\Documents\Forge3D\runs`.

## Process and security boundary

The renderer has `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`, a restrictive
Content Security Policy, denied window creation/navigation, and deny-by-default Electron permissions.
It receives only named operations from the preload bridge. The main process validates the renderer
origin, run ID, relative artifact path, and final contained filesystem path before every operation.

Artifacts are served through `forge3d-artifact:`. The protocol resolves a run ID and relative path
through the run store, rejects traversal and symbolic links, and returns only a regular file. The UI
does not receive a generic filesystem API. Reveal, default open, Blender open, Godot review, copy
path, duplicate, archive, and Recycle Bin actions are individually named. No arbitrary move action is
available.

Attachments are copied into `attachments/` before a job starts. The agent works in the run directory
with workspace-write access limited to that directory. Network access is disabled unless the user
checks the per-job cloud approval and confirms it. Provider charges, uploads, commands, or file
changes can still trigger App Server approvals.

## Codex App Server lifecycle

Forge3D starts the user's installed Codex CLI as `codex app-server` with its default stdio transport.
The transport is newline-delimited JSON and follows this lifecycle:

1. Send `initialize` with Forge3D client metadata and wait for the response.
2. Send the `initialized` notification.
3. Call `skills/list` for the runs root and locate the enabled `forge3d` skill.
4. Start or resume a persistent thread.
5. Start a turn with `$forge3d`, the explicit skill item, copied local images, the run directory,
   `workspaceWrite`, contained writable roots, and the selected model/effort.
6. Stream turn, item, agent-message, command-output, and error notifications into run history.
7. Route server-initiated command/file approval requests to the modal and return the user's exact
   decision.
8. Use `turn/steer` for new instructions and `turn/interrupt` for cancellation.
9. On `turn/completed`, persist the final status and refresh contained artifacts.

A process crash marks launching/running/cancelling jobs interrupted on the next launch. Their history
and Codex IDs remain browsable and can be continued by resuming the stored thread.

## Plugin version and repair

`skills/list` is authoritative for discovery. Forge3D reads the discovered plugin manifest and
compares it with the bundled 0.2.0 plugin. Missing, invalid, or mismatched registrations show a repair
action. Repair is explicit: the current personal plugin directory is moved to a timestamped backup,
the bundled plugin is copied, machine-specific Blender/Godot MCP configuration is generated, the
personal marketplace entry is updated, and `codex plugin add forge3d@personal` is invoked. Failure
restores the backup.

## External tools and local state

The bundle contains the Electron UI, a standalone `forge3d.exe` CLI, deterministic Blender tasks,
the Forge3D Codex plugin, and a Godot review template. Blender, Godot, WSL, CUDA, local AI models, and
Codex authentication/configuration remain external and are detected.

Generated review assets, plugin configuration, logs, and caches live under
`%LOCALAPPDATA%\Instrumenta\Forge3D`. The Godot template is synchronized there per Forge3D version.
There are no absolute references to any former checkout location.

## Preview routing

- PNG/JPEG/WebP and GIF use native image playback.
- Directories containing ordered raster frames expose a 12 fps image-sequence preview.
- GLB/glTF uses bundled Three.js, OrbitControls, animation mixers, and bounding-sphere framing.
- PLY/SPLAT/SOG uses bundled SparkJS and the proven TripoSplat coordinate conversion.
- Validation JSON and text/log artifacts render as contained text.
- Unsupported formats display metadata and retain reveal/open actions.
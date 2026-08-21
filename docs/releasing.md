# Forge3D release packaging and troubleshooting

## Build a Windows release

```powershell
.\scripts\build_desktop.ps1
```

The script builds the dependency-light Python CLI into `desktop\runtime\forge3d.exe`, installs the
locked npm tree, runs desktop tests, compiles the renderer, and packages the Electron application as
`desktop\dist-package\Forge3D-0.2.1-windows-x64.zip`. It then writes
`instrumenta-release.json` with the exact ZIP byte size, SHA-256, `Forge3D.exe` entry point, managed
install strategy, and minimum Instrumenta 0.8.0.

GitHub Releases are canonical. Do not commit `node_modules`, `.venv`, `.tmp`, runtime executables,
Electron output, user runs, models, generated Godot imports, logs, or caches.

## Release audit

1. Run `uv run --with pytest pytest -q` and `npm test` in `desktop`.
2. Run the Blender and Godot headless smoke tests when those external tools are available.
3. Build the release and run `desktop\runtime\forge3d.exe --version`.
4. Validate `instrumenta-release.json` and the ZIP through Instrumenta's release verifier.
5. Extract into an empty directory and confirm the declared `Forge3D.exe` exists.
6. Launch without a source checkout, verify Codex authentication reuse and Forge3D skill discovery,
   run one local prompt, inspect an artifact, restart, and confirm history recovery.
7. Test a deliberately corrupt bundle and failed first launch to prove rejection and rollback.
8. Complete secret, generated-file, dependency-license, and redistribution audits before public
   publication. Preserve every third-party notice.

## Troubleshooting

- **Codex is missing:** repair or install the Codex app; Forge3D searches PATH and the Codex app bin
  directory and does not embed credentials.
- **Plugin mismatch:** use the explicit Repair action, restart Codex if another Codex client is open,
  and refresh tools.
- **Blender or Godot missing:** install them separately or set `BLENDER_EXECUTABLE` /
  `GODOT_EXECUTABLE`; large external tools are intentionally not bundled.
- **WSL/CUDA unavailable:** local AI reconstruction routes remain unavailable, but authored Blender
  and file-processing workflows can still run.
- **Preview fails:** use Reveal, validate the artifact, and inspect the run transcript. Unsupported
  formats remain accessible through Open.
- **Interrupted job:** select it in history and Continue; Forge3D resumes its stored Codex thread.
- **Cloud action blocked:** the cloud checkbox is per job. Start a new approved job and still approve
  the provider/upload request when shown.
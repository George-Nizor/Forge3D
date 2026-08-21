# Forge3D publication audit

Audit updated: 2026-08-21.

This audit established the public 0.2.0 source and release baseline. The current source and desktop
version is 0.2.2. A future public 0.2.2 artifact needs its own clean build and release verification;
the 0.2.0 hash below does not magically bless newer bytes.

## Public source

- The repository is public at <https://github.com/George-Nizor/Forge3D>.
- The former repository name was replaced by Forge3D in tracked branding and runtime paths.
- The original public `v0.2.0` tag points to release commit `4328a28`.
- Secret scans found no private-key, GitHub token, OpenAI key, AWS key, or Hugging Face token
  signatures in the audited source set.
- `.venv`, `node_modules`, renderer builds, desktop packages, temporary files, model folders, logs,
  caches, user output, and run history are excluded.
- The project-owned demonstration assets were approved for public redistribution by the sole owner.

## Dependencies and model boundaries

Forge3D's own code is MIT. Blender MCP, Godot MCP Toolkit, and GDGS keep their upstream licences and
attribution. Electron, Three.js, SparkJS, fflate, Vite, and Electron Builder are MIT. The standalone
CLI carries the PyInstaller bootloader notice.

Large model weights are neither committed nor bundled. Local and cloud providers keep the capability,
licence, access, and upload restrictions recorded in `THIRD_PARTY_NOTICES.md`.

Network access is off for each new job. Contained local commands and local Blender/Godot tool calls
can be accepted automatically; remote intent stays visible.

## Published 0.2.0 evidence

Release: <https://github.com/George-Nizor/Forge3D/releases/tag/v0.2.0>

```text
Artifact  Forge3D-0.2.0-windows-x64.zip
Bytes     175,818,934
SHA-256   47ce95e92c3337be8f7eb9f8c281838768577bbf342ce0894c67b6920e6d77d6
```

The 0.2.0 audit covered the Python suite, Electron security tests, Vite production build, npm audit,
standalone CLI smoke, downloaded release manifest, ZIP digest, Instrumenta managed installation, and
an isolated packaged launch.

Those results are historical release evidence. Run the current 0.2.2 suites and build script before
publishing another tag.

## Current release checklist

For 0.2.2 or later:

1. Run the Python, desktop, Blender, and Godot checks that are available on the release machine.
2. Build with `scripts/build_desktop.ps1`.
3. Verify `instrumenta-release.json` against the ZIP.
4. Install through Instrumenta from a clean release download.
5. Run a local Codex prompt and inspect each declared artifact type.
6. Restart Forge3D and recover the run history.
7. Exercise Blender/Godot open actions, splat orbit, cancellation, archive, trash, and rollback.
8. Repeat the secret, generated-file, dependency, and redistribution audit.

A packaged launch proves that the executable opens. It does not prove Blender, Godot, CUDA, models, or
an actual workflow on that machine.

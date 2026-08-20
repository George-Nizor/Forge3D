# Forge3D publication audit

Audit updated: 2026-08-21. Target: public source repository and Windows x64 release 0.2.0.

## Public source result

- The source repository is public at <https://github.com/George-Nizor/Forge3D>.
- The former `Dev-Tools` repository was renamed to `Forge3D`; public `main` and tag `v0.2.0` point to
  release commit `4328a28`.
- Secret signature scans across tracked and unignored files found no private-key, GitHub token,
  OpenAI key, AWS key, or Hugging Face token signatures and no suspect secret filenames.
- Generated directories excluded: `.venv`, `node_modules`, renderer `dist`, `dist-package`, desktop
  runtime executable, `.tmp`, model directories, logs, caches, and user `output`/runs.
- The publishable file set contains no stale old-repository branding or absolute former-checkout paths.
- Three tracked demo assets exceed 1 MiB. On 2026-08-20, the sole project owner confirmed ownership
  and authorized their public redistribution with Forge3D.

## Dependency and redistribution review

- User-owned Forge3D code is MIT.
- Blender MCP, Godot MCP Toolkit, and GDGS retain their checked-in upstream licenses and attribution.
- Electron, Three.js, SparkJS, fflate, Vite, and Electron Builder are MIT.
- The standalone CLI uses the PyInstaller bootloader exception; its license ships with the release.
- Local/cloud model and provider terms remain explicitly gated in `THIRD_PARTY_NOTICES.md`; model
  weights are not committed or bundled.
- Network use is disabled per job until explicit user approval, so no default path uploads user files.

## Release evidence

- Public release: <https://github.com/George-Nizor/Forge3D/releases/tag/v0.2.0>.
- Release ZIP: `175,818,934` bytes, SHA-256
  `47ce95e92c3337be8f7eb9f8c281838768577bbf342ce0894c67b6920e6d77d6`.
- Windows source suite: 42 passing. Fresh WSL clone: 38 passing and four Windows-only skips.
- Electron unit/security suite: 11 passing; Vite production build passing; npm audit reports zero
  vulnerabilities.
- PyInstaller CLI smoke reports `forge3d 0.2.0`.
- The public `instrumenta-release.json` and ZIP were downloaded independently and their size/hash
  contract verified.
- Instrumenta's real public-release path discovered the release, verified the manifest and ZIP,
  extracted it, atomically activated version 0.2.0, resolved `Forge3D.exe`, and retained the pending
  rollback pointer.
- The managed public executable stayed healthy for an eight-second packaged launch using an isolated
  Electron profile.

## Remaining installed-workflow checks

Public source/release publication is complete. The remaining hands-on workflow acceptance is to run an
actual Codex prompt through the GUI with locally installed Blender/Godot, inspect the produced artifact,
restart Forge3D and recover its history, and exercise Blender/Godot open/review actions. These checks
require the interactive desktop/app-control path and external tools; they are not claimed by the unit,
protocol-fixture, managed-install, or packaged-launch evidence above.

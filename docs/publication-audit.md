# Forge3D publication audit

Audit date: 2026-08-20. Target: public source repository and Windows x64 release 0.2.0.

## Source boundary

- Secret signature scan across all tracked and unignored files: no private-key, GitHub token,
  OpenAI key, AWS key, or Hugging Face token signatures found.
- Suspect secret filenames: none.
- Generated directories excluded: `.venv`, `node_modules`, renderer `dist`, `dist-package`, desktop
  runtime executable, `.tmp`, model directories, logs, caches, and user `output`/runs.
- Publishable file set contains no stale old-repository branding or absolute former-checkout paths.
- Three pre-existing tracked demo assets exceed 1 MiB: the game-controller splat and the
  game-controller/medical-pod reference images. On 2026-08-20, the sole project owner confirmed
  ownership and authorized their public redistribution with Forge3D.
- The generated 175,805,612-byte release ZIP and standalone executable are ignored and belong only
  on GitHub Releases.

## Dependency and redistribution review

- User-owned Forge3D code is MIT.
- Blender MCP, Godot MCP Toolkit, and GDGS retain their checked-in upstream licenses and attribution.
- Electron, Three.js, SparkJS, fflate, Vite, and Electron Builder are MIT.
- The standalone CLI uses the PyInstaller bootloader exception; keep its license with releases.
- Local/cloud model and provider terms remain explicitly gated as documented in
  `THIRD_PARTY_NOTICES.md`; model weights are not committed or bundled.
- The source repository has no unapproved cloud-upload default. Network is disabled per job until
  explicit user approval.

## Release evidence

- Python suite: 41 passing.
- Electron unit/security suite: 11 passing.
- Vite production build: passing.
- PyInstaller CLI smoke: `forge3d 0.2.0`.
- Electron Builder ZIP: generated successfully (`175,805,612` bytes, SHA-256
  `501853e4ad846d2e3058438244ba582c7ffc7dad96d9b55a2046a0a65c4142ab`).
- Instrumenta release-manifest parse, size, and SHA-256 verification: passing.

## Remaining publication gates

Before making the repository or release public, inspect the exact staged diff, approve staging and
commit separately, run a clean clone, re-run tests/audits, approve the GitHub repository rename and
push, download the public release, verify its checksum, launch it without a source checkout, and
record the final tag and checksum. Blender/Godot installed-app smoke tests remain required on the
release candidate.
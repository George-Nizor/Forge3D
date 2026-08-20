# Third-party components

Forge3D keeps third-party code and model environments separate from its host
CLI.

- Blender MCP add-on: MIT, vendored from commit
  `e3ece087adecce4242d4dc3e4db28c33010b51c4`; see
  `vendor/blender-mcp/LICENSE`.
- Godot MCP Toolkit 1.0.0: MIT with bundled attributions; see
  `godot/addons/godot_mcp_toolkit/LICENSE` and `ATTRIBUTIONS.md`.
- GDGS 3.3.0: MIT, pinned at commit
  `d9de8db86a63e8bf9067c869dcdbd0614922fd1e`; see
  `godot/addons/gdgs/LICENSE` and `UPSTREAM.md`. It imports and renders
  Gaussian PLY/SPLAT assets inside Godot.
- TripoSplat: code and weights published under MIT by VAST AI Research / Tripo
  AI. They are downloaded into the user's WSL model directory, not
  redistributed by this repository.
- TripoSG: top-level code is MIT, while its NOTICE identifies HunyuanDiT and
  FlashVDM-derived components under separate Tencent community terms. Its
  inference script also requires BRIA RMBG-1.4, whose model card limits use to
  non-commercial/evaluation purposes. Forge3D gates installation and use behind
  explicit review and acceptance.
- PartCrafter: top-level code is MIT, but its official inference path loads
  BRIA RMBG-1.4 and its published training/model lineage retains TripoSG
  components. Forge3D therefore gates it behind the same explicit terms review
  and does not select it automatically.
- SPAR3D: Stability AI Community License. Installation/use is gated because
  commercial use has registration, revenue, attribution, and AUP conditions,
  and the weights require Hugging Face access acceptance.
- The official Tripo Python SDK is MIT and is fetched as the exact
  `tripo3d==0.4.2` package only for an explicitly approved cloud job. It is not
  installed into Forge3D or Blender.

The packaged Forge3D desktop also includes:

- Electron 43.4.1: MIT.
- Three.js 0.185.1: MIT; its bundled license is preserved in the npm package.
- SparkJS 2.1.0 and its fflate dependency: MIT; used only for local Gaussian
  splat preview.
- The PyInstaller bootloader used for the standalone Forge3D CLI, under the
  PyInstaller GPL license with its bootloader exception. Application code
  remains MIT and source is available in this repository.

Electron Builder and Vite are build-time tools and are not application runtime
APIs; their MIT notices remain in the locked development dependency tree.

Other optional model workers retain their upstream licenses and are downloaded
only on demand. `forge3d models info <name>` shows the recorded source and
license URL.

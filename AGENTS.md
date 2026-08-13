# Forge3D repository guidance

- Keep Forge3D a personal, prompt-first tool. Do not add a daemon, database, web UI, or generic workflow framework.
- Treat Blender `.blend` files as editable source and GLB files as runtime exports.
- Use the direct Blender MCP for interactive inspection and supervised viewport edits. Use reviewed scripts under `blender/` for repeatable processing.
- Use the direct Godot MCP for import, scene, runtime, screenshot, and debugger validation.
- Run AI inference in isolated WSL environments. Do not install ML packages into Blender's embedded Python.
- Never upload an input to a cloud 3D provider without explicit per-job approval.
- Never overwrite an existing asset output. Create a numbered version.
- Use meters. Keep Blender's Z-up source convention and validate the glTF conversion in Godot.
- Prefer Python standard library code in the host CLI. Add dependencies only when they materially reduce risk.
- Run `forge3d doctor`, the Python test suite, a Blender headless smoke test, and a Godot headless smoke test before handoff.


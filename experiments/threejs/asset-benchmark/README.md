# Three.js Asset Benchmark

This is a deliberately small evaluation of LLM-authored procedural Three.js
assets. It creates the **Aegis M4** sentry drone from named Three.js primitives
and materials, with no downloaded model or texture assets.

## Run

```powershell
npm install
npm run dev
```

The viewer includes orbit controls, exploded and wireframe views, live renderer
metrics, animation, and binary GLB export.

## Evaluation boundary

This benchmark tests how well Codex can author a polished runtime scene and
structured procedural asset in Three.js. It does not demonstrate sculpting,
organic reconstruction, automatic retopology, UV painting, or a general
Three.js-to-Godot conversion system.

The exported hierarchy records named nodes and `userData` metadata using meters
and Three.js/Godot Y-up convention. That is enough to evaluate a later
GLB-plus-manifest bridge without committing to a custom porting framework.

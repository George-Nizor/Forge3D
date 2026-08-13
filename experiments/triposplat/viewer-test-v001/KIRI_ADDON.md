# KIRI Blender add-on provenance

- Source: https://github.com/Kiri-Innovation/3dgs-render-blender-addon
- Upstream tag: `v4.1.5`
- Upstream commit: `453301da6dfef7084cfd21f80521590ed3731ccf`
- Manifest package id: `dgs_render_by_kiri_engine`
- Manifest version at that tag: `4.1.3`
- License declared by the manifest: `GPL-2.0-or-later`
- Installed Blender repository: `user_default`
- Installed module: `bl_ext.user_default.dgs_render_by_kiri_engine`
- Tested Blender: `5.0.0`, Python `3.11`

The local installation package was restricted to Windows wheels before
installation. Temporary source, staging, and zip copies were removed after a
successful import and camera render to avoid retaining more than 2 GB of
duplicate cross-platform dependencies.

KIRI requires an `f_rest_0` property even for colour-only SH0 Gaussian PLYs.
`prepare_kiri_ply.py` appends a zero-valued compatibility field without
modifying the original TripoSplat output.

"""Enable the vendored Blender MCP add-on and start its loopback server."""

from __future__ import annotations

import bpy


def main() -> None:
    module_name = "blender_mcp"
    if module_name not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=module_name)
        bpy.ops.wm.save_userpref()

    scene = bpy.context.scene
    scene.blendermcp_port = 9876
    if not scene.blendermcp_server_running:
        result = bpy.ops.blendermcp.start_server()
        if "FINISHED" not in result:
            raise RuntimeError(f"Could not start Blender MCP: {result}")

    print("Forge3D: Blender MCP is listening on 127.0.0.1:9876")


main()


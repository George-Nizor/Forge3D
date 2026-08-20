from __future__ import annotations

import json
import re
from pathlib import Path

from forge3d import __version__


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "0.2.0"


def test_release_identity_is_consistent() -> None:
    assert __version__ == RELEASE_VERSION
    assert json.loads((ROOT / "instrumenta" / "product.json").read_text(encoding="utf-8"))["version"] == RELEASE_VERSION
    assert json.loads((ROOT / "plugins" / "forge3d" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"] == RELEASE_VERSION
    desktop = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
    assert desktop["version"] == RELEASE_VERSION
    assert desktop["build"]["win"]["icon"] == "assets/icon.png"
    assert (ROOT / "desktop" / "assets" / "icon.svg").is_file()
    assert (ROOT / "desktop" / "assets" / "icon.png").is_file()
    blender_source = (ROOT / "blender" / "forge3d_task.py").read_text(encoding="utf-8")
    assert re.search(r'^TOOL_VERSION = "0\.2\.0"$', blender_source, re.MULTILINE)
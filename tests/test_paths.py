from __future__ import annotations

from pathlib import Path

from forge3d import paths


def test_plugin_root_prefers_explicit_environment(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "bundled-plugin"
    configured.mkdir()
    monkeypatch.setenv("FORGE3D_PLUGIN_ROOT", str(configured))

    assert paths.plugin_root() == configured.resolve()


def test_plugin_root_falls_back_to_toolkit_plugin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FORGE3D_PLUGIN_ROOT", raising=False)
    plugin = tmp_path / "plugins" / "forge3d"
    plugin.mkdir(parents=True)
    monkeypatch.setattr(paths, "toolkit_root", lambda: tmp_path)

    assert paths.plugin_root() == plugin.resolve()
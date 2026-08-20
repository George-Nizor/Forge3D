from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .errors import Forge3DError
from .paths import is_within, output_root, slugify

SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})

_MEDIA_TYPES = {
    ".blend": "application/x-blender",
    ".gif": "image/gif",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".log": "text/plain",
    ".ply": "application/x-ply",
    ".splat": "application/x-gaussian-splat",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_input(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise Forge3DError(f"Input file does not exist: {resolved}")
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "sha256": file_hash(resolved),
        "size_bytes": stat.st_size,
    }


def versioned_run_dir(base: Path, name: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    slug = slugify(name)
    for version in range(1, 10_000):
        candidate = base / (slug if version == 1 else f"{slug}-v{version:03d}")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise Forge3DError(f"Too many versions already exist for {slug!r}")


def _media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(
        path.suffix.casefold(),
        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


def _preview_role(path: Path, name: str) -> str:
    suffix = path.suffix.casefold()
    lowered = name.casefold()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "primary-image" if "preview" in lowered else "image"
    if suffix == ".gif":
        return "animation"
    if suffix in {".glb", ".gltf"}:
        return "model"
    if suffix in {".splat", ".ply"}:
        return "gaussian-splat"
    if suffix == ".json" and "validation" in lowered:
        return "validation"
    if suffix in {".log", ".txt", ".md", ".json"}:
        return "text"
    return "metadata"


def describe_artifact(
    path: Path | str,
    *,
    run_root: Path,
    name: str,
    workflow_route: str,
    preview_role: str | None = None,
) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = run_root / candidate
    resolved = candidate.resolve()
    root = run_root.resolve()
    if not is_within(resolved, root):
        raise Forge3DError(f"Artifact must remain inside the run directory: {resolved}")
    relative = resolved.relative_to(root).as_posix()
    descriptor: dict[str, Any] = {
        "name": name,
        "path": relative,
        "media_type": _media_type(resolved),
        "preview_role": preview_role or _preview_role(resolved, name),
        "workflow_route": workflow_route,
    }
    if resolved.is_file():
        descriptor["size_bytes"] = resolved.stat().st_size
        descriptor["sha256"] = file_hash(resolved)
    return descriptor


def _validate_manifest(data: Any, manifest_path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise Forge3DError(f"Run manifest must be an object: {manifest_path}")
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise Forge3DError(
            f"Unsupported run schema {version!r} in {manifest_path}; "
            f"expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    if not isinstance(data.get("run_id"), str) or not data["run_id"]:
        raise Forge3DError(f"Run manifest has no run_id: {manifest_path}")
    if version == 2 and not isinstance(data.get("artifacts"), list):
        raise Forge3DError(f"Run schema v2 requires an artifacts list: {manifest_path}")
    return data


@dataclass
class Run:
    directory: Path
    manifest: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        name: str,
        command: str,
        prompt: str | None = None,
        inputs: Iterable[Path] = (),
        base: Path | None = None,
        settings: dict[str, Any] | None = None,
    ) -> "Run":
        described = [describe_input(path) for path in inputs]
        directory = versioned_run_dir(base or output_root(), name)
        timestamp = utc_now()
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": str(uuid.uuid4()),
            "name": directory.name,
            "command": command,
            "workflow_route": command,
            "status": "prepared",
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": None,
            "prompt": prompt,
            "inputs": described,
            "settings": settings or {},
            "steps": [],
            "outputs": {},
            "artifacts": [],
            "validation": {},
            "tools": {},
            "codex": {"thread_id": None, "turn_ids": []},
        }
        run = cls(directory=directory, manifest=manifest)
        (directory / "attachments").mkdir()
        (directory / "textures").mkdir()
        (directory / "turntable").mkdir()
        run.write()
        return run

    @classmethod
    def load(cls, path: Path) -> "Run":
        directory = path if path.is_dir() else path.parent
        manifest_path = directory / "run.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise Forge3DError(f"No run.json found in {directory}") from exc
        except json.JSONDecodeError as exc:
            raise Forge3DError(f"Invalid run manifest {manifest_path}: {exc}") from exc
        return cls(
            directory=directory.resolve(),
            manifest=_validate_manifest(data, manifest_path),
        )

    @property
    def manifest_path(self) -> Path:
        return self.directory / "run.json"

    def _synchronize_artifacts(self) -> None:
        if self.manifest.get("schema_version") != 2:
            return
        artifacts = self.manifest.setdefault("artifacts", [])
        route = str(self.manifest.get("workflow_route") or self.manifest.get("command"))
        by_name = {item.get("name"): index for index, item in enumerate(artifacts)}
        for name, value in self.manifest.get("outputs", {}).items():
            descriptor = describe_artifact(
                value,
                run_root=self.directory,
                name=name,
                workflow_route=route,
            )
            if name in by_name:
                artifacts[by_name[name]] = descriptor
            else:
                by_name[name] = len(artifacts)
                artifacts.append(descriptor)

    def write(self) -> None:
        self._synchronize_artifacts()
        self.manifest["updated_at"] = utc_now()
        self.directory.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=".run-", suffix=".json", dir=self.directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.manifest, stream, indent=2, sort_keys=True)
                stream.write("\n")
            temporary.replace(self.manifest_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def start_step(
        self, name: str, *, backend: str | None = None, detail: str | None = None
    ) -> int:
        step: dict[str, Any] = {
            "name": name,
            "status": "running",
            "started_at": utc_now(),
        }
        if backend:
            step["backend"] = backend
        if detail:
            step["detail"] = detail
        self.manifest["steps"].append(step)
        self.manifest["status"] = "running"
        self.write()
        return len(self.manifest["steps"]) - 1

    def finish_step(
        self,
        index: int,
        *,
        outputs: dict[str, Path | str] | None = None,
        detail: str | None = None,
    ) -> None:
        step = self.manifest["steps"][index]
        step["status"] = "completed"
        step["completed_at"] = utc_now()
        if detail:
            step["detail"] = detail
        if outputs:
            normalized: dict[str, str] = {}
            for key, value in outputs.items():
                descriptor = describe_artifact(
                    value,
                    run_root=self.directory,
                    name=key,
                    workflow_route=str(self.manifest["workflow_route"]),
                )
                normalized[key] = descriptor["path"]
            step["outputs"] = normalized
            self.manifest["outputs"].update(normalized)
        self.write()

    def fail_step(self, index: int, error: BaseException) -> None:
        step = self.manifest["steps"][index]
        step["status"] = "failed"
        step["completed_at"] = utc_now()
        step["error"] = str(error)
        self.manifest["status"] = "failed"
        self.manifest["error"] = str(error)
        self.write()

    def complete(self, *, validation: dict[str, Any] | None = None) -> None:
        self.manifest["status"] = "completed"
        if validation is not None:
            self.manifest["validation"] = validation
        self.manifest["completed_at"] = utc_now()
        self.write()

    def record_tool(self, name: str, details: dict[str, Any]) -> None:
        self.manifest["tools"][name] = details
        self.write()

    def record_codex_turn(self, thread_id: str, turn_id: str) -> None:
        codex = self.manifest.setdefault("codex", {"thread_id": None, "turn_ids": []})
        codex["thread_id"] = thread_id
        if turn_id not in codex["turn_ids"]:
            codex["turn_ids"].append(turn_id)
        self.write()
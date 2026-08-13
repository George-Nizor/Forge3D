from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .errors import Forge3DError
from .paths import output_root, slugify

SCHEMA_VERSION = 1


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
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": str(uuid.uuid4()),
            "name": directory.name,
            "command": command,
            "status": "prepared",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "prompt": prompt,
            "inputs": described,
            "settings": settings or {},
            "steps": [],
            "outputs": {},
            "validation": {},
            "tools": {},
        }
        run = cls(directory=directory, manifest=manifest)
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
        return cls(directory=directory.resolve(), manifest=data)

    @property
    def manifest_path(self) -> Path:
        return self.directory / "run.json"

    def write(self) -> None:
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
            normalized = {key: str(value) for key, value in outputs.items()}
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

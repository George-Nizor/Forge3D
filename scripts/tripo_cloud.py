"""One-shot, explicitly approved Tripo image-to-model job.

The host CLI launches this script through ``uv run --with tripo3d==0.4.2`` so
the cloud SDK never becomes a Forge3D or Blender Python dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run one explicitly approved Tripo image-to-model job."
    )
    result.add_argument("image", type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--approve-upload", action="store_true")
    result.add_argument("--model-version", default="P1-20260311")
    result.add_argument("--faces", type=int)
    result.add_argument(
        "--texture-quality",
        choices=("standard", "detailed"),
        default="detailed",
    )
    result.add_argument("--no-texture", action="store_true")
    result.add_argument("--no-pbr", action="store_true")
    result.add_argument("--timeout", type=float, default=3_600)
    return result


async def run(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    # Imported only after both consent and credential checks have passed.
    from tripo3d import TaskStatus, TripoClient

    image = args.image.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)

    texture = not args.no_texture
    pbr = texture and not args.no_pbr
    async with TripoClient(api_key=api_key) as client:
        task_id = await client.image_to_model(
            image=str(image),
            model_version=args.model_version,
            face_limit=args.faces,
            texture=texture,
            pbr=pbr,
            texture_quality=args.texture_quality,
        )
        task = await client.wait_for_task(
            task_id,
            timeout=args.timeout,
            verbose=False,
        )
        if task.status != TaskStatus.SUCCESS:
            status = getattr(task.status, "value", str(task.status))
            raise RuntimeError(f"Tripo task ended with status {status}")
        downloaded = await client.download_task_models(task, str(output))

    files = {
        key: str(Path(value).expanduser().resolve())
        for key, value in downloaded.items()
        if value
    }
    if not files:
        raise RuntimeError("Tripo reported success but returned no model files")
    result = {
        "provider": "tripo",
        "sdk_version": "0.4.2",
        "task_id": task_id,
        "status": "success",
        "request": {
            "image": str(image),
            "model_version": args.model_version,
            "faces": args.faces,
            "texture": texture,
            "pbr": pbr,
            "texture_quality": args.texture_quality,
        },
        "files": files,
    }
    (output / "cloud-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    api_key = os.environ.get("TRIPO_API_KEY", "")
    if not args.approve_upload:
        print(
            "tripo_cloud: refusing to upload without --approve-upload",
            file=sys.stderr,
        )
        return 2
    if not api_key:
        print(
            "tripo_cloud: TRIPO_API_KEY is not set",
            file=sys.stderr,
        )
        return 2

    image = args.image.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if not image.is_file():
        print(f"tripo_cloud: input does not exist: {image}", file=sys.stderr)
        return 2
    if image.stat().st_size > 20 * 1024 * 1024:
        print("tripo_cloud: Tripo image uploads are limited to 20 MB", file=sys.stderr)
        return 2
    if args.faces is not None and not 48 <= args.faces <= 20_000:
        print("tripo_cloud: --faces must be between 48 and 20000", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("tripo_cloud: --timeout must be greater than zero", file=sys.stderr)
        return 2
    if output.exists():
        print(
            f"tripo_cloud: output already exists; choose a new version: {output}",
            file=sys.stderr,
        )
        return 2

    try:
        result = asyncio.run(run(args, api_key))
    except Exception as exc:
        # Preserve useful diagnostics while ensuring the credential cannot be
        # reflected by an SDK/network exception.
        message = str(exc).replace(api_key, "<redacted>")
        print(f"tripo_cloud: {type(exc).__name__}: {message}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

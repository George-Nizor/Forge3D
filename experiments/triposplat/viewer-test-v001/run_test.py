from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def parse_counts(value: str) -> list[int]:
    counts = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not counts:
        raise argparse.ArgumentTypeError("at least one Gaussian count is required")
    for count in counts:
        if not 32_768 <= count <= 262_144:
            raise argparse.ArgumentTypeError(
                "Gaussian counts must be between 32768 and 262144"
            )
        if count % 32:
            raise argparse.ArgumentTypeError("Gaussian counts must be multiples of 32")
    return counts


def elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded local TripoSplat benchmark")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--counts", type=parse_counts, default=[65_536, 262_144])
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    destination = args.output.expanduser().resolve()
    model_dir = args.model_dir.expanduser().resolve()
    if not source.is_file():
        parser.error(f"input does not exist: {source}")
    if destination.exists():
        parser.error(f"output already exists; choose a new version: {destination}")
    if not model_dir.is_dir():
        parser.error(f"model directory does not exist: {model_dir}")
    if not 1 <= args.steps <= 100:
        parser.error("steps must be between 1 and 100")

    sys.path.insert(0, str(model_dir))
    import torch
    from triposplat import TripoSplatPipeline

    destination.mkdir(parents=True)
    started = time.perf_counter()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    checkpoint = model_dir / "ckpts"
    load_started = time.perf_counter()
    pipeline = TripoSplatPipeline(
        ckpt_path=str(checkpoint / "diffusion_models/triposplat_fp16.safetensors"),
        decoder_path=str(checkpoint / "vae/triposplat_vae_decoder_fp16.safetensors"),
        dinov3_path=str(checkpoint / "clip_vision/dino_v3_vit_h.safetensors"),
        flux2_vae_encoder_path=str(checkpoint / "vae/flux2-vae.safetensors"),
        rmbg_path=str(checkpoint / "background_removal/birefnet.safetensors"),
        device="cuda",
    )
    load_seconds = elapsed(load_started)

    inference_started = time.perf_counter()
    requested: int | list[int] = args.counts[0] if len(args.counts) == 1 else args.counts
    generated, prepared = pipeline.run(
        source,
        seed=args.seed,
        steps=args.steps,
        guidance_scale=3.0,
        shift=3.0,
        num_gaussians=requested,
        erode_radius=1,
        show_progress=True,
    )
    inference_seconds = elapsed(inference_started)
    prepared.save(destination / "prepared-input.webp")

    results = generated if isinstance(generated, list) else [generated]
    artifacts: list[dict[str, object]] = []
    for count, gaussian in zip(args.counts, results, strict=True):
        write_started = time.perf_counter()
        stem = f"medical-pod-{count:06d}"
        ply = destination / f"{stem}.ply"
        splat = destination / f"{stem}.splat"
        gaussian.save_ply(ply)
        gaussian.save_splat(splat)
        artifacts.append(
            {
                "gaussians": count,
                "ply": {"path": str(ply), "bytes": ply.stat().st_size},
                "splat": {"path": str(splat), "bytes": splat.stat().st_size},
                "write_seconds": elapsed(write_started),
            }
        )

    try:
        revision = subprocess.run(
            ["git", "-C", str(model_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = "unknown"

    gib = 1024**3
    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "input": str(source),
        "prepared_input": str(destination / "prepared-input.webp"),
        "upstream_revision": revision,
        "seed": args.seed,
        "steps": args.steps,
        "guidance_scale": 3.0,
        "shift": 3.0,
        "counts": args.counts,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "timings_seconds": {
            "model_load": load_seconds,
            "inference_and_decode": inference_seconds,
            "total": elapsed(started),
        },
        "peak_vram_gib": {
            "allocated": round(torch.cuda.max_memory_allocated() / gib, 3),
            "reserved": round(torch.cuda.max_memory_reserved() / gib, 3),
        },
        "artifacts": artifacts,
        "representation_warning": (
            "These files contain Gaussian splats, not polygon meshes. They do not "
            "contain faces, UVs, PBR materials, collision, or rigging data."
        ),
    }
    (destination / "run.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

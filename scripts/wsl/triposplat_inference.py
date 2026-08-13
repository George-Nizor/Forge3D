"""Bounded TripoSplat inference entry point for Forge3D's isolated WSL worker."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path


def gaussian_count(value: str) -> int:
    count = int(value)
    if not 32_768 <= count <= 262_144 or count % 32:
        raise argparse.ArgumentTypeError(
            "gaussians must be 32768-262144 and a multiple of 32"
        )
    return count


def sampling_steps(value: str) -> int:
    steps = int(value)
    if not 1 <= steps <= 100:
        raise argparse.ArgumentTypeError("steps must be between 1 and 100")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local TripoSplat job")
    parser.add_argument("image", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gaussians", type=gaussian_count, default=262_144)
    parser.add_argument("--steps", type=sampling_steps, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source = args.image.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if not source.is_file():
        parser.error(f"input does not exist: {source}")
    output.mkdir(parents=True, exist_ok=True)
    targets = {
        "ply": output / "candidate.ply",
        "splat": output / "candidate.splat",
        "prepared_input": output / "prepared-input.webp",
        "report": output / "triposplat-run.json",
    }
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        parser.error("refusing to overwrite: " + ", ".join(existing))

    import torch
    from triposplat import TripoSplatPipeline

    started = time.perf_counter()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    pipeline = TripoSplatPipeline(
        ckpt_path="ckpts/diffusion_models/triposplat_fp16.safetensors",
        decoder_path="ckpts/vae/triposplat_vae_decoder_fp16.safetensors",
        dinov3_path="ckpts/clip_vision/dino_v3_vit_h.safetensors",
        flux2_vae_encoder_path="ckpts/vae/flux2-vae.safetensors",
        rmbg_path="ckpts/background_removal/birefnet.safetensors",
        device="cuda",
    )
    gaussian, prepared = pipeline.run(
        source,
        seed=args.seed,
        steps=args.steps,
        guidance_scale=3.0,
        shift=3.0,
        num_gaussians=args.gaussians,
        erode_radius=1,
        show_progress=True,
    )
    prepared.save(targets["prepared_input"])
    gaussian.save_ply(targets["ply"])
    gaussian.save_splat(targets["splat"])

    gib = 1024**3
    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "input": str(source),
        "settings": {
            "seed": args.seed,
            "steps": args.steps,
            "guidance_scale": 3.0,
            "shift": 3.0,
            "gaussians": args.gaussians,
            "erode_radius": 1,
        },
        "artifacts": {key: str(path) for key, path in targets.items() if key != "report"},
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_vram_gib": round(torch.cuda.max_memory_reserved() / gib, 3),
        "representation": "gaussian_splat_not_polygon_mesh",
        "limitations": [
            "No polygon faces, UVs, rig, animation, or collision are present.",
            "Unseen views are generated from one image rather than measured.",
        ],
    }
    targets["report"].write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

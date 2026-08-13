from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .blender import Blender
from .doctor import check_environment
from .errors import Forge3DError
from .models import (
    CLOUD_PROVIDERS,
    MODELS,
    TRIPO_MODEL_VERSIONS,
    ModelManager,
    catalog_rows,
    cloud_estimate,
    get_model,
    run_tripo_cloud,
)
from .paths import slugify
from .workflows import (
    make_asset,
    prepare_animation_request,
    process_asset,
    retarget_animation,
    rig_asset,
    validate_asset,
)

MESH_IMAGE_MODEL_KEYS = tuple(
    key
    for key, model in MODELS.items()
    if "image-to-mesh" in model.capabilities
    or "image-to-parts" in model.capabilities
)
RUNNABLE_IMAGE_MODEL_KEYS = tuple(
    key
    for key, model in MODELS.items()
    if any(
        capability in model.capabilities
        for capability in ("image-to-mesh", "image-to-parts", "image-to-splat")
    )
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="forge3d",
        description="Lean local 3D workflow helpers for Codex, Blender, and Godot.",
    )
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = result.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Check Blender, Godot, MCP files, WSL, and CUDA")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.set_defaults(handler=_doctor)

    make = commands.add_parser("make", help="Create a procedural or image-derived asset")
    make.add_argument("prompt")
    make.add_argument("--name")
    make_route = make.add_mutually_exclusive_group()
    make_route.add_argument("--reference", type=Path)
    make.add_argument(
        "--backend",
        default="auto",
        choices=("auto", *MESH_IMAGE_MODEL_KEYS),
        help=(
            "Explicit image backend. `auto` refuses because quality and "
            "commercial eligibility require a deliberate choice."
        ),
    )
    make_route.add_argument(
        "--recipe",
        choices=(
            "box",
            "crate",
            "equipment-case",
            "medical-case",
            "stairs",
            "room",
            "fence",
            "pipe",
            "terrain",
        ),
        help="Use one fixed procedural recipe; omit when --reference is supplied.",
    )
    make.add_argument(
        "--params",
        type=_json_object,
        default={},
        help='Recipe parameters as a JSON object, for example \'{"width":1.2}\'.',
    )
    make.add_argument("--faces", type=_positive_int)
    make.add_argument("--output-dir", type=Path)
    make.add_argument("--low-vram", action="store_true")
    make.add_argument("--ignore-vram", action="store_true")
    make.add_argument("--dry-run", action="store_true")
    make.set_defaults(handler=_make)

    process = commands.add_parser("process", help="Clean and prepare a mesh in Blender")
    process.add_argument("input", type=Path)
    process.add_argument("--name")
    process.add_argument(
        "--steps",
        default="normalize,repair",
        help="Comma-separated Blender steps.",
    )
    process.add_argument("--unwrap", action="store_true")
    process.add_argument("--lods", action="store_true")
    process.add_argument("--collision", action="store_true")
    process.add_argument("--no-preview", action="store_true")
    process.add_argument("--force", action="store_true")
    process.add_argument("--output-dir", type=Path)
    process.set_defaults(handler=_process)

    rig = commands.add_parser("rig", help="Automatically rig a mesh locally")
    rig.add_argument("input", type=Path)
    rig.add_argument("--name")
    rig.add_argument(
        "--backend",
        choices=("blender", "skintokens"),
        default="blender",
        help="Use bundled Rigify by default; SkinTokens is the explicit ML option.",
    )
    rig.add_argument("--use-skeleton", action="store_true")
    rig.add_argument("--ignore-vram", action="store_true")
    rig.add_argument("--output-dir", type=Path)
    rig.set_defaults(handler=_rig)

    retarget = commands.add_parser("retarget", help="Retarget and bake animation in Blender")
    retarget.add_argument("input", type=Path)
    retarget.add_argument("--source-armature", required=True)
    retarget.add_argument("--target-armature", required=True)
    retarget.add_argument("--bone-map", required=True, type=Path)
    retarget.add_argument("--name")
    retarget.add_argument("--no-bake", action="store_true")
    retarget.add_argument("--output-dir", type=Path)
    retarget.set_defaults(handler=_retarget)

    animate = commands.add_parser(
        "animate",
        help="Prepare a prompt-driven animation request for Codex and Blender MCP",
    )
    animate.add_argument("input", type=Path)
    animate.add_argument("prompt")
    animate.add_argument("--name")
    animate.add_argument("--output-dir", type=Path)
    animate.set_defaults(handler=_animate)

    validate = commands.add_parser("validate", help="Run Blender asset validators")
    validate.add_argument("input", type=Path)
    validation_kind = validate.add_mutually_exclusive_group()
    validation_kind.add_argument("--rig", action="store_true")
    validation_kind.add_argument("--animation", action="store_true")
    validate.add_argument("--output-dir", type=Path)
    validate.set_defaults(handler=_validate)

    open_parser = commands.add_parser("open", help="Open a .blend or run folder in Blender")
    open_parser.add_argument("path", type=Path)
    open_parser.set_defaults(handler=_open)

    models = commands.add_parser("models", help="Manage isolated local AI backends")
    model_commands = models.add_subparsers(dest="models_command", required=True)

    list_parser = model_commands.add_parser("list", help="Show the model catalog")
    list_parser.add_argument("--json", action="store_true", dest="as_json")
    list_parser.set_defaults(handler=_models_list)

    info = model_commands.add_parser("info", help="Show model details and install requirements")
    info.add_argument("model", choices=tuple(MODELS))
    info.add_argument("--json", action="store_true", dest="as_json")
    info.set_defaults(handler=_models_info)

    status = model_commands.add_parser("status", help="Check installations in WSL")
    status.add_argument("model", nargs="?", choices=tuple(MODELS))
    status.add_argument("--distro")
    status.add_argument("--json", action="store_true", dest="as_json")
    status.set_defaults(handler=_models_status)

    install = model_commands.add_parser("install", help="Clone and install one model in WSL")
    install.add_argument("model", choices=tuple(MODELS))
    install.add_argument("--accept-license", action="store_true")
    install.add_argument("--revision", default="main")
    install.add_argument("--distro")
    install.add_argument(
        "--plan",
        action="store_true",
        help="Print the exact WSL script without running it.",
    )
    install.set_defaults(handler=_models_install)

    run = model_commands.add_parser("run", help="Run an installed image-derived asset model")
    run.add_argument("model", choices=RUNNABLE_IMAGE_MODEL_KEYS)
    run.add_argument("image", type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--faces", type=_positive_int)
    run.add_argument("--parts", type=_positive_int, default=4)
    run.add_argument("--low-vram", action="store_true")
    run.add_argument(
        "--gaussians",
        type=_positive_int,
        default=262_144,
        help="TripoSplat density (32768-262144, multiple of 32).",
    )
    run.add_argument("--ignore-vram", action="store_true")
    run.add_argument("--distro")
    run.add_argument("--json", action="store_true", dest="as_json")
    run.set_defaults(handler=_models_run)

    cloud = model_commands.add_parser(
        "cloud-estimate",
        help="Describe a possible cloud fallback without uploading anything",
    )
    cloud.add_argument("provider", choices=tuple(CLOUD_PROVIDERS))
    cloud.add_argument("input", nargs="+", type=Path)
    cloud.set_defaults(handler=_models_cloud)

    cloud_run = model_commands.add_parser(
        "cloud-run",
        help="Run one explicitly approved pay-per-use cloud fallback",
    )
    cloud_run.add_argument("provider", choices=("tripo",))
    cloud_run.add_argument("image", type=Path)
    cloud_run.add_argument("--output-dir", required=True, type=Path)
    cloud_run.add_argument(
        "--approve-upload",
        action="store_true",
        help="Confirm approval for these files and this one paid job.",
    )
    cloud_run.add_argument(
        "--model-version",
        choices=TRIPO_MODEL_VERSIONS,
        default="P1-20260311",
    )
    cloud_run.add_argument("--faces", type=_tripo_faces)
    cloud_run.add_argument(
        "--texture-quality",
        choices=("standard", "detailed"),
        default="detailed",
    )
    cloud_run.add_argument("--no-texture", action="store_true")
    cloud_run.add_argument("--no-pbr", action="store_true")
    cloud_run.add_argument("--timeout", type=float, default=3_600)
    cloud_run.set_defaults(handler=_models_cloud_run)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args) or 0)
    except Forge3DError as exc:
        print(f"forge3d: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("forge3d: interrupted", file=sys.stderr)
        return 130


def _doctor(args: argparse.Namespace) -> int:
    report = check_environment()
    if args.as_json:
        _print_json(report)
    else:
        print(f"Forge3D root: {report['root']}")
        for check in report["checks"]:
            marker = "OK" if check["ok"] else ("FAIL" if check["required"] else "WARN")
            detail = check.get("version") or check.get("detail") or check.get("path", "")
            print(f"[{marker:4}] {check['name']}: {detail}")
            if not check["ok"]:
                print(f"       {check['fix']}")
    return 0 if report["ok"] else 1


def _make(args: argparse.Namespace) -> int:
    name = args.name or slugify(args.prompt)
    run = make_asset(
        prompt=args.prompt,
        name=name,
        reference=args.reference,
        backend=args.backend,
        recipe=args.recipe,
        recipe_params=args.params,
        faces=args.faces,
        output_base=_resolve_output(args.output_dir),
        dry_run=args.dry_run,
        low_vram=args.low_vram,
        ignore_vram=args.ignore_vram,
    )
    _print_run(run)
    return 0


def _process(args: argparse.Namespace) -> int:
    steps = tuple(part.strip() for part in args.steps.split(",") if part.strip())
    run = process_asset(
        source=args.input,
        name=args.name,
        output_base=_resolve_output(args.output_dir),
        steps=steps,
        unwrap=args.unwrap,
        make_lods=args.lods,
        make_collision=args.collision,
        render_preview=not args.no_preview,
        force=args.force,
    )
    _print_run(run)
    return 0


def _rig(args: argparse.Namespace) -> int:
    run = rig_asset(
        source=args.input,
        backend=args.backend,
        name=args.name,
        output_base=_resolve_output(args.output_dir),
        use_skeleton=args.use_skeleton,
        ignore_vram=args.ignore_vram,
    )
    _print_run(run)
    return 0


def _retarget(args: argparse.Namespace) -> int:
    run = retarget_animation(
        source=args.input,
        source_armature=args.source_armature,
        target_armature=args.target_armature,
        bone_map=args.bone_map,
        name=args.name,
        output_base=_resolve_output(args.output_dir),
        bake=not args.no_bake,
    )
    _print_run(run)
    return 0


def _animate(args: argparse.Namespace) -> int:
    run = prepare_animation_request(
        source=args.input,
        prompt=args.prompt,
        name=args.name,
        output_base=_resolve_output(args.output_dir),
    )
    _print_run(run)
    return 0


def _validate(args: argparse.Namespace) -> int:
    run = validate_asset(
        args.input,
        output_base=_resolve_output(args.output_dir),
        rig=args.rig,
        animation=args.animation,
    )
    _print_run(run)
    return 0


def _open(args: argparse.Namespace) -> int:
    Blender().open(args.path)
    print(f"Opened in Blender: {args.path.expanduser().resolve()}")
    return 0


def _models_list(args: argparse.Namespace) -> int:
    rows = catalog_rows()
    if args.as_json:
        _print_json(rows)
        return 0
    print(f"{'KEY':13} {'VRAM':>5} {'LICENCE':30} ROLE")
    for model in MODELS.values():
        gated = " (acceptance required)" if model.acceptance_required else ""
        print(
            f"{model.key:13} {model.vram_gb:>3}GB "
            f"{(model.license_name + gated):30.30} {model.role}"
        )
    return 0


def _models_info(args: argparse.Namespace) -> int:
    model = get_model(args.model)
    data = {
        key: value
        for key, value in vars(model).items()
    }
    data["install_command"] = (
        f"forge3d models install {model.key}"
        + (" --accept-license" if model.acceptance_required else "")
    )
    if args.as_json:
        _print_json(data)
    else:
        for key, value in data.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
    return 0


def _models_status(args: argparse.Namespace) -> int:
    manager = ModelManager(distro=args.distro)
    selected = [get_model(args.model)] if args.model else list(MODELS.values())
    rows = []
    for model in selected:
        installed = manager.is_installed(model)
        rows.append(
            {
                "model": model.key,
                "installed": installed,
                "ready": manager.is_ready(model) if installed else False,
                "revision": manager.revision(model) if installed else None,
                "license_accepted": (
                    manager.license_accepted(model)
                    if model.acceptance_required
                    else None
                ),
            }
        )
    if args.as_json:
        _print_json(rows)
    else:
        for row in rows:
            state = (
                "ready"
                if row["ready"]
                else "installed, incomplete"
                if row["installed"]
                else "not installed"
            )
            revision = f" ({row['revision'][:12]})" if row["revision"] else ""
            print(f"{row['model']}: {state}{revision}")
    return 0


def _models_install(args: argparse.Namespace) -> int:
    manager = ModelManager(distro=args.distro)
    model = get_model(args.model)
    if args.plan:
        print(manager.install_plan(model, args.revision))
        if model.acceptance_required and not manager.license_accepted(model):
            print(
                f"\nLicence acceptance is still required before execution: "
                f"{model.license_url}",
                file=sys.stderr,
            )
        return 0
    result = manager.install(
        model,
        accept_license=args.accept_license,
        revision=args.revision,
    )
    revision = result.stdout.strip().splitlines()[-1]
    print(f"Installed {model.name} at revision {revision}")
    return 0


def _models_run(args: argparse.Namespace) -> int:
    manager = ModelManager(distro=args.distro)
    result = manager.run_image(
        get_model(args.model),
        args.image,
        args.output_dir,
        faces=args.faces,
        parts=args.parts,
        low_vram=args.low_vram,
        gaussians=args.gaussians,
        ignore_vram=args.ignore_vram,
    )
    data = {
        "model": result.model,
        "revision": result.revision,
        "artifact": str(result.artifact),
        "command": list(result.command),
    }
    if args.as_json:
        _print_json(data)
    else:
        print(f"Created: {result.artifact}")
        print(f"Model revision: {result.revision}")
    return 0


def _models_cloud(args: argparse.Namespace) -> int:
    _print_json(cloud_estimate(args.provider, args.input))
    return 0


def _models_cloud_run(args: argparse.Namespace) -> int:
    result = run_tripo_cloud(
        args.image,
        args.output_dir,
        approve_upload=args.approve_upload,
        model_version=args.model_version,
        faces=args.faces,
        texture_quality=args.texture_quality,
        texture=not args.no_texture,
        pbr=not args.no_pbr,
        timeout=args.timeout,
    )
    _print_json(result)
    return 0


def _resolve_output(path: Path | None) -> Path | None:
    return path.expanduser().resolve() if path else None


def _print_run(run: Any) -> None:
    print(f"Run: {run.directory}")
    print(f"Status: {run.manifest['status']}")
    for key, value in run.manifest.get("outputs", {}).items():
        print(f"{key}: {value}")


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("must be a JSON object")
    return value


def _tripo_faces(raw: str) -> int:
    value = int(raw)
    if not 48 <= value <= 20_000:
        raise argparse.ArgumentTypeError("must be between 48 and 20000")
    return value


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .blender import Blender
from .errors import Forge3DError
from .models import ModelManager, ModelRunResult, get_model
from .runs import Run


def make_asset(
    *,
    prompt: str,
    name: str,
    reference: Path | None = None,
    backend: str = "auto",
    recipe: str | None = None,
    recipe_params: dict[str, Any] | None = None,
    faces: int | None = None,
    output_base: Path | None = None,
    dry_run: bool = False,
    manager: ModelManager | None = None,
    blender: Blender | None = None,
    low_vram: bool = False,
    ignore_vram: bool = False,
) -> Run:
    if reference is not None and recipe is not None:
        raise Forge3DError("Use either a reference backend or a recipe, not both.")
    if reference is not None and recipe_params:
        raise Forge3DError("--params applies only to procedural recipes.")
    if reference is None and recipe is None:
        raise Forge3DError(
            "A free-form prompt needs the Forge3D Codex skill to author the "
            "model. For direct CLI use, supply --reference or an explicit "
            "--recipe."
        )
    selected: str | None = None
    if reference:
        manager = manager or ModelManager()
        selected = _select_image_model(backend)
    inputs = [reference] if reference else []
    run = Run.create(
        name=name,
        command="make",
        prompt=prompt,
        inputs=inputs,
        base=output_base,
        settings={
            "backend": backend,
            "recipe": recipe,
            "recipe_params": recipe_params or {},
            "faces": faces,
            "low_vram": low_vram,
        },
    )
    if dry_run:
        run.manifest["status"] = "prepared"
        run.manifest["next_step"] = "Run again without --dry-run."
        run.write()
        return run
    if reference:
        assert manager is not None and selected is not None
        step = run.start_step("image-to-mesh", backend=selected)
        try:
            result = manager.run_image(
                get_model(selected),
                reference,
                run.directory / "generated",
                faces=faces,
                low_vram=low_vram,
                ignore_vram=ignore_vram,
            )
            _record_model(run, result)
            run.finish_step(step, outputs={"generated_mesh": result.artifact})
        except Exception as exc:
            run.fail_step(step, exc)
            raise
        source = result.artifact
    else:
        blender = blender or Blender()
        generated_dir = run.directory / "generated"
        generated_dir.mkdir(exist_ok=True)
        source = generated_dir / "procedural.blend"
        step = run.start_step("procedural", backend="blender")
        try:
            blender.task(
                "procedural",
                {
                    "output": source,
                    "recipe": recipe,
                    "params": json.dumps(
                        {"prompt": prompt, **(recipe_params or {})}
                    ),
                },
            )
            _require_output(source, "Blender procedural task")
            run.finish_step(step, outputs={"source_blend": source})
        except Exception as exc:
            run.fail_step(step, exc)
            raise
    processed = process_asset(
        source=source,
        run=run,
        blender=blender,
        steps=(
            ("normalize", "repair")
            if reference
            else (
                ("normalize", "repair", "unwrap")
                if recipe in {"equipment-case", "medical-case"}
                else ("normalize", "repair", "unwrap", "material")
            )
        ),
        unwrap=False,
        make_lods=False,
        make_collision=False,
        render_preview=True,
    )
    if reference:
        processed.manifest["status"] = "awaiting_blender_review"
        processed.manifest["quality_gate"] = {
            "backend": selected,
            "structural_validation_passed": bool(
                processed.manifest.get("validation", {}).get("passed", False)
            ),
            "visual_review_required": True,
            "orientation_review_required": True,
        }
        processed.manifest["next_step"] = (
            "Inspect silhouette, proportions, orientation, hidden sides, and "
            "surface artifacts through Blender MCP. Rebuild structured "
            "hard-surface forms procedurally instead of polishing a weak draft."
        )
        processed.write()
    return processed


def process_asset(
    *,
    source: Path,
    name: str | None = None,
    prompt: str | None = None,
    run: Run | None = None,
    output_base: Path | None = None,
    blender: Blender | None = None,
    steps: Iterable[str] = ("normalize", "repair"),
    unwrap: bool = False,
    make_lods: bool = False,
    make_collision: bool = False,
    render_preview: bool = True,
    force: bool = False,
) -> Run:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise Forge3DError(f"Input mesh does not exist: {source}")
    run = run or Run.create(
        name=name or source.stem,
        command="process",
        prompt=prompt,
        inputs=[source],
        base=output_base,
    )
    blender = blender or Blender()
    run.record_tool("blender", {"version": blender.version()})

    selected = list(steps)
    if unwrap:
        selected.append("unwrap")
    if make_lods:
        selected.append("lods")
    if make_collision:
        selected.append("collision")
    selected = list(dict.fromkeys(selected))

    current = source
    working_dir = run.directory / ".working"
    working_dir.mkdir(exist_ok=True)
    working_paths = [working_dir / "a.blend", working_dir / "b.blend"]
    for index, task_name in enumerate(selected, start=1):
        if task_name not in {
            "normalize",
            "repair",
            "unwrap",
            "material",
            "lods",
            "collision",
        }:
            raise Forge3DError(f"Unsupported process step: {task_name}")
        destination = working_paths[(index - 1) % len(working_paths)]
        step = run.start_step(task_name, backend="blender")
        try:
            blender.task(
                task_name,
                {
                    "input": current,
                    "output": destination,
                    # These two alternating files are toolkit-owned staging
                    # copies. Overwriting an older stage never touches the
                    # caller's source or canonical output.
                    "force": force or destination.exists(),
                },
            )
            _require_output(destination, f"Blender {task_name} task")
            run.finish_step(step, detail=f"Staged in {destination.name}")
            current = destination
        except Exception as exc:
            run.fail_step(step, exc)
            raise

    canonical = run.directory / "source.blend"
    if current.resolve() != canonical.resolve():
        step = run.start_step("save-source", backend="blender")
        try:
            blender.task(
                "save", {"input": current, "output": canonical, "force": force}
            )
            _require_output(canonical, "Blender save task")
            run.finish_step(step, outputs={"source_blend": canonical})
        except Exception as exc:
            run.fail_step(step, exc)
            raise

    glb = run.directory / "model.glb"
    step = run.start_step("export-glb", backend="blender")
    try:
        blender.task(
            "export-glb", {"input": canonical, "output": glb, "force": force}
        )
        _require_output(glb, "Blender GLB export")
        run.finish_step(step, outputs={"model_glb": glb})
    except Exception as exc:
        run.fail_step(step, exc)
        raise

    report = run.directory / "validation.json"
    step = run.start_step("validate", backend="blender")
    try:
        blender.task("validate", {"input": canonical, "report": report})
        validation = _load_report(report)
        run.finish_step(step, outputs={"validation_report": report})
    except Exception as exc:
        run.fail_step(step, exc)
        raise

    if render_preview:
        preview = run.directory / "preview.png"
        step = run.start_step("turntable", backend="blender")
        try:
            blender.task(
                "turntable",
                {
                    "input": canonical,
                    "output": preview,
                    "force": force,
                },
                timeout=3_600,
            )
            _require_output(preview, "Blender turntable task")
            run.finish_step(step, outputs={"preview": preview})
        except Exception as exc:
            run.fail_step(step, exc)
            raise
    run.complete(validation=validation)
    for temporary in working_paths:
        temporary.unlink(missing_ok=True)
    try:
        working_dir.rmdir()
    except OSError:
        # Keep unexpected diagnostics or sidecars rather than deleting them.
        pass
    return run


def rig_asset(
    *,
    source: Path,
    backend: str = "blender",
    name: str | None = None,
    output_base: Path | None = None,
    use_skeleton: bool = False,
    ignore_vram: bool = False,
    manager: ModelManager | None = None,
    blender: Blender | None = None,
) -> Run:
    source = source.expanduser().resolve()
    if backend not in {"blender", "skintokens"}:
        raise Forge3DError(f"Unsupported rigging backend: {backend}")
    if backend == "blender" and use_skeleton:
        raise Forge3DError("--use-skeleton is only available with SkinTokens")
    run = Run.create(
        name=name or f"{source.stem}-rigged",
        command="rig",
        inputs=[source],
        base=output_base,
        settings={"backend": backend, "use_skeleton": use_skeleton},
    )
    blender = blender or Blender()
    run.record_tool("blender", {"version": blender.version()})
    canonical = run.directory / "source.blend"

    if backend == "blender":
        rig_report = run.directory / "rig-generation.json"
        step = run.start_step("rig-humanoid", backend="blender-rigify")
        try:
            blender.task(
                "rig-humanoid",
                {
                    "input": source,
                    "output": canonical,
                    "report": rig_report,
                    "rig_name": "Forge3D_Rig",
                },
                timeout=3_600,
            )
            _require_output(canonical, "Blender Rigify task")
            _require_output(rig_report, "Blender Rigify report")
            run.finish_step(
                step,
                outputs={
                    "source_blend": canonical,
                    "rig_generation_report": rig_report,
                },
            )
        except Exception as exc:
            run.fail_step(step, exc)
            raise
    else:
        model = get_model(backend)
        manager = manager or ModelManager()
        generated = run.directory / "rigged.glb"
        step = run.start_step("auto-rig", backend=model.key)
        try:
            result = manager.rig(
                model,
                source,
                generated,
                use_skeleton=use_skeleton,
                ignore_vram=ignore_vram,
            )
            _record_model(run, result)
            run.finish_step(step, outputs={"generated_rig": result.artifact})
        except Exception as exc:
            run.fail_step(step, exc)
            raise

        step = run.start_step("save-source", backend="blender")
        try:
            blender.task("save", {"input": generated, "output": canonical})
            _require_output(canonical, "Blender save task")
            run.finish_step(step, outputs={"source_blend": canonical})
        except Exception as exc:
            run.fail_step(step, exc)
            raise

    report = run.directory / "rig-validation.json"
    step = run.start_step("rig-validate", backend="blender")
    try:
        validation_args: dict[str, Any] = {
            "input": canonical,
            "report": report,
        }
        if backend == "blender":
            validation_args["objects"] = "Forge3D_Rig"
        blender.task("rig-validate", validation_args)
        validation = _load_report(report)
        run.finish_step(step, outputs={"rig_validation_report": report})
    except Exception as exc:
        run.fail_step(step, exc)
        raise
    if backend == "blender":
        _export_game_outputs(
            run,
            blender,
            canonical,
            export_args={
                "armature": "Forge3D_Rig",
                "deform_bones_only": True,
            },
            preview_args={"armature": "Forge3D_Rig"},
        )
    else:
        _export_game_outputs(run, blender, canonical)
    run.complete(validation=validation)
    return run


def retarget_animation(
    *,
    source: Path,
    source_armature: str,
    target_armature: str,
    bone_map: Path,
    name: str | None = None,
    output_base: Path | None = None,
    bake: bool = True,
    blender: Blender | None = None,
) -> Run:
    source = source.expanduser().resolve()
    bone_map = bone_map.expanduser().resolve()
    run = Run.create(
        name=name or f"{source.stem}-retargeted",
        command="retarget",
        inputs=[source, bone_map],
        base=output_base,
        settings={
            "source_armature": source_armature,
            "target_armature": target_armature,
            "bake": bake,
        },
    )
    action_name = f"{run.directory.name}_Retargeted"
    run.manifest["settings"]["action_name"] = action_name
    run.write()
    blender = blender or Blender()
    destination = run.directory / "source.blend"
    report = run.directory / "retarget.json"
    step = run.start_step("retarget", backend="blender")
    try:
        blender.task(
            "retarget",
            {
                "input": source,
                "output": destination,
                "report": report,
                "source_armature": source_armature,
                "target_armature": target_armature,
                "bone_map": bone_map,
                "bake": bake,
                "clear_constraints": bake,
                "action_name": action_name if bake else None,
            },
        )
        _require_output(destination, "Blender retarget task")
        run.finish_step(
            step, outputs={"source_blend": destination, "retarget_report": report}
        )
    except Exception as exc:
        run.fail_step(step, exc)
        raise

    if not bake:
        run.manifest["status"] = "awaiting_blender_review"
        run.manifest["next_step"] = (
            "Inspect the live retarget constraints in Blender, then bake and "
            "validate before export."
        )
        run.write()
        return run

    animation_report = run.directory / "animation-validation.json"
    step = run.start_step("animation-validate", backend="blender")
    try:
        blender.task(
            "animation-validate",
            {
                "input": destination,
                "report": animation_report,
                "actions": action_name,
            },
        )
        validation = _load_report(animation_report)
        run.finish_step(
            step, outputs={"animation_validation_report": animation_report}
        )
    except Exception as exc:
        run.fail_step(step, exc)
        raise
    _export_game_outputs(
        run,
        blender,
        destination,
        export_args={
            "armature": target_armature,
            "actions": action_name,
        },
        preview_args={"armature": target_armature},
    )
    run.complete(validation=validation)
    return run


def prepare_animation_request(
    *,
    source: Path,
    prompt: str,
    name: str | None = None,
    output_base: Path | None = None,
) -> Run:
    source = source.expanduser().resolve()
    run = Run.create(
        name=name or f"{source.stem}-animation",
        command="animate",
        prompt=prompt,
        inputs=[source],
        base=output_base,
    )
    request = {
        "input": str(source),
        "output": str(run.directory / "source.blend"),
        "prompt": prompt,
        "completion_requirements": [
            "Edit through Blender MCP on the output working copy",
            "Run animation-validate",
            "Save preview evidence and update run.json",
        ],
    }
    request_path = run.directory / "codex-animation-request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    run.manifest["status"] = "awaiting_codex"
    run.manifest["outputs"]["codex_request"] = str(request_path)
    run.manifest["next_step"] = (
        "Use the Forge3D Codex skill and Blender MCP to perform this animation request."
    )
    run.write()
    return run


def validate_asset(
    source: Path,
    *,
    output_base: Path | None = None,
    blender: Blender | None = None,
    rig: bool = False,
    animation: bool = False,
) -> Run:
    source = source.expanduser().resolve()
    run = Run.create(
        name=f"{source.stem}-validation",
        command="validate",
        inputs=[source],
        base=output_base,
        settings={"rig": rig, "animation": animation},
    )
    blender = blender or Blender()
    task = "animation-validate" if animation else "rig-validate" if rig else "validate"
    report = run.directory / "validation.json"
    step = run.start_step(task, backend="blender")
    try:
        blender.task(task, {"input": source, "report": report})
        validation = _load_report(report)
        run.finish_step(step, outputs={"validation_report": report})
    except Exception as exc:
        run.fail_step(step, exc)
        raise
    run.complete(validation=validation)
    return run


def _select_image_model(backend: str) -> str:
    if backend != "auto":
        return get_model(backend).key
    raise Forge3DError(
        "Automatic image-to-mesh selection is disabled because no local "
        "backend is both production-quality and unconditionally licensed for "
        "commercial game work. Choose `--backend spar3d` only after confirming "
        "current Stability commercial eligibility and accepting its terms. "
        "For static visual reconstruction use `forge3d models run triposplat`; "
        "TripoSplat is Gaussian data and is deliberately not accepted as a mesh."
    )


def _record_model(run: Run, result: ModelRunResult) -> None:
    model = get_model(result.model)
    run.record_tool(
        result.model,
        {
            "revision": result.revision,
            "command": list(result.command),
            "license": model.license_name,
            "license_url": model.license_url,
            "terms_urls": list(model.terms_urls),
        },
    )


def _export_game_outputs(
    run: Run,
    blender: Blender,
    canonical: Path,
    *,
    export_args: dict[str, Any] | None = None,
    preview_args: dict[str, Any] | None = None,
) -> None:
    glb = run.directory / "model.glb"
    step = run.start_step("export-glb", backend="blender")
    try:
        blender.task(
            "export-glb",
            {
                "input": canonical,
                "output": glb,
                **(export_args or {}),
            },
        )
        _require_output(glb, "Blender GLB export")
        run.finish_step(step, outputs={"model_glb": glb})
    except Exception as exc:
        run.fail_step(step, exc)
        raise

    preview = run.directory / "preview.png"
    step = run.start_step("turntable", backend="blender")
    try:
        blender.task(
            "turntable",
            {
                "input": canonical,
                "output": preview,
                **(preview_args or {}),
            },
            timeout=3_600,
        )
        _require_output(preview, "Blender turntable task")
        run.finish_step(step, outputs={"preview": preview})
    except Exception as exc:
        run.fail_step(step, exc)
        raise


def _require_output(path: Path, operation: str) -> None:
    if not path.is_file():
        raise Forge3DError(f"{operation} did not create its expected output: {path}")


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise Forge3DError(f"Validation did not create its report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Forge3DError(f"Invalid validation report {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Forge3DError(f"Validation report must contain a JSON object: {path}")
    return data

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .errors import Forge3DError, ToolNotFoundError
from .paths import slugify, toolkit_root, workspace_root
from .process import CommandResult, CommandRunner, WSL, executable

PYTORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
PYTORCH_VERSION = "2.11.0"
TORCHVISION_VERSION = "0.26.0"
TRIPOSG_WEIGHTS_REVISION = "2c1c516d22d58db486a058d98d31bb6177344e06"
RMBG_14_REVISION = "2ceba5a5efaec153162aedea169f76caf9b46cf8"
TRIPO_SDK_VERSION = "0.4.2"
TRIPO_MODEL_VERSIONS = (
    "P1-20260311",
    "Turbo-v1.0-20250506",
    "v3.1-20260211",
    "v3.0-20250812",
    "v2.5-20250123",
    "v2.0-20240919",
    "v1.4-20240625",
)
_SAFE_REVISION = re.compile(r"^[A-Za-z0-9._/@+-]+$")


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    directory_name: str
    role: str
    repository: str
    license_name: str
    license_url: str
    python: str
    vram_gb: int
    terms_urls: tuple[str, ...] = ()
    optional: bool = False
    acceptance_required: bool = False
    capabilities: tuple[str, ...] = ()
    notes: str = ""


MODELS: dict[str, Model] = {
    "triposplat": Model(
        key="triposplat",
        name="TripoSplat",
        directory_name="TripoSplat",
        role="Primary local static Gaussian-splat reconstruction",
        repository="https://github.com/VAST-AI-Research/TripoSplat.git",
        license_name="MIT",
        license_url="https://github.com/VAST-AI-Research/TripoSplat/blob/main/LICENSE",
        python="3.11",
        vram_gb=8,
        capabilities=("image-to-splat",),
        notes=(
            "High-fidelity static visual reconstruction for background and "
            "non-deforming props. Produces PLY/SPLAT Gaussian data, not polygon "
            "geometry, UVs, a rig, or collision. Pair it with a simple authored "
            "collision proxy and use a conventional Blender mesh whenever the "
            "visible asset must deform or animate."
        ),
    ),
    "triposg": Model(
        key="triposg",
        name="TripoSG",
        directory_name="TripoSG",
        role="Restricted high-detail geometry prototype",
        repository="https://github.com/VAST-AI-Research/TripoSG.git",
        license_name=(
            "Mixed: MIT + Tencent community terms + BRIA RMBG-1.4 "
            "non-commercial"
        ),
        license_url="https://github.com/VAST-AI-Research/TripoSG/blob/main/LICENSE",
        terms_urls=(
            "https://github.com/VAST-AI-Research/TripoSG/blob/main/NOTICE",
            "https://github.com/VAST-AI-Research/TripoSG/blob/main/triposg/LICENSE",
            (
                "https://huggingface.co/briaai/RMBG-1.4/blob/"
                f"{RMBG_14_REVISION}/License.pdf"
            ),
        ),
        python="3.10",
        vram_gb=8,
        optional=True,
        acceptance_required=True,
        capabilities=("image-to-mesh",),
        notes=(
            "High-detail geometry prototype that outputs GLB but not a finished "
            "textured/PBR asset. Its NOTICE identifies Hunyuan/FlashVDM-derived "
            "code under community terms, and every inference downloads BRIA "
            "RMBG-1.4 under non-commercial/evaluation terms. Explicit backend "
            "only; do not use it for production or commercial work without a "
            "separate legal basis."
        ),
    ),
    "spar3d": Model(
        key="spar3d",
        name="SPAR3D",
        directory_name="stable-point-aware-3d",
        role="Preferred accepted local textured image-to-mesh",
        repository="https://github.com/Stability-AI/stable-point-aware-3d.git",
        license_name="Stability AI Community License",
        license_url=(
            "https://github.com/Stability-AI/"
            "stable-point-aware-3d/blob/main/LICENSE.md"
        ),
        terms_urls=(
            "https://huggingface.co/stabilityai/stable-point-aware-3d",
            "https://stability.ai/community-license",
            "https://stability.ai/use-policy",
        ),
        python="3.11",
        vram_gb=11,
        optional=True,
        acceptance_required=True,
        capabilities=("image-to-mesh", "texture"),
        notes=(
            "Best practical general local quality tier for this 16 GB machine. "
            "Hugging Face access is gated, and commercial use under the "
            "Stability AI Community License requires registration, aggregate "
            "affiliate annual revenue below US$1M, attribution, and ongoing "
            "AUP compliance; obtain an enterprise license above that threshold. "
            "Low-VRAM mode reduces the documented requirement to roughly 7 GB. "
            "Explicit backend only; never automatic."
        ),
    ),
    "partcrafter": Model(
        key="partcrafter",
        name="PartCrafter",
        directory_name="PartCrafter",
        role="Restricted specialist for separable multi-part geometry",
        repository="https://github.com/wgsxm/PartCrafter.git",
        license_name=(
            "Mixed: MIT + BRIA RMBG-1.4 non-commercial/evaluation "
            "+ TripoSG-derived model lineage"
        ),
        license_url="https://github.com/wgsxm/PartCrafter/blob/main/LICENSE",
        terms_urls=(
            (
                "https://huggingface.co/briaai/RMBG-1.4/blob/"
                f"{RMBG_14_REVISION}/License.pdf"
            ),
            "https://github.com/wgsxm/PartCrafter/blob/main/README.md",
            "https://github.com/VAST-AI-Research/TripoSG/blob/main/NOTICE",
            "https://github.com/VAST-AI-Research/TripoSG/blob/main/triposg/LICENSE",
        ),
        python="3.11",
        vram_gb=12,
        optional=True,
        acceptance_required=True,
        capabilities=("image-to-parts",),
        notes=(
            "Install only after reviewing every linked term. Upstream inference "
            "loads BRIA RMBG-1.4 and PartCrafter retains TripoSG-derived model "
            "components. Do not use it for production or commercial work "
            "without a separate legal basis."
        ),
    ),
    "skintokens": Model(
        key="skintokens",
        name="SkinTokens",
        directory_name="SkinTokens",
        role="General skeleton and skin-weight generation",
        repository="https://github.com/VAST-AI-Research/SkinTokens.git",
        license_name="MIT",
        license_url="https://github.com/VAST-AI-Research/SkinTokens/blob/main/LICENSE",
        python="3.11",
        vram_gb=14,
        optional=True,
        capabilities=("rig", "skin"),
        notes="Run alone on the 16 GB GPU and inspect deformation before export.",
    ),
    "unirig": Model(
        key="unirig",
        name="UniRig",
        directory_name="UniRig",
        role="Skeleton prediction helper",
        repository="https://github.com/VAST-AI-Research/UniRig.git",
        license_name="MIT",
        license_url="https://github.com/VAST-AI-Research/UniRig/blob/main/LICENSE",
        python="3.11",
        vram_gb=8,
        optional=True,
        capabilities=("skeleton",),
        notes=(
            "Not exposed as an auto-rig backend: the published skeleton command "
            "does not by itself create a skinned character."
        ),
    ),
}

CLOUD_PROVIDERS: dict[str, dict[str, str]] = {
    "fal-trellis2": {
        "name": "fal TRELLIS.2",
        "documentation": "https://fal.ai/models/fal-ai/trellis-2",
        "use": "static PBR reconstruction",
    },
    "fal-pixal3d": {
        "name": "fal Pixal3D",
        "documentation": "https://fal.ai/pixal3d",
        "use": "static PBR reconstruction",
    },
    "tripo": {
        "name": "Tripo API",
        "documentation": "https://platform.tripo3d.ai/docs/generation",
        "use": "topology, separated parts, or hosted rigging",
    },
    "meshy": {
        "name": "Meshy API",
        "documentation": "https://docs.meshy.ai/en/api/image-to-3d",
        "use": "image-to-3D and hosted rigging",
    },
}


def get_model(key: str) -> Model:
    try:
        return MODELS[key.casefold()]
    except KeyError as exc:
        choices = ", ".join(MODELS)
        raise Forge3DError(f"Unknown model {key!r}. Choose one of: {choices}") from exc


def catalog_rows() -> list[dict[str, Any]]:
    return [asdict(model) for model in MODELS.values()]


@dataclass(frozen=True)
class ModelRunResult:
    model: str
    revision: str
    artifact: Path
    command: tuple[str, ...]
    stdout: str
    stderr: str


class ModelManager:
    def __init__(
        self,
        *,
        root: Path | None = None,
        wsl: WSL | None = None,
        distro: str | None = None,
    ) -> None:
        self.root = (root or workspace_root()).resolve()
        self.toolkit_root = toolkit_root()
        self._wsl = wsl
        self.distro = distro
        self._models_root: str | None = None

    @property
    def wsl(self) -> WSL:
        if self._wsl is None:
            self._wsl = WSL(distro=self.distro)
        return self._wsl

    @property
    def models_root(self) -> str:
        configured = _clean_wsl_path(
            _environment_value("FORGE3D_WSL_MODELS_DIR")
        )
        if configured:
            return configured
        if self._models_root is None:
            result = self.wsl.run(["printenv", "HOME"], check=False)
            home = result.stdout.strip()
            if result.returncode or not home.startswith("/"):
                raise ToolNotFoundError(
                    "Could not determine the WSL home directory. Set "
                    "FORGE3D_WSL_MODELS_DIR to an absolute WSL path."
                )
            self._models_root = f"{home.rstrip('/')}/.local/share/forge3d/models"
        return self._models_root

    def model_dir(self, model: Model) -> str:
        return f"{self.models_root}/{model.directory_name}"

    def is_installed(self, model: Model) -> bool:
        result = self.wsl.run(
            ["test", "-x", f"{self.model_dir(model)}/.venv/bin/python"],
            check=False,
        )
        return result.returncode == 0

    def is_ready(self, model: Model) -> bool:
        if not self.is_installed(model):
            return False
        if model.acceptance_required and not self.license_accepted(model):
            return False
        result = self.wsl.run(
            [
                "test",
                "-f",
                f"{self.model_dir(model)}/.forge3d-install-complete",
            ],
            check=False,
        )
        return result.returncode == 0

    def revision(self, model: Model) -> str:
        if not self.is_installed(model):
            return "not-installed"
        result = self.wsl.run(
            ["git", "-C", self.model_dir(model), "rev-parse", "HEAD"],
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def install_plan(self, model: Model, revision: str = "main") -> str:
        if not _SAFE_REVISION.fullmatch(revision):
            raise Forge3DError(f"Unsafe git revision: {revision!r}")
        target = self.model_dir(model)
        quoted_target = shlex.quote(target)
        repo = shlex.quote(model.repository)
        commands = [
            "set -euo pipefail",
            (
                f"if [ -e {quoted_target} ] && "
                f"[ ! -d {quoted_target}/.git ]; then "
                f"echo 'Target exists but is not a git checkout' >&2; exit 2; fi"
            ),
            f"mkdir -p {shlex.quote(self.models_root)}",
            (
                f"if [ ! -d {quoted_target}/.git ]; then "
                f"git clone --filter=blob:none {repo} {quoted_target}; fi"
            ),
            f"git -C {quoted_target} fetch --tags origin",
        ]
        if revision == "main":
            commands.extend(
                [
                    f"git -C {quoted_target} checkout main",
                    f"git -C {quoted_target} pull --ff-only origin main",
                ]
            )
        else:
            commands.append(
                f"git -C {quoted_target} checkout --detach {shlex.quote(revision)}"
            )
        commands.extend(
            [
                "command -v uv >/dev/null || "
                "{ echo 'uv is required in WSL: https://docs.astral.sh/uv/' >&2; "
                "exit 3; }",
                f"cd {quoted_target}",
                "rm -f .forge3d-install-complete",
                f"uv venv --python {shlex.quote(model.python)} .venv",
                *_install_commands(
                    model,
                    triposplat_runner=self._triposplat_runner(model),
                    triposg_shim=self._triposg_shim(model),
                    triposg_constraints=self._triposg_constraints(model),
                ),
                "git rev-parse HEAD > .forge3d-install-complete",
                "git rev-parse HEAD",
            ]
        )
        return "\n".join(commands)

    def _triposplat_runner(self, model: Model) -> str | None:
        if model.key != "triposplat":
            return None
        runner = (
            self.toolkit_root
            / "scripts"
            / "wsl"
            / "triposplat_inference.py"
        )
        if not runner.is_file():
            raise ToolNotFoundError(
                f"TripoSplat inference runner is missing: {runner}"
            )
        return self.wsl.path(runner)

    def _triposg_shim(self, model: Model) -> str | None:
        if model.key != "triposg":
            return None
        shim = self.toolkit_root / "scripts" / "wsl" / "diso_shim.py"
        if not shim.is_file():
            raise ToolNotFoundError(
                f"TripoSG compatibility shim is missing: {shim}"
            )
        return self.wsl.path(shim)

    def _triposg_constraints(self, model: Model) -> str | None:
        if model.key != "triposg":
            return None
        constraints = (
            self.toolkit_root
            / "scripts"
            / "wsl"
            / "triposg-constraints.txt"
        )
        if not constraints.is_file():
            raise ToolNotFoundError(
                f"TripoSG constraints are missing: {constraints}"
            )
        return self.wsl.path(constraints)

    def install(
        self,
        model: Model,
        *,
        accept_license: bool = False,
        revision: str = "main",
        timeout: float = 7_200,
    ) -> CommandResult:
        if model.acceptance_required and not (
            accept_license or self.license_accepted(model)
        ):
            raise Forge3DError(
                f"{model.name} requires explicit acceptance of "
                f"{model.license_name}. Review {model.license_url}, then rerun "
                "with --accept-license."
            )
        if accept_license:
            self.record_license_acceptance(model)
        return self.wsl.shell(
            self.install_plan(model, revision), timeout=timeout, check=True
        )

    def record_license_acceptance(self, model: Model) -> None:
        directory = self.root / ".forge3d" / "licenses"
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "model": model.key,
            "license": model.license_name,
            "license_url": model.license_url,
            "terms_urls": list(model.terms_urls),
            "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (directory / f"{model.key}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )

    def license_accepted(self, model: Model) -> bool:
        path = self.root / ".forge3d" / "licenses" / f"{model.key}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False
        return (
            record.get("model") == model.key
            and record.get("license") == model.license_name
            and record.get("license_url") == model.license_url
            and record.get("terms_urls") == list(model.terms_urls)
        )

    def free_vram_mib(self) -> int | None:
        result = self.wsl.shell(
            "nvidia-smi --query-gpu=memory.free "
            "--format=csv,noheader,nounits",
            check=False,
        )
        if result.returncode:
            return None
        values: list[int] = []
        for line in result.stdout.splitlines():
            try:
                values.append(int(line.strip()))
            except ValueError:
                continue
        return max(values) if values else None

    def run_image(
        self,
        model: Model,
        image: Path,
        output_dir: Path,
        *,
        faces: int | None = None,
        parts: int = 4,
        low_vram: bool = False,
        gaussians: int = 262_144,
        ignore_vram: bool = False,
        timeout: float = 3_600,
    ) -> ModelRunResult:
        if not any(
            capability in model.capabilities
            for capability in ("image-to-mesh", "image-to-parts", "image-to-splat")
        ):
            raise Forge3DError(f"{model.name} is not an image-derived asset backend")
        self._require_license(model)
        image = image.expanduser().resolve()
        if not image.is_file():
            raise Forge3DError(f"Reference image does not exist: {image}")
        if model.key == "triposplat" and (
            not 32_768 <= gaussians <= 262_144 or gaussians % 32
        ):
            raise Forge3DError(
                "TripoSplat gaussians must be 32768-262144 and a multiple of 32"
            )
        self._require_installed(model)
        self._check_vram(model, ignore=ignore_vram or low_vram)

        output_dir = output_dir.expanduser().resolve()
        if output_dir.exists():
            raise Forge3DError(
                f"Output already exists; choose a new versioned directory: {output_dir}"
            )
        output_dir.mkdir(parents=True)
        wsl_image = self.wsl.path(image)
        wsl_output = self.wsl.path(output_dir)
        model_dir = self.model_dir(model)
        command, expected = _image_command(
            model,
            model_dir=model_dir,
            image=wsl_image,
            output=wsl_output,
            tag=slugify(output_dir.name),
            faces=faces,
            parts=parts,
            low_vram=low_vram,
            gaussians=gaussians,
        )
        result = self.wsl.run(command, cwd=model_dir, timeout=timeout)

        if model.key == "partcrafter":
            source = f"{model_dir}/results/{slugify(output_dir.name)}"
            self.wsl.shell(
                f"cp -a {shlex.quote(source)}/. {shlex.quote(wsl_output)}/",
                timeout=300,
            )
        artifact = _discover_artifact(output_dir, expected)
        return ModelRunResult(
            model=model.key,
            revision=self.revision(model),
            artifact=artifact,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def rig(
        self,
        model: Model,
        mesh: Path,
        output: Path,
        *,
        use_skeleton: bool = False,
        ignore_vram: bool = False,
        timeout: float = 3_600,
    ) -> ModelRunResult:
        if "rig" not in model.capabilities:
            raise Forge3DError(f"{model.name} is not a rigging backend")
        self._require_license(model)
        mesh = mesh.expanduser().resolve()
        if not mesh.is_file():
            raise Forge3DError(f"Mesh does not exist: {mesh}")
        self._require_installed(model)
        self._check_vram(model, ignore=ignore_vram)
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        model_dir = self.model_dir(model)
        wsl_mesh = self.wsl.path(mesh)
        wsl_output = self.wsl.path(output)
        if model.key == "skintokens":
            command = [
                ".venv/bin/python",
                "demo.py",
                "--input",
                wsl_mesh,
                "--output",
                wsl_output,
                "--use_transfer",
            ]
            if use_skeleton:
                command.append("--use_skeleton")
        else:
            command = [
                "bash",
                "launch/inference/generate_skeleton.sh",
                "--input",
                wsl_mesh,
                "--output",
                wsl_output,
            ]
        result = self.wsl.run(command, cwd=model_dir, timeout=timeout)
        if not output.is_file():
            raise Forge3DError(
                f"{model.name} completed but did not create the expected file: {output}"
            )
        return ModelRunResult(
            model=model.key,
            revision=self.revision(model),
            artifact=output,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _require_license(self, model: Model) -> None:
        if model.acceptance_required and not self.license_accepted(model):
            raise Forge3DError(
                f"{model.name} requires explicit acceptance of "
                f"{model.license_name}. Review {model.license_url}, then run "
                f"`forge3d models install {model.key} --accept-license`."
            )

    def _require_installed(self, model: Model) -> None:
        if not self.is_ready(model):
            raise Forge3DError(
                f"{model.name} is not fully installed or its recorded terms "
                "are stale. Run: "
                f"forge3d models install {model.key}"
            )

    def _check_vram(self, model: Model, *, ignore: bool) -> None:
        free = self.free_vram_mib()
        required = model.vram_gb * 1024
        if free is None:
            if ignore:
                return
            raise Forge3DError(
                "Could not query free GPU memory inside WSL. Check CUDA with "
                "`wsl nvidia-smi`, or rerun with --ignore-vram."
            )
        if free < required and not ignore:
            raise Forge3DError(
                f"{model.name} expects about {model.vram_gb} GB VRAM, but only "
                f"{free / 1024:.1f} GB is currently free. Close GPU-heavy apps, "
                "choose a smaller backend, or explicitly use --ignore-vram."
            )


def cloud_estimate(provider: str, inputs: Iterable[Path]) -> dict[str, Any]:
    try:
        details = CLOUD_PROVIDERS[provider]
    except KeyError as exc:
        choices = ", ".join(CLOUD_PROVIDERS)
        raise Forge3DError(
            f"Unknown cloud provider {provider!r}. Choose one of: {choices}"
        ) from exc
    described: list[dict[str, Any]] = []
    for value in inputs:
        path = value.expanduser().resolve()
        if not path.is_file():
            raise Forge3DError(f"Potential upload does not exist: {path}")
        described.append({"path": str(path), "size_bytes": path.stat().st_size})
    return {
        "provider": provider,
        **details,
        "approval_required": True,
        "upload_performed": False,
        "inputs_that_would_be_uploaded": described,
        "price_estimate": (
            "Not fetched. Check the linked provider page immediately before "
            "approval because usage pricing changes."
        ),
        "next_step": (
            "Check current price and terms, obtain explicit approval for these "
            "files and one job, then run `forge3d models cloud-run tripo ... "
            "--approve-upload`. Only Tripo has an executable fallback."
        ),
    }


def run_tripo_cloud(
    image: Path,
    output: Path,
    *,
    approve_upload: bool,
    model_version: str = "P1-20260311",
    faces: int | None = None,
    texture_quality: str = "detailed",
    texture: bool = True,
    pbr: bool = True,
    timeout: float = 3_600,
    runner: CommandRunner | None = None,
    uv_executable: str | None = None,
) -> dict[str, Any]:
    if not approve_upload:
        raise Forge3DError(
            "Cloud upload refused. Review the estimate and explicitly approve "
            "this one job with --approve-upload."
        )
    if not _environment_value("TRIPO_API_KEY"):
        raise Forge3DError(
            "TRIPO_API_KEY is not set. Store the key in the environment; do not "
            "put it in a command, prompt, or project file."
        )

    source = image.expanduser().resolve()
    if not source.is_file():
        raise Forge3DError(f"Image does not exist: {source}")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise Forge3DError("Tripo image uploads are limited to 20 MB")
    destination = output.expanduser().resolve()
    if destination.exists():
        raise Forge3DError(
            f"Cloud output already exists: {destination}. Choose a new version."
        )
    if model_version not in TRIPO_MODEL_VERSIONS:
        choices = ", ".join(TRIPO_MODEL_VERSIONS)
        raise Forge3DError(f"Unsupported Tripo model version. Choose one of: {choices}")
    if faces is not None and not 48 <= faces <= 20_000:
        raise Forge3DError("Tripo --faces must be between 48 and 20000")
    if texture_quality not in {"standard", "detailed"}:
        raise Forge3DError("Tripo texture quality must be standard or detailed")
    if timeout <= 0:
        raise Forge3DError("Cloud timeout must be greater than zero")

    uv = uv_executable or _find_uv()
    script = toolkit_root() / "scripts" / "tripo_cloud.py"
    if not script.is_file():
        raise Forge3DError(f"Tripo cloud runner is missing: {script}")
    command = [
        uv,
        "run",
        "--no-project",
        "--with",
        f"tripo3d=={TRIPO_SDK_VERSION}",
        "python",
        str(script),
        str(source),
        "--output-dir",
        str(destination),
        "--approve-upload",
        "--model-version",
        model_version,
        "--texture-quality",
        texture_quality,
        "--timeout",
        str(timeout),
    ]
    if faces is not None:
        command.extend(["--faces", str(faces)])
    if not texture:
        command.append("--no-texture")
    elif not pbr:
        command.append("--no-pbr")

    (runner or CommandRunner()).run(command, timeout=timeout + 300)
    marker = destination / "cloud-result.json"
    if not marker.is_file():
        raise Forge3DError(
            f"Tripo completed without a result manifest: {marker}"
        )
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Forge3DError(f"Could not read Tripo result manifest: {marker}") from exc
    if data.get("status") != "success" or not data.get("files"):
        raise Forge3DError(f"Tripo result manifest is incomplete: {marker}")
    return data


def _find_uv() -> str:
    discovered = executable("uv")
    if discovered:
        return discovered
    suffixes = ("uv.exe", "uv") if os.name == "nt" else ("uv",)
    for suffix in suffixes:
        candidate = Path.home() / ".local" / "bin" / suffix
        if candidate.is_file():
            return str(candidate)
    raise ToolNotFoundError(
        "uv was not found. Run scripts/setup.ps1 before using the Tripo fallback."
    )


def _environment_value(name: str) -> str | None:
    return os.environ.get(name)


def _clean_wsl_path(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith("/"):
        raise Forge3DError(
            "FORGE3D_WSL_MODELS_DIR must be an absolute Linux path inside WSL"
        )
    return value.rstrip("/")


def _install_commands(
    model: Model,
    *,
    triposplat_runner: str | None = None,
    triposg_shim: str | None = None,
    triposg_constraints: str | None = None,
) -> list[str]:
    python = ".venv/bin/python"
    pip = f"uv pip install --python {python}"
    torch = (
        f"{pip} torch=={PYTORCH_VERSION} "
        f"torchvision=={TORCHVISION_VERSION} "
        f"--index-url {PYTORCH_CUDA_INDEX}"
    )
    common = [torch, f"{pip} -r requirements.txt"]
    if model.key == "triposg":
        if not triposg_shim or not triposg_constraints:
            raise ToolNotFoundError(
                "TripoSG compatibility shim and constraints are required"
            )
        quoted_shim = shlex.quote(triposg_shim)
        quoted_constraints = shlex.quote(triposg_constraints)
        return [
            torch,
            "grep -iv '^diso\\b' requirements.txt > .forge3d-requirements.txt",
            (
                f"{pip} -r .forge3d-requirements.txt "
                f"-c {quoted_constraints}"
            ),
            (
                f"site_dir=$({python} -c "
                + shlex.quote("import site; print(site.getsitepackages()[0])")
                + ")"
            ),
            'mkdir -p "$site_dir/diso"',
            f'cp {quoted_shim} "$site_dir/diso/__init__.py"',
            (
                f"{python} -c "
                + shlex.quote(
                    "import torch, diso; "
                    "print('torch', torch.__version__, "
                    "'cuda', torch.cuda.is_available())"
                )
            ),
            (
                "HF_HUB_DISABLE_TELEMETRY=1 "
                f"{python} -c "
                + shlex.quote(
                    "from huggingface_hub import snapshot_download; "
                    "snapshot_download('VAST-AI/TripoSG', "
                    f"revision='{TRIPOSG_WEIGHTS_REVISION}', "
                    "local_dir='pretrained_weights/TripoSG'); "
                    "snapshot_download('briaai/RMBG-1.4', "
                    f"revision='{RMBG_14_REVISION}', "
                    "local_dir='pretrained_weights/RMBG-1.4')"
                )
            ),
        ]
    if model.key == "triposplat":
        if not triposplat_runner:
            raise ToolNotFoundError("TripoSplat inference runner is required")
        quoted_runner = shlex.quote(triposplat_runner)
        return [
            torch,
            f"{pip} numpy safetensors pillow tqdm huggingface_hub",
            f"cp {quoted_runner} .forge3d_run.py",
            (
                "HF_HUB_DISABLE_TELEMETRY=1 "
                f"{python} -c "
                + shlex.quote(
                    "from huggingface_hub import snapshot_download; "
                    "snapshot_download('VAST-AI/TripoSplat', local_dir='ckpts/')"
                )
            ),
        ]
    if model.key == "spar3d":
        return [
            f"{pip} setuptools==69.5.1 wheel",
            *common,
            (
                "echo 'SPAR3D weights are gated. Request access and run "
                "huggingface-cli login before inference.'"
            ),
        ]
    if model.key == "partcrafter":
        return [
            (
                f"{pip} torch==2.5.1 torchvision==0.20.1 "
                "torchaudio==2.5.1 --index-url "
                "https://download.pytorch.org/whl/cu124"
            ),
            "PATH=\"$PWD/.venv/bin:$PATH\" bash settings/setup.sh",
        ]
    if model.key == "skintokens":
        return [
            (
                f"{pip} torch==2.7.0 torchvision==0.22.0 "
                "torchaudio==2.7.0 --index-url "
                f"{PYTORCH_CUDA_INDEX}"
            ),
            f"{pip} -r requirements.txt",
            f"{pip} flash-attn --no-build-isolation",
            f"{python} download.py --model",
        ]
    if model.key == "unirig":
        return [
            (
                f"{pip} torch==2.5.1 torchvision==0.20.1 "
                "--index-url https://download.pytorch.org/whl/cu124"
            ),
            f"{pip} -r requirements.txt",
            f"{pip} spconv-cu124 numpy==1.26.4",
            (
                f"{pip} torch-scatter torch-cluster -f "
                "https://data.pyg.org/whl/torch-2.5.1+cu124.html "
                "--no-cache-dir"
            ),
        ]
    raise AssertionError(model.key)


def _image_command(
    model: Model,
    *,
    model_dir: str,
    image: str,
    output: str,
    tag: str,
    faces: int | None,
    parts: int,
    low_vram: bool,
    gaussians: int,
) -> tuple[list[str], Path | None]:
    if model.key == "triposplat":
        return [
            ".venv/bin/python",
            ".forge3d_run.py",
            image,
            "--output-dir",
            output,
            "--gaussians",
            str(gaussians),
        ], Path("candidate.ply")
    if model.key == "triposg":
        target = f"{output}/candidate.glb"
        command = [
            ".venv/bin/python",
            "-m",
            "scripts.inference_triposg",
            "--image-input",
            image,
            "--output-path",
            target,
        ]
        if faces is not None:
            command.extend(["--faces", str(faces)])
        return command, Path("candidate.glb")
    if model.key == "spar3d":
        command = [
            ".venv/bin/python",
            "run.py",
            image,
            "--output-dir",
            output,
        ]
        if low_vram:
            command.append("--low-vram-mode")
        return command, None
    if model.key == "partcrafter":
        command = [
            ".venv/bin/python",
            "scripts/inference_partcrafter.py",
            "--image_path",
            image,
            "--num_parts",
            str(parts),
            "--tag",
            tag,
            "--rmbg",
            "--render",
        ]
        return command, None
    raise Forge3DError(f"No image command is defined for {model.name}")


def _discover_artifact(output_dir: Path, expected: Path | None) -> Path:
    if expected is not None:
        candidate = output_dir / expected
        if candidate.is_file():
            return candidate.resolve()
    extensions = {".glb", ".gltf", ".fbx", ".obj", ".ply"}
    choices = [
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in extensions
    ]
    if not choices:
        raise Forge3DError(
            f"Model inference completed but no mesh was found in {output_dir}"
        )
    return max(choices, key=lambda path: path.stat().st_mtime_ns).resolve()

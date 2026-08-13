param(
    [string]$Blender = $env:BLENDER_EXECUTABLE,
    [switch]$KeepArtifacts
)

# Blender occasionally writes deprecation notices to stderr while returning
# success. Native stderr must not become a terminating PowerShell error; every
# Blender call below checks its process exit code explicitly.
$ErrorActionPreference = "Continue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$BlenderRoot = Split-Path -Parent $Here
$TaskRunner = Join-Path $BlenderRoot "forge3d_task.py"
$RigFixture = Join-Path $Here "create_rig_fixture.py"
$HumanoidFixture = Join-Path $Here "create_humanoid_fixture.py"
$BoneMap = Join-Path $Here "fixtures\simple_bone_map.json"
$Work = Join-Path ([System.IO.Path]::GetTempPath()) (
    "forge3d-blender-smoke-" + [guid]::NewGuid().ToString("N")
)
$Succeeded = $false

if (-not $Blender) {
    $command = Get-Command blender -ErrorAction SilentlyContinue
    if ($command) { $Blender = $command.Source }
}
if (-not $Blender) {
    $standalone = Get-ChildItem "C:\Program Files\Blender Foundation\Blender *\blender.exe" `
        -File -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($standalone) { $Blender = $standalone.FullName }
}
if (-not $Blender) {
    $steam = "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
    if (Test-Path -LiteralPath $steam) { $Blender = $steam }
}

if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) {
    throw "Blender executable was not found: $Blender"
}

New-Item -ItemType Directory -Path $Work | Out-Null

function Invoke-Task {
    param([string[]]$TaskArguments)
    $Output = & $Blender --background --factory-startup `
        --python $TaskRunner -- @TaskArguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $Output | Write-Host
        throw "Forge3D Blender task failed with exit code $LASTEXITCODE"
    }
    $Result = $Output | Where-Object {
        "$_".StartsWith("FORGE3D_RESULT=")
    } | Select-Object -Last 1
    if (-not $Result) {
        $Output | Write-Host
        throw "Task emitted no FORGE3D_RESULT line"
    }
}

try {
    $Generated = Join-Path $Work "01_generated.blend"
    $RequestPath = Join-Path $Work "request.json"
    $Request = @{
        task = "procedural"
        args = @{
            recipe = "crate"
            seed = 42
            output = $Generated
            report = (Join-Path $Work "01_generated.json")
        }
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($RequestPath, $Request)
    $RequestOutput = & $Blender --background --factory-startup `
        --python $TaskRunner -- --request $RequestPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        $RequestOutput | Write-Host
        throw "JSON request bridge failed"
    }

    $Normalized = Join-Path $Work "02_normalized.blend"
    Invoke-Task @(
        "normalize", "--input", $Generated, "--ground", "--origin", "base",
        "--target-size", "1.5", "--output", $Normalized,
        "--report", (Join-Path $Work "02_normalized.json")
    )

    $Repaired = Join-Path $Work "03_repaired.blend"
    Invoke-Task @(
        "repair", "--input", $Normalized, "--apply-modifiers",
        "--output", $Repaired,
        "--report", (Join-Path $Work "03_repaired.json")
    )

    $Unwrapped = Join-Path $Work "04_unwrapped.blend"
    Invoke-Task @(
        "unwrap", "--input", $Repaired, "--method", "smart",
        "--output", $Unwrapped,
        "--report", (Join-Path $Work "04_unwrapped.json")
    )

    $Material = Join-Path $Work "05_material.blend"
    Invoke-Task @(
        "material", "--input", $Unwrapped, "--material-name", "SmokePBR",
        "--base-color", "0.18,0.32,0.55,1", "--roughness", "0.38",
        "--replace-materials", "--output", $Material,
        "--report", (Join-Path $Work "05_material.json")
    )

    $Lods = Join-Path $Work "06_lods.blend"
    Invoke-Task @(
        "lods", "--input", $Material, "--ratios", "0.5,0.2",
        "--output", $Lods,
        "--report", (Join-Path $Work "06_lods.json")
    )

    $Collision = Join-Path $Work "07_collision.blend"
    Invoke-Task @(
        "collision", "--input", $Lods, "--mode", "convex",
        "--output", $Collision,
        "--report", (Join-Path $Work "07_collision.json")
    )

    $Preview = Join-Path $Work "preview.png"
    Invoke-Task @(
        "turntable", "--input", $Collision, "--objects", "Forge3D_Crate",
        "--output", $Preview, "--resolution", "64",
        "--report", (Join-Path $Work "08_preview.json")
    )

    $Glb = Join-Path $Work "model.glb"
    Invoke-Task @(
        "export-glb", "--input", $Collision, "--output", $Glb,
        "--apply-modifiers", "--report", (Join-Path $Work "09_export.json")
    )
    Invoke-Task @(
        "validate", "--input", $Collision, "--require-uv",
        "--report", (Join-Path $Work "10_validate.json")
    )

    $CaseGenerated = Join-Path $Work "10a_equipment_case_generated.blend"
    $CaseGenerationReport = Join-Path $Work "10a_equipment_case_generated.json"
    Invoke-Task @(
        "procedural", "--recipe", "medical-case",
        "--output", $CaseGenerated,
        "--report", $CaseGenerationReport
    )
    $CaseGeneration = Get-Content -Raw -LiteralPath $CaseGenerationReport |
        ConvertFrom-Json
    $CaseMaterials = @(
        $CaseGeneration.metrics.objects |
            ForEach-Object { $_.materials } |
            Select-Object -Unique
    )
    $CaseShell = $CaseGeneration.metrics.objects |
        Where-Object { $_.custom_properties.forge3d_role -like "primary_shell*" } |
        Select-Object -First 1
    if (
        $CaseGeneration.metrics.objects.Count -ne 5 -or
        $CaseMaterials.Count -ne 5 -or
        -not $CaseShell -or
        $CaseShell.dimensions[0] -le ($CaseShell.dimensions[2] * 1.35) -or
        [math]::Abs($CaseGeneration.metrics.bounds.min[2]) -gt 0.00001
    ) {
        throw "Procedural medical-case structure, horizontal silhouette, material slots, or grounding is invalid"
    }

    $CaseSource = Join-Path $Work "10b_equipment_case_source.blend"
    Invoke-Task @(
        "unwrap", "--input", $CaseGenerated, "--method", "smart",
        "--output", $CaseSource,
        "--report", (Join-Path $Work "10b_equipment_case_unwrap.json")
    )
    $CasePreview = Join-Path $Work "10c_equipment_case_preview.png"
    Invoke-Task @(
        "turntable", "--input", $CaseSource,
        "--output", $CasePreview, "--resolution", "64",
        "--report", (Join-Path $Work "10c_equipment_case_preview.json")
    )
    $CaseGlb = Join-Path $Work "10d_equipment_case.glb"
    Invoke-Task @(
        "export-glb", "--input", $CaseSource, "--output", $CaseGlb,
        "--apply-modifiers",
        "--report", (Join-Path $Work "10d_equipment_case_export.json")
    )
    Invoke-Task @(
        "validate", "--input", $CaseSource, "--require-uv", "--strict-manifold",
        "--report", (Join-Path $Work "10e_equipment_case_validation.json")
    )

    $RigBlend = Join-Path $Work "rig_fixture.blend"
    & $Blender --background --factory-startup --python $RigFixture `
        -- --output $RigBlend | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create rig fixture"
    }
    Invoke-Task @(
        "rig-validate", "--input", $RigBlend, "--objects", "TargetRig",
        "--report", (Join-Path $Work "11_rig.json")
    )
    Invoke-Task @(
        "animation-validate", "--input", $RigBlend, "--require-loop",
        "--report", (Join-Path $Work "12_animation.json")
    )
    $Retargeted = Join-Path $Work "retargeted.blend"
    Invoke-Task @(
        "retarget", "--input", $RigBlend,
        "--source-armature", "SourceRig", "--target-armature", "TargetRig",
        "--bone-map", $BoneMap, "--bake", "--clear-constraints",
        "--frame-start", "1", "--frame-end", "10",
        "--action-name", "RetargetedWave", "--output", $Retargeted,
        "--report", (Join-Path $Work "13_retarget.json")
    )
    Invoke-Task @(
        "animation-validate", "--input", $Retargeted,
        "--actions", "RetargetedWave",
        "--report", (Join-Path $Work "14_retarget_animation.json")
    )
    $RetargetRigReport = Join-Path $Work "15_retarget_rig.json"
    Invoke-Task @(
        "rig-validate", "--input", $Retargeted, "--objects", "TargetRig",
        "--report", $RetargetRigReport
    )
    $RetargetRig = Get-Content -Raw -LiteralPath $RetargetRigReport |
        ConvertFrom-Json
    if ($RetargetRig.metrics.per_armature.TargetRig.pose_constraints -ne 1) {
        throw "Retarget cleanup removed or leaked constraints on the target rig"
    }

    $HumanoidMesh = Join-Path $Work "humanoid_proxy.blend"
    & $Blender --background --factory-startup --python $HumanoidFixture `
        -- --output $HumanoidMesh | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create humanoid rig fixture"
    }
    $AutoRigged = Join-Path $Work "rigify_humanoid.blend"
    Invoke-Task @(
        "rig-humanoid", "--input", $HumanoidMesh,
        "--rig-name", "Forge3D_Rig", "--output", $AutoRigged,
        "--report", (Join-Path $Work "16_rigify.json")
    )
    Invoke-Task @(
        "rig-validate", "--input", $AutoRigged,
        "--objects", "Forge3D_Rig",
        "--report", (Join-Path $Work "17_rigify_validation.json")
    )
    $RigifyGlb = Join-Path $Work "rigify_humanoid.glb"
    Invoke-Task @(
        "export-glb", "--input", $AutoRigged,
        "--armature", "Forge3D_Rig", "--deform-bones-only",
        "--output", $RigifyGlb,
        "--report", (Join-Path $Work "18_rigify_export.json")
    )
    $RigifyExport = Get-Content -Raw -LiteralPath (
        Join-Path $Work "18_rigify_export.json"
    ) | ConvertFrom-Json
    if (
        $RigifyExport.metrics.export_armature -ne "Forge3D_Rig" -or
        $RigifyExport.metrics.objects_considered -ne 2 -or
        -not $RigifyExport.metrics.export_options.export_def_bones
    ) {
        throw "Rigify GLB export was not limited to the deform-rig closure"
    }

    foreach ($Expected in @(
        $Collision, $Preview, $Glb, $CaseSource, $CasePreview, $CaseGlb,
        $Retargeted, $AutoRigged, $RigifyGlb
    )) {
        if (-not (Test-Path -LiteralPath $Expected -PathType Leaf)) {
            throw "Expected smoke-test output is missing: $Expected"
        }
        if ((Get-Item -LiteralPath $Expected).Length -eq 0) {
            throw "Expected smoke-test output is empty: $Expected"
        }
    }

    $Succeeded = $true
    Write-Host "Forge3D Blender smoke tests passed."
    if ($KeepArtifacts) {
        Write-Host "Artifacts: $Work"
    }
    else {
        Write-Host "Temporary artifacts verified; cleaning: $Work"
    }
}
finally {
    if ($Succeeded -and -not $KeepArtifacts) {
        $ResolvedWork = [System.IO.Path]::GetFullPath($Work)
        $ResolvedTemp = [System.IO.Path]::GetFullPath(
            [System.IO.Path]::GetTempPath()
        )
        if (-not $ResolvedWork.StartsWith(
            $ResolvedTemp,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Refusing to clean a smoke directory outside the system temp path"
        }
        Remove-Item -LiteralPath $ResolvedWork -Recurse -Force
    }
    elseif (-not $Succeeded) {
        Write-Host "Failed smoke artifacts retained at: $Work"
    }
}

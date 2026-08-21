[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipCli
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$desktopRoot = Join-Path $repoRoot "desktop"
$runtimeRoot = Join-Path $desktopRoot "runtime"
$packageRoot = Join-Path $desktopRoot "dist-package"
$temporaryRoot = Join-Path $repoRoot ".tmp\desktop-build"

foreach ($command in @("uv", "npm")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required to build Forge3D."
    }
}

if (-not $SkipCli) {
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    & uv run --with "pyinstaller==6.19.0" pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name forge3d `
        --paths (Join-Path $repoRoot "src") `
        --distpath $runtimeRoot `
        --workpath (Join-Path $temporaryRoot "work") `
        --specpath (Join-Path $temporaryRoot "spec") `
        (Join-Path $repoRoot "scripts\forge3d_entry.py")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build forge3d.exe." }
}

$npmSteps = [System.Collections.Generic.List[string]]::new()
$npmSteps.Add("npm ci")
if (-not $SkipTests) {
    $npmSteps.Add("npm test")
}
$npmSteps.Add("npm run dist")

if ($env:OS -eq "Windows_NT" -and $desktopRoot.StartsWith("\\")) {
    # cmd.exe cannot use a UNC current directory. pushd maps the share to a
    # temporary drive for this child process and removes it when cmd exits.
    $npmCommand = 'pushd "{0}" && {1} && popd' -f $desktopRoot, ($npmSteps -join " && ")
    & cmd.exe /d /s /c $npmCommand
    if ($LASTEXITCODE -ne 0) { throw "Forge3D desktop dependency, test, or package step failed." }
}
else {
    Push-Location $desktopRoot
    try {
        foreach ($npmStep in $npmSteps) {
            $npmArguments = $npmStep.Substring(4).Split(" ")
            & npm @npmArguments
            if ($LASTEXITCODE -ne 0) { throw "Forge3D desktop step failed: $npmStep" }
        }
    }
    finally {
        Pop-Location
    }
}

$assetName = "Forge3D-0.2.1-windows-x64.zip"
$asset = Join-Path $packageRoot $assetName
if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
    throw "Forge3D release archive was not created: $asset"
}
$assetInfo = Get-Item -LiteralPath $asset
$manifest = [ordered]@{
    schemaVersion = 1
    product = "forge3d"
    version = "0.2.1"
    platform = "windows-x64"
    minimumInstrumentaVersion = "0.8.0"
    installStrategy = "managed-bundle"
    bundle = [ordered]@{
        asset = $assetName
        size = $assetInfo.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash.ToLowerInvariant()
        entry = "Forge3D.exe"
    }
}
$manifestPath = Join-Path $packageRoot "instrumenta-release.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($manifestPath, "$manifestJson`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "Forge3D release ready: $asset"
Write-Host "Instrumenta manifest: $manifestPath"
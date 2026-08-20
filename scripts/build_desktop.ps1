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

Push-Location $desktopRoot
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    if (-not $SkipTests) {
        & npm test
        if ($LASTEXITCODE -ne 0) { throw "Forge3D desktop tests failed." }
    }
    & npm run dist
    if ($LASTEXITCODE -ne 0) { throw "Forge3D desktop packaging failed." }
}
finally {
    Pop-Location
}

$assetName = "Forge3D-0.2.0-windows-x64.zip"
$asset = Join-Path $packageRoot $assetName
if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
    throw "Forge3D release archive was not created: $asset"
}
$assetInfo = Get-Item -LiteralPath $asset
$manifest = [ordered]@{
    schemaVersion = 1
    product = "forge3d"
    version = "0.2.0"
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
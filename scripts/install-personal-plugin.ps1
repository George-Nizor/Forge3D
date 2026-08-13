[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$sourcePlugin = Join-Path $repoRoot "plugins\forge3d"
$pluginParent = Join-Path $env:USERPROFILE "plugins"
$targetPlugin = Join-Path $pluginParent "forge3d"
$marketplace = Join-Path $env:USERPROFILE ".agents\plugins\marketplace.json"
$pythonExe = $null
$uvExe = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
$creator = Join-Path $env:USERPROFILE ".codex\skills\.system\plugin-creator\scripts\create_basic_plugin.py"
$validator = Join-Path $env:USERPROFILE ".codex\skills\.system\plugin-creator\scripts\validate_plugin.py"

if (-not (Test-Path -LiteralPath $sourcePlugin)) {
    throw "Forge3D plugin source is missing: $sourcePlugin"
}
if (-not (Test-Path -LiteralPath $creator)) {
    throw "Codex plugin creator is missing: $creator"
}
if (-not (Test-Path -LiteralPath $uvExe)) {
    throw "uv is missing: $uvExe"
}
$blenderFromPath = Get-Command blender -ErrorAction SilentlyContinue
$blenderCandidates = @(
    $env:BLENDER_EXECUTABLE,
    $(if ($blenderFromPath) { $blenderFromPath.Source }),
    "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
    "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if ($blenderCandidates) {
    $blenderRoot = Split-Path -Parent $blenderCandidates[0]
    $embeddedPython = Get-ChildItem -LiteralPath $blenderRoot -Filter python.exe -Recurse -File `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($embeddedPython) { $pythonExe = $embeddedPython.FullName }
}
if (-not $pythonExe) {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $pythonExe) {
    throw "Python was not found for Codex plugin scaffolding."
}

$resolvedParent = [System.IO.Path]::GetFullPath($pluginParent)
$resolvedTarget = [System.IO.Path]::GetFullPath($targetPlugin)
$expectedTarget = [System.IO.Path]::Combine($resolvedParent, "forge3d")
if ($resolvedTarget -ne $expectedTarget) {
    throw "Refusing to replace an unexpected plugin path: $resolvedTarget"
}

if (Test-Path -LiteralPath $targetPlugin) {
    $backupName = "forge3d.backup-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")
    Move-Item -LiteralPath $targetPlugin -Destination (Join-Path $pluginParent $backupName)
}

& $pythonExe $creator forge3d --path $pluginParent --with-skills --with-mcp --with-marketplace --force
if ($LASTEXITCODE -ne 0) {
    throw "The plugin scaffold helper failed."
}

Remove-Item -LiteralPath $targetPlugin -Recurse -Force
Copy-Item -LiteralPath $sourcePlugin -Destination $targetPlugin -Recurse

if (Test-Path -LiteralPath $validator) {
    & $uvExe run --no-project --with pyyaml python $validator $targetPlugin
    if ($LASTEXITCODE -ne 0) {
        throw "The installed Forge3D plugin failed validation."
    }
}

Write-Host "Installed Forge3D plugin to $targetPlugin"
Write-Host "Marketplace: $marketplace"

$codexBin = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
$codexCli = Get-ChildItem -LiteralPath $codexBin -Recurse -Filter codex.exe -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $codexCli) {
    throw "Could not locate the Codex CLI under $codexBin"
}
& $codexCli.FullName plugin add "forge3d@personal"
if ($LASTEXITCODE -ne 0) {
    throw "Codex could not enable forge3d@personal."
}
Write-Host "Enabled Forge3D in Codex."

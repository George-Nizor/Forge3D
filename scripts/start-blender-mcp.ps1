[CmdletBinding()]
param(
    [string]$BlendFile,
    [string]$Blender = $env:BLENDER_EXECUTABLE
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$blenderExe = $Blender
if (-not $blenderExe) {
    $command = Get-Command blender -ErrorAction SilentlyContinue
    if ($command) {
        $blenderExe = $command.Source
    }
}
if (-not $blenderExe) {
    $steamLibraryFiles = @(
        "C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf",
        "C:\Program Files\Steam\steamapps\libraryfolders.vdf"
    )
    $steamLibraries = @(
        "C:\Program Files (x86)\Steam",
        "C:\Program Files\Steam"
    )
    foreach ($libraryFile in $steamLibraryFiles) {
        if (Test-Path -LiteralPath $libraryFile) {
            $steamLibraries += [regex]::Matches(
                (Get-Content -Raw -LiteralPath $libraryFile),
                '(?m)^\s*"path"\s+"([^"]+)"'
            ) | ForEach-Object { $_.Groups[1].Value.Replace('\\', '\') }
        }
    }
    foreach ($library in $steamLibraries | Select-Object -Unique) {
        $candidate = Join-Path $library "steamapps\common\Blender\blender.exe"
        if (Test-Path -LiteralPath $candidate) {
            $blenderExe = $candidate
            break
        }
    }
}
if (-not $blenderExe) {
    $candidate = Get-ChildItem "C:\Program Files\Blender Foundation\Blender *\blender.exe" `
        -File -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($candidate) {
        $blenderExe = $candidate.FullName
    }
}
$startupScript = Join-Path $repoRoot "scripts\start_blender_mcp.py"

if (-not $blenderExe -or -not (Test-Path -LiteralPath $blenderExe)) {
    throw "Blender was not found. Pass -Blender or set BLENDER_EXECUTABLE."
}

$arguments = @("--python", "`"$startupScript`"")
if ($BlendFile) {
    $resolvedBlend = (Resolve-Path -LiteralPath $BlendFile).Path
    # Start-Process flattens ArgumentList into one command line on Windows.
    # Preserve quotes around paths containing spaces before that flattening.
    $arguments = @("`"$resolvedBlend`"", "--python", "`"$startupScript`"")
}

Start-Process -FilePath $blenderExe -ArgumentList $arguments -WindowStyle Normal

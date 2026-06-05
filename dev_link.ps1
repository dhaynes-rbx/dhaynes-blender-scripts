<#
.SYNOPSIS
    Symlinks the DHaynes Roblox Scripts extension into every installed Blender
    version so you can iterate in-repo without re-installing.

.DESCRIPTION
    Auto-detects all Blender config folders under
    %APPDATA%\Blender Foundation\Blender\<version> (4.2, 5.0, 6.x, ...) and
    creates a directory junction to this repo's extension in each one's
    extensions\user_default folder. Re-run after upgrading Blender to link any
    new version folder.

.PARAMETER Version
    Optional. Link only this version (e.g. "5.0"). Omit to link all detected
    versions.

.PARAMETER Remove
    Remove the junction(s) instead of creating them.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File dev_link.ps1
    powershell -ExecutionPolicy Bypass -File dev_link.ps1 -Version 5.0
    powershell -ExecutionPolicy Bypass -File dev_link.ps1 -Remove
#>
param(
    [string]$Version,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$extId = "dhaynes_roblox_scripts"
$source = Join-Path $PSScriptRoot $extId

if (-not (Test-Path $source)) {
    throw "Extension source not found: $source"
}

$blenderRoot = Join-Path $env:APPDATA "Blender Foundation\Blender"
if (-not (Test-Path $blenderRoot)) {
    throw "No Blender config found at $blenderRoot. Launch Blender once first."
}

# Version folders look like 4.2, 5.0, 6.1, etc.
$versionDirs = Get-ChildItem -Path $blenderRoot -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+$' }

if ($Version) {
    $versionDirs = $versionDirs | Where-Object { $_.Name -eq $Version }
    if (-not $versionDirs) {
        throw "Blender version '$Version' not found under $blenderRoot"
    }
}

if (-not $versionDirs) {
    throw "No Blender version folders found under $blenderRoot"
}

foreach ($dir in $versionDirs) {
    $repoDir = Join-Path $dir.FullName "extensions\user_default"
    $link = Join-Path $repoDir $extId

    if ($Remove) {
        if (Test-Path $link) {
            (Get-Item $link).Delete()
            Write-Host "Removed link for Blender $($dir.Name)" -ForegroundColor Yellow
        } else {
            Write-Host "No link to remove for Blender $($dir.Name)" -ForegroundColor DarkGray
        }
        continue
    }

    if (-not (Test-Path $repoDir)) {
        New-Item -ItemType Directory -Path $repoDir -Force | Out-Null
    }

    if (Test-Path $link) {
        Write-Host "Already linked for Blender $($dir.Name)" -ForegroundColor DarkGray
        continue
    }

    New-Item -ItemType Junction -Path $link -Target $source | Out-Null
    Write-Host "Linked Blender $($dir.Name) -> $source" -ForegroundColor Green
}

if (-not $Remove) {
    Write-Host ""
    Write-Host "Done. In Blender: Preferences > Get Extensions > Refresh Local, then enable 'DHaynes Roblox Scripts'." -ForegroundColor Cyan
}

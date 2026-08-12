param(
    [string]$PythonExe = "python",
    [string]$OpenStudioRoot = ""
)

$ErrorActionPreference = "Stop"

Write-Host "== IncreaseInsulationRValueForExteriorWalls: environment setup ==" -ForegroundColor Cyan

function Resolve-OpenStudioRoot {
    param([string]$RootOverride)

    if ($RootOverride -and (Test-Path $RootOverride)) {
        return (Resolve-Path $RootOverride).Path
    }

    $candidates = @(
        "C:\openstudio-3.11.0",
        "C:\openstudio-3.9.0",
        "C:\openstudio-3.8.0"
    )

    foreach ($c in $candidates) {
        if (Test-Path $c) {
            return $c
        }
    }

    return $null
}

$resolvedRoot = Resolve-OpenStudioRoot -RootOverride $OpenStudioRoot
if (-not $resolvedRoot) {
    Write-Warning "OpenStudio installation not found in common locations."
    Write-Warning "Pass -OpenStudioRoot explicitly, eg: .\setup_environment.ps1 -OpenStudioRoot <path-to-openstudio-root>"
} else {
    $pythonBindings = Join-Path $resolvedRoot "Python"
    $binPath = Join-Path $resolvedRoot "bin"
    $rubyPath = Join-Path $resolvedRoot "Ruby"

    if (Test-Path $pythonBindings) {
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = "$pythonBindings;$env:PYTHONPATH"
        } else {
            $env:PYTHONPATH = $pythonBindings
        }
        Write-Host "PYTHONPATH += $pythonBindings" -ForegroundColor Green
    }

    $prepend = @()
    if (Test-Path $binPath) { $prepend += $binPath }
    if (Test-Path $rubyPath) { $prepend += $rubyPath }
    if ($prepend.Count -gt 0) {
        $env:PATH = ($prepend -join ";") + ";" + $env:PATH
        Write-Host "PATH += $($prepend -join ';')" -ForegroundColor Green
    }
}

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
& $PythonExe -m pip install requests python-dotenv

Write-Host "Verifying imports..." -ForegroundColor Cyan
& $PythonExe -c "import dotenv; print('python-dotenv OK')"
try {
    & $PythonExe -c "import openstudio; print('openstudio OK', openstudio.openStudioVersion())"
} catch {
    Write-Warning "openstudio import failed in this interpreter. You may need to pass -PythonExe and/or -OpenStudioRoot."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$configPath = Join-Path $repoRoot "config.ini"
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path $configPath)) {
    Write-Warning "Missing config.ini at $configPath"
    Write-Host "Add EC3 token under section [EC3_API_TOKEN] with key API_TOKEN." -ForegroundColor Yellow
}

if (-not (Test-Path $envPath)) {
    Write-Warning "Missing .env at $envPath"
    Write-Host "Create .env with client_id and client_secret for RSMeans API." -ForegroundColor Yellow
}

Write-Host "Setup complete. Next step:" -ForegroundColor Cyan
Write-Host "  cd $PSScriptRoot" -ForegroundColor Gray
Write-Host "  $PythonExe apply_measure.py" -ForegroundColor Gray

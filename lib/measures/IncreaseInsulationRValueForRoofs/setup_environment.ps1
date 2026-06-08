param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Find-OpenStudioPythonPath {
    $candidates = @()

    if ($env:OPENSTUDIO_PYTHON_PATH) {
        $candidates += $env:OPENSTUDIO_PYTHON_PATH
    }

    $candidates += @(
        "C:\openstudio-3.11.0\Python",
        "C:\openstudio-3.10.0\Python",
        "C:\openstudio-3.9.0\Python"
    )

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }

    return $null
}

function Resolve-PythonExe {
    param([string]$InputPython)

    if ($InputPython -and (Test-Path $InputPython)) {
        return $InputPython
    }

    if ($env:CONDA_PREFIX) {
        $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $condaPython) {
            return $condaPython
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python executable not found. Install Python or activate your conda environment first."
}

Write-Host "Setting up IncreaseInsulationRValueForRoofs environment..." -ForegroundColor Cyan

$openstudioPythonPath = Find-OpenStudioPythonPath
if ($openstudioPythonPath) {
    Write-Host "Found OpenStudio Python path: $openstudioPythonPath" -ForegroundColor Green
    $env:OPENSTUDIO_PYTHON_PATH = $openstudioPythonPath
} else {
    Write-Warning "OpenStudio Python path not found in default locations."
    Write-Warning "Set OPENSTUDIO_PYTHON_PATH manually if openstudio import fails."
}

$pythonExe = Resolve-PythonExe -InputPython $PythonExe
Write-Host "Using Python: $pythonExe" -ForegroundColor Green

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install python-dotenv

$validationScript = @'
import os
import sys

os_path = os.environ.get("OPENSTUDIO_PYTHON_PATH")
if os_path and os_path not in sys.path:
    sys.path.insert(0, os_path)

try:
    import openstudio
    print(f"openstudio import ok: {openstudio.openStudioVersion()}")
except Exception as exc:
    print(f"openstudio import failed: {exc}")

try:
    import dotenv
    print("python-dotenv import ok")
except Exception as exc:
    print(f"python-dotenv import failed: {exc}")
'@

& $pythonExe -c $validationScript

Write-Host "Environment setup complete." -ForegroundColor Cyan
Write-Host "Tip: run this script in the same PowerShell session used for apply_measure.py." -ForegroundColor Yellow

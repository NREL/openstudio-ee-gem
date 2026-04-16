# setup_environment.ps1
# ---------------------------------------------------------------------------
# One-shot environment setup for the DoorEnhancement measure.
#
# What this script does:
#   1. Locates an OpenStudio Python directory (OPENSTUDIO_PYTHON_PATH env var
#      or standard Windows install paths for 3.11 / 3.10 / 3.9).
#   2. Locates the active Python executable (conda env or system PATH).
#   3. Upgrades pip and installs python-dotenv.
#   4. Runs a quick import check (openstudio + dotenv).
#
# Usage:
#   cd lib/measures/door_enhancement
#   ./setup_environment.ps1
# ---------------------------------------------------------------------------

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# 1. Find OpenStudio Python path
# ---------------------------------------------------------------------------
function Find-OpenStudioPythonPath {
    $explicit = $env:OPENSTUDIO_PYTHON_PATH
    if ($explicit -and (Test-Path $explicit)) {
        return $explicit
    }
    $versions = @("3.11.0", "3.10.0", "3.9.0")
    foreach ($ver in $versions) {
        $candidate = "C:\openstudio-$ver\Python"
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

# ---------------------------------------------------------------------------
# 2. Find Python executable
# ---------------------------------------------------------------------------
function Resolve-PythonExe {
    if ($env:CONDA_PREFIX) {
        $condaPy = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $condaPy) { return $condaPy }
    }
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) { return $pyCmd.Source }
    Write-Error "Python executable not found. Activate a conda environment or add Python to PATH."
    exit 1
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
Write-Host "=" * 70
Write-Host "DoorEnhancement – Environment Setup"
Write-Host "=" * 70

$osPath = Find-OpenStudioPythonPath
if ($osPath) {
    Write-Host "OpenStudio Python path: $osPath"
    $env:OPENSTUDIO_PYTHON_PATH = $osPath
} else {
    Write-Host "OpenStudio path not found in standard locations."
    Write-Host "Set OPENSTUDIO_PYTHON_PATH to the directory containing openstudio.pyd / openstudio.so"
}

$pythonExe = Resolve-PythonExe
Write-Host "Python executable    : $pythonExe"

# ---------------------------------------------------------------------------
# Install / upgrade dependencies
# ---------------------------------------------------------------------------
Write-Host "`nUpgrading pip..."
& $pythonExe -m pip install --upgrade pip --quiet

Write-Host "Installing python-dotenv..."
& $pythonExe -m pip install --upgrade python-dotenv --quiet

# ---------------------------------------------------------------------------
# Validate imports
# ---------------------------------------------------------------------------
Write-Host "`nValidating imports..."
$validationScript = @"
import sys
errors = []
# openstudio
try:
    import openstudio
    print(f'  [OK] openstudio {openstudio.openStudioVersion()}')
except ImportError as e:
    errors.append(f'  [FAIL] openstudio: {e}')

# dotenv
try:
    import dotenv
    print(f'  [OK] python-dotenv {dotenv.__version__}')
except ImportError as e:
    errors.append(f'  [FAIL] python-dotenv: {e}')

# numpy
try:
    import numpy as np
    print(f'  [OK] numpy {np.__version__}')
except ImportError as e:
    errors.append(f'  [FAIL] numpy: {e}')

if errors:
    print()
    for err in errors:
        print(err)
    sys.exit(1)
else:
    print()
    print('All imports OK.')
"@

if ($osPath) {
    $env:PYTHONPATH = "$osPath;$($env:PYTHONPATH)"
    & $pythonExe -c $validationScript
} else {
    & $pythonExe -c $validationScript
}

Write-Host "`n" + "=" * 70
Write-Host "Setup complete.  Run the measure with:"
Write-Host "    python apply_measure.py"
Write-Host "=" * 70

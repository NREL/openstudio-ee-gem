$ErrorActionPreference = "Stop"

Write-Host "=== Window Enhancement Environment Setup ==="

$measureDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $measureDir

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "Python was not found in PATH. Install Python or activate your environment first."
}

Write-Host "Using python: $($pythonCmd.Source)"
python --version

$openStudioCandidates = @(
    $env:OPENSTUDIO_PYTHON_PATH,
    "C:\openstudio-3.11.0\Python",
    "C:\openstudio-3.10.0\Python",
    "C:\openstudio-3.9.0\Python"
) | Where-Object { $_ -and $_.Trim().Length -gt 0 }

$selectedOpenStudioPath = $null
foreach ($candidate in $openStudioCandidates) {
    if (Test-Path $candidate) {
        $selectedOpenStudioPath = $candidate
        break
    }
}

if ($selectedOpenStudioPath) {
    if (-not ($env:PYTHONPATH -split ";" | Where-Object { $_ -eq $selectedOpenStudioPath })) {
        if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
            $env:PYTHONPATH = $selectedOpenStudioPath
        } else {
            $env:PYTHONPATH = "$selectedOpenStudioPath;$env:PYTHONPATH"
        }
    }
    Write-Host "OpenStudio Python path candidate: $selectedOpenStudioPath"
} else {
    Write-Warning "No known OpenStudio Python path found. If import fails, set OPENSTUDIO_PYTHON_PATH manually."
}

Write-Host "Installing python-dotenv if needed..."
python -m pip install --disable-pip-version-check python-dotenv | Out-Null

Write-Host "Verifying imports..."
python -c "import openstudio; import dotenv; print('OpenStudio version:', openstudio.openStudioVersion()); print('python-dotenv import: OK')"

Write-Host "Environment setup complete."
Write-Host "Next step: python apply_measure.py"

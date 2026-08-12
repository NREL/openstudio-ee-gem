# Environment Setup for IncreaseInsulationRValueForRoofs

## Overview

The roof insulation measure depends on:

- A Python environment where this repository runs.
- OpenStudio Python bindings.
- `python-dotenv` (used by RSMeans helper credential loading).

## Fastest Setup (PowerShell)

From the measure directory:

```powershell
cd lib/measures/IncreaseInsulationRValueForRoofs
./setup_environment.ps1
```

What this script does:

- Detects `OPENSTUDIO_PYTHON_PATH` or common local OpenStudio Python install paths.
- Installs/updates `python-dotenv` in the active Python environment.
- Runs a quick import validation for `openstudio` and `dotenv`.

## Manual Setup

1. Create and activate environment from repository root:

```powershell
conda env create -f environment.yml
conda activate openstudio312
```

2. Ensure OpenStudio bindings are reachable:

- Preferred: set `OPENSTUDIO_PYTHON_PATH` to your OpenStudio `Python` folder.
- Or ensure `openstudio` is importable directly in your environment.

3. Install required package:

```powershell
python -m pip install python-dotenv
```

4. Validate imports:

```powershell
python -c "import openstudio, dotenv; print(openstudio.openStudioVersion())"
```

## Running the Measure

```powershell
cd lib/measures/IncreaseInsulationRValueForRoofs
python apply_measure.py
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'openstudio'`

- Set `OPENSTUDIO_PYTHON_PATH` to the OpenStudio `Python` directory.
- Re-run `setup_environment.ps1` in the same shell session.

### `ModuleNotFoundError: No module named 'dotenv'`

- Run `python -m pip install python-dotenv` in the active environment.

### Mixed Python installations

- Confirm interpreter path with:

```powershell
python -c "import sys; print(sys.executable)"
```

- Ensure that is the same interpreter you used for package install.

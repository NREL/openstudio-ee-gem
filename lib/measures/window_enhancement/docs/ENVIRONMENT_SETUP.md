# Environment Setup for Window Enhancement Measure

## Overview

The Window Enhancement measure requires Python 3.8 and OpenStudio 3.11.0 to run correctly. This document explains how to set up your development environment.

## Prerequisites

- Conda (Anaconda or Miniconda) installed on your system
- Git with the openstudio-ee-gem repository cloned

## Quick Setup

### 0. Automated Setup (Recommended on Windows)

From the measure directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_environment.ps1
```

The script checks for OpenStudio Python paths, verifies `openstudio` import,
installs `python-dotenv` if missing, and prints the interpreter/version in use.

### 1. Create the Environment from environment.yml

From the repository root, run:

```bash
conda env create -f environment.yml
```

This creates a new conda environment named `openstudio-3.8` with all required dependencies.

### 2. Activate the Environment

Before running any measure tests or development work, activate the environment:

```bash
conda activate openstudio-3.8
```

Your terminal prompt should now show `(openstudio-3.8)` at the beginning.

### 3. Verify Installation

Verify the environment is set up correctly by checking the Python version:

```bash
python --version
```

Expected output: `Python 3.8.20`

## Running the Measure

Once the environment is activated, you can run the measure test script from the measure directory:

```bash
cd lib/measures/window_enhancement
python apply_measure.py
```

If you used the setup script, keep using the same shell session so any temporary
environment updates remain active.

## Environment Contents

The `openstudio-3.8` environment includes:

- **Python**: 3.8.20
- **OpenStudio**: 3.11.0 (via pip)
- **python-dotenv**: 1.0.1 (for .env file support)
- **urllib3**: 2.2.3 (for HTTP requests)
- **idna**: 3.11 (for URL handling)

## Updating the Environment

If dependencies change, update the `environment.yml` file:

```bash
conda activate openstudio-3.8
conda env export > environment.yml
```

Then commit the updated file to the repository.

## Deactivating the Environment

To return to the base conda environment:

```bash
conda deactivate
```

## Troubleshooting

### "conda: command not found"
Conda is not installed or not in your PATH. Download and install Miniconda or Anaconda from https://conda.io/projects/conda/en/latest/pages/installation/index.html

### "The specified module could not be found" (DLL error)
This indicates a Python version mismatch. Ensure you're using the correct environment:
```bash
conda activate openstudio-3.8
```

### "ModuleNotFoundError: No module named 'openstudio'"
Verify the environment is activated and has the openstudio package:
```bash
conda activate openstudio-3.8
python -c "import openstudio; print(openstudio.openStudioVersion())"
```

## Development Workflow

### For Measure Testing
1. Activate the environment: `conda activate openstudio-3.8`
2. Navigate to the measure directory: `cd lib/measures/window_enhancement`
3. Run the test script: `python apply_measure.py`

### For Code Development
You can configure VS Code to use this environment by:
1. Opening the Command Palette (Ctrl+Shift+P)
2. Searching for "Python: Select Interpreter"
3. Choosing the path to the `openstudio-3.8` environment

This ensures code completion, linting, and test execution all use the correct Python version.

## Additional Resources

- [Conda Documentation](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)
- [Window Enhancement Measure Documentation](Window_Enhancement.md)
- [RSMeans Search Strategy](RSMEANS_SEARCH_STRATEGY.md)

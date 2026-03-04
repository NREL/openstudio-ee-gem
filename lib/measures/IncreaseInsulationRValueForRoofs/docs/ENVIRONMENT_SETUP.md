# Environment Setup for Increase Insulation R-Value for Roofs

## Overview

This measure requires Python 3.8+ and OpenStudio 3.11.0. Use the repository's environment.yml to keep dependencies consistent.

## Prerequisites

- Conda (Anaconda or Miniconda)
- Git with the openstudio-ee-gem repository cloned

## Quick Setup

### 1. Create the Environment

From the repository root:

```bash
conda env create -f environment.yml
```

### 2. Activate the Environment

```bash
conda activate openstudio-3.8
```

### 3. Verify Installation

```bash
python -c "import openstudio; print(openstudio.openStudioVersion())"
```

## Running the Measure

```bash
cd lib/measures/IncreaseInsulationRValueForRoofs
python apply_measure.py
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'openstudio'"

Ensure the environment is activated and has the openstudio package:

```bash
conda activate openstudio-3.8
python -c "import openstudio; print(openstudio.openStudioVersion())"
```

### DLL or Version Errors

Use the conda environment from environment.yml and avoid mixing system Python with OpenStudio packages.

## Additional Resources

- [Conda Environments](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)
- [Measure Documentation](Increase_Insulation_Roofs.md)
- [RSMeans Search Strategy](RSMEANS_SEARCH_STRATEGY.md)

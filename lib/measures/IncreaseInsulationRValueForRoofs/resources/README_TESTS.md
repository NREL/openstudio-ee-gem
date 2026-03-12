# Resources - Test and Utility Scripts

This folder contains utility scripts, helper modules, and validation tests for the IncreaseInsulationRValueForRoofs measure.

## Core Modules

- **measure.py**: Main measure implementation (in parent directory)
- **call_rsmeans_api.py**: RSMeans API client for fetching material costs and embodied carbon data
- **EC3_lookup.py**: EC3 database lookups for environmental product declarations (EPD)
- **calculate_perimeter.py**: Utility for calculating roof perimeter

## Test and Validation Scripts

### validate_enhancements.py

Unit tests for the enhanced RSMeans scoring and search functionality.

**Purpose:** Validate that scoring logic produces expected results and material-specific search terms are generated correctly.

**Usage:**
```bash
cd lib/measures/IncreaseInsulationRValueForRoofs/resources
python validate_enhancements.py
```

**What it tests:**
- Enhanced scoring function (token matching, generic penalties, roof requirement)
- Material-specific search term generation for 8+ insulation types
- Score ranges for exact vs. generic matches

### run_roof_insulation_validation.py

Full integration test that runs the measure across all 11 insulation material types.

**Purpose:** Validate measure performance with actual OpenStudio models and RSMeans API integration.

**Requirements:**
- OpenStudio environment configured
- Test model available at `tests/models/DOE_small_office_roof_insulation.osm`
- Valid RSMeans API credentials (RSMEANS_CLIENT_ID, RSMEANS_CLIENT_SECRET environment variables)

**Usage:**
```bash
cd lib/measures/IncreaseInsulationRValueForRoofs/resources
python run_roof_insulation_validation.py
```

**Output:**
- Per-material result folders in `tests/output/roof_insulation_enhanced_validation/`
- Summary JSON with cost groupings and RSMeans diagnostics

## Visualization and Reporting

The resources folder also contains:
- Generated HTML/PNG reports for carbon impact visualization
- CSV output files for analysis

## Legacy Scripts

- **Test_API.py**: Early API testing script (may be deprecated)
- **apply_measure.py**: Alternative measure application script in parent directory

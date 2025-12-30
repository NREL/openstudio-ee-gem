# Multi-Measure Workflow Usage Guide

## Overview

The `workflow.py` script now supports applying multiple retrofit measures in a single workflow run. You can select which measures to apply and configure their arguments using the `workflow_config.json` file.

## Available Measures

1. **Window Enhancement** (`window_enhancement`)
   - Replaces existing windows with higher-performance windows
   - Includes EC3 embodied carbon calculations for new windows
   - Arguments: glazing type, frame type, R-values, SHGC, VT, etc.

2. **Wall Insulation** (`wall_insulation`)
   - Increases insulation R-value for exterior walls
   - Includes EC3 embodied carbon calculations for insulation
   - Arguments: R-value, API key, GWP statistic

3. **Roof Insulation** (`roof_insulation`)
   - Increases insulation R-value for roofs
   - Includes EC3 embodied carbon calculations for insulation
   - Arguments: R-value, API key, GWP statistic

## Configuration

Edit the `workflow_config.json` file in the same directory as `workflow.py`:

```json
{
  "measures": {
    "window_enhancement": {
      "enabled": true,
      "arguments": {
        "wf_option": "wood window frame",
        "film_option": "solar control film",
        "glass_option": "triple pane clear",
        "gwp_statistic": "mean",
        "caulking_thickness": 0.0127,
        "glass_pane_thickness": 0.003,
        "gap_thickness": 0.013,
        "glass_solar_transmittance": 0.7,
        "glass_front_emissivity": 0.84,
        "glass_back_emissivity": 0.84,
        "length_per_unit": 1.0,
        "user_num_panes": 3,
        "num_horizontal_dividers": 0,
        "num_vertical_dividers": 0,
        "space_infiltration_reduction_percent": 50.0,
        "caulking_option": "acrylic",
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "secondary_glazing_option": "none"
      }
    },
    "wall_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 13.0,
        "gwp_statistic": "mean"
      }
    },
    "roof_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 30.0,
        "gwp_statistic": "mean"
      }
    }
  }
}
```

### To Apply All Measures

Set all `"enabled": true` (default configuration).

### To Apply Only Windows

```json
{
  "measures": {
    "window_enhancement": {
      "enabled": true,
      "arguments": { ... }
    },
    "wall_insulation": {
      "enabled": false
    },
    "roof_insulation": {
      "enabled": false
    }
  }
}
```

### To Apply Only Insulation (Walls + Roofs)

```json
{
All measure arguments are now specified in `workflow_config.json`. Simply edit the JSON file to change parameters:

### For Window Enhancement
```json
"window_enhancement": {
  "enabled": true,
  "arguments": {
    "wf_option": "wood window frame",        // Frame: "wood window frame", "vinyl window frame", "aluminum window frame", "fiberglass window frame"
    "glass_option": "triple pane clear",     // Glazing: "double pane clear", "triple pane clear", etc.
    "film_option": "solar control film",     // Film: "solar control film", "none"
    "user_num_panes": 3,                     // Number of glass panes
    "gap_thickness": 0.013,                  // Gap between panes in meters
    "glass_solar_transmittance": 0.7,        // Solar transmittance (0-1)
    "glass_front_emissivity": 0.84,          // Front emissivity (0-1)
    "glass_back_emissivity": 0.84,           // Back emissivity (0-1)
    "space_infiltration_reduction_percent": 50.0,  // Infiltration reduction %
    "caulking_option": "acrylic",            // Caulking: "acrylic", "silicone", etc.
    "weatherstrip_option": "silicone adhesive smoke gasket",  // Weatherstripping type
    "gwp_statistic": "mean"                  // GWP statistic: "mean", "median", "conservative"
  }
}
```

### For Wall Insulation
```json
"wall_insulation": {
  "enabled": true,
  "arguments": {
    "r_value": 13.0,                    // R-value in h·ft²·°F/Btu
    "gwp_statistic": "mean"             // Options: mean, median, conservative
  }
}
```

### For Roof Insulation
```json
"roof_insulation": {
  "enabled": true,
  "arguments": {
    "r_value": 30.0,                    // R-value in h·ft²·°F/Btu
    "gwp_statistic": "mean"             // Options: mean, median, conservative
  }
}
```

**Note:** If you omit any argument, the workflow will use sensible defaults.arious other performance parameters

### Wall Insulation
- `r_value`: 13.0 (h·ft²·°F/Btu)
- `gwp_statistic`: "mean"

### Roof Insulation
- `r_value`: 30.0 (h·ft²·°F/Btu)
- `gwp_statistic`: "mean"

## Modifying Measure Arguments

To change the default arguments, edit the corresponding section in the `main()` function:

### For Window Enhancement (around line 790)
```python
if MEASURES_TO_APPLY.get('window_enhancement'):
    window_args = {
        'glazing_type': 'triple_pane',  # Change to 'double_pane', 'quad_pane', etc.
        'frame_type': 'wood',            # Change to 'vinyl', 'aluminum', 'fiberglass'
        'u_value_ip': 0.20,              # Adjust U-value
        # ... other parameters
    }
```

### For Wall Insulation (around line 825)
```python
if MEASURES_TO_APPLY.get('wall_insulation'):
    wall_args = {
        'r_value': 13.0,  # Change to desired R-value
        'api_key': ec3_api_token,
        'gwp_statistic': 'mean'
    }
```

### For Roof Insulation (around line 838)
```python
if MEASURES_TO_APPLY.get('roof_insulation'):
    roof_args = {
        'r_value': 30.0,  # Change to desired R-value
        'api_key': ec3_api_token,
        'gwp_statistic': 'mean'
    }
```

## Running the Workflow

```bash
cd lib/measures/ReportRetrofitImpacts
python workflow.py
```

## Output

The workflow generates the following outputs in `retrofit_results/`:

1. **modified_model.osm** - The OpenStudio model with all selected measures applied
2. **optimization_updated.xlsx** - Excel spreadsheet with baseline, modified, and delta values
3. **retrofit_comparison_spider_chart.html** - Interactive visualization comparing baseline vs. retrofit package

The final summary will list which measures were applied:

```
================================================================================
WORKFLOW COMPLETE!
================================================================================

Applied Measures:
  ✓ Window Enhancement
  ✓ Wall Insulation
  ✓ Roof Insulation

Results saved in: retrofit_results
  - Modified model: modified_model.osm
  - Updated spreadsheet: optimization_updated.xlsx
  - Spider chart: retrofit_comparison_spider_chart.html

================================================================================
```

## Technical Notes

- All measures share the same EC3 API token from `config.ini`
- API keys are automatically masked in terminal output (displayed as `***REDACTED***`)
- Measures are applied sequentially to the same model
- Total embodied carbon is the sum of embodied carbon from all applied measures
- The spider chart is labeled "Retrofit Package" when multiple measures are applied
- Each measure has its own `apply_*_measure()` function for modularity

## Troubleshooting

### Import Errors
If you see import errors for a specific measure, ensure:
1. The measure directory exists in `lib/measures/`
2. The measure has a `measure.py` file
3. The `MEASURES_TO_APPLY` flag is set to `True` for that measure

### Measure Application Failures
If a measure fails to apply:
1. Check the terminal output for specific error messages
2. Verify the measure arguments are valid
3. Ensure the EC3 API token is configured in `config.ini`
4. Check that the baseline model has the appropriate geometry for that measure (e.g., exterior walls for wall insulation)

### Zero Results
If the modified model shows zero energy savings:
1. Verify the EnergyPlus simulation ran successfully (check for eplustbl.html in run directory)
2. Check that the measure actually modified the model (inspect modified_model.osm)
3. Ensure the weather file exists in the expected location

## Future Enhancements

Potential improvements for the multi-measure workflow:

1. **Interactive CLI**: Add command-line arguments to select measures without editing the script
2. **Configuration File**: Move measure arguments to a YAML/JSON configuration file
3. **Measure Library**: Auto-discover all available measures in the `lib/measures/` directory
4. **Parameter Optimization**: Add support for running parametric studies with different argument values
5. **Cost-Benefit Analysis**: Compare multiple measure packages to find the optimal combination

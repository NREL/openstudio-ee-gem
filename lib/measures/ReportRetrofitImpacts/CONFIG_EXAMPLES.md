# Example Workflow Configurations

This directory contains example configuration files for different retrofit scenarios.

## Files

- **workflow_config.json** - Main configuration file (all measures enabled by default)
- **config_windows_only.json** - Windows enhancement only
- **config_insulation_only.json** - Wall and roof insulation only
- **config_minimal.json** - Minimal window upgrade

## Usage

To use a different configuration, either:

1. **Replace the default config:**
   ```bash
   cp config_windows_only.json workflow_config.json
   python workflow.py
   ```

2. **Or modify workflow.py to load a different file:**
   ```python
   CONFIG = load_config("config_windows_only.json")
   ```

## Example Configurations

### Windows Only (High Performance Triple-Pane)
```json
{
  "measures": {
    "window_enhancement": {
      "enabled": true,
      "arguments": {
        "glass_option": "triple pane clear",
        "wf_option": "wood window frame",
        "user_num_panes": 3
      }
    },
    "wall_insulation": {"enabled": false},
    "roof_insulation": {"enabled": false}
  }
}
```

### Insulation Package Only
```json
{
  "measures": {
    "window_enhancement": {"enabled": false},
    "wall_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 19.0,
        "gwp_statistic": "mean"
      }
    },
    "roof_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 38.0,
        "gwp_statistic": "mean"
      }
    }
  }
}
```

### Deep Energy Retrofit (Everything)
```json
{
  "measures": {
    "window_enhancement": {
      "enabled": true,
      "arguments": {
        "glass_option": "triple pane clear",
        "wf_option": "fiberglass window frame",
        "user_num_panes": 3,
        "space_infiltration_reduction_percent": 75.0
      }
    },
    "wall_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 21.0,
        "gwp_statistic": "mean"
      }
    },
    "roof_insulation": {
      "enabled": true,
      "arguments": {
        "r_value": 49.0,
        "gwp_statistic": "mean"
      }
    }
  }
}
```

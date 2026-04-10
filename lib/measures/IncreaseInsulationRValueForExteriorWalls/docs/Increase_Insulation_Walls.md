# Increase Insulation R-Value for Exterior Walls Measure

## Overview

This OpenStudio measure automates the process of adding insulation to exterior walls in building energy models. It calculates the embodied carbon impact of the insulation materials using EC3 (Environmental Product Declaration) data and estimates construction costs using the RSMeans API.

## Features

- **Automatic Wall Insulation Upgrade:** Increases R-value of all exterior walls to a target value
- **Embodied Carbon Calculation:** Uses EC3 API to retrieve Environmental Product Declaration (EPD) data
- **Cost Estimation:** Integrates RSMeans API for accurate construction cost estimates
- **Custom Cost Override:** Allows manual cost entry if API data is unavailable
- **Overhead & Profit Adjustment:** Configurable markup percentage for contractor overhead and profit
- **JSON Export:** Stores all calculations and results in AdditionalProperties of the model

## Input Arguments

### Core Insulation Parameters

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `r_value` | Double | 20.0 | Target R-value (IP units) for exterior walls after insulation |
| `insulation_material_type` | Choice | Fiberglass Batts | Type of insulation material to add |
| `apply_to_existing_walls` | Boolean | true | If true, add insulation to walls with existing exterior insulation; if false, skip those walls |

### Analysis Parameters

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `analysis_period` | Integer | 30 | Number of years for embodied carbon analysis (typical: 30-60 years) |
| `gwp_statistic` | Choice | median | GWP statistic to use from EPD (options: average, median, conservative) |

### Cost Calculation Parameters

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `calculate_costs` | Boolean | true | If true, estimate costs using RSMeans API and/or custom values |
| `use_custom_costs` | Boolean | false | If true, use `custom_cost_per_sf` instead of RSMeans lookup |
| `custom_cost_per_sf` | Double | 5.0 | Custom cost per square foot (only used if `use_custom_costs` is true) |
| `overhead_profit_percent` | Double | 10.0 | Contractor overhead and profit as percentage of material cost |

### API Configuration

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `api_key` | String | "" | EC3 API token for Environmental Product Declaration lookups |

## Insulation Material Options

### Available Materials

1. **Fiberglass Batts** (Default)
   - Cost: ~$1.18/SF
   - Embodied Carbon: ~0.084 kg CO2/kg
   - Availability: High
   - Notes: Most common, cost-effective option for exterior walls

2. **Mineral Wool Batts**
   - Cost: ~$1.40/SF
   - Embodied Carbon: ~0.120 kg CO2/kg
   - Availability: High
   - Notes: Better fire resistance, moisture resistance

3. **Extruded Polystyrene (XPS) Rigid Foam**
   - Cost: ~$1.60/SF
   - Embodied Carbon: ~2.50 kg CO2/kg
   - Availability: Medium
   - Notes: High R-value per inch, higher embodied carbon

4. **Polyiso Rigid Foam**
   - Cost: ~$1.45/SF
   - Embodied Carbon: ~1.80 kg CO2/kg
   - Availability: Medium
   - Notes: High R-value, moderate embodied carbon

## Outputs

### Model Modifications

The measure modifies the OpenStudio model by:

1. **Increasing Wall Insulation:** Adds insulation layer to all exterior walls
2. **Material Assignment:** Assigns specified insulation material to new layers
3. **Thermal Properties:** Updates construction to match target R-value

### Data Storage (AdditionalProperties)

All calculations are stored in `AdditionalProperties` on both the Facility and SimulationControl objects:

#### Facility Properties
```json
{
  "wall_insulation_upgrade_wall_area_ft2": "2886.75",
  "wall_insulation_upgrade_wall_area_m2": "268.19",
  "wall_insulation_upgrade_target_r_value": "20.0",
  "wall_insulation_upgrade_initial_cost": "3406.37",
  "wall_insulation_upgrade_overhead_profit": "340.64",
  "wall_insulation_upgrade_total_cost": "3747.00",
  "wall_insulation_upgrade_cost_per_unit": "1.18"
}
```

#### SimulationControl Properties
```json
{
  "wall_insulation_upgrade_materials": "[{...}]",
  "wall_insulation_upgrade_material_rsmeans_response": "{...}",
  "wall_insulation_upgrade_api_key": "<redacted>"
}
```

### Console Output

During execution, the measure prints:
- Initial model wall statistics
- Target R-value and wall areas
- Insulation material specifications
- EC3 API results and embodied carbon calculations
- RSMeans API lookup results and cost breakdown
- Final output model path

### Output Files

Running `apply_measure.py` generates:

1. **Model File:** `DOE_small_office_wall_insulation_upgraded.osm`
   - Original model with insulation applied
   - Contains all AdditionalProperties with results

2. **Results JSON:** `apply_measure_results.json`
   - Complete measure results in JSON format
   - Includes step values, costs, and API responses
   - API keys are redacted for security

## Usage Examples

### Example 1: Basic Usage with Default Fiberglass Batts

```json
{
  "measure_dir_name": "IncreaseInsulationRValueForExteriorWalls",
  "arguments": {
    "r_value": 20.0,
    "insulation_material_type": "Fiberglass Batts",
    "calculate_costs": true,
    "use_custom_costs": false
  }
}
```

**Expected Output:**
- R-value increased to 20.0
- Fiberglass Batts material added to all exterior walls
- RSMeans cost: ~$3,747 for 2,886 SF (example)
- Embodied carbon: ~98 kg CO2 eq

### Example 2: Using Custom Costs

```json
{
  "measure_dir_name": "IncreaseInsulationRValueForExteriorWalls",
  "arguments": {
    "r_value": 25.0,
    "insulation_material_type": "Mineral Wool Batts",
    "calculate_costs": true,
    "use_custom_costs": true,
    "custom_cost_per_cf": 8.50
  }
}
```

**Expected Output:**
- R-value increased to 25.0
- Mineral Wool Batts material added
- Custom cost used: $8.50/CF (cubic feet volume basis)
- Overhead applied: 10% (on material cost)
- Total cost depends on volume of insulation added

### Example 3: No Cost Calculation

```json
{
  "measure_dir_name": "IncreaseInsulationRValueForExteriorWalls",
  "arguments": {
    "r_value": 20.0,
    "calculate_costs": false
  }
}
```

**Expected Output:**
- R-value increased to 20.0
- No RSMeans API calls made
- No cost estimates generated
- Embodied carbon still calculated

## Command Line Usage

### Apply Measure to Default Test Model

```bash
cd lib/measures/IncreaseInsulationRValueForExteriorWalls
python apply_measure.py
```

This runs the measure with default arguments on `DOE_small_office.osm`.

### Customize Apply Script

Edit `apply_measure.py` to modify:
- Input model path (line 70)
- Measure arguments (lines 75-85)
- Output model directory (line 95)

## Cost Calculation Details

### Volume-Based Costing

The measure calculates costs on a **cubic feet (CF) volume basis** rather than area basis. This approach:
- Aligns with embodied carbon calculations (which are inherently volume-dependent)
- Accounts for varying insulation thicknesses automatically
- Provides consistency across measures (window and door enhancements use same basis)

**Volume Calculation:**
```
Volume (CF) = Added Thickness (m) × Wall Area (m²) × 35.315 CF/m³
```

**Cost Calculation:**
```
Material Cost = Volume (CF) × Cost per CF ($/CF)
Total Cost = Material Cost × (1 + Overhead/Profit %/100)
```

### RSMeans Cost Path

When RSMeans lookup is enabled, the measure searches Division 07 (Thermal and Moisture Protection) using the material name and automatically handles scoring:
1. Searches across multiple RSMeans catalogs for best match
2. Scores candidates based on term relevance
3. If `best_score < MIN_ACCEPTABLE_MATCH_SCORE (0.0)`, uses fallback RSMeans ID
4. Applies overhead/profit percentage to material cost

## Measure Flow Diagram

```
┌─────────────────────────┐
│   Input OSM Model       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Extract Walls & Costs  │
│  - Wall areas (SF/M2)   │
│  - Current R-values     │
│  - Construction details │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  EC3 API Lookup         │
│  - Material EPD data    │
│  - Embodied carbon      │
│  - Storage duration     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  RSMeans Cost Lookup    │
│  (if costs enabled)     │
│  - Material unit cost   │
│  - Division 07 search   │
│  - Labor + overhead     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Calculate Final Costs  │
│  - Material cost        │
│  - Overhead/profit      │
│  - Total cost estimate  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Apply Insulation       │
│  - Create new layer     │
│  - Assign material      │
│  - Update construction  │
│  - Modify all walls     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Store Results          │
│  - AdditionalProperties │
│  - JSON serialization   │
│  - Cost calculations    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Output OSM Model       │
│  + Results JSON         │
└─────────────────────────┘
```

## Error Handling

### Common Issues & Solutions

**Issue:** "EC3 API token not found"
- **Solution:** Verify `config.ini` contains valid EC3 token (see [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md))

**Issue:** "RSMeans API credentials not found"
- **Solution:** Set environment variables `client_id` and `client_secret` or add to `.env` file

**Issue:** "Wall areas are zero"
- **Solution:** Ensure input model has properly defined exterior walls with surface geometry

**Issue:** "No walls modified"
- **Solution:** Check that `apply_to_existing_walls` is true if walls have existing insulation

**Issue:** RSMeans returns $0 cost
- **Solution:** Check the `RSMEANS_SEARCH_STRATEGY.md` documentation for search term optimization

**Issue:** "Fallback ID used" warning in output
- **Solution:** This is normal when RSMeans search yields low-quality matches. The measure uses a pre-mapped fallback ID to ensure cost estimates are always available. No action required unless you want to specify an exact RSMeans ID via `exact_costline_id`

## Performance Considerations

- **First Run:** ~10-30 seconds (EC3 and RSMeans API calls)
- **Subsequent Runs:** ~5-10 seconds (shorter if cached)
- **API Rate Limits:** RSMeans and EC3 have rate limits - avoid running multiple measures simultaneously

## See Also

- [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) - API credential configuration
- [RSMEANS_SEARCH_STRATEGY.md](RSMEANS_SEARCH_STRATEGY.md) - Cost lookup customization
- [measure.py](../measure.py) - Full measure source code
- [apply_measure.py](../apply_measure.py) - Test/apply script

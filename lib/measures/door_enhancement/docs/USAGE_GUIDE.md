# Door Enhancement Measure – Usage Guide

## Overview

The **Door Enhancement** measure improves building door performance by:
1. **Adding weatherstripping seals** (bottom, top, and side) to reduce air infiltration
2. **Optionally replacing doors** with more thermally efficient options
3. **Calculating embodied carbon impact** using Environmental Product Declaration (EPD) data from the EC3 database
4. **Estimating construction costs** via RSMeans API or custom cost inputs

The measure adjusts space infiltration rates and generates a life-cycle embodied carbon assessment over a user-specified analysis period.

---

## Getting Started

### Prerequisites

- **OpenStudio SDK v3.11.0** or compatible
- **Python 3.7+** with libraries: `numpy`, `pandas`, `urllib3`, `requests`, `python-dotenv`
- **EC3 API credentials** (for embodied carbon lookups)
- **RSMeans API credentials** (optional; for construction cost lookups)
- **Configuration file** at repo root: `config.ini` with EC3 API token

#### Python Environment Setup (Optional)

You can create a Python environment with the required dependencies using the repo’s environment.yml:

```bash
conda env create -f environment.yml
conda activate openstudio-3.11
```

**Important**: This installs Python packages only. You still need to install the OpenStudio SDK separately and ensure its Python bindings are discoverable (e.g., update your `OPENSTUDIO_VERSION` path in apply_measure.py).

### Configuration

#### EC3 API Setup

Create `config.ini` in the repository root:

```ini
[EC3_API_TOKEN]
API_TOKEN = your_ec3_api_token_here
```

Or set environment variables:
```bash
export EC3_API_TOKEN=your_token_here
```

#### RSMeans API Setup (Optional)

Set environment variables for RSMeans authentication:
```bash
export RSMEANS_CLIENT_ID=your_client_id
export RSMEANS_CLIENT_SECRET=your_client_secret
```

Or add to a `.env` file in the measure directory (will be loaded by `call_rsmeans_api.py`):

```
RSMEANS_CLIENT_ID=your_client_id
RSMEANS_CLIENT_SECRET=your_client_secret
```

**Security Note**: Never commit `.env` files or credentials to the repository. The `.gitignore` file prevents `config.ini`, `.env`, and `*.env` from being committed.

---

## Measure Arguments

### Core Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `space_type` | Choice | *Entire Building* | Apply to specific space type or entire building |
| `space_infiltration_reduction_percent` | Double (%) | 30.0 | Percent reduction in space infiltration rates |
| `alter_coef` | Boolean | False | Modify infiltration coefficients (disabled; always preserves) |

### Door Enhancement Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `door_option` | Choice | wooden door | Door type to install (none, wooden, garage, glass, polystyrene/polyurethane/honeycomb/stiffened core steel) |
| `door_lifetime` | Integer (years) | 30 | Product lifetime of door (default varies by type: wood=20, garage=15, glass=25, steel=30) |
| `door_area_per_unit` | Double (m²) | 1.95 | Declared unit area per EPD (typically 21 sq ft / 1.95 m²) |
| `door_thermal_conductivity` | Double (W/m·K) | 0.0 | Door material conductivity (0 = use typical value) |
| `door_density` | Double (kg/m³) | 0.0 | Door material density (0 = use typical value) |
| `door_thickness` | Double (m) | 0.0 | Door thickness (0 = use typical value) |

### Sealing Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `door_bottom_seal_option` | Choice | automatic door bottom | Bottom seal type (none, brush weatherstrip, automatic door bottom, silicone smoke gasket) |
| `door_top_side_seal_option` | Choice | jamb weatherstrip | Top/side seal type (none, silicone smoke gasket, jamb weatherstrip) |
| `strip_lifetime` | Integer (years) | 15 | Product lifetime of sealing strips |
| `length_per_unit_bottom_side` | Double (m) | 0.9144 | Length of bottom seal per unit door (~36 in) |
| `length_per_unit_other_sides` | Double (m) | 5.1816 | Length of top/side seal per unit door (~204 in) |

### Embodied Carbon (EC3)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `gwp_statistic` | Choice | median | Statistic for GWP values (minimum, maximum, mean, median) |
| `api_key` | String | — | EC3 API token for EPD database access |
| `analysis_period` | Integer (years) | 30 | Life-cycle analysis period (impacts embodied carbon calculations) |

### Cost Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `use_custom_costs` | Boolean | False | Use custom cost inputs instead of RSMeans API |
| `custom_door_cost_per_unit` | Double ($/m²) | 0.0 | Custom material + labor cost for door replacement |
| `custom_bottom_seal_cost` | Double ($/m) | 0.0 | Custom material + labor cost for bottom seal |
| `custom_top_side_seal_cost` | Double ($/m) | 0.0 | Custom material + labor cost for top/side seal |

---

## Usage Examples

### Example 1: Basic Setup (RSMeans Costs, EC3 Embodied Carbon)

Using the OpenStudio GUI or Parametric Analysis Tool (PAT):

1. Select door option: **polystyrene core steel door**
2. Select bottom seal: **automatic door bottom**
3. Select top/side seal: **jamb weatherstrip**
4. GWP statistic: **median**
5. API key: *(enter your EC3 token)*
6. Use custom costs: **False** (uses RSMeans API)

**Result**: Measure applies door replacement + sealing, calculates embodied carbon (GWP in kg CO2 eq), estimates costs via RSMeans with 10% overhead profit.

---

### Example 2: Custom Costs (Avoid API Calls)

Using `apply_measure.py` script:

```python
set_arg("use_custom_costs", True)
set_arg("custom_door_cost_per_unit", 3500.0)          # $/m²
set_arg("custom_bottom_seal_cost", 45.50)             # $/m
set_arg("custom_top_side_seal_cost", 22.75)           # $/m
```

**Result**: Same door enhancement applied, but uses your provided costs instead of RSMeans API. Useful when:
- You have quotes from contractors
- RSMeans API is unavailable
- You want to test cost sensitivity without API delays

---

### Example 3: Sensitivity Analysis (Multiple Cost Scenarios)

Using PAT with custom costs:

| Run | use_custom_costs | door_cost | seal_cost | Purpose |
|-----|------------------|-----------|-----------|---------|
| 1 | True | 2500 | 30 | Low-cost scenario |
| 2 | True | 3500 | 45 | Mid-cost scenario |
| 3 | True | 4500 | 60 | High-cost scenario |

**Result**: Compare life-cycle economics across cost assumptions.

---

## Running the Measure

### Method 1: OpenStudio Application GUI

1. Load building model (OSM file)
2. Measures → Add Measure → Locate door_enhancement measure
3. Fill in arguments via dialog form
4. Click "Run"
5. View results in measure output terminal

### Method 2: Test Script (apply_measure.py)

```bash
cd lib/measures/door_enhancement
python apply_measure.py
```

**Output**:
- Modified model saved to: `tests/output/EnvelopeAndLoadTestModel_01_door_enhanced.osm`
- Results JSON: `tests/output/apply_measure_results.json`
- Terminal output shows measure progress, RSMeans/custom cost summary, and AdditionalProperties verification

### Method 3: Parametric Analysis Tool (PAT)

1. Create new project in PAT
2. Import measure (measure.xml)
3. Set argument values and ranges
4. Run batch simulations
5. Export results to CSV/analysis

---

## Understanding the Outputs

### Terminal Output – Measure Summary

**Using RSMeans API:**
```
RSMeans cost summary (cost_source=rsmeans_api): 
materials=1, total_cost=$3,569.50
```

**Using Custom Costs:**
```
Custom cost summary (cost_source=custom_input): 
door_cost=$6,825.00 (2 doors @ $3,412.50/m²)
```

### AdditionalProperties Objects

The measure creates several AdditionalProperties objects on model entities:

#### **Facility** (EC3 Embodied Carbon Results)
```
[Facility]
  ec3_total_gwp_kg_co2eq: 45.23
  ec3_embodied_carbon_kg: 45.23
  ec3_statistics: median
```

#### **RSMeans Summary** (SpaceType Object)
```
[RSMeans Summary]
  cost_source: "rsmeans_api" or "custom_input"
  rsmeans_total_material_cost_$: 3245.00
  rsmeans_total_overhead_profit_cost_$: 324.50
  rsmeans_total_cost_with_overhead_profit_$: 3569.50
  rsmeans_unit_cost_line_id: 081116100020
  rsmeans_release_id: 2024-an
  rsmeans_location_id: us-us-national
  rsmeans_catalogs: bc-mf, gb-mf, rp-mf
```

#### **RSMeans Hit N** (Per-Material Details, SpaceType Objects)
```
[RSMeans Hit 1 - 081116100020]
  rsmeans_material_name: Polystyrene Core Steel Door
  rsmeans_quantity: 2.0
  rsmeans_unit: ea
  rsmeans_unit_cost_$: 1622.50
  rsmeans_total_cost_$: 3245.00
  rsmeans_search_term_used: polystyrene core steel door
  rsmeans_door_size: 3'-0" x 6'-8"
```

### Infiltration Adjustment

Spaces in the selected space type containing doors have their infiltration rates reduced by the specified percentage:

```
Original infiltration: 0.0006 m³/s·m²
Reduction: 30%
New infiltration: 0.00042 m³/s·m²
```

---

## Key Calculations

### Embodied Carbon (GWP)

For each material (door + seals):

$$\text{Total GWP (kg CO}_2\text{ eq)} = \text{GWP per unit} \times \text{Quantity} \times \left\lceil \frac{\text{Analysis Period}}{\text{Material Lifetime}} \right\rceil$$

Example:
- Door GWP: 12 kg CO₂ eq per m²
- Door area: 2 m²
- Door lifetime: 30 years
- Analysis period: 30 years
- **Total**: 12 × 2 × 1 = **24 kg CO₂ eq**

### Cost Calculations (RSMeans)

```
Material Cost = Unit Cost × Quantity
Overhead Profit (10%) = Material Cost × 0.10
Total Cost = Material Cost + Overhead Profit
```

Example:
- Unit cost: $1,622.50/door
- Quantity: 2 doors
- Material cost: $3,245.00
- Overhead (10%): $324.50
- **Total**: **$3,569.50**

---

## Troubleshooting

### Issue: "API token not found"

**Solution**: Ensure `config.ini` exists in repository root with EC3 API token:
```ini
[EC3_API_TOKEN]
API_TOKEN = your_token_here
```

### Issue: "RSMeans lookup failed" / "Call timed out"

**Causes**:
- RSMeans API credentials missing or invalid
- Network connectivity issue
- API rate limits exceeded

**Solutions**:
1. Verify environment variables: `RSMEANS_CLIENT_ID`, `RSMEANS_CLIENT_SECRET`
2. Check network connectivity
3. Use custom costs instead: set `use_custom_costs = True`

### Issue: "Zero cost returned from RSMeans"

**Cause**: Search term didn't match any RSMeans items

**Solutions**:
1. Check terminal output for "RSMeans search term" — verify spelling
2. Try custom costs with estimated values
3. Use simplified search term (e.g., "steel door" instead of "polystyrene core steel door")

### Issue: "No doors found in model"

**Cause**: Model contains no subsurfaces with Door/GlassDoor/OverheadDoor types

**Solution**: Verify model has doors defined. The measure only modifies existing doors; it doesn't create new ones.

---

## Advanced Topics

### Custom Material Properties

Override default material properties for doors:

```python
set_arg("door_thermal_conductivity", 0.05)     # W/m·K
set_arg("door_density", 400.0)                 # kg/m³
set_arg("door_thickness", 0.055)               # m
```

This updates the door construction U-value: **U = conductivity / thickness**

### Batch Cost Analysis

Use PAT to test cost sensitivity:

1. Set `use_custom_costs = True`
2. Create parameter ranges:
   - `custom_door_cost_per_unit`: 2000, 3000, 4000, 5000 ($/m²)
   - `custom_bottom_seal_cost`: 25, 50, 75 ($/m)
3. Run parametric study (12 scenarios)
4. Export results to CSV
5. Analyze cost vs. embodied carbon trade-offs

### Reporting Measures

The `apply_reporting_measure_door_enhancement.py` extracts results:

```python
# Reads door enhancement properties from model
# Parses EnergyPlus results (eplustbl.html)
# Generates combined operational + embodied carbon report
```

---

## Data Sources & References

### Embodied Carbon (EC3 Database)
- Source: https://www.buildingtransparency.org/ec3/
- Data: Environmental Product Declarations (EPDs)
- Metrics: Global Warming Potential (GWP) in kg CO₂ equivalents

### Door Material Properties
- Sources:
  - VT Industries AWD EPD: Wooden doors
  - DE LA FONTAINE EPDs: Steel core doors
  - ASHRAE Handbook – Fundamentals: Thermal conductivity
  - Door & Hardware Institute: Service life standards

### RSMeans API (Gordian)
- Release: 2024-an
- Location: US – National Average
- Catalogs Searched: BC-MF (Building Construction), GB-MF (Green Building), RP-MF (Repair & Remodeling)
- Labor Type: Standard
- Overhead & Profit: 10% (configurable)

---

## Support & Questions

For issues or questions:
1. Check the **Troubleshooting** section above
2. Review terminal output for error messages
3. Verify inputs in **Measure Arguments** section
4. Check GitHub issues (if applicable)
5. Contact measure maintainer

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1.0 | Mar 2026 | Added custom cost inputs; added cost_source identifier |
| 1.0.0 | Jan 2026 | Initial release with RSMeans API integration |

---

**Last Updated**: March 3, 2026

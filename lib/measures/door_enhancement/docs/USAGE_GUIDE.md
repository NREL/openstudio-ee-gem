# Door Enhancement Measure – Usage Guide

## Overview

The Door Enhancement measure does four things in one pass:

1. Reduces infiltration rates in target spaces
2. Adds/updates door sealing products (bottom + top/side)
3. Optionally replaces door constructions with new thermal properties
4. Calculates embodied carbon (EC3) and cost (RSMeans or custom)

## Fast Setup

From the measure directory:

```powershell
cd lib/measures/door_enhancement
./setup_environment.ps1
python apply_measure.py
```

The setup script validates `openstudio`, `python-dotenv`, and `numpy` imports.

## Credentials

- EC3 API token: `config.ini` under `[EC3_API_TOKEN]` as `API_TOKEN`
- RSMeans API credentials: `client_id` and `client_secret` (environment or `.env`)

## Key Arguments

| Argument | Type | Default | Purpose |
|---|---|---|---|
| `space_type` | Choice | *Entire Building* | Scope for infiltration reduction |
| `space_infiltration_reduction_percent` | Double | 30.0 | Infiltration reduction (%) |
| `door_bottom_seal_option` | Choice | automatic door bottom | Bottom seal type |
| `door_top_side_seal_option` | Choice | jamb weatherstrip | Top/side seal type |
| `door_option` | Choice | wooden door | Door replacement type (`none` = no replacement) |
| `analysis_period` | Integer | 30 | Embodied-carbon analysis period |
| `gwp_statistic` | Choice | median | Statistic for EPD GWP values |
| `use_custom_costs` | Boolean | false | If true, bypass RSMeans lookup |
| `rsmeans_unit_costline_id` | String | "" | Optional exact RSMeans ID override |

## Cost Modes

### RSMeans mode (`use_custom_costs = false`)

- Searches catalogs: `bc-mf`, `gb-mf`, `rp-mf`
- Applies minimum acceptable match score of **50.0**
- If score is too low, uses fallback IDs for known door materials

### Custom mode (`use_custom_costs = true`)

- Uses `custom_door_cost_per_area`, `custom_bottom_seal_cost`, `custom_top_side_seal_cost`
- Skips API lookups

## AdditionalProperties Buckets

The measure writes structured outputs to these five objects:

- Building (`basic_input`): measure metadata, analysis period
- Site (`reno_detail`): options + renovated quantities
- Facility (`factors`): cost totals + cost basis + GWP factors
- SimulationControl (`results`): mirrored costs + RSMeans JSON diagnostics
- SizingParameters (`mtrl_prop`): material properties + RSMeans extracted hints

## RSMeans Diagnostic Fields

When cost lookup succeeds, `SimulationControl.additionalProperties` includes:

- `door_enhancement_rsmeans_matches_json`
- `door_enhancement_rsmeans_search_results_json`
- `door_enhancement_rsmeans_summary_json`
- `door_enhancement_retrofit_materials_json`

It also includes cost basis fields:

- `door_enhancement_cost_factor_basis` (`cost_per_unit`, `cost_per_length`, `mixed`, etc.)
- `door_enhancement_cost_unit_basis` (`EA`, `LF`, `EA, LF`)

## Typical Output Files

- `tests/output/EnvelopeAndLoadTestModel_01_door_enhanced.osm`
- `tests/output/apply_measure_results.json`

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

#### **SizingParameters** (Door Material + RSMeans Match Context)
```
[SizingParameters]
  door_thickness_m: 0.04445
  door_conductivity_W_per_mK: 0.104
  door_density_kg_per_m3: 472.3
  rsmeans_door_match_description: "Doors & frames, ... 3'-0\" x 7'-0\" opening ..."
  rsmeans_door_area_per_unit_m2: 1.95
  rsmeans_door_thickness_m: 0.04445
  rsmeans_applied_door_option: "polystyrene core steel door"
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
1. Verify environment variables: `client_id`, `client_secret`
2. Check network connectivity
3. Use custom costs instead: set `use_custom_costs = True`

### Issue: "Zero cost returned from RSMeans"

**Cause**: Search term didn't match any RSMeans items

**Solutions**:
1. Check terminal output for "RSMeans search term" — verify spelling
2. Try custom costs with estimated values
3. Use simplified search term (e.g., "steel door" instead of "polystyrene core steel door")

### Issue: "Door area mismatch detected between model geometry and RSMeans match"

**Cause**: RSMeans parsed opening area and modeled door area differ by >10%, and `door_area_per_unit` was not explicitly provided.

**Solutions**:
1. Set `door_area_per_unit` explicitly to your intended declared-unit area.
2. Re-run and confirm the mismatch warning is expected for your model/RSMeans line item.
3. Optionally provide explicit `door_thickness` if RSMeans text does not include thickness.

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
  - `custom_door_cost_per_area`: 2000, 3000, 4000, 5000 ($/m²)
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

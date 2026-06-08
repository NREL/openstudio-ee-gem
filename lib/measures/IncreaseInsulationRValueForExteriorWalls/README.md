

###### (Automatically generated documentation)

# Increase R-value of Insulation for Exterior Walls to a Specific Value

## Description

This OpenStudio measure increases the effective insulation level of exterior walls to a target R-value by adding a supplemental insulation layer where needed.

It also:
- retrieves EPD data from EC3 to estimate embodied carbon,
- estimates cost via RSMeans (or optional custom cost input), and
- writes structured outputs to model AdditionalProperties for downstream reporting.

This measure is standalone and does not depend on the window enhancement measure.

## Key Features

- Exterior wall-only scope (surface type `Wall`, boundary `Outdoors`)
- Automatic added thickness calculation from target delta-R and selected thermal conductivity
- EC3-based embodied carbon estimates with outlier filtering (IQR)
- RSMeans multi-catalog lookup (`bc-mf`, `gb-mf`, `rp-mf`) with fallback ID support
- Optional exact RSMeans ID override (`use_exact_costline_id` + `exact_costline_id`)
- Optional custom cost path (`custom_cost_per_cf`)
- Structured AdditionalProperties write-out across 5 model objects

## Measure Arguments

| Name | Type | Default | Notes |
|---|---|---|---|
| `r_value` | Double | `13.0` | Target wall insulation R-value in `ft^2*h*R/Btu` |
| `analysis_period` | Integer | `30` | Embodied-carbon analysis horizon (years) |
| `gwp_statistic` | Choice | required | One of: `minimum`, `maximum`, `mean`, `median` |
| `api_key` | String | `Obtain the key from EC3 website` | EC3 token |
| `insulation_material_type` | Choice | `Fiberglass Batts` | One of 11 supported insulation material types |
| `insulation_material_lifetime` | Integer | `30` | Product lifetime in years |
| `insulation_thermal_conductivity` | Double | `0.0` | If `0.0`, the measure chooses a value from RSMeans extraction or defaults |
| `insulation_material_density` | Double | `0.0` | If `0.0`, the measure chooses a value from RSMeans extraction or defaults |
| `use_custom_costs` | Bool | `false` | If true, bypass RSMeans and use custom volume cost |
| `custom_cost_per_cf` | Double | `0.0` | Custom cost in `$/CF` |
| `labor_cost_multiplier` | Double | `1.0` | Applies only on custom cost path |
| `overhead_profit_percent` | Double | `10.0` | Applies to RSMeans-derived material cost |
| `use_exact_costline_id` | Bool | `false` | Deterministic RSMeans selection |
| `exact_costline_id` | String | `` | Used only when exact-ID mode is enabled |

## RSMeans Matching and Fallback

- Candidate descriptions are scored in range `0..100`.
- Fallback ID logic triggers when best score is below:
  - `MIN_ACCEPTABLE_MATCH_SCORE = 50.0`
- Fallback IDs are defined for most insulation types in `resources/call_rsmeans_api.py`.

Notes:
- `Pure Wool Batts` currently has no hardcoded fallback ID and stays search-based.
- RSMeans cost uses `localizedCosts.totalOpCost` (installed unit cost including labor + O&P at the line-item level).

## Cost Basis Tracking

The measure writes a cost-basis flag to AdditionalProperties:
- `wall_insulation_cost_factor_basis`

Possible values:
- `cost_per_area`
- `cost_per_volume`
- `custom_cost_per_volume`
- `mixed`
- `other`
- `not_calculated`

## AdditionalProperties Organization

The measure writes outputs into five buckets:

- Building (`basic_input`)
  - `measure_name`
  - `analysis_period_years`
  - `gwp_statistic`
  - `wall_insulation_construction_names`

- Site (`reno_detail`)
  - `wall_target_insulation_r_value_ip`
  - `wall_insulation_material_type`
  - `wall_insulation_renovated_area_m2`

- Facility (`factors` + mirrored cost visibility)
  - Emission factors:
    - `wall_insulation_material_gwp_per_kg`
    - `wall_insulation_material_gwp_per_m2`
    - `wall_insulation_material_gwp_per_m3`
  - Mirrored cost fields:
    - `wall_insulation_total_additional_material_cost_$`
    - `wall_insulation_total_additional_overhead_profit_cost_$`
    - `wall_insulation_total_additional_labour_cost_$`
    - `wall_insulation_total_cost_with_overhead_and_profit_$`
    - `wall_insulation_cost_source`
    - `wall_insulation_cost_factor_basis`

- SimulationControl (`results`)
  - `wall_insulation_retrofit_materials_json`
  - `wall_insulation_rsmeans_materials_detail_json`
  - `wall_insulation_total_additional_embodied_carbon_kg`
  - `wall_insulation_total_additional_material_cost_$`
  - `wall_insulation_total_additional_overhead_profit_cost_$`
  - `wall_insulation_total_additional_labour_cost_$`
  - `wall_insulation_total_cost_with_overhead_and_profit_$`
  - `wall_insulation_cost_source`
  - `wall_insulation_cost_factor_basis`
  - `wall_insulation_total_embodied_carbon_kgCO2eq`

- SizingParameters (`mtrl_prop`)
  - `wall_insulation_material_lifetime_years`
  - `wall_insulation_material_density_kg_per_m3`
  - `wall_insulation_material_thermal_conductivity_W_per_mK`
  - `wall_insulation_rsmeans_extracted_properties_json`

Per-construction compatibility keys are also written on each modified construction:
- `renovated_exterior_wall_area_m2`
- `total_embodied_carbon_kgCO2eq`
- `insutlation_material_type` (typo preserved intentionally for reporting compatibility)

## Quick Start

```bash
cd lib/measures/IncreaseInsulationRValueForExteriorWalls
./setup_environment.ps1   # Windows PowerShell
python apply_measure.py
```

## Related Docs

- `docs/Increase_Insulation_Walls.md`
- `docs/RSMEANS_SEARCH_STRATEGY.md`
- `docs/ENVIRONMENT_SETUP.md`

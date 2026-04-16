# IncreaseInsulationRValueForRoofs

## Purpose

Increase roof insulation to a target R-value, then record both embodied-carbon and cost outputs in standardized AdditionalProperties buckets for downstream reporting.

## Execution Phases

1. Parse and validate user arguments.
2. Optionally extract RSMeans-based density/conductivity hints.
3. Modify roof constructions to reach target R-value.
4. Query EC3 EPD data and calculate embodied carbon.
5. Run RSMeans or custom cost path and persist outputs.

## Arguments

Core:

- `r_value`
- `analysis_period`
- `gwp_statistic`
- `api_key`
- `insulation_material_type`
- `insulation_material_lifetime`
- `insulation_thermal_conductivity`
- `insulation_material_density`

Costing:

- `calculate_costs`
- `use_custom_costs`
- `use_exact_costline_id`
- `exact_costline_id`
- `custom_cost_per_cf`
- `labor_cost_multiplier`
- `overhead_profit_percent`

## Costing Paths

### RSMeans path (`calculate_costs=True`, `use_custom_costs=False`)

- Generates retrofit material records (area, thickness, volume).
- Searches RSMeans catalogs and captures detailed result/search logs.
- Applies overhead and profit percentage.
- Persists both summary fields and raw diagnostics JSON.

### Custom path (`use_custom_costs=True`)

- Uses total added insulation volume.
- Computes:
	- material = `custom_cost_per_cf * total_volume_cf`
	- labor = `material * (labor_cost_multiplier - 1)`
	- installed = `material + labor`

## AdditionalProperties Organization

Building (`basic_input`):

- measure-level identity and high-level inputs.

Site (`reno_detail`):

- renovation target and aggregate roof area quantities.

Facility (`factors`):

- mirrored high-level cost totals, source, and cost basis metadata.

SimulationControl (`results`):

- aggregate results and RSMeans diagnostics payloads.
- includes: `roof_insulation_rsmeans_matches_json`, `roof_insulation_rsmeans_search_results_json`, `roof_insulation_rsmeans_summary_json`.

SizingParameters (`mtrl_prop`):

- selected material properties and extracted RSMeans material hints.

## Cost Basis Metadata

The measure stores:

- `roof_insulation_cost_factor_basis` (for example `cost_per_area`, `cost_per_volume`, `cost_per_unit`, `mixed`, `custom_cost_per_volume`)
- `roof_insulation_cost_unit_basis` (for example `SF`, `CF`, or multiple values)

## Run Locally

```powershell
cd lib/measures/IncreaseInsulationRValueForRoofs
./setup_environment.ps1
python apply_measure.py
```

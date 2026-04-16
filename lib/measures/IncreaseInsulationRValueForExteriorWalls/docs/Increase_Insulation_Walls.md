# Increase Insulation R-Value for Exterior Walls

## What This Measure Does

This ModelMeasure upgrades exterior wall constructions to a target insulation R-value by adding a supplemental insulation layer.

It also computes:
- embodied carbon from EC3 EPD data, and
- cost from RSMeans (or custom user cost input).

The measure is standalone and does not rely on the window enhancement measure.

## Execution Flow

1. Parse and validate user arguments.
2. (Optional) Early RSMeans lookup to extract material properties (density and/or conductivity).
3. Identify exterior walls and clone/modify unique constructions.
4. Query EC3 and calculate embodied carbon over the analysis period.
5. Run cost path (RSMeans or custom) and write AdditionalProperties buckets.

## Supported Insulation Materials

- Blown Cellulose
- Blown Fiberglass
- Blown Mineral Wool
- Polyiso Insulation Foam Board
- Graphite Polystyrene (GPS) Foam Board
- Expanded Polystyrene (EPS) Foam Board
- Extruded Polystyrene (XPS) Foam Board
- Mineral Wool Heavy Density Blanket
- Mineral Wool Light Density Blanket
- Fiberglass Batts
- Pure Wool Batts

## Arguments

| Name | Type | Default | Description |
|---|---|---|---|
| `r_value` | Double | `13.0` | Target insulation R-value in `ft^2*h*R/Btu` |
| `analysis_period` | Integer | `30` | Analysis period in years |
| `gwp_statistic` | Choice | required | `minimum`, `maximum`, `mean`, or `median` |
| `api_key` | String | `Obtain the key from EC3 website` | EC3 token |
| `insulation_material_type` | Choice | `Fiberglass Batts` | Material to apply |
| `insulation_material_lifetime` | Integer | `30` | Service life in years |
| `insulation_thermal_conductivity` | Double | `0.0` | User override for conductivity (W/mK) |
| `insulation_material_density` | Double | `0.0` | User override for density (kg/m3) |
| `calculate_costs` | Bool | `true` | Toggle cost calculation |
| `use_custom_costs` | Bool | `false` | Use custom `$/CF` instead of RSMeans |
| `custom_cost_per_cf` | Double | `0.0` | Custom cost basis |
| `labor_cost_multiplier` | Double | `1.0` | Labor multiplier for custom cost path |
| `overhead_profit_percent` | Double | `10.0` | Overhead + profit percentage for RSMeans path |
| `use_exact_costline_id` | Bool | `false` | Use deterministic RSMeans line selection |
| `exact_costline_id` | String | empty | Explicit RSMeans ID |

## Cost Logic Summary

- `use_custom_costs = true`
  - cost computed from volume (`quantity_volume` in CF) and `custom_cost_per_cf`
  - `wall_insulation_cost_source = custom_input`
  - `wall_insulation_cost_factor_basis = custom_cost_per_volume`

- `use_custom_costs = false`
  - cost computed from RSMeans lookup via `resources/call_rsmeans_api.py`
  - material search uses candidate scoring and optional fallback IDs
  - current fallback threshold: `MIN_ACCEPTABLE_MATCH_SCORE = 50.0`
  - `wall_insulation_cost_factor_basis` is set to `cost_per_area`, `cost_per_volume`, `mixed`, or `other`

## AdditionalProperties Buckets

### Building (basic_input)
- `measure_name`
- `analysis_period_years`
- `gwp_statistic`
- `wall_insulation_construction_names`

### Site (reno_detail)
- `wall_target_insulation_r_value_ip`
- `wall_insulation_material_type`
- `wall_insulation_renovated_area_m2`

### Facility (factors + mirrored cost visibility)
- emission factors:
  - `wall_insulation_material_gwp_per_kg`
  - `wall_insulation_material_gwp_per_m2`
  - `wall_insulation_material_gwp_per_m3`
- mirrored cost fields:
  - `wall_insulation_total_additional_material_cost_$`
  - `wall_insulation_total_additional_overhead_profit_cost_$`
  - `wall_insulation_total_additional_labour_cost_$`
  - `wall_insulation_total_cost_with_overhead_and_profit_$`
  - `wall_insulation_cost_source`
  - `wall_insulation_cost_factor_basis`

### SimulationControl (results)
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

### SizingParameters (mtrl_prop)
- `wall_insulation_material_lifetime_years`
- `wall_insulation_material_density_kg_per_m3`
- `wall_insulation_material_thermal_conductivity_W_per_mK`
- `wall_insulation_rsmeans_extracted_properties_json`

### Construction-level compatibility keys
Each modified construction also stores:
- `renovated_exterior_wall_area_m2`
- `total_embodied_carbon_kgCO2eq`
- `insutlation_material_type` (intentional legacy typo for compatibility)

## Run Example

```bash
cd lib/measures/IncreaseInsulationRValueForExteriorWalls
python apply_measure.py
```

## Troubleshooting

- EC3 token issues: see `docs/ENVIRONMENT_SETUP.md`
- RSMeans credentials missing: set `client_id` and `client_secret` in environment or `.env`
- No wall changes: verify model has exterior walls with `outsideBoundaryCondition = Outdoors`
- No RSMeans match: use `use_custom_costs=true` or specify `exact_costline_id`

# Increase Insulation R-Value for Roofs

## Overview

This measure increases roof/ceiling insulation to a target R-value and computes embodied carbon using EC3 EPD data. It also performs RSMeans cost lookup for the added insulation quantity and stores results in AdditionalProperties for downstream reporting.

## Measure Type

ModelMeasure

## Description

- Identifies the insulation layer in roof constructions (prefers massless layers or highest R/thickness ratio)
- Adjusts insulation properties or thickness to hit a target R-value
- Calculates added insulation volume and embodied carbon (GWP) using EC3 EPDs
- Stores summarized results in AdditionalProperties on Facility and SimulationControl
- Calls RSMeans API to estimate material costs for the added insulation

## Inputs and Arguments

| Argument | Type | Units | Default | Description |
|----------|------|-------|---------|-------------|
| r_value | Double | ft²·h·°F/Btu | 30.0 | Target insulation R-value for roof constructions |
| analysis_period | Integer | years | 30 | Analysis period for embodied carbon calculation |
| gwp_statistic | Choice | - | median | Statistic for EPD GWP values (min/max/mean/median) |
| api_key | String | - | - | EC3 API token |
| insulation_material_type | Choice | - | Fiberglass Batts | Material type used for EPD lookup |
| insulation_material_lifetime | Integer | years | 30 | Default lifetime if EPD doesn’t provide one |
| insulation_thermal_conductivity | Double | W/m·K | 0.0 | 0 = use typical value for selected material |
| insulation_material_density | Double | kg/m³ | 0.0 | 0 = use typical or EPD-derived value |
| calculate_costs | Boolean | - | true | Enable cost calculation (RSMeans or custom) |
| use_custom_costs | Boolean | - | false | If true, skip RSMeans and use custom cost inputs |
| custom_cost_per_sf | Double | $/SF | 0.0 | Custom insulation material cost per square foot |
| labor_cost_multiplier | Double | - | 1.0 | Multiplier applied to custom material cost to estimate labor |
| overhead_profit_percent | Double | % | 10.0 | Overhead + profit applied to RSMeans material cost |

## Costing (RSMeans or Custom)

If `calculate_costs` is enabled, the measure uses one of two paths:

### RSMeans (default)
The measure prepares a retrofit material record based on the added roof insulation area and average added thickness. The RSMeans helper then:
- Searches for a closest-match line item (division 07)
- Returns unit and total cost
- Applies overhead/profit (`overhead_profit_percent`)

### Custom Costs
If `use_custom_costs` is true, RSMeans is skipped and:
- Material cost = `custom_cost_per_sf` × total roof insulation area (SF)
- Labor cost = material cost × (`labor_cost_multiplier` − 1)

Results are recorded in AdditionalProperties and reported in apply_measure.py.

## Outputs

### AdditionalProperties (Facility)
- roof_insulation_retrofit_materials_json
- roof_insulation_total_additional_material_cost_$
- roof_insulation_total_additional_overhead_profit_cost_$
- roof_insulation_total_additional_labour_cost_$
- roof_insulation_cost_source
- roof_insulation_material_gwp_per_kg
- roof_insulation_material_gwp_per_m2
- roof_insulation_material_gwp_per_m3

### AdditionalProperties (SimulationControl)
- roof_insulation_retrofit_materials_json
- roof_insulation_total_additional_embodied_carbon_kg
- roof_insulation_total_additional_material_cost_$
- roof_insulation_total_additional_overhead_profit_cost_$
- roof_insulation_total_additional_labour_cost_$
- roof_insulation_cost_source
- roof_insulation_total_embodied_carbon_kgCO2eq

### AdditionalProperties (Building/Site/Sizing)
- roof_target_insulation_r_value_ip
- roof_insulation_material_type
- roof_insulation_renovated_area_m2
- roof_insulation_material_lifetime_years
- roof_insulation_material_density_kg_per_m3
- roof_insulation_material_thermal_conductivity_W_per_mK
- roof_insulation_construction_names

## Running the Measure

```bash
cd lib/measures/IncreaseInsulationRValueForRoofs
python apply_measure.py
```

## Related Docs

- [Environment Setup](ENVIRONMENT_SETUP.md)
- [RSMeans Search Strategy](RSMEANS_SEARCH_STRATEGY.md)

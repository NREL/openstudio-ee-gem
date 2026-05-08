
# IncreaseInsulationRValueForRoofs

This measure upgrades roof insulation to a target R-value, estimates added embodied carbon from EC3 EPD data, and estimates added installed cost using RSMeans (or user-provided custom cost inputs).

## What It Does

- Identifies roof constructions and computes the insulation delta required to hit the target R-value.
- Applies insulation updates on cloned constructions, leaving the original unchanged.
- Aggregates added insulation quantities and embodied carbon (GWP) from EC3 EPDs.
- Runs RSMeans lookup for retrofit materials and stores full match/search diagnostics.
- Writes standardized outputs into model-level AdditionalProperties buckets.

## Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `r_value` | Double | 30.0 | Target R-value (ft²·h·°F/Btu) |
| `analysis_period` | Integer | 30 | Analysis period for embodied carbon (years) |
| `gwp_statistic` | Choice | median | Statistic for EPD GWP values (min/max/mean/median) |
| `api_key` | String | — | EC3 API token |
| `insulation_material_type` | Choice | Fiberglass Batts | Material for EPD lookup and RSMeans search |
| `insulation_material_lifetime` | Integer | 30 | Fallback lifetime if EPD has none (years) |
| `insulation_thermal_conductivity` | Double | 0.0 | 0 = use typical value for selected material (W/m·K) |
| `insulation_material_density` | Double | 0.0 | 0 = use typical or EPD-derived value (kg/m³) |
| `use_custom_costs` | Boolean | false | Skip RSMeans; use custom cost inputs instead |
| `use_exact_costline_id` | Boolean | false | Force RSMeans to use the exact `exact_costline_id` |
| `exact_costline_id` | String | "" | Exact RSMeans unit costline ID |
| `custom_cost_per_cf` | Double | 0.0 | Custom insulation cost per cubic foot ($/CF) |
| `labor_cost_multiplier` | Double | 1.0 | Multiplier on custom material cost to derive labor cost |
| `overhead_profit_percent` | Double | 10.0 | Overhead + profit applied on top of RSMeans cost (%) |

## AdditionalProperties Bucket Map

| OpenStudio Object | Variable | Contents |
|---|---|---|
| Building | `basic_input` | Measure name, analysis period, GWP statistic, construction names |
| Site | `reno_detail` | Target R-value, material type, total renovated area |
| Facility | `factors` | Mirrored cost totals, cost source, cost basis metadata, GWP factors |
| SimulationControl | `results` | All cost fields + RSMeans diagnostics JSON payloads |
| SizingParameters | `mtrl_prop` | Material density, conductivity, lifetime, RSMeans extracted hints |

## Cost Source Modes

- `rsmeans_api` — RSMeans closest-match or exact-ID lookup succeeded.
- `custom_input` — custom volume-based cost mode used.
- `none` — costing disabled or unresolved.

Cost basis is persisted as:
- `roof_insulation_cost_factor_basis` (e.g. `cost_per_volume`, `cost_per_area`, `custom_cost_per_volume`)
- `roof_insulation_cost_unit_basis` (e.g. `CF`, `SF`)

## Quick Start

```powershell
cd lib/measures/IncreaseInsulationRValueForRoofs
./setup_environment.ps1
python apply_measure.py
```

Outputs are written to:
- `tests/output/DOE_small_office_roof_insulation_upgraded.osm`
- `tests/output/apply_measure_results.json`

## Documentation

- [docs/Increase_Insulation_Roofs.md](docs/Increase_Insulation_Roofs.md) — full measure guide
- [docs/RSMEANS_SEARCH_STRATEGY.md](docs/RSMEANS_SEARCH_STRATEGY.md) — RSMeans search and scoring details
- [docs/ENVIRONMENT_SETUP.md](docs/ENVIRONMENT_SETUP.md) — environment setup and troubleshooting




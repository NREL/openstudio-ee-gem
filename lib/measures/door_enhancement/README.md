# DoorEnhancement

This measure improves door performance in OpenStudio models by adding sealing products (weatherstrip, automatic door bottom, silicone smoke gasket) and optionally replacing existing doors with more thermally efficient alternatives. It estimates added embodied carbon from EC3 EPD data and estimates installed cost using RSMeans (or user-provided custom cost inputs).

## What It Does

- Reduces space infiltration rates by a user-specified percentage to simulate improved air sealing from weatherstripping.
- Fetches EC3 EPD data for the selected bottom seal, top/side seal, and door replacement materials; calculates life-cycle embodied carbon (kg CO₂ eq) over the analysis period.
- When replacing doors, updates door construction R-values from material properties (thickness, conductivity, density).
- Runs RSMeans lookup for door components (door unit, bottom seal, top/side seal) and stores full match/search diagnostics.
- Writes standardized outputs into the five standard AdditionalProperties buckets.

## Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `space_type` | Choice | *Entire Building* | Space type to apply infiltration reduction |
| `space_infiltration_reduction_percent` | Double | 30.0 | Infiltration reduction (%) |
| `alter_coef` | Boolean | false | Alter temperature/wind coefficients (disabled; always preserved) |
| `door_area_per_unit` | Double | 1.95 | Door leaf area per unit (m²) per PCR declared unit |
| `analysis_period` | Integer | 30 | Analysis period for embodied carbon (years) |
| `door_bottom_seal_option` | Choice | automatic door bottom | Bottom seal product (none/brush weatherstrip/automatic door bottom/silicone adhesive smoke gasket) |
| `door_top_side_seal_option` | Choice | jamb weatherstrip | Top and side seal product (none/silicone adhesive smoke gasket/jamb weatherstrip) |
| `door_option` | Choice | wooden door | Door replacement type (none or any steel/glass/wood/garage option) |
| `strip_lifetime` | Integer | 15 | Service life of sealing strip (years) |
| `door_lifetime` | Integer | 30 | Service life of door (years) |
| `gwp_statistic` | Choice | median | GWP statistic for EPD values (minimum/maximum/mean/median) |
| `api_key` | String | — | EC3 API token |
| `length_per_unit_bottom_side` | Double | 0.9144 | Length per unit of bottom seal (m); 0.0 = use product default |
| `length_per_unit_other_sides` | Double | 5.1816 | Length per unit of top/side seal (m); 0.0 = use product default |
| `door_thermal_conductivity` | Double | 0.0 | Door conductivity (W/m·K); 0.0 = use material default |
| `door_density` | Double | 0.0 | Door density (kg/m³); 0.0 = use material default |
| `door_thickness` | Double | 0.0 | Door thickness (m); 0.0 = use material default |
| `use_custom_costs` | Boolean | false | Skip RSMeans; use custom cost inputs |
| `custom_door_cost_per_unit` | Double | 0.0 | Custom door cost ($/m²) |
| `custom_bottom_seal_cost` | Double | 0.0 | Custom bottom seal cost ($/m) |
| `custom_top_side_seal_cost` | Double | 0.0 | Custom top/side seal cost ($/m) |
| `rsmeans_unit_costline_id` | String | "" | Optional exact RSMeans unit cost line ID |

## AdditionalProperties Bucket Map

| OpenStudio Object | Variable | Contents |
|---|---|---|
| Building | `basic_input` | Measure name, analysis period, GWP statistic, construction names |
| Site | `reno_detail` | Door/seal options, total door area, sealing lengths, door count |
| Facility | `factors` | Cost totals, cost_source, cost_factor_basis, cost_unit_basis, GWP factors |
| SimulationControl | `results` | Mirrored cost scalars + three RSMeans diagnostic JSON payloads |
| SizingParameters | `mtrl_prop` | Door material properties, seal lengths, RSMeans-extracted hints |

## Cost Source Modes

- `rsmeans_api` — RSMeans search or exact-ID lookup succeeded.
- `custom_input` — custom cost mode used.
- `none` — costing disabled or unresolved.

Cost basis is persisted as:
- `door_enhancement_cost_factor_basis` (e.g. `cost_per_unit`, `cost_per_length`, `mixed`, `custom_cost_per_unit`)
- `door_enhancement_cost_unit_basis` (e.g. `EA`, `LF`, `EA, LF`)

## RSMeans Search Strategy

When `use_custom_costs = False`, the measure builds search materials for:
- The door (unit: `ea`, division `08`)
- Bottom seal (unit: `lf`, division `08`)
- Top/side seal (unit: `lf`, division `08`)

These are searched across three catalogs (`bc-mf`, `gb-mf`, `rp-mf`). If no search result scores ≥ 50.0 (the minimum acceptable match score), the helper falls back to hard-coded costline IDs in `DOOR_FALLBACK_RSMEANS_IDS`. Full search diagnostics are stored in three JSON fields on `SimulationControl`.

## Quick Start

```powershell
cd lib/measures/door_enhancement
./setup_environment.ps1
python apply_measure.py
```

Outputs are written to:
- `tests/output/DOE_small_office_door_enhanced.osm`
- `tests/output/apply_measure_results.json`

## Documentation

- [docs/USAGE_GUIDE.md](docs/USAGE_GUIDE.md) — user workflow and examples
- [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) — concise operational reference
- [docs/TECHNICAL.md](docs/TECHNICAL.md) — architecture, data flow, and algorithms
- [docs/CUSTOM_COSTS_IMPLEMENTATION.md](docs/CUSTOM_COSTS_IMPLEMENTATION.md) — custom cost mode details

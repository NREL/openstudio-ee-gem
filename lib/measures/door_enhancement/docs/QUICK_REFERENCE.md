# Door Enhancement – Quick Reference

## Run Locally

```powershell
cd lib/measures/door_enhancement
./setup_environment.ps1
python apply_measure.py
```

## Core Inputs

| Purpose | Argument | Typical Value |
|---|---|---|
| Target scope | `space_type` | `*Entire Building*` |
| Infiltration reduction | `space_infiltration_reduction_percent` | `30.0` |
| Door replacement type | `door_option` | `polystyrene core steel door` |
| Bottom seal | `door_bottom_seal_option` | `automatic door bottom` |
| Top/side seal | `door_top_side_seal_option` | `jamb weatherstrip` |
| Carbon stat | `gwp_statistic` | `median` |
| Cost mode | `use_custom_costs` | `false` |

## Cost Behavior

- `use_custom_costs = false`: RSMeans lookup across `bc-mf`, `gb-mf`, `rp-mf`
- `use_custom_costs = true`: custom cost inputs only
- Minimum acceptable RSMeans match score: **50.0**
- Lower scores trigger fallback ID lookup

## Cost Metadata Written

The measure always writes:

- `door_enhancement_cost_source`
- `door_enhancement_cost_factor_basis`
- `door_enhancement_cost_unit_basis`

Examples:

- `cost_source = rsmeans_api`
- `cost_factor_basis = cost_per_unit` / `cost_per_length` / `mixed`
- `cost_unit_basis = EA` / `LF` / `EA, LF`

## AdditionalProperties Buckets

- Building (`basic_input`)
- Site (`reno_detail`)
- Facility (`factors`)
- SimulationControl (`results`)
- SizingParameters (`mtrl_prop`)

## RSMeans Diagnostic JSON Fields

Stored on SimulationControl:

- `door_enhancement_rsmeans_matches_json`
- `door_enhancement_rsmeans_search_results_json`
- `door_enhancement_rsmeans_summary_json`
- `door_enhancement_retrofit_materials_json`

## Output Files

- `tests/output/EnvelopeAndLoadTestModel_01_door_enhanced.osm`
- `tests/output/apply_measure_results.json`

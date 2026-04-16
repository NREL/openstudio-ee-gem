# Door Enhancement Measure – Technical Notes

## Architecture

The measure consists of two primary scripts:

- `measure.py` – OpenStudio measure logic
- `resources/call_rsmeans_api.py` – RSMeans lookup helper

## Execution Phases (`measure.py`)

1. Argument parsing and validation
2. Infiltration reduction on target spaces
3. Embodied carbon calculation from EC3 EPD data
4. RSMeans (or custom) cost calculation
5. AdditionalProperties storage

## RSMeans Search Rules (`call_rsmeans_api.py`)

Lookup order per material:

1. Optional exact user-provided line ID (`rsmeans_unit_costline_id`)
2. Progressive text search alternatives across `bc-mf`, `gb-mf`, `rp-mf`
3. Hard-coded fallback line IDs for known door components

Candidate acceptance threshold:

- `MIN_ACCEPTABLE_MATCH_SCORE = 50.0`
- Best scored candidate below 50.0 triggers fallback-ID path

## Cost Basis Derivation

Cost basis is derived from matched RSMeans units:

- `EA` only -> `cost_per_unit`
- `LF` only -> `cost_per_length`
- mixed units -> `mixed`
- custom mode -> `custom_cost_per_unit`
- no result -> `not_calculated`

The unit-set string is stored as `door_enhancement_cost_unit_basis`.

## AdditionalProperties Storage Model

The measure uses five standard buckets:

- Building (`basic_input`)
- Site (`reno_detail`)
- Facility (`factors`)
- SimulationControl (`results`)
- SizingParameters (`mtrl_prop`)

### Key Cost Fields

On Facility and SimulationControl:

- `door_enhancement_cost_source`
- `door_enhancement_cost_factor_basis`
- `door_enhancement_cost_unit_basis`
- `door_enhancement_total_material_cost_$`
- `door_enhancement_total_overhead_profit_cost_$`
- `door_enhancement_total_cost_with_overhead_profit_$`

### RSMeans Diagnostic JSON Fields

On SimulationControl:

- `door_enhancement_rsmeans_matches_json`
- `door_enhancement_rsmeans_search_results_json`
- `door_enhancement_rsmeans_summary_json`
- `door_enhancement_retrofit_materials_json`

## Local Validation Workflow

```powershell
cd lib/measures/door_enhancement
./setup_environment.ps1
python apply_measure.py
```

`apply_measure.py` verifies bucket output and writes:

- `tests/output/EnvelopeAndLoadTestModel_01_door_enhanced.osm`
- `tests/output/apply_measure_results.json`

### Cost Aggregation (RSMeans)

```python
material_cost = unit_cost × quantity
overhead_profit = material_cost × overhead_percent
total_cost = material_cost + overhead_profit
```

Example:
```
Unit cost: $1,622.50/ea
Quantity: 2 doors
Material cost: $1,622.50 × 2 = $3,245.00
Overhead (10%): $3,245.00 × 0.10 = $324.50
─────────────────────────────────────
Total cost: $3,569.50
```

---

## AdditionalProperties Schema

### Facility (EC3 Results)

| Property Name | Type | Example | Notes |
|---------------|------|---------|-------|
| ec3_total_gwp_kg_co2eq | Double | 45.23 | Total embodied carbon |
| ec3_embodied_carbon_kg | Double | 45.23 | Alias for above |
| ec3_statistics | String | "median" | Which statistic used |

### RSMeans Summary (SpaceType)

| Property Name | Type | Example | Notes |
|---------------|------|---------|-------|
| cost_source | String | "rsmeans_api" or "custom_input" | Identifies cost method |
| rsmeans_total_material_cost_$ | Double | 3245.00 | Material costs only |
| rsmeans_total_overhead_profit_cost_$ | Double | 324.50 | Overhead/labor (10% for API) |
| rsmeans_total_cost_with_overhead_profit_$ | Double | 3569.50 | Total project cost |
| rsmeans_unit_cost_line_id | String | "081116100020" | RSMeans identifier |
| rsmeans_release_id | String | "2024-an" | RSMeans version |
| rsmeans_location_id | String | "us-us-national" | Geographic location |
| rsmeans_measurement_system | String | "imp" | Units (imperial/metric) |
| rsmeans_catalogs | String | "bc-mf, gb-mf, rp-mf" | Catalogs searched |

### RSMeans Hit N (Per-Material Details, SpaceType)

| Property Name | Type | Example | Notes |
|---------------|------|---------|-------|
| rsmeans_material_name | String | "Polystyrene Core Steel Door" | Material searched |
| rsmeans_quantity | Double | 2.0 | Units found/applied |
| rsmeans_unit | String | "ea" | Unit of measure |
| rsmeans_unit_cost_$ | Double | 1622.50 | Cost per unit |
| rsmeans_total_cost_$ | Double | 3245.00 | Total for quantity |
| rsmeans_search_term_used | String | "steel door" | Actual search used |
| rsmeans_id | String | "081116100020" | RSMeans line ID |
| rsmeans_door_size | String | "3'-0" × 6'-8"" | Inferred size |
| rsmeans_catalog | String | "bc-mf" | Catalog matched |

### SizingParameters (Door Material + RSMeans Match Context)

| Property Name | Type | Example | Notes |
|---------------|------|---------|-------|
| door_thickness_m | Double | 0.04445 | Applied thickness used in replacement |
| door_conductivity_W_per_mK | Double | 0.104 | Applied conductivity |
| door_density_kg_per_m3 | Double | 472.3 | Applied density |
| rsmeans_door_match_description | String | "Doors & frames ... 3'-0\" x 7'-0\" opening" | Closest RSMeans door description |
| rsmeans_door_area_per_unit_m2 | Double | 1.95 | Parsed opening area from RSMeans description |
| rsmeans_door_thickness_m | Double | 0.04445 | Parsed thickness from RSMeans description |
| rsmeans_applied_door_option | String | "polystyrene core steel door" | Inferred/selected replacement type |

### RSMeans-Driven Door Replacement Logic

After RSMeans lookup succeeds for door materials:
1. Select closest door hit (`ea`/`each` + door name/description).
2. Parse opening area and thickness from the RSMeans description when present.
3. Infer door option keywords (garage, glass, wood, core steel variants).
4. Build replacement material properties from inferred defaults + parsed thickness.
5. Apply explicit user overrides (`door_thickness`, `door_density`, `door_thermal_conductivity`) when provided.
6. Replace subsurface door construction using the resulting properties.

Area mismatch guard:
- If parsed RSMeans opening area differs from model average door area by >10%, a warning is emitted.
- If that mismatch occurs while `door_area_per_unit` remains default, the measure errors and requests explicit `door_area_per_unit` input.

---

## Error Handling

### EC3 API Failures

```python
try:
    gwp_data = ec3_data_fetch(url, api_key)
except Exception as e:
    runner.registerWarning(f"EC3 lookup failed: {e}")
    # Falls back to zero cost or skips material
```

### RSMeans API Failures

```python
if use_custom_costs:
    # Skip API, use custom values
    rsmeans_lookup = {...custom values...}
else:
    try:
        rsmeans_lookup = run_rsmeans_cost_lookup(...)
    except Exception as e:
        runner.registerWarning(f"RSMeans lookup failed: {e}")
        # Results still saved, but cost data missing
```

### Missing Model Objects

```python
if len(sub_surfaces_to_change) == 0:
    runner.registerInfo("No doors found; skipping cost lookup")
    # Measure continues with infiltration reduction only
```

---

## Testing

### Unit Tests (test_call_rsmeans_api.py)

Deterministic helper tests:
- Handles both search response shapes (`items` and `unitLines.items`)
- Filters demo/demolition matches
- Resolves exact unit cost line item by id

### Unit Tests (test_rsmeans.py)

Deterministic lookup behavior tests:
- Door search term alternatives include door-specific terms
- Door helper does not inject window-specific search boilerplate terms
- Door fallback ID mapping is pinned to expected ids
- Direct search match path vs fallback id path
- Different material applications produce different RSMeans ids and costs
- Measure-level surfacing of fallback warnings/count

### Integration Test (apply_measure.py)

Full measure execution on sample model:
1. Loads test OSM
2. Runs with sample arguments
3. Verifies AdditionalProperties created
4. Exports results JSON

**Run**:
```bash
cd lib/measures/door_enhancement
python apply_measure.py
```

**Output**:
- Modified model: `tests/output/EnvelopeAndLoadTestModel_01_door_enhanced.osm`
- Results: `tests/output/apply_measure_results.json`

---

## Performance Considerations

### API Call Optimization

- **EC3 lookups**: Cached per material name (if same material used multiple times)
- **RSMeans lookups**: Single batch call per material (all doors together)
- **Custom costs**: No API calls; instant execution

### Memory Usage

- **Large models** (500+ doors): May accumulate many AdditionalProperties objects
  - Solution: Use custom costs or batch smaller models
- **RSMeans Hit objects**: Create one SpaceType per hit
  - Solution: Aggregate in summary only if detailed per-hit tracking not needed

### Typical Execution Time

| Scenario | Time |
|----------|------|
| Custom costs (no API) | < 1 second |
| RSMeans API (2 doors) | 3-5 seconds |
| EC3 + RSMeans (full) | 5-10 seconds |

---

## Security & Privacy

### API Key Protection

1. **Environment variables**: `client_id`, `client_secret`
2. **Config file**: `config.ini` (EC3 token) excluded via `.gitignore`
3. **Log redaction**: API keys redacted as `<redacted>` in terminal output
4. **.gitignore rules**:
   ```
   config.ini
   .env
   *.env
   ```

### No Automatic Commits of Secrets

- Use `.gitignore` to prevent accidental key commits
- Consider pre-commit hooks (gitleaks) for additional security
- Never commit credentials; always use environment variables or .gitignore'd config files

---

## Future Enhancements

1. **Material database caching**: Cache EC3 results locally
2. **Cost breakdown**: Separate material vs. labor costs in output
3. **Thermal performance**: Update door U-values based on construction
4. **Multiple door types**: Support different door types in single run
5. **Export templates**: Pre-made cost/carbon summaries to CSV
6. **Sensitivity analysis**: Built-in parameter variation mode

---

## References

- **OpenStudio SDK**: https://openstudio.net/
- **EC3 Database**: https://www.buildingtransparency.org/ec3/
- **RSMeans API**: Gordian (https://www.gordian.com/)
- **EPD Standards**: ISO 14025, EN 15804

---

**Last Updated**: March 3, 2026
**Measure Version**: 1.1.0

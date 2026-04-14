# Door Enhancement Measure – Technical Documentation

## Architecture Overview

The Door Enhancement measure is a **ModelMeasure** that modifies OpenStudio models by:
1. Reducing infiltration rates on spaces containing doors
2. Optionally replacing door constructions with higher-performance alternatives
3. Calculating embodied carbon impacts via EC3 API
4. Estimating construction costs via RSMeans API or custom inputs

### File Structure

```
lib/measures/door_enhancement/
├── measure.py                              # Main measure logic
├── measure.xml                             # OpenStudio measure metadata
├── resources/
│   └── call_rsmeans_api.py                # RSMeans API client (modular)
├── tests/
│   ├── test_call_rsmeans_api.py           # Unit tests for RSMeans
│   ├── EnvelopeAndLoadTestModel_01.osm    # Test building model
│   └── output/                             # Test run outputs
├── apply_measure.py                        # Test harness (runs measure on sample)
├── apply_reporting_measure_door_enhancement.py  # Post-simulation reporting
├── docs/
│   ├── USAGE_GUIDE.md                     # User-facing documentation
│   └── TECHNICAL.md                       # This file
└── README.md                               # Measure summary
```

---

## Core Components

### 1. DoorEnhancement Class (measure.py)

**Inheritance**: `openstudio.measure.ModelMeasure`

#### Key Methods

##### `name()` / `description()` / `modeler_description()`
Standard OpenStudio measure metadata.

##### `arguments(model)` → OSArgumentVector
Defines 18 user-configurable arguments:
- **Space selection**: Which spaces to modify
- **Infiltration**: Reduction percentage
- **Door options**: Type, lifetime, thermal properties
- **Sealing options**: Type, lifetime, lengths
- **Embodied carbon**: GWP statistic, EC3 API key, analysis period
- **Costs**: Custom vs. RSMeans, cost values

##### `run(model, runner, user_arguments)` → Boolean
Main execution method. Orchestrates:
1. Argument validation & retrieval
2. Space type selection (building-wide or specific)
3. Door subsurface identification
4. Infiltration reduction calculations
5. EC3 API lookups (GWP per material)
6. RSMeans API lookups or custom cost assignment
7. AdditionalProperties storage
8. Terminal output reporting

**Returns**: True on success, False on failure

---

### 2. EC3 Integration (resources/EC3_lookup.py)

**Purpose**: Query Environmental Product Declaration database for embodied carbon

**Key Functions**:

#### `generate_url_byname(name_like, category=None, plant_geography=None)`
Constructs EC3 API search URL with filters.

#### `ec3_data_fetch(url, api_token)`
Calls EC3 API and parses JSON response.

**Response Format**:
```json
{
  "results": [
    {
      "name": "Steel Door Leaf - Polystyrene Core",
      "gwp_median": 12.5,
      "gwp_mean": 13.2,
      "gwp_min": 11.0,
      "gwp_max": 15.0,
      "unit": "kg CO2eq/m²"
    }
  ]
}
```

**Error Handling**:
- Retry logic for timeouts
- Outlier removal (IQR method)
- Fallback to median if statistical aggregation fails

---

### 3. RSMeans Integration (resources/call_rsmeans_api.py)

**Purpose**: Query construction cost data for materials and labor

**Key Components**:

#### RSMeansAPIClient Class
Manages authentication and API calls.

**Methods**:
- `authenticate()`: Obtains bearer token via client credentials
- `search_unit_costlines(release_id, measurement_system, search_term, catalog, location_id, labor_type, division_code)`: Searches one catalog for candidate lines
- `get_unit_costlines(release_id, measurement_system, division_code, catalog, location_id, labor_type)`: Retrieves line-item costs for a specific unit cost line id

**Configuration**:
```python
release_id = "2024-an"        # RSMeans release year
catalogs = ["bc-mf", "gb-mf", "rp-mf"]  # Catalogs to search
location_id = "us-us-national"  # Geographic location
labor_type = "std"             # Labor classification
measurement_system = "imp"     # Imperial (feet, pounds)
```

#### `search_materials_across_catalogs(materials, ...)`
Intelligent multi-catalog search with fallbacks:
1. Try exact material name in BC-MF (Building Construction)
2. If zero results, try GB-MF (Green Building)
3. If zero results, try RP-MF (Repair & Remodeling)
4. Generate alternative search terms (strip sizes, simplify keywords)
5. Retry with alternatives
6. If still unmatched, attempt door-specific fallback RSMeans IDs for known materials

Notes:
- The helper is door-measure standalone; it no longer depends on window measure files/properties.
- Standalone CLI lookup reads door-specific sources (`door_enhancement_retrofit_materials.json` and `door_enhancement_retrofit_materials_json`).

**Returns**:
```python
{
  "total_cost": 3245.0,
  "materials": [
    {
      "name": "Polystyrene Core Steel Door",
      "rsmeans_id": "081116100020",
      "unit_cost": 1622.50,
      "total_cost": 3245.00,
      "catalog": "bc-mf",
      "source": "rsmeans_search"
    }
  ],
  "warnings": [
    "Used fallback RSMeans ID ..."
  ],
  "fallback_count": 1,
  "search_log": []
}
```

#### `run_rsmeans_cost_lookup(materials, ...)`
Main entry point orchestrating:
1. Catalog search
2. Cost aggregation
3. Overhead profit calculation (10% default)
4. Summary generation

**Parameters**:
- `materials`: List of dicts with `name`, `quantity`, `unit`, `division_code`
- `overhead_profit_percent`: Markup percentage (e.g., 10.0)
- `use_sandbox`: False for production API

---

### 4. Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User Input (OpenStudio GUI / apply_measure.py)              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────────┐
        │ Run Measure        │
        │ measure.py:run()   │
        └────────┬───────────┘
                 │
        ┌────────▼──────────────────────────────────┐
        │ 1. Identify Door Subsurfaces              │
        │ 2. Reduce Infiltration (-30% default)     │
        │ 3. Query EC3 API (embodied carbon)        │
        │ 4. Lookup Costs (RSMeans or Custom)       │
        │ 5. Create AdditionalProperties Objects    │
        └────────┬──────────────────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ EC3 API                        │
        │ (GWP: kg CO2eq per unit)       │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ Cost Lookup (Choose One):      │
        │ - RSMeans API (API credentials)│
        │ - Custom Values (User input)   │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────────────┐
        │ Store Results in Model:                │
        │ - Facility AdditionalProperties (EC3)  │
        │ - RSMeans Summary SpaceType (costs)    │
        │ - RSMeans Hit N SpaceTypes (per-item)  │
        └────────┬──────────────────────────────┘
                 │
        ┌────────▼──────────────────────────────┐
        │ Output:                                │
        │ - Modified OSM file                    │
        │ - Terminal logs (measure progress)    │
        │ - JSON results (step values)          │
        └────────────────────────────────────────┘
```

---

## Key Algorithms

### Infiltration Reduction

For each space in target space type containing doors:

```python
new_infiltration = original_infiltration × (1 - reduction_percent / 100)
```

Example:
- Original: 0.0006 m³/s·m²
- Reduction: 30%
- New: 0.0006 × (1 - 30/100) = **0.00042 m³/s·m²**

### Embodied Carbon Calculation

For each material (door, seals):

```python
total_gwp = gwp_per_unit × quantity × ceil(analysis_period / material_lifetime)
```

**Components**:
1. **GWP per unit**: From EC3 database (median, mean, min, or max)
2. **Quantity**: Calculated from door count and seal lengths
3. **Replacement cycles**: How many times material is replaced over analysis period

Example:
```
Door: 12 kg CO2e/m² × 2 m² × 1 cycle (30yr) = 24 kg CO2e
Bottom seal: 0.5 kg CO2e/m × 0.9 m × 2 cycles (30yr ÷ 15yr) = 0.9 kg CO2e
Top/side seal: 0.8 kg CO2e/m × 5.2 m × 2 cycles = 8.32 kg CO2e
─────────────────────────────────────────────────────────
Total embodied carbon = 24 + 0.9 + 8.32 = 33.22 kg CO2e
```

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

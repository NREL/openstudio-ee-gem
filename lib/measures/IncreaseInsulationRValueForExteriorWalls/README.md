# Increase R-value of Insulation for Exterior Walls to a Specific Value

## Description

This OpenStudio measure automates the process of adding insulation to exterior walls in building energy models. It increases the thermal resistance (R-value) of all exterior walls to a specified target value, calculates embodied carbon impacts using Environmental Product Declaration (EPD) data, and estimates construction costs using the RSMeans API.

The measure integrates with:
- **EC3 (Building Transparency)** for Environmental Product Declaration data and embodied carbon calculations
- **RSMeans API (Gordian)** for accurate construction cost estimation
- **OpenStudio** for thermal and construction model modifications

## Features

- **Automatic Wall Upgrade:** Increases R-value of all exterior walls to target value
- **Material Selection:** Choose from multiple insulation types (Fiberglass, Mineral Wool, XPS, Polyiso)
- **Embodied Carbon Calculation:** Uses EC3 API to retrieve EPD data and calculate lifecycle carbon impact
- **Cost Estimation:** Integrates RSMeans API for professional cost estimates or supports volume-based custom cost input
- **Flexible Cost Calculation:** Choose between RSMeans lookup, custom override ($/CF volume basis), or no cost calculation
- **Material Property Extraction:** Automatically extracts density and thermal properties from RSMeans descriptions
- **Smart Property Fallback:** Material properties sourced from: user input → RSMeans-extracted → hardcoded defaults
- **Overhead & Profit:** Configurable contractor markup percentage (RSMeans only)
- **Results Export:** All calculations stored in model AdditionalProperties as JSON

## Modeler Description

This measure modifies the construction assemblies of all exterior walls in the model by adding an insulation layer with the specified material type. The thermal properties of the new layer are calculated to achieve the target R-value. The measure also:

1. Looks up material embodied carbon data from EC3 API based on material type and installation area
2. Searches RSMeans database for construction cost data (Division 07 - Thermal and Moisture Protection)
3. Stores all results (costs, embodied carbon, material data) in the output model's AdditionalProperties
4. Provides a JSON results file with complete calculation details

## Measure Type
ModelMeasure

## Taxonomy
Envelope.Exterior Walls.Insulation

## Arguments

### Core Insulation Parameters

#### Insulation R-value (IP units: Btu·h·ft²/°F)

**Name:** `r_value`  
**Type:** Double  
**Units:** Btu·h·ft²/°F  
**Required:** true  
**Model Dependent:** false  
**Default:** 20.0  
**Description:** Target R-value for exterior walls after insulation is added. Higher values provide better thermal resistance.

#### Insulation Material Type

**Name:** `insulation_material_type`  
**Type:** Choice  
**Required:** true  
**Model Dependent:** false  
**Default:** Fiberglass Batts  
**Options:**
- Fiberglass Batts (most cost-effective, ~$1.18/SF)
- Mineral Wool Batts (better fire/moisture resistance, ~$1.40/SF)
- Extruded Polystyrene Foam (high performance, ~$1.60/SF)
- Polyiso Foam (balanced performance, ~$1.45/SF)

#### Apply to Existing Walls

**Name:** `apply_to_existing_walls`  
**Type:** Boolean  
**Required:** false  
**Model Dependent:** true  
**Default:** true  
**Description:** If true, add insulation to all exterior walls including those with existing insulation. If false, only upgrade walls without existing insulation.

### Analysis Parameters

#### Analysis Period (years)

**Name:** `analysis_period`  
**Type:** Integer  
**Units:** years  
**Required:** false  
**Model Dependent:** false  
**Default:** 30  
**Description:** Lifetime period for embodied carbon analysis. Typical values: 30-60 years.

#### GWP Statistic

**Name:** `gwp_statistic`  
**Type:** Choice  
**Required:** false  
**Model Dependent:** false  
**Default:** median  
**Options:**
- average (arithmetic mean of EPD data)
- median (middle value, most representative)
- conservative (highest value, worst-case scenario)

**Description:** Which statistic to use from the Environmental Product Declaration data.

### Cost Calculation Parameters

#### Calculate Costs

**Name:** `calculate_costs`  
**Type:** Boolean  
**Required:** false  
**Model Dependent:** false  
**Default:** true  
**Description:** If true, enable cost calculation via RSMeans API or custom values. If false, no cost estimation is performed.

#### Use Custom Costs

**Name:** `use_custom_costs`  
**Type:** Boolean  
**Required:** false  
**Model Dependent:** false  
**Default:** false  
**Description:** If true, use `custom_cost_per_cf` instead of RSMeans API lookup. Useful when RSMeans data is unavailable or you have known costs.

#### Custom Cost per Cubic Foot ($/CF)

**Name:** `custom_cost_per_cf`  
**Type:** Double  
**Units:** $/CF (cubic feet)  
**Required:** false  
**Model Dependent:** false  
**Default:** 5.0  
**Description:** Cost per cubic foot of insulation volume if `use_custom_costs` is enabled. Volume is calculated as: added thickness (m) × wall area (m²). Only used when custom costs are selected.

#### Overhead & Profit Percentage

**Name:** `overhead_profit_percent`  
**Type:** Double  
**Units:** % (percentage)  
**Required:** false  
**Model Dependent:** false  
**Default:** 10.0  
**Description:** Contractor overhead and profit markup as a percentage of material cost. Typical range: 10-20%.

### API Configuration

#### EC3 API Key

**Name:** `api_key`  
**Type:** String  
**Required:** false  
**Model Dependent:** false  
**Default:** (empty)  
**Description:** Environmental Product Declaration API token from Building Transparency (https://buildingtransparency.org). Leave empty to skip embodied carbon calculations or read from `config.ini`.

## Outputs

### Modified OpenStudio Model

The measure generates a new OSM file with:
- Updated exterior wall constructions with added insulation layer
- Modified material assignments to achieve target R-value
- All calculation results stored in AdditionalProperties

### Results File

A JSON file (`apply_measure_results.json`) containing:
- Step values (measure arguments)
- Material information from RSMeans lookup
- Cost calculation breakdown (material, labor, overhead, total)
- Embodied carbon results from EC3 API
- Environmental Product Declaration data

## Example Outputs

### Custom Cost Calculation (Volume Basis)
```
Added Insulation Volume: 245.00 CF (cubic feet)
Custom Cost Rate:        $10.00/CF
Total Material Cost:     $2,450.00
Labor Cost (multiplier): $2,450.00 (1x material cost)
Total Cost:              $4,900.00
```

### RSMeans Cost Breakdown
```
Applied Area:           268.19 m²
Material Cost:          $3,406.37
Overhead/Profit:        $340.64 (10%)
Total Cost:             $3,747.00
Cost per M²:            $13.97
```

### Embodied Carbon
```
Applied Area:        268.19 m²
Material:            Fiberglass Batts insulation
Embodied Carbon:     98.11 kg CO2 eq
Analysis Period:     30 years
GWP Statistic:       Median
```

## Documentation

For detailed information, see:

- **[Increase_Insulation_Walls.md](docs/Increase_Insulation_Walls.md)** - Complete measure documentation with usage examples and flow diagram
- **[ENVIRONMENT_SETUP.md](docs/ENVIRONMENT_SETUP.md)** - API configuration and environment setup guide
- **[RSMEANS_SEARCH_STRATEGY.md](docs/RSMEANS_SEARCH_STRATEGY.md)** - Cost data lookup customization and search strategy

## Material Property Sourcing

The measure intelligently selects material properties using a priority-based fallback chain:

1. **User-Provided** (highest priority): Custom values for thermal conductivity and density if explicitly provided
2. **RSMeans-Extracted**: Properties parsed from RSMeans description fields (density in pcf, R-value, etc.)
3. **Hardcoded Defaults** (lowest priority): Pre-configured values for each insulation type

This approach ensures accuracy when RSMeans data is available while maintaining robustness through fallback values. All property sources are logged during measure execution for transparency.

## Testing

The measure includes unit tests for error handling and message validation:

- `tests/test_rsmeans_error_message_content.py` - Validates error message format, sections, and parameter consistency
- `tests/test_rsmeans_error_handling.py` - Integration tests for RSMeans lookup failures and retry guidance

Run tests with:
```bash
python -m pytest lib/measures/IncreaseInsulationRValueForExteriorWalls/tests/ -v
```

## Quick Start

### 1. Setup Environment

```bash
# Install required packages
pip install openstudio requests python-dotenv

# Configure APIs
# Add EC3 token to config.ini
# Add RSMeans credentials to .env
```

### 2. Run the Measure

```bash
cd lib/measures/IncreaseInsulationRValueForExteriorWalls
python apply_measure.py
```

### 3. Check Results

- Model: `DOE_small_office_wall_insulation_upgraded.osm`
- Results: `apply_measure_results.json`
- Logs: Console output shows all calculations and API responses

## Requirements

- OpenStudio 3.9.0 or higher
- Python 3.8 or higher
- EC3 API token (for embodied carbon calculations)
- RSMeans API credentials (for cost estimation)

## API Credentials

### EC3 (Building Transparency)
- Create account: https://buildingtransparency.org
- Store token in `config.ini` at repository root
- Required for embodied carbon calculations

### RSMeans (Gordian)
- Obtain credentials from your organization
- Store in `.env` file at repository root
- Required for cost estimation via RSMeans API

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "EC3 API token not found" | Verify `config.ini` contains valid token |
| "RSMeans API credentials not found" | Check `.env` file has `client_id` and `client_secret` |
| "No walls modified" | Ensure input model has defined exterior walls |
| "Costs showing as $0" | Verify RSMeans API is accessible; check search terms |
| "Wall areas are zero" | Check that exterior walls have valid surface geometry |

See [ENVIRONMENT_SETUP.md](docs/ENVIRONMENT_SETUP.md) for detailed troubleshooting.

## Advanced Customization

### Change Search Material

Edit [measure.py](measure.py) around line 625:

```python
search_term = "Extruded Polystyrene insulation"  # Change material
division_code = "07"                             # Change division
catalog_ids = ["bc-mf", "gb-mf", "rp-mf"]      # Change catalogs
```

### Adjust Cost Calculation

Use measure arguments:
- `use_custom_costs`: Override with known cost
- `overhead_profit_percent`: Adjust contractor markup

### Use Different Insulation Material

Select from available options in `insulation_material_type` argument, or add new materials by editing the measure argument choices.

## Related Measures

- **IncreaseInsulationRValueForRoofs** - Similar measure for roof insulation
- **WindowEnhancementwithRSMeans** - Window upgrades with cost estimation
- **ReduceTransmissionFromVinylWindows** - Window replacement

## License

See LICENSE.md in repository root.

## Support

For issues or questions:
1. Check the documentation in the `docs/` folder
2. Review the [RSMEANS_SEARCH_STRATEGY.md](docs/RSMEANS_SEARCH_STRATEGY.md) for cost-related issues
3. Consult OpenStudio and API documentation references





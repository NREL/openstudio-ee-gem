# RSMeans Search Strategy

## Overview

This measure uses the RSMeans API (Gordian) to automatically lookup cost data for wall insulation materials. The search strategy is designed to find the most relevant material from the RSMeans database and extract reliable cost estimates.

## Search Configuration

### Default Material Search
- **Material:** Fiberglass Batts
- **Search Term:** "Fiberglass Batts insulation"
- **Division Code:** 07 (Thermal and Moisture Protection)
- **Catalogs:** bc-mf, gb-mf, rp-mf (Building Construction Materials, Green Building, Residential Products)

### Why This Approach?

1. **Specific Material Name:** "Fiberglass Batts insulation" is more specific than just "Fiberglass" to reduce ambiguous matches
2. **Division Code 07:** Thermal and Moisture Protection is the standard division for insulation materials in RSMeans
3. **Multiple Catalogs:** Searching across three catalogs ensures broader coverage of material availability
4. **Standard Product:** Fiberglass batts are the most commonly used and cost-effective exterior wall insulation

## Material Lookup Logic

### Step 1: Materials List Creation
The measure creates a list of materials to lookup based on the insulation being added:

```python
materials = [{
    "quantity": total_added_volume_m3,
    "description": insulation_material_type,
    "catalogIds": ["bc-mf", "gb-mf", "rp-mf"]
}]
```

### Step 2: RSMeans API Call
```python
rsmeans_lookup = search_materials_across_catalogs(
    materials=materials,
    search_term="Fiberglass Batts insulation",
    division_code="07",
    client_id=os.getenv('client_id'),
    client_secret=os.getenv('client_secret')
)
```

### Step 3: Result Processing
Results are extracted from the nested response structure:

```python
# RSMeans returns: {status, summary, results{materials}}
materials_list = rsmeans_lookup.get("results", {}).get("materials", [])

# For each material, extract key data:
for material in materials_list:
    item_id = material.get("itemId")
    description = material.get("description")
    unit_cost = material.get("localizedCosts", {}).get("totalOpCost", 0.0)
```

### Step 4: Cost Calculation
```
Material Cost = unit_cost × total_area_sf
Total Cost = Material Cost × (1 + overhead_profit_percent/100)
```

## Key RSMeans Data Fields

### Material Properties
| Field | Description | Example |
|-------|-------------|---------|
| `itemId` | RSMeans item identifier | 072113100040 |
| `description` | Full material description | Unfaced fiberglass insulation, rigid, for walls, 1" thick, R4.1, 1.5#/CF |
| `localizedCosts.totalOpCost` | Total operating cost (material + labor) | 1.18 $/SF |
| `priceAs` | Unit of measurement | $/SF |

### Response Structure
```json
{
  "status": "success",
  "summary": {
    "jobName": "string",
    "currency": "USD",
    "catalogsSearched": ["bc-mf", "gb-mf", "rp-mf"]
  },
  "results": {
    "materials": [
      {
        "itemId": "072113100040",
        "description": "Unfaced fiberglass insulation...",
        "localizedCosts": {
          "totalOpCost": 1.18
        },
        "priceAs": "$/SF"
      }
    ]
  }
}
```

## Customization Options

### Using a Different Material
Edit the search term in `measure.py` around line 625:

```python
# Current (default):
search_term = "Fiberglass Batts insulation"

# Alternative examples:
# For rigid foam: "Extruded Polystyrene insulation"
# For mineral wool: "Mineral Wool insulation"
# For spray foam: "Spray Polyurethane Foam insulation"
```

### Adding Division Codes
If searching outside Division 07, modify:

```python
division_code = "07"  # Current: Thermal and Moisture Protection

# Common alternatives:
# "06" - Wood, Plastics, and Composites
# "15" - Fire Suppression (if applicable)
```

### Expanding Catalogs
Additional RSMeans catalogs can be searched:

```python
catalog_ids = ["bc-mf", "gb-mf", "rp-mf"]  # Current: 3 catalogs

# Available catalogs (examples):
# "cc-mf" - Commercial Construction
# "fm-mf" - Facilities Management
# "hp-mf" - Highway and Bridge
```

## Cost Data Interpretation

### What Does "totalOpCost" Include?

The RSMeans `totalOpCost` field includes **both material and labor costs**. This is the industry-standard approach for construction cost estimation.

**Breakdown (typical):**
- Material cost: ~60-70%
- Labor cost: ~30-40%

### Example Calculation
```
Material Description: Unfaced fiberglass insulation, rigid, for walls, 1" thick
Unit Cost (totalOpCost): $1.18/SF
Applied Area: 2,886.75 SF

Material Cost = $1.18/SF × 2,886.75 SF = $3,406.37
Overhead/Profit (10%) = $3,406.37 × 0.10 = $340.64
Total Cost = $3,406.37 + $340.64 = $3,747.00
```

## Troubleshooting Search Issues

### No Results Found
1. Check RSMeans API credentials are valid
2. Verify division code exists (07 is most common for insulation)
3. Try broader search term: "insulation" instead of "Fiberglass Batts insulation"
4. Check that catalogs are available in your RSMeans account

### Unexpected Material Matched
1. RSMeans performs keyword matching - results depend on search term precision
2. Review `description` field in results to verify it's appropriate
3. Adjust search term to be more specific (add "wall" or "exterior")
4. Check that the unit cost (`totalOpCost`) is reasonable

### Unit Cost Mismatch
1. Verify the material matched is appropriate for your use case
2. Check `priceAs` field to confirm it's per square foot ($/SF)
3. RSMeans costs include labor - factor this into comparisons with other data sources
4. Regional variation may affect costs - verify your location setting in RSMeans

## API Documentation References

- **RSMeans Search API:** https://api.gordian.com/docs/search-api
- **Measure Implementation:** [measure.py](../measure.py) lines 612-710
- **Shared Helper:** [../resources/call_rsmeans_api.py](../resources/call_rsmeans_api.py)

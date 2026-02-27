# RSMeans Intelligent Search Strategy

## Overview
The `call_rsmeans_api.py` tool now includes intelligent search term generation that automatically tries multiple alternatives when the initial search term doesn't find matches in the RSMeans database.

## Search Strategy

### 1. **Priority Order**
For each material, the system tries search terms in this order:
1. Original material name with provided division code
2. Material-specific alternatives (see categories below)
3. Simplified terms (removing adjectives)
4. Broadest terms without division constraints

### 2. **Multi-Catalog Search**
- Searches multiple RSMeans catalogs in priority order: bc-mf, gb-mf, rp-mf, etc.
- Stops at first successful match to avoid redundant queries
- Returns best match with catalog name, unit cost, and total cost

### 3. **Material-Specific Alternatives**

#### Windows
For "window glazing":
- insulated glass unit
- double glazed window
- glass window
- window glass
- glazing
- IGU

For "window frame":
- window replacement
- window unit
- wood window frame
- vinyl window frame
- aluminum window frame
- window sash
- window
- frame

#### Doors
- door replacement
- door unit
- door assembly
- door

#### Insulation
- wall insulation
- roof insulation
- batt insulation
- rigid insulation
- insulation

#### HVAC
- Automatically converts "system" → "unit"
- Converts "equipment" → "unit"
- Falls back to "HVAC equipment"

### 4. **Simplification Strategy**
For compound terms (e.g., "high efficiency window glazing"):
- Try last word only: "glazing"
- Try first + last: "high glazing"
- Try without division constraint

## Usage

### Basic Usage
```bash
python resources/call_rsmeans_api.py
```
Automatically tries all alternatives for each material.

### Custom Catalogs
```bash
python resources/call_rsmeans_api.py --catalogs bc-mf,gb-mf,sq-mf
```

### With Overhead/Profit
```bash
python resources/call_rsmeans_api.py --overhead-profit-percent 25
```

## Current Status

### Working
- ✅ EC3 API for embodied carbon (12,588 kg CO2 eq)
- ✅ Intelligent search term generation
- ✅ Multi-catalog search across bc-mf, gb-mf, rp-mf, sq-mf, hc-mf, si-mf
- ✅ Auto-path detection from apply_measure.py
- ✅ Material extraction from OSM files

### Known Limitations
- ⚠️ Window-related terms ("glazing", "frame", etc.) return no matches in tested catalogs
- ⚠️ May indicate RSMeans database doesn't include these specific items
- ⚠️ Alternative: Consider using parametric/square-foot costs or custom cost database

## Alternative Solutions

If RSMeans continues to return no matches:

1. **Try Different RSMeans Products**
   - Square Foot Costs (sq-mf catalog)
   - Parametric estimates rather than line items

2. **Custom Cost Database**
   - Create lookup table with industry-average costs
   - Maintain in separate JSON/CSV file

3. **Alternative APIs**
   - Xactimate (insurance restoration costs)
   - BNi Building News
   - ProEst

4. **Contact RSMeans Support**
   - Verify catalog access
   - Get proper terminology for window components
   - Confirm if Division 08 includes window retrofits

## Logging

All search attempts are logged to `tests/output/rsmeans_search_results.json`:
```json
{
  "summary": {
    "materials_searched": 2,
    "materials_matched": 0,
    "catalogs_searched": ["bc-mf", "gb-mf"]
  },
  "results": {
    "errors": ["No RSMeans match found in any catalog for: window glazing"],
    "search_log": [...]
  }
}
```


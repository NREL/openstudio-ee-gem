# RSMeans Intelligent Search Strategy

## Overview
The `call_rsmeans_api.py` tool supports two lookup modes:
1) **Exact line item ID lookup** (if user supplies RSMeans IDs), and
2) **Closest-match search** (default), which tries multiple search terms and catalogs.

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

### 3. **Exact Line Item ID Lookup (Optional)**
If `rsmeans_id` is provided for a material, the lookup attempts the exact line item ID in each catalog first. If found, the match is tagged as `match_type: exact_id_match`. If not found, the system falls back to closest-match search.

### 4. **Material-Specific Alternatives**

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

### 5. **Simplification Strategy**
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

## Match Types
Each matched material includes a `match_type` field:
- `exact_id_match`: Found via user-provided RSMeans line item ID
- `closest_match`: Found via alternative-term search

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
      "materials_matched": 2,
      "catalogs_searched": ["bc-mf", "gb-mf", "rp-mf"]
   },
  "results": {
    "errors": ["No RSMeans match found in any catalog for: window glazing"],
    "search_log": [...]
  }
}
```


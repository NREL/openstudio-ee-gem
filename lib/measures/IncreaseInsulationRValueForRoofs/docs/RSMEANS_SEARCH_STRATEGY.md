# RSMeans Intelligent Search Strategy

## Overview

The roof insulation measure uses the shared `call_rsmeans_api.py` helper to perform RSMeans cost lookups. It supports:
1) Exact line-item lookup (when an RSMeans ID is provided), and
2) Closest-match search (default) across multiple catalogs.

If `use_custom_costs` is enabled, RSMeans lookup is skipped and costs are computed from user inputs.

## Search Strategy

### 1. Priority Order
For each material, the search proceeds in this order:
1. Original material name with a provided division code
2. Material-specific alternatives (insulation-focused)
3. Simplified terms (remove adjectives)
4. Broad search without division constraints

### 2. Multi-Catalog Search
Catalogs are searched in priority order (default: bc-mf, gb-mf, rp-mf). The first successful match is used.

### 3. Insulation Alternatives
If the original term fails, the helper tries:
- roof insulation
- wall insulation
- batt insulation
- rigid insulation
- insulation

### 4. Match Types
Each material is tagged with a match type:
- exact_id_match
- closest_match

## Usage

```bash
python resources/call_rsmeans_api.py
```

### Custom Catalogs

```bash
python resources/call_rsmeans_api.py --catalogs bc-mf,gb-mf,sq-mf
```

### With Overhead/Profit

```bash
python resources/call_rsmeans_api.py --overhead-profit-percent 25
```

## Logging

Search attempts and results can be captured in a JSON output file. The helper reports catalog, division, unit cost, and total cost per material.

# RSMeans Search Strategy (Roofs)

## Overview

The roof measure has a local helper at `resources/call_rsmeans_api.py` so roof costing stays independent from other measures.

Lookup modes:

1. Exact ID mode (`use_exact_costline_id=True`)
2. Closest-match mode (scored candidate selection)
3. Fallback-ID mode (keyword/default fallback when scored match is weak or missing)

## Candidate Scoring

Closest-match mode tokenizes and scores RSMeans candidates from search results.

- Score range is clamped to 0..100.
- Minimum acceptable closest-match score is **50.0**.
- Matches below 50.0 are treated as unresolved and use fallback IDs when configured.

Disallowed entries (for example fasteners, board-foot-only lines, tapered-for-drainage lines) are filtered out before final scoring.

## Catalog and Search Flow

Per material:

1. Try exact costline ID (if specified).
2. Try generated search-term alternatives across catalogs (default `bc-mf,gb-mf,rp-mf`).
3. For each candidate hit, resolve unit cost and compute total cost with area/volume-aware logic.
4. If unresolved or weak-scored, try fallback costline IDs.

## Costing Basis

For insulation, the helper supports volume-based conversion from RSMeans area lines when thickness is available:

- source unit cost may be $/SF
- converted unit cost may become $/CF for volume-based material totals

The measure persists basis metadata so downstream reporting can identify whether pricing came from area, volume, or mixed units.

## Persisted Diagnostics

The measure stores full RSMeans diagnostics JSON in AdditionalProperties:

- `roof_insulation_rsmeans_matches_json`
- `roof_insulation_rsmeans_search_results_json`
- `roof_insulation_rsmeans_summary_json`

These payloads include materials, search attempts, candidate scores, and summary metadata.

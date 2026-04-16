# RSMeans Search Strategy

## Overview

This measure uses `resources/call_rsmeans_api.py` to find insulation cost lines in Gordian RSMeans and compute project cost.

Per material, the lookup is two-step:

1. Search endpoint (`.../costlines/_search`) to find candidate IDs.
2. Costline endpoint (`.../costlines?divisionCode=<id>`) to fetch localized cost values.

The measure extracts `localizedCosts.totalOpCost` as installed unit cost.

## Catalog and Scope

Default lookup settings used by the measure:
- Release: `2024-an`
- Catalogs: `bc-mf`, `gb-mf`, `rp-mf`
- Location: `us-us-national`
- Labor type: `std`
- Measurement system: `imp`

Insulation lookups are typically constrained to Division `07`.

## Candidate Scoring

Candidates are scored by `_score_rsmeans_candidate()` on a `0..100` scale.

Signal examples:
- strong reward for exact/near-exact name matches,
- token overlap reward,
- penalties for context mismatch (for example roof vs wall),
- penalties for overly generic or disallowed entries.

The score is clamped:

```python
return max(0.0, min(100.0, score))
```

## Fallback ID Threshold

If best candidate score is below the threshold, a hardcoded fallback ID is used when available:

```python
MIN_ACCEPTABLE_MATCH_SCORE = 50.0
```

Trigger rule:

```python
best_score < MIN_ACCEPTABLE_MATCH_SCORE
```

Fallback ID mapping is in `INSULATION_FALLBACK_IDS` inside `call_rsmeans_api.py`.

## Disallowed Candidate Filter

`_is_disallowed_candidate()` removes common non-material or misleading line items such as:
- fasteners,
- clips/hangers/anchors,
- board-foot priced entries.

This avoids selecting accessory lines with unusable unit economics.

## Costing Modes

The helper supports two costing modes:

- `area`
  - standard path: `total_cost = unit_cost * quantity`

- `volume_from_area`
  - parses thickness from RSMeans description,
  - converts RSMeans area-rate to a volume-rate,
  - computes cost from added insulation volume.

For this wall-insulation measure, materials are passed with `costing_mode = volume_from_area`, so costs can scale with actual retrofit thickness.

## Exact ID Override

If `use_exact_costline_id` is enabled, the measure attempts the provided `exact_costline_id` first. If found in any catalog, that exact line is used (`match_type = exact_id_match`).

## AdditionalProperties Outputs Tied to RSMeans

The measure writes RSMeans-related outputs to:

- SimulationControl (`results` bucket)
  - `wall_insulation_rsmeans_materials_detail_json`
  - `wall_insulation_cost_source`
  - `wall_insulation_cost_factor_basis`
  - aggregate cost fields

- SizingParameters (`mtrl_prop` bucket)
  - `wall_insulation_rsmeans_extracted_properties_json`

The `wall_insulation_cost_factor_basis` field communicates how cost was calculated:
- `cost_per_area`
- `cost_per_volume`
- `custom_cost_per_volume`
- `mixed`
- `other`
- `not_calculated`

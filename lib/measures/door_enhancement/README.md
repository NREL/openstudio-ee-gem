# Door Enhancement Measure

## Summary
The Door Enhancement measure improves door-related performance in OpenStudio models by:
- reducing infiltration in spaces containing doors,
- optionally replacing doors and adding seals,
- calculating embodied carbon from EC3 EPD data,
- estimating costs through RSMeans or custom cost inputs.

## Cost Modes
- RSMeans mode (`use_custom_costs = False`): derives a door search term from model size/material context, runs multi-catalog lookup (`bc-mf`, `gb-mf`, `rp-mf`), applies 10% overhead/profit, and stores summary + hit details in AdditionalProperties.
- Custom mode (`use_custom_costs = True`): bypasses RSMeans API and uses user-provided cost inputs directly.

## RSMeans Fallback Behavior
When direct RSMeans search has no match, the helper can use door-specific fallback unit cost line IDs for known materials (for example weatherstrips, automatic door bottom, and core steel door variants). The measure logs fallback warnings and fallback counts when this path is used.

## Credentials
- EC3: API token read from `config.ini` (`[EC3_API_TOKEN] API_TOKEN=...`) or environment.
- RSMeans: `client_id` and `client_secret` environment variables (or `.env`).

## Primary Files
- `measure.py` - main measure logic
- `resources/call_rsmeans_api.py` - RSMeans lookup client/helper
- `resources/EC3_lookup.py` - EC3 data retrieval and processing
- `apply_measure.py` - local integration harness

## Additional Docs
- `docs/USAGE_GUIDE.md` - user workflow and examples
- `docs/QUICK_REFERENCE.md` - concise operational reference
- `docs/TECHNICAL.md` - architecture, data flow, and algorithms

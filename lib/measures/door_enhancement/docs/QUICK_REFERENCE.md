# Door Enhancement Measure – Quick Reference

## 30-Second Overview

The Door Enhancement measure improves building doors by:
- ✓ Adding weatherstripping seals (reduces air infiltration)
- ✓ Optionally replacing doors with efficient models
- ✓ Calculating embodied carbon (GWP) via EC3 database
- ✓ Estimating costs via RSMeans API or custom inputs

---

## Running the Measure

### Via OpenStudio GUI (Fastest)
1. Load model → Measures → Add → door_enhancement
2. Set door option: "polystyrene core steel door"
3. Set seals: "automatic door bottom" + "jamb weatherstrip"
4. Enter EC3 API key
5. Click "Run"

### Via Python Script
```bash
cd lib/measures/door_enhancement
python apply_measure.py
```

### Via Parametric Analysis (Sensitivity Analysis)
Use PAT with multiple cost values to compare scenarios.

---

## Essential Arguments

| What | Argument | Example |
|------|----------|---------|
| **Which door?** | `door_option` | polystyrene core steel door |
| **Bottom seal?** | `door_bottom_seal_option` | automatic door bottom |
| **Top/side seal?** | `door_top_side_seal_option` | jamb weatherstrip |
| **Costs from?** | `use_custom_costs` | False (use RSMeans API) |
| **Exact RSMeans ID?** | `rsmeans_unit_costline_id` | 081116100020 |
| **Custom costs?** | `custom_door_cost_per_unit` | 3500 ($/m²) |
| **Carbon data?** | `api_key` | Your EC3 token |
| **Time period?** | `analysis_period` | 30 (years) |

---

## What Gets Modified

- **Infiltration rates**: Reduced by 30% (configurable)
- **Door constructions**: Replaced with selected type
- **Model properties**: EC3 carbon + RSMeans costs added
- **Infiltration objects**: Updated on all door-containing spaces

---

## Outputs

### Terminal Shows
```
RSMeans cost summary (cost_source=rsmeans_api): 
materials=1, total_cost=$3,569.50
```

### Model Contains
- **Facility AdditionalProperties**: EC3 embodied carbon results
- **RSMeans Summary SpaceType**: Total costs + cost_source identifier
- **RSMeans Hit N SpaceTypes**: Per-material details (optional)

---

## Cost Options

### Option A: RSMeans API (Automatic)
```python
use_custom_costs = False
# Measure queries RSMeans, calculates costs automatically
# Needs: client_id, client_secret env vars
```

### Option B: Custom Costs (Manual)
```python
use_custom_costs = True
custom_door_cost_per_unit = 3500.0          # $/m²
custom_bottom_seal_cost = 45.50             # $/m
custom_top_side_seal_cost = 22.75           # $/m
```

**Identify costs with** `cost_source` in output:
- `"rsmeans_api"` → Automatically looked up
- `"custom_input"` → User-provided values

---

## Embodied Carbon Formula

```
Total GWP = (GWP per unit × Quantity) × ⌈Analysis Period ÷ Material Lifetime⌉
```

Example: 12 kg CO₂/m² × 2 m² × 1 replacement = **24 kg CO₂ eq**

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "API token not found" | Set `EC3_API_TOKEN` env var or add to `config.ini` |
| "RSMeans lookup failed" | Use `use_custom_costs = True` instead |
| "No doors found" | Model must contain Door/GlassDoor subsurfaces |
| "Zero cost" | Check RSMeans search term in terminal output |

---

## File Locations

```
measure.py                      Main logic
resources/call_rsmeans_api.py   RSMeans API client
apply_measure.py                Test script
docs/USAGE_GUIDE.md            Full user documentation
docs/TECHNICAL.md              Architecture & algorithms
```

---

## API Requirements

### EC3 (Embodied Carbon)
- **Account**: https://www.buildingtransparency.org/ec3/
- **Env var**: `EC3_API_TOKEN`
- **Cost**: Free (registration required)

### RSMeans (Construction Costs)
- **Account**: Gordian (https://www.gordian.com/)
- **Env vars**: `client_id`, `client_secret`
- **Cost**: Subscription required

---

## Key Properties (Model Output)

```json
{
  "Facility": {
    "ec3_total_gwp_kg_co2eq": 45.23
  },
  "RSMeans Summary": {
    "cost_source": "rsmeans_api",
    "rsmeans_total_cost_with_overhead_profit_$": 3569.50,
    "rsmeans_unit_cost_line_id": "081116100020"
  }
}
```

---

## Door Options & Lifetimes

| Door Type | Default Lifetime |
|-----------|------------------|
| Wooden door | 20 years |
| Garage door | 15 years |
| Glass door | 25 years |
| Steel core doors | 30 years |

---

## Sealing Lengths (Per Unit)

| Seal Type | Length |
|-----------|--------|
| Bottom seal | ~0.9 m (36 in) |
| Top/side seal | ~5.2 m (204 in) |

---

## Version Info

**Current**: 1.1.0 (March 2026)

**Recent Changes**:
- Added custom cost inputs
- Added `cost_source` identifier
- Improved RSMeans search fallbacks

---

## Next Steps

1. **Read**: Full USAGE_GUIDE.md for all arguments
2. **Test**: Run `apply_measure.py` on sample model
3. **Configure**: Set up EC3/RSMeans credentials
4. **Run**: Apply measure to your building model
5. **Analyze**: Review output costs & embodied carbon

---

**Need help?** See USAGE_GUIDE.md → Troubleshooting section

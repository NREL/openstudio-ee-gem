# Custom Cost Inputs Implementation

## Overview
Added support for custom cost inputs to the Door Enhancement measure, allowing users to bypass RSMeans API lookups and provide their own material and labor cost values.

## Implementation Details

### New Arguments Added to `measure.py`

Four new optional arguments have been added to the `arguments()` method:

1. **use_custom_costs** (Boolean, default: False)
   - Display Name: "Use Custom Cost Inputs?"
   - Description: If true, use custom material and labor costs instead of querying the RSMeans API
   - When True: RSMeans API is bypassed; custom cost values are used instead

2. **custom_door_cost_per_unit** (Double, default: 0.0)
   - Display Name: "Custom Door Cost ($/m²)"
   - Units: $/m²
   - Description: Material and labor cost for door replacement per unit area
   - Only used if use_custom_costs = true

3. **custom_bottom_seal_cost** (Double, default: 0.0)
   - Display Name: "Custom Bottom Seal Cost ($/m)"
   - Units: $/m
   - Description: Material and labor cost for bottom seal per unit length
   - Only used if use_custom_costs = true

4. **custom_top_side_seal_cost** (Double, default: 0.0)
   - Display Name: "Custom Top/Side Seal Cost ($/m)"
   - Units: $/m
   - Description: Material and labor cost for top and side seal per unit length
   - Only used if use_custom_costs = true

### Logic Flow in `run()` Method

1. **Argument Retrieval**: Custom cost arguments are retrieved at the start of the `run()` method
2. **Conditional Cost Lookup**:
   - If `use_custom_costs = True`: Creates a mock RSMeans lookup result using the custom cost values
   - If `use_custom_costs = False`: Performs standard RSMeans API lookup as before
3. **Terminal Output**: Appropriate messages inform the user which method is being used
4. **AdditionalProperties Storage**: Both custom and RSMeans costs are stored consistently

### Usage Examples

#### Via OpenStudio GUI
- User sees measure parameters dialog
- Checks "Use Custom Cost Inputs?" box
- Enters custom dollar values for door and seals
- Measure runs with those values

#### Via apply_measure.py Script
```python
set_arg("use_custom_costs", True)
set_arg("custom_door_cost_per_unit", 3500.0)          # $/m²
set_arg("custom_bottom_seal_cost", 45.50)            # $/m
set_arg("custom_top_side_seal_cost", 22.75)          # $/m
```

#### Via Parametric Analysis Tool (PAT)
- User sets `use_custom_costs` to true
- User provides custom cost values
- Can run multiple iterations with different cost scenarios

### Benefits

1. **Flexibility**: Users can input costs from their own data sources (quotes, historical projects, etc.)
2. **Speed**: Avoids RSMeans API latency when costs are already known
3. **Backward Compatibility**: Default behavior unchanged (use_custom_costs = False uses RSMeans)
4. **Consistency**: Same code path for storing and reporting results regardless of cost source

### Files Modified

- `lib/measures/door_enhancement/measure.py`
  - Added 4 new arguments in `arguments()` method
  - Added custom cost retrieval in `run()` method
  - Modified RSMeans cost lookup logic to support custom costs

- `lib/measures/door_enhancement/apply_measure.py`
  - Added commented example showing how to use custom cost arguments

### Testing

Both files have been validated for Python syntax correctness:
- `measure.py` ✓ Compiles successfully
- `apply_measure.py` ✓ Compiles successfully

### Future Enhancements

- Consider adding separate inputs for material vs. labor costs
- Add cost breakdown reporting to AdditionalProperties
- Support for cost escalation factors over time
- Integration with project budget tracking

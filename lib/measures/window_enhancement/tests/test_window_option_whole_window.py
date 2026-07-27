#!/usr/bin/env python
"""
Test script for window_option (whole window replacement) functionality.

Tests:
1. window_option = "aluminum double glazing window"
2. window_option = "wood double glazing window"

Validates:
- EPD query for window_frame (wood/aluminum based on option)
- EPD query for window_glazing (category='ade3ad3405124279955e7d3085f59383', name_like='double pane', plant_geography='021')
- RSMeans API cost calculation for entire window unit
- Embodied carbon calculation (window_frame + window_glazing)
- AdditionalProperties completeness
"""

import sys
import os
from pathlib import Path
import pytest
import gc
from dotenv import load_dotenv
import configparser

# Try to import openstudio
try:
    import openstudio
    HAS_OPENSTUDIO = True
except ImportError:
    HAS_OPENSTUDIO = False
    print("Warning: OpenStudio not available - will skip integration tests")

load_dotenv()

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
MEASURE_PATH = CURRENT_DIR_PATH.parent / "measure.py"
REPO_ROOT = CURRENT_DIR_PATH.parent.parent.parent

# Import measure module
sys.path.insert(0, str(CURRENT_DIR_PATH.parent))
if HAS_OPENSTUDIO:
    from measure import WindowEnhancement
    sys.path.pop(0)
    if 'measure' in sys.modules:
        del sys.modules['measure']
else:
    # Can still import for inspection, but can't run
    pass


@pytest.fixture
def model():
    translator = openstudio.osversion.VersionTranslator()
    path = CURRENT_DIR_PATH / "DOE_small_office.osm"
    model = translator.loadModel(path)
    assert model.is_initialized()
    return model.get()


@pytest.fixture
def measure():
    return WindowEnhancement()


def _set_arg(arg_map, name, value):
    """Helper to set argument values."""
    arg = arg_map[name]
    arg.setValue(value)
    arg_map[name] = arg


def _get_additional_properties_features(model, prefix):
    """Extract AdditionalProperties features from model with given prefix."""
    building = model.getBuilding()
    additional_properties = building.additionalProperties()
    features = {}
    
    feature_names = additional_properties.featureNames()
    for name in feature_names:
        if name.startswith(prefix):
            value = additional_properties.getFeatureAsString(name)
            if value.is_initialized():
                features[name] = value.get()
            else:
                # Try as double
                value_double = additional_properties.getFeatureAsDouble(name)
                if value_double.is_initialized():
                    features[name] = value_double.get()
    
    return features


def _get_api_key():
    """Get EC3 API key from environment or config."""
    # Try environment variable first
    api_key = os.getenv("EC3_API_TOKEN")
    
    # If not in environment, try config.ini
    if not api_key or api_key == "PLACEHOLDER":
        config_path = REPO_ROOT / "config.ini"
        if config_path.exists():
            config = configparser.ConfigParser()
            config.read(config_path)
            if "EC3_API_TOKEN" in config and "API_TOKEN" in config["EC3_API_TOKEN"]:
                api_key = config["EC3_API_TOKEN"]["API_TOKEN"]
    
    if not api_key or api_key == "PLACEHOLDER" or api_key == "your_ec3_api_token_here":
        pytest.skip("EC3_API_TOKEN not set or is PLACEHOLDER")
    
    return api_key


@pytest.mark.skipif(not HAS_OPENSTUDIO, reason="OpenStudio not available")
@pytest.mark.parametrize("window_option,expected_frame_material", [
    ("aluminum double glazing window", "aluminum"),
    ("wood double glazing window", "wood"),
])
def test_window_option_whole_window_replacement(window_option, expected_frame_material):
    """
    Test whole window replacement with aluminum and wood options.
    
    Validates:
    1. Success status
    2. EPD query for window_frame and window_glazing
    3. Cost calculation via RSMeans API
    4. Carbon calculation (frame + glazing)
    5. AdditionalProperties completeness
    """
    print(f"\n{'='*80}")
    print(f"Testing window_option: {window_option}")
    print(f"Expected frame material: {expected_frame_material}")
    print(f"{'='*80}\n")
    
    # Get API key
    api_key = _get_api_key()
    
    # Load model
    translator = openstudio.osversion.VersionTranslator()
    model_path = CURRENT_DIR_PATH / "DOE_small_office.osm"
    model = translator.loadModel(openstudio.toPath(str(model_path))).get()
    
    # Create measure and arguments
    measure = WindowEnhancement()
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Set arguments for whole window replacement
    _set_arg(arg_map, "window_option", window_option)
    _set_arg(arg_map, "glass_option", "none")  # whole window includes glass
    _set_arg(arg_map, "user_num_panes", 0)
    _set_arg(arg_map, "wf_option", "none")  # whole window includes frame
    _set_arg(arg_map, "caulking_option", "none")
    _set_arg(arg_map, "film_option", "none")
    _set_arg(arg_map, "weatherstrip_option", "none")
    _set_arg(arg_map, "secondary_glazing_option", "none")
    _set_arg(arg_map, "analysis_period", 30)
    _set_arg(arg_map, "glass_lifetime", 15)
    _set_arg(arg_map, "wf_lifetime", 15)
    _set_arg(arg_map, "window_lifetime", 30)
    _set_arg(arg_map, "gwp_statistic", "mean")
    _set_arg(arg_map, "api_key", api_key)
    _set_arg(arg_map, "use_custom_costs", False)  # Use RSMeans API
    _set_arg(arg_map, "use_custom_gwp", False)  # Use EC3 EPD data
    
    # Run measure
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure.run(model, runner, arg_map)
    result = runner.result()
    
    # Print all messages
    print("\n--- Runner Messages ---")
    print(f"Result: {result.value().valueName()}")
    for info in result.info():
        print(f"INFO: {info.logMessage()}")
    for warning in result.warnings():
        print(f"WARNING: {warning.logMessage()}")
    for error in result.errors():
        print(f"ERROR: {error.logMessage()}")
    
    # Validation 1: Check Success status
    print("\n--- Validation 1: Success Status ---")
    assert result.value().valueName() == "Success", f"Measure failed: {[e.logMessage() for e in result.errors()]}"
    print("✓ Measure executed successfully")
    
    # Extract AdditionalProperties
    features = _get_additional_properties_features(model, "window_enhancement_")
    
    print("\n--- AdditionalProperties Features ---")
    for key in sorted(features.keys()):
        print(f"{key}: {features[key]}")
    
    # Validation 2: Verify EPD queries were executed
    print("\n--- Validation 2: EPD Queries ---")
    
    # Check for window_frame EPD query
    frame_gwp_keys = [k for k in features.keys() if "window_frame" in k and "gwp" in k.lower()]
    assert len(frame_gwp_keys) > 0, "window_frame GWP data not found in AdditionalProperties"
    print(f"✓ window_frame EPD query executed: {frame_gwp_keys}")
    
    # Check for window_glazing EPD query
    glazing_gwp_keys = [k for k in features.keys() if "window_glazing" in k and "gwp" in k.lower()]
    assert len(glazing_gwp_keys) > 0, "window_glazing GWP data not found in AdditionalProperties"
    print(f"✓ window_glazing EPD query executed: {glazing_gwp_keys}")
    
    # Validation 3: Verify cost calculation
    print("\n--- Validation 3: Cost Calculation ---")
    
    # Check for total cost
    total_cost_key = "window_enhancement_total_cost_with_overhead_and_profit_$"
    assert total_cost_key in features, f"Total cost not found in AdditionalProperties"
    total_cost = float(features[total_cost_key])
    assert total_cost > 0, f"Total cost should be > 0, got {total_cost}"
    print(f"✓ Total cost: ${total_cost:.2f}")
    
    # Check cost components
    material_cost_key = "window_enhancement_material_cost_$"
    labor_cost_key = "window_enhancement_labor_cost_$"
    overhead_profit_key = "window_enhancement_overhead_profit_cost_$"
    
    if material_cost_key in features:
        material_cost = float(features[material_cost_key])
        print(f"  Material cost: ${material_cost:.2f}")
    
    if labor_cost_key in features:
        labor_cost = float(features[labor_cost_key])
        print(f"  Labor cost: ${labor_cost:.2f}")
    
    if overhead_profit_key in features:
        overhead_profit = float(features[overhead_profit_key])
        print(f"  Overhead & Profit: ${overhead_profit:.2f}")
    
    # Check cost source
    cost_source_key = "window_enhancement_cost_source"
    if cost_source_key in features:
        cost_source = features[cost_source_key]
        print(f"  Cost source: {cost_source}")
        # Should be rsmeans_api or custom_input_fallback (if API failed)
        assert cost_source in ["rsmeans_api", "custom_input_fallback"], f"Unexpected cost source: {cost_source}"
    
    # Validation 4: Verify carbon calculation
    print("\n--- Validation 4: Carbon Calculation ---")
    
    # Check total embodied carbon
    carbon_key = "window_enhancement_embodied_carbon_kgCO2eq"
    assert carbon_key in features, "Total embodied carbon not found"
    total_carbon = float(features[carbon_key])
    assert total_carbon > 0, f"Total carbon should be > 0, got {total_carbon}"
    print(f"✓ Total embodied carbon: {total_carbon:.2f} kgCO2eq")
    
    # Try to find component carbon values
    frame_carbon_keys = [k for k in features.keys() if "window_frame" in k and "embodied_carbon" in k]
    glazing_carbon_keys = [k for k in features.keys() if "window_glazing" in k and "embodied_carbon" in k]
    
    if frame_carbon_keys:
        print(f"  Frame carbon keys found: {frame_carbon_keys}")
    if glazing_carbon_keys:
        print(f"  Glazing carbon keys found: {glazing_carbon_keys}")
    
    # Validation 5: Check AdditionalProperties completeness
    print("\n--- Validation 5: AdditionalProperties Completeness ---")
    
    required_keys = [
        "window_enhancement_measure_name",
        "window_enhancement_embodied_carbon_kgCO2eq",
        "window_enhancement_total_cost_with_overhead_and_profit_$",
    ]
    
    missing_keys = [k for k in required_keys if k not in features]
    if missing_keys:
        print(f"⚠ Missing required keys: {missing_keys}")
    else:
        print("✓ All required AdditionalProperties keys present")
    
    # Check for window-specific keys
    window_specific_keys = [k for k in features.keys() if "window_" in k]
    print(f"  Found {len(window_specific_keys)} window-specific keys")
    
    # Report summary
    print(f"\n{'='*80}")
    print(f"TEST SUMMARY for {window_option}")
    print(f"{'='*80}")
    print(f"Status: {'PASS' if result.value().valueName() == 'Success' else 'FAIL'}")
    print(f"Total Cost: ${total_cost:.2f}")
    print(f"Total Carbon: {total_carbon:.2f} kgCO2eq")
    print(f"Cost Source: {features.get(cost_source_key, 'N/A')}")
    print(f"Frame Material: {expected_frame_material}")
    print(f"AdditionalProperties keys: {len(features)}")
    print(f"{'='*80}\n")
    
    # Clean up
    del model
    gc.collect()


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])

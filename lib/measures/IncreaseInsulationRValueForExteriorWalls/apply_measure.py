"""
Apply IncreaseInsulationRValueForExteriorWalls measure to a test model.

This script:
1. Loads a test OSM file from the tests/ folder
2. Runs the ModelMeasure with a set of configurable arguments
3. Saves the modified model to tests/output/
4. Verifies that AdditionalProperties were attached to modified constructions
"""

from pathlib import Path
import sys
import json
import os
import configparser

# ---------------------------------------------------------------------------
# OpenStudio path setup
# ---------------------------------------------------------------------------
OPENSTUDIO_VERSION = "3.11.0"
openstudio_path = f"/Applications/OpenStudio-{OPENSTUDIO_VERSION}/Python"

if Path(openstudio_path).exists():
    sys.path.insert(0, openstudio_path)
    print(f"Using OpenStudio from: {openstudio_path}")
else:
    print(f"Warning: OpenStudio path not found at {openstudio_path}")
    print("Will attempt to use system OpenStudio installation")

import openstudio
from measure import IncreaseInsulationRValueForExteriorWalls

print(f"OpenStudio version: {openstudio.openStudioVersion()}")

# ---------------------------------------------------------------------------
# Read API token from repo-level config.ini
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.absolute()
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config.ini"

API_TOKEN = "PLACEHOLDER"
if CONFIG_PATH.exists():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    try:
        API_TOKEN = config["EC3_API_TOKEN"]["API_TOKEN"]
        print(f"API token loaded from: {CONFIG_PATH}")
    except KeyError:
        print(f"Warning: could not read API_TOKEN from {CONFIG_PATH}")
else:
    print(f"Warning: config.ini not found at {CONFIG_PATH}")


def load_model(model_path):
    """Load an OSM file and return the Model object."""
    translator = openstudio.osversion.VersionTranslator()
    translator.setAllowNewerVersions(True)
    loaded = translator.loadModel(openstudio.toPath(str(model_path)))
    if not loaded.is_initialized():
        raise RuntimeError(f"Failed to load model: {model_path}\n"
                           f"Errors: {translator.errors()}")
    return loaded.get()


def run_measure(model, args_overrides=None):
    """
    Instantiate and run the measure.

    Args:
        model: openstudio.model.Model
        args_overrides: dict of {arg_name: value} to override defaults

    Returns:
        (success: bool, runner: OSRunner)
    """
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForExteriorWalls()

    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

    def set_arg(name, value):
        if name in arg_map:
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
        else:
            print(f"  Warning: argument '{name}' not found in measure arguments")

    # --- Default argument values ---
    set_arg("r_value", 20.0)                          # ft²·h·°F/Btu
    set_arg("analysis_period", 30)                    # years
    set_arg("gwp_statistic", "median")
    set_arg("api_key", API_TOKEN)
    # set_arg("insulation_material_type", "Blown Cellulose")
    # set_arg("insulation_material_type", "Blown Fiberglass")
    # set_arg("insulation_material_type", "Blown Mineral Wool")
    # set_arg("insulation_material_type", "Polyiso Insulation Foam Board")
    # set_arg("insulation_material_type", "Graphite Polystyrene (GPS) Foam Board")
    # set_arg("insulation_material_type", "Expanded Polystyrene (EPS) Foam Board")
    # set_arg("insulation_material_type", "Extruded Polystyrene (XPS) Foam Board")
    # set_arg("insulation_material_type", "Mineral Wool Heavy Density Blanket")
    # set_arg("insulation_material_type", "Mineral Wool Light Density Blanket")
    # set_arg("insulation_material_type", "Fiberglass Batts")
    set_arg("insulation_material_type", "Pure Wool Batts")
    set_arg("insulation_material_lifetime", 30)
    set_arg("insulation_thermal_conductivity", 0.0)   # 0 = use typical
    set_arg("insulation_material_density", 0.0)       # 0 = use typical

    # Apply any caller-supplied overrides
    if args_overrides:
        for name, value in args_overrides.items():
            set_arg(name, value)

    print("\nRunning measure...")
    measure.run(model, runner, arg_map)
    success = runner.result().value().valueName() == "Success"
    return success, runner


def print_runner_output(runner):
    """Print info, warnings, and errors from the runner."""
    result = runner.result()
    print(f"\nResult: {result.value().valueName()}")

    if result.info():
        print("\nInfo:")
        for msg in result.info():
            print(f"  [INFO] {msg.logMessage()}")

    if result.warnings():
        print("\nWarnings:")
        for msg in result.warnings():
            print(f"  [WARN] {msg.logMessage()}")

    if result.errors():
        print("\nErrors:")
        for msg in result.errors():
            print(f"  [ERR ] {msg.logMessage()}")


def verify_additional_properties(model):
    """
    Check the new separate Facility AdditionalProperties (summary block).
    Returns a list of (object_name, prop_name, value) tuples.
    """
    found = []
    facility = model.getFacility()
    ap = facility.additionalProperties()
    for feature_name in ap.featureNames():
        val_opt = ap.getFeatureAsDouble(feature_name)
        if val_opt.is_initialized():
            found.append(("Facility", feature_name, val_opt.get()))
        else:
            val_str = ap.getFeatureAsString(feature_name)
            if val_str.is_initialized():
                found.append(("Facility", feature_name, val_str.get()))
    return found


def main():
    print("=" * 80)
    print("IncreaseInsulationRValueForExteriorWalls – apply_measure.py")
    print("=" * 80)

    # Paths
    model_path = SCRIPT_DIR / "tests" / "DOE_small_office.osm"
    output_dir = SCRIPT_DIR / "tests" / "output"
    output_model_path = output_dir / "DOE_small_office_wall_insulation_upgraded.osm"
    results_json_path = output_dir / "apply_measure_results.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nInput model : {model_path}")
    print(f"Output model: {output_model_path}")

    if not model_path.exists():
        print(f"\nERROR: Model file not found: {model_path}")
        sys.exit(1)

    # Load model
    print("\nLoading model...")
    model = load_model(model_path)
    print("  Model loaded successfully.")

    # Run measure
    print("\n" + "=" * 80)
    print("RUNNING MEASURE")
    print("=" * 80)

    success, runner = run_measure(model)
    print_runner_output(runner)

    def _sv_value(sv):
        """Safely extract a StepValue's value regardless of return type."""
        vtype = sv.variantType().valueName()
        extractors = {
            "Double": sv.valueAsDouble,
            "Integer": sv.valueAsInteger,
            "Boolean": sv.valueAsBoolean,
            "String": sv.valueAsString,
        }
        fn = extractors.get(vtype)
        if fn is None:
            return None
        val = fn()
        # OpenStudio may return an Optional wrapper or a native Python type
        if hasattr(val, "is_initialized"):
            return val.get() if val.is_initialized() else None
        return val

    # Collect step values
    step_values = {}
    for sv in runner.result().stepValues():
        try:
            step_values[sv.name()] = _sv_value(sv)
        except Exception as exc:
            step_values[sv.name()] = f"<error: {exc}>"

    # Redact sensitive API key from output
    if "api_key" in step_values:
        step_values["api_key"] = "<redacted>"

    if step_values:
        print("\nStep Values reported by measure:")
        for k, v in step_values.items():
            print(f"  {k}: {v}")

    # Verify AdditionalProperties
    print("\n" + "=" * 80)
    print("VERIFYING SEPARATE FACILITY ADDITIONAL PROPERTIES")
    print("=" * 80)

    ap_data = verify_additional_properties(model)
    if ap_data:
        print(f"Found {len(ap_data)} properties in separate Facility AdditionalProperties:")
        
        # Track material and overhead costs to calculate total
        material_cost = None
        overhead_cost = None
        
        for obj_name, prop_name, value in ap_data:
            print(f"  [{obj_name}] {prop_name}: {value}")
            
            # Capture cost values for total calculation
            if prop_name == "wall_insulation_total_additional_material_cost_$":
                try:
                    material_cost = float(value)
                except (ValueError, TypeError):
                    pass
            elif prop_name == "wall_insulation_total_additional_overhead_profit_cost_$":
                try:
                    overhead_cost = float(value)
                except (ValueError, TypeError):
                    pass
        
        # Print total cost if both values are available
        if material_cost is not None and overhead_cost is not None:
            total_cost = material_cost + overhead_cost
            print(f"  [Facility] wall_insulation_total_cost_with_overhead_and_profit_$: {total_cost:.2f}")
    else:
        print("  No properties found on Facility.")

    # Save modified model
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)

    model.save(openstudio.toPath(str(output_model_path)), True)
    print(f"  Modified model saved to: {output_model_path}")

    # Save JSON summary
    results = {
        "measure": "IncreaseInsulationRValueForExteriorWalls",
        "success": success,
        "step_values": step_values,
        "additional_properties_count": len(ap_data),
        "additional_properties_sample": [
            {"construction": c, "property": p, "value": v}
            for c, p, v in ap_data[:10]
        ]
    }
    with open(results_json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results JSON saved to: {results_json_path}")

    print("\n" + "=" * 80)
    if success:
        print("SUCCESS: Measure applied successfully!")
    else:
        print("FAILURE: Measure did not complete successfully.")
    print("=" * 80 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

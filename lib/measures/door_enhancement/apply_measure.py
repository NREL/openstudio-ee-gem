"""
Apply DoorEnhancement measure to a test model.

This script:
1. Loads a test OSM file from the tests/ folder
2. Runs the ModelMeasure with a set of configurable arguments
3. Saves the modified model to tests/output/
4. Verifies that AdditionalProperties were attached to modified door subsurfaces
"""

from pathlib import Path
import sys
import json
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
from measure import DoorEnhancement

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
    Instantiate and run the DoorEnhancement measure.

    The space_type argument is a choice argument that references OpenStudio
    model object handles. We default to '*Entire Building*' by identifying
    the building handle from the loaded model.

    Args:
        model: openstudio.model.Model
        args_overrides: dict of {arg_name: value} to override defaults

    Returns:
        (success: bool, runner: OSRunner)
    """
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = DoorEnhancement()

    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

    def set_arg(name, value):
        if name in arg_map:
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
        else:
            print(f"  Warning: argument '{name}' not found in measure arguments")

    # space_type: use the building handle to select *Entire Building*
    building = model.getBuilding()
    set_arg("space_type", str(building.handle()))

    # --- Core arguments ---
    set_arg("space_infiltration_reduction_percent", 30.0)
    set_arg("alter_coef", False)
    set_arg("door_area_per_unit", 1.95)         # m²  (declared unit per PCR)
    set_arg("analysis_period", 30)              # years

    # --- Sealing options ---
    set_arg("door_bottom_seal_option", "automatic door bottom")
    # set_arg("door_bottom_seal_option", "none")
    # set_arg("door_bottom_seal_option", "brush weatherstrip")
    # set_arg("door_bottom_seal_option", "silicone adhesive smoke gasket")
    set_arg("door_top_side_seal_option", "jamb weatherstrip")
    # set_arg("door_top_side_seal_option", "none")
    # set_arg("door_top_side_seal_option", "silicone adhesive smoke gasket")
    set_arg("strip_lifetime", 15)               # years

    # --- Door replacement option ---
    set_arg("door_option", "polystyrene core steel door")  # replace door with a realistic option
    # set_arg("door_option", "none")
    # set_arg("door_option", "wooden door")
    # set_arg("door_option", "garage door")
    # set_arg("door_option", "glass door")
    # set_arg("door_option", "polyurethane core steel door")
    # set_arg("door_option", "honeycomb core steel door")
    # set_arg("door_option", "stiffened core steel door")
    set_arg("door_lifetime", 30)                # years (default for steel doors)
    set_arg("door_thermal_conductivity", 0.0)   # 0 = use typical
    set_arg("door_density", 0.0)                # 0 = use typical
    set_arg("door_thickness", 0.0)              # 0 = use typical

    # --- Sealing strip lengths ---
    set_arg("length_per_unit_bottom_side", 0.9144)  # m  (~36 in)
    set_arg("length_per_unit_other_sides", 5.1816)  # m  (~204 in)

    # --- EC3 / GWP ---
    set_arg("gwp_statistic", "median")
    set_arg("api_key", API_TOKEN)

    # --- Custom costs (optional; set use_custom_costs=True to enable) ---
    set_arg("use_custom_costs", False)                     # False = use RSMeans API; True = use custom costs below
    set_arg("rsmeans_unit_costline_id", "")               # optional exact RSMeans line ID override
    set_arg("custom_door_cost_per_unit", 3500.0)          # $/m² (e.g., material + labor for door)
    set_arg("custom_bottom_seal_cost", 45.50)             # $/m  (e.g., material + labor for bottom seal)
    set_arg("custom_top_side_seal_cost", 22.75)           # $/m  (e.g., material + labor for top/side seal)

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
    Check Facility AdditionalProperties and RSMeans-specific objects.
    Returns a list of (object_name, prop_name, value) tuples.
    """
    found = []

    def _collect_props(label, ap):
        for feature_name in ap.featureNames():
            val_opt = ap.getFeatureAsDouble(feature_name)
            if val_opt.is_initialized():
                found.append((label, feature_name, val_opt.get()))
            else:
                val_str = ap.getFeatureAsString(feature_name)
                if val_str.is_initialized():
                    found.append((label, feature_name, val_str.get()))

    facility = model.getFacility()
    _collect_props("Facility", facility.additionalProperties())

    # Include RSMeans Summary object (stored as a SpaceType)
    for st in model.getSpaceTypes():
        name = st.nameString()
        if name == "RSMeans Summary":
            _collect_props(name, st.additionalProperties())

    return found


def main():
    print("=" * 80)
    print("DoorEnhancement – apply_measure.py")
    print("=" * 80)

    # Paths
    model_path = SCRIPT_DIR / "tests" / "EnvelopeAndLoadTestModel_01.osm"
    output_dir = SCRIPT_DIR / "tests" / "output"
    output_model_path = output_dir / "EnvelopeAndLoadTestModel_01_door_enhanced.osm"
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

    # Count doors in model
    doors = [ss for ss in model.getSubSurfaces()
             if ss.subSurfaceType() in ("Door", "GlassDoor", "OverheadDoor")]
    print(f"  Doors found in model: {len(doors)}")
    for d in doors:
        print(f"    - {d.nameString()} ({d.subSurfaceType()})")

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
            name = sv.name()
            if name.lower() == "api_key":
                step_values[name] = "<redacted>"
            else:
                step_values[name] = _sv_value(sv)
        except Exception as exc:
            step_values[sv.name()] = f"<error: {exc}>"

    if step_values:
        print("\nStep Values reported by measure:")
        for k, v in step_values.items():
            print(f"  {k}: {v}")

    # Verify AdditionalProperties on Building
    print("\n" + "=" * 80)
    print("VERIFYING FACILITY + RSMEANS ADDITIONAL PROPERTIES")
    print("=" * 80)

    ap_data = verify_additional_properties(model)
    if ap_data:
        print(f"Found {len(ap_data)} properties in separate Facility AdditionalProperties:")
        for obj_name, prop_name, value in ap_data:
            print(f"  [{obj_name}] {prop_name}: {value}")
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
        "measure": "DoorEnhancement",
        "success": success,
        "step_values": step_values,
        "doors_in_model": len(doors),
        "additional_properties_count": len(ap_data),
        "additional_properties_sample": [
            {"subsurface": s, "property": p, "value": v}
            for s, p, v in ap_data[:10]
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

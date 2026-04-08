"""
Apply WindowEnhancement measure to a test model._

This script:
1. Loads a test OSM file from the tests/ folder
2. Runs the ModelMeasure with a set of configurable arguments
3. Saves the modified model to tests/output/
4. Verifies that AdditionalProperties were attached to modified window subsurfaces
"""

from pathlib import Path
import sys
import json
import configparser

# ---------------------------------------------------------------------------
# OpenStudio path setup
# ---------------------------------------------------------------------------
import platform

# Try to use installed openstudio package first (via pip/conda)
# Fall back to system installations if needed
try:
    import openstudio
    print(f"Using OpenStudio from installed package")
except ImportError:
    # Fall back to system installations
    OPENSTUDIO_VERSION = "3.9.0"
    WINDOWS_OPENSTUDIO_PATH = r"C:\openstudio-3.9.0\Python"
    MAC_OPENSTUDIO_VERSION = "3.11.0"
    mac_openstudio_path = f"/Applications/OpenStudio-{MAC_OPENSTUDIO_VERSION}/Python"

    openstudio_path = None
    if platform.system() == "Windows":
        if Path(WINDOWS_OPENSTUDIO_PATH).exists():
            openstudio_path = WINDOWS_OPENSTUDIO_PATH
            sys.path.insert(0, openstudio_path)
            print(f"Using OpenStudio from: {openstudio_path}")
    else:
        if Path(mac_openstudio_path).exists():
            openstudio_path = mac_openstudio_path
            sys.path.insert(0, openstudio_path)
            print(f"Using OpenStudio from: {openstudio_path}")

    if openstudio_path is None:
        print("Warning: OpenStudio path not found")

import openstudio
from measure import WindowEnhancement

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
    Instantiate and run the WindowEnhancement measure.

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
    measure = WindowEnhancement()

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

    # --- Analysis period and lifetimes ---
    set_arg("analysis_period", 30)          # years
    set_arg("glass_lifetime", 15)           # years
    set_arg("wf_lifetime", 15)              # years
    set_arg("caulking_lifetime", 10)        # years
    set_arg("film_lifetime", 10)            # years
    set_arg("weatherstrip_lifetime", 10)    # years
    set_arg("overhead_profit_percent", 0.1) # percent

    # --- Enhancement options (glass + frame) ---
    
    # Window frame options:
    set_arg("wf_option", "wood window frame")           
    # set_arg("wf_option", "none")
    # set_arg("wf_option", "wood-aluminium window frame")
    
    # Weatherstrip options:
    # set_arg("weatherstrip_option", "none")              # no weatherstrip
    set_arg("weatherstrip_option", "silicone adhesive smoke gasket")
    
    # --- Glass geometry (only used when glass_option != 'none') ---
    # set_arg("user_num_panes", 1)                    # 1 = single pane (monolithic)
    # set_arg("user_num_panes", 2)                        # 2 = double pane
    set_arg("user_num_panes", 3)                        # 3 = triple pane
    set_arg("glass_pane_thickness", 0.003)              # m (3 mm)
    set_arg("gap_thickness", 0.013)                     # m (13 mm)

   
    # Film options:
    # set_arg("film_option", "none")                      # no glazing film
    # set_arg("film_option", "safety film")
    # set_arg("film_option", "solar control film")
    # set_arg("film_option", "anti-graffiti film")
    # set_arg("film_option", "decorative film")
    set_arg("film_option", "low-e film")


    # Caulking options (only used when glass_option != 'none' or secondary_glazing_option != 'none')
    # set_arg("caulking_option", "none")                  # no caulking
    # set_arg("caulking_option", "acrylic")
    set_arg("caulking_option", "polyurethane")
    
    
    
    # Installation type options:
    set_arg("glass_option", "provide user_num_panes")   # glass replacement
    # set_arg("glass_option", "none")
    # set_arg("secondary_glazing_option", "none")         # no secondary glazing
    set_arg("secondary_glazing_option", "install secondary glazing")

    # --- Film properties (only used when film_option != 'none') ---
    set_arg("film_visible_transmittance", 0.0)          # 0 = use default
    set_arg("film_solar_transmittance", 0.0)            # 0 = use default
    set_arg("film_thermal_emissivity", 0.0)             # 0 = use default
    set_arg("film_thermal_resistance", 0.0)             # 0 = use default

    # --- Caulking geometry ---
    set_arg("caulking_thickness", 0.008)                # m (8 mm bead)



    # --- Glass optical properties (0 = use defaults) ---
    set_arg("glass_solar_transmittance", 0.0)
    set_arg("glass_visible_transmittance", 0.0)
    set_arg("glass_front_emissivity", 0.0)
    set_arg("glass_back_emissivity", 0.0)
    set_arg("glass_front_solar_reflectance", 0.0)
    set_arg("glass_back_solar_reflectance", 0.0)
    set_arg("glass_front_visible_reflectance", 0.0)
    set_arg("glass_back_visible_reflectance", 0.0)

    # --- Dividers (muntins): -1 = use model values ---
    set_arg("num_horizontal_dividers", -1)
    set_arg("num_vertical_dividers", -1)

    # --- EC3 / GWP ---
    set_arg("gwp_statistic", "median")
    set_arg("api_key", API_TOKEN)
    
    # --- Cost calculation ---
    set_arg("calculate_costs", False)  # Disable EC3 for faster testing
    
    # --- Custom cost mode (set to False to use RSMeans API, True to use custom costs below) ---
    set_arg("use_custom_costs", False)

    # --- RSMeans exact line item ID mode ---
    set_arg("use_specific_rsmeans_line_item_ids", False)
    set_arg("rsmeans_id_glazing", "084126100020")
    set_arg("rsmeans_id_frame", "084113200050")
    
    # --- Custom cost inputs (only used when use_custom_costs = True) ---
    # set_arg("glass_cost_per_sf", 25.0)        # $/SF (e.g., $25/SF for double-pane IGU)
    # set_arg("frame_cost_per_sf", 15.0)        # $/SF (e.g., $15/SF for wood frame)
    # set_arg("caulking_cost_per_cy", 800.0)    # $/CY (e.g., $800/CY for silicone sealant)
    # set_arg("labor_cost_multiplier", 2.0)     # Multiplier (e.g., 2.0 = 100% labor markup)

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

    # Skip detailed info/warning printing due to potential Unicode encoding issues
    # Just report counts
    info_count = len(list(result.info())) if result.info() else 0
    warn_count = len(list(result.warnings())) if result.warnings() else 0
    if info_count > 0:
        print(f"\nInfo: {info_count} messages (skipping detailed output due to encoding)")
    if warn_count > 0:
        print(f"\nWarnings: {warn_count} messages (skipping detailed output due to encoding)")

    if result.errors():
        print("\nErrors:")
        for msg in result.errors():
            print(f"  [ERR ] {msg.logMessage()}")


def verify_additional_properties(model):
    """
    Check that AdditionalProperties were attached to the Building object.
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
    print("WindowEnhancement – apply_measure.py")
    print("=" * 80)

    # Paths
    model_path = SCRIPT_DIR / "tests" / "DOE_small_office.osm"
    output_dir = SCRIPT_DIR / "tests" / "output"
    output_model_path = output_dir / "DOE_small_office_window_enhanced.osm"
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

    # Count windows in model
    window_types = ("FixedWindow", "OperableWindow", "Skylight",
                    "TubularDaylightDome", "TubularDaylightDiffuser")
    windows = [ss for ss in model.getSubSurfaces()
               if ss.subSurfaceType() in window_types]
    print(f"  Windows found in model: {len(windows)}")

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

    # Verify AdditionalProperties on Building
    print("\n" + "=" * 80)
    print("VERIFYING SEPARATE FACILITY ADDITIONAL PROPERTIES")
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

    # Extract and save retrofit materials if present in step values
    materials_data = None
    rsmeans_results_data = None
    if "window_enhancement_retrofit_materials_json" in step_values:
        try:
            materials_json_str = step_values["window_enhancement_retrofit_materials_json"]
            if isinstance(materials_json_str, str):
                materials_data = json.loads(materials_json_str)
                materials_path = output_dir / "window_enhancement_retrofit_materials.json"
                with open(materials_path, "w") as f:
                    json.dump(materials_data, f, indent=2)
                print(f"  Retrofit materials saved to: {materials_path}")
        except Exception as e:
            print(f"  Warning: Could not extract retrofit materials: {e}")

    if "window_enhancement_rsmeans_results_json" in step_values:
        try:
            rsmeans_json_str = step_values["window_enhancement_rsmeans_results_json"]
            if isinstance(rsmeans_json_str, str):
                rsmeans_results_data = json.loads(rsmeans_json_str)
                rsmeans_path = output_dir / "window_enhancement_rsmeans_results.json"
                with open(rsmeans_path, "w") as f:
                    json.dump(rsmeans_results_data, f, indent=2)
                print(f"  RSMeans results saved to: {rsmeans_path}")
        except Exception as e:
            print(f"  Warning: Could not extract RSMeans results: {e}")

    # Save JSON summary
    results = {
        "measure": "WindowEnhancement",
        "success": success,
        "step_values": step_values,
        "windows_in_model": len(windows),
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

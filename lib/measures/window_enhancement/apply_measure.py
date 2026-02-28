"""
Apply WindowEnhancement measure to a test model.

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
import os
import shutil
import subprocess

# ---------------------------------------------------------------------------
# OpenStudio path setup
# ---------------------------------------------------------------------------
OPENSTUDIO_VERSION = "3.11.0"


def detect_openstudio_python_path():
    env_path = os.environ.get("OPENSTUDIO_PYTHON_PATH")
    candidates = [
        env_path,
        f"C:/Program Files/openstudio-{OPENSTUDIO_VERSION}/Python",
        f"C:/Program Files/OpenStudio-{OPENSTUDIO_VERSION}/Python",
        f"/Applications/OpenStudio-{OPENSTUDIO_VERSION}/Python",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def detect_python312_command():
    """Return a command list to launch Python 3.12, or None if not found."""
    env_python = os.environ.get("PYTHON312_EXE")
    if env_python and Path(env_python).exists():
        return [env_python]

    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3.12"]

    py312 = shutil.which("python3.12")
    if py312:
        return [py312]

    common_candidates = [
        Path.home() / "AppData/Local/Programs/Python/Python312/python.exe",
        Path("C:/Python312/python.exe"),
    ]
    for candidate in common_candidates:
        if candidate.exists():
            return [str(candidate)]

    return None


def ensure_python_compatibility(openstudio_python_path):
    """
    OpenStudio 3.11 Python bindings on Windows are compiled for Python 3.12.
    If a different Python is running, attempt to relaunch this script with 3.12.
    """
    if not openstudio_python_path:
        return

    requires_python_312 = "openstudio-3.11" in openstudio_python_path.lower()
    if not requires_python_312:
        return

    if sys.version_info[:2] == (3, 12):
        return

    relaunch_guard = os.environ.get("WINDOW_ENHANCEMENT_PY312_RELAUNCH") == "1"
    version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if relaunch_guard:
        raise RuntimeError(
            "OpenStudio 3.11 requires Python 3.12, but script is still running under "
            f"Python {version_str}."
        )

    cmd_prefix = detect_python312_command()
    if not cmd_prefix:
        raise RuntimeError(
            "OpenStudio 3.11 Python bindings require Python 3.12. "
            f"Current interpreter is Python {version_str} at {sys.executable}. "
            "Install Python 3.12 and rerun, or set PYTHON312_EXE to your Python 3.12 executable."
        )

    print(
        "Detected incompatible Python version for OpenStudio 3.11 bindings "
        f"(current: {version_str}). Relaunching with Python 3.12..."
    )

    env = os.environ.copy()
    env["WINDOW_ENHANCEMENT_PY312_RELAUNCH"] = "1"
    script_path = Path(__file__).resolve()
    completed = subprocess.run([*cmd_prefix, str(script_path), *sys.argv[1:]], env=env)
    sys.exit(completed.returncode)


openstudio_path = detect_openstudio_python_path()
ensure_python_compatibility(openstudio_path)
if openstudio_path:
    if openstudio_path not in sys.path:
        sys.path.insert(0, openstudio_path)
    print(f"Using OpenStudio Python bindings from: {openstudio_path}")
else:
    print("Warning: OpenStudio Python path not found for 3.11.0")
    print("Will attempt to use system OpenStudio installation")

try:
    import openstudio
except ImportError as exc:
    msg = str(exc)
    if "python312.dll" in msg:
        raise RuntimeError(
            "OpenStudio 3.11 Python bindings require Python 3.12 on this machine. "
            "Please run this script with Python 3.12 and set OPENSTUDIO_PYTHON_PATH "
            "to the OpenStudio 3.11 Python folder if needed."
        ) from exc
    raise

from measure import WindowEnhancement

print(f"OpenStudio version: {openstudio.openStudioVersion()}")
if not openstudio.openStudioVersion().startswith("3.11"):
    raise RuntimeError(
        "Loaded OpenStudio version is not 3.11.x, which is required for model_to_run.osm. "
        "Set OPENSTUDIO_PYTHON_PATH to OpenStudio 3.11 Python bindings and use Python 3.12."
    )

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
    set_arg("space_infiltration_reduction_percent", 50.0)

    # --- Analysis period and lifetimes ---
    set_arg("analysis_period", 30)          # years
    set_arg("glass_lifetime", 15)           # years
    set_arg("wf_lifetime", 15)              # years
    set_arg("caulking_lifetime", 10)        # years
    set_arg("film_lifetime", 10)            # years
    set_arg("weatherstrip_lifetime", 10)    # years

    # --- Enhancement options aligned with workflow Scenario 1 (window-only) ---
    set_arg("wf_option", "none")                        # window frame option
    set_arg("caulking_option", "none")               # apply acrylic caulking
    set_arg("film_option", "none")                      # no glazing film
    set_arg("weatherstrip_option", "none")              # no weatherstrip
    set_arg("glass_option", "provide user_num_panes")   # match workflow window scenario
    set_arg("secondary_glazing_option", "none")         # no secondary glazing

    # --- Film properties (only used when film_option != 'none') ---
    set_arg("film_visible_transmittance", 0.0)          # 0 = use default
    set_arg("film_solar_transmittance", 0.0)            # 0 = use default
    set_arg("film_thermal_emissivity", 0.0)             # 0 = use default
    set_arg("film_thermal_resistance", 0.0)             # 0 = use default

    # --- Caulking geometry ---
    set_arg("caulking_thickness", 0.003)                # m (8 mm bead)

    # --- Glass geometry (only used when glass_option != 'none') ---
    set_arg("user_num_panes", 3)                        # U=0.20 -> 3 panes in workflow
    set_arg("glass_pane_thickness", 0.003)              # m (3 mm)
    set_arg("gap_thickness", 0.013)                     # m (13 mm)
    set_arg("length_per_unit", 5.1816)

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
    model_path = SCRIPT_DIR / "tests" / "in.osm"
    output_dir = SCRIPT_DIR / "tests" / "output"
    output_model_path = output_dir / "in_window_enhanced.osm"
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

# Standard library
import json
import os
import subprocess
import time
from itertools import product
import sys
from pathlib import Path
import configparser
import shutil
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import csv

# Add OpenStudio 3.11.0 Python bindings to path BEFORE importing
def detect_openstudio_python_path():
    env_path = os.environ.get("OPENSTUDIO_PYTHON_PATH")
    candidates = [
        env_path,
        "C:/Program Files/openstudio-3.11.0/Python",
        "/Applications/OpenStudio-3.11.0/Python",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None

OPENSTUDIO_PYTHON_PATH = detect_openstudio_python_path()
if OPENSTUDIO_PYTHON_PATH and OPENSTUDIO_PYTHON_PATH not in sys.path:
    sys.path.insert(0, OPENSTUDIO_PYTHON_PATH)
elif not OPENSTUDIO_PYTHON_PATH:
    print("Warning: OpenStudio Python path not found; trying system package.")
import openstudio

# Read EC3 API Token from config.ini
def get_ec3_api_token():
    """Read EC3 API token from config.ini file."""
    script_dir = Path.cwd()
    repo_root = script_dir.parent.parent
    config_path = repo_root / "config.ini"
    
    if not config_path.exists():
        print(f"Warning: config.ini not found at {config_path}")
        return None
    
    config = configparser.ConfigParser()
    config.read(config_path)
    
    try:
        return config["EC3_API_TOKEN"]["API_TOKEN"]
    except KeyError:
        print("Warning: EC3_API_TOKEN not found in config.ini")
        return None

EC3_API_TOKEN = get_ec3_api_token()


# =========================
# HELPER FUNCTIONS
# =========================

def get_city_weather_files(city_name, base_weather_path):
    """Get the EPW and DDY file paths for a given city name."""
    city_folder_path = os.path.join(base_weather_path, city_name)
    if not os.path.exists(city_folder_path):
        print(f"Error: Folder '{city_folder_path}' does not exist")
        return None

    epw_file = None
    ddy_file = None
    for filename in os.listdir(city_folder_path):
        if filename.lower().endswith(".epw"):
            epw_file = os.path.join(city_folder_path, filename)
        elif filename.lower().endswith(".ddy"):
            ddy_file = os.path.join(city_folder_path, filename)

    return {"epw": epw_file, "ddy": ddy_file}


def generate_scenario_name(scenario_dict):
    """Generate a unique scenario name from scenario parameters."""
    parts = []
    
    if scenario_dict.get("is_baseline", False):
        parts.append("baseline")
    else:
        scenario_index = scenario_dict.get("scenario_index")
        if scenario_index is not None:
            parts.append(f"scenario_{int(scenario_index)}")

        has_window_request = any([
            scenario_dict.get("window_u_factor") not in [None, ""],
            scenario_dict.get("window_num_panes") not in [None, ""],
            str(scenario_dict.get("glass_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("wf_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("film_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])

        measure_count = sum([
            1 if scenario_dict.get("wall_r_value") else 0,
            1 if scenario_dict.get("roof_r_value") else 0,
            1 if has_window_request else 0,
            1 if scenario_dict.get("door_option") else 0,
        ])
        
        if measure_count > 1:
            parts.append("all")
        
        if scenario_dict.get("wall_r_value"):
            parts.append(f"wall_r{scenario_dict['wall_r_value']}")
        if scenario_dict.get("roof_r_value"):
            parts.append(f"roof_r{scenario_dict['roof_r_value']}")
        if scenario_dict.get("window_u_factor"):
            parts.append(f"window_u{scenario_dict['window_u_factor']}")
        elif scenario_dict.get("window_num_panes"):
            parts.append(f"window_num_panes{scenario_dict['window_num_panes']}")
        if scenario_dict.get("door_option"):
            door_abbrev = scenario_dict['door_option'].replace(' ', '_').replace('door', 'd')
            parts.append(f"door_{door_abbrev}")
    
    parts.append(scenario_dict["building_type"])
    parts.append(scenario_dict["city"])
    
    return "_".join(parts)


def run_osw(osw_dict, osw_filename, run_dir, openstudio_path, label):
    """Write an OSW and run it with the OpenStudio CLI. Returns True on success."""
    osw_path = os.path.join(run_dir, osw_filename)
    os.makedirs(run_dir, exist_ok=True)
    with open(osw_path, "w") as f:
        json.dump(osw_dict, f, indent=2)

    try:
        result = subprocess.run(
            [openstudio_path, "run", "-w", osw_filename],
            check=False,
            capture_output=True,
            text=True,
            cwd=run_dir,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        print(f"❌ {label}: timed out after 600s")
        return False
    except Exception as e:
        print(f"❌ {label}: subprocess error: {e}")
        return False

    out_osw_path = os.path.join(run_dir, "out.osw")
    if not os.path.exists(out_osw_path):
        print(f"❌ {label}: out.osw not found (OpenStudio may have crashed)")
        if result.stderr:
            print(f"   STDERR: {result.stderr[:500]}")
        return False

    with open(out_osw_path, "r") as f:
        out_osw = json.load(f)

    if out_osw.get("completed_status") != "Success":
        print(f"❌ {label}: OSW failed")
        run_log_path = os.path.join(run_dir, "run", "run.log")
        if os.path.exists(run_log_path):
            with open(run_log_path, "r") as log_f:
                for line in log_f:
                    if "ERROR" in line:
                        print(f"   LOG: {line.rstrip()}")
        return False

    return True


def apply_python_measure(model, measure_folder, measure_class_name, arguments_dict):
    """
    Apply a Python OpenStudio ModelMeasure directly to a model in-process.
    Returns True if successful, False otherwise.
    """
    measure_folder_str = str(measure_folder)
    try:
        if measure_folder_str not in sys.path:
            sys.path.insert(0, measure_folder_str)

        import measure as measure_module
        import importlib
        importlib.reload(measure_module)

        measure_class = getattr(measure_module, measure_class_name)

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        measure = measure_class()

        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

        for arg_name, arg_value in arguments_dict.items():
            if arg_name in arg_map:
                arg = arg_map[arg_name]
                arg.setValue(arg_value)
                arg_map[arg_name] = arg

        measure.run(model, runner, arg_map)

        result_value = runner.result().value().valueName()
        if result_value != "Success":
            print(f"  Measure result: {result_value}")
            for error in runner.result().errors():
                print(f"    ERROR: {error.logMessage()}")
            return False

        return True

    except Exception as e:
        print(f"  ERROR applying measure: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if measure_folder_str in sys.path:
            sys.path.remove(measure_folder_str)


def apply_reporting_measure(model_path, sql_file_path, measure_dir_path, label):
    """
    Apply the OperatingCostCarbonReportingMeasure (Python ReportingMeasure)
    in-process after simulation completes. The OSW runner can't execute Python
    measures, so we call it directly using the OpenStudio Python bindings.

    Returns True if successful, False otherwise.
    """
    measure_folder = os.path.join(measure_dir_path, "OperatingCostCarbonReportingMeasure")
    measure_folder_str = str(measure_folder)
    try:
        # Load model
        translator = openstudio.osversion.VersionTranslator()
        loaded = translator.loadModel(openstudio.toPath(str(model_path)))
        if not loaded.is_initialized():
            print(f"  ⚠️  {label}: could not load model for reporting measure")
            return False
        model = loaded.get()

        # Attach SQL file to model
        sql_file = openstudio.SqlFile(openstudio.toPath(str(sql_file_path)))
        model.setSqlFile(sql_file)

        # Set up runner with SQL file and model
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        runner.setLastEnergyPlusSqlFilePath(openstudio.toPath(str(sql_file_path)))
        runner.setLastOpenStudioModel(model)

        # Import and instantiate the measure
        if measure_folder_str not in sys.path:
            sys.path.insert(0, measure_folder_str)
        import measure as measure_module
        import importlib
        importlib.reload(measure_module)
        measure = measure_module.OperatingCostCarbonReport()

        # Arguments (none required for this measure — reads from CSV resources)
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

        # Run
        measure.run(runner, arg_map)

        result_value = runner.result().value().valueName()
        if result_value != "Success":
            print(f"  ⚠️  {label}: reporting measure result: {result_value}")
            for error in runner.result().errors():
                print(f"    ERROR: {error.logMessage()}")
            return False

        # Save model with AdditionalProperties written by the reporting measure
        model.save(openstudio.toPath(str(model_path)), True)
        del model

        return True

    except Exception as e:
        print(f"  ⚠️  {label}: reporting measure error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if measure_folder_str in sys.path:
            sys.path.remove(measure_folder_str)


# =========================
# CORE: SINGLE SCENARIO CREATION/RUN
# =========================

def create_simulation(
    city,
    base_run_dir,
    measure_dir_path,
    base_weather_path,
    scenario_dict,
    overwrite_existing=False,
    building_type="SmallOffice",
    template="90.1-2013",
    climate_zone="ASHRAE 169-2013-5A",
    openstudio_path="openstudio",
):
    # --- Weather ---
    wf = get_city_weather_files(city, base_weather_path)
    if wf is None or wf["epw"] is None:
        print(f"❌ Weather files not found for {city}")
        return None

    epw_path = os.path.abspath(wf["epw"])
    scenario_name = generate_scenario_name(scenario_dict)
    scenario_run_dir = os.path.abspath(os.path.join(base_run_dir, scenario_name))
    os.makedirs(scenario_run_dir, exist_ok=True)

    # Skip if already done
    sql_output_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
    if os.path.exists(sql_output_path) and not overwrite_existing:
        print(f"⏭️  Skipping {scenario_name} - simulation already exists")
        return scenario_name

    measure_paths = [os.path.abspath(measure_dir_path)]
    file_paths = [os.path.abspath(base_weather_path), os.path.dirname(epw_path)]

    prototype_step = {
        "measure_dir_name": "create_DOE_prototype_building",
        "name": "Create DOE Prototype Building",
        "arguments": {
            "building_type": building_type,
            "template": template,
            "climate_zone": climate_zone,
            "epw_file": "Not Applicable",
        },
    }

    # ====================================================================
    # BASELINE: OSW with prototype only → E+ simulation runs automatically
    # Then apply Python reporting measure in-process.
    # ====================================================================
    if scenario_dict.get("is_baseline", False):
        osw = {
            "weather_file": epw_path,
            "file_paths": file_paths,
            "measure_paths": measure_paths,
            "steps": [prototype_step],
            "name": scenario_name,
        }
        success = run_osw(osw, "run.osw", scenario_run_dir, openstudio_path, scenario_name)
        if not success:
            return None

        # Apply Python reporting measure after simulation
        model_path = os.path.join(scenario_run_dir, "run", "in.osm")
        sql_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
        if os.path.exists(sql_path):
            print(f"  Applying reporting measure...")
            apply_reporting_measure(model_path, sql_path, measure_dir_path, scenario_name)

    # ====================================================================
    # NON-BASELINE:
    #   Phase 1 — create prototype in a _proto/ subfolder
    #   Phase 2 — apply Python model measures in-process
    #   Phase 3 — OSW with seed_file (no measure steps) → E+ simulation
    #   Phase 4 — apply Python reporting measure in-process
    # ====================================================================
    else:
        # --- Phase 1: create prototype in isolated subfolder ---
        proto_dir = os.path.join(scenario_run_dir, "_proto")
        proto_osw = {
            "weather_file": epw_path,
            "file_paths": file_paths,
            "measure_paths": measure_paths,
            "steps": [prototype_step],
            "name": f"{scenario_name}_proto",
        }
        success = run_osw(proto_osw, "proto.osw", proto_dir, openstudio_path, f"{scenario_name} [prototype]")
        if not success:
            return None

        proto_model_path = os.path.join(proto_dir, "run", "in.osm")
        if not os.path.exists(proto_model_path):
            print(f"❌ {scenario_name}: prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)

        # --- Phase 2: apply Python model measures ---
        translator = openstudio.osversion.VersionTranslator()
        loaded_model = translator.loadModel(openstudio.toPath(final_model_path))

        if not loaded_model.is_initialized():
            print(f"❌ {scenario_name}: failed to load prototype model")
            return None

        model = loaded_model.get()

        if scenario_dict.get("wall_r_value"):
            wall_args = {
                "r_value": float(scenario_dict["wall_r_value"]),
                "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                "api_key": EC3_API_TOKEN or "",
                "insulation_material_type": str(scenario_dict.get("wall_insulation_material_type") or "Blown Fiberglass"),
                "insulation_material_lifetime": float(scenario_dict.get("wall_insulation_material_lifetime") or 30),
                "insulation_thermal_conductivity": float(scenario_dict.get("wall_insulation_thermal_conductivity") or 0.0),
                "insulation_material_density": float(scenario_dict.get("wall_insulation_material_density") or 0.0),
            }
            print(f"  Applying wall insulation (R={scenario_dict['wall_r_value']})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForExteriorWalls", "IncreaseInsulationRValueForExteriorWalls", wall_args):
                print(f"❌ {scenario_name}: wall measure failed")
                del model
                return None

        if scenario_dict.get("roof_r_value"):
            roof_args = {
                "r_value": float(scenario_dict["roof_r_value"]),
                "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                "api_key": EC3_API_TOKEN or "",
                "insulation_material_type": str(scenario_dict.get("roof_insulation_material_type") or "Blown Fiberglass"),
                "insulation_material_lifetime": float(scenario_dict.get("roof_insulation_material_lifetime") or 30),
                "insulation_thermal_conductivity": float(scenario_dict.get("roof_insulation_thermal_conductivity") or 0.0),
                "insulation_material_density": float(scenario_dict.get("roof_insulation_material_density") or 0.0),
            }
            print(f"  Applying roof insulation (R={scenario_dict['roof_r_value']})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForRoofs", "IncreaseInsulationRValueForRoofs", roof_args):
                print(f"❌ {scenario_name}: roof measure failed")
                del model
                return None

        has_window_renovation = any([
            scenario_dict.get("window_u_factor") not in [None, ""],
            scenario_dict.get("window_num_panes") not in [None, ""],
            str(scenario_dict.get("glass_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("wf_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("film_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])

        if has_window_renovation:
            if EC3_API_TOKEN is None:
                print(f"⚠️  EC3 API token not found, skipping window enhancement")
            else:
                requested_panes = scenario_dict.get("window_num_panes")
                if requested_panes not in [None, ""]:
                    num_panes = max(1, min(3, int(float(requested_panes))))
                elif scenario_dict.get("window_u_factor") not in [None, ""]:
                    u_factor = float(scenario_dict["window_u_factor"])
                    num_panes = 2 if u_factor >= 0.30 else 3
                else:
                    num_panes = 2

                window_args = {
                    "glass_option": str(scenario_dict.get("glass_option") or "provide user_num_panes"),
                    "user_num_panes": num_panes,
                    "space_infiltration_reduction_percent": float(scenario_dict.get("window_infiltration_reduction_percent") or 50.0),
                    "glass_pane_thickness": float(scenario_dict.get("glass_pane_thickness") or 0.003),
                    "gap_thickness": float(scenario_dict.get("gap_thickness") or 0.013),
                    "glass_solar_transmittance": float(scenario_dict.get("glass_solar_transmittance") or 0.7),
                    "glass_visible_transmittance": float(scenario_dict.get("glass_visible_transmittance") or 0.8),
                    "glass_front_emissivity": float(scenario_dict.get("glass_front_emissivity") or 0.84),
                    "glass_back_emissivity": float(scenario_dict.get("glass_back_emissivity") or 0.84),
                    "glass_front_solar_reflectance": float(scenario_dict.get("glass_front_solar_reflectance") or 0.15),
                    "glass_back_solar_reflectance": float(scenario_dict.get("glass_back_solar_reflectance") or 0.15),
                    "glass_front_visible_reflectance": float(scenario_dict.get("glass_front_visible_reflectance") or 0.1),
                    "glass_back_visible_reflectance": float(scenario_dict.get("glass_back_visible_reflectance") or 0.1),
                    "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                    "glass_lifetime": float(scenario_dict.get("glass_lifetime") or 15),
                    "wf_lifetime": float(scenario_dict.get("wf_lifetime") or 15),
                    "caulking_lifetime": float(scenario_dict.get("caulking_lifetime") or 10),
                    "film_lifetime": float(scenario_dict.get("film_lifetime") or 10),
                    "weatherstrip_lifetime": float(scenario_dict.get("weatherstrip_lifetime") or 10),
                    "wf_option": str(scenario_dict.get("wf_option") or "none"),
                    "caulking_option": str(scenario_dict.get("caulking_option") or "none"),
                    "caulking_thickness": float(scenario_dict.get("caulking_thickness") or 0.003),
                    "film_option": str(scenario_dict.get("film_option") or "none"),
                    "film_visible_transmittance": float(scenario_dict.get("film_visible_transmittance") or 0.0),
                    "film_solar_transmittance": float(scenario_dict.get("film_solar_transmittance") or 0.0),
                    "film_thermal_emissivity": float(scenario_dict.get("film_thermal_emissivity") or 0.0),
                    "film_thermal_resistance": float(scenario_dict.get("film_thermal_resistance") or 0.0),
                    "weatherstrip_option": str(scenario_dict.get("weatherstrip_option") or "none"),
                    "length_per_unit": float(scenario_dict.get("length_per_unit") or 1.0),
                    "secondary_glazing_option": str(scenario_dict.get("secondary_glazing_option") or "none"),
                    "api_key": EC3_API_TOKEN,
                    "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                }
                print(f"  Applying window enhancement ({num_panes} panes)...")
                if not apply_python_measure(model, Path(measure_dir_path) / "window_enhancement", "WindowEnhancement", window_args):
                    print(f"❌ {scenario_name}: window measure failed")
                    del model
                    return None

        has_door_renovation = any([
            scenario_dict.get("door_option") not in [None, ""],
            str(scenario_dict.get("door_bottom_seal_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("door_top_side_seal_option", "none")).strip().lower() != "none",
        ])

        if has_door_renovation:
            if EC3_API_TOKEN is None:
                print(f"⚠️  EC3 API token not found, skipping door enhancement")
            else:
                door_args = {
                    "space_infiltration_reduction_percent": float(scenario_dict.get("door_infiltration_reduction_percent") or 30.0),
                    "alter_coef": bool(scenario_dict.get("alter_coef", False)),
                    "door_area_per_unit": float(scenario_dict.get("door_area_per_unit") or 1.95),
                    "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                    "door_bottom_seal_option": str(scenario_dict.get("door_bottom_seal_option") or "automatic door bottom"),
                    "door_top_side_seal_option": str(scenario_dict.get("door_top_side_seal_option") or "jamb weatherstrip"),
                    "door_option": str(scenario_dict.get("door_option") or "wooden door"),
                    "strip_lifetime": float(scenario_dict.get("strip_lifetime") or 15),
                    "door_lifetime": float(scenario_dict.get("door_lifetime") or 30),
                    "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                    "api_key": EC3_API_TOKEN,
                    "length_per_unit_bottom_side": float(scenario_dict.get("length_per_unit_bottom_side") or 0.9144),
                    "length_per_unit_other_sides": float(scenario_dict.get("length_per_unit_other_sides") or 5.1816),
                    "door_thermal_conductivity": float(scenario_dict.get("door_thermal_conductivity") or 0.0),
                    "door_density": float(scenario_dict.get("door_density") or 0.0),
                    "door_thickness": float(scenario_dict.get("door_thickness") or 0.0),
                }
                print(f"  Applying door enhancement (door={door_args['door_option']})...")
                if not apply_python_measure(model, Path(measure_dir_path) / "door_enhancement", "DoorEnhancement", door_args):
                    print(f"❌ {scenario_name}: door measure failed")
                    del model
                    return None

        model.save(openstudio.toPath(final_model_path), True)
        del model

        # --- Phase 3: OSW with seed to run EnergyPlus (no measure steps) ---
        sim_osw = {
            "weather_file": epw_path,
            "seed_file": final_model_path,
            "file_paths": file_paths,
            "measure_paths": measure_paths,
            "steps": [],
            "name": scenario_name,
        }
        success = run_osw(sim_osw, "run.osw", scenario_run_dir, openstudio_path, scenario_name)
        if not success:
            return None

        # --- Phase 4: Apply Python reporting measure after simulation ---
        model_path = os.path.join(scenario_run_dir, "run", "in.osm")
        sql_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
        if os.path.exists(sql_path):
            print(f"  Applying reporting measure...")
            apply_reporting_measure(model_path, sql_path, measure_dir_path, scenario_name)

    print(f"✅ Completed: {scenario_name}")
    return scenario_name

# =========================
# SCENARIO GENERATION
# =========================

def generate_scenarios(
    cities,
    building_types,
    custom_combos=None,
):
    """
    Generate scenarios:
    - Always includes baseline
    - Explicit combinations via custom_combos
    """
    scenarios = []

    # 1) BASELINE
    for city, building_type in product(cities, building_types):
        scenarios.append({
            "is_baseline": True,
            "city": city,
            "building_type": building_type,
            "wall_r_value": None,
            "roof_r_value": None,
            "window_u_factor": None,
            "door_option": None,
        })

    # 2) EXPLICIT CUSTOM COMBINATIONS
    if custom_combos:
        for combo_index, combo in enumerate(custom_combos, start=1):
            for city, building_type in product(cities, building_types):
                scenario = {
                    "is_baseline": False,
                    "city": city,
                    "building_type": building_type,
                    "scenario_index": combo_index,
                    "wall_r_value": None,
                    "roof_r_value": None,
                    "window_u_factor": None,
                    "window_num_panes": None,
                    "door_option": None,
                }
                scenario.update(combo)
                scenario["is_baseline"] = False
                scenario["city"] = city
                scenario["building_type"] = building_type
                scenario["scenario_index"] = combo_index
                scenarios.append(scenario)

    return scenarios


# =========================
# POSTPROCESS: COLLECT RESULTS
# =========================

def extract_additional_properties_from_osm(osm_path):
    """
    Extract AdditionalProperties from an OSM file.
    Returns dict with keys for building props and site props (reporting measure).
    """
    try:
        translator = openstudio.osversion.VersionTranslator()
        translator.setAllowNewerVersions(True)
        loaded_model = translator.loadModel(openstudio.toPath(str(osm_path)))

        if not loaded_model.is_initialized():
            return {}

        model = loaded_model.get()
        prop_dict = {}

        # Extract from Building (envelope measure data)
        building = model.getBuilding()
        bldg_props = building.additionalProperties()
        for name in bldg_props.featureNames():
            val = bldg_props.getFeatureAsString(name)
            if val.is_initialized():
                v = val.get()
                try:
                    prop_dict[name] = float(v)
                except ValueError:
                    prop_dict[name] = v

        # Extract from Site (reporting measure data)
        site = model.getSite()
        site_props = site.additionalProperties()
        for name in site_props.featureNames():
            val = site_props.getFeatureAsString(name)
            if val.is_initialized():
                v = val.get()
                try:
                    prop_dict[name] = float(v)
                except ValueError:
                    prop_dict[name] = v

        # Extract from Facility (cross-measure summary)
        facility = model.getFacility()
        fac_props = facility.additionalProperties()
        for name in fac_props.featureNames():
            val = fac_props.getFeatureAsString(name)
            if val.is_initialized():
                v = val.get()
                try:
                    prop_dict[f"facility_{name}"] = float(v)
                except ValueError:
                    prop_dict[f"facility_{name}"] = v

        del model
        return prop_dict

    except Exception as e:
        print(f"  ⚠️  Failed to extract properties from {osm_path}: {e}")
        return {}


def collect_results_to_csv(base_run_dir, csv_base_name="parametric_results"):
    """
    Walk all run directories, extract AdditionalProperties from OSM files,
    and collect all results into a comprehensive CSV.
    """
    import pandas as pd
    rows = []

    for scenario_folder in sorted(os.listdir(base_run_dir)):
        scenario_path = os.path.join(base_run_dir, scenario_folder)
        if not os.path.isdir(scenario_path):
            continue

        # Look for SQL file
        sql_path = os.path.join(scenario_path, "run", "eplusout.sql")
        if not os.path.exists(sql_path):
            continue

        # Parse scenario name
        scenario_parts = scenario_folder.split("_")
        is_baseline = scenario_parts[0] == "baseline"

        row = {
            "scenario_name": scenario_folder,
            "is_baseline": is_baseline,
        }

        # Extract AdditionalProperties from final OSM file
        osm_path = os.path.join(scenario_path, "run", "in.osm")
        if os.path.exists(osm_path):
            print(f"  Extracting properties from {scenario_folder}...")
            additional_props = extract_additional_properties_from_osm(osm_path)
            row.update(additional_props)

        rows.append(row)

    if not rows:
        print("\nℹ️ No simulation results found.")
        return None

    df_results = pd.DataFrame(rows)

    # Reorder columns
    priority_cols = ["scenario_name", "is_baseline"]
    existing_priority = [c for c in priority_cols if c in df_results.columns]
    remaining = sorted([c for c in df_results.columns if c not in existing_priority])
    df_results = df_results[existing_priority + remaining]

    csv_path = os.path.join(base_run_dir, f"{csv_base_name}.csv")
    df_results.to_csv(csv_path, index=False)
    print(f"\n🧾 Results CSV: {csv_path}")
    print(f"   Total scenarios: {len(df_results)}")
    print(f"   Columns: {len(df_results.columns)}")

    return df_results


def get_prop_value(props, name):
    """Helper to safely extract value from AdditionalProperties by type."""
    if props.getFeatureAsDouble(name).is_initialized():
        return props.getFeatureAsDouble(name).get()
    if props.getFeatureAsString(name).is_initialized():
        return props.getFeatureAsString(name).get()
    if props.getFeatureAsInteger(name).is_initialized():
        return props.getFeatureAsInteger(name).get()
    return None

def extract_scenario_data(osm_path, scenario_name):
    """Loads an OSM and extracts target properties from AdditionalProperties."""
    results = {"scenario": scenario_name}
    
    vt = openstudio.osversion.VersionTranslator()
    model_ptr = vt.loadModel(openstudio.toPath(str(osm_path)))
    
    if not model_ptr.is_initialized():
        print(f"  ✗ Failed to load: {osm_path.name}")
        return None

    model = model_ptr.get()
    idd_type = openstudio.IddObjectType("OS:AdditionalProperties")
    all_props_objects = model.getObjectsByType(idd_type)
    
    found_any = False
    for obj in all_props_objects:
        opt_props = openstudio.model.toAdditionalProperties(obj)
        
        if opt_props.is_initialized():
            props = opt_props.get()
            feature_names = props.featureNames()
            
            # 1. Embodied Carbon with Measure Name prefix
            if "total_additional_embodied_carbon_kgCO2" in feature_names:
                measure_name = get_prop_value(props, "name")
                val = get_prop_value(props, "total_additional_embodied_carbon_kgCO2")
                if measure_name and val is not None:
                    header = f"{measure_name} total_additional_embodied_carbon_kgCO2"
                    results[header] = val
                    found_any = True

            # 2. Operating Data
            op_keys = [
                "annual_electricity_cost_usd",
                "annual_gas_cost_usd",
                "annual_electricity_operating_emissions_kg_co2e",
                "annual_gas_operating_emissions_kg_co2e"
            ]
            for key in op_keys:
                if key in feature_names:
                    val = get_prop_value(props, key)
                    if val is not None:
                        results[key] = val
                        found_any = True
                
    return results if found_any else None

def generate_parametric_recap(target_path):
    """
    Main function to run the extraction and generate parametric_results.csv
    """
    root_path = Path(target_path)
    
    if not root_path.exists():
        print(f"Error: Path '{target_path}' does not exist.")
        return

    all_data = []
    all_headers = set()
    
    print("="*80)
    print(f"GENERATING PARAMETRIC RECAP FROM: {root_path}")
    print("="*80)

    # Search for OSM files
    osm_files = [p for p in root_path.rglob("*.osm") if p.name in ["in.osm", "in_modified.osm"]]

    for osm_path in sorted(osm_files):
        # Determine scenario name from folder structure
        parts = list(osm_path.parts)
        try:
            idx = parts.index('run')
            scenario = parts[idx-1]
        except ValueError:
            scenario = osm_path.parent.name
            
        # print(f"Processing Scenario: {scenario}")
        
        data = extract_scenario_data(osm_path, scenario)
        if data:
            all_data.append(data)
            all_headers.update(data.keys())

    if not all_data:
        print("\n✗ No matching data found.")
        return

    # Define Header Order
    fixed_headers = [
        "scenario",
        "annual_electricity_cost_usd",
        "annual_gas_cost_usd",
        "annual_electricity_operating_emissions_kg_co2e",
        "annual_gas_operating_emissions_kg_co2e"
    ]
    
    embodied_headers = sorted([h for h in all_headers if h not in fixed_headers and h != "scenario"])
    fieldnames = fixed_headers + embodied_headers
    
    csv_path = root_path / "parametric_results.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_data)

    print("\n" + "="*80)
    print(f"COMPLETE: {len(all_data)} scenarios successfully processed.")
    print(f"Report saved to: {csv_path}")
    print("="*80)


# =========================
# GLOBAL SETTINGS
# =========================

RUN_NAME = "run_test_004"

def detect_openstudio_cli_path():
    env_path = os.environ.get("OPENSTUDIO_PATH")
    candidates = [
        env_path,
        "C:/Program Files/openstudio-3.11.0/bin/openstudio.exe",
        "/Applications/OpenStudio-3.11.0/bin/openstudio",
        "openstudio",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if candidate == "openstudio" or os.path.exists(candidate):
            return candidate
    return "openstudio"

OPENSTUDIO_PATH = detect_openstudio_cli_path()
OVERWRITE_EXISTING = True

notebook_dir = Path.cwd()
base_weather_path = str(notebook_dir / "weather")
measure_dir_path = str(notebook_dir.parent / "measures")
base_run_dir = str(notebook_dir / "simulations" / RUN_NAME)

city_climate_zones = {
    "Amarillo":     "ASHRAE 169-2013-3B",
}

# =========================
# PARAMETRIC STUDY CONFIGURATION
# =========================

CITIES = list(city_climate_zones.keys())

BUILDING_TYPES = [
    "SmallOffice",
]

TEMPLATE = "90.1-2010"

CUSTOM_COMBOS = [
    {
        "wall_r_value": 13,
        "wall_insulation_material_type": "Fiberglass Batts",
        "roof_r_value": 24.4,
        "roof_insulation_material_type": "Blown Fiberglass",
        "window_num_panes": 3,
        "window_infiltration_reduction_percent": 30.0,
        "glass_option": "provide user_num_panes",
        "wf_option": "wood window frame",
        "caulking_option": "acrylic",
        "film_option": "low-e film",
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "secondary_glazing_option": "none",
        "door_option": "wooden door",
        "door_infiltration_reduction_percent": 30.0,
        "door_bottom_seal_option": "automatic door bottom",
        "door_top_side_seal_option": "jamb weatherstrip",
        "analysis_period": 30,
        "gwp_statistic": "median",
    },
]

# =========================
# MAIN - RUN PARAMETRIC STUDY
# =========================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PARAMETRIC STUDY: BUILDING ENERGY EFFICIENCY MEASURES")
    print(f"Using OpenStudio: {OPENSTUDIO_PATH}")
    print(f"Run Name: {RUN_NAME}")
    print(f"Output Directory: {base_run_dir}")
    print("=" * 70)

    print("\n📋 Generating scenarios...")
    scenarios = generate_scenarios(
        cities=CITIES,
        building_types=BUILDING_TYPES,
        custom_combos=CUSTOM_COMBOS,
    )

    total_sims = len(scenarios)
    baseline_count = sum(1 for s in scenarios if s["is_baseline"])
    custom_count = total_sims - baseline_count

    print(f"\n📦 Total scenarios: {total_sims}")
    print(f"   - Cities: {len(CITIES)}")
    print(f"   - Building Types: {len(BUILDING_TYPES)}")
    print(f"\n   Breakdown:")
    print(f"   - Baseline: {baseline_count}")
    print(f"   - Custom combos: {custom_count}")
    print("=" * 70)

    sim_count = 0
    start_time = time.time()
    successful_scenarios = []
    failed_scenarios = []

    for scenario in scenarios:
        sim_count += 1
        city = scenario["city"]
        building_type = scenario["building_type"]
        climate_zone = city_climate_zones.get(city, "ASHRAE 169-2013-5A")

        scenario_name = generate_scenario_name(scenario)
        print(f"\n[{sim_count}/{total_sims}] {scenario_name}")

        sim_start = time.time()

        result = create_simulation(
            city=city,
            base_run_dir=base_run_dir,
            measure_dir_path=measure_dir_path,
            base_weather_path=base_weather_path,
            scenario_dict=scenario,
            overwrite_existing=OVERWRITE_EXISTING,
            building_type=building_type,
            template=TEMPLATE,
            climate_zone=climate_zone,
            openstudio_path=OPENSTUDIO_PATH,
        )

        if result:
            successful_scenarios.append(result)
        else:
            failed_scenarios.append(scenario_name)

        sim_elapsed = time.time() - sim_start
        print(f"   ⏱️  Time: {sim_elapsed/60:.1f} min")

    total_elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("SIMULATION SUMMARY")
    print("=" * 70)
    print(f"⏱️  Total time: {total_elapsed/60:.1f} min ({total_elapsed/3600:.2f} hours)")
    print(f"✅ Successful: {len(successful_scenarios)}/{total_sims}")
    print(f"❌ Failed: {len(failed_scenarios)}/{total_sims}")

    if failed_scenarios:
        print("\nFailed scenarios:")
        for failed in failed_scenarios:
            print(f"  - {failed}")

    # Collect results
    print("\n" + "=" * 70)
    print("COLLECTING RESULTS FROM OSM FILES")
    print("=" * 70)
    generate_parametric_recap(f"./simulations/{RUN_NAME}")
    print("\n✅ Parametric study complete!")

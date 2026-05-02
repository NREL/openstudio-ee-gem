#!/usr/bin/env python3
# Auto-generated from workflow.ipynb

# Standard library

import json
import os
import subprocess
import time
from itertools import product, zip_longest
import re
import sys
from pathlib import Path
import configparser
import shutil
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import csv
import sqlite3

# OpenStudio 3.11.0 Python bindings are built for Python 3.12.
def _resolve_existing_path(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        candidate = str(candidate)
        if os.path.exists(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _is_python312_command(cmd):
    try:
        probe = subprocess.run(
            cmd + ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return probe.returncode == 0 and probe.stdout.strip() == "3.12"
    except Exception:
        return False


def _find_python312_command():
    candidates = [[p] for p in [os.environ.get("PYTHON312_PATH"), shutil.which("python3.12")] if p]

    if os.name == "nt":
        roots = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path(os.environ.get("ProgramFiles", "")),
            Path(os.environ.get("ProgramFiles(x86)", "")),
        ]
        for root in roots:
            if not str(root):
                continue
            candidates.extend([[str(p)] for p in sorted(root.glob("Python312*/python.exe"))])

        py_launcher = shutil.which("py")
        if py_launcher:
            candidates.append([py_launcher, "-3.12"])

    if sys.executable:
        candidates.append([sys.executable])

    seen = set()
    for cmd in candidates:
        key = tuple(cmd)
        if key in seen:
            continue
        seen.add(key)
        if _is_python312_command(cmd):
            return cmd
    return None

def _ensure_openstudio_python_compatibility():
    required_major, required_minor = 3, 12
    if (sys.version_info.major, sys.version_info.minor) == (required_major, required_minor):
        return

    detected = f"{sys.version_info.major}.{sys.version_info.minor}"
    required = f"{required_major}.{required_minor}"
    python312_cmd = _find_python312_command()
    # Try seamless re-exec once when running as a script.
    if __name__ == "__main__" and python312_cmd and os.environ.get("OPENSTUDIO_SKIP_REEXEC") != "1":
        print(
            "Detected incompatible Python "
            + detected
            + " for OpenStudio bindings. Re-launching with Python "
            + required
            + "..."
        )
        env = os.environ.copy()
        env["OPENSTUDIO_SKIP_REEXEC"] = "1"
        completed = subprocess.run(python312_cmd + sys.argv, env=env)
        raise SystemExit(completed.returncode)

    cmd_text = " ".join(f'"{part}"' if " " in str(part) else str(part) for part in (python312_cmd or []))
    command_hint = (
        f"{cmd_text} \"{Path(__file__).resolve()}\""
        if python312_cmd
        else "<path-to-python-3.12> workflow.py"
    )
    raise RuntimeError(
        "OpenStudio 3.11.0 Python bindings require Python "
        + required
        + ". Current interpreter is Python "
        + detected
        + ".\n"
        + "Run this script with Python 3.12, for example:\n"
        + command_hint
    )

_ensure_openstudio_python_compatibility()

# Add OpenStudio 3.11.0 Python bindings to path BEFORE importing
def detect_openstudio_python_path():
    env_path = os.environ.get("OPENSTUDIO_PYTHON_PATH")
    candidates = []
    if env_path:
        candidates.append(env_path)

    # Infer OpenStudio Python bindings from CLI path if available.
    cli_candidate = os.environ.get("OPENSTUDIO_PATH") or shutil.which("openstudio")
    if cli_candidate and os.path.exists(cli_candidate):
        cli_path = Path(cli_candidate).resolve()
        inferred_python_dir = cli_path.parent.parent / "Python"
        candidates.append(str(inferred_python_dir))

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
    script_dir = Path(__file__).parent
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

# --- HELPER FUNCTIONS ---
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

def _material_slug(material_name):
    if material_name is None:
        return None
    slug = str(material_name).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or None

def generate_scenario_name(scenario_dict):
    """Generate a unique scenario name from scenario parameters."""
    parts = []
    if scenario_dict.get("is_baseline", False):
        parts.append("baseline")
    else:
        scenario_index = scenario_dict.get("scenario_index")
        if scenario_index is not None:
            parts.append(f"scenario_{int(scenario_index)}")
        else:
            measure_count = sum([
                1 if scenario_dict.get("wall_r_value") else 0,
                1 if scenario_dict.get("roof_r_value") else 0,
                1 if scenario_dict.get("window_num_panes") else 0,
                1 if scenario_dict.get("door_option") else 0,
            ])
            if measure_count > 1:
                parts.append("all")
            if scenario_dict.get("wall_r_value"):
                wall_part = f"wall_r{scenario_dict['wall_r_value']}"
                wall_material_slug = _material_slug(scenario_dict.get("wall_insulation_material_type"))
                if wall_material_slug:
                    wall_part += f"_{wall_material_slug}"
                parts.append(wall_part)
            if scenario_dict.get("roof_r_value"):
                roof_part = f"roof_r{scenario_dict['roof_r_value']}"
                roof_material_slug = _material_slug(scenario_dict.get("roof_insulation_material_type"))
                if roof_material_slug:
                    roof_part += f"_{roof_material_slug}"
                parts.append(roof_part)
            if scenario_dict.get("window_num_panes"):
                parts.append(f"window_num_panes{int(float(scenario_dict['window_num_panes']))}")
            window_infil = scenario_dict.get("window_enhancement_infiltration_reduction_percent", scenario_dict.get("window_infiltration_reduction_percent"))
            if window_infil not in [None, "", 0, 0.0]:
                parts.append(f"window_infil{float(window_infil):g}")
            for key, tag in [
                ("weatherstrip_option", "window_weatherstrip"),
                ("wf_option", "window_wf"),
                ("film_option", "window_film"),
                ("caulking_option", "window_caulking"),
                ("secondary_glazing_option", "window_secondary_igu"),
            ]:
                value = scenario_dict.get(key)
                if value not in [None, "", "none"]:
                    parts.append(f"{tag}_{_material_slug(value)}")
            if scenario_dict.get("door_option"):
                door_abbrev = scenario_dict['door_option'].replace(' ', '_').replace('door', 'd')
                parts.append(f"door_{door_abbrev}")
            door_infil = scenario_dict.get("door_infiltration_reduction_percent")
            if door_infil not in [None, "", 0, 0.0]:
                parts.append(f"door_infil{float(door_infil):g}")
            for key, tag in [
                ("door_bottom_seal_option", "door_bottom_seal"),
                ("door_top_side_seal_option", "door_top_side_seal"),
            ]:
                value = scenario_dict.get(key)
                if value not in [None, "", "none"]:
                    parts.append(f"{tag}_{_material_slug(value)}")
    parts.append(scenario_dict["building_type"])
    parts.append(scenario_dict["city"])
    return "_".join(parts)

def detect_window_upgrade_status(model, requested_panes):
    """Detect whether requested pane upgrade was actually applied to model windows."""
    windows = [
        ss for ss in model.getSubSurfaces()
        if ss.subSurfaceType() in ["FixedWindow", "OperableWindow", "Skylight"]
    ]
    if not windows:
        return None

    upgraded_count = 0
    simple_glazing_count = 0
    for subsurface in windows:
        if not subsurface.construction().is_initialized():
            continue
        construction = subsurface.construction().get()
        construction_name = construction.nameString()
        if f"_New_{requested_panes}Pane_Construction" in construction_name:
            upgraded_count += 1

        is_simple = False
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            for layer_index in range(layered.numLayers()):
                layer_material = layered.getLayer(layer_index)
                if layer_material.to_SimpleGlazing().is_initialized():
                    is_simple = True
                    break
        if is_simple:
            simple_glazing_count += 1

    if upgraded_count > 0:
        return "upgraded"
    if simple_glazing_count == len(windows):
        return "failed_simple_glazing"
    return "requested_not_applied"

def collect_window_inventory(model):
    """Collect window inventory needed for report-side action status decisions."""
    inventory = {
        "window_total_count": 0,
        "window_fixed_count": 0,
        "window_operable_count": 0,
        "window_skylight_count": 0,
        "window_simple_glazing_count": 0,
    }
    windows = [
        ss for ss in model.getSubSurfaces()
        if ss.subSurfaceType() in ["FixedWindow", "OperableWindow", "Skylight"]
    ]
    inventory["window_total_count"] = len(windows)
    for subsurface in windows:
        subtype = str(subsurface.subSurfaceType())
        if subtype == "FixedWindow":
            inventory["window_fixed_count"] += 1
        elif subtype == "OperableWindow":
            inventory["window_operable_count"] += 1
        elif subtype == "Skylight":
            inventory["window_skylight_count"] += 1

        if not subsurface.construction().is_initialized():
            continue
        construction = subsurface.construction().get()
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            for layer_index in range(layered.numLayers()):
                layer_material = layered.getLayer(layer_index)
                if layer_material.to_SimpleGlazing().is_initialized():
                    inventory["window_simple_glazing_count"] += 1
                    break

    return inventory

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
        print(f" {label}: timed out after 600s")
        return False

    except Exception as e:
        print(f" {label}: subprocess error: {e}")
        return False

    out_osw_path = os.path.join(run_dir, "out.osw")
    if not os.path.exists(out_osw_path):
        print(f" {label}: out.osw not found (OpenStudio may have crashed)")
        if result.stderr:
            print(f"   STDERR: {result.stderr[:500]}")
        return False
    with open(out_osw_path, "r") as f:
        out_osw = json.load(f)
    if out_osw.get("completed_status") != "Success":
        print(f" {label}: OSW failed")
        run_log_path = os.path.join(run_dir, "run", "run.log")
        if os.path.exists(run_log_path):
            with open(run_log_path, "r") as log_f:
                for line in log_f:
                    if "ERROR" in line:
                        print(f"    LOG: {line.rstrip()}")
        return False
    return True

def append_scenario_failure_log(scenario_run_dir, reason):
    """Append a timestamped failure reason to scenario_failure.log."""
    failure_log_path = os.path.join(scenario_run_dir, "scenario_failure.log")
    try:
        os.makedirs(os.path.dirname(failure_log_path), exist_ok=True)
        with open(failure_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {reason}\n")
    except Exception as log_err:
        print(f"  Warning: failed to write failure log at {failure_log_path}: {log_err}")

def load_measure_module_from_folder(measure_folder, module_tag):
    """Load a measure module directly from measure.py to avoid sys.modules cache collisions."""
    measure_path = os.path.join(str(measure_folder), "measure.py")
    if not os.path.exists(measure_path):
        raise FileNotFoundError(f"measure.py not found at {measure_path}")

    import importlib.util
    module_name = f"_dynamic_measure_{module_tag}_{abs(hash(os.path.abspath(measure_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, measure_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {measure_path}")

    measure_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(measure_module)
    return measure_module

def apply_python_measure(model, measure_folder, measure_class_name, arguments_dict):
    """
    Apply a Python OpenStudio ModelMeasure directly to a model in-process.
    Returns True if successful, False otherwise.
    """
    measure_folder_str = str(measure_folder)
    try:
        measure_module = load_measure_module_from_folder(measure_folder_str, measure_class_name)
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
            print(f"    {label}: could not load model for reporting measure")
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
        measure_module = load_measure_module_from_folder(measure_folder_str, "OperatingCostCarbonReport")
        measure = measure_module.OperatingCostCarbonReport()
        # Arguments (none required for this measure  reads from CSV resources)
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        # Run
        measure.run(runner, arg_map)
        result_value = runner.result().value().valueName()
        if result_value != "Success":
            print(f"    {label}: reporting measure result: {result_value}")
            for error in runner.result().errors():
                print(f"     ERROR: {error.logMessage()}")
            return False

        # Save model with AdditionalProperties written by the reporting measure
        model.save(openstudio.toPath(str(model_path)), True)
        del model
        return True

    except Exception as e:
        print(f"    {label}: reporting measure error: {e}")
        import traceback
        traceback.print_exc()
        return False

def enforce_weather_url_in_osm(osm_path, epw_path):
    """Force OS:WeatherFile URL in an OSM to the selected EPW path."""
    try:
        with open(osm_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        target = os.path.abspath(epw_path).replace("\\", "/")
        in_weather_obj = False
        updated = False
        for i, line in enumerate(lines):
            if not in_weather_obj and line.strip().startswith("OS:WeatherFile,"):
                in_weather_obj = True
                continue

            if in_weather_obj:
                if "!- Url" in line or "!- URL" in line:
                    indent = line[: len(line) - len(line.lstrip())]
                    rest = line.split(",", 1)[1] if "," in line else " !- Url\n"
                    lines[i] = f"{indent}{target},{rest}"
                    updated = True
                    break
                if ";" in line:
                    break

        if updated:
            with open(osm_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        else:
            print(f"    Could not locate weather URL field in: {osm_path}")

        return updated
    except Exception as e:
        print(f"    Failed to enforce weather URL in {osm_path}: {e}")
        return False

# --- CORE: SINGLE SCENARIO CREATION/RUN ---
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
        print(f"  Weather files not found for {city}")
        append_scenario_failure_log(os.path.abspath(os.path.join(base_run_dir, generate_scenario_name(scenario_dict))), f"weather files not found for city={city}")
        return None

    epw_path = os.path.abspath(wf["epw"])
    scenario_name = generate_scenario_name(scenario_dict)
    scenario_run_dir = os.path.abspath(os.path.join(base_run_dir, scenario_name))
    os.makedirs(scenario_run_dir, exist_ok=True)
    def log_failure(reason):
        append_scenario_failure_log(scenario_run_dir, reason)

    # Skip if already done
    sql_output_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
    if os.path.exists(sql_output_path) and not overwrite_existing:
        print(f"  Skipping {scenario_name} - simulation already exists")
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
    # BASELINE: follow the same two-stage weather path as scenarios
    #   Phase 1: create prototype in a _proto/ subfolder
    #   Phase 2: OSW with seed_file (no measure steps), then run E+ simulation
    #   Phase 3: apply Python reporting measure in-process
    # ====================================================================
    if scenario_dict.get("is_baseline", False):
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
            log_failure("prototype OSW failed (baseline)")
            return None

        proto_model_path = os.path.join(proto_dir, "run", "in.osm")
        if not os.path.exists(proto_model_path):
            print(f"  {scenario_name}: prototype model not found at {proto_model_path}")
            log_failure(f"prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)
        enforce_weather_url_in_osm(final_model_path, epw_path)
        # --- Phase 2: run simulation from seeded model ---
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
            log_failure("simulation OSW failed (baseline)")
            return None

        # --- Phase 3: apply Python reporting measure after simulation ---
        model_path = os.path.join(scenario_run_dir, "run", "in.osm")
        sql_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
        if os.path.exists(sql_path):
            print(f"  Applying reporting measure...")
            apply_reporting_measure(model_path, sql_path, measure_dir_path, scenario_name)

    # ====================================================================
    # NON-BASELINE:
    #   Phase 1: create prototype in a _proto/ subfolder
    #   Phase 2: apply Python model measures in-process
    #   Phase 3: OSW with seed_file (no measure steps), then run E+ simulation
    #   Phase 4: apply Python reporting measure in-process
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
            log_failure("prototype OSW failed (non-baseline)")
            return None
        proto_model_path = os.path.join(proto_dir, "run", "in.osm")
        if not os.path.exists(proto_model_path):
            print(f"  {scenario_name}: prototype model not found at {proto_model_path}")
            log_failure(f"prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)
        # --- Phase 2: apply Python model measures ---
        translator = openstudio.osversion.VersionTranslator()
        loaded_model = translator.loadModel(openstudio.toPath(final_model_path))
        if not loaded_model.is_initialized():
            print(f"  {scenario_name}: failed to load prototype model")
            log_failure("failed to load prototype model")
            return None

        model = loaded_model.get()
        wall_args = None
        roof_args = None
        window_args = None
        door_args = None
        window_upgrade_status = None
        window_infiltration_reduction = scenario_dict.get(
            "window_enhancement_infiltration_reduction_percent",
            scenario_dict.get("window_infiltration_reduction_percent"),
        )
        has_window_renovation = any([
            scenario_dict.get("window_num_panes"),
            window_infiltration_reduction not in [None, "", 0, 0.0],
            str(scenario_dict.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("wf_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("film_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        has_door_renovation = any([
            scenario_dict.get("door_option"),
            scenario_dict.get("door_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario_dict.get("door_bottom_seal_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("door_top_side_seal_option", "none")).strip().lower() != "none",
        ])
        requires_ec3_data = any([
            scenario_dict.get("wall_r_value"),
            scenario_dict.get("roof_r_value"),
            has_window_renovation,
            has_door_renovation,
        ])
        if requires_ec3_data and not EC3_API_TOKEN:
            print("  EC3 API token is required for online cost/carbon calculations; scenario skipped.")
            log_failure("missing EC3 API token for required online cost/carbon calculations")
            del model
            return None

        if scenario_dict.get("wall_r_value"):
            wall_material_type = scenario_dict.get("wall_insulation_material_type") or "Blown Fiberglass"
            wall_material_lifetime = float(scenario_dict.get("wall_insulation_material_lifetime") or 30)
            wall_args = {
                "r_value": float(scenario_dict["wall_r_value"]),
                "analysis_period": 30,
                "gwp_statistic": "median",
                "api_key": EC3_API_TOKEN,
                "insulation_material_type": wall_material_type,
                "insulation_material_lifetime": wall_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
                "calculate_costs": bool(scenario_dict.get("calculate_costs", True)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "custom_cost_per_cf": float(scenario_dict.get("custom_cost_per_cf") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            print(f"  Applying wall insulation (R={scenario_dict['wall_r_value']}, material={wall_material_type})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForExteriorWalls", "IncreaseInsulationRValueForExteriorWalls", wall_args):
                print(f"   {scenario_name}: wall measure failed")
                log_failure("wall measure failed")
                del model
                return None
        if scenario_dict.get("roof_r_value"):
            roof_material_type = scenario_dict.get("roof_insulation_material_type") or "Blown Fiberglass"
            roof_material_lifetime = float(scenario_dict.get("roof_insulation_material_lifetime") or 30)
            roof_args = {
                "r_value": float(scenario_dict["roof_r_value"]),
                "analysis_period": 30,
                "gwp_statistic": "median",
                "api_key": EC3_API_TOKEN,
                "insulation_material_type": roof_material_type,
                "insulation_material_lifetime": roof_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
                "calculate_costs": bool(scenario_dict.get("calculate_costs", True)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "custom_cost_per_cf": float(scenario_dict.get("custom_cost_per_cf") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            print(f"  Applying roof insulation (R={scenario_dict['roof_r_value']}, material={roof_material_type})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForRoofs", "IncreaseInsulationRValueForRoofs", roof_args):
                print(f"   {scenario_name}: roof measure failed")
                log_failure("roof measure failed")
                del model
                return None
        if has_window_renovation:
            requested_num_panes = scenario_dict.get("window_num_panes")
            if requested_num_panes in [None, ""]:
                num_panes = 2
                glass_option = str(scenario_dict.get("glass_option") or "none")
            else:
                raw_num_panes = int(float(requested_num_panes))
                num_panes = max(1, min(3, raw_num_panes))
                glass_option = str(scenario_dict.get("glass_option") or "provide user_num_panes")
            window_args = {
                "glass_option": glass_option,
                "user_num_panes": num_panes,
                "space_infiltration_reduction_percent": float(window_infiltration_reduction if window_infiltration_reduction not in [None, ""] else scenario_dict.get("space_infiltration_reduction_percent", 0.0) or 0.0),
                "glass_pane_thickness": float(scenario_dict.get("glass_pane_thickness") or 0.0),
                "gap_thickness": float(scenario_dict.get("gap_thickness") or 0.0),
                "glass_solar_transmittance": float(scenario_dict.get("glass_solar_transmittance") or 0.0),
                "glass_visible_transmittance": float(scenario_dict.get("glass_visible_transmittance") or 0.0),
                "glass_front_emissivity": float(scenario_dict.get("glass_front_emissivity") or 0.0),
                "glass_back_emissivity": float(scenario_dict.get("glass_back_emissivity") or 0.0),
                "glass_front_solar_reflectance": float(scenario_dict.get("glass_front_solar_reflectance") or 0.0),
                "glass_back_solar_reflectance": float(scenario_dict.get("glass_back_solar_reflectance") or 0.0),
                "glass_front_visible_reflectance": float(scenario_dict.get("glass_front_visible_reflectance") or 0.0),
                "glass_back_visible_reflectance": float(scenario_dict.get("glass_back_visible_reflectance") or 0.0),
                "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                "glass_lifetime": float(scenario_dict.get("glass_lifetime") or 15),
                "wf_lifetime": float(scenario_dict.get("wf_lifetime") or 15),
                "caulking_lifetime": float(scenario_dict.get("caulking_lifetime") or 10),
                "film_lifetime": float(scenario_dict.get("film_lifetime") or 10),
                "weatherstrip_lifetime": float(scenario_dict.get("weatherstrip_lifetime") or 10),
                "wf_option": str(scenario_dict.get("wf_option") or "none"),
                "caulking_option": str(scenario_dict.get("caulking_option") or "none"),
                "caulking_thickness": float(scenario_dict.get("caulking_thickness") or 0.0),
                "film_option": str(scenario_dict.get("film_option") or "none"),
                "film_visible_transmittance": float(scenario_dict.get("film_visible_transmittance") or 0.0),
                "film_solar_transmittance": float(scenario_dict.get("film_solar_transmittance") or 0.0),
                "film_thermal_emissivity": float(scenario_dict.get("film_thermal_emissivity") or 0.0),
                "film_thermal_resistance": float(scenario_dict.get("film_thermal_resistance") or 0.0),
                "weatherstrip_option": str(scenario_dict.get("weatherstrip_option") or "none"),
                "length_per_unit": float(scenario_dict.get("length_per_unit") or 0.0),
                "secondary_glazing_option": str(scenario_dict.get("secondary_glazing_option") or "none"),
                "api_key": EC3_API_TOKEN,
                "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                "calculate_costs": bool(scenario_dict.get("calculate_costs", True)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "glass_cost_per_cf": float(scenario_dict.get("glass_cost_per_cf") or 0.0),
                "frame_cost_per_sf": float(scenario_dict.get("frame_cost_per_sf") or 0.0),
                "caulking_cost_per_cy": float(scenario_dict.get("caulking_cost_per_cy") or 0.0),
                "film_cost_per_sf": float(scenario_dict.get("film_cost_per_sf") or 0.0),
                "weatherstrip_cost_per_lf": float(scenario_dict.get("weatherstrip_cost_per_lf") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            print(f"  Applying window enhancement (num_panes={num_panes}, glass_option={glass_option})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "window_enhancement", "WindowEnhancement", window_args):
                print(f"    {scenario_name}: window measure failed")
                log_failure("window measure failed")
                del model
                return None

            window_upgrade_status = detect_window_upgrade_status(model, num_panes)

        if has_door_renovation:
            door_args = {
                "space_infiltration_reduction_percent": float(scenario_dict.get("door_infiltration_reduction_percent", scenario_dict.get("space_infiltration_reduction_percent", 0.0)) or 0.0),
                "alter_coef": bool(scenario_dict.get("alter_coef", False)),
                "door_area_per_unit": float(scenario_dict.get("door_area_per_unit") or 0.0),
                "analysis_period": float(scenario_dict.get("analysis_period") or 30),
                "door_bottom_seal_option": str(scenario_dict.get("door_bottom_seal_option") or "none"),
                "door_top_side_seal_option": str(scenario_dict.get("door_top_side_seal_option") or "none"),
                "door_option": str(scenario_dict.get("door_option") or "none"),
                "strip_lifetime": float(scenario_dict.get("strip_lifetime") or 15),
                "door_lifetime": float(scenario_dict.get("door_lifetime") or 30),
                "gwp_statistic": str(scenario_dict.get("gwp_statistic") or "median"),
                "api_key": EC3_API_TOKEN,
                "length_per_unit_bottom_side": float(scenario_dict.get("length_per_unit_bottom_side") or 0.0),
                "length_per_unit_other_sides": float(scenario_dict.get("length_per_unit_other_sides") or 0.0),
                "door_thermal_conductivity": float(scenario_dict.get("door_thermal_conductivity") or 0.0),
                "door_density": float(scenario_dict.get("door_density") or 0.0),
                "door_thickness": float(scenario_dict.get("door_thickness") or 0.0),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "custom_door_cost_per_area": float(scenario_dict.get("custom_door_cost_per_area") or 0.0),
                "custom_bottom_seal_cost": float(scenario_dict.get("custom_bottom_seal_cost") or 0.0),
                "custom_top_side_seal_cost": float(scenario_dict.get("custom_top_side_seal_cost") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 0.0),
            }
            print(f"  Applying door enhancement (door={door_args['door_option']})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "door_enhancement", "DoorEnhancement", door_args):
                print(f"    {scenario_name}: door measure failed")
                log_failure("door measure failed")
                del model
                return None

        renovation_details = "Envelope renovation applied (details generated at report time)"
        model.getSite().additionalProperties().setFeature("renovation_details", renovation_details)
        model.save(openstudio.toPath(final_model_path), True)
        enforce_weather_url_in_osm(final_model_path, epw_path)
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
            log_failure("simulation OSW failed (non-baseline)")
            return None
        # --- Phase 4: Apply Python reporting measure after simulation ---
        model_path = os.path.join(scenario_run_dir, "run", "in.osm")
        sql_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
        if os.path.exists(sql_path):
            print(f"  Applying reporting measure...")
            apply_reporting_measure(model_path, sql_path, measure_dir_path, scenario_name)
    print(f"  Completed: {scenario_name}")
    return scenario_name

# --- SCENARIO GENERATION ---
def generate_scenarios(
    cities,
    building_types,
    custom_combos=None,
):

    """
    Generate scenarios:
    - Always includes baseline
    - Custom explicit combinations via custom_combos
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
            "window_num_panes": None,
            "door_option": None,
            "wall_insulation_material_type": None,
            "wall_insulation_material_lifetime": None,
            "roof_insulation_material_type": None,
            "roof_insulation_material_lifetime": None,
            "scenario_index": None,
            "window_enhancement_infiltration_reduction_percent": None,
            "door_infiltration_reduction_percent": None,
            "weatherstrip_option": None,
            "wf_option": None,
            "film_option": None,
            "caulking_option": None,
            "secondary_glazing_option": None,
            "door_bottom_seal_option": None,
            "door_top_side_seal_option": None,
        })

    # 2) CUSTOM EXPLICIT COMBINATIONS
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
                    "window_num_panes": None,
                    "door_option": None,
                    "wall_insulation_material_type": None,
                    "wall_insulation_material_lifetime": None,
                    "roof_insulation_material_type": None,
                    "roof_insulation_material_lifetime": None,
                }
                # Keep all user-defined combo arguments for downstream measure args.
                scenario.update(combo)
                # Guard required fields from accidental override in combo.
                scenario["is_baseline"] = False
                scenario["city"] = city
                scenario["building_type"] = building_type
                scenario["scenario_index"] = combo_index
                scenarios.append(scenario)
    return scenarios

# --- POSTPROCESS: COLLECT RESULTS ---
def extract_total_site_energy_gj(sql_path):
    """Extract Total Site Energy [GJ] from EnergyPlus SQL tabular data."""
    try:
        with sqlite3.connect(str(sql_path)) as conn:
            cur = conn.cursor()
            cur.execute(

                """
                SELECT Value
                FROM TabularDataWithStrings
                WHERE lower(ReportName) = 'annualbuildingutilityperformancesummary'

                  AND lower(TableName) = 'site and source energy'
                  AND lower(RowName) = 'total site energy'

                LIMIT 1
                """

            )
            row = cur.fetchone()
            if row and row[0] not in (None, ""):
                return float(row[0])

    except Exception as e:
        print(f"     Failed to read total site energy from SQL {sql_path}: {e}")

    return None

def get_prop_value(props, name):
    """Helper to safely extract value from AdditionalProperties by type."""
    if props.getFeatureAsDouble(name).is_initialized():
        return props.getFeatureAsDouble(name).get()

    if props.getFeatureAsString(name).is_initialized():
        return props.getFeatureAsString(name).get()

    if props.getFeatureAsInteger(name).is_initialized():
        return props.getFeatureAsInteger(name).get()

    return None

def _clean_text(raw):
    if raw is None:
        return None

    txt = str(raw).strip()
    if txt == "":
        return None

    if txt.lower() in {"nan", "null", "none", "not_applied", "not applied"}:
        return None

    return txt

def _safe_float(raw):
    try:
        if pd.isna(raw):
            return None

    except Exception:
        pass

    try:
        return float(raw)

    except Exception:
        return None

def extract_scenario_data(osm_path, scenario_name):
    """
    Loads an OSM and extracts target properties from AdditionalProperties.
    """
    results = {"scenario": scenario_name}
    vt = openstudio.osversion.VersionTranslator()
    model_ptr = vt.loadModel(openstudio.toPath(str(osm_path)))
    if not model_ptr.is_initialized():
        print(f"   Failed to load: {osm_path.name}")
        return None

    model = model_ptr.get()
    results["building_area_m2"] = model.getBuilding().floorArea()
    results["window_upgrade_status"] = None
    results.update(collect_window_inventory(model))
    if scenario_name.startswith("baseline"):
        results["renovation_details"] = "Baseline (no envelope renovation)"
    else:
        results["renovation_details"] = "Envelope renovation applied (details generated at report time)"

    found_any = True
    # 1) Embodied carbon from SimulationControl.additionalProperties().
    sim_props = model.getSimulationControl().additionalProperties()
    ec_keys = [
        "wall_insulation_embodied_carbon_kgCO2eq",
        "roof_insulation_embodied_carbon_kgCO2eq",
        "window_enhancement_embodied_carbon_kgCO2eq",
        "door_enhancement_embodied_carbon_kgCO2eq",
    ]
    for key in ec_keys:
        if key in sim_props.featureNames():
            val = get_prop_value(sim_props, key)
            if val is not None:
                results[key] = val
                found_any = True

    # Also capture embodied-carbon keys from all AdditionalProperties objects
    # (newer measures store keys such as *_embodied_carbon_kgCO2eq).
    idd_type = openstudio.IddObjectType("OS:AdditionalProperties")
    for obj in model.getObjectsByType(idd_type):
        opt_props = openstudio.model.toAdditionalProperties(obj)
        if not opt_props.is_initialized():
            continue
        props = opt_props.get()
        for fname in props.featureNames():
            lname = str(fname).lower()
            if "embodied_carbon" not in lname:
                continue
            val = get_prop_value(props, fname)
            if val is not None:
                results[fname] = val
                found_any = True

    # Convenience aggregate for analysis widgets.
    if "total_additional_embodied_carbon_kg" not in results:
        total_embodied = (
            float(results.get("wall_insulation_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            + float(results.get("roof_insulation_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            + float(results.get("window_enhancement_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            + float(results.get("door_enhancement_embodied_carbon_kgCO2eq", 0.0) or 0.0)
        )
        results["total_additional_embodied_carbon_kg"] = total_embodied

    # 2) Operating cost and emissions from Site.additionalProperties().
    site_props = model.getSite().additionalProperties()
    facility_props = model.getFacility().additionalProperties()
    sizing_props = model.getSizingParameters().additionalProperties()
    if "renovation_details" in site_props.featureNames():
        site_renovation_details = get_prop_value(site_props, "renovation_details")
        if site_renovation_details is not None:
            site_renovation_details = str(site_renovation_details).strip()
            if site_renovation_details and site_renovation_details.lower() not in {"nan", "none", "null"}:
                # OpenStudio may serialize punctuation as HTML entities in OSM strings.
                site_renovation_details = site_renovation_details.replace("&#59;", ";").replace("&#44;", ",")
                results["renovation_details"] = site_renovation_details
    op_keys = [
        "annual_electricity_cost_usd",
        "annual_gas_cost_usd",
        "annual_electricity_operating_emissions_kg_co2e",
        "annual_gas_operating_emissions_kg_co2e",
        "total_site_energy_gj",
    ]
    for key in op_keys:
        if key in site_props.featureNames():
            val = get_prop_value(site_props, key)
            if val is not None:
                results[key] = val
                found_any = True

    # 3. Construction cost fields (wall/roof/window/door)
    construction_cost_key_map = {
        "wall_insulation_material_cost_$": "wall_insulation_material_cost_usd",
        "wall_insulation_labor_cost_$": "wall_insulation_labor_cost_usd",
        "wall_insulation_overhead_profit_cost_$": "wall_insulation_overhead_profit_cost_usd",
        "wall_insulation_total_cost_with_overhead_and_profit_$": "wall_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_material_cost_$": "roof_insulation_material_cost_usd",
        "roof_insulation_labor_cost_$": "roof_insulation_labor_cost_usd",
        "roof_insulation_overhead_profit_cost_$": "roof_insulation_overhead_profit_cost_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_$": "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "window_enhancement_material_cost_$": "window_enhancement_material_cost_usd",
        "window_enhancement_labor_cost_$": "window_enhancement_labor_cost_usd",
        "window_enhancement_overhead_profit_cost_$": "window_enhancement_overhead_profit_cost_usd",
        "window_enhancement_total_cost_with_overhead_and_profit_$": "window_enhancement_total_cost_with_overhead_and_profit_usd",
        "door_enhancement_material_cost_$": "door_enhancement_material_cost_usd",
        "door_enhancement_labor_cost_$": "door_enhancement_labor_cost_usd",
        "door_enhancement_overhead_profit_cost_$": "door_enhancement_overhead_profit_cost_usd",
        "door_enhancement_total_cost_with_overhead_and_profit_$": "door_enhancement_total_cost_with_overhead_and_profit_usd",
    }
    for src_props in [sim_props, facility_props]:
        for raw_key, norm_key in construction_cost_key_map.items():
            if norm_key in results:
                continue
            if raw_key in src_props.featureNames():
                val = get_prop_value(src_props, raw_key)
                if val is not None:
                    results[norm_key] = val
                    found_any = True

    explicit_material_keys = [
        "wall_insulation_material_lifetime_years",
        "wall_insulation_material_density_kg_per_m3",
        "wall_insulation_material_thermal_conductivity_W_per_mK",
        "wall_insulation_custom_labor_cost_multiplier",
        "wall_insulation_custom_cost_per_cf",
        "roof_insulation_material_lifetime_years",
        "roof_insulation_material_density_kg_per_m3",
        "roof_insulation_material_thermal_conductivity_W_per_mK",
        "roof_insulation_custom_labor_cost_multiplier",
        "roof_insulation_custom_cost_per_cf",
        "window_glass_lifetime_years",
        "window_frame_lifetime_years",
        "window_caulking_lifetime_years",
        "window_film_lifetime_years",
        "window_weatherstrip_lifetime_years",
        "window_enhancement_custom_labor_cost_multiplier",
        "window_custom_glass_cost_per_cf",
        "window_custom_frame_cost_per_sf",
        "window_custom_caulking_cost_per_cy",
        "window_custom_film_cost_per_sf",
        "window_custom_weatherstrip_cost_per_lf",
        "door_strip_lifetime_years",
        "door_lifetime_years",
        "door_density_kg_per_m3",
        "door_conductivity_W_per_mK",
        "door_enhancement_custom_labor_cost_multiplier",
        "door_enhancement_custom_door_cost_per_area",
        "door_enhancement_custom_bottom_seal_cost_per_m",
        "door_enhancement_custom_top_side_seal_cost_per_m",
    ]
    all_ap_sources = [
        model.getBuilding().additionalProperties(),
        site_props,
        facility_props,
        sim_props,
        sizing_props,
    ]
    idd_type = openstudio.IddObjectType("OS:AdditionalProperties")
    for obj in model.getObjectsByType(idd_type):
        opt_props = openstudio.model.toAdditionalProperties(obj)
        if opt_props.is_initialized():
            all_ap_sources.append(opt_props.get())

    for src_props in all_ap_sources:
        for key in explicit_material_keys:
            if key in results:
                continue
            if key in src_props.featureNames():
                val = get_prop_value(src_props, key)
                if val is not None:
                    results[key] = val
                    found_any = True

    # Capture any remaining AdditionalProperties keys so new measure outputs
    # are automatically included in CSV without manual allowlist updates.
    for src_props in all_ap_sources:
        for key in src_props.featureNames():
            if key in results:
                continue
            val = get_prop_value(src_props, key)
            if val is not None:
                results[key] = val
                found_any = True

    # Prefer already-computed measure totals when available.
    # If missing, fall back to component sums.
    wall_total = float(results.get("wall_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    roof_total = float(results.get("roof_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    if wall_total <= 0.0:
        wall_total = (
            float(results.get("wall_insulation_material_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_labor_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_overhead_profit_cost_usd", 0.0) or 0.0)
        )
    if roof_total <= 0.0:
        roof_total = (
            float(results.get("roof_insulation_material_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_labor_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_overhead_profit_cost_usd", 0.0) or 0.0)
        )

    window_total = (
        float(results.get("window_enhancement_material_cost_usd", 0.0) or 0.0)
        + float(results.get("window_enhancement_labor_cost_usd", 0.0) or 0.0)
        + float(results.get("window_enhancement_overhead_profit_cost_usd", 0.0) or 0.0)
    )
    door_total = (
        float(results.get("door_enhancement_material_cost_usd", 0.0) or 0.0)
        + float(results.get("door_enhancement_labor_cost_usd", 0.0) or 0.0)
        + float(results.get("door_enhancement_overhead_profit_cost_usd", 0.0) or 0.0)
    )
    results["total_additional_construction_cost_usd"] = wall_total + roof_total + window_total + door_total
    results["total_construction_cost_usd"] = results["total_additional_construction_cost_usd"]
    # Total site energy (GJ): prefer Site AdditionalProperties; fallback to SQL tabular data
    site_energy_keys = ["total_site_energy_GJ", "total_site_energy_gj"]
    for key in site_energy_keys:
        if key in site_props.featureNames():
            val = get_prop_value(site_props, key)
            if val is not None:
                results["total_site_energy_gj"] = val
                found_any = True
                break

    if "total_site_energy_gj" not in results:
        sql_path = osm_path.parent / "eplusout.sql"
        if sql_path.exists():
            total_site_energy = extract_total_site_energy_gj(sql_path)
            if total_site_energy is not None:
                results["total_site_energy_gj"] = total_site_energy
                found_any = True

    # Explicit reno detail keys written by envelope measures
    reno_keys = [
        "wall_insulation_renovated_area_m2",
        "wall_insulation_added_volume_m3",
        "roof_insulation_renovated_area_m2",
        "roof_insulation_added_volume_m3",
        "wall_insulation_material_thermal_conductivity_W_per_mK",
        "wall_insulation_material_density_kg_per_m3",
        "window_enhancement_retrofit_materials_json",
        "window_total_count",
        "window_fixed_count",
        "window_operable_count",
        "window_skylight_count",
        "window_simple_glazing_count",
        "window_upgrade_status",
        "window_enhancement_infiltration_reduction_percent",
        "window_glass_pane_thickness_m",
        "window_glass_gap_thickness_m",
        "window_enhancement_renovated_area_m2",
        "window_enhancement_renovated_glazing_area_m2",
        "window_enhancement_renovated_frame_area_m2",
        "window_enhancement_renovated_perimeter_m",
        "window_enhancement_renovated_caulking_volume_m3",
        "window_enhancement_renovated_weatherstrip_length_m",
        "window_weatherstrip_length_per_unit",
        "door_sealing_bottom_length_m",
        "door_sealing_side_length_m",
        "door_enhancement_renovated_area_m2",
    ]
    for key in reno_keys:
        if key in site_props.featureNames():
            val = get_prop_value(site_props, key)
            if val is not None:
                results[key] = val
                found_any = True

    return results if found_any else None

def generate_parametric_recap(target_path, city_climate_zones=None):
    """
    Main function to run the extraction and generate parametric_results.csv
    """
    root_path = Path(target_path)
    if not root_path.exists():
        print(f"Error: Path '{target_path}' does not exist.")
        return

    all_data = []
    all_headers = set()
    print("=" * 80)
    print(f"GENERATING PARAMETRIC RECAP FROM: {root_path}")
    print("=" * 80)
    scenario_dirs = [p for p in sorted(root_path.iterdir()) if p.is_dir()]
    for scenario_dir in scenario_dirs:
        scenario = scenario_dir.name
        primary_osm = scenario_dir / "run" / "in.osm"
        secondary_osm = scenario_dir / "run" / "in_modified.osm"
        if primary_osm.exists():
            osm_path = primary_osm
        elif secondary_osm.exists():
            osm_path = secondary_osm
        else:
            continue

        data = extract_scenario_data(osm_path, scenario)
        if data is None:
            data = {"scenario": scenario}
        if "renovation_details" not in data or not str(data.get("renovation_details", "")).strip():
            if str(scenario).startswith("baseline"):
                data["renovation_details"] = "Baseline (no envelope renovation)"
            else:
                data["renovation_details"] = "Envelope renovation applied (details generated at report time)"
        if data:
            s_parts = scenario.split("_")
            data["city"] = s_parts[-1]
            data["building_type"] = s_parts[-2]
            data["climate_zone"] = city_climate_zones.get(s_parts[-1], "") if city_climate_zones else ""
            all_data.append(data)
            all_headers.update(data.keys())

    if not all_data:
        print("\n No matching data found.")
        return

    fixed_headers = [
        "scenario",
        "city",
        "building_type",
        "climate_zone",
        "building_area_m2",
        "renovation_details",
        "annual_electricity_cost_usd",
        "annual_gas_cost_usd",
        "annual_electricity_operating_emissions_kg_co2e",
        "annual_gas_operating_emissions_kg_co2e",
        "total_site_energy_gj",
        "wall_insulation_renovated_area_m2",
        "wall_insulation_added_volume_m3",
        "roof_insulation_renovated_area_m2",
        "roof_insulation_added_volume_m3",
        "wall_insulation_material_thermal_conductivity_W_per_mK",
        "wall_insulation_material_density_kg_per_m3",
        "wall_insulation_material_lifetime_years",
        "roof_insulation_material_thermal_conductivity_W_per_mK",
        "roof_insulation_material_density_kg_per_m3",
        "roof_insulation_material_lifetime_years",
        "window_enhancement_retrofit_materials_json",
        "window_total_count",
        "window_fixed_count",
        "window_operable_count",
        "window_skylight_count",
        "window_simple_glazing_count",
        "window_upgrade_status",
        "window_enhancement_infiltration_reduction_percent",
        "window_glass_pane_thickness_m",
        "window_glass_gap_thickness_m",
        "window_enhancement_renovated_area_m2",
        "window_enhancement_renovated_glazing_area_m2",
        "window_enhancement_renovated_frame_area_m2",
        "window_enhancement_renovated_perimeter_m",
        "window_enhancement_renovated_caulking_volume_m3",
        "window_enhancement_renovated_weatherstrip_length_m",
        "window_weatherstrip_length_per_unit",
        "window_glass_lifetime_years",
        "window_frame_lifetime_years",
        "window_caulking_lifetime_years",
        "window_film_lifetime_years",
        "window_weatherstrip_lifetime_years",
        "window_enhancement_custom_labor_cost_multiplier",
        "window_custom_glass_cost_per_cf",
        "window_custom_frame_cost_per_sf",
        "window_custom_caulking_cost_per_cy",
        "window_custom_film_cost_per_sf",
        "window_custom_weatherstrip_cost_per_lf",
        "door_strip_lifetime_years",
        "door_lifetime_years",
        "door_density_kg_per_m3",
        "door_conductivity_W_per_mK",
        "door_sealing_bottom_length_m",
        "door_sealing_side_length_m",
        "door_enhancement_renovated_area_m2",
        "door_enhancement_custom_labor_cost_multiplier",
        "door_enhancement_custom_door_cost_per_area",
        "door_enhancement_custom_bottom_seal_cost_per_m",
        "door_enhancement_custom_top_side_seal_cost_per_m",
        "wall_insulation_embodied_carbon_kgCO2eq",
        "roof_insulation_embodied_carbon_kgCO2eq",
        "window_enhancement_embodied_carbon_kgCO2eq",
        "door_enhancement_embodied_carbon_kgCO2eq",
        "wall_insulation_custom_labor_cost_multiplier",
        "wall_insulation_custom_cost_per_cf",
        "roof_insulation_custom_labor_cost_multiplier",
        "roof_insulation_custom_cost_per_cf",
        "wall_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "window_enhancement_total_cost_with_overhead_and_profit_usd",
        "door_enhancement_total_cost_with_overhead_and_profit_usd",
        "wall_insulation_material_cost_usd",
        "wall_insulation_labor_cost_usd",
        "wall_insulation_overhead_profit_cost_usd",
        "roof_insulation_material_cost_usd",
        "roof_insulation_labor_cost_usd",
        "roof_insulation_overhead_profit_cost_usd",
        "window_enhancement_material_cost_usd",
        "window_enhancement_labor_cost_usd",
        "window_enhancement_overhead_profit_cost_usd",
        "door_enhancement_material_cost_usd",
        "door_enhancement_labor_cost_usd",
        "door_enhancement_overhead_profit_cost_usd",
        "total_additional_construction_cost_usd",
        "total_construction_cost_usd",
    ]
    extra_headers = sorted([h for h in all_headers if h not in fixed_headers and h != "scenario"])
    fieldnames = [h for h in fixed_headers if h in all_headers | {"scenario"}] + extra_headers
    desired_scenarios = [
        generate_scenario_name(s)
        for s in generate_scenarios(cities=CITIES, building_types=BUILDING_TYPES, custom_combos=CUSTOM_COMBOS)
    ]
    scenario_order = {name: idx for idx, name in enumerate(desired_scenarios)}
    all_data = sorted(
        all_data,
        key=lambda row: (scenario_order.get(str(row.get("scenario", "")), len(scenario_order)), str(row.get("scenario", ""))),
    )
    csv_path = root_path / "parametric_results.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        original_rows = [fieldnames]
        original_rows.extend([[row.get(field, "") for field in fieldnames] for row in all_data])
        transposed_rows = zip_longest(*original_rows, fillvalue="")
        writer.writerows(transposed_rows)

    print("\n" + "=" * 80)
    print(f"COMPLETE: {len(all_data)} scenarios successfully processed.")
    print(f"Report saved to: {csv_path}")
    print("=" * 80)

# --- GLOBAL SETTINGS ---
RUN_NAME = "run_test_008"
def detect_openstudio_cli_path():
    candidates = [os.environ.get("OPENSTUDIO_PATH"), shutil.which("openstudio")]

    # Windows fallback: scan common install roots for openstudio-*/bin/openstudio.exe.
    if os.name == "nt":
        for root in [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]:
            if not root:
                continue
            candidates.extend(str(p) for p in sorted(Path(root).glob("openstudio-*/bin/openstudio.exe"), reverse=True))

    # macOS fallback: scan /Applications/OpenStudio-*/bin/openstudio.
    if sys.platform == "darwin":
        candidates.extend(str(p) for p in sorted(Path("/Applications").glob("OpenStudio-*/bin/openstudio"), reverse=True))

    return _resolve_existing_path(candidates)

OPENSTUDIO_PATH = detect_openstudio_cli_path()
OVERWRITE_EXISTING = False

notebook_dir = Path(__file__).parent
base_weather_path = str(notebook_dir / "weather")
measure_dir_path = str(notebook_dir.parent / "measures")
base_run_dir = str(notebook_dir / "simulations" / RUN_NAME)
city_climate_zones = {
    # "Amarillo":     "ASHRAE 169-2013-3B",
    # "Atlanta":      "ASHRAE 169-2013-3A",
    # "Baltimore":    "ASHRAE 169-2013-4A",
    # "Chicago":      "ASHRAE 169-2013-5A",
    # "Denver":       "ASHRAE 169-2013-5B",
    "Duluth":       "ASHRAE 169-2013-7A", 
    # "ElPaso":       "ASHRAE 169-2013-3B",
    # "Fairbanks":    "ASHRAE 169-2013-8A",
    # "Helena":       "ASHRAE 169-2013-6B",
    # "Houston":      "ASHRAE 169-2013-2A",
    # "Miami":        "ASHRAE 169-2013-1A",
    # "Minneapolis":  "ASHRAE 169-2013-6A",
    # "Phoenix":      "ASHRAE 169-2013-2B",
    # "PortAngeles":  "ASHRAE 169-2013-4C",
    # "Portland":     "ASHRAE 169-2013-4C",
    # "SanFrancisco": "ASHRAE 169-2013-3C",
}

# --- PARAMETRIC STUDY CONFIGURATION ---
CITIES = list(city_climate_zones.keys())
BUILDING_TYPES = [
    "SmallOffice",
    # "MediumOffice",
    # "LargeOffice",
    # "SmallHotel",
    # "LargeHotel",
    # "Warehouse",
    # "RetailStandalone",
    # "RetailStripmall",
    # "PrimarySchool",
    # "SecondarySchool",
]

TEMPLATE = "90.1-2010"

# --- CUSTOM COMBINATION SCENARIOS ---
# Supported optional keys in each combo:
# - window_infiltration_reduction_percent, door_infiltration_reduction_percent
# - weatherstrip_option, wf_option, film_option, caulking_option, secondary_glazing_option
# - door_bottom_seal_option, door_top_side_seal_option
# - wall_insulation_material_type, wall_insulation_material_lifetime
# - roof_insulation_material_type, roof_insulation_material_lifetime

CUSTOM_COMBOS = [
    # Scenario 1: Wall + Roof
    # {
    #     "wall_r_value":    10,
    #     "wall_insulation_material_type": "Fiberglass Batts",
    #     "roof_r_value":    20,
    #     "roof_insulation_material_type": "Blown Fiberglass",
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # # Scenario 2: Wall + Roof
    # {
    #     "wall_r_value":    13,
    #     "wall_insulation_material_type": "Fiberglass Batts",
    #     "roof_r_value":    24.4,
    #     "roof_insulation_material_type": "Blown Fiberglass",
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # # Scenario 3: Wall + Roof
    # {
    #     "wall_r_value":    13,
    #     "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    #     "roof_r_value":    24.4,
    #     "roof_insulation_material_type": "Extruded Polystyrene (XPS) Foam Board",
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # # Scenario 4: Wall + Roof
    # {
    #     "wall_r_value":    20,
    #     "wall_insulation_material_type": "Fiberglass Batts",
    #     "roof_r_value":    30,
    #     "roof_insulation_material_type": "Blown Fiberglass",
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # # Scenario 5: Wall only, EPS foam board
    # {
    #     "wall_r_value":    30,
    #     "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    #     "roof_r_value":    None,
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # # Scenario 6: Roof only
    # {
    #     "wall_r_value":    None,
    #     "roof_r_value":    30,
    #     "roof_insulation_material_type": "Blown Fiberglass",
    #     "window_num_panes": None,
    #     "door_option":     None,
    # },
    # Scenario 7: All 4 measures  Wall + Door + Roof + Window
    {
        "wall_r_value":    10,
        "wall_insulation_material_type": "Extruded Polystyrene (XPS) Foam Board",
        "roof_r_value":    15,
        "roof_insulation_material_type": "Blown Mineral Wool",
        "door_option":     "glass door",
        "door_infiltration_reduction_percent": 20.0,
        "door_bottom_seal_option": "none",
        "door_top_side_seal_option": "none",
        "window_num_panes": 1,
        "window_infiltration_reduction_percent": 20.0,
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "wf_option": "none",
        "film_option": "safety film",
        "caulking_option": "none",
    },
    # Scenario 8: All 4 measures  Wall + Door + Roof + Window
    {
        "wall_r_value":    30,
        "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
        "roof_r_value":    25,
        "roof_insulation_material_type": "Polyiso Insulation Foam Board",
        "door_option":     "polystyrene core steel door",
        "door_infiltration_reduction_percent": 25.0,
        "door_bottom_seal_option": "brush weatherstrip",
        "door_top_side_seal_option": "silicone adhesive smoke gasket",
        "window_num_panes": 2,
        "window_infiltration_reduction_percent": 25.0,
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "wf_option": "none",
        "film_option": "anti-graffiti film",
        "caulking_option": "polyurethane",
    },
    #Scenario 9: All 4 measures  Wall + Door + Roof + Window
    {
        "wall_r_value":    20.4,
        "wall_insulation_material_type": "Fiberglass Batts",
        "roof_r_value":    34.5,
        "roof_insulation_material_type": "Blown Fiberglass",
        "door_option":     "wooden door",
        "door_infiltration_reduction_percent": 30.0,
        "door_bottom_seal_option": "automatic door bottom",
        "door_top_side_seal_option": "jamb weatherstrip",
        "window_num_panes": 3,
        "window_enhancement_infiltration_reduction_percent": 30.0,
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "wf_option": "none",
        "film_option": "low-e film",
        "caulking_option": "acrylic",
    },
]

def scenario_output_exists(base_run_dir, scenario_dict):
    scenario_name = generate_scenario_name(scenario_dict)
    sql_path = os.path.join(base_run_dir, scenario_name, "run", "eplusout.sql")
    return os.path.exists(sql_path)

# --- MAIN - RUN PARAMETRIC STUDY ---
if __name__ == "__main__":
    if not OPENSTUDIO_PATH:
        raise RuntimeError(
            "OpenStudio CLI not found. Set OPENSTUDIO_PATH to your openstudio executable, "
            "or add openstudio to PATH."
        )

    print("\n" + "=" * 70)
    print("PARAMETRIC STUDY: BUILDING ENERGY EFFICIENCY MEASURES")
    print(f"Using OpenStudio: {OPENSTUDIO_PATH}")
    print(f"Run Name: {RUN_NAME}")
    print(f"Output Directory: {base_run_dir}")
    print("=" * 70)
    print("\n Generating scenarios...")
    scenarios = generate_scenarios(
        cities=CITIES,
        building_types=BUILDING_TYPES,
        custom_combos=CUSTOM_COMBOS,
    )
    total_sims = len(scenarios)
    baseline_count = sum(1 for s in scenarios if s["is_baseline"])
    individual_wall = sum(1 for s in scenarios if not s["is_baseline"] and s["wall_r_value"] and not s["roof_r_value"] and not s["window_num_panes"] and not s["door_option"])
    individual_roof = sum(1 for s in scenarios if not s["is_baseline"] and s["roof_r_value"] and not s["wall_r_value"] and not s["window_num_panes"] and not s["door_option"])
    individual_window = sum(1 for s in scenarios if not s["is_baseline"] and s["window_num_panes"] and not s["wall_r_value"] and not s["roof_r_value"] and not s["door_option"])
    individual_door = sum(1 for s in scenarios if not s["is_baseline"] and s["door_option"] and not s["wall_r_value"] and not s["roof_r_value"] and not s["window_num_panes"])
    all_measures = sum(1 for s in scenarios if not s["is_baseline"] and sum([bool(s["wall_r_value"]), bool(s["roof_r_value"]), bool(s["window_num_panes"]), bool(s["door_option"])]) > 1)
    print(f"\n Total scenarios: {total_sims}")
    print(f"   - Cities: {len(CITIES)}")
    print(f"   - Building Types: {len(BUILDING_TYPES)}")
    print(f"\n   Breakdown:")
    print(f"   - Baseline: {baseline_count}")
    print(f"   - Wall only: {individual_wall}")
    print(f"   - Roof only: {individual_roof}")
    print(f"   - Window only: {individual_window}")
    print(f"   - Door only: {individual_door}")
    print(f"   - Combined (2 measures): {all_measures}")
    print("=" * 70)
    sim_count = 0
    start_time = time.time()
    successful_scenarios = []
    failed_scenarios = []
    all_selected_have_results = all(scenario_output_exists(base_run_dir, s) for s in scenarios)
    skip_simulation_run = all_selected_have_results and CUSTOM_COMBOS and not OVERWRITE_EXISTING
    if skip_simulation_run:
        print("\n  Existing simulation outputs detected for selected scenarios.")
        print("   Skipping simulation run and regenerating CSV only.")
        successful_scenarios = [generate_scenario_name(s) for s in scenarios]

    else:
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
                failure_log_path = os.path.join(base_run_dir, scenario_name, "scenario_failure.log")
                try:
                    os.makedirs(os.path.dirname(failure_log_path), exist_ok=True)
                    if not os.path.exists(failure_log_path) or os.path.getsize(failure_log_path) == 0:
                        with open(failure_log_path, "a", encoding="utf-8") as f:
                            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] scenario failed in main loop (no detailed reason captured)\n")
                except Exception as log_err:
                    print(f"     failed to write failure log for {scenario_name}: {log_err}")

            sim_elapsed = time.time() - sim_start
            print(f"     Time: {sim_elapsed/60:.1f} min")

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print("SIMULATION SUMMARY")
    print("=" * 70)
    print(f"     Total time: {total_elapsed/60:.1f} min ({total_elapsed/3600:.2f} hours)")
    print(f"    Successful: {len(successful_scenarios)}/{total_sims}")
    print(f"    Failed: {len(failed_scenarios)}/{total_sims}")
    if failed_scenarios:
        print("\nFailed scenarios:")
        for failed in failed_scenarios:
            print(f"  - {failed}")

    # Collect results
    print("\n" + "=" * 70)
    print("COLLECTING RESULTS FROM OSM FILES")
    print("=" * 70)
    generate_parametric_recap(base_run_dir, city_climate_zones)
    print("\n Parametric study complete!")

# --- Interactive Spider Chart + Summary Table ---
# Spider chart for parametric_results.csv (4 scenarios)
from pathlib import Path
import textwrap
import pandas as pd
import plotly.graph_objects as go

base_dir = Path(base_run_dir)
def _find_or_build_parametric_csv(base_dir):
    csv_path = base_dir / "parametric_results.csv"
    if csv_path.exists():
        return csv_path
    print("Warning: parametric_results.csv not found; attempting to regenerate recap CSV.")
    generate_parametric_recap(base_dir, city_climate_zones)
    return csv_path if csv_path.exists() else None


csv_candidates = [base_dir / "parametric_results.csv"]
csv_path = _find_or_build_parametric_csv(base_dir)

if csv_path is None:
    print(f"Warning: Could not find CSV in: {csv_candidates}")
    print("Skipping spider chart and summary table generation.")
    if __name__ == "__main__":
        raise SystemExit(0)
    raise FileNotFoundError(f"Could not find CSV in: {csv_candidates}")

df = pd.read_csv(csv_path, header=None, dtype=str)
# parametric_results.csv is written in transposed form (fields as rows, scenarios as columns).
# Restore the conventional orientation: scenarios as rows, fields as columns.
if not df.empty and str(df.iloc[0, 0]).strip().lower() == "scenario":
    df = df.T
    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)
    df.columns.name = None
baseline_first_mask = df["scenario"].astype(str).str.contains("baseline", case=False, na=False)
df = pd.concat([df[baseline_first_mask], df[~baseline_first_mask]], ignore_index=True)
scenario_values = df["scenario"].astype(str).tolist()
scenario_display_map = {}
scenario_counter = 1
for name in scenario_values:
    if "baseline" in str(name).lower():
        scenario_display_map[name] = "Baseline"
    elif name not in scenario_display_map:
        scenario_display_map[name] = f"Scenario {scenario_counter}"
        scenario_counter += 1

construction_cost_cols = [
    "total_construction_cost_usd",
    "total_additional_construction_cost_usd",
    "construction_cost_usd",
    "additional_construction_cost_usd",
]
available_construction_cost_col = next((c for c in construction_cost_cols if c in df.columns), None)

required_base_cols = [
    "scenario",
    "annual_electricity_operating_emissions_kg_co2e",
    "annual_gas_operating_emissions_kg_co2e",
    "annual_electricity_cost_usd",
    "annual_gas_cost_usd",
]
expected_embodied_cols = [
    "window_enhancement_embodied_carbon_kgCO2eq",
    "door_enhancement_embodied_carbon_kgCO2eq",
    "wall_insulation_embodied_carbon_kgCO2eq",
    "roof_insulation_embodied_carbon_kgCO2eq",
]

missing_required = [c for c in required_base_cols if c not in df.columns]
if missing_required:
    raise ValueError(f"Missing required columns: {missing_required}")

for col in expected_embodied_cols:
    if col not in df.columns:
        df[col] = 0.0
        print(f"Warning: missing optional column '{col}', filled with 0.0")

numeric_cols = [c for c in required_base_cols if c != "scenario"] + expected_embodied_cols
df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

df["total_additional_embodied_carbon_kg"] = (
    df["window_enhancement_embodied_carbon_kgCO2eq"]
    + df["door_enhancement_embodied_carbon_kgCO2eq"]
    + df["wall_insulation_embodied_carbon_kgCO2eq"]
    + df["roof_insulation_embodied_carbon_kgCO2eq"]
)
df["annual_operational_carbon_kg_co2e"] = (
    df["annual_electricity_operating_emissions_kg_co2e"]
    + df["annual_gas_operating_emissions_kg_co2e"]
)
df["annual_operational_cost_usd"] = (
    df["annual_electricity_cost_usd"]
    + df["annual_gas_cost_usd"]
)

if available_construction_cost_col:
    df["total_construction_cost_usd"] = pd.to_numeric(df[available_construction_cost_col], errors="coerce").fillna(0.0)
else:
    df["total_construction_cost_usd"] = 0.0

# Calculate payback periods relative to baseline
baseline_mask = df["scenario"].astype(str).str.contains("baseline", case=False, na=False)
if baseline_mask.any():
    baseline_row = df[baseline_mask].iloc[0]
    baseline_annual_cost = baseline_row["annual_operational_cost_usd"]
    baseline_annual_emissions = baseline_row["annual_operational_carbon_kg_co2e"]
    # Calculate cost and carbon deltas for all scenarios
    df["cost_delta"] = baseline_annual_cost - df["annual_operational_cost_usd"]
    df["emissions_delta"] = baseline_annual_emissions - df["annual_operational_carbon_kg_co2e"]
    # Function to safely calculate payback
    def safe_payback(total_value, annual_saving):
        if pd.isna(total_value) or pd.isna(annual_saving):
            return None
        total_value = float(total_value)
        annual_saving = float(annual_saving)
        if total_value <= 0 or annual_saving <= 0:
            return None
        return total_value / annual_saving

    if available_construction_cost_col:
        df["cost_payback_period_years"] = df.apply(lambda r: safe_payback(r[available_construction_cost_col], r["cost_delta"]), axis=1)
    else:
        df["cost_payback_period_years"] = None

    df["carbon_payback_period_years"] = df.apply(lambda r: safe_payback(r["total_additional_embodied_carbon_kg"], r["emissions_delta"]), axis=1)
else:
    df["cost_payback_period_years"] = None
    df["carbon_payback_period_years"] = None

metrics = [
    "total_additional_embodied_carbon_kg",
    "annual_operational_carbon_kg_co2e",
    "annual_operational_cost_usd",
    "total_construction_cost_usd",
    "cost_payback_period_years",
    "carbon_payback_period_years",
]

metric_labels = {
    "total_additional_embodied_carbon_kg": "Retrofit Embodied Carbon (kgCO2e)",
    "annual_operational_carbon_kg_co2e": "Annual Operational Carbon (kgCO2e)",
    "annual_operational_cost_usd": "Annual Operational Cost (USD)",
    "total_construction_cost_usd": "Retrofit Construction Cost (USD)",
    "cost_payback_period_years": "Cost Payback Period (years)",
    "carbon_payback_period_years": "Carbon Payback Period (years)",
}

def wrap_label(text, width=22):
    parts = textwrap.wrap(str(text), width=width)
    return "<br>".join(parts) if parts else str(text)

theta_raw = [metric_labels[m] for m in metrics]
theta = [wrap_label(label, width=22) for label in theta_raw]
max_vals = df[metrics].max().replace(0, 1.0)

fig = go.Figure()

def _format_hover_value(v):
    val = float(v)
    if abs(val) >= 10:
        return f"{val:,.0f}"
    return f"{val:,.2f}"

for _, row in df.iterrows():
    raw_vals = [float(row[m]) if pd.notna(row[m]) else 0 for m in metrics]
    norm_vals = [(float(row[m]) / float(max_vals[m])) if pd.notna(row[m]) and max_vals[m] > 0 else 0 for m in metrics]
    formatted_vals = [_format_hover_value(v) for v in raw_vals]
    formatted_norm_vals = [_format_hover_value(v) for v in norm_vals]
    fig.add_trace(
        go.Scatterpolar(
            theta=theta + [theta[0]],
            r=norm_vals + [norm_vals[0]],
            customdata=formatted_norm_vals + [formatted_norm_vals[0]],
            text=formatted_vals + [formatted_vals[0]],
            name=scenario_display_map.get(str(row["scenario"]), str(row["scenario"])),
            hovertemplate="<b>%{theta}</b><br>Normalized: %{customdata}<br>Value: %{text}<extra>%{fullData.name}</extra>",
        )
    )

fig.update_layout(
    title="Parametric Scenario Comparison (Normalized Spider Chart)",
    polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
    showlegend=True,
)

# Use inline Plotly JS so the report is self-contained and works offline.
spider_chart_html = fig.to_html(include_plotlyjs=True, full_html=False)
print("Interactive spider chart and summary table are displayed below.")

# Inline render right after running the cell (avoids plotly mime renderer dependency)

# Results table matching spider chart metrics
table_df = df[["scenario"] + metrics].rename(columns=metric_labels)
table_df["scenario"] = table_df["scenario"].astype(str).map(lambda s: scenario_display_map.get(s, s))
table_df = table_df.round(2)

# --- Report Builder Imports ---
from report_template import (
    build_report_html,
    build_material_list_row_html,
    component_from_entry,
    extract_material_type_name,
    material_metrics_from_entry,
    parse_materials_payload,
)

# --- Report Generation Helpers ---
from pathlib import Path

from datetime import datetime

import pandas as pd

def _to_num(df, col):
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return pd.Series([0.0] * len(df), index=df.index)

def generate_html_report(df, html_report_path, run_name="run"):
    scenario_col = "scenario" if "scenario" in df.columns else "scenario_name"
    if scenario_col not in df.columns:
        raise ValueError("CSV must include 'scenario' or 'scenario_name' column.")

    baseline_first_mask = df[scenario_col].astype(str).str.contains("baseline", case=False, na=False)
    df = pd.concat([df[baseline_first_mask], df[~baseline_first_mask]], ignore_index=True)
    scenario_values = df[scenario_col].astype(str).tolist()
    scenario_display_map = {}
    scenario_counter = 1
    for name in scenario_values:
        if "baseline" in str(name).lower():
            scenario_display_map[name] = "Baseline"

        elif name not in scenario_display_map:
            scenario_display_map[name] = f"Scenario {scenario_counter}"
            scenario_counter += 1

    elec_cost = _to_num(df, "annual_electricity_cost_usd")
    gas_cost = _to_num(df, "annual_gas_cost_usd")
    annual_operational_cost = elec_cost + gas_cost
    elec_emis = _to_num(df, "annual_electricity_operating_emissions_kg_co2e")
    gas_emis = _to_num(df, "annual_gas_operating_emissions_kg_co2e")
    annual_operational_carbon = elec_emis + gas_emis
    site_energy = _to_num(df, "total_site_energy_gj")
    analysis_period_col_candidates = ["analysis_period", "wall_analysis_period", "window_analysis_period", "roof_analysis_period", "door_analysis_period", "analysis_period_years", "analysis_period_yrs"]
    available_analysis_period_col = next((c for c in analysis_period_col_candidates if c in df.columns), None)
    default_embodied_analysis_period_years = 30.0
    if available_analysis_period_col:
        raw_analysis_period = pd.to_numeric(df[available_analysis_period_col], errors="coerce")
        valid_periods = raw_analysis_period[raw_analysis_period > 0]
        if not valid_periods.empty:
            default_embodied_analysis_period_years = float(valid_periods.iloc[0])

        analysis_period_years = raw_analysis_period.where(raw_analysis_period > 0, default_embodied_analysis_period_years).fillna(default_embodied_analysis_period_years)

    else:
        analysis_period_years = pd.Series([default_embodied_analysis_period_years] * len(df), index=df.index)

    wall_ec = _to_num(df, "wall_insulation_embodied_carbon_kgCO2eq")
    roof_ec = _to_num(df, "roof_insulation_embodied_carbon_kgCO2eq")
    window_ec = _to_num(df, "window_enhancement_embodied_carbon_kgCO2eq")
    door_ec = _to_num(df, "door_enhancement_embodied_carbon_kgCO2eq")
    report = pd.DataFrame({

        "scenario": df[scenario_col].astype(str),
        "annual_cost_usd": elec_cost + gas_cost,
        "annual_emissions_kg": elec_emis + gas_emis,
        "total_site_energy_gj": site_energy,
        "analysis_period_years": analysis_period_years,
        "wall_ec": wall_ec,
        "roof_ec": roof_ec,
        "window_ec": window_ec,
        "door_ec": door_ec,

    })
    report["embodied_carbon_kg"] = report[["wall_ec", "roof_ec", "window_ec", "door_ec"]].sum(axis=1)
    floor_area_col_candidates = [

        "building_area_m2",
        "total_floor_area_m2",
        "floor_area_m2",
        "building_floor_area_m2",

    ]
    building_area_m2 = None
    for area_col in floor_area_col_candidates:
        if area_col in df.columns:
            area_series = pd.to_numeric(df[area_col], errors="coerce")
            area_series = area_series[area_series > 0]
            if not area_series.empty:
                building_area_m2 = float(area_series.iloc[0])
                break

    baseline_mask = report["scenario"].str.contains("baseline", case=False, na=False)
    baseline = report[baseline_mask].head(1)
    if baseline.empty:
        baseline = report.head(1)

    b = baseline.iloc[0]
    embodied_analysis_period_years = max(float(default_embodied_analysis_period_years), 1.0)
    comparison_df = report[~baseline_mask].copy()
    lowest_cost_payback_text = "N/A"
    lowest_cost_payback_scenario = "No valid cost payback scenario"
    lowest_carbon_payback_text = "N/A"
    lowest_carbon_payback_scenario = "No valid carbon payback scenario"
    if comparison_df.empty:
        comparison_df = report.head(0).copy()

    comparison_df["cost_delta"] = comparison_df["annual_cost_usd"] - b["annual_cost_usd"]
    comparison_df["cost_delta_pct"] = comparison_df["cost_delta"] / b["annual_cost_usd"] * 100.0 if b["annual_cost_usd"] > 0 else 0.0
    comparison_df["emissions_delta"] = comparison_df["annual_emissions_kg"] - b["annual_emissions_kg"]
    comparison_df["emissions_delta_pct"] = comparison_df["emissions_delta"] / b["annual_emissions_kg"] * 100.0 if b["annual_emissions_kg"] > 0 else 0.0
    if comparison_df.empty:
        max_savings = b
        max_emissions_reduction = b
        max_savings_scenario = "No renovation scenarios"
        max_emissions_scenario = "No renovation scenarios"
        max_cost_delta = 0.0
        max_cost_delta_pct = 0.0
        max_emis_delta = 0.0
        max_emis_delta_pct = 0.0

    else:
        max_savings = comparison_df.loc[comparison_df["cost_delta"].idxmin()]
        max_emissions_reduction = comparison_df.loc[comparison_df["emissions_delta"].idxmin()]
        max_savings_scenario = scenario_display_map.get(str(max_savings["scenario"]), str(max_savings["scenario"]))
        max_emissions_scenario = scenario_display_map.get(str(max_emissions_reduction["scenario"]), str(max_emissions_reduction["scenario"]))
        max_cost_delta = float(max_savings["cost_delta"])
        max_cost_delta_pct = float(max_savings["cost_delta_pct"])
        max_emis_delta = float(max_emissions_reduction["emissions_delta"])
        max_emis_delta_pct = float(max_emissions_reduction["emissions_delta_pct"])

    construction_cost_columns = [

        "total_construction_cost_usd",
        "total_additional_construction_cost_usd",
        "construction_cost_usd",
        "additional_construction_cost_usd",

    ]
    available_construction_cost_col = next((c for c in construction_cost_columns if c in df.columns), None)
    if comparison_df.empty:
        min_construction_cost_scenario = "No renovation scenarios"
        min_construction_cost_text = "N/A"
        min_embodied_scenario = "No renovation scenarios"
        min_embodied_text = "N/A"
        min_embodied_intensity_text = "N/A"

    else:
        if available_construction_cost_col:
            construction_cost_series = pd.to_numeric(df[available_construction_cost_col], errors="coerce").fillna(float("inf"))
            construction_df = pd.DataFrame({

                "scenario": df[scenario_col].astype(str),
                "construction_cost": construction_cost_series,

            })
            construction_df = construction_df[~construction_df["scenario"].str.contains("baseline", case=False, na=False)]
            valid_construction_df = construction_df[construction_df["construction_cost"] < float("inf")]
            if valid_construction_df.empty:
                min_construction_cost_scenario = "No construction cost data"
                min_construction_cost_text = "N/A"

            else:
                min_construction_row = valid_construction_df.loc[valid_construction_df["construction_cost"].idxmin()]
                min_construction_cost_scenario = scenario_display_map.get(str(min_construction_row["scenario"]), str(min_construction_row["scenario"]))
                min_construction_cost_text = (f"${float(min_construction_row['construction_cost']):,.0f}" if abs(float(min_construction_row['construction_cost'])) >= 10 else f"${float(min_construction_row['construction_cost']):,.2f}")

        else:
            min_construction_cost_scenario = "Construction cost not in CSV"
            min_construction_cost_text = "N/A"

        min_embodied_row = comparison_df.loc[comparison_df["embodied_carbon_kg"].idxmin()]
        min_embodied_scenario = scenario_display_map.get(str(min_embodied_row["scenario"]), str(min_embodied_row["scenario"]))
        min_embodied_text = (f"{float(min_embodied_row['embodied_carbon_kg']):,.0f} kgCO2e" if abs(float(min_embodied_row['embodied_carbon_kg'])) >= 10 else f"{float(min_embodied_row['embodied_carbon_kg']):,.2f} kgCO2e")
        if building_area_m2 and building_area_m2 > 0:
            min_embodied_intensity = float(min_embodied_row["embodied_carbon_kg"]) / building_area_m2
            min_embodied_intensity_text = (f"{min_embodied_intensity:,.0f} kgCO<sub>2</sub>e/m<sup>2</sup>" if abs(min_embodied_intensity) >= 10 else f"{min_embodied_intensity:,.2f} kgCO<sub>2</sub>e/m<sup>2</sup>")

        else:
            min_embodied_intensity_text = "N/A"

    max_cost_class = "positive" if max_cost_delta <= 0 else ""
    max_emis_class = "positive" if max_emis_delta <= 0 else ""
    max_chart_cost = max(b["annual_cost_usd"], max_savings["annual_cost_usd"], 1.0)
    baseline_cost_w = b["annual_cost_usd"] / max_chart_cost * 100.0
    best_cost_w = max_savings["annual_cost_usd"] / max_chart_cost * 100.0
    max_chart_emis = max(b["annual_emissions_kg"], max_emissions_reduction["annual_emissions_kg"], 1.0)
    baseline_emis_w = b["annual_emissions_kg"] / max_chart_emis * 100.0
    best_emis_w = max_emissions_reduction["annual_emissions_kg"] / max_chart_emis * 100.0
    def _format_chart_number(v):
        try:
            val = float(v)

        except Exception:
            return str(v)

        if abs(val) >= 10:
            return f"{val:,.0f}"

        return f"{val:,.2f}"

    def money(v):
        return f"${_format_chart_number(v)}"

    def num(v):
        return _format_chart_number(v)

    def num_energy(v):
        return f"{float(v):,.2f}"

    if available_construction_cost_col:
        construction_cost_values = pd.to_numeric(df[available_construction_cost_col], errors="coerce")

    else:
        construction_cost_values = pd.Series([float("nan")] * len(report), index=report.index)

    spider_table_rows = "".join(

        f"<tr><td>{scenario_display_map.get(str(report.iloc[i]['scenario']), str(report.iloc[i]['scenario']))}</td><td>{num(float(report.iloc[i]['embodied_carbon_kg']))}</td><td>{money(float(construction_cost_values.iloc[i])) if pd.notna(construction_cost_values.iloc[i]) else 'N/A'}</td><td>{num(float(annual_operational_carbon.iloc[i]))}</td><td>{money(float(annual_operational_cost.iloc[i]))}</td></tr>"
        for i in range(len(report))

    )
    if not spider_table_rows:
        spider_table_rows = "<tr><td colspan='5'>No spider chart data found in CSV.</td></tr>"

    if "renovation_details" in df.columns:
        renovation_df = df[[scenario_col, "renovation_details"]].copy()

    else:
        renovation_df = df[[scenario_col]].copy()
        renovation_df["renovation_details"] = "Not available in CSV"

    renovation_df[scenario_col] = renovation_df[scenario_col].astype(str)
    renovation_df["renovation_details"] = renovation_df["renovation_details"].fillna("Not specified").astype(str)
    renovation_df["renovation_type"] = "unknown"

    scenario_config_map = {
        generate_scenario_name(s): s
        for s in generate_scenarios(cities=CITIES, building_types=BUILDING_TYPES, custom_combos=CUSTOM_COMBOS)
    }

    def _has_meaningful_value(raw):
        if raw is None:
            return False
        val = str(raw).strip()
        if val == "":
            return False
        return val.lower() not in {"nan", "null", "none", "not_applied", "not applied"}

    def _as_float(raw):
        try:
            return float(str(raw).strip())
        except Exception:
            return None

    def _clean_plain_text(raw):
        if raw is None:
            return ""
        text = re.sub(r"<[^>]+>", " ", str(raw))
        text = text.replace("&#59;", ";").replace("&#44;", ",")
        return re.sub(r"\s+", " ", text).strip()

    def _clean_summary_note(raw):
        text = _clean_plain_text(raw)
        if not text:
            return None
        text = text.replace(";", ". ")
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text

    def _friendly_option(raw):
        if not _has_meaningful_value(raw):
            return None
        text = re.sub(r"\s+", " ", str(raw).replace("_", " ").strip())
        mapped = {
            "wf wood": "wood frame",
            "wf vinyl": "vinyl frame",
            "wf aluminum": "aluminum frame",
            "provide user num panes": "custom pane count",
        }
        return mapped.get(text.lower(), text)

    def _build_measure_section(label, bullets):
        clean_bullets = [b for b in bullets if b]
        if not clean_bullets:
            return ""
        bullet_html = "".join(f"<li>{b}</li>" for b in clean_bullets)
        return (
            f"<div><strong>{label}:</strong>"
            + "<ul class='reno-action-list' style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>"
            + bullet_html
            + "</ul></div>"
        )

    def _applied_action(action_label, detail=None):
        if detail:
            return f"{action_label}: {detail}"
        return action_label

    def _skipped_action(action_label, reason=None):
        if reason:
            return f"{action_label} (skipped: {reason})"
        return f"{action_label} (skipped)"

    def _format_requested_r_value(raw):
        val = _as_float(raw)
        if val is None:
            return str(raw)
        return f"{val:.1f}"

    def _target_r_already_satisfied(note_text):
        note = _clean_summary_note(note_text)
        if not note:
            return False
        note_l = note.lower()
        skips_match = re.search(r"target-already-met\s*skips\s*=\s*(\d+)", note_l)
        if skips_match:
            try:
                return int(skips_match.group(1)) > 0
            except Exception:
                pass
        return (
            "already met or exceeded the target r-value" in note_l
            or "target r-value already satisfied" in note_l
        )

    def _fallback_scenario_value(scenario_name, measure_name, argument_name):
        scenario_cfg = scenario_config_map.get(str(scenario_name), {})
        if not scenario_cfg:
            return None

        window_requested = any([
            scenario_cfg.get("window_num_panes"),
            scenario_cfg.get("window_enhancement_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            scenario_cfg.get("window_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario_cfg.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("wf_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("film_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        door_requested = any([
            scenario_cfg.get("door_option"),
            scenario_cfg.get("door_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario_cfg.get("door_bottom_seal_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("door_top_side_seal_option", "none")).strip().lower() != "none",
        ])

        fallback_map = {
            "wall": {
                "__status__": "applied" if scenario_cfg.get("wall_r_value") else None,
                "r_value": scenario_cfg.get("wall_r_value"),
                "insulation_material_type": scenario_cfg.get("wall_insulation_material_type"),
            },
            "roof": {
                "__status__": "applied" if scenario_cfg.get("roof_r_value") else None,
                "r_value": scenario_cfg.get("roof_r_value"),
                "insulation_material_type": scenario_cfg.get("roof_insulation_material_type"),
            },
            "window": {
                "__status__": "applied" if window_requested else None,
                "user_num_panes": scenario_cfg.get("window_num_panes"),
                "weatherstrip_option": scenario_cfg.get("weatherstrip_option"),
                "film_option": scenario_cfg.get("film_option"),
                "wf_option": scenario_cfg.get("wf_option"),
                "caulking_option": scenario_cfg.get("caulking_option"),
                "secondary_glazing_option": scenario_cfg.get("secondary_glazing_option"),
            },
            "door": {
                "__status__": "applied" if door_requested else None,
                "door_option": scenario_cfg.get("door_option"),
                "door_bottom_seal_option": scenario_cfg.get("door_bottom_seal_option"),
                "door_top_side_seal_option": scenario_cfg.get("door_top_side_seal_option"),
            },
        }

        return fallback_map.get(measure_name, {}).get(argument_name)

    def _arg_value(scenario_name, measure_name, argument_name):
        if args_df_shared is not None:
            subset = args_df_shared[
                (args_df_shared["scenario"] == str(scenario_name))
                & (args_df_shared["measure"] == str(measure_name))
                & (args_df_shared["argument"] == str(argument_name))
            ]
            if not subset.empty:
                return str(subset.iloc[0]["value"])
        fallback = _fallback_scenario_value(scenario_name, measure_name, argument_name)
        if fallback is None:
            return None
        return str(fallback)

    args_csv_path = html_report_path.parent / "scenario_user_arguments.csv"
    args_df_shared = None
    if args_csv_path.exists():
        args_df_shared = pd.read_csv(args_csv_path)
        args_df_shared["scenario"] = args_df_shared["scenario"].astype(str)
        args_df_shared["measure"] = args_df_shared["measure"].astype(str)
        args_df_shared["argument"] = args_df_shared["argument"].astype(str)
        args_df_shared["value"] = args_df_shared["value"].astype(str)

    def _window_simple_glazing_blocked(row, scenario_summary):
        total_count = _as_float(row.get("window_total_count"))
        simple_count = _as_float(row.get("window_simple_glazing_count"))
        if total_count is not None and total_count > 0 and simple_count is not None and simple_count >= total_count:
            return True
        note = _clean_summary_note(scenario_summary.get("window"))
        return bool(note and "simpleglazing" in note.lower())

    def _window_action_bullets(row, scenario_name, scenario_summary):
        bullets = []
        panes = _arg_value(scenario_name, "window", "user_num_panes")
        weatherstrip_opt = _arg_value(scenario_name, "window", "weatherstrip_option")
        film_opt = _arg_value(scenario_name, "window", "film_option")
        frame_opt = _arg_value(scenario_name, "window", "wf_option")
        caulking_opt = _arg_value(scenario_name, "window", "caulking_option")
        secondary_opt = _arg_value(scenario_name, "window", "secondary_glazing_option")
        frame_area = _as_float(row.get("window_enhancement_renovated_frame_area_m2"))
        glazing_area = _as_float(row.get("window_enhancement_renovated_glazing_area_m2"))
        caulking_volume = _as_float(row.get("window_enhancement_renovated_caulking_volume_m3"))
        weatherstrip_length = _as_float(row.get("window_enhancement_renovated_weatherstrip_length_m"))
        operable_count = _as_float(row.get("window_operable_count"))
        simple_glazing_blocked = _window_simple_glazing_blocked(row, scenario_summary)
        upgrade_status = str(row.get("window_upgrade_status") or "").strip().lower()
        if upgrade_status in {"", "nan", "null", "none"}:
            upgrade_status = None

        if _has_meaningful_value(panes):
            if upgrade_status == "upgraded":
                bullets.append(_applied_action(f"{panes}-pane replacement"))
            elif simple_glazing_blocked:
                bullets.append(_skipped_action(f"{panes}-pane replacement", "SimpleGlazing windows"))
            else:
                bullets.append(_skipped_action(f"{panes}-pane replacement"))

        if _has_meaningful_value(weatherstrip_opt):
            if weatherstrip_length is not None and weatherstrip_length > 0:
                bullets.append(_applied_action("Weatherstrip application", _friendly_option(weatherstrip_opt)))
            elif operable_count is not None and operable_count <= 0:
                bullets.append(_skipped_action("Weatherstrip application", "no OperableWindow"))
            else:
                bullets.append(_skipped_action("Weatherstrip application"))

        if _has_meaningful_value(film_opt):
            if simple_glazing_blocked:
                bullets.append(_skipped_action("Glazing film application", "SimpleGlazing windows"))
            elif glazing_area is not None and glazing_area > 0:
                bullets.append(_applied_action("Glazing film application", _friendly_option(film_opt)))
            else:
                bullets.append(_skipped_action("Glazing film application"))

        if _has_meaningful_value(caulking_opt):
            if caulking_volume is not None and caulking_volume > 0:
                bullets.append(_applied_action("Caulking application", _friendly_option(caulking_opt)))
            else:
                bullets.append(_skipped_action("Caulking application"))

        if _has_meaningful_value(frame_opt):
            if frame_area is not None and frame_area > 0:
                bullets.append(_applied_action("Window frame replacement", _friendly_option(frame_opt)))
            else:
                bullets.append(_skipped_action("Window frame replacement"))

        if _has_meaningful_value(secondary_opt):
            if simple_glazing_blocked:
                bullets.append(_skipped_action("Secondary glazing application", "SimpleGlazing windows"))
            elif glazing_area is not None and glazing_area > 0:
                bullets.append(_applied_action("Secondary glazing application", _friendly_option(secondary_opt)))
            else:
                bullets.append(_skipped_action("Secondary glazing application"))

        return bullets

    summary_col_candidates = {
        "wall": ["wall_summary_notes", "wall_insulation_summary_notes"],
        "roof": ["roof_summary_notes", "roof_insulation_summary_notes"],
        "window": ["window_summary_notes", "window_enhancement_summary_notes"],
        "door": ["door_summary_notes", "door_enhancement_summary_notes"],
    }
    source_df = df.copy()
    source_df[scenario_col] = source_df[scenario_col].astype(str)
    source_rows_by_scenario = {str(src[scenario_col]): src for _, src in source_df.iterrows()}
    summary_notes_by_scenario = {}
    for _, src in source_df.iterrows():
        scenario_name = str(src[scenario_col])
        notes = {}
        for measure, candidates in summary_col_candidates.items():
            for col in candidates:
                if col in source_df.columns:
                    note = _clean_summary_note(src.get(col))
                    if note:
                        notes[measure] = note
                    break
        if notes:
            summary_notes_by_scenario[scenario_name] = notes

    for idx, row in renovation_df.iterrows():
        scenario_name = str(row[scenario_col])
        source_row = source_rows_by_scenario.get(scenario_name, row)
        if "baseline" in scenario_name.lower():
            renovation_df.at[idx, "renovation_type"] = "baseline"
            renovation_df.at[idx, "renovation_details"] = "Baseline (no envelope renovation)"
            continue

        measure_flags = {}
        for m in ["wall", "roof", "window", "door"]:
            status_val = _arg_value(scenario_name, m, "__status__")
            measure_flags[m] = (status_val == "applied")

        reno_types = [m for m in ["wall", "roof", "window", "door"] if measure_flags[m]]
        if reno_types:
            renovation_df.at[idx, "renovation_type"] = " + ".join(reno_types)

        details_parts = []
        scenario_summary = summary_notes_by_scenario.get(scenario_name, {})

        if measure_flags["wall"]:
            wall_r = _arg_value(scenario_name, "wall", "r_value")
            wall_mat = _arg_value(scenario_name, "wall", "insulation_material_type")
            detail_parts = []
            if _has_meaningful_value(wall_mat):
                detail_parts.append(str(wall_mat))
            if _has_meaningful_value(wall_r):
                detail_parts.append(f"target R-{_format_requested_r_value(wall_r)}")
            wall_note = scenario_summary.get("wall")
            wall_target_already_met = _target_r_already_satisfied(wall_note)
            wall_action = _applied_action("Exterior wall insulation", ", ".join(detail_parts) if detail_parts else None)
            if wall_target_already_met:
                wall_action = _skipped_action(wall_action, "target R-value already satisfied")
            details_parts.append(_build_measure_section("Wall upgrade", [
                wall_action
            ]))

        if measure_flags["roof"]:
            roof_r = _arg_value(scenario_name, "roof", "r_value")
            roof_mat = _arg_value(scenario_name, "roof", "insulation_material_type")
            detail_parts = []
            if _has_meaningful_value(roof_mat):
                detail_parts.append(str(roof_mat))
            if _has_meaningful_value(roof_r):
                detail_parts.append(f"target R-{_format_requested_r_value(roof_r)}")
            roof_note = scenario_summary.get("roof")
            roof_target_already_met = _target_r_already_satisfied(roof_note)
            roof_action = _applied_action("Roof insulation", ", ".join(detail_parts) if detail_parts else None)
            if roof_target_already_met:
                roof_action = _skipped_action(roof_action, "target R-value already satisfied")
            details_parts.append(_build_measure_section("Roof upgrade", [
                roof_action
            ]))

        if measure_flags["window"]:
            details_parts.append(
                _build_measure_section(
                    "Window upgrade",
                    _window_action_bullets(source_row, scenario_name, scenario_summary),
                )
            )

        if measure_flags["door"]:
            door_opt = _arg_value(scenario_name, "door", "door_option")
            bottom_seal = _arg_value(scenario_name, "door", "door_bottom_seal_option")
            top_side_seal = _arg_value(scenario_name, "door", "door_top_side_seal_option")
            door_lines = []
            if _has_meaningful_value(door_opt):
                total_doors = _as_float(source_row.get("total_doors_processed_count"))
                changed_doors = _as_float(source_row.get("total_doors_with_r_value_change_count"))
                friendly_opt = _friendly_option(door_opt)
                if changed_doors is not None and changed_doors == 0:
                    door_lines.append(_applied_action("Door replacement", f"{friendly_opt} (skipped due to door type incompatibility)"))
                elif changed_doors is not None and total_doors is not None and changed_doors < total_doors:
                    skipped = int(total_doors - changed_doors)
                    door_lines.append(_applied_action("Door replacement", f"{friendly_opt} ({skipped} of {int(total_doors)} door(s) skipped: door type incompatibility)"))
                else:
                    door_lines.append(_applied_action("Door replacement", friendly_opt))
            if _has_meaningful_value(bottom_seal):
                door_lines.append(_applied_action("Bottom seal", _friendly_option(bottom_seal)))
            if _has_meaningful_value(top_side_seal):
                door_lines.append(_applied_action("Top/side seal", _friendly_option(top_side_seal)))
            details_parts.append(_build_measure_section("Door upgrade", door_lines))

        if details_parts:
            renovation_df.at[idx, "renovation_details"] = "".join(details_parts)

    renovation_rows = "".join(

        f"<tr><td>{scenario_display_map.get(row[scenario_col], row[scenario_col])}</td><td>{row['renovation_type']}</td><td>{row['renovation_details']}</td></tr>"
        for _, row in renovation_df.iterrows()

    )
    # Build material list section by scenario (e.g., roof insulation volume, weatherstrip length).
    material_list_rows = []
    args_df_material = args_df_shared
    def _arg_lookup_material(scenario_name, measure_name, argument_name):
        if args_df_material is not None:
            subset = args_df_material[
                (args_df_material["scenario"] == str(scenario_name))
                & (args_df_material["measure"] == str(measure_name))
                & (args_df_material["argument"] == str(argument_name))
            ]
            if not subset.empty:
                return str(subset.iloc[0]["value"])
        return _arg_value(scenario_name, measure_name, argument_name)

    def _fmt_metric(value):
        val = _safe_float(value)
        if val is None:
            return "N/A"

        if abs(val) < 1e-9:
            return "N/A"

        if abs(val) < 0.01:
            return f"{val:.4f}".rstrip("0").rstrip(".")

        return num(val)

    def _add_material_row(scenario_name, component, material_name, volume_m3=None, area_m2=None, thickness_m=None, length_m=None, thermal_conductivity=None, density=None, lifetime_years=None):
        mat = _clean_text(material_name) or "N/A"
        material_list_rows.append(

            build_material_list_row_html(
                scenario_display=scenario_display_map.get(str(scenario_name), str(scenario_name)),
                component=component,
                material_name=mat,
                volume_m3=_fmt_metric(volume_m3),
                area_m2=_fmt_metric(area_m2),
                thickness_m=_fmt_metric(thickness_m),
                length_m=_fmt_metric(length_m),
                thermal_conductivity=_fmt_metric(thermal_conductivity),
                density=_fmt_metric(density),
                lifetime_years=_fmt_metric(lifetime_years),
            )

        )

    def _window_entry_is_applied(entry, data_row, scenario_name):
        name = str(entry.get("name", "")).strip().lower()
        description = str(entry.get("description", "")).strip().lower()
        simple_glazing_count = _safe_float(data_row.get("window_simple_glazing_count"))
        total_window_count = _safe_float(data_row.get("window_total_count"))
        all_simple_glazing = bool(total_window_count and simple_glazing_count is not None and simple_glazing_count >= total_window_count)
        window_upgrade_status = _clean_text(data_row.get("window_upgrade_status"))
        frame_area, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_frame_area_m2",
        ])
        glazing_area, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_glazing_area_m2",
        ])
        caulking_volume, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_caulking_volume_m3",
        ])
        weatherstrip_length, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_weatherstrip_length_m",
        ])
        if "weatherstrip" in name or "weatherstrip" in description:
            return weatherstrip_length is not None and weatherstrip_length > 0
        if "sealant" in name or "caulking" in description:
            return caulking_volume is not None and caulking_volume > 0
        if "window frame" in name or "frame" in description:
            return frame_area is not None and frame_area > 0
        if "film" in name or "film" in description:
            return not all_simple_glazing and glazing_area is not None and glazing_area > 0
        if "secondary glazing" in name or "secondary glazing" in description:
            return not all_simple_glazing and glazing_area is not None and glazing_area > 0
        if "glazing" in name or "pane" in description:
            return window_upgrade_status == "upgraded"
        return True

    seen_material_rows = set()
    def _register_material_row(scenario_name, component, material_name, volume_m3, area_m2, thickness_m, length_m):
        dedupe_key = (
            scenario_name,
            component,
            _clean_text(material_name),
            round(volume_m3 or 0.0, 6),
            round(area_m2 or 0.0, 6),
            round(thickness_m or 0.0, 6),
            round(length_m or 0.0, 6),
        )
        if dedupe_key in seen_material_rows:
            return False
        seen_material_rows.add(dedupe_key)
        return True

    def _add_material_entry_from_payload(scenario_name, measure_name, entry, thermal_conductivity=None, density=None, lifetime_years=None):
        component = component_from_entry(measure_name, entry)
        # Use "name" field and extract just the material type, not full description
        material_name = extract_material_type_name(entry.get("name") or entry.get("description"))
        volume_m3, area_m2, thickness_m, length_m = material_metrics_from_entry(entry)
        entry_lifetime_years = _safe_float(
            entry.get("lifetime_years")
            or entry.get("service_life_years")
            or entry.get("lifetime")
        )
        if not _register_material_row(
            scenario_name,
            component,
            material_name,
            volume_m3,
            area_m2,
            thickness_m,
            length_m,
        ):
            return
        _add_material_row(
            scenario_name,
            component,
            material_name,
            volume_m3=volume_m3,
            area_m2=area_m2,
            thickness_m=thickness_m,
            length_m=length_m,
            thermal_conductivity=thermal_conductivity,
            density=density,
            lifetime_years=entry_lifetime_years if entry_lifetime_years is not None else lifetime_years,
        )

    def _window_component_lifetime(component, data_row):
        if component in {"Window glazing", "Secondary glazing"}:
            return _safe_float(data_row.get("window_glass_lifetime_years"))
        if component == "Window frame":
            return _safe_float(data_row.get("window_frame_lifetime_years"))
        if component == "Window caulking":
            return _safe_float(data_row.get("window_caulking_lifetime_years"))
        if component == "Glazing film":
            return _safe_float(data_row.get("window_film_lifetime_years"))
        if component == "Window weatherstrip":
            return _safe_float(data_row.get("window_weatherstrip_lifetime_years"))
        return None

    def _door_component_lifetime(component, data_row):
        if component == "Door panel":
            return _safe_float(data_row.get("door_lifetime_years"))
        if component in {"Door bottom seal", "Door top/side seal"}:
            return _safe_float(data_row.get("door_strip_lifetime_years"))
        return None

    def _pick_first_numeric(row, candidates):
        for key in candidates:
            if key in row.index:
                val = _safe_float(row.get(key))
                if val is not None:
                    return val, key

        return None, None

    for _, data_row in df.iterrows():
        scenario_name = str(data_row[scenario_col])
        if "baseline" in scenario_name.lower():
            continue

        wall_status = _clean_text(_arg_lookup_material(scenario_name, "wall", "__status__"))
        roof_status = _clean_text(_arg_lookup_material(scenario_name, "roof", "__status__"))
        window_status = _clean_text(_arg_lookup_material(scenario_name, "window", "__status__"))
        door_status = _clean_text(_arg_lookup_material(scenario_name, "door", "__status__"))
        if wall_status == "applied":
            wall_thermal_conductivity, _ = _pick_first_numeric(data_row, [
                "wall_insulation_material_thermal_conductivity_W_per_mK",
            ])
            wall_density, _ = _pick_first_numeric(data_row, [
                "wall_insulation_material_density_kg_per_m3",
            ])
            wall_lifetime, _ = _pick_first_numeric(data_row, [
                "wall_insulation_material_lifetime_years",
            ])
            wall_vol, _ = _pick_first_numeric(data_row, [
                "wall_insulation_added_volume_m3",
            ])
            wall_area, _ = _pick_first_numeric(data_row, [
                "wall_insulation_renovated_area_m2",
            ])
            _add_material_row(
                scenario_name,
                "Wall insulation",
                _clean_text(data_row.get("wall_insulation_material_type")) or _arg_lookup_material(scenario_name, "wall", "insulation_material_type"),
                volume_m3=wall_vol,
                area_m2=wall_area,
                thermal_conductivity=wall_thermal_conductivity,
                density=wall_density,
                lifetime_years=wall_lifetime,
            )

        if roof_status == "applied":
            roof_thermal_conductivity, _ = _pick_first_numeric(data_row, [
                "roof_insulation_material_thermal_conductivity_W_per_mK",
            ])
            roof_density, _ = _pick_first_numeric(data_row, [
                "roof_insulation_material_density_kg_per_m3",
            ])
            roof_lifetime, _ = _pick_first_numeric(data_row, [
                "roof_insulation_material_lifetime_years",
            ])
            roof_vol, _ = _pick_first_numeric(data_row, [
                "roof_insulation_added_volume_m3",
            ])
            roof_area, _ = _pick_first_numeric(data_row, [
                "roof_insulation_renovated_area_m2",
            ])
            roof_thickness = (roof_vol / roof_area) if (roof_vol is not None and roof_area is not None and roof_area > 0) else None
            _add_material_row(
                scenario_name,
                "Roof insulation",
                _arg_lookup_material(scenario_name, "roof", "insulation_material_type"),
                volume_m3=roof_vol,
                area_m2=roof_area,
                thickness_m=roof_thickness,
                thermal_conductivity=roof_thermal_conductivity,
                density=roof_density,
                lifetime_years=roof_lifetime,
            )

        if window_status == "applied":
            frame_area, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_frame_area_m2",
            ])
            caulking_volume, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_caulking_volume_m3",
            ])
            weatherstrip_length, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_weatherstrip_length_m",
            ])

            if frame_area is not None and frame_area > 0:
                _add_material_row(
                    scenario_name,
                    "Window frame",
                    _arg_lookup_material(scenario_name, "window", "wf_option"),
                    area_m2=frame_area,
                    lifetime_years=_safe_float(data_row.get("window_frame_lifetime_years")),
                )
            if caulking_volume is not None and caulking_volume > 0:
                _add_material_row(
                    scenario_name,
                    "Window caulking",
                    _arg_lookup_material(scenario_name, "window", "caulking_option"),
                    volume_m3=caulking_volume,
                    lifetime_years=_safe_float(data_row.get("window_caulking_lifetime_years")),
                )
            if weatherstrip_length is not None and weatherstrip_length > 0:
                _add_material_row(
                    scenario_name,
                    "Window weatherstrip",
                    _arg_lookup_material(scenario_name, "window", "weatherstrip_option"),
                    length_m=weatherstrip_length,
                    lifetime_years=_safe_float(data_row.get("window_weatherstrip_lifetime_years")),
                )

        if door_status == "applied":
            door_density, _ = _pick_first_numeric(data_row, [
                "door_density_kg_per_m3",
            ])
            door_conductivity, _ = _pick_first_numeric(data_row, [
                "door_conductivity_W_per_mK",
            ])
            door_area, _ = _pick_first_numeric(data_row, [
                "door_enhancement_renovated_area_m2",
                "total_renovated_door_area_m2",
            ])
            if door_area is not None and door_area > 0:
                _add_material_row(
                    scenario_name,
                    "Door",
                    _arg_lookup_material(scenario_name, "door", "door_option"),
                    area_m2=door_area,
                    thermal_conductivity=door_conductivity,
                    density=door_density,
                    lifetime_years=_safe_float(data_row.get("door_lifetime_years")),
                )
            door_bottom_length, _ = _pick_first_numeric(data_row, [
                "door_sealing_bottom_length_m",
            ])
            if door_bottom_length is not None and door_bottom_length > 0:
                _add_material_row(
                    scenario_name,
                    "Door bottom sealing",
                    _arg_lookup_material(scenario_name, "door", "door_bottom_seal_option"),
                    length_m=door_bottom_length,
                    lifetime_years=_safe_float(data_row.get("door_strip_lifetime_years")),
                )
            door_top_side_length, _ = _pick_first_numeric(data_row, [
                "door_sealing_side_length_m",
            ])
            if door_top_side_length is not None and door_top_side_length > 0:
                _add_material_row(
                    scenario_name,
                    "Door top/side sealing",
                    _arg_lookup_material(scenario_name, "door", "door_top_side_seal_option"),
                    length_m=door_top_side_length,
                    lifetime_years=_safe_float(data_row.get("door_strip_lifetime_years")),
                )

    if material_list_rows:
        material_list_section_html = (

            "<div class='section'><h2>Material List</h2><div class='summary-box'><p>Material properties and consumption by renovation scenario. Missing values are shown as N/A.</p></div><table class='material-costs-table material-list-table'><tr><th>Scenario</th><th>Component</th><th>Material name</th><th>Volume (m<sup>3</sup>)</th><th>Area (m<sup>2</sup>)</th><th>Thickness (m)</th><th>Length (m)</th><th>Thermal Conductivity (W/m&middot;K)</th><th>Density (kg/m<sup>3</sup>)</th><th>Product Lifetime (years)</th></tr>"
            + "".join(material_list_rows)
            + "</table></div>"

        )

    else:
        material_list_section_html = "<div class='section'><h2>Material List</h2><div class='summary-box'><p>No material consumption data found for renovation scenarios.</p></div></div>"

    def _build_measure_pie_panel(panel_title, slices, formatter, total_suffix=""):
        valid_slices = [(label, float(value), color) for label, value, color in slices if value is not None and float(value) > 0]
        if not valid_slices:
            return (
                "<div class='scenario-pie-panel'>"
                + f"<h4>{panel_title}</h4>"
                + "<div class='scenario-pie-empty'>No retrofit measure contribution data.</div>"
                + "</div>"
            )

        total_value = sum(value for _, value, _ in valid_slices)
        if total_value <= 0:
            return (
                "<div class='scenario-pie-panel'>"
                + f"<h4>{panel_title}</h4>"
                + "<div class='scenario-pie-empty'>No retrofit measure contribution data.</div>"
                + "</div>"
            )

        grad_parts = []
        legend_items = []
        start_pct = 0.0
        for label, value, color in valid_slices:
            pct = (value / total_value) * 100.0
            end_pct = min(100.0, start_pct + pct)
            grad_parts.append(f"{color} {start_pct:.4f}% {end_pct:.4f}%")
            legend_items.append(
                "<div class='scenario-pie-legend-item'>"
                + f"<span class='scenario-pie-swatch' style='background:{color};'></span>"
                + f"<span>{label}: {formatter(value)} ({pct:.1f}%)</span>"
                + "</div>"
            )
            start_pct = end_pct

        pie_style = f"background:conic-gradient({', '.join(grad_parts)});"
        total_text = f"Total: {formatter(total_value)}{total_suffix}"
        return (
            "<div class='scenario-pie-panel'>"
            + f"<h4>{panel_title}</h4>"
            + "<div class='scenario-pie-wrap'>"
            + f"<div class='scenario-pie' style='{pie_style}'></div>"
            + f"<div class='scenario-pie-legend'>{''.join(legend_items)}</div>"
            + "</div>"
            + f"<div class='scenario-pie-total'>{total_text}</div>"
            + "</div>"
        )

    measure_color_map = {
        "Wall": "#1f77b4",
        "Roof": "#ff7f0e",
        "Window": "#2ca02c",
        "Door": "#d62728",
    }
    pie_cards = []
    for _, scenario_row in df.iterrows():
        scenario_name = str(scenario_row[scenario_col])
        if "baseline" in scenario_name.lower():
            continue

        wall_cost, _ = _pick_first_numeric(scenario_row, [
            "wall_insulation_total_cost_with_overhead_and_profit_usd",
            "wall_insulation_total_cost_with_overhead_and_profit_$",
        ])
        roof_cost, _ = _pick_first_numeric(scenario_row, [
            "roof_insulation_total_cost_with_overhead_and_profit_usd",
            "roof_insulation_total_cost_with_overhead_and_profit_$",
        ])
        window_cost, _ = _pick_first_numeric(scenario_row, [
            "window_enhancement_total_cost_with_overhead_and_profit_usd",
            "window_enhancement_total_cost_with_overhead_and_profit_$",
        ])
        door_cost, _ = _pick_first_numeric(scenario_row, [
            "door_enhancement_total_cost_with_overhead_and_profit_usd",
            "door_enhancement_total_cost_with_overhead_and_profit_$",
        ])

        wall_carbon, _ = _pick_first_numeric(scenario_row, ["wall_insulation_embodied_carbon_kgCO2eq"])
        roof_carbon, _ = _pick_first_numeric(scenario_row, ["roof_insulation_embodied_carbon_kgCO2eq"])
        window_carbon, _ = _pick_first_numeric(scenario_row, ["window_enhancement_embodied_carbon_kgCO2eq"])
        door_carbon, _ = _pick_first_numeric(scenario_row, ["door_enhancement_embodied_carbon_kgCO2eq"])

        cost_slices = [
            ("Wall", wall_cost, measure_color_map["Wall"]),
            ("Roof", roof_cost, measure_color_map["Roof"]),
            ("Window", window_cost, measure_color_map["Window"]),
            ("Door", door_cost, measure_color_map["Door"]),
        ]
        carbon_slices = [
            ("Wall", wall_carbon, measure_color_map["Wall"]),
            ("Roof", roof_carbon, measure_color_map["Roof"]),
            ("Window", window_carbon, measure_color_map["Window"]),
            ("Door", door_carbon, measure_color_map["Door"]),
        ]

        scenario_label = scenario_display_map.get(scenario_name, scenario_name)
        pie_cards.append(
            "<div class='scenario-pie-card'>"
            + f"<div class='scenario-pie-title'>{scenario_label}</div>"
            + "<div class='scenario-pie-row'>"
            + _build_measure_pie_panel("Cost breakdown by retrofit measure", cost_slices, money)
            + _build_measure_pie_panel("Carbon breakdown by retrofit measure", carbon_slices, num, " kg CO2e")
            + "</div></div>"
        )

    if pie_cards:
        result_summary_pie_charts_html = (
            "<div class='summary-box'><p>Per-scenario retrofit contribution breakdown."
            + " Each scenario includes two pie charts: cost and embodied carbon by retrofit measure.</p></div>"
            + "<div class='scenario-pie-grid'>"
            + "".join(pie_cards)
            + "</div>"
        )
    else:
        result_summary_pie_charts_html = (
            "<div class='summary-box'><p>No non-baseline scenarios available for retrofit measure breakdown pie charts.</p></div>"
        )

    energy_analysis_rows = []
    for _, row in comparison_df.iterrows():
        row_delta = b["total_site_energy_gj"] - row["total_site_energy_gj"]
        row_delta_pct = (row_delta / b["total_site_energy_gj"] * 100.0) if b["total_site_energy_gj"] > 0 else 0.0
        positive_class = "positive" if row_delta >= 0 else ""
        energy_analysis_rows.append(

            f"<tr>"
            f"<td>{scenario_display_map.get(row['scenario'], row['scenario'])}</td>"
            f"<td>Total Site Energy (GJ)</td>"
            f"<td>{num_energy(b['total_site_energy_gj'])}</td>"
            f"<td>{num_energy(row['total_site_energy_gj'])}</td>"
            f"<td class=\"{positive_class}\">{num_energy(row_delta)}</td>"
            f"<td class=\"{positive_class}\">{num_energy(row_delta_pct)}%</td>"
            f"</tr>"

        )

    if energy_analysis_rows:
        energy_analysis_table = "".join(energy_analysis_rows)

    else:
        energy_analysis_table = "<tr><td colspan='6'>No applied renovation scenarios found.</td></tr>"

    def _safe_payback_report(total_value, annual_saving):
        if pd.isna(total_value) or pd.isna(annual_saving):
            return None

        if float(total_value) <= 0 or float(annual_saving) <= 0:
            return None

        return float(total_value) / float(annual_saving)

    if comparison_df.empty:
        cost_payback_chart_rows = "<div style='font-size:12px;color:#666;'>No applied renovation scenarios found.</div>"
        carbon_payback_chart_rows = "<div style='font-size:12px;color:#666;'>No applied renovation scenarios found.</div>"
        material_comparison_section_html = ""
        lowest_cost_payback_text = "N/A"
        lowest_cost_payback_scenario = "No renovation scenarios"
        lowest_carbon_payback_text = "N/A"
        lowest_carbon_payback_scenario = "No renovation scenarios"

    else:
        payback_df = comparison_df[["scenario", "cost_delta", "emissions_delta", "embodied_carbon_kg", "annual_emissions_kg", "annual_cost_usd"]].copy()
        if available_construction_cost_col:
            construction_series = pd.to_numeric(df[available_construction_cost_col], errors="coerce")
            construction_lookup = pd.DataFrame({

                "scenario": df[scenario_col].astype(str),
                "construction_cost": construction_series,

            })
            payback_df = payback_df.merge(construction_lookup, on="scenario", how="left")

        else:
            payback_df["construction_cost"] = float("nan")

        payback_df["cost_payback_years"] = payback_df.apply(lambda r: _safe_payback_report(r["construction_cost"], -r["cost_delta"]), axis=1)
        payback_df["carbon_payback_years"] = payback_df.apply(lambda r: _safe_payback_report(r["embodied_carbon_kg"], -r["emissions_delta"]), axis=1)
        valid_cost_paybacks = payback_df["cost_payback_years"].dropna()
        valid_carbon_paybacks = payback_df["carbon_payback_years"].dropna()
        max_cost_payback = float(valid_cost_paybacks.max()) if not valid_cost_paybacks.empty else 1.0
        max_carbon_payback = float(valid_carbon_paybacks.max()) if not valid_carbon_paybacks.empty else 1.0
        if max_cost_payback <= 0:
            max_cost_payback = 1.0

        if max_carbon_payback <= 0:
            max_carbon_payback = 1.0

        valid_cost_payback_rows = payback_df[pd.notna(payback_df["cost_payback_years"])].copy()
        if valid_cost_payback_rows.empty:
            lowest_cost_payback_text = "N/A"
            lowest_cost_payback_scenario = "No valid cost payback scenario"

        else:
            min_cost_payback_row = valid_cost_payback_rows.loc[valid_cost_payback_rows["cost_payback_years"].idxmin()]
            lowest_cost_payback_text = f"{num(float(min_cost_payback_row['cost_payback_years']))} years"
            lowest_cost_payback_scenario = scenario_display_map.get(str(min_cost_payback_row["scenario"]), str(min_cost_payback_row["scenario"]))

        valid_carbon_payback_rows = payback_df[pd.notna(payback_df["carbon_payback_years"])].copy()
        if valid_carbon_payback_rows.empty:
            lowest_carbon_payback_text = "N/A"
            lowest_carbon_payback_scenario = "No valid carbon payback scenario"

        else:
            min_carbon_payback_row = valid_carbon_payback_rows.loc[valid_carbon_payback_rows["carbon_payback_years"].idxmin()]
            lowest_carbon_payback_text = f"{num(float(min_carbon_payback_row['carbon_payback_years']))} years"
            lowest_carbon_payback_scenario = scenario_display_map.get(str(min_carbon_payback_row["scenario"]), str(min_carbon_payback_row["scenario"]))

        cost_payback_chart_rows = "".join(

            f"<div class='bar-row'><div class='bar-label'>{scenario_display_map.get(str(r['scenario']), str(r['scenario']))}</div><div class='bar-track'><div class='bar retrofit' style='width:{((float(r['cost_payback_years']) / max_cost_payback) * 100.0):.1f}%;'></div></div><div class='bar-value'>{num(float(r['cost_payback_years']))} yrs</div></div>" if pd.notna(r['cost_payback_years']) else f"<div class='bar-row'><div class='bar-label'>{scenario_display_map.get(str(r['scenario']), str(r['scenario']))}</div><div class='bar-track'></div><div class='bar-value'>N/A</div></div>"
            for _, r in payback_df.iterrows()

        )
        carbon_payback_chart_rows = "".join(

            f"<div class='bar-row'><div class='bar-label'>{scenario_display_map.get(str(r['scenario']), str(r['scenario']))}</div><div class='bar-track'><div class='bar retrofit' style='width:{((float(r['carbon_payback_years']) / max_carbon_payback) * 100.0):.1f}%;'></div></div><div class='bar-value'>{num(float(r['carbon_payback_years']))} yrs</div></div>" if pd.notna(r['carbon_payback_years']) else f"<div class='bar-row'><div class='bar-label'>{scenario_display_map.get(str(r['scenario']), str(r['scenario']))}</div><div class='bar-track'></div><div class='bar-value'>N/A</div></div>"
            for _, r in payback_df.iterrows()

        )
        if not cost_payback_chart_rows:
            cost_payback_chart_rows = "<div style='font-size:12px;color:#666;'>No data available for cost payback chart.</div>"

        if not carbon_payback_chart_rows:
            carbon_payback_chart_rows = "<div style='font-size:12px;color:#666;'>No data available for carbon payback chart.</div>"

        # Build material-comparison groups from scenario_user_arguments.csv instead of scenario-name parsing.
        # This is robust for simplified names like scenario_3_... that do not encode wall_r/material slug.
        material_rows = []
        args_csv_path = html_report_path.parent / "scenario_user_arguments.csv"
        if args_df_shared is not None:
            args_df_cmp = args_df_shared
            def _cmp_arg_value(scenario_name, measure_name, argument_name):
                subset = args_df_cmp[

                    (args_df_cmp["scenario"] == scenario_name)
                    & (args_df_cmp["measure"] == measure_name)
                    & (args_df_cmp["argument"] == argument_name)

                ]
                if subset.empty:
                    return None

                return str(subset.iloc[0]["value"])

            for _, payback_row in payback_df.iterrows():
                scenario_name = str(payback_row["scenario"])
                wall_status = _cmp_arg_value(scenario_name, "wall", "__status__")
                roof_status = _cmp_arg_value(scenario_name, "roof", "__status__")
                # Prefer wall material comparison groups first, then roof.
                if wall_status == "applied":
                    wall_r = _cmp_arg_value(scenario_name, "wall", "r_value")
                    wall_mat = _cmp_arg_value(scenario_name, "wall", "insulation_material_type")
                    roof_r = _cmp_arg_value(scenario_name, "roof", "r_value")
                    window_u_cmp = _cmp_arg_value(scenario_name, "window", "u_value")
                    door_type_cmp = _cmp_arg_value(scenario_name, "door", "door_option")
                    if wall_r and wall_mat:
                        group_key = ("wall", str(wall_r), str(roof_r) if roof_r else None, str(window_u_cmp) if window_u_cmp else None, str(door_type_cmp).lower() if door_type_cmp else None)
                        label = f"Wall insulation material comparison (target R-{wall_r})"
                        material_name = str(wall_mat)

                    else:
                        continue

                elif roof_status == "applied":
                    roof_r = _cmp_arg_value(scenario_name, "roof", "r_value")
                    roof_mat = _cmp_arg_value(scenario_name, "roof", "insulation_material_type")
                    wall_r = _cmp_arg_value(scenario_name, "wall", "r_value")
                    window_u_cmp = _cmp_arg_value(scenario_name, "window", "u_value")
                    door_type_cmp = _cmp_arg_value(scenario_name, "door", "door_option")
                    if roof_r and roof_mat:
                        group_key = ("roof", str(roof_r), str(wall_r) if wall_r else None, str(window_u_cmp) if window_u_cmp else None, str(door_type_cmp).lower() if door_type_cmp else None)
                        label = f"Roof insulation material comparison (target R-{roof_r})"
                        material_name = str(roof_mat)

                    else:
                        continue

                else:
                    continue

                material_rows.append({

                    "group_key": group_key,
                    "label": label,
                    "material": material_name,
                    "scenario_display": scenario_display_map.get(str(payback_row["scenario"]), str(payback_row["scenario"])),
                    "cost_saving": float(payback_row["annual_cost_usd"]) - float(b["annual_cost_usd"]),
                    "annual_operational_carbon": float(payback_row["annual_emissions_kg"]),
                    "total_embodied_carbon": float(payback_row["embodied_carbon_kg"]),
                    "operational_carbon_saving": float(payback_row["annual_emissions_kg"]) - float(b["annual_emissions_kg"]),
                    "annual_operational_cost": float(payback_row["annual_cost_usd"]),
                    "total_construction_cost": float(payback_row["construction_cost"]) if pd.notna(payback_row["construction_cost"]) else 0.0,
                    "operational_cost_saving": float(payback_row["annual_cost_usd"]) - float(b["annual_cost_usd"]),
                    "cost_payback": float(payback_row["cost_payback_years"]) if pd.notna(payback_row["cost_payback_years"]) else None,
                    "carbon_payback": float(payback_row["carbon_payback_years"]) if pd.notna(payback_row["carbon_payback_years"]) else None,

                })

        material_section_blocks = []
        if material_rows:
            material_df = pd.DataFrame(material_rows)
            prepared_groups = []
            for _, group_df in material_df.groupby("group_key", sort=False):
                if group_df["material"].nunique() < 2:
                    continue

                group_df = group_df.sort_values(by="cost_saving", ascending=False).copy()
                prepared_groups.append(group_df)

            if prepared_groups:
                material_plot_df = pd.concat(prepared_groups, ignore_index=True)
                global_max_positive = max((material_plot_df["annual_operational_carbon"] + material_plot_df["total_embodied_carbon"]).max(), 1.0)
                global_max_negative = max(material_plot_df["operational_carbon_saving"].abs().max(), 1.0)
                shared_axis_max = max(global_max_positive, global_max_negative, 1.0)
                global_max_positive_cost = max((material_plot_df["annual_operational_cost"] + material_plot_df["total_construction_cost"]).max(), 1.0)
                global_max_negative_cost = max(material_plot_df["operational_cost_saving"].abs().max(), 1.0)
                shared_cost_axis_max = max(global_max_positive_cost, global_max_negative_cost, 1.0)
                for group_df in prepared_groups:
                    group_rows_html = "".join(

                        f"<tr><td>{row['scenario_display']}</td><td>{row['material']}</td><td>{money(row['cost_saving'])}</td><td>{num(float(row['operational_carbon_saving']))}</td><td>{(num(float(row['cost_payback'])) + ' yrs') if pd.notna(row['cost_payback']) else 'N/A'}</td><td>{(num(float(row['carbon_payback'])) + ' yrs') if pd.notna(row['carbon_payback']) else 'N/A'}</td></tr>"
                        for _, row in group_df.iterrows()

                    )
                    chart_cols_html = "".join(

                        f"<div style='display:flex;flex-direction:column;align-items:center;gap:6px;min-width:132px;'><div style='position:relative;width:76px;height:190px;'><div style='position:absolute;left:0;right:0;top:50%;height:1px;background:#8a8a8a;'></div><div style='position:absolute;left:10px;width:22px;bottom:50%;height:{max((float(row['annual_operational_carbon'])/shared_axis_max)*50.0,0.0):.2f}%;background:#007bff;border-radius:0;'></div><div style='position:absolute;left:10px;width:22px;bottom:{50.0 + max((float(row['annual_operational_carbon'])/shared_axis_max)*50.0,0.0):.2f}%;height:{max((float(row['total_embodied_carbon'])/shared_axis_max)*50.0,0.0):.2f}%;background:#fd7e14;border-radius:0;'></div><div style='position:absolute;left:10px;width:22px;top:50%;height:{max((max(-float(row['operational_carbon_saving']), 0.0)/shared_axis_max)*50.0,0.0):.2f}%;background:#28a745;border-radius:0;'></div><div style='position:absolute;left:44px;width:22px;bottom:50%;height:{max((float(row['annual_operational_cost'])/shared_cost_axis_max)*50.0,0.0):.2f}%;background:#9ecae1;border-radius:0;'></div><div style='position:absolute;left:44px;width:22px;bottom:{50.0 + max((float(row['annual_operational_cost'])/shared_cost_axis_max)*50.0,0.0):.2f}%;height:{max((float(row['total_construction_cost'])/shared_cost_axis_max)*50.0,0.0):.2f}%;background:#fdd0a2;border-radius:0;'></div><div style='position:absolute;left:44px;width:22px;top:50%;height:{max((max(-float(row['operational_cost_saving']), 0.0)/shared_cost_axis_max)*50.0,0.0):.2f}%;background:#b8e6b8;border-radius:0;'></div></div><div style='font-size:11px;color:#444;text-align:center;line-height:1.25;'>{row['material']}</div></div>"
                        for _, row in group_df.iterrows()

                    )
                    carbon_axis_html = (

                        f"<div style='position:relative;width:74px;height:190px;border-right:1px solid #9aa0a6;'><div style='position:absolute;right:0;left:0;top:0;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:25%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:50%;height:1px;background:#8a8a8a;'></div><div style='position:absolute;right:0;left:0;top:75%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:100%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:8px;top:-7px;font-size:10px;color:#666;'>{num(shared_axis_max)}</div><div style='position:absolute;right:8px;top:calc(25% - 7px);font-size:10px;color:#666;'>{num(shared_axis_max * 0.5)}</div><div style='position:absolute;right:8px;top:calc(50% - 7px);font-size:10px;color:#666;'>0.00</div><div style='position:absolute;right:8px;top:calc(75% - 7px);font-size:10px;color:#666;'>{num(-shared_axis_max * 0.5)}</div><div style='position:absolute;right:8px;top:calc(100% - 7px);font-size:10px;color:#666;'>{num(-shared_axis_max)}</div><div style='position:absolute;left:-2px;top:50%;transform:translate(-100%,-50%) rotate(-90deg);transform-origin:center;font-size:10px;color:#666;white-space:nowrap;'>Carbon (kg CO2e)</div></div>"

                    )
                    cost_axis_html = (

                        f"<div style='position:relative;width:86px;height:190px;border-left:1px solid #9aa0a6;'><div style='position:absolute;right:0;left:0;top:0;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:25%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:50%;height:1px;background:#8a8a8a;'></div><div style='position:absolute;right:0;left:0;top:75%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;right:0;left:0;top:100%;height:1px;background:#e1e5ea;'></div><div style='position:absolute;left:8px;top:-7px;font-size:10px;color:#666;'>{money(shared_cost_axis_max)}</div><div style='position:absolute;left:8px;top:calc(25% - 7px);font-size:10px;color:#666;'>{money(shared_cost_axis_max * 0.5)}</div><div style='position:absolute;left:8px;top:calc(50% - 7px);font-size:10px;color:#666;'>$0.00</div><div style='position:absolute;left:8px;top:calc(75% - 7px);font-size:10px;color:#666;'>{money(-shared_cost_axis_max * 0.5)}</div><div style='position:absolute;left:8px;top:calc(100% - 7px);font-size:10px;color:#666;'>{money(-shared_cost_axis_max)}</div><div style='position:absolute;right:-2px;top:50%;transform:translate(100%,-50%) rotate(90deg);transform-origin:center;font-size:10px;color:#666;white-space:nowrap;'>Cost (USD)</div></div>"

                    )
                    chart_html = (

                        "<div style='margin-top:10px;'>"
                        + f"<div style='display:flex;justify-content:center;gap:12px;align-items:flex-start;flex-wrap:nowrap;overflow-x:auto;border:1px solid #ddd;border-radius:6px;padding:12px;background:#fafafa;'><div style='flex:0 0 auto;'>{carbon_axis_html}</div><div style='display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;'>{chart_cols_html}</div><div style='flex:0 0 auto;'>{cost_axis_html}</div></div></div>"
                        + "<div style='display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:10px;font-size:11px;color:#444;'><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#007bff;border-radius:0;display:inline-block;'></span>Annual operational carbon (positive)</span><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#fd7e14;border-radius:0;display:inline-block;'></span>Retrofit embodied carbon (positive)</span><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#28a745;border-radius:0;display:inline-block;'></span>Annual operational carbon saving (negative)</span><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#9ecae1;border-radius:0;display:inline-block;'></span>Annual operational cost (positive)</span><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#fdd0a2;border-radius:0;display:inline-block;'></span>Retrofit construction cost (positive)</span><span style='display:inline-flex;align-items:center;gap:6px;'><span style='width:12px;height:12px;background:#b8e6b8;border-radius:0;display:inline-block;'></span>Annual operational cost saving (negative)</span></div>"

                    )
                    material_section_blocks.append(

                        f"<h3>{group_df.iloc[0]['label']}</h3><table><tr><th>Scenario</th><th>Insulation Material Type</th><th>Operational Cost Saving (Scenario - Baseline) ($/yr)</th><th>Operational Carbon Saving (Scenario - Baseline) (kg CO2e/yr)</th><th>Cost Payback Period (years)</th><th>Carbon Payback Period (years)</th></tr>{group_rows_html}</table>{chart_html}"

                    )

        if material_section_blocks:
            material_comparison_section_html = (

                "<div class='section'><h2>Material Type Comparison</h2><div class='summary-box'><p>Auto-generated when scenarios share the same target insulation settings but use different insulation materials.</p></div>"
                + "".join(material_section_blocks)
                + "</div>"

            )

        else:
            material_comparison_section_html = ""

    generated_time = datetime.now().strftime("%B %d, %Y")
    report_year = datetime.now().year
    html = build_report_html(

        embodied_analysis_period_years=embodied_analysis_period_years,
        renovation_rows=renovation_rows,
        energy_analysis_table=energy_analysis_table,
        max_cost_class=max_cost_class,
        money=money,
        max_cost_delta=max_cost_delta,
        max_cost_delta_pct=max_cost_delta_pct,
        max_savings_scenario=max_savings_scenario,
        max_emis_class=max_emis_class,
        num=num,
        max_emis_delta=max_emis_delta,
        max_emis_delta_pct=max_emis_delta_pct,
        max_emissions_scenario=max_emissions_scenario,
        min_construction_cost_text=min_construction_cost_text,
        min_construction_cost_scenario=min_construction_cost_scenario,
        min_embodied_text=min_embodied_text,
        min_embodied_intensity_text=min_embodied_intensity_text,
        min_embodied_scenario=min_embodied_scenario,
        lowest_cost_payback_text=lowest_cost_payback_text,
        lowest_cost_payback_scenario=lowest_cost_payback_scenario,
        lowest_carbon_payback_text=lowest_carbon_payback_text,
        lowest_carbon_payback_scenario=lowest_carbon_payback_scenario,
        spider_table_rows=spider_table_rows,
        baseline_cost_w=baseline_cost_w,
        b=b,
        best_cost_w=best_cost_w,
        max_savings=max_savings,
        baseline_emis_w=baseline_emis_w,
        best_emis_w=best_emis_w,
        max_emissions_reduction=max_emissions_reduction,
        cost_payback_chart_rows=cost_payback_chart_rows,
        carbon_payback_chart_rows=carbon_payback_chart_rows,
        material_list_section_html=material_list_section_html,
        material_comparison_section_html=material_comparison_section_html,
        generated_time=generated_time,
        report_year=report_year,
        run_name=run_name,
        spider_chart_embed_html=spider_chart_html,
        result_summary_pie_charts_html=result_summary_pie_charts_html,

    )
    # Normalize section order: keep a single Material List block and place it right before Result Summary.
    material_list_marker = "<div class='section'><h2>Material List</h2>"
    result_summary_marker = "<h2>Result Summary</h2>"
    ml_sections = []
    search_from = 0
    while True:
        start = html.find(material_list_marker, search_from)
        if start == -1:
            break

        end = html.find("</table></div>", start)
        if end == -1:
            break

        end += len("</table></div>")
        ml_sections.append((start, end))
        search_from = end

    if ml_sections:
        material_list_html = html[ml_sections[-1][0]:ml_sections[-1][1]]
        for start, end in reversed(ml_sections):
            html = html[:start] + html[end:]

        result_summary_idx = html.find(result_summary_marker)
        if result_summary_idx != -1:
            html = html[:result_summary_idx] + material_list_html + "\n\n        " + html[result_summary_idx:]

        else:
            footer_idx = html.find('<div class="footer">')
            if footer_idx != -1:
                html = html[:footer_idx] + material_list_html + "\n\n        " + html[footer_idx:]

    html = html.replace("kgCO2e", "kg CO2e").replace("CO2", "CO<sub>2</sub>")
    html_report_path.write_text(html, encoding="utf-8")
    return html_report_path

# --- Legacy Filename Wrapper Status ---
# Compatibility wrapper disabled: workflow now uses only SCOPE report filenames.
print("Legacy filename compatibility wrapper is disabled.")

# --- HTML Report Generation Execution ---
# Execute report generation (kept separate from function definitions).
import re
from html import unescape

base_dir = Path(base_run_dir)
args_csv_path = base_dir / "scenario_user_arguments.csv"
if not args_csv_path.exists() and 'export_scenario_user_arguments_csv' in globals():
    scenarios_for_export = globals().get('scenarios')
    if scenarios_for_export is None:
        scenarios_for_export = generate_scenarios(cities=CITIES, building_types=BUILDING_TYPES, custom_combos=CUSTOM_COMBOS)
    export_scenario_user_arguments_csv(
        base_run_dir=str(base_dir),
        scenarios=scenarios_for_export,
        ec3_api_token=EC3_API_TOKEN,
    )
elif not args_csv_path.exists():
    print(f"Warning: scenario_user_arguments.csv not found in {base_dir} and export function is unavailable.")
csv_candidates = [
    base_dir / "parameter_results.csv",
    base_dir / "parametric_results.csv",
]
csv_path = next((p for p in csv_candidates if p.exists()), None)
if csv_path is None:
    raise FileNotFoundError(f"Could not find CSV in: {csv_candidates}")

df_report = pd.read_csv(csv_path)
html_output_path = base_dir / "SCOPE_retrofit_measure_analysis_report.html"
out = generate_html_report(df_report, html_output_path, run_name=RUN_NAME)
legacy_main_html = base_dir / 'parametric_report.html'
if legacy_main_html.exists() and legacy_main_html != html_output_path:
    legacy_main_html.unlink()

def _format_metric_value_for_threshold(val):
    if abs(val) >= 10:
        return f"{val:,.0f}"
    return f"{val:,.2f}"

def _patch_min_embodied_metric(report_path):
    html = report_path.read_text(encoding="utf-8")
    pattern = r'(<div class="metric-label">Min Embodied Carbon Scenario</div>\s*<div class="metric-value">)([0-9,]+(?:\.[0-9]+)?)(\s*kgCO2e</div>)'
    def _repl(m):
        raw = float(m.group(2).replace(",", ""))
        return m.group(1) + _format_metric_value_for_threshold(raw) + m.group(3)
    patched = re.sub(pattern, _repl, html)
    report_path.write_text(patched, encoding="utf-8")

def _first_non_empty(series):
    vals = series.dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    return vals.iloc[0] if not vals.empty else None

def _derive_building_information(df):
    weather_file = None
    building_name = None
    building_location = None
    floor_area_text = "N/A"
    for col in ["weather_file", "epw_file", "epw_filename", "epw_name"]:
        if col in df.columns:
            raw_weather_file = _first_non_empty(df[col])
            if raw_weather_file:
                weather_file = Path(str(raw_weather_file)).name
                break

    if weather_file is None:
        city_for_weather = None
        for col in ["city", "building_city", "location_city"]:
            if col in df.columns:
                city_for_weather = _first_non_empty(df[col])
                if city_for_weather:
                    break

        if city_for_weather is None:
            city_for_weather = str(globals().get("city", "")).strip() or None

        if city_for_weather and "get_city_weather_files" in globals():
            weather_files = get_city_weather_files(city_for_weather, globals().get("base_weather_path", ""))
            if weather_files and weather_files.get("epw"):
                weather_file = Path(str(weather_files["epw"])).name
    if weather_file is None:
        weather_file = "N/A"

    for col in ["building_name", "building_type", "building"]:
        if col in df.columns:
            building_name = _first_non_empty(df[col])
            if building_name:
                break
    if building_name is None:
        building_name = str(globals().get("building_type", "N/A"))

    # Build location as 'city, state' when possible.
    city_name = None
    for col in ["city", "building_city", "location_city"]:
        if col in df.columns:
            city_name = _first_non_empty(df[col])
            if city_name:
                break
    if city_name is None:
        city_name = str(globals().get("city", "")).strip() or None

    state_code = None
    for col in ["state", "state_code", "province_state", "location_state", "region"]:
        if col in df.columns:
            state_code = _first_non_empty(df[col])
            if state_code:
                break

    if state_code is None and weather_file and weather_file != "N/A":
        state_match = re.search(r"(?:^|[_-])([A-Z]{2})(?:[_-])", str(weather_file))
        if state_match:
            state_code = state_match.group(1)

    if city_name and state_code:
        building_location = f"{city_name}, {state_code}"
    elif city_name:
        building_location = city_name
    elif state_code:
        building_location = state_code
    else:
        building_location = "N/A"

    area_columns = [
        ("building_area_m2", "m<sup>2</sup>"),
        ("total_floor_area_m2", "m<sup>2</sup>"),
        ("floor_area_m2", "m<sup>2</sup>"),
        ("building_floor_area_m2", "m<sup>2</sup>"),
        ("total_floor_area_ft2", "ft<sup>2</sup>"),
        ("floor_area_ft2", "ft<sup>2</sup>"),
        ("building_floor_area_ft2", "ft<sup>2</sup>"),
    ]
    for col, unit in area_columns:
        if col in df.columns:
            area_vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if not area_vals.empty:
                area_value = float(area_vals.iloc[0])
                floor_area_text = f"{area_value:,.0f} {unit}"
                break

    return {
        "weather_file": weather_file,
        "building_name": building_name or "N/A",
        "building_location": building_location or "N/A",
        "floor_area": floor_area_text,
    }

def _patch_building_information(report_path, info):
    html = report_path.read_text(encoding="utf-8")
    # Remove existing section first so reruns do not duplicate it.
    html = re.sub(
        r'<div class="section">\s*<h[23]>Building Information</h[23]>.*?</div>\s*',
        "",
        html,
        flags=re.DOTALL,
    )
    building_section_html = (
        "\n        <div class=\"section\">"
        "\n            <h3>Building Information</h3>"
        "\n            <div class=\"summary-box\">"
        "\n                <ul style=\"margin:8px 0 0 20px;padding:0;list-style-type:disc;\">"
        f"\n                    <li>Weather File: {info['weather_file']}</li>"
        f"\n                    <li>Building Name: {info['building_name']}</li>"
        f"\n                    <li>Building Location: {info['building_location']}</li>"
        f"\n                    <li>Total Floor Area: {info['floor_area']}</li>"
        "\n                </ul>"
        "\n            </div>"
        "\n        </div>\n"
    )
    # Insert inside Executive Summary, above Renovation Details by Scenario.
    html, count = re.subn(
        r'(\s*<h3>Renovation Details by Scenario</h3>)',
        building_section_html + r'\1',
        html,
        count=1,
        flags=re.DOTALL,
    )
    if count == 0:
        # Fallback for templates without the Renovation Details heading.
        html, count = re.subn(
            r'(<h2>Executive Summary</h2>.*?<div class="summary-box">.*?</div>\s*)(<table>)',
            r'\1' + building_section_html + r'\2',
            html,
            count=1,
            flags=re.DOTALL,
        )

    if count == 0:
        # Final fallback placement near top if template structure changes significantly.
        html = re.sub(
            r'(<div class="header">.*?</div>)',
            r'\1' + building_section_html,
            html,
            count=1,
            flags=re.DOTALL,
        )

    report_path.write_text(html, encoding="utf-8")

def _patch_report_headings(report_path):
    html = report_path.read_text(encoding="utf-8")
    html = html.replace("<h2>Energy Analysis</h2>", "<h2>Annual Energy Analysis</h2>")
    html = html.replace("<h2>Building Information</h2>", "<h3>Building Information</h3>")
    report_path.write_text(html, encoding="utf-8")

def _normalize_renovation_table(report_path):
    html = report_path.read_text(encoding="utf-8")
    # Keep rich outcome wording generated from summary notes.
    has_rich_old_format = "Requested options:" in html and "Status:" in html and "Summary:" in html
    has_rich_new_format = "Requested:" in html and "Outcome:" in html and "Details:" in html
    has_rich_compact_format = "Requested:" in html and "Outcome:" in html and "Key points:" in html
    has_action_list_format = "reno-action-list" in html
    if has_rich_old_format or has_rich_new_format or has_rich_compact_format or has_action_list_format:
        return
    table_pattern = r'(<table class="renovation-table">\s*<tr><th>Scenario</th><th>Renovation Type</th><th>Renovation Details</th></tr>)(.*?)(</table>)'
    table_match = re.search(table_pattern, html, flags=re.DOTALL)
    if not table_match:
        return

    table_head = table_match.group(1)
    table_rows = table_match.group(2)
    table_tail = table_match.group(3)
    row_pattern = r'<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>'
    rows = re.findall(row_pattern, table_rows, flags=re.DOTALL)
    if not rows:
        return

    def _strip_tags(text):
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = unescape(clean)
        return re.sub(r"\s+", " ", clean).strip()

    def _extract_param(raw_text, key):
        m = re.search(rf"{re.escape(key)}\s*=\s*([^;,]+)", raw_text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None

    normalized_rows = []
    for scenario_html, reno_type_html, details_html in rows:
        original_type = _strip_tags(reno_type_html).lower()
        details_plain = _strip_tags(details_html)
        details_lower = details_plain.lower()
        if original_type != "unknown":
            normalized_rows.append((scenario_html, reno_type_html, details_html))
            continue

        if "baseline" in details_lower:
            normalized_rows.append((scenario_html, "baseline", "Baseline (no envelope renovation)"))
            continue

        parts = []
        types = []
        wall_match = re.search(r"wall insulation improved to r-?\s*([0-9.]+)\s*using\s*([^;]+)", details_plain, flags=re.IGNORECASE)
        if wall_match:
            types.append("wall")
            wall_r = wall_match.group(1).strip()
            wall_mat = wall_match.group(2).strip()
            parts.append(f"<div><strong>Wall upgrade:</strong> Exterior walls were upgraded to R-{wall_r} with {wall_mat} insulation.</div>")
        elif "wall" in details_lower:
            types.append("wall")
            parts.append("<div><strong>Wall upgrade:</strong> Exterior wall insulation was upgraded.</div>")

        roof_match = re.search(r"roof insulation improved to r-?\s*([0-9.]+)\s*using\s*([^;]+)", details_plain, flags=re.IGNORECASE)
        if roof_match:
            types.append("roof")
            roof_r = roof_match.group(1).strip()
            roof_mat = roof_match.group(2).strip()
            parts.append(f"<div><strong>Roof upgrade:</strong> The roof was upgraded to R-{roof_r} using {roof_mat} insulation.</div>")
        elif "roof" in details_lower:
            types.append("roof")
            parts.append("<div><strong>Roof upgrade:</strong> Roof insulation was upgraded.</div>")

        if "window" in details_lower:
            types.append("window")
            window_bullets = []
            pane_match = re.search(r"(\d+)-pane", details_plain, flags=re.IGNORECASE)
            if pane_match:
                window_bullets.append(f"Upgraded to {pane_match.group(1)}-pane glazing")
            win_infil_match = re.search(r"infiltration reduction(?:\s+set\s+to)?\s*([0-9.]+)%", details_plain, flags=re.IGNORECASE)
            if win_infil_match:
                window_bullets.append(f"Infiltration reduction: {win_infil_match.group(1)}%")
            weatherstrip = _extract_param(details_plain, "weatherstrip_option")
            if weatherstrip:
                window_bullets.append(f"Weatherstripping: {weatherstrip}")
            film = _extract_param(details_plain, "film_option")
            if film:
                window_bullets.append(f"Glazing film: {film}")
            frame = _extract_param(details_plain, "wf_option")
            if frame:
                window_bullets.append(f"Window frame: {frame}")
            if window_bullets:
                bullet_html = "".join(f"<li>{item}</li>" for item in window_bullets)
                parts.append("<div><strong>Window upgrade:</strong><ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>" + bullet_html + "</ul></div>")
            else:
                parts.append("<div><strong>Window upgrade:</strong> Window upgrades were applied.</div>")

        if "door" in details_lower:
            types.append("door")
            door_bullets = []
            door_type_match = re.search(r"door system upgraded\s*\(([^)]+)\)", details_plain, flags=re.IGNORECASE)
            if door_type_match:
                door_bullets.append(f"Door type: {door_type_match.group(1).strip()}")
            door_infil_match = re.search(r"infiltration reduction(?:\s+set\s+to)?\s*([0-9.]+)%", details_plain, flags=re.IGNORECASE)
            if door_infil_match:
                door_bullets.append(f"Infiltration reduction: {door_infil_match.group(1)}%")
            if door_bullets:
                bullet_html = "".join(f"<li>{item}</li>" for item in door_bullets)
                parts.append("<div><strong>Door upgrade:</strong><ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>" + bullet_html + "</ul></div>")
            else:
                parts.append("<div><strong>Door upgrade:</strong> Door upgrades were applied.</div>")

        normalized_type = " + ".join(types) if types else "unknown"
        normalized_details = "".join(parts) if parts else details_html
        normalized_rows.append((scenario_html, normalized_type, normalized_details))

    normalized_rows_html = "".join(
        f"<tr><td>{scenario}</td><td>{rtype}</td><td>{details}</td></tr>"
        for scenario, rtype, details in normalized_rows
    )
    normalized_table = table_head + normalized_rows_html + table_tail
    html = html[:table_match.start()] + normalized_table + html[table_match.end():]
    report_path.write_text(html, encoding="utf-8")

building_info = _derive_building_information(df_report)

_patch_min_embodied_metric(out)
_patch_building_information(out, building_info)
_patch_report_headings(out)
_normalize_renovation_table(out)

print(f"HTML report generated: {out}")

# --- Granular Renovation Notice Patching ---
# Enforce granular execution notices without erasing successful renovation details.
import re
from html import unescape

def _build_report_scenario_display_map(df):
    scenario_col = "scenario" if "scenario" in df.columns else "scenario_name"
    tmp = df.copy()
    baseline_first_mask = tmp[scenario_col].astype(str).str.contains("baseline", case=False, na=False)
    tmp = pd.concat([tmp[baseline_first_mask], tmp[~baseline_first_mask]], ignore_index=True)
    mapping = {}
    counter = 1
    for name in tmp[scenario_col].astype(str).tolist():
        if "baseline" in name.lower():
            mapping[name] = "Baseline"
        elif name not in mapping:
            mapping[name] = f"Scenario {counter}"
            counter += 1
    return mapping

def _strip_tags(text):
    clean = re.sub(r"<[^>]+>", " ", str(text))
    clean = unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()

def _load_args_df(base_dir):
    args_path = base_dir / "scenario_user_arguments.csv"
    if not args_path.exists():
        return None
    args_df = pd.read_csv(args_path)
    for col in ["scenario", "measure", "argument", "value"]:
        if col in args_df.columns:
            args_df[col] = args_df[col].astype(str)
    return args_df

def _arg_value(args_df, scenario_name, measure_name, argument_name):
    if args_df is None:
        return None
    subset = args_df[
        (args_df["scenario"] == str(scenario_name))
        & (args_df["measure"] == str(measure_name))
        & (args_df["argument"] == str(argument_name))
    ]
    if subset.empty:
        return None
    return str(subset.iloc[0]["value"])

def _is_meaningful_option(val):
    if val is None:
        return False
    s = str(val).strip().lower()
    return s not in {"", "none", "nan", "null", "not_applied", "not applied"}

def _to_float_or_none(val):
    try:
        return float(str(val).strip())
    except Exception:
        return None

def _clean_summary_note_text(note):
    if note is None:
        return None
    text = _strip_tags(str(note))
    text = text.replace('&#59;', ';').replace('&#44;', ',').strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text

def _collect_summary_notes_by_scenario(df):
    if df is None or len(df) == 0:
        return {}

    scenario_col = "scenario" if "scenario" in df.columns else ("scenario_name" if "scenario_name" in df.columns else None)
    if scenario_col is None:
        return {}

    col_candidates = {
        "window": ["window_summary_notes"],
        "door": ["door_summary_notes"],
        "roof": ["roof_summary_notes", "roof_insulation_summary_notes"],
        "wall": ["wall_summary_notes", "wall_insulation_summary_notes"],
    }
    measure_cols = {}
    for measure, candidates in col_candidates.items():
        for col in candidates:
            if col in df.columns:
                measure_cols[measure] = col
                break

    if not measure_cols:
        return {}

    mapping = {}
    for _, row in df.iterrows():
        scenario_name = str(row.get(scenario_col, "")).strip()
        if not scenario_name:
            continue
        scenario_notes = {}
        for measure, col in measure_cols.items():
            note = _clean_summary_note_text(row.get(col))
            if note:
                scenario_notes[measure] = note
        if scenario_notes:
            mapping[scenario_name] = scenario_notes
    return mapping

def _clean_option_value(val):
    if not _is_meaningful_option(val):
        return None
    raw = re.sub(r"\s+", " ", str(val).replace("_", " ").strip())
    key = raw.lower()
    friendly_map = {
        "provide user num panes": "custom pane count",
        "wf wood": "wood frame",
        "wf vinyl": "vinyl frame",
        "wf aluminum": "aluminum frame",
    }
    return friendly_map.get(key, raw)

def _fmt_panes(val):
    if val is None or val <= 0:
        return None
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}-pane"
    return f"{val:g}-pane"

def _join_requested_details(*details):
    clean_details = [d for d in details if d]
    if not clean_details:
        return ""
    return ", ".join(clean_details)

def _remove_old_generated_notes(details_html):
    # Remove prior auto-generated notes so reruns are idempotent and clean.
    stale_prefixes = [
        "Window construction is a SimpleGlazing object;",
        "Glass pane replacement:",
        "Glass pane replacement applied:",
        "Glass pane replacement was not applied",
        "Glass pane replacement completed",
        "Glass pane upgrade skipped",
        "Glass pane upgrade completed",
        "Window frame replacement:",
        "Window frame replacement applied:",
        "Window frame replacement completed",
        "Installed window frame:",
        "Caulking:",
        "Caulking applied:",
        "Caulking completed",
        "Applied caulking:",
        "Glazing film:",
        "Glazing film applied:",
        "Glazing film completed",
        "Applied glazing film:",
        "Weatherstripping:",
        "Weatherstripping applied:",
        "Weatherstripping completed",
        "Applied weatherstripping:",
        "Secondary glazing:",
        "Secondary glazing applied:",
        "Secondary glazing was not applied",
        "Secondary glazing completed",
        "Secondary glazing skipped",
        "Some requested wall renovation actions were not applied.",
        "Some requested roof renovation actions were not applied.",
        "Some requested door renovation actions were not applied.",
        "Wall insulation retrofit:",
        "Roof insulation retrofit:",
        "Door retrofit:",
        "Wall insulation retrofit completed.",
        "Roof insulation retrofit completed.",
        "Door retrofit completed.",
        "Wall insulation upgrade",
        "Roof insulation upgrade",
        "Door retrofit",
    ]
    cleaned = details_html
    for prefix in stale_prefixes:
        cleaned = re.sub(
            rf"<li>\s*{re.escape(prefix)}.*?</li>",
            "",
            cleaned,
            flags=re.DOTALL,
        )

    # Remove empty lists left after cleanup.
    cleaned = re.sub(
        r"<ul[^>]*>\s*</ul>",
        "",
        cleaned,
        flags=re.DOTALL,
    )
    return cleaned

def _extract_measure_section_text(details_html, measure_label):
    m = re.search(rf"<div><strong>{re.escape(measure_label)}:</strong>(.*?)</div>", str(details_html), flags=re.DOTALL)
    if not m:
        return ""
    return _strip_tags(m.group(1)).lower()

def _append_bulleted_notes(details_html, measure_label, notes):
    # Append only missing notes; keep all existing success details intact.
    if not notes:
        return details_html

    measure_pattern = rf'(<div><strong>{re.escape(measure_label)}:</strong>)(.*?)(</div>)'
    m = re.search(measure_pattern, details_html, flags=re.DOTALL)
    if m:
        body = m.group(2)
        body_text = _strip_tags(body)
        missing_notes = [n for n in notes if n not in body_text]
        if not missing_notes:
            return details_html

        if "<ul" in body and "</ul>" in body:
            new_items = "".join(f"<li>{n}</li>" for n in missing_notes)
            new_body = re.sub(r"</ul>", new_items + "</ul>", body, count=1, flags=re.DOTALL)
        else:
            base_note = _strip_tags(body)
            merged = []
            if base_note:
                merged.append(base_note)
            merged.extend(missing_notes)
            bullet_html = "".join(f"<li>{n}</li>" for n in merged)
            new_body = f"<ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>{bullet_html}</ul>"

        return details_html[:m.start(2)] + new_body + details_html[m.end(2):]

    bullet_html = "".join(f"<li>{n}</li>" for n in notes)
    return (
        details_html
        + f"<div><strong>{measure_label}:</strong>"
        + f"<ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>{bullet_html}</ul></div>"
    )

def _derive_window_submeasure_notes(scenario_name, details_html, args_df, simple_glazing_failed_scenarios):
    notes = []
    user_num_panes = _to_float_or_none(_arg_value(args_df, scenario_name, "window", "user_num_panes"))
    glass_option = _arg_value(args_df, scenario_name, "window", "glass_option")
    wf_option = _arg_value(args_df, scenario_name, "window", "wf_option")
    caulking_option = _arg_value(args_df, scenario_name, "window", "caulking_option")
    film_option = _arg_value(args_df, scenario_name, "window", "film_option")
    weatherstrip_option = _arg_value(args_df, scenario_name, "window", "weatherstrip_option")
    secondary_option = _arg_value(args_df, scenario_name, "window", "secondary_glazing_option")
    simple_glazing_blocked = scenario_name in simple_glazing_failed_scenarios
    glass_requested = (user_num_panes is not None and user_num_panes > 0) or _is_meaningful_option(glass_option)
    frame_requested = _is_meaningful_option(wf_option)
    caulking_requested = _is_meaningful_option(caulking_option)
    film_requested = _is_meaningful_option(film_option)
    weatherstrip_requested = _is_meaningful_option(weatherstrip_option)
    secondary_requested = _is_meaningful_option(secondary_option)
    panes_detail = _fmt_panes(user_num_panes)
    glass_detail = _clean_option_value(glass_option)
    frame_detail = _clean_option_value(wf_option)
    caulking_detail = _clean_option_value(caulking_option)
    film_detail = _clean_option_value(film_option)
    weatherstrip_detail = _clean_option_value(weatherstrip_option)
    secondary_detail = _clean_option_value(secondary_option)
    if glass_requested:
        requested_details = _join_requested_details(panes_detail, glass_detail)
        if simple_glazing_blocked:
            if requested_details:
                notes.append(
                    "Glass pane upgrade skipped because SimpleGlazing does not support pane replacement "
                    + f"(requested: {requested_details})."
                )
            else:
                notes.append("Glass pane upgrade skipped because SimpleGlazing does not support pane replacement.")
        else:
            if requested_details:
                notes.append(f"Glass pane upgrade completed ({requested_details}).")
            else:
                notes.append("Glass pane upgrade completed.")

    if frame_requested:
        if frame_detail:
            notes.append(f"Installed window frame: {frame_detail}.")
        else:
            notes.append("Window frame upgrade completed.")

    if caulking_requested:
        if caulking_detail:
            notes.append(f"Applied caulking: {caulking_detail}.")
        else:
            notes.append("Caulking completed.")

    if film_requested:
        if film_detail:
            notes.append(f"Applied glazing film: {film_detail}.")
        else:
            notes.append("Glazing film completed.")

    if weatherstrip_requested:
        if weatherstrip_detail:
            notes.append(f"Applied weatherstripping: {weatherstrip_detail}.")
        else:
            notes.append("Weatherstripping completed.")

    if secondary_requested:
        if simple_glazing_blocked:
            if secondary_detail:
                notes.append(
                    "Secondary glazing skipped because it is not supported for SimpleGlazing "
                    + f"(requested: {secondary_detail})."
                )
            else:
                notes.append("Secondary glazing skipped because it is not supported for SimpleGlazing.")
        else:
            if secondary_detail:
                notes.append(f"Secondary glazing completed ({secondary_detail}).")
            else:
                notes.append("Secondary glazing completed.")

    return notes

def _derive_measure_level_notes(scenario_name, details_html, args_df, measure, label):
    status = _arg_value(args_df, scenario_name, measure, "__status__")
    if status != "applied":
        return []

    section_text = _extract_measure_section_text(details_html, label)
    failed_keywords = ["failed", "not applied", "unable to"]
    if section_text and any(k in section_text for k in failed_keywords):
        if measure == "wall":
            return ["Wall insulation upgrade partially completed (see run logs for details)."]
        if measure == "roof":
            return ["Roof insulation upgrade partially completed (see run logs for details)."]
        if measure == "door":
            return ["Door retrofit partially completed (see run logs for details)."]

    # If section exists and no failure signal, mark applied.
    if section_text:
        if measure == "wall":
            return ["Wall insulation upgrade completed."]
        if measure == "roof":
            return ["Roof insulation upgrade completed."]
        if measure == "door":
            return ["Door retrofit completed."]

    # Requested but not explicitly visible in report details.
    if measure == "wall":
        return ["Wall insulation upgrade was requested, but no explicit outcome was recorded."]
    if measure == "roof":
        return ["Roof insulation upgrade was requested, but no explicit outcome was recorded."]
    if measure == "door":
        return ["Door retrofit was requested, but no explicit outcome was recorded."]

    return []

def _enforce_granular_execution_notices(report_path, scenario_map, args_df, simple_glazing_failed_scenarios, summary_notes_by_scenario):
    if not report_path.exists():
        return

    inverse_map = {v: k for k, v in scenario_map.items()}
    html = report_path.read_text(encoding="utf-8")
    table_pattern = (
        r'(<table[^>]*>.*?<tr>\s*<th>\s*Scenario\s*</th>\s*<th>\s*Renovation Type\s*</th>'
        r'\s*<th>\s*Renovation Details\s*</th>\s*</tr>)(.*?)(</table>)'
    )
    table_match = re.search(table_pattern, html, flags=re.DOTALL)
    if not table_match:
        return

    table_head = table_match.group(1)
    table_rows = table_match.group(2)
    table_tail = table_match.group(3)
    row_pattern = r'<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>'
    rows = re.findall(row_pattern, table_rows, flags=re.DOTALL)
    if not rows:
        return

    new_rows = []
    for scenario_html, reno_type_html, details_html in rows:
        has_rich_old_format = "Requested options:" in details_html and "Status:" in details_html and "Summary:" in details_html
        has_rich_new_format = "Requested:" in details_html and "Outcome:" in details_html and "Details:" in details_html
        has_rich_compact_format = "Requested:" in details_html and "Outcome:" in details_html and "Key points:" in details_html
        has_action_list_format = "reno-action-list" in details_html
        if has_rich_old_format or has_rich_new_format or has_rich_compact_format or has_action_list_format:
            new_rows.append(f"<tr><td>{scenario_html}</td><td>{reno_type_html}</td><td>{details_html}</td></tr>")
            continue

        scenario_label = _strip_tags(scenario_html)
        scenario_name = inverse_map.get(scenario_label)
        details_html = _remove_old_generated_notes(details_html)
        if scenario_name:
            scenario_summary_notes = summary_notes_by_scenario.get(scenario_name, {})
            # Window sub-measure level notes
            window_status = _arg_value(args_df, scenario_name, "window", "__status__")
            if window_status == "applied":
                if "window" in scenario_summary_notes:
                    window_notes = [scenario_summary_notes["window"]]
                else:
                    window_notes = _derive_window_submeasure_notes(
                        scenario_name,
                        details_html,
                        args_df,
                        simple_glazing_failed_scenarios,
                    )
                details_html = _append_bulleted_notes(details_html, "Window upgrade", window_notes)

            # Other measure-level notes
            wall_notes = [scenario_summary_notes["wall"]] if "wall" in scenario_summary_notes else _derive_measure_level_notes(scenario_name, details_html, args_df, "wall", "Wall upgrade")
            roof_notes = [scenario_summary_notes["roof"]] if "roof" in scenario_summary_notes else _derive_measure_level_notes(scenario_name, details_html, args_df, "roof", "Roof upgrade")
            door_notes = [scenario_summary_notes["door"]] if "door" in scenario_summary_notes else _derive_measure_level_notes(scenario_name, details_html, args_df, "door", "Door upgrade")
            details_html = _append_bulleted_notes(details_html, "Wall upgrade", wall_notes)
            details_html = _append_bulleted_notes(details_html, "Roof upgrade", roof_notes)
            details_html = _append_bulleted_notes(details_html, "Door upgrade", door_notes)

        new_rows.append(f"<tr><td>{scenario_html}</td><td>{reno_type_html}</td><td>{details_html}</td></tr>")

    new_table = table_head + "".join(new_rows) + table_tail
    html = html[:table_match.start()] + new_table + html[table_match.end():]
    report_path.write_text(html, encoding="utf-8")

scenario_display_map_for_patch = _build_report_scenario_display_map(df_report)
args_df_for_patch = _load_args_df(base_dir)
summary_notes_by_scenario = _collect_summary_notes_by_scenario(df_report)

scenario_col = "scenario" if "scenario" in df_report.columns else "scenario_name"
simple_glazing_failed_scenarios = set()
if "renovation_details" in df_report.columns:
    for _, row in df_report.iterrows():
        scenario_name = str(row.get(scenario_col, ""))
        d = str(row.get("renovation_details", "")).lower()
        if "simple glazing" in d and ("failed to upgrade" in d or "unable to" in d or "not applied" in d):
            simple_glazing_failed_scenarios.add(scenario_name)

main_report_path = html_output_path

report_paths = {main_report_path}
run_dir = base_dir / "simulations" / str(RUN_NAME)
for report_name in ["SCOPE_retrofit_measure_analysis_report.html"]:
    report_paths.add(run_dir / report_name)

applied_count = 0
for report_path in report_paths:
    before = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    _enforce_granular_execution_notices(report_path, scenario_display_map_for_patch, args_df_for_patch, simple_glazing_failed_scenarios, summary_notes_by_scenario)
    after = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if before != after:
        applied_count += 1

print(f"Applied granular execution notices for renovation details. Updated {applied_count} report(s).")

# --- PDF Export ---
# Auto-export main HTML report to PDF
import subprocess
from pathlib import Path

base_dir = Path(base_run_dir)

def _detect_edge_executable():
    candidates = [
        Path(r"C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def _export_html_to_pdf(html_path, pdf_path):
    edge_path = _detect_edge_executable()
    if edge_path is None:
        print("Warning: Microsoft Edge not found; skipping PDF export.")
        return False

    html_abs = Path(html_path).resolve()
    pdf_abs = Path(pdf_path).resolve()
    cmd = [
        str(edge_path),
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_abs}",
        html_abs.as_uri(),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return pdf_abs.exists()

main_candidates = [
    base_dir / "SCOPE_retrofit_measure_analysis_report.html",
    Path.cwd() / "SCOPE_retrofit_measure_analysis_report.html",
]

main_html = next((p for p in main_candidates if p.exists()), None)

if main_html is None:
    print("Warning: Main HTML report not found; skipping main PDF export.")
else:
    main_pdf = main_html.with_suffix(".pdf")
    if _export_html_to_pdf(main_html, main_pdf):
        print(f"PDF report generated: {main_pdf}")
    else:
        print(f"Warning: Failed to generate PDF for {main_html.name}")

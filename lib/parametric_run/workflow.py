#!/usr/bin/env python3
# Auto-generated from workflow.ipynb

# Standard library

import json
import os
import subprocess
import time
from itertools import product
import re
import sys
from pathlib import Path
import configparser
import shutil
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import csv
import sqlite3

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
            window_infil = scenario_dict.get("window_infiltration_reduction_percent")
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

def summarize_renovation_details(scenario_name, wall_args=None, roof_args=None, window_args=None, door_args=None, window_upgrade_status=None):

    if scenario_name.startswith("baseline"):
        return "Baseline (no envelope renovation)"

    def fmt_value(value, unit=""):
        if value is None or value == "":
            return None
        if isinstance(value, float):
            text = f"{value:g}"
        else:
            text = str(value)
        return f"{text}{unit}" if unit else text

    def include_param(key, value):
        if value in [None, ""]:
            return False
        if "option" in str(key).lower() and str(value).strip().lower() == "none":
            return False
        return True

    details = []
    if wall_args:
        wall_r = wall_args.get("r_value")
        wall_mat = wall_args.get("insulation_material_type", "insulation material")
        details.append(f"Wall insulation improved to R-{wall_r} using {wall_mat}")

    if roof_args:
        roof_r = roof_args.get("r_value")
        roof_mat = roof_args.get("insulation_material_type", "insulation material")
        details.append(f"Roof insulation improved to R-{roof_r} using {roof_mat}")

    if window_args:
        panes = window_args.get("user_num_panes")
        infil_red = window_args.get("space_infiltration_reduction_percent")
        if window_upgrade_status == "failed_simple_glazing":
            window_main = f"Window system failed to upgrade to {panes}-pane because all window constructions are simple glazing objects; infiltration reduction set to {infil_red}%"
        elif window_upgrade_status == "requested_not_applied":
            window_main = f"Window system requested {panes}-pane upgrade but no window construction was replaced; infiltration reduction set to {infil_red}%"
        else:
            window_main = f"Window system upgraded to {panes}-pane with {infil_red}% infiltration reduction"

        window_parts = []
        for key in ["glass_option", "wf_option", "caulking_option", "film_option", "weatherstrip_option", "secondary_glazing_option"]:
            value = window_args.get(key)
            if include_param(key, value):
                window_parts.append(f"{key}={value}")

        caulking_thickness = fmt_value(window_args.get("caulking_thickness"), " m")
        if caulking_thickness:
            window_parts.append(f"caulking_thickness={caulking_thickness}")

        glass_thickness = fmt_value(window_args.get("glass_pane_thickness"), " m")
        if glass_thickness:
            window_parts.append(f"glass_pane_thickness={glass_thickness}")

        gap_thickness = fmt_value(window_args.get("gap_thickness"), " m")
        if gap_thickness:
            window_parts.append(f"gap_thickness={gap_thickness}")

        window_suffix = f"; parameters: {', '.join(window_parts)}" if window_parts else ""
        details.append(f"{window_main}{window_suffix}")

    if door_args:
        door_type = door_args.get("door_option", "door")
        infil_red = door_args.get("space_infiltration_reduction_percent")
        door_parts = []
        for key in ["door_bottom_seal_option", "door_top_side_seal_option"]:
            value = door_args.get(key)
            if include_param(key, value):
                door_parts.append(f"{key}={value}")
        door_suffix = f"; parameters: {', '.join(door_parts)}" if door_parts else ""
        details.append(f"Door system upgraded ({door_type}) with {infil_red}% infiltration reduction{door_suffix}")

    if not details:
        wall_match = re.search(r"wall_r([0-9.]+)(?:_([a-z0-9_]+?))?(?=_(?:roof_r|window_|door_|[A-Z])|$)", scenario_name)
        if wall_match:
            wall_r = wall_match.group(1)
            wall_mat = wall_match.group(2).replace("_", " ").title() if wall_match.group(2) else "Blown Fiberglass"
            details.append(f"Wall insulation improved to R-{wall_r} using {wall_mat}")
        roof_match = re.search(r"roof_r([0-9.]+)(?:_([a-z0-9_]+?))?(?=_(?:wall_r|window_|door_|[A-Z])|$)", scenario_name)
        if roof_match:
            roof_r = roof_match.group(1)
            roof_mat = roof_match.group(2).replace("_", " ").title() if roof_match.group(2) else "Blown Fiberglass"
            details.append(f"Roof insulation improved to R-{roof_r} using {roof_mat}")
        window_match = re.search(r"window_(?:num_panes|panes)([0-9]+)|window_u([0-9.]+)", scenario_name)
        if window_match:
            panes = int(window_match.group(1)) if window_match.group(1) is not None else (2 if float(window_match.group(2)) >= 0.30 else 3)
            panes = max(1, min(3, panes))
            details.append(f"Window system requested {panes}-pane upgrade with 50.0% infiltration reduction")
        door_match = re.search(r"door_(.+?)_(SmallOffice|MediumOffice|LargeOffice|SmallHotel|LargeHotel|Warehouse|RetailStandalone|RetailStripmall|PrimarySchool|SecondarySchool)_", scenario_name)
        if door_match:
            door_type = door_match.group(1).replace("_", " ")
            door_type = re.sub(r"\bd\b", "door", door_type)
            details.append(f"Door system upgraded ({door_type}) with 30.0% infiltration reduction")

    if not details:
        return "Envelope renovation applied (details not parsed)"
    return "; ".join(details)

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

def _decode_material_slug(slug, default_material):
    if not slug:
        return default_material
    material_map = {
        "blown_fiberglass": "Blown Fiberglass",
        "blown_cellulose": "Blown Cellulose",
        "blown_mineral_wool": "Blown Mineral Wool",
        "polyiso_insulation_foam_board": "Polyiso Insulation Foam Board",
        "extruded_polystyrene_xps_foam_board": "Extruded Polystyrene XPS Foam Board",
        "expanded_polystyrene_eps_foam_board": "Expanded Polystyrene EPS Foam Board",
    }
    return material_map.get(slug, slug.replace("_", " ").title())

def infer_window_args_from_scenario_name(scenario_name):

    """Infer basic window measure args from scenario name when explicit args are unavailable."""

    window_match = re.search(r"window_(?:num_panes|panes)([0-9]+)|window_u([0-9.]+)", str(scenario_name))
    if not window_match:
        return None

    panes = int(window_match.group(1)) if window_match.group(1) is not None else (2 if float(window_match.group(2)) >= 0.30 else 3)
    panes = max(1, min(3, panes))

    return {
        "user_num_panes": panes,
        "space_infiltration_reduction_percent": 0.0,
        "glass_option": "provide user_num_panes",
        "caulking_option": "none",
        "caulking_thickness": 0.0,
        "wf_option": "none",
        "film_option": "none",
        "weatherstrip_option": "none",
        "secondary_glazing_option": "none",
        "glass_pane_thickness": 0.0,
        "gap_thickness": 0.0,
        "gwp_statistic": "median",
    }

def infer_wall_args_from_scenario_name(scenario_name):
    wall_match = re.search(r"wall_r([0-9.]+)(?:_([a-z0-9_]+?))?(?=_(?:roof_r|window_|door_|[A-Z])|$)", str(scenario_name))
    if not wall_match:
        return None
    wall_material = _decode_material_slug(wall_match.group(2), "Blown Fiberglass")
    return {
        "r_value": float(wall_match.group(1)),
        "insulation_material_type": wall_material,
        "insulation_material_lifetime": 30,
        "gwp_statistic": "median",
    }

def infer_roof_args_from_scenario_name(scenario_name):
    roof_match = re.search(r"roof_r([0-9.]+)(?:_([a-z0-9_]+?))?(?=_(?:wall_r|window_|door_|[A-Z])|$)", str(scenario_name))
    if not roof_match:
        return None
    roof_material = _decode_material_slug(roof_match.group(2), "Blown Fiberglass")
    return {
        "r_value": float(roof_match.group(1)),
        "insulation_material_type": roof_material,
        "insulation_material_lifetime": 30,
        "gwp_statistic": "median",
    }

def infer_door_args_from_scenario_name(scenario_name):

    door_match = re.search(r"door_(.+?)_(SmallOffice|MediumOffice|LargeOffice|SmallHotel|LargeHotel|Warehouse|RetailStandalone|RetailStripmall|PrimarySchool|SecondarySchool)_", str(scenario_name))

    if not door_match:
        return None

    door_type = door_match.group(1).replace("_", " ")
    door_type = re.sub(r"\bd\b", "door", door_type)

    return {
        "door_option": door_type,
        "space_infiltration_reduction_percent": 0.0,
        "door_bottom_seal_option": "automatic door bottom",
        "door_top_side_seal_option": "jamb weatherstrip",
        "gwp_statistic": "median",
    }

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
        print(f"✗ {label}: timed out after 600s")
        return False

    except Exception as e:
        print(f"ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ {label}: subprocess error: {e}")
        return False

    out_osw_path = os.path.join(run_dir, "out.osw")
    if not os.path.exists(out_osw_path):
        print(f"ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ {label}: out.osw not found (OpenStudio may have crashed)")
        if result.stderr:
            print(f"   STDERR: {result.stderr[:500]}")
        return False
    with open(out_osw_path, "r") as f:
        out_osw = json.load(f)
    if out_osw.get("completed_status") != "Success":
        print(f"ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ {label}: OSW failed")
        run_log_path = os.path.join(run_dir, "run", "run.log")
        if os.path.exists(run_log_path):
            with open(run_log_path, "r") as log_f:
                for line in log_f:
                    if "ERROR" in line:
                        print(f"   ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ LOG: {line.rstrip()}")
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
            print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {label}: could not load model for reporting measure")
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
        # Arguments (none required for this measure ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â reads from CSV resources)
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        # Run
        measure.run(runner, arg_map)
        result_value = runner.result().value().valueName()

        if result_value != "Success":
            print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {label}: reporting measure result: {result_value}")
            for error in runner.result().errors():
                print(f"    ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â ERROR: {error.logMessage()}")
            return False

        # Save model with AdditionalProperties written by the reporting measure
        model.save(openstudio.toPath(str(model_path)), True)
        del model
        return True

    except Exception as e:
        print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {label}: reporting measure error: {e}")
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
            print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Could not locate weather URL field in: {osm_path}")

        return updated
    except Exception as e:
        print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Failed to enforce weather URL in {osm_path}: {e}")
        return False

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
        print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Weather files not found for {city}")
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
        print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Skipping {scenario_name} - simulation already exists")
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
    #   Phase 1  create prototype in a _proto/ subfolder
    #   Phase 2  OSW with seed_file (no measure steps) ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡ E+ simulation
    #   Phase 3  apply Python reporting measure in-process
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
            print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {scenario_name}: prototype model not found at {proto_model_path}")
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
    #   Phase 1  create prototype in a _proto/ subfolder
    #   Phase 2  apply Python model measures in-process
    #   Phase 3  OSW with seed_file (no measure steps) ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡ E+ simulation
    #   Phase 4  apply Python reporting measure in-process
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
            print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {scenario_name}: prototype model not found at {proto_model_path}")
            log_failure(f"prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)

        # --- Phase 2: apply Python model measures ---

        translator = openstudio.osversion.VersionTranslator()
        loaded_model = translator.loadModel(openstudio.toPath(final_model_path))
        if not loaded_model.is_initialized():
            print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {scenario_name}: failed to load prototype model")
            log_failure("failed to load prototype model")
            return None

        model = loaded_model.get()
        wall_args = None
        roof_args = None
        window_args = None
        door_args = None

        window_upgrade_status = None
        if scenario_dict.get("wall_r_value"):
            wall_material_type = scenario_dict.get("wall_insulation_material_type") or "Blown Fiberglass"
            wall_material_lifetime = float(scenario_dict.get("wall_insulation_material_lifetime") or 30)
            wall_args = {
                "r_value": float(scenario_dict["wall_r_value"]),
                "analysis_period": 30,
                "gwp_statistic": "median",
                "api_key": EC3_API_TOKEN or "",
                "insulation_material_type": wall_material_type,
                "insulation_material_lifetime": wall_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
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
                "api_key": EC3_API_TOKEN or "",
                "insulation_material_type": roof_material_type,
                "insulation_material_lifetime": roof_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
            }
            print(f"  Applying roof insulation (R={scenario_dict['roof_r_value']}, material={roof_material_type})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForRoofs", "IncreaseInsulationRValueForRoofs", roof_args):
                print(f"   {scenario_name}: roof measure failed")
                log_failure("roof measure failed")
                del model
                return None
        has_window_renovation = any([
            scenario_dict.get("window_num_panes"),
            scenario_dict.get("window_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario_dict.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("wf_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("film_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        if has_window_renovation:

            if EC3_API_TOKEN is None:
                print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  EC3 API token not found, skipping window enhancement")
            else:
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
                    "space_infiltration_reduction_percent": float(scenario_dict.get("window_infiltration_reduction_percent", scenario_dict.get("space_infiltration_reduction_percent", 0.0)) or 0.0),
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
                }

                print(f"  Applying window enhancement (num_panes={num_panes}, glass_option={glass_option})...")
                if not apply_python_measure(model, Path(measure_dir_path) / "window_enhancement", "WindowEnhancement", window_args):
                    print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {scenario_name}: window measure failed")
                    log_failure("window measure failed")
                    del model
                    return None

                window_upgrade_status = detect_window_upgrade_status(model, num_panes)

        has_door_renovation = any([
            scenario_dict.get("door_option"),
            scenario_dict.get("door_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario_dict.get("door_bottom_seal_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("door_top_side_seal_option", "none")).strip().lower() != "none",
        ])
        if has_door_renovation:
            if EC3_API_TOKEN is None:
                print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  EC3 API token not found, skipping door enhancement")
            else:
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
                }

                print(f"  Applying door enhancement (door={door_args['door_option']})...")
                if not apply_python_measure(model, Path(measure_dir_path) / "door_enhancement", "DoorEnhancement", door_args):
                    print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  {scenario_name}: door measure failed")
                    log_failure("door measure failed")
                    del model
                    return None

        renovation_details = summarize_renovation_details(
            scenario_name,
            wall_args=wall_args,
            roof_args=roof_args,
            window_args=window_args,
            door_args=door_args,
            window_upgrade_status=window_upgrade_status,
        )

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
    print(f"ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Completed: {scenario_name}")
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
            "window_infiltration_reduction_percent": None,
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

# =========================
# POSTPROCESS: COLLECT RESULTS
# =========================

def _read_props_to_dict(props, prefix=""):
    """Helper: read all features from an AdditionalProperties object into a dict."""
    result = {}
    for name in props.featureNames():
        val = props.getFeatureAsString(name)
        if val.is_initialized():
            v = val.get()
            try:
                result[prefix + name] = float(v)
            except ValueError:
                result[prefix + name] = v
    return result

def extract_additional_properties_from_osm(osm_path):
    """
    Extract AdditionalProperties from an OSM file.
    Reads from: Building, Site, Facility, SimulationControl, SizingParameters.
    Returns a flat dict of all found properties.
    """
    try:
        translator = openstudio.osversion.VersionTranslator()
        translator.setAllowNewerVersions(True)
        loaded_model = translator.loadModel(openstudio.toPath(str(osm_path)))
        if not loaded_model.is_initialized():
            return {}
        model = loaded_model.get()
        prop_dict = {}
        # Building ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â measure inputs (measure_name, analysis_period_years, gwp_statistic, etc.)
        prop_dict.update(_read_props_to_dict(model.getBuilding().additionalProperties()))
        prop_dict["building_area_m2"] = model.getBuilding().floorArea()
        # Site ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â reno details + operating cost/emissions from reporting measure
        prop_dict.update(_read_props_to_dict(model.getSite().additionalProperties()))
        # Facility ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â GWP factors
        prop_dict.update(_read_props_to_dict(model.getFacility().additionalProperties()))
        # SimulationControl ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â embodied carbon results
        prop_dict.update(_read_props_to_dict(model.getSimulationControl().additionalProperties()))
        # SizingParameters ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â material properties (lifetimes, densities, etc.)
        prop_dict.update(_read_props_to_dict(model.getSizingParameters().additionalProperties()))

        # Fallback: sweep all OS:AdditionalProperties objects so measure-level
        # embodied-carbon fields (eg *_embodied_carbon_kgCO2eq) are not missed.
        idd_type = openstudio.IddObjectType("OS:AdditionalProperties")
        for obj in model.getObjectsByType(idd_type):
            opt_props = openstudio.model.toAdditionalProperties(obj)
            if opt_props.is_initialized():
                prop_dict.update(_read_props_to_dict(opt_props.get()))
        del model
        return prop_dict

    except Exception as e:
        print(f"  ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€¦Ã¢â‚¬â„¢  Failed to extract properties from {osm_path}: {e}")
        return {}

def collect_results_to_csv(base_run_dir, csv_base_name="parametric_results", city_climate_zones=None):
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
        sql_path = os.path.join(scenario_path, "run", "eplusout.sql")
        if not os.path.exists(sql_path):
            continue
        scenario_parts = scenario_folder.split("_")
        is_baseline = scenario_parts[0] == "baseline"
        city = scenario_parts[-1]
        building_type = scenario_parts[-2]
        climate_zone = city_climate_zones.get(city, "") if city_climate_zones else ""
        renovation_details = summarize_renovation_details(scenario_folder)
        row = {
            "scenario_name": scenario_folder,
            "is_baseline": is_baseline,
            "city": city,
            "building_type": building_type,
            "climate_zone": climate_zone,
            "renovation_details": renovation_details,
        }

        osm_path = os.path.join(scenario_path, "run", "in.osm")
        if os.path.exists(osm_path):
            print(f"  Extracting properties from {scenario_folder}...")
            row.update(extract_additional_properties_from_osm(osm_path))
        rows.append(row)
    if not rows:
        print("\nÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã‚Â° No simulation results found.")
        return None

    df_results = pd.DataFrame(rows)
    priority_cols = ["scenario_name", "is_baseline", "city", "building_type", "climate_zone", "building_area_m2", "renovation_details"]
    existing_priority = [c for c in priority_cols if c in df_results.columns]
    remaining = sorted([c for c in df_results.columns if c not in existing_priority])
    df_results = df_results[existing_priority + remaining]
    csv_path = os.path.join(base_run_dir, f"{csv_base_name}.csv")
    df_results.to_csv(csv_path, index=False)

    print(f"\nÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€¦Ã‚Â  Results CSV: {csv_path}")
    print(f"   Total scenarios: {len(df_results)}")
    print(f"   Columns: {len(df_results.columns)}")

    return df_results

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

        print(f"    ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ Failed to read total site energy from SQL {sql_path}: {e}")

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

def extract_scenario_data(osm_path, scenario_name):

    """

    Loads an OSM and extracts target properties from AdditionalProperties.

    """

    results = {"scenario": scenario_name}

    vt = openstudio.osversion.VersionTranslator()

    model_ptr = vt.loadModel(openstudio.toPath(str(osm_path)))

    if not model_ptr.is_initialized():

        print(f"  ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢ Failed to load: {osm_path.name}")

        return None

    model = model_ptr.get()
    results["building_area_m2"] = model.getBuilding().floorArea()
    inferred_wall_args = infer_wall_args_from_scenario_name(scenario_name)
    inferred_roof_args = infer_roof_args_from_scenario_name(scenario_name)
    inferred_window_args = infer_window_args_from_scenario_name(scenario_name)
    inferred_door_args = infer_door_args_from_scenario_name(scenario_name)
    window_upgrade_status = None

    if inferred_window_args:
        window_upgrade_status = detect_window_upgrade_status(model, inferred_window_args["user_num_panes"])

    results["renovation_details"] = summarize_renovation_details(
        scenario_name,
        wall_args=inferred_wall_args,
        roof_args=inferred_roof_args,
        window_args=inferred_window_args,
        door_args=inferred_door_args,
        window_upgrade_status=window_upgrade_status,
    )

    found_any = True
    # 1. Embodied Carbon ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â SimulationControl.additionalProperties()
    sim_props = model.getSimulationControl().additionalProperties()
    ec_keys = [
        "wall_insulation_total_additional_embodied_carbon_kg",
        "roof_insulation_total_additional_embodied_carbon_kg",
        "window_enhancement_total_additional_embodied_carbon_kg",
        "door_enhancement_total_additional_embodied_carbon_kg",
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

    # Normalize newer embodied-carbon keys to legacy recap columns
    # expected by downstream tables/charts.
    ec_legacy_map = {
        "wall_insulation_embodied_carbon_kgCO2eq": "wall_insulation_total_additional_embodied_carbon_kg",
        "roof_insulation_embodied_carbon_kgCO2eq": "roof_insulation_total_additional_embodied_carbon_kg",
        "window_enhancement_embodied_carbon_kgCO2eq": "window_enhancement_total_additional_embodied_carbon_kg",
        "door_enhancement_embodied_carbon_kgCO2eq": "door_enhancement_total_additional_embodied_carbon_kg",
    }
    for new_key, legacy_key in ec_legacy_map.items():
        if legacy_key in results:
            continue
        if new_key in results:
            results[legacy_key] = results[new_key]

    # Convenience aggregate for analysis widgets.
    if "total_additional_embodied_carbon_kg" not in results:
        total_embodied = (
            float(results.get("wall_insulation_total_additional_embodied_carbon_kg", 0.0) or 0.0)
            + float(results.get("roof_insulation_total_additional_embodied_carbon_kg", 0.0) or 0.0)
            + float(results.get("window_enhancement_total_additional_embodied_carbon_kg", 0.0) or 0.0)
            + float(results.get("door_enhancement_total_additional_embodied_carbon_kg", 0.0) or 0.0)
        )
        results["total_additional_embodied_carbon_kg"] = total_embodied

    # 2. Operating Cost and Emissions ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Site.additionalProperties()
    site_props = model.getSite().additionalProperties()
    facility_props = model.getFacility().additionalProperties()
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
        "wall_insulation_total_additional_material_cost_$": "wall_insulation_total_additional_material_cost_usd",
        "wall_insulation_total_additional_labour_cost_$": "wall_insulation_total_additional_labour_cost_usd",
        "wall_insulation_total_additional_overhead_profit_cost_$": "wall_insulation_total_additional_overhead_profit_cost_usd",
        "wall_insulation_total_cost_with_overhead_and_profit_$": "wall_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_total_additional_material_cost_$": "roof_insulation_total_additional_material_cost_usd",
        "roof_insulation_total_additional_installed_cost_$": "roof_insulation_total_additional_installed_cost_usd",
        "roof_insulation_total_additional_overhead_profit_cost_$": "roof_insulation_total_additional_overhead_profit_cost_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_$": "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "window_enhancement_total_additional_material_cost_$": "window_enhancement_total_additional_material_cost_usd",
        "window_enhancement_total_additional_labour_cost_$": "window_enhancement_total_additional_labour_cost_usd",
        "window_enhancement_total_additional_overhead_profit_cost_$": "window_enhancement_total_additional_overhead_profit_cost_usd",
        "door_enhancement_total_additional_material_cost_$": "door_enhancement_total_additional_material_cost_usd",
        "door_enhancement_total_additional_labour_cost_$": "door_enhancement_total_additional_labour_cost_usd",
        "door_enhancement_total_additional_overhead_profit_cost_$": "door_enhancement_total_additional_overhead_profit_cost_usd",
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

    # Prefer already-computed measure totals when available.
    # If missing, fall back to component sums.
    wall_total = float(results.get("wall_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    roof_total = float(results.get("roof_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    if wall_total <= 0.0:
        wall_total = (
            float(results.get("wall_insulation_total_additional_material_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_total_additional_labour_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_total_additional_overhead_profit_cost_usd", 0.0) or 0.0)
        )
    if roof_total <= 0.0:
        roof_total = (
            float(results.get("roof_insulation_total_additional_installed_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_total_additional_overhead_profit_cost_usd", 0.0) or 0.0)
        )

    window_total = (
        float(results.get("window_enhancement_total_additional_material_cost_usd", 0.0) or 0.0)
        + float(results.get("window_enhancement_total_additional_labour_cost_usd", 0.0) or 0.0)
        + float(results.get("window_enhancement_total_additional_overhead_profit_cost_usd", 0.0) or 0.0)
    )
    door_total = (
        float(results.get("door_enhancement_total_additional_material_cost_usd", 0.0) or 0.0)
        + float(results.get("door_enhancement_total_additional_labour_cost_usd", 0.0) or 0.0)
        + float(results.get("door_enhancement_total_additional_overhead_profit_cost_usd", 0.0) or 0.0)
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
        "roof_insulation_renovated_area_m2",
        "wall_insulation_renovated_volume_m3",
        "roof_insulation_renovated_volume_m3",
        "wall_insulation_summary_notes",
        "roof_insulation_summary_notes",
        "window_enhancement_summary_notes",
        "door_enhancement_summary_notes",
        "total_renovated_wall_insulation_area_m2",
        "total_renovated_roof_insulation_area_m2",
        "total_renovated_wall_insulation_volume_m3",
        "total_renovated_roof_insulation_volume_m3",
        "total_renovated_window_area_m2",
        "total_renovated_glazing_area_m2",
        "total_renovated_frame_area_m2",
        "total_renovated_perimeter_m",
        "total_renovated_caulking_volume_m3",
        "total_renovated_weatherstrip_length_m",
        "total_renovated_door_area_m2",
        "total_renovated_sealing_bottom_length_m",
        "total_renovated_sealing_side_length_m",
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
        full_props = extract_additional_properties_from_osm(osm_path)
        if data is None:
            data = {"scenario": scenario}
        if full_props:
            data.update(full_props)
        if "renovation_details" not in data or not str(data.get("renovation_details", "")).strip():
            data["renovation_details"] = summarize_renovation_details(scenario)
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
        "roof_insulation_renovated_area_m2",
        "wall_insulation_renovated_volume_m3",
        "roof_insulation_renovated_volume_m3",
        "wall_insulation_summary_notes",
        "roof_insulation_summary_notes",
        "window_enhancement_summary_notes",
        "door_enhancement_summary_notes",
        "total_renovated_wall_insulation_area_m2",
        "total_renovated_roof_insulation_area_m2",
        "total_renovated_wall_insulation_volume_m3",
        "total_renovated_roof_insulation_volume_m3",
        "total_renovated_window_area_m2",
        "total_renovated_glazing_area_m2",
        "total_renovated_frame_area_m2",
        "total_renovated_perimeter_m",
        "total_renovated_caulking_volume_m3",
        "total_renovated_weatherstrip_length_m",
        "total_renovated_door_area_m2",
        "total_renovated_sealing_bottom_length_m",
        "total_renovated_sealing_side_length_m",
        "wall_insulation_total_additional_embodied_carbon_kg",
        "roof_insulation_total_additional_embodied_carbon_kg",
        "window_enhancement_total_additional_embodied_carbon_kg",
        "door_enhancement_total_additional_embodied_carbon_kg",
        "wall_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "window_enhancement_total_additional_material_cost_usd",
        "window_enhancement_total_additional_labour_cost_usd",
        "window_enhancement_total_additional_overhead_profit_cost_usd",
        "door_enhancement_total_additional_material_cost_usd",
        "door_enhancement_total_additional_labour_cost_usd",
        "door_enhancement_total_additional_overhead_profit_cost_usd",
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
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_data)

    print("\n" + "=" * 80)
    print(f"COMPLETE: {len(all_data)} scenarios successfully processed.")
    print(f"Report saved to: {csv_path}")
    print("=" * 80)

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
OVERWRITE_EXISTING = False

notebook_dir = Path(__file__).parent
base_weather_path = str(notebook_dir / "weather")
measure_dir_path = str(notebook_dir.parent / "measures")
base_run_dir = str(notebook_dir / "simulations" / RUN_NAME)
city_climate_zones = {
     "Amarillo":     "ASHRAE 169-2013-3B",
    # "Atlanta":      "ASHRAE 169-2013-3A",
    # "Baltimore":    "ASHRAE 169-2013-4A",
    # "Chicago":      "ASHRAE 169-2013-5A",
    # "Denver":       "ASHRAE 169-2013-5B",
    # "Duluth":       "ASHRAE 169-2013-7A", ###
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

# =========================
# PARAMETRIC STUDY CONFIGURATION
# =========================

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

# =========================
# CUSTOM COMBINATION SCENARIOS
# =========================

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
    # # Scenario 7: All 4 measures  Wall + Door + Roof + Window
    # {
    #     "wall_r_value":    20,
    #     "wall_insulation_material_type": "Extruded Polystyrene (XPS) Foam Board",
    #     "roof_r_value":    20,
    #     "roof_insulation_material_type": "Blown Mineral Wool",
    #     "door_option":     "glass door",
    #     "door_infiltration_reduction_percent": 20.0,
    #     "door_bottom_seal_option": "none",
    #     "door_top_side_seal_option": "none",
    #     "window_num_panes": 1,
    #     "window_infiltration_reduction_percent": 20.0,
    #     "weatherstrip_option": "silicone adhesive smoke gasket",
    #     "wf_option": "wood-aluminium window frame",
    #     "film_option": "safety film",
    #     "caulking_option": "none",
    # },
    # # Scenario 8: All 4 measures  Wall + Door + Roof + Window
    # {
    #     "wall_r_value":    25,
    #     "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    #     "roof_r_value":    25,
    #     "roof_insulation_material_type": "Polyiso Insulation Foam Board",
    #     "door_option":     "polystyrene core steel door",
    #     "door_infiltration_reduction_percent": 25.0,
    #     "door_bottom_seal_option": "brush weatherstrip",
    #     "door_top_side_seal_option": "silicone adhesive smoke gasket",
    #     "window_num_panes": 2,
    #     "window_infiltration_reduction_percent": 25.0,
    #     "weatherstrip_option": "silicone adhesive smoke gasket",
    #     "wf_option": "wood window frame",
    #     "film_option": "anti-graffiti film",
    #     "caulking_option": "polyurethane",
    # },
    # Scenario 9: All 4 measures  Wall + Door + Roof + Window
    {
        "wall_r_value":    13,
        "wall_insulation_material_type": "Fiberglass Batts",
        "roof_r_value":    24.4,
        "roof_insulation_material_type": "Blown Fiberglass",
        "door_option":     "wooden door",
        "door_infiltration_reduction_percent": 30.0,
        "door_bottom_seal_option": "automatic door bottom",
        "door_top_side_seal_option": "jamb weatherstrip",
        "window_num_panes": 3,
        "window_infiltration_reduction_percent": 30.0,
        "weatherstrip_option": "silicone adhesive smoke gasket",
        "wf_option": "wood window frame",
        "film_option": "low-e film",
        "caulking_option": "acrylic",
    },
]

def scenario_output_exists(base_run_dir, scenario_dict):
    scenario_name = generate_scenario_name(scenario_dict)
    sql_path = os.path.join(base_run_dir, scenario_name, "run", "eplusout.sql")
    return os.path.exists(sql_path)

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
    print("\nÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡ Generating scenarios...")

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

    print(f"\nÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡ Total scenarios: {total_sims}")
    print(f"   - Cities: {len(CITIES)}")
    print(f"   - Building Types: {len(BUILDING_TYPES)}")
    print(f"\n   Breakdown:")
    print(f"   - Baseline: {baseline_count}")
    print(f"   - Wall only: {individual_wall}")
    print(f"   - Roof only: {individual_roof}")
    print(f"   - Window only: {individual_window}")
    print(f"   - Door only: {individual_door}")
    print(f"   - Combined (ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡2 measures): {all_measures}")
    print("=" * 70)

    sim_count = 0
    start_time = time.time()
    successful_scenarios = []
    failed_scenarios = []
    all_selected_have_results = all(scenario_output_exists(base_run_dir, s) for s in scenarios)
    skip_simulation_run = all_selected_have_results and CUSTOM_COMBOS and not OVERWRITE_EXISTING

    if skip_simulation_run:
        print("\nÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Existing simulation outputs detected for selected scenarios.")
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
                    print(f"   ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  failed to write failure log for {scenario_name}: {log_err}")

            sim_elapsed = time.time() - sim_start
            print(f"   ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â±ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Time: {sim_elapsed/60:.1f} min")

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print("SIMULATION SUMMARY")
    print("=" * 70)
    print(f"   ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â±ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â  Total time: {total_elapsed/60:.1f} min ({total_elapsed/3600:.2f} hours)")
    print(f"   ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ Successful: {len(successful_scenarios)}/{total_sims}")
    print(f"   ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€¦Ã¢â‚¬â„¢ Failed: {len(failed_scenarios)}/{total_sims}")

    if failed_scenarios:
        print("\nFailed scenarios:")
        for failed in failed_scenarios:
            print(f"  - {failed}")

    # Collect results
    print("\n" + "=" * 70)
    print("COLLECTING RESULTS FROM OSM FILES")
    print("=" * 70)

    generate_parametric_recap(f"./simulations/{RUN_NAME}", city_climate_zones)
    print("\nÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â° Parametric study complete!")


# ============================================================
# Spider chart for parametric_results.csv (4 scenarios)
from pathlib import Path
import textwrap
import pandas as pd
import plotly.graph_objects as go

base_dir = Path.cwd() / "simulations" / RUN_NAME
csv_candidates = [
    base_dir / "parametric_results.csv",
]

csv_path = next((p for p in csv_candidates if p.exists()), None)
if csv_path is None:
    raise FileNotFoundError(f"Could not find CSV in: {csv_candidates}")

df = pd.read_csv(csv_path)
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
    "window_enhancement_total_additional_embodied_carbon_kg",
    "door_enhancement_total_additional_embodied_carbon_kg",
    "wall_insulation_total_additional_embodied_carbon_kg",
    "roof_insulation_total_additional_embodied_carbon_kg",
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
    df["window_enhancement_total_additional_embodied_carbon_kg"]
    + df["door_enhancement_total_additional_embodied_carbon_kg"]
    + df["wall_insulation_total_additional_embodied_carbon_kg"]
    + df["roof_insulation_total_additional_embodied_carbon_kg"]
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


# ============================================================
def build_report_html(
    embodied_analysis_period_years,
    renovation_rows,
    energy_analysis_table,
    max_cost_class,
    money,
    max_cost_delta,
    max_cost_delta_pct,
    max_savings_scenario,
    max_emis_class,
    num,
    max_emis_delta,
    max_emis_delta_pct,
    max_emissions_scenario,
    min_construction_cost_text,
    min_construction_cost_scenario,
    min_embodied_text,
    min_embodied_intensity_text,
    min_embodied_scenario,
    lowest_cost_payback_text,
    lowest_cost_payback_scenario,
    lowest_carbon_payback_text,
    lowest_carbon_payback_scenario,
    spider_table_rows,
    baseline_cost_w,
    b,
    best_cost_w,
    max_savings,
    baseline_emis_w,
    best_emis_w,
    max_emissions_reduction,
    cost_payback_chart_rows,
    carbon_payback_chart_rows,
    material_list_section_html,
    material_comparison_section_html,
    generated_time,
    report_year,
    run_name,
    spider_chart_embed_html="",
):
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SCOPE Retrofit Measure Analysis Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: white; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #1f4788; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ color: #1f4788; font-size: 28px; margin-bottom: 5px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-top: 5px; }}
        h2 {{ color: #1f4788; font-size: 18px; margin-top: 30px; margin-bottom: 15px; border-left: 4px solid #1f4788; padding-left: 10px; }}
        h3 {{ color: #1f4788; font-size: 15px; margin-top: 15px; margin-bottom: 10px; }}
        .section {{ margin-bottom: 30px; }}
        .summary-box {{ background-color: #e8f0f8; border-left: 4px solid #1f4788; padding: 15px; margin-bottom: 20px; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background-color: #1f4788; color: white; padding: 12px; text-align: left; font-weight: bold; border: 1px solid #ddd; }}
        td {{ padding: 10px 12px; border: 1px solid #ddd; }}
        .renovation-table th:first-child,
        .renovation-table td:first-child {{ white-space: nowrap; min-width: 100px; }}
        .material-costs-table th:first-child,
        .material-costs-table td:first-child {{ white-space: nowrap; min-width: 100px; }}
        .material-list-table {{ table-layout: fixed; width: 100%; }}
        .material-list-table th,
        .material-list-table td {{ font-size: 11px; padding: 6px 8px; word-break: break-word; }}
        .material-list-table th:first-child,
        .material-list-table td:first-child {{ min-width: 72px; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .metric-box {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .metric-card {{ background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1f4788; margin: 10px 0; }}
        .metric-label {{ font-size: 12px; color: #666; }}
        .positive {{ color: #28a745; font-weight: bold; }}
        .viz-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
        .chart-card {{ border: 1px solid #ddd; border-radius: 6px; padding: 15px; background: #fafafa; }}
        .chart-title {{ font-size: 14px; font-weight: 600; color: #1f4788; margin-bottom: 10px; }}
        .bar-chart {{ display: grid; gap: 10px; }}
        .bar-row {{ display: grid; grid-template-columns: 130px 1fr 80px; align-items: center; gap: 10px; }}
        .bar-label {{ font-size: 12px; color: #444; }}
        .bar-track {{ height: 12px; background: #e6e6e6; border-radius: 6px; overflow: hidden; }}
        .bar {{ height: 100%; border-radius: 6px; }}
        .bar.baseline {{ background: #6c757d; }}
        .bar.retrofit {{ background: #28a745; }}
        .bar-value {{ font-size: 12px; color: #333; text-align: right; white-space: nowrap; }}
        .legend {{ display: flex; gap: 12px; margin-top: 10px; font-size: 12px; color: #555; flex-wrap: wrap; }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
        .legend-swatch {{ width: 12px; height: 12px; border-radius: 3px; }}
        .stacked-chart {{ display: grid; gap: 10px; margin-top: 10px; }}
        .stacked-row {{ display: grid; grid-template-columns: 130px 1fr 120px; align-items: center; gap: 10px; }}
        .stacked-label {{ font-size: 12px; color: #444; }}
        .stacked-track {{ display: flex; height: 14px; background: #e6e6e6; border-radius: 7px; overflow: hidden; }}
        .stacked-segment {{ height: 100%; }}
        .stacked-segment.embodied {{ background: #fd7e14; }}
        .stacked-segment.operational {{ background: #007bff; }}
        .stacked-value {{ font-size: 12px; color: #333; text-align: right; white-space: nowrap; }}
        .iframe-wrap {{ border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: #fff; margin-top: 10px; }}
        .iframe-wrap iframe {{ width: 100%; height: 520px; border: 0; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SCOPE Retrofit Measure Analysis Report</h1>
            <div class="subtitle">Comprehensive Energy and Financial Analysis</div>
        </div>

        <div class="section">
            <h2>Executive Summary</h2>
            <div class="summary-box">
                <p>This report compares energy consumption and operational costs between baseline and all applied renovation scenarios from CSV results. Embodied carbon is annualized using an analysis period of {embodied_analysis_period_years:g} years, while operational carbon is reported over 1 year. The construction cost data is from {report_year} RSMeans Database. The embodied carbon is calculated using data from EC3 Environmental Product Declaration (EPD) Database. Since RSMeans Database is proprietary, users can adopt customized cost dataset when needed.</p>
            </div>
            <h3>Renovation Details by Scenario</h3>
            <table class="renovation-table">
                <tr><th>Scenario</th><th>Renovation Type</th><th>Renovation Details</th></tr>
                {renovation_rows}
            </table>
        </div>

        <div class="section">
            <h2>Annual Energy Analysis</h2>
            <table>
                <tr><th>Scenario</th><th>Metric</th><th>Baseline</th><th>Renovation</th><th>Delta</th><th>Savings %</th></tr>
                {energy_analysis_table}
            </table>
        </div>

        <div class="section">
            <h2>Key Performance Metrics</h2>
            <div class="metric-box">
                <div class="chart-card">
                    <div class="chart-title">Operational Cost Saving (Scenario - Baseline) ($/yr) Comparison</div>
                    <div class="bar-chart">
                        <div class="bar-row">
                            <div class="bar-label">Baseline</div>
                            <div class="bar-track"><div class="bar baseline" style="width: {baseline_cost_w:.1f}%;"></div></div>
                            <div class="bar-value">{money(b['annual_cost_usd'])}</div>
                        </div>
                        <div class="bar-row">
                            <div class="bar-label">{max_savings_scenario}</div>
                            <div class="bar-track"><div class="bar retrofit" style="width: {best_cost_w:.1f}%;"></div></div>
                            <div class="bar-value">{money(max_savings['annual_cost_usd'])}</div>
                        </div>
                    </div>
                    <div class="legend">
                        <span class="legend-item"><span class="legend-swatch" style="background:#6c757d"></span>Baseline</span>
                        <span class="legend-item"><span class="legend-swatch" style="background:#28a745"></span>{max_savings_scenario}</span>
                    </div>
                    <p style="font-size:12px;color:#666;margin-top:8px;">Max saving: <span class="{max_cost_class}">{money(max_cost_delta)} ({num(max_cost_delta_pct)}%)</span></p>
                </div>
                <div class="chart-card">
                    <div class="chart-title">Operational Carbon Saving (Scenario - Baseline) (kg CO2e/yr) Comparison</div>
                    <div class="bar-chart">
                        <div class="bar-row">
                            <div class="bar-label">Baseline</div>
                            <div class="bar-track"><div class="bar baseline" style="width: {baseline_emis_w:.1f}%;"></div></div>
                            <div class="bar-value">{num(b['annual_emissions_kg'])}</div>
                        </div>
                        <div class="bar-row">
                            <div class="bar-label">{max_emissions_scenario}</div>
                            <div class="bar-track"><div class="bar retrofit" style="width: {best_emis_w:.1f}%;"></div></div>
                            <div class="bar-value">{num(max_emissions_reduction['annual_emissions_kg'])}</div>
                        </div>
                    </div>
                    <div class="legend">
                        <span class="legend-item"><span class="legend-swatch" style="background:#6c757d"></span>Baseline</span>
                        <span class="legend-item"><span class="legend-swatch" style="background:#28a745"></span>{max_emissions_scenario}</span>
                    </div>
                    <p style="font-size:12px;color:#666;margin-top:8px;">Max saving: <span class="{max_emis_class}">{num(max_emis_delta)} kgCO2e ({num(max_emis_delta_pct)}%)</span></p>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Min Retrofit Construction Cost</div>
                    <div class="metric-value">{min_construction_cost_text}</div>
                    <div style="font-size:12px;color:#666;">{min_construction_cost_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Min Retrofit Embodied Carbon</div>
                    <div class="metric-value">{min_embodied_text}</div>
                    <div style="font-size:12px;color:#666;">Embodied carbon intensity (ECI): {min_embodied_intensity_text}</div>
                    <div style="font-size:12px;color:#666;">{min_embodied_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Lowest Retrofit Cost Payback Period</div>
                    <div class="metric-value">{lowest_cost_payback_text}</div>
                    <div style="font-size:12px;color:#666;">{lowest_cost_payback_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Lowest Retrofit Carbon Payback Period</div>
                    <div class="metric-value">{lowest_carbon_payback_text}</div>
                    <div style="font-size:12px;color:#666;">{lowest_carbon_payback_scenario}</div>
            </div>
        </div>

        <div class="section">
            <h2>Comparative Visualizations between Renovation Scenarios</h2>
            <div class="chart-card" style="margin-top: 20px;">
                <div class="chart-title">Spider Chart Visualization</div>
                <div class="iframe-wrap">
                    {spider_chart_embed_html}\n
                </div>
            </div>

        </div>

        <div class="section">
            <h2>Payback Period of the Retrofit</h2>
            <div class="viz-grid">
                <div class="chart-card">
                    <div class="chart-title">Cost Payback Period</div>
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">Payback = retrofit construction cost / abs(Operational Cost Saving (Scenario - Baseline) ($/yr)).</p>
                    <div class="bar-chart">
                        {cost_payback_chart_rows}
                    </div>
                </div>

                <div class="chart-card">
                    <div class="chart-title">Carbon Payback Period</div>
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">Payback = retrofit embodied carbon / abs(Operational Carbon Saving (Scenario - Baseline) (kg CO2e/yr)).</p>
                    <div class="bar-chart">
                        {carbon_payback_chart_rows}
                    </div>
                </div>
            </div>
        </div>

        {material_comparison_section_html}

        {material_list_section_html}

        <div class="section">
            <h2>Result Summary</h2>
            </div>
            <table class="material-costs-table">
                <tr><th>Scenario</th><th>Retrofit Embodied Carbon (kgCO2e)</th><th>Retrofit Construction Cost (USD)</th><th>Annual Operational Carbon (kgCO2e)</th><th>Annual Operational Cost (USD)</th></tr>
                {spider_table_rows}

            </table>
        </div>

        <div class="footer">
            <p>Generated: {generated_time} | Report Type: Retrofit Impact Analysis | Run: {run_name}</p>
        </div>
    </div>
</body>
</html>
"""
    return html


# ============================================================
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



    wall_ec = _to_num(df, "wall_insulation_total_additional_embodied_carbon_kg")

    roof_ec = _to_num(df, "roof_insulation_total_additional_embodied_carbon_kg")

    window_ec = _to_num(df, "window_enhancement_total_additional_embodied_carbon_kg")

    door_ec = _to_num(df, "door_enhancement_total_additional_embodied_carbon_kg")



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

            min_embodied_intensity_text = (f"{min_embodied_intensity:,.0f} kgCO2e/mÂ²" if abs(min_embodied_intensity) >= 10 else f"{min_embodied_intensity:,.2f} kgCO2e/mÂ²")

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



    args_csv_path = html_report_path.parent / "scenario_user_arguments.csv"

    if args_csv_path.exists():

        args_df = pd.read_csv(args_csv_path)

        args_df["scenario"] = args_df["scenario"].astype(str)

        args_df["measure"] = args_df["measure"].astype(str)

        args_df["argument"] = args_df["argument"].astype(str)

        args_df["value"] = args_df["value"].astype(str)



        def _arg_value(scenario_name, measure_name, argument_name):

            subset = args_df[

                (args_df["scenario"] == scenario_name)

                & (args_df["measure"] == measure_name)

                & (args_df["argument"] == argument_name)

            ]

            if subset.empty:

                return None

            return str(subset.iloc[0]["value"])



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



        for idx, row in renovation_df.iterrows():

            scenario_name = str(row[scenario_col])

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

            if measure_flags["wall"]:

                wall_r = _arg_value(scenario_name, "wall", "r_value")

                wall_mat = _arg_value(scenario_name, "wall", "insulation_material_type")

                if wall_r and wall_mat:

                    details_parts.append(f"<div><strong>Wall upgrade:</strong> Exterior walls were upgraded to R-{wall_r} with {wall_mat} insulation.</div>")

                else:

                    details_parts.append("<div><strong>Wall upgrade:</strong> Exterior wall insulation was upgraded.</div>")



            if measure_flags["roof"]:

                roof_r = _arg_value(scenario_name, "roof", "r_value")

                roof_mat = _arg_value(scenario_name, "roof", "insulation_material_type")

                if roof_r and roof_mat:

                    details_parts.append(f"<div><strong>Roof upgrade:</strong> The roof was upgraded to R-{roof_r} using {roof_mat} insulation.</div>")

                else:

                    details_parts.append("<div><strong>Roof upgrade:</strong> Roof insulation was upgraded.</div>")



            if measure_flags["window"]:

                panes = _arg_value(scenario_name, "window", "user_num_panes")

                window_bullets = []

                if _has_meaningful_value(panes):

                    window_bullets.append(f"Upgraded to {panes}-pane glazing")



                weatherstrip_opt = _arg_value(scenario_name, "window", "weatherstrip_option")

                film_opt = _arg_value(scenario_name, "window", "film_option")

                frame_opt = _arg_value(scenario_name, "window", "wf_option")

                caulking_opt = _arg_value(scenario_name, "window", "caulking_option")

                secondary_glazing_opt = _arg_value(scenario_name, "window", "secondary_glazing_option")



                window_option_details = []

                if _has_meaningful_value(weatherstrip_opt):

                    window_option_details.append(f"Weatherstripping: {weatherstrip_opt}")

                if _has_meaningful_value(film_opt):

                    window_option_details.append(f"Glazing film: {film_opt}")

                if _has_meaningful_value(frame_opt):

                    window_option_details.append(f"Window frame: {frame_opt}")

                if _has_meaningful_value(caulking_opt):

                    window_option_details.append(f"Caulking: {caulking_opt}")

                if _has_meaningful_value(secondary_glazing_opt):

                    window_option_details.append(f"Secondary glazing: {secondary_glazing_opt}")



                win_infil = _as_float(_arg_value(scenario_name, "window", "space_infiltration_reduction_percent"))

                if win_infil is not None:

                    window_option_details.append(f"Infiltration reduction: {win_infil:g}%")



                if window_option_details:

                    window_bullets.extend(window_option_details)



                if window_bullets:

                    window_list_html = "".join(f"<li>{item}</li>" for item in window_bullets)

                    details_parts.append("<div><strong>Window upgrade:</strong><ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>" + window_list_html + "</ul></div>")

                else:

                    details_parts.append("<div><strong>Window upgrade:</strong> Window upgrades were applied.</div>")



            if measure_flags["door"]:

                door_opt = _arg_value(scenario_name, "door", "door_option")

                door_bullets = []

                if _has_meaningful_value(door_opt):

                    door_bullets.append(f"Door type: {door_opt}")



                bottom_seal = _arg_value(scenario_name, "door", "door_bottom_seal_option")

                top_side_seal = _arg_value(scenario_name, "door", "door_top_side_seal_option")

                if _has_meaningful_value(bottom_seal):

                    door_bullets.append(f"Bottom seal: {bottom_seal}")

                if _has_meaningful_value(top_side_seal):

                    door_bullets.append(f"Top/side seals: {top_side_seal}")



                door_infil = _as_float(_arg_value(scenario_name, "door", "space_infiltration_reduction_percent"))

                if door_infil is not None:

                    door_bullets.append(f"Infiltration reduction: {door_infil:g}%")



                if door_bullets:

                    door_list_html = "".join(f"<li>{item}</li>" for item in door_bullets)

                    details_parts.append("<div><strong>Door upgrade:</strong><ul style='margin:6px 0 6px 18px;padding:0;list-style-type:disc;'>" + door_list_html + "</ul></div>")

                else:

                    details_parts.append("<div><strong>Door upgrade:</strong> Door upgrades were applied.</div>")



            if details_parts:

                renovation_df.at[idx, "renovation_details"] = "".join(details_parts)



    renovation_rows = "".join(

        f"<tr><td>{scenario_display_map.get(row[scenario_col], row[scenario_col])}</td><td>{row['renovation_type']}</td><td>{row['renovation_details']}</td></tr>"

        for _, row in renovation_df.iterrows()

    )



    # Build material list section by scenario (e.g., roof insulation volume, weatherstrip length).

    material_list_rows = []

    args_df_material = None

    if args_csv_path.exists():

        args_df_material = pd.read_csv(args_csv_path)

        args_df_material["scenario"] = args_df_material["scenario"].astype(str)

        args_df_material["measure"] = args_df_material["measure"].astype(str)

        args_df_material["argument"] = args_df_material["argument"].astype(str)

        args_df_material["value"] = args_df_material["value"].astype(str)



    def _arg_lookup_material(scenario_name, measure_name, argument_name):

        if args_df_material is None:

            return None

        subset = args_df_material[

            (args_df_material["scenario"] == str(scenario_name))

            & (args_df_material["measure"] == str(measure_name))

            & (args_df_material["argument"] == str(argument_name))

        ]

        if subset.empty:

            return None

        return str(subset.iloc[0]["value"])



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



    def _fmt_metric(value):

        val = _safe_float(value)

        if val is None:

            return "N/A"

        if abs(val) < 0.005:

            return "N/A"

        return num(val)



    def _add_material_row(scenario_name, component, material_name, volume_m3=None, area_m2=None, thickness_m=None, length_m=None, thermal_conductivity=None, density=None):

        mat = _clean_text(material_name) or "N/A"

        material_list_rows.append(

            f"<tr><td>{scenario_display_map.get(str(scenario_name), str(scenario_name))}</td><td>{component}</td><td>{mat}</td><td>{_fmt_metric(volume_m3)}</td><td>{_fmt_metric(area_m2)}</td><td>{_fmt_metric(thickness_m)}</td><td>{_fmt_metric(length_m)}</td><td>{_fmt_metric(thermal_conductivity)}</td><td>{_fmt_metric(density)}</td></tr>"

        )



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

            wall_vol, _ = _pick_first_numeric(data_row, [

                "total_renovated_wall_insulation_volume_m3",

                "wall_insulation_renovated_volume_m3",

            ])

            wall_area, _ = _pick_first_numeric(data_row, [

                "total_renovated_wall_insulation_area_m2",

                "wall_insulation_renovated_area_m2",

            ])

            wall_thickness = (wall_vol / wall_area) if (wall_vol is not None and wall_area is not None and wall_area > 0) else None

            _add_material_row(

                scenario_name,

                "Wall insulation",

                _arg_lookup_material(scenario_name, "wall", "insulation_material_type"),

                volume_m3=wall_vol,

                area_m2=wall_area,

                thickness_m=wall_thickness,

                thermal_conductivity=_arg_lookup_material(scenario_name, "wall", "insulation_thermal_conductivity"),

                density=_arg_lookup_material(scenario_name, "wall", "insulation_material_density"),

            )



        if roof_status == "applied":

            roof_vol, _ = _pick_first_numeric(data_row, [

                "total_renovated_roof_insulation_volume_m3",

                "roof_insulation_renovated_volume_m3",

            ])

            roof_area, _ = _pick_first_numeric(data_row, [

                "total_renovated_roof_insulation_area_m2",

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

                thermal_conductivity=_arg_lookup_material(scenario_name, "roof", "insulation_thermal_conductivity"),

                density=_arg_lookup_material(scenario_name, "roof", "insulation_material_density"),

            )



        if window_status == "applied":

            _add_material_row(

                scenario_name,

                "Window weatherstrip",

                _arg_lookup_material(scenario_name, "window", "weatherstrip_option"),

                length_m=data_row.get("total_renovated_weatherstrip_length_m", None),

            )

            _add_material_row(

                scenario_name,

                "Window caulking",

                _arg_lookup_material(scenario_name, "window", "caulking_option"),

                volume_m3=data_row.get("total_renovated_caulking_volume_m3", None),

            )



        if door_status == "applied":

            _add_material_row(

                scenario_name,

                "Door bottom seal",

                _arg_lookup_material(scenario_name, "door", "door_bottom_seal_option"),

                length_m=data_row.get("total_renovated_sealing_bottom_length_m", None),

                thermal_conductivity=_arg_lookup_material(scenario_name, "door", "door_thermal_conductivity"),

                density=_arg_lookup_material(scenario_name, "door", "door_density"),

            )

            _add_material_row(

                scenario_name,

                "Door top/side seal",

                _arg_lookup_material(scenario_name, "door", "door_top_side_seal_option"),

                length_m=data_row.get("total_renovated_sealing_side_length_m", None),

                thermal_conductivity=_arg_lookup_material(scenario_name, "door", "door_thermal_conductivity"),

                density=_arg_lookup_material(scenario_name, "door", "door_density"),

            )



    if material_list_rows:

        material_list_section_html = (

            "<div class='section'><h2>Material List</h2><div class='summary-box'><p>Material properties and consumption by renovation scenario. Missing values are shown as N/A.</p></div><table class='material-costs-table material-list-table'><tr><th>Scenario</th><th>Component</th><th>Material</th><th>Volume (m<sup>3</sup>)</th><th>Area (m<sup>2</sup>)</th><th>Thickness (m)</th><th>Length (m)</th><th>Thermal Conductivity (W/m&middot;K)</th><th>Density (kg/m<sup>3</sup>)</th></tr>"

            + "".join(material_list_rows)

            + "</table></div>"

        )

    else:

        material_list_section_html = "<div class='section'><h2>Material List</h2><div class='summary-box'><p>No material consumption data found for renovation scenarios.</p></div></div>"



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

        if args_csv_path.exists():

            args_df_cmp = pd.read_csv(args_csv_path)

            for col in ["scenario", "measure", "argument", "value"]:

                if col in args_df_cmp.columns:

                    args_df_cmp[col] = args_df_cmp[col].astype(str)



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
        spider_chart_embed_html=globals().get("spider_chart_html", ""),

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



# ============================================================
# Compatibility wrapper disabled: workflow now uses only SCOPE report filenames.
print("Legacy filename compatibility wrapper is disabled.")


# ============================================================
# Execute report generation (kept separate from function definitions).
import re
from html import unescape

base_dir = Path.cwd() / "simulations" / RUN_NAME
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
        ("building_area_m2", "mÂ²"),
        ("total_floor_area_m2", "mÂ²"),
        ("floor_area_m2", "mÂ²"),
        ("building_floor_area_m2", "mÂ²"),
        ("total_floor_area_ft2", "ftÂ²"),
        ("floor_area_ft2", "ftÂ²"),
        ("building_floor_area_ft2", "ftÂ²"),
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

# ============================================================
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
        "window": ["window_enhancement_summary_notes", "window_summary_notes"],
        "door": ["door_enhancement_summary_notes", "door_summary_notes"],
        "roof": ["roof_insulation_summary_notes", "roof_summary_notes"],
        "wall": ["wall_insulation_summary_notes", "wall_summary_notes"],
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

# ============================================================
# Auto-export main HTML report to PDF
import subprocess
from pathlib import Path

base_dir = Path.cwd() / "simulations" / RUN_NAME

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
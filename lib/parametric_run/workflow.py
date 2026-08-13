#!/usr/bin/env python3
# Auto-generated from workflow.ipynb
"""Parametric retrofit study driver for the openstudio-ee-gem measures.

End-to-end pipeline (executed when this file is run as a script):
  1. Detect the OpenStudio CLI + 3.11.0 Python bindings (Python 3.12 required).
  2. Build a list of retrofit scenarios for each (city, building_type) pair,
     drawing from CUSTOM_COMBOS or the JSON override env var.
  3. For each scenario, write an OSW that creates a DOE prototype building,
     applies up to four envelope measures (wall insulation, roof insulation,
     window enhancement, door enhancement), and runs EnergyPlus.
  4. Postprocess: open every result OSM and pull retrofit/cost/embodied-carbon
     properties from the model's AdditionalProperties into parametric_results.csv.
  5. Render an interactive HTML report (and PDF via Edge) summarising scenarios.

Environment variables (used by lib/parametric_run/run_all_tests.py to drive
multiple sequential runs without editing this file):
  - WORKFLOW_RUN_NAME           Override the output folder name (RUN_NAME).
  - WORKFLOW_OVERWRITE_EXISTING Force re-simulation even if eplusout.sql exists.
  - WORKFLOW_CUSTOM_COMBOS_JSON JSON list of combo dicts replacing CUSTOM_COMBOS.
  - OPENSTUDIO_PATH             Path to the openstudio CLI executable.
  - OPENSTUDIO_PYTHON_PATH      Path to the OpenStudio Python bindings folder.
  - EC3_API_TOKEN               Read from config.ini if not in env.
"""

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

# --- ENVIRONMENT / PYTHON 3.12 + OPENSTUDIO 3.11.0 BINDINGS DETECTION ---
# OpenStudio 3.11.0 Python bindings are built for Python 3.12, so the helpers
# below locate (or re-launch under) a compatible interpreter and add the
# OpenStudio Python folder to sys.path before `import openstudio`.
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
    """Locate the OpenStudio 3.11.0 Python bindings folder.

    Order of preference: OPENSTUDIO_PYTHON_PATH env var, then the Python/
    sibling folder of the detected OpenStudio CLI install. Returns None if
    nothing is found (caller falls back to a system-installed `openstudio`).
    """
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

# Add auxiliary/ to path so helper modules are importable regardless of cwd
_AUXILIARY_DIR = str(Path(__file__).parent / "auxiliary")
if _AUXILIARY_DIR not in sys.path:
    sys.path.insert(0, _AUXILIARY_DIR)

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
                ("window_option", "window_wf"),
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
    """Infer whether requested pane upgrade was applied based on model constructions."""
    windows = [
        ss for ss in model.getSubSurfaces()
        if ss.subSurfaceType() in ["FixedWindow", "OperableWindow", "Skylight"]
    ]
    if not windows:
        return "none"

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
        "window_layered_glazing_count": 0,
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
        is_simple = False
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            for layer_index in range(layered.numLayers()):
                layer_material = layered.getLayer(layer_index)
                if layer_material.to_SimpleGlazing().is_initialized():
                    inventory["window_simple_glazing_count"] += 1
                    is_simple = True
                    break
        if not is_simple:
            inventory["window_layered_glazing_count"] += 1

    return inventory


def _construction_r_value_ip(construction):
    """Return construction R-value in IP units (ft^2*h*R/Btu), or None."""
    if not construction.to_LayeredConstruction().is_initialized():
        return None

    layered = construction.to_LayeredConstruction().get()
    if not layered.thermalConductance().is_initialized():
        return None

    conductance_si = layered.thermalConductance().get()
    if conductance_si <= 0:
        return None

    try:
        r_value_si = 1.0 / conductance_si
        return openstudio.convert(r_value_si, "m^2*K/W", "ft^2*h*R/Btu").get()
    except Exception:
        return None


def collect_baseline_envelope_inventory(model):
    """Collect outdoor wall/roof construction counts and current R-values for baseline reporting."""
    inventory = {
        "baseline_wall_construction_r_values_json": "[]",
        "baseline_roof_construction_r_values_json": "[]",
    }
    grouped = {
        "wall": {},
        "roof": {},
    }

    for surface in model.getSurfaces():
        if str(surface.outsideBoundaryCondition()) != "Outdoors":
            continue

        surface_type = str(surface.surfaceType())
        target_key = None
        if surface_type == "Wall":
            target_key = "wall"
        elif surface_type in {"RoofCeiling", "Roof"}:
            target_key = "roof"
        if not target_key:
            continue

        if not surface.construction().is_initialized():
            continue
        construction = surface.construction().get()
        r_value_ip = _construction_r_value_ip(construction)
        if r_value_ip is None:
            continue

        construction_name = construction.nameString() or "Unnamed construction"
        by_name = grouped[target_key]
        if construction_name not in by_name:
            by_name[construction_name] = {
                "construction": construction_name,
                "r_value_ip": r_value_ip,
                "count": 0,
            }
        by_name[construction_name]["count"] += 1

    for key, field in [
        ("wall", "baseline_wall_construction_r_values_json"),
        ("roof", "baseline_roof_construction_r_values_json"),
    ]:
        rows = list(grouped[key].values())
        rows.sort(key=lambda item: (-int(item.get("count", 0)), str(item.get("construction", ""))))
        inventory[field] = json.dumps(rows)

    return inventory


def collect_door_inventory(model):
    """Collect door counts by subtype for baseline report text."""
    inventory = {
        "baseline_door_total_count": 0,
        "baseline_door_glass_count": 0,
        "baseline_door_overhead_count": 0,
        "baseline_door_standard_count": 0,
    }

    for subsurface in model.getSubSurfaces():
        subtype = str(subsurface.subSurfaceType())
        if subtype not in {"Door", "GlassDoor", "OverheadDoor"}:
            continue

        inventory["baseline_door_total_count"] += 1
        if subtype == "GlassDoor":
            inventory["baseline_door_glass_count"] += 1
        elif subtype == "OverheadDoor":
            inventory["baseline_door_overhead_count"] += 1
        else:
            inventory["baseline_door_standard_count"] += 1

    return inventory


def build_baseline_renovation_details(envelope_inventory, window_inventory, door_inventory):
    """Build baseline renovation details HTML for report table."""

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

    def _fmt_r(raw):
        try:
            return f"R-{float(raw):.1f}"
        except Exception:
            return "N/A"

    def _envelope_bullets(action_label, json_text):
        try:
            rows = json.loads(str(json_text or "[]"))
        except Exception:
            rows = []

        if not rows:
            return [f"{action_label}: current R-value of insulation is N/A"]

        if len(rows) == 1:
            return [
                f"{action_label}: current R-value of insulation is {_fmt_r(rows[0].get('r_value_ip'))}"
            ]

        bullets = []
        for row in rows:
            construction_name = str(row.get("construction") or "Unnamed construction")
            bullets.append(
                f"{action_label} ({construction_name}): current R-value of insulation is {_fmt_r(row.get('r_value_ip'))}"
            )
        return bullets

    window_total = int(window_inventory.get("window_total_count", 0) or 0)
    window_simple = int(window_inventory.get("window_simple_glazing_count", 0) or 0)
    window_layered = int(window_inventory.get("window_layered_glazing_count", 0) or 0)

    door_total = int(door_inventory.get("baseline_door_total_count", 0) or 0)
    door_glass = int(door_inventory.get("baseline_door_glass_count", 0) or 0)
    door_overhead = int(door_inventory.get("baseline_door_overhead_count", 0) or 0)
    door_standard = int(door_inventory.get("baseline_door_standard_count", 0) or 0)

    sections = [
        _build_measure_section(
            "Current Condition of Exterior Wall",
            _envelope_bullets("Exterior wall insulation", envelope_inventory.get("baseline_wall_construction_r_values_json")),
        ),
        _build_measure_section(
            "Current Condition of Roof",
            _envelope_bullets("Roof insulation", envelope_inventory.get("baseline_roof_construction_r_values_json")),
        ),
        _build_measure_section(
            "Current Condition of Window",
            [
                (
                    "Number of window constructions is "
                    + f"{window_total}, with {window_simple} simple glazing type windows, "
                    + f"and {window_layered} layered construction windows"
                )
            ],
        ),
        _build_measure_section(
            "Current Condition of Door",
            [
                (
                    "Number of door constructions is "
                    + f"{door_total}, with {door_glass} glass door, {door_overhead} overhead door, "
                    + f"and {door_standard} door"
                )
            ],
        ),
    ]
    return "".join([section for section in sections if section])

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


def _sanitize_prototype_weather_noise(proto_dir):
    """Remove known prototype-stage weather noise from log artifacts."""
    noise_markers = (
        "UseWeatherFile' is selected in YearDescription, but there are no weather file set for the model.",
        "Cannot find file",
        ".rain",
        "Could not translate Schedule:File",
    )

    def _is_noise_line(line):
        return any(marker in line for marker in noise_markers)

    run_log_path = os.path.join(proto_dir, "run", "run.log")
    if os.path.exists(run_log_path):
        try:
            with open(run_log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            filtered_lines = [line for line in lines if not _is_noise_line(line)]
            if len(filtered_lines) != len(lines):
                with open(run_log_path, "w", encoding="utf-8") as f:
                    f.writelines(filtered_lines)
        except Exception as e:
            print(f"    Warning: failed to sanitize prototype run.log at {run_log_path}: {e}")

    out_osw_path = os.path.join(proto_dir, "out.osw")
    if os.path.exists(out_osw_path):
        try:
            with open(out_osw_path, "r", encoding="utf-8", errors="ignore") as f:
                out_osw = json.load(f)

            def _clean_value(value):
                if isinstance(value, str):
                    cleaned_lines = [line for line in value.splitlines() if not _is_noise_line(line)]
                    return "\n".join(cleaned_lines)
                if isinstance(value, list):
                    return [_clean_value(item) for item in value]
                if isinstance(value, dict):
                    return {key: _clean_value(item) for key, item in value.items()}
                return value

            cleaned_out_osw = _clean_value(out_osw)
            if cleaned_out_osw != out_osw:
                with open(out_osw_path, "w", encoding="utf-8") as f:
                    json.dump(cleaned_out_osw, f, indent=2)
        except Exception as e:
            print(f"    Warning: failed to sanitize prototype out.osw at {out_osw_path}: {e}")

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

def _isolate_measure_resources_imports(measure_folder_str):
    """Prepare sys.path / sys.modules so each measure imports its OWN
    resources/* modules instead of reusing a sibling measure's cached copy.

    Each measure does ``from resources.call_rsmeans_api import ...`` (and
    similar for ``resources.EC3_lookup``).  Python caches these under the
    bare names ``resources.call_rsmeans_api`` etc. in ``sys.modules``, so the
    first measure to load wins and every later measure silently reuses the
    earlier copy.  Because each measure has its OWN ``resources/`` folder
    with measure-specific fallback ID dicts and helpers, this shadowing
    causes wrong RSMeans/EC3 lookups (e.g. door measure receiving wall
    measure's fallback dict).

    Returns a callable that restores the previous sys.path / sys.modules
    state when invoked.
    """
    saved_sys_path = list(sys.path)
    saved_modules = {
        name: mod for name, mod in sys.modules.items()
        if name == "resources" or name.startswith("resources.")
    }
    # Drop any cached resources.* so the next import resolves to this
    # measure's folder.
    for name in list(sys.modules):
        if name == "resources" or name.startswith("resources."):
            del sys.modules[name]
    if measure_folder_str not in sys.path:
        sys.path.insert(0, measure_folder_str)

    def _restore():
        sys.path[:] = saved_sys_path
        for name in list(sys.modules):
            if name == "resources" or name.startswith("resources."):
                del sys.modules[name]
        sys.modules.update(saved_modules)

    return _restore


def apply_python_measure(model, measure_folder, measure_class_name, arguments_dict, failure_logger=None):
    """
    Apply a Python OpenStudio ModelMeasure directly to a model in-process.
    Returns True if successful, False otherwise.

    If `failure_logger` is provided, it is called with a multi-line detail
    string when the measure fails (runner errors or a Python exception),
    so callers can persist the reason to scenario_failure.log instead of
    relying on stdout capture.
    """
    measure_folder_str = str(measure_folder)
    restore_imports = _isolate_measure_resources_imports(measure_folder_str)
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
            error_messages = [error.logMessage() for error in runner.result().errors()]
            for msg in error_messages:
                print(f"    ERROR: {msg}")
            if failure_logger is not None:
                detail_lines = [f"{measure_class_name} result: {result_value}"]
                if error_messages:
                    detail_lines.extend(f"  ERROR: {msg}" for msg in error_messages)
                else:
                    detail_lines.append("  (no runner errors recorded)")
                failure_logger("\n".join(detail_lines))
            return False
        return True
    except Exception as e:
        print(f"  ERROR applying measure: {str(e)}")
        import traceback
        tb_str = traceback.format_exc()
        traceback.print_exc()
        if failure_logger is not None:
            failure_logger(f"{measure_class_name} raised {type(e).__name__}: {e}\n{tb_str}")
        return False
    finally:
        restore_imports()

def apply_reporting_measure(model_path, sql_file_path, measure_dir_path, label):
    """
    Apply the OperatingCostCarbonReportingMeasure (Python ReportingMeasure)
    in-process after simulation completes. The OSW runner can't execute Python
    measures, so we call it directly using the OpenStudio Python bindings.
    Returns True if successful, False otherwise.
    """
    measure_folder = os.path.join(measure_dir_path, "OperatingCostCarbonReportingMeasure")
    measure_folder_str = str(measure_folder)
    restore_imports = _isolate_measure_resources_imports(measure_folder_str)
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
    finally:
        restore_imports()

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

def apply_ddy_design_days_to_model(osm_path, ddy_path, replace_existing=True):
    """Load DDY and write its DesignDay objects into model_to_run OSM."""
    if not ddy_path:
        return False
    try:
        osm_path = os.path.abspath(str(osm_path))
        ddy_path = os.path.abspath(str(ddy_path))
        if not os.path.exists(ddy_path):
            print(f"    DDY file not found: {ddy_path}")
            return False

        translator = openstudio.osversion.VersionTranslator()
        loaded_model = translator.loadModel(openstudio.toPath(osm_path))
        if not loaded_model.is_initialized():
            print(f"    Failed to load model for DDY injection: {osm_path}")
            return False
        model = loaded_model.get()

        loaded_idf = openstudio.IdfFile.load(openstudio.toPath(ddy_path))
        if not loaded_idf.is_initialized():
            print(f"    Failed to load DDY file: {ddy_path}")
            return False

        ddy_workspace = openstudio.Workspace(loaded_idf.get())
        reverse_translator = openstudio.energyplus.ReverseTranslator()
        ddy_model = reverse_translator.translateWorkspace(ddy_workspace)
        ddy_design_days = list(ddy_model.getDesignDays())
        if not ddy_design_days:
            print(f"    No DesignDay objects found in DDY: {ddy_path}")
            return False

        # Remove ExternalFile and ScheduleFile objects from ddy_model before cloning
        # to prevent importing rainfall data file references that don't exist in run directory
        removed_count = 0
        for external_file in list(ddy_model.getExternalFiles()):
            external_file.remove()
            removed_count += 1
        for schedule_file in list(ddy_model.getScheduleFiles()):
            schedule_file.remove()
            removed_count += 1
        if removed_count > 0:
            print(f"    Cleaned {removed_count} file reference(s) from DDY before import")

        if replace_existing:
            for design_day in list(model.getDesignDays()):
                design_day.remove()

        for design_day in ddy_design_days:
            design_day.clone(model)

        model.save(openstudio.toPath(osm_path), True)
        print(f"    Applied {len(ddy_design_days)} DDY design days to model_to_run")
        del model
        return True
    except Exception as e:
        print(f"    Failed to apply DDY design days from {ddy_path}: {e}")
        return False

def ensure_window_frame_and_divider(model, frame_width=0.05):
    """Add a default WindowPropertyFrameAndDivider to windows that lack one.

    For every FixedWindow, OperableWindow, and Skylight SubSurface in `model`
    that does not already have a FrameAndDivider assigned, create a new
    WindowPropertyFrameAndDivider with frame_width=`frame_width` (m) and
    divider_width=0.0, then assign it to that SubSurface.
    """
    window_types = {"FixedWindow", "OperableWindow", "Skylight"}
    added = 0
    for subsurface in model.getSubSurfaces():
        if str(subsurface.subSurfaceType()) not in window_types:
            continue
        if subsurface.windowPropertyFrameAndDivider().is_initialized():
            continue
        fad = openstudio.model.WindowPropertyFrameAndDivider(model)
        fad.setFrameWidth(frame_width)
        fad.setDividerWidth(0.0)
        subsurface.setWindowPropertyFrameAndDivider(fad)
        added += 1
    if added:
        print(f"    Added default FrameAndDivider (frame_width={frame_width} m) to {added} window(s)")

def apply_window_frame_and_divider_to_osm(osm_path, frame_width=0.05):
    """Load an OSM, apply ensure_window_frame_and_divider, and save in-place."""
    try:
        translator = openstudio.osversion.VersionTranslator()
        loaded = translator.loadModel(openstudio.toPath(str(osm_path)))
        if not loaded.is_initialized():
            print(f"    apply_window_frame_and_divider_to_osm: failed to load {osm_path}")
            return False
        model = loaded.get()
        ensure_window_frame_and_divider(model, frame_width=frame_width)
        model.save(openstudio.toPath(str(osm_path)), True)
        del model
        return True
    except Exception as e:
        print(f"    apply_window_frame_and_divider_to_osm error: {e}")
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
    """Build, apply measures to, and simulate one scenario via OpenStudio CLI.

    Stages performed for each scenario_dict:
      1. Resolve EPW/DDY for `city` and create the per-scenario run folder.
      2. Skip-if-already-done (unless overwrite_existing=True).
      3. Step 1 OSW -> create_DOE_prototype_building (writes in.osm).
      4. Apply Python measures in-process for any non-baseline scenario:
         IncreaseInsulationRValueForExteriorWalls / ...ForRoofs /
         window_enhancement / door_enhancement; save in_modified.osm.
      5. Step 2 OSW -> run EnergyPlus (and the ReportRetrofitImpacts
         reporting measure) on the modified model.

    Returns the scenario_name on success, or None on any failure (a
    scenario_failure.log is written into the scenario run folder).
    """
    # --- Weather ---
    wf = get_city_weather_files(city, base_weather_path)
    if wf is None or wf["epw"] is None:
        print(f"  Weather files not found for {city}")
        append_scenario_failure_log(os.path.abspath(os.path.join(base_run_dir, generate_scenario_name(scenario_dict))), f"weather files not found for city={city}")
        return None

    epw_path = os.path.abspath(wf["epw"])
    ddy_path = os.path.abspath(wf["ddy"]) if wf.get("ddy") else None
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
    file_paths = [os.path.abspath(base_weather_path), os.path.abspath(os.path.dirname(epw_path))]
    prototype_step = {
        "measure_dir_name": "create_DOE_prototype_building",
        "name": "Create DOE Prototype Building",
        "arguments": {
            "building_type": building_type,
            "template": template,
            "climate_zone": climate_zone,
            "epw_file": epw_path,
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
        _sanitize_prototype_weather_noise(proto_dir)

        proto_model_path = os.path.join(proto_dir, "run", "in.osm")
        if not os.path.exists(proto_model_path):
            print(f"  {scenario_name}: prototype model not found at {proto_model_path}")
            log_failure(f"prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)
        enforce_weather_url_in_osm(final_model_path, epw_path)
        apply_ddy_design_days_to_model(final_model_path, ddy_path)
        apply_window_frame_and_divider_to_osm(final_model_path)
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
        _sanitize_prototype_weather_noise(proto_dir)
        proto_model_path = os.path.join(proto_dir, "run", "in.osm")
        if not os.path.exists(proto_model_path):
            print(f"  {scenario_name}: prototype model not found at {proto_model_path}")
            log_failure(f"prototype model not found at {proto_model_path}")
            return None

        final_model_path = os.path.join(scenario_run_dir, "model_to_run.osm")
        shutil.copy2(proto_model_path, final_model_path)
        apply_ddy_design_days_to_model(final_model_path, ddy_path)
        # --- Phase 2: apply Python model measures ---
        translator = openstudio.osversion.VersionTranslator()
        loaded_model = translator.loadModel(openstudio.toPath(final_model_path))
        if not loaded_model.is_initialized():
            print(f"  {scenario_name}: failed to load prototype model")
            log_failure("failed to load prototype model")
            return None

        model = loaded_model.get()
        ensure_window_frame_and_divider(model)
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
            scenario_dict.get("window_num_panes") not in [None, "", 0, 0.0],
            window_infiltration_reduction not in [None, "", 0, 0.0],
            str(scenario_dict.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("window_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("film_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_dict.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        has_door_renovation = any([
            str(scenario_dict.get("door_option", "none")).strip().lower() != "none",
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
                "use_lifetime_multiplier": bool(scenario_dict.get("use_lifetime_multiplier", False)),
                "gwp_statistic": "median",
                "api_key": EC3_API_TOKEN,
                "insulation_material_type": wall_material_type,
                "insulation_material_lifetime": wall_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
                "calculate_costs": bool(scenario_dict.get("calculate_costs", False)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "cost_calculation_basis": str(scenario_dict.get("cost_calculation_basis") or "totalop"),
                "custom_cost_per_cf": float(scenario_dict.get("wall_insulation_custom_cost_per_cf") or scenario_dict.get("custom_cost_per_cf") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            print(f"  Applying wall insulation (R={scenario_dict['wall_r_value']}, material={wall_material_type})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForExteriorWalls", "IncreaseInsulationRValueForExteriorWalls", wall_args, failure_logger=log_failure):
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
                "use_lifetime_multiplier": bool(scenario_dict.get("use_lifetime_multiplier", False)),
                "gwp_statistic": "median",
                "api_key": EC3_API_TOKEN,
                "insulation_material_type": roof_material_type,
                "insulation_material_lifetime": roof_material_lifetime,
                "insulation_thermal_conductivity": 0.0,
                "insulation_material_density": 0.0,
                "calculate_costs": bool(scenario_dict.get("calculate_costs", False)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "cost_calculation_basis": str(scenario_dict.get("cost_calculation_basis") or "totalop"),
                "custom_cost_per_cf": float(scenario_dict.get("roof_insulation_custom_cost_per_cf") or scenario_dict.get("custom_cost_per_cf") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            print(f"  Applying roof insulation (R={scenario_dict['roof_r_value']}, material={roof_material_type})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "IncreaseInsulationRValueForRoofs", "IncreaseInsulationRValueForRoofs", roof_args, failure_logger=log_failure):
                print(f"   {scenario_name}: roof measure failed")
                log_failure("roof measure failed")
                del model
                return None
        if has_window_renovation:
            window_option = str(scenario_dict.get("window_option") or "none")
            legacy_window_option_map = {
                "wood-aluminum glazing window": "wood double glazing window",
                "wood-aluminum double glazing window": "wood double glazing window",
            }
            window_option = legacy_window_option_map.get(window_option.strip().lower(), window_option)
            requested_num_panes = scenario_dict.get("window_num_panes")
            
            # When entire window replacement is specified, glass_option should be "none"
            # and num_panes is not used (entire window includes glazing)
            if window_option.strip().lower() != "none":
                glass_option = "none"
                num_panes = 0
            elif requested_num_panes in [None, "", 0, 0.0]:
                # No specific pane count provided and no entire window replacement
                num_panes = 0
                glass_option = str(scenario_dict.get("glass_option") or "none")
            else:
                # Glass replacement specified
                raw_num_panes = int(float(requested_num_panes))
                num_panes = max(1, min(3, raw_num_panes))
                glass_option = str(scenario_dict.get("glass_option") or "provide user_num_panes")
            
            # Note: When window_option (entire window replacement) is specified,
            # the measure will ignore glass_option as entire window includes glazing.
            # No validation needed here - measure handles the logic internally.
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
                "use_lifetime_multiplier": bool(scenario_dict.get("use_lifetime_multiplier", False)),
                "glass_lifetime": float(scenario_dict.get("glass_lifetime") or 15),
                "window_lifetime": float(scenario_dict.get("wf_lifetime") or scenario_dict.get("window_lifetime") or 15),
                "caulking_lifetime": float(scenario_dict.get("caulking_lifetime") or 10),
                "film_lifetime": float(scenario_dict.get("film_lifetime") or 10),
                "weatherstrip_lifetime": float(scenario_dict.get("weatherstrip_lifetime") or 10),
                "window_option": window_option,
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
                "calculate_costs": bool(scenario_dict.get("calculate_costs", False)),
                "use_custom_costs": bool(scenario_dict.get("use_custom_costs", False)),
                "cost_calculation_basis": str(scenario_dict.get("cost_calculation_basis") or "totalop"),
                "glass_cost_per_cf": float(scenario_dict.get("glass_cost_per_cf") or 0.0),
                "frame_cost_per_sf": float(scenario_dict.get("frame_cost_per_sf") or 0.0),
                "caulking_cost_per_cy": float(scenario_dict.get("caulking_cost_per_cy") or 0.0),
                "film_cost_per_sf": float(scenario_dict.get("film_cost_per_sf") or 0.0),
                "weatherstrip_cost_per_lf": float(scenario_dict.get("weatherstrip_cost_per_lf") or 0.0),
                "u_factor_modification_percentage": float(scenario_dict.get("u_factor_modification_percentage") or 0.0),
                "shgc_modification_percentage": float(scenario_dict.get("shgc_modification_percentage") or 0.0),
                "visible_transmittance_modification_percentage": float(scenario_dict.get("visible_transmittance_modification_percentage") or 0.0),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 10.0),
            }
            if window_option.strip().lower() != "none":
                print(f"  Applying window enhancement (entire window: {window_option}, infiltration reduction: {window_infiltration_reduction}%)...")
            else:
                print(f"  Applying window enhancement (num_panes={num_panes}, glass_option={glass_option})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "window_enhancement", "WindowEnhancement", window_args, failure_logger=log_failure):
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
                "use_lifetime_multiplier": bool(scenario_dict.get("use_lifetime_multiplier", False)),
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
                "cost_calculation_basis": str(scenario_dict.get("cost_calculation_basis") or "totalop"),
                "labor_cost_multiplier": float(scenario_dict.get("labor_cost_multiplier") or 1.0),
                "overhead_profit_percent": float(scenario_dict.get("overhead_profit_percent") or 0.0),
            }
            print(f"  Applying door enhancement (door={door_args['door_option']})...")
            if not apply_python_measure(model, Path(measure_dir_path) / "door_enhancement", "DoorEnhancement", door_args, failure_logger=log_failure):
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
    - For climate-zone-specific R-value testing: filters combos to match each city's climate zone
    """
    # Climate zone to minimum wall R-value mapping (from ASHRAE 90.1)
    CLIMATE_ZONE_TO_R_VALUE = {
        "ASHRAE 169-2013-1A": 8.1,
        "ASHRAE 169-2013-2A": 11.9,
        "ASHRAE 169-2013-2B": 11.9,
        "ASHRAE 169-2013-3A": 13.0,
        "ASHRAE 169-2013-3B": 13.0,
        "ASHRAE 169-2013-3C": 13.0,
        "ASHRAE 169-2013-4A": 15.6,
        "ASHRAE 169-2013-4C": 15.6,
        "ASHRAE 169-2013-5A": 18.2,
        "ASHRAE 169-2013-5B": 18.2,
        "ASHRAE 169-2013-6A": 20.4,
        "ASHRAE 169-2013-6B": 20.4,
        "ASHRAE 169-2013-7A": 20.4,
        "ASHRAE 169-2013-8A": 27.0,
    }

    # Climate zone to minimum roof R-value mapping (from ASHRAE 90.1)
    CLIMATE_ZONE_TO_ROOF_R_VALUE = {
        "ASHRAE 169-2013-1A": 24.4,
        "ASHRAE 169-2013-2A": 24.4,
        "ASHRAE 169-2013-2B": 24.4,
        "ASHRAE 169-2013-3A": 24.4,
        "ASHRAE 169-2013-3B": 24.4,
        "ASHRAE 169-2013-3C": 24.4,
        "ASHRAE 169-2013-4A": 27.0,
        "ASHRAE 169-2013-4C": 27.0,
        "ASHRAE 169-2013-5A": 27.0,
        "ASHRAE 169-2013-5B": 27.0,
        "ASHRAE 169-2013-6A": 32.3,
        "ASHRAE 169-2013-6B": 32.3,
        "ASHRAE 169-2013-7A": 34.5,
        "ASHRAE 169-2013-8A": 38.5,
    }

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
            "window_option": None,
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
                city_climate_zone = city_climate_zones.get(city)
                city_target_wall_r_value = CLIMATE_ZONE_TO_R_VALUE.get(city_climate_zone)
                city_target_roof_r_value = CLIMATE_ZONE_TO_ROOF_R_VALUE.get(city_climate_zone)

                combo_wall_r_value = combo.get("wall_r_value")
                combo_roof_r_value = combo.get("roof_r_value")
                if combo_roof_r_value in (0, 0.0, "0", "0.0"):
                    combo_roof_r_value = None

                # Skip combos whose wall/roof R-values do not match the city's climate-zone targets.
                if combo_wall_r_value is not None and city_target_wall_r_value is not None:
                    if abs(float(combo_wall_r_value) - float(city_target_wall_r_value)) > 0.01:
                        continue
                if combo_roof_r_value is not None and city_target_roof_r_value is not None:
                    if abs(float(combo_roof_r_value) - float(city_target_roof_r_value)) > 0.01:
                        continue

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


def export_scenario_user_arguments_csv(base_run_dir, scenarios, ec3_api_token=None):
    """Export requested scenario arguments used by report post-processing."""
    output_path = Path(base_run_dir) / "scenario_user_arguments.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for scenario in scenarios:
        scenario_name = generate_scenario_name(scenario)

        window_option = scenario.get("window_option")
        if str(window_option or "").strip().lower() in {"", "none"}:
            window_option = scenario.get("wf_option")

        window_infiltration_reduction = scenario.get(
            "window_enhancement_infiltration_reduction_percent",
            scenario.get("window_infiltration_reduction_percent"),
        )
        window_requested = any([
            scenario.get("window_num_panes") not in [None, "", 0, 0.0],
            window_infiltration_reduction not in [None, "", 0, 0.0],
            str(scenario.get("weatherstrip_option", "none")).strip().lower() != "none",
            str(window_option or "none").strip().lower() != "none",
            str(scenario.get("film_option", "none")).strip().lower() != "none",
            str(scenario.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        door_requested = any([
            str(scenario.get("door_option", "none")).strip().lower() != "none",
            scenario.get("door_infiltration_reduction_percent") not in [None, "", 0, 0.0],
            str(scenario.get("door_bottom_seal_option", "none")).strip().lower() != "none",
            str(scenario.get("door_top_side_seal_option", "none")).strip().lower() != "none",
        ])

        wall_status = "applied" if scenario.get("wall_r_value") else "not_applied"
        roof_status = "applied" if scenario.get("roof_r_value") else "not_applied"
        window_status = "applied" if window_requested else "not_applied"
        door_status = "applied" if door_requested else "not_applied"

        rows.extend([
            {"scenario": scenario_name, "measure": "wall", "argument": "__status__", "value": wall_status},
            {"scenario": scenario_name, "measure": "wall", "argument": "r_value", "value": scenario.get("wall_r_value") or ""},
            {"scenario": scenario_name, "measure": "wall", "argument": "insulation_material_type", "value": scenario.get("wall_insulation_material_type") or ""},
            {"scenario": scenario_name, "measure": "roof", "argument": "__status__", "value": roof_status},
            {"scenario": scenario_name, "measure": "roof", "argument": "r_value", "value": scenario.get("roof_r_value") or ""},
            {"scenario": scenario_name, "measure": "roof", "argument": "insulation_material_type", "value": scenario.get("roof_insulation_material_type") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "__status__", "value": window_status},
            {"scenario": scenario_name, "measure": "window", "argument": "user_num_panes", "value": scenario.get("window_num_panes") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "u_value", "value": scenario.get("u_value") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "weatherstrip_option", "value": scenario.get("weatherstrip_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "u_factor_modification_percentage", "value": scenario.get("u_factor_modification_percentage") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "shgc_modification_percentage", "value": scenario.get("shgc_modification_percentage") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "visible_transmittance_modification_percentage", "value": scenario.get("visible_transmittance_modification_percentage") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "film_option", "value": scenario.get("film_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "window_option", "value": window_option or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "wf_option", "value": scenario.get("wf_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "caulking_option", "value": scenario.get("caulking_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "secondary_glazing_option", "value": scenario.get("secondary_glazing_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "glass_option", "value": scenario.get("glass_option") or ""},
            {"scenario": scenario_name, "measure": "window", "argument": "window_infiltration_reduction_percent", "value": scenario.get("window_infiltration_reduction_percent") or scenario.get("window_enhancement_infiltration_reduction_percent") or ""},
            {"scenario": scenario_name, "measure": "door", "argument": "__status__", "value": door_status},
            {"scenario": scenario_name, "measure": "door", "argument": "door_option", "value": scenario.get("door_option") or ""},
            {"scenario": scenario_name, "measure": "door", "argument": "door_bottom_seal_option", "value": scenario.get("door_bottom_seal_option") or ""},
            {"scenario": scenario_name, "measure": "door", "argument": "door_top_side_seal_option", "value": scenario.get("door_top_side_seal_option") or ""},
        ])

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["scenario", "measure", "argument", "value"])
        writer.writeheader()
        writer.writerows(rows)

    return output_path

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


def extract_fuel_energy_gj(sql_path):
    """Extract site energy by fuel type from EnergyPlus SQL End Uses table (GJ)."""
    result = {}
    try:
        with sqlite3.connect(str(sql_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ColumnName, SUM(CAST(Value AS REAL)) as total_gj
                FROM TabularDataWithStrings
                WHERE lower(ReportName) = 'annualbuildingutilityperformancesummary'
                  AND lower(TableName) = 'end uses'
                  AND lower(RowName) != 'total end uses'
                  AND lower(Units) = 'gj'
                GROUP BY ColumnName
                """
            )
            for col_name, total_gj in cur.fetchall():
                if total_gj is not None and float(total_gj) > 0:
                    slug = str(col_name).strip().lower().replace(" ", "_").replace("-", "_")
                    result[f"{slug}_site_energy_gj"] = round(float(total_gj), 4)
    except Exception as e:
        print(f"     Failed to read fuel energy from SQL {sql_path}: {e}")
    return result

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
    window_inventory = collect_window_inventory(model)
    door_inventory = collect_door_inventory(model)
    results.update(window_inventory)
    results.update(door_inventory)
    baseline_details_html = None
    if scenario_name.startswith("baseline"):
        envelope_inventory = collect_baseline_envelope_inventory(model)
        results.update(envelope_inventory)
        baseline_details_html = build_baseline_renovation_details(
            envelope_inventory,
            window_inventory,
            door_inventory,
        )
        results["renovation_details"] = baseline_details_html or "Baseline (no envelope renovation)"
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
        # Support both legacy and current window measure field names
        window_carbon = (
            float(results.get("window_enhancement_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            or float(results.get("window_embodied_carbon_kgCO2eq", 0.0) or 0.0)
        )
        total_embodied = (
            float(results.get("wall_insulation_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            + float(results.get("roof_insulation_embodied_carbon_kgCO2eq", 0.0) or 0.0)
            + window_carbon
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
    if scenario_name.startswith("baseline") and baseline_details_html:
        results["renovation_details"] = baseline_details_html
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
        "wall_insulation_cost_calculation_basis": "wall_insulation_cost_calculation_basis",
        "roof_insulation_material_cost_$": "roof_insulation_material_cost_usd",
        "roof_insulation_labor_cost_$": "roof_insulation_labor_cost_usd",
        "roof_insulation_equipment_cost_$": "roof_insulation_equipment_cost_usd",
        "roof_insulation_overhead_profit_cost_$": "roof_insulation_overhead_profit_cost_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_$": "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_cost_calculation_basis": "roof_insulation_cost_calculation_basis",
        "window_enhancement_material_cost_$": "window_enhancement_material_cost_usd",
        "window_enhancement_labor_cost_$": "window_enhancement_labor_cost_usd",
        "window_enhancement_overhead_profit_cost_$": "window_enhancement_overhead_profit_cost_usd",
        "window_enhancement_total_cost_with_overhead_and_profit_$": "window_enhancement_total_cost_with_overhead_and_profit_usd",
        "window_cost_calculation_basis": "window_cost_calculation_basis",
        "door_enhancement_material_cost_$": "door_enhancement_material_cost_usd",
        "door_enhancement_labor_cost_$": "door_enhancement_labor_cost_usd",
        "door_enhancement_overhead_profit_cost_$": "door_enhancement_overhead_profit_cost_usd",
        "door_enhancement_total_cost_with_overhead_and_profit_$": "door_enhancement_total_cost_with_overhead_and_profit_usd",
        "door_cost_calculation_basis": "door_cost_calculation_basis",
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
        "door_enhancement_custom_bottom_seal_cost_per_lf",
        "door_enhancement_custom_top_side_seal_cost_per_lf",
        "door_custom_door_cost_per_sf",
        "door_custom_bottom_seal_cost_per_lf",
        "door_custom_top_side_seal_cost_per_lf",
        "door_api_door_cost_per_sf",
        "door_api_bottom_seal_cost_per_lf",
        "door_api_top_side_seal_cost_per_lf",
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

    _legacy_door_unit_keys = {
        "door_custom_door_cost_per_area",
        "door_api_door_cost_per_area",
        "door_api_bottom_seal_cost_per_m",
        "door_api_top_side_seal_cost_per_m",
    }
    _new_door_unit_keys = {
        "door_custom_door_cost_per_sf",
        "door_api_door_cost_per_sf",
        "door_api_bottom_seal_cost_per_lf",
        "door_api_top_side_seal_cost_per_lf",
    }
    _legacy_key_found = any(key in results for key in _legacy_door_unit_keys)
    _new_key_found = any(key in results for key in _new_door_unit_keys)
    if _legacy_key_found and not _new_key_found:
        print("Warning: Found legacy door unit-cost keys without new sf/lf keys in AdditionalProperties.")

    for key in _new_door_unit_keys:
        if key not in results:
            continue
        num_val = _safe_float(results.get(key))
        if num_val is None or num_val < 0.0:
            print(f"Warning: Invalid value for '{key}' in AdditionalProperties; treating as empty.")
            results[key] = ""

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
    # If missing, fall back to component sums. Wall/roof use *_usd keys;
    # window/door measures may expose *_$ keys.
    wall_total = float(results.get("wall_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    roof_total = float(results.get("roof_insulation_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    if wall_total <= 0.0:
        wall_total = (
            float(results.get("wall_insulation_material_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_labor_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_equipment_cost_usd", 0.0) or 0.0)
            + float(results.get("wall_insulation_overhead_profit_cost_usd", 0.0) or 0.0)
        )
    if roof_total <= 0.0:
        roof_total = (
            float(results.get("roof_insulation_material_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_labor_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_equipment_cost_usd", 0.0) or 0.0)
            + float(results.get("roof_insulation_overhead_profit_cost_usd", 0.0) or 0.0)
        )

    window_total = float(results.get("window_total_cost_with_overhead_and_profit_$", 0.0) or 0.0)
    if window_total <= 0.0:
        window_total = float(results.get("window_enhancement_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    if window_total <= 0.0:
        window_total = (
            float(results.get("window_material_cost_$", 0.0) or 0.0)
            + float(results.get("window_labor_cost_$", 0.0) or 0.0)
            + float(results.get("window_equipment_cost_$", 0.0) or 0.0)
            + float(results.get("window_overhead_profit_cost_$", 0.0) or 0.0)
        )
    if window_total <= 0.0:
        window_total = (
            float(results.get("window_enhancement_material_cost_usd", 0.0) or 0.0)
            + float(results.get("window_enhancement_labor_cost_usd", 0.0) or 0.0)
            + float(results.get("window_enhancement_overhead_profit_cost_usd", 0.0) or 0.0)
        )
    door_total = float(results.get("door_enhancement_total_cost_with_overhead_and_profit_usd", 0.0) or 0.0)
    if door_total <= 0.0:
        door_total = float(results.get("door_total_cost_with_overhead_and_profit_$", 0.0) or 0.0)
    if door_total <= 0.0:
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

    # Extract per-fuel site energy from SQL (water is excluded because it is m3, not GJ).
    sql_path_fuel = osm_path.parent / "eplusout.sql"
    if sql_path_fuel.exists():
        fuel_data = extract_fuel_energy_gj(sql_path_fuel)
        for fkey, fval in fuel_data.items():
            if fkey not in results and fval is not None:
                results[fkey] = fval
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
        "electricity_site_energy_gj",
        "natural_gas_site_energy_gj",
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
        "door_enhancement_custom_bottom_seal_cost_per_lf",
        "door_enhancement_custom_top_side_seal_cost_per_lf",
        "door_custom_door_cost_per_sf",
        "door_custom_bottom_seal_cost_per_lf",
        "door_custom_top_side_seal_cost_per_lf",
        "door_api_door_cost_per_sf",
        "door_api_bottom_seal_cost_per_lf",
        "door_api_top_side_seal_cost_per_lf",
        "wall_insulation_embodied_carbon_kgCO2eq",
        "roof_insulation_embodied_carbon_kgCO2eq",
        "window_enhancement_embodied_carbon_kgCO2eq",
        "door_enhancement_embodied_carbon_kgCO2eq",
        "wall_insulation_custom_labor_cost_multiplier",
        "wall_insulation_custom_cost_per_cf",
        "roof_insulation_custom_labor_cost_multiplier",
        "roof_insulation_custom_cost_per_cf",
        "wall_insulation_cost_calculation_basis",
        "roof_insulation_cost_calculation_basis",
        "window_cost_calculation_basis",
        "door_cost_calculation_basis",
        "wall_insulation_total_cost_with_overhead_and_profit_usd",
        "roof_insulation_total_cost_with_overhead_and_profit_usd",
        "window_enhancement_total_cost_with_overhead_and_profit_usd",
        "door_enhancement_total_cost_with_overhead_and_profit_usd",
        "wall_insulation_material_cost_usd",
        "wall_insulation_labor_cost_usd",
        "wall_insulation_overhead_profit_cost_usd",
        "roof_insulation_material_cost_usd",
        "roof_insulation_labor_cost_usd",
        "roof_insulation_equipment_cost_usd",
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
# RUN_NAME, OVERWRITE_EXISTING, and CUSTOM_COMBOS can be overridden via env vars
# (used by run_all_tests.py to drive multiple sequential runs without editing this file).
# RUN_NAME is purely a folder label under simulations/ -- it has no effect on
# the model itself. Defaults to "run_test_009" for this branch's ad-hoc standalone runs.
RUN_NAME = os.environ.get("WORKFLOW_RUN_NAME", "roof_insulation_case_study")
def detect_openstudio_cli_path():
    """Find the OpenStudio CLI executable on this machine.

    Tries OPENSTUDIO_PATH, then PATH lookup, then platform-specific install
    folders (Program Files on Windows, /Applications on macOS). Returns the
    first existing path or None.
    """
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
# OVERWRITE_EXISTING=True forces every selected scenario to re-simulate even
# if its eplusout.sql already exists. Defaults to skipping completed runs.
OVERWRITE_EXISTING = os.environ.get("WORKFLOW_OVERWRITE_EXISTING", "0").lower() in ("1", "true", "yes")

# Project layout: this script lives in lib/parametric_run/.
notebook_dir = Path(__file__).parent                       # lib/parametric_run/
base_weather_path = str(notebook_dir / "weather")          # EPW/DDY per city
measure_dir_path = str(notebook_dir.parent / "measures")   # lib/measures/
base_run_dir = str(notebook_dir / "simulations" / RUN_NAME)  # this run's outputs

# Default to local RSMeans CSV mode so cost lookups can run without live
# API credentials across all workflow test runs. Callers can still override
# via pre-set environment variables.
os.environ.setdefault("RSMEANS_OFFLINE_CSV_FORCE", "1")
os.environ.setdefault(
    "RSMEANS_OFFLINE_CSV_PATH",
    str(notebook_dir / "custom_cost_datasets" / "2026_rsmeans_data.csv"),
)

city_climate_zones = {
    "IL_Chicago_Midway":      "ASHRAE 169-2013-5A",
    # "MN_Duluth":       "ASHRAE 169-2013-7A",
    # "ME_Bangor":        "ASHRAE 169-2013-6A",
    "TX_Houston":      "ASHRAE 169-2013-2A",
    "FL_Miami":        "ASHRAE 169-2013-1A",
    "MN_Minneapolis":  "ASHRAE 169-2013-6A",
    # "AZ_Phoenix":      "ASHRAE 169-2013-2B",
    # "NV_Las_Vegas":      "ASHRAE 169-2013-3B",
    # "CA_San_Francisco": "ASHRAE 169-2013-3C",
    # "WA_Seattle":      "ASHRAE 169-2013-4C",
}

# --- PARAMETRIC STUDY CONFIGURATION ---
CITIES = list(city_climate_zones.keys())
BUILDING_TYPES = [
    # "LargeOffice",
    # "MediumOffice",
     "SmallOffice",
    # "SmallHotel",
    # "LargeHotel",
    # "Warehouse",
    # "RetailStandalone",
    # "RetailStripmall",
    # "PrimarySchool",
    # "SecondarySchool",
]

#TEMPLATE = "90.1-2004"
#TEMPLATE = "DOE Ref 1980-2004"
TEMPLATE = "DOE Ref Pre-1980"

# --- CUSTOM COMBINATION SCENARIOS ---
# Each entry in CUSTOM_COMBOS is a retrofit "recipe" applied on top of the
# baseline DOE prototype. A baseline scenario is generated automatically and
# does NOT need to be listed here. Set a measure key to None (or omit it) to
# skip that measure for the scenario.
#
# Required-ish core keys:
#   wall_r_value           Target R-value (h*ft^2*F/Btu) for wall measure, or None.
#   roof_r_value           Target R-value for roof measure, or None.
#   window_num_panes       1, 2, or 3 to upgrade glazing (None = no glazing change).
#   door_option            "glass door" / "wooden door" / "polystyrene core steel door" / etc.
#
# Supported optional keys (all envelope-measure tuning):
#   - window_infiltration_reduction_percent, door_infiltration_reduction_percent
#   - weatherstrip_option, window_option, film_option, caulking_option, secondary_glazing_option
#   - door_bottom_seal_option, door_top_side_seal_option
#   - wall_insulation_material_type, wall_insulation_material_lifetime
#   - roof_insulation_material_type, roof_insulation_material_lifetime
## When run_all_tests.py drives this script, WORKFLOW_CUSTOM_COMBOS_JSON
# (set near the bottom of this section) replaces the file-based defaults.

_CUSTOM_COMBOS_PATH = Path(__file__).with_name("roof_insulation_case_study.json")
with open(_CUSTOM_COMBOS_PATH, "r", encoding="utf-8") as _custom_combos_file:
    CUSTOM_COMBOS = json.load(_custom_combos_file)

# Optional override via env var (JSON-encoded list of combo dicts) so that
# run_all_tests.py can drive multiple sequential runs.
_combos_override_json = os.environ.get("WORKFLOW_CUSTOM_COMBOS_JSON")
if _combos_override_json:
    import json as _json
    CUSTOM_COMBOS = _json.loads(_combos_override_json)

def scenario_output_exists(base_run_dir, scenario_dict):
    """Return True if this scenario's EnergyPlus SQL output already exists."""
    scenario_name = generate_scenario_name(scenario_dict)
    sql_path = os.path.join(base_run_dir, scenario_name, "run", "eplusout.sql")
    return os.path.exists(sql_path)

# --- MAIN - RUN PARAMETRIC STUDY ---
# Pipeline: validate CLI -> generate scenarios -> run sims -> recap CSV
# -> HTML/PDF report (the report stage lives further down, after the spider
# chart helpers; it runs against parametric_results.csv produced here).
class _TeeStream:
    """Write-through wrapper that mirrors writes to a stream and a log file."""

    def __init__(self, primary, log_file):
        self._primary = primary
        self._log_file = log_file

    def write(self, data):
        self._primary.write(data)
        try:
            self._log_file.write(data)
            self._log_file.flush()
        except Exception:
            pass
        return len(data) if isinstance(data, str) else 0

    def flush(self):
        self._primary.flush()
        try:
            self._log_file.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._primary, name)


def _install_workflow_log_tee(log_path):
    """Tee stdout/stderr to log_path so failure detail isn't lost on console close."""
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        log_file.write(f"\n===== workflow run started {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        sys.stdout = _TeeStream(sys.stdout, log_file)
        sys.stderr = _TeeStream(sys.stderr, log_file)
        return log_file
    except Exception as tee_err:
        print(f"Warning: failed to enable workflow log tee at {log_path}: {tee_err}")
        return None


if __name__ == "__main__":
    # Phase 0: sanity-check that the OpenStudio CLI was found.
    if not OPENSTUDIO_PATH:
        raise RuntimeError(
            "OpenStudio CLI not found. Set OPENSTUDIO_PATH to your openstudio executable, "
            "or add openstudio to PATH."
        )

    # Tee all stdout/stderr to simulations/<RUN_NAME>/workflow.log so that
    # measure errors and tracebacks survive after the console closes.
    _install_workflow_log_tee(os.path.join(base_run_dir, "workflow.log"))

    print("\n" + "=" * 70)
    print("PARAMETRIC STUDY: BUILDING ENERGY EFFICIENCY MEASURES")
    print(f"Using OpenStudio: {OPENSTUDIO_PATH}")
    print(f"Run Name: {RUN_NAME}")
    print(f"Output Directory: {base_run_dir}")
    print("=" * 70)
    # Phase 1: build the full scenario list (baseline + each custom combo per
    # city / building type).
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
    # Phase 2: run EnergyPlus for each scenario (or skip if all outputs exist
    # and the user did not request OVERWRITE_EXISTING).
    sim_count = 0
    start_time = time.time()
    successful_scenarios = []
    failed_scenarios = []
    all_selected_have_results = all(scenario_output_exists(base_run_dir, s) for s in scenarios)
    skip_simulation_run = all_selected_have_results and CUSTOM_COMBOS and not OVERWRITE_EXISTING
    if skip_simulation_run:
        # Fast path: only re-run postprocessing/reporting against existing OSMs.
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

    # Phase 3: postprocess -- read each scenario's modified OSM and pull
    # AdditionalProperties (cost, embodied carbon, retrofit settings, etc.)
    # into simulations/<RUN_NAME>/parametric_results.csv. The HTML/PDF
    # report is rendered later by the report-generation block below.
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

WINDOW_EC_PRIMARY_COL = "window_enhancement_embodied_carbon_kgCO2eq"
WINDOW_EC_LEGACY_COL = "window_embodied_carbon_kgCO2eq"


def _numeric_series_with_default(frame, col):
    if col in frame.columns:
        return pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(frame), index=frame.index)


def _window_embodied_series(frame):
    current = _numeric_series_with_default(frame, WINDOW_EC_PRIMARY_COL)
    legacy = _numeric_series_with_default(frame, WINDOW_EC_LEGACY_COL)
    return current.where(current > 0, legacy)


def _reconcile_window_embodied_column(frame, emit_logs=False):
    if WINDOW_EC_LEGACY_COL in frame.columns and WINDOW_EC_PRIMARY_COL not in frame.columns:
        frame[WINDOW_EC_PRIMARY_COL] = _numeric_series_with_default(frame, WINDOW_EC_LEGACY_COL)
        if emit_logs:
            print("Info: Using 'window_embodied_carbon_kgCO2eq' for window enhancement carbon calculation")

    if WINDOW_EC_LEGACY_COL in frame.columns and WINDOW_EC_PRIMARY_COL in frame.columns:
        current = _numeric_series_with_default(frame, WINDOW_EC_PRIMARY_COL)
        merged = _window_embodied_series(frame)
        if emit_logs and not merged.equals(current):
            print("Info: Filled window_enhancement_embodied_carbon_kgCO2eq from legacy values where needed")
        frame[WINDOW_EC_PRIMARY_COL] = merged

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

_reconcile_window_embodied_column(df, emit_logs=True)

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
df["annual_operational_energy_gj"] = pd.to_numeric(df["total_site_energy_gj"], errors="coerce").fillna(0.0)

if available_construction_cost_col:
    df["total_construction_cost_usd"] = pd.to_numeric(df[available_construction_cost_col], errors="coerce").fillna(0.0)
else:
    df["total_construction_cost_usd"] = 0.0

# Calculate payback periods relative to baseline
baseline_mask = df["scenario"].astype(str).str.contains("baseline", case=False, na=False)
if baseline_mask.any():
    baselines = df[baseline_mask].copy()

    if "city" in df.columns:
        city_series = df["city"].astype(str)
    else:
        city_series = pd.Series(["Unknown"] * len(df), index=df.index)

    if city_series.str.strip().eq("").all() or city_series.str.strip().eq("Unknown").all():
        def _extract_city_from_scenario(scenario_name):
            match = re.search(r'_(Amarillo|Atlanta|Baltimore|Buffalo|Chicago|Denver|Duluth|ElPaso|Fairbanks|Helena|Houston|Miami|Minneapolis|Phoenix|PortAngeles|Portland|SanFrancisco)(?:_|$)', str(scenario_name))
            if match:
                return match.group(1)
            return "Unknown"

        city_series = df["scenario"].astype(str).apply(_extract_city_from_scenario)

    df["city"] = city_series
    baseline_by_city = {}
    for _, baseline_row in baselines.iterrows():
        baseline_by_city[str(baseline_row.get("city", "Unknown"))] = baseline_row
    default_baseline = baselines.iloc[0]

    # Calculate cost and carbon deltas per city-specific baseline
    df["cost_delta"] = 0.0
    df["emissions_delta"] = 0.0
    df["energy_delta"] = 0.0
    df["energy_delta_pct"] = 0.0
    for idx, row in df.iterrows():
        city_name = str(row.get("city", "Unknown"))
        city_baseline = baseline_by_city.get(city_name, default_baseline)
        df.at[idx, "cost_delta"] = city_baseline["annual_operational_cost_usd"] - row["annual_operational_cost_usd"]
        df.at[idx, "emissions_delta"] = city_baseline["annual_operational_carbon_kg_co2e"] - row["annual_operational_carbon_kg_co2e"]
        df.at[idx, "energy_delta"] = city_baseline["annual_operational_energy_gj"] - row["annual_operational_energy_gj"]
        df.at[idx, "energy_delta_pct"] = (
            df.at[idx, "energy_delta"] / city_baseline["annual_operational_energy_gj"] * 100.0
            if city_baseline["annual_operational_energy_gj"] > 0
            else 0.0
        )
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
# (auxiliary/ is already on sys.path from the top-level setup above)
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
    """Render the interactive HTML retrofit report from parametric_results.csv.

    Inputs the recap DataFrame (one row per scenario, baseline first) and
    writes the HTML file at html_report_path. The report includes a building
    info card, scenario comparison tables, embodied/operational charts, and
    a spider chart. Downstream patch helpers (_patch_*) refine the page after
    this function returns.
    """
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

    _reconcile_window_embodied_column(df)
    wall_ec = _to_num(df, "wall_insulation_embodied_carbon_kgCO2eq")
    roof_ec = _to_num(df, "roof_insulation_embodied_carbon_kgCO2eq")
    window_ec = _window_embodied_series(df)
    door_ec = _to_num(df, "door_enhancement_embodied_carbon_kgCO2eq")
    report = pd.DataFrame({

        "scenario": df[scenario_col].astype(str),
        "city": df["city"].astype(str) if "city" in df.columns else pd.Series(["Unknown"] * len(df)),
        "annual_cost_usd": elec_cost + gas_cost,
        "annual_emissions_kg": elec_emis + gas_emis,
        "total_site_energy_gj": site_energy,
        "annual_operational_energy_gj": site_energy,
        "analysis_period_years": analysis_period_years,
        "wall_ec": wall_ec,
        "roof_ec": roof_ec,
        "window_ec": window_ec,
        "door_ec": door_ec,

    })

    if "city" not in df.columns or report["city"].str.strip().eq("").all() or report["city"].str.strip().eq("Unknown").all():
        def extract_city(scenario_name):
            match = re.search(r'_(Amarillo|Atlanta|Baltimore|Buffalo|Chicago|Denver|Duluth|ElPaso|Fairbanks|Helena|Houston|Miami|Minneapolis|Phoenix|PortAngeles|Portland|SanFrancisco)(?:_|$)', str(scenario_name))
            if match:
                return match.group(1)
            return "Unknown"

        report["city"] = report["scenario"].apply(extract_city)

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
    baselines = report[baseline_mask].copy()
    baseline_by_city = {}
    for _, baseline_row in baselines.iterrows():
        city_name = baseline_row.get("city", "Unknown")
        baseline_by_city[city_name] = baseline_row
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

    comparison_df["cost_delta"] = 0.0
    comparison_df["cost_delta_pct"] = 0.0
    comparison_df["emissions_delta"] = 0.0
    comparison_df["emissions_delta_pct"] = 0.0
    comparison_df["energy_delta"] = 0.0
    comparison_df["energy_delta_pct"] = 0.0
    for idx, row in comparison_df.iterrows():
        city_name = row.get("city", "Unknown")
        city_baseline = baseline_by_city.get(city_name, b)
        comparison_df.at[idx, "cost_delta"] = row["annual_cost_usd"] - city_baseline["annual_cost_usd"]
        comparison_df.at[idx, "cost_delta_pct"] = (
            comparison_df.at[idx, "cost_delta"] / city_baseline["annual_cost_usd"] * 100.0
            if city_baseline["annual_cost_usd"] > 0
            else 0.0
        )
        comparison_df.at[idx, "emissions_delta"] = row["annual_emissions_kg"] - city_baseline["annual_emissions_kg"]
        comparison_df.at[idx, "emissions_delta_pct"] = (
            comparison_df.at[idx, "emissions_delta"] / city_baseline["annual_emissions_kg"] * 100.0
            if city_baseline["annual_emissions_kg"] > 0
            else 0.0
        )
        comparison_df.at[idx, "energy_delta"] = city_baseline["annual_operational_energy_gj"] - row["annual_operational_energy_gj"]
        comparison_df.at[idx, "energy_delta_pct"] = (
            comparison_df.at[idx, "energy_delta"] / city_baseline["annual_operational_energy_gj"] * 100.0
            if city_baseline["annual_operational_energy_gj"] > 0
            else 0.0
        )
    if comparison_df.empty:
        max_savings = b
        max_emissions_reduction = b
        max_savings_scenario = "No renovation scenarios"
        max_emissions_scenario = "No renovation scenarios"
        max_cost_delta = 0.0
        max_cost_delta_pct = 0.0
        max_emis_delta = 0.0
        max_emis_delta_pct = 0.0
        max_energy_savings_row = b
        max_energy_scenario = "No renovation scenarios"
        max_energy_delta_gj = 0.0
        max_energy_delta_pct = 0.0
        max_energy_class = ""
        max_energy_savings_text = "N/A"
        max_energy_savings_scenario = "No renovation scenarios"
        baseline_energy_w = 0.0
        best_energy_w = 0.0

    else:
        max_savings = comparison_df.loc[comparison_df["cost_delta"].idxmin()]
        max_emissions_reduction = comparison_df.loc[comparison_df["emissions_delta"].idxmin()]
        max_energy_savings_row = comparison_df.loc[comparison_df["energy_delta"].idxmax()]
        max_savings_scenario = scenario_display_map.get(str(max_savings["scenario"]), str(max_savings["scenario"]))
        max_emissions_scenario = scenario_display_map.get(str(max_emissions_reduction["scenario"]), str(max_emissions_reduction["scenario"]))
        max_energy_scenario = scenario_display_map.get(str(max_energy_savings_row["scenario"]), str(max_energy_savings_row["scenario"]))
        max_cost_delta = float(max_savings["cost_delta"])
        max_cost_delta_pct = float(max_savings["cost_delta_pct"])
        max_emis_delta = float(max_emissions_reduction["emissions_delta"])
        max_emis_delta_pct = float(max_emissions_reduction["emissions_delta_pct"])
        max_energy_delta_gj = float(max_energy_savings_row["energy_delta"])
        max_energy_delta_pct = float(max_energy_savings_row["energy_delta_pct"])
        max_energy_class = "positive" if max_energy_delta_gj >= 0 else ""
        max_energy_savings_text = f"{max_energy_delta_gj:,.2f} GJ/yr" if max_energy_delta_gj > 0 else "N/A"
        max_energy_savings_scenario = max_energy_scenario
        energy_chart_baseline = baseline_by_city.get(str(max_energy_savings_row.get("city", "Unknown")), b)
        max_chart_energy = max(energy_chart_baseline["annual_operational_energy_gj"], max_energy_savings_row["annual_operational_energy_gj"], 1.0)
        baseline_energy_w = energy_chart_baseline["annual_operational_energy_gj"] / max_chart_energy * 100.0
        best_energy_w = max_energy_savings_row["annual_operational_energy_gj"] / max_chart_energy * 100.0

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
    cost_chart_baseline = baseline_by_city.get(max_savings.get("city", "Unknown"), b)
    emis_chart_baseline = baseline_by_city.get(max_emissions_reduction.get("city", "Unknown"), b)
    max_chart_cost = max(cost_chart_baseline["annual_cost_usd"], max_savings["annual_cost_usd"], 1.0)
    baseline_cost_w = cost_chart_baseline["annual_cost_usd"] / max_chart_cost * 100.0
    best_cost_w = max_savings["annual_cost_usd"] / max_chart_cost * 100.0
    max_chart_emis = max(emis_chart_baseline["annual_emissions_kg"], max_emissions_reduction["annual_emissions_kg"], 1.0)
    baseline_emis_w = emis_chart_baseline["annual_emissions_kg"] / max_chart_emis * 100.0
    best_emis_w = max_emissions_reduction["annual_emissions_kg"] / max_chart_emis * 100.0
    baseline_cost_value = float(cost_chart_baseline["annual_cost_usd"])
    baseline_emis_value = float(emis_chart_baseline["annual_emissions_kg"])
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

    def _extract_location_info(row):
        """Extract weather file and building location for a scenario."""
        weather_file = None
        building_location = None
        
        # Try to extract location info from scenario column name
        # Pattern: baseline_SmallOffice_IL_Chicago_Midway or scenario_1_SmallOffice_IL_Chicago_Midway
        scenario_name = str(row.get(scenario_col, ""))
        parts = scenario_name.split("_")
        
        state_code = None
        city_name = None
        weather_folder = None
        
        # Determine where the building_type is (different for baseline vs scenario_N)
        building_type_idx = None
        state_code_idx = None
        
        if len(parts) >= 3:
            if parts[0].lower() == "baseline":
                # baseline_SmallOffice_IL_...
                building_type_idx = 1
                state_code_idx = 2
            elif parts[0].lower() == "scenario":
                # scenario_1_SmallOffice_IL_...
                if len(parts) >= 4 and parts[1].isdigit():
                    building_type_idx = 2
                    state_code_idx = 3
        
        if state_code_idx is not None and state_code_idx < len(parts):
            state_code = parts[state_code_idx]
            
            # Reconstruct the weather folder path from scenario parts
            # We need to handle cases like "Chicago_Midway" or "San_Francisco"
            if state_code_idx + 1 < len(parts):
                remaining_parts = parts[state_code_idx + 1:]  # ["Chicago", "Midway"] or ["San", "Francisco"] etc.
                # Try to find matching weather folder by combining parts progressively
                for i in range(len(remaining_parts), 0, -1):
                    potential_folder = f"{state_code}_{'_'.join(remaining_parts[:i])}"
                    # Check if this folder exists
                    potential_path = os.path.join(globals().get("base_weather_path", "lib/parametric_run/weather"), potential_folder)
                    if os.path.exists(potential_path):
                        weather_folder = potential_folder
                        city_name = "_".join(remaining_parts[:i]).replace("_", " ")
                        break
        
        # If we found the weather folder, use it to get weather files
        if weather_folder and "get_city_weather_files" in globals():
            weather_files = get_city_weather_files(weather_folder, globals().get("base_weather_path", ""))
            if weather_files and weather_files.get("epw"):
                weather_file = Path(str(weather_files["epw"])).name
        
        # Fall back to city column if available
        if not weather_file:
            for col in ["weather_file", "epw_file", "epw_filename", "epw_name"]:
                if col in df.columns and _has_meaningful_value(row.get(col)):
                    weather_file = Path(str(row[col])).name
                    break
        
        if not weather_file:
            weather_file = "N/A"
        
        # Build building location string
        if city_name and state_code:
            building_location = f"{city_name}, {state_code}"
        elif city_name:
            building_location = city_name
        elif state_code:
            building_location = state_code
        else:
            building_location = "N/A"
        
        return weather_file, building_location

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
            str(scenario_cfg.get("window_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("film_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("caulking_option", "none")).strip().lower() != "none",
            str(scenario_cfg.get("secondary_glazing_option", "none")).strip().lower() != "none",
        ])
        door_requested = any([
            str(scenario_cfg.get("door_option", "none")).strip().lower() != "none",
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
                "window_infiltration_reduction_percent": scenario_cfg.get("window_infiltration_reduction_percent") or scenario_cfg.get("window_enhancement_infiltration_reduction_percent"),
                "u_factor_modification_percentage": scenario_cfg.get("u_factor_modification_percentage"),
                "shgc_modification_percentage": scenario_cfg.get("shgc_modification_percentage"),
                "visible_transmittance_modification_percentage": scenario_cfg.get("visible_transmittance_modification_percentage"),
                "film_option": scenario_cfg.get("film_option"),
                "window_option": scenario_cfg.get("window_option"),
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

    def _window_glass_replacement_executed(row, scenario_name, scenario_summary=None):
        upgrade_status = str(row.get("window_upgrade_status") or "").strip().lower()
        if upgrade_status in {"", "nan", "null", "none"}:
            upgrade_status = None
        if upgrade_status == "upgraded":
            return True

        material_cost = _as_float(row.get("window_enhancement_material_cost_usd"))
        if material_cost is None or material_cost <= 0:
            return False

        u_mod = _as_float(_arg_value(scenario_name, "window", "u_factor_modification_percentage")) or 0.0
        shgc_mod = _as_float(_arg_value(scenario_name, "window", "shgc_modification_percentage")) or 0.0
        vt_mod = _as_float(_arg_value(scenario_name, "window", "visible_transmittance_modification_percentage")) or 0.0
        if abs(u_mod) == 0 and abs(shgc_mod) == 0 and abs(vt_mod) == 0:
            return False

        note = None
        if scenario_summary:
            note = _clean_summary_note(scenario_summary.get("window"))
        if not note:
            note = _clean_summary_note(row.get("window_summary_notes"))
        if not note:
            note = _clean_summary_note(row.get("window_enhancement_summary_notes"))
        if note and "glass replacement selected but all window constructions are simpleglazing" in note.lower():
            return False

        return True

    def _get_parameter_changes_bullets(scenario_name):
        """Generate bullets for modified optical parameters."""
        bullets = []
        
        # Get parameter values from scenario
        infil_reduction = _as_float(_arg_value(scenario_name, "window", "window_infiltration_reduction_percent"))
        u_factor_mod = _as_float(_arg_value(scenario_name, "window", "u_factor_modification_percentage"))
        shgc_mod = _as_float(_arg_value(scenario_name, "window", "shgc_modification_percentage"))
        vt_mod = _as_float(_arg_value(scenario_name, "window", "visible_transmittance_modification_percentage"))
        
        # Compare with baseline (baseline has 0 or None for all these)
        baseline_infil_reduction = 0.0
        baseline_u_factor_mod = 0.0
        baseline_shgc_mod = 0.0
        baseline_vt_mod = 0.0
        
        # Check for changes and add bullets
        if infil_reduction is not None and abs(infil_reduction - baseline_infil_reduction) > 0.01:
            bullets.append(f"Window infiltration reduction: {infil_reduction:.1f}%")
        
        if u_factor_mod is not None and abs(u_factor_mod - baseline_u_factor_mod) > 0.01:
            direction = "improvement" if u_factor_mod < 0 else "degradation"
            bullets.append(f"U-factor modification: {u_factor_mod:+.1f}% ({direction})")
        
        if shgc_mod is not None and abs(shgc_mod - baseline_shgc_mod) > 0.01:
            direction = "reduction" if shgc_mod < 0 else "increase"
            bullets.append(f"SHGC modification: {shgc_mod:+.1f}% ({direction})")
        
        if vt_mod is not None and abs(vt_mod - baseline_vt_mod) > 0.01:
            direction = "reduction" if vt_mod < 0 else "increase"
            bullets.append(f"Visible transmittance modification: {vt_mod:+.1f}% ({direction})")
        
        return bullets

    def _window_action_bullets(row, scenario_name, scenario_summary):
        bullets = []
        panes = _arg_value(scenario_name, "window", "user_num_panes")
        weatherstrip_opt = _arg_value(scenario_name, "window", "weatherstrip_option")
        film_opt = _arg_value(scenario_name, "window", "film_option")
        frame_opt = _arg_value(scenario_name, "window", "window_option")
        caulking_opt = _arg_value(scenario_name, "window", "caulking_option")
        secondary_opt = _arg_value(scenario_name, "window", "secondary_glazing_option")
        whole_window_selected = (
            _has_meaningful_value(frame_opt)
            and str(frame_opt).strip().lower() != "none"
        )
        frame_area = _as_float(row.get("window_enhancement_renovated_frame_area_m2"))
        glazing_area = _as_float(row.get("window_enhancement_renovated_glazing_area_m2"))
        caulking_volume = _as_float(row.get("window_enhancement_renovated_caulking_volume_m3"))
        weatherstrip_length = _as_float(row.get("window_enhancement_renovated_weatherstrip_length_m"))

        # Legacy fallbacks from older/reporting-measure output keys.
        if glazing_area is None:
            glazing_area = _as_float(row.get("window_renovated_glazing_area_m2"))
        if caulking_volume is None:
            caulking_volume = _as_float(row.get("window_renovated_caulking_volume_m3"))
        if weatherstrip_length is None:
            weatherstrip_length = _as_float(row.get("window_renovated_weatherstrip_length_m"))
        if frame_area is None:
            total_window_area = _as_float(row.get("window_renovated_area_m2"))
            if total_window_area is None:
                total_window_area = _as_float(row.get("window_option_renovated_area_m2"))
            if total_window_area is not None and glazing_area is not None:
                frame_area = max(total_window_area - glazing_area, 0.0)
        operable_count = _as_float(row.get("window_operable_count"))

        if whole_window_selected:
            if frame_area is not None and frame_area > 0:
                bullets.append(_applied_action("Entire window replacement", _friendly_option(frame_opt)))
            else:
                bullets.append(_skipped_action("Entire window replacement", _friendly_option(frame_opt)))

        if _has_meaningful_value(panes) and not whole_window_selected:
            if _window_glass_replacement_executed(row, scenario_name, scenario_summary):
                bullets.append(_applied_action(f"{panes}-pane replacement"))
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
            if glazing_area is not None and glazing_area > 0:
                bullets.append(_applied_action("Glazing film application", _friendly_option(film_opt)))
            else:
                bullets.append(_skipped_action("Glazing film application"))

        if _has_meaningful_value(caulking_opt):
            if caulking_volume is not None and caulking_volume > 0:
                bullets.append(_applied_action("Caulking application", _friendly_option(caulking_opt)))
            else:
                bullets.append(_skipped_action("Caulking application"))

        if _has_meaningful_value(frame_opt) and not whole_window_selected:
            if frame_area is not None and frame_area > 0:
                bullets.append(_applied_action("Window frame replacement", _friendly_option(frame_opt)))
            else:
                bullets.append(_skipped_action("Window frame replacement"))

        if _has_meaningful_value(secondary_opt):
            if glazing_area is not None and glazing_area > 0:
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
            
            # Add location information for baseline
            weather_file, building_location = _extract_location_info(source_row)
            location_bullets = [
                f"Weather File: {weather_file}",
                f"Building Location: {building_location}"
            ]
            location_section = _build_measure_section("Location Information", location_bullets)
            
            baseline_details = source_row.get("renovation_details")
            if _has_meaningful_value(baseline_details):
                renovation_df.at[idx, "renovation_details"] = location_section + str(baseline_details)
            else:
                renovation_df.at[idx, "renovation_details"] = location_section + "Baseline (no envelope renovation)"
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

        # Add location information section at the beginning
        weather_file, building_location = _extract_location_info(source_row)
        location_bullets = [
            f"Weather File: {weather_file}",
            f"Building Location: {building_location}"
        ]
        details_parts.append(_build_measure_section("Location Information", location_bullets))

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
            
            # Add optical parameter changes section if any parameters have changed
            param_changes = _get_parameter_changes_bullets(scenario_name)
            if param_changes:
                details_parts.append(
                    _build_measure_section(
                        "Optical parameters modified",
                        param_changes,
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
        frame_area, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_frame_area_m2",
        ])
        glazing_area, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_glazing_area_m2",
            "window_renovated_glazing_area_m2",
        ])
        caulking_volume, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_caulking_volume_m3",
            "window_renovated_caulking_volume_m3",
        ])
        weatherstrip_length, _ = _pick_first_numeric(data_row, [
            "window_enhancement_renovated_weatherstrip_length_m",
            "window_renovated_weatherstrip_length_m",
        ])
        if frame_area is None:
            total_window_area, _ = _pick_first_numeric(data_row, [
                "window_renovated_area_m2",
                "window_option_renovated_area_m2",
            ])
            if total_window_area is not None and glazing_area is not None:
                frame_area = max(total_window_area - glazing_area, 0.0)
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
            return _window_glass_replacement_executed(data_row, scenario_name)
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
            window_option_value = _clean_text(_arg_lookup_material(scenario_name, "window", "window_option"))
            whole_window_requested = _has_meaningful_value(window_option_value)
            if whole_window_requested and str(window_option_value).strip().lower() == "none":
                whole_window_requested = False

            frame_area, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_frame_area_m2",
            ])
            glazing_area_for_frame, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_glazing_area_m2",
                "window_renovated_glazing_area_m2",
            ])
            total_window_area, _ = _pick_first_numeric(data_row, [
                "window_renovated_area_m2",
                "window_option_renovated_area_m2",
            ])
            if frame_area is None:
                if total_window_area is not None and glazing_area_for_frame is not None:
                    frame_area = max(total_window_area - glazing_area_for_frame, 0.0)
            caulking_volume, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_caulking_volume_m3",
                "window_renovated_caulking_volume_m3",
            ])
            weatherstrip_length, _ = _pick_first_numeric(data_row, [
                "window_enhancement_renovated_weatherstrip_length_m",
                "window_renovated_weatherstrip_length_m",
            ])

            if whole_window_requested and total_window_area is not None and total_window_area > 0:
                _add_material_row(
                    scenario_name,
                    "Entire window",
                    window_option_value,
                    area_m2=total_window_area,
                    lifetime_years=_safe_float(data_row.get("window_frame_lifetime_years")),
                )
            elif frame_area is not None and frame_area > 0:
                _add_material_row(
                    scenario_name,
                    "Window frame",
                    _arg_lookup_material(scenario_name, "window", "window_option"),
                    area_m2=frame_area,
                    lifetime_years=_safe_float(data_row.get("window_frame_lifetime_years")),
                )
            caulking_option_value = _clean_text(_arg_lookup_material(scenario_name, "window", "caulking_option"))
            caulking_requested = _has_meaningful_value(caulking_option_value) and str(caulking_option_value).strip().lower() != "none"
            if caulking_requested and caulking_volume is not None and caulking_volume > 0:
                _add_material_row(
                    scenario_name,
                    "Window caulking",
                    caulking_option_value,
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
        window_carbon, _ = _pick_first_numeric(scenario_row, [
            "window_enhancement_embodied_carbon_kgCO2eq",
            "window_embodied_carbon_kgCO2eq",
        ])
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
        city_name = row.get("city", "Unknown")
        baseline_energy_row = baseline_by_city.get(city_name, b)
        row_delta = baseline_energy_row["total_site_energy_gj"] - row["total_site_energy_gj"]
        row_delta_pct = (row_delta / baseline_energy_row["total_site_energy_gj"] * 100.0) if baseline_energy_row["total_site_energy_gj"] > 0 else 0.0
        positive_class = "positive" if row_delta >= 0 else ""
        energy_analysis_rows.append(

            f"<tr>"
            f"<td>{scenario_display_map.get(row['scenario'], row['scenario'])}</td>"
            f"<td>Total Site Energy (GJ)</td>"
            f"<td>{num_energy(baseline_energy_row['total_site_energy_gj'])}</td>"
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
        payback_df = comparison_df[["scenario", "city", "cost_delta", "emissions_delta", "embodied_carbon_kg", "annual_emissions_kg", "annual_cost_usd"]].copy()
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
                city_name = str(payback_row.get("city", "Unknown"))
                city_baseline = baseline_by_city.get(city_name, b)
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
                    "cost_saving": float(payback_row["annual_cost_usd"]) - float(city_baseline["annual_cost_usd"]),
                    "annual_operational_carbon": float(payback_row["annual_emissions_kg"]),
                    "total_embodied_carbon": float(payback_row["embodied_carbon_kg"]),
                    "operational_carbon_saving": float(payback_row["annual_emissions_kg"]) - float(city_baseline["annual_emissions_kg"]),
                    "annual_operational_cost": float(payback_row["annual_cost_usd"]),
                    "total_construction_cost": float(payback_row["construction_cost"]) if pd.notna(payback_row["construction_cost"]) else 0.0,
                    "operational_cost_saving": float(payback_row["annual_cost_usd"]) - float(city_baseline["annual_cost_usd"]),
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
        baseline_cost_value=baseline_cost_value,
        b=b,
        best_cost_w=best_cost_w,
        max_savings=max_savings,
        baseline_emis_w=baseline_emis_w,
        baseline_emis_value=baseline_emis_value,
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

df_report = pd.read_csv(csv_path, header=None, dtype=str)
# parametric_results.csv is written in transposed form (fields as rows, scenarios as columns).
# Restore the conventional orientation: scenarios as rows, fields as columns.
if not df_report.empty and str(df_report.iloc[0, 0]).strip().lower() == "scenario":
    df_report = df_report.T
    df_report.columns = df_report.iloc[0]
    df_report = df_report.iloc[1:].reset_index(drop=True)
    df_report.columns.name = None
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
    building_name = None
    floor_area_text = "N/A"

    # First try to extract building type from scenario column name
    # Pattern: baseline_SmallOffice_IL_Chicago or scenario_1_SmallOffice_IL_Chicago
    if "scenario" in df.columns:
        first_scenario = str(df["scenario"].iloc[0])
        parts = first_scenario.split("_")
        
        # Determine where the building_type is
        if len(parts) >= 2:
            building_type_idx = None
            if parts[0].lower() == "baseline":
                building_type_idx = 1
            elif parts[0].lower() == "scenario" and len(parts) >= 3 and parts[1].isdigit():
                building_type_idx = 2
            
            if building_type_idx is not None and building_type_idx < len(parts):
                potential_building_type = parts[building_type_idx]
                if potential_building_type and potential_building_type[0].isupper():
                    building_name = potential_building_type
    
    # Fall back to searching columns
    if building_name is None:
        for col in ["building_name", "building_type", "building"]:
            if col in df.columns:
                val = _first_non_empty(df[col])
                if val and val.lower() not in ["nan", "null", "none", ""]:
                    building_name = val
                    break
    
    if building_name is None:
        building_name = str(globals().get("building_type", "N/A"))

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
        "building_name": building_name or "N/A",
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
        f"\n                    <li>Building Name: {info['building_name']}</li>"
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
            frame = _extract_param(details_plain, "window_option")
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
    window_option = _arg_value(args_df, scenario_name, "window", "window_option")
    caulking_option = _arg_value(args_df, scenario_name, "window", "caulking_option")
    film_option = _arg_value(args_df, scenario_name, "window", "film_option")
    weatherstrip_option = _arg_value(args_df, scenario_name, "window", "weatherstrip_option")
    secondary_option = _arg_value(args_df, scenario_name, "window", "secondary_glazing_option")
    simple_glazing_blocked = scenario_name in simple_glazing_failed_scenarios
    glass_requested = (user_num_panes is not None and user_num_panes > 0) or _is_meaningful_option(glass_option)
    frame_requested = _is_meaningful_option(window_option)
    caulking_requested = _is_meaningful_option(caulking_option)
    film_requested = _is_meaningful_option(film_option)
    weatherstrip_requested = _is_meaningful_option(weatherstrip_option)
    secondary_requested = _is_meaningful_option(secondary_option)
    panes_detail = _fmt_panes(user_num_panes)
    glass_detail = _clean_option_value(glass_option)
    frame_detail = _clean_option_value(window_option)
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

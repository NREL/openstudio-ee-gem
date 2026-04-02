#!/usr/bin/env python
"""
Simplified parametric workflow - runs simulations only via OpenStudio CLI.
This version skips in-process Python measure applications to avoid Python 3.12 conflict.
"""

import json
import os
import subprocess
import time
from itertools import product
from pathlib import Path
import configparser

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
        if scenario_dict.get("wall_r_value"):
            parts.append(f"wall_r{scenario_dict['wall_r_value']}")
        if scenario_dict.get("roof_r_value"):
            parts.append(f"roof_r{scenario_dict['roof_r_value']}")
        if scenario_dict.get("window_u_factor"):
            parts.append(f"window_u{scenario_dict['window_u_factor']}")
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
        print(f"❌ {label}: OSW failed with status: {out_osw.get('completed_status')}")
        run_log_path = os.path.join(run_dir, "run", "run.log")
        if os.path.exists(run_log_path):
            with open(run_log_path, "r") as log_f:
                for line in log_f:
                    if "ERROR" in line:
                        print(f"   LOG: {line.rstrip()}")
        return False

    return True


def create_baseline_simulation(
    city,
    base_run_dir,
    measure_dir_path,
    base_weather_path,
    building_type="SmallOffice",
    template="90.1-2010",
    climate_zone="ASHRAE 169-2013-5A",
    openstudio_path="openstudio",
):
    """Create and run baseline simulation only (no Python measures)."""
    
    wf = get_city_weather_files(city, base_weather_path)
    if wf is None or wf["epw"] is None:
        print(f"❌ Weather files not found for {city}")
        return None

    epw_path = os.path.abspath(wf["epw"])
    scenario_dict = {
        "is_baseline": True,
        "city": city,
        "building_type": building_type,
        "wall_r_value": None,
        "roof_r_value": None,
        "window_u_factor": None,
        "door_option": None,
    }
    scenario_name = generate_scenario_name(scenario_dict)
    scenario_run_dir = os.path.abspath(os.path.join(base_run_dir, scenario_name))
    os.makedirs(scenario_run_dir, exist_ok=True)

    # Skip if already done
    sql_output_path = os.path.join(scenario_run_dir, "run", "eplusout.sql")
    if os.path.exists(sql_output_path):
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

    osw = {
        "weather_file": epw_path,
        "file_paths": file_paths,
        "measure_paths": measure_paths,
        "steps": [prototype_step],
        "name": scenario_name,
    }
    
    success = run_osw(osw, "run.osw", scenario_run_dir, openstudio_path, scenario_name)
    if success:
        print(f"✅ Completed: {scenario_name}")
    
    return scenario_name if success else None


# =========================
# GLOBAL SETTINGS
# =========================

RUN_NAME = "run_test_004_cli_only"

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

notebook_dir = Path.cwd()
base_weather_path = str(notebook_dir / "weather")
measure_dir_path = str(notebook_dir.parent / "measures")
base_run_dir = str(notebook_dir / "simulations" / RUN_NAME)

city_climate_zones = {
    "Amarillo": "ASHRAE 169-2013-3B",
}

CITIES = list(city_climate_zones.keys())
BUILDING_TYPES = ["SmallOffice"]
TEMPLATE = "90.1-2010"

# =========================
# MAIN - RUN BASELINE ONLY
# =========================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PARAMETRIC STUDY: BASELINE SIMULATION (CLI ONLY)")
    print(f"Using OpenStudio CLI: {OPENSTUDIO_PATH}")
    print(f"Run Name: {RUN_NAME}")
    print(f"Output Directory: {base_run_dir}")
    print("=" * 70)

    print("\n📋 Generating baseline scenarios...")
    scenarios = []
    
    for city, building_type in product(CITIES, BUILDING_TYPES):
        climate_zone = city_climate_zones.get(city, "ASHRAE 169-2013-5A")
        scenarios.append({
            "city": city,
            "building_type": building_type,
            "climate_zone": climate_zone,
        })

    total_sims = len(scenarios)
    print(f"\n📦 Total scenarios: {total_sims}")
    print(f"   - Cities: {len(CITIES)}")
    print(f"   - Building Types: {len(BUILDING_TYPES)}")
    print("=" * 70)

    sim_count = 0
    start_time = time.time()
    successful_scenarios = []
    failed_scenarios = []

    for scenario in scenarios:
        sim_count += 1
        city = scenario["city"]
        building_type = scenario["building_type"]
        climate_zone = scenario["climate_zone"]

        print(f"\n[{sim_count}/{total_sims}] Running baseline for {building_type} in {city}...")

        sim_start = time.time()

        result = create_baseline_simulation(
            city=city,
            base_run_dir=base_run_dir,
            measure_dir_path=measure_dir_path,
            base_weather_path=base_weather_path,
            building_type=building_type,
            template=TEMPLATE,
            climate_zone=climate_zone,
            openstudio_path=OPENSTUDIO_PATH,
        )

        if result:
            successful_scenarios.append(result)
        else:
            failed_scenarios.append(f"{building_type}_{city}")

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
    
    # Create simple CSV report
    csv_path = os.path.join(base_run_dir, "parametric_results.csv")
    with open(csv_path, 'w') as f:
        f.write("scenario_name,status\n")
        for scenario in successful_scenarios:
            f.write(f"{scenario},success\n")
        for scenario in failed_scenarios:
            f.write(f"{scenario},failed\n")
    
    print(f"\n🧾 Results CSV: {csv_path}")
    print("\n✅ Parametric study complete!")

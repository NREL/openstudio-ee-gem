# Standard library
import json
import os
import sqlite3
import subprocess
import warnings
import time
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning

# Tidy warnings
warnings.simplefilter(action="ignore", category=PerformanceWarning)


# =========================
# HELPER FUNCTIONS
# =========================

def sanitize_name(s):
    """
    Make a safe folder/name string from any value.
    """
    return str(s).replace(" ", "").replace(":", "").replace("/", "_").replace(".", "p")


# Label mappings so we can round-trip scenario parameters from the folder names
HP_LABEL_MAP = {
    "two_speed_lab_data": "HP2Speed",
    "cchpc_2027_spec": "CCHPC",
}
HP_LABEL_REVERSE_MAP = {v: k for k, v in HP_LABEL_MAP.items()}

BACKUP_LABEL_MAP = {
    "match_original_primary_heating_fuel": "backup_gas",
    "electric_resistance_backup": "backup_electric",
}
BACKUP_LABEL_REVERSE_MAP = {v: k for k, v in BACKUP_LABEL_MAP.items()}


def get_city_weather_files(city_name):
    """
    Get the EPW and DDY file paths for a given city name.
    """
    if city_name not in city_region_state:
        print(f"Error: '{city_name}' not found in city_region_state dictionary")
        return None

    folder_name = city_name
    city_folder_path = os.path.join(base_weather_path, folder_name)
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


def get_energy_from_sql(sql_file_path, default_year, variable):
    """
    Legacy helper: Extract hourly energy time series from an EnergyPlus SQL file.
    (Kept in case you still want the monthly aggregation somewhere else.)
    """
    conversion_factors = {
        "Electricity": 2.77778e-10,  # Joules -> MWh
        "NaturalGas": 9.48043e-9,    # Joules -> Therms
    }

    query = """
    SELECT r.VariableValue * ? AS VariableValue, t.Month, t.Day, t.Hour, t.Minute
    FROM ReportVariableDataDictionary AS d
    JOIN ReportVariableData AS r
      ON d.ReportVariableDataDictionaryIndex = r.ReportVariableDataDictionaryIndex
    JOIN Time AS t
      ON r.TimeIndex = t.TimeIndex
    WHERE d.VariableName = ?
      AND d.ReportingFrequency = 'Zone Timestep'
    """

    with sqlite3.connect(sql_file_path) as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params=(conversion_factors[variable], f"{variable}:Facility"),
        )

    df["Year"] = default_year
    df["DateTime"] = pd.to_datetime(df[["Year", "Month", "Day", "Hour", "Minute"]])
    df.set_index("DateTime", inplace=True)

    # Resample to hourly values
    return df["VariableValue"].resample("H").sum()


def extract_simulation_data(sql_path, year):
    """
    Legacy helper: Aggregate hourly energy to monthly electricity / gas + peak demand.
    (Not used in the new hourly Excel workflow, but left here if useful.)
    """
    elec = get_energy_from_sql(sql_path, year, "Electricity")
    gas = get_energy_from_sql(sql_path, year, "NaturalGas")

    df_sim = pd.DataFrame(
        {
            "Electricity_MWh": elec,
            "Gas_Therms": gas,
        }
    )

    df_monthly = df_sim.resample("M").agg(
        {
            "Electricity_MWh": ["sum", "max"],
            "Gas_Therms": "sum",
        }
    )

    df_monthly.columns = ["Electricity_MWh", "Max_Electricity_MW", "Gas_Therms"]
    return df_monthly.loc[str(year)]


# =========================
# LABEL / NAME HELPERS
# =========================

def format_hp_label(hprtu: str) -> str:
    """
    Human-friendly label for HP scenario.
    """
    if hprtu is None:
        return "Baseline"
    return HP_LABEL_MAP.get(hprtu, sanitize_name(hprtu))


def format_backup_label(backup: str) -> str:
    """
    Human-friendly label for backup scheme.
    """
    if backup is None:
        return "Baseline"
    if backup in BACKUP_LABEL_MAP:
        return BACKUP_LABEL_MAP[backup]
    else:
        return f"backup_{sanitize_name(backup)}"


def format_lock_label(lock: float) -> str:
    """
    lock_-10p0F -> lock_-10F, lock_30p0F -> lock_30F, etc.
    """
    if lock is None:
        return "Baseline"
    try:
        lock_val = float(lock)
        if lock_val.is_integer():
            temp_str = str(int(lock_val))
        else:
            temp_str = str(lock_val).replace(".", "p")
    except Exception:
        temp_str = sanitize_name(lock)
    return f"lock_{temp_str}F"


def format_clg_label(clg: float) -> str:
    """
    clg_1p0 -> clgupsize_1x, clg_2p0 -> clgupsize_2x, etc.
    """
    try:
        clg_val = float(clg)
        if clg_val.is_integer():
            factor_str = str(int(clg_val))
        else:
            factor_str = str(clg_val).replace(".", "p")
    except Exception:
        factor_str = sanitize_name(clg)
    return f"clgupsize_{factor_str}x"


def format_perf_oversizing_label(perf: float) -> str:
    """
    perf_0p0 -> perfOvrsz_0, perf_0p25 -> perfOvrsz_25pct, etc.
    """
    if perf is None:
        return "Baseline"
    try:
        perf_val = float(perf)
        if perf_val == 0.0:
            return "perfOvrsz_0"
        else:
            pct_str = str(int(perf_val * 100))
            return f"perfOvrsz_{pct_str}pct"
    except Exception:
        return f"perfOvrsz_{sanitize_name(perf)}"


def format_htg_sizing_label(htg_temp: str) -> str:
    """
    '0F' -> htgSzg_0F, '-10F' -> htgSzg_m10F, '17F' -> htgSzg_17F
    """
    if htg_temp is None:
        return "Baseline"
    temp_clean = htg_temp.replace("-", "m").replace("F", "")
    return f"htgSzg_{temp_clean}F"


# =========================
# NEW: HOURLY EXTRACTION
# =========================

def get_all_hourly_data(sql_file_path, default_year=2024):
    """
    Extracts all 'Hourly' variables, pivots them, and calculates:
      - Electricity:Facility (MWh) as sum of all Electricity Energy (J) components
      - NaturalGas:Facility (Therms) as sum of all gas energy (J) components
    """
    # Conversion factors
    J_TO_MWH = 2.77778e-10
    NATURAL_GAS_J_TO_THERMS = 9.48043e-9

    query = """
    SELECT 
        rd.Name,       
        rd.KeyValue,   
        rd.Units,      
        r.VariableValue, 
        t.Month, 
        t.Day, 
        t.Hour, 
        t.Minute
    FROM ReportVariableData AS r
    JOIN ReportDataDictionary AS rd               
        ON r.ReportVariableDataDictionaryIndex = rd.ReportDataDictionaryIndex 
    JOIN Time AS t 
        ON r.TimeIndex = t.TimeIndex
    WHERE rd.ReportingFrequency = 'Hourly' 
    ORDER BY r.TimeIndex
    """

    print(f"  🗂  Reading hourly data from SQL: {sql_file_path}")
    with sqlite3.connect(sql_file_path) as conn:
        df = pd.read_sql_query(query, conn)

    if df.empty:
        print("  ⚠️  No hourly variables found.")
        return pd.DataFrame()

    # Build DateTime
    df["Year"] = default_year
    base_dates = pd.to_datetime(df[["Year", "Month", "Day"]])
    time_deltas = (
        pd.to_timedelta(df["Hour"], unit="h")
        + pd.to_timedelta(df["Minute"], unit="m")
    )
    df["DateTime"] = base_dates + time_deltas

    # Column names: Name [+ KeyValue] (+ Units)
    df["KeyValue"] = df["KeyValue"].fillna("")
    df["ColumnName"] = df.apply(
        lambda x: (
            f"{x['Name']} [{x['KeyValue']}] ({x['Units']})"
            if x["KeyValue"]
            else f"{x['Name']} ({x['Units']})"
        ),
        axis=1,
    )

    # Pivot
    pivot_df = df.pivot_table(
        index="DateTime",
        columns="ColumnName",
        values="VariableValue",
        aggfunc="first",
    )

    # Total electricity (MWh) from all electricity energy (J) components
    elec_cols_J = [
        col for col in pivot_df.columns if "Electricity Energy" in col and "(J)" in col
    ]
    if elec_cols_J:
        pivot_df["Total Electricity (J)"] = pivot_df[elec_cols_J].sum(axis=1)
        new_col_name = "Electricity:Facility (MWh)"
        pivot_df[new_col_name] = pivot_df["Total Electricity (J)"] * J_TO_MWH
        pivot_df.drop(columns=["Total Electricity (J)"], inplace=True)
        print(f"  ⚡ Created '{new_col_name}' from {len(elec_cols_J)} components.")
    else:
        print("  ⚠️  No electricity energy (J) columns found; skipping total electricity.")

    # Total natural gas (Therms) from gas energy (J) columns
    gas_cols_J = [
        col
        for col in pivot_df.columns
        if ("Gas Energy" in col or "NaturalGas" in col) and "(J)" in col
    ]
    if gas_cols_J:
        pivot_df["Total NaturalGas (J)"] = pivot_df[gas_cols_J].sum(axis=1)
        new_gas_col_name = "NaturalGas:Facility (Therms)"
        pivot_df[new_gas_col_name] = (
            pivot_df["Total NaturalGas (J)"] * NATURAL_GAS_J_TO_THERMS
        )
        pivot_df.drop(columns=["Total NaturalGas (J)"], inplace=True)
        print(f"  🔥 Created '{new_gas_col_name}' from {len(gas_cols_J)} components.")
    else:
        print("  ℹ️  No gas energy (J) columns found; skipping total natural gas.")

    print(f"  ✅ Final extracted DataFrame shape: {pivot_df.shape}")
    return pivot_df


def write_excel_part_worker(part_index, runs_subset, base_run_dir, year, delete_artifacts, excel_base_name):
    """
    Worker function to write a single Excel part file from a subset of runs.
    This is at module scope so it can be pickled and executed in child processes.
    """
    # Ensure per-run hourly output directory exists and write parts there
    hourly_dir_local = os.path.join(base_run_dir, "hourly_outputs")
    os.makedirs(hourly_dir_local, exist_ok=True)
    excel_path = os.path.join(hourly_dir_local, f"{excel_base_name}_part{part_index}.xlsx")
    print(f"\n📁 [Part {part_index}] Opening Excel writer: {excel_path}")
    writer_local = pd.ExcelWriter(excel_path, engine="xlsxwriter")
    used_sheet_names_local = set()
    sheet_count_local = 0

    for city, bldg, scenario_name, run_dir, sql_path in runs_subset:
        print(
            f"\n🔎 [Part {part_index}] Processing SQL -> Excel sheet:\n"
            f"   City={city}, Bldg={bldg}, Scenario={scenario_name}"
        )

        df_hourly = get_all_hourly_data(sql_path, default_year=year)

        if df_hourly.empty:
            print(f"  ⚠️  [Part {part_index}] Skipping empty dataframe.")
        else:
            base_name = sanitize_name(f"{city[:3]}_{bldg[:3]}_{scenario_name}")
            sheet_name = base_name[:31]

            # Ensure uniqueness within this workbook
            suffix = 1
            original_name = sheet_name
            while sheet_name in used_sheet_names_local:
                sheet_name = (original_name[:29] + str(suffix))[:31]
                suffix += 1

            used_sheet_names_local.add(sheet_name)

            df_hourly.to_excel(writer_local, sheet_name=sheet_name)
            sheet_count_local += 1
            print(f"  ✅ [Part {part_index}] Written to sheet '{sheet_name}'")

        # Optionally delete artifacts
        if delete_artifacts:
            try:
                os.remove(sql_path)
                print(f"  🧹 [Part {part_index}] Deleted {sql_path}")
            except FileNotFoundError:
                pass
            zip_path = os.path.join(run_dir, "data_point.zip")
            if os.path.isfile(zip_path):
                try:
                    os.remove(zip_path)
                    print(f"  🧹 [Part {part_index}] Deleted {zip_path}")
                except FileNotFoundError:
                    pass

    writer_local.close()
    print(f"\n📦 [Part {part_index}] Finished writing {excel_path} ({sheet_count_local} sheets)")
    return excel_path


# =========================
# CORE: SINGLE SCENARIO CREATION/RUN
# =========================

def create_city_scenarios(
    city,
    base_run_dir,
    measure_dir_path,
    seed_model_path,
    overwrite_existing=False,
    building_type="RetailStandalone",  # or "SmallOffice", etc.
    # --- single-scenario controls ---
    scenario_name="HP_Scenario",
    skip_hp=False,  # True => Baseline (HP measure skipped)
    hprtu_scenario=None,  # e.g. "two_speed_lab_data", "cchpc_2027_spec"
    backup_ht_fuel_scheme=None,  # "match_original_primary_heating_fuel" or "electric_resistance_backup"
    hp_min_comp_lockout_temp_f=None,  # float, e.g. 0.0, 30.0, -10.0
    clg_oversizing_estimate=None,  # float, e.g. 1.0
    performance_oversizing_factor=None,  # float, e.g. 0.0, 0.25, 0.5
    htg_sizing_option=None,  # str, e.g. '0F', '-10F', '17F', '47F'
    htg_oversizing_estimate=None,  # float, e.g. 1.0
):
    """
    Build and run ONE OSW workflow for a given city + building_type + HP configuration.

    - If skip_hp=True, the HP RTU measure is skipped -> Baseline gas RTU.
    - If skip_hp=False, the HP RTU measure runs with its OWN default values,
      except for any of these that you explicitly pass:
        * hprtu_scenario
        * backup_ht_fuel_scheme
        * hp_min_comp_lockout_temp_f
        * clg_oversizing_estimate
        * performance_oversizing_factor
        * htg_sizing_option
        * htg_oversizing_estimate
    """

    # --- Weather for this city ---
    wf = get_city_weather_files(city)
    if wf is None or wf["epw"] is None:
        print(f"❌ Weather files not found for {city}")
        return

    epw_path = wf["epw"]

    # --- Lookups for this city ---
    info = city_region_state[city]
    grid_state = info["state"]          # e.g. "CO"
    grid_region = info["cambium_region"]  # e.g. "RMPAc"
    cz_short = info["climate_zone"]    # e.g. "5B"
    # Map zone 7 to 7A and zone 8 to 8A for measure compatibility
    if cz_short == "7":
        cz_short = "7A"
    elif cz_short == "8":
        cz_short = "8A"
    cz_long = f"ASHRAE 169-2013-{cz_short}"  # e.g. "ASHRAE 169-2013-5B"

    # --- Scenario folder ---
    # Structure: /simulations/<city>/<building_type>/<scenario_name>/
    city_run_dir = os.path.join(base_run_dir, city, building_type)
    os.makedirs(city_run_dir, exist_ok=True)

    run_dir = os.path.join(city_run_dir, scenario_name)
    sql_output_path = os.path.join(run_dir, "run", "eplusout.sql")

    if os.path.exists(sql_output_path) and not overwrite_existing:
        print(
            f"⏭️  Skipping {city} – {building_type} – {scenario_name} "
            f"- simulation already exists at {sql_output_path}"
        )
        return
    elif os.path.exists(sql_output_path) and overwrite_existing:
        print(f"♻️  Overwriting existing simulation for {city} – {building_type} – {scenario_name}")

    os.makedirs(run_dir, exist_ok=True)
    osw_path = os.path.join(run_dir, "in.osw")

    # -------------------------
    # Build OSW from scratch
    # -------------------------
    steps = []

    # 1) Create Bar From Building Type Ratios – climate_zone from city map
    steps.append(
        {
            "measure_dir_name": "create_bar_from_building_type_ratios",
            "name": "Create Bar From Building Type Ratios",
            "arguments": {
                "bar_division_method": "Single Space Type - Core and Perimeter",
                "bldg_type_a": building_type,
                "climate_zone": cz_long,
                "double_loaded_corridor": "None",
                "story_multiplier": "None",
                "template": "90.1-2010",
                "total_bldg_floor_area": 5000,
            },
        }
    )

    # 2) Create Typical Building from Model
    steps.append(
        {
            "measure_dir_name": "create_typical_building_from_model",
            "name": "Create Typical Building from Model",
            "arguments": {
                "template": "90.1-2010",
                "system_type": "PSZ-AC with gas coil",
                "hvac_delivery_type": "Forced Air",
                "htg_src": "NaturalGas",
                "clg_src": "Electricity",
                "swh_src": "Inferred",
                "kitchen_makeup": "Adjacent",
                "exterior_lighting_zone": "3 - All Other Areas",
                "add_constructions": True,
                "wall_construction_type": "Inferred",
                "add_space_type_loads": True,
                "add_elevators": False,
                "add_internal_mass": True,
                "add_exterior_lights": False,
                "onsite_parking_fraction": 1.0,
                "add_exhaust": False,
                "add_swh": True,
                "add_thermostat": True,
                "add_hvac": True,
                "add_refrigeration": False,
                "modify_wkdy_op_hrs": False,
                "wkdy_op_hrs_start_time": 8.0,
                "wkdy_op_hrs_duration": 8.0,
                "modify_wknd_op_hrs": False,
                "wknd_op_hrs_start_time": 8.0,
                "wknd_op_hrs_duration": 8.0,
                "unmet_hours_tolerance": 1.0,
                "remove_objects": True,
                "use_upstream_args": True,
                "enable_dst": True,
            },
        }
    )

    # 3) Clean Design Days From DDY
    steps.append(
        {
            "measure_dir_name": "clean_design_days_from_ddy",
            "name": "Clean Design Days From DDY",
            "arguments": {},
        }
    )

    # 4) Upgrade HVAC Add Heat Pump RTU – only override a few args
    upgrade_args = {"__SKIP__": skip_hp}

    if not skip_hp:
        # Only set arguments that you explicitly passed (others use measure defaults)
        if hprtu_scenario is not None:
            upgrade_args["hprtu_scenario"] = hprtu_scenario
        if backup_ht_fuel_scheme is not None:
            upgrade_args["backup_ht_fuel_scheme"] = backup_ht_fuel_scheme
        if hp_min_comp_lockout_temp_f is not None:
            upgrade_args["hp_min_comp_lockout_temp_f"] = hp_min_comp_lockout_temp_f
        if clg_oversizing_estimate is not None:
            upgrade_args["clg_oversizing_estimate"] = clg_oversizing_estimate
        if performance_oversizing_factor is not None:
            upgrade_args["performance_oversizing_factor"] = performance_oversizing_factor
        if htg_sizing_option is not None:
            upgrade_args["htg_sizing_option"] = htg_sizing_option
        if htg_oversizing_estimate is not None:
            upgrade_args["htg_oversizing_estimate"] = htg_oversizing_estimate

    steps.append(
        {
            "measure_dir_name": "upgrade_hvac_add_heat_pump_rtu",
            "name": "add_heat_pump_rtu",
            "arguments": upgrade_args,
        }
    )

    # 5) Add HP diagnostics Output:Variables (hourly)
    steps.append(
        {
            "measure_dir_name": "AddHPDiagnosticsOutputs",
            "name": "Add HP Diagnostics Output Variables",
            "arguments": {},
        }
    )

    # 6) Set Supplemental Heater Max Temperature (EnergyPlus pre-simulation fix)
    # CRITICAL FIX: This ensures supplemental heater can heat to full supply temperature
    # Must run after all ModelMeasures and before simulation/ReportingMeasures
    steps.append(
        {
            "measure_dir_name": "set_supplemental_heater_max_temp",
            "name": "Set Maximum Supply Air Temperature from Supplemental Heater",
            "arguments": {},
        }
    )

    # 7) OpenStudio Results
    steps.append(
        {
            "measure_dir_name": "OpenStudioResults",
            "name": "OpenStudio Results",
            "arguments": {},
        }
    )

    # 8) ComStock Sensitivity Reports
    steps.append(
        {
            "measure_dir_name": "comstock_sensitivity_reports",
            "name": "ComStock_Sensitivity_Reports",
            "arguments": {},
        }
    )

    # 9) Emissions Reporting
    steps.append(
        {
            "measure_dir_name": "emissions_reporting",
            "name": "Emissions Reporting",
            "arguments": {
                "grid_region": grid_region,
                "grid_state": grid_state,
                "emissions_scenario": "LRMER_MidCase_30",
            },
        }
    )

    osw = {
        "seed_file": seed_model_path,
        "weather_file": epw_path,
        "file_paths": [base_weather_path],
        "measure_paths": [measure_dir_path],
        "steps": steps,
        "name": f"{city} - {building_type} - {scenario_name}",
    }

    with open(osw_path, "w") as f:
        json.dump(osw, f, indent=2)

    # -------------------------
    # Run it with the CLI
    # -------------------------
    try:
        subprocess.run(
            ["openstudio", "run", "-w", osw_path],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        # Still show failures
        print(f"❌ {city} – {building_type} – {scenario_name} simulation failed.")
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)


def get_param_grid(test_mode: bool):
    """
    For TEST_MODE, thin the grid; otherwise use full combinations.
    """
    if DIAGNOSTIC_MODE:
        cities = DIAG_CITIES
        bldgs = DIAG_BUILDINGS
        hps = DIAG_HPS
        backs = DIAG_BACKUPS
        locks = DIAG_LOCKS
        perf_ovrsz = [0.0, 0.25]
        htg_szg = ['0F', '-10F']
        print("🧪 DIAGNOSTIC_MODE=True: running focused scenarios for sizing diagnostics")
    elif test_mode:
        # Use cities present in city_region_state for quick validation
        cities = ["Chicago", "Denver"]  # Cold + dry-cold
        bldgs = BUILDING_TYPES[:1]  # Just SmallOffice
        hps = HPRTU_SCENARIOS[:1]
        backs = ["electric_resistance_backup"]  # Just electric
        locks = [0.0, 17.0]  # Two lockout temps
        perf_ovrsz = [0.0, 0.5, 1.0]  # Test 0%, 50%, 100% oversizing
        htg_szg = ['17F', '0F']  # Two sizing temps
        print("🔬 TEST_MODE=True: running a reduced parameter set")
    else:
        cities = list(city_region_state.keys())
        bldgs = BUILDING_TYPES
        hps = HPRTU_SCENARIOS
        backs = BACKUP_SCHEMES
        locks = LOCKOUT_TEMPS_F
        perf_ovrsz = PERFORMANCE_OVERSIZING_FACTORS
        htg_szg = HTG_SIZING_OPTIONS
        print("🚀 TEST_MODE=False: running full parameter grid")

    return cities, bldgs, hps, backs, locks, perf_ovrsz, htg_szg


def build_jobs():
    cities, bldgs, hps, backs, locks, perf_ovrsz, htg_szg = get_param_grid(TEST_MODE)

    jobs = []
    for city in cities:
        for bldg in bldgs:
            # Baseline job per city/building_type: skip HP measure
            jobs.append((city, bldg, None, None, None, None, None, "Baseline"))

            # HP jobs per parameter grid
            for hprtu in hps:
                for backup in backs:
                    for lock in locks:
                        for perf in perf_ovrsz:
                            for htg in htg_szg:
                                hp_label = format_hp_label(hprtu)
                                backup_label = format_backup_label(backup)
                                lock_label = format_lock_label(lock)
                                perf_label = format_perf_oversizing_label(perf)
                                htg_label = format_htg_sizing_label(htg)

                                scenario_name = "__".join(
                                    [hp_label, backup_label, lock_label, perf_label, htg_label]
                                )

                                jobs.append(
                                    (city, bldg, hprtu, backup, lock, perf, htg, scenario_name)
                                )
    print(f"📦 Total simulations to run: {len(jobs)}")
    return jobs


def run_single_job(job):
    city, bldg, hprtu, backup, lock, perf, htg, scenario_name = job
    start = time.time()
    # Baseline scenario: skip HP measure
    if scenario_name == "Baseline":
        create_city_scenarios(
            city=city,
            base_run_dir=base_run_dir,
            measure_dir_path=measure_dir_path,
            seed_model_path=seed_model_path,
            overwrite_existing=OVERWRITE_EXISTING,
            building_type=bldg,
            scenario_name=scenario_name,
            skip_hp=True,
        )
    else:
        create_city_scenarios(
            city=city,
            base_run_dir=base_run_dir,
            measure_dir_path=measure_dir_path,
            seed_model_path=seed_model_path,
            overwrite_existing=OVERWRITE_EXISTING,
            building_type=bldg,
            scenario_name=scenario_name,
            skip_hp=False,
            hprtu_scenario=hprtu,
            backup_ht_fuel_scheme=backup,
            hp_min_comp_lockout_temp_f=lock,
            performance_oversizing_factor=perf,
            htg_sizing_option=htg,
            clg_oversizing_estimate=1.0,  # Keep at 1.0 - not varied
        )
    elapsed = time.time() - start
    return city, bldg, hprtu, backup, lock, perf, htg, scenario_name, elapsed


# =========================
# POSTPROCESS: EXPORT ALL HOURLY TO EXCEL
# =========================

def iter_sql_runs(base_run_dir):
    """
    Generator over all (city, building_type, scenario_name, run_dir, sql_path)
    that have an eplusout.sql present.
    """
    for city in city_region_state.keys():
        for bldg in BUILDING_TYPES:
            city_run_dir = os.path.join(base_run_dir, city, bldg)
            if not os.path.isdir(city_run_dir):
                continue
            for scenario_name in sorted(os.listdir(city_run_dir)):
                scenario_dir = os.path.join(city_run_dir, scenario_name)
                run_dir = os.path.join(scenario_dir, "run")
                
                # First try the standard location
                sql_path = os.path.join(run_dir, "eplusout.sql")
                if os.path.isfile(sql_path):
                    yield city, bldg, scenario_name, run_dir, sql_path
                else:
                    # For failed workflows, search recursively for eplusout.sql
                    for root, dirs, files in os.walk(run_dir):
                        if "eplusout.sql" in files:
                            sql_path = os.path.join(root, "eplusout.sql")
                            yield city, bldg, scenario_name, root, sql_path
                            break  # Only take the first one found


def export_all_hourly_to_excel(
    base_run_dir,
    year,
    delete_artifacts=False,
    max_sheets_per_file=50,
    excel_base_name="HP_hourly_outputs",
):
    """
    Walks all run directories, extracts hourly data from each eplusout.sql,
    writes each to a separate Excel sheet, and (optionally) deletes SQL + zip.

    If there are more than `max_sheets_per_file` sheets, it splits into
    multiple Excel files: <excel_base_name>_part1.xlsx, part2, etc.
    """
    # Ensure output directory for hourly Excel parts
    hourly_dir = os.path.join(base_run_dir, "hourly_outputs")
    os.makedirs(hourly_dir, exist_ok=True)

    # Gather all available SQL runs first
    runs = list(iter_sql_runs(base_run_dir))
    if not runs:
        print("\nℹ️ No SQL runs found for Excel export.")
        return

    # Note: the per-part writer function is defined at module scope
    # as `write_excel_part_worker` so it can be pickled by ProcessPoolExecutor.

    # Split runs list into chunks where each chunk has at most max_sheets_per_file items
    chunks = [
        runs[i : i + max_sheets_per_file]
        for i in range(0, len(runs), max_sheets_per_file)
    ]

    # If only one chunk, keep the original single-threaded behavior for simplicity
    if len(chunks) == 1:
        # Single-chunk: call worker directly to avoid spawn overhead
        from functools import partial

        write_excel_part_worker(1, chunks[0], base_run_dir, year, delete_artifacts, excel_base_name)
        return

    # Otherwise, parallelize across available workers (but limit to number of chunks)
    num_workers = min(MAX_WORKERS, len(chunks))
    print(f"\n⚙️ Parallelizing Excel export across {num_workers} workers ({len(chunks)} parts)")

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {}
        for idx, chunk in enumerate(chunks, start=1):
            futures[executor.submit(write_excel_part_worker, idx, chunk, base_run_dir, year, delete_artifacts, excel_base_name)] = idx

        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                result_path = fut.result()
                print(f"🎉 Part {idx} completed: {result_path}")
            except Exception as e:
                print(f"⚠️ Part {idx} failed with error: {e}")

    print("\n📦 Finished writing all Excel files.")


# =========================
# POSTPROCESS: COLLECT RESULTS.JSON TO CSV
# =========================

def collect_results_to_csv(
    base_run_dir,
    csv_base_name="HP_results",
):
    """
    Walk all run directories, read results.json (if present), and collect
    numeric outputs from:
      - 'OpenStudio Results'
      - 'ComStock_Sensitivity_Reports'

    For each successful run (with eplusout.sql present), one row is added with:
      - city, building_type, scenario_name
      - decoded HP parameters from scenario_name
      - climate_zone (from city_region_state)
      - numeric fields from the two measures (booleans dropped)
    """
    rows = []

    for city, bldg, scenario_name, run_dir, sql_path in iter_sql_runs(base_run_dir):
        # Try results.json in the run directory first, then in the scenario dir
        results_path = os.path.join(run_dir, "results.json")
        if not os.path.isfile(results_path):
            # Try the scenario directory
            scenario_dir = os.path.dirname(run_dir)
            alt_results_path = os.path.join(scenario_dir, "results.json")
            if os.path.isfile(alt_results_path):
                results_path = alt_results_path
            else:
                # For failed workflows, search in the same directory as eplusout.sql
                sql_dir = os.path.dirname(sql_path)
                sql_dir_results = os.path.join(sql_dir, "results.json")
                if os.path.isfile(sql_dir_results):
                    results_path = sql_dir_results
                else:
                    # As a last resort, search recursively under the run directory
                    found = None
                    for root, dirs, files in os.walk(run_dir):
                        if "results.json" in files:
                            found = os.path.join(root, "results.json")
                            break
                    if found:
                        results_path = found
                    else:
                        print(
                            f"  ⚠️  results.json not found for "
                            f"{city} / {bldg} / {scenario_name}, skipping."
                        )
                        continue

        try:
            with open(results_path, "r") as f:
                results_data = json.load(f)
        except Exception as e:
            print(
                f"  ⚠️  Failed to read results.json for "
                f"{city} / {bldg} / {scenario_name}: {e}"
            )
            continue

        # Base metadata
        row = {
            "city": city,
            "building_type": bldg,
            "scenario_name": scenario_name,
        }

        # === NEW: add climate zone (and optionally state / Cambium) ===
        city_info = city_region_state.get(city, {})
        row["climate_zone"] = city_info.get("climate_zone")
        row["state"] = city_info.get("state")
        row["cambium_region"] = city_info.get("cambium_region")

        # Decode HP parameters from scenario_name (hp_label, backup_label, lock temp, perf oversize, htg sizing)
        is_baseline = scenario_name == "Baseline"
        if is_baseline:
            hp_label = "Baseline"
            backup_label = None
            lock_label = None
            perf_label = None
            htg_label = None
        else:
            parts = scenario_name.split("__")
            hp_label = parts[0] if len(parts) > 0 else None
            backup_label = parts[1] if len(parts) > 1 else None
            lock_label = parts[2] if len(parts) > 2 else None
            perf_label = parts[3] if len(parts) > 3 else None
            htg_label = parts[4] if len(parts) > 4 else None

        row["hp_label"] = hp_label
        row["backup_label"] = backup_label
        row["is_baseline"] = bool(is_baseline)

        # Best-effort reconstruction of original HP scenario string
        if is_baseline:
            row["hprtu_scenario"] = None
        elif hp_label is not None:
            row["hprtu_scenario"] = HP_LABEL_REVERSE_MAP.get(hp_label, hp_label)
        else:
            row["hprtu_scenario"] = None

        # Backup scheme in original measure-argument form where we know it
        if is_baseline:
            row["backup_scheme"] = None
        elif backup_label is not None:
            row["backup_scheme"] = BACKUP_LABEL_REVERSE_MAP.get(
                backup_label, backup_label
            )
        else:
            row["backup_scheme"] = None

        # Parse lockout temperature from label like "lock_-10F"
        lock_temp_f = None
        if isinstance(lock_label, str) and lock_label.startswith("lock_") and lock_label.endswith("F"):
            temp_str = lock_label[len("lock_") : -1]  # strip "lock_" and trailing "F"
            temp_str = temp_str.replace("p", ".")
            try:
                lock_temp_f = float(temp_str)
            except ValueError:
                lock_temp_f = None
        row["lockout_temp_F"] = None if is_baseline else lock_temp_f

        # Parse performance oversizing from label like "perfOvrsz_25pct" or "perfOvrsz_0"
        perf_oversize = None
        if isinstance(perf_label, str) and perf_label.startswith("perfOvrsz_"):
            suffix = perf_label[len("perfOvrsz_") :]
            try:
                if suffix.endswith("pct"):
                    pct_val = int(suffix[:-3])
                    perf_oversize = float(pct_val) / 100.0
                else:
                    perf_oversize = float(suffix.replace("p", "."))
            except ValueError:
                perf_oversize = None
        row["performance_oversizing_factor"] = None if is_baseline else perf_oversize

        # Parse heating sizing option from label like "htgSzg_m10F" or "htgSzg_17F"
        htg_sizing_option = None
        htg_sizing_temp_F = None
        if isinstance(htg_label, str) and htg_label.startswith("htgSzg_"):
            val = htg_label[len("htgSzg_") :]
            # Normalize 'm10F' -> '-10F'
            val_norm = val.replace("m", "-")
            htg_sizing_option = f"{val_norm}"
            # Extract numeric temperature if possible (strip trailing 'F')
            try:
                temp_str = val_norm[:-1] if val_norm.endswith("F") else val_norm
                htg_sizing_temp_F = float(temp_str)
            except ValueError:
                htg_sizing_temp_F = None
        row["htg_sizing_option"] = None if is_baseline else htg_sizing_option
        row["htg_sizing_temp_F"] = None if is_baseline else htg_sizing_temp_F

        # Legacy cooling oversize (not used) left as None for compatibility
        row["clg_oversizing_factor"] = None

        # Pull numeric values from the two measures (drop booleans)
        for measure_key in ("OpenStudio Results", "ComStock_Sensitivity_Reports"):
            if measure_key not in results_data:
                continue
            measure_dict = results_data.get(measure_key, {})
            if not isinstance(measure_dict, dict):
                continue

            for key, value in measure_dict.items():
                # Keep only numeric (int/float) and explicitly drop booleans
                if isinstance(value, bool) or value is None:
                    continue
                if isinstance(value, (int, float)):
                    row[key] = value

        rows.append(row)

    if not rows:
        print("\nℹ️ No results.json files found; writing empty results CSV with headers.")
        # Create an empty DataFrame with the common metadata columns so downstream tools
        # find the expected file even when no runs produced results.json.
        empty_cols = [
            "city",
            "building_type",
            "scenario_name",
            "climate_zone",
            "state",
            "cambium_region",
            "hp_label",
            "backup_label",
            "is_baseline",
            "hprtu_scenario",
            "backup_scheme",
            "lockout_temp_F",
            "performance_oversizing_factor",
            "htg_sizing_option",
            "htg_sizing_temp_F",
            "clg_oversizing_factor",
        ]
        df_empty = pd.DataFrame(columns=empty_cols)
        csv_path = os.path.join(base_run_dir, f"{csv_base_name}.csv")
        df_empty.to_csv(csv_path, index=False)
        print(f"\n🧾 Empty Results CSV written to: {csv_path}")
        return

    df_results = pd.DataFrame(rows)

    # Optional post-processing diagnostics: compute heat/cool ratio if capacity columns exist
    heat_cols = [
        c for c in df_results.columns if any(k in c.lower() for k in ["heat", "heating"]) and "capacity" in c.lower()
    ]
    cool_cols = [
        c for c in df_results.columns if any(k in c.lower() for k in ["cool", "cooling"]) and "capacity" in c.lower()
    ]
    # Heuristic: pick first numeric columns as candidates
    def pick_numeric(cols):
        for c in cols:
            if pd.api.types.is_numeric_dtype(df_results[c]):
                return c
        return None
    heat_col = pick_numeric(heat_cols)
    cool_col = pick_numeric(cool_cols)
    if heat_col and cool_col:
        df_results["heat_cool_ratio"] = df_results[heat_col] / df_results[cool_col]
        df_results["heat_cool_flag"] = ((df_results["heat_cool_ratio"] < 0.8) | (df_results["heat_cool_ratio"] > 1.25)).astype(int)

    csv_path = os.path.join(base_run_dir, f"{csv_base_name}.csv")
    df_results.to_csv(csv_path, index=False)
    print(f"\n🧾 Results CSV written to: {csv_path}")

# =========================
# GLOBAL SETTINGS
# =========================

# Default year for time series aggregation / plots
YEAR = 2023
OVERWRITE_EXISTING = True  # Rerun existing simulations to apply measure fix

# Whether to delete eplusout.sql and data_point.zip after extraction
DELETE_SQL_AND_ZIP = False  # Keep SQL files for analysis

# Excel splitting control
MAX_SHEETS_PER_EXCEL = 20
EXCEL_BASE_NAME = "HP_hourly_outputs"

# Flag: whether to produce the Excel workbook(s) with hourly timeseries
PRODUCE_HOURLY_EXCEL = False  # Disable Excel export for faster runs unless needed

# Smoke-run reduced grid to validate airflow sizing changes
TEST_MODE = True            # Reduced parameter set across a few cities
# TEST_MODE = False        # <<< set False for full runs
TEST_CITY = "Chicago"       # <<< primary city for smoke-run

# Diagnostics mode: run a focused subset to validate sizing concerns
DIAGNOSTIC_MODE = False
DIAG_BUILDINGS = ["SmallOffice"]           # focus building type
DIAG_HPS = ["two_speed_lab_data"]
DIAG_BACKUPS = ["electric_resistance_backup"]
DIAG_LOCKS = [0.0, 17.0]

# Parallelism
N_LOGICAL = os.cpu_count() or 1
# Use 75% of logical cores for large batch runs, cap at 80 to leave headroom
MAX_WORKERS = min(80, max(1, int(N_LOGICAL * 0.75)))
print(f"Detected {N_LOGICAL} logical cores, using MAX_WORKERS = {MAX_WORKERS}")

# === FIXED PATHS (server) ===
seed_model_path = "/home/cbianchi/HPSizing/AAA_TEST/SeedModel.osm"
base_weather_path = "/home/cbianchi/HPSizing/AAA_TEST/weather"
measure_dir_path = "/home/cbianchi/HPSizing/AAA_TEST/measures"
base_run_dir = "/home/cbianchi/HPSizing/AAA_TEST/simulations"


# === CITY MAP (state, climate zone, Cambium region) ===
city_region_state = {
    "Baltimore":    {"state": "MD", "climate_zone": "4A", "cambium_region": "RFCEc"},
    "Chicago":      {"state": "IL", "climate_zone": "5A", "cambium_region": "RFCWc"},
    "Denver":       {"state": "CO", "climate_zone": "5B", "cambium_region": "RMPAc"},
    "Minneapolis":  {"state": "MN", "climate_zone": "6A", "cambium_region": "MROEc"},
    "Helena":       {"state": "MT", "climate_zone": "6B", "cambium_region": "NWPPc"},
}


# =========================
# PARAMETER SWEEP CONTROL
# (comment stuff on/off here)
# =========================
BUILDING_TYPES = [
    "SmallOffice",
]

HPRTU_SCENARIOS = [
    "two_speed_lab_data",   # lab data
    # "cchpc_2027_spec",    # CCHPc curves - has problematic PLF curves
]

BACKUP_SCHEMES = [
    "electric_resistance_backup",
]

LOCKOUT_TEMPS_F = [
    17.0,
    0.0,
    -10.0,
]

HTG_SIZING_OPTIONS = [
    '17F',   # Moderate climate sizing
    '0F',    # Cold climate sizing
    '-10F',  # Very cold climate sizing
]

PERFORMANCE_OVERSIZING_FACTORS = [
    0.0,     # No upsizing (strictly cooling-driven)
    0.15,    # 15% upsizing allowed for heating
    0.25,    # 25% upsizing allowed for heating
    0.5,     # 50% upsizing allowed for heating
    0.75,    # 75% upsizing allowed for heating
    1.0,     # 100% upsizing allowed for heating
    1.15,    # 115% upsizing allowed for heating
    1.25,    # 125% upsizing allowed for heating
    1.5,     # 150% upsizing allowed for heating
]


# =========================
# MAIN (PARALLEL DISPATCH + EXPORT)
# =========================

if __name__ == "__main__":
    jobs = build_jobs()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(run_single_job, job): job for job in jobs}

        for i, future in enumerate(as_completed(future_to_job), start=1):
            job = future_to_job[future]
            try:
                (
                    city,
                    bldg,
                    hprtu,
                    backup,
                    lock,
                    perf,
                    htg,
                    scenario_name,
                    elapsed,
                ) = future.result()
                mins = elapsed / 60.0
                print(
                    f"[{i}/{len(jobs)}] {city} | {bldg} | "
                    f"{format_hp_label(hprtu)} | "
                    f"{format_backup_label(backup)} | "
                    f"{format_lock_label(lock)} | "
                    f"{format_perf_oversizing_label(perf)} | "
                    f"{format_htg_sizing_label(htg)} -> {mins:.1f} min"
                )
            except Exception as exc:
                city, bldg, hprtu, backup, lock, perf, htg, scenario_name = job
                print(
                    f"[FAIL] {city} | {bldg} | "
                    f"{format_hp_label(hprtu)} | "
                    f"{format_backup_label(backup)} | "
                    f"{format_lock_label(lock)} | "
                    f"{format_perf_oversizing_label(perf)} | "
                    f"{format_htg_sizing_label(htg)} -> {exc}"
                )

    # After all sims are done, optional hourly Excel export
    if PRODUCE_HOURLY_EXCEL:
        print("\n============================")
        print("📊 Exporting all hourly outputs to Excel...")
        print("============================")
        export_all_hourly_to_excel(
            base_run_dir=base_run_dir,
            year=YEAR,
            delete_artifacts=DELETE_SQL_AND_ZIP,
            max_sheets_per_file=MAX_SHEETS_PER_EXCEL,
            excel_base_name=EXCEL_BASE_NAME,
        )

    # Collect run-level results.json metrics to a single CSV
    print("\n============================")
    print("🧾 Exporting run-level summary to CSV...")
    print("============================")
    collect_results_to_csv(
        base_run_dir=base_run_dir,
        csv_base_name="HP_results",
    )

    # If requested, delete SQL and ZIP artifacts regardless of Excel export
    if DELETE_SQL_AND_ZIP:
        print("\n============================")
        print("🧹 Deleting SQL and ZIP artifacts from run folders...")
        print("============================")
        for city, bldg, scenario_name, run_dir, sql_path in iter_sql_runs(base_run_dir):
            try:
                if os.path.isfile(sql_path):
                    os.remove(sql_path)
                    print(f"  🗑️ Deleted {sql_path}")
            except Exception as e:
                print(f"  ⚠️ Failed to delete {sql_path}: {e}")

            zip_path = os.path.join(run_dir, "data_point.zip")
            if os.path.isfile(zip_path):
                try:
                    os.remove(zip_path)
                    print(f"  🗑️ Deleted {zip_path}")
                except Exception as e:
                    print(f"  ⚠️ Failed to delete {zip_path}: {e}")

    # Example nohup:
    # nohup python3 run_simulations.py > hpsims.log 2>&1 &

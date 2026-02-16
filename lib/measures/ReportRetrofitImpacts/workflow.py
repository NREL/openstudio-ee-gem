"""
Comprehensive workflow script for building retrofit analysis.

This script:
1. Loads a baseline model
2. Extracts baseline embodied carbon and runs baseline EnergyPlus simulation
3. Applies selected retrofit measures (window, wall, roof) with EC3 embodied carbon calculations
4. Runs modified model EnergyPlus simulation
5. Calculates deltas (operational energy, embodied carbon, cost)
6. Updates optimization.xlsx with all scenario data
7. Generates spider chart for comparison

Configuration:
    Edit workflow_config.json to select which measures to apply and configure their arguments.
    See MULTI_MEASURE_USAGE.md for detailed configuration instructions.

Usage:
    python workflow.py
"""

import sys
import os
from pathlib import Path
import json

# ============================================================================
# CONFIGURATION: Load from JSON file
# ============================================================================
def load_config(config_path="workflow_config.json"):
    """Load workflow configuration from JSON file."""
    config_file = Path(__file__).parent / config_path
    
    if not config_file.exists():
        print(f"⚠ Configuration file not found: {config_file}")
        print("Using default configuration: all measures enabled")
        return {
            "measures": {
                "window_enhancement": {"enabled": True, "arguments": {}},
                "wall_insulation": {"enabled": True, "arguments": {"r_value": 13.0, "gwp_statistic": "mean"}},
                "roof_insulation": {"enabled": True, "arguments": {"r_value": 30.0, "gwp_statistic": "mean"}}
            }
        }
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    print(f"[OK] Loaded configuration from: {config_file}")
    return config

# Load configuration
CONFIG = load_config()
MEASURES_TO_APPLY = {key: value.get('enabled', False) for key, value in CONFIG.get('measures', {}).items()}
# ============================================================================

# Add measure directories to Python path
measure_dir = Path(__file__).parent.absolute()
window_measure_dir = measure_dir.parent / "window_enhancement"
wall_insulation_dir = measure_dir.parent / "IncreaseInsulationRValueForExteriorWalls"
roof_insulation_dir = measure_dir.parent / "IncreaseInsulationRValueForRoofs"

# Import OpenStudio first (before modifying sys.path)
try:
    import openstudio
except ImportError:
    print("Error: OpenStudio Python bindings not found.")
    print("Make sure OpenStudio is installed and Python bindings are available.")
    sys.exit(1)

# Import required modules
import pandas as pd
from openpyxl import load_workbook
import plotly.graph_objects as go
from dotenv import load_dotenv
import subprocess
import json
import shutil
import re

# Import from ReportRetrofitImpacts measure (must be done before adding window_enhancement to path)
sys.path.insert(0, str(measure_dir))
from measure import ECReport
from call_RSmeans import RSMeansAPIClient

# Import WindowEnhancement measure using importlib to avoid name collision
import importlib.util

if MEASURES_TO_APPLY.get('window_enhancement'):
    spec = importlib.util.spec_from_file_location("window_measure", window_measure_dir / "measure.py")
    window_measure_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(window_measure_module)
    WindowEnhancement = window_measure_module.WindowEnhancement

if MEASURES_TO_APPLY.get('wall_insulation'):
    spec_wall = importlib.util.spec_from_file_location("wall_insulation_measure", wall_insulation_dir / "measure.py")
    wall_insulation_module = importlib.util.module_from_spec(spec_wall)
    spec_wall.loader.exec_module(wall_insulation_module)
    # Note: The class is incorrectly named in the measure file
    WallInsulationMeasure = wall_insulation_module.IncreaseInsulationRValueForRoofs

if MEASURES_TO_APPLY.get('roof_insulation'):
    spec_roof = importlib.util.spec_from_file_location("roof_insulation_measure", roof_insulation_dir / "measure.py")
    roof_insulation_module = importlib.util.module_from_spec(spec_roof)
    spec_roof.loader.exec_module(roof_insulation_module)
    RoofInsulationMeasure = roof_insulation_module.IncreaseInsulationRValueForRoofs


def find_openstudio_cli():
    """Find OpenStudio CLI executable."""
    common_paths = [
        r"C:\openstudio-3.8.0\bin\openstudio.exe",
        r"C:\openstudio-3.7.0\bin\openstudio.exe",
        r"C:\openstudio-3.9.0\bin\openstudio.exe",
        r"/usr/local/openstudio-3.8.0/bin/openstudio",
        r"/Applications/OpenStudio-3.8.0/bin/openstudio"
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Try to find in PATH
    cli_path = shutil.which("openstudio")
    if cli_path:
        return cli_path
    
    raise FileNotFoundError("OpenStudio CLI not found. Please install OpenStudio.")


def run_energyplus_simulation(osm_path, weather_file=None):
    """
    Run EnergyPlus simulation using OpenStudio CLI.
    
    Args:
        osm_path: Path to the OpenStudio model file
        weather_file: Path to the weather file (optional)
    
    Returns:
        Path to eplustbl.html report if successful, None otherwise
    """
    osm_path = Path(osm_path)
    
    if not osm_path.exists():
        print(f"[ERROR] Model file not found: {osm_path}")
        return None
    
    # Find OpenStudio CLI
    try:
        cli_path = find_openstudio_cli()
        print(f"[OK] Found OpenStudio CLI: {cli_path}")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return None
    
    # Create workflow.osw in the same directory as the model
    workflow_dir = osm_path.parent
    workflow_path = workflow_dir / "workflow.osw"
    
    # Determine weather file path
    weather_file_str = ""
    if weather_file and Path(weather_file).exists():
        weather_file_str = str(Path(weather_file).absolute())
    
    workflow_json = {
        "seed_file": osm_path.name,
        "weather_file": weather_file_str,
        "steps": [],
        "created_at": "2025-12-30T00:00:00Z",
        "updated_at": "2025-12-30T00:00:00Z"
    }
    
    with open(workflow_path, 'w') as f:
        json.dump(workflow_json, f, indent=2)
    
    print(f"[OK] Created workflow: {workflow_path}")
    
    # Run OpenStudio CLI
    print(f"Running EnergyPlus simulation...")
    try:
        result = subprocess.run(
            [cli_path, "run", "-w", str(workflow_path)],
            cwd=str(workflow_dir),
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode == 0:
            print(f"[OK] Simulation completed successfully")
        else:
            print(f"⚠ Simulation completed with warnings (return code: {result.returncode})")
            if result.stderr:
                print(f"STDERR: {result.stderr[:500]}")
    
    except subprocess.TimeoutExpired:
        print("[ERROR] Simulation timed out after 600 seconds")
        return None
    except Exception as e:
        print(f"[ERROR] Error running simulation: {e}")
        return None
    
    # Look for eplustbl.html in multiple possible locations
    possible_report_paths = [
        workflow_dir / "run" / "eplustbl.htm",
        workflow_dir / "run" / "eplustbl.html",
        workflow_dir / "reports" / "eplustbl.html",
        workflow_dir / "reports" / "eplustbl.htm"
    ]
    
    for report_path in possible_report_paths:
        if report_path.exists():
            print(f"[OK] Found report: {report_path}")
            return report_path
    
    print("⚠ Could not find eplustbl.html report")
    return None


def extract_model_data(osm_path):
    """
    Extract embodied carbon data from OpenStudio model AdditionalProperties.
    
    Args:
        osm_path: Path to the OpenStudio model file
    
    Returns:
        dict with extracted data
    """
    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(str(osm_path))
    
    if not model_opt.is_initialized():
        print(f"[ERROR] Failed to load model: {osm_path}")
        return {}
    
    model = model_opt.get()
    carbon, carbon_detail = extract_embodied_carbon(model)
    
    return {
        'embodied_carbon': carbon,
        'carbon_detail': carbon_detail
    }


def extract_embodied_carbon(model):
    """Extract total embodied carbon from model AdditionalProperties.
    
    Checks constructions, surfaces, and subsurfaces for embodied carbon data.
    Different measures store data in different places:
    - Window enhancement: stores on subsurfaces
    - Insulation measures: may store on constructions or surfaces
    """
    total_carbon = 0.0
    carbon_by_component = {}
    
    # Check constructions
    for construction in model.getConstructions():
        props = construction.additionalProperties()
        
        # Look for embodied carbon properties (different naming conventions)
        for feature_name in ["total_embodied_carbon_kgCO2eq", "embodied_carbon_kgCO2eq", "embodied_carbon_kg_co2_eq"]:
            if props.hasFeature(feature_name):
                value = props.getFeatureAsDouble(feature_name)
                if value.is_initialized():
                    carbon = value.get()
                    total_carbon += carbon
                    carbon_by_component[f"Construction: {construction.nameString()}"] = carbon
                    break
    
    # Check subsurfaces (windows, doors) - where window_enhancement stores data
    for subsurface in model.getSubSurfaces():
        props = subsurface.additionalProperties()
        
        for feature_name in ["embodied_carbon_kg_co2_eq", "embodied_carbon_kgCO2eq", "total_embodied_carbon_kgCO2eq"]:
            if props.hasFeature(feature_name):
                value = props.getFeatureAsDouble(feature_name)
                if value.is_initialized():
                    carbon = value.get()
                    total_carbon += carbon
                    carbon_by_component[f"Subsurface: {subsurface.nameString()}"] = carbon
                    break
    
    # Check surfaces (walls, roofs, floors) - where insulation measures might store data
    for surface in model.getSurfaces():
        props = surface.additionalProperties()
        
        for feature_name in ["embodied_carbon_kg_co2_eq", "embodied_carbon_kgCO2eq", "total_embodied_carbon_kgCO2eq"]:
            if props.hasFeature(feature_name):
                value = props.getFeatureAsDouble(feature_name)
                if value.is_initialized():
                    carbon = value.get()
                    total_carbon += carbon
                    carbon_by_component[f"Surface: {surface.nameString()}"] = carbon
                    break
    
    return total_carbon, carbon_by_component


def apply_window_enhancement_measure(model, arguments):
    """
    Apply window enhancement measure to the model.
    
    Args:
        model: OpenStudio model
        arguments: dict of measure arguments
    
    Returns:
        bool: Success status
    """
    print(f"\n{'='*80}")
    print("Applying Window Enhancement Measure")
    print(f"{'='*80}\n")
    
    # Create OSRunner
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    
    # Create measure
    measure = WindowEnhancement()
    
    # Get measure arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Set argument values
    for arg in args:
        arg_name = arg.name()
        if arg_name in arguments:
            value = arguments[arg_name]
            
            # Set value based on argument type
            if isinstance(value, bool):
                arg.setValue(value)
            elif isinstance(value, int):
                arg.setValue(int(value))
            elif isinstance(value, float):
                arg.setValue(float(value))
            else:
                arg.setValue(str(value))
            
            # Update the map
            arg_map[arg_name] = arg
            
            # Mask sensitive information in output
            if arg_name in ['api_key', 'client_id', 'client_secret', 'token', 'password']:
                display_value = '***REDACTED***'
            else:
                display_value = value
            print(f"  Set {arg_name} = {display_value}")
    
    # Run measure
    result = measure.run(model, runner, arg_map)
    
    # Print results
    print(f"Result: {runner.result().value().valueName()}")
    
    for info in runner.result().info():
        print(f"INFO: {info.logMessage()}")
    
    for warning in runner.result().warnings():
        print(f"WARNING: {warning.logMessage()}")
    
    for error in runner.result().errors():
        print(f"ERROR: {error.logMessage()}")
    
    return result


def apply_wall_insulation_measure(model, arguments):
    """
    Apply wall insulation measure to the model.
    
    Args:
        model: OpenStudio model
        arguments: dict of measure arguments
    
    Returns:
        bool: Success status
    """
    print(f"\n{'='*80}")
    print("Applying Wall Insulation Measure")
    print(f"{'='*80}\n")
    
    # Create OSRunner
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    
    # Create measure
    measure = WallInsulationMeasure()
    
    # Get measure arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Set argument values
    for arg in args:
        arg_name = arg.name()
        if arg_name in arguments:
            value = arguments[arg_name]
            
            # Set value based on argument type
            if isinstance(value, bool):
                arg.setValue(value)
            elif isinstance(value, int):
                arg.setValue(int(value))
            elif isinstance(value, float):
                arg.setValue(float(value))
            else:
                arg.setValue(str(value))
            
            # Update the map
            arg_map[arg_name] = arg
            
            # Mask sensitive information in output
            if arg_name in ['api_key', 'client_id', 'client_secret', 'token', 'password']:
                display_value = '***REDACTED***'
            else:
                display_value = value
            print(f"  Set {arg_name} = {display_value}")
    
    # Run measure
    result = measure.run(model, runner, arg_map)
    
    # Print results
    print(f"Result: {runner.result().value().valueName()}")
    
    for info in runner.result().info():
        print(f"INFO: {info.logMessage()}")
    
    for warning in runner.result().warnings():
        print(f"WARNING: {warning.logMessage()}")
    
    for error in runner.result().errors():
        print(f"ERROR: {error.logMessage()}")
    
    return result


def apply_roof_insulation_measure(model, arguments):
    """
    Apply roof insulation measure to the model.
    
    Args:
        model: OpenStudio model
        arguments: dict of measure arguments
    
    Returns:
        bool: Success status
    """
    print(f"\n{'='*80}")
    print("Applying Roof Insulation Measure")
    print(f"{'='*80}\n")
    
    # Create OSRunner
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    
    # Create measure
    measure = RoofInsulationMeasure()
    
    # Get measure arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Set argument values
    for arg in args:
        arg_name = arg.name()
        if arg_name in arguments:
            value = arguments[arg_name]
            
            # Set value based on argument type
            if isinstance(value, bool):
                arg.setValue(value)
            elif isinstance(value, int):
                arg.setValue(int(value))
            elif isinstance(value, float):
                arg.setValue(float(value))
            else:
                arg.setValue(str(value))
            
            # Update the map
            arg_map[arg_name] = arg
            
            # Mask sensitive information in output
            if arg_name in ['api_key', 'client_id', 'client_secret', 'token', 'password']:
                display_value = '***REDACTED***'
            else:
                display_value = value
            print(f"  Set {arg_name} = {display_value}")
    
    # Run measure
    result = measure.run(model, runner, arg_map)
    
    # Print results
    print(f"Result: {runner.result().value().valueName()}")
    
    for info in runner.result().info():
        print(f"INFO: {info.logMessage()}")
    
    for warning in runner.result().warnings():
        print(f"WARNING: {warning.logMessage()}")
    
    for error in runner.result().errors():
        print(f"ERROR: {error.logMessage()}")
    
    return result


def get_rsmeans_cost(component_type="windows", runner=None):
    """
    Get cost estimate from RSMeans API.
    
    Args:
        component_type: Type of component (e.g., 'windows')
        runner: Optional OSRunner for logging
    
    Returns:
        float: Cost estimate or 0.0 if unavailable
    """
    load_dotenv()
    client_id = os.getenv('client_id')
    client_secret = os.getenv('client_secret')
    
    if not client_id or not client_secret:
        print("⚠ RSMeans API credentials not found in .env file")
        return 0.0
    
    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=True)
    
    if not client.authenticate():
        print("⚠ Failed to authenticate with RSMeans API")
        return 0.0
    
    print("[OK] Successfully authenticated with RSMeans API")
    
    # Search for relevant cost line items
    search_results = client.search_unit_costlines(
        release_id='2019-an',
        measurement_system='imp',
        searchTerm=component_type
    )
    
    if search_results and len(search_results) > 0:
        # Get first result's unit cost (simplified - should be refined)
        try:
            cost = float(search_results[0].get('unitCost', 0.0))
            print(f"[OK] Retrieved cost estimate: ${cost:.2f}")
            return cost
        except (ValueError, KeyError, IndexError):
            print("⚠ Could not parse cost from RSMeans results")
            return 0.0
    
    return 0.0


def update_optimization_spreadsheet(baseline_data, modified_data, delta_data, output_path):
    """
    Update optimization.xlsx with scenario data.
    Excel structure: Factor | Scenario_1 | Scenario_2 | Scenario_3 | Unit | Basis
    
    We'll update Scenario_1 with modified data and Basis with baseline data.
    
    Args:
        baseline_data: dict with baseline metrics
        modified_data: dict with modified metrics  
        delta_data: dict with delta metrics
        output_path: Path to save updated spreadsheet
    """
    print(f"\n{'='*80}")
    print("Updating Optimization Spreadsheet")
    print(f"{'='*80}\n")
    
    excel_path = measure_dir / 'resources' / 'optimization.xlsx'
    
    if not excel_path.exists():
        print(f"✗ Excel file not found: {excel_path}")
        return
    
    wb = load_workbook(excel_path, data_only=False, keep_links=True)
    
    if 'values' not in wb.sheetnames:
        print("✗ Sheet 'values' not found in Excel file")
        return
    
    ws = wb['values']
    
    # Map our data to Excel factor names (note: "Embodied Energy" in Excel means operational energy)
    factor_mapping = {
        'Embodied Carbon': {
            'Scenario_1': modified_data['embodied_carbon'],
            'Basis': baseline_data['embodied_carbon']
        },
        'Embodied Energy': {  # Excel uses this name for operational energy
            'Scenario_1': modified_data['operational_energy'],
            'Basis': baseline_data['operational_energy']
        },
        'Cost': {
            'Scenario_1': modified_data['cost'],
            'Basis': baseline_data['cost']
        }
    }
    
    # Build column index map from header row
    col_map = {}
    for col_idx, cell in enumerate(ws[1], start=1):
        if cell.value:
            col_map[str(cell.value).strip()] = col_idx
    
    print(f"  Excel columns found: {list(col_map.keys())}")
    
    # Update cells
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        factor_name = str(row[0].value).strip() if row[0].value else ""
        
        if factor_name in factor_mapping:
            for col_name, value in factor_mapping[factor_name].items():
                if col_name in col_map:
                    col_idx = col_map[col_name]
                    ws.cell(row=row_idx, column=col_idx, value=value)
                    print(f"  Updated {factor_name} - {col_name}: {value:.2f}")
                else:
                    print(f"  ⚠ Column '{col_name}' not found in Excel")
    
    wb.save(output_path)
    print(f"\n[OK] Spreadsheet saved: {output_path}")


def generate_spider_chart(baseline_data, modified_data, output_path):
    """Generate spider chart comparing baseline and modified scenarios."""
    print(f"\n{'='*80}")
    print("Generating Spider Chart")
    print(f"{'='*80}\n")
    
    categories = ['Embodied Carbon\n(kg CO2eq)', 
                  'Operational Energy\n(GJ)', 
                  'Cost\n($)']
    
    # Normalize values (as % of baseline)
    baseline_values = [
        baseline_data['embodied_carbon'],
        baseline_data['operational_energy'],
        baseline_data['cost']
    ]
    
    modified_values = [
        modified_data['embodied_carbon'],
        modified_data['operational_energy'],
        modified_data['cost']
    ]
    
    # Debug output
    print("Raw Values:")
    for cat, base, mod in zip(categories, baseline_values, modified_values):
        print(f"  {cat.replace(chr(10), ' ')}: Baseline={base:.2f}, Modified={mod:.2f}")
    
    normalized_baseline = [100, 100, 100]  # Baseline is 100%
    
    # Better normalization handling for edge cases
    normalized_modified = []
    for mod, base, cat in zip(modified_values, baseline_values, categories):
        if base > 0:
            # Normal case: express as percentage of baseline
            norm = (mod / base * 100)
        elif mod > 0:
            # Edge case: baseline is 0 but modified has value
            # Can't express as % of baseline, so use absolute value scaled
            norm = 150  # Show at max to indicate "infinite increase"
            print(f"  ⚠ Warning: {cat.replace(chr(10), ' ')} baseline is 0, setting to 150% to show increase")
        else:
            # Both are 0
            norm = 100
        normalized_modified.append(norm)
    
    print("\nNormalized Values (% of Baseline):")
    for cat, norm in zip(categories, normalized_modified):
        print(f"  {cat.replace(chr(10), ' ')}: {norm:.1f}%")
    
    # Create spider chart
    fig = go.Figure()
    
    # Baseline trace
    fig.add_trace(go.Scatterpolar(
        r=normalized_baseline,
        theta=categories,
        fill='toself',
        name='Baseline',
        line_color='blue',
        line_width=2
    ))
    
    # Modified/Retrofit trace
    fig.add_trace(go.Scatterpolar(
        r=normalized_modified,
        theta=categories,
        fill='toself',
        name='Retrofit Package',
        line_color='red',
        line_width=2
    ))
    
    # Update layout
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 150],
                ticksuffix='%'
            )),
        title={
            'text': "Building Retrofit Impact Analysis<br><sub>Values shown as % of baseline</sub>",
            'x': 0.5,
            'xanchor': 'center'
        },
        height=700,
        width=900,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=120, r=150, t=100, b=100)
    )
    
    fig.write_html(output_path)
    print(f"[OK] Spider chart saved: {output_path}")
    print(f"  Chart shows normalized % comparison relative to baseline")


def main():
    print(f"\n{'='*80}")
    print("COMPREHENSIVE BUILDING RETROFIT WORKFLOW")
    print(f"{'='*80}\n")
    
    # Configuration
    baseline_model_path = measure_dir / "tests" / "example_model.osm"
    weather_file = measure_dir / "tests" / "weather" / "USA_CO_Denver.intl.AP.725650_TMY3.epw"
    output_dir = measure_dir / "tests" / "workflow_output"
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if files exist
    if not baseline_model_path.exists():
        print(f"[ERROR] Baseline model not found: {baseline_model_path}")
        sys.exit(1)
    
    if not weather_file.exists():
        print(f"⚠ Weather file not found: {weather_file}")
        print("  EnergyPlus simulations will be skipped")
    
    print(f"Baseline model: {baseline_model_path}")
    print(f"Weather file: {weather_file}")
    print(f"Output directory: {output_dir}\n")
    
    # =========================================================================
    # STEP 1: Process Baseline Model
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 1: BASELINE MODEL ANALYSIS")
    print(f"{'='*80}\n")
    
    # Load baseline model
    translator = openstudio.osversion.VersionTranslator()
    baseline_model_opt = translator.loadModel(str(baseline_model_path))
    
    if not baseline_model_opt.is_initialized():
        print("[ERROR] Failed to load baseline model")
        sys.exit(1)
    
    baseline_model = baseline_model_opt.get()
    print(f"[OK] Loaded baseline model")
    
    # Extract baseline embodied carbon
    baseline_carbon, baseline_carbon_detail = extract_embodied_carbon(baseline_model)
    print(f"[OK] Baseline embodied carbon: {baseline_carbon:.2f} kg CO2eq")
    
    # Run baseline simulation using existing function from apply_reporting_measure
    baseline_eplustbl_path = None
    if weather_file.exists():
        baseline_eplustbl_path = run_energyplus_simulation(baseline_model_path, weather_file)
    
    # Parse baseline energy from eplustbl.html if available
    baseline_energy = 0.0
    if baseline_eplustbl_path and baseline_eplustbl_path.exists():
        # Use ECReport's parse method
        report = ECReport()
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        eplustbl_data = report.parse_eplustbl_html(baseline_eplustbl_path, runner)
        if "total_site_energy_GJ" in eplustbl_data and eplustbl_data["total_site_energy_GJ"]:
            baseline_energy = float(eplustbl_data["total_site_energy_GJ"])
    
    print(f"[OK] Baseline operational energy: {baseline_energy:.2f} GJ")
    
    # Get baseline cost (could be zero if no RSMeans data)
    baseline_cost = 1000.0  # Placeholder - could use RSMeans
    print(f"[OK] Baseline cost: ${baseline_cost:.2f}")
    
    baseline_data = {
        'embodied_carbon': baseline_carbon,
        'operational_energy': baseline_energy,
        'cost': baseline_cost
    }
    
    # =========================================================================
    # STEP 2: Apply Selected Retrofit Measures
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 2: APPLY SELECTED RETROFIT MEASURES")
    print(f"{'='*80}\n")
    
    # Show which measures are enabled
    enabled_measures = [k for k, v in MEASURES_TO_APPLY.items() if v]
    print(f"Enabled measures: {', '.join(enabled_measures)}\n")
    
    # Create a copy of the model for modification
    modified_model = baseline_model.clone().to_Model()
    
    # Read EC3 API token from config.ini
    import configparser
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.path.join(repo_root, "config.ini")
    config = configparser.ConfigParser()
    config.read(config_path)
    ec3_api_token = config["EC3_API_TOKEN"]["API_TOKEN"]
    
    # Apply Window Enhancement if enabled
    if MEASURES_TO_APPLY.get('window_enhancement'):
        # Get arguments from config, or use defaults
        window_config = CONFIG.get('measures', {}).get('window_enhancement', {}).get('arguments', {})
        window_args = {
            # Required choice arguments
            'wf_option': window_config.get('wf_option', 'wood window frame'),
            'film_option': window_config.get('film_option', 'solar control film'),
            'glass_option': window_config.get('glass_option', 'triple pane clear'),
            'gwp_statistic': window_config.get('gwp_statistic', 'mean'),
            
            # Required string arguments
            'api_key': ec3_api_token,
            
            # Required double arguments
            'caulking_thickness': window_config.get('caulking_thickness', 0.0127),  # 0.5 inches in meters
            'glass_pane_thickness': window_config.get('glass_pane_thickness', 0.003),  # 3mm
            'gap_thickness': window_config.get('gap_thickness', 0.013),  # 13mm
            'glass_solar_transmittance': window_config.get('glass_solar_transmittance', 0.7),
            'glass_front_emissivity': window_config.get('glass_front_emissivity', 0.84),
            'glass_back_emissivity': window_config.get('glass_back_emissivity', 0.84),
            'length_per_unit': window_config.get('length_per_unit', 1.0),  # meters
            
            # Required integer arguments
            'user_num_panes': window_config.get('user_num_panes', 3),
            'num_horizontal_dividers': window_config.get('num_horizontal_dividers', 0),
            'num_vertical_dividers': window_config.get('num_vertical_dividers', 0),
            
            # Optional arguments
            'space_infiltration_reduction_percent': window_config.get('space_infiltration_reduction_percent', 50.0),
            'caulking_option': window_config.get('caulking_option', 'acrylic'),
            'weatherstrip_option': window_config.get('weatherstrip_option', 'silicone adhesive smoke gasket'),
            'secondary_glazing_option': window_config.get('secondary_glazing_option', 'none')
        }
        
        success = apply_window_enhancement_measure(modified_model, window_args)
        
        if not success:
            print("[ERROR] Failed to apply window enhancement measure")
            sys.exit(1)
    
    # Apply Wall Insulation if enabled
    if MEASURES_TO_APPLY.get('wall_insulation'):
        # Get arguments from config, or use defaults
        wall_config = CONFIG.get('measures', {}).get('wall_insulation', {}).get('arguments', {})
        wall_args = {
            'r_value': wall_config.get('r_value', 13.0),
            'api_key': ec3_api_token,
            'gwp_statistic': wall_config.get('gwp_statistic', 'mean')
        }
        
        success = apply_wall_insulation_measure(modified_model, wall_args)
        
        if not success:
            print("[ERROR] Failed to apply wall insulation measure")
            sys.exit(1)
    
    # Apply Roof Insulation if enabled
    if MEASURES_TO_APPLY.get('roof_insulation'):
        # Get arguments from config, or use defaults
        roof_config = CONFIG.get('measures', {}).get('roof_insulation', {}).get('arguments', {})
        roof_args = {
            'r_value': roof_config.get('r_value', 30.0),
            'api_key': ec3_api_token,
            'gwp_statistic': roof_config.get('gwp_statistic', 'mean')
        }
        
        success = apply_roof_insulation_measure(modified_model, roof_args)
        
        if not success:
            print("[ERROR] Failed to apply roof insulation measure")
            sys.exit(1)
    
    # Save modified model
    modified_model_path = output_dir / "modified_model.osm"
    modified_model.save(str(modified_model_path), True)
    print(f"[OK] Saved modified model: {modified_model_path}")
    
    # =========================================================================
    # STEP 3: Process Modified Model
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 3: MODIFIED MODEL ANALYSIS")
    print(f"{'='*80}\n")
    
    # Extract modified embodied carbon
    modified_carbon, modified_carbon_detail = extract_embodied_carbon(modified_model)
    print(f"[OK] Modified embodied carbon: {modified_carbon:.2f} kg CO2eq")
    
    # Run modified simulation using existing function from apply_reporting_measure
    modified_eplustbl_path = None
    if weather_file.exists():
        modified_eplustbl_path = run_energyplus_simulation(modified_model_path, weather_file)
    
    # Parse modified energy from eplustbl.html if available
    modified_energy = 0.0
    if modified_eplustbl_path and modified_eplustbl_path.exists():
        # Use ECReport's parse method
        report = ECReport()
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        eplustbl_data = report.parse_eplustbl_html(modified_eplustbl_path, runner)
        if "total_site_energy_GJ" in eplustbl_data and eplustbl_data["total_site_energy_GJ"]:
            modified_energy = float(eplustbl_data["total_site_energy_GJ"])
    
    print(f"[OK] Modified operational energy: {modified_energy:.2f} GJ")
    
    # Get modified cost
    modified_cost = baseline_cost + get_rsmeans_cost("windows")
    print(f"[OK] Modified cost: ${modified_cost:.2f}")
    
    modified_data = {
        'embodied_carbon': modified_carbon,
        'operational_energy': modified_energy,
        'cost': modified_cost
    }
    
    # =========================================================================
    # STEP 4: Calculate Deltas
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 4: CALCULATE DELTAS")
    print(f"{'='*80}\n")
    
    delta_data = {
        'embodied_carbon': modified_carbon - baseline_carbon,
        'operational_energy': modified_energy - baseline_energy,
        'cost': modified_cost - baseline_cost
    }
    
    print(f"Δ Embodied Carbon: {delta_data['embodied_carbon']:+.2f} kg CO2eq")
    print(f"Δ Operational Energy: {delta_data['operational_energy']:+.2f} GJ")
    print(f"Δ Cost: ${delta_data['cost']:+.2f}")
    
    # =========================================================================
    # STEP 5: Update Optimization Spreadsheet
    # =========================================================================
    updated_excel_path = output_dir / "optimization_updated.xlsx"
    update_optimization_spreadsheet(baseline_data, modified_data, delta_data, updated_excel_path)
    
    # =========================================================================
    # STEP 6: Generate Spider Chart
    # =========================================================================
    spider_chart_path = output_dir / "retrofit_comparison_spider_chart.html"
    generate_spider_chart(baseline_data, modified_data, spider_chart_path)
    
    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print(f"\n\n{'='*80}")
    print("WORKFLOW COMPLETE!")
    print(f"{'='*80}\n")
    
    # Show which measures were applied
    applied_measures = []
    if MEASURES_TO_APPLY.get('window_enhancement'):
        applied_measures.append("Window Enhancement")
    if MEASURES_TO_APPLY.get('wall_insulation'):
        applied_measures.append("Wall Insulation")
    if MEASURES_TO_APPLY.get('roof_insulation'):
        applied_measures.append("Roof Insulation")
    
    print(f"Applied Measures:")
    for measure in applied_measures:
        print(f"  [OK] {measure}")
    
    print(f"\nResults saved in: {output_dir}")
    print(f"  - Modified model: modified_model.osm")
    print(f"  - Updated spreadsheet: optimization_updated.xlsx")
    print(f"  - Spider chart: retrofit_comparison_spider_chart.html")
    print(f"\n{'='*80}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Apply Operating Cost Carbon Reporting Measure to in.osm
This script:
1. Loads in.osm from tests folder
2. Runs an EnergyPlus simulation to generate SQL output
3. Applies the reporting measure to calculate costs and emissions
4. Saves the model with AdditionalProperties to in_modified.osm
"""

from pathlib import Path
import sys
import json
import shutil

OPENSTUDIO_VERSION = "3.11.0"


def detect_openstudio_paths(version: str):
    """Detect OpenStudio Python bindings and CLI executable path."""
    candidate_python_paths = [
        Path(f"C:/Program Files/openstudio-{version}/Python"),
        Path(f"/Applications/OpenStudio-{version}/Python")
    ]
    candidate_cli_paths = [
        Path(f"C:/Program Files/openstudio-{version}/bin/openstudio.exe"),
        Path(f"/Applications/OpenStudio-{version}/bin/openstudio")
    ]

    py_path = next((p for p in candidate_python_paths if p.exists()), None)
    cli_path = next((p for p in candidate_cli_paths if p.exists()), None)
    return py_path, cli_path


openstudio_path, openstudio_cli_path = detect_openstudio_paths(OPENSTUDIO_VERSION)

if openstudio_path:
    sys.path.insert(0, str(openstudio_path))
    print(f"Using OpenStudio Python bindings from: {openstudio_path}")
else:
    print("Warning: OpenStudio Python bindings path not found in standard locations")
    print("Will attempt to use system Python OpenStudio package")

if openstudio_cli_path:
    print(f"Using OpenStudio CLI from: {openstudio_cli_path}")
else:
    print("Warning: OpenStudio CLI not found in standard locations; will use PATH lookup")

if openstudio_path and sys.version_info[:2] != (3, 12):
    print(
        f"Warning: Detected Python {sys.version_info.major}.{sys.version_info.minor}. "
        "OpenStudio 3.11 Python bindings require Python 3.12."
    )

import openstudio
from measure import OperatingCostCarbonReport

print(f"OpenStudio version: {openstudio.openStudioVersion()}")


def run_simulation(model_path, epw_path, run_dir):
    """
    Run an OpenStudio/EnergyPlus simulation.
    
    Args:
        model_path: Path to the OSM file
        epw_path: Path to the weather file
        run_dir: Directory where simulation will be run
        
    Returns:
        True if successful, False otherwise
    """
    print("\n" + "="*80)
    print("RUNNING ENERGYPLUS SIMULATION")
    print("="*80)
    
    # Load the model
    translator = openstudio.osversion.VersionTranslator()
    translator.setAllowNewerVersions(True)  # Allow loading newer version models
    model_path_os = openstudio.toPath(str(model_path))
    loaded_model = translator.loadModel(model_path_os)
    
    if not loaded_model.is_initialized():
        print(f"ERROR: Failed to load model at {model_path}")
        print(f"Version translator errors: {translator.errors()}")
        print(f"Version translator warnings: {translator.warnings()}")
        return False
    
    model = loaded_model.get()
    print(f"✓ Model loaded successfully")
    
    # Create run directory
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up workflow
    workflow = openstudio.WorkflowJSON()
    workflow.setSeedFile(openstudio.toPath(str(model_path)))
    workflow.setWeatherFile(openstudio.toPath(str(epw_path)))
    
    # Add output requests for hourly data
    # We need to request hourly output for electricity and gas
    output_variable = model.getOutputVariables()
    
    # Add hourly electricity output
    elec_output = openstudio.model.OutputVariable("Electricity:Facility", model)
    elec_output.setReportingFrequency("Hourly")
    
    # Add hourly gas output
    gas_output = openstudio.model.OutputVariable("NaturalGas:Facility", model)
    gas_output.setReportingFrequency("Hourly")
    
    # Save updated model to run directory
    model_run_path = run_dir / "in.osm"
    model.save(openstudio.toPath(str(model_run_path)), True)
    
    # Create workflow OSW file
    osw_path = run_dir / "workflow.osw"
    workflow.saveAs(openstudio.toPath(str(osw_path)))
    
    print(f"Model prepared at: {model_run_path}")
    print(f"Running simulation...")
    
    # Run simulation using OpenStudio CLI
    import subprocess
    try:
        # Update osw to include weather file and seed
        osw_dict = {
            "seed_file": str(model_run_path),
            "weather_file": str(epw_path),
            "steps": []
        }
        
        with open(osw_path, 'w') as f:
            json.dump(osw_dict, f, indent=2)
        
        # Run with openstudio CLI
        openstudio_cmd = str(openstudio_cli_path) if openstudio_cli_path else "openstudio"
        result = subprocess.run(
            [openstudio_cmd, "run", "-w", str(osw_path)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        sql_path = run_dir / "run" / "eplusout.sql"
        if sql_path.exists():
            print(f"✓ Simulation completed successfully")
            print(f"  SQL file: {sql_path}")
            return True
        else:
            print(f"✗ Simulation failed - no SQL file generated")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ Error running simulation: {str(e)}")
        return False


def apply_reporting_measure(model, sql_file_path):
    """
    Apply the reporting measure to calculate costs and emissions.
    
    Args:
        model: OpenStudio model object
        sql_file_path: Path to the SQL file from simulation
        
    Returns:
        Dictionary with results, or None if failed
    """
    print("\n" + "="*80)
    print("APPLYING REPORTING MEASURE")
    print("="*80)
    
    # Attach SQL file to model
    if not Path(sql_file_path).exists():
        print(f"ERROR: SQL file not found: {sql_file_path}")
        return None
    
    sql_file = openstudio.SqlFile(openstudio.toPath(str(sql_file_path)))
    model.setSqlFile(sql_file)
    
    # Create runner and measure instance
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    
    # Set the SQL file in the runner
    runner.setLastEnergyPlusSqlFilePath(openstudio.toPath(str(sql_file_path)))
    
    # Set the model in the runner
    runner.setLastOpenStudioModel(model)
    
    measure = OperatingCostCarbonReport()
    
    # Setup arguments (empty for this measure)
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Run the measure
    print("Running measure...")
    result = measure.run(runner, arg_map)
    
    # Display results
    print("\n" + "="*80)
    print("MEASURE RESULTS")
    print("="*80)
    print(f"Result: {runner.result().value().valueName()}")
    
    if runner.result().info():
        print("\nInfo Messages:")
        for info in runner.result().info():
            print(f"  ℹ {info.logMessage()}")
    
    if runner.result().warnings():
        print("\nWarnings:")
        for warning in runner.result().warnings():
            print(f"  ⚠ {warning.logMessage()}")
    
    if runner.result().errors():
        print("\nErrors:")
        for error in runner.result().errors():
            print(f"  ✗ {error.logMessage()}")
    
    # Check if measure actually succeeded
    if runner.result().value().valueName() != "Success":
        print("\n✗ Measure did not complete successfully")
        return None, None
    
    # Extract output values
    print("\n" + "="*80)
    print("CALCULATED VALUES")
    print("="*80)
    
    output_names = [
        "annual_electricity_kwh",
        "annual_gas_gj",
        "annual_electricity_emissions_kg",
        "annual_gas_emissions_kg",
        "annual_total_emissions_kg",
        "annual_total_emissions_mt",
        "on_peak_electricity_kwh",
        "off_peak_electricity_kwh",
        "peak_demand_kw",
        "annual_electricity_cost",
        "annual_gas_cost",
        "annual_total_utility_cost"
    ]
    
    results_dict = {}
    step_values = runner.result().stepValues()
    
    # stepValues() returns a vector/list of StepValue objects
    for step_value in step_values:
        name = step_value.name()
        if name in output_names:
            # Handle different API versions
            try:
                if hasattr(step_value, 'valueAsVariant'):
                    value = float(step_value.valueAsVariant())
                elif hasattr(step_value, 'value'):
                    value = float(step_value.value())
                else:
                    value = float(str(step_value))
            except Exception as e:
                print(f"  {name}: Error extracting value: {e}")
                continue
            
            results_dict[name] = value
            
            # Format output nicely
            if "kwh" in name:
                print(f"  {name}: {value:,.2f} kWh")
            elif "gj" in name:
                print(f"  {name}: {value:,.2f} GJ")
            elif "emissions" in name:
                if "mt" in name:
                    print(f"  {name}: {value:,.2f} metric tons CO2e")
                else:
                    print(f"  {name}: {value:,.2f} kg CO2e")
            elif "cost" in name:
                print(f"  {name}: ${value:,.2f}")
            elif "kw" in name:
                print(f"  {name}: {value:,.2f} kW")
            else:
                print(f"  {name}: {value:,.2f}")
    
    # Check if we got all expected values
    for name in output_names:
        if name not in results_dict:
            print(f"  {name}: Not available")
    
    print("="*80)
    
    # Get the modified model from the runner
    modified_model = None
    model_opt = runner.lastOpenStudioModel()
    if model_opt.is_initialized():
        modified_model = model_opt.get()
    
    return results_dict, modified_model


def main():
    """Main execution function."""
    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    
    # Define paths
    model_path = CURRENT_DIR_PATH / "tests" / "in.osm"
    epw_path = CURRENT_DIR_PATH / "tests" / "in.epw"
    run_dir = CURRENT_DIR_PATH / "tests" / "run"
    output_model_path = CURRENT_DIR_PATH / "tests" / "in_modified.osm"
    results_json_path = CURRENT_DIR_PATH / "tests" / "measure_results.json"
    
    print("="*80)
    print("OPERATING COST CARBON REPORTING MEASURE - TEST")
    print("="*80)
    print(f"Input model: {model_path}")
    print(f"Weather file: {epw_path}")
    print(f"Output model: {output_model_path}")
    print("="*80)
    
    # Check if input files exist
    if not model_path.exists():
        print(f"\n✗ ERROR: Model file not found: {model_path}")
        sys.exit(1)
    
    if not epw_path.exists():
        print(f"\n✗ ERROR: Weather file not found: {epw_path}")
        sys.exit(1)
    
    # Step 1: Run simulation
    success = run_simulation(model_path, epw_path, run_dir)
    
    if not success:
        print("\n✗ Simulation failed. Cannot apply reporting measure without SQL data.")
        sys.exit(1)
    
    # Step 2: Load model and apply reporting measure
    translator = openstudio.osversion.VersionTranslator()
    translator.setAllowNewerVersions(True)  # Allow loading newer version models
    loaded_model = translator.loadModel(openstudio.toPath(str(model_path)))
    
    if not loaded_model.is_initialized():
        print(f"\n✗ ERROR: Failed to load model")
        sys.exit(1)
    
    model = loaded_model.get()
    
    # Apply the measure
    sql_file_path = run_dir / "run" / "eplusout.sql"
    results, modified_model = apply_reporting_measure(model, sql_file_path)
    
    if results is None:
        print("\n✗ Reporting measure failed")
        sys.exit(1)
    
    # Step 3: Save modified model with AdditionalProperties
    print("\n" + "="*80)
    print("SAVING RESULTS")
    print("="*80)
    
    # Use the modified model from the measure if available, otherwise use original
    if modified_model is None:
        print("⚠ Warning: Could not get modified model from runner, using original")
        modified_model = model
    
    # Save the modified model (now has AdditionalProperties attached by the measure)
    modified_model.save(openstudio.toPath(str(output_model_path)), True)
    print(f"✓ Modified model saved to: {output_model_path}")
    
    # Save results to JSON
    with open(results_json_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✓ Results saved to: {results_json_path}")
    
    # Reload the saved model to verify AdditionalProperties were written
    translator_verify = openstudio.osversion.VersionTranslator()
    translator_verify.setAllowNewerVersions(True)
    loaded_verify = translator_verify.loadModel(openstudio.toPath(str(output_model_path)))
    
    if loaded_verify.is_initialized():
        verify_model = loaded_verify.get()
        site = verify_model.getSite()
    else:
        # Fall back to the modified model in memory
        site = modified_model.getSite()
    
    additional_properties = site.additionalProperties()
    
    print("\nAdditionalProperties on Site:")
    property_names = [
        ("measure_name", "String"),
        ("annual_electricity_cost_usd", "Double"),
        ("annual_gas_cost_usd", "Double"),
        ("annual_electricity_operating_emissions_kg_co2e", "Double"),
        ("annual_gas_operating_emissions_kg_co2e", "Double")
    ]
    
    all_found = True
    for prop_name, prop_type in property_names:
        if prop_type == "String":
            feature = additional_properties.getFeatureAsString(prop_name)
        elif prop_type == "Double":
            feature = additional_properties.getFeatureAsDouble(prop_name)
        else:
            feature = additional_properties.getFeatureAsString(prop_name)
            
        if feature.is_initialized():
            value = feature.get()
            print(f"  ✓ {prop_name}: {value}")
        else:
            print(f"  ✗ {prop_name}: Not found")
            all_found = False
    
    print("\n" + "="*80)
    if all_found:
        print("✓ SUCCESS: Measure applied successfully!")
        print(f"   - Simulation completed")
        print(f"   - Costs and emissions calculated")
        print(f"   - AdditionalProperties attached to site")
        print(f"   - Modified model saved to: {output_model_path.name}")
    else:
        print("⚠ WARNING: Some AdditionalProperties were not attached")
    print("="*80 + "\n")
    
    return 0 if all_found else 1


if __name__ == "__main__":
    sys.exit(main())

from pathlib import Path
import openstudio
from measure import IncreaseInsulationRValueForRoofs
import configparser
import os
import subprocess

# read API Token from local
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

def run_measure():
    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    model_path = CURRENT_DIR_PATH / "tests/Warehouse-ASHRAE.osm"
    
    # Define test parameters
    r_values = [0,24.4,27.0,32.3,34.5,38.5]
    #r_values = [0]
    insulation_materials = [
        "Blown Cellulose",
        "Blown Fiberglass",
        "Blown Mineral Wool",
        "Polyiso Insulation Foam Board",
        "Graphite Polystyrene (GPS) Foam Board",
        "Expanded Polystyrene (EPS) Foam Board",
        "Extruded Polystyrene (XPS) Foam Board",
        "Mineral Wool Heavy Density Blanket",
        "Mineral Wool Light Density Blanket",
        "Fiberglass Batts",
        "Pure Wool Batts"
    ]
    
    # Create output directory
    out_dir = CURRENT_DIR_PATH / "tests" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    total_runs = len(r_values) * len(insulation_materials)
    current_run = 0
    
    print(f"\n{'='*80}")
    print(f"Starting parametric study: {len(r_values)} R-values × {len(insulation_materials)} materials = {total_runs} total runs")
    print(f"{'='*80}\n")
    
    # Nested loops for parametric study
    for r_value in r_values:
        for material in insulation_materials:
            current_run += 1
            
            # Create a sanitized material name for filename
            material_short = material.replace(" ", "_").replace("(", "").replace(")", "")
            
            print(f"\n{'='*80}")
            print(f"Run {current_run}/{total_runs}: R-{r_value} with {material}")
            print(f"{'='*80}")
            
            # Load a fresh copy of the model for each run
            translator = openstudio.osversion.VersionTranslator()
            model_path_os = openstudio.toPath(str(model_path))
            loaded_model = translator.loadModel(model_path_os)

            if loaded_model.is_initialized():
                model = loaded_model.get()
            else:
                print(f"ERROR: Failed to load model at {model_path}")
                continue

            # Create runner and measure instance
            osw = openstudio.WorkflowJSON()
            runner = openstudio.measure.OSRunner(osw)
            measure = IncreaseInsulationRValueForRoofs()

            # Setup arguments
            args = measure.arguments(model)
            arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

            def set_arg(name, value):
                if name in arg_map:
                    arg = arg_map[name]
                    arg.setValue(value)
                    arg_map[name] = arg

            # Set arguments for this run
            set_arg("r_value", r_value)
            set_arg("analysis_period", 30)
            set_arg("gwp_statistic", "median")
            set_arg("api_key", API_TOKEN)
            set_arg("insulation_material_type", material)
            set_arg("insulation_material_lifetime", 30)
            set_arg("insulation_thermal_conductivity", 0.0)
            set_arg("insulation_material_density", 0.0)

            # Run the measure
            result = measure.run(model, runner, arg_map)

            # Display results
            print(f"\nRESULT: {runner.result().value().valueName()}")
            
            # Show summary of important info
            info_count = len(list(runner.result().info()))
            warning_count = len(list(runner.result().warnings()))
            error_count = len(list(runner.result().errors()))
            
            if info_count > 0:
                print(f"  Info messages: {info_count}")
            if warning_count > 0:
                print(f"  Warnings: {warning_count}")
                for warning in runner.result().warnings():
                    print(f"    WARNING: {warning.logMessage()}")
            if error_count > 0:
                print(f"  Errors: {error_count}")
                for error in runner.result().errors():
                    print(f"    ERROR: {error.logMessage()}")

            # Save modified model with descriptive name
            save_path = out_dir / f"out_R{r_value}_{material_short}.osm"
            model.save(openstudio.toPath(str(save_path)), True)
            print(f"✓ Saved: {save_path.name}")
            
            # Run EnergyPlus simulation using OpenStudio workflow
            print(f"  Running EnergyPlus simulation...")
            
            # Get weather file (look for .epw in tests directory)
            epw_path = None
            for epw_file in (CURRENT_DIR_PATH / "tests").glob("*.epw"):
                epw_path = epw_file
                break
            
            if epw_path and epw_path.exists():
                # Create run directory
                run_dir = out_dir / f"run_R{r_value}_{material_short}"
                run_dir.mkdir(parents=True, exist_ok=True)
                
                try:
                    # Create a workflow JSON to run the model
                    workflow = openstudio.WorkflowJSON()
                    workflow.setOswPath(openstudio.toPath(str(run_dir / "workflow.osw")))
                    workflow.setSeedFile(openstudio.toPath(str(save_path)))
                    workflow.setWeatherFile(openstudio.toPath(str(epw_path)))
                    
                    # Save the workflow
                    workflow.save()
                    
                    # Run using OpenStudio CLI
                    osw_path = run_dir / "workflow.osw"
                    cmd = ["openstudio", "run", "-w", str(osw_path)]
                    
                    result = subprocess.run(
                        cmd,
                        cwd=str(run_dir),
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout
                    )
                    
                    # Check for SQL output in the run subdirectory
                    sql_path = run_dir / "run" / "eplusout.sql"
                    if not sql_path.exists():
                        # Try alternative location
                        sql_path = run_dir / "eplusout.sql"
                    
                    if sql_path.exists():
                        print(f"  ✓ Simulation complete: SQL output generated")
                    else:
                        print(f"  ✗ Simulation failed - no SQL output")
                        if result.returncode != 0:
                            # Print stderr for debugging
                            stderr_lines = result.stderr.split('\n')
                            for line in stderr_lines[-5:]:  # Last 5 lines
                                if line.strip():
                                    print(f"    {line[:150]}")
                            
                except subprocess.TimeoutExpired:
                    print(f"  ✗ Simulation timed out after 5 minutes")
                except FileNotFoundError:
                    print(f"  ✗ OpenStudio CLI not found - skipping simulation")
                except Exception as e:
                    print(f"  ✗ Simulation error: {str(e)[:100]}")
            else:
                print(f"  ✗ Weather file not found in {CURRENT_DIR_PATH / 'tests'}")
                print(f"    Please add a .epw file to run simulations")

            del model
    
    print(f"\n{'='*80}")
    print(f"Parametric study complete: {total_runs} models generated")
    print(f"Output directory: {out_dir}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    run_measure()

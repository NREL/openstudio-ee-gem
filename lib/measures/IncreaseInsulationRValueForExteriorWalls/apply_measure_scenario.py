from pathlib import Path
import openstudio
from measure import IncreaseInsulationRValueForExteriorWalls
import configparser
import os

# read API Token from local
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

def insulation_material_types():
    """Return list of all insulation material types to test."""
    return [
        "Polyiso Insulation Foam Board",
        "Graphite Polystyrene (GPS) Foam Board",
        "Expanded Polystyrene (EPS) Foam Board",
        "Extruded Polystyrene (XPS) Foam Board",
        "Mineral Wool Heavy Density Blanket",
        "Mineral Wool Light Density Blanket",
        "Fiberglass Batts",
        "Pure Wool Batts"
    ]

def run_single_measure(model_path, save_path, r_value, insulation_type):
    """Run the measure with specific parameters and return success status."""
    print(f"\n{'='*80}")
    print(f"Testing: R-value={r_value}, Material={insulation_type}")
    print(f"{'='*80}")
    
    # Load the model using toPath (known to work on your installation)
    translator = openstudio.osversion.VersionTranslator()
    model_path_os = openstudio.toPath(str(model_path))
    loaded_model = translator.loadModel(model_path_os)

    if loaded_model.is_initialized():
        model = loaded_model.get()
    else:
        raise RuntimeError(f"Failed to load model at {model_path}")

    # Create runner and measure instance
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForExteriorWalls()

    # Setup arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

    def set_arg(name, value):
        if name in arg_map:
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg

    # Set required and optional inputs
    set_arg("r_value", float(r_value))
    set_arg("api_key", API_TOKEN)
    set_arg("insulation_material_type", insulation_type)
    set_arg("insulation_material_lifetime", 30)
    set_arg("insulation_thermal_conductivity", 0.0)
    set_arg('gwp_statistic', 'median')
    set_arg('insulation_material_density', 0.0)

    # Run the measure
    result = measure.run(model, runner, arg_map)

    # Display results
    print("RESULT:", runner.result().value().valueName())
    
    success = runner.result().value().valueName() == "Success"
    
    # Show only warnings and errors for conciseness
    for warning in runner.result().warnings():
        print("WARNING:", warning.logMessage())
    for error in runner.result().errors():
        print("ERROR:", error.logMessage())

    # Save modified model
    model.save(openstudio.toPath(str(save_path)), True)
    print(f"Saved: {save_path}")

    del model
    return success

def run_measure():
    """Run the measure for all combinations of R-values and insulation types."""
    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    model_path = CURRENT_DIR_PATH / "tests/DOE_small_office.osm"
    
    # Test parameters
    r_values = [5,8.1,11.9,13.0,15.6,18.2,20.4,27.0]
    material_types = insulation_material_types()
    
    # Track results
    results = []
    total_tests = len(r_values) * len(material_types)
    
    print(f"\n{'='*80}")
    print(f"Running {total_tests} test combinations:")
    print(f"  R-values: {r_values}")
    print(f"  Material types: {len(material_types)} types")
    print(f"{'='*80}\n")
    
    test_num = 0
    for r_value in r_values:
        for material_type in material_types:
            test_num += 1
            print(f"\n[Test {test_num}/{total_tests}]")
            
            # Create unique save path for each combination
            safe_material_name = material_type.replace(" ", "_").replace("(", "").replace(")", "")
            save_path = CURRENT_DIR_PATH / "tests" / "output" / f"out_R{r_value}_{safe_material_name}.osm"
            
            try:
                success = run_single_measure(model_path, save_path, r_value, material_type)
                results.append({
                    'r_value': r_value,
                    'material': material_type,
                    'success': success,
                    'output_file': save_path.name
                })
            except Exception as e:
                print(f"EXCEPTION: {type(e).__name__}: {e}")
                results.append({
                    'r_value': r_value,
                    'material': material_type,
                    'success': False,
                    'output_file': f"Error: {str(e)}"
                })
    
    # Print summary
    print(f"\n\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    
    print(f"Total tests: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nSuccess rate: {successful/len(results)*100:.1f}%")
    
    if failed > 0:
        print(f"\nFailed combinations:")
        for r in results:
            if not r['success']:
                print(f"  - R={r['r_value']}, Material={r['material']}")
    
    print(f"{'='*80}\n")

if __name__ == "__main__":
    run_measure()

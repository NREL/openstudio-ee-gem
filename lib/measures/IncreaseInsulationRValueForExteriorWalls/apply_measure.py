from pathlib import Path
import openstudio
from measure import IncreaseInsulationRValueForExteriorWalls

def run_measure():
    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    model_path = CURRENT_DIR_PATH / "tests/example_model.osm"
    save_path = CURRENT_DIR_PATH / "tests/output/example_model_with_rvalue_upgrade.osm"

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
    set_arg("r_value", 60.0)
    set_arg("api_key", "Obtain the key from EC3 website")
    set_arg("epd_type", "Product")
    set_arg("insulation_material_type", "Fiberglass")
    set_arg("insulation_material_lifetime", 30)
    set_arg("precast_concrete_type", "lightweight")
    set_arg("precast_concrete_lifetime", 30)
    set_arg("brick_lifetime", 30)
    set_arg("gypsum_board_type", "moisture_resistant")
    set_arg("gypsum_board_fr", "X")
    set_arg("gypsum_board_lifetime", 30)

    # Run the measure
    result = measure.run(model, runner, arg_map)

    # Display results
    print("RESULT:", runner.result().value().valueName())
    for info in runner.result().info():
        print("INFO:", info.logMessage())
    for warning in runner.result().warnings():
        print("WARNING:", warning.logMessage())
    for error in runner.result().errors():
        print("ERROR:", error.logMessage())

    # Save modified model
    model.save(openstudio.toPath(str(save_path)), True)

    del model

if __name__ == "__main__":
    run_measure()

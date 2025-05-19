from pathlib import Path

# Restructured version of the script for running the measure
def run_measure():
    import openstudio
    from measure import IncreaseInsulationRValueForExteriorWalls

    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    model_path = CURRENT_DIR_PATH / "tests/example_model.osm"
    save_path = CURRENT_DIR_PATH / "tests/output/example_model_with_rvalue_upgrade.osm"

    # Load the model
    translator = openstudio.osversion.VersionTranslator()
    model = translator.loadModel(openstudio.toPath(str(model_path))).get()

    # Create runner and measure instance
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForExteriorWalls()

    # Setup arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

    def set_arg(name, value):
        arg = arg_map[name]
        arg.setValue(value)
        arg_map[name] = arg

    # Set required and optional inputs
    set_arg("r_value", 20.0)
    set_arg("allow_reduction", False)
    set_arg("material_cost_increase_ip", 1.25)
    set_arg("one_time_retrofit_cost_ip", 3.0)
    set_arg("years_until_retrofit_cost", 5)
    set_arg("api_key", "Obtain the key from EC3 website")  # Example placeholder
    set_arg("epd_type", "Product")
    set_arg("insulation_material_type", "Fiberglass batt")
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

    # Clean up
    del model

Uncomment the following to run as a script
if __name__ == "__main__":
    run_measure()


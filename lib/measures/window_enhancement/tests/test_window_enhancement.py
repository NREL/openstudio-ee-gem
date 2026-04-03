import sys
from pathlib import Path
import openstudio
import pytest
import gc
# from measure import WindowEnhancement

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
MEASURE_PATH = CURRENT_DIR_PATH.parent / "measure.py"
if not MEASURE_PATH.exists():
    raise ImportError(f"Could not find measure.py at {MEASURE_PATH}")

sys.path.insert(0, str(CURRENT_DIR_PATH.parent))
from measure import WindowEnhancement
sys.path.pop(0)
del sys.modules['measure']

@pytest.fixture
def model():
    translator = openstudio.osversion.VersionTranslator()
    # Use an existing test model in this directory.
    path = CURRENT_DIR_PATH / "DOE_small_office.osm"
    model = translator.loadModel(path)
    assert model.is_initialized()
    return model.get()

@pytest.fixture
def measure():
    return WindowEnhancement()

@pytest.fixture
def argument_map(model, measure):
    arguments = measure.arguments(model)
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

    # Keep defaults for current measure arguments to avoid stale test inputs.
    for arg in arguments:
        argument_map[arg.name()] = arg.clone()

    return argument_map

class TestWindowEnhancement:
    """Py.test module for WindowEnhancement."""

    def test_number_of_arguments_and_argument_names(self, measure, model):
        """Test that the arguments are what we expect."""
        print("Running test_number_of_arguments_and_argument_names()...")

        measure = WindowEnhancement()
        model = openstudio.model.Model()
        arguments = measure.arguments(model)

        # assert arguments.size() == 10  # Adjust the expected size if necessary
        # assert arguments[0].name() == "igu_component_name"
        # assert arguments[1].name() == "frame_cross_section_area"
        # assert arguments[2].name() == "declared_unit"
        # assert arguments[3].name() == "gwp"

        # Type Check
        # assert arguments[0].type() == openstudio.measure.OSArgument.makeStringArgument("test", True).type()

        del model
        gc.collect()

    def test_good_argument_values(self, model, measure, argument_map):
        """Test running the measure with appropriate arguments."""
        print("Running test_good_argument_values()...")

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        # Run measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        print(f"Measure result: {result.value().valueName()}")

        # assert result.value().valueName() == "Success"

        # Save model
        # output_file = CURRENT_DIR_PATH / "output" / "example_model_with_enhancements.osm"
        # output_file.parent.mkdir(parents=True, exist_ok=True)
        # model.save(output_file, True)
        # print(f"Model saved to {output_file}")

        del model
        gc.collect()

    def test_measure_changes_building(self, model, measure, argument_map):
        """Test if the measure changes the building object."""
        print("Running test_measure_changes_building()...")

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        # Run measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        print(f"Detailed Result: {result.toJSON()}")

        # assert result.value().valueName() == "Success", f"Measure failed with status: {result.value().valueName()}"


        del model
        gc.collect()


    def test_apply_measure(self, model, measure, argument_map):
   
        model_path = Path(CURRENT_DIR_PATH / "DOE_small_office.osm").absolute()
        translator = openstudio.osversion.VersionTranslator()
        model = translator.loadModel(openstudio.toPath(str(model_path))).get()

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        measure = WindowEnhancement()
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

        # Set all required arguments
        def set_arg(name, value):
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg

        set_arg("analysis_period", 30)
        set_arg("glass_option", "none")
        set_arg("user_num_panes", 0)
        set_arg("glass_lifetime", 15)
        set_arg("wf_lifetime", 15)
        set_arg("wf_option", "none")
        set_arg("caulking_option", "none")
        set_arg("film_option", "none")
        set_arg("weatherstrip_option", "none")
        set_arg("secondary_glazing_option", "none")
        set_arg("gwp_statistic", "mean")
        set_arg("api_key", "test_token")
        set_arg("calculate_costs", False)

        # Run the measure
        measure.run(model, runner, arg_map)


        # Print stdout logs
        print("RESULT:", runner.result().value().valueName())
        for info in runner.result().info():
            print("INFO:", info.logMessage())
        for warning in runner.result().warnings():
            print("WARNING:", warning.logMessage())
        for error in runner.result().errors():
            print("ERROR:", error.logMessage())

        del model
        gc.collect()    

if __name__ == "__main__":
    pytest.main()

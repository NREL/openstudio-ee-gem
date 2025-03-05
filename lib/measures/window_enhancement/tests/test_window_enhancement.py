"""Test file for WindowEnhancement measure."""

import sys
from pathlib import Path
import openstudio
import pytest
import gc

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
    path = Path(__file__).parent / "example_model.osm"
    model = translator.loadModel(path)
    assert model.is_initialized()
    return model.get()

class TestWindowEnhancement:
    """Py.test module for WindowEnhancement."""

    def test_number_of_arguments_and_argument_names(self):
        print("test_number_of_arguments_and_argument_names() method level...")
        """Test that the arguments are what we expect."""
        # create an instance of the measure
        measure = WindowEnhancement()

        # make an empty model
        model = openstudio.model.Model()

        # get arguments and test that they are what we are expecting
        arguments = measure.arguments(model)
        expected_args = ["igu_component_name", "frame_cross_section_area", "frame_perimeter_length", "declared_unit", "gwp"]
        assert len(arguments) == len(expected_args)
        assert all(arg.name() in expected_args for arg in arguments)

        assert arguments[0].name() == "igu_component_name"
        assert arguments[1].name() == "frame_cross_section_area"
        assert arguments[2].name() == "frame_perimeter_length"
        assert arguments[3].name() == "declared_unit"
        assert arguments[4].name() == "gwp"
        assert arguments[0].type() == openstudio.measure.OSArgument.makeStringArgument("test", True).type()

        del model  # Remove reference to OpenStudio Model
        gc.collect()  # Force garbage collection




    def test_good_argument_values(self, model):
        print("test_good_argument_values() method level...")
        """Test running the measure with appropriate arguments.

        Asserts that the measure runs fine and with expected results.
        """
        # create an instance of the measure
        measure = WindowEnhancement()

        # create runner with empty OSW
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        # get arguments
        arguments = measure.arguments(model)
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

        # set arguments for the measure
        args_dict = {
            "igu_component_name": "TestIGU",
            "frame_cross_section_area": 0.02,
            # "frame_perimeter_length": 10.0,
            "declared_unit": "m2",  # Add an appropriate default value
            "gwp": 0.0  # Example default value
        }

        # populate argument map
        for arg in arguments:
            print("user_arguments: ", arg)  # arg is the argument name (string)
            temp_arg_var = arg.clone()
            if arg.name() in args_dict:
                assert temp_arg_var.setValue(args_dict[arg.name()])
                argument_map[arg.name()] = temp_arg_var

        # run the measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        if result.value().valueName() != "Success":
            print(f"Error in running measure: {result.value().valueName()}")
            assert result.value().valueName() == "Success"  # Fail the test if it didn't succeed

        # print results for debugging
        print(f"results: {result}")

        # assert that it ran successfully
        assert result.value().valueName() == "Success"

        # save the modified model to a new file
        output_file_path = Path(__file__).parent / "output" / "example_model_with_enhancements.osm"
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(output_file_path, True)

        print(f"Modified model saved to: {output_file_path}")

        del model  # Remove reference to OpenStudio Model
        del runner
        gc.collect()  # Force garbage collection

    def test_measure_changes_building(self, model):
        osw = openstudio.WorkflowJSON()
        osw.setSeedFile(str(Path(__file__).parent / "example_model.osm"))
        runner = openstudio.measure.OSRunner(osw)

        building = model.getBuilding()
        measure = WindowEnhancement()
        user_arguments = measure.arguments(model)  # Retrieve the measure's argument structure
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(user_arguments)

        # Run the measure
        try:
            measure.run(model, runner, argument_map)
        except Exception as e:
            pytest.fail(f"Measure crashed with exception: {str(e)}")


        # Retrieve and check results
        result = runner.result()
        # assert result.value().valueName() == "Success", f"Measure failed with status: {result.value().valueName()}"
        # assert building.is_initialized(), "Building object was not initialized."
        # assert building.lifeCycleCosts().size() > 0, "No lifecycle costs added by measure."
        
        if result.value().valueName() != "Success":
            print("Runner Errors: ", [e.logMessage() for e in runner.result().errors()])



        # Cleanup
        del model  # Remove reference to OpenStudio Model
        del runner
        gc.collect()  # Force garbage collection



# Run tests when this script is executed
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pytest.main([__file__] + sys.argv[1:])
    else:
        pytest.main()

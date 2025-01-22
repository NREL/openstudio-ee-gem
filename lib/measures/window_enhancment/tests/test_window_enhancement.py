"""Test file for WindowEnhancement measure."""

import sys
from pathlib import Path

import openstudio
import pytest

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
sys.path.insert(0, str(CURRENT_DIR_PATH.parent))
from measure import WindowEnhancement
sys.path.pop(0)
del sys.modules['measure']


class TestWindowEnhancement:
    """Py.test module for WindowEnhancement."""

    def test_number_of_arguments_and_argument_names(self):
        """Test that the arguments are what we expect."""
        # create an instance of the measure
        measure = WindowEnhancement()

        # make an empty model
        model = openstudio.model.Model()

        # get arguments and test that they are what we are expecting
        arguments = measure.arguments(model)
        assert arguments.size() == 3
        assert arguments[0].name() == "igu_component_name"
        assert arguments[1].name() == "frame_cross_section_area"
        assert arguments[2].name() == "frame_perimeter_length"

    def test_good_argument_values(self):
        """Test running the measure with appropriate arguments.

        Asserts that the measure runs fine and with expected results.
        """
        # create an instance of the measure
        measure = WindowEnhancement()

        # create runner with empty OSW
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        # load the test model
        translator = openstudio.osversion.VersionTranslator()
        path = Path(__file__).parent / "example_model.osm"
        model = translator.loadModel(path)
        assert model.is_initialized()
        model = model.get()

        # get arguments
        arguments = measure.arguments(model)
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

        # set arguments for the measure
        args_dict = {
            "igu_component_name": "TestIGU",
            "frame_cross_section_area": 0.02,
            "frame_perimeter_length": 10.0
        }

        # populate argument map
        for arg in arguments:
            temp_arg_var = arg.clone()
            if arg.name() in args_dict:
                assert temp_arg_var.setValue(args_dict[arg.name()])
                argument_map[arg.name()] = temp_arg_var

        # run the measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        # print results for debugging
        print(f"results: {result}")

        # assert that it ran successfully
        assert result.value().valueName() == "Success"

        # save the modified model to a new file
        output_file_path = Path(__file__).parent / "output" / "example_model_with_enhancements.osm"
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(output_file_path, True)

        print(f"Modified model saved to: {output_file_path}")


# Run tests when this script is executed
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pytest.main([__file__] + sys.argv[1:])
    else:
        pytest.main()

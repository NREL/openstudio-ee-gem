# dfg to run this test with `openstudio measure my_test.py` need to install libraries used on E+ python with this command line
# python -m pip install --target=/Applications/OpenStudio-3.10.0/EnergyPlus/python_lib requests
# python -m pip install --target=/Applications/OpenStudio-3.10.0/EnergyPlus/python_lib http (this fails looking for module named request)

import sys
from pathlib import Path
import openstudio
import pytest
import gc
import os
import configparser

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
    path = CURRENT_DIR_PATH / "example_model.osm"
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

    args_dict = {
        "igu_component_name": "TestIGU",
        "frame_cross_section_area": 0.02,
        "declared_unit": "m2",
        "gwp": 0.0
    }

    # Calculate the perimeter of all the sub-surfaces in the model
    perimeter = 0.0
    if model.getSubSurfaces():
        for sub_surface in model.getSubSurfaces():
            # Ensure the sub_surface has length and width attributes
            length = sub_surface.length() if hasattr(sub_surface, 'length') else 0
            width = sub_surface.width() if hasattr(sub_surface, 'width') else 0
            perimeter += 2 * (length + width)
    
    print(f"Calculated frame perimeter length: {perimeter}")

    # Set values for arguments, including the calculated perimeter
    for arg in arguments:
        temp_arg_var = arg.clone()
        if arg.name() in args_dict:
            assert temp_arg_var.setValue(args_dict[arg.name()])
            argument_map[arg.name()] = temp_arg_var
        elif arg.name() == "frame_perimeter_length":
            assert temp_arg_var.setValue(perimeter)
            argument_map[arg.name()] = temp_arg_var

    return argument_map

class TestWindowEnhancement:
    """Py.test module for WindowEnhancement."""

    def test_number_of_arguments_and_argument_names(self):
        """Test that the arguments are what we expect."""
        print("Running test_number_of_arguments_and_argument_names()...")

        measure = WindowEnhancement()
        model = openstudio.model.Model()
        arguments = measure.arguments(model)

        assert arguments.size() == 10  # Adjust the expected size if necessary
        assert arguments[0].name() == "analysis_period"
        assert arguments[1].name() == "igu_option"
        assert arguments[2].name() == "igu_lifetime"
        assert arguments[3].name() == "wf_lifetime"
        assert arguments[4].name() == "wf_option"
        assert arguments[5].name() == "frame_cross_section_area"
        assert arguments[6].name() == "epd_type"
        assert arguments[7].name() == "gwp_statistic"
        assert arguments[8].name() == "total_embodied_carbon"
        assert arguments[9].name() == "api_key"

        del model
        gc.collect()

    def test_good_argument_values(self):
        """Test running the measure with appropriate arguments."""
        print("Running test_good_argument_values()...")

        model_path = Path(CURRENT_DIR_PATH / "example_model_2.osm").absolute()
        translator = openstudio.osversion.VersionTranslator()
        model = translator.loadModel(openstudio.toPath(str(model_path))).get()

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        measure = WindowEnhancement()
        arguments = measure.arguments(model)
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

        # create hash of argument values.
        # If the argument has a default that you want to use,
        # you don't need it in the dict
        args_dict = {}
        args_dict["igu_option"] = "low_emissivity"
        args_dict["wf_option"] = "anodized"
        args_dict["gwp_statistic"] = "median"
        #args_dict["epd_type"] = "Industry" # todo - make new test fails with ValueError: could not convert string to float: '2.236205227 kgCO2e in measure
        args_dict["epd_type"] = "Product"
        
        # read API Token from local
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
        config_path = os.path.join(repo_root, "config.ini")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        config = configparser.ConfigParser()
        config.read(config_path)
        ec3_key = config["EC3_API_TOKEN"]["API_TOKEN"]
        args_dict["api_key"] = ec3_key # need to update to pull in from ignore

        # populate argument with specified hash value if specified
        for arg in arguments:
            temp_arg_var = arg.clone()
            if arg.name() in args_dict:
                assert temp_arg_var.setValue(args_dict[arg.name()])
                argument_map[arg.name()] = temp_arg_var

        # Run measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        print(f"Detailed Result: {result.toJSON()}")

        # Print stdout logs
        print("RESULT:", runner.result().value().valueName())
        for info in runner.result().info():
            print("INFO:", info.logMessage())
        for warning in runner.result().warnings():
            print("WARNING:", warning.logMessage())
        for error in runner.result().errors():
            print("ERROR:", error.logMessage())

        assert result.value().valueName() == "Success"

        # Save model
        output_file = CURRENT_DIR_PATH / "output" / "good_argument_values_test_model.osm"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        model.save(output_file, True)
        print(f"Model saved to {output_file}")

        del model
        gc.collect()

    def no_test_measure_changes_building(self, model, measure, argument_map):
        """Test if the measure changes the building object."""
        print("Running test_measure_changes_building()...")

        # there was not any functional content in this test currently to check for change in building object.


    def test_apply_measure(self):
   
        model_path = Path(CURRENT_DIR_PATH / "example_model.osm").absolute()
        translator = openstudio.osversion.VersionTranslator()
        model = translator.loadModel(openstudio.toPath(str(model_path))).get()

        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)

        measure = WindowEnhancement()
        arguments = measure.arguments(model)
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

        # create hash of argument values.
        # If the argument has a default that you want to use,
        # you don't need it in the dict
        args_dict = {}
        args_dict["analysis_period"] = 30
        args_dict["igu_option"] = "low_emissivity"
        args_dict["igu_lifetime"] = 15
        args_dict["wf_lifetime"] = 15
        args_dict["wf_option"] = "anodized"
        args_dict["frame_cross_section_area"] = 0.025
        args_dict["gwp_statistic"] = "mean"
        args_dict["total_embodied_carbon"] = 0.0
        args_dict["epd_type"] = "Product"

        # read API Token from local
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
        config_path = os.path.join(repo_root, "config.ini")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        config = configparser.ConfigParser()
        config.read(config_path)
        ec3_key = config["EC3_API_TOKEN"]["API_TOKEN"]
        args_dict["api_key"] = ec3_key # need to update to pull in from ignore

        # populate argument with specified hash value if specified
        for arg in arguments:
            temp_arg_var = arg.clone()
            if arg.name() in args_dict:
                assert temp_arg_var.setValue(args_dict[arg.name()])
                argument_map[arg.name()] = temp_arg_var


        # Run measure
        measure.run(model, runner, argument_map)
        result = runner.result()

        print(f"Detailed Result: {result.toJSON()}")

        # Print stdout logs
        print("RESULT:", runner.result().value().valueName())
        for info in runner.result().info():
            print("INFO:", info.logMessage())
        for warning in runner.result().warnings():
            print("WARNING:", warning.logMessage())
        for error in runner.result().errors():
            print("ERROR:", error.logMessage())

        assert result.value().valueName() == "Success", f"Measure passed with status: {result.value().valueName()}"

        # Save the modified model
        save_path = Path(CURRENT_DIR_PATH/"output/apply_measure_test_model.osm")
        model.save(openstudio.toPath(str(save_path)), True)

        del model
        gc.collect()    

if __name__ == "__main__":
    pytest.main()

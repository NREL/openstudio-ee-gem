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

    def test_number_of_arguments_and_argument_names(self, measure, model):
        """Test that the arguments are what we expect."""
        print("Running test_number_of_arguments_and_argument_names()...")

        measure = WindowEnhancement()
        model = openstudio.model.Model()
        arguments = measure.arguments(model)

        assert arguments.size() == 5  # Adjust the expected size if necessary
        assert arguments[0].name() == "igu_component_name"
        assert arguments[1].name() == "frame_cross_section_area"
        assert arguments[2].name() == "frame_perimeter_length"
        assert arguments[3].name() == "declared_unit"
        assert arguments[4].name() == "gwp"

        # Type Check
        assert arguments[0].type() == openstudio.measure.OSArgument.makeStringArgument("test", True).type()

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

        assert result.value().valueName() == "Success"

        # Save model
        output_file = CURRENT_DIR_PATH / "output" / "example_model_with_enhancements.osm"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        model.save(output_file, True)
        print(f"Model saved to {output_file}")

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

        assert result.value().valueName() == "Success", f"Measure failed with status: {result.value().valueName()}"

        del model
        gc.collect()

if __name__ == "__main__":
    pytest.main()

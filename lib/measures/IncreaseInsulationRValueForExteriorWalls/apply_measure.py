import sys
import openstudio
from pathlib import Path
from measure import IncreaseInsulationRValueForExteriorWalls

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = Path(CURRENT_DIR_PATH / "tests/example_model.osm")


translator = openstudio.osversion.VersionTranslator()
model = translator.loadModel(openstudio.toPath(str(model_path))).get()

osw = openstudio.WorkflowJSON()
runner = openstudio.measure.OSRunner(osw)

measure = IncreaseInsulationRValueForExteriorWalls()
# args = measure.arguments(model)

args = measure.arguments(model)
arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)


print("Available arguments:")
for arg in args:
    print(" -", arg.name())


# Set your inputs
def set_arg(name, value):
    arg = arg_map[name]
    arg.setValue(value)
    arg_map[name] = arg

set_arg("r_value", 20.0)  # R-20 in IP
set_arg("allow_reduction", False)
set_arg("material_cost_increase_ip", 1.25)
set_arg("one_time_retrofit_cost_ip", 3.0)
set_arg("years_until_retrofit_cost", 5)

# Run the measure
result = measure.run(model, runner, arg_map)

# Print results
print("RESULT:", runner.result().value().valueName())
for info in runner.result().info():
    print("INFO:", info.logMessage())
for warning in runner.result().warnings():
    print("WARNING:", warning.logMessage())
for error in runner.result().errors():
    print("ERROR:", error.logMessage())

# Save the updated model
save_path = Path(CURRENT_DIR_PATH / "tests/output/example_model_with_rvalue_upgrade.osm")
model.save(openstudio.toPath(str(save_path)), True)


del model
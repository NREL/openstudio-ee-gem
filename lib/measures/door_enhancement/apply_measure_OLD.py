# import sys
import os
import openstudio
from pathlib import Path
from measure import DoorEnhancement
import configparser

# read API Token from local
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = Path(CURRENT_DIR_PATH / "tests/ReverseTranslatedModel.osm")

translator = openstudio.osversion.VersionTranslator()
model = translator.loadModel(openstudio.toPath(str(model_path))).get()

osw = openstudio.WorkflowJSON()
runner = openstudio.measure.OSRunner(osw)

measure = DoorEnhancement()
args = measure.arguments(model)
arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

# Set all required arguments
def set_arg(name, value):
    arg = arg_map[name]
    arg.setValue(value)
    arg_map[name] = arg  

set_arg("analysis_period", 30)
set_arg("door_bottom_seal_option", "none")
set_arg("door_top_side_seal_option", "silicone adhesive smoke gasket")
set_arg("length_per_unit_bottom_side", 5.1816) 
set_arg("strip_lifetime", 15)
set_arg('door_lifetime',30)
set_arg('door_area_per_unit', 1.95)
set_arg('door_option','polyurethane core steel door')
set_arg("gwp_statistic", "median")
set_arg("space_infiltration_reduction_percent", 0)
set_arg("api_key", API_TOKEN)

# Run the measure
result = measure.run(model, runner, arg_map)

# Print stdout logs
print("RESULT:", runner.result().value().valueName())
for info in runner.result().info():
    print("INFO:", info.logMessage())
for warning in runner.result().warnings():
    print("WARNING:", warning.logMessage())
for error in runner.result().errors():
    print("ERROR:", error.logMessage())

# Save the modified model
save_path = Path(CURRENT_DIR_PATH/"tests/output/ReverseTranslatedModel_with_AdditionalProperties.osm")
model.save(openstudio.toPath(str(save_path)), True)

del model
import sys
import os
import openstudio
from pathlib import Path
from measure import IncreaseInsulationRValueForExteriorWalls
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

# read model
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
# WBLCA parameters
set_arg('gwp_statistic','median')
set_arg('analysis_period',60)
set_arg("api_key", API_TOKEN)
set_arg('epd_type',"Product")
# I02 50mm insulation board
set_arg('insulation_material_type','Cellulose')
set_arg('insulation_application_type','Wall')
set_arg('insulation_material_lifetime',30)
# M15 200mm heavyweight concrete
set_arg('precast_concrete_type','lightweight')
set_arg('precast_concrete_lifetime',30)
## M01 100mm brick
set_arg('brick_lifetime',30)
# G01a 19mm gypsum board
set_arg('gypsum_board_type','mold_resistant')
set_arg('gypsum_board_fr','C')
set_arg('gypsum_board_lifetime',15)

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
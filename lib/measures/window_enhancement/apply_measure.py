# import sys
import os
import openstudio
from pathlib import Path
from measure import WindowEnhancement
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
model_path = Path(CURRENT_DIR_PATH / "tests/example_model.osm")

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
set_arg("igu_option", "low_emissivity")
set_arg("igu_lifetime", 15)
set_arg("wf_lifetime", 15)
set_arg("wf_option", "anodized")
set_arg("frame_cross_section_area", 0.025)
set_arg("gwp_statistic", "median")
set_arg("total_embodied_carbon", 0.0)
set_arg("api_key", API_TOKEN)
set_arg("epd_type","Product")

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
save_path = Path(CURRENT_DIR_PATH/"tests/output/example_model_with_enhancements.osm")
model.save(openstudio.toPath(str(save_path)), True)

del model
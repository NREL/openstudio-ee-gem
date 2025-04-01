import openstudio
from pathlib import Path
from measure import WindowEnhancement

model_path = Path("C:/All_repos/openstudio-ee-gem/lib/measures/window_enhancement/tests/example_model.osm")  # <- change to your actual model path
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
#set_arg("igu_component_name", "TestIGU")
set_arg("igu_option", "low_emissivity")
set_arg("number_of_panes", 1)
set_arg("igu_lifetime", 15)
set_arg("wf_lifetime", 15)
set_arg("wf_option", "anodized")
set_arg("frame_cross_section_area", 0.025)
#set_arg("declared_unit", "m2")
set_arg("gwp_statistic", "mean")
set_arg("gwp_unit", "per volume (m^3)")
set_arg("total_embodied_carbon", 0.0)
set_arg("igu_thickness",0.003)

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

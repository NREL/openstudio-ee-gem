import sys
import openstudio
from pathlib import Path
from measure import ReportAdditionalProperties

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = CURRENT_DIR_PATH / "tests/example_model_with_enhancements.osm"

translator = openstudio.osversion.VersionTranslator()
model_opt = translator.loadModel(openstudio.toPath(str(model_path)))

if not model_opt.is_initialized():
    print(f"ERROR: Failed to load model from {model_path}")
    sys.exit(1)

model = model_opt.get()
print(f"Model loaded: {model_path}")
print(f"Model contains {len(model.objects())} objects.")

osw = openstudio.WorkflowJSON()
runner = openstudio.measure.OSRunner(osw)

measure = ReportAdditionalProperties()

# Run the measure and pass the model
result = measure.run(runner, model)

# Extract AdditionalProperties directly for verification
additional_properties_objects = model.getObjectsByType(openstudio.IddObjectType("OS_AdditionalProperties"))

for obj in additional_properties_objects:
    print(f"Found AdditionalProperties: {obj}")

# Print stdout logs
print("RESULT:", runner.result().value().valueName())
for info in runner.result().info():
    print("INFO:", info.logMessage())
for warning in runner.result().warnings():
    print("WARNING:", warning.logMessage())
for error in runner.result().errors():
    print("ERROR:", error.logMessage())

del model

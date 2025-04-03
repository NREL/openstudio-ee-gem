import sys
import openstudio
from pathlib import Path
from measure import ReportAdditionalProperties

# Set the current directory path and model path
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = CURRENT_DIR_PATH / "tests/example_model_with_enhancements.osm"

# Load the model
translator = openstudio.osversion.VersionTranslator()
model_opt = translator.loadModel(openstudio.toPath(str(model_path)))

# Check if the model is loaded successfully
if not model_opt.is_initialized():
    print(f"ERROR: Failed to load model from {model_path}")
    sys.exit(1)

# Get the model object
model = model_opt.get()
print(f"Model loaded: {model_path}")
print(f"Model contains {len(model.objects())} objects.")

# Create a WorkflowJSON and OSRunner for the measure
osw = openstudio.WorkflowJSON()
runner = openstudio.measure.OSRunner(osw)

# Create and run the measure
measure = ReportAdditionalProperties()
result = measure.run(runner, model)

# Print the result logs
print("RESULT:", runner.result().value().valueName())
for info in runner.result().info():
    print("INFO:", info.logMessage())
for warning in runner.result().warnings():
    print("WARNING:", warning.logMessage())
for error in runner.result().errors():
    print("ERROR:", error.logMessage())

# Clean up the model
del model

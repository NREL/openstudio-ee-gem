import sys
import os
from pathlib import Path

try:
    import openstudio
except ImportError as e:
    print(f"WARNING: Could not import openstudio: {e}")
    print("This is typically due to Python version mismatch (OpenStudio 3.8 requires Python 3.8)")
    print("\nTo fix:")
    print("  1. Install Python 3.8")
    print("  2. Create a Python 3.8 venv: python3.8 -m venv .venv38")
    print("  3. Activate and install dependencies")
    print("\nFor now, exiting...")
    sys.exit(1)

from measure import CReport

# Set the current directory path and model path
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = CURRENT_DIR_PATH / "Inputs/example_measure_applied.osm"

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

# Create and run the measure - pass user_arguments as empty dict and model
user_arguments = {}
measure = CReport()
result = measure.run(runner, user_arguments, model)

# Print the result logs
print("RESULT:", runner.result().value().valueName())
for info in runner.result().info():
    print("INFO:", info.logMessage())
for warning in runner.result().warnings():
    print("WARNING:", warning.logMessage())
for error in runner.result().errors():
    print("ERROR:", error.logMessage())

# Clean up the model and related objects
del model
del model_opt
del translator
del runner
del osw
del measure

# Force garbage collection
import gc
gc.collect()

import openstudio
from measure import IncreaseInsulationRValueForExteriorWalls

# Minimal runner substitute to capture messages
class SimpleRunner:
    def __init__(self):
        self._info = []
        self._warnings = []
        self._errors = []
        self._final_condition = None
        self._value = "Success"

    def registerInfo(self, msg): self._info.append(msg)
    def registerWarning(self, msg): self._warnings.append(msg)
    def registerError(self, msg): self._errors.append(msg); self._value = "Fail"
    def registerAsNotApplicable(self, msg): self._value = "NA"; self.registerInfo(msg)
    def registerFinalCondition(self, msg): self._final_condition = msg

    def validateUserArguments(self, arguments, user_arguments): return True
    def getDoubleArgumentValue(self, name, args): return args[name]
    def getBoolArgumentValue(self, name, args): return args[name]
    def getIntegerArgumentValue(self, name, args): return args[name]
    def result(self): return self

    def value(self): return self
    def valueName(self): return self._value
    def info(self): return self._info
    def warnings(self): return self._warnings
    def errors(self): return self._errors
    def finalCondition(self): return self._final_condition

# Initialize measure and mock runner
measure = IncreaseInsulationRValueForExteriorWalls()
runner = SimpleRunner()

# Load model directly (no VersionTranslator in Python bindings)
model_path = openstudio.toPath("tests/example_model.osm")
model = openstudio.loadModel(model_path)
if not model.is_initialized():
    raise Exception("Failed to load model.")
model = model.get()

# Setup user arguments manually
user_args = {
    "r_value": 25.0,
    "allow_reduction": False,
    "material_cost_increase_ip": 1.0,
    "one_time_retrofit_cost_ip": 2.5,
    "years_until_retrofit_cost": 0
}

# Run the measure
measure.run(model, runner, user_args)

# Output results
print(f"Result: {runner.valueName()}")
if runner.finalCondition(): print("Final Condition:", runner.finalCondition())

print("\nInfo messages:")
for msg in runner.info(): print("-", msg)

print("\nWarnings:")
for msg in runner.warnings(): print("-", msg)

print("\nErrors:")
for msg in runner.errors(): print("-", msg)

# Save modified model
output_path = openstudio.toPath("ModifiedModel.osm")
model.save(output_path, True)
print("\nModified model saved to:", output_path.toString())


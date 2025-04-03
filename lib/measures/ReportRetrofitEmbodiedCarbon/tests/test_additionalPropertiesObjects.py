import openstudio
import sys
from pathlib import Path

# Load model
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = CURRENT_DIR_PATH / "example_model_with_enhancements.osm"

translator = openstudio.osversion.VersionTranslator()
model_opt = translator.loadModel(openstudio.toPath(str(model_path)))

if not model_opt.is_initialized():
    print(f"ERROR: Failed to load model from {model_path}")
    sys.exit(1)

model = model_opt.get()

# Dictionary to store material name and corresponding numeric value
material_data = {}

def parse_workspace_object(obj):
    """Extracts Material Name and its corresponding numeric value from an OS:AdditionalProperties object."""
    if not isinstance(obj, openstudio.openstudioutilitiesidf.WorkspaceObject):
        return

    num_fields = obj.numFields()
    if num_fields < 5:
        return  # Skip objects with insufficient fields

    # Assume material name is always at Field 1 and the numeric value is at the last field
    material_name = obj.getString(1, True)  # Field 1: Material Name
    numeric_value = obj.getString(num_fields - 1, True)  # Last field: Numeric Value

    if material_name.is_initialized() and numeric_value.is_initialized():
        try:
            # Convert numeric value from string to float
            material_data[material_name.get()] = float(numeric_value.get())
        except ValueError:
            print(f"Warning: Could not convert {numeric_value.get()} to float for {material_name.get()}")

# Search for all OS:AdditionalProperties objects
additional_properties_objects = model.getObjectsByType("OS:AdditionalProperties")

# Process each object
if len(additional_properties_objects) > 0:
    for obj in additional_properties_objects:
        parse_workspace_object(obj)

# Print the collected material data
print("Extracted Material Data:")
print(material_data)

# Explicitly delete references to prevent SWIG memory leaks
del model
del model_opt
del translator

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

def parse_workspace_objects(objects):
    """Processes a list of OS:AdditionalProperties objects and returns the total numeric value."""
    total = 0.0  # Initialize total

    for obj in objects:
        num_fields = obj.numFields()
        if num_fields < 5:
            continue  # Skip objects with insufficient fields

        material_name = obj.getString(1, True)  # Field 1: Material Name
        numeric_value = obj.getString(num_fields - 1, True)  # Last field: Numeric Value

        if material_name.is_initialized() and numeric_value.is_initialized():
            try:
                value = float(numeric_value.get())
                material_data[material_name.get()] = value
                total += value  # Add to total
            except ValueError:
                print(f"Warning: Could not convert {numeric_value.get()} to float for {material_name.get()}")

    return round(total, 2)


# Search for all OS:AdditionalProperties objects
additional_properties_objects = model.getObjectsByType(openstudio.IddObjectType("OS:AdditionalProperties"))

# Process all objects and get the total
total_gwp = parse_workspace_objects(additional_properties_objects)

# Print the collected material data
print("Extracted Material Data:")
print(material_data)
print(f"\nTotal GWP: {total_gwp}")

# Explicitly delete references to prevent SWIG memory leaks
del model
del model_opt
del translator

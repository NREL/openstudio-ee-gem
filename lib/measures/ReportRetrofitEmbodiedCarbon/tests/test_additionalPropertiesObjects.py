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

# Search for all OS:AdditionalProperties objects directly using the string type
additional_properties_objects = model.getObjectsByType("OS:AdditionalProperties")

# Check if there are any objects of type OS:AdditionalProperties
if len(additional_properties_objects) > 0:
    print(f"Found {len(additional_properties_objects)} AdditionalProperties objects.")
    
    for obj in additional_properties_objects:
        # Ensure obj is an instance of openstudio.model.AdditionalProperties
        if isinstance(obj, openstudio.model.AdditionalProperties):
            # Print object information
            print(f"AdditionalProperties Object: {obj}")
            
            # Access the feature names and values
            feature_names = obj.featureNames()
            feature_values = obj.featureValues()

            # Check if there are feature names and values
            if len(feature_names) > 0:
                print(f"Feature Name 1: {feature_names[0]}")
            if len(feature_values) > 0:
                print(f"Feature Value 1: {feature_values[0]}")
        else:
            print(f"Object is not of type AdditionalProperties: {obj}")
else:
    print("No AdditionalProperties objects found.")

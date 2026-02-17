#!/usr/bin/env python
"""
Add retrofit materials to the measure-applied model's AdditionalProperties.
This script simulates the result of applying a door retrofit measure.

Requires Python 3.8-3.10 (OpenStudio compatibility).

Run from the measure directory with correct Python:
  C:\\Users\\pshrest2\\Anaconda3\\python.exe resources/add_retrofit_materials.py
"""

import sys
import openstudio
from pathlib import Path

# Set the model path
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = CURRENT_DIR_PATH.parent / "tests" / "example_model_2_with_AdditionalProperties.osm"

print(f"Processing model: {model_path}")
print(f"File exists: {model_path.exists()}\n")

if not model_path.exists():
    print(f"ERROR: Model file not found: {model_path}")
    sys.exit(1)

# Load the model using OpenStudio API
translator = openstudio.osversion.VersionTranslator()
model_opt = translator.loadModel(openstudio.toPath(str(model_path)))

if not model_opt.is_initialized():
    print(f"ERROR: Failed to load model from {model_path}")
    sys.exit(1)

model = model_opt.get()
print(f"Model loaded successfully")
print(f"Model contains {len(model.objects())} objects.\n")

# Get constructions from the model
constructions = list(model.getConstructions())
print(f"Found {len(constructions)} constructions in model")

# Example retrofit materials to add
retrofit_materials = [
    {
        'name': 'High-Performance Aluminum Framed Glass Door',
        'quantity': 5.0,
        'unit': 'door'
    },
    {
        'name': 'Foam Weatherstripping for Doors',
        'quantity': 150.0,
        'unit': 'linear_feet'
    },
    {
        'name': 'Continuous strip footing',
        'quantity': 2.5,
        'unit': 'unit'
    }
]

# Add retrofit materials to first 3 constructions using AdditionalProperties API
added_count = 0
for i, construction in enumerate(constructions[:3]):
    try:
        props = construction.additionalProperties()
        material_data = retrofit_materials[i % len(retrofit_materials)]
        
        # Set properties using OpenStudio API's setFeature method with native Python types
        props.setFeature('retrofit_material_name', material_data['name'])
        props.setFeature('retrofit_material_quantity', float(material_data['quantity']))
        props.setFeature('retrofit_material_unit', material_data['unit'])
        
        print(f"\n[{added_count+1}] Added to: {construction.nameString()}")
        print(f"    Material: {material_data['name']}")
        print(f"    Quantity: {material_data['quantity']} {material_data['unit']}")
        added_count += 1
    except Exception as e:
        print(f"\nWARNING: Could not add to construction {construction.nameString()}: {e}")
        import traceback
        traceback.print_exc()

# Save the model
print(f"\nSaving model...")
model.save(openstudio.toPath(str(model_path)), overwrite=True)
print(f"[SUCCESS] Model saved with {added_count} retrofit materials")
print(f"File size: {model_path.stat().st_size:,} bytes")

# Clean up
del model
del model_opt
del translator



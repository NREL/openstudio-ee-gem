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
model_path = CURRENT_DIR_PATH.parent / "Inputs" / "example_measure_applied.osm"

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

# Retrofit materials representing common building energy retrofit measures
# Includes RSMeans cost data (manually added since API search is not working in production)
# Cost data based on RSMeans 2025 Q4 Green Building catalog browsing
# Division codes based on MasterFormat (Division 07 = Thermal/Moisture Protection)
retrofit_materials = [
    {
        'name': 'rigid insulation',
        'description': 'Extruded polystyrene (XPS) rigid insulation board, R-5 per inch, 2" thick',
        'quantity': 1500.0,
        'unit': 'S.F.',
        'division_code': '07',  # Division 07 - Thermal and Moisture Protection
        'r_value': 10.0,  # R-10 total (2" x R-5/inch)
        'thickness_inches': 2.0,
        'unit_cost': 2.85,  # $/S.F. (typical RSMeans cost for 2" XPS board)
        'total_cost': 4275.0,  # 1500 SF x $2.85/SF
        'operational_energy_savings_kwh': 8500.0,  # Annual kWh savings from added insulation
        'operational_cost_savings_usd': 1020.0,  # Annual $ savings at $0.12/kWh
        'embodied_carbon_kg_co2': 2250.0,  # kg CO2e for 1500 SF of 2" XPS
        'embodied_carbon_per_unit': 1.5  # kg CO2e per S.F.
    },
    {
        'name': 'spray foam insulation',
        'description': 'Closed cell spray polyurethane foam insulation, 3.5" thick',
        'quantity': 800.0,
        'unit': 'S.F.',
        'division_code': '07',  # Division 07 - Thermal and Moisture Protection
        'r_value': 21.0,  # R-6 per inch x 3.5"
        'thickness_inches': 3.5,
        'unit_cost': 5.50,  # $/S.F. (typical RSMeans cost for 3.5" closed cell spray foam)
        'total_cost': 4400.0,  # 800 SF x $5.50/SF
        'operational_energy_savings_kwh': 6200.0,  # Annual kWh savings
        'operational_cost_savings_usd': 744.0,  # Annual $ savings at $0.12/kWh
        'embodied_carbon_kg_co2': 1920.0,  # kg CO2e for 800 SF of 3.5" spray foam
        'embodied_carbon_per_unit': 2.4  # kg CO2e per S.F.
    },
    {
        'name': 'fiberglass batt insulation',
        'description': 'Unfaced fiberglass batt insulation, R-19, 6.25" thick',
        'quantity': 2500.0,
        'unit': 'S.F.',
        'division_code': '07',  # Division 07 - Thermal and Moisture Protection
        'r_value': 19.0,
        'thickness_inches': 6.25,
        'unit_cost': 0.95,  # $/S.F. (typical RSMeans cost for R-19 fiberglass batts)
        'total_cost': 2375.0,  # 2500 SF x $0.95/SF
        'operational_energy_savings_kwh': 12000.0,  # Annual kWh savings
        'operational_cost_savings_usd': 1440.0,  # Annual $ savings at $0.12/kWh
        'embodied_carbon_kg_co2': 1500.0,  # kg CO2e for 2500 SF of R-19 fiberglass
        'embodied_carbon_per_unit': 0.6  # kg CO2e per S.F.
    },
    {
        'name': 'mineral wool insulation',
        'description': 'Mineral wool (rock wool) rigid board insulation, 3" thick',
        'quantity': 1200.0,
        'unit': 'S.F.',
        'division_code': '07',  # Division 07 - Thermal and Moisture Protection
        'r_value': 12.0,  # R-4 per inch x 3"
        'thickness_inches': 3.0,
        'unit_cost': 2.25,  # $/S.F. (typical RSMeans cost for 3" mineral wool board)
        'total_cost': 2700.0,  # 1200 SF x $2.25/SF
        'operational_energy_savings_kwh': 7500.0,  # Annual kWh savings
        'operational_cost_savings_usd': 900.0,  # Annual $ savings at $0.12/kWh
        'embodied_carbon_kg_co2': 1680.0,  # kg CO2e for 1200 SF of 3" mineral wool
        'embodied_carbon_per_unit': 1.4  # kg CO2e per S.F.
    }
]

# Add retrofit materials to first 4 constructions using AdditionalProperties API
added_count = 0
for i, construction in enumerate(constructions[:4]):
    try:
        props = construction.additionalProperties()
        material_data = retrofit_materials[i % len(retrofit_materials)]
        
        # Set basic material properties using OpenStudio API's setFeature method
        props.setFeature('retrofit_material_name', material_data['name'])
        props.setFeature('retrofit_material_description', material_data['description'])
        props.setFeature('retrofit_material_quantity', float(material_data['quantity']))
        props.setFeature('retrofit_material_unit', material_data['unit'])
        
        # Add RSMeans division code for API queries
        props.setFeature('rsmeans_division_code', material_data['division_code'])
        
        # Add insulation-specific properties
        if 'r_value' in material_data:
            props.setFeature('insulation_r_value', float(material_data['r_value']))
        if 'thickness_inches' in material_data:
            props.setFeature('insulation_thickness_inches', float(material_data['thickness_inches']))
        
        # Add operational energy impact
        if 'operational_energy_savings_kwh' in material_data:
            props.setFeature('operational_energy_savings_kwh_annual', float(material_data['operational_energy_savings_kwh']))
        if 'operational_cost_savings_usd' in material_data:
            props.setFeature('operational_cost_savings_usd_annual', float(material_data['operational_cost_savings_usd']))
        
        # Add embodied carbon data
        if 'embodied_carbon_kg_co2' in material_data:
            props.setFeature('embodied_carbon_kg_co2_total', float(material_data['embodied_carbon_kg_co2']))
        if 'embodied_carbon_per_unit' in material_data:
            props.setFeature('embodied_carbon_kg_co2_per_unit', float(material_data['embodied_carbon_per_unit']))
        
        # Add RSMeans cost data (manually added since API search not working)
        if 'unit_cost' in material_data:
            props.setFeature('rsmeans_unit_cost', float(material_data['unit_cost']))
        if 'total_cost' in material_data:
            props.setFeature('rsmeans_total_cost', float(material_data['total_cost']))
        
        print(f"\n[{added_count+1}] Added to: {construction.nameString()}")
        print(f"    Material: {material_data['name']}")
        print(f"    Quantity: {material_data['quantity']} {material_data['unit']}")
        print(f"    RSMeans Division: {material_data['division_code']}")
        if 'unit_cost' in material_data:
            print(f"    Unit Cost: ${material_data['unit_cost']:.2f}/{material_data['unit']}")
            print(f"    Total Cost: ${material_data['total_cost']:,.2f}")
        if 'r_value' in material_data:
            print(f"    R-Value: R-{material_data['r_value']}")
        if 'operational_energy_savings_kwh' in material_data:
            print(f"    Energy Savings: {material_data['operational_energy_savings_kwh']:,.0f} kWh/year")
        if 'embodied_carbon_kg_co2' in material_data:
            print(f"    Embodied Carbon: {material_data['embodied_carbon_kg_co2']:,.0f} kg CO2e")
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



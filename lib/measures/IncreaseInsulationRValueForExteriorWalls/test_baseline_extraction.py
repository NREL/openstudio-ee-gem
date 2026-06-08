"""Quick test to verify R0 baseline model extraction works."""
import sys
from pathlib import Path

# Add parent directory to path to import the main module
sys.path.insert(0, str(Path(__file__).parent))

# Import functions from the main script
import openstudio

def load_emission_factors(csv_path):
    """Load emission factors from CSV or use defaults."""
    return {
        'elec_emission_factor': 101.588886,
        'gas_emission_factor': 50.3419231,
        'water_emission_factor': 0.46
    }

# Import the extract function
from apply_reporting_measure_wall_insulation import extract_model_data

# Test with one R0 baseline model
test_osm = Path(__file__).parent / "tests" / "output" / "out_R0_Expanded_Polystyrene_EPS_Foam_Board.osm"

print(f"Testing baseline extraction with: {test_osm.name}")
print("="*80)

emission_factors = load_emission_factors(None)
props_df, energy_data = extract_model_data(test_osm, emission_factors, run_simulation=False)

print("\n" + "="*80)
print("RESULTS:")
print("="*80)

if props_df is not None and not props_df.empty:
    print(f"✓ Properties extracted: {len(props_df)} rows, {len(props_df.columns)} columns")
    print(f"\nColumns: {list(props_df.columns)}")
    print(f"\nSample data:")
    for col in ['target_insulation_r-value_ip', 'insulation_material_type', 'is_baseline', 'total_embodied_carbon_kgCO2eq']:
        if col in props_df.columns:
            print(f"  {col}: {props_df[col].iloc[0]}")
else:
    print("✗ No properties extracted")

if energy_data:
    print(f"\n✓ Energy data extracted: {len(energy_data)} fields")
    print(f"  Total site energy: {energy_data.get('total_site_energy_GJ', 'N/A')} GJ")
    print(f"  Total operational carbon: {energy_data.get('total_operational_carbon_kgCO2e', 'N/A')} kgCO2e")
else:
    print("\n✗ No energy data extracted")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)

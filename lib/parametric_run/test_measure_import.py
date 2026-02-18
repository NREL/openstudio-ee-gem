#!/usr/bin/env python3
"""Quick test to verify measures can be imported without errors."""

import sys
from pathlib import Path

# Add OpenStudio Python bindings
OPENSTUDIO_PYTHON_PATH = "/Applications/OpenStudio-3.11.0/Python"
if OPENSTUDIO_PYTHON_PATH not in sys.path:
    sys.path.insert(0, OPENSTUDIO_PYTHON_PATH)

import openstudio

measure_dir = Path(__file__).parent.parent / "measures"

# Test wall insulation measure
print("Testing wall insulation measure...")
wall_measure_path = measure_dir / "IncreaseInsulationRValueForExteriorWalls"
sys.path.insert(0, str(wall_measure_path))

try:
    import measure
    import importlib
    importlib.reload(measure)
    from measure import IncreaseInsulationRValueForExteriorWalls
    
    wall_measure = IncreaseInsulationRValueForExteriorWalls()
    print(f"✅ Wall measure loaded: {wall_measure.name()}")
except Exception as e:
    print(f"❌ Wall measure failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

sys.path.remove(str(wall_measure_path))

# Test roof insulation measure
print("\nTesting roof insulation measure...")
roof_measure_path = measure_dir / "IncreaseInsulationRValueForRoofs"
sys.path.insert(0, str(roof_measure_path))

try:
    import measure
    import importlib
    importlib.reload(measure)
    from measure import IncreaseInsulationRValueForRoofs
    
    roof_measure = IncreaseInsulationRValueForRoofs()
    print(f"✅ Roof measure loaded: {roof_measure.name()}")
except Exception as e:
    print(f"❌ Roof measure failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

sys.path.remove(str(roof_measure_path))

print("\n✅ All measures loaded successfully!")

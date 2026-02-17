#!/usr/bin/env python
"""Simple test script for the retrofit measure with energy comparison."""

import sys
from pathlib import Path

# Add measure directory to path
measure_dir = Path(__file__).parent.absolute()
if str(measure_dir) not in sys.path:
    sys.path.insert(0, str(measure_dir))

print("Testing energy comparison functionality...")

try:
    import openstudio
    print("✓ openstudio imported")
except ImportError as e:
    print(f"✗ openstudio import failed: {e}")

try:
    import pandas as pd
    print("✓ pandas imported")
except ImportError as e:
    print(f"✗ pandas import failed: {e}")

try:
    import plotly.graph_objects as go
    print("✓ plotly imported")
except ImportError as e:
    print(f"✗ plotly import failed: {e}")

try:
    from reportlab.lib.pagesizes import letter
    print("✓ reportlab imported")
except ImportError as e:
    print(f"✗ reportlab import failed: {e}")

try:
    from measure import CReport
    print("✓ measure imported")
    
    # Create measure instance
    measure = CReport()
    print("✓ CReport instantiated")
    
    # Test energy comparison with mock data
    from unittest.mock import MagicMock
    runner = MagicMock()
    runner.registerInfo = lambda x: print(f"  INFO: {x}")
    runner.registerWarning = lambda x: print(f"  WARNING: {x}")
    runner.registerError = lambda x: print(f"  ERROR: {x}")
    
    print("\nTesting energy comparison...")
    energy_deltas = measure.compare_energy_results(runner)
    if energy_deltas:
        print(f"✓ Energy comparison successful")
        print(f"  - Baseline Energy: {energy_deltas.get('baseline_energy_GJ', 'N/A')} GJ")
        print(f"  - Measure Energy: {energy_deltas.get('measure_energy_GJ', 'N/A')} GJ")
        print(f"  - Energy Delta: {energy_deltas.get('energy_delta_GJ', 'N/A')} GJ")
        print(f"  - Cost Delta: ${energy_deltas.get('cost_delta_usd', 'N/A')}")
    else:
        print("✗ No energy deltas returned")
    
    print("\nTesting PDF generation...")
    success = measure.generate_pdf_report(runner, energy_deltas)
    if success:
        print("✓ PDF generated successfully")
    else:
        print("✗ PDF generation failed")
    
except Exception as e:
    import traceback
    print(f"✗ Error: {e}")
    traceback.print_exc()

print("\nTest complete!")

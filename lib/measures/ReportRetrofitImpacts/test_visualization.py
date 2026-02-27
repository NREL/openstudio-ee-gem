#!/usr/bin/env python
"""Test script to generate parametric visualizations."""

import sys
from pathlib import Path

# Add measure directory to path
measure_dir = Path(__file__).parent
sys.path.insert(0, str(measure_dir))
sys.path.insert(0, str(measure_dir / 'resources'))

# Import the measure class
from measure import CReport

# Create instance and test visualization
report = CReport()

# Test if parametric CSV exists
csv_path = measure_dir / 'Inputs' / 'parametric_results.csv'
print(f"Checking for parametric CSV: {csv_path}")
print(f"  Exists: {csv_path.exists()}")

if csv_path.exists():
    print("\nGenerating parametric visualizations...")
    try:
        report.generate_parametric_visualizations(csv_path)
        print("✅ Visualization generated successfully!")
        
        output_path = measure_dir / 'Outputs' / 'optimization_visualization.html'
        if output_path.exists():
            file_size = output_path.stat().st_size
            print(f"✅ Output file created: {output_path}")
            print(f"   File size: {file_size / (1024*1024):.2f} MB")
        else:
            print("❌ Output file not created")
    except Exception as e:
        print(f"❌ Error generating visualization: {str(e)}")
        import traceback
        traceback.print_exc()
else:
    print("❌ parametric_results.csv not found in Inputs folder")
    print("\nAttempting fallback spider chart visualization...")
    try:
        report.generate_spider_chart_visualization()
        print("✅ Fallback visualization generated!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

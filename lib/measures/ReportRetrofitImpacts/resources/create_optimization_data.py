#!/usr/bin/env python
"""
Create optimization.xlsx with dummy scenario data for spider chart visualization.
Includes multiple retrofit scenarios with varying costs, energy savings, and embodied carbon.
"""

import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# Set paths
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
output_path = CURRENT_DIR_PATH.parent / "Inputs" / "optimization.xlsx"

print(f"Creating optimization data file: {output_path}")

# Define scenarios with different retrofit packages
# Scenario 1: Basic insulation upgrade (low cost, moderate savings)
# Scenario 2: Comprehensive upgrade (high cost, high savings)
# Scenario 3: Balanced approach (medium cost, good savings)

data = {
    'Factor': [
        'Initial Cost',
        'Energy Savings',
        'Embodied Carbon',
        'Payback Period',
        'Annual Cost Savings'
    ],
    'Unit': [
        'USD',
        'kWh/year',
        'kg CO2e',
        'years',
        'USD/year'
    ],
    'Basis': [
        20000,    # $20k baseline cost
        40000,    # 40,000 kWh/year savings baseline
        10000,    # 10,000 kg CO2e baseline
        10,       # 10 years baseline payback
        5000      # $5k/year baseline savings
    ],
    'Scenario_1': [
        8500,     # Low initial cost (basic insulation)
        25000,    # Moderate energy savings
        5000,     # Lower embodied carbon
        4.2,      # Short payback period
        3000      # Moderate annual savings
    ],
    'Scenario_2': [
        25000,    # High initial cost (comprehensive upgrade)
        55000,    # High energy savings
        15000,    # Higher embodied carbon
        6.5,      # Longer payback
        7200      # High annual savings
    ],
    'Scenario_3': [
        13750,    # Medium initial cost (our actual scenario)
        34200,    # Good energy savings
        7350,     # Moderate embodied carbon
        3.9,      # Good payback
        4104      # Good annual savings
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Calculate normalized values for spider chart (0-1 scale)
for scenario in ['Scenario_1', 'Scenario_2', 'Scenario_3']:
    df[f'Normalized_{scenario}'] = df[scenario] / df['Basis']

# Create Excel workbook with openpyxl for better control
wb = Workbook()
ws = wb.active
ws.title = "values"

# Write data to worksheet
for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
    for c_idx, value in enumerate(row, 1):
        ws.cell(row=r_idx, column=c_idx, value=value)

# Add a description sheet
ws_desc = wb.create_sheet("description")
descriptions = [
    ["Scenario", "Description"],
    ["Scenario_1", "Basic Insulation Package - Fiberglass batts in walls and attic. Low cost, moderate savings."],
    ["Scenario_2", "Comprehensive Upgrade - Spray foam, rigid insulation, air sealing, window upgrades. High performance."],
    ["Scenario_3", "Balanced Approach - Mix of rigid board, mineral wool, and fiberglass. Good cost-performance ratio."]
]

for r_idx, row in enumerate(descriptions, 1):
    for c_idx, value in enumerate(row, 1):
        ws_desc.cell(row=r_idx, column=c_idx, value=value)

# Save workbook
wb.save(output_path)
print(f"✓ Created optimization.xlsx with 3 scenarios")
print(f"✓ Scenario 1: Basic insulation ($8,500)")
print(f"✓ Scenario 2: Comprehensive ($25,000)")
print(f"✓ Scenario 3: Balanced ($13,750 - current retrofit)")
print(f"✓ File size: {output_path.stat().st_size:,} bytes")

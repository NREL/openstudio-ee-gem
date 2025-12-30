"""
Visualize door enhancement results from CSV output
Creates scatter plots showing operational vs embodied carbon by infiltration reduction percentage
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Set up paths
CURRENT_DIR = Path(__file__).parent.absolute()
csv_path = CURRENT_DIR / "resources/door_enhancement_report.csv"

# Read the CSV - it has two sections separated by blank lines
# First section: Door Enhancement Building AdditionalProperties
# Second section: EnergyPlus Simulation Summary

def read_multi_section_csv(file_path):
    """Read CSV with multiple sections separated by blank lines"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find section breaks
    sections = []
    current_section = []
    
    for line in lines:
        if line.strip().startswith('#') or (not line.strip() and current_section):
            if current_section:
                sections.append(current_section)
                current_section = []
            if line.strip().startswith('#'):
                current_section.append(line)
        else:
            current_section.append(line)
    
    if current_section:
        sections.append(current_section)
    
    # Parse each section
    dataframes = {}
    for section in sections:
        if not section:
            continue
        
        # Get section name from comment line
        section_name = section[0].strip('#').strip() if section[0].startswith('#') else "Unknown"
        
        # Create dataframe from section data
        section_data = ''.join(section[1:] if section[0].startswith('#') else section)
        df = pd.read_csv(pd.io.common.StringIO(section_data))
        dataframes[section_name] = df
    
    return dataframes

# Read the data
print(f"Reading data from {csv_path}...")
sections = read_multi_section_csv(csv_path)

# Extract the two sections
door_properties = sections.get('Door Enhancement Building AdditionalProperties')
simulation_summary = sections.get('EnergyPlus Simulation Summary')

if door_properties is None or simulation_summary is None:
    raise ValueError("Could not find expected sections in CSV")

print(f"\nFound {len(door_properties.columns)-1} scenarios")

# Extract data for each scenario
scenarios = []

for col in door_properties.columns[1:]:  # Skip first column (property names)
    scenario_name = col
    
    # Parse scenario name to extract infiltration percentage
    # Format: "Scenario_X: bottom_seal top_side_seal door_option infiltXX"
    parts = scenario_name.split('infilt')
    if len(parts) < 2:
        continue
    
    infiltration_pct = int(parts[1])
    
    # Get embodied carbon from door_properties
    embodied_carbon_row = door_properties[door_properties.iloc[:, 0] == 'door_enhancement_total_embodied_carbon_kgCO2eq']
    embodied_carbon = float(embodied_carbon_row[col].values[0]) if not embodied_carbon_row.empty else None
    
    # Get operational carbon from simulation_summary
    operational_carbon_row = simulation_summary[simulation_summary.iloc[:, 0] == 'total_operational_carbon_kgCO2e']
    operational_carbon = float(operational_carbon_row[col].values[0]) if not operational_carbon_row.empty else None
    
    # Get seal options
    bottom_seal_row = door_properties[door_properties.iloc[:, 0] == 'door_enhancement_bottom_seal_option']
    bottom_seal = bottom_seal_row[col].values[0] if not bottom_seal_row.empty else None
    
    top_side_seal_row = door_properties[door_properties.iloc[:, 0] == 'door_enhancement_top_side_seal_option']
    top_side_seal = top_side_seal_row[col].values[0] if not top_side_seal_row.empty else None
    
    scenarios.append({
        'scenario_name': scenario_name,
        'infiltration_reduction_pct': infiltration_pct,
        'embodied_carbon_kgCO2eq': embodied_carbon,
        'operational_carbon_kgCO2e': operational_carbon,
        'bottom_seal': bottom_seal,
        'top_side_seal': top_side_seal
    })

# Create DataFrame
df = pd.DataFrame(scenarios)
print(f"\nProcessed {len(df)} scenarios")
print(f"Infiltration reduction percentages: {sorted(df['infiltration_reduction_pct'].unique())}")

# Group by infiltration reduction percentage and calculate statistics
grouped = df.groupby('infiltration_reduction_pct').agg({
    'operational_carbon_kgCO2e': ['mean', 'std', 'min', 'max'],
    'embodied_carbon_kgCO2eq': ['mean', 'std', 'min', 'max']
}).reset_index()

print("\nGrouped Statistics:")
print(grouped)

# Create the scatter plot with dual y-axes
fig, ax1 = plt.subplots(figsize=(12, 7))

# Define colors for different seal combinations
seal_combinations = df.apply(lambda row: f"{row['bottom_seal'][:15]}... + {row['top_side_seal'][:15]}...", axis=1)
unique_seals = seal_combinations.unique()
colors = plt.cm.tab10(np.linspace(0, 1, len(unique_seals)))
color_map = dict(zip(unique_seals, colors))

# Left y-axis: Operational Carbon
ax1.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Operational Carbon (kgCO₂e)', fontsize=12, fontweight='bold', color='tab:blue')
ax1.tick_params(axis='y', labelcolor='tab:blue')

# Plot operational carbon
for seal_combo in unique_seals:
    mask = seal_combinations == seal_combo
    ax1.scatter(
        df[mask]['infiltration_reduction_pct'],
        df[mask]['operational_carbon_kgCO2e'],
        alpha=0.6,
        s=100,
        color=color_map[seal_combo],
        marker='o',
        label=seal_combo,
        edgecolors='black',
        linewidths=0.5
    )

# Add trend line for operational carbon
z = np.polyfit(df['infiltration_reduction_pct'], df['operational_carbon_kgCO2e'], 1)
p = np.poly1d(z)
x_trend = np.linspace(df['infiltration_reduction_pct'].min(), df['infiltration_reduction_pct'].max(), 100)
ax1.plot(x_trend, p(x_trend), '--', color='tab:blue', linewidth=2, alpha=0.5, label='Operational Trend')

# Right y-axis: Embodied Carbon
ax2 = ax1.twinx()
ax2.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:red')
ax2.tick_params(axis='y', labelcolor='tab:red')

# Plot embodied carbon with different marker and labels
embodied_labels_added = {}  # Track which embodied carbon values have been labeled
for seal_combo in unique_seals:
    mask = seal_combinations == seal_combo
    embodied_values = df[mask]['embodied_carbon_kgCO2eq'].values
    infiltration_values = df[mask]['infiltration_reduction_pct'].values
    
    ax2.scatter(
        infiltration_values,
        embodied_values,
        alpha=0.6,
        s=100,
        color=color_map[seal_combo],
        marker='^',
        edgecolors='black',
        linewidths=0.5
    )
    
    # Add label for this seal combination at the rightmost point
    if len(embodied_values) > 0:
        unique_embodied = embodied_values[0]  # Embodied carbon is same for all infiltration %
        if unique_embodied not in embodied_labels_added:
            # Find the rightmost infiltration percentage for this combo
            max_infilt_idx = np.argmax(infiltration_values)
            label_x = infiltration_values[max_infilt_idx]
            label_y = embodied_values[max_infilt_idx]
            
            # Create shorter label
            bottom = seal_combo.split('+')[0].strip().replace('...', '')
            top = seal_combo.split('+')[1].strip().replace('...', '')
            short_label = f"{bottom[:12]}+\n{top[:12]}"
            
            ax2.annotate(short_label,
                        xy=(label_x, label_y),
                        xytext=(10, 0),
                        textcoords='offset points',
                        fontsize=8,
                        color='tab:red',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='tab:red', alpha=0.7),
                        ha='left',
                        va='center')
            embodied_labels_added[unique_embodied] = True

# Add horizontal lines for average embodied carbon (since it doesn't vary with infiltration)
for embodied_val in df['embodied_carbon_kgCO2eq'].unique():
    ax2.axhline(y=embodied_val, color='tab:red', linestyle=':', alpha=0.3, linewidth=1)

# Title and grid
plt.title('Door Enhancement: Operational vs Embodied Carbon by Infiltration Reduction\n(Circles=Operational, Triangles=Embodied)',
          fontsize=14, fontweight='bold', pad=20)
ax1.grid(True, alpha=0.3, linestyle='--')

# Create custom legend with seal combinations
from matplotlib.lines import Line2D

# Create legend entries for each seal combination
legend_lines = []
legend_labels = []

# Add seal combination entries with colors
for seal_combo, color in color_map.items():
    legend_lines.append(Line2D([0], [0], marker='o', color='w', 
                               markerfacecolor=color, markersize=10, 
                               markeredgecolor='black', linewidth=0))
    # Shorten label for legend
    bottom = seal_combo.split('+')[0].strip().replace('...', '')
    top = seal_combo.split('+')[1].strip().replace('...', '')
    legend_labels.append(f"{bottom[:15]}+ {top[:15]}")

# Add operational trend line
lines1, labels1 = ax1.get_legend_handles_labels()
trend_lines = [l for l, lab in zip(lines1, labels1) if 'Trend' in lab]
trend_labels = [lab for lab in labels1 if 'Trend' in lab]
legend_lines.extend(trend_lines)
legend_labels.extend(trend_labels)

# Add marker type explanations
custom_lines = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=10, label='Operational', markeredgecolor='black'),
    Line2D([0], [0], marker='^', color='w', markerfacecolor='gray', markersize=10, label='Embodied (labeled)', markeredgecolor='black'),
]
legend_lines.extend(custom_lines)
legend_labels.extend(['Operational Carbon', 'Embodied Carbon (labeled)'])

ax1.legend(legend_lines, legend_labels, loc='upper left', fontsize=8, ncol=1, 
          title='Seal Combinations & Data Types', title_fontsize=9)

# Add horizontal lines for average embodied carbon (since it doesn't vary with infiltration)
for embodied_val in df['embodied_carbon_kgCO2eq'].unique():
    ax2.axhline(y=embodied_val, color='tab:red', linestyle=':', alpha=0.3, linewidth=1)

# Title and grid
plt.title('Door Enhancement: Operational vs Embodied Carbon by Infiltration Reduction\n(Circles=Operational, Triangles=Embodied)',
          fontsize=14, fontweight='bold', pad=20)
ax1.grid(True, alpha=0.3, linestyle='--')

# Create custom legend
# Combine legends from both axes
lines1, labels1 = ax1.get_legend_handles_labels()
# Filter out seal combination entries for cleaner legend
legend_lines = [l for l, lab in zip(lines1, labels1) if 'Trend' in lab]
legend_labels = [lab for lab in labels1 if 'Trend' in lab]

# Add custom entries for marker types
from matplotlib.lines import Line2D
custom_lines = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=10, label='Operational Carbon', markeredgecolor='black'),
    Line2D([0], [0], marker='^', color='w', markerfacecolor='gray', markersize=10, label='Embodied Carbon', markeredgecolor='black'),
]
legend_lines.extend(custom_lines)
legend_labels.extend(['Operational Carbon', 'Embodied Carbon'])

ax1.legend(legend_lines, legend_labels, loc='upper right', fontsize=10)

# Adjust layout
fig.tight_layout()

# Save the plot
output_path = CURRENT_DIR / "tests/output/carbon_analysis.png"
output_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"\nPlot saved to: {output_path}")

# Create a second plot: grouped by infiltration reduction percentage with error bars
fig2, ax3 = plt.subplots(figsize=(12, 7))

# Calculate means
infiltration_pcts = sorted(df['infiltration_reduction_pct'].unique())
operational_means = [df[df['infiltration_reduction_pct'] == pct]['operational_carbon_kgCO2e'].mean() for pct in infiltration_pcts]
operational_stds = [df[df['infiltration_reduction_pct'] == pct]['operational_carbon_kgCO2e'].std() for pct in infiltration_pcts]
embodied_means = [df[df['infiltration_reduction_pct'] == pct]['embodied_carbon_kgCO2eq'].mean() for pct in infiltration_pcts]
embodied_stds = [df[df['infiltration_reduction_pct'] == pct]['embodied_carbon_kgCO2eq'].std() for pct in infiltration_pcts]

# Left y-axis: Operational Carbon with error bars
ax3.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
ax3.set_ylabel('Operational Carbon (kgCO₂e)', fontsize=12, fontweight='bold', color='tab:blue')
ax3.errorbar(infiltration_pcts, operational_means, yerr=operational_stds, 
             fmt='o-', color='tab:blue', linewidth=2, markersize=10, 
             capsize=5, capthick=2, label='Operational Carbon (mean ± std)')
ax3.tick_params(axis='y', labelcolor='tab:blue')

# Right y-axis: Embodied Carbon with error bars
ax4 = ax3.twinx()
ax4.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:red')
ax4.errorbar(infiltration_pcts, embodied_means, yerr=embodied_stds,
             fmt='^-', color='tab:red', linewidth=2, markersize=10,
             capsize=5, capthick=2, label='Embodied Carbon (mean ± std)')
ax4.tick_params(axis='y', labelcolor='tab:red')

# Title and grid
plt.title('Door Enhancement: Average Carbon Impact by Infiltration Reduction\n(with Standard Deviation)',
          fontsize=14, fontweight='bold', pad=20)
ax3.grid(True, alpha=0.3, linestyle='--')

# Legends
ax3.legend(loc='upper left', fontsize=10)
ax4.legend(loc='upper right', fontsize=10)

# Adjust layout
fig2.tight_layout()

# Save the second plot
output_path2 = CURRENT_DIR / "tests/output/carbon_analysis_grouped.png"
plt.savefig(output_path2, dpi=300, bbox_inches='tight')
print(f"Grouped plot saved to: {output_path2}")

# Show plots
plt.show()

print("\n✓ Visualization complete!")

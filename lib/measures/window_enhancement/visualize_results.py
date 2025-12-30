"""
Visualize window enhancement results from CSV output
Creates scatter plots showing operational vs embodied carbon by infiltration reduction percentage
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Set up paths
CURRENT_DIR = Path(__file__).parent.absolute()

# Try to load the combined report first (includes both embodied and operational carbon)
combined_csv_path = CURRENT_DIR / "tests/output/window_enhancement_report.csv"
basic_csv_path = CURRENT_DIR / "tests/output/retrofit_combinations_results.csv"

# Check which CSV is available
if combined_csv_path.exists():
    csv_path = combined_csv_path
    has_operational_data = True
    print(f"Reading combined data from {csv_path}...")
elif basic_csv_path.exists():
    csv_path = basic_csv_path
    has_operational_data = False
    print(f"Reading basic data from {csv_path}...")
    print("Note: To include operational carbon data, run apply_reporting_measure_window_enhancement.py first")
else:
    print(f"Error: No CSV file found.")
    print(f"  Looked for: {combined_csv_path}")
    print(f"  Looked for: {basic_csv_path}")
    print("Please run apply_measure_scenario.py first to generate the data.")
    exit(1)

if not csv_path.exists():
    print(f"Error: CSV file not found at {csv_path}")
    print("Please run apply_measure_scenario.py first to generate the data.")
    exit(1)

df = pd.read_csv(csv_path)

print(f"\nLoaded {len(df)} scenarios")

# Handle column name variations
if 'Infiltration_Reduction_%' in df.columns:
    infilt_col = 'Infiltration_Reduction_%'
elif 'window_enhancement_space_infiltration_reduction_percent' in df.columns:
    infilt_col = 'window_enhancement_space_infiltration_reduction_percent'
    df['Infiltration_Reduction_%'] = df[infilt_col]
else:
    print("Error: Could not find infiltration reduction column")
    exit(1)

# Handle embodied carbon column variations
if 'Total_Embodied_Carbon_kgCO2eq' in df.columns:
    embodied_col = 'Total_Embodied_Carbon_kgCO2eq'
elif 'window_enhancement_total_embodied_carbon_kgCO2eq' in df.columns:
    embodied_col = 'window_enhancement_total_embodied_carbon_kgCO2eq'
    df['Total_Embodied_Carbon_kgCO2eq'] = df[embodied_col]
else:
    print("Error: Could not find embodied carbon column")
    exit(1)

print(f"Infiltration reduction percentages: {sorted(df['Infiltration_Reduction_%'].unique())}")

# Filter successful scenarios
if 'Result' in df.columns:
    df_success = df[df['Result'] == 'Success'].copy()
    print(f"Successful scenarios: {len(df_success)}")
else:
    df_success = df.copy()
    print(f"Processing all scenarios: {len(df_success)}")

if len(df_success) == 0:
    # Handle both CSV formats
    frame_col = 'Frame_Option' if 'Frame_Option' in df_success.columns else 'window_enhancement_wf_option'
    caulk_col = 'Caulking_Option' if 'Caulking_Option' in df_success.columns else 'window_enhancement_caulking_option'
    glass_col = 'Glass_Option' if 'Glass_Option' in df_success.columns else 'window_enhancement_glass_option'
    num_panes_col = 'Num_Panes' if 'Num_Panes' in df_success.columns else 'window_enhancement_user_num_panes'
    film_col = 'Film_Option' if 'Film_Option' in df_success.columns else 'window_enhancement_film_option'
    ws_col = 'Weatherstrip_Option' if 'Weatherstrip_Option' in df_success.columns else 'window_enhancement_weatherstrip_option'
    sg_col = 'Secondary_Glazing_Option' if 'Secondary_Glazing_Option' in df_success.columns else 'window_enhancement_secondary_glazing_option'
    
    if frame_col in row.index and pd.notna(row[frame_col]) and row[frame_col] != 'none':
        parts.append(f"Fr:{str(row[frame_col])[:4]}")
    
    if caulk_col in row.index and pd.notna(row[caulk_col]) and row[caulk_col] != 'none':
        parts.append(f"Ca:{str(row[caulk_col])[:4]}")
    
    if glass_col in row.index and pd.notna(row[glass_col]) and row[glass_col] != 'none':
        if num_panes_col in row.index and pd.notna(row[num_panes_col]) and row[num_panes_col] != '':
            parts.append(f"Gl:{row[num_panes_col]}P")
    
    if film_col in row.index and pd.notna(row[film_col]) and row[film_col] != 'none':
        film_short = str(row[film_col]).replace(' film', '').replace('solar control', 'SC').replace('low-e', 'LE')[:4]
        parts.append(f"Fi:{film_short}")
    
    if ws_col in row.index and pd.notna(row[ws_col]) and row[ws_col] != 'none':
        parts.append(f"WS")
    
if len(df_success) == 0:
    print("Error: No valid scenarios found. Cannot create visualizations.")
    exit(1)

# Create combination labels
def create_combo_label(row):
    """Create a short label for each combination"""
    parts = []
    
    # Handle both CSV formats
    frame_col = 'Frame_Option' if 'Frame_Option' in df_success.columns else 'window_enhancement_wf_option'
    caulk_col = 'Caulking_Option' if 'Caulking_Option' in df_success.columns else 'window_enhancement_caulking_option'
    glass_col = 'Glass_Option' if 'Glass_Option' in df_success.columns else 'window_enhancement_glass_option'
    num_panes_col = 'Num_Panes' if 'Num_Panes' in df_success.columns else 'window_enhancement_user_num_panes'
    film_col = 'Film_Option' if 'Film_Option' in df_success.columns else 'window_enhancement_film_option'
    ws_col = 'Weatherstrip_Option' if 'Weatherstrip_Option' in df_success.columns else 'window_enhancement_weatherstrip_option'
    sg_col = 'Secondary_Glazing_Option' if 'Secondary_Glazing_Option' in df_success.columns else 'window_enhancement_secondary_glazing_option'
    
    if frame_col in row.index and pd.notna(row[frame_col]) and row[frame_col] != 'none':
        parts.append(f"Fr:{str(row[frame_col])[:4]}")
    
    if caulk_col in row.index and pd.notna(row[caulk_col]) and row[caulk_col] != 'none':
        parts.append(f"Ca:{str(row[caulk_col])[:4]}")
    
    if glass_col in row.index and pd.notna(row[glass_col]) and row[glass_col] != 'none':
        if num_panes_col in row.index and pd.notna(row[num_panes_col]) and row[num_panes_col] != '':
            parts.append(f"Gl:{row[num_panes_col]}P")
    
    if film_col in row.index and pd.notna(row[film_col]) and row[film_col] != 'none':
        film_short = str(row[film_col]).replace(' film', '').replace('solar control', 'SC').replace('low-e', 'LE')[:4]
        parts.append(f"Fi:{film_short}")
    
    if ws_col in row.index and pd.notna(row[ws_col]) and row[ws_col] != 'none':
        parts.append(f"WS")
    
    if sg_col in row.index and pd.notna(row[sg_col]) and row[sg_col] != 'none':
        parts.append(f"SG")
    
    if not parts:
        return "None"
    
    return "+".join(parts)

df_success['combo_label'] = df_success.apply(create_combo_label, axis=1)

# Get unique combinations and assign colors
unique_combos = df_success['combo_label'].unique()
colors = plt.cm.tab10(np.linspace(0, 1, len(unique_combos)))
color_map = dict(zip(unique_combos, colors))

print(f"\nUnique combinations: {len(unique_combos)}")
print(f"Combinations: {', '.join(list(unique_combos)[:10])}{'...' if len(unique_combos) > 10 else ''}")

# Group by infiltration reduction percentage and calculate statistics
grouped = df_success.groupby('Infiltration_Reduction_%').agg({
    'Total_Embodied_Carbon_kgCO2eq': ['mean', 'std', 'min', 'max', 'count']
}).reset_index()

print("\nEmbodied Carbon Statistics by Infiltration Reduction:")
print(grouped)

# Check if operational carbon data is available
if has_operational_data and 'total_operational_carbon_kgCO2e' in df_success.columns:
    print("\n✓ Operational carbon data available - creating dual-axis plots")
    operational_col = 'total_operational_carbon_kgCO2e'
    
    # ============================================================================
    # PLOT 1: Dual-axis scatter plot - Operational vs Embodied Carbon
    # ============================================================================
    fig, ax1 = plt.subplots(figsize=(14, 8))
    
    # Left y-axis: Operational Carbon
    ax1.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Operational Carbon (kgCO₂e)', fontsize=12, fontweight='bold', color='tab:blue')
    ax1.tick_params(axis='y', labelcolor='tab:blue')
    
    # Plot operational carbon
    for combo_label in unique_combos:
        mask = df_success['combo_label'] == combo_label
        ax1.scatter(
            df_success[mask]['Infiltration_Reduction_%'],
            df_success[mask][operational_col],
            alpha=0.6,
            s=100,
            color=color_map[combo_label],
            marker='o',
            label=combo_label,
            edgecolors='black',
            linewidths=0.8
        )
    
    # Add trend line for operational carbon
    valid_operational = df_success[df_success[operational_col].notna()]
    if len(valid_operational) > 1:
        z = np.polyfit(valid_operational['Infiltration_Reduction_%'], valid_operational[operational_col], 1)
        p = np.poly1d(z)
        x_trend = np.linspace(valid_operational['Infiltration_Reduction_%'].min(), 
                             valid_operational['Infiltration_Reduction_%'].max(), 100)
        ax1.plot(x_trend, p(x_trend), '--', color='tab:blue', linewidth=2, alpha=0.5, label='Operational Trend')
    
    # Right y-axis: Embodied Carbon
    ax2 = ax1.twinx()
    ax2.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:red')
    ax2.tick_params(axis='y', labelcolor='tab:red')
    
    # Plot embodied carbon with different marker and labels
    embodied_labels_added = {}
    for combo_label in unique_combos:
        mask = df_success['combo_label'] == combo_label
        embodied_values = df_success[mask]['Total_Embodied_Carbon_kgCO2eq'].values
        infiltration_values = df_success[mask]['Infiltration_Reduction_%'].values
        
        ax2.scatter(
            infiltration_values,
            embodied_values,
            alpha=0.6,
            s=100,
            color=color_map[combo_label],
            marker='^',
            edgecolors='black',
            linewidths=0.8
        )
        
        # Add label for unique embodied carbon values
        if len(embodied_values) > 0:
            unique_embodied = embodied_values[0]
            if unique_embodied not in embodied_labels_added:
                max_infilt_idx = np.argmax(infiltration_values)
                label_x = infiltration_values[max_infilt_idx]
                label_y = embodied_values[max_infilt_idx]
                
                ax2.annotate(combo_label,
                            xy=(label_x, label_y),
                            xytext=(8, 0),
                            textcoords='offset points',
                            fontsize=7,
                            color='tab:red',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                     edgecolor=color_map[combo_label], alpha=0.8, linewidth=1.5),
                            ha='left',
                            va='center')
                embodied_labels_added[unique_embodied] = True
    
    # Add horizontal lines for different embodied carbon levels
    for embodied_val in df_success['Total_Embodied_Carbon_kgCO2eq'].unique():
        ax2.axhline(y=embodied_val, color='tab:red', linestyle=':', alpha=0.2, linewidth=1)
    
    # Title and grid
    plt.title('Window Enhancement: Operational vs Embodied Carbon by Infiltration Reduction\n(Circles=Operational, Triangles=Embodied, Labels show renovation combinations)',
              fontsize=13, fontweight='bold', pad=20)
    ax1.grid(True, alpha=0.3, linestyle='--')
    
    # Create custom legend
    from matplotlib.lines import Line2D
    
    legend_lines = []
    legend_labels = []
    
    # Add marker type explanations
    legend_lines.extend([
        Line2D([0], [0], marker='o', color='w', markerfacecolor='tab:blue', markersize=10, 
               label='Operational', markeredgecolor='black'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='tab:red', markersize=10, 
               label='Embodied', markeredgecolor='black'),
    ])
    legend_labels.extend(['Operational Carbon', 'Embodied Carbon (labeled)'])
    
    ax1.legend(legend_lines, legend_labels, loc='upper left', fontsize=10)
    
    fig.tight_layout()
    
    output_path_dual = CURRENT_DIR / "tests/output/window_carbon_operational_vs_embodied.png"
    output_path_dual.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path_dual, dpi=300, bbox_inches='tight')
    print(f"\n✓ Dual-axis plot saved to: {output_path_dual}")
    
    # ============================================================================
    # PLOT 2: Grouped by infiltration reduction with error bars (dual y-axis)
    # ============================================================================
    fig2, ax3 = plt.subplots(figsize=(12, 7))
    
    infiltration_pcts = sorted(valid_operational['Infiltration_Reduction_%'].unique())
    operational_means = [valid_operational[valid_operational['Infiltration_Reduction_%'] == pct][operational_col].mean() 
                        for pct in infiltration_pcts]
    operational_stds = [valid_operational[valid_operational['Infiltration_Reduction_%'] == pct][operational_col].std() 
                       for pct in infiltration_pcts]
    embodied_means = [df_success[df_success['Infiltration_Reduction_%'] == pct]['Total_Embodied_Carbon_kgCO2eq'].mean() 
                     for pct in infiltration_pcts]
    embodied_stds = [df_success[df_success['Infiltration_Reduction_%'] == pct]['Total_Embodied_Carbon_kgCO2eq'].std() 
                    for pct in infiltration_pcts]
    
    # Left y-axis: Operational Carbon
    ax3.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Operational Carbon (kgCO₂e)', fontsize=12, fontweight='bold', color='tab:blue')
    ax3.errorbar(infiltration_pcts, operational_means, yerr=operational_stds, 
                 fmt='o-', color='tab:blue', linewidth=2.5, markersize=12, 
                 capsize=8, capthick=2.5, label='Operational Carbon (mean ± std)')
    ax3.tick_params(axis='y', labelcolor='tab:blue')
    
    # Right y-axis: Embodied Carbon
    ax4 = ax3.twinx()
    ax4.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:red')
    ax4.errorbar(infiltration_pcts, embodied_means, yerr=embodied_stds,
                 fmt='^-', color='tab:red', linewidth=2.5, markersize=12,
                 capsize=8, capthick=2.5, label='Embodied Carbon (mean ± std)')
    ax4.tick_params(axis='y', labelcolor='tab:red')
    
    plt.title('Window Enhancement: Average Carbon Impact by Infiltration Reduction\n(with Standard Deviation)',
              fontsize=13, fontweight='bold', pad=20)
    ax3.grid(True, alpha=0.3, linestyle='--')
    
    ax3.legend(loc='upper left', fontsize=10)
    ax4.legend(loc='upper right', fontsize=10)
    
    fig2.tight_layout()
    
    output_path_grouped = CURRENT_DIR / "tests/output/window_carbon_grouped_dual_axis.png"
    plt.savefig(output_path_grouped, dpi=300, bbox_inches='tight')
    print(f"✓ Grouped dual-axis plot saved to: {output_path_grouped}")
    
else:
    print("\n⚠ Operational carbon data not available - creating embodied carbon only plots")
    print("  Run apply_reporting_measure_window_enhancement.py to add operational carbon data")

# ============================================================================
# PLOT 3: Embodied Carbon scatter plot (original)
# ============================================================================
fig3, ax5 = plt.subplots(figsize=(14, 8))

print(f"\nUnique combinations: {len(unique_combos)}")
print(f"Combinations: {', '.join(unique_combos)}")

# Group by infiltration reduction percentage and calculate statistics
grouped = df_success.groupby('Infiltration_Reduction_%').agg({
    'Total_Embodied_Carbon_kgCO2eq': ['mean', 'std', 'min', 'max', 'count']
}).reset_index()

print("\nGrouped Statistics:")
print(grouped)

# ============================================================================
# PLOT 1: Scatter plot with all scenarios
# ============================================================================
fig, ax1 = plt.subplots(figsize=(14, 8))

# Plot embodied carbon on the y-axis
ax1.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
ax1.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:blue')
ax1.tick_params(axis='y', labelcolor='tab:blue')

# Plot each combination with different colors
for combo_label in unique_combos:
    mask = df_success['combo_label'] == combo_label
    ax1.scatter(
        df_success[mask]['Infiltration_Reduction_%'],
        df_success[mask]['Total_Embodied_Carbon_kgCO2eq'],
        alpha=0.7,
        s=120,
        color=color_map[combo_label],
        marker='o',
        label=combo_label,
        edgecolors='black',
        linewidths=0.8
    )

# Add horizontal lines for different embodied carbon levels
for embodied_val in df_success['Total_Embodied_Carbon_kgCO2eq'].unique():
    ax1.axhline(y=embodied_val, color='gray', linestyle=':', alpha=0.2, linewidth=1)

# Add labels for each unique embodied carbon level
embodied_labels_added = {}
for combo_label in unique_combos:
    mask = df_success['combo_label'] == combo_label
    combo_data = df_success[mask]
    
    if len(combo_data) > 0:
        unique_embodied = combo_data['Total_Embodied_Carbon_kgCO2eq'].iloc[0]
        
        if unique_embodied not in embodied_labels_added:
            # Find the rightmost infiltration percentage for this combo
            max_infilt_idx = combo_data['Infiltration_Reduction_%'].idxmax()
            label_x = combo_data.loc[max_infilt_idx, 'Infiltration_Reduction_%']
            label_y = combo_data.loc[max_infilt_idx, 'Total_Embodied_Carbon_kgCO2eq']
            
            ax1.annotate(combo_label,
                        xy=(label_x, label_y),
                        xytext=(8, 0),
                        textcoords='offset points',
                        fontsize=8,
                        color='tab:blue',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                 edgecolor=color_map[combo_label], alpha=0.8, linewidth=1.5),
                        ha='left',
                        va='center')
            embodied_labels_added[unique_embodied] = True

# Title and grid
plt.title('Window Enhancement: Embodied Carbon by Renovation Options and Infiltration Reduction\n(Each point represents a scenario combination; labels show renovation options)',
          fontsize=13, fontweight='bold', pad=20)
ax1.grid(True, alpha=0.3, linestyle='--')

# Legend - limit to reasonable number of entries
if len(unique_combos) <= 15:
    ax1.legend(loc='upper left', fontsize=8, ncol=2, title='Renovation Combinations', title_fontsize=9)
else:
    # Too many combinations for legend, add note
    ax1.text(0.02, 0.98, f'{len(unique_combos)} different combinations tested\n(see labels on plot)', 
            transform=ax1.transAxes, fontsize=9, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

# Adjust layout
fig.tight_layout()

# Save the plot
output_path = CURRENT_DIR / "tests/output/window_carbon_analysis.png"
output_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"\nPlot saved to: {output_path}")

# ============================================================================
# PLOT 2: Grouped by infiltration reduction percentage with error bars
# ============================================================================
fig2, ax2 = plt.subplots(figsize=(12, 7))

# Calculate means and standard deviations
infiltration_pcts = sorted(df_success['Infiltration_Reduction_%'].unique())
embodied_means = [df_success[df_success['Infiltration_Reduction_%'] == pct]['Total_Embodied_Carbon_kgCO2eq'].mean() 
                  for pct in infiltration_pcts]
embodied_stds = [df_success[df_success['Infiltration_Reduction_%'] == pct]['Total_Embodied_Carbon_kgCO2eq'].std() 
                 for pct in infiltration_pcts]
counts = [df_success[df_success['Infiltration_Reduction_%'] == pct].shape[0] 
          for pct in infiltration_pcts]

# Plot with error bars
ax2.errorbar(infiltration_pcts, embodied_means, yerr=embodied_stds, 
             fmt='o-', color='tab:blue', linewidth=2.5, markersize=12, 
             capsize=8, capthick=2.5, label=f'Embodied Carbon (mean ± std, n={counts[0]})')

ax2.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Embodied Carbon (kgCO₂eq)', fontsize=12, fontweight='bold', color='tab:blue')
ax2.tick_params(axis='y', labelcolor='tab:blue')

# Add individual scenario points in background
for combo_label in unique_combos:
    mask = df_success['combo_label'] == combo_label
    ax2.scatter(
        df_success[mask]['Infiltration_Reduction_%'],
        df_success[mask]['Total_Embodied_Carbon_kgCO2eq'],
        alpha=0.3,
        s=50,
        color=color_map[combo_label],
        marker='o',
        edgecolors='none'
    )

# Title and grid
plt.title('Window Enhancement: Average Embodied Carbon by Infiltration Reduction\n(with Standard Deviation and Individual Scenarios)',
          fontsize=13, fontweight='bold', pad=20)
ax2.grid(True, alpha=0.3, linestyle='--')

# Legend
ax2.legend(loc='upper left', fontsize=10)

# Adjust layout
fig2.tight_layout()

# Save the second plot
output_path2 = CURRENT_DIR / "tests/output/window_carbon_analysis_grouped.png"
plt.savefig(output_path2, dpi=300, bbox_inches='tight')
print(f"Grouped plot saved to: {output_path2}")

# ============================================================================
# PLOT 3: Heatmap showing embodied carbon by primary renovation options
# ============================================================================
# Group by the most impactful options for heatmap
fig3, ax3 = plt.subplots(figsize=(12, 8))

# Create a summary showing embodied carbon by glass option and film option
heatmap_data = df_success.groupby(['Glass_Option', 'Film_Option'])['Total_Embodied_Carbon_kgCO2eq'].mean().reset_index()

# Create pivot table
pivot_table = heatmap_data.pivot(index='Glass_Option', columns='Film_Option', values='Total_Embodied_Carbon_kgCO2eq')

# Create heatmap
im = ax3.imshow(pivot_table.values, cmap='YlOrRd', aspect='auto')

# Set ticks and labels
ax3.set_xticks(np.arange(len(pivot_table.columns)))
ax3.set_yticks(np.arange(len(pivot_table.index)))
ax3.set_xticklabels([col.replace(' film', '') for col in pivot_table.columns], rotation=45, ha='right')
ax3.set_yticklabels([idx.replace('provide user_num_panes', 'User Panes').replace('_', ' ').title() for idx in pivot_table.index])

# Add colorbar
cbar = plt.colorbar(im, ax=ax3)
cbar.set_label('Mean Embodied Carbon (kgCO₂eq)', rotation=270, labelpad=20, fontweight='bold')

# Add values to cells
for i in range(len(pivot_table.index)):
    for j in range(len(pivot_table.columns)):
        value = pivot_table.values[i, j]
        if not np.isnan(value):
            text = ax3.text(j, i, f'{value:.1f}',
                           ha="center", va="center", color="black", fontweight='bold', fontsize=9)

plt.title('Window Enhancement: Mean Embodied Carbon by Glass and Film Options\n(Averaged across all other renovation options)',
          fontsize=13, fontweight='bold', pad=15)
ax3.set_xlabel('Film Option', fontsize=11, fontweight='bold')
ax3.set_ylabel('Glass Option', fontsize=11, fontweight='bold')

fig3.tight_layout()

# Save the heatmap
output_path3 = CURRENT_DIR / "tests/output/window_carbon_heatmap.png"
plt.savefig(output_path3, dpi=300, bbox_inches='tight')
print(f"Heatmap saved to: {output_path3}")

# Show plots
plt.show()

print("\n✓ Visualization complete!")
print(f"\nGenerated {3} plots:")
print(f"  1. Scatter plot: {output_path.name}")
print(f"  2. Grouped plot: {output_path2.name}")
print(f"  3. Heatmap: {output_path3.name}")

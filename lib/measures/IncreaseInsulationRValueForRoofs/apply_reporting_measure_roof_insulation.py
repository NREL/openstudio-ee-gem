"""
Apply reporting measure to extract AdditionalProperties from roof insulation models.

Usage:
    python apply_reporting_measure.py
"""

import sys
import os

# Set UTF-8 encoding for console output to handle Unicode characters
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from pathlib import Path

# Add the measure directory to Python path
measure_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(measure_dir))

# Import OpenStudio
try:
    import openstudio
except ImportError:
    print("Error: OpenStudio Python bindings not found.")
    print("Make sure OpenStudio is installed and Python bindings are available.")
    sys.exit(1)

def load_emission_factors():
    """Load emission factors from CSV file."""
    emission_factors_path = Path(__file__).parent.parent.parent / "ReportRetrofitImpacts" / "resources" / "emission_factors_for_operational_carbon.csv"
    
    import pandas as pd
    if not emission_factors_path.exists():
        print(f"Warning: Emission factors file not found at {emission_factors_path}")
        print("  Using default emission factors")
        return {
            'elec_emission_factor': 101.588886,  # kgCO2e_per_GJ
            'gas_emission_factor': 50.3419231,    # kgCO2e_per_GJ
            'water_emission_factor': 0.46         # kgCO2e_per_m3
        }
    
    try:
        df = pd.read_csv(emission_factors_path)
        factors = {}
        for _, row in df.iterrows():
            factors[row['Item']] = float(row['Value'])
        print(f"✓ Loaded emission factors from {emission_factors_path.name}")
        print(f"  Electricity: {factors['elec_emission_factor']:.2f} kgCO2e/GJ")
        print(f"  Natural Gas: {factors['gas_emission_factor']:.2f} kgCO2e/GJ")
        print(f"  Water: {factors['water_emission_factor']:.2f} kgCO2e/m³")
        return factors
    except Exception as e:
        print(f"⚠ Warning: Error reading emission factors: {e}")
        print("  Using default emission factors")
        return {
            'elec_emission_factor': 101.588886,
            'gas_emission_factor': 50.3419231,
            'water_emission_factor': 0.46
        }

def extract_model_data(osm_path, emission_factors):
    """Extract AdditionalProperties from OSM file and energy results from SQL file."""
    print(f"\n{'='*80}")
    print(f"Processing: {osm_path.name}")
    print(f"{'='*80}")
    
    # Load the model
    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(str(osm_path))
    
    if not model_opt.is_initialized():
        print(f"✗ Error: Could not load model from {osm_path}")
        return None, None
    
    model = model_opt.get()
    print(f"✓ Model loaded successfully. Contains {len(model.getConstructions())} constructions.")
    
    # Extract AdditionalProperties directly
    import pandas as pd
    props_data = []
    
    for construction in model.getConstructions():
        props = construction.additionalProperties()
        feature_names = props.featureNames()
        
        if len(feature_names) > 0:
            item = {}
            
            for feature_name in feature_names:
                value = None
                
                # Try Double first
                value_double = props.getFeatureAsDouble(feature_name)
                if value_double.is_initialized():
                    value = value_double.get()
                else:
                    # Try Integer
                    value_int = props.getFeatureAsInteger(feature_name)
                    if value_int.is_initialized():
                        value = value_int.get()
                    else:
                        # Try String
                        value_str = props.getFeatureAsString(feature_name)
                        if value_str.is_initialized():
                            value = value_str.get()
                
                if value is not None:
                    item[feature_name] = value
            
            if item:
                item["construction_handle"] = construction.handle().__str__()
                props_data.append(item)
    
    props_df = pd.DataFrame(props_data) if props_data else pd.DataFrame()
    
    # Extract energy results from eplustbl.html file
    scenario_name = osm_path.stem
    run_dir = osm_path.parent / f"run_{scenario_name[4:]}"  # Remove 'out_' prefix
    
    # Try multiple possible eplustbl.html locations
    eplustbl_paths = [
        run_dir / "run" / "eplustbl.html",
        run_dir / "reports" / "eplustbl.html",
        run_dir / "eplustbl.html"
    ]
    
    energy_data = {}
    eplustbl_path = None
    for possible_path in eplustbl_paths:
        if possible_path.exists():
            eplustbl_path = possible_path
            break
    
    if eplustbl_path and eplustbl_path.exists():
        try:
            # Parse EnergyPlus HTML report
            html_text = eplustbl_path.read_text(encoding="utf-8", errors="ignore")
            
            # Use inline parsing functions
            import re
            def extract_field(pattern, text):
                m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                return m.group(1).strip() if m else ""
            
            def extract_building_string(text):
                m = re.search(r'Building:\s*<b>([^<]+)</b>', text, flags=re.IGNORECASE)
                if m:
                    return m.group(1).strip()
                return ""
            
            energy_data["building_name"] = extract_building_string(html_text)
            energy_data["environment"] = extract_field(r'Environment:\s*<b>([^<]+)</b>', html_text)
            energy_data["simulation_hours"] = extract_field(r'Values gathered over\s+([0-9.]+)\s+hours', html_text)
            energy_data["total_site_energy_GJ"] = extract_field(r'Total Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            energy_data["net_site_energy_GJ"] = extract_field(r'Net Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            energy_data["total_source_energy_GJ"] = extract_field(r'Total Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            energy_data["net_source_energy_GJ"] = extract_field(r'Net Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            energy_data["total_building_area_m2"] = extract_field(r'Total Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            energy_data["net_conditioned_building_area_m2"] = extract_field(r'Net Conditioned Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
            
            # Extract End Uses data
            # Pattern explanation: After "Total End Uses", capture electricity (1st td), natural gas (2nd td), and water (14th/last td)
            energy_data["total_end_uses_electricity_GJ"] = extract_field(
                r'Total End Uses</td>\s*<td[^>]*>\s*([0-9.]+)\s*</td>', html_text)
            energy_data["total_end_uses_natural_gas_GJ"] = extract_field(
                r'Total End Uses</td>\s*<td[^>]*>\s*[0-9.]+\s*</td>\s*<td[^>]*>\s*([0-9.]+)\s*</td>', html_text)
            
            # Water is in the 14th column (last column before </tr>)
            # Match Total End Uses, then skip 13 columns, then capture the 14th value
            water_pattern = r'Total End Uses</td>' + r'(?:\s*<td[^>]*>\s*[0-9.]+\s*</td>)' * 13 + r'\s*<td[^>]*>\s*([0-9.]+)\s*</td>'
            energy_data["total_end_uses_water_m3"] = extract_field(water_pattern, html_text)
            
            # Debug: Print End Uses values
            print(f"  DEBUG - End Uses parsed:")
            print(f"    Electricity: {energy_data.get('total_end_uses_electricity_GJ', 'N/A')}")
            print(f"    Natural Gas: {energy_data.get('total_end_uses_natural_gas_GJ', 'N/A')}")
            print(f"    Water: {energy_data.get('total_end_uses_water_m3', 'N/A')}")
            
            # Calculate total operational carbon
            try:
                elec_gj = float(energy_data.get('total_end_uses_electricity_GJ', 0) or 0)
                gas_gj = float(energy_data.get('total_end_uses_natural_gas_GJ', 0) or 0)
                water_m3 = float(energy_data.get('total_end_uses_water_m3', 0) or 0)
                
                total_operational_carbon = (
                    elec_gj * emission_factors['elec_emission_factor'] +
                    gas_gj * emission_factors['gas_emission_factor'] +
                    water_m3 * emission_factors['water_emission_factor']
                )
                
                energy_data['total_operational_carbon_kgCO2e'] = f"{total_operational_carbon:.2f}"
                print(f"  ✓ Operational carbon calculated: {total_operational_carbon:.2f} kgCO2e")
                print(f"    = {elec_gj:.2f} GJ × {emission_factors['elec_emission_factor']:.2f}")
                print(f"    + {gas_gj:.2f} GJ × {emission_factors['gas_emission_factor']:.2f}")
                print(f"    + {water_m3:.2f} m³ × {emission_factors['water_emission_factor']:.2f}")
            except (ValueError, TypeError, KeyError) as e:
                print(f"  ⚠ Could not calculate operational carbon: {e}")
                energy_data['total_operational_carbon_kgCO2e'] = ''
            
            # Check if we actually got any data
            non_empty_fields = sum(1 for v in energy_data.values() if v)
            if non_empty_fields > 0:
                print(f"✓ Energy data extracted from HTML: {non_empty_fields}/{len(energy_data)} fields")
            else:
                print(f"  ⚠ No EnergyPlus data extracted from HTML")
                energy_data = {}
                
        except Exception as e:
            print(f"  ⚠ Error reading HTML: {str(e)[:100]}")
            energy_data = {}
    else:
        print(f"  ⚠ eplustbl.html not found in run directory")
    
    return props_df, energy_data

def create_scatterplot(csv_path, measure_dir):
    """Create a scatterplot with dual y-axes showing energy and carbon vs insulation R-value."""
    print(f"\n{'='*80}")
    print("Creating scatterplot...")
    print(f"{'='*80}")
    print(f"  DEBUG: CSV path = {csv_path}")
    print(f"  DEBUG: CSV exists = {os.path.exists(csv_path)}")
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("✗ matplotlib not found. Installing matplotlib...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import numpy as np
            print("✓ matplotlib installed successfully")
        except Exception as e:
            print(f"✗ Failed to install matplotlib: {e}")
            print("  Skipping plot generation")
            return
    
    import pandas as pd
    import re
    
    # Read CSV file - it has two sections
    try:
        # Read the entire file to find section boundaries
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Roof Construction AdditionalProperties' in line:
                construction_start = i + 1
            elif '# EnergyPlus Simulation Summary' in line:
                energyplus_start = i + 1
        
        # Read construction section
        construction_lines = []
        if construction_start is not None:
            i = construction_start
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                construction_lines.append(lines[i])
                i += 1
        
        # Read energyplus section
        energyplus_lines = []
        if energyplus_start is not None:
            i = energyplus_start
            while i < len(lines) and lines[i].strip():
                energyplus_lines.append(lines[i])
                i += 1
        
        # Parse both sections
        from io import StringIO
        construction_df = pd.read_csv(StringIO(''.join(construction_lines)))
        construction_df = construction_df.set_index(construction_df.columns[0]).T
        
        energyplus_df = pd.read_csv(StringIO(''.join(energyplus_lines)))
        energyplus_df = energyplus_df.set_index(energyplus_df.columns[0]).T
        
        # Merge both dataframes
        df = pd.concat([construction_df, energyplus_df], axis=1)
        
        print(f"  ✓ Read {len(df)} scenarios from CSV")
        print(f"  Construction columns: {list(construction_df.columns)[:3]}...")
        print(f"  EnergyPlus columns: {list(energyplus_df.columns)[:3]}...")
        print(f"  Merged df has columns: {list(df.columns)[:5]}...")
        print(f"  Checking for required columns:")
        print(f"    - total_embodied_carbon_kgCO2eq: {'total_embodied_carbon_kgCO2eq' in df.columns}")
        print(f"    - insulation_material_type: {'insulation_material_type' in df.columns}")
        print(f"    - total_site_energy_GJ: {'total_site_energy_GJ' in df.columns}")
        
        # Sample data for first scenario
        if len(df) > 0:
            first_scenario = df.index[0]
            print(f"  Sample data for {first_scenario}:")
            print(f"    Carbon: {df.loc[first_scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else 'NOT FOUND'}")
            print(f"    Material: {df.loc[first_scenario, 'insulation_material_type'] if 'insulation_material_type' in df.columns else 'NOT FOUND'}")
            print(f"    Energy: {df.loc[first_scenario, 'total_site_energy_GJ'] if 'total_site_energy_GJ' in df.columns else 'NOT FOUND'}")
        
    except Exception as e:
        print(f"✗ Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Extract data for plotting
    r_values = []
    carbon_values = []
    energy_values = []
    scenario_names = []
    material_types = []
    
    print(f"  Processing {len(df)} scenarios from CSV...")
    
    for scenario in df.index:
        try:
            # Extract R-value from scenario name
            r_value_match = re.search(r'R(\d+\.?\d*)', scenario)
            r_value = float(r_value_match.group(1)) if r_value_match else None
            
            # Get carbon and material from construction data
            carbon = df.loc[scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else None
            material_type = df.loc[scenario, 'insulation_material_type'] if 'insulation_material_type' in df.columns else 'Unknown'
            energy = df.loc[scenario, 'total_site_energy_GJ'] if 'total_site_energy_GJ' in df.columns else None
            
            print(f"  {scenario}: R={r_value}, Carbon={carbon}, Energy={energy}, Material={material_type}")
            
            # Convert to proper types
            if carbon is not None and not pd.isna(carbon):
                carbon = float(carbon)
            else:
                carbon = None
                
            if energy is not None and not pd.isna(energy):
                energy = float(energy)
            else:
                energy = None
            
            # Debug: Print first few values
            if len(r_values) < 3:
                print(f"  {scenario}: R={r_value}, Carbon={carbon}, Energy={energy}, Material={material_type}")
            
            # Add to lists if all values are valid
            if r_value is not None and carbon is not None and energy is not None and r_value >= 0:
                r_values.append(r_value)
                carbon_values.append(carbon)
                energy_values.append(energy)
                scenario_names.append(scenario)
                material_types.append(material_type)
        except Exception as e:
            print(f"  ⚠ Error processing {scenario}: {e}")
            continue
    
    if not r_values:
        print("✗ No valid data found for plotting")
        return
    
    # Define color map for insulation materials (includes all 11 material types from the measure)
    material_colors = {
        'Blown Cellulose': '#bcbd22',  # yellow-green
        'Blown Fiberglass': '#17becf',  # cyan
        'Blown Mineral Wool': '#aec7e8',  # light blue
        'Expanded Polystyrene (EPS) Foam Board': '#1f77b4',  # blue
        'Extruded Polystyrene (XPS) Foam Board': '#ff7f0e',  # orange
        'Fiberglass Batts': '#2ca02c',  # green
        'Graphite Polystyrene (GPS) Foam Board': '#d62728',  # red
        'Mineral Wool Heavy Density Blanket': '#9467bd',  # purple
        'Mineral Wool Light Density Blanket': '#8c564b',  # brown
        'Polyiso Insulation Foam Board': '#e377c2',  # pink
        'Pure Wool Batts': '#7f7f7f',  # gray
    }
    
    # Create figure with dual y-axes
    fig, ax1 = plt.subplots(figsize=(14, 8))
    ax2 = ax1.twinx()  # Create second y-axis for carbon
    
    # First, plot site energy on left axis (primary)
    color1 = 'tab:blue'
    ax1.set_xlabel('Target Insulation R-Value (IP)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Total Site Energy (GJ)', color=color1, fontsize=12, fontweight='bold')
    
    # Check if we have energy data
    energy_with_data = [e for e in energy_values if e is not None]
    if energy_with_data:
        # Plot site energy as a single series
        r_with_energy = [r for r, e in zip(r_values, energy_values) if e is not None]
        e_with_data = [e for e in energy_values if e is not None]
        
        # Debug: Check for unique energy values per R-value
        unique_r_values = sorted(set(r_with_energy))
        print(f"\n  Energy data summary:")
        for r_val in unique_r_values:
            energy_at_r = [e for r, e in zip(r_with_energy, e_with_data) if r == r_val]
            print(f"    R={r_val:.1f}: {len(energy_at_r)} data points, energy={energy_at_r[0]:.2f} GJ")
        
        ax1.scatter(r_with_energy, e_with_data, color=color1, s=100, alpha=0.6, 
                   label='Site Energy', marker='o', zorder=3)
        ax1.tick_params(axis='y', labelcolor=color1)
        
        # Add trendline for site energy
        if len(r_with_energy) >= 2:
            z1 = np.polyfit(r_with_energy, e_with_data, 1)  # Linear fit
            p1 = np.poly1d(z1)
            r_sorted = np.sort(np.unique(r_with_energy))
            ax1.plot(r_sorted, p1(r_sorted), color=color1, linestyle='--', linewidth=2, 
                    alpha=0.8, label=f'Energy Trend (slope={z1[0]:.2f})', zorder=2)
    
    ax1.grid(True, alpha=0.3)
    
    # Plot embodied carbon on right axis with different colors for each material type
    ax2.set_ylabel('Total Embodied Carbon (kgCO2eq)', fontsize=12, fontweight='bold')
    
    for material in material_colors.keys():
        # Filter data for this material
        mask = [mat == material for mat in material_types]
        r_vals_mat = [r for r, m in zip(r_values, mask) if m]
        carbon_vals_mat = [c for c, m in zip(carbon_values, mask) if m]
        
        if r_vals_mat:  # Only plot if there's data for this material
            # Simplify legend labels
            label = material.replace(' Foam Board', '').replace(' Blanket', '').replace(' Batts', '')
            
            # Plot embodied carbon with material-specific colors
            ax2.scatter(r_vals_mat, carbon_vals_mat, 
                       color=material_colors[material], 
                       s=100, alpha=0.7, 
                       label=label,
                       marker='s',  # Square markers for carbon
                       edgecolors='black', 
                       linewidths=0.5,
                       zorder=3)
            
            # Add trendline for each material type if there are at least 2 points
            if len(r_vals_mat) >= 2:
                z_mat = np.polyfit(r_vals_mat, carbon_vals_mat, 1)  # Linear fit
                p_mat = np.poly1d(z_mat)
                r_mat_sorted = np.sort(r_vals_mat)
                ax2.plot(r_mat_sorted, p_mat(r_mat_sorted), 
                        color=material_colors[material], 
                        linestyle='--', linewidth=1.5, alpha=0.6, zorder=2)
    
    ax2.tick_params(axis='y')
    
    # Configure plot
    ax1.set_xlabel('Target Insulation R-Value (IP)', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    # Add title
    plt.title('Energy and Carbon Impact vs. Roof Insulation R-Value', fontsize=14, fontweight='bold', pad=20)
    
    # Add legends - Site Energy on left, Materials on right
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc='upper left', fontsize=10, title='Operational Energy')
    
    # Material legend on the right side
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines2, labels2, loc='upper right', fontsize=9, title='Insulation Material', ncol=1)
    
    # Adjust layout to prevent label cutoff
    fig.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "roof_insulation_carbon_impact.png"
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_plot, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Scatterplot saved: {output_plot}")
    print(f"  Data points plotted: {len(r_values)}")
    print(f"  R-value range: {min(r_values):.1f} - {max(r_values):.1f}")
    print(f"  Carbon range: {min(carbon_values):.2f} - {max(carbon_values):.2f} kgCO2eq")
    
    energy_with_data = [e for e in energy_values if e is not None]
    if energy_with_data:
        print(f"  Energy range: {min(energy_with_data):.2f} - {max(energy_with_data):.2f} GJ")
        print(f"  Energy data points: {len(energy_with_data)}/{len(energy_values)}")
    else:
        print(f"  ⚠ No energy data available - run simulations with apply_measure.py first")

def create_carbon_comparison_plot(csv_path, measure_dir):
    """Create a scatterplot with dual y-axes showing operational carbon and embodied carbon vs insulation R-value."""
    print(f"\n{'='*80}")
    print("Creating carbon comparison plot...")
    print(f"{'='*80}")
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("✗ matplotlib not found. Skipping carbon comparison plot.")
        return
    
    import pandas as pd
    import re
    
    # Read CSV file - it has two sections
    try:
        # Read the entire file to find section boundaries
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Roof Construction AdditionalProperties' in line:
                construction_start = i + 1
            elif '# EnergyPlus Simulation Summary' in line:
                energyplus_start = i + 1
        
        # Read construction section
        construction_lines = []
        if construction_start is not None:
            i = construction_start
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                construction_lines.append(lines[i])
                i += 1
        
        # Read energyplus section
        energyplus_lines = []
        if energyplus_start is not None:
            i = energyplus_start
            while i < len(lines) and lines[i].strip():
                energyplus_lines.append(lines[i])
                i += 1
        
        # Parse both sections
        from io import StringIO
        construction_df = pd.read_csv(StringIO(''.join(construction_lines)))
        construction_df = construction_df.set_index(construction_df.columns[0]).T
        
        energyplus_df = pd.read_csv(StringIO(''.join(energyplus_lines)))
        energyplus_df = energyplus_df.set_index(energyplus_df.columns[0]).T
        
        # Merge both dataframes
        df = pd.concat([construction_df, energyplus_df], axis=1)
        
        print(f"  ✓ Read {len(df)} scenarios from CSV")
        
    except Exception as e:
        print(f"✗ Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Extract data for plotting
    r_values = []
    embodied_carbon_values = []
    operational_carbon_values = []
    scenario_names = []
    material_types = []
    
    print(f"  Processing {len(df)} scenarios with carbon data from CSV...")
    
    for scenario in df.index:
        try:
            # Extract R-value from scenario name
            r_value_match = re.search(r'R(\d+\.?\d*)', scenario)
            r_value = float(r_value_match.group(1)) if r_value_match else None
            
            # Get carbon values and material from CSV
            embodied_carbon = df.loc[scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else None
            operational_carbon = df.loc[scenario, 'total_operational_carbon_kgCO2e'] if 'total_operational_carbon_kgCO2e' in df.columns else None
            material_type = df.loc[scenario, 'insulation_material_type'] if 'insulation_material_type' in df.columns else 'Unknown'
            
            # Convert to proper types
            if embodied_carbon is not None and not pd.isna(embodied_carbon):
                embodied_carbon = float(embodied_carbon)
            else:
                embodied_carbon = None
                
            if operational_carbon is not None and not pd.isna(operational_carbon):
                operational_carbon = float(operational_carbon)
            else:
                operational_carbon = None
            
            # Add to lists if all values are valid
            if r_value is not None and embodied_carbon is not None and operational_carbon is not None and r_value >= 0:
                r_values.append(r_value)
                embodied_carbon_values.append(embodied_carbon)
                operational_carbon_values.append(operational_carbon)
                scenario_names.append(scenario)
                material_types.append(material_type)
        except Exception as e:
            print(f"  ⚠ Error processing {scenario}: {e}")
            continue
    
    if not r_values:
        print("✗ No valid carbon data found for plotting")
        return
    
    # Define color map for insulation materials
    material_colors = {
        'Blown Cellulose': '#bcbd22',
        'Blown Fiberglass': '#17becf',
        'Blown Mineral Wool': '#aec7e8',
        'Expanded Polystyrene (EPS) Foam Board': '#1f77b4',
        'Extruded Polystyrene (XPS) Foam Board': '#ff7f0e',
        'Fiberglass Batts': '#2ca02c',
        'Graphite Polystyrene (GPS) Foam Board': '#d62728',
        'Mineral Wool Heavy Density Blanket': '#9467bd',
        'Mineral Wool Light Density Blanket': '#8c564b',
        'Polyiso Insulation Foam Board': '#e377c2',
        'Pure Wool Batts': '#7f7f7f',
    }
    
    # Create figure with dual y-axes
    fig, ax1 = plt.subplots(figsize=(14, 8))
    ax2 = ax1.twinx()
    
    # Left axis: Operational Carbon (blue)
    color1 = 'tab:blue'
    ax1.set_xlabel('Target Insulation R-Value (IP)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Operational Carbon (kgCO2e)', color=color1, fontsize=12, fontweight='bold')
    
    # Plot operational carbon as single series (same for all materials at same R-value)
    unique_r_values = sorted(set(r_values))
    print(f"\n  Operational Carbon data summary:")
    for r_val in unique_r_values:
        op_carbon_at_r = [oc for r, oc in zip(r_values, operational_carbon_values) if r == r_val]
        if op_carbon_at_r:
            print(f"    R={r_val:.1f}: {op_carbon_at_r[0]:.2f} kgCO2e")
    
    ax1.scatter(r_values, operational_carbon_values, color=color1, s=100, alpha=0.6,
               label='Operational Carbon', marker='o', zorder=3)
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Add trendline for operational carbon
    if len(r_values) >= 2:
        z1 = np.polyfit(r_values, operational_carbon_values, 1)
        p1 = np.poly1d(z1)
        r_sorted = np.sort(unique_r_values)
        ax1.plot(r_sorted, p1(r_sorted), color=color1, linestyle='--', linewidth=2,
                alpha=0.8, label=f'Op. Carbon Trend (slope={z1[0]:.2f})', zorder=2)
    
    ax1.grid(True, alpha=0.3)
    
    # Right axis: Embodied Carbon with material-specific colors
    ax2.set_ylabel('Embodied Carbon (kgCO2e)', fontsize=12, fontweight='bold')
    
    for material in material_colors.keys():
        # Filter data for this material
        mask = [mat == material for mat in material_types]
        r_vals_mat = [r for r, m in zip(r_values, mask) if m]
        embodied_vals_mat = [ec for ec, m in zip(embodied_carbon_values, mask) if m]
        
        if r_vals_mat:
            # Simplify legend labels
            label = material.replace(' Foam Board', '').replace(' Blanket', '').replace(' Batts', '')
            
            # Plot embodied carbon with material-specific colors
            ax2.scatter(r_vals_mat, embodied_vals_mat,
                       color=material_colors[material],
                       s=100, alpha=0.7,
                       label=label,
                       marker='s',  # Square markers for embodied carbon
                       edgecolors='black',
                       linewidths=0.5,
                       zorder=3)
            
            # Add trendline for each material type
            if len(r_vals_mat) >= 2:
                z_mat = np.polyfit(r_vals_mat, embodied_vals_mat, 1)
                p_mat = np.poly1d(z_mat)
                r_mat_sorted = np.sort(r_vals_mat)
                ax2.plot(r_mat_sorted, p_mat(r_mat_sorted),
                        color=material_colors[material],
                        linestyle='--', linewidth=1.5, alpha=0.6, zorder=2)
    
    ax2.tick_params(axis='y')
    
    # Add title
    plt.title('Operational vs Embodied Carbon Impact', fontsize=14, fontweight='bold', pad=20)
    
    # Add legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc='upper left', fontsize=10, title='Operational Carbon')
    
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines2, labels2, loc='upper right', fontsize=9, title='Embodied Carbon by Material', ncol=1)
    
    # Adjust layout
    fig.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "roof_insulation_carbon_comparison.png"
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_plot, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Carbon comparison plot saved: {output_plot}")
    print(f"  Data points plotted: {len(r_values)}")
    print(f"  R-value range: {min(r_values):.1f} - {max(r_values):.1f}")
    print(f"  Operational carbon range: {min(operational_carbon_values):.2f} - {max(operational_carbon_values):.2f} kgCO2e")
    print(f"  Embodied carbon range: {min(embodied_carbon_values):.2f} - {max(embodied_carbon_values):.2f} kgCO2e")

def create_stacked_bar_chart(csv_path, measure_dir):
    """Create a stacked bar chart showing operational and embodied carbon for all scenarios."""
    print(f"\n{'='*80}")
    print("Creating stacked bar chart...")
    print(f"{'='*80}")
    
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("✗ matplotlib not found. Skipping stacked bar chart generation")
        return
    
    import pandas as pd
    import re
    
    # Read CSV file - it has two sections
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Roof Construction AdditionalProperties' in line:
                construction_start = i + 1
            elif '# EnergyPlus Simulation Summary' in line:
                energyplus_start = i + 1
        
        # Read construction section
        construction_lines = []
        if construction_start is not None:
            i = construction_start
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                construction_lines.append(lines[i])
                i += 1
        
        # Read energyplus section
        energyplus_lines = []
        if energyplus_start is not None:
            i = energyplus_start
            while i < len(lines) and lines[i].strip():
                energyplus_lines.append(lines[i])
                i += 1
        
        # Parse both sections
        from io import StringIO
        construction_df = pd.read_csv(StringIO(''.join(construction_lines)))
        construction_df = construction_df.set_index(construction_df.columns[0]).T
        
        energyplus_df = pd.read_csv(StringIO(''.join(energyplus_lines)))
        energyplus_df = energyplus_df.set_index(energyplus_df.columns[0]).T
        
        # Merge both dataframes
        df = pd.concat([construction_df, energyplus_df], axis=1)
        
        print(f"  ✓ Read {len(df)} scenarios from CSV")
        
    except Exception as e:
        print(f"✗ Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Extract data for plotting
    scenario_names = []
    operational_carbon = []
    embodied_carbon = []
    
    print(f"  Processing {len(df)} scenarios from CSV...")
    
    for scenario in df.index:
        try:
            # Get carbon values
            op_carbon = df.loc[scenario, 'total_operational_carbon_kgCO2e'] if 'total_operational_carbon_kgCO2e' in df.columns else None
            em_carbon = df.loc[scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else None
            
            # Convert to proper types
            if op_carbon is not None and not pd.isna(op_carbon):
                op_carbon = float(op_carbon)
            else:
                op_carbon = 0.0
                
            if em_carbon is not None and not pd.isna(em_carbon):
                em_carbon = float(em_carbon)
            else:
                em_carbon = 0.0
            
            scenario_names.append(scenario)
            operational_carbon.append(op_carbon)
            embodied_carbon.append(em_carbon)
            
        except Exception as e:
            print(f"  ⚠ Error processing {scenario}: {e}")
    
    if not scenario_names:
        print("✗ No valid data found for plotting")
        return
    
    # Group scenarios by R-value
    r_value_groups = {}
    for scenario, op_carbon, em_carbon in zip(scenario_names, operational_carbon, embodied_carbon):
        r_match = re.search(r'R(\d+\.?\d*)', scenario)
        if r_match:
            r_val = float(r_match.group(1))
            if r_val not in r_value_groups:
                r_value_groups[r_val] = {'scenarios': [], 'op_carbon': [], 'em_carbon': []}
            r_value_groups[r_val]['scenarios'].append(scenario)
            r_value_groups[r_val]['op_carbon'].append(op_carbon)
            r_value_groups[r_val]['em_carbon'].append(em_carbon)
    
    # Sort R-values for consistent ordering
    sorted_r_values = sorted(r_value_groups.keys())
    n_subplots = len(sorted_r_values)
    
    # Determine subplot layout (e.g., 2 rows, n cols to fit all R-values)
    n_cols = min(3, n_subplots)  # Max 3 columns
    n_rows = (n_subplots + n_cols - 1) // n_cols  # Ceiling division
    
    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(8 * n_cols, 6 * n_rows))
    
    # Handle case where there's only one subplot
    if n_subplots == 1:
        axes = np.array([axes])
    axes = axes.flatten() if n_subplots > 1 else axes
    
    # Find global min/max for consistent y-axis scaling
    all_totals = []
    for r_val in sorted_r_values:
        group = r_value_groups[r_val]
        totals = [(op + em) / 1000 for op, em in zip(group['op_carbon'], group['em_carbon'])]
        all_totals.extend(totals)
    y_max = max(all_totals) * 1.1  # Add 10% margin
    
    # Create a subplot for each R-value
    for idx, r_val in enumerate(sorted_r_values):
        ax = axes[idx]
        group = r_value_groups[r_val]
        
        # Get data for this R-value and sort by embodied carbon (low to high)
        scenarios = group['scenarios']
        op_carbon = group['op_carbon']
        em_carbon = group['em_carbon']
        
        # Sort by embodied carbon values
        sorted_data = sorted(zip(em_carbon, scenarios, op_carbon))
        em_carbon_sorted, scenarios_sorted, op_carbon_sorted = zip(*sorted_data)
        
        scenarios = list(scenarios_sorted)
        op_carbon_tons = [oc / 1000 for oc in op_carbon_sorted]
        em_carbon_tons = [ec / 1000 for ec in em_carbon_sorted]
        
        # Set up x-axis positions
        x_pos = np.arange(len(scenarios))
        
        # Create stacked bars
        # Bottom: Operational carbon (blue)
        bars1 = ax.bar(x_pos, op_carbon_tons, 
                       color='#4472C4', label='Operational Carbon',
                       edgecolor='white', linewidth=0.5)
        
        # Top: Embodied carbon (orange)
        bars2 = ax.bar(x_pos, em_carbon_tons, bottom=op_carbon_tons,
                       color='#ED7D31', label='Embodied Carbon',
                       edgecolor='white', linewidth=0.5)
        
        # Customize subplot
        ax.set_xlabel('Insulation Material', fontsize=10, fontweight='bold')
        ax.set_ylabel('Carbon (ton CO2e)', fontsize=10, fontweight='bold')
        ax.set_title(f'Target R-Value = {r_val:.1f}', fontsize=12, fontweight='bold', pad=10)
        
        # Extract material names from scenario names (remove R-value prefix)
        material_labels = []
        for scenario in scenarios:
            # Remove "out_R##_" prefix to get material name
            material = re.sub(r'^out_R\d+\.?\d*_', '', scenario)
            material_labels.append(material)
        
        # Set x-axis labels
        ax.set_xticks(x_pos)
        ax.set_xticklabels(material_labels, rotation=45, ha='right', fontsize=9)
        
        # Set consistent y-axis limits
        ax.set_ylim(0, y_max)
        
        # Add legend to first subplot only
        if idx == 0:
            ax.legend(loc='upper right', frameon=True, shadow=True, fontsize=10)
        
        # Add grid
        ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Format y-axis
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    
    # Hide unused subplots
    for idx in range(n_subplots, len(axes)):
        axes[idx].axis('off')
    
    # Add main title
    fig.suptitle('Operational and Embodied Carbon by Target R-Value and Material', 
                 fontsize=16, fontweight='bold', y=0.995)
    
    # Tight layout
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    
    # Save the plot
    output_plot = measure_dir / "resources" / "roof_insulation_stacked_bar.png"
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_plot, dpi=300, bbox_inches='tight')
    plt.close()
    
    # Calculate statistics
    total_carbon = [op + em for op, em in zip(operational_carbon, embodied_carbon)]
    
    print(f"✓ Stacked bar chart saved: {output_plot}")
    print(f"  Scenarios plotted: {len(scenario_names)}")
    print(f"  Operational carbon range: {min(operational_carbon):.2f} - {max(operational_carbon):.2f} kgCO2e")
    print(f"  Embodied carbon range: {min(embodied_carbon):.2f} - {max(embodied_carbon):.2f} kgCO2e")
    print(f"  Total carbon range: {min(total_carbon):.2f} - {max(total_carbon):.2f} kgCO2e")

def main():
    # Find all output OSM files from the roof insulation measure
    output_dir = Path(__file__).parent / "tests" / "output"
    
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        print("\nPlease run the apply_measure.py script first.")
        sys.exit(1)
    
    # Find all OSM files matching the pattern out_R*_*.osm
    osm_files = sorted(output_dir.glob("out_R*.osm"))
    
    if not osm_files:
        print(f"Error: No output OSM files found in {output_dir}")
        print("Expected files matching pattern: out_R*.osm")
        print("\nPlease run the apply_measure.py script first.")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Found {len(osm_files)} output model(s) to process")
    print(f"{'='*80}")
    for osm_file in osm_files:
        print(f"  - {osm_file.name}")
    
    # Load emission factors once
    print(f"\n{'='*80}")
    print("Loading emission factors...")
    print(f"{'='*80}")
    emission_factors = load_emission_factors()
    
    # Track results
    all_model_data = []
    all_energy_data = []  # List to store energy data (not dict)
    successful = 0
    failed = 0
    
    # Process each model and collect data
    for idx, osm_path in enumerate(osm_files, 1):
        print(f"\n[Model {idx}/{len(osm_files)}]")
        
        props_df, energy_data = extract_model_data(osm_path, emission_factors)
        
        if props_df is not None and not props_df.empty:
            # Add scenario identifier column
            props_df['scenario_name'] = osm_path.stem
            
            all_model_data.append(props_df)
            
            # Store energy data if available
            if energy_data:
                energy_data['scenario_name'] = osm_path.stem
                all_energy_data.append(energy_data)
            
            print(f"✓ Data extracted successfully from {osm_path.name}")
            successful += 1
        else:
            failed += 1
            print(f"✗ Failed to extract data from {osm_path.name}")
    
    # Combine all data into a single CSV
    if all_model_data:
        import pandas as pd
        combined_df = pd.concat(all_model_data, ignore_index=True)
        
        # Reorder columns to put scenario_name first
        cols = combined_df.columns.tolist()
        if 'scenario_name' in cols:
            cols.remove('scenario_name')
            cols = ['scenario_name'] + cols
            combined_df = combined_df[cols]
        
        # Save combined report with both sections
        output_csv = measure_dir / "resources" / "roof_insulation_report.csv"
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_csv, 'w', newline='', encoding='utf-8') as f:
                # First, write Construction AdditionalProperties section (transposed and reversed)
                f.write("# Roof Construction AdditionalProperties\n")
                
                construction_transposed = combined_df.set_index('scenario_name').T
                construction_transposed = construction_transposed.iloc[::-1]
                construction_transposed.to_csv(f)
                f.write("\n")
                
                # Second, write EnergyPlus Simulation Summary section
                if all_energy_data:
                    f.write("# EnergyPlus Simulation Summary\n")
                    
                    # Convert energy data list to DataFrame
                    energyplus_df = pd.DataFrame(all_energy_data)
                    energyplus_transposed = energyplus_df.set_index('scenario_name').T
                    energyplus_transposed.to_csv(f)
            
            construction_features = len(combined_df.columns) - 1  # -1 for scenario_name
            energyplus_metrics = len(all_energy_data[0]) - 1 if all_energy_data else 0  # -1 for scenario_name
            
            print(f"\n✓ Combined report saved: {output_csv}")
            print(f"  Scenarios: {len(all_model_data)}")
            print(f"  Construction features: {construction_features}")
            if all_energy_data:
                print(f"  EnergyPlus metrics: {energyplus_metrics}")
        
        except PermissionError:
            print(f"\n✗ ERROR: Cannot write to {output_csv}")
            print(f"  The file may be open in Excel or another program.")
            print(f"  Please close the file and run this script again.")
            return 1
        
        # Create scatterplot with energy data
        create_scatterplot(output_csv, measure_dir)
        
        # Create carbon comparison plot
        create_carbon_comparison_plot(output_csv, measure_dir)
        
        # Create stacked bar chart
        create_stacked_bar_chart(output_csv, measure_dir)
    
    # Print final summary
    print(f"\n\n{'='*80}")
    print("PROCESSING SUMMARY")
    print(f"{'='*80}")
    print(f"Total models processed: {len(osm_files)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nSuccess rate: {successful/len(osm_files)*100:.1f}%")
    
    if all_model_data:
        print(f"\n✓ All scenario data combined into single CSV:")
        print(f"  {output_csv}")
    
    print(f"{'='*80}\n")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

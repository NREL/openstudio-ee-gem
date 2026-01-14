"""
Apply reporting measure to extract AdditionalProperties from window enhancement models and parse EnergyPlus simulation results.

Usage:
    python apply_reporting_measure_window_enhancement.py
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

def run_energyplus_simulation(osm_path):
    """Run EnergyPlus simulation for an OSM file."""
    print(f"  Running EnergyPlus simulation...")
    
    import subprocess
    
    try:
        # Load the model to get weather file
        translator = openstudio.osversion.VersionTranslator()
        model_opt = translator.loadModel(str(osm_path))
        
        if not model_opt.is_initialized():
            print(f"  ✗ Could not load model for simulation")
            return False
        
        model = model_opt.get()
        
        # Create output directory for this scenario
        scenario_name = osm_path.stem
        run_dir = osm_path.parent / f"run_{scenario_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Use the specified weather file
        weather_file_path = Path(__file__).parent / "tests" / "USA_CO_Denver-Aurora-Buckley.AFB_.724695_TMY3.epw"
        
        if not weather_file_path.exists():
            print(f"  ⚠ Weather file not found: {weather_file_path}")
            return False
        
        weather_file_path = str(weather_file_path.absolute())
        print(f"    Using weather file: {weather_file_path}")
        
        # Create a simple workflow JSON file
        workflow_dict = {
            "seed_file": str(osm_path.name),
            "weather_file": weather_file_path,
            "measure_paths": [],
            "steps": []
        }
        
        import json
        workflow_path = run_dir / "in.osw"
        with open(workflow_path, 'w') as f:
            json.dump(workflow_dict, f, indent=2)
        
        # Copy OSM file to run directory
        import shutil
        osm_dest = run_dir / osm_path.name
        shutil.copy(str(osm_path), str(osm_dest))
        
        # Run the workflow using OpenStudio CLI
        print(f"    Running simulation in: {run_dir}")
        
        result = subprocess.run(
            ["openstudio", "run", "-w", str(workflow_path)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode == 0:
            print(f"  ✓ Simulation completed successfully")
            return True
        else:
            print(f"  ✗ Simulation failed with return code {result.returncode}")
            if result.stderr:
                print(f"    Error: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Simulation timeout (>10 minutes)")
        return False
    except Exception as e:
        print(f"  ✗ Simulation error: {e}")
        return False

def extract_model_data(osm_path, emission_factors):
    """Extract Building AdditionalProperties from OSM file and energy results from SQL file."""
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
    building = model.getBuilding()
    print(f"✓ Model loaded successfully")
    
    # Extract Building AdditionalProperties for window enhancement
    import pandas as pd
    
    building_props = building.additionalProperties()
    feature_names = building_props.featureNames()
    
    # Filter for window_enhancement properties
    window_enhancement_props = {}
    window_enhancement_features = [
        # Basic measure parameters
        'window_enhancement_analysis_period_years',
        'window_enhancement_glass_lifetime_years',
        'window_enhancement_frame_lifetime_years',
        'window_enhancement_caulking_lifetime_years',
        'window_enhancement_film_lifetime_years',
        'window_enhancement_weatherstrip_lifetime_years',
        'window_enhancement_gwp_statistic',
        'window_enhancement_infiltration_reduction_percent',
        
        # Renovation options selected
        'window_enhancement_frame_option',
        'window_enhancement_caulking_option',
        'window_enhancement_film_option',
        'window_enhancement_weatherstrip_option',
        'window_enhancement_glass_option',
        'window_enhancement_secondary_glazing_option',
        
        # Glass properties
        'window_enhancement_num_panes',
        'window_enhancement_glass_pane_thickness_m',
        'window_enhancement_gap_thickness_m',
        'window_enhancement_glass_solar_transmittance',
        'window_enhancement_glass_visible_transmittance',
        'window_enhancement_glass_front_emissivity',
        'window_enhancement_glass_back_emissivity',
        'window_enhancement_glass_front_solar_reflectance',
        'window_enhancement_glass_back_solar_reflectance',
        'window_enhancement_glass_front_visible_reflectance',
        'window_enhancement_glass_back_visible_reflectance',
        
        # Film properties
        'window_enhancement_film_visible_transmittance',
        'window_enhancement_film_solar_transmittance',
        'window_enhancement_film_thermal_emissivity',
        'window_enhancement_film_thermal_resistance_m2KperW',
        
        # Caulking properties
        'window_enhancement_caulking_thickness_m',
        
        # Weatherstrip properties
        'window_enhancement_weatherstrip_length_per_unit_m',
        
        # Divider information
        'window_enhancement_num_horizontal_dividers',
        'window_enhancement_num_vertical_dividers',
        
        # Aggregate results - Embodied carbon
        'window_enhancement_total_embodied_carbon_kgCO2eq',
        
        # Aggregate results - Material quantities
        'window_enhancement_total_window_area_m2',
        'window_enhancement_total_glazing_area_m2',
        'window_enhancement_total_frame_area_m2',
        'window_enhancement_total_perimeter_m',
        'window_enhancement_total_caulking_volume_m3',
        'window_enhancement_total_weatherstrip_length_m',
        
        # Aggregate results - Window counts
        'window_enhancement_windows_processed_count',
        'window_enhancement_windows_with_glass_upgrade_count',
        'window_enhancement_windows_with_frame_replacement_count',
        'window_enhancement_windows_with_film_count',
        'window_enhancement_windows_with_caulking_count',
        'window_enhancement_windows_with_weatherstrip_count',
        'window_enhancement_windows_with_secondary_glazing_count',
        
        # GWP values per functional unit
        'window_enhancement_glass_gwp_per_m2_kgCO2eq',
        'window_enhancement_glass_gwp_per_m3_kgCO2eq',
        'window_enhancement_frame_gwp_per_m2_kgCO2eq',
        'window_enhancement_caulking_gwp_per_m3_kgCO2eq',
        'window_enhancement_film_gwp_per_m2_kgCO2eq',
        'window_enhancement_weatherstrip_gwp_per_m_kgCO2eq',
        'window_enhancement_secondary_glazing_gwp_per_m2_kgCO2eq',
        
        # Construction information
        'window_enhancement_construction_names',
        'window_enhancement_construction_handles'
    ]
    
    print(f"  Extracting window enhancement properties...")
    for feature_name in window_enhancement_features:
        value = None
        
        # Try Double first
        value_double = building_props.getFeatureAsDouble(feature_name)
        if value_double.is_initialized():
            value = value_double.get()
        else:
            # Try Integer
            value_int = building_props.getFeatureAsInteger(feature_name)
            if value_int.is_initialized():
                value = value_int.get()
            else:
                # Try String
                value_str = building_props.getFeatureAsString(feature_name)
                if value_str.is_initialized():
                    value = value_str.get()
        
        if value is not None:
            window_enhancement_props[feature_name] = value
            print(f"    ✓ {feature_name}: {value}")
    
    # Create DataFrame with properties
    if window_enhancement_props:
        props_df = pd.DataFrame([window_enhancement_props])
        print(f"  ✓ Extracted {len(window_enhancement_props)} window enhancement properties")
    else:
        props_df = pd.DataFrame()
        print(f"  ⚠ No window enhancement properties found in building")
    
    # Extract energy results from eplustbl.html file
    scenario_name = osm_path.stem
    run_dir = osm_path.parent / f"run_{scenario_name}"
    
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
            energy_data["total_end_uses_electricity_GJ"] = extract_field(
                r'Total End Uses</td>\s*<td[^>]*>\s*([0-9.]+)\s*</td>', html_text)
            energy_data["total_end_uses_natural_gas_GJ"] = extract_field(
                r'Total End Uses</td>\s*<td[^>]*>\s*[0-9.]+\s*</td>\s*<td[^>]*>\s*([0-9.]+)\s*</td>', html_text)
            
            # Water is in the 14th column (last column before </tr>)
            water_pattern = r'Total End Uses</td>' + r'(?:\s*<td[^>]*>\s*[0-9.]+\s*</td>)' * 13 + r'\s*<td[^>]*>\s*([0-9.]+)\s*</td>'
            energy_data["total_end_uses_water_m3"] = extract_field(water_pattern, html_text)
            
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
                
                energy_data["total_operational_carbon_kgCO2e"] = total_operational_carbon
                
                print(f"  ✓ Calculated operational carbon: {total_operational_carbon:.2f} kgCO2e")
                print(f"    Electricity: {elec_gj:.2f} GJ × {emission_factors['elec_emission_factor']:.2f} = {elec_gj * emission_factors['elec_emission_factor']:.2f} kgCO2e")
                print(f"    Natural Gas: {gas_gj:.2f} GJ × {emission_factors['gas_emission_factor']:.2f} = {gas_gj * emission_factors['gas_emission_factor']:.2f} kgCO2e")
                print(f"    Water: {water_m3:.2f} m³ × {emission_factors['water_emission_factor']:.2f} = {water_m3 * emission_factors['water_emission_factor']:.2f} kgCO2e")
                
            except (ValueError, TypeError) as e:
                print(f"  ⚠ Could not calculate operational carbon: {e}")
                energy_data["total_operational_carbon_kgCO2e"] = None
            
            energy_df = pd.DataFrame([energy_data])
            print(f"  ✓ Extracted energy data from {eplustbl_path.name}")
            
        except Exception as e:
            print(f"  ⚠ Error parsing energy results: {e}")
            energy_df = pd.DataFrame()
    else:
        print(f"  ⚠ No eplustbl.html found. Skipping energy data extraction.")
        energy_df = pd.DataFrame()
    
    return props_df, energy_df

def create_carbon_comparison_plot(csv_path, measure_dir):
    """Create a scatterplot with dual y-axes showing operational carbon and embodied carbon vs infiltration reduction."""
    print(f"\n{'='*80}")
    print("Creating carbon comparison plot...")
    print(f"{'='*80}")
    
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
        except Exception as e:
            print(f"✗ Failed to install matplotlib: {e}")
            return
    
    import pandas as pd
    import re
    
    # Read CSV file (transposed format)
    try:
        df = pd.read_csv(csv_path, index_col=0, header=None)
        df = df.T  # Transpose back to normal format
        
        print(f"  ✓ Read {len(df)} scenarios from CSV")
        print(f"  Available columns: {list(df.columns)[:5]}...")
        
    except Exception as e:
        print(f"✗ Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Extract data for plotting
    infiltration_values = []
    embodied_carbon_values = []
    operational_carbon_values = []
    scenario_names = []
    
    print(f"  Processing {len(df)} scenarios from CSV...")
    
    for idx, row in df.iterrows():
        try:
            scenario = row.get('scenario_file', f'scenario_{idx}')
            
            # Extract infiltration reduction percentage
            infiltration = row.get('window_enhancement_infiltration_reduction_percent', None)
            if infiltration is None or pd.isna(infiltration):
                continue
            
            # Extract carbon values
            embodied = row.get('window_enhancement_total_embodied_carbon_kgCO2eq', None)
            operational = row.get('total_operational_carbon_kgCO2e', None)
            
            if embodied is None or pd.isna(embodied):
                continue
            if operational is None or pd.isna(operational):
                continue
            
            infiltration_values.append(float(infiltration))
            embodied_carbon_values.append(float(embodied))
            operational_carbon_values.append(float(operational))
            scenario_names.append(str(scenario))
            
        except Exception as e:
            print(f"  ⚠ Skipping scenario {idx}: {e}")
            continue
    
    if not infiltration_values:
        print("✗ No valid carbon data found for plotting")
        return
    
    # Create figure with dual y-axes
    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2 = ax1.twinx()
    
    # Left axis: Operational Carbon (blue)
    color1 = 'tab:blue'
    ax1.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Operational Carbon (kgCO2e)', color=color1, fontsize=12, fontweight='bold')
    
    # Plot operational carbon
    ax1.scatter(infiltration_values, operational_carbon_values, color=color1, s=100, alpha=0.6,
               label='Operational Carbon', marker='o', zorder=3)
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Add trendline for operational carbon
    if len(infiltration_values) >= 2:
        unique_inf = sorted(set(infiltration_values))
        z1 = np.polyfit(infiltration_values, operational_carbon_values, 1)
        p1 = np.poly1d(z1)
        ax1.plot(unique_inf, p1(unique_inf), color=color1, linestyle='--', linewidth=2,
                alpha=0.8, label=f'Op. Carbon Trend (slope={z1[0]:.2f})', zorder=2)
    
    ax1.grid(True, alpha=0.3)
    
    # Right axis: Embodied Carbon (orange)
    color2 = 'tab:orange'
    ax2.set_ylabel('Embodied Carbon (kgCO2e)', color=color2, fontsize=12, fontweight='bold')
    
    ax2.scatter(infiltration_values, embodied_carbon_values, color=color2, s=100, alpha=0.6,
               label='Embodied Carbon', marker='s', zorder=3)
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Add trendline for embodied carbon
    if len(infiltration_values) >= 2:
        z2 = np.polyfit(infiltration_values, embodied_carbon_values, 1)
        p2 = np.poly1d(z2)
        ax2.plot(unique_inf, p2(unique_inf), color=color2, linestyle='--', linewidth=2,
                alpha=0.8, label=f'Emb. Carbon Trend (slope={z2[0]:.2f})', zorder=2)
    
    # Add title
    plt.title('Operational vs Embodied Carbon by Infiltration Reduction', 
             fontsize=14, fontweight='bold', pad=20)
    
    # Add legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc='upper left', fontsize=10, title='Operational Carbon')
    
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines2, labels2, loc='upper right', fontsize=10, title='Embodied Carbon')
    
    # Adjust layout
    fig.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "window_enhancement_carbon_comparison.png"
    output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_plot, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Carbon comparison plot saved: {output_plot}")
    print(f"  Data points plotted: {len(infiltration_values)}")
    print(f"  Infiltration reduction range: {min(infiltration_values):.1f}% - {max(infiltration_values):.1f}%")
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
    
    # Read CSV file (transposed format)
    try:
        df = pd.read_csv(csv_path, index_col=0, header=None)
        df = df.T  # Transpose back to normal format
        
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
    infiltration_reduction = []
    
    print(f"  Processing {len(df)} scenarios from CSV...")
    
    for idx, row in df.iterrows():
        try:
            scenario = row.get('scenario_file', f'scenario_{idx}')
            
            # Extract carbon values
            op_carbon = row.get('total_operational_carbon_kgCO2e', None)
            em_carbon = row.get('window_enhancement_total_embodied_carbon_kgCO2eq', None)
            infiltration = row.get('window_enhancement_infiltration_reduction_percent', None)
            
            if op_carbon is None or pd.isna(op_carbon):
                continue
            if em_carbon is None or pd.isna(em_carbon):
                continue
            if infiltration is None or pd.isna(infiltration):
                continue
            
            scenario_names.append(str(scenario))
            operational_carbon.append(float(op_carbon))
            embodied_carbon.append(float(em_carbon))
            infiltration_reduction.append(float(infiltration))
            
        except Exception as e:
            print(f"  ⚠ Skipping scenario {idx}: {e}")
            continue
    
    if not scenario_names:
        print("✗ No valid data found for plotting")
        return
    
    # Sort data by infiltration reduction percentage
    sorted_data = sorted(zip(infiltration_reduction, scenario_names, operational_carbon, embodied_carbon))
    infiltration_sorted, scenarios_sorted, op_carbon_sorted, em_carbon_sorted = zip(*sorted_data)
    
    # Convert to tons for better readability
    op_carbon_tons = [oc / 1000 for oc in op_carbon_sorted]
    em_carbon_tons = [ec / 1000 for ec in em_carbon_sorted]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Set up x-axis positions
    x_pos = np.arange(len(scenarios_sorted))
    
    # Create stacked bars
    # Bottom: Operational carbon (blue)
    bars1 = ax.bar(x_pos, op_carbon_tons, 
                   color='#4472C4', label='Operational Carbon',
                   edgecolor='white', linewidth=0.5)
    
    # Top: Embodied carbon (orange)
    bars2 = ax.bar(x_pos, em_carbon_tons, bottom=op_carbon_tons,
                   color='#ED7D31', label='Embodied Carbon',
                   edgecolor='white', linewidth=0.5)
    
    # Customize plot
    ax.set_xlabel('Infiltration Reduction (%)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Carbon (ton CO2e)', fontsize=12, fontweight='bold')
    ax.set_title('Operational and Embodied Carbon by Infiltration Reduction', 
                fontsize=14, fontweight='bold', pad=20)
    
    # Set x-axis labels with infiltration percentages
    x_labels = [f"{inf:.0f}%" for inf in infiltration_sorted]
    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=10)
    
    # Add legend
    ax.legend(loc='upper right', fontsize=11, framealpha=0.9)
    
    # Add grid
    ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # Add value labels on bars
    for i, (op_val, em_val) in enumerate(zip(op_carbon_tons, em_carbon_tons)):
        total = op_val + em_val
        ax.text(i, total + 0.02 * max([op + em for op, em in zip(op_carbon_tons, em_carbon_tons)]), 
               f'{total:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Tight layout
    plt.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "window_enhancement_stacked_bar.png"
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
    """Main function to process all OSM files in the output directory."""
    print("\n" + "="*80)
    print("Window Enhancement Reporting Measure")
    print("="*80 + "\n")
    
    # Load emission factors
    emission_factors = load_emission_factors()
    
    # Find all OSM files in the tests/output directory
    output_dir = Path(__file__).parent / "tests" / "output"
    
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        print("Please run apply_measure_scenario.py first to generate scenario models.")
        return
    
    osm_files = sorted(output_dir.glob("*.osm"))
    
    if not osm_files:
        print(f"No OSM files found in {output_dir}")
        return
    
    print(f"Found {len(osm_files)} OSM files to process\n")
    
    # Ask user whether to run simulations
    print("Would you like to run EnergyPlus simulations for all scenarios?")
    print("  (This will take significant time - approximately 2-5 minutes per scenario)")
    run_simulations = input("Run simulations? [y/N]: ").strip().lower() == 'y'
    print()
    
    if run_simulations:
        print(f"Running simulations for {len(osm_files)} scenarios...")
        for i, osm_path in enumerate(osm_files, 1):
            print(f"\n[{i}/{len(osm_files)}] Simulating: {osm_path.name}")
            run_energyplus_simulation(osm_path)
    else:
        print("Skipping simulations. Using existing simulation results if available.\n")
    
    # Process all OSM files
    all_props_data = []
    all_energy_data = []
    
    for i, osm_path in enumerate(osm_files, 1):
        props_df, energy_df = extract_model_data(osm_path, emission_factors)
        
        if props_df is not None and not props_df.empty:
            # Add scenario identifier
            props_df.insert(0, 'scenario_file', osm_path.name)
            all_props_data.append(props_df)
        
        if energy_df is not None and not energy_df.empty:
            energy_df.insert(0, 'scenario_file', osm_path.name)
            all_energy_data.append(energy_df)
    
    # Combine all data
    import pandas as pd
    
    if all_props_data:
        combined_props = pd.concat(all_props_data, ignore_index=True)
        
        # Save to CSV (transposed)
        props_csv_path = output_dir / "window_enhancement_properties_report.csv"
        combined_props.T.to_csv(props_csv_path, header=False)
        print(f"\n✓ Saved window enhancement properties to: {props_csv_path}")
        print(f"  Total scenarios: {len(combined_props)}")
    else:
        print("\n⚠ No window enhancement properties data collected")
    
    if all_energy_data:
        combined_energy = pd.concat(all_energy_data, ignore_index=True)
        
        # Save to CSV (transposed)
        energy_csv_path = output_dir / "window_enhancement_energy_report.csv"
        combined_energy.T.to_csv(energy_csv_path, header=False)
        print(f"\n✓ Saved energy simulation results to: {energy_csv_path}")
        print(f"  Total scenarios: {len(combined_energy)}")
    else:
        print("\n⚠ No energy simulation data collected")
    
    # If both datasets exist, create a combined report
    if all_props_data and all_energy_data:
        combined_report = pd.merge(combined_props, combined_energy, on='scenario_file', how='outer')
        
        # Save combined report (transposed)
        combined_csv_path = output_dir / "window_enhancement_report.csv"
        combined_report.T.to_csv(combined_csv_path, header=False)
        print(f"\n✓ Saved combined report to: {combined_csv_path}")
        print(f"  Total scenarios: {len(combined_report)}")
        
        # Print summary statistics
        if 'window_enhancement_total_embodied_carbon_kgCO2eq' in combined_report.columns:
            print(f"\n{'='*80}")
            print("Embodied Carbon Summary:")
            print(f"{'='*80}")
            embodied_col = combined_report['window_enhancement_total_embodied_carbon_kgCO2eq'].dropna()
            if len(embodied_col) > 0:
                print(f"  Mean: {embodied_col.mean():.2f} kgCO2eq")
                print(f"  Min: {embodied_col.min():.2f} kgCO2eq")
                print(f"  Max: {embodied_col.max():.2f} kgCO2eq")
                print(f"  Std Dev: {embodied_col.std():.2f} kgCO2eq")
        
        if 'total_operational_carbon_kgCO2e' in combined_report.columns:
            print(f"\n{'='*80}")
            print("Operational Carbon Summary:")
            print(f"{'='*80}")
            operational_col = combined_report['total_operational_carbon_kgCO2e'].dropna()
            if len(operational_col) > 0:
                print(f"  Mean: {operational_col.mean():.2f} kgCO2e")
                print(f"  Min: {operational_col.min():.2f} kgCO2e")
                print(f"  Max: {operational_col.max():.2f} kgCO2e")
                print(f"  Std Dev: {operational_col.std():.2f} kgCO2e")
        
        # Generate visualizations
        measure_dir = Path(__file__).parent
        
        print(f"\n{'='*80}")
        print("Generating visualizations...")
        print(f"{'='*80}")
        
        # Create carbon comparison plot
        create_carbon_comparison_plot(combined_csv_path, measure_dir)
        
        # Create stacked bar chart
        create_stacked_bar_chart(combined_csv_path, measure_dir)
    
    print(f"\n{'='*80}")
    print("✓ Report generation complete!")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()

"""
Apply the ReportRetrofitImpacts reporting measure to test extraction of AdditionalProperties.

Usage:
    python apply_reporting_measure.py
"""

import sys
import os
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

# Import the measure
from measure import ECReport

def run_energyplus_simulation(osm_path):
    """Run EnergyPlus simulation to generate eplustbl.html report."""
    print(f"\n{'='*80}")
    print("Running EnergyPlus simulation to generate eplustbl.html report...")
    print(f"{'='*80}\n")
    
    # Create output directory for simulation
    run_dir = osm_path.parent / f"{osm_path.stem}_simulation"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Find the weather file
    weather_file = osm_path.parent.parent / "USA_CO_Denver-Aurora-Buckley.AFB_.724695_TMY3.epw"
    
    if not weather_file.exists():
        # Try alternate location
        weather_file = osm_path.parent / "USA_CO_Denver-Aurora-Buckley.AFB_.724695_TMY3.epw"
    
    if not weather_file.exists():
        print(f"  WARNING: Weather file not found. Simulation may fail.")
        weather_file_name = ""
    else:
        weather_file_name = weather_file.name
        print(f"  Found weather file: {weather_file.name}")
    
    # Create workflow JSON manually
    import json
    workflow_dict = {
        "seed_file": str(osm_path.name),
        "weather_file": weather_file_name,
        "measure_paths": [],
        "file_paths": [],
        "run_directory": "./"
    }
    
    # Save the workflow
    osw_path = run_dir / "workflow.osw"
    with open(osw_path, 'w') as f:
        json.dump(workflow_dict, f, indent=2)
    
    # Copy the OSM file and weather file to the run directory
    import shutil
    shutil.copy(osm_path, run_dir / osm_path.name)
    if weather_file.exists():
        shutil.copy(weather_file, run_dir / weather_file.name)
    
    print(f"Created workflow: {osw_path}")
    
    # Run the workflow using OpenStudio CLI
    print(f"\nRunning OpenStudio workflow (this may take a few minutes)...")
    import subprocess
    
    # Try to find OpenStudio CLI
    cli_paths = [
        r"C:\openstudio-3.8.0\bin\openstudio.exe",
        r"C:\openstudio-3.7.0\bin\openstudio.exe",
        r"C:\openstudio\bin\openstudio.exe",
        "openstudio",  # Try system PATH
    ]
    
    cli_exe = None
    for path in cli_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                cli_exe = path
                print(f"Found OpenStudio CLI: {path}")
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not cli_exe:
        print("\nWARNING: Could not find OpenStudio CLI.")
        print("Skipping EnergyPlus simulation.")
        return None
    
    # Run the workflow
    try:
        result = subprocess.run(
            [cli_exe, "run", "-w", str(osw_path)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✓ Simulation completed successfully")
        else:
            print(f"✗ Simulation failed with return code {result.returncode}")
            if result.stderr:
                print(f"Error output:\n{result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        print("✗ Simulation timed out after 5 minutes")
        return None
    except Exception as e:
        print(f"✗ Error running simulation: {e}")
        return None
    
    # Check for eplustbl.html in the run directory
    possible_report_paths = [
        run_dir / "reports" / "eplustbl.html",
        run_dir / "run" / "eplustbl.html",
        run_dir / "eplustbl.html",
    ]
    
    for report_path in possible_report_paths:
        if report_path.exists():
            print(f"✓ Found EnergyPlus report: {report_path}")
            # Copy to the main output directory for easier access
            dest_path = osm_path.parent / "eplustbl.html"
            import shutil
            shutil.copy(report_path, dest_path)
            print(f"  Copied to: {dest_path}")
            return dest_path
    
    print("✗ eplustbl.html not found in simulation output")
    return None

def extract_model_data(osm_path):
    """Extract AdditionalProperties and EnergyPlus data from a single OSM file."""
    print(f"\n{'='*80}")
    print(f"Processing: {osm_path.name}")
    print(f"{'='*80}")
    
    # Check if eplustbl.html already exists
    eplustbl_path = osm_path.parent / f"{osm_path.stem}_eplustbl.html"
    
    if not eplustbl_path.exists():
        print(f"eplustbl.html not found. Running EnergyPlus simulation...")
        eplustbl_path = run_energyplus_simulation(osm_path)
        if eplustbl_path and eplustbl_path.exists():
            # Rename to include model name
            new_eplustbl_path = osm_path.parent / f"{osm_path.stem}_eplustbl.html"
            import shutil
            if eplustbl_path != new_eplustbl_path:
                shutil.move(str(eplustbl_path), str(new_eplustbl_path))
                eplustbl_path = new_eplustbl_path
    else:
        print(f"✓ Found existing EnergyPlus report: {eplustbl_path}")
    
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
    
    # Parse EnergyPlus HTML if available
    eplustbl_data = {}
    if eplustbl_path and eplustbl_path.exists():
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
        
        eplustbl_data["building_name"] = extract_building_string(html_text)
        eplustbl_data["environment"] = extract_field(r'Environment:\s*<b>([^<]+)</b>', html_text)
        eplustbl_data["simulation_hours"] = extract_field(r'Values gathered over\s+([0-9.]+)\s+hours', html_text)
        eplustbl_data["total_site_energy_GJ"] = extract_field(r'Total Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        eplustbl_data["net_site_energy_GJ"] = extract_field(r'Net Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        eplustbl_data["total_source_energy_GJ"] = extract_field(r'Total Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        eplustbl_data["net_source_energy_GJ"] = extract_field(r'Net Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        eplustbl_data["total_building_area_m2"] = extract_field(r'Total Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        eplustbl_data["net_conditioned_building_area_m2"] = extract_field(r'Net Conditioned Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        # Check if we actually got any data
        non_empty_fields = sum(1 for v in eplustbl_data.values() if v)
        print(f"✓ Parsed EnergyPlus report data ({non_empty_fields}/{len(eplustbl_data)} fields populated)")
        
        if non_empty_fields == 0:
            print(f"  WARNING: No EnergyPlus data extracted from {eplustbl_path.name}")
            eplustbl_data = {}  # Return empty dict if no data found
    else:
        print(f"  No EnergyPlus report available")
    
    return props_df, eplustbl_data

def create_scatterplot(props_df, energyplus_data, measure_dir):
    """Create a scatterplot with dual y-axes showing energy and carbon vs insulation R-value."""
    print(f"\n{'='*80}")
    print("Creating scatterplot...")
    print(f"{'='*80}")
    
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
    except ImportError:
        print("✗ matplotlib not found. Installing matplotlib...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            print("✓ matplotlib installed successfully")
        except Exception as e:
            print(f"✗ Failed to install matplotlib: {e}")
            print("  Skipping plot generation")
            return
    
    import pandas as pd
    
    # Merge construction properties with EnergyPlus data
    energyplus_df = pd.DataFrame(energyplus_data)
    
    # Get target_insulation_r-value_ip and total_embodied_carbon_kgCO2eq from props_df
    # These are in transposed format, so we need to extract them
    r_values = []
    carbon_values = []
    energy_values = []
    scenario_names = []
    material_types = []
    
    for scenario in energyplus_df['scenario_name']:
        if scenario in props_df['scenario_name'].values:
            # Get R-value and carbon from construction properties
            scenario_data = props_df[props_df['scenario_name'] == scenario].iloc[0]
            r_value = scenario_data.get('target_insulation_r-value_ip', None)
            carbon = scenario_data.get('total_embodied_carbon_kgCO2eq', None)
            material_type = scenario_data.get('insutlation_material_type', 'Unknown')
            
            # Get energy from EnergyPlus data
            energy_data = energyplus_df[energyplus_df['scenario_name'] == scenario].iloc[0]
            energy = energy_data.get('total_site_energy_GJ', None)
            
            # Only include if all values are available and R-value > 0
            if r_value is not None and carbon is not None and energy is not None:
                try:
                    r_val = float(r_value)
                    if r_val > 0:  # Exclude R5 scenarios with 0 values
                        r_values.append(r_val)
                        carbon_values.append(float(carbon))
                        energy_values.append(float(energy))
                        scenario_names.append(scenario)
                        material_types.append(material_type)
                except (ValueError, TypeError):
                    continue
    
    if not r_values:
        print("✗ No valid data found for plotting")
        return
    
    # Define color map for insulation materials
    material_colors = {
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
    
    # Plot total_site_energy_GJ on left y-axis
    color1 = 'tab:blue'
    ax1.set_xlabel('Target Insulation R-Value (IP)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Total Site Energy (GJ)', color=color1, fontsize=12, fontweight='bold')
    ax1.scatter(r_values, energy_values, color=color1, s=100, alpha=0.6, label='Site Energy', marker='o')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, alpha=0.3)
    
    # Create second y-axis for total_embodied_carbon_kgCO2eq
    ax2 = ax1.twinx()
    ax2.set_ylabel('Total Embodied Carbon (kgCO2eq)', fontsize=12, fontweight='bold')
    
    # Plot embodied carbon with different colors for each material type
    for material in material_colors.keys():
        # Filter data for this material
        mask = [mat == material for mat in material_types]
        r_vals_mat = [r for r, m in zip(r_values, mask) if m]
        carbon_vals_mat = [c for c, m in zip(carbon_values, mask) if m]
        
        if r_vals_mat:  # Only plot if there's data for this material
            # Simplify legend labels
            label = material.replace(' Foam Board', '').replace(' Blanket', '').replace(' Batts', '')
            ax2.scatter(r_vals_mat, carbon_vals_mat, 
                       color=material_colors[material], 
                       s=100, alpha=0.7, 
                       label=label, 
                       marker='s', 
                       edgecolors='black', 
                       linewidths=0.5)
    
    ax2.tick_params(axis='y')
    
    # Add title
    plt.title('Energy and Carbon Impact vs. Insulation R-Value', fontsize=14, fontweight='bold', pad=20)
    
    # Add legends - Site Energy on left, Materials on right
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc='upper left', fontsize=10, title='Operational Energy')
    
    # Material legend on the right side
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines2, labels2, loc='upper right', fontsize=9, title='Insulation Material', ncol=1)
    
    # Adjust layout to prevent label cutoff
    fig.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "retrofit_impact_scatterplot.png"
    plt.savefig(output_plot, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Scatterplot saved: {output_plot}")
    print(f"  Data points plotted: {len(r_values)}")
    print(f"  R-value range: {min(r_values):.1f} - {max(r_values):.1f}")
    print(f"  Energy range: {min(energy_values):.2f} - {max(energy_values):.2f} GJ")
    print(f"  Carbon range: {min(carbon_values):.2f} - {max(carbon_values):.2f} kgCO2eq")

def main():
    # Find all output OSM files from the insulation measure
    output_dir = Path(__file__).parent.parent / "IncreaseInsulationRValueForExteriorWalls" / "tests" / "output"
    
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        print("\nPlease run the IncreaseInsulationRValueForExteriorWalls/apply_measure.py script first.")
        sys.exit(1)
    
    # Find all OSM files matching the pattern out_R*_*.osm
    osm_files = sorted(output_dir.glob("out_R*.osm"))
    
    if not osm_files:
        print(f"Error: No output OSM files found in {output_dir}")
        print("Expected files matching pattern: out_R*.osm")
        print("\nPlease run the IncreaseInsulationRValueForExteriorWalls/apply_measure.py script first.")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Found {len(osm_files)} output model(s) to process")
    print(f"{'='*80}")
    for osm_file in osm_files:
        print(f"  - {osm_file.name}")
    
    # Track results
    all_model_data = []
    successful = 0
    failed = 0
    
    # Process each model and collect data
    all_energyplus_data = []  # Store EnergyPlus data separately
    
    for idx, osm_path in enumerate(osm_files, 1):
        print(f"\n[Model {idx}/{len(osm_files)}]")
        
        props_df, eplustbl_data = extract_model_data(osm_path)
        
        if props_df is not None:
            # Add scenario identifier column
            props_df['scenario_name'] = osm_path.stem
            
            all_model_data.append(props_df)
            
            # Store EnergyPlus data separately with scenario name
            if eplustbl_data:
                eplustbl_data['scenario_name'] = osm_path.stem
                all_energyplus_data.append(eplustbl_data)
                print(f"✓ Data extracted successfully from {osm_path.name}")
                print(f"  EnergyPlus metrics: {len(eplustbl_data) - 1} fields")  # -1 for scenario_name
            else:
                print(f"✓ Data extracted successfully from {osm_path.name} (no EnergyPlus data)")
            
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
        output_csv = measure_dir / "resources" / "retrofit_measure_report.csv"
        
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            # First, write Construction AdditionalProperties section (transposed and reversed)
            f.write("# Construction AdditionalProperties\n")
            
            construction_transposed = combined_df.set_index('scenario_name').T
            construction_transposed = construction_transposed.iloc[::-1]
            construction_transposed.to_csv(f)
            f.write("\n")
            
            # Second, write EnergyPlus Simulation Summary section
            if all_energyplus_data:
                f.write("# EnergyPlus Simulation Summary\n")
                
                # Create DataFrame from EnergyPlus data
                energyplus_df = pd.DataFrame(all_energyplus_data)
                energyplus_transposed = energyplus_df.set_index('scenario_name').T
                energyplus_transposed.to_csv(f)
        
        construction_features = len(combined_df.columns) - 1  # -1 for scenario_name
        energyplus_metrics = len(all_energyplus_data[0]) - 1 if all_energyplus_data else 0  # -1 for scenario_name
        
        print(f"\n✓ Combined report saved: {output_csv}")
        print(f"  Scenarios: {len(all_model_data)}")
        print(f"  Construction features: {construction_features}")
        print(f"  EnergyPlus metrics: {energyplus_metrics}")
        
        # Create scatterplot with dual y-axes
        if all_energyplus_data:
            create_scatterplot(combined_df, all_energyplus_data, measure_dir)
    
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

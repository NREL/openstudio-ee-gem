"""
Apply reporting measure to extract AdditionalProperties from wall insulation models.

Usage:
    python apply_reporting_measure_wall_insulation.py
"""
import sys
import os
import codecs

# Set UTF-8 encoding for console output to handle Unicode characters
if sys.platform == 'win32':
    import io
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
    emission_factors_path = Path(__file__).parent.parent / "ReportRetrofitImpacts" / "resources" / "emission_factors_for_operational_carbon.csv"
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
    import subprocess
    import json
    import shutil
    
    scenario_name = osm_path.stem
    run_dir = osm_path.parent / f"{scenario_name}_simulation"
    
    # Check if simulation has already been run
    eplustbl_paths = [
        run_dir / "eplustbl.htm",
        run_dir / "eplustbl.html",
        run_dir / "run" / "eplustbl.html",
        run_dir / "reports" / "eplustbl.html"
    ]
    
    for eplustbl_path in eplustbl_paths:
        if eplustbl_path.exists():
            print(f"  ✓ Simulation results already exist: {eplustbl_path.name}")
            return True
    
    print(f"  Running EnergyPlus simulation...")
    
    # Create run directory
    run_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Load the model
        translator = openstudio.osversion.VersionTranslator()
        model_opt = translator.loadModel(str(osm_path))
        
        if not model_opt.is_initialized():
            print(f"  ✗ Error: Could not load model from {osm_path}")
            return False
        
        model = model_opt.get()
        
        # Get weather file path from model and verify/find it
        weather_file_obj = model.getWeatherFile()
        epw_path = None
        
        # Try to get path from model
        if weather_file_obj.path().is_initialized():
            model_epw_path = Path(weather_file_obj.path().get().__str__())
            if model_epw_path.exists():
                epw_path = model_epw_path
                print(f"  ✓ Using weather file from model: {epw_path.name}")
            else:
                print(f"  ⚠ Weather file in model not found: {model_epw_path}")
        
        # If no valid weather file found, search common locations
        if not epw_path:
            possible_epw_locations = [
                # Check in the output directory
                osm_path.parent / "weather.epw",
                osm_path.parent / "*.epw",
                # Check in tests directory
                osm_path.parent.parent / "weather.epw",
                osm_path.parent.parent / "*.epw",
                # Check relative to measure directory
                Path(__file__).parent / "tests" / "weather.epw",
                Path(__file__).parent / "tests" / "*.epw",
                Path(__file__).parent / "weather.epw",
                Path(__file__).parent / "*.epw",
            ]
            
            for location in possible_epw_locations:
                if "*" in str(location):
                    # Use glob for wildcard patterns
                    matches = list(location.parent.glob(location.name))
                    if matches:
                        epw_path = matches[0]
                        break
                elif location.exists():
                    epw_path = location
                    break
            
            if epw_path:
                print(f"  ✓ Found weather file: {epw_path}")
                # No need to update the model - the OSW will override it
            else:
                print(f"  ⚠ Warning: No weather file found. Simulation may fail.")
                print(f"    Checked locations:")
                for loc in possible_epw_locations[:6]:  # Show first few
                    print(f"      - {loc}")
                # Don't return False yet - let the simulation try anyway
        
        # Use OpenStudio CLI to run the workflow
        # Create a minimal OSW (OpenStudio Workflow) file
        osw_path = run_dir / "workflow.osw"
        
        osw_content = {
            "seed_file": str(osm_path.absolute()),
            "weather_file": str(epw_path.absolute()) if epw_path and epw_path.exists() else "",
            "measure_paths": [],
            "file_paths": [],
            "run_directory": "./run",
            "steps": [],
            "created_at": "20260120T120000Z",
            "updated_at": "20260120T120000Z",
            "oswVersion": "3.9.0"
        }
        
        with open(osw_path, 'w') as f:
            json.dump(osw_content, f, indent=2)
        
        if epw_path and epw_path.exists():
            print(f"  ✓ Workflow file created: {osw_path.name} (weather: {epw_path.name})")
        else:
            print(f"  ✓ Workflow file created: {osw_path.name} (no weather file)")
        
        # Find OpenStudio CLI executable
        openstudio_exe = None
        possible_cli_paths = [
            r"C:\openstudio-3.8.0\bin\openstudio.exe",
            r"C:\openstudio-3.7.0\bin\openstudio.exe",
            r"C:\openstudio-3.9.0\bin\openstudio.exe",
            r"C:\Program Files\OpenStudio-3.8.0\bin\openstudio.exe",
            r"C:\Program Files\OpenStudio-3.7.0\bin\openstudio.exe",
            "/usr/local/openstudio/bin/openstudio",  # Linux/Mac
            "/Applications/OpenStudio-3.8.0/bin/openstudio",  # Mac
        ]
        
        # Try to find OpenStudio CLI in PATH
        openstudio_exe = shutil.which("openstudio")
        
        if not openstudio_exe:
            # Check common installation paths
            for cli_path in possible_cli_paths:
                if Path(cli_path).exists():
                    openstudio_exe = cli_path
                    break
        
        if not openstudio_exe:
            print(f"  ✗ Error: OpenStudio CLI not found in PATH or common locations")
            print(f"    Checked: {possible_cli_paths}")
            print(f"  ⚠ You can run the simulation manually using:")
            print(f"    openstudio run -w {osw_path}")
            return False
        
        # Run OpenStudio CLI
        cmd = [openstudio_exe, "run", "-w", str(osw_path)]
        
        print(f"  ▶ Running: {' '.join([Path(c).name if i == 0 else c for i, c in enumerate(cmd)])}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                cwd=str(run_dir)
            )
            
            if result.returncode == 0:
                print(f"  ✓ OpenStudio simulation completed successfully")
                
                # Verify output files exist in run directory
                for eplustbl_path in eplustbl_paths:
                    if eplustbl_path.exists():
                        print(f"  ✓ Output file created: {eplustbl_path.name}")
                        return True
                
                print(f"  ⚠ Warning: Simulation completed but output files not found")
                print(f"    Checking run subdirectory...")
                # Check if files are in a 'run' subdirectory
                run_subdir = run_dir / "run"
                if run_subdir.exists():
                    for file in run_subdir.glob("*eplustbl*"):
                        print(f"  ✓ Found output file: {file}")
                        return True
                return False
            else:
                print(f"  ✗ OpenStudio simulation failed with return code: {result.returncode}")
                if result.stderr:
                    print(f"  Error output: {result.stderr[:500]}")
                if result.stdout:
                    print(f"  Standard output: {result.stdout[-500:]}")
                return False
        except FileNotFoundError:
            print(f"  ✗ Error: Could not execute OpenStudio CLI at: {openstudio_exe}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Error: OpenStudio simulation timed out (>10 minutes)")
        return False
    except Exception as e:
        print(f"  ✗ Error running simulation: {e}")
        import traceback
        traceback.print_exc()
        return False

def extract_model_data(osm_path, emission_factors, run_simulation=True):
    """Extract AdditionalProperties from OSM file and energy results from SQL file."""
    print(f"\n{'='*80}")
    print(f"Processing: {osm_path.name}")
    print(f"{'='*80}")
    
    # Run EnergyPlus simulation if requested
    if run_simulation:
        run_energyplus_simulation(osm_path)
    
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
    
    # Check if this is an R0 baseline model (no insulation properties found)
    is_baseline = False
    if props_df.empty or 'target_insulation_r-value_ip' not in props_df.columns:
        # Check if filename indicates R0 baseline
        if '_R0_' in osm_path.name or osm_path.stem.startswith('out_R0'):
            is_baseline = True
            print(f"  ℹ Detected R0 baseline model - will extract energy data only")
            # Create baseline properties dataframe with placeholder values
            props_df = pd.DataFrame([{
                'construction_handle': 'baseline',
                'construction_name': 'Baseline (No Insulation Upgrade)',
                'target_insulation_r-value_ip': 0.0,
                'original_insulation_r-value_ip': 9.45178657550291,  # Default from other models
                'insulation_material_type': 'Baseline (No Added Insulation)',
                'insulation_material_thermal_conductivity_W_per_mK': 0.0,
                'insulation_material_density_kg_per_m3': 0.0,
                'insulation_material_gwp_per_kg': 0.0,
                'insulation_material_gwp_per_m2': 0.0,
                'insulation_material_gwp_per_m3': 0.0,
                'insulation_material_lifetime_years': 0.0,
                'insulation_material_lifetime_source': 'N/A - Baseline',
                'total_volume_m3': 0.0,
                'total_embodied_carbon_kgCO2eq': 0.0,
                'added_insulation_layer_thickness_m': 0.0,
                'added_insulation_layer_mass_kg': 0.0,
                'renovated_exterior_wall_area_m2': 0.0,
                'analysis_period_years': 30,
                'is_baseline': 'TRUE'
            }])
    
    # Extract energy results from eplustbl.html file
    scenario_name = osm_path.stem
    run_dir = osm_path.parent / f"{scenario_name}_simulation"
    
    # Try multiple possible eplustbl.html/htm locations
    eplustbl_paths = [
        run_dir / "eplustbl.htm",
        run_dir / "eplustbl.html",
        run_dir / "run" / "eplustbl.html",
        run_dir / "reports" / "eplustbl.html"
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
                elec_GJ = float(energy_data.get('total_end_uses_electricity_GJ', 0) or 0)
                gas_GJ = float(energy_data.get('total_end_uses_natural_gas_GJ', 0) or 0)
                water_m3 = float(energy_data.get('total_end_uses_water_m3', 0) or 0)
                
                op_carbon_electricity = elec_GJ * emission_factors['elec_emission_factor']
                op_carbon_gas = gas_GJ * emission_factors['gas_emission_factor']
                op_carbon_water = water_m3 * emission_factors['water_emission_factor']
                
                total_op_carbon = op_carbon_electricity + op_carbon_gas + op_carbon_water
                
                energy_data['operational_carbon_electricity_kgCO2e'] = op_carbon_electricity
                energy_data['operational_carbon_gas_kgCO2e'] = op_carbon_gas
                energy_data['operational_carbon_water_kgCO2e'] = op_carbon_water
                energy_data['total_operational_carbon_kgCO2e'] = total_op_carbon
            except (ValueError, TypeError, KeyError) as e:
                print(f"  ⚠ Error calculating operational carbon: {e}")
                energy_data['total_operational_carbon_kgCO2e'] = ''
            
            # Check if we actually got any data
            non_empty_fields = sum(1 for v in energy_data.values() if v)
            if non_empty_fields > 0:
                print(f"✓ Parsed EnergyPlus report data ({non_empty_fields}/{len(energy_data)} fields populated)")
            else:
                print(f"  ⚠ WARNING: No EnergyPlus data extracted from {eplustbl_path.name}")
                energy_data = {}
                
        except Exception as e:
            print(f"  ⚠ Error reading HTML: {str(e)[:100]}")
            energy_data = {}
    else:
        print(f"  ⚠ eplustbl.html not found in run directory")
    
    # Calculate totals from construction properties and add to energy data
    if not props_df.empty and 'renovated_exterior_wall_area_m2' in props_df.columns:
        # Calculate total renovated wall area (sum across all constructions)
        try:
            total_wall_area = props_df['renovated_exterior_wall_area_m2'].sum()
            energy_data['total_renovated_wall_area_m2'] = total_wall_area
            print(f"  ✓ Total renovated wall area: {total_wall_area:.2f} m²")
        except (ValueError, TypeError, KeyError) as e:
            print(f"  ⚠ Error calculating total wall area: {e}")
            energy_data['total_renovated_wall_area_m2'] = 0.0
        
        # Calculate total embodied carbon (sum across all constructions)
        try:
            total_embodied_carbon = props_df['total_embodied_carbon_kgCO2eq'].sum()
            energy_data['total_embodied_carbon_all_constructions_kgCO2eq'] = total_embodied_carbon
            print(f"  ✓ Total embodied carbon (all constructions): {total_embodied_carbon:.2f} kgCO2eq")
        except (ValueError, TypeError, KeyError) as e:
            print(f"  ⚠ Error calculating total embodied carbon: {e}")
            energy_data['total_embodied_carbon_all_constructions_kgCO2eq'] = 0.0
    else:
        # For baseline or models without wall area data
        energy_data['total_renovated_wall_area_m2'] = 0.0
        energy_data['total_embodied_carbon_all_constructions_kgCO2eq'] = 0.0
    
    # For baseline models, if we got energy data but no properties, still return the data
    if is_baseline:
        if energy_data:
            print(f"✓ Baseline model data extracted (energy data: {len(energy_data)} fields)")
        else:
            print(f"  ⚠ No energy data extracted for baseline model")
    
    # Only return None if we have neither properties nor energy data (unless it's a baseline with energy data)
    if props_df.empty and not energy_data and not is_baseline:
        print(f"✗ No data extracted from {osm_path.name}")
        return None, None
    
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
    import traceback
    
    # Read CSV file - it has two sections
    try:
        # Read the entire file to find section boundaries
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Wall Construction AdditionalProperties' in line:
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
        
        # Check if energyplus_lines is empty
        if not energyplus_lines:
            print("✗ Error: EnergyPlus section not found or empty in CSV file")
            print("  Looking for '# EnergyPlus Simulation Summary' header")
            return
        
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
        print(f"    - insutlation_material_type: {'insutlation_material_type' in df.columns}")
        print(f"    - total_site_energy_GJ: {'total_site_energy_GJ' in df.columns}")
        
        # Sample data for first scenario
        if len(df) > 0:
            first_scenario = df.index[0]
            print(f"  Sample data for {first_scenario}:")
            print(f"    Carbon: {df.loc[first_scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else 'NOT FOUND'}")
            print(f"    Material: {df.loc[first_scenario, 'insutlation_material_type'] if 'insutlation_material_type' in df.columns else 'NOT FOUND'}")
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
            material = df.loc[scenario, 'insutlation_material_type'] if 'insutlation_material_type' in df.columns else None
            
            # Get energy from EnergyPlus data
            energy = df.loc[scenario, 'total_site_energy_GJ'] if 'total_site_energy_GJ' in df.columns else None
            
            # Convert to appropriate types
            if r_value is not None and carbon is not None and material is not None:
                try:
                    carbon_val = float(carbon)
                    energy_val = float(energy) if energy and str(energy).strip() else None
                    
                    r_values.append(r_value)
                    carbon_values.append(carbon_val)
                    energy_values.append(energy_val)
                    scenario_names.append(scenario)
                    material_types.append(str(material))
                except (ValueError, TypeError) as e:
                    print(f"  ⚠ Skipping {scenario}: Error converting values - {e}")
                    continue
        except Exception as e:
            print(f"  ⚠ Error processing scenario {scenario}: {e}")
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
            energies_at_r = [e for r, e in zip(r_with_energy, e_with_data) if r == r_val]
            print(f"    R={r_val}: {len(energies_at_r)} data points, mean={sum(energies_at_r)/len(energies_at_r):.2f} GJ")
        
        ax1.scatter(r_with_energy, e_with_data, color=color1, s=100, alpha=0.6, 
                   label='Site Energy', marker='o', zorder=3)
        ax1.tick_params(axis='y', labelcolor=color1)
        
        # Add trendline for site energy
        if len(r_with_energy) >= 2:
            z1 = np.polyfit(r_with_energy, e_with_data, 1)
            p1 = np.poly1d(z1)
            r_sorted = np.sort(unique_r_values)
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
            ax2.scatter(r_vals_mat, carbon_vals_mat,
                       color=material_colors[material],
                       s=100, alpha=0.7,
                       label=label,
                       marker='s',
                       edgecolors='black',
                       linewidths=0.5,
                       zorder=3)
            
            # Add trendline for each material type if there are at least 2 points
            if len(r_vals_mat) >= 2:
                z_mat = np.polyfit(r_vals_mat, carbon_vals_mat, 1)
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
    plt.title('Energy and Carbon Impact vs. Wall Insulation R-Value', fontsize=14, fontweight='bold', pad=20)
    
    # Add legends - Site Energy on left, Materials on right
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc='upper left', fontsize=10, title='Operational Energy')
    
    # Material legend on the right side
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines2, labels2, loc='upper right', fontsize=9, title='Insulation Material', ncol=1)
    
    # Adjust layout to prevent label cutoff
    fig.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "wall_insulation_carbon_impact.png"
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
    import traceback
    
    # Read CSV file - it has two sections
    try:
        # Read the entire file to find section boundaries
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Wall Construction AdditionalProperties' in line:
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
        
        # Check if energyplus_lines is empty
        if not energyplus_lines:
            print("✗ Error: EnergyPlus section not found or empty in CSV file")
            print("  Looking for '# EnergyPlus Simulation Summary' header")
            return
        
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
            
            # Get embodied carbon and material from construction data
            embodied_carbon = df.loc[scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else None
            material = df.loc[scenario, 'insutlation_material_type'] if 'insutlation_material_type' in df.columns else None
            
            # Get operational carbon from EnergyPlus data
            operational_carbon = df.loc[scenario, 'total_operational_carbon_kgCO2e'] if 'total_operational_carbon_kgCO2e' in df.columns else None
            
            # Convert to appropriate types
            if r_value is not None and embodied_carbon is not None and material is not None and operational_carbon is not None:
                try:
                    embodied_val = float(embodied_carbon)
                    operational_val = float(operational_carbon)
                    
                    r_values.append(r_value)
                    embodied_carbon_values.append(embodied_val)
                    operational_carbon_values.append(operational_val)
                    scenario_names.append(scenario)
                    material_types.append(str(material))
                except (ValueError, TypeError) as e:
                    print(f"  ⚠ Skipping {scenario}: Error converting carbon values - {e}")
                    continue
        except Exception as e:
            print(f"  ⚠ Error processing scenario {scenario}: {e}")
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
            print(f"    R={r_val}: mean={sum(op_carbon_at_r)/len(op_carbon_at_r):.2f} kgCO2e")
    
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
            label = material.replace(' Foam Board', '').replace(' Blanket', '').replace(' Batts', '')
            ax2.scatter(r_vals_mat, embodied_vals_mat,
                       color=material_colors[material],
                       s=100, alpha=0.7,
                       label=label,
                       marker='s',
                       edgecolors='black',
                       linewidths=0.5,
                       zorder=3)
            
            # Add trendline for each material type if there are at least 2 points
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
    output_plot = measure_dir / "resources" / "wall_insulation_carbon_comparison.png"
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
    import traceback
    
    # Read CSV file - it has two sections
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the start of each section
        construction_start = None
        energyplus_start = None
        
        for i, line in enumerate(lines):
            if '# Wall Construction AdditionalProperties' in line:
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
        
        # Check if energyplus_lines is empty
        if not energyplus_lines:
            print("✗ Error: EnergyPlus section not found or empty in CSV file")
            print("  Looking for '# EnergyPlus Simulation Summary' header")
            return
        
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
            # Get operational and embodied carbon
            op_carbon = df.loc[scenario, 'total_operational_carbon_kgCO2e'] if 'total_operational_carbon_kgCO2e' in df.columns else None
            em_carbon = df.loc[scenario, 'total_embodied_carbon_kgCO2eq'] if 'total_embodied_carbon_kgCO2eq' in df.columns else None
            
            # Convert to appropriate types
            if op_carbon is not None and em_carbon is not None:
                try:
                    op_val = float(op_carbon)
                    em_val = float(em_carbon)
                    
                    scenario_names.append(scenario)
                    operational_carbon.append(op_val)
                    embodied_carbon.append(em_val)
                except (ValueError, TypeError) as e:
                    print(f"  ⚠ Skipping {scenario}: Error converting carbon values - {e}")
                    continue
            
        except Exception as e:
            print(f"  ⚠ Error processing scenario {scenario}: {e}")
            continue
    
    if not scenario_names:
        print("✗ No valid data found for plotting")
        return
    
    # Sort scenarios by R-value (extracted from scenario name)
    import re
    scenario_r_values = []
    for scenario in scenario_names:
        r_match = re.search(r'R(\d+\.?\d*)', scenario)
        r_val = float(r_match.group(1)) if r_match else 0
        scenario_r_values.append(r_val)
    
    # Create a list of tuples and sort by R-value, then by scenario name
    sorted_data = sorted(zip(scenario_r_values, scenario_names, operational_carbon, embodied_carbon))
    
    # Unpack sorted data
    _, scenario_names, operational_carbon, embodied_carbon = zip(*sorted_data)
    scenario_names = list(scenario_names)
    operational_carbon = list(operational_carbon)
    embodied_carbon = list(embodied_carbon)
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=(20, 8))
    
    # Set up x-axis positions
    x_pos = np.arange(len(scenario_names))
    
    # Convert from kg to tons (divide by 1000)
    operational_carbon_tons = [oc / 1000 for oc in operational_carbon]
    embodied_carbon_tons = [ec / 1000 for ec in embodied_carbon]
    
    # Create stacked bars
    # Bottom: Operational carbon (blue)
    bars1 = ax.bar(x_pos, operational_carbon_tons, 
                   color='#4472C4', label='Operational Carbon',
                   edgecolor='white', linewidth=0.5)
    
    # Top: Embodied carbon (orange)
    bars2 = ax.bar(x_pos, embodied_carbon_tons, bottom=operational_carbon_tons,
                   color='#ED7D31', label='Embodied Carbon',
                   edgecolor='white', linewidth=0.5)
    
    # Customize the plot
    ax.set_xlabel('Scenarios', fontsize=12, fontweight='bold')
    ax.set_ylabel('Total Carbon Emission at Year 1 (ton CO2e)', fontsize=12, fontweight='bold')
    ax.set_title('Operational and Embodied Carbon by Scenario', fontsize=14, fontweight='bold', pad=20)
    
    # Set x-axis labels - rotate for readability
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scenario_names, rotation=90, ha='right', fontsize=8)
    
    # Add horizontal dashed lines to show operational carbon levels for different R-values
    # Extract R-value from scenario names and group operational carbon by R-value
    import re
    r_value_op_carbon = {}
    for scenario, op_carbon_kg in zip(scenario_names, operational_carbon):
        r_match = re.search(r'R(\d+\.?\d*)', scenario)
        if r_match:
            r_val = float(r_match.group(1))
            if r_val not in r_value_op_carbon:
                r_value_op_carbon[r_val] = op_carbon_kg
    
    # Sort by R-value and add dashed lines
    for r_val in sorted(r_value_op_carbon.keys()):
        op_carbon_tons = r_value_op_carbon[r_val] / 1000
        ax.axhline(y=op_carbon_tons, color='gray', linestyle='--', linewidth=1.5, alpha=0.7, zorder=1)
        # Add R-value label at the right edge
        ax.text(len(scenario_names) - 0.5, op_carbon_tons, f'  R={r_val:.1f}', 
               verticalalignment='center', fontsize=9, color='gray', fontweight='bold')
    
    # Add legend
    ax.legend(loc='upper right', frameon=True, shadow=True, fontsize=11)
    
    # Add grid for better readability
    ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # Format y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    
    # Tight layout
    plt.tight_layout()
    
    # Save the plot
    output_plot = measure_dir / "resources" / "wall_insulation_stacked_bar.png"
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
    # Find all output OSM files from the wall insulation measure
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
        
        # Run simulation and extract data (run_simulation=True by default)
        props_df, energy_data = extract_model_data(osm_path, emission_factors, run_simulation=True)
        
        if props_df is not None and not props_df.empty:
            # Add scenario identifier column
            props_df['scenario_name'] = osm_path.stem
            
            all_model_data.append(props_df)
            
            # Store energy data separately with scenario name
            if energy_data:
                energy_data['scenario_name'] = osm_path.stem
                all_energy_data.append(energy_data)
                print(f"✓ Data extracted successfully from {osm_path.name}")
                print(f"  EnergyPlus metrics: {len(energy_data) - 1} fields")  # -1 for scenario_name
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
        output_csv = measure_dir / "resources" / "wall_insulation_report.csv"
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_csv, 'w', newline='', encoding='utf-8') as f:
                # First, write Construction AdditionalProperties section (transposed and reversed)
                f.write("# Wall Construction AdditionalProperties\n")
                
                construction_transposed = combined_df.set_index('scenario_name').T
                construction_transposed = construction_transposed.iloc[::-1]
                construction_transposed.to_csv(f)
                f.write("\n")
                
                # Second, write EnergyPlus Simulation Summary section
                if all_energy_data:
                    f.write("# EnergyPlus Simulation Summary\n")
                    
                    # Create DataFrame from energy data
                    energy_df = pd.DataFrame(all_energy_data)
                    energy_transposed = energy_df.set_index('scenario_name').T
                    energy_transposed.to_csv(f)
            
            construction_features = len(combined_df.columns) - 1  # -1 for scenario_name
            energy_metrics = len(all_energy_data[0]) - 1 if all_energy_data else 0  # -1 for scenario_name
            
            print(f"\n✓ Combined report saved: {output_csv}")
            print(f"  Scenarios: {len(all_model_data)}")
            print(f"  Construction features: {construction_features}")
            print(f"  EnergyPlus metrics: {energy_metrics}")
        
        except PermissionError:
            print(f"\n✗ Permission denied: Cannot write to {output_csv}")
            print("  Please close the file if it is open in another program.")
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

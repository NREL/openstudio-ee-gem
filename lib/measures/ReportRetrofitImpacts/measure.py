# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import sys
import os
from pathlib import Path

# Add resources directory to Python path for imports
measure_dir = Path(__file__).parent
resources_dir = measure_dir / 'resources'
if str(resources_dir) not in sys.path:
    sys.path.insert(0, str(resources_dir))

import openstudio
import pandas as pd
from openpyxl import load_workbook
import plotly.graph_objects as go
import configparser
import re
import json
from dotenv import load_dotenv
from call_RSmeans import RSMeansAPIClient

CURRENT_DIR_PATH = Path(__file__).absolute()
optimization_excel_path = CURRENT_DIR_PATH.parent / 'Inputs' / 'optimization.xlsx'
new_optimization_excel_output_path = CURRENT_DIR_PATH.parent / 'Outputs' / 'optimization_updated.xlsx'
optimization_csv_output_path = CURRENT_DIR_PATH.parent / 'Outputs' / 'retrofit_measure_report.csv'
html_template_path = CURRENT_DIR_PATH.parent / 'resources' / 'retrofit_report_template.html'

# Paths for baseline and measure-applied scenarios
inputs_dir = CURRENT_DIR_PATH.parent / 'Inputs'
run_dir = inputs_dir / 'run'
baseline_run_dir = run_dir / 'run_baseline'
measure_applied_run_dir = run_dir / 'run_measure_applied'
baseline_eplustbl_path = baseline_run_dir / 'eplustbl.htm'  # EnergyPlus creates .htm not .html
measure_applied_eplustbl_path = measure_applied_run_dir / 'eplustbl.htm'  # EnergyPlus creates .htm not .html
html_report_path = CURRENT_DIR_PATH.parent / 'Outputs' / 'retrofit_analysis_report.html'

# Energy cost fallback ($/GJ)
DEFAULT_ENERGY_COST_PER_GJ = 15.0  # Used only if no cost data can be derived

class CReport(openstudio.measure.ReportingMeasure):
    def __init__(self):
        super().__init__()

    def name(self):
        return "ReportAdditionalProperties"

    def description(self):
        return "Reports all AdditionalProperties objects and their key-value pairs in the model."

    def modeler_description(self):
        return "Traverses the model and extracts data from AdditionalProperties objects."

    def modify_optimization_sheet(self, replacement_value):

        """Reads and modifies Excel spreadsheet for optimization visualizations"""
        wb = load_workbook(optimization_excel_path, data_only=False, keep_links=True)
        try:
            # Select the 'values' worksheet specifically
            if 'values' not in wb.sheetnames:
                raise ValueError("Sheet named 'values' not found in the Excel file.")
            ws = wb['values']

            # Find the row with "Embodied Carbon" in the first column
            target_row = None
            for row in ws.iter_rows(min_row=1, max_col=1):
                cell = row[0]
                if str(cell.value).strip() == 'Embodied Carbon':
                    target_row = cell.row
                    break

            # Find the column with "Scenario_1" in the header row
            target_col = None
            for cell in ws[1]:  # First row is assumed to be the header
                if str(cell.value).strip() == 'Scenario_1':
                    target_col = cell.column
                    break

            # Modify the value if both row and column are found
            if target_row and target_col:
                ws.cell(row=target_row, column=target_col).value = replacement_value
            else:
                raise ValueError("Could not find 'Embodied Carbon' row or 'Scenario_1' column.")

            # Save updated workbook
            wb.save(new_optimization_excel_output_path)
        finally:
            wb.close()

    def optimization(self):
        """Generate optimization visualization and save to HTML file."""
        try:
            # Read from the original optimization file for base data
            factor_values = pd.read_excel(optimization_excel_path, sheet_name="values")
            n_scenarios = 3

            for scenario in range(1, n_scenarios + 1):
                factor_values["Normalized_Scenario_" + str(scenario)] = factor_values["Scenario_" + str(scenario)] / factor_values["Basis"]

            fig = go.Figure()

            for scenario in range(1, n_scenarios + 1):
                fig.add_trace(
                    go.Scatterpolar(
                        theta=factor_values["Factor"],
                        r=factor_values["Normalized_Scenario_" + str(scenario)],
                        name="Scenario_" + str(scenario)
                    ))

            # Update layout for better visibility
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 1]
                    )),
                showlegend=True,
                title="Retrofit Optimization Scenario Comparison"
            )

            # Save to Outputs directory
            html_output_path = CURRENT_DIR_PATH.parent / 'Outputs' / 'optimization_visualization.html'
            html_output_path.parent.mkdir(exist_ok=True)
            fig.write_html(str(html_output_path))
            print(f"Visualization saved to: {html_output_path}")
            
        except Exception as e:
            print(f"Error generating optimization visualization: {str(e)}")

    def extract_field(self, pattern: str, html_text: str) -> str:
        """Extract text matching the pattern from HTML."""
        m = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    def parse_float(self, value: str) -> float:
        """Parse a numeric string that may contain commas or currency symbols."""
        if value is None:
            return 0.0
        cleaned = re.sub(r'[^0-9.+-]', '', str(value))
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def extract_new_materials_from_model(self, model, runner):
        """
        Extract new retrofit materials from AdditionalProperties objects.
        Returns list of materials with name, quantity, and unit.
        
        Assumes AdditionalProperties have keys like:
          - 'retrofit_material_name': str
          - 'retrofit_material_quantity': float
          - 'retrofit_material_unit': str (optional, defaults to 'unit')
        """
        materials = []
        
        try:
            # Iterate through all constructions and look for retrofit materials
            for construction in model.getConstructions():
                props = construction.additionalProperties()
                feature_names = props.featureNames()
                
                if len(feature_names) == 0:
                    continue
                
                # Extract material properties
                material_name = None
                material_quantity = 1.0
                material_unit = "unit"
                unit_cost = None
                total_cost = None
                
                for feature_name in feature_names:
                    feature_name_lower = feature_name.lower()
                    
                    # Extract material name
                    if 'retrofit_material_name' in feature_name_lower or 'material_name' in feature_name_lower:
                        value_str = props.getFeatureAsString(feature_name)
                        if value_str.is_initialized():
                            material_name = value_str.get()
                    
                    # Extract quantity
                    elif 'retrofit_material_quantity' in feature_name_lower or 'material_quantity' in feature_name_lower:
                        value_double = props.getFeatureAsDouble(feature_name)
                        if value_double.is_initialized():
                            material_quantity = value_double.get()
                        else:
                            value_int = props.getFeatureAsInteger(feature_name)
                            if value_int.is_initialized():
                                material_quantity = float(value_int.get())
                    
                    # Extract unit
                    elif 'retrofit_material_unit' in feature_name_lower or 'material_unit' in feature_name_lower:
                        value_str = props.getFeatureAsString(feature_name)
                        if value_str.is_initialized():
                            material_unit = value_str.get()
                    
                    # Extract RSMeans unit cost
                    elif 'rsmeans_unit_cost' in feature_name_lower:
                        value_double = props.getFeatureAsDouble(feature_name)
                        if value_double.is_initialized():
                            unit_cost = value_double.get()
                    
                    # Extract RSMeans total cost
                    elif 'rsmeans_total_cost' in feature_name_lower:
                        value_double = props.getFeatureAsDouble(feature_name)
                        if value_double.is_initialized():
                            total_cost = value_double.get()
                
                # If we found a material name, add it to the list
                if material_name:
                    material_dict = {
                        'name': material_name,
                        'quantity': material_quantity,
                        'unit': material_unit
                    }
                    if unit_cost is not None:
                        material_dict['unit_cost'] = unit_cost
                    if total_cost is not None:
                        material_dict['total_cost'] = total_cost
                    
                    materials.append(material_dict)
                    runner.registerInfo(f"Found retrofit material: {material_name} (qty: {material_quantity} {material_unit})")
            
            runner.registerInfo(f"Extracted {len(materials)} retrofit materials from model AdditionalProperties")
            return materials
        
        except Exception as e:
            runner.registerWarning(f"Error extracting materials from model: {str(e)}")
            return []

    def load_retrofit_materials_from_inputs(self, runner):
        """Load retrofit materials from Inputs/retrofit_materials.json if present."""
        materials_path = CURRENT_DIR_PATH.parent / 'Inputs' / 'retrofit_materials.json'
        if not materials_path.exists():
            return []

        try:
            with open(materials_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                materials = data.get('materials', [])
            elif isinstance(data, list):
                materials = data
            else:
                runner.registerWarning(f"Unexpected JSON format in {materials_path}; expected list or dict with 'materials'.")
                return []

            # Basic validation
            cleaned = []
            for item in materials:
                if not isinstance(item, dict):
                    continue
                name = item.get('name')
                if not name:
                    continue
                cleaned.append({
                    'name': name,
                    'quantity': float(item.get('quantity', 1.0)),
                    'unit': item.get('unit', 'unit')
                })

            runner.registerInfo(f"Loaded {len(cleaned)} retrofit materials from Inputs/retrofit_materials.json")
            return cleaned
        except Exception as e:
            runner.registerWarning(f"Could not read Inputs/retrofit_materials.json: {str(e)}")
            return []

    def extract_building_string(self, html_text: str) -> str:
        """Extract building name from EnergyPlus HTML report."""
        # Primary: find text inside <b> tag after 'Building:'
        m = re.search(r'Building:\s*<b>([^<]+)</b>', html_text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Fallback 1: text after 'Building:' up to next tag
        m2 = re.search(r'Building:\s*([^<\r\n]+)', html_text, flags=re.IGNORECASE)
        if m2:
            return m2.group(1).strip()
        # Fallback 2: strip tags and search line-based
        text = re.sub(r'<[^>]+>', '', html_text)
        m3 = re.search(r'Building:\s*(.+)', text, flags=re.IGNORECASE)
        return m3.group(1).strip() if m3 else ""

    def parse_eplustbl_html(self, html_path, runner):
        """Parse EnergyPlus eplustbl.html report and extract key metrics."""
        if not html_path.exists():
            runner.registerWarning(f"EnergyPlus HTML report not found: {html_path}")
            return {}
        
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        
        data = {}
        
        # Building name
        data["building_name"] = self.extract_building_string(html_text)
        
        # Environment: text inside <b> tag after 'Environment:'
        data["environment"] = self.extract_field(r'Environment:\s*<b>([^<]+)</b>', html_text)
        
        # Simulation hours: extract number from "Values gathered over X hours"
        hours_match = self.extract_field(r'Values gathered over\s+([0-9.]+)\s+hours', html_text)
        data["simulation_hours"] = hours_match if hours_match else ""
        
        # Site and Source Energy from the table
        data["total_site_energy_GJ"] = self.extract_field(
            r'Total Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        data["net_site_energy_GJ"] = self.extract_field(
            r'Net Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        data["total_source_energy_GJ"] = self.extract_field(
            r'Total Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        data["net_source_energy_GJ"] = self.extract_field(
            r'Net Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)

        # Total Energy Cost (if present in Economics Summary)
        data["total_energy_cost_usd"] = self.extract_field(
            r'Total Energy Cost</td>\s*<td[^>]*>\s*\$?([0-9,\.]+)', html_text)
        
        # Building Areas
        data["total_building_area_m2"] = self.extract_field(
            r'Total Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        data["net_conditioned_building_area_m2"] = self.extract_field(
            r'Net Conditioned Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        runner.registerInfo(f"Parsed EnergyPlus report: {data.get('building_name', 'N/A')}")
        return data

    def resolve_energy_cost_per_gj(self, runner, baseline_data):
        """Determine energy cost per GJ from report data or configuration."""
        # 1) Try to derive from baseline report (total cost / total site energy)
        baseline_energy = self.parse_float(baseline_data.get('total_site_energy_GJ'))
        baseline_cost = self.parse_float(baseline_data.get('total_energy_cost_usd'))

        if baseline_energy > 0 and baseline_cost > 0:
            derived = baseline_cost / baseline_energy
            runner.registerInfo(f"Derived energy cost from baseline report: ${derived:.2f}/GJ")
            return derived

        # 2) Check .env override
        load_dotenv()
        env_cost = os.getenv('ENERGY_COST_PER_GJ')
        if env_cost:
            try:
                env_value = float(env_cost)
                runner.registerInfo(f"Using ENERGY_COST_PER_GJ from .env: ${env_value:.2f}/GJ")
                return env_value
            except ValueError:
                runner.registerWarning(f"Invalid ENERGY_COST_PER_GJ in .env: {env_cost}")

        # 3) Check config.ini (if available)
        try:
            config_path = None
            for parent in CURRENT_DIR_PATH.parents:
                candidate = parent / 'config.ini'
                if candidate.exists():
                    config_path = candidate
                    break

            if config_path:
                config = configparser.ConfigParser()
                config.read(config_path)
                if config.has_section('ENERGY_COST') and config.has_option('ENERGY_COST', 'ENERGY_COST_PER_GJ'):
                    cfg_value = float(config.get('ENERGY_COST', 'ENERGY_COST_PER_GJ'))
                    runner.registerInfo(f"Using ENERGY_COST_PER_GJ from config.ini: ${cfg_value:.2f}/GJ")
                    return cfg_value
        except Exception as e:
            runner.registerWarning(f"Could not read ENERGY_COST from config.ini: {str(e)}")

        # 4) Fallback
        runner.registerWarning(f"Falling back to default energy cost: ${DEFAULT_ENERGY_COST_PER_GJ:.2f}/GJ")
        return DEFAULT_ENERGY_COST_PER_GJ
    

    def pull_rsmeans_cost_from_api(self, runner, materials=None):
        """
        Pull RSMeans cost data for retrofit materials from the API and write to Excel.
        Uses credentials from environment variables (client_id, client_secret).
        
        Args:
            runner: OpenStudio runner for logging
            materials: Optional list of materials [{name, quantity, unit}, ...]
                      If None, uses hardcoded example.
        """
        try:
            # Load environment variables
            load_dotenv()
            client_id = os.getenv('client_id')
            client_secret = os.getenv('client_secret')
            
            if not client_id or not client_secret:
                runner.registerWarning("RSMeans API credentials (client_id, client_secret) not found in environment. Skipping RSMeans cost retrieval.")
                return {}
            
            runner.registerInfo("Initializing RSMeans API client...")
            
            # Check if materials already have cost data from AdditionalProperties
            materials_with_costs = [m for m in materials if 'total_cost' in m and m['total_cost'] is not None]
            
            if len(materials_with_costs) == len(materials):
                # All materials have costs, skip API call
                runner.registerInfo(f"All {len(materials)} materials already have cost data from AdditionalProperties. Skipping RSMeans API query.")
                total_cost = sum(m['total_cost'] for m in materials)
                return {
                    'total_cost': total_cost,
                    'materials': materials,
                    'errors': [],
                    'search_log': []
                }
            
            # Initialize the API client (production environment)
            client = RSMeansAPIClient(client_id, client_secret, use_sandbox=False)
            
            # Authenticate with the API
            if not client.authenticate():
                runner.registerWarning("Failed to authenticate with RSMeans API. Skipping cost retrieval.")
                return {}
            
            runner.registerInfo("Successfully authenticated with RSMeans API.")
            
            # Use provided materials or default example
            if not materials:
                materials = [
                    {'name': 'continuous strip footing', 'quantity': 1.0, 'unit': 'unit'}
                ]
                runner.registerInfo("Using default hardcoded material for backwards compatibility")
            
            runner.registerInfo(f"Querying RSMeans API for {len(materials)} materials...")
            
            # Path to save search results
            search_results_path = CURRENT_DIR_PATH.parent / 'Outputs' / 'search_results.json'
            
            # Search for materials in batch (using latest 2025 Q4 release, Green Building catalog)
            batch_results = client.search_materials_batch(
                materials=materials,
                release_id='2025-q4',
                catalog='gb-mf',
                location_id='us-us-national',
                labor_type='std',
                measurement_system='imp',
                save_search_results_path=str(search_results_path)
            )
            
            # Log results
            runner.registerInfo(f"RSMeans query complete. Total cost: ${batch_results['total_cost']:.2f}")
            runner.registerInfo(f"Search results saved to: {search_results_path}")
            
            if batch_results['materials']:
                for mat in batch_results['materials']:
                    runner.registerInfo(f"  - {mat['name']}: ${mat['total_cost']:.2f} ({mat['quantity']} {mat.get('unit', 'units')})")
            
            if batch_results['errors']:
                for error in batch_results['errors']:
                    runner.registerWarning(f"  RSMeans lookup issue: {error}")
            
            # Write aggregated cost to Excel
            if batch_results['total_cost'] > 0 and new_optimization_excel_output_path.exists():
                try:
                    wb = load_workbook(new_optimization_excel_output_path)
                    try:
                        ws = wb.active
                        ws["B4"] = batch_results['total_cost']
                        wb.save(new_optimization_excel_output_path)
                        runner.registerInfo(f"Retrofit materials cost written to Excel: ${batch_results['total_cost']:.2f}")
                    finally:
                        wb.close()
                except Exception as e:
                    runner.registerWarning(f"Could not write cost data to Excel: {str(e)}")
            
            return batch_results
        
        except Exception as e:
            runner.registerWarning(f"Error retrieving RSMeans cost data: {str(e)}")
            return {}

    def compare_energy_results(self, runner):
        """
        Compare energy results between baseline and measure-applied scenarios.
        Returns dictionary with energy deltas and costs.
        """
        baseline_data = {}
        measure_data = {}
        
        try:
            # Parse baseline energy results
            if baseline_eplustbl_path.exists():
                baseline_data = self.parse_eplustbl_html(baseline_eplustbl_path, runner)
                runner.registerInfo(f"Baseline energy data loaded: {baseline_data.get('total_site_energy_GJ', 'N/A')} GJ")
            else:
                runner.registerWarning(f"Baseline eplustbl.html not found at {baseline_eplustbl_path}")
            
            # Parse measure-applied energy results
            if measure_applied_eplustbl_path.exists():
                measure_data = self.parse_eplustbl_html(measure_applied_eplustbl_path, runner)
                runner.registerInfo(f"Measure-applied energy data loaded: {measure_data.get('total_site_energy_GJ', 'N/A')} GJ")
            else:
                runner.registerWarning(f"Measure-applied eplustbl.html not found at {measure_applied_eplustbl_path}")
            
            # Calculate energy deltas
            deltas = {}
            if baseline_data and measure_data:
                try:
                    baseline_energy = float(baseline_data.get('total_site_energy_GJ', 0))
                    measure_energy = float(measure_data.get('total_site_energy_GJ', 0))
                    
                    energy_delta = baseline_energy - measure_energy
                    energy_delta_pct = (energy_delta / baseline_energy * 100) if baseline_energy > 0 else 0
                    energy_cost_per_gj = self.resolve_energy_cost_per_gj(runner, baseline_data)
                    cost_delta = energy_delta * energy_cost_per_gj
                    
                    deltas = {
                        'baseline_energy_GJ': baseline_energy,
                        'measure_energy_GJ': measure_energy,
                        'energy_delta_GJ': energy_delta,
                        'energy_delta_pct': energy_delta_pct,
                        'cost_delta_usd': cost_delta,
                        'energy_cost_per_gj': energy_cost_per_gj,
                        'baseline_building': baseline_data.get('building_name', 'Baseline'),
                        'measure_building': measure_data.get('building_name', 'Measure Applied')
                    }
                    
                    runner.registerInfo(f"Energy Delta: {energy_delta:.2f} GJ ({energy_delta_pct:.1f}%)")
                    runner.registerInfo(f"Cost Delta: ${cost_delta:.2f}/year")
                except ValueError as e:
                    runner.registerWarning(f"Could not convert energy values to float: {str(e)}")
            
            return deltas
        
        except Exception as e:
            runner.registerWarning(f"Error comparing energy results: {str(e)}")
            return {}

    def generate_html_report(self, runner, energy_deltas):
        """Generate a self-contained HTML report with real baseline/measure values and retrofit material costs."""
        try:
            baseline_energy = energy_deltas.get('baseline_energy_GJ', 0.0)
            measure_energy = energy_deltas.get('measure_energy_GJ', 0.0)
            energy_delta = energy_deltas.get('energy_delta_GJ', 0.0)
            energy_delta_pct = energy_deltas.get('energy_delta_pct', 0.0)
            energy_cost_per_gj = energy_deltas.get('energy_cost_per_gj', DEFAULT_ENERGY_COST_PER_GJ)
            retrofit_materials_cost = energy_deltas.get('retrofit_materials_cost', 0.0)
            retrofit_materials = energy_deltas.get('retrofit_materials', [])

            baseline_cost = baseline_energy * energy_cost_per_gj
            measure_cost = measure_energy * energy_cost_per_gj
            cost_delta = energy_deltas.get('cost_delta_usd', baseline_cost - measure_cost)

            def pct(value, total):
                return (value / total * 100.0) if total > 0 else 0.0

            baseline_energy_pct = 100.0
            measure_energy_pct = min(pct(measure_energy, baseline_energy), 100.0) if baseline_energy > 0 else 0.0
            baseline_cost_pct = 100.0
            measure_cost_pct = min(pct(measure_cost, baseline_cost), 100.0) if baseline_cost > 0 else 0.0

            if not html_template_path.exists():
                runner.registerWarning(f"HTML template not found: {html_template_path}")
                return False

            template = html_template_path.read_text(encoding='utf-8')
            
            # Format retrofit materials table if available
            materials_table_html = ""
            if retrofit_materials:
                materials_table_html = "<table>\n"
                materials_table_html += "<tr><th>Material</th><th>Qty</th><th>Unit Cost</th><th>Total Cost</th></tr>\n"
                for mat in retrofit_materials:
                    materials_table_html += f"<tr><td>{mat.get('name', 'Unknown')}</td>"
                    materials_table_html += f"<td>{mat.get('quantity', 0)}</td>"
                    materials_table_html += f"<td>${mat.get('unit_cost', 0):.2f}</td>"
                    materials_table_html += f"<td>${mat.get('total_cost', 0):.2f}</td></tr>\n"
                materials_table_html += "</table>\n"
            
            html = template.format(
                baseline_energy=baseline_energy,
                measure_energy=measure_energy,
                energy_delta=energy_delta,
                energy_delta_pct=energy_delta_pct,
                energy_cost_per_gj=energy_cost_per_gj,
                cost_delta=cost_delta,
                baseline_energy_pct=baseline_energy_pct,
                measure_energy_pct=measure_energy_pct,
                baseline_cost=baseline_cost,
                measure_cost=measure_cost,
                baseline_cost_pct=baseline_cost_pct,
                measure_cost_pct=measure_cost_pct,
                retrofit_materials_cost=retrofit_materials_cost,
                retrofit_materials_table=materials_table_html,
            )

            html_report_path.write_text(html, encoding='utf-8')
            runner.registerInfo(f"HTML report generated: {html_report_path}")
            return True
        except Exception as e:
            runner.registerWarning(f"Error generating HTML report: {str(e)}")
            return False

    def run(self, runner, user_arguments, model):
        # Verify model is provided
        if not model:
            runner.registerError("No model provided to measure.")
            return False

        # Extract AdditionalProperties using OpenStudio API
        props_data = []

        # Iterate through all constructions and extract their additional properties
        for construction in model.getConstructions():
            props = construction.additionalProperties()

            # Check if this construction has any features
            feature_names = props.featureNames()
            if len(feature_names) > 0:
                item = {}

                # Extract each feature - try all type accessors
                for feature_name in feature_names:
                    value = None

                    # Try Double first (most common for numeric data)
                    value_double = props.getFeatureAsDouble(feature_name)
                    if value_double.is_initialized():
                        value = value_double.get()
                    else:
                        # Try Integer
                        value_int = props.getFeatureAsInteger(feature_name)
                        if value_int.is_initialized():
                            value = value_int.get()
                        else:
                            # Try String (always works as fallback)
                            value_str = props.getFeatureAsString(feature_name)
                            if value_str.is_initialized():
                                value = value_str.get()

                    # Store the value if we got something
                    if value is not None:
                        item[feature_name] = value

                if item:
                    item["construction_handle"] = construction.handle().__str__()
                    props_data.append(item)

        # Create DataFrame
        props_df = pd.DataFrame(props_data)

        if not props_df.empty:
            runner.registerInfo(f"Extracted AdditionalProperties from {len(props_data)} constructions.")
            runner.registerInfo(f"AdditionalProperties DataFrame:\n{props_df.to_string()}")
        else:
            runner.registerInfo("No AdditionalProperties found on constructions.")

        # Calculate total embodied carbon if the column exists
        total_gwp = 0.0
        if not props_df.empty and "total_embodied_carbon_kgCO2eq" in props_df.columns:
            # Convert to numeric and sum
            props_df["total_embodied_carbon_kgCO2eq"] = pd.to_numeric(
                props_df["total_embodied_carbon_kgCO2eq"], errors='coerce')
            total_gwp = props_df["total_embodied_carbon_kgCO2eq"].sum()
            runner.registerInfo(f"Total Embodied Carbon (GWP): {total_gwp:.2f} kg CO2 eq")

        # Parse EnergyPlus HTML report if available
        eplustbl_data = {}
        try:
            workflow = runner.workflow()
            if workflow:
                run_dir = Path(workflow.absoluteRunDir())
                runner.registerInfo(f"Looking for eplustbl.html in run directory: {run_dir}")

                # Look for eplustbl.html in common locations
                possible_html_paths = [
                    run_dir / "eplustbl.html",
                    run_dir / "run" / "eplustbl.html",
                    run_dir.parent / "eplustbl.html",
                    run_dir / "reports" / "eplustbl.html",
                ]

                runner.registerInfo(f"Checking {len(possible_html_paths)} possible locations for eplustbl.html")
                for html_path in possible_html_paths:
                    runner.registerInfo(f"  Checking: {html_path} - Exists: {html_path.exists()}")
                    if html_path.exists():
                        eplustbl_data = self.parse_eplustbl_html(html_path, runner)
                        break

                if not eplustbl_data:
                    runner.registerWarning("eplustbl.html not found in any expected location. EnergyPlus summary will be omitted.")
        except Exception as e:
            runner.registerWarning(f"Could not access workflow directory: {str(e)}")

        # Create merged output CSV
        if not props_df.empty or eplustbl_data:
            try:
                with open(optimization_csv_output_path, 'w', newline='', encoding='utf-8') as f:
                    # Write AdditionalProperties section first (transposed and reversed)
                    if not props_df.empty:
                        f.write("# Construction AdditionalProperties\n")
                        # Transpose the dataframe (features as rows, constructions as columns)
                        props_df_transposed = props_df.T
                        # Reverse the order of rows (features)
                        props_df_transposed = props_df_transposed.iloc[::-1]
                        props_df_transposed.to_csv(f)
                        runner.registerInfo(f"Added {len(props_df)} construction records (transposed and reversed) to merged CSV.")
                        f.write("\n")

                    # Write EnergyPlus summary section if available
                    if eplustbl_data:
                        f.write("# EnergyPlus Simulation Summary\n")
                        for key, value in eplustbl_data.items():
                            f.write(f"{key},{value}\n")
                        runner.registerInfo("Added EnergyPlus summary to merged CSV.")

                runner.registerInfo(f"Merged data exported to CSV: {optimization_csv_output_path}")
            except Exception as e:
                runner.registerWarning(f"Could not write merged CSV: {e}")
        else:
            runner.registerInfo("No data to export.")

        # Write result to Excel if we have embodied carbon data
        if total_gwp > 0:
            try:
                self.modify_optimization_sheet(total_gwp)
                runner.registerInfo(f"Updated Excel with embodied carbon value: {total_gwp:.2f} kg CO2 eq")
            except Exception as e:
                runner.registerWarning(f"Could not update Excel: {str(e)}")

        # Generate optimization visualization (always run this)
        try:
            self.optimization()
            runner.registerInfo("Optimization visualization generated and saved to: Outputs/optimization_visualization.html")
        except Exception as e:
            runner.registerWarning(f"Could not generate optimization visualization: {str(e)}")

        # Extract retrofit materials from model AdditionalProperties (or override via Inputs file)
        retrofit_materials = self.load_retrofit_materials_from_inputs(runner)
        if not retrofit_materials:
            retrofit_materials = self.extract_new_materials_from_model(model, runner)

        # Call RSMeans API to get cost data for retrofit materials
        rsmeans_results = self.pull_rsmeans_cost_from_api(runner, materials=retrofit_materials if retrofit_materials else None)

        # Compare energy results between baseline and measure-applied scenarios
        runner.registerInfo("Starting energy comparison analysis...")
        energy_deltas = self.compare_energy_results(runner)

        # Combine results for HTML report
        if energy_deltas and rsmeans_results:
            energy_deltas['retrofit_materials_cost'] = rsmeans_results.get('total_cost', 0.0)
            energy_deltas['retrofit_materials'] = rsmeans_results.get('materials', [])

        # Generate HTML report with energy analysis and costs
        if energy_deltas:
            runner.registerInfo("Generating HTML report...")
            self.generate_html_report(runner, energy_deltas)

        runner.registerInfo("Report complete.")

        return True

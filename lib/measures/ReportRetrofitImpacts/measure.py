# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import sys
import os
from pathlib import Path

# Add measure directory to Python path for resource imports
measure_dir = Path(__file__).parent
if str(measure_dir) not in sys.path:
    sys.path.insert(0, str(measure_dir))

import openstudio
import pandas as pd
from openpyxl import load_workbook
import plotly.graph_objects as go
import requests
import configparser
import re
from dotenv import load_dotenv
from call_RSmeans import RSMeansAPIClient

CURRENT_DIR_PATH = Path(__file__).absolute()
optimization_excel_path = CURRENT_DIR_PATH.parent / 'resources' / 'optimization.xlsx'
new_optimization_excel_output_path = CURRENT_DIR_PATH.parent / 'resources' / 'optimization_updated.xlsx'
optimization_csv_output_path = CURRENT_DIR_PATH.parent / 'resources' / 'retrofit_measure_report.csv'

# Paths for baseline and measure-applied scenarios
tests_dir = CURRENT_DIR_PATH.parent / 'tests'
baseline_run_dir = tests_dir / 'run_baseline'
measure_applied_run_dir = tests_dir / 'run_measure_applied'
baseline_eplustbl_path = baseline_run_dir / 'eplustbl.html'
measure_applied_eplustbl_path = measure_applied_run_dir / 'eplustbl.html'
html_report_path = tests_dir / 'outputs' / 'retrofit_analysis_report.html'

# Energy cost fallback ($/GJ)
DEFAULT_ENERGY_COST_PER_GJ = 15.0  # Used only if no cost data can be derived

# Visualization path
optimization_viz_path = tests_dir / 'outputs' / 'optimization_visualization.html'

class CReport(openstudio.measure.ReportingMeasure):
    def __init__(self):
        super().__init__()

        self.material_data = {}

    def name(self):
        return "ReportAdditionalProperties"

    def description(self):
        return "Reports all AdditionalProperties objects and their key-value pairs in the model."

    def modeler_description(self):
        return "Traverses the model and extracts data from AdditionalProperties objects."

    def parse_workspace_objects(self, objects):
        """Processes a list of OS:AdditionalProperties objects and returns the total numeric value."""
        total = 0.0

        for obj in objects:
            num_fields = obj.numFields()
            if num_fields < 5:
                continue

            material_name = obj.getString(1, True)
            numeric_value = obj.getString(num_fields - 1, True)

            if material_name.is_initialized() and numeric_value.is_initialized():
                try:
                    value = float(numeric_value.get())
                    self.material_data[material_name.get()] = value
                    total += value
                except ValueError:
                    print(f"Warning: Could not convert {numeric_value.get()} to float for {material_name.get()}")

        return round(total, 2)

    def modify_optimization_sheet(self, replacement_value):

        """Reads and modifies Excel spreadsheet for optimization visualizations"""
        wb = load_workbook(optimization_excel_path, data_only=False, keep_links=True)

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

            # Save to HTML file instead of showing in browser
            html_output_path = tests_dir / 'outputs' / 'optimization_visualization.html'
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
    

    def parse_osm_additional_properties(self, osm_path, runner):
        """Parse OS:AdditionalProperties objects directly from an OSM file."""
        import re
        
        if not osm_path.exists():
            runner.registerWarning(f"OSM file not found: {osm_path}")
            return pd.DataFrame()
        
        text = osm_path.read_text(encoding='utf-8', errors='ignore')
        
        # Find all OS:AdditionalProperties blocks
        pattern = r'OS:AdditionalProperties,\s*(.*?)(?=\n\s*(?:OS:|!----|$))'
        matches = re.findall(pattern, text, re.DOTALL)
        
        props_data = []
        for match in matches:
            lines = [line.strip() for line in match.strip().split('\n') if line.strip()]
            
            # Parse the block: every 3 lines = feature_name, data_type, value
            item = {}
            i = 2  # Skip handle and object name lines
            
            while i < len(lines):
                # Feature name
                if i >= len(lines):
                    break
                feature_line = lines[i].split('!-')[0].strip().rstrip(',')
                i += 1
                
                # Data type
                if i >= len(lines):
                    break
                data_type = lines[i].split('!-')[0].strip().rstrip(',')
                i += 1
                
                # Value
                if i >= len(lines):
                    break
                value_line = lines[i].split('!-')[0].strip().rstrip(';,')
                i += 1
                
                # Store the feature
                if feature_line:
                    # Convert value based on data type
                    try:
                        if data_type == "Integer":
                            item[feature_line] = int(value_line)
                        elif data_type == "Double":
                            item[feature_line] = float(value_line)
                        else:  # String
                            item[feature_line] = value_line
                    except ValueError:
                        item[feature_line] = value_line
            
            if item:
                props_data.append(item)
        
        if props_data:
            df = pd.DataFrame(props_data)
            runner.registerInfo(f"Parsed {len(props_data)} AdditionalProperties from OSM file.")
            runner.registerInfo(f"AdditionalProperties DataFrame:\n{df.to_string()}")
            return df
        else:
            runner.registerInfo("No AdditionalProperties found in OSM file.")
            return pd.DataFrame()

    def extract_additional_properties_from_model(self, model, runner):
        """Extract AdditionalProperties from the model and return aggregated data."""
        props_data = []
        
        # Get all construction objects and their additional properties
        for construction in model.getConstructions():
            props = construction.additionalProperties()
            if props.hasFeature("total_embodied_carbon_kgCO2eq"):
                item = {
                    "object_type": "Construction",
                    "object_name": construction.nameString(),
                }
                # Extract all features
                for feature_name in props.featureNames():
                    value = props.getFeatureAsString(feature_name)
                    if value.is_initialized():
                        item[feature_name] = value.get()
                props_data.append(item)
        
        # Also check other model objects if needed
        # (Add more object types here as needed: materials, spaces, etc.)
        
        if props_data:
            runner.registerInfo(f"Found {len(props_data)} objects with AdditionalProperties.")
            # Create DataFrame for easy aggregation
            df = pd.DataFrame(props_data)
            runner.registerInfo(f"AdditionalProperties DataFrame:\n{df.to_string()}")
            return df
        else:
            runner.registerInfo("No AdditionalProperties found on constructions.")
            return pd.DataFrame()

    def pull_rsmeans_cost_from_api(self, runner):
        """
        Pull RSMeans cost data from the API and write to Excel.
        Uses credentials from environment variables (client_id, client_secret).
        """
        try:
            # Load environment variables
            load_dotenv()
            client_id = os.getenv('client_id')
            client_secret = os.getenv('client_secret')
            
            if not client_id or not client_secret:
                runner.registerWarning("RSMeans API credentials (client_id, client_secret) not found in environment. Skipping RSMeans cost retrieval.")
                return
            
            runner.registerInfo("Initializing RSMeans API client...")
            
            # Initialize the API client
            client = RSMeansAPIClient(client_id, client_secret, use_sandbox=True)
            
            # Authenticate with the API
            if not client.authenticate():
                runner.registerWarning("Failed to authenticate with RSMeans API. Skipping cost retrieval.")
                return
            
            runner.registerInfo("Successfully authenticated with RSMeans API.")
            
            # Example: Search for a construction item and retrieve its cost
            # This can be customized based on what materials are in your model
            search_term = "continuous strip footing"  # Example search term
            runner.registerInfo(f"Searching RSMeans database for: {search_term}")
            
            search_results = client.search_unit_costlines(
                release_id='2019-an',
                measurement_system='imp',
                searchTerm=search_term
            )
            
            if search_results and 'items' in search_results and len(search_results['items']) > 0:
                # Get the first result
                first_item = search_results['items'][0]
                division_code = first_item.get('id')
                item_description = first_item.get('description', 'Unknown')
                
                runner.registerInfo(f"Found item: {item_description} (Code: {division_code})")
                
                # Get detailed cost information for this item
                if division_code:
                    cost_line = client.get_unit_costlines(
                        release_id='2019-an',
                        catalog='bc-mf',
                        location_id='us-us-national',
                        labor_type='std',
                        measurement_system='imp',
                        divisionCode=division_code
                    )
                    
                    if cost_line and 'items' in cost_line:
                        for item in cost_line['items']:
                            if item.get('id') == division_code:
                                total_op_cost = item.get('localizedCosts', {}).get('totalOpCost')
                                
                                if total_op_cost is not None:
                                    runner.registerInfo(f"Total operational cost for {item_description}: ${total_op_cost}")
                                    
                                    # Write to Excel if the file exists
                                    if new_optimization_excel_output_path.exists():
                                        try:
                                            wb = load_workbook(new_optimization_excel_output_path)
                                            ws = wb.active
                                            ws["B4"] = total_op_cost
                                            wb.save(new_optimization_excel_output_path)
                                            runner.registerInfo(f"RSMeans cost data written to Excel: {new_optimization_excel_output_path}")
                                        except Exception as e:
                                            runner.registerWarning(f"Could not write cost data to Excel: {str(e)}")
                                else:
                                    runner.registerWarning(f"Total operational cost not found for {division_code}")
                                break
            else:
                runner.registerInfo(f"No results found for search term: {search_term}")
        
        except Exception as e:
            runner.registerWarning(f"Error retrieving RSMeans cost data: {str(e)}")

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
                """Generate a self-contained HTML report with real baseline/measure values."""
                try:
                        baseline_energy = energy_deltas.get('baseline_energy_GJ', 0.0)
                        measure_energy = energy_deltas.get('measure_energy_GJ', 0.0)
                        energy_delta = energy_deltas.get('energy_delta_GJ', 0.0)
                        energy_delta_pct = energy_deltas.get('energy_delta_pct', 0.0)
                        energy_cost_per_gj = energy_deltas.get('energy_cost_per_gj', DEFAULT_ENERGY_COST_PER_GJ)

                        baseline_cost = baseline_energy * energy_cost_per_gj
                        measure_cost = measure_energy * energy_cost_per_gj
                        cost_delta = energy_deltas.get('cost_delta_usd', baseline_cost - measure_cost)

                        def pct(value, total):
                                return (value / total * 100.0) if total > 0 else 0.0

                        baseline_energy_pct = 100.0
                        measure_energy_pct = min(pct(measure_energy, baseline_energy), 100.0) if baseline_energy > 0 else 0.0
                        baseline_cost_pct = 100.0
                        measure_cost_pct = min(pct(measure_cost, baseline_cost), 100.0) if baseline_cost > 0 else 0.0

                        html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Retrofit Measure Analysis Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: white; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #1f4788; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ color: #1f4788; font-size: 28px; margin-bottom: 5px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-top: 5px; }}
        h2 {{ color: #1f4788; font-size: 18px; margin-top: 30px; margin-bottom: 15px; border-left: 4px solid #1f4788; padding-left: 10px; }}
        .section {{ margin-bottom: 30px; }}
        .summary-box {{ background-color: #e8f0f8; border-left: 4px solid #1f4788; padding: 15px; margin-bottom: 20px; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background-color: #1f4788; color: white; padding: 12px; text-align: left; font-weight: bold; border: 1px solid #ddd; }}
        td {{ padding: 10px 12px; border: 1px solid #ddd; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .metric-box {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .metric-card {{ background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1f4788; margin: 10px 0; }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
        .positive {{ color: #28a745; font-weight: bold; }}
        .neutral {{ color: #666; }}
        .recommendation {{ background-color: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0; border-radius: 3px; }}
        .recommendation-title {{ color: #155724; font-weight: bold; margin-bottom: 10px; }}
        .viz-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
        .chart-card {{ border: 1px solid #ddd; border-radius: 6px; padding: 15px; background: #fafafa; }}
        .chart-title {{ font-size: 14px; font-weight: 600; color: #1f4788; margin-bottom: 10px; }}
        .bar-chart {{ display: grid; gap: 10px; }}
        .bar-row {{ display: grid; grid-template-columns: 130px 1fr 80px; align-items: center; gap: 10px; }}
        .bar-label {{ font-size: 12px; color: #444; }}
        .bar-track {{ height: 12px; background: #e6e6e6; border-radius: 6px; overflow: hidden; }}
        .bar {{ height: 100%; border-radius: 6px; }}
        .bar.baseline {{ background: #6c757d; }}
        .bar.retrofit {{ background: #28a745; }}
        .bar-value {{ font-size: 12px; color: #333; text-align: right; white-space: nowrap; }}
        .legend {{ display: flex; gap: 12px; margin-top: 10px; font-size: 12px; color: #555; }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
        .legend-swatch {{ width: 12px; height: 12px; border-radius: 3px; }}
        .iframe-wrap {{ border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: #fff; margin-top: 10px; }}
        .iframe-wrap iframe {{ width: 100%; height: 520px; border: 0; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; text-align: center; }}
        @media print {{ body {{ background-color: white; }} .container {{ max-width: 100%; margin: 0; padding: 0; box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class=\"container\">
        <div class=\"header\">
            <h1>Retrofit Measure Analysis Report</h1>
            <div class=\"subtitle\">Comprehensive Energy and Financial Analysis</div>
        </div>

        <div class=\"section\">
            <h2>Executive Summary</h2>
            <div class=\"summary-box\">
                <p>This report compares energy consumption and operational costs between a baseline building model and the same building with proposed retrofit measures applied. All energy-cost values are derived from the EnergyPlus Economics Summary where available.</p>
            </div>
        </div>

        <div class=\"section\">
            <h2>Energy Analysis</h2>
            <table>
                <tr><th>Metric</th><th>Baseline</th><th>Measure Applied</th><th>Delta</th><th>Savings %</th></tr>
                <tr>
                    <td>Total Site Energy (GJ)</td>
                    <td>{baseline_energy:.2f}</td>
                    <td>{measure_energy:.2f}</td>
                    <td class=\"positive\">{energy_delta:.2f}</td>
                    <td class=\"positive\">{energy_delta_pct:.1f}%</td>
                </tr>
            </table>
        </div>

        <div class=\"section\">
            <h2>Key Performance Metrics</h2>
            <div class=\"metric-box\">
                <div class=\"metric-card\">
                    <div class=\"metric-label\">Annual Energy Savings</div>
                    <div class=\"metric-value positive\">{energy_delta:.2f} GJ</div>
                </div>
                <div class=\"metric-card\">
                    <div class=\"metric-label\">Energy Cost</div>
                    <div class=\"metric-value\">${energy_cost_per_gj:.2f}/GJ</div>
                </div>
                <div class=\"metric-card\">
                    <div class=\"metric-label\">Annual Cost Savings</div>
                    <div class=\"metric-value positive\">${cost_delta:,.2f}</div>
                </div>
                <div class=\"metric-card\">
                    <div class=\"metric-label\">Savings Percent</div>
                    <div class=\"metric-value positive\">{energy_delta_pct:.1f}%</div>
                </div>
            </div>
        </div>

        <div class=\"section\">
            <h2>Comparative Visualizations</h2>
            <div class=\"viz-grid\">
                <div class=\"chart-card\">
                    <div class=\"chart-title\">Energy Comparison (GJ)</div>
                    <div class=\"bar-chart\">
                        <div class=\"bar-row\">
                            <div class=\"bar-label\">Baseline</div>
                            <div class=\"bar-track\"><div class=\"bar baseline\" style=\"width: {baseline_energy_pct:.1f}%;\"></div></div>
                            <div class=\"bar-value\">{baseline_energy:.2f}</div>
                        </div>
                        <div class=\"bar-row\">
                            <div class=\"bar-label\">Measure Applied</div>
                            <div class=\"bar-track\"><div class=\"bar retrofit\" style=\"width: {measure_energy_pct:.1f}%;\"></div></div>
                            <div class=\"bar-value\">{measure_energy:.2f}</div>
                        </div>
                    </div>
                    <div class=\"legend\">
                        <span class=\"legend-item\"><span class=\"legend-swatch\" style=\"background:#6c757d\"></span>Baseline</span>
                        <span class=\"legend-item\"><span class=\"legend-swatch\" style=\"background:#28a745\"></span>Measure Applied</span>
                    </div>
                </div>

                <div class=\"chart-card\">
                    <div class=\"chart-title\">Annual Energy Cost (USD)</div>
                    <div class=\"bar-chart\">
                        <div class=\"bar-row\">
                            <div class=\"bar-label\">Baseline</div>
                            <div class=\"bar-track\"><div class=\"bar baseline\" style=\"width: {baseline_cost_pct:.1f}%;\"></div></div>
                            <div class=\"bar-value\">${baseline_cost:,.2f}</div>
                        </div>
                        <div class=\"bar-row\">
                            <div class=\"bar-label\">Measure Applied</div>
                            <div class=\"bar-track\"><div class=\"bar retrofit\" style=\"width: {measure_cost_pct:.1f}%;\"></div></div>
                            <div class=\"bar-value\">${measure_cost:,.2f}</div>
                        </div>
                    </div>
                    <div class=\"legend\">
                        <span class=\"legend-item\"><span class=\"legend-swatch\" style=\"background:#6c757d\"></span>Baseline</span>
                        <span class=\"legend-item\"><span class=\"legend-swatch\" style=\"background:#28a745\"></span>Measure Applied</span>
                    </div>
                </div>
            </div>

            <div class=\"chart-card\" style=\"margin-top: 20px;\">
                <div class=\"chart-title\">Optimization Visualization</div>
                <p style=\"font-size:12px;color:#666;margin-bottom:8px;\">Embedded from optimization_visualization.html in the same output folder.</p>
                <div class=\"iframe-wrap\">
                    <iframe src=\"optimization_visualization.html\" title=\"Optimization Visualization\"></iframe>
                </div>
            </div>
        </div>

        <div class=\"footer\">
            <p>Generated: February 16, 2026 | Report Type: Retrofit Impact Analysis | Measure: ReportRetrofitImpacts</p>
        </div>
    </div>
</body>
</html>"""

                        html_report_path.write_text(html, encoding='utf-8')
                        runner.registerInfo(f"HTML report generated: {html_report_path}")
                        return True
                except Exception as e:
                        runner.registerWarning(f"Error generating HTML report: {str(e)}")
                        return False
        # Don't call super().run() - it expects a real OSRunner, not our mock
        # super().run(runner, user_arguments)
        
        self.material_data.clear()
        
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
        
        runner.registerInfo(f"Extracted Material Data: {str(self.material_data)}")
        
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
            runner.registerInfo("Optimization visualization generated and saved to: tests/outputs/optimization_visualization.html")
        except Exception as e:
            runner.registerWarning(f"Could not generate optimization visualization: {str(e)}")
        
        # Call RSMeans API to get cost data
        self.pull_rsmeans_cost_from_api(runner)
        
        # Compare energy results between baseline and measure-applied scenarios
        runner.registerInfo("Starting energy comparison analysis...")
        energy_deltas = self.compare_energy_results(runner)
        
        # Generate HTML report with energy analysis and costs
        if energy_deltas:
            runner.registerInfo("Generating HTML report...")
            self.generate_html_report(runner, energy_deltas)

        runner.registerInfo("Report complete.")

        return True

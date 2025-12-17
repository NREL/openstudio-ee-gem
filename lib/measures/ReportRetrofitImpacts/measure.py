# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
import plotly.graph_objects as go
import requests
import re

CURRENT_DIR_PATH = Path(__file__).absolute()
optimization_excel_path = CURRENT_DIR_PATH.parent / 'resources' / 'optimization.xlsx'
new_optimization_excel_output_path = CURRENT_DIR_PATH.parent / 'resources' / 'optimization_updated.xlsx'
optimization_csv_output_path = CURRENT_DIR_PATH.parent / 'resources' / 'retrofit_measure_report.csv'
rsmeans_data_path = CURRENT_DIR_PATH.parent / 'resources' / 'Master_Format_Codes.xlsx'

class ECReport(openstudio.measure.ReportingMeasure):
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

        optimization_weights = pd.read_excel(optimization_excel_path, sheet_name = "weights") # Not being currently used
        factor_values = pd.read_excel(optimization_excel_path, sheet_name = "values")
        n_scenarios = 3

        for scenario in range(1,n_scenarios+1):
            #print(scenario)
            factor_values["Normalized_Scenario_" + str(scenario)] = factor_values["Scenario_" + str(scenario)]/factor_values["Basis"]

        fig = go.Figure()

        for scenario in range(1, n_scenarios+1):
            fig.add_trace(
                go.Scatterpolar(
                    theta = factor_values["Factor"],
                    r = factor_values["Normalized_Scenario_" + str (scenario)], name = "Scenario_" + str(scenario)
                ))

        fig.show()

    def extract_field(self, pattern: str, html_text: str) -> str:
        """Extract text matching the pattern from HTML."""
        m = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

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
        
        # Building Areas
        data["total_building_area_m2"] = self.extract_field(
            r'Total Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        data["net_conditioned_building_area_m2"] = self.extract_field(
            r'Net Conditioned Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
        
        runner.registerInfo(f"Parsed EnergyPlus report: {data.get('building_name', 'N/A')}")
        return data
    
    def pull_rsmeans_cost(self, sheet_name, code_3):
        """
        Pulls RSMeans cost data from the Excel file. Currently, user needs to provide
        sheet name and Column E value from Master Format Codes
        """
        #
        rsmeans_data = pd.read_excel(rsmeans_data_path, sheet_name=sheet_name)
        product_cost = rsmeans_data.loc[rsmeans_data['Code 3'] == code_3, 'Total Incl O&P'].values
        if len(product_cost) > 0:
            print("RSMeans Total Incl O&P (USD) = " + str(product_cost[0]))
        else:
            print("No cost found for the given code.")
        return


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

    def run(self, runner, user_arguments):
        # Don't call super().run() - it expects a real OSRunner, not our mock
        # super().run(runner, user_arguments)
        
        self.material_data.clear()
        
        # Load the model from the output OSM file using OpenStudio API
        model = None
        if runner.workflow().is_initialized():
            workflow = runner.workflow().get()
            run_dir = Path(workflow.absoluteRunDir())
            # Common locations for output OSM
            possible_paths = [
                run_dir / "in.osm",
                run_dir / "out_DOE_small_office.osm",  # Test file name
                run_dir.parent / "in.osm",
                run_dir / "run" / "in.osm",
            ]
            # Also check for any .osm file in the directory
            if run_dir.exists():
                for osm_file in run_dir.glob("*.osm"):
                    possible_paths.append(osm_file)
            
            for path in possible_paths:
                if path.exists():
                    runner.registerInfo(f"Loading model from: {path}")
                    # Load model using OpenStudio API
                    translator = openstudio.osversion.VersionTranslator()
                    model_opt = translator.loadModel(str(path))
                    if model_opt.is_initialized():
                        model = model_opt.get()
                        runner.registerInfo("Model loaded successfully via OpenStudio API")
                        break
        
        if not model:
            runner.registerError("Could not load model from output OSM file.")
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
        if runner.workflow().is_initialized():
            workflow = runner.workflow().get()
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

        # Write result to Excel
        if total_gwp > 0:
            self.modify_optimization_sheet(total_gwp)
            self.optimization()
        
        self.pull_rsmeans_cost("windows costs", "08 53 13.40")

        runner.registerInfo("Report complete.")

        return True

# Register the measure
measure = ECReport()

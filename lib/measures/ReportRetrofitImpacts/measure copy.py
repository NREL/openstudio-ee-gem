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

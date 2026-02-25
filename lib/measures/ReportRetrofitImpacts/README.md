

###### (Automatically generated documentation)

# ReportRetrofitImpacts

## Description
This reporting measure compares a baseline model against a measure-applied model, extracts energy results from EnergyPlus HTML reports, derives real $/GJ from the Economics Summary when available, and generates a final HTML report with side-by-side visualizations and the optimization chart.

## Modeler Description
Workflow summary:
1) Parse baseline and measure-applied EnergyPlus reports (eplustbl.html).
2) Compute deltas (energy, percent savings, and annual cost savings).
3) Generate optimization visualization (Plotly HTML).
4) Write the final HTML report to tests/outputs/retrofit_analysis_report.html with embedded visuals.

## Measure Type
ReportingMeasure

## Taxonomy


## Arguments

## Inputs Required Before Running
1) Baseline EnergyPlus report: Inputs/run_baseline/eplustbl.html
2) Measure-applied EnergyPlus report: Inputs/run_measure_applied/eplustbl.html
3) Retrofit materials list: Inputs/retrofit_materials.json (optional; overrides model-derived materials if present)
4) HTML template: resources/retrofit_report_template.html
5) Example model for local run: Inputs/example_measure_applied.osm
6) Baseline seed model for workflow: Inputs/example_baseline.osm
## How to Run
1) Ensure the baseline and measure-applied eplustbl.html files exist in Inputs/run_baseline and Inputs/run_measure_applied.
2) Run the test harness:
	python apply_measure.py
3) Open the final report at tests/outputs/retrofit_analysis_report.html.


### Tasty Treats

**Name:** template_section,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Material Properties

**Name:** mat_prop_section,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### General Building Information

**Name:** general_building_information_section,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false





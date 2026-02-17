

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
- Baseline EnergyPlus report: tests/run_baseline/eplustbl.html
- Measure-applied EnergyPlus report: tests/run_measure_applied/eplustbl.html
- Optional: .env with ENERGY_COST_PER_GJ to override (only used if Economics Summary is missing)
- Optional: config.ini with [ENERGY_COST] ENERGY_COST_PER_GJ (fallback if .env missing)

## How to Run
1) Ensure the baseline and measure-applied eplustbl.html files exist in tests/run_baseline and tests/run_measure_applied.
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





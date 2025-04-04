import pandas as pd
import numpy as np
import itertools as itr
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from openpyxl import load_workbook

# Define current and target paths
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
excel_path = CURRENT_DIR_PATH.parent / 'resources' / 'optimization.xlsx'

optimization_weights = pd.read_excel(excel_path, sheet_name = "weights")

factor_values = pd.read_excel(excel_path, sheet_name = "values")

n_scenarios = 3

for scenario in range(1,n_scenarios+1):
    #print(scenario)
    factor_values["Normalized_Scenario_" + str(scenario)] = factor_values["Scenario_" + str(scenario)]/factor_values["Basis"]


fig = go.Figure()

for scenario in range(1,n_scenarios+1):
    fig.add_trace(
        go.Scatterpolar(
            theta = factor_values["Factor"],
            r = factor_values["Normalized_Scenario_" + str (scenario)], name = "Scenario_" + str(scenario) 
        ))
    
fig.show()
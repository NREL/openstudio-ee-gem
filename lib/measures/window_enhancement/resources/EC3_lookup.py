# EC3 API Lookup Script
import requests
import json
import re
from typing import Dict, Any, List
from pathlib import Path
import configparser
from datetime import datetime
import os
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

# #find material_name by category
# material_category = {"concrete":{"ReadyMix","Precast","CementGrout","FlowableFill"},
#                      "masonry":{"Brick", "CMU"},
#                      "steel":{"RebarSteel","WireMeshSteel","ColdFormedSteel","StructuralSteel"},
#                      "aluminum":{"AluminiumExtrusions"},
#                      "wood":{"PrefabricatedWood","DimensionLumbe","SheathingPanels","CompositeLumber","MassTimber","NonStructuralWood"},
#                      "sheathing":{"GypsumSheathingBoard","CementitiousSheathingBoard"},
#                      "thermal_moisture_protection":{"Insulation","MembraneRoofing"},
#                      "cladding":{"RoofPanels","InsulatedRoofPanels","WallPanels","InsulatedWallPanels"},
#                      "openings":{"glazing":["InsulatingGlazingUnits","FlatGlassPanes","ProcessedNonInsulatingGlassPanes"],
#                                  "extrusions":["AluminiumExtrusions"]},
#                      "finishes":{"CementBoard","Gypsum","Tiling","CeilingPanel","Flooring","PaintingAndCoating"}
#                      }
# for testing use, do not delete
material_category = {
                     "test":["AluminiumExtrusions"]
                     }

def generate_url(material_name, endpoint ="materials", page_number=1, page_size=250, jurisdiction="021", date=None, option=None, boolean="yes",
                  glass_panes=None, epd_type="Product"):
    '''
    jurisdiction = "021" means Northern America region
    '''
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")  # use today's date as default
    url = (
        f"https://api.buildingtransparency.org/api/{endpoint}"
        f"?page_number={page_number}&page_size={page_size}"
        f"&mf=!EC3%20search(%22{material_name}%22)%20WHERE%20"
        f"%0A%20%20jurisdiction%3A%20IN(%22{jurisdiction}%22)%20AND%0A%20%20"
        f"epd__date_validity_ends%3A%20%3E%20%22{date}%22%20AND%0A%20%20"
        f"epd_types%3A%20IN(%22{epd_type}%20EPDs%22)%20"
    )
    conditions = []
    if option and boolean:
        conditions.append(f"{option}%3A%20{boolean}")

    if glass_panes:
        conditions.append(f"glass_panes%3A%20%3E~%20{glass_panes}")

    if conditions:
        url += "AND%0A%20%20" + "%20AND%0A%20%20".join(conditions) + "%20%0A"

    url += "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
    
    return url

def fetch_epd_data(url,api_token):
    """
    input url address generted by generate_url()
    Fetch EPD data from the EC3 API.
    return: Parsed JSON response or empty list on failure.
    """
    try: 
        print(f"Fetching data from URL: {url}")  # Log the URL being fetched
        # API configuration
        HEADERS = {"Accept": "application/json", "Authorization": "Bearer " + api_token}
        response = requests.get(url, headers=HEADERS, verify=False)
        response.raise_for_status() # HTTPError if failure 
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        if 'response' in locals():  # Check if response was defined
            print(f"Response content: {response.text}")
        else:
            print("No response content available.")
        return []

def parse_product_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse GWP data for a given EPD.
    :param epd: EPD dictionary
    :return: Parsed GWP data
    """
    # initialize parameters and dictionary
    parsed_data = {}
    gwp_per_m3 = 0.0
    gwp_per_m2 = 0.0
    gwp_per_kg = 0.0

    # extract information from EPD's json repsonse
    declared_unit = epd.get("declared_unit")
    thickness = epd.get("thickness")
    gwp_per_declared_unit = epd.get("gwp")
    mass_per_declared_unit = epd.get("mass_per_declared_unit")
    density = epd.get("density")
    gwp_per_kg = epd.get("gwp_per_kg")
    epd_name = epd.get('name')
    description = epd.get('description')
    original_ec3_link = epd['manufacturer']['original_ec3_link']

    # Per mass
    if gwp_per_kg != None:
        gwp_per_kg = extract_numeric_value(gwp_per_kg)

    elif gwp_per_kg == None and "t" in declared_unit:
        gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_kg = gwp_per_kg/1000 # convert from t to kg

    elif gwp_per_kg == None and "kg" in declared_unit:
        gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)

    elif mass_per_declared_unit != None and gwp_per_kg == None and not any(unit in declared_unit for unit in ["kg", "t"]):
        gwp_per_kg = divide(gwp_per_declared_unit, mass_per_declared_unit)

    # Per volume
    if "m3" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)

    elif "cf" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_m3 = gwp_per_m3 * 35.3147 # convert from cubic feet to m3

    elif "m2" in declared_unit and thickness and "mm" in thickness:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_m3 = gwp_per_m2/(extract_numeric_value(thickness)/1000)

    elif density and "kg / m3" in density and gwp_per_kg:
        gwp_per_m3 = multiply(gwp_per_kg, density)

    # Per area
    if "m2" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)

    elif "sf" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_m2 = gwp_per_m2 * 10.7639 # convert from square feet to m2

    elif "m3" in declared_unit and thickness and "mm" in thickness:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_m2 = gwp_per_m3 * (extract_numeric_value(thickness)/1000)
    
    parsed_data["epd_name"] = epd_name
    parsed_data["declared_unit"] = declared_unit
    parsed_data["gwp_per_declared_unit"] = gwp_per_declared_unit
    parsed_data["mass_per_declared_unit"] = mass_per_declared_unit
    parsed_data["thickness"] = thickness
    parsed_data["density"] = density
    parsed_data["gwp_per_m3 (kg CO2 eq/m3)"] = gwp_per_m3
    parsed_data["gwp_per_m2 (kg CO2 eq/m2)"] = gwp_per_m2
    parsed_data["gwp_per_kg (kg CO2 eq/kg)"] = gwp_per_kg 
    parsed_data["original_ec3_link"] = original_ec3_link
    parsed_data["description"] = description

    return parsed_data

def parse_industrial_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse GWP data for a given EPD.
    :param epd: EPD dictionary
    :return: Parsed GWP data
    """

    parsed_data = {}
    gwp_per_m3 = 0.0
    gwp_per_m2 = 0.0
    gwp_per_kg = 0.0

    declared_unit = epd.get("declared_unit")
    gwp_per_kg = epd.get("gwp_per_kg")
    gwp_per_declared_unit = epd.get("gwp")
    epd_name = epd.get('name')
    original_ec3_link = epd.get('original_ec3_link')
    description = epd.get('description')
    density_min = epd.get('density_min')
    density_max = epd.get('density_max')
    area = epd.get('area')

    if density_min is not None and density_max is not None:
        density_avg = (extract_numeric_value(density_max) + extract_numeric_value(density_min))/2
    elif density_min is not None:
        density_avg = extract_numeric_value(density_min)
    elif density_max is not None:
        density_avg = extract_numeric_value(density_max)
    else:
        density_avg = None

    # Per area (stop using this becasue the area value is not sensible)
    # if "m^2" in area:
    #     gwp_per_m2 = extract_numeric_value(gwp_per_declared_unit)/extract_numeric_value(area)

    # Per mass
    if "t" in declared_unit:
        gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
        gwp_per_kg = gwp_per_kg / 1000 # convert to kg
    elif "kg" in declared_unit:
        gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)

    # Per volume
    if gwp_per_kg != None and density_avg != None:
        gwp_per_m3 = gwp_per_kg * density_avg
        
    parsed_data["epd_name"] = epd_name
    parsed_data["declared_unit"] = declared_unit
    parsed_data["gwp_per_declared_unit"] = gwp_per_declared_unit
    parsed_data["density_min"] = density_min
    parsed_data["density_max"] = density_max
    parsed_data["area"] = area
    parsed_data["gwp_per_m3 (kg CO2 eq/m3)"] = gwp_per_m3
    parsed_data["gwp_per_m2 (kg CO2 eq/m2)"] = gwp_per_m2
    parsed_data["gwp_per_kg (kg CO2 eq/kg)"] = gwp_per_kg 
    parsed_data["original_ec3_link"] = original_ec3_link
    parsed_data["description"] = description

    return parsed_data

def extract_numeric_value(value: Any) -> float:
    """
    Extract numeric value from a string or number.
    :param value: Value to process
    :return: Extracted numeric value
    """
    match = re.search(r"[-+]?\d*\.?\d+", str(value))
    return float(match.group()) if match else 0.0

# extract numeric values then divide
def divide(member: Any, denominator: Any) -> float:
    try:
        member_value = extract_numeric_value(member)
        denominator_value = extract_numeric_value(denominator)
        return round(member_value/denominator_value, 2)
    except ZeroDivisionError:
        return 0.0

# extract numeric values then multiply
def multiply(multiplicand: Any, multiplier: Any) -> float:

    multiplicand_value = extract_numeric_value(multiplicand)
    multiplier_value = extract_numeric_value(multiplier)
    return round(multiplicand_value * multiplier_value, 2)

def calculate_geometry(self, sub_surface):
    """
    Calculate the length, width, perimeter, and area of the window from its vertices.
    Assumes the window is a quadrilateral (typically a rectangle).
    """
    vertices = sub_surface.vertices()
    if len(vertices) != 4:
        return {
            "length": 0.0,
            "width": 0.0,
            "perimeter": 0.0,
            "area": 0.0
        }

    # Calculate all edge lengths
    edge_lengths = []
    perimeter = 0.0
    for i in range(4):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % 4]
        edge = v2 - v1
        length = edge.length()
        edge_lengths.append(length)
        perimeter += length

    # Assume opposite edges are equal, so we can group into two unique lengths
    length = max(edge_lengths)
    width = min(edge_lengths)

    # Area = length × width
    area = length * width

    return {
        "length": length,
        "width": width,
        "perimeter": perimeter,
        "area": area
    }

def main():
    """
    Main function to execute the script.
    """
    print("Fetching EC3 EPD data...")

    for category, list in material_category.items():
        print(material_category[category])
        for name in list:
            print(name)
            product_url = generate_url(name, endpoint="materials", epd_type="Product")
            industry_url = generate_url(name, endpoint="industry_epds", epd_type="Industry")

            product_epd_data = fetch_epd_data(product_url,API_TOKEN) 
            industrial_epd_data = fetch_epd_data(industry_url,API_TOKEN)
            print(f"Number of  product EPDs for {name}: {len(product_epd_data)}")
            print(f"Number of  industrial EPDs for {name}: {len(industrial_epd_data)}")
            for idx, epd in enumerate(product_epd_data, start=1):
                parsed_data = parse_product_epd(epd)
                print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")
            for idx, epd in enumerate(industrial_epd_data, start=1):
                parsed_data = parse_industrial_epd(epd)
                print(f"Industrial EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

if __name__ == "__main__":
    main()
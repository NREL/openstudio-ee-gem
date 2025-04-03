# EC3 API Lookup Script
import requests
import json
import re
from typing import Dict, Any, List
from pathlib import Path
import configparser
from datetime import datetime
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

# #find material_name by category
material_category = {"concrete":["ReadyMix","Precast"],
                     "glazing":["InsulatingGlazingUnits","FlatGlassPanes","ProcessedNonInsulatingGlassPanes"],
                     "extrusions":["AluminiumExtrusions"],
                     "steel":["Rebar","WireMeshSteel","ColdFormedFraming","DeckingSteel","HotRolledSections","HollowSections","PlateSteel","RoofPanels","WallPanels","CoilSteel"]
                     }
# for testing use, do not delete
# material_category = {
#                      "glazing":["InsulatingGlazingUnits"],
#                      "extrusions":["AluminiumExtrusions"]
#                      }

def generate_url(material_name, endpoint ="materials", page_number=1, page_size=250, jurisdiction="021", date=None, option=None, boolean="yes", glass_panes=None, epd_type="Product"):
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

# API configuration
HEADERS = {"Accept": "application/json", "Authorization": "Bearer " + API_TOKEN}

# Constants
EXCLUDE_KEYS = [
    'manufacturer', 'plant_or_group', 'category', 'created_on', 'updated_on',
    'gwp', 'gwp_z', 'pct80_gwp_per_category_declared_unit', 'conservative_estimate',
    'best_practice', 'standard_deviation', 'uncertainty_factor',
    'uncertainty_adjusted_gwp', 'lowest_plausible_gwp'
]

def fetch_epd_data(url):
    """
    input url address generted by generate_url()
    Fetch EPD data from the EC3 API.
    return: Parsed JSON response or empty list on failure.
    """
    try: 
        print(f"Fetching data from URL: {url}")  # Log the URL being fetched
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

def parse_gwp_data(epd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse GWP data for a given EPD.
    :param epd: EPD dictionary
    :return: Parsed GWP data
    """

    parsed_data = {}
    gwp_per_unit_volume = 0.0
    gwp_per_unit_area = 0.0
    gwp_per_unit_mass = 0.0

    declared_unit = epd.get("declared_unit")
    thickness_unit = epd.get("thickness")
    gwp_per_category_declared_unit = epd.get("gwp_per_category_declared_unit")
    density_unit = epd.get("density")
    gwp_per_unit_mass = epd.get("gwp_per_kg")
    original_ec3_link = epd['plant_or_group']['owned_by']['original_ec3_link']
    description = epd['category']['description']

    # Per volume
    if declared_unit and "m3" in declared_unit:
        gwp_per_unit_volume = calculate_gwp_per_volume(gwp_per_category_declared_unit, declared_unit)
    elif declared_unit and "m2" in declared_unit and thickness_unit and "mm" in str(thickness_unit):
        gwp_per_unit_volume = calculate_gwp_per_volume_from_area(gwp_per_category_declared_unit, thickness_unit)
    elif density_unit and gwp_per_unit_mass:
        gwp_per_unit_volume = calculate_gwp_from_density_and_mass(gwp_per_unit_mass, density_unit)

    # Per area
    if declared_unit and "sf" in declared_unit:
        gwp_per_unit_area = calculate_gwp_per_area(gwp_per_category_declared_unit, declared_unit)

    # Per mass
    if gwp_per_unit_mass:
        gwp_per_unit_mass = extract_numeric_value(gwp_per_unit_mass)

    parsed_data["gwp_per_unit_volume (kg CO2 eq/m3)"] = gwp_per_unit_volume
    parsed_data["gwp_per_unit_area (kg CO2 eq/m2)"] = gwp_per_unit_area
    parsed_data["gwp_per_unit_mass (kg CO2 eq/kg)"] = gwp_per_unit_mass 
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

def calculate_gwp_per_volume(gwp: Any, declared_unit: Any) -> float:
    """
    Calculate GWP per volume.
    :param gwp: GWP per category declared unit
    :param declared_unit: Declared unit
    :return: GWP per volume
    """
    try:
        gwp_value = extract_numeric_value(gwp)
        declared_value = extract_numeric_value(declared_unit)
        return gwp_value / declared_value
    except ZeroDivisionError:
        return 0.0

def calculate_gwp_per_volume_from_area(gwp: Any, thickness_unit: Any) -> float:
    """
    Calculate GWP per volume from area and thickness.
    :param gwp: GWP per category declared unit
    :param thickness_unit: Thickness unit
    :return: GWP per volume
    """
    try:
        thickness = extract_numeric_value(thickness_unit) * 1e-3  # Convert mm to meters
        gwp_value = extract_numeric_value(gwp)
        return gwp_value / thickness
    except ZeroDivisionError:
        return 0.0

def calculate_gwp_from_density_and_mass(gwp_mass: Any, density_unit: Any) -> float:
    """
    Calculate GWP per volume using density and mass.
    :param gwp_mass: GWP per mass
    :param density_unit: Density unit
    :return: GWP per volume
    """
    density = extract_numeric_value(density_unit)
    gwp_mass = extract_numeric_value(gwp_mass)
    return round(gwp_mass * density, 2)

def calculate_gwp_per_area(gwp: Any, declared_unit: Any) -> float:
    """
    Calculate GWP per area.
    :param gwp: GWP per category declared unit
    :param declared_unit: Declared unit
    :return: GWP per area
    """
    try:
        gwp_value = extract_numeric_value(gwp)
        declared_value = extract_numeric_value(declared_unit)
        return round((gwp_value / declared_value) / 0.092903, 2)  # Convert m2 to ft2
    except ZeroDivisionError:
        return 0.0

def main():
    """
    Main function to execute the script.
    """
    print("Fetching EC3 EPD data...")

    for category, list in material_category.items():
        print(material_category[category])
        for name in list:
            print(name)
            product_url = generate_url(name)
            industry_url = generate_url(name, endpoint="industry_epds", epd_type="Indsutry")
            epd_data = fetch_epd_data(product_url) + fetch_epd_data(industry_url)
            print(f"Number of  EPDs for {name}: {len(epd_data)}")
            if len(epd_data) == 0:
                sys.exit
            for idx, epd in enumerate(epd_data, start=1):
                parsed_data = parse_gwp_data(epd)
                print(f"EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

if __name__ == "__main__":
    main()
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
import pprint as pp
import urllib.parse

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

# the dictionary below stores the material_name for generate_url function
# material_category = {"concrete":{"ReadyMix","PrecastConcrete","CementGrout","FlowableFill"},
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
                     "test":["Insulation"]
                     }
# Generate a EC3 API URL with search and filters
def generate_url(material_name, endpoint ="materials", page_number=1, page_size=3, jurisdiction="021", date=None, option=None, boolean="yes",
                  glass_panes=None, epd_type="Product", insulation_application = None, insulation_material = None):
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
    
    if insulation_material:
        url += f"%20AND%0A%20%20insulating_material%3A%20IN(%22{insulation_material}%22)"
    
    if insulation_application:
        url += f"%20AND%0A%20%20insulation_intended_application%3A%20IN(%22{insulation_application}%22)%20"

    url += "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
    
    return url

def generate_url_byname(query: str = None,
                        name_like: str = None,
                        description_like: str = None,
                        category: str = None,
                        page_number: int = 1,
                        page_size: int = 250,
                        declaration_type: str = "Product EPD",
                        plant_geography: str = "021") -> str:
    """
    Generate a URL for fetching EPD data based on EPD name or description.
    jurisdiction = "021" means Northern America region
    Don't change the order of parameters in the URL, otherwise the API won't work.
    """
    base_url = "https://api.buildingtransparency.org/api/epds"
    params = [
        ("page_number", page_number),
        ("page_size", page_size),
        ("sort_by", "-updated_on"),
    ]
        # Place category immediately after sort_by if provided.
    if category:
        # e.g., insulation: "bf1c8882d7784db4b10d9d5698b8b5cc"
        # door hardware: "ca54e842c0fc4bf2b4f3a8564c3b1a4d"
        params.append(("category", category))

    # Add the rest
    if query:
        params.append(("q", query))
    if name_like:
        params.append(("name__like", name_like))
    if description_like:
        params.append(("description__like", description_like))
    if plant_geography:
        params.append(("plant_geography", plant_geography))
    if declaration_type:
        params.append(("declaration_type", declaration_type))

    return f"{base_url}?{urllib.parse.urlencode(params)}"

# this function is sending API call, the response is json format
def fetch_epd_data(url,api_token):
    """
    input url address generted by generate_url()
    Fetch EPD data from the EC3 API.
    return: Parsed JSON response or empty list on failure.
    """
    try: 
        # print(f"Fetching data from URL: {url}")  # Log the URL being fetched
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
# process the json response obtained from fetch_epd_data function for product epds
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

    # pp.pprint(epd)
    # extract information from EPD's json repsonse
    declared_unit = epd.get("declared_unit")
    thickness = epd.get("thickness")
    gwp_per_declared_unit = epd.get("gwp")
    mass_per_declared_unit = epd.get("mass_per_declared_unit")
    density = epd.get("density")
    gwp_per_kg = extract_numeric_value(epd.get("gwp_per_kg"))
    epd_name = epd.get('name')
    description = epd.get('description')
    original_ec3_link = epd['manufacturer']['original_ec3_link']
    # For the two parameters below, need to confirm the accuracy of data before using; for insulation material, the mass per declared unit is always 2.04 kg,
    # not sure where this 2.04 kg is from, didn't see it in EPD, better not to use
    category_mass_per_declared_unit = epd['category']['mass_per_declared_unit']
    category_decalred_unit = epd['category']['declared_unit']

    if mass_per_declared_unit is None and category_mass_per_declared_unit is not None and any(x in category_decalred_unit for x in ["m2", "m^2"]):
        mass_per_declared_unit = divide(category_mass_per_declared_unit,category_decalred_unit)

    # Per kg
    if gwp_per_kg is None or gwp_per_kg == 0.0:
        if "t" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
        elif "kg" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
        # handle when mass_per_declared_unit exist
        elif mass_per_declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, mass_per_declared_unit)

    # Per m3
    if any(x in declared_unit for x in ["m3", "m^3"]): # these functional units come in differnet expression style, need to incorporate different styles by looking into json reponse
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
    elif "cf" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147 # convert from cubic feet to m3
    elif any(x in declared_unit for x in ["m\u00b2","m2", "m^2"]) and thickness and "mm" in thickness:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)/(extract_numeric_value(thickness)/1000)
    elif density and any(x in density for x in ["kg / m3", "kg / m^3"]) and gwp_per_kg:
        gwp_per_m3 = multiply(gwp_per_kg, density)

    # Per m2
    if any(x in declared_unit for x in ["m\u00b2","m2", "m^2"]):
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
    elif any(x in declared_unit for x in ["ft²","sf", "ft^2"]):
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639 # convert from square feet to m2
    elif any(x in declared_unit for x in ["m3", "m^3"]) and thickness and "mm" in thickness:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness)/1000)
    
    parsed_data["epd_name"] = epd_name
    parsed_data["declared_unit"] = declared_unit
    parsed_data["gwp_per_declared_unit"] = gwp_per_declared_unit
    parsed_data["mass_per_declared_unit"] = mass_per_declared_unit
    parsed_data["thickness"] = thickness
    parsed_data["density"] = density
    parsed_data["gwp_per_m3 (kg CO2 eq/m3)"] = gwp_per_m3
    parsed_data["gwp_per_m2 (kg CO2 eq/m2)"] = gwp_per_m2
    parsed_data["gwp_per_kg (kg CO2 eq/kg)"] = gwp_per_kg 
    parsed_data["category_mass_per_declared_unit"] = category_mass_per_declared_unit
    parsed_data["category_decalred_unit"] = category_decalred_unit
    parsed_data["original_ec3_link"] = original_ec3_link
    parsed_data["description"] = description

    return parsed_data
# process the json response obtained from fetch_epd_data function for industrial epds
def parse_industrial_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse GWP data for a given EPD.
    :param epd: EPD dictionary
    :return: Parsed GWP data
    """

    # pp.pprint(epd)

    file_path = "my_data.json"

    with open(file_path, 'w') as json_file:
        json.dump(epd, json_file)

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
    servicelife_min = epd.get('reference_service_life_min')
    servicelife_max = epd.get('reference_service_life_max')
    thickness_per_declared_unit_min = epd.get('thickness_per_declared_unit_min')
    thickness_per_declared_unit_max = epd.get('thickness_per_declared_unit_max')
    mass_per_declared_unit = epd.get('mass_per_declared_unit')
    area = epd.get('area')

    density_avg = compute_average(density_min, density_max)
    servicelife_avg = compute_average(servicelife_min,servicelife_max)
    thickness_per_declared_unit_avg = compute_average(thickness_per_declared_unit_min,thickness_per_declared_unit_max)

    # Per kg
    if gwp_per_kg is None or gwp_per_kg == 0.0:
        if "t" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
        elif "kg" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
        # handle when mass_per_declared_unit exist
        elif mass_per_declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, mass_per_declared_unit)

    # Per m3
    if any(x in declared_unit for x in ["m3", "m^3"]):
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
    elif "cf" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147 # convert from cubic feet to m3
    elif any(x in declared_unit for x in ["m\u00b2","m2", "m^2"]) and thickness_per_declared_unit_avg and "mm" in thickness_per_declared_unit_min:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)/(extract_numeric_value(thickness_per_declared_unit_avg)/1000)
    elif density_avg and gwp_per_kg:
        gwp_per_m3 = multiply(gwp_per_kg, density_avg)

    # Per m2
    if any(x in declared_unit for x in ["m\u00b2","m2", "m^2"]):
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
    elif "sf" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639 # convert from square feet to m2
    elif any(x in declared_unit for x in ["m3", "m^3"]) and thickness_per_declared_unit_avg and (("mm" in thickness_per_declared_unit_min) or ("mm" in thickness_per_declared_unit_max)):
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness_per_declared_unit_avg)/1000)
        
    parsed_data["epd_name"] = epd_name
    parsed_data["declared_unit"] = declared_unit
    parsed_data["gwp_per_declared_unit"] = gwp_per_declared_unit
    parsed_data["density_min"] = density_min
    parsed_data["density_max"] = density_max
    parsed_data["reference_service_life_min"] = servicelife_min
    parsed_data["reference_service_life_max"] = servicelife_max
    parsed_data["thickness_per_declared_unit_min"] = thickness_per_declared_unit_min
    parsed_data["thickness_per_declared_unit_max"] = thickness_per_declared_unit_max
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
        member_value = extract_numeric_value(member)
        denominator_value = extract_numeric_value(denominator)
        return member_value/denominator_value

# extract numeric values then multiply
def multiply(multiplicand: Any, multiplier: Any) -> float:
    multiplicand_value = extract_numeric_value(multiplicand)
    multiplier_value = extract_numeric_value(multiplier)
    return multiplicand_value * multiplier_value
# when vertex coordinates are provided in openstudio model, this function can calculate area, perimeter, width and length
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
# handle the case when no epd returned from API request 
def test_empty_epd(primary, fallback):
    if primary:
        return True
    elif fallback:
        return False
    else:
        return None

def compute_gwp_data(keys, epd_list_by_material, epd_type, gwp_statistic):
    # keys is a list storing material type, e.g., ["brick", "precast concrete", "insulation", "gypsum board"]
    # epd_list_by_material is the json repsonse of EPDs belonging to certain material type, this is generated using 'fetch_epd_data' function 
    # epd_type = "product" or "industrial"
    gwp_data = {}
    # map use for retrieving gwp per functional unit from parsed_data, which is generated using 'parse_product_epd' and 'parse_industrial_epd' functions
    mapping = {
        "gwp_per_m2": "gwp_per_m2 (kg CO2 eq/m2)",
        "gwp_per_kg": "gwp_per_kg (kg CO2 eq/kg)",
        "gwp_per_m3": "gwp_per_m3 (kg CO2 eq/m3)"
    }
    for key, epds in zip(keys, epd_list_by_material):
        # print(key)
        gwp_data[key] = {
            "gwp_per_m2": 0.0,
            "gwp_per_kg": 0.0,
            "gwp_per_m3": 0.0
        }
        gwp_values = {
            "gwp_per_m2": [],
            "gwp_per_kg": [],
            "gwp_per_m3": []
        }

        for epd in epds:
            if epd_type == "Industrial":
                parsed_data = parse_industrial_epd(epd)
            elif epd_type == "Product":
                parsed_data = parse_product_epd(epd)
            else:
                print(f"Unknown epd_type '{epd_type}' for {key}")
                continue

            for unit_key, json_key in mapping.items():
                value = extract_numeric_value(parsed_data.get(json_key))
                if value is not None:
                    gwp_values[unit_key].append(float(value))
        for unit_key, values_list in gwp_values.items():
            if len(values_list) == 0:
                print(f"No GWP values for {unit_key} in {key} using {epd_type}")
            elif len(values_list) == 1:
                gwp_data[key][unit_key] = values_list[0]
            elif gwp_statistic == "minimum":
                gwp_data[key][unit_key] = float(np.min(values_list))
            elif gwp_statistic == "maximum":
                gwp_data[key][unit_key] = float(np.max(values_list))
            elif gwp_statistic == "mean":
                gwp_data[key][unit_key] = float(np.mean(values_list))
            elif gwp_statistic == "median":
                gwp_data[key][unit_key] = float(np.median(values_list))
            else:
                print(f"Unsupported gwp_statistic: {gwp_statistic}")
    
    return gwp_data
# used for industrial epds, get average values for density, thickness and etc
def compute_average(min,max):
    if min is not None and max is not None:
        avg = (extract_numeric_value(max) + extract_numeric_value(min)) / 2
    elif min is not None:
        avg = extract_numeric_value(min)
    elif max is not None:
        avg = extract_numeric_value(max)
    else:
        avg = None

    return avg

def main():
    """
    Main function to execute the script.
    """
    print("Fetching EC3 EPD data...")

    print("Search EPD based on names:")
    search_url=generate_url_byname(name_like= "cellulose", category="bf1c8882d7784db4b10d9d5698b8b5cc")
    epd_data = fetch_epd_data(search_url, API_TOKEN)
    
    for idx, epd in enumerate(epd_data, start=1):
                parsed_data = parse_product_epd(epd)
                print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")
    print(f"Number of  product EPDs: {len(epd_data)}")

    # print("Search EPD based on Masterformat divisons:")
    # for category, list in material_category.items():
    #     # print(material_category[category])
    #     for name in list:
    #         # print(name)
    #         product_url = generate_url(name, endpoint="materials", epd_type="Product",insulation_application='Exterior%20Wall')
    #         industry_url = generate_url(name, endpoint="industry_epds", epd_type="Industry")

    #         product_epd_data = fetch_epd_data(product_url,API_TOKEN) 
    #         industrial_epd_data = fetch_epd_data(industry_url,API_TOKEN)
    #         # print(f"Number of  product EPDs for {name}: {len(product_epd_data)}")
    #         # print(f"Number of  industrial EPDs for {name}: {len(industrial_epd_data)}")
    #         for idx, epd in enumerate(product_epd_data, start=1):
    #             parsed_data = parse_product_epd(epd)
    #             # print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")
    #         for idx, epd in enumerate(industrial_epd_data, start=1):
    #             parsed_data = parse_industrial_epd(epd)
    #             # print(f"Industrial EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

if __name__ == "__main__":
    main()










# import requests
# import json
# import re
# from typing import Dict, Any, List
# from pathlib import Path
# import configparser
# from datetime import datetime
# import os
# import numpy as np
# import logging

# # ---------------- CONFIGURATION ----------------

# def load_api_token(config_path: str) -> str:
#     if not os.path.exists(config_path):
#         raise FileNotFoundError(f"Config file not found: {config_path}")
#     config = configparser.ConfigParser()
#     config.read(config_path)
#     return config["EC3_API_TOKEN"]["API_TOKEN"]

# script_dir = os.path.dirname(os.path.abspath(__file__))
# repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
# config_path = os.path.join(repo_root, "config.ini")
# API_TOKEN = load_api_token(config_path)

# # ---------------- LOGGING ----------------

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # ---------------- MATERIAL SELECTION ----------------

# material_category = {
#     "test": ["Insulation"]
# }

# # ---------------- URL GENERATION ----------------

# def generate_url(material_name, endpoint="materials", page_number=1, page_size=3, jurisdiction="021",
#                  date=None, option=None, boolean="yes", glass_panes=None, epd_type="Product",
#                  insulation_application=None, insulation_material=None):
#     if date is None:
#         date = datetime.today().strftime("%Y-%m-%d")

#     url = (
#         f"https://api.buildingtransparency.org/api/{endpoint}"
#         f"?page_number={page_number}&page_size={page_size}"
#         f"&mf=!EC3%20search(%22{material_name}%22)%20WHERE%20"
#         f"%0A%20%20jurisdiction%3A%20IN(%22{jurisdiction}%22)%20AND%0A%20%20"
#         f"epd__date_validity_ends%3A%20%3E%20%22{date}%22%20AND%0A%20%20"
#         f"epd_types%3A%20IN(%22{epd_type}%20EPDs%22)%20"
#     )

#     conditions = []
#     if option and boolean:
#         conditions.append(f"{option}%3A%20{boolean}")
#     if glass_panes:
#         conditions.append(f"glass_panes%3A%20%3E~%20{glass_panes}")
#     if insulation_material:
#         conditions.append(f"insulating_material%3A%20IN(%22{insulation_material}%22)")
#     if insulation_application:
#         conditions.append(f"insulation_intended_application%3A%20IN(%22{insulation_application}%22)")

#     if conditions:
#         url += "AND%0A%20%20" + "%20AND%0A%20%20".join(conditions) + "%20%0A"

#     url += "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
#     return url

# # ---------------- FETCH & PARSE ----------------

# def fetch_epd_data(url: str, api_token: str):
#     try:
#         logger.info(f"Fetching data from: {url}")
#         headers = {"Accept": "application/json", "Authorization": "Bearer " + api_token}
#         response = requests.get(url, headers=headers, verify=False)
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Error fetching data: {e}")
#         return []

# def get_parsed_epds(url: str, token: str, epd_type: str) -> List[Dict[str, Any]]:
#     epds = fetch_epd_data(url, token)
#     parser = parse_product_epd if epd_type.lower() == "product" else parse_industrial_epd
#     return [parser(epd) for epd in epds]

# # ---------------- PARSERS ----------------

# def parse_product_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
#     declared_unit = epd.get("declared_unit")
#     thickness = epd.get("thickness")
#     gwp_per_declared_unit = epd.get("gwp")
#     mass_per_declared_unit = epd.get("mass_per_declared_unit")
#     density = epd.get("density")
#     gwp_per_kg = extract_numeric_value(epd.get("gwp_per_kg"))
#     epd_name = epd.get("name")
#     description = epd.get("description")
#     original_ec3_link = epd["manufacturer"]["original_ec3_link"]
#     category_mass = epd["category"]["mass_per_declared_unit"]
#     category_unit = epd["category"]["declared_unit"]

#     if mass_per_declared_unit is None and category_mass and "m2" in category_unit:
#         mass_per_declared_unit = divide(category_mass, category_unit)

#     if gwp_per_kg is None:
#         if "t" in declared_unit:
#             gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
#         elif "kg" in declared_unit:
#             gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
#         elif mass_per_declared_unit:
#             gwp_per_kg = divide(gwp_per_declared_unit, mass_per_declared_unit)

#     gwp_per_m3 = gwp_per_m2 = 0.0

#     if "m3" in declared_unit:
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
#     elif "cf" in declared_unit:
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147
#     elif "m2" in declared_unit and "mm" in str(thickness):
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) / (extract_numeric_value(thickness) / 1000)
#     elif density and gwp_per_kg:
#         gwp_per_m3 = multiply(gwp_per_kg, density)

#     if "m2" in declared_unit:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
#     elif "ft²" in declared_unit or "sf" in declared_unit:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639
#     elif "m3" in declared_unit and thickness:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness) / 1000)

#     return {
#         "epd_name": epd_name,
#         "declared_unit": declared_unit,
#         "gwp_per_declared_unit": gwp_per_declared_unit,
#         "mass_per_declared_unit": mass_per_declared_unit,
#         "thickness": thickness,
#         "density": density,
#         "gwp_per_m3 (kg CO2 eq/m3)": gwp_per_m3,
#         "gwp_per_m2 (kg CO2 eq/m2)": gwp_per_m2,
#         "gwp_per_kg (kg CO2 eq/kg)": gwp_per_kg,
#         "category_mass_per_declared_unit": category_mass,
#         "category_decalred_unit": category_unit,
#         "original_ec3_link": original_ec3_link,
#         "description": description
#     }

# def parse_industrial_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
#     declared_unit = epd.get("declared_unit")
#     gwp_per_declared_unit = epd.get("gwp")
#     gwp_per_kg = epd.get("gwp_per_kg")
#     density_min = epd.get("density_min")
#     density_max = epd.get("density_max")
#     thickness_min = epd.get("thickness_per_declared_unit_min")
#     thickness_max = epd.get("thickness_per_declared_unit_max")
#     density_avg = compute_average(density_min, density_max)
#     thickness_avg = compute_average(thickness_min, thickness_max)

#     if gwp_per_kg is None:
#         if "t" in declared_unit:
#             gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
#         elif "kg" in declared_unit:
#             gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)

#     gwp_per_m3 = gwp_per_m2 = 0.0

#     if "m3" in declared_unit:
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
#     elif "cf" in declared_unit:
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147
#     elif "m2" in declared_unit and "mm" in str(thickness_avg):
#         gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) / (extract_numeric_value(thickness_avg) / 1000)
#     elif density_avg and gwp_per_kg:
#         gwp_per_m3 = multiply(gwp_per_kg, density_avg)

#     if "m2" in declared_unit:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
#     elif "sf" in declared_unit:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639
#     elif "m3" in declared_unit and thickness_avg:
#         gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness_avg) / 1000)

#     return {
#         "epd_name": epd.get("name"),
#         "declared_unit": declared_unit,
#         "gwp_per_declared_unit": gwp_per_declared_unit,
#         "gwp_per_m3 (kg CO2 eq/m3)": gwp_per_m3,
#         "gwp_per_m2 (kg CO2 eq/m2)": gwp_per_m2,
#         "gwp_per_kg (kg CO2 eq/kg)": gwp_per_kg,
#         "original_ec3_link": epd.get("original_ec3_link"),
#         "description": epd.get("description")
#     }

# # ---------------- UTILITY FUNCTIONS ----------------

# def extract_numeric_value(value: Any) -> float:
#     match = re.search(r"[-+]?\d*\.?\d+", str(value))
#     return float(match.group()) if match else 0.0

# def divide(numerator: Any, denominator: Any) -> float:
#     return extract_numeric_value(numerator) / extract_numeric_value(denominator)

# def multiply(a: Any, b: Any) -> float:
#     return extract_numeric_value(a) * extract_numeric_value(b)

# def compute_average(min_val, max_val):
#     if min_val and max_val:
#         return (extract_numeric_value(min_val) + extract_numeric_value(max_val)) / 2
#     return extract_numeric_value(min_val or max_val)

# # ---------------- MAIN ----------------

# def main():
#     logger.info("Fetching EC3 EPD data...")

#     for category, materials in material_category.items():
#         for name in materials:
#             logger.info(f"Material: {name}")
#             product_url = generate_url(name, endpoint="materials", epd_type="Product", insulation_application="Exterior%20Wall")
#             industry_url = generate_url(name, endpoint="industry_epds", epd_type="Industry")

#             product_epds = get_parsed_epds(product_url, API_TOKEN, "Product")
#             industry_epds = get_parsed_epds(industry_url, API_TOKEN, "Industrial")

#             logger.info(f"Found {len(product_epds)} product EPDs, {len(industry_epds)} industrial EPDs")

#             for idx, epd in enumerate(product_epds, 1):
#                 logger.info(f"Product EPD #{idx}:\n{json.dumps(epd, indent=4)}")
#             for idx, epd in enumerate(industry_epds, 1):
#                 logger.info(f"Industrial EPD #{idx}:\n{json.dumps(epd, indent=4)}")

# if __name__ == "__main__":
#     main()


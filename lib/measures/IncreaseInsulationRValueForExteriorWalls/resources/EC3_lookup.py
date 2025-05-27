import requests
import json
import re
from typing import Dict, Any, List
from pathlib import Path
import configparser
from datetime import datetime
import os
import numpy as np
import logging

# ---------------- CONFIGURATION ----------------

def load_api_token(config_path: str) -> str:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    config = configparser.ConfigParser()
    config.read(config_path)
    return config["EC3_API_TOKEN"]["API_TOKEN"]

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")
API_TOKEN = load_api_token(config_path)

# ---------------- LOGGING ----------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- MATERIAL SELECTION ----------------

material_category = {
    "test": ["Insulation"]
}

# ---------------- URL GENERATION ----------------

def generate_url(material_name, endpoint="materials", page_number=1, page_size=3, jurisdiction="021",
                 date=None, option=None, boolean="yes", glass_panes=None, epd_type="Product",
                 insulation_application=None, insulation_material=None):
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")

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
    if insulation_material:
        conditions.append(f"insulating_material%3A%20IN(%22{insulation_material}%22)")
    if insulation_application:
        conditions.append(f"insulation_intended_application%3A%20IN(%22{insulation_application}%22)")

    if conditions:
        url += "AND%0A%20%20" + "%20AND%0A%20%20".join(conditions) + "%20%0A"

    url += "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
    return url

# ---------------- FETCH & PARSE ----------------

def fetch_epd_data(url: str, api_token: str):
    try:
        logger.info(f"Fetching data from: {url}")
        headers = {"Accept": "application/json", "Authorization": "Bearer " + api_token}
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data: {e}")
        return []

def get_parsed_epds(url: str, token: str, epd_type: str) -> List[Dict[str, Any]]:
    epds = fetch_epd_data(url, token)
    parser = parse_product_epd if epd_type.lower() == "product" else parse_industrial_epd
    return [parser(epd) for epd in epds]

# ---------------- PARSERS ----------------

def parse_product_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
    declared_unit = epd.get("declared_unit")
    thickness = epd.get("thickness")
    gwp_per_declared_unit = epd.get("gwp")
    mass_per_declared_unit = epd.get("mass_per_declared_unit")
    density = epd.get("density")
    gwp_per_kg = extract_numeric_value(epd.get("gwp_per_kg"))
    epd_name = epd.get("name")
    description = epd.get("description")
    original_ec3_link = epd["manufacturer"]["original_ec3_link"]
    category_mass = epd["category"]["mass_per_declared_unit"]
    category_unit = epd["category"]["declared_unit"]

    if mass_per_declared_unit is None and category_mass and "m2" in category_unit:
        mass_per_declared_unit = divide(category_mass, category_unit)

    if gwp_per_kg is None:
        if "t" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
        elif "kg" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)
        elif mass_per_declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, mass_per_declared_unit)

    gwp_per_m3 = gwp_per_m2 = 0.0

    if "m3" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
    elif "cf" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147
    elif "m2" in declared_unit and "mm" in str(thickness):
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) / (extract_numeric_value(thickness) / 1000)
    elif density and gwp_per_kg:
        gwp_per_m3 = multiply(gwp_per_kg, density)

    if "m2" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
    elif "ft²" in declared_unit or "sf" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639
    elif "m3" in declared_unit and thickness:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness) / 1000)

    return {
        "epd_name": epd_name,
        "declared_unit": declared_unit,
        "gwp_per_declared_unit": gwp_per_declared_unit,
        "mass_per_declared_unit": mass_per_declared_unit,
        "thickness": thickness,
        "density": density,
        "gwp_per_m3 (kg CO2 eq/m3)": gwp_per_m3,
        "gwp_per_m2 (kg CO2 eq/m2)": gwp_per_m2,
        "gwp_per_kg (kg CO2 eq/kg)": gwp_per_kg,
        "category_mass_per_declared_unit": category_mass,
        "category_decalred_unit": category_unit,
        "original_ec3_link": original_ec3_link,
        "description": description
    }

def parse_industrial_epd(epd: Dict[str, Any]) -> Dict[str, Any]:
    declared_unit = epd.get("declared_unit")
    gwp_per_declared_unit = epd.get("gwp")
    gwp_per_kg = epd.get("gwp_per_kg")
    density_min = epd.get("density_min")
    density_max = epd.get("density_max")
    thickness_min = epd.get("thickness_per_declared_unit_min")
    thickness_max = epd.get("thickness_per_declared_unit_max")
    density_avg = compute_average(density_min, density_max)
    thickness_avg = compute_average(thickness_min, thickness_max)

    if gwp_per_kg is None:
        if "t" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit) / 1000
        elif "kg" in declared_unit:
            gwp_per_kg = divide(gwp_per_declared_unit, declared_unit)

    gwp_per_m3 = gwp_per_m2 = 0.0

    if "m3" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit)
    elif "cf" in declared_unit:
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) * 35.3147
    elif "m2" in declared_unit and "mm" in str(thickness_avg):
        gwp_per_m3 = divide(gwp_per_declared_unit, declared_unit) / (extract_numeric_value(thickness_avg) / 1000)
    elif density_avg and gwp_per_kg:
        gwp_per_m3 = multiply(gwp_per_kg, density_avg)

    if "m2" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit)
    elif "sf" in declared_unit:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * 10.7639
    elif "m3" in declared_unit and thickness_avg:
        gwp_per_m2 = divide(gwp_per_declared_unit, declared_unit) * (extract_numeric_value(thickness_avg) / 1000)

    return {
        "epd_name": epd.get("name"),
        "declared_unit": declared_unit,
        "gwp_per_declared_unit": gwp_per_declared_unit,
        "gwp_per_m3 (kg CO2 eq/m3)": gwp_per_m3,
        "gwp_per_m2 (kg CO2 eq/m2)": gwp_per_m2,
        "gwp_per_kg (kg CO2 eq/kg)": gwp_per_kg,
        "original_ec3_link": epd.get("original_ec3_link"),
        "description": epd.get("description")
    }

# ---------------- UTILITY FUNCTIONS ----------------

def extract_numeric_value(value: Any) -> float:
    match = re.search(r"[-+]?\d*\.?\d+", str(value))
    return float(match.group()) if match else 0.0

def divide(numerator: Any, denominator: Any) -> float:
    return extract_numeric_value(numerator) / extract_numeric_value(denominator)

def multiply(a: Any, b: Any) -> float:
    return extract_numeric_value(a) * extract_numeric_value(b)

def compute_average(min_val, max_val):
    if min_val and max_val:
        return (extract_numeric_value(min_val) + extract_numeric_value(max_val)) / 2
    return extract_numeric_value(min_val or max_val)

# ---------------- MAIN ----------------

def main():
    logger.info("Fetching EC3 EPD data...")

    for category, materials in material_category.items():
        for name in materials:
            logger.info(f"Material: {name}")
            product_url = generate_url(name, endpoint="materials", epd_type="Product", insulation_application="Exterior%20Wall")
            industry_url = generate_url(name, endpoint="industry_epds", epd_type="Industry")

            product_epds = get_parsed_epds(product_url, API_TOKEN, "Product")
            industry_epds = get_parsed_epds(industry_url, API_TOKEN, "Industrial")

            logger.info(f"Found {len(product_epds)} product EPDs, {len(industry_epds)} industrial EPDs")

            for idx, epd in enumerate(product_epds, 1):
                logger.info(f"Product EPD #{idx}:\n{json.dumps(epd, indent=4)}")
            for idx, epd in enumerate(industry_epds, 1):
                logger.info(f"Industrial EPD #{idx}:\n{json.dumps(epd, indent=4)}")

if __name__ == "__main__":
    main()


# EC3 API Lookup Script
import requests
import json
import re
from typing import Dict, Any, List
from pathlib import Path
import configparser

config = configparser.ConfigParser()
config.read("config.ini")  # Ensure the correct path is provided if not in the same directory

# Load API token and URLs from the config file
API_TOKEN = config.get("EC3", "API_TOKEN")
IGU_URL = config.get("EC3", "IGU_URL")
WFRAME_URL = config.get("EC3", "WFRAME_URL")

# API configuration
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {API_TOKEN}"}

# Constants
EXCLUDE_KEYS = [
    'manufacturer', 'plant_or_group', 'category', 'created_on', 'updated_on',
    'gwp', 'gwp_z', 'pct80_gwp_per_category_declared_unit', 'conservative_estimate',
    'best_practice', 'standard_deviation', 'uncertainty_factor',
    'uncertainty_adjusted_gwp', 'lowest_plausible_gwp'
]

# API URLs
URLS = {
    "igu": IGU_URL,
    "wframe": WFRAME_URL
}

def fetch_epd_data(url: str) -> List[Dict[str, Any]]:
    """
    Fetch EPD data from the EC3 API.
    :param url: API endpoint URL
    :return: Parsed JSON response or empty list on failure
    """
    try:
        print(f"Fetching data from URL: {url}")  # Log the URL being fetched
        response = requests.get(url, headers=HEADERS, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}")
        print(f"Response content: {response.text if response else 'No response content'}")  # Print response content for debugging
        return []

def parse_gwp_data(epd: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse GWP data for a given EPD.
    :param epd: EPD dictionary
    :return: Parsed GWP data
    """
    parsed_data = {}
    gwp_per_unit_volume = "Not specified"
    gwp_per_unit_area = "Not specified"
    gwp_per_unit_mass = "Not specified"

    declared_unit = epd.get("declared_unit")
    thickness_unit = epd.get("thickness")
    gwp_per_category_declared_unit = epd.get("gwp_per_category_declared_unit")
    density_unit = epd.get("density")
    gwp_per_unit_mass = epd.get("gwp_per_kg")

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

    parsed_data["gwp_per_unit_volume"] = f"{gwp_per_unit_volume} kg CO2 e/m3"
    parsed_data["gwp_per_unit_area"] = f"{gwp_per_unit_area} kg CO2 e/m2"
    parsed_data["gwp_per_unit_mass"] = f"{gwp_per_unit_mass} kg CO2 e/kg" if gwp_per_unit_mass else "Not specified"
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
    for key, url in URLS.items():
        print(f"\nProcessing {key.upper()} data...")
        epd_data = fetch_epd_data(url)
        print(f"Number of EPDs for {key}: {len(epd_data)}")
        for idx, epd in enumerate(epd_data, start=1):
            parsed_data = parse_gwp_data(epd)
            print(f"EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

if __name__ == "__main__":
    main()

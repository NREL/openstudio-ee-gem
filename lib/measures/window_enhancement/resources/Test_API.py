# How to use this script:
# This script is for reading the unparsed json reponse from EC3, just change 'test_url' to get different json response; 
# change page size to '1' can read json repsonse of an individual EPD, which will be the first EPD in the search result
# Note: This script now also demonstrates extracting reference_service_life from EPD data

# Test EC3 API Call
import requests
import pprint
import os
import configparser
from EC3_lookup import parse_product_epd

# reading EC3 API token
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

#change the url below to get different json repsonse
test_url = ("https://api.buildingtransparency.org/api/materials?page_number=1&page_size=1&mf=!EC3%20search(%22Insulation%22)%20WHERE%20%0A%20%20jurisdiction%3A%20IN(%22019%22)%20AND%0A%20%20epd__date_validity_ends%3A%20%3E%20%222025-05-06%22%20AND%0A%20%20epd_types%3A%20IN(%22Product%20EPDs%22)%20AND%0A%20%20insulation_intended_application%3A%20IN(%22Exterior%20Wall%22)%20%0A!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)")
# Headers for the request
headers = {
    "Accept": "application/json",
    "Authorization": "Bearer "+ API_TOKEN
}

# Execute the GET request
test_response = requests.get(test_url, headers=headers, verify=False)

# read the JSON response using pprint package, easier to read
test_response = test_response.json()
pprint.pp(test_response)
#print(test_response)
# Print the number of EPDs
print(f"Number of EPDs: {len(test_response)}")

# Test lifetime extraction from EPD data
print("\n" + "="*80)
print("TESTING LIFETIME EXTRACTION FROM EPD DATA")
print("="*80)
if test_response and len(test_response) > 0:
    for idx, epd in enumerate(test_response, start=1):
        print(f"\nEPD {idx}:")
        parsed_data = parse_product_epd(epd)
        print(f"  EPD Name: {parsed_data.get('epd_name', 'N/A')}")
        print(f"  Reference Service Life: {parsed_data.get('reference_service_life', 'Not specified in EPD')}")
        print(f"  GWP per m2: {parsed_data.get('gwp_per_m2 (kg CO2 eq/m2)', 'N/A')}")
        print(f"  GWP per m3: {parsed_data.get('gwp_per_m3 (kg CO2 eq/m3)', 'N/A')}")
        print(f"  Declared Unit: {parsed_data.get('declared_unit', 'N/A')}")
else:
    print("No EPD data found in response")
print("="*80)
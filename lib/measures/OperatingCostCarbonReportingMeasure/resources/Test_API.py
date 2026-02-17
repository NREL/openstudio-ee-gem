# How to use this script:
# This script is for reading the unparsed json reponse from EC3, just change 'test_url' to get different json response; 
# change page size to '1' can read json repsonse of an individual EPD, which will be the first EPD in the search result

# Test EC3 API Call
import requests
import pprint
import os
import configparser

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
test_url = ("https://api.buildingtransparency.org/api/epds?page_number=1&page_size=250&sort_by=-updated_on&category=56f3c898f94b459eb18feadeb792ab88&name__like=batts+insulation+wool&plant_geography=021&declaration_type=Product+EPD")
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
# Test EC3 API Call
import requests
import pprint
import os
import configparser
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

test_url = ("https://api.buildingtransparency.org/api/epds?page_number=1&page_size=25&sort_by=-updated_on&category=bf1c8882d7784db4b10d9d5698b8b5cc&q=cellulose&plant_geography=021&declaration_type=Product%20EPD")
# Headers for the request
headers = {
    "Accept": "application/json",
    "Authorization": "Bearer "+ API_TOKEN
}

# Execute the GET request
test_response = requests.get(test_url, headers=headers, verify=False)

# Parse the JSON response
test_response = test_response.json()
pprint.pp(test_response)
# Print the response and the number of EPDs
print(f"Number of EPDs: {len(test_response)}")

# Show current working directory
print("Current working directory:", os.getcwd())

# Save JSON response to a txt file (pretty formatted, easy to read)
with open("response.txt", "w", encoding="utf-8") as f:
    json.dump(test_response, f, indent=4, ensure_ascii=False)
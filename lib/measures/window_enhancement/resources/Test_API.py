# Test EC3 API Call
import requests
import pprint
import os
import configparser

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

test_url = ("https://api.buildingtransparency.org/api/materials?page_number=1&page_size=25&mf=!EC3%20search(%22AluminiumExtrusions%22)%20WHERE%20%0A%20%20jurisdiction%3A%20IN(%22021%22)%20AND%0A%20%20epd__date_validity_ends%3A%20%3E%20%222025-04-08%22%20AND%0A%20%20epd_types%3A%20IN(%22Product%20EPDs%22)%20%0A!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)")
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
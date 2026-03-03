# Test EC3 API Call
import requests
import pprint
import os
import configparser
import json

import test

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

test_url = ("https://buildingtransparency.org/api/epds?page_number=1&page_size=25&fields=id%2Copen_xpd_uuid%2Cis_failed%2Cfailures%2Cerrors%2Cwarnings%2Cdate_validity_ends%2Ccqd_sync_unlocked%2Cmy_capabilities%2Coriginal_data_format%2Ccategory%2Cdisplay_name%2Cmanufacturer%2Cplant_or_group%2Cname%2Cdescription%2Cprogram_operator%2Cprogram_operator_fkey%2Cverifier%2Cdeveloper%2Cmatched_plants_count%2Cplant_geography%2Cpcr%2Cshort_name%2Cversion%2Cdate_of_issue%2Clanguage%2Cgwp%2Cuncertainty_adjusted_gwp%2Cdeclared_unit%2Cupdated_on%2Ccorrections_count%2Cdeclaration_type%2Cbox_id%2Cis_downloadable&sort_by=-updated_on&name__like=wood%20door%20leaf&declaration_type=Product%20EPD")
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

print(test_response[0].get('gwp'))
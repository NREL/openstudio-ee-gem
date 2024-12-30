# Test EC3 API Call
import requests
import json
import re
import pprint

test_url = (
    "https://api.buildingtransparency.org/api/materials"
    "?page_number=1&page_size=25"
    "&mf=!EC3%20search(%22StructuralPrecast%22)%20WHERE%20"
    "%0A%20%20jurisdiction%3A%20IN(%22US%22%2C%20%22CA%22)%20AND%0A%20%20"
    "epd__date_validity_ends%3A%20%3E%20%222024-12-30%22%20AND%0A%20%20"
    "epd_types%3A%20IN(%22Product%20EPDs%22)%20"
    "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
)

# Headers for the request
headers = {
    "Accept": "application/json",
    "Authorization": "Bearer z7z4qVkNNmKeXtBM41C2DTSj0Sta7h"
}

# Execute the GET request
test_response = requests.get(test_url, headers=headers, verify=False)

# Parse the JSON response
test_response = test_response.json()
pprint.pp(test_response)
# Print the response and the number of EPDs
print(f"Number of EPDs: {len(test_response)}")
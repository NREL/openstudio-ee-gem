# Test EC3 API Call
import requests
import json
import re
import pprint
'''
EC3_category_array = {
    "ConstructionMaterials": {
        "Concrete": [
            "ReadyMix",
            "Shotcrete",
            "CementGrout",
            "FlowableFill",
            "Precast",
            "Rebar",
            "WireMeshSteel",
            "SCM",
            "Cement",
            "Aggregates"
        ],
        "Masonry": [
            "Brick",
            "ConcreteUnitMasonry",
            "Mortar",
            "Cementitious",
            "Aggregates"
        ],
        "Steel": [],
        "Aluminum": [],
        "Wood": [],
        "Sheathing": [],
        "ThermalMoistureProtection": [], 
        "Cladding": [],
        "Openings": [], 
        "Finishes": [],
        "ConveyingEquipment": [],
        "NetworkInfrastrucure": [], 
        "Asphalt": [],
        "Accessories": [], 
        "ManufacturingInputs": [],
        "BulkMaterials": [],
        "Placeholders": []
    },
    "BuildingAssemblies": {
        "NewCoustomAssembly": [],
        "ReinforcedConcrete": [], 
        "Walls": [],
        "Floors": [], 
        "GlazingFenesration": [], 
    },
}
'''

test_url = ("https://api.buildingtransparency.org/api/industry_epds?page_number=1&page_size=250&mf=!EC3%20search(%22WallPanels%22)%20WHERE%20%0A%20%20jurisdiction%3A%20IN(%22021%22)%20AND%0A%20%20epd__date_validity_ends%3A%20%3E%20%222025-03-20%22%20AND%0A%20%20epd_types%3A%20IN(%22Indsutry%20EPDs%22)%20!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)")

# Headers for the request
headers = {
    "Accept": "application/json",
    "Authorization": "Bearer 5fk7wP4cJg6pcmx6ncZN0ftMdoVR8u"
}

# Execute the GET request
test_response = requests.get(test_url, headers=headers, verify=False)

# Parse the JSON response
test_response = test_response.json()
pprint.pp(test_response)
# Print the response and the number of EPDs
print(f"Number of EPDs: {len(test_response)}")
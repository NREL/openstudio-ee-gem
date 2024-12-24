# EC3 API Call
import requests
import json
import re
import pprint

print("EC3 API Call:")

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

# Define the URL with query parameters (FIXME: Not including API key in public repo. Will need to be included in a gitignored config.ini file)
windows_url = (
    "https://api.buildingtransparency.org/api/epds"
    "?page_number=1&page_size=25&fields=id%2Copen_xpd_uuid%2Cis_failed%2Cfailures%2Cerrors%2Cwarnings"
    "%2Cdate_validity_ends%2Ccqd_sync_unlocked%2Cmy_capabilities%2Coriginal_data_format%2Ccategory"
    "%2Cdisplay_name%2Cmanufacturer%2Cplant_or_group%2Cname%2Cdescription%2Cprogram_operator"
    "%2Cprogram_operator_fkey%2Cverifier%2Cdeveloper%2Cmatched_plants_count%2Cplant_geography%2Cpcr"
    "%2Cshort_name%2Cversion%2Cdate_of_issue%2Clanguage%2Cgwp%2Cuncertainty_adjusted_gwp%2Cdeclared_unit"
    "%2Cupdated_on%2Ccorrections_count%2Cdeclaration_type%2Cbox_id%2Cis_downloadable"
    "&sort_by=-updated_on&name__like=window&description__like=window&q=windows&plant_geography=US&declaration_type=Product%20EPD"
)

igu_url =  (
    "https://api.buildingtransparency.org/api/materials"
    "?page_number=1&page_size=100"
    "&mf=!EC3%20search(%22InsulatingGlazingUnits%22)%20WHERE%20"
    "%0A%20%20jurisdiction%3A%20IN(%22021%22)%20AND%0A%20%20"
    "epd__date_validity_ends%3A%20%3E%20%222024-12-05%22%20AND%0A%20%20"
    "epd_types%3A%20IN(%22Product%20EPDs%22)%20"
    "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
)

wframe_url = (
    "https://api.buildingtransparency.org/api/materials"
    "?page_number=1&page_size=25"
    "&mf=!EC3%20search(%22AluminiumExtrusions%22)%20WHERE%20"
    "%0A%20%20jurisdiction%3A%20IN(%22021%22)%20AND%0A%20%20"
    "epd__date_validity_ends%3A%20%3E%20%222024-12-09%22%20AND%0A%20%20"
    "epd_types%3A%20IN(%22Product%20EPDs%22)%20"
    "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
)


# Headers for the request
headers = {
    "Accept": "application/json",
    "Authorization": "Bearer z7z4qVkNNmKeXtBM41C2DTSj0Sta7h"
}

# Execute the GET request
igu_response = requests.get(igu_url, headers=headers, verify=False)
wframe_response = requests.get(wframe_url, headers=headers, verify=False)

# Parse the JSON response
igu_response = igu_response.json()
wframe_response = wframe_response.json()
print(igu_response)
# Print the response and the number of EPDs
print(f"Number of EPDs for IGU: {len(igu_response)}")
print(f"Number of EPDs for window frame: {len(wframe_response)}")

# List of keys to exclude
exclude_keys = [
    'manufacturer', 
    'plant_or_group', 
    'category',
    'created_on',
    'updated_on',
    'gwp',
    'gwp_z',
    'pct80_gwp_per_category_declared_unit',
    'conservative_estimate',
    'best_practice',
    'standard_deviation',
    'uncertainty_factor',
    'uncertainty_adjusted_gwp',
    'lowest_plausible_gwp',
    ]

# Create an empty list to store EPDs of IGU
igu_epd_data = {}
wframe_epd_data = {}

for igu_epd_no, igu_epd in enumerate(igu_response, start=1):
    print(f"========================================EPD No. {igu_epd_no}:==========================================")
    # Initialize gwp per unit volume of IGU  
    gwp_per_unit_volume = "Not specified"
    gwp_per_unit_area = "Not specified"
    gwp_per_unit_mass = "Not specified"
    # Create an empty list to store each key,value pair in an individual EPD object 
    igu_object = {}

    for key, value in igu_epd.items():
        if value is not None and key not in exclude_keys:
            # Append the key-value pair to the list
            igu_object[key] = value
            # Extract the relevant keys
            declared_unit = igu_epd.get("declared_unit")
            thickness_unit = igu_epd.get("thickness")
            gwp_per_category_declared_unit = igu_epd.get("gwp_per_category_declared_unit")
            warnings = igu_epd.get("warnings")
            mass_per_declared_unit = igu_epd.get("mass_per_declared_unit")
            density_unit = igu_epd.get("density")
            gwp_per_unit_mass = igu_epd.get("gwp_per_kg")

            # Calculations
            if declared_unit and "m3" in declared_unit:
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                gwp_per_unit_volume = gwp_per_category_declared_unit_value

            elif declared_unit and "m2" in declared_unit and thickness_unit and "mm" in str(thickness_unit):
                thickness = float(re.search(r"[-+]?\d*\.?\d+", thickness_unit).group())  # Extract numeric part
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                thickness = thickness * 1e-3 # Convert thickness to meters
                gwp_per_unit_volume = round(gwp_per_category_declared_unit_value / thickness,2)
                gwp_per_unit_area = gwp_per_category_declared_unit_value

            elif declared_unit and "kg" in declared_unit and density_unit:
                density = float(re.search(r"[-+]?\d*\.?\d+", density_unit).group())  # Extract numeric part
                gwp_per_unit_volume = gwp_per_category_declared_unit_value * density
                gwp_per_unit_volume = round(gwp_per_unit_volume,2)
            
            elif declared_unit and "t" in declared_unit and density_unit:
                density = float(re.search(r"[-+]?\d*\.?\d+", density_unit).group())  # Extract numeric part
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                gwp_per_unit_volume = (gwp_per_category_declared_unit_value / 1000) * density
                gwp_per_unit_volume = round(gwp_per_unit_volume,2)
                

    igu_object["gwp_per_unit_volume"] = f"{gwp_per_unit_volume} kg CO2e/m3"
    igu_object["gwp_per_unit_area"] = f"{gwp_per_unit_area} kg CO2e/m2"
    if gwp_per_unit_mass == None:
        igu_object["gwp_per_unit_mass"] = "Not avaialble in this EPD"
    else:
        igu_object["gwp_per_unit_mass"] = f"{gwp_per_unit_mass}/kg"
    object_key = "object" + str(igu_epd_no)
    igu_epd_data[object_key] = igu_object
    pprint.pp(igu_object)

for wframe_epd_no, wframe_epd in enumerate(wframe_response, start=1):
    print(f"========================================EPD No. {wframe_epd_no}:==========================================")
    # Initialize gwp per unit volume of window frame 
    gwp_per_unit_volume = "Not specified"
    gwp_per_unit_area = "Not specified"
    gwp_per_unit_mass = "Not specified"
    # Create an empty list to store each key,value pair in an individual EPD object 
    wframe_object = {}

    for key, value in wframe_epd.items():
        if value is not None and key not in exclude_keys:
            # Append the key-value pair to the list
            wframe_object[key] = value
            # Extract the relevant keys
            declared_unit = wframe_epd.get("declared_unit")
            thickness_unit = wframe_epd.get("thickness")
            gwp_per_category_declared_unit = wframe_epd.get("gwp_per_category_declared_unit")
            warnings = wframe_epd.get("warnings")
            mass_per_declared_unit = wframe_epd.get("mass_per_declared_unit")
            density_unit = wframe_epd.get("density")
            gwp_per_unit_mass = wframe_epd.get("gwp_per_kg")

            # Calculations
            if declared_unit and "m3" in declared_unit:
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                gwp_per_unit_volume = gwp_per_category_declared_unit_value

            elif declared_unit and "m2" in declared_unit and thickness_unit and "mm" in str(thickness_unit):
                thickness = float(re.search(r"[-+]?\d*\.?\d+", thickness_unit).group())  # Extract numeric part
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                thickness = thickness * 1e-3 # Convert thickness to meters
                gwp_per_unit_volume = round(gwp_per_category_declared_unit_value / thickness,2)
                gwp_per_unit_area = gwp_per_category_declared_unit_value

            elif declared_unit and "kg" in declared_unit and density_unit:
                density = float(re.search(r"[-+]?\d*\.?\d+", density_unit).group())  # Extract numeric part
                gwp_per_unit_volume = gwp_per_category_declared_unit_value * density
                gwp_per_unit_volume = round(gwp_per_unit_volume,2)
            
            elif declared_unit and "t" in declared_unit and density_unit:
                density = float(re.search(r"[-+]?\d*\.?\d+", density_unit).group())  # Extract numeric part
                gwp_per_category_declared_unit_value = float(re.search(r"[-+]?\d*\.?\d+", str(gwp_per_category_declared_unit)).group())
                gwp_per_unit_volume = (gwp_per_category_declared_unit_value / 1000) * density
                gwp_per_unit_volume = round(gwp_per_unit_volume,2)

    wframe_object["gwp_per_unit_volume"] = f"{gwp_per_unit_volume} kg CO2 e/m3"
    wframe_object["gwp_per_unit_area"] = f"{gwp_per_unit_area} kg CO2 e/m2"
    if gwp_per_unit_mass == None:
        wframe_object["gwp_per_unit_mass"] = "Not avaialble in this EPD"
    else:
        wframe_object["gwp_per_unit_mass"] = f"{gwp_per_unit_mass}/kg"
    object_key = "object" + str(wframe_epd_no)
    wframe_epd_data[object_key] = wframe_object
    #print(wframe_object)
    #pprint.pp(wframe_object)
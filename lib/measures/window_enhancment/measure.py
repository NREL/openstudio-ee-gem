"""insert your copyright here.

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/reference/measure_writing_guide/
"""

import typing

import openstudio

################################################################EC3 API Call#############################################################################
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
        "Steel":[],  
        "Aluminum":[],  
        "Wood":[],
        "Sheathing":[], 
        "ThermalMoistureProtection":[],  
        "Cladding":[],  
        "Openings":[],  
        "Finishes":[], 
        "ConveyingEquipment":[], 
        "NetworkInfrastrucure":[],  
        "Asphalt":[],  
        "Accessories":[],  
        "ManufacturingInputs":[], 
        "BulkMaterials":[],  
        "Placeholders":[]
    },
    "BuildingAssemblies": {
        "NewCoustomAssembly":[], 
        "ReinforcedConcrete":[],  
        "Walls":[],  
        "Floors":[],  
        "GlazingFenesration":[],  
    },
}

# Define the URL with query parameters
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

igu_url = (
    "https://api.buildingtransparency.org/api/materials"
    "?page_number=1&page_size=100"
    "&mf=!EC3%20search(%22InsulatingGlazingUnits%22)%20WHERE%20"
    "%0A%20%20jurisdiction%3A%20IN(%22021%22%2C%20%22NAFTA%22)%20AND%0A%20%20"
    "epd__date_validity_ends%3A%20%3E%20%222024-12-11%22%20AND%0A%20%20"
    "epd_types%3A%20IN(%22Product%20EPDs%22)%20"
    "!pragma%20eMF(%222.0%2F1%22)%2C%20lcia(%22TRACI%202.1%22)"
)

wframe_url = (
    "https://api.buildingtransparency.org/api/materials"
    "?page_number=1&page_size=100"
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
    pprint.pp(wframe_object)

class WindowEnhancment(openstudio.measure.ModelMeasure):
    """A ModelMeasure."""

    def name(self):
        """Returns the human readable name.

        Measure name should be the title case of the class name.
        The measure name is the first contact a user has with the measure;
        it is also shared throughout the measure workflow, visible in the OpenStudio Application,
        PAT, Server Management Consoles, and in output reports.
        As such, measure names should clearly describe the measure's function,
        while remaining general in nature
        """
        return "Window Enhancment"

    def description(self):
        """Human readable description.

        The measure description is intended for a general audience and should not assume
        that the reader is familiar with the design and construction practices suggested by the measure.
        """
        return "Make existing window better by adding film, storm window, or something else."

    def modeler_description(self):
        """Human readable description of modeling approach.

        The modeler description is intended for the energy modeler using the measure.
        It should explain the measure's intent, and include any requirements about
        how the baseline model must be set up, major assumptions made by the measure,
        and relevant citations or references to applicable modeling resources
        """
        return "I'm going to use layred construction and not simple glazing to do this. We have to think about how to address simple glazing with this."

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Prepares user arguments for the measure.

        Measure arguments define which -- if any -- input parameters the user may set before running the measure.
        """
        # define the arguments that the user will input
    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Prepares user arguments for the measure.

        Measure arguments define which -- if any -- input parameters the user may set before running the measure.
        """
        args = openstudio.measure.OSArgumentVector()

        # make a choice argument for constructions that are appropriate for windows
        construction_handles = openstudio.StringVector()
        construction_display_names = openstudio.StringVector()

        # putting space types and names into hash
        construction_args = model.getConstructions(model)
        construction_args_hash = {}
        for construction_arg in construction_args:
            construction_args_hash[str(construction_arg.name)] = construction_arg
            print(construction_arg)

        # looping through sorted hash of constructions
        construction_args_hash = dict(sorted(construction_args_hash.items()))
        construction_handles = []
        construction_display_names = []
        for key, value in construction_args_hash.items():
            # only include if construction is a valid fenestration construction
            if value.isFenestration():
                construction_handles.append(str(value.handle))
                construction_display_names.append(key)
        print(construction_handles)
        print(construction_display_names)

        # make a choice argument for fixed windows
        construction = openstudio.measure.OSArgument.makeChoiceArgument("construction", construction_handles, construction_display_names, True)
        construction.setDisplayName("Pick a Window Construction From the Model to Replace Existing Window Constructions.")
        args.append(construction)

        # clone construction to get proper area for measure economics, in case it is used elsewhere in the building
        new_object = construction.clone(model)
        if not new_object.to_Construction().is_empty():
            construction = new_object.to_Construction.get()

        #make a bool argument for fixed windows
        change_fixed_windows = openstudio.measure.OSArgument.makeBoolArgument("change_fixed_windows", True)
        change_fixed_windows.setDisplayName("Change Fixed Windows?")
        change_fixed_windows.setDefaultValue(True)
        args.append(change_fixed_windows)

        #make a bool argument for operable windows
        change_operable_windows = openstudio.measure.OSArgument.makeBoolArgument("change_operable_windows", True)
        change_operable_windows.setDisplayName("Change Operable Windows?")
        change_operable_windows.setDefaultValue(True)
        args.append(change_operable_windows)

        # make an argument carbon intensity of IGU
        ci_igu = openstudio.measure.OSArgument.makeDoubleArgument("ci_igu", True)
        ci_igu.setDisplayName("GWP of IGU in kg CO2 eq per m3")
        ci_igu.setDefaultValue(0.0)
        args.append(ci_igu)

        # make an argument carbon intensity of window frame
        ci_wframe = openstudio.measure.OSArgument.makeDoubleArgument("ci_wframe", True)
        ci_wframe.setDisplayName("GWP of window frame in kg CO2 eq per m3")
        ci_wframe.setDefaultValue(0.0)
        args.append(ci_wframe)

        # make an argument volume of IGU
        vol_igu = openstudio.measure.OSArgument.makeDoubleArgument("vol_igu", True)
        vol_igu.setDisplayName("Volume of IGU in m3")
        vol_igu.setDefaultValue(0.0)
        args.append(vol_igu)

        # make an argument volume of window frame
        vol_wframe = openstudio.measure.OSArgument.makeDoubleArgument("vol_wframe", True)
        vol_wframe.setDisplayName("Volume of window frame in m3")
        vol_wframe.setDefaultValue(0.0)
        args.append(vol_wframe)
        
        return args

    def run(
        self,
        model: openstudio.model.Model,
        runner: openstudio.measure.OSRunner,
        user_arguments: openstudio.measure.OSArgumentMap,
    ):
        """Defines what happens when the measure is run."""
        super().run(model, runner, user_arguments)  # Do **NOT** remove this line

        if not (runner.validateUserArguments(self.arguments(model), user_arguments)):
            return False

        # assign the user inputs to variables
        ci_igu = runner.getDoubleArgumentValue("ci_igu", user_arguments)
        ci_wframe = runner.getDoubleArgumentValue("ci_wframe", user_arguments)
        vol_igu = runner.getDoubleArgumentValue("vol_igu", user_arguments)
        vol_wframe = runner.getDoubleArgumentValue("vol_wframe", user_arguments)

        # check the ci_igu for reasonableness
        if ci_igu < 0:
            runner.registerError("GWP of IGU can not be zero.")
            return False
        
        # check the ci_wframe for reasonableness
        if ci_wframe < 0:
            runner.registerError("GWP of window frame can not be zero.")
            return False
        
        # check the vol_igu for reasonableness
        if vol_igu < 0:
            runner.registerError("Volume of IGU can not be zero.")
            return False
        
        # check the vol_wframe for reasonableness
        if vol_wframe < 0:
            runner.registerError("Volume of window frame can not be zero.")
            return False
        
        # report initial condition of model
        runner.registerInitialCondition(f"The building started with {len(model.getSpaces())} spaces.")

        # add a new space to the model
        new_space = openstudio.model.Space(model)
        new_space.setName("space_name")

        #https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_glazing.html
        igu_pane_1 = openstudio.model.StandardGlazing(model)
        igu_pane_2 = openstudio.model.Glazing(model)
        openstudio.model.AirGap/WindowMaterial.GasField
        igu.setName("IGU")

        #https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_shade.html
        shade = openstudio.model.ShadingMaterial(model)
        shade_thickness = shade.getThickness()

        #https://openstudio-sdk-documentation.s3.amazonaws.com/cpp/OpenStudio-1.7.0-doc/model/html/classopenstudio_1_1model_1_1_window_property_frame_and_divider.html
        wframe = openstudio.model.WindowPropertyFrameAndDivider(model)
        wframe.setFrameWidth(thickness)
        wframe_thickness = wframe.frameWidth()

        # ip construction area for reporting
        '''
        const_area_ip = openstudio.convert(openstudio.Quantity(construction.getNetArea, openstudio.createUnit('m^2').get), openstudio.createUnit('ft^2').get).get.value
        net_area_ft2 = net_area_m2 * 10.7639  # 1 m2 ≈ 10.7639 inch2
        const_area_ip = net_area_ft2
        '''

        # echo the new space's name back to the user
        runner.registerInfo(f"Space {new_space.nameString()} was added.")

        # report final condition of model
        runner.registerFinalCondition(f"The building finished with {len(model.getSpaces())} spaces.")

        return True


# register the measure to be used by the application
WindowEnhancment().registerWithApplication()

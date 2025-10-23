# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

from atexit import register
from re import sub
import openstudio
import typing
import numpy as np
import pprint as pp
from resources.EC3_lookup import extract_numeric_value, fetch_epd_data, parse_product_epd,generate_url_byname,calculate_geometry,lifetime_multiplier

# Start the measure
class DoorEnhancement(openstudio.measure.ModelMeasure):

    """A ModelMeasure for door enhancement, installing brush weatherstrip
      or automatic door bottom
        or silicone adhesive smoke gasket (Silicon Adhesive Smoke and Fire Gaskets are adhesive-backed, silicone gasketing products installed on the perimeter of a door opening or at the meeting edges of a pair of doors to slow/prohibit the passage of smoke, fire, weather, sound, and dirt.)
        to the door and calculate embodied carbon."""

    def name(self):
        """Measure name."""
        return "Door Enhancement"

    def description(self):
        """Brief description of the measure."""
        return "Calculates embodied emissions for door enhancements using EC3 database lookup. This measure only functions if you have an EC3 key and the required Python libraries installed. In addition to getting embodied car value it does also alter the thermal performance of the doors based on the selections made"

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure evaluates the embodied carbon impact of adding an strip or storm door "
                "to an existing structure by analyzing frame material data from EC3.")
    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]
        
    @staticmethod
    def strip_options():
        return ["none","brush weatherstrip","automatic door bottom","silicone adhesive smoke gasket"]
    
    @staticmethod
    def door_options():
        return ['none','wooden door','garage door','glass door','polystyrene core steel door', 'polyurethane core steel door','fiberglass core steel door','honeycomb core steel door','stiffened core steel door','defined by model']

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define the arguments that user will input."""
        args = openstudio.measure.OSArgumentVector()

        #As per the guiding Product Category Rule (PCR), the declared unit is defined as 21 sq.ft. (1.95m2) of door leaf at a nominal 44.45 mm (1-3/4 in.) thickness.
        door_area_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("door_area_per_unit", True)
        door_area_per_unit.setDisplayName("Door Area per Unit")
        door_area_per_unit.setDescription("Area per unit of door leaf in m2")
        door_area_per_unit.setDefaultValue(1.95)
        args.append(door_area_per_unit)

        #make an argument for analysis period
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        #make an argument for strip options for filtering EPDs of strip
        strip_options_chs = openstudio.StringVector()
        for option in self.strip_options():
            strip_options_chs.append(option)
        strip_option = openstudio.measure.OSArgument.makeChoiceArgument("strip_option", strip_options_chs, True)
        strip_option.setDisplayName("strip option") 
        strip_option.setDescription("Select none if no strip is to be installed, otherwise select the type of strip to be installed.")
        strip_option.setDefaultValue("brush weatherstrip")
        args.append(strip_option)

        # make an argument for door options for filtering EPDs of door
        door_options_chs = openstudio.StringVector()
        for option in self.door_options():
            door_options_chs.append(option)
        door_option = openstudio.measure.OSArgument.makeChoiceArgument("door_option", door_options_chs, True)
        door_option.setDisplayName("door option")   
        door_option.setDescription("Select none if no door is to be installed, otherwise select the type of door to be installed. Select 'defined by model' to use the existing door construction types in the model.")
        door_option.setDefaultValue("wooden door")
        args.append(door_option)

        # make an argument for product life time of strip
        strip_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("strip_lifetime",True)
        strip_lifetime.setDisplayName("Product Lifetime of strip")
        strip_lifetime.setDescription("Life expectancy of door bottom strip")
        strip_lifetime.setDefaultValue(15)
        args.append(strip_lifetime)

        # make an argument for product life time of door
        door_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("door_lifetime",True)
        door_lifetime.setDisplayName("Product Lifetime of door")
        door_lifetime.setDescription("Life expectancy of door")
        door_lifetime.setDefaultValue(30)
        args.append(door_lifetime)

        # make an argument for selecting which gwp statistic to use for embodied carbon calculation
        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        args.append(gwp_statistic)

        # make an argument for api_token
        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

        # make an argument for mass per length of strip
        # 36''= 0.9144 m for weatherstrip brush, source: https://www.pemko.com/en/view-pdf?id=AADSS1046707&page=1
        # 17' = 5.1816 m for silicone adhesive smoke gasket, source: https://buildingtransparency.org/ec3/epds/ec327rq0
        # 36'' = 0.9144 m for automatic door bottom, source: https://www.adair.com/p-1537-automatic-door-bottom.aspx
        length_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit", True)
        length_per_unit.setDisplayName("Length per Unit of Strip")
        length_per_unit.setDescription("Length per unit of door bottom strip in m")
        length_per_unit.setDefaultValue(0.9144)
        args.append(length_per_unit)

        return args

    def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
        """Define what happens when the measure is run. Execute the measure."""
        runner.registerInfo("Starting doorEnhancement measure execution.")

        # Check if model exists
        if not model:
            runner.registerError("Model is None. Exiting measure.")
            return False
        # built-in error checking
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Retrieve user inputs
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        strip_option = runner.getStringArgumentValue("strip_option", user_arguments)
        door_option = runner.getStringArgumentValue("door_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        strip_lifetime = runner.getIntegerArgumentValue("strip_lifetime",user_arguments)
        door_lifetime = runner.getIntegerArgumentValue("door_lifetime",user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        length_per_unit = runner.getDoubleArgumentValue("length_per_unit", user_arguments)
        door_area_per_unit = runner.getDoubleArgumentValue("door_area_per_unit", user_arguments)

        # Debug: Print all user arguments received
        runner.registerInfo(f"User Arguments: {user_arguments}")
        for arg_name, arg_value in user_arguments.items():
            try:
                # Ensure that arg_value is valid and that the valueAsString() method can be called
                value_str = arg_value.valueAsString() if arg_value is not None else "None"
                runner.registerInfo(f"user_argument: {arg_name} = {value_str}")
            except Exception as e:
                runner.registerInfo(f"Error processing argument: {arg_name} - {str(e)}")
        
        # Check if numeric values are reasonable
        if analysis_period <= 0:
            runner.registerError("Choose an integer larger than 0 for analysis period of embodied carbon calculation.")
        if strip_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door bottom strip.")
        if door_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door.")

        # Print the number of sub-surfaces before processing
        sub_surfaces = model.getSubSurfaces()
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")
        # List storing subsurface object subject to change
        sub_surfaces_to_change = []
        # loop through sub surfaces
        for subsurface in sub_surfaces:

            if subsurface.subSurfaceType() in ["Door","GlassDoor","OverheadDoor"]:
                # append the subsurface objects carrying doors into list
                sub_surfaces_to_change.append(subsurface) 
                runner.registerInfo(f"Processing door construction in {subsurface.nameString()}")           
            else:# if sub_surface.subSurfaceType() not in ["Fixeddoor", "Operabledoor"]:
                runner.registerInfo(f"Skipping non-door surface: {subsurface.nameString()}")
                continue

        # dictionary storing properties of subsurfaces containing door construcitons
        subsurface_dict = {}
        
        # loop through layered door construciton to collect door materials
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            subsurface_dict[subsurface_name] = {}
            if subsurface.construction().is_initialized():
                subsurface_const = subsurface.construction().get()
            if subsurface_const.to_LayeredConstruction().is_initialized():
                layered_construction = subsurface_const.to_LayeredConstruction().get()

            subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"] = 0.0

            subsurface_dict[subsurface_name]["strip"] = {}
            subsurface_dict[subsurface_name]["subsurface object"] = subsurface
            subsurface_dict[subsurface_name]["strip"]["object"] = layered_construction
            subsurface_dict[subsurface_name]["strip"]["lifetime"] = strip_lifetime
            subsurface_dict[subsurface_name]["embodied_carbon"] = 0.0
            subsurface_dict[subsurface_name]["dimension"] = calculate_geometry(self, subsurface)

            subsurface_dict[subsurface_name]['door'] = {}
            subsurface_dict[subsurface_name]['subsurface object'] = subsurface
            subsurface_dict[subsurface_name]['door']['lifetime'] = door_lifetime
            subsurface_dict[subsurface_name]['embodied_carbon'] = 0.0
            subsurface_dict[subsurface_name]['dimension'] = calculate_geometry(self, subsurface)

            epd_datalist = {}

            strip_product_url = generate_url_byname(name_like = strip_option, category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d')
            strip_product_epd = fetch_epd_data(url = strip_product_url, api_token = api_key)
            epd_datalist["strip"] = strip_product_epd

            door_product_url = None
            if door_option == 'defined by model':
                if subsurface_name == "Door":
                    door_product_url = generate_url_byname(name_like = 'wood door leaf')
                elif subsurface_name == "GlassDoor":
                    door_product_url = generate_url_byname(name_like = 'window door system', plant_geography = '150')
                elif subsurface_name == "OverheadDoor":
                    door_product_url = generate_url_byname(name_like = 'garage door', plant_geography = '150')
            elif door_option == 'wooden door':
                door_product_url = generate_url_byname(name_like = 'wood door leaf')
            elif door_option == 'glass door':
                door_product_url = generate_url_byname(name_like = 'window door system', plant_geography = '150')
            elif door_option == 'garage door':
                door_product_url = generate_url_byname(name_like = 'garage door', plant_geography = '150')
            elif door_option == 'fiberglass core steel door':
                door_product_url = generate_url_byname(name_like = 'fiberglass core', category = '73e602b930884f559e904184f35ee4ed')
            elif door_option == 'stiffened core steel door':
                door_product_url = generate_url_byname(name_like = 'stiffened core', category = 'e9605505973e4f088078c6f53e58129f')
            elif door_option == 'none':
                door_product_url = None
            else:
                door_product_url = generate_url_byname(name_like = door_option)

            door_product_epd = fetch_epd_data(url = door_product_url, api_token = api_key)
            epd_datalist["door"] = door_product_epd

            for material_name, epd_data in epd_datalist.items():
                # collect  GWP values per functional unit

                gwp_values = {}
                gwp_values["gwp_per_m2"] = []
                gwp_values["gwp_per_kg"] = []
                gwp_values["gwp_per_m3"] = []
                gwp_values["gwp_per_m"] = []
                gwp_values['gwp_per_unit'] = []

                for idx, epd in enumerate(epd_data,start = 1):
                    # parse json repsonse based on epd_type
                    parsed_data = parse_product_epd(epd)
                    # per unit
                    gwp_per_unit = parsed_data["gwp_per_unit (kg CO2 eq/unit)"]
   
                    # per area
                    gwp_per_m2 = parsed_data["gwp_per_m2 (kg CO2 eq/m2)"]
                    if gwp_per_m2 != 0.0:
                        gwp_values["gwp_per_m2"].append(float(gwp_per_m2))
                    elif gwp_per_m2 == 0.0 and gwp_per_unit != 0.0 and material_name == "door" and door_option != 'garage door':
                        gwp_per_m2 = gwp_per_unit/door_area_per_unit
                        gwp_values["gwp_per_m2"].append(float(gwp_per_m2))

                    gwp_per_kg = parsed_data["gwp_per_kg (kg CO2 eq/kg)"]
                    gwp_per_m = 0.0
                    if gwp_per_kg != 0.0:
                        gwp_values["gwp_per_kg"].append(float(gwp_per_kg))
                        if material_name == "strip":
                            gwp_per_m = gwp_per_kg * extract_numeric_value(parsed_data["mass_per_declared_unit"])/length_per_unit


                    gwp_per_m3 = parsed_data["gwp_per_m3 (kg CO2 eq/m3)"]
                    if gwp_per_m3 != 0.0:
                        gwp_values["gwp_per_m3"].append(float(gwp_per_m3))

                    if gwp_per_m != 0.0:
                        gwp_values["gwp_per_m"].append(float(gwp_per_m))
                
                # extract gwp statistics by 
                for functional_unit, list in gwp_values.items():
                    if len(list) == 0:
                        gwp = None
                        runner.registerInfo(f"No GWP values returned from {functional_unit}")
                    elif len(list) == 1:
                        gwp = list[0]
                    elif gwp_statistic == "minimum":
                        gwp = float(np.min(list))
                    elif gwp_statistic == "maximum":
                        gwp = float(np.max(list))
                    elif gwp_statistic == "mean":
                        gwp = float(np.mean(list))
                    elif gwp_statistic == "median":
                        gwp = float(np.median(list))
                    # store gwp value
                    subsurface_dict[subsurface_name][material_name][functional_unit] = gwp

                # multipliers for calculating embodied carbon over analysis period
                multiplier = lifetime_multiplier(subsurface_dict[subsurface_name][material_name]["lifetime"], analysis_period)
                
                embodied_carbon = 0.0
                if material_name == "strip":
                    strip_length = None
                    # silicone adhesive smoke gasket is applied to the full perimeter of the door
                    if subsurface.subSurfaceType() in ["Door","GlassDoor"] and strip_option in ["brush weatherstrip","silicone adhesive smoke gasket"]:
                        strip_length = subsurface_dict[subsurface_name]['dimension']['perimeter_m']
                    else:
                        strip_length = subsurface_dict[subsurface_name]['dimension']['width_m']
                    
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] *
                                                strip_length *
                                                multiplier)
                elif material_name == "door":
                    door_area = subsurface_dict[subsurface_name]['dimension']['area_m2']
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] != None:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] *
                                                    door_area *
                                                    multiplier)
                    else:
                        runner.registerInfo(f"No GWP per m2 value available for door in {subsurface_name}, skipping embodied carbon calculation for door.")
                
                subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                runner.registerInfo(f"Embodied carbon of {material_name} in {subsurface_name} (kg CO2 eq): {subsurface_dict[subsurface_name][material_name]['embodied_carbon_kg_co2_eq']}")
                
                subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"]

            runner.registerInfo(f"Embodied carbon in this subsurface in kg CO2 eq: {subsurface_dict[subsurface_name]['door_renovation_embodied_carbon_kg_co2_eq']}")

            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["subsurface object"].additionalProperties()
            additional_properties.setFeature("Subsurface name", subsurface_name)
            additional_properties.setFeature("embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"])
   
        pp.pprint(subsurface_dict)

        return True

# Register the measure
DoorEnhancement().registerWithApplication()

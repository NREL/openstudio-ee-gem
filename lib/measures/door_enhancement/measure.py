# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import typing
import numpy as np
import pprint as pp
from resources.EC3_lookup import fetch_epd_data
from resources.EC3_lookup import parse_product_epd
from resources.EC3_lookup import parse_industrial_epd
from resources.EC3_lookup import generate_url
from resources.EC3_lookup import calculate_geometry

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
        return ["electrochromic","fire_resistant","laminated","low_emissivity","tempered"]
    
    @staticmethod
    def wf_options():
        return ["anodized","painted","thermally_improved"]
    
    @staticmethod
    def epd_types():
        return ["Product","Industry"]

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define the arguments that user will input."""
        args = openstudio.measure.OSArgumentVector()

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
        strip_option.setDescription("Type of door bottom strip")
        args.append(strip_option)

        # make an argument for product life time of strip
        strip_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("strip_lifetime",True)
        strip_lifetime.setDisplayName("Product Lifetime of strip")
        strip_lifetime.setDescription("Life expectancy of door bottom strip")
        strip_lifetime.setDefaultValue(15)
        args.append(strip_lifetime)


        # make an argument for selecting EPD type
        edp_type_chs = openstudio.StringVector()
        for type in self.epd_types():
            edp_type_chs.append(type)
        epd_type = openstudio.measure.OSArgument.makeChoiceArgument("epd_type",edp_type_chs, True)
        epd_type.setDisplayName("EPD Type") 
        epd_type.setDescription("Type of EPD for searching GWP values, Product EPDs refer to specific products from a manufacturer, while industrial EPDs represent average data across an entire industry sector.")
        args.append(epd_type)

        # make an argument for selecting which gwp statistic to use for embodied carbon calculation
        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        args.append(gwp_statistic)

        # make an argument for total embodied carbon (TEC) of whole construction/building
        total_embodied_carbon = openstudio.measure.OSArgument.makeDoubleArgument("total_embodied_carbon", True)
        total_embodied_carbon.setDisplayName("Total Embodied Carbon of Building/Building Assembly")
        total_embodied_carbon.setDescription("Total GWP or embodied carbon intensity of the building (assembly) in kg CO2 eq.")
        total_embodied_carbon.setDefaultValue(0.0)
        args.append(total_embodied_carbon)

        # make an argument for api_token
        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

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
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        strip_lifetime = runner.getIntegerArgumentValue("strip_lifetime",user_arguments)
        total_embodied_carbon = runner.getDoubleArgumentValue("total_embodied_carbon",user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        epd_type = runner.getStringArgumentValue("epd_type", user_arguments)

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
            runner.registerError("Choose an integer larger than 0 for analysis period of embodeid carbon calcualtion.")
        if strip_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door bottom strip.")


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

            subsurface_dict[subsurface_name]["Door_bottom"] = {}
            subsurface_dict[subsurface_name]["Subsurface object"] = subsurface
            subsurface_dict[subsurface_name]["Door_bottom"]["Object"] = layered_construction
            subsurface_dict[subsurface_name]["Door_bottom"]["Lifetime"] = strip_lifetime
            subsurface_dict[subsurface_name]["Embodied_carbon"] = 0.0
            subsurface_dict[subsurface_name]["Dimension"] = calculate_geometry(self, subsurface)

            epd_datalist = {}

            strip_product_url = generate_url(material_name = "Door_bottom_strip", option = strip_option, epd_type= "Product", endpoint = "materials")
            strip_industry_url = generate_url(material_name = "Door_bottom_strip", option = strip_option, epd_type= "Industry", endpoint = "industry_epds")
            strip_product_epd = fetch_epd_data(url = strip_product_url, api_token = api_key)
            strip_industry_epd = fetch_epd_data(url = strip_industry_url, api_token = api_key)

            if epd_type == "Product":
                if not strip_product_epd:
                    strip_epd = strip_industry_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    strip_epd = strip_product_epd
                epd_datalist["strip"] = strip_epd

            elif epd_type == "Industry":
                if not strip_industry_epd:
                    strip_epd = strip_product_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    strip_epd = strip_industry_epd
                epd_datalist["strip"] = strip_epd

            for material_name, epd_data in epd_datalist.items():
                # collect  GWP values per functional unit
                gwp_values = {}
                gwp_values["gwp_per_m2"] = []
                gwp_values["gwp_per_kg"] = []
                gwp_values["gwp_per_m3"] = []

                for idx, epd in enumerate(epd_data,start = 1):
                    # parse json repsonse based on epd_eype
                    if epd_type == "Industry":
                        parsed_data = parse_industrial_epd(epd)
                    elif epd_type == "Product":
                        parsed_data = parse_product_epd(epd)

                    gwp_per_m2 = parsed_data["gwp_per_m2 (kg CO2 eq/m2)"]
                    if gwp_per_m2 != None:
                        gwp_values["gwp_per_m2"].append(float(gwp_per_m2))

                    gwp_per_kg = parsed_data["gwp_per_kg (kg CO2 eq/kg)"]
                    if gwp_per_kg != None:
                        gwp_values["gwp_per_kg"].append(float(gwp_per_kg))

                    gwp_per_m3 = parsed_data["gwp_per_m3 (kg CO2 eq/m3)"]
                    if gwp_per_m3 != None:
                        gwp_values["gwp_per_m3"].append(float(gwp_per_m3))
                
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

                if analysis_period <= subsurface_dict[subsurface_name][material_name]["Lifetime"]:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["Volume (m3)"])
                    subsurface_dict[subsurface_name][material_name]["embodied_carbon"] = embodied_carbon
                else:
                    multiplier = np.ceil(analysis_period/subsurface_dict[subsurface_name][material_name]["Lifetime"])
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["Volume (m3)"] * multiplier)
                    subsurface_dict[subsurface_name][material_name]["embodied_carbon"] = embodied_carbon

                subsurface_dict[subsurface_name]["door_embodied_carbon"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon"]

            runner.registerInfo(f"door's embodied carbon in this subsurface: {subsurface_dict[subsurface_name]['door_embodied_carbon']}")

            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["Subsurface object"].additionalProperties()
            additional_properties.setFeature("Subsurface name", subsurface_name)
            additional_properties.setFeature("Embodied carbon", subsurface_dict[subsurface_name]["door_embodied_carbon"])
   
        pp.pprint(subsurface_dict)

        return True

# Register the measure
DoorEnhancement().registerWithApplication()

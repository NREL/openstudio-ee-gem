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
class WindowEnhancement(openstudio.measure.ModelMeasure):

    """A ModelMeasure for window enhancement, calculating embodied carbon."""

    def name(self):
        """Measure name."""
        return "Window Enhancement"

    def description(self):
        """Brief description of the measure."""
        return "Calculates embodied emissions for window frame enhancements using EC3 database lookup."

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure evaluates the embodied carbon impact of adding an IGU or storm window "
                "to an existing structure by analyzing frame material data from EC3.")
    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]
        
    @staticmethod
    def igu_options():
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

        #make an argument for igu options for filtering EPDs of igu
        igu_options_chs = openstudio.StringVector()
        for option in self.igu_options():
            igu_options_chs.append(option)
        igu_option = openstudio.measure.OSArgument.makeChoiceArgument("igu_option", igu_options_chs, True)
        igu_option.setDisplayName("IGU option") 
        igu_option.setDescription("Type of insulating glazing unit")
        args.append(igu_option)

        # make an argument for product life time of igu
        igu_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("igu_lifetime",True)
        igu_lifetime.setDisplayName("Product Lifetime of IGU")
        igu_lifetime.setDescription("Life expectancy of insulating glazing unit")
        igu_lifetime.setDefaultValue(15)
        args.append(igu_lifetime)

        # make an argument for product life time of window frame
        wf_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("wf_lifetime",True)
        wf_lifetime.setDisplayName("Product Lifetime of Window Frame")
        wf_lifetime.setDescription("Life expectancy of window frame")
        wf_lifetime.setDefaultValue(15)
        args.append(wf_lifetime)

        #make an argument for window frame options for filtering EPDs 
        wf_options_chs = openstudio.StringVector()
        for option in self.wf_options():
            wf_options_chs.append(option)
        wf_option = openstudio.measure.OSArgument.makeChoiceArgument("wf_option",wf_options_chs, True)
        wf_option.setDisplayName("Window frame option") 
        wf_option.setDescription("Type of aluminum extrusion")
        args.append(wf_option)

        # make an argument for cross-sectional area of window frame
        frame_cross_section_area = openstudio.measure.OSArgument.makeDoubleArgument("frame_cross_section_area", True)
        frame_cross_section_area.setDisplayName("Frame Cross Section Area (m²)")
        frame_cross_section_area.setDescription("Cross-sectional area of the IGU frame in square meters.")
        frame_cross_section_area.setDefaultValue(0.0025)
        args.append(frame_cross_section_area)

        # make an argument for selecting EPD type
        edp_type_chs = openstudio.StringVector()
        for type in self.epd_types():
            edp_type_chs.append(type)
        epd_type = openstudio.measure.OSArgument.makeChoiceArgument("epd_type",edp_type_chs, True)
        epd_type.setDisplayName("EPD Type") 
        epd_type.setDescription("Type of EPD for searching GWP values, Product EPDs refer to specific products from a manufacturer, while industrial EPDs represent average data across an entire industry sector.")
        args.append(epd_type)

        # make an argument for selcting which gwp statistic to use for embodied carbon calculation
        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        args.append(gwp_statistic)

        # make an argument for total embodied carbon (TEC) of whole construction/building
        total_embodied_carbon = openstudio.measure.OSArgument.makeDoubleArgument("total_embodied_carbon", True)
        total_embodied_carbon.setDisplayName("Total Embodeid Carbon of Building/Building Assembly")
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
        runner.registerInfo("Starting WindowEnhancement measure execution.")

        # Check if model exists
        if not model:
            runner.registerError("Model is None. Exiting measure.")
            return False
        # built-in error checking
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Retrieve user inputs
        frame_cross_section_area = runner.getDoubleArgumentValue("frame_cross_section_area", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        igu_option = runner.getStringArgumentValue("igu_option", user_arguments)
        wf_option = runner.getStringArgumentValue("wf_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        igu_lifetime = runner.getIntegerArgumentValue("igu_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgumentValue("wf_lifetime",user_arguments)
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
        if igu_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of insulating glazing unit.")
        if wf_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of window frame.")

        # Print the number of sub-surfaces before processing
        sub_surfaces = model.getSubSurfaces()
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")
        # List storing subsurface object subject to change, here we want to catch "Name: Sub Surface 2, Surface Type: FixedWindow, Space Name: Space 2"
        sub_surfaces_to_change = []
        # loop through sub surfaces
        for subsurface in sub_surfaces:

            if subsurface.subSurfaceType() in ["FixedWindow","OperableWindow","Skylight"]:
                # append the subsurface objects carrying windows into list
                sub_surfaces_to_change.append(subsurface) 
                runner.registerInfo(f"Processing window construction in {subsurface.nameString()}")           
            else:# if sub_surface.subSurfaceType() not in ["FixedWindow", "OperableWindow"]:
                runner.registerInfo(f"Skipping non-window surface: {subsurface.nameString()}")
                continue

        # dictionary storing properties of subsurfaces containing window construcitons 
        subsurface_dict = {}
        # loop through layered window construciton to collect glazing materials
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            subsurface_dict[subsurface_name] = {}
            if subsurface.construction().is_initialized():
                subsurface_const = subsurface.construction().get()
            if subsurface_const.to_LayeredConstruction().is_initialized():
                layered_construction = subsurface_const.to_LayeredConstruction().get()

            subsurface_dict[subsurface_name]["Glazing"] = {}
            subsurface_dict[subsurface_name]["Frame"] = {}
            subsurface_dict[subsurface_name]["Subsurface object"] = subsurface
            subsurface_dict[subsurface_name]["Glazing"]["Object"] = layered_construction
            subsurface_dict[subsurface_name]["Glazing"]["Lifetime"] = igu_lifetime
            subsurface_dict[subsurface_name]["Frame"]["Lifetime"] = wf_lifetime
            subsurface_dict[subsurface_name]["window_embodied_carbon"] = 0.0
            subsurface_dict[subsurface_name]["Dimension"] = calculate_geometry(self, subsurface)

            # determine number of panes of window
            # EC3 handle num_panes use ">=" operator instead of "="
            # If use unprocessed single pane EPD, underestimate emission associated with product manufacturing
            # if use multiple pane EPD, thickness of each pane in EPD might be different from the model (adopt this option, smaller error than single pane option)
            print(layered_construction.numLayers())
            if layered_construction.numLayers() == 1:
                num_panes = 1 
            elif layered_construction.numLayers() == 3:
                num_panes = 2
            elif layered_construction.numLayers() == 5:
                num_panes = 3 
            else:
                runner.registerInfo("currently unable to handle more complex scenarios.")
            subsurface_dict[subsurface_name]["Number of panes"] = num_panes

            # get thickness from each window construction layer
            total_glazing_thickness = 0.0
            for i in range(layered_construction.numLayers()):
                material = layered_construction.getLayer(i)
                runner.registerInfo(f"Layer {i+1}: {material.nameString()}") 
                if material.thickness(): # count air layer thickness (delete: and "Air" not in material.nameString():)
                    glazing_thickness = material.thickness()
                    runner.registerInfo(f"In {subsurface_name}: Material: {material.nameString()}, Thickness: {glazing_thickness} m")
                    total_glazing_thickness += glazing_thickness
                else: # handle the case when no thickness is prodvied by the model 
                    glazing_thickness = 0.003
                    total_glazing_thickness += glazing_thickness
                    runner.registerInfo(f"In {subsurface_name}: Material: {material.nameString()} doesn't have thickness attribute and a default thickness of 3 mm assigned.")
            
            glazing_area = subsurface_dict[subsurface_name]["Dimension"]["area"]
            subsurface_dict[subsurface_name]["Glazing"]["Total thickness (m)"] = total_glazing_thickness
            subsurface_dict[subsurface_name]["Glazing"]["Area (m2)"]  = glazing_area
            subsurface_dict[subsurface_name]["Glazing"]["Volume (m3)"] = total_glazing_thickness * glazing_area

            # get frame and divider dimensions:
            # reference: https://bigladdersoftware.com/epx/docs/9-3/input-output-reference/group-thermal-zone-description-geometry.html#windowpropertyframeanddivider
            if subsurface.windowPropertyFrameAndDivider().is_initialized(): # check if frame_and_divider exist in selected subsurface
                frame = subsurface.windowPropertyFrameAndDivider().get()
                frame_name = frame.nameString()
                frame_width = frame.frameWidth()
                frame_op = frame.frameOutsideProjection()
                frame_ip = frame.frameInsideProjection()
                frame_cross_section_area = frame_width * (frame_op + frame_ip + subsurface_dict[subsurface_name]["Glazing"]["Total thickness (m)"])
                frame_perimeter = subsurface_dict[subsurface_name]["Dimension"]["perimeter"]

                if frame.numberOfHorizontalDividers() != 0 or frame.numberOfVerticalDividers() != 0:
                    divider_width = frame.dividerWidth()
                    divider_op = frame.dividerOutsideProjection()
                    divider_ip = frame.dividerInsideProjection()
                    divider_cross_section_area = divider_width * (divider_op + divider_ip + subsurface_dict[subsurface_name]["Glazing"]["Total thickness (m)"])
                    num_hori_divider = frame.numberOfHorizontalDividers() # integer
                    num_verti_divider = frame.numberOfVerticalDividers() # integer
                    total_divider_length = (num_hori_divider * subsurface_dict[subsurface_name]["Dimension"]["width"] +
                                             num_verti_divider * subsurface_dict[subsurface_name]["Dimension"]["length"])
                else:
                    divider_width = 0.0
                    divider_cross_section_area = 0.0
                    runner.registerInfo(f"In {subsurface.nameString()}'s Frame {frame_name}: no divider")

                runner.registerInfo(f"In {subsurface.nameString()}'s Frame and divider: {frame_name},"
                                    f"Frame Width: {frame_width} m, cross sectional area: {frame_cross_section_area} m2, perimeter: {frame_perimeter}"
                                    f"Divider width: {divider_width}m, cross sectional area: {divider_cross_section_area} m2, total length: {total_divider_length} m")
            else:
                runner.registerInfo(f"In {subsurface.nameString()}: no frame and divider")

            subsurface_dict[subsurface_name]["Frame"]["Object"] = frame
            subsurface_dict[subsurface_name]["Frame"]["Frame cross sectional area (m2)"] = frame_cross_section_area
            subsurface_dict[subsurface_name]["Frame"]["Divider cross sectional area (m2)"] = divider_cross_section_area
            subsurface_dict[subsurface_name]["Frame"]["Volume (m3)"] = frame_cross_section_area * frame_perimeter + divider_cross_section_area * total_divider_length

            epd_datalist = {}

            glazing_product_url = generate_url(material_name = "InsulatingGlazingUnits", option = igu_option, glass_panes = num_panes, epd_type= "Product", endpoint = "materials")
            frame_product_url = generate_url(material_name = "AluminiumExtrusions", epd_type= "Product", endpoint = "materials") # EC3 only has aluminum option, revisit later
            glazing_industry_url = generate_url(material_name = "InsulatingGlazingUnits", option = igu_option, glass_panes = num_panes, epd_type= "Industry", endpoint = "industry_epds")
            frame_industry_url = generate_url(material_name = "AluminiumExtrusions", epd_type= "Industry", endpoint = "industry_epds")
            glazing_product_epd = fetch_epd_data(url = glazing_product_url, api_token = api_key)
            frame_product_epd = fetch_epd_data(url = frame_product_url, api_token = api_key)
            glazing_industry_epd = fetch_epd_data(url = glazing_industry_url, api_token = api_key)
            frame_industry_epd = fetch_epd_data(url = frame_industry_url, api_token = api_key)

            if epd_type == "Product":
                if not glazing_product_epd:
                    glazing_epd = glazing_industry_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    glazing_epd = glazing_product_epd
                epd_datalist["Glazing"] = glazing_epd
                if not frame_product_epd:
                    frame_epd = frame_industry_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    frame_epd = frame_product_epd
                epd_datalist["Frame"] = frame_epd

            elif epd_type == "Industry":
                if not glazing_industry_epd:
                    glazing_epd = glazing_product_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    glazing_epd = glazing_industry_epd
                epd_datalist["Glazing"] = glazing_epd
                if not frame_industry_epd:
                    frame_epd = frame_product_epd
                    runner.registerInfo("Product EPDs are not avialable, industry EPDs are accessed instead")
                else:
                    frame_epd = frame_industry_epd
                epd_datalist["Frame"] = frame_epd

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

                subsurface_dict[subsurface_name]["window_embodied_carbon"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon"]

            runner.registerInfo(f"window's embodied carbon in this subsurface: {subsurface_dict[subsurface_name]['window_embodied_carbon']}")

            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["Subsurface object"].additionalProperties()
            additional_properties.setFeature("Subsurface name", subsurface_name)
            additional_properties.setFeature("Embodied carbon", subsurface_dict[subsurface_name]["window_embodied_carbon"])
   
        pp.pprint(subsurface_dict)

        return True

# Register the measure
WindowEnhancement().registerWithApplication()

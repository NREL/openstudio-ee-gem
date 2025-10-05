# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************
import pprint as pp
from re import sub
import openstudio
import typing
import numpy as np
from resources.EC3_lookup import fetch_epd_data,parse_product_epd,generate_url_byname,calculate_geometry,lifetime_multiplier,extract_numeric_value

# Start the measure
class WindowEnhancement(openstudio.measure.ModelMeasure):

    """A ModelMeasure for window enhancement, calculating embodied carbon. EC3 data fetched through categorization and keywords."""

    def name(self):
        """Measure name."""
        return "Window Enhancement"

    def description(self):
        """Brief description of the measure."""
        return "Calculates embodied emissions for window frame enhancements using EC3 database lookup. This measure only functions if you have an EC3 key and the required Python libraries installed. In addition to getting embodied car value it does also alter the thermal performance of the windows based on the selections made"

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure evaluates the embodied carbon impact of adding an IGU or storm window "
                "to an existing structure by analyzing frame material data from EC3.")
    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]
    
    @staticmethod
    def wf_options():
        return ["none","wood window frame","wood-aluminum window frame"] # options provided are based on EPD availability
    
    @staticmethod
    def caulking_options():
        return ["none", "acrylic", "polyurethane"]
    
    @staticmethod
    def film_options():
        return ["none", 'safety film', 'solar control film', 'anti-graffiti film', 'decorative film', 'low-e film']

    @staticmethod
    def window_options():
        return ["none", "fixed window", "project window", "sliding window", "storefront window"]

    @staticmethod
    def weatherstrip_options():
        return ["none", "silicone adhesive smoke gasket"] # add more options if there are more EPDs available
    
    @staticmethod
    def glass_options():
        return ["none","provide user_num_panes"]

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define the arguments that user will input."""
        args = openstudio.measure.OSArgumentVector()

        #make an argument for analysis period
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        # make an argument for product life time of glass pane
        glass_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("glass_lifetime",True)
        glass_lifetime.setDisplayName("Product Lifetime of Glass pane")
        glass_lifetime.setDescription("Life expectancy of glass pane")
        glass_lifetime.setDefaultValue(15)
        args.append(glass_lifetime)

        # make an argument for product life time of window frame
        wf_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("wf_lifetime",True)
        wf_lifetime.setDisplayName("Product Lifetime of Window Frame")
        wf_lifetime.setDescription("Life expectancy of window frame")
        wf_lifetime.setDefaultValue(15)
        args.append(wf_lifetime)

        # make an argument for product life time of caulking sealant
        caulking_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("caulking_lifetime",True)
        caulking_lifetime.setDisplayName("Product Lifetime of Caulking Sealant")
        caulking_lifetime.setDescription("Life expectancy of caulking sealant")
        caulking_lifetime.setDefaultValue(10)
        args.append(caulking_lifetime)

        # make an argument for product life time of glazing film
        film_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("film_lifetime",True)
        film_lifetime.setDisplayName("Product Lifetime of Glazing Film")
        film_lifetime.setDescription("Life expectancy of glazing film")
        film_lifetime.setDefaultValue(10)
        args.append(film_lifetime)

        #make an argument for product life time of weatherstrip
        weatherstrip_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("weatherstrip_lifetime",True)
        weatherstrip_lifetime.setDisplayName("Product Lifetime of Weatherstrip")
        weatherstrip_lifetime.setDescription("Life expectancy of weatherstrip")
        weatherstrip_lifetime.setDefaultValue(10)
        args.append(weatherstrip_lifetime)

        # make an argument for product life time of window
        window_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("window_lifetime",True)
        window_lifetime.setDisplayName("Product Lifetime of Window")
        window_lifetime.setDescription("Life expectancy of window")
        window_lifetime.setDefaultValue(30)
        args.append(window_lifetime)

        # make an argument for window frame options for filtering EPDs 
        wf_options_chs = openstudio.StringVector()
        for option in self.wf_options():
            wf_options_chs.append(option)
        wf_option = openstudio.measure.OSArgument.makeChoiceArgument("wf_option",wf_options_chs, True)
        wf_option.setDisplayName("Window frame option")
        wf_option.setDescription("Select none if no window frame is to be installed, otherwise provide frame type.")
        args.append(wf_option)

        # make an argument for caulking material options for filtering EPDs
        caulking_options_chs = openstudio.StringVector()
        for option in self.caulking_options():
            caulking_options_chs.append(option)
        caulking_option = openstudio.measure.OSArgument.makeChoiceArgument("caulking_option", caulking_options_chs, True)
        caulking_option.setDisplayName("Caulking Material Option")
        caulking_option.setDescription("Select none if no caulking is to be applied, otherwise provide material type.")
        args.append(caulking_option)

        # make an argument for film options for filtering EPDs
        film_options_chs = openstudio.StringVector()
        for option in self.film_options():
            film_options_chs.append(option)
        film_option = openstudio.measure.OSArgument.makeChoiceArgument("film_option", film_options_chs, True)
        film_option.setDisplayName("Glazing Film Option")
        film_option.setDescription("Select none if no glazing film is to be installed, otherwise provide film type.")
        args.append(film_option)

        # make an argument for window options for filtering EPDs
        window_options_chs = openstudio.StringVector()  
        for option in self.window_options():
            window_options_chs.append(option)
        window_option = openstudio.measure.OSArgument.makeChoiceArgument("window_option", window_options_chs, True)
        window_option.setDisplayName("Window Type Option")
        window_option.setDescription("Select none if no new window is to be installed, otherwise provide window type. NOTE: if window_option is selected, wf_option and glass_option will be ignored in the calculation to avoid double counting.")
        args.append(window_option)

        # make an argument for glass option for filtering EPDs and decide whether to renovate
        glass_options_chs = openstudio.StringVector()
        for option in self.glass_options():
            glass_options_chs.append(option)
        glass_option = openstudio.measure.OSArgument.makeChoiceArgument("glass_option", glass_options_chs, True)
        glass_option.setDisplayName("Glass Option on Renovation")
        glass_option.setDescription("Select none if no new glass pane is to be installed, otherwise provide user_num_panes.")
        args.append(glass_option)

        # make an argument for weatherstrip options for filtering EPDs
        weatherstrip_options_chs = openstudio.StringVector()
        for option in self.weatherstrip_options():
            weatherstrip_options_chs.append(option)
        weatherstrip_option = openstudio.measure.OSArgument.makeChoiceArgument("weatherstrip_option", weatherstrip_options_chs, True)
        weatherstrip_option.setDisplayName("Weatherstrip Option")
        weatherstrip_option.setDescription("Material type of weatherstrip")
        args.append(weatherstrip_option)

        # make an argument for caulking material thickness applied
        caulking_thickness = openstudio.measure.OSArgument.makeDoubleArgument("caulking_thickness", True)
        caulking_thickness.setDisplayName("Caulking Material Thickness (m)")
        caulking_thickness.setDescription("Thickness of the caulking material applied in meters.")
        caulking_thickness.setDefaultValue(0.008) # 8 mm thickness
        args.append(caulking_thickness)

        # make an argument for number of panes to be replaced
        user_num_panes = openstudio.measure.OSArgument.makeIntegerArgument("user_num_panes", True)
        user_num_panes.setDisplayName("Number of Glass Panes Provided by User")
        user_num_panes.setDescription("Number of glass panes to be installed as determined by user")
        user_num_panes.setDefaultValue(0) # 0 means do not install any new glass panes
        args.append(user_num_panes)

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
        # 17' = 5.1816 m for silicone adhesive smoke gasket, source: https://buildingtransparency.org/ec3/epds/ec327rq0
        length_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit", True)
        length_per_unit.setDisplayName("Length per Unit of Strip")
        length_per_unit.setDescription("Length per unit of window sash strip in m")
        length_per_unit.setDefaultValue(5.1816)
        args.append(length_per_unit)

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
        caulking_thickness = runner.getDoubleArgumentValue("caulking_thickness", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        wf_option = runner.getStringArgumentValue("wf_option", user_arguments)
        caulking_option = runner.getStringArgumentValue("caulking_option", user_arguments)
        film_option = runner.getStringArgumentValue("film_option", user_arguments)
        window_option = runner.getStringArgumentValue("window_option", user_arguments)
        weatherstrip_option = runner.getStringArgumentValue("weatherstrip_option", user_arguments)
        glass_option = runner.getStringArgumentValue("glass_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        glass_lifetime = runner.getIntegerArgumentValue("glass_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgumentValue("wf_lifetime",user_arguments)
        caulking_lifetime = runner.getIntegerArgumentValue("caulking_lifetime",user_arguments)
        film_lifetime = runner.getIntegerArgumentValue("film_lifetime",user_arguments)
        weatherstrip_lifetime = runner.getIntegerArgumentValue("weatherstrip_lifetime",user_arguments)
        window_lifetime = runner.getIntegerArgumentValue("window_lifetime",user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        user_num_panes = runner.getIntegerArgumentValue("user_num_panes", user_arguments)
        length_per_unit = runner.getDoubleArgumentValue("length_per_unit", user_arguments)
        # epd_type = runner.getStringArgumentValue("epd_type", user_arguments)

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
        if glass_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of glass pane.")
        if wf_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of window frame.")
        if caulking_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of caulking sealant.")
        if film_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of glazing film.")
        if weatherstrip_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of weatherstrip.")
        if window_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of window.")

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
        
        # loop through layered window construciton to collect glass materials
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            subsurface_dict[subsurface_name] = {}
            if subsurface.construction().is_initialized():
                subsurface_const = subsurface.construction().get()
            if subsurface_const.to_LayeredConstruction().is_initialized():
                layered_construction = subsurface_const.to_LayeredConstruction().get()

            # If num_panes not provided by users, determine number of panes from model
            num_panes = 0
            if user_num_panes > 0 and user_num_panes <= 3:
                num_panes = user_num_panes
                runner.registerInfo(f"Number of panes to be installed provided by user is {num_panes}, use it for all the windows.")
            elif user_num_panes > 3:
                num_panes = 3 # assign triple pane as the maximum number of panes
                runner.registerInfo("Number of panes is changed tidio 3 because user_num_panes is more than 3, currently unable to handle more complex scenarios due to the lack of EPD data.")
            elif user_num_panes == 0:
                runner.registerInfo("Number of panes to be installed is not provided by user, deriving the value from the model.")
                if layered_construction.numLayers() == 1:
                    num_panes = 1
                elif layered_construction.numLayers() == 3:
                    num_panes = 2
                elif layered_construction.numLayers() == 5:
                    num_panes = 3
            else:
                runner.registerError("Number of panes provided by user is less than 0, please provide a valid integer.")
                return False
            
            # initialize total embodied carbon of window renovation in this subsurface
            subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"] = 0.0 

            # create renovation scenarios for each window type subsurface
            subsurface_dict[subsurface_name]["glass"] = {}
            subsurface_dict[subsurface_name]["frame"] = {}
            subsurface_dict[subsurface_name]["caulking"] = {}
            subsurface_dict[subsurface_name]["film"] = {}
            subsurface_dict[subsurface_name]["weatherstrip"] = {}
            subsurface_dict[subsurface_name]["window"] = {}

            #assign openstudio model
            subsurface_dict[subsurface_name]["subsurface_object"] = subsurface
            subsurface_dict[subsurface_name]["glass"]["object"] = layered_construction
            #assign lifetime values
            subsurface_dict[subsurface_name]["glass"]["lifetime"] = glass_lifetime
            subsurface_dict[subsurface_name]["frame"]["lifetime"] = wf_lifetime
            subsurface_dict[subsurface_name]["caulking"]["lifetime"] = caulking_lifetime
            subsurface_dict[subsurface_name]["film"]["lifetime"] = film_lifetime
            subsurface_dict[subsurface_name]["weatherstrip"]["lifetime"] = weatherstrip_lifetime
            subsurface_dict[subsurface_name]["window"]["lifetime"] = window_lifetime
            #assign renovation options
            subsurface_dict[subsurface_name]["glass"]["renovation_option"] = num_panes
            subsurface_dict[subsurface_name]["frame"]["renovation_option"] = wf_option
            subsurface_dict[subsurface_name]["caulking"]["renovation_option"] = caulking_option
            subsurface_dict[subsurface_name]["film"]["renovation_option"] = film_option
            subsurface_dict[subsurface_name]["weatherstrip"]["renovation_option"] = weatherstrip_option
            subsurface_dict[subsurface_name]["window"]["renovation_option"] = window_option

            #initialize total embodied carbon of window renovation in this subsurface
            subsurface_dict[subsurface_name]["window_embodied_carbon_kg_co2_eq"] = 0.0
            #calculate and store subsurface dimension
            subsurface_dict[subsurface_name]["dimension"] = calculate_geometry(self, subsurface)

            # calculate glazing area and caulking material consumption
            #reference: https://bigladdersoftware.com/epx/docs/9-3/input-output-reference/group-thermal-zone-description-geometry.html#windowpropertyframeanddivider
            if subsurface.windowPropertyFrameAndDivider().is_initialized(): # check if frame_and_divider exist in selected subsurface
                frame = subsurface.windowPropertyFrameAndDivider().get()
                frame_name = frame.nameString()
                frame_width = float(frame.frameWidth()) # need to subtract from total width and length to get glazing area

                # handle the case when divider exist
                if frame.numberOfHorizontalDividers() != 0 or frame.numberOfVerticalDividers() != 0:
                    divider_width = float(frame.dividerWidth())
                    num_hori_divider = frame.numberOfHorizontalDividers() # integer, number of horizontal dividers
                    num_verti_divider = frame.numberOfVerticalDividers() # integer, number of vertical dividers
                else:
                    divider_width = 0.0
                    num_hori_divider = 0
                    num_verti_divider = 0   
                    runner.registerInfo(f"In {subsurface.nameString()}'s Frame {frame_name}: no divider")

                runner.registerInfo(f"In {subsurface.nameString()}'s Frame and divider: {frame_name},"
                                    f"Frame Width: {frame_width} m"
                                    f"Divider width: {divider_width}m")
            else:
                runner.registerInfo(f"In {subsurface.nameString()}: no frame and divider")

            window_width = float(subsurface_dict[subsurface_name]["dimension"]["width_m"])
            window_length = float(subsurface_dict[subsurface_name]["dimension"]["length_m"])
            window_area = float(subsurface_dict[subsurface_name]["dimension"]["area_m2"])
            window_perimeter = float(subsurface_dict[subsurface_name]["dimension"]["perimeter_m"])

            # calculate glazing area for applying glazing film 
            subsurface_dict[subsurface_name]["film"]["width_m"] = float(window_width - 2 * frame_width - num_verti_divider * divider_width)
            subsurface_dict[subsurface_name]["film"]["length_m"] = float(window_length - 2 * frame_width - num_hori_divider * divider_width)
            subsurface_dict[subsurface_name]["film"]["area_m2"] = subsurface_dict[subsurface_name]["film"]["width_m"] * subsurface_dict[subsurface_name]["film"]["length_m"]
            # calculate caulking material consumption in volume
            caulking_volume = window_perimeter * 0.5 * np.pi * (caulking_thickness/2)**2 # in m3, assuming the caulking forms a half-cylindrical bead along the joint
            subsurface_dict[subsurface_name]["caulking"]["length_m"] = window_perimeter
            subsurface_dict[subsurface_name]["caulking"]["thickness_m"] = float(caulking_thickness)
            subsurface_dict[subsurface_name]["caulking"]["volume_m3"] = float(caulking_volume)
            # calculate weatherstrip material consumption in length
            strip_length = 0.0
            # strip length is the shorter side of the window, assuming the strip is applied to the operable part of the window only
            if subsurface.subSurfaceType() == "OperableWindow":
                strip_length = min(window_length, window_width) # use the shorter side of the window as the length of strip applied
            subsurface_dict[subsurface_name]["weatherstrip"]["length_m"] = float(strip_length)
            # assign window area to window, glass, and window frame
            subsurface_dict[subsurface_name]["window"]["area_m2"] = window_area
            subsurface_dict[subsurface_name]["glass"]["area_m2"] = window_area
            subsurface_dict[subsurface_name]["frame"]["area_m2"] = window_area

            # fetch EPD data from EC3 database
            epd_datalist = {}

            # window frame EPD
            frame_product_url = None
            if wf_option != "none" and window_option == "none": # if window_option is selected, glass and frame option will be ignored to avoid double counting
                frame_product_url = generate_url_byname(name_like = wf_option, plant_geography = '150') # '150' means Europe, there is no EPDs in NA region
            elif wf_option != "none" and window_option != "none":
                runner.registerInfo("Both window option and frame option are selected, to avoid double counting, window option is ignored in the calculation.")
            else:
                runner.registerInfo("No window frame renovation option selected, skip fetching window frame EPD data.")

            # glass pane EPD
            glass_product_url = None
            if glass_option != "none" and window_option == "none": # if window_option is selected, glass and frame option will be ignored to avoid double counting
                if num_panes == 1:
                    glass_product_url = generate_url_byname(category = '6daae3d967104f5c8c85199b259f58c8', name_like = 'monolithic glass')
                elif num_panes == 2:
                    glass_product_url = generate_url_byname(category = 'ade3ad3405124279955e7d3085f59383', name_like = 'double pane')
                elif num_panes == 3:
                    glass_product_url = generate_url_byname(category = 'ade3ad3405124279955e7d3085f59383', name_like = 'triple pane')
            elif glass_option != "none" and window_option != "none":
                runner.registerInfo("Both window option and glass option are selected, to avoid double counting, window option is ignored in the calculation.")
            else:
                runner.registerInfo("No glass pane renovation option selected, skip fetching glass pane EPD data.")

            # caulking sealant EPD
            caulking_product_url = None
            if caulking_option == "acrylic":
                caulking_product_url = generate_url_byname(name_like = 'sealant', description_like = caulking_option)
            elif caulking_option == "polyurethane":
                caulking_product_url = generate_url_byname(category = 'e95e0d13de844101beb364b47af73d45', description_like = 'window')
            else:
                runner.registerInfo("No caulking renovation option selected, skip fetching caulking EPD data.")

            # glazing film EPD
            film_product_url = None
            if film_option != "none":
                film_product_url = generate_url_byname(category = '3aa3a34fae9a400fa297339ba88e1fab', name_like = film_option)
            else:
                runner.registerInfo("No glazing film renovation option selected, skip fetching glazing film EPD data.")

            # weatherstrip EPD
            weatherstrip_product_url = None
            if weatherstrip_option != "none":
                weatherstrip_product_url = generate_url_byname(category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d', name_like = weatherstrip_option)
            else:
                runner.registerInfo("No weatherstrip renovation option selected, skip fetching weatherstrip EPD data.")

            # window product EPD
            window_product_url = None
            if window_option != "none" and glass_option == "none" and wf_option == "none": # if window_option is selected, glass and frame option will be ignored to avoid double counting
                window_product_url = generate_url_byname(name_like = window_option)
            elif window_option != "none" and (glass_option != "none" or wf_option != "none"):
                runner.registerInfo("Both window option and glass or frame option are selected, to avoid double counting, window option is ignored in the calculation.")
            else:
                runner.registerInfo("No window renovation option selected, skip fetching window product EPD data.")

            # fetch EPD data using generated url
            glass_product_epd = fetch_epd_data(url = glass_product_url, api_token = api_key)
            frame_product_epd = fetch_epd_data(url = frame_product_url, api_token = api_key)
            caulking_product_epd = fetch_epd_data(url = caulking_product_url, api_token = api_key)
            film_product_epd = fetch_epd_data(url = film_product_url, api_token = api_key)
            weatherstrip_product_epd = fetch_epd_data(url = weatherstrip_product_url, api_token = api_key)
            window_product_epd = fetch_epd_data(url = window_product_url, api_token = api_key)

            # store EPD data in a dictionary
            epd_datalist = {}
            epd_datalist["glass"] = glass_product_epd
            epd_datalist["frame"] = frame_product_epd
            epd_datalist["caulking"] = caulking_product_epd
            epd_datalist["film"] = film_product_epd
            epd_datalist["weatherstrip"] = weatherstrip_product_epd
            epd_datalist["window"] = window_product_epd

            # process EPD data to extract GWP values
            for material_name, epd_data in epd_datalist.items():
                if epd_data is None:
                    runner.registerInfo(f"Renovation option is none, no epd data fetched, GWP values is None.")
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_kg"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m"] = None
                    continue

                # collect  GWP values per functional unit
                gwp_values = {}
                gwp_values["gwp_per_m2"] = []
                gwp_values["gwp_per_kg"] = []
                gwp_values["gwp_per_m3"] = []
                gwp_values["gwp_per_m"] = [] 

                for idx, epd in enumerate(epd_data,start = 1):
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

                    gwp_per_m = gwp_per_kg * extract_numeric_value(parsed_data["mass_per_declared_unit"])/length_per_unit
                    if gwp_per_m != None:
                        gwp_values["gwp_per_m"].append(float(gwp_per_m))
                
                # extract gwp statistics
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

                if material_name in ["glass","film","frame","window"]: # functional unit is area, 1 m2
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] is None:
                        embodied_carbon = 0.0
                        runner.registerInfo(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] * subsurface_dict[subsurface_name][material_name]["area_m2"] * multiplier)
                elif material_name == "caulking": # functional unit is volume, 1 m3
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] is None:
                        embodied_carbon = 0.0
                        runner.registerInfo(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["volume_m3"] * multiplier)
                elif material_name == "weatherstrip": # functional unit is length, 1 m
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m"] is None:
                        embodied_carbon = 0.0
                        runner.registerInfo(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] * subsurface_dict[subsurface_name][material_name]["length_m"] * multiplier)

                # assign embodied carbon
                subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                runner.registerInfo(f"Embodied carbon of {material_name} in {subsurface_name} (kg CO2 eq): {subsurface_dict[subsurface_name][material_name]['embodied_carbon_kg_co2_eq']}")

                if parsed_data["thickness"]:# provide thickness of the product if available
                    subsurface_dict[subsurface_name][material_name]["thickness"] = parsed_data["thickness"]
                subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"]

            runner.registerInfo(f"Embodied carbon of window renovation in this subsurface (kg CO2 eq): {subsurface_dict[subsurface_name]['window_renovation_embodied_carbon_kg_co2_eq']}")


            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["subsurface_object"].additionalProperties()
            additional_properties.setFeature("subsurface_name", subsurface_name)
            additional_properties.setFeature("embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"])

        pp.pprint(subsurface_dict)
        return True

# Register the measure
WindowEnhancement().registerWithApplication()

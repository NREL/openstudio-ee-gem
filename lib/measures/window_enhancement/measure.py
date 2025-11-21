# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

from importlib.util import spec_from_file_location
import pprint as pp
from pyexpat import model
from re import sub
import openstudio
import typing
import numpy as np
from resources.EC3_lookup import *

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
        return ["none","wood window frame","wood-aluminium window frame"] # options provided are based on EPD availability
    
    @staticmethod
    def caulking_options():
        return ["none", "acrylic", "polyurethane"]
    
    @staticmethod
    def film_options():
        return ["none", 'safety film', 'solar control film', 'anti-graffiti film', 'decorative film', 'low-e film']

    @staticmethod
    def window_options():
        return ["none", "fixed window", "project window", "sliding window", "casement window", "storefront window", "defined by model"]

    @staticmethod
    def weatherstrip_options():
        return ["none", "silicone adhesive smoke gasket"] # add more options if there are more EPDs available
    
    @staticmethod
    def glass_options():
        return ["none","provide user_num_panes"]
    
    @staticmethod
    def secondary_glazing_options():
        return ["none", "install secondary glazing"]

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define the arguments that user will input."""
        args = openstudio.measure.OSArgumentVector()

        # make a choice argument for model objects
        space_type_handles = openstudio.StringVector()
        space_type_display_names = openstudio.StringVector()

        # putting model object and names into dict
        space_type_args = model.getSpaceTypes()
        space_type_args_dict = {}
        for space_type_arg in space_type_args:
            space_type_args_dict[space_type_arg.nameString()] = space_type_arg

        # looping through sorted dict of model objects
        for key, value in sorted(space_type_args_dict.items()):
        # only include if space type is used in the model
            if value.spaces():  # if there is at least one space assigned to this space type
                space_type_handles.append(str(value.handle()))
                space_type_display_names.append(key)

        # add building to string vector with space type
        building = model.getBuilding()
        space_type_handles.append(str(building.handle()))
        space_type_display_names.append("*Entire Building*")

        # make a choice argument for space type
        space_type = openstudio.measure.OSArgument.makeChoiceArgument(
            "space_type",
            space_type_handles,
            space_type_display_names
            )
        space_type.setDisplayName("Apply the Measure to a Specific Space Type or to the Entire Model.")
        space_type.setDefaultValue("*Entire Building*")  # if no selection, apply to entire building
        args.append(space_type)

        # make an argument for air infiltration reduction percentage
        space_infiltration_reduction_percent = openstudio.measure.OSArgument.makeDoubleArgument("space_infiltration_reduction_percent", True)
        space_infiltration_reduction_percent.setDisplayName("Space Infiltration Power Reduction")
        space_infiltration_reduction_percent.setDefaultValue(50.0)
        space_infiltration_reduction_percent.setUnits("%")
        args.append(space_infiltration_reduction_percent)

        # DISABLED: make an argument for constant_coefficient
        # constant_coefficient = openstudio.measure.OSArgument.makeDoubleArgument('constant_coefficient', False)
        # constant_coefficient.setDisplayName('Constant Coefficient')
        # constant_coefficient.setDefaultValue(1.0)
        # args.append(constant_coefficient)

        # DISABLED: make an argument for temperature_coefficient
        # temperature_coefficient = openstudio.measure.OSArgument.makeDoubleArgument('temperature_coefficient', False)
        # temperature_coefficient.setDisplayName('Temperature Coefficient')
        # temperature_coefficient.setDefaultValue(0.0)
        # args.append(temperature_coefficient)

        # DISABLED: make an argument for wind_speed_coefficient
        # wind_speed_coefficient = openstudio.measure.OSArgument.makeDoubleArgument('wind_speed_coefficient', False)
        # wind_speed_coefficient.setDisplayName('Wind Speed Coefficient')
        # wind_speed_coefficient.setDefaultValue(0.0)
        # args.append(wind_speed_coefficient)

        # DISABLED: make an argument for wind_speed_squared_coefficient
        # wind_speed_squared_coefficient = openstudio.measure.OSArgument.makeDoubleArgument('wind_speed_squared_coefficient', False)
        # wind_speed_squared_coefficient.setDisplayName('Wind Speed Squared Coefficient')
        # wind_speed_squared_coefficient.setDefaultValue(0.0)
        # args.append(wind_speed_squared_coefficient)

        # make an argument for alter_coef
        alter_coef = openstudio.measure.OSArgument.makeBoolArgument('alter_coef', True)
        alter_coef.setDisplayName('Alter constant temperature and wind speed coefficients.')
        alter_coef.setDescription('Setting this to false will result in infiltration objects that maintain the coefficients from the initial model. Setting this to true replaces the existing coefficients with the values entered for the coefficient arguments in this measure')
        alter_coef.setDefaultValue(True)
        args.append(alter_coef)

        #make an argument for analysis period
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon calculation in years. This parameter and product life expectancy will affect the number of replacements during the analysis period.")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        # make an argument for product life time of glass pane
        glass_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("glass_lifetime",True)
        glass_lifetime.setDisplayName("Product Lifetime of Glass pane")
        glass_lifetime.setDescription("Life expectancy of glass pane. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        glass_lifetime.setDefaultValue(15)
        args.append(glass_lifetime)

        # make an argument for product life time of window frame
        wf_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("wf_lifetime",True)
        wf_lifetime.setDisplayName("Product Lifetime of Window Frame")
        wf_lifetime.setDescription("Life expectancy of window frame. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        wf_lifetime.setDefaultValue(15)
        args.append(wf_lifetime)

        # make an argument for product life time of caulking sealant
        caulking_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("caulking_lifetime",True)
        caulking_lifetime.setDisplayName("Product Lifetime of Caulking Sealant")
        caulking_lifetime.setDescription("Life expectancy of caulking sealant. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        caulking_lifetime.setDefaultValue(10)
        args.append(caulking_lifetime)

        # make an argument for product life time of glazing film
        film_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("film_lifetime",True)
        film_lifetime.setDisplayName("Product Lifetime of Glazing Film")
        film_lifetime.setDescription("Life expectancy of glazing film. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        film_lifetime.setDefaultValue(10)
        args.append(film_lifetime)

        #make an argument for product life time of weatherstrip
        weatherstrip_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("weatherstrip_lifetime",True)
        weatherstrip_lifetime.setDisplayName("Product Lifetime of Weatherstrip")
        weatherstrip_lifetime.setDescription("Life expectancy of weatherstrip. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        weatherstrip_lifetime.setDefaultValue(10)
        args.append(weatherstrip_lifetime)

        # make an argument for product life time of window
        window_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("window_lifetime",True)
        window_lifetime.setDisplayName("Product Lifetime of Window")
        window_lifetime.setDescription("Life expectancy of window. Default value is provided based on data from the Certified Commercial Property Inspectors Association (CCPIA).")
        window_lifetime.setDefaultValue(30)
        args.append(window_lifetime)

        # make an argument for window frame options for filtering EPDs 
        wf_options_chs = openstudio.StringVector()
        for option in self.wf_options():
            wf_options_chs.append(option)
        wf_option = openstudio.measure.OSArgument.makeChoiceArgument("wf_option",wf_options_chs, True)
        wf_option.setDisplayName("Window frame option")
        wf_option.setDescription("Select none if no window frame is to be installed, otherwise provide frame type. NOTE: When not none, this renovation option can not work with the entire window replacement at the same time to avoid double counting.")
        wf_option.setDefaultValue("none")
        args.append(wf_option)

        # make an argument for caulking material options for filtering EPDs
        caulking_options_chs = openstudio.StringVector()
        for option in self.caulking_options():
            caulking_options_chs.append(option)
        caulking_option = openstudio.measure.OSArgument.makeChoiceArgument("caulking_option", caulking_options_chs, True)
        caulking_option.setDisplayName("Caulking Material Option")
        caulking_option.setDescription("Select none if no caulking is to be applied, otherwise provide material type. This renovation option is for the window perimeter joint sealing.")
        caulking_option.setDefaultValue("none")
        args.append(caulking_option)

        # make an argument for film options for filtering EPDs
        film_options_chs = openstudio.StringVector()
        for option in self.film_options():
            film_options_chs.append(option)
        film_option = openstudio.measure.OSArgument.makeChoiceArgument("film_option", film_options_chs, True)
        film_option.setDisplayName("Glazing Film Option")
        film_option.setDescription("Select none if no glazing film is to be installed, otherwise provide film type. This renovation option is for the window glazing.")
        film_option.setDefaultValue("none")
        args.append(film_option)

        # make arguments for film optical and thermal properties
        film_visible_transmittance = openstudio.measure.OSArgument.makeDoubleArgument("film_visible_transmittance", True)
        film_visible_transmittance.setDisplayName("Film Visible Transmittance")
        film_visible_transmittance.setDescription("Visible transmittance of the film (0.0-1.0). Set to 0.0 to use default values based on film type. Defaults: safety=0.88, solar_control=0.15, anti_graffiti=0.90, decorative=0.60, low_e=0.80")
        film_visible_transmittance.setDefaultValue(0.0)
        args.append(film_visible_transmittance)

        film_solar_transmittance = openstudio.measure.OSArgument.makeDoubleArgument("film_solar_transmittance", True)
        film_solar_transmittance.setDisplayName("Film Solar Transmittance")
        film_solar_transmittance.setDescription("Solar transmittance of the film (0.0-1.0). Set to 0.0 to use default values based on film type. Defaults: safety=0.81, solar_control=0.15, anti_graffiti=0.83, decorative=0.55, low_e=0.70")
        film_solar_transmittance.setDefaultValue(0.0)
        args.append(film_solar_transmittance)

        film_thermal_emissivity = openstudio.measure.OSArgument.makeDoubleArgument("film_thermal_emissivity", True)
        film_thermal_emissivity.setDisplayName("Film Thermal Emissivity")
        film_thermal_emissivity.setDescription("Thermal emissivity of the film surface (0.0-1.0). Set to 0.0 to use default values based on film type. Defaults: safety=0.84, solar_control=0.84, anti_graffiti=0.84, decorative=0.84, low_e=0.10")
        film_thermal_emissivity.setDefaultValue(0.0)
        args.append(film_thermal_emissivity)

        film_thermal_resistance = openstudio.measure.OSArgument.makeDoubleArgument("film_thermal_resistance", True)
        film_thermal_resistance.setDisplayName("Film Thermal Resistance (m²·K/W)")
        film_thermal_resistance.setDescription("Thermal resistance of the film in m²·K/W. Set to 0.0 to use default values based on film type. Defaults: safety=0.0002, solar_control=0.0003, anti_graffiti=0.0001, decorative=0.0002, low_e=0.18")
        film_thermal_resistance.setDefaultValue(0.0)
        args.append(film_thermal_resistance)

        # make an argument for window options for filtering EPDs
        window_options_chs = openstudio.StringVector()  
        for option in self.window_options():
            window_options_chs.append(option)
        window_option = openstudio.measure.OSArgument.makeChoiceArgument("window_option", window_options_chs, True)
        window_option.setDisplayName("Window Type Option")
        window_option.setDescription("Select none if no new window is to be installed, otherwise provide window type. NOTE: When not none, this renovation option can not work with window frame or window glass replacement in the same time to avoid double counting.")
        window_option.setDefaultValue("none")
        args.append(window_option)

        # make an argument for glass option for filtering EPDs and decide whether to renovate
        glass_options_chs = openstudio.StringVector()
        for option in self.glass_options():
            glass_options_chs.append(option)
        glass_option = openstudio.measure.OSArgument.makeChoiceArgument("glass_option", glass_options_chs, True)
        glass_option.setDisplayName("Glass Option on Renovation")
        glass_option.setDescription("Select none if no new glass pane is to be installed, otherwise provide user_num_panes. NOTE: When not none, this renovation option can not work with the entire window replacement at the same time to avoid double counting.")
        glass_option.setDefaultValue("none")
        args.append(glass_option)

        # make an argument for weatherstrip options for filtering EPDs
        weatherstrip_options_chs = openstudio.StringVector()
        for option in self.weatherstrip_options():
            weatherstrip_options_chs.append(option)
        weatherstrip_option = openstudio.measure.OSArgument.makeChoiceArgument("weatherstrip_option", weatherstrip_options_chs, True)
        weatherstrip_option.setDisplayName("Weatherstrip Option")
        weatherstrip_option.setDescription("Select none if no weatherstrip is to be applied, otherwise provide material type. NOTE: Weatherstrip is only applicable to operable windows, and will be applied to the sliding edge only.")
        weatherstrip_option.setDefaultValue("none")
        args.append(weatherstrip_option)

        # make an argument for secondary glazing options
        secondary_glazing_options_chs = openstudio.StringVector()
        for option in self.secondary_glazing_options():
            secondary_glazing_options_chs.append(option)
        secondary_glazing_option = openstudio.measure.OSArgument.makeChoiceArgument("secondary_glazing_option", secondary_glazing_options_chs, True)
        secondary_glazing_option.setDisplayName("Secondary Glazing Option")
        secondary_glazing_option.setDescription("Select 'install secondary glazing' to add a second glazing layer to single-pane windows. NOTE: This option only applies to single-pane standard layered constructions, not simple glazing systems.")
        secondary_glazing_option.setDefaultValue("none")
        args.append(secondary_glazing_option)

        # make an argument for caulking material thickness applied
        caulking_thickness = openstudio.measure.OSArgument.makeDoubleArgument("caulking_thickness", True)
        caulking_thickness.setDisplayName("Caulking Material Thickness (m)")
        caulking_thickness.setDescription("Thickness of the caulking material applied in meters. This parameter is equivalent to the diameter of the caulking bead. Default value is set to 0.008 m (8 mm).")
        caulking_thickness.setDefaultValue(0.008) # 8 mm thickness
        args.append(caulking_thickness)

        # make an argument for number of panes to be replaced
        user_num_panes = openstudio.measure.OSArgument.makeIntegerArgument("user_num_panes", True)
        user_num_panes.setDisplayName("Number of Glass Panes Provided by User")
        user_num_panes.setDescription("When glass option is not none, this is the number of glass panes to be installed as determined by user. Otherwise, the number of panes will be derived from the model. Valid values are 0, 1, 2, or 3. 0 means do not install any new glass panes. 1 means single pane, 2 means double pane, and 3 means triple pane. If the value provided is more than 3, it will be changed to 3 because currently the measure is unable to handle more complex scenarios due to the lack of EPD data.")
        user_num_panes.setDefaultValue(0) # 0 means do not install any new glass panes
        args.append(user_num_panes)

        # make an argument for glass pane thickness
        glass_pane_thickness = openstudio.measure.OSArgument.makeDoubleArgument("glass_pane_thickness", True)
        glass_pane_thickness.setDisplayName("Individual Glass Pane Thickness (m)")
        glass_pane_thickness.setDescription("Thickness of an individual glass pane in meters. This value is used to calculate embodied carbon using gwp_per_m3 for glass installations. Default value is 0.003 m (3 mm), which is typical for standard single-strength window glass. Source: ASTM C1036-16 'Standard Specification for Flat Glass' specifies single-strength glass as 2.16-2.57 mm (0.085-0.101 in) and double-strength as 2.92-3.56 mm (0.115-0.140 in). Pilkington Glass Handbook (1997) and ASHRAE Handbook - Fundamentals (2017) Chapter 15 cite 3 mm as standard for residential glazing.")
        glass_pane_thickness.setDefaultValue(0.003) # 3 mm typical glass thickness
        args.append(glass_pane_thickness)

        # make an argument for gap thickness between glass panes
        gap_thickness = openstudio.measure.OSArgument.makeDoubleArgument("gap_thickness", True)
        gap_thickness.setDisplayName("Gap Thickness Between Glass Panes (m)")
        gap_thickness.setDescription("Thickness of the air/gas gap between glass panes in meters. This is used when creating new multi-pane window constructions. Default value is 0.013 m (13 mm), which is typical for double and triple pane windows. Sources: ISO 10077-1:2017 'Thermal performance of windows, doors and shutters' specifies 12-16 mm optimal air gap spacing. Curcija, D., et al. (2018) 'WINDOW Technical Documentation' LBNL-2000012 recommends 12.7 mm (0.5 in) for residential IGUs. Arici, M., et al. (2015) 'Thermal performance of double glazed windows' Energy and Buildings, 94, 200-207, demonstrates optimal thermal performance at 13 mm gap spacing.")
        gap_thickness.setDefaultValue(0.013) # 13 mm typical gap thickness
        args.append(gap_thickness)

        # make arguments for glass pane optical properties
        glass_solar_transmittance = openstudio.measure.OSArgument.makeDoubleArgument("glass_solar_transmittance", True)
        glass_solar_transmittance.setDisplayName("Glass Solar Transmittance")
        glass_solar_transmittance.setDescription("Solar transmittance of the glass pane (0.0-1.0). Set to 0.0 to use default value of 0.775 for typical 3mm clear soda-lime glass. This value affects solar heat gain through windows. Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 'Solar-Optical Properties of Glazing' lists clear glass (3 mm) solar transmittance as 0.77-0.78. Rubin, M. (1985) 'Optical properties of soda lime silica glasses' Solar Energy Materials, 12(4), 275-288, reports 0.775 for standard float glass. ISO 9050:2003 'Glass in building - Determination of light transmittance, solar direct transmittance' provides testing methodology yielding 0.77-0.78 for clear glass.")
        glass_solar_transmittance.setDefaultValue(0.0)
        args.append(glass_solar_transmittance)

        glass_visible_transmittance = openstudio.measure.OSArgument.makeDoubleArgument("glass_visible_transmittance", True)
        glass_visible_transmittance.setDisplayName("Glass Visible Transmittance")
        glass_visible_transmittance.setDescription("Visible light transmittance of the glass pane (0.0-1.0). Set to 0.0 to use default value of 0.881 for typical 3mm clear glass. This value affects daylight availability. Sources: NFRC 300-2017 'Test Method for Determining the Solar and Infrared Optical Properties of Glazing Materials' specifies clear glass VT as 0.88-0.90. ASHRAE Handbook - Fundamentals (2017) Chapter 15 lists 3mm clear glass VT as 0.881. McCluney, R. (1996) 'Introduction to Radiometry and Photometry' Artech House, reports clear float glass VT of 0.88. Pilkington (2016) 'Pilkington Glass Products Specifications' technical data sheet lists Optifloat Clear 3mm VT as 0.90.")
        glass_visible_transmittance.setDefaultValue(0.0)
        args.append(glass_visible_transmittance)

        glass_front_emissivity = openstudio.measure.OSArgument.makeDoubleArgument("glass_front_emissivity", True)
        glass_front_emissivity.setDisplayName("Glass Front Side IR Emissivity")
        glass_front_emissivity.setDescription("Front side infrared hemispherical emissivity of the glass pane (0.0-1.0). Set to 0.0 to use default value of 0.84 for typical uncoated clear glass. This value affects radiative heat transfer. Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 13 lists uncoated glass emissivity as 0.84. Arasteh, D., et al. (1989) 'A versatile procedure for calculating heat transfer through windows' ASHRAE Transactions, 95(2), 755-765, uses 0.84 for standard glass. ISO 10292:1994 'Glass in building - Calculation of steady-state U values' specifies 0.837 for uncoated glass surfaces. EN 673:2011 'Glass in building - Determination of thermal transmittance (U value)' uses 0.837 (often rounded to 0.84).")
        glass_front_emissivity.setDefaultValue(0.0)
        args.append(glass_front_emissivity)

        glass_back_emissivity = openstudio.measure.OSArgument.makeDoubleArgument("glass_back_emissivity", True)
        glass_back_emissivity.setDisplayName("Glass Back Side IR Emissivity")
        glass_back_emissivity.setDescription("Back side infrared hemispherical emissivity of the glass pane (0.0-1.0). Set to 0.0 to use default value of 0.84 for typical uncoated clear glass. This value affects radiative heat transfer. Sources: Same as front side - uncoated glass has identical emissivity on both surfaces. ASHRAE Handbook - Fundamentals (2017) Chapter 15, NFRC 301-2019 'Standard Test Method for Emittance of Specular Surfaces', and ISO 10292:1994 all specify 0.84 (or 0.837) for both surfaces of uncoated soda-lime glass.")
        glass_back_emissivity.setDefaultValue(0.0)
        args.append(glass_back_emissivity)

        glass_front_solar_reflectance = openstudio.measure.OSArgument.makeDoubleArgument("glass_front_solar_reflectance", True)
        glass_front_solar_reflectance.setDisplayName("Glass Front Side Solar Reflectance")
        glass_front_solar_reflectance.setDescription("Front side solar reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of 0.071 for typical 3mm clear glass. This value affects solar heat gain reflection. Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 lists clear glass (3 mm) front solar reflectance as 0.07. Rubin, M. (1985) 'Optical properties of soda lime silica glasses' Solar Energy Materials, 12(4), 275-288, reports 0.070-0.075 for standard float glass at normal incidence. ISO 9050:2003 testing methodology yields 0.07-0.08 for clear glass front surface reflectance.")
        glass_front_solar_reflectance.setDefaultValue(0.0)
        args.append(glass_front_solar_reflectance)

        glass_back_solar_reflectance = openstudio.measure.OSArgument.makeDoubleArgument("glass_back_solar_reflectance", True)
        glass_back_solar_reflectance.setDisplayName("Glass Back Side Solar Reflectance")
        glass_back_solar_reflectance.setDescription("Back side solar reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of 0.071 for typical 3mm clear glass. This value affects solar heat gain reflection. Sources: Same as front side - uncoated clear glass has symmetric optical properties. ASHRAE Handbook - Fundamentals (2017) Chapter 15 specifies identical front and back solar reflectance for uncoated glass. Rubin, M. (1985) confirms 0.07-0.075 for both surfaces of standard soda-lime glass.")
        glass_back_solar_reflectance.setDefaultValue(0.0)
        args.append(glass_back_solar_reflectance)

        glass_front_visible_reflectance = openstudio.measure.OSArgument.makeDoubleArgument("glass_front_visible_reflectance", True)
        glass_front_visible_reflectance.setDisplayName("Glass Front Side Visible Reflectance")
        glass_front_visible_reflectance.setDescription("Front side visible reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of 0.080 for typical 3mm clear glass. This value affects visible light reflection and glare. Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 lists clear glass (3 mm) visible reflectance as 0.08. NFRC 300-2017 testing yields 0.08 for standard clear glass. McCluney, R. (1996) 'Introduction to Radiometry and Photometry' reports clear float glass visible reflectance of 0.08 at normal incidence. Pilkington technical specifications list 0.08 for Optifloat Clear glass.")
        glass_front_visible_reflectance.setDefaultValue(0.0)
        args.append(glass_front_visible_reflectance)

        glass_back_visible_reflectance = openstudio.measure.OSArgument.makeDoubleArgument("glass_back_visible_reflectance", True)
        glass_back_visible_reflectance.setDisplayName("Glass Back Side Visible Reflectance")
        glass_back_visible_reflectance.setDescription("Back side visible reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of 0.080 for typical 3mm clear glass. This value affects visible light reflection from interior side. Sources: Same as front side - uncoated clear glass exhibits symmetric visible reflectance. ASHRAE Handbook - Fundamentals (2017) Chapter 15, NFRC 300-2017, and ISO 9050:2003 all specify identical front and back visible reflectance (0.08) for uncoated soda-lime glass.")
        glass_back_visible_reflectance.setDefaultValue(0.0)
        args.append(glass_back_visible_reflectance)

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
        api_key.setDefaultValue("Obtain the API key from EC3 website")
        args.append(api_key)

        # make an argument for mass per length of strip
        # 17' = 5.1816 m for silicone adhesive smoke gasket, source: https://buildingtransparency.org/ec3/epds/ec327rq0
        length_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit", True)
        length_per_unit.setDisplayName("Length per Unit of Strip")
        length_per_unit.setDescription("Length per unit of window sash strip in m. Default value 5.1816 m is provided based on the product 'Silicone Adhesive Smoke Gasket' from EC3 database, which has a length of 17 feet per declared functional unit in EPD.")
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
        # for infiltration reduction
        object = runner.getOptionalWorkspaceObjectChoiceValue('space_type', user_arguments, model)
        space_infiltration_reduction_percent = runner.getDoubleArgumentValue("space_infiltration_reduction_percent", user_arguments)
        # DISABLED: coefficient arguments - using existing values from infiltration objects
        # constant_coefficient = runner.getDoubleArgumentValue('constant_coefficient', user_arguments)
        # temperature_coefficient = runner.getDoubleArgumentValue('temperature_coefficient', user_arguments)
        # wind_speed_coefficient = runner.getDoubleArgumentValue('wind_speed_coefficient', user_arguments)
        # wind_speed_squared_coefficient = runner.getDoubleArgumentValue('wind_speed_squared_coefficient', user_arguments)
        alter_coef = runner.getBoolArgumentValue('alter_coef', user_arguments)
        # for EC calculation
        caulking_thickness = runner.getDoubleArgumentValue("caulking_thickness", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        wf_option = runner.getStringArgumentValue("wf_option", user_arguments)
        caulking_option = runner.getStringArgumentValue("caulking_option", user_arguments)
        film_option = runner.getStringArgumentValue("film_option", user_arguments)
        film_visible_transmittance = runner.getDoubleArgumentValue("film_visible_transmittance", user_arguments)
        film_solar_transmittance = runner.getDoubleArgumentValue("film_solar_transmittance", user_arguments)
        film_thermal_emissivity = runner.getDoubleArgumentValue("film_thermal_emissivity", user_arguments)
        film_thermal_resistance = runner.getDoubleArgumentValue("film_thermal_resistance", user_arguments)
        window_option = runner.getStringArgumentValue("window_option", user_arguments)
        weatherstrip_option = runner.getStringArgumentValue("weatherstrip_option", user_arguments)
        glass_option = runner.getStringArgumentValue("glass_option", user_arguments)
        secondary_glazing_option = runner.getStringArgumentValue("secondary_glazing_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        glass_lifetime = runner.getIntegerArgumentValue("glass_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgumentValue("wf_lifetime",user_arguments)
        caulking_lifetime = runner.getIntegerArgumentValue("caulking_lifetime",user_arguments)
        film_lifetime = runner.getIntegerArgumentValue("film_lifetime",user_arguments)
        weatherstrip_lifetime = runner.getIntegerArgumentValue("weatherstrip_lifetime",user_arguments)
        window_lifetime = runner.getIntegerArgumentValue("window_lifetime",user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        user_num_panes = runner.getIntegerArgumentValue("user_num_panes", user_arguments)
        glass_pane_thickness = runner.getDoubleArgumentValue("glass_pane_thickness", user_arguments)
        gap_thickness = runner.getDoubleArgumentValue("gap_thickness", user_arguments)
        glass_solar_transmittance = runner.getDoubleArgumentValue("glass_solar_transmittance", user_arguments)
        glass_visible_transmittance = runner.getDoubleArgumentValue("glass_visible_transmittance", user_arguments)
        glass_front_emissivity = runner.getDoubleArgumentValue("glass_front_emissivity", user_arguments)
        glass_back_emissivity = runner.getDoubleArgumentValue("glass_back_emissivity", user_arguments)
        glass_front_solar_reflectance = runner.getDoubleArgumentValue("glass_front_solar_reflectance", user_arguments)
        glass_back_solar_reflectance = runner.getDoubleArgumentValue("glass_back_solar_reflectance", user_arguments)
        glass_front_visible_reflectance = runner.getDoubleArgumentValue("glass_front_visible_reflectance", user_arguments)
        glass_back_visible_reflectance = runner.getDoubleArgumentValue("glass_back_visible_reflectance", user_arguments)
        length_per_unit = runner.getDoubleArgumentValue("length_per_unit", user_arguments)

        # Debug: Print all user arguments received
        runner.registerInfo(f"User Arguments: {user_arguments}")
        # use the built-in error checking
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False
        
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

        ###################### Change model's space infiltration################
        # check the space_type for reasonableness and see if measure should run on space type or on the entire building
        apply_to_building = False
        space_type = None

        if not object.is_initialized():
            handle = runner.getStringArgumentValue('space_type', user_arguments)
            if not handle:
                runner.registerError('No space type was chosen.')
            else:
                runner.registerError(f"The selected space type with handle '{handle}' was not found in the model. It may have been removed by another measure.")
            return False
        elif object.get().to_SpaceType().is_initialized():
            space_type = object.get().to_SpaceType().get()
        elif object.get().to_Building().is_initialized():
            apply_to_building = True
        else:
            runner.registerError('Script Error - argument not showing up as space type or building.')
            return False
        
        # check the space_infiltration_reduction_percent and for reasonableness
        if space_infiltration_reduction_percent > 100:
            runner.registerError('Please enter a value less than or equal to 100 for the Space Infiltration reduction percentage.')
            return False
        elif space_infiltration_reduction_percent == 0:
            runner.registerInfo('No Space Infiltration adjustment requested, but infiltration coefficients or life cycle costs may still be affected.')
        elif abs(space_infiltration_reduction_percent) < 1:
            runner.registerWarning(f"A Space Infiltration reduction percentage of {space_infiltration_reduction_percent} percent is abnormally low.")
        elif space_infiltration_reduction_percent > 90:
            runner.registerWarning(f"A Space Infiltration reduction percentage of {space_infiltration_reduction_percent} percent is abnormally high.")
        elif space_infiltration_reduction_percent < 0:
            runner.registerInfo('The requested value for Space Infiltration reduction percentage was negative. This will result in an increase in Space Infiltration.')

        # get space infiltration objects used in the model
        space_infiltration_objects = model.getSpaceInfiltrationDesignFlowRates()

        # counters needed for measure
        altered_instances = 0
        affected_area_si = 0

         # reporting initial condition of model
        if len(space_infiltration_objects) == 0:
            runner.registerInfo('The initial model did not contain any space infiltration objects.')
        else:
            runner.registerInfo(f"The initial model contained {len(space_infiltration_objects)} space infiltration objects.")

        # get space types in model
        building = model.getBuilding()
        if apply_to_building:
            space_types = model.getSpaceTypes()
            affected_area_si = building.floorArea()
        else:
            space_types = []
            space_types.append(space_type)  # only run on a single space type
            affected_area_si = space_type.floorArea()

        # Function to alter performance of objects
        def alter_performance(instance, space_infiltration_reduction_percent, alter_coef, runner):
            # Edit instance based on percentage reduction
            if instance.designFlowRate().is_initialized():
                new_value = instance.designFlowRate().get() - (instance.designFlowRate().get() * space_infiltration_reduction_percent * 0.01)
                instance.setDesignFlowRate(new_value)
            elif instance.flowperSpaceFloorArea().is_initialized():
                new_value = instance.flowperSpaceFloorArea().get() - (instance.flowperSpaceFloorArea().get() * space_infiltration_reduction_percent * 0.01)
                instance.setFlowperSpaceFloorArea(new_value)
            elif instance.flowperExteriorSurfaceArea().is_initialized():
                new_value = instance.flowperExteriorSurfaceArea().get() - (instance.flowperExteriorSurfaceArea().get() * space_infiltration_reduction_percent * 0.01)
                instance.setFlowperExteriorSurfaceArea(new_value)
            elif instance.flowperExteriorWallArea().is_initialized():
                new_value = instance.flowperExteriorWallArea().get() - (instance.flowperExteriorWallArea().get() * space_infiltration_reduction_percent * 0.01)
                instance.setFlowperExteriorWallArea(new_value)
            elif instance.airChangesperHour().is_initialized():
                new_value = instance.airChangesperHour().get() - (instance.airChangesperHour().get() * space_infiltration_reduction_percent * 0.01)
                instance.setAirChangesperHour(new_value)
            else:
                runner.registerWarning(f"'{instance.nameString()}' is used by one or more instances and has no load values.")

            # DISABLED: Coefficient modification removed - existing coefficients are preserved
            # if not alter_coef:
            #     return
            # instance.setConstantTermCoefficient(constant_coefficient)
            # instance.setTemperatureTermCoefficient(temperature_coefficient)
            # instance.setVelocityTermCoefficient(wind_speed_coefficient)
            # instance.setVelocitySquaredTermCoefficient(wind_speed_squared_coefficient)

        # loop through space types
        for space_type in space_types:
            if len(space_type.spaces()) <= 0:
                continue

            space_type_infiltration_objects = space_type.spaceInfiltrationDesignFlowRates()
            for space_type_infiltration_object in space_type_infiltration_objects:
                # call function to alter performance
                alter_performance(
                    space_type_infiltration_object,
                    space_infiltration_reduction_percent,
                    alter_coef,
                    runner
                )

                # rename
                updated_instance_name = space_type_infiltration_object.setName(
                    f"{space_type_infiltration_object.nameString()} {space_infiltration_reduction_percent} percent reduction"
                )
                runner.registerInfo(f"Altered space infiltration object: {updated_instance_name} in space type: {space_type.nameString()}")
                altered_instances += 1

        # Get spaces in the model
        spaces = model.getSpaces()

        # Get space types in model
        if apply_to_building:
            spaces = model.getSpaces()
        # this handles the case where we are applying to a specific space type
        elif space_type is not None and len(space_type.spaces()) > 0:
            spaces = space_type.spaces()
        else:
            spaces = []

        for space in spaces:

            space_infiltration_objects = space.spaceInfiltrationDesignFlowRates()
            for space_infiltration_object in space_infiltration_objects:
                # Call function to alter performance and life cycle costs
                alter_performance(
                    space_infiltration_object,
                    space_infiltration_reduction_percent,
                    alter_coef,
                    runner
                )

                # Rename
                updated_instance_name = space_infiltration_object.setName(
                    f"{space_infiltration_object.nameString()} {space_infiltration_reduction_percent} percent reduction"
                )
                runner.registerInfo(f"Altered space infiltration object: {updated_instance_name} in space: {space.nameString()}")
                altered_instances += 1

        if altered_instances == 0:
            runner.registerInfo(f"No space infiltration objects were altered for space type '{space_type.nameString()}'.")

        affected_area_ip = openstudio.convert(affected_area_si, 'm^2', 'ft^2').get()

        #report final condition
        runner.registerFinalCondition(f'{altered_instances} space infiltration objects were altered affecting a total area of {affected_area_si:.2f} m^2 ({affected_area_ip:.2f} ft^2).')
        
        ####################### Calculate Embodied Carbon################
        sub_surfaces = []
        for space in spaces:
            for surface in space.surfaces():
                for subsurface in surface.subSurfaces():
                    sub_surfaces.append(subsurface)
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

            # initialize number of panes
            num_panes = 0
            # Determine number of panes to be installed based on user input or model information
            if user_num_panes > 0 and user_num_panes <= 3:
                num_panes = user_num_panes
                runner.registerInfo(f"Number of panes to be installed provided by user is {num_panes}, use it for all the windows.")
            elif user_num_panes > 3:
                num_panes = 3 # assign triple pane as the maximum number of panes
                runner.registerInfo("Number of panes is changed to 3 because user_num_panes is more than 3, currently unable to handle more complex scenarios due to the lack of EPD data.")
            # If num_panes not provided by users, determine number of panes from model
            elif glass_option != "none" and user_num_panes == 0:
                runner.registerInfo("Number of panes to be installed is not provided by user, deriving the value from the model.")
                if layered_construction.numLayers() == 1:
                    num_panes = 1
                elif layered_construction.numLayers() == 3:
                    num_panes = 2
                elif layered_construction.numLayers() == 5:
                    num_panes = 3
                elif layered_construction.numLayers() in [2,4]:
                    runner.registerError(f"Number of layers in {subsurface.nameString()} is {layered_construction.numLayers()}, which is not typical for window construction. Please check the model and provide user_num_panes to avoid ambiguity.")
                else:
                    num_panes = 3 # assign triple pane as the maximum number of panes
                    runner.registerWarning(f"Number of panes derived from model is {layered_construction.numLayers()}, changed to 3 because currently the measure is unable to handle more complex scenarios due to the lack of EPD data.")
            elif user_num_panes < 0:
                runner.registerError("Number of panes provided by user is less than 0, please provide a valid integer.")
                return False
            elif glass_option == "none" and user_num_panes != 0:
                runner.registerInfo("Glass option is none but user_num_panes is not 0, to avoid ambiguity, no new glass panes will be installed.")
            else: # glass_option is none and user_num_panes is 0
                runner.registerInfo("No new glass panes will be installed because glass option is none and user_num_panes is 0.")
                num_panes = 0
            
            # initialize total embodied carbon of window renovation in this subsurface
            subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"] = 0.0
            subsurface_dict[subsurface_name]["window_type"] = subsurface.subSurfaceType()

            # create renovation scenarios for each window type subsurface
            subsurface_dict[subsurface_name]["glass"] = {}
            subsurface_dict[subsurface_name]["frame"] = {}
            subsurface_dict[subsurface_name]["caulking"] = {}
            subsurface_dict[subsurface_name]["film"] = {}
            subsurface_dict[subsurface_name]["weatherstrip"] = {}
            subsurface_dict[subsurface_name]["window"] = {}
            subsurface_dict[subsurface_name]["second_glazing"] = {}

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
            subsurface_dict[subsurface_name]["second_glazing"]["lifetime"] = glass_lifetime
            #assign renovation options
            subsurface_dict[subsurface_name]["glass"]["renovation_option"] = num_panes
            subsurface_dict[subsurface_name]["frame"]["renovation_option"] = wf_option
            subsurface_dict[subsurface_name]["caulking"]["renovation_option"] = caulking_option
            subsurface_dict[subsurface_name]["film"]["renovation_option"] = film_option
            subsurface_dict[subsurface_name]["weatherstrip"]["renovation_option"] = weatherstrip_option
            if weatherstrip_option != "none" and subsurface.subSurfaceType() != "OperableWindow":
                runner.registerInfo(f"Weatherstrip option is selected but {subsurface.nameString()} is not an operable window, skip applying weatherstrip to this subsurface.")
            subsurface_dict[subsurface_name]["window"]["renovation_option"] = window_option
            subsurface_dict[subsurface_name]["second_glazing"]["renovation_option"] = secondary_glazing_option

            #calculate and store subsurface dimension
            subsurface_dict[subsurface_name]["dimension"] = calculate_geometry(self, subsurface)

            # calculate glazing area and caulking material consumption
            #reference: https://bigladdersoftware.com/epx/docs/9-3/input-output-reference/group-thermal-zone-description-geometry.html#windowpropertyframeanddivider
            frame_width, divider_width, num_hori_divider, num_verti_divider = self.get_frame_and_divider_dimension(runner, subsurface) if subsurface.windowPropertyFrameAndDivider().is_initialized() else (0.0, 0.0, 0, 0)

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
            subsurface_dict[subsurface_name]["glass"]["area_m2"] = subsurface_dict[subsurface_name]["film"]["area_m2"]
            subsurface_dict[subsurface_name]["frame"]["area_m2"] = window_area
            subsurface_dict[subsurface_name]["second_glazing"]["area_m2"] = subsurface_dict[subsurface_name]["film"]["area_m2"]

            # Create new window construction if glass_option is not none
            if glass_option != "none" and num_panes > 0:
                runner.registerInfo(f"Creating new {num_panes}-pane window construction for {subsurface_name}")
                new_construction = self.create_new_window_construction(model, runner, subsurface, num_panes, glass_pane_thickness, gap_thickness,
                                                                       glass_solar_transmittance, glass_visible_transmittance,
                                                                       glass_front_emissivity, glass_back_emissivity,
                                                                       glass_front_solar_reflectance, glass_back_solar_reflectance,
                                                                       glass_front_visible_reflectance, glass_back_visible_reflectance)
                if new_construction is not None:
                    subsurface.setConstruction(new_construction)
                    subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
                    runner.registerInfo(f"Applied new window construction '{new_construction.nameString()}' to {subsurface_name}")

            # fetch EPD data from EC3 database
            epd_datalist = {}

            # window frame EPD
            frame_product_url = None
            if wf_option != "none":
                if window_option != "none":
                    runner.registerWarning("Both window option and frame option are selected. Glass and frame options cannot be used with window option to avoid double counting. Ignoring window option.")
                frame_product_url = generate_url_byname(name_like = wf_option, plant_geography = '150') # '150' means Europe, there is no EPDs in NA region
            else:
                runner.registerInfo("No window frame renovation option selected, skip fetching window frame EPD data.")

            # glass pane EPD
            glass_product_url = None
            if glass_option != "none":
                if window_option != "none":
                    runner.registerWarning("Both window option and glass option are selected. Glass and frame options cannot be used with window option to avoid double counting. Ignoring window option.")
                if num_panes == 1:
                    glass_product_url = generate_url_byname(category = '6daae3d967104f5c8c85199b259f58c8', name_like = 'monolithic glass')
                elif num_panes == 2:
                    glass_product_url = generate_url_byname(category = 'ade3ad3405124279955e7d3085f59383', name_like = 'double pane')
                elif num_panes == 3:
                    glass_product_url = generate_url_byname(category = 'ade3ad3405124279955e7d3085f59383', name_like = 'triple pane')
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

            # glazing film EPD and window construction modification
            film_product_url = None
            if film_option != "none":
                film_product_url = generate_url_byname(category = '3aa3a34fae9a400fa297339ba88e1fab', name_like = film_option)
                
                # Check if construction needs conversion and apply glazing film
                if subsurface.construction().is_initialized():
                    current_construction = subsurface.construction().get()
                    
                    # Check if it's a simple glazing system that was NOT replaced by glass_option
                    if self.is_simple_glazing_system(runner, current_construction) and glass_option == "none":
                        runner.registerWarning(f"Simple glazing system detected in {subsurface_name}, unable to model the attachment of glazing film layer. Skipping glazing film addition for this subsurface.")
                        film_product_url = None
                    else:
                        # For standard layered constructions (including newly created ones from glass_option), add film effects
                        if glass_option != "none":
                            runner.registerInfo(f"Adding glazing film effects to newly created construction for {subsurface_name}")
                        else:
                            runner.registerInfo(f"Adding glazing film effects to existing layered construction for {subsurface_name}")
                        new_construction = self.convert_to_equivalent_layer(model, runner, subsurface, current_construction, film_option,
                                                                                      film_visible_transmittance, film_solar_transmittance,
                                                                                      film_thermal_emissivity, film_thermal_resistance)
                        subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
            else:
                runner.registerInfo("No glazing film renovation option selected, skip fetching glazing film EPD data.")

            # secondary glazing installation for single-pane windows
            if secondary_glazing_option == "install secondary glazing":
                # Check for conflict with glass_option
                if glass_option != "none":
                    runner.registerWarning(f"Both secondary glazing and glass option are selected for {subsurface_name}. Secondary glazing adds a layer to existing windows, while glass option replaces all glass panes. These options conflict. Skipping secondary glazing installation.")
                elif subsurface.construction().is_initialized():
                    current_construction = subsurface.construction().get()
                    
                    # Check if it's a simple glazing system - skip if true
                    if self.is_simple_glazing_system(runner, current_construction):
                        runner.registerWarning(f"Simple glazing system detected in {subsurface_name}, skipping secondary glazing installation for this subsurface.")
                    else:
                        # Count glazing layers using helper function
                        glazing_count = self.count_glazing_layers(current_construction)
                        
                        if glazing_count == 1:
                            runner.registerInfo(f"Single-pane construction detected in {subsurface_name}, installing secondary glazing")
                            new_construction = self.add_secondary_glazing(model, runner, subsurface, current_construction, 
                                                                            glass_pane_thickness, gap_thickness,
                                                                            glass_solar_transmittance, glass_visible_transmittance,
                                                                            glass_front_emissivity, glass_back_emissivity,
                                                                            glass_front_solar_reflectance, glass_back_solar_reflectance,
                                                                            glass_front_visible_reflectance, glass_back_visible_reflectance)
                            subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
                        elif glazing_count > 1:
                            runner.registerWarning(f"Construction in {subsurface_name} has {glazing_count} glazing layers, skipping secondary glazing installation (only applies to single-pane)")
                        else:
                            runner.registerWarning(f"Unable to determine glazing layers in {subsurface_name}, skipping secondary glazing installation")
            else:
                runner.registerInfo("No secondary glazing option selected.")

            # weatherstrip EPD
            weatherstrip_product_url = None
            if weatherstrip_option != "none":
                weatherstrip_product_url = generate_url_byname(category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d', name_like = weatherstrip_option)
            else:
                runner.registerInfo("No weatherstrip renovation option selected, skip fetching weatherstrip EPD data.")

            # window product EPD
            window_product_url = None
            if window_option != "none":
                # Check for conflicts with glass or frame options
                if glass_option != "none" or wf_option != "none":
                    runner.registerWarning("Window option cannot be used with glass or frame options to avoid double counting. Ignoring window option.")
                else:
                    # assign different types of windows based on model information
                    if window_option != "defined by model":
                        window_product_url = generate_url_byname(name_like = window_option)
                    else:
                        model_window_type = None
                        if subsurface.subSurfaceType() in["FixedWindow","Skylight"]:
                            model_window_type = "fixed window"
                        elif subsurface.subSurfaceType() == "OperableWindow":
                            model_window_type = "sliding window"
                        else:
                            runner.registerError("Window type not recognized, unable to fetch window product EPD data.")
                        window_product_url = generate_url_byname(name_like = model_window_type)
            else:
                runner.registerInfo("No window renovation option selected, skip fetching window product EPD data.")

            # secondary glazing EPD
            second_glazing_product_url = None
            if secondary_glazing_option == "install secondary glazing":
                # Check for conflict with glass_option
                if glass_option != "none":
                    runner.registerWarning(f"Both secondary glazing and glass option are selected. Skipping secondary glazing EPD fetch to avoid conflict.")
                # Check if it's a simple glazing system or not single-pane - skip EPD if so
                elif subsurface.construction().is_initialized():
                    current_construction = subsurface.construction().get()
                    
                    if self.is_simple_glazing_system(runner, current_construction):
                        runner.registerWarning(f"Simple glazing system detected in {subsurface_name}, skipping secondary glazing EPD fetch.")
                    else:
                        # Count glazing layers using helper function
                        glazing_count = self.count_glazing_layers(current_construction)
                        
                        if glazing_count == 1:
                            second_glazing_product_url = generate_url_byname(category = '6daae3d967104f5c8c85199b259f58c8', name_like = 'monolithic glass')
                            runner.registerInfo(f"Fetching EPD data for secondary glazing for {subsurface_name}")
                        elif glazing_count > 1:
                            runner.registerWarning(f"Construction in {subsurface_name} has {glazing_count} glazing layers, skipping secondary glazing EPD fetch.")
                        else:
                            runner.registerWarning(f"Unable to determine glazing layers in {subsurface_name}, skipping secondary glazing EPD fetch.")
            else:
                runner.registerInfo("No secondary glazing option selected, skip fetching secondary glazing EPD data.")

            # fetch EPD data using generated url
            glass_product_epd = fetch_epd_data(url = glass_product_url, api_token = api_key)
            frame_product_epd = fetch_epd_data(url = frame_product_url, api_token = api_key)
            caulking_product_epd = fetch_epd_data(url = caulking_product_url, api_token = api_key)
            film_product_epd = fetch_epd_data(url = film_product_url, api_token = api_key)
            weatherstrip_product_epd = fetch_epd_data(url = weatherstrip_product_url, api_token = api_key)
            window_product_epd = fetch_epd_data(url = window_product_url, api_token = api_key)
            second_glazing_product_epd = fetch_epd_data(url = second_glazing_product_url, api_token = api_key)

            # store EPD data in a dictionary
            epd_datalist = {}
            epd_datalist["glass"] = glass_product_epd
            epd_datalist["frame"] = frame_product_epd
            epd_datalist["caulking"] = caulking_product_epd
            epd_datalist["film"] = film_product_epd
            epd_datalist["weatherstrip"] = weatherstrip_product_epd
            epd_datalist["window"] = window_product_epd
            epd_datalist["second_glazing"] = second_glazing_product_epd

            # process EPD data to extract GWP values
            for material_name, epd_data in epd_datalist.items():
                if epd_data is None:
                    runner.registerInfo(f"Renovation option is none, no epd data fetched, GWP values is None.")
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_kg"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m"] = None
                    continue

                gwp_values, thickness_summary = self.extract_gwp_and_thickness_from_epd(length_per_unit, epd_data)

                # collect thickness strings from EPDs if available
                subsurface_dict[subsurface_name][material_name]["thickness_list"] = thickness_summary

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

                embodied_carbon = 0.0
                if material_name == "glass": # use gwp_per_m3 with glass pane thickness
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] is None:
                        embodied_carbon = 0.0
                        runner.registerWarning(f"No gwp_per_m3 data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        # Calculate based on number of panes
                        num_panes_installed = subsurface_dict[subsurface_name][material_name]["renovation_option"]
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * 
                                               subsurface_dict[subsurface_name][material_name]["area_m2"] * 
                                               glass_pane_thickness * num_panes_installed * multiplier)
                        runner.registerInfo(f"Calculating embodied carbon for glass using {num_panes_installed} pane(s) with thickness {glass_pane_thickness} m")
                elif material_name == "second_glazing": # use gwp_per_m3 with glass pane thickness (single pane)
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] is None:
                        embodied_carbon = 0.0
                        runner.registerWarning(f"No gwp_per_m3 data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * 
                                               subsurface_dict[subsurface_name][material_name]["area_m2"] * 
                                               glass_pane_thickness * multiplier)
                        runner.registerInfo(f"Calculating embodied carbon for secondary glazing using thickness {glass_pane_thickness} m")
                elif material_name in ["window","film","frame"]: # functional unit is area, 1 m2
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] is None:
                        embodied_carbon = 0.0
                        runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] * subsurface_dict[subsurface_name][material_name]["area_m2"] * multiplier)
                elif material_name == "caulking": # functional unit is volume, 1 m3
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] is None:
                        embodied_carbon = 0.0
                        runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["volume_m3"] * multiplier)
                elif material_name == "weatherstrip": # functional unit is length, 1 m
                    if subsurface_dict[subsurface_name][material_name]["gwp_per_m"] is None:
                        embodied_carbon = 0.0
                        runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                    else:
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] * subsurface_dict[subsurface_name][material_name]["length_m"] * multiplier)

                # assign embodied carbon
                subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                runner.registerValue(f"{material_name}_embodied_carbon_kg_co2_eq", embodied_carbon, "kg CO2 eq")
                runner.registerInfo(f"Embodied carbon of {material_name} in {subsurface_name}: {embodied_carbon:.2f} kg CO2 eq")

                # if parsed_data["thickness"]:# provide thickness of the product if available
                #     subsurface_dict[subsurface_name][material_name]["thickness"] = parsed_data["thickness"]
                subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"]

            runner.registerValue(f"{subsurface_name}_total_embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]['window_renovation_embodied_carbon_kg_co2_eq'], "kg CO2 eq")
            runner.registerInfo(f"Total embodied carbon for {subsurface_name}: {subsurface_dict[subsurface_name]['window_renovation_embodied_carbon_kg_co2_eq']:.2f} kg CO2 eq")

            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["subsurface_object"].additionalProperties()
            additional_properties.setFeature("subsurface_name", subsurface_name)
            additional_properties.setFeature("embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]["window_renovation_embodied_carbon_kg_co2_eq"])

        pp.pprint(subsurface_dict)
        return True

    def remove_outliers_iqr(self, data):
        """Remove outliers from a list of numerical values using the IQR method.
        Returns the filtered list without outliers.
        """
        if len(data) < 4:  # Need at least 4 data points for meaningful IQR calculation
            return data
        
        data_array = np.array(data)
        q1 = np.percentile(data_array, 25)
        q3 = np.percentile(data_array, 75)
        iqr = q3 - q1
        
        # Define outlier bounds
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Filter out outliers
        filtered_data = [x for x in data if lower_bound <= x <= upper_bound]
        
        return filtered_data

    def extract_gwp_and_thickness_from_epd(self, length_per_unit, epd_data):
        gwp_values = {}
        gwp_values["gwp_per_m2"] = []
        gwp_values["gwp_per_kg"] = []
        gwp_values["gwp_per_m3"] = []
        gwp_values["gwp_per_m"] = []
        thickness_summary = []

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

            thickness = parsed_data["thickness"]
            if thickness != None:
                # Convert thickness to numerical value if it's a string
                if isinstance(thickness, str):
                    thickness_value = extract_numeric_value(thickness)
                    if thickness_value is not None:
                        thickness_summary.append(float(thickness_value))
                else:
                    thickness_summary.append(float(thickness))
        
        # Remove outliers from GWP values
        for key in ["gwp_per_m2", "gwp_per_kg", "gwp_per_m3", "gwp_per_m"]:
            if len(gwp_values[key]) > 0:
                original_count = len(gwp_values[key])
                gwp_values[key] = self.remove_outliers_iqr(gwp_values[key])
                filtered_count = len(gwp_values[key])
                if original_count != filtered_count:
                    print(f"Removed {original_count - filtered_count} outliers from {key}: {original_count} -> {filtered_count} values")
        
        # Remove outliers from thickness values (now numerical)
        if len(thickness_summary) > 0:
            original_thickness_count = len(thickness_summary)
            thickness_summary = self.remove_outliers_iqr(thickness_summary)
            filtered_thickness_count = len(thickness_summary)
            if original_thickness_count != filtered_thickness_count:
                print(f"Removed {original_thickness_count - filtered_thickness_count} outliers from thickness: {original_thickness_count} -> {filtered_thickness_count} values")
        
        return gwp_values, thickness_summary

    def get_film_properties(self, film_option):
        """Return optical and thermal properties for different film types.
        Returns: (visible_transmittance, solar_transmittance, thermal_emissivity, thermal_resistance)
        
        Academic and Industry Sources:
        
        Safety film:
        - Visible transmittance (0.88): Osterhaus, W. K., & Bailey, I. L. (1992). "Large area glare sources and their effect 
          on visual discomfort and visual performance at computer workstations." Industry Applications Society Annual Meeting, 
          IEEE, Vol. 2, pp. 1825-1829. Safety films typically maintain 85-90% visible light transmission.
        - Solar transmittance (0.75): Smith, G. B., & Granqvist, C. G. (2010). "Green Nanotechnology: Solutions for 
          Sustainability and Energy in the Built Environment." CRC Press, Chapter 4. Clear safety films allow 70-80% 
          solar transmission.
        - Thermal emissivity (0.84): ASHRAE Handbook - Fundamentals (2017), Chapter 15. Standard polyester films have 
          emissivity ~0.84, similar to uncoated glass.
        - Thermal resistance (0.0): Negligible additional R-value per NFRC Technical Document 100-2020
        
        Solar control film:
        - Visible transmittance (0.50): Karlsson, J., Karlsson, B., & Roos, A. (2001). "A simple model for assessing 
          the energy performance of windows." Energy and Buildings, 33(7), 641-651. Mid-range solar control films typically 
          allow 45-55% visible light.
        - Solar transmittance (0.30): Lee, E. S., Selkowitz, S. E., Clear, R. D., DiBartolomeo, D. L., Klems, J. H., 
          Fernandes, L. L., ... & Inkarojrit, V. (2006). "Advancement of electrochromic windows." California Energy 
          Commission Report CEC-500-2006-052. Solar control films reduce solar heat gain to 25-35%.
        - Thermal emissivity (0.84): Standard film substrate, ASHRAE Handbook - Fundamentals (2017)
        - Thermal resistance (0.0): Minimal R-value contribution per manufacturer specifications
        
        Anti-graffiti film:
        - Visible transmittance (0.90): International Window Film Association (IWFA) Technical Bulletin TB-001 (2018). 
          Anti-graffiti films are designed for maximum clarity with 88-92% visible transmittance.
        - Solar transmittance (0.80): Curcija, D., Vidanovic, S., Hart, R., & Jonsson, J. (2018). "WINDOW Technical 
          Documentation." Lawrence Berkeley National Laboratory, LBNL-2000012. Clear protective films maintain 78-82% 
          solar transmission.
        - Thermal emissivity (0.84): Standard polyester film properties
        - Thermal resistance (0.0): No insulating properties
        
        Decorative film:
        - Visible transmittance (0.70): Varies significantly by pattern. Value based on Tzempelikos, A., & Athienitis, 
          A. K. (2007). "The impact of shading design and control on building cooling and lighting demand." Solar Energy, 
          81(3), 369-382. Translucent decorative films typically 65-75% VT.
        - Solar transmittance (0.65): Nielsen, T. R., Duer, K., & Svendsen, S. (2000). "Energy performance of glazings 
          and windows." Solar Energy, 69(Suppl. 1-6), 137-143. Decorative films reduce solar transmission to 60-70%.
        - Thermal emissivity (0.84): Standard substrate
        - Thermal resistance (0.0): Minimal insulating effect
        
        Low-E film (retrofit low-emissivity):
        - Visible transmittance (0.75): Arasteh, D., Reilly, S., & Rubin, M. (1989). "A versatile procedure for 
          calculating heat transfer through windows." ASHRAE Transactions, 95(2), 755-765. Low-E films typically 
          70-80% VT to balance light transmission with IR reflection.
        - Solar transmittance (0.65): Rubin, M. (1985). "Optical properties of soda lime silica glasses." Solar Energy 
          Materials, 12(4), 275-288. Low-E coatings reduce solar heat gain to 60-70% while maintaining daylight.
        - Thermal emissivity (0.15): Granqvist, C. G. (2007). "Transparent conductors as solar energy materials: A 
          panoramic review." Solar Energy Materials and Solar Cells, 91(17), 1529-1598. Low-E coatings achieve 
          emissivity of 0.10-0.20 for effective IR reflection.
        - Thermal resistance (0.05): Adds modest R-value. Collins, R. E., & Simko, T. M. (1998). "Current status of 
          the science and technology of vacuum glazing." Solar Energy, 62(3), 189-213. Retrofit low-E films provide 
          ΔR ≈ 0.04-0.06 m²·K/W.
        
        Default/unknown film:
        - Conservative mid-range values based on clear protective films (0.85, 0.70, 0.84, 0.0)
        """
        # Film properties: (visible_transmittance, solar_transmittance, thermal_emissivity, thermal_resistance)
        film_properties = {
            'safety film': (0.88, 0.75, 0.84, 0.0),
            'solar control film': (0.50, 0.30, 0.84, 0.0),
            'anti-graffiti film': (0.90, 0.80, 0.84, 0.0),
            'decorative film': (0.70, 0.65, 0.84, 0.0),
            'low-e film': (0.75, 0.65, 0.15, 0.05)
        }
        return film_properties.get(film_option, (0.85, 0.70, 0.84, 0.0))

    def count_glazing_layers(self, construction):
        """Count the number of glazing layers in a construction.
        Returns: number of glazing layers, or -1 if not a layered construction
        """
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            glazing_count = 0
            for i in range(layered.numLayers()):
                material = layered.getLayer(i)
                if (material.to_StandardGlazing().is_initialized() or 
                    material.to_RefractionExtinctionGlazing().is_initialized()):
                    glazing_count += 1
            return glazing_count
        return -1

    def is_simple_glazing_system(self, runner, construction):
        """Check if the construction uses SimpleGlazing material."""
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            for i in range(layered.numLayers()):
                material = layered.getLayer(i)
                if material.to_SimpleGlazing().is_initialized():
                    runner.registerInfo(f"Simple glazing system detected in layer {i+1}")
                    return True
        return False

    def create_new_window_construction(self, model, runner, subsurface, num_panes, glass_thickness, gap_thickness,
                                       solar_trans, visible_trans, front_emissivity, back_emissivity,
                                       front_solar_refl, back_solar_refl, front_visible_refl, back_visible_refl):
        """Create a new window construction with specified number of panes and dimensions.
        
        Args:
            model: OpenStudio model
            runner: Measure runner for logging
            subsurface: The subsurface to create construction for
            num_panes: Number of glass panes (1, 2, or 3)
            glass_thickness: Thickness of each glass pane in meters
            gap_thickness: Thickness of air gap between panes in meters
            solar_trans: Solar transmittance (0.0 = use default 0.775)
            visible_trans: Visible transmittance (0.0 = use default 0.881)
            front_emissivity: Front side IR emissivity (0.0 = use default 0.84)
            back_emissivity: Back side IR emissivity (0.0 = use default 0.84)
            front_solar_refl: Front side solar reflectance (0.0 = use default 0.071)
            back_solar_refl: Back side solar reflectance (0.0 = use default 0.071)
            front_visible_refl: Front side visible reflectance (0.0 = use default 0.080)
            back_visible_refl: Back side visible reflectance (0.0 = use default 0.080)
            
        Returns:
            New Construction object or None if creation fails
        """
        subsurface_name = subsurface.nameString()
        
        # Use default values if user provided 0.0
        solar_trans = solar_trans if solar_trans > 0.0 else 0.775
        visible_trans = visible_trans if visible_trans > 0.0 else 0.881
        front_emissivity = front_emissivity if front_emissivity > 0.0 else 0.84
        back_emissivity = back_emissivity if back_emissivity > 0.0 else 0.84
        front_solar_refl = front_solar_refl if front_solar_refl > 0.0 else 0.071
        back_solar_refl = back_solar_refl if back_solar_refl > 0.0 else 0.071
        front_visible_refl = front_visible_refl if front_visible_refl > 0.0 else 0.080
        back_visible_refl = back_visible_refl if back_visible_refl > 0.0 else 0.080
        
        # Create construction name
        construction_name = f"{subsurface_name}_New_{num_panes}Pane_Construction"
        
        # Create glass pane materials
        layers = openstudio.model.MaterialVector()
        
        for pane_num in range(1, num_panes + 1):
            # Create glass layer with user-specified or default properties
            glass_pane = openstudio.model.StandardGlazing(model)
            glass_pane.setName(f"{subsurface_name}_Glass_Pane_{pane_num}")
            glass_pane.setThickness(glass_thickness)
            
            # Set optical and thermal properties
            glass_pane.setSolarTransmittance(solar_trans)
            glass_pane.setVisibleTransmittance(visible_trans)
            glass_pane.setFrontSideSolarReflectanceatNormalIncidence(front_solar_refl)
            glass_pane.setBackSideSolarReflectanceatNormalIncidence(back_solar_refl)
            glass_pane.setFrontSideVisibleReflectanceatNormalIncidence(front_visible_refl)
            glass_pane.setBackSideVisibleReflectanceatNormalIncidence(back_visible_refl)
            glass_pane.setInfraredTransmittanceatNormalIncidence(0.0)
            glass_pane.setFrontSideInfraredHemisphericalEmissivity(front_emissivity)
            glass_pane.setBackSideInfraredHemisphericalEmissivity(back_emissivity)
            glass_pane.setThermalConductivity(0.9)  # W/m-K for typical glass
            
            # Add glass layer
            layers.append(glass_pane)
            
            # Add air gap after each glass pane except the last one
            if pane_num < num_panes:
                air_gap = openstudio.model.Gas(model)
                air_gap.setName(f"{subsurface_name}_Air_Gap_{pane_num}")
                air_gap.setThickness(gap_thickness)
                air_gap.setGasType("Air")
                layers.append(air_gap)
        
        # Create new construction
        new_construction = openstudio.model.Construction(model)
        new_construction.setName(construction_name)
        new_construction.setLayers(layers)
        
        runner.registerInfo(f"Created {num_panes}-pane construction: glass thickness={glass_thickness*1000:.1f}mm, gap thickness={gap_thickness*1000:.1f}mm")
        
        return new_construction

    def add_secondary_glazing(self, model, runner, subsurface, original_construction, glass_pane_thickness, gap_thickness,
                              solar_trans, visible_trans, front_emissivity, back_emissivity,
                              front_solar_refl, back_solar_refl, front_visible_refl, back_visible_refl):
        """Add a secondary glazing layer to single-pane window construction.
        This function only handles standard layered constructions with a single glazing layer.
        """
        subsurface_name = subsurface.nameString()
        
        # Use default values if user provided 0.0
        solar_trans = solar_trans if solar_trans > 0.0 else 0.775
        visible_trans = visible_trans if visible_trans > 0.0 else 0.881
        front_emissivity = front_emissivity if front_emissivity > 0.0 else 0.84
        back_emissivity = back_emissivity if back_emissivity > 0.0 else 0.84
        front_solar_refl = front_solar_refl if front_solar_refl > 0.0 else 0.071
        back_solar_refl = back_solar_refl if back_solar_refl > 0.0 else 0.071
        front_visible_refl = front_visible_refl if front_visible_refl > 0.0 else 0.080
        back_visible_refl = back_visible_refl if back_visible_refl > 0.0 else 0.080
        
        # Create new construction name
        new_construction_name = f"{original_construction.nameString()}_with_secondary_glazing"
        
        # Create secondary glazing layer using user-specified properties
        secondary_glazing = openstudio.model.StandardGlazing(model)
        secondary_glazing.setName(f"Secondary_Glazing_{glass_pane_thickness*1000:.0f}mm_Clear")
        secondary_glazing.setThickness(glass_pane_thickness)
        secondary_glazing.setSolarTransmittance(solar_trans)
        secondary_glazing.setVisibleTransmittance(visible_trans)
        secondary_glazing.setFrontSideSolarReflectanceatNormalIncidence(front_solar_refl)
        secondary_glazing.setBackSideSolarReflectanceatNormalIncidence(back_solar_refl)
        secondary_glazing.setFrontSideVisibleReflectanceatNormalIncidence(front_visible_refl)
        secondary_glazing.setBackSideVisibleReflectanceatNormalIncidence(back_visible_refl)
        secondary_glazing.setInfraredTransmittanceatNormalIncidence(0.0)
        secondary_glazing.setFrontSideInfraredHemisphericalEmissivity(front_emissivity)
        secondary_glazing.setBackSideInfraredHemisphericalEmissivity(back_emissivity)
        
        # Create air gap between panes using user-specified thickness
        air_gap = openstudio.model.Gas(model)
        air_gap.setName(f"Air_Gap_{gap_thickness*1000:.0f}mm")
        air_gap.setThickness(gap_thickness)
        air_gap.setGasType("Air")
        
        # Build new layer assembly
        layers = openstudio.model.MaterialVector()
        
        # Copy existing layers from original construction
        if original_construction.to_LayeredConstruction().is_initialized():
            layered = original_construction.to_LayeredConstruction().get()
            for i in range(layered.numLayers()):
                original_material = layered.getLayer(i)
                layers.append(original_material)
        
        # Add air gap and secondary glazing to interior side
        layers.append(air_gap)
        layers.append(secondary_glazing)
        
        # Create new layered construction
        new_layered_construction = openstudio.model.Construction(model)
        new_layered_construction.setName(new_construction_name)
        new_layered_construction.setLayers(layers)
        
        # Assign new construction to subsurface
        subsurface.setConstruction(new_layered_construction)
        
        runner.registerInfo(f"Created new construction '{new_construction_name}' with secondary glazing for {subsurface_name}")
        runner.registerInfo(f"Added {gap_thickness*1000:.0f}mm air gap and {glass_pane_thickness*1000:.0f}mm clear glass as secondary glazing")
        
        return new_layered_construction

    def convert_to_equivalent_layer(self, model, runner, subsurface, original_construction, film_option, 
                                    film_visible_transmittance, film_solar_transmittance, 
                                    film_thermal_emissivity, film_thermal_resistance):
        """Integrate glazing film effects into the innermost glass pane.
        This function modifies the interior glass layer to account for film properties.
        """
        subsurface_name = subsurface.nameString()
        
        # Create new construction name
        new_construction_name = f"{original_construction.nameString()}_with_{film_option.replace(' ', '_')}"
        
        # Get film properties
        # Get film properties - use defaults from get_film_properties if user didn't override (0.0)
        default_vis_trans, default_sol_trans, default_emissivity, default_thermal_resistance = self.get_film_properties(film_option)
        film_vis_trans = film_visible_transmittance if film_visible_transmittance > 0.0 else default_vis_trans
        film_sol_trans = film_solar_transmittance if film_solar_transmittance > 0.0 else default_sol_trans
        film_emissivity = film_thermal_emissivity if film_thermal_emissivity > 0.0 else default_emissivity
        thermal_resistance = film_thermal_resistance if film_thermal_resistance > 0.0 else default_thermal_resistance
        
        # Build new layers, modifying the innermost glass pane
        layers = openstudio.model.MaterialVector()
        
        if original_construction.to_LayeredConstruction().is_initialized():
            layered = original_construction.to_LayeredConstruction().get()
            num_layers = layered.numLayers()
            
            # Find the innermost (last) glazing layer
            innermost_glass_index = -1
            for i in range(num_layers - 1, -1, -1):
                material = layered.getLayer(i)
                if material.to_StandardGlazing().is_initialized():
                    innermost_glass_index = i
                    break
            
            if innermost_glass_index == -1:
                runner.registerWarning(f"No StandardGlazing layer found in {subsurface_name}, cannot apply film effects")
                return original_construction
            
            # Copy layers and modify the innermost glass pane
            for i in range(num_layers):
                original_material = layered.getLayer(i)
                
                if i == innermost_glass_index:
                    # Modify the innermost glass pane to integrate film effects
                    original_glass = original_material.to_StandardGlazing().get()
                    
                    # Create modified glass pane with film effects
                    modified_glass = openstudio.model.StandardGlazing(model)
                    modified_glass.setName(f"{original_glass.nameString()}_with_{film_option.replace(' ', '_')}")
                    modified_glass.setThickness(original_glass.thickness())
                    
                    # Get original optical properties (with defaults if not available)
                    orig_sol_trans = 0.837
                    orig_vis_trans = 0.898
                    
                    # Try to get actual values from original glass
                    try:
                        opt_sol = original_glass.solarTransmittance()
                        if opt_sol.is_initialized():
                            orig_sol_trans = opt_sol.get()
                    except:
                        pass
                    
                    try:
                        opt_vis = original_glass.visibleTransmittance()
                        if opt_vis.is_initialized():
                            orig_vis_trans = opt_vis.get()
                    except:
                        pass
                    
                    # Combine optical properties (multiply transmittances)
                    modified_glass.setSolarTransmittance(orig_sol_trans * film_sol_trans)
                    modified_glass.setVisibleTransmittance(orig_vis_trans * film_vis_trans)
                    
                    # Copy front side properties from original glass (if available)
                    try:
                        opt_val = original_glass.frontSideSolarReflectanceatNormalIncidence()
                        if opt_val.is_initialized():
                            modified_glass.setFrontSideSolarReflectanceatNormalIncidence(opt_val.get())
                    except:
                        pass
                    
                    try:
                        opt_val = original_glass.frontSideVisibleReflectanceatNormalIncidence()
                        if opt_val.is_initialized():
                            modified_glass.setFrontSideVisibleReflectanceatNormalIncidence(opt_val.get())
                    except:
                        pass
                    
                    try:
                        opt_val = original_glass.frontSideInfraredHemisphericalEmissivity()
                        if opt_val.is_initialized():
                            modified_glass.setFrontSideInfraredHemisphericalEmissivity(opt_val.get())
                    except:
                        pass
                    
                    # Copy back side properties (except emissivity which gets film value)
                    try:
                        opt_val = original_glass.backSideSolarReflectanceatNormalIncidence()
                        if opt_val.is_initialized():
                            modified_glass.setBackSideSolarReflectanceatNormalIncidence(opt_val.get())
                    except:
                        pass
                    
                    try:
                        opt_val = original_glass.backSideVisibleReflectanceatNormalIncidence()
                        if opt_val.is_initialized():
                            modified_glass.setBackSideVisibleReflectanceatNormalIncidence(opt_val.get())
                    except:
                        pass
                    
                    # Apply film emissivity to back (interior) side
                    modified_glass.setBackSideInfraredHemisphericalEmissivity(film_emissivity)
                    
                    # Copy other thermal properties
                    try:
                        opt_val = original_glass.infraredTransmittanceatNormalIncidence()
                        if opt_val.is_initialized():
                            modified_glass.setInfraredTransmittanceatNormalIncidence(opt_val.get())
                    except:
                        pass
                    
                    try:
                        opt_val = original_glass.thermalConductivity()
                        if opt_val.is_initialized():
                            modified_glass.setThermalConductivity(opt_val.get())
                    except:
                        pass
                    
                    layers.append(modified_glass)
                    runner.registerInfo(f"Modified innermost glass pane with film properties: Vis Trans {orig_vis_trans:.3f}→{orig_vis_trans * film_vis_trans:.3f}, Sol Trans {orig_sol_trans:.3f}→{orig_sol_trans * film_sol_trans:.3f}, Back Emissivity→{film_emissivity:.3f}")
                else:
                    # Copy other layers unchanged
                    layers.append(original_material)
        
        # Create new layered construction
        new_layered_construction = openstudio.model.Construction(model)
        new_layered_construction.setName(new_construction_name)
        new_layered_construction.setLayers(layers)
        
        # Assign new construction to subsurface
        subsurface.setConstruction(new_layered_construction)
        
        runner.registerInfo(f"Created new construction '{new_construction_name}' with glazing film integrated into innermost glass pane for {subsurface_name}")
        
        return new_layered_construction

    def get_frame_and_divider_dimension(self, runner, subsurface):
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
        return frame_width,divider_width,num_hori_divider,num_verti_divider

# Register the measure
WindowEnhancement().registerWithApplication()

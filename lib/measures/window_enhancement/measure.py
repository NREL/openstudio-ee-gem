# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************


import importlib.util
import re
from pathlib import Path
import openstudio
import typing
import numpy as np
from resources.EC3_lookup import *


_LOCAL_EC3_LOOKUP_PATH = Path(__file__).resolve().parent / "resources" / "EC3_lookup.py"
_LOCAL_EC3_SPEC = importlib.util.spec_from_file_location("window_enhancement_local_ec3_lookup", _LOCAL_EC3_LOOKUP_PATH)
_LOCAL_EC3_MODULE = importlib.util.module_from_spec(_LOCAL_EC3_SPEC)
_LOCAL_EC3_SPEC.loader.exec_module(_LOCAL_EC3_MODULE)


def fetch_epd_data(url, api_token):
    return _LOCAL_EC3_MODULE.fetch_epd_data(url=url, api_token=api_token)


class WindowEnhancement(openstudio.measure.ModelMeasure):

    """A ModelMeasure for window enhancement, calculating embodied carbon.
    
    EC3 data fetched through categorization and keywords.
    """

    def name(self):
        """Measure name."""
        return "Window Enhancement"

    def description(self):
        """Brief description of the measure."""
        return ("Improves window performance through six retrofit enhancement options: (1) frame replacement, "
                "(2) glass pane upgrades (single/double/triple pane), (3) caulking/sealant application, "
                "(4) glazing film installation (safety, solar control, low-e, etc.), (5) weatherstripping, "
                "and (6) secondary glazing for single-pane windows. The measure calculates embodied carbon impact "
                "using Environmental Product Declaration (EPD) data from the EC3 database, modifies window "
                "thermal and optical properties based on selected enhancements, and adjusts space infiltration "
                "rates to reflect improved air sealing. Requires an EC3 API key and Python libraries (numpy, "
                "pandas, urllib3).")

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure performs three main functions:\n\n"
                "1. **Infiltration Reduction**: Reduces space infiltration rates by a user-specified percentage "
                "(default 50%) to simulate improved air sealing from window enhancements. The reduction applies "
                "to all window-containing spaces in the selected space type or entire building.\n\n"
                "2. **Embodied Carbon Calculation**: Calculates life-cycle embodied carbon (kg CO2 eq) for six "
                "window enhancement options over the analysis period:\n"
                "   - **Glass pane replacement**: Single, double, or triple pane configurations with customizable "
                "optical and thermal properties\n"
                "   - **Frame replacement**: Vinyl, aluminum, wood, or fiberglass frame materials\n"
                "   - **Glazing film application**: Safety, solar control, anti-graffiti, decorative, or low-e films\n"
                "   - **Caulking**: Acrylic or polyurethane sealants for perimeter air sealing\n"
                "   - **Weatherstripping**: Felt, foam, V-strip, vinyl, or silicone gaskets (operable windows only)\n"
                "   - **Secondary glazing**: Additional interior glass pane for single-pane windows\n\n"
                "3. **Thermal and Optical Property Updates**: The measure modifies window constructions:\n"
                "   - Glass replacement: Creates new multi-pane layered constructions with user-specified or "
                "default glass properties (transmittance, reflectance, emissivity, thickness)\n"
                "   - Film application: Modifies the innermost glass pane to simulate combined glass+film optical "
                "and thermal performance\n"
                "   - Secondary glazing: Adds additional glass pane with air gap to existing single-pane windows\n\n"
                "The measure retrieves EPD data from the EC3 database via API, calculates statistical GWP values "
                "(min/max/mean/median), removes outliers using the IQR method, and accounts for product lifetimes "
                "and replacement cycles over the analysis period. Material quantities are calculated based on window "
                "dimensions, including areas (glass, film, frame), lengths (weatherstrip, perimeter), and volumes "
                "(caulking). Users can override the number of horizontal and vertical dividers (muntins) to calculate "
                "accurate glazing areas, or use default values from the model. Results including embodied carbon values, "
                "material quantities, and renovation details are reported in a comprehensive summary showing infiltration "
                "reduction, windows processed, renovations applied, and total embodied carbon.\n\n"
                "**Important Notes**:\n"
                "- Users can select multiple enhancement options simultaneously\n"
                "- Users can specify custom number of horizontal and vertical dividers (default: -1 uses model values)\n"
                "- Weatherstripping only applies to operable windows\n"
                "- Secondary glazing requires single-pane layered constructions (not simple glazing systems)\n"
                "- Glass replacement with secondary glazing will skip secondary glazing to avoid conflicts\n"
                "- Film application requires layered constructions with StandardGlazing materials")
    @staticmethod
    def gwp_statistics():
        return ["minimum", "maximum", "mean", "median"]
    
    @staticmethod
    def wf_options():
        return ["none", "wood window frame", "wood-aluminium window frame"]
    
    @staticmethod
    def caulking_options():
        return ["none", "acrylic", "polyurethane"]
    
    @staticmethod
    def film_options():
        return ["none", 'safety film', 'solar control film', 'anti-graffiti film', 'decorative film', 'low-e film']

    @staticmethod
    def weatherstrip_options():
        return ["none", "silicone adhesive smoke gasket"]
    
    @staticmethod
    def glass_options():
        return ["none", "provide user_num_panes"]
    
    @staticmethod
    def secondary_glazing_options():
        return ["none", "install secondary glazing"]

    def _resolve_glazing_rsmeans_id(self, material_name, material_payload, user_specified_id):
        """Resolve RSMeans ID for glazing-related materials.

        Priority:
        1) User-specified ID (if provided)
        2) Curated fallback ID from call_rsmeans_api helper
        3) Raise ValueError (caller should terminate measure)
        """
        explicit_id = str(user_specified_id or "").strip()
        if explicit_id:
            return explicit_id

        measure_dir = Path(__file__).parent
        rsmeans_helper_path = measure_dir / "resources" / "call_rsmeans_api.py"
        if not rsmeans_helper_path.exists():
            raise ValueError(
                f"RSMeans helper not found at {rsmeans_helper_path}; cannot resolve fallback ID for '{material_name}'."
            )

        spec = importlib.util.spec_from_file_location("call_rsmeans_api", rsmeans_helper_path)
        if spec is None or spec.loader is None:
            raise ValueError("Unable to load RSMeans helper module for fallback ID resolution.")
        rsmeans_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rsmeans_module)

        fallback_resolver = getattr(rsmeans_module, "_get_default_fallback_rsmeans_id", None)
        if not callable(fallback_resolver):
            raise ValueError("RSMeans fallback ID resolver '_get_default_fallback_rsmeans_id' is unavailable.")

        payload_name = str((material_payload or {}).get("name", "") or "").strip()
        payload_desc = str((material_payload or {}).get("description", "") or "").strip()
        fallback_lookup_name = payload_name or material_name

        fallback_id = fallback_resolver(fallback_lookup_name, material_payload)
        if not fallback_id and fallback_lookup_name != material_name:
            # Retry with caller-provided semantic material key.
            fallback_id = fallback_resolver(material_name, material_payload)
        if fallback_id:
            return str(fallback_id).strip()

        raise ValueError(
            "No RSMeans ID available: user-specified ID and fallback ID are both missing. "
            f"material_name='{material_name}', payload_name='{payload_name}', payload_description='{payload_desc}'."
        )

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
            if value.spaces():
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

        # Create argument for air infiltration reduction percentage.
        space_infiltration_reduction_percent = openstudio.measure.OSArgument.makeDoubleArgument(
            "space_infiltration_reduction_percent", True)
        space_infiltration_reduction_percent.setDisplayName("Space Infiltration Power Reduction")
        space_infiltration_reduction_percent.setDefaultValue(50.0)
        space_infiltration_reduction_percent.setUnits("%")
        args.append(space_infiltration_reduction_percent)

        # Infiltration coefficients are intentionally not exposed as arguments;
        # this measure preserves existing model coefficients and scales rates.

        # Create argument for analysis period.
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription(
            "Analysis period of embodied carbon calculation in years. This parameter and product life "
            "expectancy will affect the number of replacements during the analysis period.")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        # Create argument for glass pane product lifetime.
        glass_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("glass_lifetime",True)
        glass_lifetime.setDisplayName("Product Lifetime of Glass pane")
        glass_lifetime.setDescription(
            "Life expectancy of glass pane. Default value is provided based on data from the "
            "Certified Commercial Property Inspectors Association (CCPIA).")
        glass_lifetime.setDefaultValue(15)
        args.append(glass_lifetime)

        # Create argument for window frame product lifetime.
        wf_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("wf_lifetime",True)
        wf_lifetime.setDisplayName("Product Lifetime of Window Frame")
        wf_lifetime.setDescription(
            "Life expectancy of window frame. Default value is provided based on data from the "
            "Certified Commercial Property Inspectors Association (CCPIA).")
        wf_lifetime.setDefaultValue(15)
        args.append(wf_lifetime)

        # Create argument for caulking sealant product lifetime.
        caulking_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("caulking_lifetime",True)
        caulking_lifetime.setDisplayName("Product Lifetime of Caulking Sealant")
        caulking_lifetime.setDescription(
            "Life expectancy of caulking sealant. Default value is provided based on data from the "
            "Certified Commercial Property Inspectors Association (CCPIA).")
        caulking_lifetime.setDefaultValue(10)
        args.append(caulking_lifetime)

        # Create argument for glazing film product lifetime.
        film_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("film_lifetime",True)
        film_lifetime.setDisplayName("Product Lifetime of Glazing Film")
        film_lifetime.setDescription(
            "Life expectancy of glazing film. Default value is provided based on data from the "
            "Certified Commercial Property Inspectors Association (CCPIA).")
        film_lifetime.setDefaultValue(10)
        args.append(film_lifetime)

        # Create argument for weatherstrip product lifetime.
        weatherstrip_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("weatherstrip_lifetime",True)
        weatherstrip_lifetime.setDisplayName("Product Lifetime of Weatherstrip")
        weatherstrip_lifetime.setDescription(
            "Life expectancy of weatherstrip. Default value is provided based on data from the "
            "Certified Commercial Property Inspectors Association (CCPIA).")
        weatherstrip_lifetime.setDefaultValue(10)
        args.append(weatherstrip_lifetime)

        # Create argument for overhead and profit percent on material cost.
        overhead_profit_percent = openstudio.measure.OSArgument.makeDoubleArgument("overhead_profit_percent", True)
        overhead_profit_percent.setDisplayName("Overhead + Profit Percent")
        overhead_profit_percent.setDescription(
            "Percent applied to total material cost to estimate overhead and profit. Set to 0 to disable.")
        overhead_profit_percent.setDefaultValue(0.0)
        args.append(overhead_profit_percent)

        # Create argument for window frame options used to filter EPDs.
        wf_options_chs = openstudio.StringVector()
        for option in self.wf_options():
            wf_options_chs.append(option)
        wf_option = openstudio.measure.OSArgument.makeChoiceArgument("wf_option",wf_options_chs, True)
        wf_option.setDisplayName("Window frame option")
        wf_option.setDescription(
            "Select none if no window frame is to be installed, otherwise provide frame type. NOTE: "
            "When not none, this renovation option can not work with the entire window replacement at "
            "the same time to avoid double counting.")
        wf_option.setDefaultValue("none")
        args.append(wf_option)

        # Create argument for caulking options used to filter EPDs.
        caulking_options_chs = openstudio.StringVector()
        for option in self.caulking_options():
            caulking_options_chs.append(option)
        caulking_option = openstudio.measure.OSArgument.makeChoiceArgument(
            "caulking_option", caulking_options_chs, True)
        caulking_option.setDisplayName("Caulking Material Option")
        caulking_option.setDescription(
            "Select none if no caulking is to be applied, otherwise provide material type. This "
            "renovation option is for the window perimeter joint sealing.")
        caulking_option.setDefaultValue("none")
        args.append(caulking_option)

        # Create argument for glazing film options used to filter EPDs.
        film_options_chs = openstudio.StringVector()
        for option in self.film_options():
            film_options_chs.append(option)
        film_option = openstudio.measure.OSArgument.makeChoiceArgument("film_option", film_options_chs, True)
        film_option.setDisplayName("Glazing Film Option")
        film_option.setDescription(
            "Select none if no glazing film is to be installed, otherwise provide film type. This "
            "renovation option is for the window glazing.")
        film_option.setDefaultValue("none")
        args.append(film_option)

        # make arguments for film optical and thermal properties
        film_visible_transmittance = openstudio.measure.OSArgument.makeDoubleArgument(
            "film_visible_transmittance", True)
        film_visible_transmittance.setDisplayName("Film Visible Transmittance")
        film_visible_transmittance.setDescription(
            "Visible transmittance of the film only (0.0-1.0). This value is multiplied with existing "
            "glass transmittance to calculate combined glass+film performance. Set to 0.0 to use default "
            "values based on film type. Defaults: safety=0.88, solar_control=0.15, anti_graffiti=0.90, "
            "decorative=0.60, low_e=0.80")
        film_visible_transmittance.setDefaultValue(0.0)
        args.append(film_visible_transmittance)

        film_solar_transmittance = openstudio.measure.OSArgument.makeDoubleArgument(
            "film_solar_transmittance", True)
        film_solar_transmittance.setDisplayName("Film Solar Transmittance")
        film_solar_transmittance.setDescription(
            "Solar transmittance of the film only (0.0-1.0). This value is multiplied with existing "
            "glass transmittance to calculate combined glass+film performance. Set to 0.0 to use default "
            "values based on film type. Defaults: safety=0.81, solar_control=0.15, anti_graffiti=0.83, "
            "decorative=0.55, low_e=0.70")
        film_solar_transmittance.setDefaultValue(0.0)
        args.append(film_solar_transmittance)

        film_thermal_emissivity = openstudio.measure.OSArgument.makeDoubleArgument(
            "film_thermal_emissivity", True)
        film_thermal_emissivity.setDisplayName("Film Thermal Emissivity")
        film_thermal_emissivity.setDescription(
            "Thermal emissivity of the film surface only (0.0-1.0). This value replaces the back-side "
            "emissivity of the innermost glass pane to simulate film application. Set to 0.0 to use default "
            "values based on film type. Defaults: safety=0.84, solar_control=0.84, anti_graffiti=0.84, "
            "decorative=0.84, low_e=0.10")
        film_thermal_emissivity.setDefaultValue(0.0)
        args.append(film_thermal_emissivity)

        film_thermal_resistance = openstudio.measure.OSArgument.makeDoubleArgument(
            "film_thermal_resistance", True)
        film_thermal_resistance.setDisplayName("Film Thermal Resistance (m²·K/W)")
        film_thermal_resistance.setDescription(
            "Thermal resistance of the film only in m²·K/W. This represents the insulating value of the "
            "film layer itself. Set to 0.0 to use default values based on film type. Defaults: "
            "safety=0.0002, solar_control=0.0003, anti_graffiti=0.0001, decorative=0.0002, low_e=0.18")
        film_thermal_resistance.setDefaultValue(0.0)
        args.append(film_thermal_resistance)

        # Create argument for glass replacement option and EPD filtering.
        glass_options_chs = openstudio.StringVector()
        for option in self.glass_options():
            glass_options_chs.append(option)
        glass_option = openstudio.measure.OSArgument.makeChoiceArgument("glass_option", glass_options_chs, True)
        glass_option.setDisplayName("Glass Option on Renovation")
        glass_option.setDescription(
            "Select none if no new glass pane is to be installed, otherwise provide user_num_panes. "
            "NOTE: When not none, this renovation option can not work with the entire window replacement "
            "at the same time to avoid double counting.")
        glass_option.setDefaultValue("none")
        args.append(glass_option)

        # Create argument for weatherstrip options used to filter EPDs.
        weatherstrip_options_chs = openstudio.StringVector()
        for option in self.weatherstrip_options():
            weatherstrip_options_chs.append(option)
        weatherstrip_option = openstudio.measure.OSArgument.makeChoiceArgument(
            "weatherstrip_option", weatherstrip_options_chs, True)
        weatherstrip_option.setDisplayName("Weatherstrip Option")
        weatherstrip_option.setDescription(
            "Select none if no weatherstrip is to be applied, otherwise provide material type. NOTE: "
            "Weatherstrip is only applicable to operable windows, and will be applied to the sliding edge only.")
        weatherstrip_option.setDefaultValue("none")
        args.append(weatherstrip_option)

        # Create argument for secondary glazing options.
        secondary_glazing_options_chs = openstudio.StringVector()
        for option in self.secondary_glazing_options():
            secondary_glazing_options_chs.append(option)
        secondary_glazing_option = openstudio.measure.OSArgument.makeChoiceArgument(
            "secondary_glazing_option", secondary_glazing_options_chs, True)
        secondary_glazing_option.setDisplayName("Secondary Glazing Option")
        secondary_glazing_option.setDescription(
            "Select 'install secondary glazing' to add a second glazing layer to single-pane windows. "
            "NOTE: This option only applies to single-pane standard layered constructions, not simple "
            "glazing systems.")
        secondary_glazing_option.setDefaultValue("none")
        args.append(secondary_glazing_option)

        # Create argument for applied caulking thickness.
        caulking_thickness = openstudio.measure.OSArgument.makeDoubleArgument("caulking_thickness", True)
        caulking_thickness.setDisplayName("Caulking Material Thickness (m)")
        caulking_thickness.setDescription(
            "Thickness of the caulking material applied in meters. This parameter is equivalent to the "
            "diameter of the caulking bead. Default value is set to 0.008 m (8 mm).")
        caulking_thickness.setDefaultValue(0.008) # 8 mm thickness
        args.append(caulking_thickness)

        # Create argument for user-specified pane count.
        user_num_panes = openstudio.measure.OSArgument.makeIntegerArgument("user_num_panes", True)
        user_num_panes.setDisplayName("Number of Glass Panes Provided by User")
        user_num_panes.setDescription(
            "When glass option is not none, this is the number of glass panes to be installed as determined "
            "by user. Otherwise, the number of panes will be derived from the model. Valid values are 0, 1, "
            "2, or 3. 0 means do not install any new glass panes. 1 means single pane, 2 means double pane, "
            "and 3 means triple pane. If the value provided is more than 3, it will be changed to 3 because "
            "currently the measure is unable to handle more complex scenarios due to the lack of EPD data.")
        user_num_panes.setDefaultValue(0) # 0 means do not install any new glass panes
        args.append(user_num_panes)

        # Create argument for glass pane thickness.
        glass_pane_thickness = openstudio.measure.OSArgument.makeDoubleArgument("glass_pane_thickness", True)
        glass_pane_thickness.setDisplayName("Individual Glass Pane Thickness (m)")
        glass_pane_thickness.setDescription(
            "Thickness of an individual glass pane in meters. This value is used to calculate embodied "
            "carbon using gwp_per_m3 for glass installations. Default value is 0.003 m (3 mm), which is "
            "typical for standard single-strength window glass. Source: ASTM C1036-16 'Standard Specification "
            "for Flat Glass' specifies single-strength glass as 2.16-2.57 mm (0.085-0.101 in) and "
            "double-strength as 2.92-3.56 mm (0.115-0.140 in). Pilkington Glass Handbook (1997) and "
            "ASHRAE Handbook - Fundamentals (2017) Chapter 15 cite 3 mm as standard for residential glazing.")
        glass_pane_thickness.setDefaultValue(0.003) # 3 mm typical glass thickness
        args.append(glass_pane_thickness)

        # Create argument for gap thickness between glass panes.
        gap_thickness = openstudio.measure.OSArgument.makeDoubleArgument("gap_thickness", True)
        gap_thickness.setDisplayName("Gap Thickness Between Glass Panes (m)")
        gap_thickness.setDescription(
            "Thickness of the air/gas gap between glass panes in meters. Enter 0.0 to use default value. This is used when creating new "
            "multi-pane window constructions. Default value is 0.013 m (13 mm), which is typical for double "
            "and triple pane windows. Sources: ISO 10077-1:2017 'Thermal performance of windows, doors and "
            "shutters' specifies 12-16 mm optimal air gap spacing. Curcija, D., et al. (2018) 'WINDOW "
            "Technical Documentation' LBNL-2000012 recommends 12.7 mm (0.5 in) for residential IGUs. Arici, "
            "M., et al. (2015) 'Thermal performance of double glazed windows' Energy and Buildings, 94, "
            "200-207, demonstrates optimal thermal performance at 13 mm gap spacing.")
        gap_thickness.setDefaultValue(0.013) # 13 mm typical gap thickness
        args.append(gap_thickness)

        # make arguments for glass pane optical properties
        glass_solar_transmittance = openstudio.measure.OSArgument.makeDoubleArgument("glass_solar_transmittance", True)
        glass_solar_transmittance.setDisplayName("Glass Solar Transmittance")
        glass_solar_transmittance.setDescription(
            "Solar transmittance of the glass pane (0.0-1.0). Set to 0.0 to use default value of 0.775 for "
            "typical 3mm clear soda-lime glass. This value affects solar heat gain through windows. Sources: "
            "ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 'Solar-Optical Properties of Glazing' "
            "lists clear glass (3 mm) solar transmittance as 0.77-0.78. Rubin, M. (1985) 'Optical properties "
            "of soda lime silica glasses' Solar Energy Materials, 12(4), 275-288, reports 0.775 for standard "
            "float glass. ISO 9050:2003 'Glass in building - Determination of light transmittance, solar "
            "direct transmittance' provides testing methodology yielding 0.77-0.78 for clear glass.")
        glass_solar_transmittance.setDefaultValue(0.837)
        args.append(glass_solar_transmittance)

        glass_visible_transmittance = openstudio.measure.OSArgument.makeDoubleArgument(
            "glass_visible_transmittance", True)
        glass_visible_transmittance.setDisplayName("Glass Visible Transmittance")
        glass_visible_transmittance.setDescription(
            "Visible light transmittance of the glass pane (0.0-1.0). Set to 0.0 to use default value of "
            "0.881 for typical 3mm clear glass. This value affects daylight availability. Sources: NFRC "
            "300-2017 'Test Method for Determining the Solar and Infrared Optical Properties of Glazing "
            "Materials' specifies clear glass VT as 0.88-0.90. ASHRAE Handbook - Fundamentals (2017) Chapter "
            "15 lists 3mm clear glass VT as 0.881. McCluney, R. (1996) 'Introduction to Radiometry and "
            "Photometry' Artech House, reports clear float glass VT of 0.88. Pilkington (2016) 'Pilkington "
            "Glass Products Specifications' technical data sheet lists Optifloat Clear 3mm VT as 0.90.")
        glass_visible_transmittance.setDefaultValue(0.898)
        args.append(glass_visible_transmittance)

        glass_front_emissivity = openstudio.measure.OSArgument.makeDoubleArgument("glass_front_emissivity", True)
        glass_front_emissivity.setDisplayName("Glass Front Side IR Emissivity")
        glass_front_emissivity.setDescription(
            "Front side infrared hemispherical emissivity of the glass pane (0.0-1.0). Set to 0.0 to use "
            "default value of 0.84 for typical uncoated clear glass. This value affects radiative heat "
            "transfer. Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 13 lists uncoated "
            "glass emissivity as 0.84. Arasteh, D., et al. (1989) 'A versatile procedure for calculating "
            "heat transfer through windows' ASHRAE Transactions, 95(2), 755-765, uses 0.84 for standard "
            "glass. ISO 10292:1994 'Glass in building - Calculation of steady-state U values' specifies "
            "0.837 for uncoated glass surfaces. EN 673:2011 'Glass in building - Determination of thermal "
            "transmittance (U value)' uses 0.837 (often rounded to 0.84).")
        glass_front_emissivity.setDefaultValue(0.84)
        args.append(glass_front_emissivity)

        glass_back_emissivity = openstudio.measure.OSArgument.makeDoubleArgument("glass_back_emissivity", True)
        glass_back_emissivity.setDisplayName("Glass Back Side IR Emissivity")
        glass_back_emissivity.setDescription(
            "Back side infrared hemispherical emissivity of the glass pane (0.0-1.0). Set to 0.0 to use "
            "default value of 0.84 for typical uncoated clear glass. This value affects radiative heat "
            "transfer. Sources: Same as front side - uncoated glass has identical emissivity on both surfaces. "
            "ASHRAE Handbook - Fundamentals (2017) Chapter 15, NFRC 301-2019 'Standard Test Method for "
            "Emittance of Specular Surfaces', and ISO 10292:1994 all specify 0.84 (or 0.837) for both "
            "surfaces of uncoated soda-lime glass.")
        glass_back_emissivity.setDefaultValue(0.84)
        args.append(glass_back_emissivity)

        glass_front_solar_reflectance = openstudio.measure.OSArgument.makeDoubleArgument(
            "glass_front_solar_reflectance", True)
        glass_front_solar_reflectance.setDisplayName("Glass Front Side Solar Reflectance")
        glass_front_solar_reflectance.setDescription(
            "Front side solar reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value "
            "of 0.071 for typical 3mm clear glass. This value affects solar heat gain reflection. Sources: "
            "ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 lists clear glass (3 mm) front solar "
            "reflectance as 0.07. Rubin, M. (1985) 'Optical properties of soda lime silica glasses' Solar "
            "Energy Materials, 12(4), 275-288, reports 0.070-0.075 for standard float glass at normal "
            "incidence. ISO 9050:2003 testing methodology yields 0.07-0.08 for clear glass front surface "
            "reflectance.")
        glass_front_solar_reflectance.setDefaultValue(0.075)
        args.append(glass_front_solar_reflectance)

        glass_back_solar_reflectance = openstudio.measure.OSArgument.makeDoubleArgument(
            "glass_back_solar_reflectance", True)
        glass_back_solar_reflectance.setDisplayName("Glass Back Side Solar Reflectance")
        glass_back_solar_reflectance.setDescription(
            "Back side solar reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of "
            "0.071 for typical 3mm clear glass. This value affects solar heat gain reflection. Sources: Same "
            "as front side - uncoated clear glass has symmetric optical properties. ASHRAE Handbook - "
            "Fundamentals (2017) Chapter 15 specifies identical front and back solar reflectance for uncoated "
            "glass. Rubin, M. (1985) confirms 0.07-0.075 for both surfaces of standard soda-lime glass.")
        glass_back_solar_reflectance.setDefaultValue(0.075)
        args.append(glass_back_solar_reflectance)

        glass_front_visible_reflectance = openstudio.measure.OSArgument.makeDoubleArgument(
            "glass_front_visible_reflectance", True)
        glass_front_visible_reflectance.setDisplayName("Glass Front Side Visible Reflectance")
        glass_front_visible_reflectance.setDescription(
            "Front side visible reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value "
            "of 0.080 for typical 3mm clear glass. This value affects visible light reflection and glare. "
            "Sources: ASHRAE Handbook - Fundamentals (2017) Chapter 15, Table 15 lists clear glass (3 mm) "
            "visible reflectance as 0.08. NFRC 300-2017 testing yields 0.08 for standard clear glass. "
            "McCluney, R. (1996) 'Introduction to Radiometry and Photometry' reports clear float glass visible "
            "reflectance of 0.08 at normal incidence. Pilkington technical specifications list 0.08 for "
            "Optifloat Clear glass.")
        glass_front_visible_reflectance.setDefaultValue(0.081)
        args.append(glass_front_visible_reflectance)

        glass_back_visible_reflectance = openstudio.measure.OSArgument.makeDoubleArgument(
            "glass_back_visible_reflectance", True)
        glass_back_visible_reflectance.setDisplayName("Glass Back Side Visible Reflectance")
        glass_back_visible_reflectance.setDescription(
            "Back side visible reflectance at normal incidence (0.0-1.0). Set to 0.0 to use default value of "
            "0.080 for typical 3mm clear glass. This value affects visible light reflection from interior side. "
            "Sources: Same as front side - uncoated clear glass exhibits symmetric visible reflectance. ASHRAE "
            "Handbook - Fundamentals (2017) Chapter 15, NFRC 300-2017, and ISO 9050:2003 all specify identical "
            "front and back visible reflectance (0.08) for uncoated soda-lime glass.")
        glass_back_visible_reflectance.setDefaultValue(0.081)
        args.append(glass_back_visible_reflectance)

        # Create argument for GWP statistic selection.
        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        args.append(gwp_statistic)

        # Create argument for EC3 API token.
        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database. "
                              "Get token from https://buildingtransparency.org. "
                              "SECURITY: Do not share this token; keep it private. "
                              "For CI/CD, use EC3_API_TOKEN environment variable instead.")
        api_key.setDefaultValue("Obtain the API key from EC3 website")
        args.append(api_key)

        # Create argument for weatherstrip length per declared unit.
        # 17' = 5.1816 m for silicone adhesive smoke gasket, source: https://buildingtransparency.org/ec3/epds/ec327rq0
        length_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit", True)
        length_per_unit.setDisplayName("Length per Unit of Strip")
        length_per_unit.setDescription(
            "Length per unit of window sash strip in m. Default value 5.1816 m is provided based on the "
            "product 'Silicone Adhesive Smoke Gasket' from EC3 database, which has a length of 17 feet per "
            "declared functional unit in EPD.")
        length_per_unit.setDefaultValue(5.1816)
        args.append(length_per_unit)

        # Create argument for number of horizontal dividers.
        num_horizontal_dividers = openstudio.measure.OSArgument.makeIntegerArgument("num_horizontal_dividers", True)
        num_horizontal_dividers.setDisplayName("Number of Horizontal Dividers (Muntins)")
        num_horizontal_dividers.setDescription(
            "Number of horizontal dividers (muntins) in each window. Set to -1 to use values from the "
            "model's WindowPropertyFrameAndDivider objects. When set to a non-negative value, this overrides "
            "the model values and applies uniformly to all windows.")
        num_horizontal_dividers.setDefaultValue(-1)
        args.append(num_horizontal_dividers)

        # Create argument for number of vertical dividers.
        num_vertical_dividers = openstudio.measure.OSArgument.makeIntegerArgument("num_vertical_dividers", True)
        num_vertical_dividers.setDisplayName("Number of Vertical Dividers (Muntins)")
        num_vertical_dividers.setDescription(
            "Number of vertical dividers (muntins) in each window. Set to -1 to use values from the model's "
            "WindowPropertyFrameAndDivider objects. When set to a non-negative value, this overrides the "
            "model values and applies uniformly to all windows.")
        num_vertical_dividers.setDefaultValue(-1)
        args.append(num_vertical_dividers)

        # ============================================================================
        # ENERGY PERFORMANCE GUARD ARGUMENTS - Prevent non-beneficial glazing updates
        # ============================================================================
        energy_guard_enabled = openstudio.measure.OSArgument.makeBoolArgument("energy_guard_enabled", True)
        energy_guard_enabled.setDisplayName("Enable Energy Performance Guard?")
        energy_guard_enabled.setDescription(
            "If true, compare original vs updated window constructions using proxy metrics and stop "
            "when the updated construction appears worse.")
        energy_guard_enabled.setDefaultValue(True)
        args.append(energy_guard_enabled)

        energy_guard_strict = openstudio.measure.OSArgument.makeBoolArgument("energy_guard_strict", True)
        energy_guard_strict.setDisplayName("Energy Guard Strict Mode?")
        energy_guard_strict.setDescription(
            "If true and proxy metrics cannot be evaluated for a window, the measure fails. "
            "If false, unknown cases are skipped with a warning.")
        energy_guard_strict.setDefaultValue(True)
        args.append(energy_guard_strict)

        energy_guard_check_shgc = openstudio.measure.OSArgument.makeBoolArgument("energy_guard_check_shgc", True)
        energy_guard_check_shgc.setDisplayName("Energy Guard Also Check Solar Transmittance Proxy?")
        energy_guard_check_shgc.setDescription(
            "If true, enforce non-increasing SHGC proxy (approximated from glazing transmittance product) "
            "in addition to U-value proxy checks.")
        energy_guard_check_shgc.setDefaultValue(False)
        args.append(energy_guard_check_shgc)

        energy_guard_u_tolerance = openstudio.measure.OSArgument.makeDoubleArgument("energy_guard_u_tolerance", True)
        energy_guard_u_tolerance.setDisplayName("Energy Guard U-Value Tolerance")
        energy_guard_u_tolerance.setDescription(
            "Allowed increase in U-value proxy (W/m2-K) before failing. Set to 0 for strict non-increase.")
        energy_guard_u_tolerance.setDefaultValue(0.0)
        args.append(energy_guard_u_tolerance)

        energy_guard_shgc_tolerance = openstudio.measure.OSArgument.makeDoubleArgument("energy_guard_shgc_tolerance", True)
        energy_guard_shgc_tolerance.setDisplayName("Energy Guard SHGC Proxy Tolerance")
        energy_guard_shgc_tolerance.setDescription(
            "Allowed increase in SHGC proxy before failing when SHGC checks are enabled.")
        energy_guard_shgc_tolerance.setDefaultValue(0.0)
        args.append(energy_guard_shgc_tolerance)

        # ============================================================================
        # COST DATA ARGUMENTS - User-provided fallback costs when RSMeans API fails
        # ============================================================================
        
        # Glass/Glazing cost
        glass_cost_per_cf = openstudio.measure.OSArgument.makeDoubleArgument("glass_cost_per_cf", True)
        glass_cost_per_cf.setDisplayName("Glass Replacement Cost ($/CF)")
        glass_cost_per_cf.setDescription(
            "User-provided unit cost for glass replacement in dollars per cubic foot. "
            "This is used as a fallback when RSMeans API lookup fails or returns no results. "
            "Typical range: $500-1200/CF depending on glass type. Set to 0 to skip cost calculation for glass.")
        glass_cost_per_cf.setDefaultValue(0.0)
        args.append(glass_cost_per_cf)

        # Frame cost
        frame_cost_per_sf = openstudio.measure.OSArgument.makeDoubleArgument("frame_cost_per_sf", True)
        frame_cost_per_sf.setDisplayName("Window Frame Cost ($/SF)")
        frame_cost_per_sf.setDescription(
            "User-provided unit cost for window frame replacement in dollars per square foot. "
            "This is used as a fallback when RSMeans API lookup fails. "
            "Typical range: $20-40/SF depending on frame material (wood, aluminum, vinyl). Set to 0 to skip.")
        frame_cost_per_sf.setDefaultValue(0.0)
        args.append(frame_cost_per_sf)

        # Caulking cost
        caulking_cost_per_cy = openstudio.measure.OSArgument.makeDoubleArgument("caulking_cost_per_cy", True)
        caulking_cost_per_cy.setDisplayName("Caulking Cost ($/CY)")
        caulking_cost_per_cy.setDescription(
            "User-provided unit cost for caulking/sealant in dollars per cubic yard. "
            "Typical range: $100-200/CY. Set to 0 to skip cost calculation for caulking.")
        caulking_cost_per_cy.setDefaultValue(0.0)
        args.append(caulking_cost_per_cy)

        # Film cost
        film_cost_per_sf = openstudio.measure.OSArgument.makeDoubleArgument("film_cost_per_sf", True)
        film_cost_per_sf.setDisplayName("Glazing Film Cost ($/SF)")
        film_cost_per_sf.setDescription(
            "User-provided unit cost for glazing film in dollars per square foot. "
            "Used when custom costs are enabled or RSMeans lookup fails. "
            "Set to 0 to skip cost calculation for film."
        )
        film_cost_per_sf.setDefaultValue(0.0)
        args.append(film_cost_per_sf)

        # Weatherstrip cost
        weatherstrip_cost_per_lf = openstudio.measure.OSArgument.makeDoubleArgument(
            "weatherstrip_cost_per_lf", True
        )
        weatherstrip_cost_per_lf.setDisplayName("Weatherstrip Cost ($/LF)")
        weatherstrip_cost_per_lf.setDescription(
            "User-provided unit cost for weatherstrip in dollars per linear foot. "
            "Used when custom costs are enabled or RSMeans lookup fails. "
            "Set to 0 to skip cost calculation for weatherstrip."
        )
        weatherstrip_cost_per_lf.setDefaultValue(0.0)
        args.append(weatherstrip_cost_per_lf)

        # Labor cost
        labor_cost_multiplier = openstudio.measure.OSArgument.makeDoubleArgument("labor_cost_multiplier", True)
        labor_cost_multiplier.setDisplayName("Labor Cost Multiplier (applies to custom material cost)")
        labor_cost_multiplier.setDescription(
            "Total installed cost as a multiple of custom material cost. labor = material × (multiplier − 1). "
            "Must be ≥ 1.0. Default 1.0 means no separate labor cost. "
            "e.g. 1.5 = installed cost is 1.5× material, meaning labor is 50% of material cost.")
        labor_cost_multiplier.setDefaultValue(1.0)
        args.append(labor_cost_multiplier)

        # Use custom costs instead of RSMeans API
        use_custom_costs = openstudio.measure.OSArgument.makeBoolArgument("use_custom_costs", True)
        use_custom_costs.setDisplayName("Use Custom Cost Inputs?")
        use_custom_costs.setDescription(
            "If true, skip RSMeans API lookup and use the custom cost inputs below. "
            "If false, the measure will attempt RSMeans API first and fall back to custom costs only if it fails.")
        use_custom_costs.setDefaultValue(False)
        args.append(use_custom_costs)

        # Optional: Use specific RSMeans line item IDs instead of closest-match search
        use_specific_rsmeans_line_item_ids = openstudio.measure.OSArgument.makeBoolArgument(
            "use_specific_rsmeans_line_item_ids", True
        )
        use_specific_rsmeans_line_item_ids.setDisplayName("Use Specific RSMeans Line Item IDs?")
        use_specific_rsmeans_line_item_ids.setDescription(
            "If true, the measure will use the RSMeans line item IDs provided below for exact matching. "
            "If false, the measure will search for the closest match in RSMeans catalogs.")
        use_specific_rsmeans_line_item_ids.setDefaultValue(False)
        args.append(use_specific_rsmeans_line_item_ids)

        rsmeans_id_glazing = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_glazing", True)
        rsmeans_id_glazing.setDisplayName("RSMeans Line Item ID - Glazing")
        rsmeans_id_glazing.setDescription(
            "Optional RSMeans line item ID for window glazing. Leave blank to use closest-match search.")
        rsmeans_id_glazing.setDefaultValue("")
        args.append(rsmeans_id_glazing)

        rsmeans_id_frame = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_frame", True)
        rsmeans_id_frame.setDisplayName("RSMeans Line Item ID - Frame")
        rsmeans_id_frame.setDescription(
            "Optional RSMeans line item ID for window frame. Leave blank to use closest-match search.")
        rsmeans_id_frame.setDefaultValue("")
        args.append(rsmeans_id_frame)

        rsmeans_id_caulking = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_caulking", True)
        rsmeans_id_caulking.setDisplayName("RSMeans Line Item ID - Caulking")
        rsmeans_id_caulking.setDescription(
            "Optional RSMeans line item ID for caulking/sealant. Leave blank to use closest-match search.")
        rsmeans_id_caulking.setDefaultValue("")
        args.append(rsmeans_id_caulking)

        rsmeans_id_film = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_film", True)
        rsmeans_id_film.setDisplayName("RSMeans Line Item ID - Film")
        rsmeans_id_film.setDescription(
            "Optional RSMeans line item ID for glazing film. Leave blank to use closest-match search.")
        rsmeans_id_film.setDefaultValue("")
        args.append(rsmeans_id_film)

        rsmeans_id_weatherstrip = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_weatherstrip", True)
        rsmeans_id_weatherstrip.setDisplayName("RSMeans Line Item ID - Weatherstrip")
        rsmeans_id_weatherstrip.setDescription(
            "Optional RSMeans line item ID for weatherstrip. Leave blank to use closest-match search.")
        rsmeans_id_weatherstrip.setDefaultValue("")
        args.append(rsmeans_id_weatherstrip)

        rsmeans_id_secondary_glazing = openstudio.measure.OSArgument.makeStringArgument("rsmeans_id_secondary_glazing", True)
        rsmeans_id_secondary_glazing.setDisplayName("RSMeans Line Item ID - Secondary Glazing")
        rsmeans_id_secondary_glazing.setDescription(
            "Optional RSMeans line item ID for secondary glazing. Leave blank to use closest-match search.")
        rsmeans_id_secondary_glazing.setDefaultValue("")
        args.append(rsmeans_id_secondary_glazing)

        use_custom_gwp = openstudio.measure.OSArgument.makeBoolArgument("use_custom_gwp", True)
        use_custom_gwp.setDisplayName("Use Custom GWP Inputs (skip EC3)")
        use_custom_gwp.setDefaultValue(False)
        args.append(use_custom_gwp)

        custom_glass_gwp_per_m3 = openstudio.measure.OSArgument.makeDoubleArgument("custom_glass_gwp_per_m3", True)
        custom_glass_gwp_per_m3.setDisplayName("Custom Glass GWP (kgCO2eq/m3)")
        custom_glass_gwp_per_m3.setDefaultValue(0.0)
        args.append(custom_glass_gwp_per_m3)

        custom_frame_gwp_per_m2 = openstudio.measure.OSArgument.makeDoubleArgument("custom_frame_gwp_per_m2", True)
        custom_frame_gwp_per_m2.setDisplayName("Custom Frame GWP (kgCO2eq/m2)")
        custom_frame_gwp_per_m2.setDefaultValue(0.0)
        args.append(custom_frame_gwp_per_m2)

        custom_caulking_gwp_per_m3 = openstudio.measure.OSArgument.makeDoubleArgument("custom_caulking_gwp_per_m3", True)
        custom_caulking_gwp_per_m3.setDisplayName("Custom Caulking GWP (kgCO2eq/m3)")
        custom_caulking_gwp_per_m3.setDefaultValue(0.0)
        args.append(custom_caulking_gwp_per_m3)

        custom_weatherstrip_gwp_per_m = openstudio.measure.OSArgument.makeDoubleArgument("custom_weatherstrip_gwp_per_m", True)
        custom_weatherstrip_gwp_per_m.setDisplayName("Custom Weatherstrip GWP (kgCO2eq/m)")
        custom_weatherstrip_gwp_per_m.setDefaultValue(0.0)
        args.append(custom_weatherstrip_gwp_per_m)

        custom_film_gwp_per_m2 = openstudio.measure.OSArgument.makeDoubleArgument("custom_film_gwp_per_m2", True)
        custom_film_gwp_per_m2.setDisplayName("Custom Film GWP (kgCO2eq/m2)")
        custom_film_gwp_per_m2.setDefaultValue(0.0)
        args.append(custom_film_gwp_per_m2)

        # ============================================================================
        # SIMPLE GLAZING MODIFICATION PARAMETERS
        # ============================================================================
        # These parameters only apply to windows with Simple Glazing constructions.
        
        u_factor_modification_percentage = openstudio.measure.OSArgument.makeDoubleArgument(
            "u_factor_modification_percentage", True)
        u_factor_modification_percentage.setDisplayName("U Factor Modification (%)")
        u_factor_modification_percentage.setDescription(
            "【ONLY for Simple Glazing】 Percentage modification of U-factor. "
            "Negative values improve thermal performance (lower heat loss). "
            "Range: [-50%, +50%]. Default: 0.0 (no modification). "
            "Formula: new_U = original_U × (1 + percentage/100). "
            "This parameter has NO EFFECT on Layered Constructions.")
        u_factor_modification_percentage.setDefaultValue(0.0)
        args.append(u_factor_modification_percentage)

        shgc_modification_percentage = openstudio.measure.OSArgument.makeDoubleArgument(
            "shgc_modification_percentage", True)
        shgc_modification_percentage.setDisplayName("SHGC Modification (%)")
        shgc_modification_percentage.setDescription(
            "【ONLY for Simple Glazing】 Percentage modification of Solar Heat Gain Coefficient (SHGC). "
            "Negative values reduce solar heat gain (beneficial in cooling climates). "
            "Range: [-50%, +50%]. Default: 0.0 (no modification). "
            "This parameter has NO EFFECT on Layered Constructions.")
        shgc_modification_percentage.setDefaultValue(0.0)
        args.append(shgc_modification_percentage)

        visible_transmittance_modification_percentage = openstudio.measure.OSArgument.makeDoubleArgument(
            "visible_transmittance_modification_percentage", True)
        visible_transmittance_modification_percentage.setDisplayName("Visible Transmittance Modification (%)")
        visible_transmittance_modification_percentage.setDescription(
            "【ONLY for Simple Glazing】 Percentage modification of Visible Transmittance (VT). "
            "Positive values increase daylighting (more transparent). "
            "Negative values reduce daylighting (more opaque). "
            "Range: [-50%, +50%]. Default: 0.0 (no modification). "
            "This parameter has NO EFFECT on Layered Constructions.")
        visible_transmittance_modification_percentage.setDefaultValue(0.0)
        args.append(visible_transmittance_modification_percentage)

        return args

    def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner,
            user_arguments: openstudio.measure.OSArgumentMap):
        super().run(model, runner, user_arguments)

        # Phase 1: Validate arguments and load user inputs.
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Retrieve user inputs
        # for infiltration reduction
        object = runner.getOptionalWorkspaceObjectChoiceValue('space_type', user_arguments, model)
        space_infiltration_reduction_percent = runner.getDoubleArgumentValue(
            "space_infiltration_reduction_percent", user_arguments)
        # Coefficients are read from existing infiltration objects.
        # for EC calculation
        caulking_thickness = runner.getDoubleArgumentValue("caulking_thickness", user_arguments)
        if caulking_thickness == 0.0:
            caulking_thickness = 0.008
            runner.registerInfo("Argument 'caulking_thickness' set to 0.0, using default value 0.008 m.")
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        use_custom_gwp = runner.getBoolArgumentValue("use_custom_gwp", user_arguments)
        custom_glass_gwp_per_m3 = runner.getDoubleArgumentValue("custom_glass_gwp_per_m3", user_arguments)
        custom_frame_gwp_per_m2 = runner.getDoubleArgumentValue("custom_frame_gwp_per_m2", user_arguments)
        custom_caulking_gwp_per_m3 = runner.getDoubleArgumentValue("custom_caulking_gwp_per_m3", user_arguments)
        custom_weatherstrip_gwp_per_m = runner.getDoubleArgumentValue("custom_weatherstrip_gwp_per_m", user_arguments)
        custom_film_gwp_per_m2 = runner.getDoubleArgumentValue("custom_film_gwp_per_m2", user_arguments)
        wf_option = runner.getStringArgumentValue("wf_option", user_arguments)
        caulking_option = runner.getStringArgumentValue("caulking_option", user_arguments)
        film_option = runner.getStringArgumentValue("film_option", user_arguments)
        film_visible_transmittance = runner.getDoubleArgumentValue(
            "film_visible_transmittance", user_arguments)
        film_solar_transmittance = runner.getDoubleArgumentValue(
            "film_solar_transmittance", user_arguments)
        film_thermal_emissivity = runner.getDoubleArgumentValue(
            "film_thermal_emissivity", user_arguments)
        film_thermal_resistance = runner.getDoubleArgumentValue(
            "film_thermal_resistance", user_arguments)
        weatherstrip_option = runner.getStringArgumentValue("weatherstrip_option", user_arguments)
        glass_option = runner.getStringArgumentValue("glass_option", user_arguments)
        secondary_glazing_option = runner.getStringArgumentValue(
            "secondary_glazing_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        glass_lifetime = runner.getIntegerArgumentValue("glass_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgumentValue("wf_lifetime",user_arguments)
        caulking_lifetime = runner.getIntegerArgumentValue("caulking_lifetime",user_arguments)
        film_lifetime = runner.getIntegerArgumentValue("film_lifetime",user_arguments)
        weatherstrip_lifetime = runner.getIntegerArgumentValue("weatherstrip_lifetime",user_arguments)
        overhead_profit_percent = runner.getDoubleArgumentValue("overhead_profit_percent", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        
        # Simple Glazing modification parameters (only applicable to Simple Glazing constructions)
        u_factor_mod_pct = runner.getDoubleArgumentValue("u_factor_modification_percentage", user_arguments)
        shgc_mod_pct = runner.getDoubleArgumentValue("shgc_modification_percentage", user_arguments)
        vt_mod_pct = runner.getDoubleArgumentValue("visible_transmittance_modification_percentage", user_arguments)
        user_num_panes = runner.getIntegerArgumentValue("user_num_panes", user_arguments)
        glass_pane_thickness_input = runner.getDoubleArgumentValue("glass_pane_thickness", user_arguments)
        gap_thickness_input = runner.getDoubleArgumentValue("gap_thickness", user_arguments)
        use_default_glass_thickness = (glass_pane_thickness_input == 0.0)
        use_default_gap_thickness = (gap_thickness_input == 0.0)
        glass_pane_thickness = glass_pane_thickness_input
        gap_thickness = gap_thickness_input
        if use_default_glass_thickness:
            glass_pane_thickness = 0.003
            runner.registerInfo("Argument 'glass_pane_thickness' set to 0.0, using default value 0.003 m.")
        if use_default_gap_thickness:
            gap_thickness = 0.013
            runner.registerInfo("Argument 'gap_thickness' set to 0.0, using default value 0.013 m.")
        glass_solar_transmittance = runner.getDoubleArgumentValue(
            "glass_solar_transmittance", user_arguments)
        glass_visible_transmittance = runner.getDoubleArgumentValue(
            "glass_visible_transmittance", user_arguments)
        glass_front_emissivity = runner.getDoubleArgumentValue("glass_front_emissivity", user_arguments)
        glass_back_emissivity = runner.getDoubleArgumentValue("glass_back_emissivity", user_arguments)
        glass_front_solar_reflectance = runner.getDoubleArgumentValue(
            "glass_front_solar_reflectance", user_arguments)
        glass_back_solar_reflectance = runner.getDoubleArgumentValue(
            "glass_back_solar_reflectance", user_arguments)
        glass_front_visible_reflectance = runner.getDoubleArgumentValue(
            "glass_front_visible_reflectance", user_arguments)
        glass_back_visible_reflectance = runner.getDoubleArgumentValue(
            "glass_back_visible_reflectance", user_arguments)
        length_per_unit_input = runner.getDoubleArgumentValue("length_per_unit", user_arguments)
        use_default_length_per_unit = (length_per_unit_input == 0.0)
        length_per_unit = length_per_unit_input
        if use_default_length_per_unit:
            length_per_unit = 5.1816
            runner.registerInfo("Argument 'length_per_unit' set to 0.0, using default value 5.1816 m.")
        num_horizontal_dividers = runner.getIntegerArgumentValue("num_horizontal_dividers", user_arguments)
        num_vertical_dividers = runner.getIntegerArgumentValue("num_vertical_dividers", user_arguments)

        # Energy performance guard arguments
        energy_guard_enabled = runner.getBoolArgumentValue("energy_guard_enabled", user_arguments)
        energy_guard_strict = runner.getBoolArgumentValue("energy_guard_strict", user_arguments)
        energy_guard_check_shgc = runner.getBoolArgumentValue("energy_guard_check_shgc", user_arguments)
        energy_guard_u_tolerance = runner.getDoubleArgumentValue("energy_guard_u_tolerance", user_arguments)
        energy_guard_shgc_tolerance = runner.getDoubleArgumentValue("energy_guard_shgc_tolerance", user_arguments)
        if energy_guard_u_tolerance < 0.0:
            runner.registerError("Energy guard U-value tolerance must be non-negative.")
            return False
        if energy_guard_shgc_tolerance < 0.0:
            runner.registerError("Energy guard SHGC tolerance must be non-negative.")
            return False
        if use_custom_gwp and min(
            custom_glass_gwp_per_m3,
            custom_frame_gwp_per_m2,
            custom_caulking_gwp_per_m3,
            custom_weatherstrip_gwp_per_m,
            custom_film_gwp_per_m2,
        ) < 0.0:
            runner.registerError("Custom GWP inputs must be non-negative.")
            return False
        
        # Cost-related arguments (user-provided fallback costs)
        use_custom_costs = runner.getBoolArgumentValue("use_custom_costs", user_arguments)
        use_specific_rsmeans_line_item_ids = runner.getBoolArgumentValue(
            "use_specific_rsmeans_line_item_ids", user_arguments
        )
        rsmeans_id_glazing = runner.getStringArgumentValue("rsmeans_id_glazing", user_arguments).strip()
        rsmeans_id_frame = runner.getStringArgumentValue("rsmeans_id_frame", user_arguments).strip()
        rsmeans_id_caulking = runner.getStringArgumentValue("rsmeans_id_caulking", user_arguments).strip()
        rsmeans_id_film = runner.getStringArgumentValue("rsmeans_id_film", user_arguments).strip()
        rsmeans_id_weatherstrip = runner.getStringArgumentValue("rsmeans_id_weatherstrip", user_arguments).strip()
        rsmeans_id_secondary_glazing = runner.getStringArgumentValue(
            "rsmeans_id_secondary_glazing", user_arguments
        ).strip()
        glass_cost_per_cf = runner.getDoubleArgumentValue("glass_cost_per_cf", user_arguments)
        frame_cost_per_sf = runner.getDoubleArgumentValue("frame_cost_per_sf", user_arguments)
        caulking_cost_per_cy = runner.getDoubleArgumentValue("caulking_cost_per_cy", user_arguments)
        film_cost_per_sf = runner.getDoubleArgumentValue("film_cost_per_sf", user_arguments)
        weatherstrip_cost_per_lf = runner.getDoubleArgumentValue("weatherstrip_cost_per_lf", user_arguments)
        labor_cost_multiplier = runner.getDoubleArgumentValue("labor_cost_multiplier", user_arguments)
        has_window_cost_component = any([
            glass_option != "none" and user_num_panes > 0,
            wf_option != "none",
            caulking_option != "none",
            film_option != "none",
            weatherstrip_option != "none",
            secondary_glazing_option != "none",
        ])

        if use_custom_costs:
            runner.registerInfo("Custom cost mode enabled. Will use user-provided cost values instead of RSMeans API.")
            runner.registerInfo(f"  Glass cost: ${glass_cost_per_cf}/CF")
            runner.registerInfo(f"  Frame cost: ${frame_cost_per_sf}/SF")
            runner.registerInfo(f"  Caulking cost: ${caulking_cost_per_cy}/CY")
            runner.registerInfo(f"  Film cost: ${film_cost_per_sf}/SF")
            runner.registerInfo(f"  Weatherstrip cost: ${weatherstrip_cost_per_lf}/LF")
            runner.registerInfo(f"  Labor multiplier: {labor_cost_multiplier}")
            if not has_window_cost_component:
                runner.registerInfo("No window cost component is enabled (all options are 'none'); custom cost values will not be applied.")
        else:
            # Pre-flight warning: RSMeans is the active path. If the user has
            # not supplied any fallback custom rates, the measure will hard-error
            # when RSMeans returns no match. Surface this risk up front.
            if (float(glass_cost_per_cf) <= 0.0
                    and float(frame_cost_per_sf) <= 0.0
                    and float(caulking_cost_per_cy) <= 0.0
                    and float(film_cost_per_sf) <= 0.0
                    and float(weatherstrip_cost_per_lf) <= 0.0):
                runner.registerWarning(
                    "RSMeans cost lookup is the active cost source (use_custom_costs=false) "
                    "but no fallback custom rates have been provided. If RSMeans returns no "
                    "match for the selected components, the measure will fail. Consider "
                    "setting non-zero values for the relevant 'glass_cost_per_cf', "
                    "'frame_cost_per_sf', 'caulking_cost_per_cy', 'film_cost_per_sf', or "
                    "'weatherstrip_cost_per_lf' arguments as a safety net."
                )

        if energy_guard_enabled:
            runner.registerInfo("Energy performance guard enabled.")
            runner.registerInfo(f"  Strict mode: {energy_guard_strict}")
            runner.registerInfo(f"  Check SHGC proxy: {energy_guard_check_shgc}")
            runner.registerInfo(f"  U tolerance: {energy_guard_u_tolerance}")
            runner.registerInfo(f"  SHGC tolerance: {energy_guard_shgc_tolerance}")

        # Check for conflicting renovation options
        if glass_option == "provide user_num_panes" and user_num_panes > 0 and secondary_glazing_option == "install secondary glazing":
            runner.registerWarning("Both glass replacement and secondary glazing are selected. These options conflict - glass replacement creates a new multi-pane window while secondary glazing adds an interior pane to existing windows. Secondary glazing will be disabled to avoid double-counting and construction conflicts.")
            secondary_glazing_option = "none"
            runner.registerInfo("  → Secondary glazing option changed to 'none' due to glass replacement conflict")

        # Validate all user arguments
        if not self.validate_user_arguments_values(runner, analysis_period, glass_lifetime, wf_lifetime, 
                                 caulking_lifetime, film_lifetime, weatherstrip_lifetime, 
                                 caulking_thickness, glass_pane_thickness, 
                                 gap_thickness, length_per_unit, film_visible_transmittance, 
                                 film_solar_transmittance, film_thermal_emissivity, 
                                 film_thermal_resistance, glass_solar_transmittance, 
                                 glass_visible_transmittance, glass_front_emissivity, 
                                 glass_back_emissivity, glass_front_solar_reflectance, 
                                 glass_back_solar_reflectance, glass_front_visible_reflectance, 
                                 glass_back_visible_reflectance, labor_cost_multiplier,
                                 u_factor_mod_pct, shgc_mod_pct, vt_mod_pct):
            return False

        # Effective values may be overridden by RSMeans only when user selected auto/default (0.0).
        effective_glass_pane_thickness = float(glass_pane_thickness)
        effective_gap_thickness = float(gap_thickness)
        effective_length_per_unit = float(length_per_unit)

        # Early RSMeans lookup to infer preferred defaults from matched descriptions.
        if not use_custom_costs:
            seed_materials = []
            try:
                if glass_option != "none" and user_num_panes > 0:
                    glazing_seed = {
                        "name": "window glazing",
                        "description": f"{user_num_panes}-pane glass replacement",
                        "quantity": 100.0,
                        "unit": "SF",
                        "division_code": "08",
                    }
                    glazing_seed["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                        "window glazing",
                        glazing_seed,
                        rsmeans_id_glazing,
                    )
                    glazing_seed["strict_rsmeans_id_only"] = True
                    seed_materials.append(glazing_seed)

                if secondary_glazing_option != "none":
                    second_seed = {
                        "name": "secondary glazing",
                        "description": "secondary glazing installation",
                        "quantity": 100.0,
                        "unit": "SF",
                        "division_code": "08",
                    }
                    second_seed["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                        "secondary glazing",
                        second_seed,
                        rsmeans_id_secondary_glazing,
                    )
                    second_seed["strict_rsmeans_id_only"] = True
                    seed_materials.append(second_seed)
            except ValueError as e:
                runner.registerError(str(e))
                return False

            if weatherstrip_option != "none":
                weather_seed = {
                    "name": "weatherstrip",
                    "description": weatherstrip_option,
                    "quantity": 100.0,
                    "unit": "LF",
                    "division_code": "08",
                }
                if use_specific_rsmeans_line_item_ids and rsmeans_id_weatherstrip:
                    weather_seed["rsmeans_id"] = rsmeans_id_weatherstrip
                seed_materials.append(weather_seed)

            if seed_materials:
                early_rsmeans = self.pull_rsmeans_cost_from_api(
                    runner,
                    seed_materials,
                    use_custom_costs=False,
                    overhead_profit_percent=overhead_profit_percent,
                )
                if early_rsmeans and early_rsmeans.get("status") == "ok":
                    inferred = self._infer_defaults_from_rsmeans_descriptions(
                        runner,
                        early_rsmeans.get("results", {}).get("materials", []),
                        glass_option,
                        secondary_glazing_option,
                        weatherstrip_option,
                    )

                    if use_default_glass_thickness and "glass_thickness_m" in inferred:
                        effective_glass_pane_thickness = inferred["glass_thickness_m"]
                    if use_default_gap_thickness and "gap_thickness_m" in inferred:
                        effective_gap_thickness = inferred["gap_thickness_m"]
                    if use_default_length_per_unit and "length_per_unit_m" in inferred:
                        effective_length_per_unit = inferred["length_per_unit_m"]

        runner.registerInfo(
            "Effective geometric values: "
            f"glass_thickness={effective_glass_pane_thickness:.6f} m, "
            f"gap_thickness={effective_gap_thickness:.6f} m, "
            f"weatherstrip_length_per_unit={effective_length_per_unit:.4f} m"
        )

        ###################### Change model's space infiltration################
        # Process infiltration reduction
        success, altered_instances, affected_area_si, spaces = self.process_infiltration_reduction(
            model, runner, object, space_infiltration_reduction_percent, user_arguments)
        
        if not success:
            return False
        
        ####################### Calculate Embodied Carbon#######################
        sub_surfaces = []
        for space in spaces:
            for surface in space.surfaces():
                for subsurface in surface.subSurfaces():
                    sub_surfaces.append(subsurface)

        # Track window subtype availability for summary note compatibility checks.
        available_window_subsurface_types = {
            "FixedWindow": 0,
            "OperableWindow": 0,
            "Skylight": 0,
        }
        for subsurface in sub_surfaces:
            subtype = subsurface.subSurfaceType()
            if subtype in available_window_subsurface_types:
                available_window_subsurface_types[subtype] += 1
        
        runner.registerInfo("=" * 80)
        runner.registerInfo("SUBSURFACE DISCOVERY")
        runner.registerInfo("=" * 80)
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")

        # Filter window subsurfaces
        runner.registerInfo("-" * 80)
        runner.registerInfo("Filtering window subsurfaces...")
        runner.registerInfo("-" * 80)
        sub_surfaces_to_change = []
        for subsurface in sub_surfaces:
            if subsurface.subSurfaceType() in ["FixedWindow", "OperableWindow", "Skylight"]:
                sub_surfaces_to_change.append(subsurface)
                runner.registerInfo(f"  ✓ Processing window: {subsurface.nameString()}")
            else:
                runner.registerInfo(f"  ✗ Skipping non-window surface: {subsurface.nameString()}")
                continue

        def _is_simple_glazing_in_subsurface(subsurface):
            if not subsurface.construction().is_initialized():
                return False
            construction = subsurface.construction().get()
            if not construction.to_LayeredConstruction().is_initialized():
                return False
            layered = construction.to_LayeredConstruction().get()
            for i in range(layered.numLayers()):
                if layered.getLayer(i).to_SimpleGlazing().is_initialized():
                    return True
            return False

        # Dictionary storing properties of subsurfaces containing window constructions 
        subsurface_dict = {}
        carbon_data_unavailable_tracker = {"count": 0, "reasons": []}
        epd_response_cache = {}
        total_window_constructions = len(sub_surfaces_to_change)
        simple_glazing_objects_count = sum(
            1 for subsurface in sub_surfaces_to_change
            if _is_simple_glazing_in_subsurface(subsurface)
        )

        def _fetch_epd_with_cache(url):
            cache_key = str(url) if url is not None else "__none__"
            if cache_key in epd_response_cache:
                return epd_response_cache[cache_key]
            data = fetch_epd_data(url=url, api_token=api_key)
            epd_response_cache[cache_key] = data
            return data
        
        # Check for Simple Glazing modification parameters and warn if not applicable
        has_simple_glazing_params = (u_factor_mod_pct != 0.0 or shgc_mod_pct != 0.0 or vt_mod_pct != 0.0)
        
        if has_simple_glazing_params:
            runner.registerInfo("\n" + "=" * 80)
            runner.registerInfo("SIMPLE GLAZING MODIFICATION PARAMETERS DETECTED")
            runner.registerInfo("=" * 80)
            runner.registerInfo(f"  U Factor modification: {u_factor_mod_pct:+.2f}%")
            runner.registerInfo(f"  SHGC modification: {shgc_mod_pct:+.2f}%")
            runner.registerInfo(f"  Visible Transmittance modification: {vt_mod_pct:+.2f}%")
            runner.registerInfo("NOTE: These parameters only apply to Simple Glazing constructions.")
        
        # Pre-scan to detect if any windows have Simple Glazing
        has_any_simple_glazing = False
        for subsurface in sub_surfaces_to_change:
            if self.is_simple_glazing_system(runner, subsurface.construction().get() if subsurface.construction().is_initialized() else None):
                has_any_simple_glazing = True
                break
        
        # Warn if parameters are set but no Simple Glazing windows exist
        if has_simple_glazing_params and not has_any_simple_glazing:
            runner.registerWarning(
                "Simple Glazing modification parameters are set (U Factor/SHGC/Visible Transmittance), "
                "but all selected windows use Layered Construction. These parameters will have NO EFFECT. "
                "To use these parameters, please select windows with Simple Glazing constructions.")
        
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("WINDOW RENOVATION PROCESSING")
        runner.registerInfo("=" * 80)
        
        # Loop through layered window construction to collect glass materials
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            runner.registerInfo(f"\n{'─' * 80}")
            runner.registerInfo(f"Processing: {subsurface_name}")
            runner.registerInfo(f"{'─' * 80}")

            original_construction_for_guard = None
            if subsurface.construction().is_initialized():
                original_construction_for_guard = subsurface.construction().get()
            
            # Initialize to None to handle SimpleGlazing case
            layered_construction = None
            is_simple_glazing = False

            if subsurface.construction().is_initialized():
                subsurface_const = subsurface.construction().get()
                is_simple_glazing = self.is_simple_glazing_system(runner, subsurface_const)
                if is_simple_glazing:
                    runner.registerInfo(f"  ℹ SimpleGlazing detected in {subsurface_name}")
                elif subsurface_const.to_LayeredConstruction().is_initialized():
                    layered_construction = subsurface_const.to_LayeredConstruction().get()
            
            # Per-window renovation options.
            glass_option_for_this_window = glass_option
            film_option_for_this_window = film_option
            secondary_glazing_option_for_this_window = secondary_glazing_option
            wf_option_for_this_window = wf_option
            caulking_option_for_this_window = caulking_option
            weatherstrip_option_for_this_window = weatherstrip_option

            # For SimpleGlazing windows, handle based on whether modification parameters are set.
            if is_simple_glazing:
                if u_factor_mod_pct != 0.0 or shgc_mod_pct != 0.0 or vt_mod_pct != 0.0:
                    # Apply Simple Glazing property modifications
                    runner.registerInfo(
                        f"\n  → Applying Simple Glazing property modifications to {subsurface_name}")
                    modified = self.modify_simple_glazing_properties(
                        runner, subsurface, 
                        u_factor_mod_pct, shgc_mod_pct, vt_mod_pct
                    )
                    if modified:
                        runner.registerInfo(
                            f"    ✓ Simple Glazing properties successfully modified "
                            f"(U: {u_factor_mod_pct:+.1f}%, SHGC: {shgc_mod_pct:+.1f}%, VT: {vt_mod_pct:+.1f}%)")
                    else:
                        runner.registerWarning(
                            f"    ✗ Failed to modify Simple Glazing properties for {subsurface_name}")
                else:
                    runner.registerInfo(
                        f"  ℹ Simple Glazing detected in {subsurface_name}. "
                        f"No modification parameters set (u_factor_modification_percentage, "
                        f"shgc_modification_percentage, visible_transmittance_modification_percentage). "
                        f"To modify this window's properties, please set one or more of these parameters.")
                
                # Glass, film, and secondary glazing options remain enabled for SimpleGlazing
                runner.registerInfo(
                    f"  ℹ Simple Glazing detected. Glass replacement and glazing film will be attempted on this window. "
                    f"U-factor/SHGC/VT modifications are also available via parameters.")

            # Determine number of panes to be installed
            if layered_construction is not None or glass_option_for_this_window == "none":
                num_panes, continue_processing = self.determine_num_panes(runner, user_num_panes, glass_option_for_this_window, layered_construction, subsurface)
            else:
                # SimpleGlazing without glass replacement - set num_panes to 0
                num_panes = 0
                continue_processing = True
            if not continue_processing:
                return False
            
            # Initialize subsurface data structure
            subsurface_dict[subsurface_name] = self.initialize_subsurface_data(
                subsurface_name, subsurface, layered_construction, num_panes,
                glass_lifetime, wf_lifetime, caulking_lifetime, film_lifetime,
                weatherstrip_lifetime, wf_option_for_this_window, caulking_option_for_this_window,
                film_option_for_this_window, weatherstrip_option_for_this_window, secondary_glazing_option_for_this_window, runner)
            
            # Calculate material dimensions and quantities
            self.calculate_material_dimensions(runner, subsurface, subsurface_dict[subsurface_name], caulking_thickness, 
                                              num_horizontal_dividers, num_vertical_dividers)

            # Create new window construction if glass_option is not none
            if glass_option_for_this_window != "none" and num_panes > 0:
                runner.registerInfo(f"\n  → Creating new {num_panes}-pane window construction for {subsurface_name}")
                new_construction = self.create_new_window_construction(model, runner, subsurface, num_panes, effective_glass_pane_thickness, effective_gap_thickness,
                                                                       glass_solar_transmittance, glass_visible_transmittance,
                                                                       glass_front_emissivity, glass_back_emissivity,
                                                                       glass_front_solar_reflectance, glass_back_solar_reflectance,
                                                                       glass_front_visible_reflectance, glass_back_visible_reflectance)
                if new_construction is not None:
                    subsurface.setConstruction(new_construction)
                    subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
                    runner.registerInfo(f"    ✓ Applied new construction '{new_construction.nameString()}' to {subsurface_name}")

            # Apply glazing film if requested
            if film_option_for_this_window != "none" and subsurface.construction().is_initialized():
                current_construction = subsurface.construction().get()
                if glass_option_for_this_window != "none":
                    runner.registerInfo(f"\n  → Adding glazing film effects to newly created construction for {subsurface_name}")
                else:
                    runner.registerInfo(f"\n  → Adding glazing film effects to existing layered construction for {subsurface_name}")
                new_construction = self.convert_to_equivalent_layer(model, runner, subsurface, current_construction, film_option_for_this_window,
                                                                      film_visible_transmittance, film_solar_transmittance,
                                                                      film_thermal_emissivity, film_thermal_resistance)
                subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
                subsurface_dict[subsurface_name]["film"]["cost_executed"] = new_construction is not None
            
            # Apply secondary glazing if requested
            if secondary_glazing_option_for_this_window == "install secondary glazing":
                secondary_glazing_applied = False
                if glass_option_for_this_window != "none":
                    runner.registerWarning(f"Both secondary glazing and glass option are selected for {subsurface_name}. Secondary glazing adds a layer to existing windows, while glass option replaces all glass panes. These options conflict. Skipping secondary glazing installation.")
                    subsurface_dict[subsurface_name]["second_glazing"]["renovation_option"] = "none"
                elif subsurface.construction().is_initialized():
                    current_construction = subsurface.construction().get()
                    glazing_count = self.count_glazing_layers(current_construction)
                    if glazing_count == 1:
                        runner.registerInfo(f"\n  → Single-pane construction detected in {subsurface_name}, installing secondary glazing")
                        new_construction = self.add_secondary_glazing(model, runner, subsurface, current_construction, 
                                                                        effective_glass_pane_thickness, effective_gap_thickness,
                                                                        glass_solar_transmittance, glass_visible_transmittance,
                                                                        glass_front_emissivity, glass_back_emissivity,
                                                                        glass_front_solar_reflectance, glass_back_solar_reflectance,
                                                                        glass_front_visible_reflectance, glass_back_visible_reflectance)
                        subsurface_dict[subsurface_name]["glass"]["object"] = new_construction
                        secondary_glazing_applied = True
                    elif glazing_count > 1:
                        runner.registerWarning(f"Construction in {subsurface_name} has {glazing_count} glazing layers, skipping secondary glazing installation (only applies to single-pane)")
                        subsurface_dict[subsurface_name]["second_glazing"]["renovation_option"] = "none"
                    else:
                        runner.registerWarning(f"Unable to determine glazing layers in {subsurface_name}, skipping secondary glazing installation")
                        subsurface_dict[subsurface_name]["second_glazing"]["renovation_option"] = "none"

            if energy_guard_enabled and original_construction_for_guard is not None and subsurface.construction().is_initialized():
                updated_construction_for_guard = subsurface.construction().get()
                guard_ok = self.enforce_energy_performance_guard(
                    runner,
                    subsurface_name,
                    original_construction_for_guard,
                    updated_construction_for_guard,
                    check_shgc=energy_guard_check_shgc,
                    strict=energy_guard_strict,
                    u_tolerance=energy_guard_u_tolerance,
                    shgc_tolerance=energy_guard_shgc_tolerance,
                )
                if not guard_ok:
                    runner.registerError(
                        f"Energy guard failed for {subsurface_name}. "
                        "Stopping to prevent potential performance degradation."
                    )
                    return False

            # Fetch EPD URLs for all materials
            epd_urls = self.fetch_epd_urls(runner, subsurface_name, wf_option_for_this_window, glass_option_for_this_window, num_panes,
                                           caulking_option_for_this_window, film_option_for_this_window, weatherstrip_option_for_this_window, secondary_glazing_option_for_this_window,
                                           subsurface, glass_option_for_this_window)
            
            # Fetch EPD data using generated URLs
            if use_custom_gwp:
                if subsurface_name == sub_surfaces_to_change[0].nameString():
                    runner.registerInfo("Custom GWP mode enabled: skipping EC3 API calls for window carbon calculation.")
                epd_datalist = {
                    "glass": [],
                    "frame": [],
                    "caulking": [],
                    "film": [],
                    "weatherstrip": [],
                    "second_glazing": [],
                }
            else:
                epd_datalist = {
                    "glass": _fetch_epd_with_cache(epd_urls["glass"]),
                    "frame": _fetch_epd_with_cache(epd_urls["frame"]),
                    "caulking": _fetch_epd_with_cache(epd_urls["caulking"]),
                    "film": _fetch_epd_with_cache(epd_urls["film"]),
                    "weatherstrip": _fetch_epd_with_cache(epd_urls["weatherstrip"]),
                    "second_glazing": _fetch_epd_with_cache(epd_urls["second_glazing"])
                }

            # Process EPD data and calculate embodied carbon
            self.process_epd_for_subsurface(runner, subsurface_name, subsurface_dict[subsurface_name], 
                                           epd_datalist, gwp_statistic, analysis_period, 
                                           effective_glass_pane_thickness, effective_length_per_unit,
                                           carbon_data_unavailable_tracker,
                                           use_custom_gwp=use_custom_gwp,
                                           custom_glass_gwp_per_m3=custom_glass_gwp_per_m3,
                                           custom_frame_gwp_per_m2=custom_frame_gwp_per_m2,
                                           custom_caulking_gwp_per_m3=custom_caulking_gwp_per_m3,
                                           custom_weatherstrip_gwp_per_m=custom_weatherstrip_gwp_per_m,
                                           custom_film_gwp_per_m2=custom_film_gwp_per_m2)

            runner.registerValue(f"{subsurface_name}_total_embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]['window_renovation_embodied_carbon_kg_co2_eq'], "kg CO2 eq")
            runner.registerInfo(f"\n{'─' * 80}")
            runner.registerInfo(f"  TOTAL EMBODIED CARBON FOR {subsurface_name}:")
            runner.registerInfo(f"  {subsurface_dict[subsurface_name]['window_renovation_embodied_carbon_kg_co2_eq']:.2f} kg CO2 eq")
            runner.registerInfo(f"{'─' * 80}")

        # Calculate total embodied carbon
        total_embodied_carbon = sum(
            subsurface_dict[name]["window_renovation_embodied_carbon_kg_co2_eq"] 
            for name in subsurface_dict.keys()
        )
        
        # Count windows with various renovations
        windows_with_glass_upgrade = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["glass"]["renovation_option"] > 0
        )
        windows_with_frame_replacement = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["frame"]["renovation_option"] != "none"
        )
        windows_with_film = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["film"]["renovation_option"] != "none"
        )
        windows_with_caulking = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["caulking"]["renovation_option"] != "none"
        )
        windows_with_weatherstrip = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["weatherstrip"]["renovation_option"] != "none"
        )
        windows_with_secondary_glazing = sum(
            1 for name in subsurface_dict.keys() 
            if subsurface_dict[name]["second_glazing"]["renovation_option"] != "none"
        )
        
        # Calculate total material quantities
        total_window_area_m2 = sum(
            subsurface_dict[name]["dimension"]["area_m2"] 
            for name in subsurface_dict.keys()
        )
        
        total_glazing_area_m2 = sum(
            subsurface_dict[name]["glass"]["area_m2"] 
            for name in subsurface_dict.keys()
        )

        executed_glazing_area_m2 = sum(
            subsurface_dict[name]["glass"]["area_m2"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["glass"]["renovation_option"] > 0
        )

        executed_secondary_glazing_area_m2 = sum(
            subsurface_dict[name]["second_glazing"]["area_m2"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["second_glazing"]["renovation_option"] != "none"
        )

        executed_film_area_m2 = sum(
            subsurface_dict[name]["film"]["area_m2"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["film"].get("cost_executed", False)
        )
        
        total_frame_area_m2 = sum(
            subsurface_dict[name]["frame"]["area_m2"] 
            for name in subsurface_dict.keys()
        )

        executed_frame_area_m2 = sum(
            subsurface_dict[name]["frame"]["area_m2"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["frame"]["renovation_option"] != "none"
        )

        executed_frame_window_count = sum(
            1
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["frame"]["renovation_option"] != "none"
        )

        total_perimeter_m = sum(
            subsurface_dict[name]["dimension"]["perimeter_m"] 
            for name in subsurface_dict.keys()
        )
        
        total_caulking_volume_m3 = sum(
            subsurface_dict[name]["caulking"]["volume_m3"] 
            for name in subsurface_dict.keys()
        )

        executed_caulking_volume_m3 = sum(
            subsurface_dict[name]["caulking"]["volume_m3"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["caulking"]["renovation_option"] != "none"
        )

        # Total caulking bead length used for RSMeans cost lookup. RSMeans
        # joint-sealant cost-lines are priced per LF, not per CY, so cost
        # quantity must be in LF to avoid mis-pricing (a CY-keyed lookup
        # silently picks up an LF-priced line and returns ~$0).
        executed_caulking_length_m = sum(
            subsurface_dict[name]["caulking"]["length_m"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["caulking"]["renovation_option"] != "none"
        )
        
        # Calculate total weatherstrip length (only operable windows)
        total_weatherstrip_length_m = 0.0
        for name in subsurface_dict.keys():
            if subsurface_dict[name]["subsurface_object"].subSurfaceType() == "OperableWindow":
                # Weatherstrip applied to sliding edge (minimum of length and width)
                total_weatherstrip_length_m += subsurface_dict[name]["weatherstrip"]["length_m"]

        executed_weatherstrip_length_m = sum(
            subsurface_dict[name]["weatherstrip"]["length_m"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name]["weatherstrip"]["renovation_option"] != "none"
        )
        
        # Store basic measure input in building's additional properties
        building = model.getBuilding()
        basic_input = building.additionalProperties()
        # Store renovation options in site's additional properties
        site = model.getSite()
        reno_detail = site.additionalProperties()
        # Store emission factors and cost factors in facility's additional properties
        facility = model.getFacility()
        factors = facility.additionalProperties()
        # Store carbon and cost results in simulation control's additional properties
        simcontrol = model.getSimulationControl()
        results = simcontrol.additionalProperties()
        # Store construction material properties in SizingParameters's additional properties
        sizingpara = model.getSizingParameters()
        mtrl_prop = sizingpara.additionalProperties()
        (
            basic_input_features,
            reno_detail_features,
            mtrl_prop_features,
            factors_features,
            results_features,
        ) = self._initialize_additional_property_feature_maps(
            analysis_period=analysis_period,
            gwp_statistic=gwp_statistic,
            space_infiltration_reduction_percent=space_infiltration_reduction_percent,
            total_weatherstrip_length_m=total_weatherstrip_length_m,
            total_window_area_m2=total_window_area_m2,
            total_glazing_area_m2=total_glazing_area_m2,
            total_frame_area_m2=total_frame_area_m2,
            total_perimeter_m=total_perimeter_m,
            total_caulking_volume_m3=total_caulking_volume_m3,
            glass_pane_thickness=glass_pane_thickness,
            gap_thickness=gap_thickness,
            wf_option=wf_option,
            caulking_option=caulking_option,
            film_option=film_option,
            weatherstrip_option=weatherstrip_option,
            glass_option=glass_option,
            secondary_glazing_option=secondary_glazing_option,
            glass_lifetime=glass_lifetime,
            wf_lifetime=wf_lifetime,
            caulking_lifetime=caulking_lifetime,
            film_lifetime=film_lifetime,
            weatherstrip_lifetime=weatherstrip_lifetime,
            total_embodied_carbon=total_embodied_carbon,
            length_per_unit=length_per_unit,
            gwp_source=("custom_user_inputs" if use_custom_gwp else "ec3"),
        )
        reno_detail_features["window_processed_count"] = len(sub_surfaces_to_change)
        reno_detail_features["window_simple_glazing_objects_count"] = simple_glazing_objects_count

        available_window_types_summary = (
            f"available subsurface counts -> "
            f"FixedWindow={available_window_subsurface_types['FixedWindow']}, "
            f"OperableWindow={available_window_subsurface_types['OperableWindow']}, "
            f"Skylight={available_window_subsurface_types['Skylight']}"
        )
        construction_counts_summary = (
            f"window constructions={total_window_constructions}, "
            f"simple glazing objects={simple_glazing_objects_count}"
        )
        selected_window_renovation = any([
            glass_option != "none",
            wf_option != "none",
            caulking_option != "none",
            film_option != "none",
            weatherstrip_option != "none",
            secondary_glazing_option != "none",
        ])

        conflict_reasons = []
        conflict_reason_set = set()

        def _add_conflict(reason):
            if reason and reason not in conflict_reason_set:
                conflict_reason_set.add(reason)
                conflict_reasons.append(reason)

        processed_window_count = len(sub_surfaces_to_change)
        no_supported_window_subsurfaces = processed_window_count == 0
        no_operable_windows = available_window_subsurface_types["OperableWindow"] == 0
        has_simple_glazing = simple_glazing_objects_count > 0
        all_windows_simple_glazing = has_simple_glazing and processed_window_count > 0 and simple_glazing_objects_count == processed_window_count

        if selected_window_renovation and no_supported_window_subsurfaces:
            _add_conflict("No supported window subsurfaces found for selected renovation options")

        if weatherstrip_option != "none" and no_operable_windows:
            _add_conflict("Weatherstrip selected but no OperableWindow subsurfaces found")

        def _append_simple_glazing_conflicts(option_selected, option_label):
            if not option_selected:
                return
            if all_windows_simple_glazing:
                _add_conflict(f"{option_label} selected but all window constructions are SimpleGlazing")
            elif has_simple_glazing:
                _add_conflict(
                    f"{option_label} partially blocked by SimpleGlazing windows "
                    f"({simple_glazing_objects_count}/{processed_window_count})"
                )

        requested_actions = []
        if glass_option != "none":
            requested_actions.append(f"glass upgrade ({glass_option})")
        if wf_option != "none":
            requested_actions.append(f"frame upgrade ({wf_option})")
        if caulking_option != "none":
            requested_actions.append(f"caulking ({caulking_option})")
        if film_option != "none":
            requested_actions.append(f"film ({film_option})")
        if weatherstrip_option != "none":
            requested_actions.append(f"weatherstrip ({weatherstrip_option})")
        if secondary_glazing_option != "none":
            requested_actions.append(f"secondary glazing ({secondary_glazing_option})")

        if requested_actions:
            requested_summary = ", ".join(requested_actions)
        else:
            requested_summary = "no window renovation options"

        if conflict_reasons:
            summary_notes = (
                "Requested: "
                + requested_summary
                + ". Outcome: Completed with option conflicts; one or more requested actions were skipped or partially applied. "
                + "Reason(s): "
                + " | ".join(conflict_reasons)
                + ". Context: "
                + construction_counts_summary
                + "; "
                + available_window_types_summary
                + "."
            )
        else:
            summary_notes = (
                "Requested: "
                + requested_summary
                + ". Outcome: Window enhancement completed without option conflicts. Context: "
                + construction_counts_summary
                + "; "
                + available_window_types_summary
                + "."
            )

        reno_detail_features["window_summary_notes"] = summary_notes
        reno_detail_features["window_weatherstrip_length_per_unit"] = length_per_unit
   
        # Phase 2: Build normalized material payload for RSMeans lookup.
        try:
            materials = self._build_rsmeans_material_payload(
                total_glazing_area_m2=executed_glazing_area_m2,
                total_secondary_glazing_area_m2=executed_secondary_glazing_area_m2,
                total_film_area_m2=executed_film_area_m2,
                total_frame_area_m2=executed_frame_area_m2,
                total_caulking_volume_m3=executed_caulking_volume_m3,
                total_caulking_length_m=executed_caulking_length_m,
                total_weatherstrip_length_m=executed_weatherstrip_length_m,
                glass_option=glass_option,
                wf_option=wf_option,
                caulking_option=caulking_option,
                film_option=film_option,
                weatherstrip_option=weatherstrip_option,
                secondary_glazing_option=secondary_glazing_option,
                user_num_panes=user_num_panes,
                effective_glass_pane_thickness=effective_glass_pane_thickness,
                effective_gap_thickness=effective_gap_thickness,
                use_specific_rsmeans_line_item_ids=use_specific_rsmeans_line_item_ids,
                rsmeans_id_glazing=rsmeans_id_glazing,
                rsmeans_id_frame=rsmeans_id_frame,
                rsmeans_id_caulking=rsmeans_id_caulking,
                rsmeans_id_film=rsmeans_id_film,
                rsmeans_id_weatherstrip=rsmeans_id_weatherstrip,
                rsmeans_id_secondary_glazing=rsmeans_id_secondary_glazing,
                num_windows_executed=executed_frame_window_count,
                    total_window_area_m2=total_window_area_m2,
            )
        except ValueError as e:
            runner.registerError(str(e))
            return False

        # Phase 3: Calculate capital cost using RSMeans or custom fallback inputs.
        cost_metrics = self._calculate_cost_metrics(
            runner=runner,
            materials=materials,
            use_custom_costs=use_custom_costs,
            overhead_profit_percent=overhead_profit_percent,
            labor_cost_multiplier=labor_cost_multiplier,
            total_glazing_area_m2=executed_glazing_area_m2,
            total_secondary_glazing_area_m2=executed_secondary_glazing_area_m2,
            total_film_area_m2=executed_film_area_m2,
            total_frame_area_m2=executed_frame_area_m2,
            total_caulking_volume_m3=executed_caulking_volume_m3,
            total_caulking_length_m=executed_caulking_length_m,
            total_weatherstrip_length_m=executed_weatherstrip_length_m,
            glass_cost_per_cf=glass_cost_per_cf,
            frame_cost_per_sf=frame_cost_per_sf,
            caulking_cost_per_cy=caulking_cost_per_cy,
            film_cost_per_sf=film_cost_per_sf,
            weatherstrip_cost_per_lf=weatherstrip_cost_per_lf,
            glass_option=glass_option,
            wf_option=wf_option,
            caulking_option=caulking_option,
            film_option=film_option,
            weatherstrip_option=weatherstrip_option,
            user_num_panes=user_num_panes,
            effective_glass_pane_thickness=effective_glass_pane_thickness,
            secondary_glazing_option=secondary_glazing_option,
            subsurface_dict=subsurface_dict,
            effective_gap_thickness=effective_gap_thickness,
            analysis_period=analysis_period,
            glass_lifetime=glass_lifetime,
            wf_lifetime=wf_lifetime,
            caulking_lifetime=caulking_lifetime,
            film_lifetime=film_lifetime,
            weatherstrip_lifetime=weatherstrip_lifetime,
        )
        if cost_metrics.get("fatal_error", False):
            return False

        total_material_cost = cost_metrics["total_material_cost"]
        total_labor_cost = cost_metrics["total_labor_cost"]
        total_equipment_cost = float(cost_metrics.get("total_equipment_cost", 0.0))
        total_overhead_profit_cost = cost_metrics["total_overhead_profit_cost"]
        total_cost_with_overhead_profit = cost_metrics["total_cost_with_overhead_profit"]
        cost_factor_basis = cost_metrics["cost_factor_basis"]
        rsmeans_material_features = cost_metrics["rsmeans_material_features"]
        rsmeans_glass_cost_per_cf = cost_metrics["rsmeans_glass_cost_per_cf"]
        rsmeans_glass_cost_per_sf = cost_metrics.get("rsmeans_glass_cost_per_sf", "N/A")
        rsmeans_frame_cost_per_sf = cost_metrics["rsmeans_frame_cost_per_sf"]
        rsmeans_caulking_cost_per_cy = cost_metrics["rsmeans_caulking_cost_per_cy"]
        rsmeans_caulking_cost_per_lf = cost_metrics.get("rsmeans_caulking_cost_per_lf", "N/A")
        rsmeans_caulking_pricing_unit_cost = cost_metrics.get("rsmeans_caulking_pricing_unit_cost", "N/A")
        rsmeans_caulking_pricing_unit_uom = cost_metrics.get("rsmeans_caulking_pricing_unit_uom", "N/A")
        rsmeans_film_cost_per_sf = cost_metrics["rsmeans_film_cost_per_sf"]
        rsmeans_weatherstrip_cost_per_lf = cost_metrics["rsmeans_weatherstrip_cost_per_lf"]

        self._update_cost_and_rsmeans_feature_maps(
            results_features=results_features,
            factors_features=factors_features,
            mtrl_prop_features=mtrl_prop_features,
            total_material_cost=total_material_cost,
            total_labor_cost=total_labor_cost,
            total_equipment_cost=total_equipment_cost,
            total_overhead_profit_cost=total_overhead_profit_cost,
            total_cost_with_overhead_profit=total_cost_with_overhead_profit,
            cost_factor_basis=cost_factor_basis,
            overhead_profit_percent=overhead_profit_percent,
            labor_cost_multiplier=labor_cost_multiplier,
            rsmeans_material_features=rsmeans_material_features,
            glass_cost_per_cf=glass_cost_per_cf,
            frame_cost_per_sf=frame_cost_per_sf,
            caulking_cost_per_cy=caulking_cost_per_cy,
            film_cost_per_sf=film_cost_per_sf,
            weatherstrip_cost_per_lf=weatherstrip_cost_per_lf,
            rsmeans_glass_cost_per_cf=rsmeans_glass_cost_per_cf,
            rsmeans_glass_cost_per_sf=rsmeans_glass_cost_per_sf,
            rsmeans_frame_cost_per_sf=rsmeans_frame_cost_per_sf,
            rsmeans_caulking_cost_per_cy=rsmeans_caulking_cost_per_cy,
            rsmeans_caulking_cost_per_lf=rsmeans_caulking_cost_per_lf,
            rsmeans_caulking_pricing_unit_cost=rsmeans_caulking_pricing_unit_cost,
            rsmeans_caulking_pricing_unit_uom=rsmeans_caulking_pricing_unit_uom,
            rsmeans_film_cost_per_sf=rsmeans_film_cost_per_sf,
            rsmeans_weatherstrip_cost_per_lf=rsmeans_weatherstrip_cost_per_lf,
            cost_source=cost_metrics["cost_source"],
        )

        self._update_gwp_and_construction_feature_maps(
            subsurface_dict=subsurface_dict,
            factors_features=factors_features,
            basic_input_features=basic_input_features,
        )

        # Centralized AdditionalProperties write-out for easier review and debugging.
        self._write_features(basic_input, basic_input_features)
        self._write_features(reno_detail, reno_detail_features)
        self._write_features(mtrl_prop, mtrl_prop_features)
        self._write_features(factors, factors_features)
        self._write_features(results, results_features)
        
        runner.registerInfo(f"\n✓ Window enhancement summary stored in building additional properties")
        
        # Build renovation summary list
        renovation_summary = []
        if windows_with_glass_upgrade > 0:
            renovation_summary.append(f"{windows_with_glass_upgrade} glass upgrade(s)")
        if windows_with_frame_replacement > 0:
            renovation_summary.append(f"{windows_with_frame_replacement} frame replacement(s)")
        if windows_with_film > 0:
            renovation_summary.append(f"{windows_with_film} film application(s)")
        if windows_with_caulking > 0:
            renovation_summary.append(f"{windows_with_caulking} caulking application(s)")
        if windows_with_weatherstrip > 0:
            renovation_summary.append(f"{windows_with_weatherstrip} weatherstrip installation(s)")
        if windows_with_secondary_glazing > 0:
            renovation_summary.append(f"{windows_with_secondary_glazing} secondary glazing installation(s)")
        
        affected_area_ip = openstudio.convert(affected_area_si, 'm^2', 'ft^2').get()
        
        # Report final condition
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("MEASURE SUMMARY")
        runner.registerInfo("=" * 80)
        runner.registerInfo(f"Infiltration: Modified {altered_instances} objects affecting {affected_area_si:.2f} m² ({affected_area_ip:.2f} ft²)")
        runner.registerInfo(f"Windows processed: {len(sub_surfaces_to_change)} subsurfaces")
        if renovation_summary:
            runner.registerInfo(f"Renovations applied: {', '.join(renovation_summary)}")
        else:
            runner.registerInfo(f"Renovations applied: None (infiltration reduction only)")
        runner.registerInfo(f"Total embodied carbon: {total_embodied_carbon:.2f} kg CO2 eq")
        runner.registerInfo(f"Cost factor basis: {cost_factor_basis}")
        runner.registerInfo("=" * 80)
        
        if renovation_summary:
            runner.registerFinalCondition(
                f"Window enhancement completed: {altered_instances} infiltration objects modified, "
                f"{len(sub_surfaces_to_change)} windows processed with {', '.join(renovation_summary)}, "
                f"Total EC: {total_embodied_carbon:.2f} kg CO2 eq, Cost factor basis: {cost_factor_basis}"
            )
        else:
            runner.registerFinalCondition(
                f"Window enhancement completed: {altered_instances} infiltration objects modified, "
                f"{len(sub_surfaces_to_change)} windows processed (infiltration only), "
                f"Total EC: {total_embodied_carbon:.2f} kg CO2 eq, Cost factor basis: {cost_factor_basis}"
            )

        return True

    def calculate_custom_costs_from_user_rates(
        self,
        runner,
        total_glazing_area_m2,
        total_secondary_glazing_area_m2,
        total_film_area_m2,
        total_frame_area_m2,
        total_caulking_volume_m3,
        total_weatherstrip_length_m,
        glass_cost_per_cf,
        frame_cost_per_sf,
        caulking_cost_per_cy,
        film_cost_per_sf,
        weatherstrip_cost_per_lf,
        glass_option,
        wf_option,
        caulking_option,
        film_option,
        weatherstrip_option,
        user_num_panes,
        glass_pane_thickness,
        secondary_glazing_option,
        glass_multiplier=1,
        frame_multiplier=1,
        caulking_multiplier=1,
        film_multiplier=1,
        weatherstrip_multiplier=1,
    ):
        """
        Calculate material costs using user-provided unit rates.
        Serves as fallback when RSMeans API fails or is disabled.
        
        Args:
            total_glazing_area_m2: Total glass area in m²
            total_secondary_glazing_area_m2: Total secondary glazing area in m²
            total_film_area_m2: Total glazing film area in m²
            total_frame_area_m2: Total frame area in m²
            total_caulking_volume_m3: Total caulking volume in m³
            total_weatherstrip_length_m: Total weatherstrip length in m
            glass_cost_per_cf: User-provided glass cost ($/CF)
            frame_cost_per_sf: User-provided frame cost ($/SF)
            caulking_cost_per_cy: User-provided caulking cost ($/CY)
            film_cost_per_sf: User-provided film cost ($/SF)
            weatherstrip_cost_per_lf: User-provided weatherstrip cost ($/LF)
            glass_option: Whether glass replacement is selected
            wf_option: Whether frame replacement is selected
            caulking_option: Whether caulking is selected
            film_option: Whether glazing film is selected
            weatherstrip_option: Whether weatherstrip is selected
            user_num_panes: Number of panes used for glass replacement
            glass_pane_thickness: Glass thickness in meters
            secondary_glazing_option: Whether secondary glazing is selected
        
        Returns:
            Total material cost in dollars
        """
        
        def _m2_to_sf(value_m2: float) -> float:
            return value_m2 * 10.7639
        
        def _m3_to_cy(value_m3: float) -> float:
            return value_m3 * 1.30795

        def _m3_to_gal(value_m3: float) -> float:
            return value_m3 * 264.172052

        def _m_to_ft(value_m: float) -> float:
            return value_m * 3.28084

        def _m_to_lf(value_m: float) -> float:
            return value_m * 3.28084
        
        total_cost = 0.0
        
        # Glass replacement cost (volume basis)
        if glass_option != "none" and glass_cost_per_cf > 0 and total_glazing_area_m2 > 0:
            pane_count = max(1, int(user_num_panes)) if user_num_panes and user_num_panes > 0 else 1
            glass_qty_sf = _m2_to_sf(total_glazing_area_m2)
            glass_thickness_ft = _m_to_ft(float(glass_pane_thickness)) if glass_pane_thickness > 0 else 0.0
            glass_qty_cf = glass_qty_sf * glass_thickness_ft * pane_count
            glass_cost = glass_qty_cf * glass_cost_per_cf * glass_multiplier
            total_cost += glass_cost
            runner.registerInfo(
                f"  Glass: {glass_qty_cf:.2f} CF * ${glass_cost_per_cf:.2f}/CF * {glass_multiplier}x lifetime_mult "
                f"(area={glass_qty_sf:.2f} SF, thickness={glass_thickness_ft:.4f} ft, panes={pane_count}) = ${glass_cost:,.2f}"
            )

        # Secondary glazing cost (volume basis)
        if secondary_glazing_option != "none" and glass_cost_per_cf > 0 and total_secondary_glazing_area_m2 > 0:
            secondary_qty_sf = _m2_to_sf(total_secondary_glazing_area_m2)
            secondary_thickness_ft = _m_to_ft(float(glass_pane_thickness)) if glass_pane_thickness > 0 else 0.0
            secondary_qty_cf = secondary_qty_sf * secondary_thickness_ft
            secondary_cost = secondary_qty_cf * glass_cost_per_cf * glass_multiplier
            total_cost += secondary_cost
            runner.registerInfo(
                f"  Secondary glazing: {secondary_qty_cf:.2f} CF * ${glass_cost_per_cf:.2f}/CF * {glass_multiplier}x lifetime_mult "
                f"(area={secondary_qty_sf:.2f} SF, thickness={secondary_thickness_ft:.4f} ft) = ${secondary_cost:,.2f}"
            )
        
        # Frame cost
        if wf_option != "none" and frame_cost_per_sf > 0 and total_frame_area_m2 > 0:
            frame_qty_sf = _m2_to_sf(total_frame_area_m2)
            frame_cost = frame_qty_sf * frame_cost_per_sf * frame_multiplier
            total_cost += frame_cost
            runner.registerInfo(f"  Frame: {frame_qty_sf:.2f} SF * ${frame_cost_per_sf:.2f}/SF * {frame_multiplier}x lifetime_mult = ${frame_cost:,.2f}")
        
        # Caulking cost
        if caulking_option != "none" and caulking_cost_per_cy > 0 and total_caulking_volume_m3 > 0:
            caulking_qty_cy = _m3_to_cy(total_caulking_volume_m3)
            caulking_cost = caulking_qty_cy * caulking_cost_per_cy * caulking_multiplier
            total_cost += caulking_cost
            runner.registerInfo(f"  Caulking: {caulking_qty_cy:.2f} CY * ${caulking_cost_per_cy:.2f}/CY * {caulking_multiplier}x lifetime_mult = ${caulking_cost:,.2f}")

        # Film cost
        if film_option != "none" and film_cost_per_sf > 0 and total_film_area_m2 > 0:
            film_qty_sf = _m2_to_sf(total_film_area_m2)
            film_cost = film_qty_sf * film_cost_per_sf * film_multiplier
            total_cost += film_cost
            runner.registerInfo(
                f"  Film: {film_qty_sf:.2f} SF * ${film_cost_per_sf:.2f}/SF * {film_multiplier}x lifetime_mult = ${film_cost:,.2f}"
            )

        # Weatherstrip cost
        if (
            weatherstrip_option != "none"
            and weatherstrip_cost_per_lf > 0
            and total_weatherstrip_length_m > 0
        ):
            weatherstrip_qty_lf = _m_to_lf(total_weatherstrip_length_m)
            weatherstrip_cost = weatherstrip_qty_lf * weatherstrip_cost_per_lf * weatherstrip_multiplier
            total_cost += weatherstrip_cost
            runner.registerInfo(
                "  Weatherstrip: "
                f"{weatherstrip_qty_lf:.2f} LF * ${weatherstrip_cost_per_lf:.2f}/LF * {weatherstrip_multiplier}x lifetime_mult "
                f"= ${weatherstrip_cost:,.2f}"
            )
        
        return total_cost

    def pull_rsmeans_cost_from_api(
        self,
        runner,
        materials,
        use_custom_costs=False,
        overhead_profit_percent=0.0,
    ):
        """
        Pull RSMeans cost data for retrofit materials using API credentials.
        If use_custom_costs is True, returns an empty dict to signal custom cost mode.
        
        Args:
            runner: OpenStudio measure runner
            materials: List of material dictionaries for RSMeans API (with 'name', 'description', 'quantity', 'unit' keys)
            use_custom_costs: Boolean flag to skip RSMeans API lookup
            
        Returns:
            Dictionary of RSMeans cost results, or empty dict if custom costs enabled
        """
        if use_custom_costs:
            runner.registerInfo("Custom cost mode enabled - skipping RSMeans API lookup.")
            return {}
        
        try:
            # Load the updated call_rsmeans_api module dynamically
            measure_dir = Path(__file__).parent
            rsmeans_helper_path = measure_dir / "resources" / "call_rsmeans_api.py"
            
            if not rsmeans_helper_path.exists():
                runner.registerWarning(f"RSMeans helper not found at {rsmeans_helper_path}. Skipping RSMeans cost retrieval.")
                return {}
            
            spec = importlib.util.spec_from_file_location("call_rsmeans_api", rsmeans_helper_path)
            rsmeans_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rsmeans_module)
            
            runner.registerInfo("Initializing RSMeans API lookup...")
            
            # Use the run_rsmeans_cost_lookup function from the updated module
            result = rsmeans_module.run_rsmeans_cost_lookup(
                materials=materials,
                release_id='2024-an',
                catalogs=['bc-mf', 'gb-mf', 'rp-mf'],
                location_id='us-us-national',
                labor_type='std',
                measurement_system='imp',
                use_sandbox=False,
                overhead_profit_percent=overhead_profit_percent,
            )
            
            if result.get('status') == 'success' or result.get('status') == 'ok':
                summary = result.get('summary', {})
                runner.registerInfo(f"RSMeans API lookup successful:")
                runner.registerInfo(f"  Materials found: {summary.get('materials_count', 0)}")
                runner.registerInfo(f"  Total material cost: ${summary.get('total_material_cost', 0):,.2f}")
                runner.registerInfo(f"  Overhead + Profit ({summary.get('overhead_profit_percent', 0)}%): ${summary.get('total_overhead_profit_cost', 0):,.2f}")
                runner.registerInfo(f"  Total cost with O&P: ${summary.get('total_cost_with_overhead_profit', 0):,.2f}")
                return result
            else:
                runner.registerWarning(f"RSMeans API lookup failed: {result.get('summary', {}).get('error', 'Unknown error')}")
                return {}
                
        except Exception as e:
            runner.registerWarning(f"RSMeans API lookup failed: {str(e)}")
            return {}

    def determine_num_panes(self, runner, user_num_panes, glass_option, layered_construction, subsurface):
        """Figure out how many glass panes (1, 2, or 3) to install in the window.
        
        Uses user input if provided, otherwise counts layers in existing window construction.
        Returns (number_of_panes, True) if successful, or (0, False) if error.
        """
        num_panes = 0

        # If glass replacement is disabled (e.g. user selected 'none' or this
        # subsurface is SimpleGlazing and glass replacement was demoted), then
        # no panes are installed -- regardless of any non-zero user_num_panes.
        # This prevents glass cost/embodied carbon from being billed for a
        # window where glass was never actually replaced.
        if glass_option == "none":
            return 0, True

        if user_num_panes > 0 and user_num_panes <= 3:
            num_panes = user_num_panes
            runner.registerInfo(f"  ℹ Number of panes: {num_panes} (user-specified, applied to all windows)")
        elif user_num_panes > 3:
            num_panes = 3
        elif glass_option != "none" and user_num_panes == 0:
            if layered_construction is None:
                runner.registerError(f"Cannot derive number of panes from SimpleGlazing construction. Please specify num_panes explicitly.")
                return 0, False
            runner.registerInfo("  ℹ Number of panes not specified, deriving from model...")
            if layered_construction.numLayers() == 1:
                num_panes = 1
            elif layered_construction.numLayers() == 3:
                num_panes = 2
            elif layered_construction.numLayers() == 5:
                num_panes = 3
            elif layered_construction.numLayers() in [2,4]:
                runner.registerError(f"Number of layers in {subsurface.nameString()} is {layered_construction.numLayers()}, which is not typical for window construction. Please check the model and provide user_num_panes to avoid ambiguity.")
                return 0, False
            else:
                num_panes = 3
                runner.registerWarning(f"Number of panes derived from model is {layered_construction.numLayers()}, changed to 3 because currently the measure is unable to handle more complex scenarios due to the lack of EPD data.")
        elif user_num_panes < 0:
            runner.registerError("Number of panes provided by user is less than 0, please provide a valid integer.")
            return 0, False
        else:
            num_panes = 0
        
        return num_panes, True

    def initialize_subsurface_data(self, subsurface_name, subsurface, layered_construction, num_panes,
                                   glass_lifetime, wf_lifetime, caulking_lifetime, film_lifetime,
                                   weatherstrip_lifetime, wf_option, caulking_option,
                                   film_option, weatherstrip_option, secondary_glazing_option,
                                   runner):
        """Set up data storage for one window with all renovation details.
        
        Creates nested dictionary to track materials (glass, frame, caulking, film, etc),
        their lifetimes, and renovation options. Returns the initialized dictionary.
        """
        data = {}
        data["window_renovation_embodied_carbon_kg_co2_eq"] = 0.0
        data["window_type"] = subsurface.subSurfaceType()
        
        # Create renovation scenarios for each window type subsurface
        data["glass"] = {}
        data["frame"] = {}
        data["caulking"] = {}
        data["film"] = {}
        data["weatherstrip"] = {}
        data["second_glazing"] = {}
        
        # Assign openstudio model
        data["subsurface_object"] = subsurface
        data["glass"]["object"] = layered_construction
        
        # Assign lifetime values
        data["glass"]["lifetime"] = glass_lifetime
        data["frame"]["lifetime"] = wf_lifetime
        data["caulking"]["lifetime"] = caulking_lifetime
        data["film"]["lifetime"] = film_lifetime
        data["weatherstrip"]["lifetime"] = weatherstrip_lifetime
        data["second_glazing"]["lifetime"] = glass_lifetime
        
        # Assign renovation options
        data["glass"]["renovation_option"] = num_panes
        data["frame"]["renovation_option"] = wf_option
        data["caulking"]["renovation_option"] = caulking_option
        data["film"]["renovation_option"] = film_option
        # Default to not executed; set to True only after successful film application.
        data["film"]["cost_executed"] = False
        if weatherstrip_option != "none" and subsurface.subSurfaceType() != "OperableWindow":
            data["weatherstrip"]["renovation_option"] = "none"
            runner.registerInfo(
                f"  ⚠ Weatherstrip skipped for {subsurface.nameString()} "
                f"(subsurface type: {subsurface.subSurfaceType()}, only OperableWindow is supported)"
            )
        else:
            data["weatherstrip"]["renovation_option"] = weatherstrip_option
        
        data["second_glazing"]["renovation_option"] = secondary_glazing_option
        
        return data

    def calculate_material_dimensions(self, runner, subsurface, subsurface_data, caulking_thickness, 
                                      user_num_horizontal_dividers=-1, user_num_vertical_dividers=-1):
        """Calculate how much material is needed for each renovation component.
        
        Computes areas (glass, frame, film), lengths (weatherstrip, perimeter),
        and volumes (caulking) based on window dimensions. Updates the subsurface_data
        dictionary with calculated values.
        
        Args:
            user_num_horizontal_dividers: User-specified number of horizontal dividers. -1 means use model values.
            user_num_vertical_dividers: User-specified number of vertical dividers. -1 means use model values.
        """
        # Calculate and store subsurface dimension
        subsurface_data["dimension"] = calculate_geometry(self, subsurface)
        
        # Get frame and divider dimensions from model
        frame_width, divider_width, num_hori_divider, num_verti_divider = \
            self.get_frame_and_divider_dimension(runner, subsurface) if subsurface.windowPropertyFrameAndDivider().is_initialized() else (0.0, 0.0, 0, 0)
        
        # Override with user-specified values if provided (non-negative)
        if user_num_horizontal_dividers >= 0:
            num_hori_divider = user_num_horizontal_dividers
            runner.registerInfo(f"  ℹ Using user-specified horizontal dividers: {num_hori_divider}")
        if user_num_vertical_dividers >= 0:
            num_verti_divider = user_num_vertical_dividers
            runner.registerInfo(f"  ℹ Using user-specified vertical dividers: {num_verti_divider}")
        
        window_width = float(subsurface_data["dimension"]["width_m"])
        window_length = float(subsurface_data["dimension"]["length_m"])
        window_area = float(subsurface_data["dimension"]["area_m2"])
        window_perimeter = float(subsurface_data["dimension"]["perimeter_m"])
        
        # Calculate glazing area for applying glazing film
        subsurface_data["film"]["width_m"] = float(window_width - 2 * frame_width - num_verti_divider * divider_width)
        subsurface_data["film"]["length_m"] = float(window_length - 2 * frame_width - num_hori_divider * divider_width)
        subsurface_data["film"]["area_m2"] = subsurface_data["film"]["width_m"] * subsurface_data["film"]["length_m"]
        
        # Calculate caulking material consumption in volume
        caulking_volume = window_perimeter * 0.5 * np.pi * (caulking_thickness/2)**2
        subsurface_data["caulking"]["length_m"] = window_perimeter
        subsurface_data["caulking"]["thickness_m"] = float(caulking_thickness)
        subsurface_data["caulking"]["volume_m3"] = float(caulking_volume)
        
        # Calculate weatherstrip material consumption in length
        strip_length = 0.0
        if subsurface.subSurfaceType() == "OperableWindow":
            strip_length = min(window_length, window_width)
        subsurface_data["weatherstrip"]["length_m"] = float(strip_length)
        
        # Assign window area to glass and window frame
        subsurface_data["glass"]["area_m2"] = subsurface_data["film"]["area_m2"]
        # Frame area is the perimeter strip: total window area minus the inner
        # glazing/film opening. Clamp to zero in case of rounding or when the
        # OS model carries no frame width (frame_width == 0).
        subsurface_data["frame"]["area_m2"] = max(
            0.0, float(window_area) - float(subsurface_data["film"]["area_m2"])
        )
        # For embodied carbon calculation, use the complete window area (GWP factor
        # is based on full window, not frame-only perimeter strip). Stored separately
        # to keep cost calculation using the corrected perimeter area.
        subsurface_data["frame"]["area_m2_for_carbon"] = float(window_area)
        subsurface_data["second_glazing"]["area_m2"] = subsurface_data["film"]["area_m2"]

    def fetch_epd_urls(self, runner, subsurface_name, wf_option, glass_option, num_panes,
                       caulking_option, film_option, weatherstrip_option, secondary_glazing_option,
                       subsurface, glass_option_input):
        """Build EC3 database URLs to fetch environmental data for each material.
        
        Generates search URLs based on material types selected (frame, glass, caulking, etc).
        Returns dictionary mapping material names to their EC3 EPD lookup URLs.
        """
        urls = {}
        
        # Window frame EPD
        urls["frame"] = None
        if wf_option != "none":
            urls["frame"] = generate_url_byname(name_like=wf_option, plant_geography='150')
        
        # Glass pane EPD
        urls["glass"] = None
        if glass_option != "none":
            urls["glass"] = generate_url_byname(
                category='6daae3d967104f5c8c85199b259f58c8',
                name_like='monolithic glass'
            )
        
        # Caulking sealant EPD
        urls["caulking"] = None
        if caulking_option == "acrylic":
            urls["caulking"] = generate_url_byname(name_like='sealant', description_like=caulking_option)
        elif caulking_option == "polyurethane":
            urls["caulking"] = generate_url_byname(category='e95e0d13de844101beb364b47af73d45', description_like='window')
        
        # Glazing film EPD
        urls["film"] = None
        if film_option != "none":
            urls["film"] = generate_url_byname(category='3aa3a34fae9a400fa297339ba88e1fab', name_like=film_option)
        
        # Weatherstrip EPD
        urls["weatherstrip"] = None
        if weatherstrip_option != "none" and subsurface.subSurfaceType() == "OperableWindow":
            urls["weatherstrip"] = generate_url_byname(category='ca54e842c0fc4bf2b4f3a8564c3b1a4d', name_like=weatherstrip_option)
        
        # Secondary glazing EPD
        urls["second_glazing"] = None
        if secondary_glazing_option == "install secondary glazing":
            if glass_option_input != "none":
                runner.registerWarning(f"Both secondary glazing and glass option are selected. Skipping secondary glazing EPD fetch to avoid conflict.")
            elif subsurface.construction().is_initialized():
                current_construction = subsurface.construction().get()
                if self.is_simple_glazing_system(runner, current_construction):
                    runner.registerWarning(f"Simple glazing system detected in {subsurface_name}, skipping secondary glazing EPD fetch.")
                else:
                    glazing_count = self.count_glazing_layers(current_construction)
                    if glazing_count == 1:
                        urls["second_glazing"] = generate_url_byname(category='6daae3d967104f5c8c85199b259f58c8', name_like='monolithic glass')
                    elif glazing_count > 1:
                        runner.registerWarning(f"Construction in {subsurface_name} has {glazing_count} glazing layers, skipping secondary glazing EPD fetch.")
                    else:
                        runner.registerWarning(f"Unable to determine glazing layers in {subsurface_name}, skipping secondary glazing EPD fetch.")
        
        return urls

    def process_epd_for_subsurface(self, runner, subsurface_name, subsurface_data, epd_datalist, 
                                    gwp_statistic, analysis_period, glass_pane_thickness, length_per_unit,
                                    carbon_data_unavailable_tracker=None,
                                    use_custom_gwp=False,
                                    custom_glass_gwp_per_m3=0.0,
                                    custom_frame_gwp_per_m2=0.0,
                                    custom_caulking_gwp_per_m3=0.0,
                                    custom_weatherstrip_gwp_per_m=0.0,
                                    custom_film_gwp_per_m2=0.0):
        """Calculate total embodied carbon (CO2 emissions) for all window materials.
        
        Extracts GWP values and lifetime from EPD data, applies selected statistic (min/max/mean/median),
        multiplies by material quantities and replacement cycles over analysis period.
        Updates subsurface_data with embodied carbon for each material and lifetime from EPD.
        """
        if carbon_data_unavailable_tracker is None:
            carbon_data_unavailable_tracker = {"count": 0, "reasons": []}

        def _mark_carbon_data_unavailable(reason):
            carbon_data_unavailable_tracker["count"] += 1
            if reason not in carbon_data_unavailable_tracker["reasons"]:
                carbon_data_unavailable_tracker["reasons"].append(reason)

        for material_name, epd_data in epd_datalist.items():
            if use_custom_gwp:
                multiplier = lifetime_multiplier(subsurface_data[material_name]["lifetime"], analysis_period)
                subsurface_data[material_name]["gwp_per_m2"] = None
                subsurface_data[material_name]["gwp_per_kg"] = None
                subsurface_data[material_name]["gwp_per_m3"] = None
                subsurface_data[material_name]["gwp_per_m"] = None

                if material_name in ["glass", "second_glazing"]:
                    subsurface_data[material_name]["gwp_per_m3"] = float(custom_glass_gwp_per_m3)
                elif material_name == "frame":
                    subsurface_data[material_name]["gwp_per_m2"] = float(custom_frame_gwp_per_m2)
                elif material_name == "caulking":
                    subsurface_data[material_name]["gwp_per_m3"] = float(custom_caulking_gwp_per_m3)
                elif material_name == "film":
                    subsurface_data[material_name]["gwp_per_m2"] = float(custom_film_gwp_per_m2)
                elif material_name == "weatherstrip":
                    subsurface_data[material_name]["gwp_per_m"] = float(custom_weatherstrip_gwp_per_m)

                embodied_carbon = 0.0
                if material_name == "glass":
                    num_panes_installed = subsurface_data[material_name]["renovation_option"]
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] *
                                            subsurface_data[material_name]["area_m2"] *
                                            glass_pane_thickness * num_panes_installed * multiplier)
                elif material_name == "second_glazing":
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] *
                                            subsurface_data[material_name]["area_m2"] *
                                            glass_pane_thickness * multiplier)
                elif material_name in ["window", "film", "frame"]:
                    if material_name == "film" and not subsurface_data[material_name].get("cost_executed", False):
                        embodied_carbon = 0.0
                    else:
                        if material_name == "frame":
                            area_for_gwp = subsurface_data[material_name].get("area_m2_for_carbon", subsurface_data[material_name]["area_m2"])
                        else:
                            area_for_gwp = subsurface_data[material_name]["area_m2"]
                        embodied_carbon = float(subsurface_data[material_name]["gwp_per_m2"] * area_for_gwp * multiplier)
                elif material_name == "caulking":
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] * subsurface_data[material_name]["volume_m3"] * multiplier)
                elif material_name == "weatherstrip":
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m"] * subsurface_data[material_name]["length_m"] * multiplier)

                subsurface_data[material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                subsurface_data[material_name]["lifetime_source"] = "user_input"
                subsurface_data["window_renovation_embodied_carbon_kg_co2_eq"] += embodied_carbon
                continue

            if epd_data is None or (isinstance(epd_data, list) and len(epd_data) == 0):
                subsurface_data[material_name]["gwp_per_m2"] = None
                subsurface_data[material_name]["gwp_per_kg"] = None
                subsurface_data[material_name]["gwp_per_m3"] = None
                subsurface_data[material_name]["gwp_per_m"] = None
                _mark_carbon_data_unavailable(f"missing_epd_{material_name}")
                runner.registerWarning(
                    f"No EPD data found for {material_name} in {subsurface_name}; "
                    "embodied carbon set to 0 for this material."
                )
                continue

            # Extract GWP, thickness, and lifetime from EPD data
            gwp_values, thickness_summary, lifetime_values = self.extract_gwp_and_thickness_from_epd(length_per_unit, epd_data)
            subsurface_data[material_name]["thickness_list"] = thickness_summary
            
            # Process lifetime from EPD (with fallback to user input)
            user_lifetime = subsurface_data[material_name]["lifetime"]
            if len(lifetime_values) == 0:
                epd_lifetime = user_lifetime
            else:
                # Apply the same statistic method as GWP values
                if len(lifetime_values) == 1:
                    epd_lifetime = lifetime_values[0]
                elif gwp_statistic == "minimum":
                    epd_lifetime = float(np.min(lifetime_values))
                elif gwp_statistic == "maximum":
                    epd_lifetime = float(np.max(lifetime_values))
                elif gwp_statistic == "mean":
                    epd_lifetime = float(np.mean(lifetime_values))
                elif gwp_statistic == "median":
                    epd_lifetime = float(np.median(lifetime_values))
                else:
                    epd_lifetime = float(np.mean(lifetime_values))  # Default to mean
            
            subsurface_data[material_name]["lifetime"] = epd_lifetime
            subsurface_data[material_name]["lifetime_source"] = "EPD" if epd_lifetime != user_lifetime else "user_input"

            # Extract gwp statistics
            for functional_unit, gwp_list in gwp_values.items():
                if len(gwp_list) == 0:
                    gwp = None
                elif len(gwp_list) == 1:
                    gwp = gwp_list[0]
                elif gwp_statistic == "minimum":
                    gwp = float(np.min(gwp_list))
                elif gwp_statistic == "maximum":
                    gwp = float(np.max(gwp_list))
                elif gwp_statistic == "mean":
                    gwp = float(np.mean(gwp_list))
                elif gwp_statistic == "median":
                    gwp = float(np.median(gwp_list))
                subsurface_data[material_name][functional_unit] = gwp
            
            # Multipliers for calculating embodied carbon over analysis period (using updated lifetime)
            multiplier = lifetime_multiplier(subsurface_data[material_name]["lifetime"], analysis_period)

            embodied_carbon = 0.0
            if material_name == "glass":
                if subsurface_data[material_name]["gwp_per_m3"] is None:
                    embodied_carbon = 0.0
                    _mark_carbon_data_unavailable(f"missing_gwp_{material_name}")
                    runner.registerWarning(f"No gwp_per_m3 data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                else:
                    num_panes_installed = subsurface_data[material_name]["renovation_option"]
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] * 
                                           subsurface_data[material_name]["area_m2"] * 
                                           glass_pane_thickness * num_panes_installed * multiplier)
                    runner.registerInfo(f"    • Glass: {num_panes_installed} pane(s) * {glass_pane_thickness*1000:.1f}mm thickness")
            elif material_name == "second_glazing":
                if subsurface_data[material_name]["gwp_per_m3"] is None:
                    embodied_carbon = 0.0
                    _mark_carbon_data_unavailable(f"missing_gwp_{material_name}")
                    runner.registerWarning(f"No gwp_per_m3 data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                else:
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] * 
                                           subsurface_data[material_name]["area_m2"] * 
                                           glass_pane_thickness * multiplier)
                    runner.registerInfo(f"    • Secondary glazing: {glass_pane_thickness*1000:.1f}mm thickness")
            elif material_name in ["window","film","frame"]:
                if material_name == "film" and not subsurface_data[material_name].get("cost_executed", False):
                    embodied_carbon = 0.0
                    runner.registerInfo(
                        f"    ○ Film skipped for {subsurface_name} (not physically applied), assigning 0 embodied carbon."
                    )
                elif subsurface_data[material_name]["gwp_per_m2"] is None:
                    embodied_carbon = 0.0
                    _mark_carbon_data_unavailable(f"missing_gwp_{material_name}")
                    runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                else:
                    # For frame, use the complete window area (GWP factor is per m2
                    # of full window, not frame-only perimeter area). Other materials
                    # use their respective areas as normal.
                    if material_name == "frame":
                        area_for_gwp = subsurface_data[material_name].get("area_m2_for_carbon", subsurface_data[material_name]["area_m2"])
                    else:
                        area_for_gwp = subsurface_data[material_name]["area_m2"]
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m2"] * area_for_gwp * multiplier)
            elif material_name == "caulking":
                if subsurface_data[material_name]["gwp_per_m3"] is None:
                    embodied_carbon = 0.0
                    _mark_carbon_data_unavailable(f"missing_gwp_{material_name}")
                    runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                else:
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m3"] * subsurface_data[material_name]["volume_m3"] * multiplier)
            elif material_name == "weatherstrip":
                if subsurface_data[material_name]["gwp_per_m"] is None:
                    embodied_carbon = 0.0
                    _mark_carbon_data_unavailable(f"missing_gwp_{material_name}")
                    runner.registerWarning(f"No GWP data found for {material_name} in {subsurface_name}, assigning 0 embodied carbon.")
                else:
                    embodied_carbon = float(subsurface_data[material_name]["gwp_per_m"] * subsurface_data[material_name]["length_m"] * multiplier)

            # Assign embodied carbon
            subsurface_data[material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
            runner.registerValue(f"{material_name}_embodied_carbon_kg_co2_eq", embodied_carbon, "kg CO2 eq")
            runner.registerInfo(f"    ✓ {material_name.replace('_', ' ').title()}: {embodied_carbon:.2f} kg CO2 eq")
            
            subsurface_data["window_renovation_embodied_carbon_kg_co2_eq"] += subsurface_data[material_name]["embodied_carbon_kg_co2_eq"]

    def validate_user_arguments_values(self, runner, analysis_period, glass_lifetime, wf_lifetime, 
                                        caulking_lifetime, film_lifetime, weatherstrip_lifetime, 
                                        caulking_thickness, glass_pane_thickness, 
                                        gap_thickness, length_per_unit, film_visible_transmittance, 
                                        film_solar_transmittance, film_thermal_emissivity, 
                                        film_thermal_resistance, glass_solar_transmittance, 
                                        glass_visible_transmittance, glass_front_emissivity, 
                                        glass_back_emissivity, glass_front_solar_reflectance, 
                                        glass_back_solar_reflectance, glass_front_visible_reflectance, 
                                        glass_back_visible_reflectance, labor_cost_multiplier,
                                        u_factor_mod_pct=0.0, shgc_mod_pct=0.0, vt_mod_pct=0.0):
        """Check that all user inputs are within reasonable ranges.
        
        Validates lifetimes (>0, within max limits), dimensions (>0, physically realistic),
        and optical properties (between 0.0 and 1.0). Returns True if all valid, False otherwise.
        """
        # Check lifetime parameters
        if analysis_period <= 0:
            runner.registerError("Analysis period must be greater than 0 years.")
            return False
        if analysis_period > 100:
            runner.registerError("Analysis period must be 100 years or less.")
            return False
        if glass_lifetime <= 0:
            runner.registerError("Glass pane lifetime must be greater than 0 years.")
            return False
        if glass_lifetime > 100:
            runner.registerError("Glass pane lifetime must be 100 years or less.")
            return False
        if wf_lifetime <= 0:
            runner.registerError("Window frame lifetime must be greater than 0 years.")
            return False
        if wf_lifetime > 100:
            runner.registerError("Window frame lifetime must be 100 years or less.")
            return False
        if caulking_lifetime <= 0:
            runner.registerError("Caulking sealant lifetime must be greater than 0 years.")
            return False
        if caulking_lifetime > 50:
            runner.registerError("Caulking sealant lifetime must be 50 years or less.")
            return False
        if film_lifetime <= 0:
            runner.registerError("Glazing film lifetime must be greater than 0 years.")
            return False
        if film_lifetime > 50:
            runner.registerError("Glazing film lifetime must be 50 years or less.")
            return False
        if weatherstrip_lifetime <= 0:
            runner.registerError("Weatherstrip lifetime must be greater than 0 years.")
            return False
        if weatherstrip_lifetime > 50:
            runner.registerError("Weatherstrip lifetime must be 50 years or less.")
            return False
        if labor_cost_multiplier < 1.0:
            runner.registerError("Labor cost multiplier must be at least 1.0.")
            return False

        # Check geometric parameters
        if caulking_thickness <= 0.0:
            runner.registerError("Caulking thickness must be greater than 0.")
            return False
        if caulking_thickness > 0.05:
            runner.registerError("Caulking thickness must be 0.05 m (50 mm) or less.")
            return False
        if glass_pane_thickness <= 0.0:
            runner.registerError("Glass pane thickness must be greater than 0.")
            return False
        if glass_pane_thickness > 0.025:
            runner.registerError("Glass pane thickness must be 0.025 m (25 mm) or less.")
            return False
        if gap_thickness < 0.0:
            runner.registerError("Gap thickness must be non-negative.")
            return False
        if gap_thickness > 0.05:
            runner.registerError("Gap thickness must be 0.05 m (50 mm) or less.")
            return False
        if length_per_unit <= 0.0:
            runner.registerError("Length per unit must be greater than 0.")
            return False
        
        # Check optical and thermal properties (0.0 means use defaults, so allow it)
        # Film properties
        if film_visible_transmittance < 0.0 or film_visible_transmittance > 1.0:
            runner.registerError("Film visible transmittance must be between 0.0 and 1.0.")
            return False
        if film_solar_transmittance < 0.0 or film_solar_transmittance > 1.0:
            runner.registerError("Film solar transmittance must be between 0.0 and 1.0.")
            return False
        if film_thermal_emissivity < 0.0 or film_thermal_emissivity > 1.0:
            runner.registerError("Film thermal emissivity must be between 0.0 and 1.0.")
            return False
        if film_thermal_resistance < 0.0 or film_thermal_resistance > 1.0:
            runner.registerError("Film thermal resistance must be between 0.0 and 1.0 m²·K/W.")
            return False
        
        # Glass properties
        if glass_solar_transmittance < 0.0 or glass_solar_transmittance > 1.0:
            runner.registerError("Glass solar transmittance must be between 0.0 and 1.0.")
            return False
        if glass_visible_transmittance < 0.0 or glass_visible_transmittance > 1.0:
            runner.registerError("Glass visible transmittance must be between 0.0 and 1.0.")
            return False
        if glass_front_emissivity < 0.0 or glass_front_emissivity > 1.0:
            runner.registerError("Glass front emissivity must be between 0.0 and 1.0.")
            return False
        if glass_back_emissivity < 0.0 or glass_back_emissivity > 1.0:
            runner.registerError("Glass back emissivity must be between 0.0 and 1.0.")
            return False
        if glass_front_solar_reflectance < 0.0 or glass_front_solar_reflectance > 1.0:
            runner.registerError("Glass front solar reflectance must be between 0.0 and 1.0.")
            return False
        if glass_back_solar_reflectance < 0.0 or glass_back_solar_reflectance > 1.0:
            runner.registerError("Glass back solar reflectance must be between 0.0 and 1.0.")
            return False
        if glass_front_visible_reflectance < 0.0 or glass_front_visible_reflectance > 1.0:
            runner.registerError("Glass front visible reflectance must be between 0.0 and 1.0.")
            return False
        if glass_back_visible_reflectance < 0.0 or glass_back_visible_reflectance > 1.0:
            runner.registerError("Glass back visible reflectance must be between 0.0 and 1.0.")
            return False
        
        # Validate Simple Glazing modification parameters
        # These parameters are optional (default 0.0 = no modification)
        if u_factor_mod_pct != 0.0:
            if u_factor_mod_pct < -50.0 or u_factor_mod_pct > 50.0:
                runner.registerWarning(
                    f"U-factor modification percentage {u_factor_mod_pct}% is outside "
                    "recommended range [-50%, +50%]. Extreme values may result in physically "
                    "unreasonable window performance. Proceeding anyway.")
        
        if shgc_mod_pct != 0.0:
            if shgc_mod_pct < -50.0 or shgc_mod_pct > 50.0:
                runner.registerWarning(
                    f"SHGC modification percentage {shgc_mod_pct}% is outside "
                    "recommended range [-50%, +50%]. Extreme values may result in physically "
                    "unreasonable window performance. Proceeding anyway.")
        
        if vt_mod_pct != 0.0:
            if vt_mod_pct < -50.0 or vt_mod_pct > 50.0:
                runner.registerWarning(
                    f"Visible Transmittance modification percentage {vt_mod_pct}% is outside "
                    "recommended range [-50%, +50%]. Extreme values may result in physically "
                    "unreasonable window performance. Proceeding anyway.")
        
        return True

    def process_infiltration_reduction(self, model, runner, object, space_infiltration_reduction_percent, user_arguments):
        """Reduce air infiltration (leakage) in building spaces by specified percentage.
        
        Applies reduction to space infiltration objects to model improved air sealing from
        window enhancements. Returns (success, count_modified, total_area, spaces_list).
        """
        # Check the space_type for reasonableness and see if measure should run on space type or on the entire building
        apply_to_building = False
        space_type = None

        if not object.is_initialized():
            handle = runner.getStringArgumentValue('space_type', user_arguments)
            if not handle:
                runner.registerError('No space type was chosen.')
            else:
                runner.registerError(f"The selected space type with handle '{handle}' was not found in the model. It may have been removed by another measure.")
            return False, 0, 0.0, []
        elif object.get().to_SpaceType().is_initialized():
            space_type = object.get().to_SpaceType().get()
        elif object.get().to_Building().is_initialized():
            apply_to_building = True
        else:
            runner.registerError('Script Error - argument not showing up as space type or building.')
            return False, 0, 0.0, []

        # Check the space_infiltration_reduction_percent for reasonableness
        if space_infiltration_reduction_percent > 100:
            runner.registerError('Please enter a value less than or equal to 100 for the Space Infiltration reduction percentage.')
            return False, 0, 0.0, []

        # Get space infiltration objects used in the model
        space_infiltration_objects = model.getSpaceInfiltrationDesignFlowRates()

        # Counters needed for measure
        altered_instances = 0
        affected_area_si = 0

        # Report initial condition of model
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("INFILTRATION PROCESSING")
        runner.registerInfo("=" * 80)
        if len(space_infiltration_objects) == 0:
            runner.registerInfo('  ℹ Initial model contained no space infiltration objects')
        else:
            runner.registerInfo(f"  ℹ Initial model contained {len(space_infiltration_objects)} space infiltration objects")

        # Get space types in model
        building = model.getBuilding()
        if apply_to_building:
            space_types = model.getSpaceTypes()
            affected_area_si = building.floorArea()
        else:
            space_types = []
            space_types.append(space_type)  # Only run on a single space type
            affected_area_si = space_type.floorArea()

        def alter_performance(instance, space_infiltration_reduction_percent, runner):
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

        # Loop through space types
        for space_type in space_types:
            if len(space_type.spaces()) <= 0:
                continue

            space_type_infiltration_objects = space_type.spaceInfiltrationDesignFlowRates()
            for space_type_infiltration_object in space_type_infiltration_objects:
                # Call function to alter performance
                alter_performance(
                    space_type_infiltration_object,
                    space_infiltration_reduction_percent,
                    runner
                )

                # Rename
                updated_instance_name = space_type_infiltration_object.setName(
                    f"{space_type_infiltration_object.nameString()} {space_infiltration_reduction_percent} percent reduction"
                )
                runner.registerInfo(f"  ✓ Altered: {updated_instance_name} (Space Type: {space_type.nameString()})")
                altered_instances += 1

        # Get spaces based on selection
        if apply_to_building:
            spaces = model.getSpaces()
        elif space_type is not None and len(space_type.spaces()) > 0:
            spaces = space_type.spaces()
        else:
            spaces = []

        for space in spaces:
            space_infiltration_objects = space.spaceInfiltrationDesignFlowRates()
            for space_infiltration_object in space_infiltration_objects:
                # Call function to alter performance
                alter_performance(
                    space_infiltration_object,
                    space_infiltration_reduction_percent,
                    runner
                )

                # Rename
                updated_instance_name = space_infiltration_object.setName(
                    f"{space_infiltration_object.nameString()} {space_infiltration_reduction_percent} percent reduction"
                )
                runner.registerInfo(f"  ✓ Altered: {updated_instance_name} (Space: {space.nameString()})")
                altered_instances += 1

        if altered_instances == 0:
            runner.registerInfo(f"  ℹ No space infiltration objects altered for space type '{space_type.nameString()}'")
        
        return True, altered_instances, affected_area_si, spaces

    def remove_outliers_iqr(self, data):
        """Remove extreme outlier values from data using statistical method.
        
        Uses Interquartile Range (IQR) to identify and remove data points that are
        unusually high or low. Returns cleaned list with outliers removed.
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

    @staticmethod
    def _extract_rsmeans_lengths_from_description(description):
        """Extract likely thickness/gap/length hints from an RSMeans description string.

        Returns a dict with optional keys:
          - glass_thickness_m
          - gap_thickness_m
          - length_per_unit_m
        """
        if not description:
            return {}

        desc = str(description).lower()
        parsed = {}

        def _to_m(value, unit):
            if unit in ["mm", "millimeter", "millimeters"]:
                return value / 1000.0
            if unit in ["in", "inch", "inches", '"']:
                return value * 0.0254
            if unit in ["ft", "foot", "feet", "lf"]:
                return value * 0.3048
            return None

        # Parse explicit gap/air-space first.
        gap_patterns = [
            r'(?:air\s*(?:gap|space)|gap)\s*[:=]?\s*([\d.]+)\s*(mm|millimeters?|in|inch|inches|"|ft|feet|foot)',
            r'([\d.]+)\s*(mm|millimeters?|in|inch|inches|")\s*(?:air\s*(?:gap|space)|gap)',
        ]
        for pattern in gap_patterns:
            m = re.search(pattern, desc)
            if m:
                gap_val = _to_m(float(m.group(1)), m.group(2))
                if gap_val and 0.003 <= gap_val <= 0.05:
                    parsed["gap_thickness_m"] = gap_val
                    break

        # Generic thickness candidates.
        thickness_candidates = []
        for m in re.finditer(r'([\d.]+)\s*(mm|millimeters?|in|inch|inches|")', desc):
            val_m = _to_m(float(m.group(1)), m.group(2))
            if val_m and 0.001 <= val_m <= 0.03:
                thickness_candidates.append(val_m)
        if thickness_candidates:
            parsed["glass_thickness_m"] = min(thickness_candidates)

        # Length-per-unit candidates (weatherstrip): ft/lf tokens in plausible range.
        length_candidates_m = []
        for m in re.finditer(r'([\d.]+)\s*(ft|foot|feet|lf)', desc):
            length_m = _to_m(float(m.group(1)), m.group(2))
            if length_m and 0.3 <= length_m <= 50.0:
                length_candidates_m.append(length_m)
        if length_candidates_m:
            parsed["length_per_unit_m"] = max(length_candidates_m)

        return parsed

    def _infer_defaults_from_rsmeans_descriptions(
        self,
        runner,
        materials_results,
        glass_option,
        secondary_glazing_option,
        weatherstrip_option,
    ):
        """Infer geometric defaults from RSMeans matched material descriptions."""
        inferred = {}
        if not materials_results:
            return inferred

        for mat in materials_results:
            name = str(mat.get("name", "")).lower()
            desc = mat.get("description", "")
            parsed = self._extract_rsmeans_lengths_from_description(desc)
            if not parsed:
                continue

            if ("glaz" in name or "window" in name) and (
                glass_option != "none" or secondary_glazing_option != "none"
            ):
                if "glass_thickness_m" in parsed and "glass_thickness_m" not in inferred:
                    inferred["glass_thickness_m"] = parsed["glass_thickness_m"]
                if "gap_thickness_m" in parsed and "gap_thickness_m" not in inferred:
                    inferred["gap_thickness_m"] = parsed["gap_thickness_m"]

            if ("weather" in name or "gasket" in name or "strip" in name) and weatherstrip_option != "none":
                if "length_per_unit_m" in parsed and "length_per_unit_m" not in inferred:
                    inferred["length_per_unit_m"] = parsed["length_per_unit_m"]

        if inferred:
            runner.registerInfo(f"Inferred defaults from RSMeans descriptions: {inferred}")
        return inferred

    def extract_gwp_and_thickness_from_epd(self, length_per_unit, epd_data):
        """Extract global warming potential (GWP) values and lifetime from EPD product data.
        
        Parses EPD records to get carbon emissions per unit (m2, kg, m3, m), thickness,
        and reference service life. Removes statistical outliers from numerical data.
        Returns (gwp_values_dict, thickness_list, lifetime_list).
        """
        gwp_values = {}
        gwp_values["gwp_per_m2"] = []
        gwp_values["gwp_per_kg"] = []
        gwp_values["gwp_per_m3"] = []
        gwp_values["gwp_per_m"] = []
        thickness_summary = []
        lifetime_values = []

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
            
            # Extract reference service life
            reference_service_life = parsed_data.get("reference_service_life")
            if reference_service_life is not None:
                if isinstance(reference_service_life, (int, float)):
                    lifetime_values.append(float(reference_service_life))
                elif isinstance(reference_service_life, str):
                    # Extract numeric value from string (e.g., "25 years" -> 25)
                    numeric_value = extract_numeric_value(reference_service_life)
                    if numeric_value is not None and numeric_value > 0:
                        lifetime_values.append(float(numeric_value))
        
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
        
        # Remove outliers from lifetime values
        if len(lifetime_values) > 0:
            original_lifetime_count = len(lifetime_values)
            lifetime_values = self.remove_outliers_iqr(lifetime_values)
            filtered_lifetime_count = len(lifetime_values)
            if original_lifetime_count != filtered_lifetime_count:
                print(f"Removed {original_lifetime_count - filtered_lifetime_count} outliers from lifetime: {original_lifetime_count} -> {filtered_lifetime_count} values")
        
        return gwp_values, thickness_summary, lifetime_values

    def get_film_properties(self, film_option):
        """Get standard optical and thermal properties for different glazing film types from technical data of product.
        """
        # Film properties: (visible_transmittance, solar_transmittance, thermal_emissivity, thermal_resistance)
        film_properties = {
            'safety film': (0.89, 0.81, 0.87, 0.16),
            'solar control film': (0.23, 0.13, 0.52, 0.21),
            'anti-graffiti film': (0.89, 0.82, 0.9, 0.16),
            'decorative film': (0.85, 0.76, 0.7, 0.16),
            'low-e film': (0.12, 0.08, 0.38, 0.23)
        }
        return film_properties.get(film_option, (0.85, 0.70, 0.84, 0.0))

    def count_glazing_layers(self, construction):
        """Count how many glass panes are in a window construction.
        
        Examines construction layers to find glass materials (single, double, triple pane).
        Returns number of glass layers found, or -1 if not a standard layered construction.
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
        """Check if window uses simplified modeling approach (SimpleGlazing).
        
        Simple glazing uses U-factor and SHGC instead of detailed layers. Returns True if
        SimpleGlazing is detected, False otherwise. Some operations don't work with SimpleGlazing.
        """
        if construction is None:
            return False
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            for i in range(layered.numLayers()):
                material = layered.getLayer(i)
                if material.to_SimpleGlazing().is_initialized():
                    runner.registerInfo(f"  ℹ Simple glazing system detected in layer {i+1}")
                    return True
        return False

    def modify_simple_glazing_properties(self, runner, subsurface, u_factor_mod_pct, shgc_mod_pct, vt_mod_pct):
        """Modify Simple Glazing properties by percentage.
        
        Applies percentage modifications to U-factor, SHGC, and visible transmittance.
        Returns True if successful, False otherwise.
        
        Args:
            runner: OSRunner for logging
            subsurface: SubSurface object with Simple Glazing construction
            u_factor_mod_pct: Percentage modification for U-factor (e.g., -20.0 for -20%)
            shgc_mod_pct: Percentage modification for SHGC
            vt_mod_pct: Percentage modification for visible transmittance
        
        Returns:
            bool: True if modification was successful
        """
        try:
            subsurface_name = subsurface.nameString()
            
            # Check if subsurface has a construction
            if not subsurface.construction().is_initialized():
                runner.registerWarning(f"    {subsurface_name} has no construction assigned.")
                return False
            
            construction = subsurface.construction().get()
            
            # Check if it's a LayeredConstruction
            if not construction.to_LayeredConstruction().is_initialized():
                runner.registerWarning(f"    {subsurface_name} construction is not a LayeredConstruction.")
                return False
            
            layered = construction.to_LayeredConstruction().get()
            
            # Find the SimpleGlazing layer
            simple_glazing = None
            for i in range(layered.numLayers()):
                material = layered.getLayer(i)
                if material.to_SimpleGlazing().is_initialized():
                    simple_glazing = material.to_SimpleGlazing().get()
                    break
            
            if simple_glazing is None:
                runner.registerWarning(f"    No SimpleGlazing material found in {subsurface_name}.")
                return False
            
            # Get current values
            orig_u = float(simple_glazing.uFactor())
            orig_shgc = float(simple_glazing.solarHeatGainCoefficient())
            
            # Handle optional VT value
            vt_opt = simple_glazing.visibleTransmittance()
            if hasattr(vt_opt, 'is_initialized'):
                if vt_opt.is_initialized():
                    orig_vt = float(vt_opt.get())
                else:
                    orig_vt = 0.6  # Default if not set
            else:
                orig_vt = float(vt_opt) if vt_opt else 0.6
            
            # Calculate new values with percentage modification
            new_u = orig_u * (1.0 + u_factor_mod_pct / 100.0)
            new_shgc = orig_shgc * (1.0 + shgc_mod_pct / 100.0)
            new_vt = orig_vt * (1.0 + vt_mod_pct / 100.0)
            
            # Clamp to valid ranges and log any clamping
            u_clamped = False
            shgc_clamped = False
            vt_clamped = False
            
            if new_u < 0.1 or new_u > 10.0:
                new_u = max(0.1, min(10.0, new_u))
                u_clamped = True
                runner.registerWarning(
                    f"    U-factor after modification clamped to [0.1, 10.0] W/m²K. "
                    f"Original modification would result in {orig_u * (1.0 + u_factor_mod_pct / 100.0):.4f} W/m²K.")
            
            if new_shgc < 0.0 or new_shgc > 1.0:
                new_shgc = max(0.0, min(1.0, new_shgc))
                shgc_clamped = True
                runner.registerWarning(
                    f"    SHGC after modification clamped to [0.0, 1.0]. "
                    f"Original modification would result in {orig_shgc * (1.0 + shgc_mod_pct / 100.0):.4f}.")
            
            if new_vt < 0.0 or new_vt > 1.0:
                new_vt = max(0.0, min(1.0, new_vt))
                vt_clamped = True
                runner.registerWarning(
                    f"    Visible Transmittance after modification clamped to [0.0, 1.0]. "
                    f"Original modification would result in {orig_vt * (1.0 + vt_mod_pct / 100.0):.4f}.")
            
            # Apply modifications
            simple_glazing.setUFactor(new_u)
            simple_glazing.setSolarHeatGainCoefficient(new_shgc)
            simple_glazing.setVisibleTransmittance(new_vt)
            
            # Log the modifications
            runner.registerValue(f"{subsurface_name}_original_u_factor", orig_u, "W/m²K")
            runner.registerValue(f"{subsurface_name}_modified_u_factor", new_u, "W/m²K")
            runner.registerValue(f"{subsurface_name}_original_shgc", orig_shgc, "")
            runner.registerValue(f"{subsurface_name}_modified_shgc", new_shgc, "")
            runner.registerValue(f"{subsurface_name}_original_vt", orig_vt, "")
            runner.registerValue(f"{subsurface_name}_modified_vt", new_vt, "")
            
            runner.registerInfo(
                f"    ✓ Simple Glazing properties modified:")
            runner.registerInfo(
                f"      U-factor:     {orig_u:.4f} → {u_factor_mod_pct:+.1f}% → {new_u:.4f} W/m²K")
            runner.registerInfo(
                f"      SHGC:         {orig_shgc:.4f} → {shgc_mod_pct:+.1f}% → {new_shgc:.4f}")
            runner.registerInfo(
                f"      VT:           {orig_vt:.4f} → {vt_mod_pct:+.1f}% → {new_vt:.4f}")
            
            return True
            
        except Exception as e:
            runner.registerError(
                f"Error modifying Simple Glazing properties for {subsurface_name}: {str(e)}")
            return False

    def _optional_double_or_default(self, maybe_value, default_value):
        """Return OptionalDouble value when initialized; otherwise use default."""
        try:
            if maybe_value.is_initialized():
                return float(maybe_value.get())
        except Exception:
            pass
        return float(default_value)

    def _estimate_construction_energy_proxy(self, construction):
        """Estimate U-value and SHGC proxies from construction layers.

        U proxy is estimated from layer conductance summation, and SHGC proxy uses
        product of glazing solar transmittance values. This is used as a safety
        screening metric, not as a replacement for full EnergyPlus simulation.
        """
        u_proxy = None
        shgc_proxy = None

        # Handle SimpleGlazing constructions if possible.
        if construction.to_LayeredConstruction().is_initialized():
            layered = construction.to_LayeredConstruction().get()
            r_terms = []
            glazing_sol_trans = []

            gas_k_map = {
                "air": 0.026,
                "argon": 0.016,
                "krypton": 0.009,
                "xenon": 0.005,
            }

            for i in range(layered.numLayers()):
                layer = layered.getLayer(i)

                if layer.to_StandardGlazing().is_initialized():
                    g = layer.to_StandardGlazing().get()
                    thickness_m = float(g.thickness())
                    conductivity = self._optional_double_or_default(g.thermalConductivity(), 0.9)
                    if conductivity > 0 and thickness_m > 0:
                        r_terms.append(thickness_m / conductivity)
                    glazing_sol_trans.append(self._optional_double_or_default(g.solarTransmittance(), 0.775))
                    continue

                if layer.to_Gas().is_initialized():
                    gas = layer.to_Gas().get()
                    thickness_m = float(gas.thickness())
                    gas_type = "air"
                    try:
                        gas_type = str(gas.gasType()).strip().lower()
                    except Exception:
                        gas_type = "air"
                    conductivity = gas_k_map.get(gas_type, gas_k_map["air"])
                    if conductivity > 0 and thickness_m > 0:
                        r_terms.append(thickness_m / conductivity)
                    continue

                if layer.to_SimpleGlazing().is_initialized():
                    sg = layer.to_SimpleGlazing().get()
                    try:
                        u_proxy = float(sg.uFactor())
                    except Exception:
                        u_proxy = None
                    try:
                        shgc_proxy = float(sg.solarHeatGainCoefficient())
                    except Exception:
                        shgc_proxy = None

            if u_proxy is None and len(r_terms) > 0:
                r_total = float(np.sum(r_terms))
                if r_total > 0:
                    u_proxy = 1.0 / r_total

            if shgc_proxy is None and len(glazing_sol_trans) > 0:
                shgc_proxy = float(np.prod(glazing_sol_trans))

        return {"u_proxy": u_proxy, "shgc_proxy": shgc_proxy}

    def enforce_energy_performance_guard(
        self,
        runner,
        subsurface_name,
        original_construction,
        updated_construction,
        check_shgc=False,
        strict=True,
        u_tolerance=0.0,
        shgc_tolerance=0.0,
    ):
        """Enforce that updated construction is not worse than original by proxy metrics."""
        old_proxy = self._estimate_construction_energy_proxy(original_construction)
        new_proxy = self._estimate_construction_energy_proxy(updated_construction)

        old_u = old_proxy.get("u_proxy")
        new_u = new_proxy.get("u_proxy")
        old_shgc = old_proxy.get("shgc_proxy")
        new_shgc = new_proxy.get("shgc_proxy")

        runner.registerInfo(
            f"  Energy guard proxies for {subsurface_name}: "
            f"U(old={old_u}, new={new_u}), SHGC(old={old_shgc}, new={new_shgc})"
        )

        if old_u is None or new_u is None:
            msg = f"Could not evaluate U-value proxy for {subsurface_name}."
            if strict:
                runner.registerError(msg)
                return False
            runner.registerWarning(msg + " Skipping guard check for this window.")
            return True

        if float(new_u) > float(old_u) + float(u_tolerance):
            runner.registerError(
                f"Energy guard violation for {subsurface_name}: "
                f"new U proxy {new_u:.4f} > old {old_u:.4f} + tol {u_tolerance:.4f}."
            )
            return False

        if check_shgc:
            if old_shgc is None or new_shgc is None:
                msg = f"Could not evaluate SHGC proxy for {subsurface_name}."
                if strict:
                    runner.registerError(msg)
                    return False
                runner.registerWarning(msg + " Skipping SHGC guard for this window.")
                return True

            if float(new_shgc) > float(old_shgc) + float(shgc_tolerance):
                runner.registerError(
                    f"Energy guard violation for {subsurface_name}: "
                    f"new SHGC proxy {new_shgc:.4f} > old {old_shgc:.4f} + tol {shgc_tolerance:.4f}."
                )
                return False

        return True

    def create_new_window_construction(self, model, runner, subsurface, num_panes, glass_thickness, gap_thickness,
                                       solar_trans, visible_trans, front_emissivity, back_emissivity,
                                       front_solar_refl, back_solar_refl, front_visible_refl, back_visible_refl):
        """Build a new multi-pane window construction from scratch.
        
        Creates single, double, or triple pane window with user-specified glass thickness,
        air gap spacing, and optical/thermal properties. Uses defaults if 0.0 provided.
        
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
            glass_pane.setThermalConductivity(0.9)  # W/m-K for Openstudio Material: Clear 3mm
            
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
        
        runner.registerInfo(f"    • Created {num_panes}-pane construction")
        runner.registerInfo(f"      Glass: {glass_thickness*1000:.1f}mm | Air gap: {gap_thickness*1000:.1f}mm")
        
        return new_construction

    def add_secondary_glazing(self, model, runner, subsurface, original_construction, glass_pane_thickness, gap_thickness,
                              solar_trans, visible_trans, front_emissivity, back_emissivity,
                              front_solar_refl, back_solar_refl, front_visible_refl, back_visible_refl):
        """Add an extra glass pane to the inside of single-pane windows.
        
        Converts single-pane to double-pane by adding air gap and interior glass layer.
        Improves insulation and reduces heat loss. Returns new construction object.
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
        
        runner.registerInfo(f"    ✓ Created construction with secondary glazing: '{new_construction_name}'")
        runner.registerInfo(f"      Added: {gap_thickness*1000:.0f}mm air gap + {glass_pane_thickness*1000:.0f}mm glass pane")
        
        return new_layered_construction

    def convert_to_equivalent_layer(self, model, runner, subsurface, original_construction, film_option, 
                                    film_visible_transmittance, film_solar_transmittance, 
                                    film_thermal_emissivity, film_thermal_resistance):
        """Apply window film effects by modifying the inner glass pane properties.
        
        Simulates film installation by adjusting the innermost glass layer's light transmission,
        solar heat gain, and thermal radiation to match film + glass combined performance.
        Returns modified construction object.
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
                    runner.registerInfo(f"    → Modified innermost glass pane with film properties:")
                    runner.registerInfo(f"      Visible Transmittance: {orig_vis_trans:.3f} → {orig_vis_trans * film_vis_trans:.3f}")
                    runner.registerInfo(f"      Solar Transmittance: {orig_sol_trans:.3f} → {orig_sol_trans * film_sol_trans:.3f}")
                    runner.registerInfo(f"      Back Emissivity: → {film_emissivity:.3f}")
                else:
                    # Copy other layers unchanged
                    layers.append(original_material)
        
        # Create new layered construction
        new_layered_construction = openstudio.model.Construction(model)
        new_layered_construction.setName(new_construction_name)
        new_layered_construction.setLayers(layers)
        
        # Assign new construction to subsurface
        subsurface.setConstruction(new_layered_construction)
        
        runner.registerInfo(f"    ✓ Created construction with integrated glazing film: '{new_construction_name}'")
        
        return new_layered_construction

    def _parse_inches_token_to_float(self, token):
        token = str(token).strip()
        if not token:
            return None
        if "-" in token:
            whole, frac = token.split("-", 1)
            try:
                whole_val = float(whole)
            except ValueError:
                return None
            if "/" in frac:
                num, den = frac.split("/", 1)
                try:
                    return whole_val + (float(num) / float(den))
                except (ValueError, ZeroDivisionError):
                    return None
            return None
        if "/" in token:
            num, den = token.split("/", 1)
            try:
                return float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                return None
        try:
            return float(token)
        except ValueError:
            return None

    def _extract_igu_total_thickness_m(self, text):
        desc = str(text or "")
        if not desc:
            return None

        mm_match = re.search(r"(\d+(?:\.\d+)?)\s*mm\b", desc, flags=re.IGNORECASE)
        if mm_match:
            try:
                return float(mm_match.group(1)) / 1000.0
            except ValueError:
                return None

        patterns = [
            r"(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*\"",
            r"(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*(?:in|inch|inches)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, desc, flags=re.IGNORECASE)
            if match:
                inches = self._parse_inches_token_to_float(match.group(1))
                if inches and inches > 0.0:
                    return inches * 0.0254
        return None

    def _infer_pane_count_from_text(self, text):
        desc = str(text or "").lower()
        if not desc:
            return None
        if "triple" in desc or "3 pane" in desc or "3-pane" in desc:
            return 3
        if "double" in desc or "2 pane" in desc or "2-pane" in desc:
            return 2
        if "single" in desc or "1 pane" in desc or "1-pane" in desc:
            return 1
        return None

    def _infer_gas_type_from_text(self, text):
        desc = str(text or "").lower()
        if "krypton" in desc:
            return "Krypton"
        if "xenon" in desc:
            return "Xenon"
        if "argon" in desc:
            return "Argon"
        if "air" in desc:
            return "Air"
        return None

    def _infer_glass_conductivity_from_text(self, text):
        desc = str(text or "").lower()
        if "laminated" in desc:
            return 0.95
        if "tempered" in desc:
            return 1.0
        # Low-E coatings mostly affect emissivity, not bulk conductivity.
        return 0.9

    def _infer_low_e_emissivity_from_text(self, text):
        desc = str(text or "").lower()
        if "low-e" in desc or "low e" in desc:
            return 0.10
        return None

    def extract_glazing_spec_from_rsmeans_results(self, rsmeans_lookup):
        materials_results = ((rsmeans_lookup or {}).get("results") or {}).get("materials", [])
        if not materials_results:
            return None

        glazing_material = None
        for mat in materials_results:
            name_norm = str(mat.get("name", "")).strip().lower()
            if name_norm == "window glazing":
                glazing_material = mat
                break
        if glazing_material is None:
            for mat in materials_results:
                name_norm = str(mat.get("name", "")).strip().lower()
                if name_norm == "secondary glazing":
                    glazing_material = mat
                    break
        if glazing_material is None:
            return None

        desc = str(glazing_material.get("rsmeans_description") or glazing_material.get("description") or "")
        pane_count = self._infer_pane_count_from_text(desc)
        gas_type = self._infer_gas_type_from_text(desc)
        conductivity = self._infer_glass_conductivity_from_text(desc)
        low_e_emissivity = self._infer_low_e_emissivity_from_text(desc)

        source_line_thickness_ft = glazing_material.get("source_line_thickness_ft")
        igu_total_thickness_m = None
        try:
            if source_line_thickness_ft is not None:
                igu_total_thickness_m = float(source_line_thickness_ft) * 0.3048
        except (TypeError, ValueError):
            igu_total_thickness_m = None

        if igu_total_thickness_m is None:
            igu_total_thickness_m = self._extract_igu_total_thickness_m(desc)

        return {
            "description": desc,
            "pane_count": pane_count,
            "gas_type": gas_type,
            "glass_conductivity": conductivity,
            "low_e_emissivity": low_e_emissivity,
            "igu_total_thickness_m": igu_total_thickness_m,
        }

    def _apply_glazing_spec_to_layered_construction(self, runner, layered_construction, spec, glass_pane_thickness, default_gap_thickness):
        glazing_count = 0
        gas_count = 0
        gas_thickness_m = default_gap_thickness

        target_panes = spec.get("pane_count")
        if not target_panes or target_panes < 1:
            target_panes = None

        igu_total_thickness_m = spec.get("igu_total_thickness_m")
        if igu_total_thickness_m and target_panes and target_panes > 1:
            derived_gap = (igu_total_thickness_m - target_panes * glass_pane_thickness) / float(target_panes - 1)
            if 0.0 < derived_gap <= 0.05:
                gas_thickness_m = derived_gap

        gas_type = spec.get("gas_type")
        glass_conductivity = spec.get("glass_conductivity", 0.9)
        low_e_emissivity = spec.get("low_e_emissivity")

        for i in range(layered_construction.numLayers()):
            layer = layered_construction.getLayer(i)

            if layer.to_StandardGlazing().is_initialized():
                glazing = layer.to_StandardGlazing().get()
                try:
                    glazing.setThermalConductivity(glass_conductivity)
                except Exception:
                    pass
                if low_e_emissivity is not None:
                    try:
                        glazing.setBackSideInfraredHemisphericalEmissivity(low_e_emissivity)
                    except Exception:
                        pass
                glazing_count += 1

            elif layer.to_Gas().is_initialized():
                gas_layer = layer.to_Gas().get()
                try:
                    gas_layer.setThickness(gas_thickness_m)
                except Exception:
                    pass
                if gas_type:
                    try:
                        gas_layer.setGasType(gas_type)
                    except Exception:
                        pass
                gas_count += 1

        return glazing_count, gas_count, gas_thickness_m

    def apply_rsmeans_glazing_updates_to_model(self, runner, subsurface_dict, rsmeans_lookup, glass_pane_thickness, gap_thickness):
        spec = self.extract_glazing_spec_from_rsmeans_results(rsmeans_lookup)
        if not spec:
            runner.registerWarning(
                "RSMeans model update skipped: no matched glazing/secondary glazing line found in RSMeans results."
            )
            return

        if spec.get("pane_count") is None:
            runner.registerWarning(
                "RSMeans glazing parse: pane count not identified from description; existing pane layering will be retained."
            )
        if spec.get("gas_type") is None:
            runner.registerWarning(
                "RSMeans glazing parse: gas type not identified from description; existing gas type (or Air default) will be retained."
            )
        if spec.get("igu_total_thickness_m") is None:
            runner.registerWarning(
                f"RSMeans glazing parse: IGU total thickness not identified; default gap_thickness ({gap_thickness*1000:.1f}mm) will be retained."
            )

        modified_windows = 0
        total_glazing_layers = 0
        total_gas_layers = 0
        applied_gap_values = []

        for subsurface_name, data in subsurface_dict.items():
            subsurface_obj = data.get("subsurface_object")
            if subsurface_obj is None or not subsurface_obj.construction().is_initialized():
                continue

            construction = subsurface_obj.construction().get()
            if not construction.to_LayeredConstruction().is_initialized():
                continue

            layered = construction.to_LayeredConstruction().get()
            glazing_count, gas_count, applied_gap = self._apply_glazing_spec_to_layered_construction(
                runner,
                layered,
                spec,
                glass_pane_thickness,
                gap_thickness,
            )
            if glazing_count == 0 and gas_count == 0:
                continue

            modified_windows += 1
            total_glazing_layers += glazing_count
            total_gas_layers += gas_count
            applied_gap_values.append(applied_gap)

        if modified_windows > 0:
            gap_msg = ""
            if applied_gap_values:
                gap_msg = f", gap≈{float(np.mean(applied_gap_values))*1000:.1f}mm"
            runner.registerInfo(
                "Applied RSMeans-informed glazing updates to "
                f"{modified_windows} window construction(s): "
                f"{total_glazing_layers} glazing layer(s), {total_gas_layers} gas layer(s){gap_msg}."
            )
            runner.registerInfo(
                f"  RSMeans glazing basis: '{spec.get('description', '')}'"
            )
        else:
            runner.registerWarning(
                "RSMeans glazing parse succeeded, but no layered window constructions were eligible for model updates."
            )

    @staticmethod
    def _write_features(target_ap, feature_map):
        for feature_name, feature_value in feature_map.items():
            target_ap.setFeature(feature_name, feature_value)

    def _initialize_additional_property_feature_maps(
        self,
        analysis_period,
        gwp_statistic,
        gwp_source,
        space_infiltration_reduction_percent,
        total_weatherstrip_length_m,
        total_window_area_m2,
        total_glazing_area_m2,
        total_frame_area_m2,
        total_perimeter_m,
        total_caulking_volume_m3,
        glass_pane_thickness,
        gap_thickness,
        wf_option,
        caulking_option,
        film_option,
        weatherstrip_option,
        glass_option,
        secondary_glazing_option,
        glass_lifetime,
        wf_lifetime,
        caulking_lifetime,
        film_lifetime,
        weatherstrip_lifetime,
        total_embodied_carbon,
        length_per_unit,
    ):
        basic_input_features = {
            "window_analysis_period_years": analysis_period,
            "window_gwp_statistic": gwp_statistic,
            "window_gwp_source": gwp_source,
            "window_measure_name": "Window Enhancement for Infiltration Reduction",
        }
        # Keep only canonical reno_detail keys.
        reno_detail_features = {
            "window_infiltration_reduction_percent": space_infiltration_reduction_percent,
            "window_glass_pane_thickness_m": glass_pane_thickness,
            "window_glass_gap_thickness_m": gap_thickness,
            "window_frame_option": wf_option,
            "window_caulking_option": caulking_option,
            "window_film_option": film_option,
            "window_weatherstrip_option": weatherstrip_option,
            "window_glass_option": glass_option,
            "window_secondary_glazing_option": secondary_glazing_option,
            "window_renovated_area_m2": total_window_area_m2,
            "window_renovated_glazing_area_m2": total_glazing_area_m2,
            "window_renovated_frame_area_m2": total_frame_area_m2,
            "window_renovated_perimeter_m": total_perimeter_m,
            "window_renovated_caulking_volume_m3": total_caulking_volume_m3,
            "window_renovated_weatherstrip_length_m": total_weatherstrip_length_m,
            "window_weatherstrip_length_per_unit": length_per_unit,
        }
        mtrl_prop_features = {
            "window_glass_lifetime_years": glass_lifetime,
            "window_frame_lifetime_years": wf_lifetime,
            "window_caulking_lifetime_years": caulking_lifetime,
            "window_film_lifetime_years": film_lifetime,
            "window_weatherstrip_lifetime_years": weatherstrip_lifetime,
        }
        factors_features = {}
        results_features = {
            "window_embodied_carbon_kgCO2eq": total_embodied_carbon,
        }

        return (
            basic_input_features,
            reno_detail_features,
            mtrl_prop_features,
            factors_features,
            results_features,
        )

    def _build_rsmeans_material_payload(
        self,
        total_glazing_area_m2,
        total_secondary_glazing_area_m2,
        total_film_area_m2,
        total_frame_area_m2,
        total_caulking_volume_m3,
        total_weatherstrip_length_m,
        glass_option,
        wf_option,
        caulking_option,
        film_option,
        weatherstrip_option,
        secondary_glazing_option,
        user_num_panes,
        effective_glass_pane_thickness,
        effective_gap_thickness,
        use_specific_rsmeans_line_item_ids,
        rsmeans_id_glazing,
        rsmeans_id_frame,
        rsmeans_id_caulking,
        rsmeans_id_film,
        rsmeans_id_weatherstrip,
        rsmeans_id_secondary_glazing,
        total_caulking_length_m=0.0,
        num_windows_executed=0,
        total_window_area_m2=0.0,
    ):
        materials = []

        def _m2_to_sf(value_m2: float) -> float:
            return value_m2 * 10.7639

        def _m3_to_cy(value_m3: float) -> float:
            return value_m3 * 1.30795

        def _m3_to_gal(value_m3: float) -> float:
            return value_m3 * 264.172052

        def _m_to_lf(value_m: float) -> float:
            return value_m * 3.28084

        def _m_to_ft(value_m: float) -> float:
            return value_m * 3.28084

        if glass_option != "none" and total_glazing_area_m2 > 0:
            pane_count = max(1, int(user_num_panes or 1))
            pane_count_label = int(user_num_panes) if float(user_num_panes or 0) > 0 else pane_count
            glass_thickness_ft = _m_to_ft(float(effective_glass_pane_thickness)) if effective_glass_pane_thickness > 0 else 0.0
            glazing_qty_sf = _m2_to_sf(total_glazing_area_m2)
            glazing_material = {
                "name": "window glazing",
                "description": (
                    f"{pane_count_label}-pane glass replacement; "
                    f"single-pane thickness {effective_glass_pane_thickness*1000:.1f} mm; "
                    f"gap {effective_gap_thickness*1000:.1f} mm"
                ),
                "quantity": glazing_qty_sf,
                "unit": "SF",
                "quantity_volume": float(glazing_qty_sf * glass_thickness_ft * pane_count),
                "unit_volume": "CF",
                "rsmeans_thickness_ft": float(glass_thickness_ft),
                "costing_mode": "volume_from_area",
                "quantity_si": total_glazing_area_m2,
                "unit_si": "m2",
                "division_code": "08",
            }
            glazing_material["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                "window glazing",
                glazing_material,
                rsmeans_id_glazing,
            )
            glazing_material["strict_rsmeans_id_only"] = True
            materials.append(glazing_material)

        if wf_option != "none" and total_frame_area_m2 > 0:
            frame_material = {
                "name": "window frame",
                "description": f"{wf_option} frame replacement",
                "quantity": _m2_to_sf(total_frame_area_m2),
                "unit": "SF",
                "quantity_si": total_frame_area_m2,
                "unit_si": "m2",
                "division_code": "08",
                # num_windows is the per-EA quantity used by the
                # "window unit minus glazing" frame-cost derivation.
                "num_windows": float(num_windows_executed or 0),
                # window_area_sf carries the OSM total window-area basis used for
                # the derived frame total cost and reported $/SF metric.
                "window_area_sf": _m2_to_sf(float(total_window_area_m2 or 0.0)),
            }
            if use_specific_rsmeans_line_item_ids and rsmeans_id_frame:
                frame_material["rsmeans_id"] = rsmeans_id_frame
            materials.append(frame_material)

        if film_option != "none" and total_film_area_m2 > 0:
            film_material = {
                "name": "glazing film",
                "description": film_option,
                "quantity": _m2_to_sf(total_film_area_m2),
                "unit": "SF",
                "quantity_si": total_film_area_m2,
                "unit_si": "m2",
                "division_code": "08",
            }
            film_material["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                "glazing film",
                film_material,
                rsmeans_id_film,
            )
            film_material["strict_rsmeans_id_only"] = True
            materials.append(film_material)

        if caulking_option != "none" and total_caulking_volume_m3 > 0:
            caulking_volume_gal = _m3_to_gal(total_caulking_volume_m3)
            caulking_material = {
                "name": "sealant",
                "description": f"{caulking_option} caulking",
                "quantity": caulking_volume_gal,
                "unit": "GAL",
                "quantity_si": float(total_caulking_volume_m3),
                "unit_si": "m3",
                # Preserve CY and LF context for downstream reporting metrics.
                "quantity_volume": _m3_to_cy(total_caulking_volume_m3),
                "unit_volume": "CY",
                "quantity_volume_si": total_caulking_volume_m3,
                "unit_volume_si": "m3",
                "quantity_length": _m_to_lf(total_caulking_length_m) if total_caulking_length_m > 0 else 0.0,
                "unit_length": "LF",
                "quantity_length_si": float(total_caulking_length_m),
                "unit_length_si": "m",
                "division_code": "0792",  # Joint Sealants (MasterFormat); avoid stray matches in 0701 concrete maintenance
            }
            caulking_material["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                "sealant",
                caulking_material,
                rsmeans_id_caulking,
            )
            caulking_material["strict_rsmeans_id_only"] = True
            materials.append(caulking_material)

        if weatherstrip_option != "none" and total_weatherstrip_length_m > 0:
            weatherstrip_material = {
                "name": "weatherstrip",
                "description": weatherstrip_option,
                "quantity": _m_to_lf(total_weatherstrip_length_m),
                "unit": "LF",
                # RSMeans may return weatherstrip unit cost as $/EA (or opening).
                # Apply fixed each length = 3 inches (0.25 ft) to convert EA -> LF.
                "unit_length_per_each_in": 3.0,
                "unit_length_per_each_ft": 0.25,
                "quantity_si": total_weatherstrip_length_m,
                "unit_si": "m",
                "division_code": "08",
            }
            if rsmeans_id_weatherstrip:
                weatherstrip_material["rsmeans_id"] = rsmeans_id_weatherstrip
            materials.append(weatherstrip_material)

        if secondary_glazing_option != "none" and total_secondary_glazing_area_m2 > 0:
            secondary_glazing_qty_sf = _m2_to_sf(total_secondary_glazing_area_m2)
            secondary_glass_thickness_ft = _m_to_ft(float(effective_glass_pane_thickness)) if effective_glass_pane_thickness > 0 else 0.0
            secondary_glazing_material = {
                "name": "secondary glazing",
                "description": (
                    "secondary glazing installation; "
                    f"single-pane thickness {effective_glass_pane_thickness*1000:.1f} mm; "
                    f"gap {effective_gap_thickness*1000:.1f} mm"
                ),
                "quantity": secondary_glazing_qty_sf,
                "unit": "SF",
                "quantity_volume": float(secondary_glazing_qty_sf * secondary_glass_thickness_ft),
                "unit_volume": "CF",
                "rsmeans_thickness_ft": float(secondary_glass_thickness_ft),
                "costing_mode": "volume_from_area",
                "quantity_si": total_secondary_glazing_area_m2,
                "unit_si": "m2",
                "division_code": "08",
            }
            secondary_glazing_material["rsmeans_id"] = self._resolve_glazing_rsmeans_id(
                "secondary glazing",
                secondary_glazing_material,
                rsmeans_id_secondary_glazing,
            )
            secondary_glazing_material["strict_rsmeans_id_only"] = True
            materials.append(secondary_glazing_material)

        return materials

    def _calculate_cost_metrics(
        self,
        runner,
        materials,
        use_custom_costs,
        overhead_profit_percent,
        labor_cost_multiplier,
        total_glazing_area_m2,
        total_secondary_glazing_area_m2,
        total_film_area_m2,
        total_frame_area_m2,
        total_caulking_volume_m3,
        total_caulking_length_m,
        total_weatherstrip_length_m,
        glass_cost_per_cf,
        frame_cost_per_sf,
        caulking_cost_per_cy,
        film_cost_per_sf,
        weatherstrip_cost_per_lf,
        glass_option,
        wf_option,
        caulking_option,
        film_option,
        weatherstrip_option,
        user_num_panes,
        effective_glass_pane_thickness,
        secondary_glazing_option,
        subsurface_dict,
        effective_gap_thickness,
        analysis_period=30,
        glass_lifetime=15,
        wf_lifetime=15,
        caulking_lifetime=10,
        film_lifetime=10,
        weatherstrip_lifetime=10,
    ):
        total_material_cost = 0.0
        total_overhead_profit_cost = 0.0
        total_labor_cost = 0.0
        total_equipment_cost = 0.0
        cost_factor_basis = "not_calculated"
        rsmeans_lookup = None
        rsmeans_summary = {}
        rsmeans_totals_provided = False
        fatal_error = False
        rsmeans_material_features = {}
        rsmeans_glass_cost_per_cf = "N/A"
        rsmeans_glass_cost_per_sf = "N/A"
        rsmeans_frame_cost_per_sf = "N/A"
        rsmeans_caulking_cost_per_cy = "N/A"
        rsmeans_caulking_cost_per_lf = "N/A"
        rsmeans_caulking_pricing_unit_cost = "N/A"
        rsmeans_caulking_pricing_unit_uom = "N/A"
        rsmeans_film_cost_per_sf = "N/A"
        rsmeans_weatherstrip_cost_per_lf = "N/A"
        cost_source = "none"

        if materials:
            if use_custom_costs:
                runner.registerInfo("\n" + "=" * 80)
                runner.registerInfo("USING CUSTOM USER-PROVIDED COSTS (RSMeans API SKIPPED)")
                runner.registerInfo("=" * 80)

                _glass_mult = int(lifetime_multiplier(glass_lifetime, analysis_period))
                _frame_mult = int(lifetime_multiplier(wf_lifetime, analysis_period))
                _caulk_mult = int(lifetime_multiplier(caulking_lifetime, analysis_period))
                _film_mult = int(lifetime_multiplier(film_lifetime, analysis_period))
                _ws_mult = int(lifetime_multiplier(weatherstrip_lifetime, analysis_period))
                total_material_cost = self.calculate_custom_costs_from_user_rates(
                    runner, total_glazing_area_m2, total_secondary_glazing_area_m2, total_film_area_m2,
                    total_frame_area_m2, total_caulking_volume_m3,
                    total_weatherstrip_length_m, glass_cost_per_cf, frame_cost_per_sf,
                    caulking_cost_per_cy, film_cost_per_sf, weatherstrip_cost_per_lf,
                    glass_option, wf_option, caulking_option, film_option, weatherstrip_option,
                    user_num_panes, effective_glass_pane_thickness, secondary_glazing_option,
                    glass_multiplier=_glass_mult,
                    frame_multiplier=_frame_mult,
                    caulking_multiplier=_caulk_mult,
                    film_multiplier=_film_mult,
                    weatherstrip_multiplier=_ws_mult,
                )
                total_labor_cost = (
                    total_material_cost * (labor_cost_multiplier - 1.0)
                    if labor_cost_multiplier > 1.0 else 0.0
                )
                cost_factor_basis = "custom_user_inputs"
                cost_source = "custom_input"

                runner.registerInfo(f"✓ Custom costs calculated: ${total_material_cost:,.2f} (material) + ${total_labor_cost:,.2f} (labor) (multiplier={labor_cost_multiplier})")
            else:
                runner.registerInfo("\n" + "=" * 80)
                runner.registerInfo("ATTEMPTING RSMeans API LOOKUP FOR CAPITAL COSTS")
                runner.registerInfo("=" * 80)

                rsmeans_lookup = self.pull_rsmeans_cost_from_api(
                    runner,
                    materials,
                    use_custom_costs=False,
                    overhead_profit_percent=overhead_profit_percent,
                )

                if rsmeans_lookup and rsmeans_lookup.get("status") == "ok":
                    summary = rsmeans_lookup.get("summary", {})
                    total_material_cost = float(summary.get("total_material_cost", 0.0))
                    total_labor_cost = float(summary.get("total_labor_cost", 0.0))
                    total_equipment_cost = float(summary.get("total_equipment_cost", 0.0))
                    total_overhead_profit_cost = float(summary.get("total_overhead_profit_cost", 0.0))
                    cost_factor_basis = "rsmeans_api"
                    cost_source = "rsmeans_api"
                    rsmeans_summary = summary
                    rsmeans_totals_provided = True

                    # Ensure RSMeans detail keys are always written on successful API responses.
                    rsmeans_material_features.update({
                        "window_glass_rsmeans_id": "N/A",
                        "window_glass_rsmeans_description": "N/A",
                        "window_frame_rsmeans_id": "N/A",
                        "window_frame_rsmeans_description": "N/A",
                        "window_caulking_rsmeans_id": "N/A",
                        "window_caulking_rsmeans_description": "N/A",
                        "window_film_rsmeans_id": "N/A",
                        "window_film_rsmeans_description": "N/A",
                        "window_weatherstrip_rsmeans_id": "N/A",
                        "window_weatherstrip_rsmeans_description": "N/A",
                        "window_secondary_glazing_rsmeans_id": "N/A",
                        "window_secondary_glazing_rsmeans_description": "N/A",
                    })

                    runner.registerInfo(f"✓ RSMeans API successful:")
                    runner.registerInfo(f"  Materials found: {summary.get('materials_count', 0)}")
                    runner.registerInfo(f"  Total material cost: ${summary.get('total_material_cost', 0):,.2f}")
                    runner.registerInfo(f"  Overhead + Profit: ${summary.get('total_overhead_profit_cost', 0):,.2f}")
                    runner.registerInfo(f"  Total cost with O&P: ${total_material_cost:,.2f}")
                    materials_results = rsmeans_lookup.get("results", {}).get("materials", [])

                    if materials_results:
                        for mat in materials_results:
                            mat_name = str(mat.get("name", "")).strip().lower()
                            matched_rsmeans_id = mat.get("rsmeans_id", "")
                            matched_rsmeans_description = mat.get("rsmeans_description") or mat.get("description", "")

                            feature_prefix = None
                            if "glazing film" in mat_name:
                                feature_prefix = "window_film"
                            elif "window glazing" in mat_name or mat_name == "glazing":
                                feature_prefix = "window_glass"
                            elif "window frame" in mat_name:
                                feature_prefix = "window_frame"
                            elif "weatherstrip" in mat_name:
                                feature_prefix = "window_weatherstrip"
                            elif "secondary glazing" in mat_name:
                                feature_prefix = "window_secondary_glazing"
                            elif "sealant" in mat_name or "caulking" in mat_name:
                                feature_prefix = "window_caulking"

                            if feature_prefix:
                                if matched_rsmeans_id:
                                    rsmeans_material_features[f"{feature_prefix}_rsmeans_id"] = str(matched_rsmeans_id)
                                if matched_rsmeans_description:
                                    rsmeans_material_features[f"{feature_prefix}_rsmeans_description"] = str(matched_rsmeans_description)

                    if materials_results:
                        runner.registerInfo("  RSMeans materials detail:")
                        for mat in materials_results:
                            mat_name = mat.get("name", "(unknown)")
                            mat_qty = mat.get("quantity", 0.0)
                            mat_unit = mat.get("unit", "")
                            mat_unit_cost = mat.get("unit_cost", 0.0)
                            mat_total_cost = mat.get("total_cost", 0.0)
                            mat_basis = mat.get("unit_cost_basis", mat_unit)
                            runner.registerInfo(
                                f"    - {mat_name}: {mat_qty:.2f} {mat_unit}, "
                                f"unit=${mat_unit_cost:.2f}/{mat_basis}, total=${mat_total_cost:,.2f}"
                            )

                    # Apply per-material lifetime multipliers to RSMeans costs.
                    if materials_results:
                        _lc_mult_map = [
                            ("glazing film",     int(lifetime_multiplier(film_lifetime, analysis_period))),
                            ("secondary glazing", int(lifetime_multiplier(glass_lifetime, analysis_period))),
                            ("window glazing",   int(lifetime_multiplier(glass_lifetime, analysis_period))),
                            ("glazing",          int(lifetime_multiplier(glass_lifetime, analysis_period))),
                            ("window frame",     int(lifetime_multiplier(wf_lifetime, analysis_period))),
                            ("weatherstrip",     int(lifetime_multiplier(weatherstrip_lifetime, analysis_period))),
                            ("sealant",          int(lifetime_multiplier(caulking_lifetime, analysis_period))),
                            ("caulking",         int(lifetime_multiplier(caulking_lifetime, analysis_period))),
                        ]
                        _adj_mat_total = 0.0
                        _adj_lab_total = 0.0
                        _adj_eq_total = 0.0
                        for _m in materials_results:
                            _mn = str(_m.get("name", "")).strip().lower()
                            _mc = float(_m.get("total_cost", 0.0))
                            _ml = float(_m.get("total_labor_cost", 0.0))
                            _me = float(_m.get("total_equipment_cost", 0.0))
                            _mm = float(_m.get("total_material_cost", _mc) or 0.0)
                            _m["total_cost_pre_lifetime"] = _mc
                            _m["total_labor_cost_pre_lifetime"] = _ml
                            _m["total_equipment_cost_pre_lifetime"] = _me
                            _m["total_material_cost_pre_lifetime"] = _mm
                            _lc_m = 1
                            for _key, _mult in _lc_mult_map:
                                if _key in _mn:
                                    _lc_m = _mult
                                    break
                            _m["total_cost"] = _mc * _lc_m
                            _m["total_labor_cost"] = _ml * _lc_m
                            _m["total_equipment_cost"] = _me * _lc_m
                            _adj_mat_total += _m["total_cost"]
                            _adj_lab_total += _m["total_labor_cost"]
                            _adj_eq_total += _m["total_equipment_cost"]
                        _ohp_pct = float(summary.get("overhead_profit_percent", 0.0))
                        total_material_cost = _adj_mat_total
                        total_labor_cost = _adj_lab_total
                        total_equipment_cost = _adj_eq_total
                        total_overhead_profit_cost = (
                            (_adj_mat_total + _adj_lab_total + _adj_eq_total)
                            * _ohp_pct * 0.01
                        )
                        summary["total_material_cost"] = total_material_cost
                        summary["total_labor_cost"] = total_labor_cost
                        summary["total_equipment_cost"] = total_equipment_cost
                        summary["total_overhead_profit_cost"] = total_overhead_profit_cost
                        summary["total_cost_with_overhead_profit"] = (
                            total_material_cost
                            + total_labor_cost
                            + total_equipment_cost
                            + total_overhead_profit_cost
                        )
                        runner.registerInfo(
                            f"RSMeans costs scaled by lifetime multipliers. "
                            f"Lifecycle material=${total_material_cost:,.2f} "
                            f"labor=${total_labor_cost:,.2f} equipment=${total_equipment_cost:,.2f}"
                        )

                    if materials_results:
                        _glass_cost_total = 0.0
                        _frame_cost_total = 0.0
                        _caulking_cost_total = 0.0
                        _film_cost_total = 0.0
                        _weatherstrip_cost_total = 0.0
                        _glass_unit_cost_cf = None
                        _glass_unit_cost_sf = None
                        _frame_unit_cost_sf = None
                        _caulking_unit_cost_cy = None
                        _caulking_pricing_unit_cost = None
                        _caulking_pricing_unit_uom = None
                        _film_unit_cost_sf = None
                        _weatherstrip_unit_cost_lf = None

                        _frame_window_area_sf = 0.0
                        for _m in materials_results:
                            _mn = str(_m.get("name", "")).strip().lower()
                            _basis = str(_m.get("bare_material_unit_basis", _m.get("unit_cost_basis", _m.get("unit", "")))).upper().replace(" ", "")
                            _mode = str(_m.get("costing_mode", "")).strip().lower()
                            _bare_unit = float(_m.get("bare_material_unit_cost", 0.0) or 0.0)
                            _pricing_eff = float(_m.get("pricing_unit_cost_effective", 0.0) or 0.0)
                            _pricing_eff_uom = str(_m.get("pricing_unit_uom_effective", "")).upper().replace(" ", "")
                            _pricing_raw = float(_m.get("pricing_unit_cost_raw", 0.0) or 0.0)
                            _pricing_raw_uom = str(_m.get("pricing_unit_uom_raw", "")).upper().replace(" ", "")
                            # API unit-rate fields are intentionally bare material
                            # unit costs (pre-lifetime). Do not use installed totals
                            # in this chain, so API vs CUSTOM stays comparable.
                            _mc = float(
                                _m.get(
                                    "total_material_cost_pre_lifetime",
                                    _m.get(
                                        "total_material_cost",
                                        _m.get("total_cost_pre_lifetime", _m.get("total_cost", 0.0)),
                                    ),
                                )
                                or 0.0
                            )
                            if _mn == "glazing film":
                                _film_cost_total += _mc
                                if _pricing_eff > 0.0 and _pricing_eff_uom == "SF":
                                    _film_unit_cost_sf = _pricing_eff
                                if _bare_unit > 0.0:
                                    if _basis == "SF":
                                        _film_unit_cost_sf = _bare_unit
                            elif _mn in ["window glazing", "glazing", "secondary glazing"]:
                                _glass_cost_total += _mc
                                if _pricing_eff > 0.0:
                                    if _pricing_eff_uom == "CF":
                                        _glass_unit_cost_cf = _pricing_eff
                                    elif _pricing_eff_uom == "SF":
                                        _glass_unit_cost_sf = _pricing_eff
                                if _bare_unit > 0.0:
                                    if _basis == "CF":
                                        _glass_unit_cost_cf = _bare_unit
                                    elif _basis == "SF":
                                        _glass_unit_cost_sf = _bare_unit
                                    elif _basis == "SF" and _mode == "volume_from_area":
                                        _src_thk_ft = float(_m.get("source_line_thickness_ft", 0.0) or 0.0)
                                        if _src_thk_ft > 0.0:
                                            _glass_unit_cost_cf = _bare_unit / _src_thk_ft
                            elif _mn == "window frame":
                                _frame_cost_total += _mc
                                _frame_window_area_sf = float(_m.get("window_area_sf", 0.0) or 0.0)
                                if _pricing_eff > 0.0 and _pricing_eff_uom == "SF":
                                    _frame_unit_cost_sf = _pricing_eff
                            elif _mn in ["sealant", "caulking"]:
                                _caulking_cost_total += _mc
                                if _pricing_raw > 0.0 and _pricing_raw_uom:
                                    _caulking_pricing_unit_cost = _pricing_raw
                                    _caulking_pricing_unit_uom = _pricing_raw_uom
                                if _pricing_eff > 0.0 and _pricing_eff_uom == "CY":
                                    _caulking_unit_cost_cy = _pricing_eff
                                if _bare_unit > 0.0:
                                    if _basis == "CY":
                                        _caulking_unit_cost_cy = _bare_unit
                                    elif _basis == "GAL":
                                        _caulking_unit_cost_cy = _bare_unit * 201.974
                            elif _mn == "weatherstrip":
                                _weatherstrip_cost_total += _mc
                                if _pricing_eff > 0.0 and _pricing_eff_uom == "LF":
                                    _weatherstrip_unit_cost_lf = _pricing_eff
                                if _bare_unit > 0.0:
                                    if _basis == "LF":
                                        _weatherstrip_unit_cost_lf = _bare_unit
                                    elif _basis == "EA":
                                        _len_each_ft = float(_m.get("unit_length_per_each_ft", 0.0) or 0.0)
                                        if _len_each_ft > 0.0:
                                            _weatherstrip_unit_cost_lf = _bare_unit / _len_each_ft

                        _glass_volume_cf = (
                            (float(total_glazing_area_m2) + float(total_secondary_glazing_area_m2))
                            * float(effective_glass_pane_thickness)
                            * 35.3146667
                        )
                        _frame_area_sf = float(total_frame_area_m2) * 10.7639
                        _caulking_volume_cy = float(total_caulking_volume_m3) * 1.30795
                        _caulking_length_lf = float(total_caulking_length_m) * 3.28084
                        _film_area_sf = float(total_film_area_m2) * 10.7639
                        _weatherstrip_length_lf = float(total_weatherstrip_length_m) * 3.28084

                        if _glass_unit_cost_cf is not None and _glass_unit_cost_cf > 0.0:
                            rsmeans_glass_cost_per_cf = _glass_unit_cost_cf
                        if _glass_unit_cost_sf is not None and _glass_unit_cost_sf > 0.0:
                            rsmeans_glass_cost_per_sf = _glass_unit_cost_sf
                        if _frame_unit_cost_sf is not None and _frame_unit_cost_sf > 0.0:
                            rsmeans_frame_cost_per_sf = _frame_unit_cost_sf
                        if _caulking_unit_cost_cy is not None and _caulking_unit_cost_cy > 0.0:
                            rsmeans_caulking_cost_per_cy = _caulking_unit_cost_cy
                        if _caulking_pricing_unit_cost is not None and _caulking_pricing_unit_cost > 0.0:
                            rsmeans_caulking_pricing_unit_cost = _caulking_pricing_unit_cost
                            rsmeans_caulking_pricing_unit_uom = _caulking_pricing_unit_uom or "N/A"
                        if _film_unit_cost_sf is not None and _film_unit_cost_sf > 0.0:
                            rsmeans_film_cost_per_sf = _film_unit_cost_sf
                        if _weatherstrip_unit_cost_lf is not None and _weatherstrip_unit_cost_lf > 0.0:
                            rsmeans_weatherstrip_cost_per_lf = _weatherstrip_unit_cost_lf

                    self.apply_rsmeans_glazing_updates_to_model(
                        runner,
                        subsurface_dict,
                        rsmeans_lookup,
                        effective_glass_pane_thickness,
                        effective_gap_thickness,
                    )

                else:
                    runner.registerInfo("✗ RSMeans API lookup failed or returned no costs.")
                    runner.registerInfo("\nFalling back to user-provided cost data...")

                    _glass_mult_fb = int(lifetime_multiplier(glass_lifetime, analysis_period))
                    _frame_mult_fb = int(lifetime_multiplier(wf_lifetime, analysis_period))
                    _caulk_mult_fb = int(lifetime_multiplier(caulking_lifetime, analysis_period))
                    _film_mult_fb = int(lifetime_multiplier(film_lifetime, analysis_period))
                    _ws_mult_fb = int(lifetime_multiplier(weatherstrip_lifetime, analysis_period))
                    total_material_cost = self.calculate_custom_costs_from_user_rates(
                        runner, total_glazing_area_m2, total_secondary_glazing_area_m2, total_film_area_m2,
                        total_frame_area_m2, total_caulking_volume_m3,
                        total_weatherstrip_length_m, glass_cost_per_cf, frame_cost_per_sf,
                        caulking_cost_per_cy, film_cost_per_sf, weatherstrip_cost_per_lf,
                        glass_option, wf_option, caulking_option, film_option, weatherstrip_option,
                        user_num_panes, effective_glass_pane_thickness, secondary_glazing_option,
                        glass_multiplier=_glass_mult_fb,
                        frame_multiplier=_frame_mult_fb,
                        caulking_multiplier=_caulk_mult_fb,
                        film_multiplier=_film_mult_fb,
                        weatherstrip_multiplier=_ws_mult_fb,
                    )
                    total_labor_cost = (
                        total_material_cost * (labor_cost_multiplier - 1.0)
                        if labor_cost_multiplier > 1.0 else 0.0
                    )
                    if total_material_cost > 0:
                        cost_factor_basis = "custom_user_inputs"
                        cost_source = "custom_input_fallback"

                    if total_material_cost > 0:
                        runner.registerInfo(f"✓ Using user-provided costs: ${total_material_cost:,.2f} materials + ${total_labor_cost:,.2f} labor (multiplier={labor_cost_multiplier})")
                    else:
                        runner.registerError(
                            "RSMeans lookup failed/returned no costs AND no custom cost rates were "
                            "provided. The window enhancement cost cannot be determined.\n"
                            "SOLUTION: Retry the measure with custom cost input:\n"
                            "  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
                            "  2. Provide non-zero values for the relevant component rates: "
                            "'custom_glass_cost_per_cf', 'custom_frame_cost_per_sf', "
                            "'custom_caulking_cost_per_cy', 'custom_film_cost_per_sf', "
                            "'custom_weatherstrip_cost_per_lf' (only the components used by your "
                            "selected glass/frame/caulking/film/weatherstrip options need values)."
                        )
                        fatal_error = True

        if not rsmeans_totals_provided:
            total_overhead_profit_cost = (total_material_cost + total_labor_cost) * (overhead_profit_percent / 100.0)
        if rsmeans_totals_provided:
            total_cost_with_overhead_profit = float(rsmeans_summary.get("total_cost_with_overhead_profit", 0.0))
        else:
            total_cost_with_overhead_profit = total_material_cost + total_labor_cost + total_overhead_profit_cost

        return {
            "total_material_cost": total_material_cost,
            "total_labor_cost": total_labor_cost,
            "total_equipment_cost": total_equipment_cost,
            "total_overhead_profit_cost": total_overhead_profit_cost,
            "total_cost_with_overhead_profit": total_cost_with_overhead_profit,
            "cost_factor_basis": cost_factor_basis,
            "rsmeans_material_features": rsmeans_material_features,
            "rsmeans_glass_cost_per_cf": rsmeans_glass_cost_per_cf,
            "rsmeans_glass_cost_per_sf": rsmeans_glass_cost_per_sf,
            "rsmeans_frame_cost_per_sf": rsmeans_frame_cost_per_sf,
            "rsmeans_caulking_cost_per_cy": rsmeans_caulking_cost_per_cy,
            "rsmeans_caulking_cost_per_lf": rsmeans_caulking_cost_per_lf,
            "rsmeans_caulking_pricing_unit_cost": rsmeans_caulking_pricing_unit_cost,
            "rsmeans_caulking_pricing_unit_uom": rsmeans_caulking_pricing_unit_uom,
            "rsmeans_film_cost_per_sf": rsmeans_film_cost_per_sf,
            "rsmeans_weatherstrip_cost_per_lf": rsmeans_weatherstrip_cost_per_lf,
            "cost_source": cost_source,
            "fatal_error": fatal_error,
        }

    def _update_cost_and_rsmeans_feature_maps(
        self,
        results_features,
        factors_features,
        mtrl_prop_features,
        total_material_cost,
        total_labor_cost,
        total_equipment_cost,
        total_overhead_profit_cost,
        total_cost_with_overhead_profit,
        cost_factor_basis,
        overhead_profit_percent,
        labor_cost_multiplier,
        rsmeans_material_features,
        glass_cost_per_cf,
        frame_cost_per_sf,
        caulking_cost_per_cy,
        film_cost_per_sf,
        weatherstrip_cost_per_lf,
        rsmeans_glass_cost_per_cf,
        rsmeans_glass_cost_per_sf,
        rsmeans_frame_cost_per_sf,
        rsmeans_caulking_cost_per_cy,
        rsmeans_caulking_cost_per_lf,
        rsmeans_caulking_pricing_unit_cost,
        rsmeans_caulking_pricing_unit_uom,
        rsmeans_film_cost_per_sf,
        rsmeans_weatherstrip_cost_per_lf,
        cost_source,
    ):
        results_features.update({
            "window_material_cost_$": total_material_cost,
            "window_labor_cost_$": total_labor_cost,
            "window_equipment_cost_$": total_equipment_cost,
            "window_overhead_profit_cost_$": total_overhead_profit_cost,
            "window_total_cost_with_overhead_and_profit_$": total_cost_with_overhead_profit,
            "window_cost_factor_basis": cost_factor_basis,
        })

        factors_features.update({
            "window_cost_source": cost_source,
            "window_overhead_profit_percent": overhead_profit_percent,
            "window_cost_factor_basis": cost_factor_basis,
        })
        if cost_source == "rsmeans_api":
            # Keep API factors as bare material unit costs.
            factors_features.update({
                "window_api_glass_cost_per_cf": rsmeans_glass_cost_per_cf,
                "window_api_frame_cost_per_sf": rsmeans_frame_cost_per_sf,
                "window_api_caulking_cost_per_cy": rsmeans_caulking_cost_per_cy,
                "window_api_film_cost_per_sf": rsmeans_film_cost_per_sf,
                "window_api_weatherstrip_cost_per_lf": rsmeans_weatherstrip_cost_per_lf,
                "window_api_caulking_pricing_unit_cost": rsmeans_caulking_pricing_unit_cost,
                "window_api_caulking_pricing_unit_uom": rsmeans_caulking_pricing_unit_uom,
            })
        if cost_source in ("custom_input", "custom_input_fallback"):
            # Keep custom factors as user-entered bare material unit costs.
            factors_features.update({
                "window_custom_labor_cost_multiplier": labor_cost_multiplier,
                "window_custom_glass_cost_per_cf": glass_cost_per_cf,
                "window_custom_frame_cost_per_sf": frame_cost_per_sf,
                "window_custom_caulking_cost_per_cy": caulking_cost_per_cy,
                "window_custom_film_cost_per_sf": film_cost_per_sf,
                "window_custom_weatherstrip_cost_per_lf": weatherstrip_cost_per_lf,
            })
        mtrl_prop_features.update(rsmeans_material_features)

    def _update_gwp_and_construction_feature_maps(self, subsurface_dict, factors_features, basic_input_features):
        gwp_glass_per_m2_list = []
        gwp_glass_per_m3_list = []
        gwp_frame_per_m2_list = []
        gwp_caulking_per_m3_list = []
        gwp_film_per_m2_list = []
        gwp_weatherstrip_per_m_list = []
        gwp_second_glazing_per_m2_list = []

        for name in subsurface_dict.keys():
            if 'glass' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['glass']:
                gwp_m2 = subsurface_dict[name]['glass']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_glass_per_m2_list.append(gwp_m2)

            if 'glass' in subsurface_dict[name] and 'gwp_per_m3' in subsurface_dict[name]['glass']:
                gwp_m3 = subsurface_dict[name]['glass']['gwp_per_m3']
                if gwp_m3 is not None and gwp_m3 > 0:
                    gwp_glass_per_m3_list.append(gwp_m3)

            if 'frame' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['frame']:
                gwp_m2 = subsurface_dict[name]['frame']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_frame_per_m2_list.append(gwp_m2)

            if 'caulking' in subsurface_dict[name] and 'gwp_per_m3' in subsurface_dict[name]['caulking']:
                gwp_m3 = subsurface_dict[name]['caulking']['gwp_per_m3']
                if gwp_m3 is not None and gwp_m3 > 0:
                    gwp_caulking_per_m3_list.append(gwp_m3)

            if 'film' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['film']:
                gwp_m2 = subsurface_dict[name]['film']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_film_per_m2_list.append(gwp_m2)

            if 'weatherstrip' in subsurface_dict[name] and 'gwp_per_m' in subsurface_dict[name]['weatherstrip']:
                gwp_m = subsurface_dict[name]['weatherstrip']['gwp_per_m']
                if gwp_m is not None and gwp_m > 0:
                    gwp_weatherstrip_per_m_list.append(gwp_m)

            if 'second_glazing' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['second_glazing']:
                gwp_m2 = subsurface_dict[name]['second_glazing']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_second_glazing_per_m2_list.append(gwp_m2)

        if gwp_glass_per_m2_list:
            factors_features["window_glass_gwp_per_m2_kgCO2eq"] = float(np.mean(gwp_glass_per_m2_list))
        if gwp_glass_per_m3_list:
            factors_features["window_glass_gwp_per_m3_kgCO2eq"] = float(np.mean(gwp_glass_per_m3_list))
        if gwp_frame_per_m2_list:
            factors_features["window_frame_gwp_per_m2_kgCO2eq"] = float(np.mean(gwp_frame_per_m2_list))
        if gwp_caulking_per_m3_list:
            factors_features["window_caulking_gwp_per_m3_kgCO2eq"] = float(np.mean(gwp_caulking_per_m3_list))
        if gwp_film_per_m2_list:
            factors_features["window_film_gwp_per_m2_kgCO2eq"] = float(np.mean(gwp_film_per_m2_list))
        if gwp_weatherstrip_per_m_list:
            factors_features["window_weatherstrip_gwp_per_m_kgCO2eq"] = float(np.mean(gwp_weatherstrip_per_m_list))
        if gwp_second_glazing_per_m2_list:
            factors_features["window_secondary_glazing_gwp_per_m2_kgCO2eq"] = float(np.mean(gwp_second_glazing_per_m2_list))

        construction_names = []
        for name in subsurface_dict.keys():
            if 'glass' in subsurface_dict[name] and 'object' in subsurface_dict[name]['glass']:
                construction = subsurface_dict[name]['glass']['object']
                if construction is not None:
                    construction_names.append(construction.nameString())

        if construction_names:
            basic_input_features["window_construction_names"] = ', '.join(construction_names)

    def get_frame_and_divider_dimension(self, runner, subsurface):
        """Get dimensions of window frame and any dividers (muntins).
        
        Extracts frame width and divider dimensions to calculate actual glazing area.
        Returns (frame_width, divider_width, num_horizontal_dividers, num_vertical_dividers).
        """
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
                runner.registerInfo(f"  ℹ Frame '{frame_name}': No dividers")

            runner.registerInfo(f"  ℹ Frame and divider: {frame_name}")
            runner.registerInfo(f"    Frame width: {frame_width*1000:.1f}mm | Divider width: {divider_width*1000:.1f}mm")
        else:
            runner.registerInfo(f"  ℹ No frame and divider for {subsurface.nameString()}")
        return frame_width,divider_width,num_hori_divider,num_verti_divider

# Register the measure
WindowEnhancement().registerWithApplication()

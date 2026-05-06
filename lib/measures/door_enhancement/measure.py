# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

# =============================================================================
# DoorEnhancement – execution flow overview
# =============================================================================
# Phase 1 – Argument parsing and validation
#   Read all user arguments; resolve seal/door options and length-per-unit
#   defaults; validate numeric ranges.
#
# Phase 2 – Infiltration reduction
#   Reduce SpaceInfiltrationDesignFlowRate values by the requested percentage
#   for all spaces in the selected space type (or whole building).
#
# Phase 3 – Embodied carbon (EC) calculation
#   For each door subsurface: fetch EC3 EPD data for bottom seal, top/side
#   seal, and optional door replacement; compute per-functional-unit GWP;
#   accumulate total embodied carbon over the analysis period.
#
# Phase 4 – RSMeans cost lookup
#   Build search-material records for the door, bottom seal, and top/side seal;
#   call pull_rsmeans_cost_from_api() which invokes search_materials_across_
#   catalogs() from resources/call_rsmeans_api.py.  If use_custom_costs=True,
#   build a synthetic result dict instead.
#
# Phase 5 – AdditionalProperties storage
#   Write all outputs into the five standard buckets:
#     Building   → basic_input  (measure name, analysis period, GWP statistic)
#     Site       → reno_detail  (renovation quantities, sealing options)
#     Facility   → factors      (cost totals, cost_source, cost_factor_basis,
#                                GWP factors)
#     SimControl → results      (mirrored cost scalars + three RSMeans JSON
#                                diagnostic payloads)
#     SizingPara → mtrl_prop    (door material properties, RSMeans hints)
# =============================================================================

import openstudio
import typing
import json
import re
from resources.call_rsmeans_api import RSMeansAPIClient, run_rsmeans_cost_lookup
import numpy as np
from resources.EC3_lookup import (
    calculate_geometry,
    extract_numeric_value,
    fetch_epd_data,
    generate_url_byname,
    lifetime_multiplier,
    parse_product_epd,
)

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
        return ("Improves door performance by adding weatherstripping seals (bottom, top, and side) "
                "and optionally replacing doors with more thermally efficient options. The measure "
                "calculates the embodied carbon impact using Environmental Product Declaration (EPD) "
                "data from the EC3 database and adjusts space infiltration rates to reflect improved "
                "air sealing. Requires an EC3 API key and Python libraries (numpy, pandas, urllib3).")

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure performs two main functions:\n\n"
                "1. **Infiltration Reduction**: Reduces space infiltration rates by a user-specified "
                "percentage (default 30%) to simulate improved air sealing from weatherstripping. "
                "The reduction applies to all door-containing spaces in the selected space type or "
                "entire building.\n\n"
                "2. **Embodied Carbon Calculation**: Calculates life-cycle embodied carbon (kg CO2 eq) "
                "for door enhancement materials over the analysis period, including:\n"
                "   - Bottom seals: brush weatherstrip, automatic door bottom, or silicone smoke gasket\n"
                "   - Top/side seals: silicone smoke gasket or jamb weatherstrip\n"
                "   - Optional door replacement: wood, glass, garage, or insulated steel core doors\n\n"
                "3. **Thermal Performance Update**: When replacing doors, the measure updates door "
                "constructions with new R-values based on material properties (thickness, conductivity, "
                "density) from literature sources or user inputs.\n\n"
                "The measure retrieves EPD data from the EC3 database via API, calculates statistical "
                "GWP values (min/max/mean/median), removes outliers, and accounts for product lifetimes "
                "and replacement cycles over the analysis period. Results are attached as additional "
                "properties to each modified door subsurface.")
    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]
        
    @staticmethod
    def bottom_seal_options():
        return ["none","brush weatherstrip","automatic door bottom","silicone adhesive smoke gasket"]
    
    @staticmethod
    def top_side_seal_options():
        return ["none","silicone adhesive smoke gasket", "jamb weatherstrip"]
    
    @staticmethod
    def door_options():
        return ['none','wooden door','garage door','glass door','polystyrene core steel door', 'polyurethane core steel door','honeycomb core steel door','stiffened core steel door']

    @staticmethod
    def door_service_life(door_option):
        """Return reference service life (years) for a given door option.
        Returns the service_life from door_material_properties().
        """
        mat_props = DoorEnhancement.door_material_properties()
        if door_option in mat_props:
            return mat_props[door_option]['service_life']
        else:
            return 30  # Default to 30 years if option not found

    @staticmethod
    def door_r_values():
        """Return typical R-values (m²·K/W) for different door types.
        These are calculated from material properties: R = thickness / conductivity
        Sources: 
        - Wooden door: https://www.energystar.gov/products/building_products/doors
        - Steel core doors: https://www.dasma.com/garage-door-r-values/
        - Glass door: https://www.nfrc.org/
        """
        mat_props = DoorEnhancement.door_material_properties()
        r_values = {}
        for door_type, props in mat_props.items():
            if props['conductivity'] > 0.0 and props['thickness'] > 0.0:
                r_values[door_type] = props['thickness'] / props['conductivity']
            else:
                r_values[door_type] = 0.0
        return r_values

    @staticmethod
    def door_material_properties():
        """Return material properties (conductivity W/m·K, density kg/m³, thickness m, service_life years) for different door types.
        R-value is calculated as: R = thickness / conductivity
        """
        return {
            'none': {'conductivity': 0.0, 'density': 0.0, 'thickness': 0.0, 'service_life': 0},
            'wooden door': {'conductivity': 0.15, 'density': 638, 'thickness': 0.04445, 'service_life': 20}, # Density&thickness is from: https://www.vtindustries.com/webres/File/architectural-doors/Sustainability/VT%20AWD%20EPD%20030821_Final.pdf；k is from ASHRAE Handbook – Fundamentals: Lists particleboard/wood composites in 0.12–0.18 W/m·K range.
            'garage door': {'conductivity': 0.025, 'density': 477, 'thickness': 0.04445, 'service_life': 15}, # RSL is from EPD of BOTTICELLI SMART BT A850 23V; other information estimated from EPD
            'glass door': {'conductivity': 0.1, 'density': 2500, 'thickness': 0.05, 'service_life': 25}, # Use density of glass; RSL: ALUPROF Aluminum systems: window and door system; thickness: https://www.modernfoldstyles.com/PDFs/Glass%20Acoustic%20Brochure%20and%20Spec.pdf; Conductivity: https://search.nfrc.org/search/cpd/cpd_search_detail.aspx?cpdnum=PAN-K-3
            'polystyrene core steel door': {'conductivity': 0.104, 'density': 472.3, 'thickness': 0.04445, 'service_life': 30}, # RSL,Density,thickness and thermal conductivity is from: EPD of DE LA FONTAINE's commercial steel door
            'polyurethane core steel door': {'conductivity': 0.096, 'density': 490, 'thickness': 0.04445, 'service_life': 30}, # RSL,Density, thickness and thermal conductivity is from: EPD of DE LA FONTAINE's commercial steel door
            'honeycomb core steel door': {'conductivity': 0.05, 'density': 481.6, 'thickness': 0.04445, 'service_life': 30}, # RSL,Density, thickness and thermal conductivity is from: EPD of DE LA FONTAINE's commercial steel door
            'stiffened core steel door': {'conductivity': 0.139, 'density': 570.9, 'thickness': 0.04445, 'service_life': 30} # RSL,Density, thickness and thermal conductivity is from: EPD of DE LA FONTAINE's commercial steel door
        }

    def generate_sealing_url(self,option):
        url = None
        if option == "brush weatherstrip":
            url = generate_url_byname(name_like = 'brush weatherstrip', category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d')
        elif option == "automatic door bottom":
            url = generate_url_byname(name_like = 'automatic door bottom', category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d')
        elif option == "silicone adhesive smoke gasket":
            url = generate_url_byname(name_like = 'silicone adhesive smoke gasket', category = 'ca54e842c0fc4bf2b4f3a8564c3b1a4d')
        elif option == "jamb weatherstrip":
            url = generate_url_byname(name_like = 'jamb weatherstripping')
        else:
            url = None
        return url
    
    def generate_door_url(self, option, subsurface_type):
        door_product_url = None
        if option == 'wooden door':
            door_product_url = generate_url_byname(name_like = 'wood door leaf')
        elif option == 'glass door':
            door_product_url = generate_url_byname(name_like = 'sliding glass door')
        elif option == 'garage door':
            door_product_url = generate_url_byname(name_like = 'garage door', plant_geography = '150')
        elif option == 'stiffened core steel door':
            door_product_url = generate_url_byname(name_like = 'stiffened core', category = 'e9605505973e4f088078c6f53e58129f')
        elif option in ['honeycomb core steel door','polystyrene core steel door','polyurethane core steel door']:
            door_product_url = generate_url_byname(name_like = option)
        else:
            door_product_url = None

        return door_product_url

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
        space_infiltration_reduction_percent.setDefaultValue(30.0)
        space_infiltration_reduction_percent.setUnits("%")
        args.append(space_infiltration_reduction_percent)

        # make an argument for alter_coef
        alter_coef = openstudio.measure.OSArgument.makeBoolArgument('alter_coef', True)
        alter_coef.setDisplayName('Alter constant temperature and wind speed coefficients.')
        alter_coef.setDescription('Setting this to false will result in infiltration objects that maintain the coefficients from the initial model. This option is disabled for this measure and coefficients are always preserved.')
        alter_coef.setDefaultValue(False)
        args.append(alter_coef)

        door_area_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("door_area_per_unit", True)
        door_area_per_unit.setDisplayName("Door Area per Unit")
        door_area_per_unit.setDescription("Area per unit of door leaf in m2, used for GWP calculations. Default is 1.95 m2 based on PCR for door leaf. Adjust if your doors are significantly larger or smaller than this reference area.")
        door_area_per_unit.setDefaultValue(1.95)
        args.append(door_area_per_unit)

        #make an argument for analysis period
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        #make an argument for bottom seal options for filtering EPDs of bottom seal
        door_bottom_seal_options_chs = openstudio.StringVector()
        for option in self.bottom_seal_options():
            door_bottom_seal_options_chs.append(option)
        door_bottom_seal_option = openstudio.measure.OSArgument.makeChoiceArgument("door_bottom_seal_option", door_bottom_seal_options_chs, True)
        door_bottom_seal_option.setDisplayName("Door Bottom Seal Option") 
        door_bottom_seal_option.setDescription("Select none if no bottom seal is to be installed, otherwise select the type of bottom seal to be installed.")
        door_bottom_seal_option.setDefaultValue("automatic door bottom")
        args.append(door_bottom_seal_option)

        #make an argument for top and side seal options for filtering EPDs of top and side seal
        door_top_side_seal_options_chs = openstudio.StringVector()
        for option in self.top_side_seal_options():
            door_top_side_seal_options_chs.append(option)
        door_top_side_seal_option = openstudio.measure.OSArgument.makeChoiceArgument("door_top_side_seal_option", door_top_side_seal_options_chs, True)
        door_top_side_seal_option.setDisplayName("Door Top and Side Seal Option")
        door_top_side_seal_option.setDescription("Select none if no top or side seal is to be installed, otherwise select the type of top or side seal to be installed.")
        door_top_side_seal_option.setDefaultValue("jamb weatherstrip")
        args.append(door_top_side_seal_option)

        # make an argument for door options for filtering EPDs of door
        door_options_chs = openstudio.StringVector()
        for option in self.door_options():
            door_options_chs.append(option)
        door_option = openstudio.measure.OSArgument.makeChoiceArgument("door_option", door_options_chs, True)
        door_option.setDisplayName("door option")   
        door_option.setDescription("Select none if no door is to be installed, otherwise select the type of door to be installed.")
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
        door_lifetime.setDescription("Life expectancy of door (years). Default values are based on door type: wooden=20, garage=20, glass=25, steel core doors=30 years. These reference service life (RSL) values are from industry standards (Steel Door Institute, Door and Hardware Institute, NAHB).")
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

        # make an argument for length per unit of sealing strip
        length_per_unit_bottom_side = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit_bottom_side", True)
        length_per_unit_bottom_side.setDisplayName("Length per Unit of Bottom Side Strip")
        length_per_unit_bottom_side.setDescription("Length per unit of door bottom sealing strip in m. Enter 0.0 to use default values based on selected sealing product.")
        length_per_unit_bottom_side.setDefaultValue(0.9144)
        args.append(length_per_unit_bottom_side)

        # make an argument for length per unit of top and side sealing strip
        length_per_unit_other_sides = openstudio.measure.OSArgument.makeDoubleArgument("length_per_unit_other_sides", True)
        length_per_unit_other_sides.setDisplayName("Length per Unit of Top and Side Strip")
        length_per_unit_other_sides.setDescription("Length per unit of door top and side sealing strip in m. Enter 0.0 to use default values based on selected sealing product.")
        length_per_unit_other_sides.setDefaultValue(5.1816)
        args.append(length_per_unit_other_sides)

        # make an argument for door thermal conductivity
        door_thermal_conductivity = openstudio.measure.OSArgument.makeDoubleArgument("door_thermal_conductivity", True)
        door_thermal_conductivity.setDisplayName("Door Thermal Conductivity (W/m·K)")
        door_thermal_conductivity.setDescription("Thermal conductivity of the door material (only applies when door option is not 'none'). Enter 0.0 to use default values. Defaults: wooden=0.14, garage=0.028, glass=0.96, polystyrene core=0.035, polyurethane core=0.026, fiberglass core=0.035, honeycomb core=0.05, stiffened core=0.06 W/m·K")
        door_thermal_conductivity.setDefaultValue(0.0)
        args.append(door_thermal_conductivity)

        # make an argument for door density
        door_density = openstudio.measure.OSArgument.makeDoubleArgument("door_density", True)
        door_density.setDisplayName("Door Material Density (kg/m³)")
        door_density.setDescription("Density of the door material (only applies when door option is not 'none'). Enter 0.0 to use default values. Defaults: wooden=600, garage=100, glass=2500, polystyrene core=150, polyurethane core=490, fiberglass core=180, honeycomb core=120, stiffened core=250 kg/m³")
        door_density.setDefaultValue(0.0)
        args.append(door_density)

        # make an argument for door thickness
        door_thickness = openstudio.measure.OSArgument.makeDoubleArgument("door_thickness", True)
        door_thickness.setDisplayName("Door Thickness (m)")
        door_thickness.setDescription("Thickness of the door (only applies when door option is not 'none'). Enter 0.0 to use default values. Defaults: wooden=0.044, garage=0.084, glass=0.006, polystyrene core=0.062, polyurethane core=0.045, fiberglass core=0.074, honeycomb core=0.071, stiffened core=0.053 m")
        door_thickness.setDefaultValue(0.0)
        args.append(door_thickness)

        # make an argument for use custom costs instead of RSMeans API
        use_custom_costs = openstudio.measure.OSArgument.makeBoolArgument("use_custom_costs", False)
        use_custom_costs.setDisplayName("Use Custom Cost Inputs?")
        use_custom_costs.setDescription("If true, use custom material and labor costs instead of querying the RSMeans API.")
        use_custom_costs.setDefaultValue(False)
        args.append(use_custom_costs)

        # make an argument for custom door cost ($/unit area)
        custom_door_cost_per_area = openstudio.measure.OSArgument.makeDoubleArgument("custom_door_cost_per_area", False)
        custom_door_cost_per_area.setDisplayName("Custom Door Cost ($/m²)")
        custom_door_cost_per_area.setDescription("Custom material cost for door replacement per unit area. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_door_cost_per_area.setUnits("$/m²")
        custom_door_cost_per_area.setDefaultValue(0.0)
        args.append(custom_door_cost_per_area)

        # make an argument for custom bottom seal cost ($/length)
        custom_bottom_seal_cost = openstudio.measure.OSArgument.makeDoubleArgument("custom_bottom_seal_cost", False)
        custom_bottom_seal_cost.setDisplayName("Custom Bottom Seal Cost ($/m)")
        custom_bottom_seal_cost.setDescription("Custom material cost for bottom seal per unit length. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_bottom_seal_cost.setUnits("$/m")
        custom_bottom_seal_cost.setDefaultValue(0.0)
        args.append(custom_bottom_seal_cost)

        # make an argument for custom top/side seal cost ($/length)
        custom_top_side_seal_cost = openstudio.measure.OSArgument.makeDoubleArgument("custom_top_side_seal_cost", False)
        custom_top_side_seal_cost.setDisplayName("Custom Top/Side Seal Cost ($/m)")
        custom_top_side_seal_cost.setDescription("Custom material cost for top and side seal per unit length. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_top_side_seal_cost.setUnits("$/m")
        custom_top_side_seal_cost.setDefaultValue(0.0)
        args.append(custom_top_side_seal_cost)

        # make an argument for labor cost multiplier (custom cost path only)
        labor_cost_multiplier = openstudio.measure.OSArgument.makeDoubleArgument("labor_cost_multiplier", True)
        labor_cost_multiplier.setDisplayName("Labor Cost Multiplier (applies to custom material cost)")
        labor_cost_multiplier.setDescription("Total installed cost as a multiple of custom material cost. labor = material × (multiplier − 1). Only used if 'Use Custom Cost Inputs?' is true. Must be ≥ 1.0. Default 1.0 means no separate labor cost (e.g. 1.5 = installed cost is 1.5× material, meaning labor is 50% of material).")
        labor_cost_multiplier.setDefaultValue(1.0)
        args.append(labor_cost_multiplier)

        # make an argument for overhead + profit percent (applies to both custom and RSMeans cost paths)
        overhead_profit_percent = openstudio.measure.OSArgument.makeDoubleArgument("overhead_profit_percent", True)
        overhead_profit_percent.setDisplayName("Overhead + Profit Percent")
        overhead_profit_percent.setDescription(
            "Overhead and profit percentage applied on top of (material + labor) for the custom cost path. "
            "For the RSMeans API path, O&P is handled by the API and this value is informational only. "
            "Default 0.0 means no overhead/profit added."
        )
        overhead_profit_percent.setDefaultValue(0.0)
        args.append(overhead_profit_percent)

        # optional exact RSMeans unit cost line ID override
        rsmeans_unit_costline_id = openstudio.measure.OSArgument.makeStringArgument("rsmeans_unit_costline_id", True)
        rsmeans_unit_costline_id.setDisplayName("RSMeans Unit Cost Line ID (Optional Override)")
        rsmeans_unit_costline_id.setDescription("Optional exact RSMeans unit cost line ID. If provided, the measure attempts this ID first before normal search logic.")
        rsmeans_unit_costline_id.setDefaultValue("")
        args.append(rsmeans_unit_costline_id)

        return args

    def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
        """Define what happens when the measure is run. Execute the measure."""
        super().run(model, runner, user_arguments)

        # ── Phase 1: Argument parsing ─────────────────────────────────────────
        # Retrieve all user-supplied values.  Numeric defaults for seal lengths
        # and material properties are resolved below after option detection.
        runner.registerInfo("Starting doorEnhancement measure execution.")

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
        alter_coef = runner.getBoolArgumentValue('alter_coef', user_arguments)
        # for EC calculation
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        door_bottom_seal_option = runner.getStringArgumentValue("door_bottom_seal_option", user_arguments)
        door_top_side_seal_option = runner.getStringArgumentValue("door_top_side_seal_option", user_arguments)
        length_per_unit_bottom_side = runner.getDoubleArgumentValue("length_per_unit_bottom_side", user_arguments)
        length_per_unit_other_sides = runner.getDoubleArgumentValue("length_per_unit_other_sides", user_arguments)
        door_option = runner.getStringArgumentValue("door_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        strip_lifetime = runner.getIntegerArgumentValue("strip_lifetime",user_arguments)
        door_lifetime = runner.getIntegerArgumentValue("door_lifetime",user_arguments)
        
        # If door_lifetime is default/invalid and door_option is specified, use default from material properties
        if door_lifetime <= 0 and door_option != 'none':
            default_lifetime = self.door_service_life(door_option)
            runner.registerInfo(f"Using default lifetime for {door_option}: {default_lifetime} years")
            door_lifetime = default_lifetime
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        door_area_per_unit = runner.getDoubleArgumentValue("door_area_per_unit", user_arguments)
        if door_area_per_unit == 0.0:
            door_area_per_unit = 1.95
            runner.registerInfo("Argument 'door_area_per_unit' set to 0.0, using default value 1.95 m2.")
        door_thermal_conductivity = runner.getDoubleArgumentValue("door_thermal_conductivity", user_arguments)
        door_density = runner.getDoubleArgumentValue("door_density", user_arguments)
        door_thickness = runner.getDoubleArgumentValue("door_thickness", user_arguments)

        # Retrieve custom cost arguments
        use_custom_costs = runner.getBoolArgumentValue("use_custom_costs", user_arguments)
        custom_door_cost_per_area = runner.getDoubleArgumentValue("custom_door_cost_per_area", user_arguments)
        custom_bottom_seal_cost = runner.getDoubleArgumentValue("custom_bottom_seal_cost", user_arguments)
        custom_top_side_seal_cost = runner.getDoubleArgumentValue("custom_top_side_seal_cost", user_arguments)
        labor_cost_multiplier = runner.getDoubleArgumentValue("labor_cost_multiplier", user_arguments)
        overhead_profit_percent = runner.getDoubleArgumentValue("overhead_profit_percent", user_arguments)
        rsmeans_unit_costline_id = runner.getStringArgumentValue("rsmeans_unit_costline_id", user_arguments).strip()

        if use_custom_costs:
            runner.registerInfo("Custom cost mode enabled. Using user-provided cost values instead of RSMeans API.")
            runner.registerInfo(f"  Door cost: ${custom_door_cost_per_area}/m²")
            runner.registerInfo(f"  Bottom seal cost: ${custom_bottom_seal_cost}/m")
            runner.registerInfo(f"  Top/side seal cost: ${custom_top_side_seal_cost}/m")
            runner.registerInfo(f"  Labor cost multiplier: {labor_cost_multiplier}")
            runner.registerInfo(f"  Overhead + profit percent: {overhead_profit_percent}%")
            if rsmeans_unit_costline_id:
                runner.registerInfo("  RSMeans Unit Cost Line ID override ignored because custom cost mode is enabled.")
        else:
            # Pre-flight warning: RSMeans is the active path. If the user has
            # not supplied any fallback custom rates, the measure will hard-error
            # when RSMeans returns no match. Surface this risk up front.
            if (float(custom_door_cost_per_area) <= 0.0
                    and float(custom_bottom_seal_cost) <= 0.0
                    and float(custom_top_side_seal_cost) <= 0.0):
                runner.registerWarning(
                    "RSMeans cost lookup is the active cost source (use_custom_costs=false) "
                    "but no fallback custom rates have been provided. If RSMeans returns no "
                    "match for the selected door/seal options, the measure will fail. "
                    "Consider setting non-zero values for the relevant "
                    "'custom_door_cost_per_area', 'custom_bottom_seal_cost', or "
                    "'custom_top_side_seal_cost' arguments as a safety net."
                )
            if rsmeans_unit_costline_id:
                runner.registerInfo(f"RSMeans Unit Cost Line ID override requested: {rsmeans_unit_costline_id}")
        length_per_unit_dict = {
            "brush weatherstrip": 0.9144,  # 36" = 0.9144 m, source: https://www.pemko.com/en/view-pdf?id=AADSS1046707&page=1
            "silicone adhesive smoke gasket": 5.1816,  # 17' = 5.1816 m, source: https://buildingtransparency.org/ec3/epds/ec327rq0
            "automatic door bottom": 0.9144,  # 36" = 0.9144 m, source: https://www.adair.com/p-1537-automatic-door-bottom.aspx
            "jamb weatherstrip": 5.181,  # 5.181 m, source: https://buildingtransparency.org/ec3/epds/ec3zsugu
            "none": 0.0
        }
        if length_per_unit_bottom_side == 0.0:
            length_per_unit_bottom_side = length_per_unit_dict[door_bottom_seal_option]
        if length_per_unit_other_sides == 0.0:
            length_per_unit_other_sides = length_per_unit_dict[door_top_side_seal_option]

        # Check if numeric values are reasonable
        if analysis_period <= 0:
            runner.registerError("Choose an integer larger than 0 for analysis period of embodied carbon calculation.")
            return False
        if strip_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door bottom strip.")
            return False
        if door_area_per_unit <= 0:
            runner.registerError("Choose a numeric value larger than 0 for door area per unit.")
            return False
        if door_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door.")
            return False
        if length_per_unit_bottom_side < 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door bottom sealing strip.")
            return False
        if length_per_unit_other_sides < 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door other sides sealing strip.")
            return False
        if door_thermal_conductivity < 0:
            runner.registerError("Door thermal conductivity must be non-negative.")
            return False
        if door_density < 0:
            runner.registerError("Door material density must be non-negative.")
            return False
        if door_thickness < 0:
            runner.registerError("Door thickness must be non-negative.")
            return False
        if labor_cost_multiplier < 1.0:
            runner.registerError("Labor cost multiplier must be at least 1.0.")
            return False

        # Check for conflicting door options
        if door_option != 'none':
            if door_thermal_conductivity > 0.0 and door_density > 0.0 and door_thickness > 0.0:
                # All three custom properties provided - this is fine
                runner.registerInfo(f"Using custom door material properties for {door_option}")
            elif door_thermal_conductivity > 0.0 or door_density > 0.0 or door_thickness > 0.0:
                # Only some properties provided - warning
                runner.registerWarning(f"Only some door material properties provided. Missing properties will use defaults for {door_option}")

        # Resolve door material properties once and reuse these values everywhere.
        user_specified_door_conductivity = door_thermal_conductivity > 0.0
        user_specified_door_density = door_density > 0.0
        user_specified_door_thickness = door_thickness > 0.0
        resolved_door_material_props = {}
        resolved_door_conductivity = None
        resolved_door_density = None
        resolved_door_thickness = None
        if door_option != 'none':
            default_props = self.door_material_properties().get(door_option, {})
            resolved_door_conductivity = (
                door_thermal_conductivity if user_specified_door_conductivity else default_props.get('conductivity')
            )
            resolved_door_density = door_density if user_specified_door_density else default_props.get('density')
            resolved_door_thickness = door_thickness if user_specified_door_thickness else default_props.get('thickness')

            resolved_door_material_props = default_props.copy()
            if resolved_door_conductivity is not None:
                resolved_door_material_props['conductivity'] = resolved_door_conductivity
            if resolved_door_density is not None:
                resolved_door_material_props['density'] = resolved_door_density
            if resolved_door_thickness is not None:
                resolved_door_material_props['thickness'] = resolved_door_thickness
        
        # ── Phase 2: Infiltration reduction ───────────────────────────────────
        # check the space_type for reasonableness and see if measure should run on space type or on the entire building
        apply_to_building = False
        space_type = None

        if not object.is_initialized():
            handle = runner.getStringArgumentValue('space_type', user_arguments)
            if not handle:
                runner.registerError('Space type argument is empty.')
            else:
                runner.registerError(f"Space type with handle '{handle}' not found.")
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

        # get space infiltration objects used in the model
        space_infiltration_objects = model.getSpaceInfiltrationDesignFlowRates()

        # counters needed for measure
        altered_infiltration_instances = 0
        affected_area_si = 0

         # reporting initial condition of model
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("INFILTRATION PROCESSING")
        runner.registerInfo("=" * 80)
        if len(space_infiltration_objects) == 0:
            runner.registerInfo('  ℹ Initial model contained no space infiltration objects')
        else:
            runner.registerInfo(f"  ℹ Initial model contained {len(space_infiltration_objects)} space infiltration objects")

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
            # Coefficients are not modified in door enhancement measure

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
                runner.registerInfo(f"  ✓ Altered: {updated_instance_name} (Space Type: {space_type.nameString()})")
                altered_infiltration_instances += 1

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
                # Call function to alter performance
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
                runner.registerInfo(f"  ✓ Altered: {updated_instance_name} (Space: {space.nameString()})")
                altered_infiltration_instances += 1

        if altered_infiltration_instances == 0:
            runner.registerInfo("  ℹ No space infiltration objects were altered")

        affected_area_ip = openstudio.convert(affected_area_si, 'm^2', 'ft^2').get()

        #report infiltration modification condition
        runner.registerInfo(f'{altered_infiltration_instances} space infiltration objects were altered affecting a total area of {affected_area_si:.2f} m^2 ({affected_area_ip:.2f} ft^2).')
        
        # ── Phase 3: Embodied carbon calculation ──────────────────────────────
        # Collect all door subsurfaces, fetch EC3 EPD data per door, and
        # accumulate embodied carbon (kg CO₂ eq) over the analysis period.
        sub_surfaces = []
        for space in spaces:
            for surface in space.surfaces():
                for subsurface in surface.subSurfaces():
                    sub_surfaces.append(subsurface)

        # Track door subtype availability for summary note conflict detection.
        available_door_subsurface_types = {
            "Door": 0,
            "GlassDoor": 0,
            "OverheadDoor": 0,
        }
        for subsurface in sub_surfaces:
            subtype = subsurface.subSurfaceType()
            if subtype in available_door_subsurface_types:
                available_door_subsurface_types[subtype] += 1

        def is_door_option_compatible_with_subsurface(selected_door_option, subsurface_obj):
            normalized_option = str(selected_door_option).strip().lower().replace("_", " ").replace("-", " ")
            normalized_option = " ".join(normalized_option.split())
            subtype = subsurface_obj.subSurfaceType()

            if normalized_option in {"none", ""}:
                return False
            if normalized_option in {"glass door", "glassdoor"}:
                return subtype == "GlassDoor"
            if normalized_option in {"garage door", "garagedoor"}:
                return subtype == "OverheadDoor"
            return subtype == "Door"
        
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("SUBSURFACE DISCOVERY")
        runner.registerInfo("=" * 80)
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")
        
        runner.registerInfo("-" * 80)
        runner.registerInfo("Filtering door subsurfaces...")
        runner.registerInfo("-" * 80)
        # List storing subsurface object subject to change
        sub_surfaces_to_change = []
        # loop through sub surfaces
        for subsurface in sub_surfaces:

            if subsurface.subSurfaceType() in ["Door","GlassDoor","OverheadDoor"]:
                # append the subsurface objects carrying doors into list
                sub_surfaces_to_change.append(subsurface) 
                runner.registerInfo(f"  ✓ Processing door: {subsurface.nameString()}")           
            else:# if sub_surface.subSurfaceType() not in ["Fixeddoor", "Operabledoor"]:
                runner.registerInfo(f"  ✗ Skipping non-door surface: {subsurface.nameString()}")
                continue

        # dictionary storing properties of subsurfaces containing door construcitons
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("DOOR RENOVATION PROCESSING")
        runner.registerInfo("=" * 80)
        
        subsurface_dict = {}
        carbon_data_unavailable_tracker = {"count": 0, "reasons": []}
        epd_response_cache = {}

        def _fetch_epd_with_cache(url):
            cache_key = str(url) if url is not None else "__none__"
            if cache_key in epd_response_cache:
                return epd_response_cache[cache_key]
            epd_data = fetch_epd_data(url=url, api_token=api_key)
            epd_response_cache[cache_key] = epd_data
            return epd_data

        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            door_option_compatible = is_door_option_compatible_with_subsurface(door_option, subsurface)
            runner.registerInfo(f"\n{'─' * 80}")
            runner.registerInfo(f"Processing: {subsurface_name}")
            runner.registerInfo(f"{'─' * 80}")
            subsurface_dict[subsurface_name] = {}
            subsurface_dict[subsurface_name]["subsurface object"] = subsurface
            subsurface_dict[subsurface_name]["Door type"] = subsurface.subSurfaceType()
            subsurface_dict[subsurface_name]["door_option_compatible"] = door_option_compatible
            subsurface_dict[subsurface_name]["dimension"] = calculate_geometry(self, subsurface)
            subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"] = 0.0

            subsurface_dict[subsurface_name]["door_bottom_sealing"] = {}
            subsurface_dict[subsurface_name]["door_bottom_sealing"]["lifetime"] = strip_lifetime

            subsurface_dict[subsurface_name]["door_side_sealing"] = {}
            subsurface_dict[subsurface_name]["door_side_sealing"]["lifetime"] = strip_lifetime

            subsurface_dict[subsurface_name]['door'] = {}
            subsurface_dict[subsurface_name]['door']['lifetime'] = door_lifetime

            epd_datalist = {}
            bottom_sealing_product_url = self.generate_sealing_url(door_bottom_seal_option)
            side_sealing_product_url = self.generate_sealing_url(door_top_side_seal_option)
            bottom_sealing_product_epd = _fetch_epd_with_cache(bottom_sealing_product_url)
            side_sealing_product_epd = _fetch_epd_with_cache(side_sealing_product_url)
            epd_datalist["door_bottom_sealing"] = bottom_sealing_product_epd
            epd_datalist["door_side_sealing"] = side_sealing_product_epd
            
            # Debug: Log EPD data status
            if bottom_sealing_product_epd is None:
                runner.registerInfo(f"  DEBUG: Bottom sealing EPD is None")
            elif isinstance(bottom_sealing_product_epd, list):
                runner.registerInfo(f"  DEBUG: Bottom sealing EPD returned {len(bottom_sealing_product_epd)} records")
            
            if side_sealing_product_epd is None:
                runner.registerInfo(f"  DEBUG: Side sealing EPD is None")
            elif isinstance(side_sealing_product_epd, list):
                runner.registerInfo(f"  DEBUG: Side sealing EPD returned {len(side_sealing_product_epd)} records")

            door_product_url = self.generate_door_url(door_option, subsurface.subSurfaceType())
            door_product_epd = _fetch_epd_with_cache(door_product_url)
            epd_datalist["door"] = door_product_epd
            
            if door_product_epd is None:
                runner.registerInfo(f"  DEBUG: Door EPD is None")
            elif isinstance(door_product_epd, list):
                runner.registerInfo(f"  DEBUG: Door EPD returned {len(door_product_epd)} records")

            for material_name, epd_data in epd_datalist.items():
                # Skip if no EPD data available (None or empty list), but initialize with zeros
                if epd_data is None or (isinstance(epd_data, list) and len(epd_data) == 0):
                    runner.registerInfo(f"  ⚠ No EPD data available for {material_name}, setting embodied carbon to 0")
                    carbon_data_unavailable_tracker["count"] += 1
                    reason_key = f"missing_epd_{material_name}"
                    if reason_key not in carbon_data_unavailable_tracker["reasons"]:
                        carbon_data_unavailable_tracker["reasons"].append(reason_key)
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_m"] = None
                    subsurface_dict[subsurface_name][material_name]["gwp_per_unit"] = None
                    subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = 0.0
                    continue
                
                # collect  GWP values per functional unit
                gwp_values = {}
                gwp_values["gwp_per_m2"] = []
                gwp_values["gwp_per_m"] = []
                gwp_values['gwp_per_unit'] = []
                
                # Collect lifetime values from EPD
                lifetime_values = []

                for idx, epd in enumerate(epd_data,start = 1):
                    # parse json repsonse based on epd_type
                    parsed_data = parse_product_epd(epd)
                    
                    # Debug: Print parsed data for first EPD
                    if idx == 1:
                        runner.registerInfo(f"  DEBUG [{material_name}] EPD #{idx}: {parsed_data.get('epd_name', 'Unknown')}")
                        runner.registerInfo(f"    Declared unit: {parsed_data.get('declared_unit', 'N/A')}")
                        runner.registerInfo(f"    GWP per declared unit: {parsed_data.get('gwp_per_declared_unit', 'N/A')}")
                        runner.registerInfo(f"    GWP per unit: {parsed_data['gwp_per_unit (kg CO2 eq/unit)']}")
                        runner.registerInfo(f"    GWP per m2: {parsed_data['gwp_per_m2 (kg CO2 eq/m2)']}")
                        runner.registerInfo(f"    GWP per m: calculated from unit")
                    
                    # per unit
                    gwp_per_unit = parsed_data["gwp_per_unit (kg CO2 eq/unit)"]
                    if gwp_per_unit != 0.0:
                        gwp_values["gwp_per_unit"].append(float(gwp_per_unit)) # doesn't count 0.0 values in case it lowers average gwp value
   
                    # per area
                    gwp_per_m2 = parsed_data["gwp_per_m2 (kg CO2 eq/m2)"]
                    if gwp_per_m2 != 0.0:
                        gwp_values["gwp_per_m2"].append(float(gwp_per_m2))
                    elif gwp_per_m2 == 0.0 and gwp_per_unit != 0.0 and material_name == "door":
                        gwp_per_m2 = gwp_per_unit/door_area_per_unit
                        gwp_values["gwp_per_m2"].append(float(gwp_per_m2))

                    # per length
                    # Guard against division-by-zero: length_per_unit_dict["none"] == 0.0,
                    # so skip the per-length conversion when the corresponding seal option
                    # is disabled.
                    gwp_per_m = 0.0
                    if (gwp_per_unit != 0
                            and material_name == "door_bottom_sealing"
                            and door_bottom_seal_option != "none"
                            and length_per_unit_dict.get(door_bottom_seal_option, 0.0) > 0.0):
                        gwp_per_m = gwp_per_unit / length_per_unit_dict[door_bottom_seal_option]
                        gwp_values["gwp_per_m"].append(float(gwp_per_m))
                    elif (gwp_per_unit != 0
                            and material_name == "door_side_sealing"
                            and door_top_side_seal_option != "none"
                            and length_per_unit_dict.get(door_top_side_seal_option, 0.0) > 0.0):
                        gwp_per_m = gwp_per_unit / length_per_unit_dict[door_top_side_seal_option]
                        gwp_values["gwp_per_m"].append(float(gwp_per_m))
                    
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

                # Remove outliers using IQR method
                for functional_unit, values_list in gwp_values.items():
                    if len(values_list) >= 4:  # Only remove outliers if we have enough data points
                        original_count = len(values_list)
                        q1 = np.percentile(values_list, 25)
                        q3 = np.percentile(values_list, 75)
                        iqr = q3 - q1
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr
                        filtered_list = [x for x in values_list if lower_bound <= x <= upper_bound]
                        
                        if len(filtered_list) < original_count:
                            runner.registerInfo(
                                f"    • Removed {original_count - len(filtered_list)} outlier(s) from {functional_unit} "
                                f"({material_name}: {original_count} → {len(filtered_list)} values)"
                            )
                            # Only use filtered list if it's not empty
                            if len(filtered_list) > 0:
                                gwp_values[functional_unit] = filtered_list
                            else:
                                runner.registerWarning(
                                    f"All values were outliers for {functional_unit}, using original data"
                                )

                # Remove outliers from lifetime values
                if len(lifetime_values) >= 4:
                    original_lifetime_count = len(lifetime_values)
                    q1 = np.percentile(lifetime_values, 25)
                    q3 = np.percentile(lifetime_values, 75)
                    iqr = q3 - q1
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    filtered_lifetime = [x for x in lifetime_values if lower_bound <= x <= upper_bound]
                    
                    if len(filtered_lifetime) < original_lifetime_count:
                        runner.registerInfo(
                            f"    • Removed {original_lifetime_count - len(filtered_lifetime)} outlier(s) from lifetime "
                            f"({material_name}: {original_lifetime_count} → {len(filtered_lifetime)} values)"
                        )
                        if len(filtered_lifetime) > 0:
                            lifetime_values = filtered_lifetime
                
                # Process lifetime from EPD (with fallback to user input, then to default material properties)
                user_lifetime = subsurface_dict[subsurface_name][material_name]["lifetime"]
                
                if len(lifetime_values) == 0:
                    # No EPD lifetime - use user input (which already incorporates defaults)
                    epd_lifetime = user_lifetime
                    runner.registerInfo(f"    ℹ No lifetime data in EPD for {material_name}, using user input: {user_lifetime} years")
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
                    runner.registerInfo(f"    ✓ {material_name.replace('_', ' ').title()} lifetime from EPD: {epd_lifetime:.1f} years (was {user_lifetime} from user input)")
                
                # Update lifetime in subsurface_dict
                subsurface_dict[subsurface_name][material_name]["lifetime"] = epd_lifetime
                subsurface_dict[subsurface_name][material_name]["lifetime_source"] = "EPD" if epd_lifetime != user_lifetime else "user_input"

                # extract gwp statistics by user input
                gwp = None
                for functional_unit, values_list in gwp_values.items():
                    if len(values_list) == 0:
                        gwp = None
                        runner.registerInfo(f"    ⚠ No GWP values available for {functional_unit}")
                    elif len(values_list) == 1:
                        gwp = values_list[0]
                    elif gwp_statistic == "minimum":
                        gwp = float(np.min(values_list))
                    elif gwp_statistic == "maximum":
                        gwp = float(np.max(values_list))
                    elif gwp_statistic == "mean":
                        gwp = float(np.mean(values_list))
                    elif gwp_statistic == "median":
                        gwp = float(np.median(values_list))
                    # store gwp value
                    subsurface_dict[subsurface_name][material_name][functional_unit] = gwp

                # multipliers for calculating embodied carbon over analysis period
                multiplier = lifetime_multiplier(subsurface_dict[subsurface_name][material_name]["lifetime"], analysis_period)
                
                embodied_carbon = 0.0
                sealing_bottom_length = subsurface_dict[subsurface_name]['dimension']['width_m']
                sealing_side_length = (subsurface_dict[subsurface_name]['dimension']['perimeter_m'] - subsurface_dict[subsurface_name]['dimension']['width_m'])
                door_area = subsurface_dict[subsurface_name]['dimension']['area_m2']
                selected_gwp_per_m = subsurface_dict[subsurface_name][material_name].get("gwp_per_m")
                selected_gwp_per_m2 = subsurface_dict[subsurface_name][material_name].get("gwp_per_m2")
                if material_name == "door_bottom_sealing" and selected_gwp_per_m not in [None, 0.0]:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] *
                            sealing_bottom_length *
                            multiplier)
                elif material_name == "door_side_sealing" and selected_gwp_per_m not in [None, 0.0]:
                    if subsurface.subSurfaceType() != 'OverheadDoor':
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] *
                                                sealing_side_length *
                                                multiplier)
                    else:
                        embodied_carbon = 0.0
                        runner.registerInfo(f"  ○ Door side sealing skipped for {subsurface_name} (overhead door)")
                    
                elif material_name == "door" and door_option_compatible and selected_gwp_per_m2 not in [None, 0.0]:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] *
                                                door_area *
                                                multiplier)
                else:
                    runner.registerInfo(f"  ○ {material_name}: No GWP data available, entering 0.0")
                    carbon_data_unavailable_tracker["count"] += 1
                    reason_key = f"missing_gwp_{material_name}"
                    if reason_key not in carbon_data_unavailable_tracker["reasons"]:
                        carbon_data_unavailable_tracker["reasons"].append(reason_key)
                    embodied_carbon = 0.0

                # store embodied carbon value for this renovation option on this subsurface
                subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                runner.registerInfo(f"    ✓ {material_name.replace('_', ' ').title()}: {embodied_carbon:.2f} kg CO2 eq")
                
                subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"]

            runner.registerInfo(f"\n{'─' * 80}")
            runner.registerInfo(f"  TOTAL EMBODIED CARBON FOR {subsurface_name}:")
            runner.registerInfo(f"  {subsurface_dict[subsurface_name]['door_renovation_embodied_carbon_kg_co2_eq']:.2f} kg CO2 eq")
            runner.registerInfo(f"{'─' * 80}")

            # Modify door construction based on material properties if door replacement is selected
            if door_option != 'none' and door_option_compatible:
                # Get resolved material properties for selected door type.
                mat_props = resolved_door_material_props.copy()
                if not mat_props:
                    runner.registerWarning(f"No material properties found for {door_option}, skipping R-value calculation.")
                    continue
                
                # Calculate R-value from material properties: R = thickness / conductivity
                if mat_props['conductivity'] > 0.0 and mat_props['thickness'] > 0.0:
                    new_r_value_si = mat_props['thickness'] / mat_props['conductivity']
                else:
                    runner.registerWarning(f"Invalid material properties for {door_option}, skipping R-value calculation.")
                    new_r_value_si = 0.0
                
                # Get current construction
                if subsurface.construction().is_initialized():
                    old_construction = subsurface.construction().get()
                    old_construction_name = old_construction.nameString()
                    
                    # Get current R-value for comparison
                    old_r_value_si = 0.0
                    if old_construction.to_LayeredConstruction().is_initialized():
                        lc = old_construction.to_LayeredConstruction().get()
                        if lc.thermalConductance().is_initialized():
                            old_r_value_si = 1.0 / lc.thermalConductance().get()
                    
                    old_r_value_ip = openstudio.convert(old_r_value_si, "m^2*K/W", "ft^2*h*R/Btu").get()
                    new_r_value_ip = openstudio.convert(new_r_value_si, "m^2*K/W", "ft^2*h*R/Btu").get()
                    
                    # Clone construction for modification
                    new_construction = old_construction.clone(model).to_Construction().get()
                    new_construction.setName(f"{old_construction_name} - {door_option} R-{new_r_value_si:.2f}")
                    
                    # Create a new standard opaque material with physical properties
                    new_door_material = openstudio.model.StandardOpaqueMaterial(model)
                    new_door_material.setName(f"{door_option} R-{new_r_value_si:.2f}")
                    new_door_material.setThickness(mat_props['thickness'])
                    new_door_material.setConductivity(mat_props['conductivity'])
                    new_door_material.setDensity(mat_props['density'])
                    new_door_material.setSpecificHeat(1000)  # J/kg·K, typical for building materials
                    
                    # Set the construction to use only the new material
                    new_construction.setLayers([new_door_material])
                    
                    # Apply new construction to subsurface
                    subsurface.setConstruction(new_construction)
                    
                    # Store R-value and material properties in subsurface dict
                    subsurface_dict[subsurface_name]['old_r_value_si'] = old_r_value_si
                    subsurface_dict[subsurface_name]['new_r_value_si'] = new_r_value_si
                    subsurface_dict[subsurface_name]['new_construction_name'] = new_construction.nameString()
                    subsurface_dict[subsurface_name]['material_thickness_m'] = mat_props['thickness']
                    subsurface_dict[subsurface_name]['material_conductivity_W_per_mK'] = mat_props['conductivity']
                    subsurface_dict[subsurface_name]['material_density_kg_per_m3'] = mat_props['density']
                    
                    runner.registerInfo(f"\n  → Door construction updated for {subsurface_name}:")
                    runner.registerInfo(f"    Material: {door_option}")
                    runner.registerInfo(f"    R-value: {old_r_value_si:.2f} → {new_r_value_si:.2f} m²·K/W (R-{old_r_value_ip:.1f} → R-{new_r_value_ip:.1f} IP)")
                    runner.registerInfo(f"    Thickness: {mat_props['thickness']*1000:.1f} mm | Conductivity: {mat_props['conductivity']:.3f} W/m·K")
                else:
                    runner.registerWarning(f"No construction found for {subsurface_name}, R-value not modified.")

        # Calculate total embodied carbon and count door replacements
        total_embodied_carbon = sum(
            subsurface_dict[name]["door_renovation_embodied_carbon_kg_co2_eq"] 
            for name in subsurface_dict.keys()
        )
        
        # Count doors with R-value changes
        doors_with_r_value_change = sum(
            1 for name in subsurface_dict.keys() 
            if 'new_r_value_si' in subsurface_dict[name]
        )

        # Calculate total door area
        total_door_area_m2 = sum(
            subsurface_dict[name]["dimension"]["area_m2"] 
            for name in subsurface_dict.keys()
        )

        total_eligible_door_area_m2 = sum(
            subsurface_dict[name]["dimension"]["area_m2"]
            for name in subsurface_dict.keys()
            if subsurface_dict[name].get("door_option_compatible", False)
        )
        eligible_door_count = sum(
            1
            for name in subsurface_dict.keys()
            if subsurface_dict[name].get("door_option_compatible", False)
        )
        
        # Collect door construction names for traceability
        construction_names = []
        for name in subsurface_dict.keys():
            if 'new_construction_name' in subsurface_dict[name]:
                construction_names.append(subsurface_dict[name]['new_construction_name'])
            else:
                subsurface = subsurface_dict[name]["subsurface object"]
                if subsurface.construction().is_initialized():
                    construction = subsurface.construction().get()
                    construction_names.append(construction.nameString())
        
        # Calculate total sealing lengths
        total_sealing_bottom_length_m = 0.0
        total_sealing_side_length_m = 0.0
        
        for name in subsurface_dict.keys():
            # Bottom sealing length (door width)
            if door_bottom_seal_option != 'none':
                sealing_bottom_length = subsurface_dict[name]['dimension']['width_m']
                total_sealing_bottom_length_m += sealing_bottom_length
            
            # Side sealing length (perimeter minus width, excluding overhead doors)
            if door_top_side_seal_option != 'none':
                subsurface = subsurface_dict[name]["subsurface object"]
                if subsurface.subSurfaceType() != 'OverheadDoor':
                    sealing_side_length = (subsurface_dict[name]['dimension']['perimeter_m'] - 
                                          subsurface_dict[name]['dimension']['width_m'])
                    total_sealing_side_length_m += sealing_side_length

        # ── Phase 4: RSMeans cost lookup ──────────────────────────────────────
        # Build search-material records describing each door component
        # (whole door, bottom seal, top/side seal) and query the RSMeans API
        # (or use custom cost inputs when use_custom_costs=True).
        #
        # rsmeans_lookup is initialised to None here so Phase 5 storage can
        # always test `if rsmeans_lookup is not None:` safely.
        rsmeans_lookup = None
        rsmeans_materials = []  # search-material records built below
        matched_rsmeans = {
            "door_material": {"id": "", "description": ""},
            "door_bottom_seal": {"id": "", "description": ""},
            "door_top_side_seal": {"id": "", "description": ""},
        }

        def _format_ft_in(value_m: float) -> str:
            """Convert metres to a ft-in string for RSMeans search terms."""
            inches_total = value_m * 39.37007874
            feet = int(inches_total // 12)
            inches = int(round(inches_total - feet * 12))
            if inches == 12:
                feet += 1
                inches = 0
            return f"{feet} ft {inches} in"

        def _mixed_number_to_float(value: str):
            text = str(value or "").strip()
            if not text:
                return None
            # Supports forms like: 1-3/4, 1 3/4, 3/4, 1.75
            mixed_match = re.match(r"^(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)$", text)
            if mixed_match:
                whole = float(mixed_match.group(1))
                numerator = float(mixed_match.group(2))
                denominator = float(mixed_match.group(3))
                if denominator != 0:
                    return whole + numerator / denominator
            fraction_match = re.match(r"^(\d+)\s*/\s*(\d+)$", text)
            if fraction_match:
                numerator = float(fraction_match.group(1))
                denominator = float(fraction_match.group(2))
                if denominator != 0:
                    return numerator / denominator
            try:
                return float(text)
            except Exception:
                return None

        def _parse_rsmeans_opening_area_m2(text: str):
            desc = str(text or "")

            # Pattern A: 3'-0" x 7'-0"  or  3' x 7'  (inch marks optional)
            ft_in_match = re.search(
                r"(\d+(?:\.\d+)?)\s*'\s*(?:-?\s*(\d+(?:\.\d+)?)\s*\")?\s*[xX]\s*(\d+(?:\.\d+)?)\s*'\s*(?:-?\s*(\d+(?:\.\d+)?)\s*\")?",
                desc,
            )
            if ft_in_match:
                w_ft = float(ft_in_match.group(1))
                w_in = float(ft_in_match.group(2) or 0.0)
                h_ft = float(ft_in_match.group(3))
                h_in = float(ft_in_match.group(4) or 0.0)
                width_m = (w_ft * 12.0 + w_in) * 0.0254
                height_m = (h_ft * 12.0 + h_in) * 0.0254
                return width_m * height_m

            # Pattern: 3 ft 0 in x 7 ft 0 in
            ft_word_match = re.search(
                r"(\d+(?:\.\d+)?)\s*ft\s*(\d+(?:\.\d+)?)?\s*in?\s*[xX]\s*(\d+(?:\.\d+)?)\s*ft\s*(\d+(?:\.\d+)?)?\s*in?",
                desc,
                flags=re.IGNORECASE,
            )
            if ft_word_match:
                w_ft = float(ft_word_match.group(1))
                w_in = float(ft_word_match.group(2) or 0.0)
                h_ft = float(ft_word_match.group(3))
                h_in = float(ft_word_match.group(4) or 0.0)
                width_m = (w_ft * 12.0 + w_in) * 0.0254
                height_m = (h_ft * 12.0 + h_in) * 0.0254
                return width_m * height_m

            return None

        def _parse_rsmeans_thickness_m(text: str):
            desc = str(text or "")
            lowered = desc.lower()

            # Prioritize explicit thickness context when present.
            context_match = re.search(
                r"(?:thick(?:ness)?|door\s+leaf)\D{0,20}(\d+\s*-\s*\d+\s*/\s*\d+|\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(?:\"|in\b|inch\b|inches\b)",
                lowered,
                flags=re.IGNORECASE,
            )
            if context_match:
                inches = _mixed_number_to_float(context_match.group(1))
                if inches and inches > 0.0:
                    return inches * 0.0254

            # Fallback: first inch value in description if no explicit context exists.
            generic_matches = re.findall(
                r"(\d+\s*-\s*\d+\s*/\s*\d+|\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(?:\"|in\b|inch\b|inches\b)",
                lowered,
                flags=re.IGNORECASE,
            )
            for match in generic_matches:
                inches = _mixed_number_to_float(match)
                if inches and 0.125 <= inches <= 6.0:
                    return inches * 0.0254

            return None

        def _parse_rsmeans_door_material_props(text: str):
            """Extract door material properties from RSMeans match description.

            Returns keys: area_m2, thickness (m), density (kg/m3) when found.
            """
            desc = str(text or "")
            lowered = desc.lower()
            extracted = {}

            area_m2 = _parse_rsmeans_opening_area_m2(desc)
            if area_m2 is not None and area_m2 > 0.0:
                extracted["area_m2"] = area_m2

            thickness_m = _parse_rsmeans_thickness_m(desc)
            if thickness_m is not None and thickness_m > 0.0:
                extracted["thickness"] = thickness_m

            density_patterns = [
                r"density\s*[:=]?\s*([\d.]+)\s*(?:pcf|lb/ft\^?3|lb/ft3|lb/ft³)",
                r"([\d.]+)\s*(?:pcf|lb/ft\^?3|lb/ft3|lb/ft³)",
            ]
            for pattern in density_patterns:
                match = re.search(pattern, lowered, flags=re.IGNORECASE)
                if match:
                    try:
                        pcf = float(match.group(1))
                        if pcf > 0.0:
                            extracted["density"] = pcf * 16.01846337
                            break
                    except Exception:
                        pass

            return extracted

        def _infer_door_option_from_rsmeans(text: str):
            desc = str(text or "").lower()
            if "polyurethane" in desc and "core" in desc and "steel" in desc:
                return "polyurethane core steel door"
            if "polystyrene" in desc and "core" in desc and "steel" in desc:
                return "polystyrene core steel door"
            if "honeycomb" in desc and "core" in desc and "steel" in desc:
                return "honeycomb core steel door"
            if "stiffened" in desc and "core" in desc and "steel" in desc:
                return "stiffened core steel door"
            if "garage" in desc or "overhead" in desc:
                return "garage door"
            if "glass" in desc or "glazed" in desc or "glazing" in desc:
                return "glass door"
            if "wood" in desc:
                return "wooden door"
            return None

        def _select_rsmeans_door_hit(rsmeans_lookup_data):
            if not rsmeans_lookup_data or rsmeans_lookup_data.get("status") != "ok":
                return None
            materials = rsmeans_lookup_data.get("results", {}).get("materials", [])
            if not materials:
                return None

            for item in materials:
                unit = str(item.get("unit", "")).lower()
                name_text = str(item.get("name", "")).lower()
                desc_text = str(item.get("rsmeans_description", item.get("description", ""))).lower()
                if unit in ["ea", "each"] and ("door" in name_text or "door" in desc_text):
                    return item
            return materials[0]

        rsmeans_summary_line = None
        rsmeans_size_str = ""
        rsmeans_door_hit = None
        rsmeans_door_area_per_unit_m2 = None
        rsmeans_door_thickness_m = None
        rsmeans_door_match_description = ""
        rsmeans_applied_door_option = None
        rsmeans_area_cost_adjusted = False

        if len(sub_surfaces_to_change) > 0:
            first_name = next(iter(subsurface_dict.keys()))
            dims = subsurface_dict[first_name].get("dimension", {})
            width_m = dims.get("width_m", 0.0)
            height_m = dims.get("length_m", 0.0)
            if width_m > 0.0 and height_m > 0.0:
                rsmeans_size_str = f"{_format_ft_in(width_m)} x {_format_ft_in(height_m)}"
            else:
                rsmeans_size_str = "approx size unknown"

            rsmeans_materials = []
            if door_option != 'none' and eligible_door_count > 0:
                rsmeans_materials.append(
                    {
                        "name": f"{door_option} door",
                        "description": f"{eligible_door_count} door(s); size: {rsmeans_size_str}",
                        "quantity": float(eligible_door_count),
                        "unit": "EA",
                        "division_code": "08",
                        "explicit_rsmeans_id": rsmeans_unit_costline_id,
                    }
                )

            if door_bottom_seal_option != 'none' and total_sealing_bottom_length_m > 0.0:
                rsmeans_materials.append(
                    {
                        "name": f"door bottom seal {door_bottom_seal_option}",
                        "description": f"Bottom seal material ({door_bottom_seal_option})",
                        "quantity": float(total_sealing_bottom_length_m * 3.28084),
                        "unit": "LF",
                        "division_code": "0871",  # Door Hardware (incl. weatherstripping); avoid stray door/glass matches
                    }
                )

            if door_top_side_seal_option != 'none' and total_sealing_side_length_m > 0.0:
                rsmeans_materials.append(
                    {
                        "name": f"door top side seal {door_top_side_seal_option}",
                        "description": f"Top/side seal material ({door_top_side_seal_option})",
                        "quantity": float(total_sealing_side_length_m * 3.28084),
                        "unit": "LF",
                        "division_code": "0871",  # Door Hardware (incl. weatherstripping); avoid stray door/glass matches
                    }
                )

            try:
                if use_custom_costs:
                    runner.registerInfo("Using custom cost inputs (RSMeans API lookup skipped).")
                    # Lifetime multipliers: number of replacements over the analysis period.
                    _mult_door = int(lifetime_multiplier(door_lifetime, analysis_period))
                    _mult_seal = int(lifetime_multiplier(strip_lifetime, analysis_period))
                    # --- Step 1: Material costs (each rate × quantity × lifetime_multiplier) ---
                    # door material cost = rate ($/m²) × total door area (m²) × door_lifetime_multiplier
                    door_cost_total = custom_door_cost_per_area * float(total_eligible_door_area_m2) * _mult_door
                    # bottom seal cost = rate ($/m) × total bottom seal length (m) × seal_lifetime_multiplier; 0 if seal option is 'none'
                    bottom_seal_cost_total = (custom_bottom_seal_cost * float(total_sealing_bottom_length_m) * _mult_seal
                                              if door_bottom_seal_option != 'none' else 0.0)
                    # top/side seal cost = rate ($/m) × total top/side seal length (m) × seal_lifetime_multiplier; 0 if seal option is 'none'
                    top_side_seal_cost_total = (custom_top_side_seal_cost * float(total_sealing_side_length_m) * _mult_seal
                                                if door_top_side_seal_option != 'none' else 0.0)
                    # total material cost = sum of all component material costs
                    total_custom_material_cost = door_cost_total + bottom_seal_cost_total + top_side_seal_cost_total

                    # --- Step 2: Labor cost derived from material cost via multiplier ---
                    # labor = material × (multiplier - 1)
                    # e.g. multiplier=1.0 → labor=$0 (default, no labor added)
                    #      multiplier=1.5 → labor = 50% of material cost
                    #      multiplier=2.0 → labor = 100% of material cost (labor equals material)
                    total_custom_labor_cost = (
                        total_custom_material_cost * (labor_cost_multiplier - 1.0)
                        if labor_cost_multiplier > 1.0 else 0.0
                    )

                    # --- Step 3: Overhead + profit on top of (material + labor) ---
                    total_custom_overhead_cost = (
                        (total_custom_material_cost + total_custom_labor_cost) * (overhead_profit_percent / 100.0)
                        if overhead_profit_percent > 0.0 else 0.0
                    )

                    # --- Step 4: Total installed cost = material + labor + overhead ---
                    total_custom_installed_cost = total_custom_material_cost + total_custom_labor_cost + total_custom_overhead_cost
                    rsmeans_lookup = {
                        "status": "ok",
                        "cost_source": "custom_input",
                        "summary": {
                            "materials_count": len(rsmeans_materials),
                            "total_material_cost": total_custom_material_cost,
                            "total_labor_cost": total_custom_labor_cost,
                            "overhead_profit_percent": overhead_profit_percent,
                            "total_overhead_profit_cost": total_custom_overhead_cost,
                            "total_cost_with_overhead_profit": total_custom_installed_cost,
                            "release_id": "custom",
                            "location_id": "custom",
                            "labor_type": "custom",
                            "measurement_system": "custom",
                            "catalogs_searched": []
                        }
                    }
                    rsmeans_summary_line = (
                        "Custom cost summary (cost_source=custom_input): "
                        f"door_cost=${door_cost_total:,.2f} "
                        f"({total_eligible_door_area_m2:.2f} m² @ ${custom_door_cost_per_area}/m²), "
                        f"bottom_seal_cost=${bottom_seal_cost_total:,.2f} "
                        f"({total_sealing_bottom_length_m:.2f} m @ ${custom_bottom_seal_cost}/m), "
                        f"top_side_seal_cost=${top_side_seal_cost_total:,.2f} "
                        f"({total_sealing_side_length_m:.2f} m @ ${custom_top_side_seal_cost}/m), "
                        f"material=${total_custom_material_cost:,.2f}, "
                        f"labor=${total_custom_labor_cost:,.2f} (multiplier={labor_cost_multiplier}), "
                        f"overhead=${total_custom_overhead_cost:,.2f} ({overhead_profit_percent}%), "
                        f"total=${total_custom_installed_cost:,.2f}"
                    )
                    runner.registerInfo(rsmeans_summary_line)
                else:
                    runner.registerInfo("Starting RSMeans lookup...")
                    runner.registerInfo(f"RSMeans materials requested: {len(rsmeans_materials)}")
                    rsmeans_lookup = self.pull_rsmeans_cost_from_api(runner, rsmeans_materials)
                    # Add cost_source identifier to RSMeans API results
                    if rsmeans_lookup:
                        rsmeans_lookup["cost_source"] = "rsmeans_api"
                    runner.registerInfo(f"RSMeans lookup status: {rsmeans_lookup.get('status', 'unknown')}")
                    if rsmeans_lookup.get("status") == "ok":
                        summary = rsmeans_lookup.get("summary", {})
                        rsmeans_summary_line = (
                            "RSMeans cost summary (cost_source=rsmeans_api): "
                            f"materials={summary.get('materials_count', 0)}, "
                            f"total_cost=${summary.get('total_cost_with_overhead_profit', 0.0):,.2f}"
                        )
                        runner.registerInfo(rsmeans_summary_line)
                        rsmeans_results = rsmeans_lookup.get("results", {})
                        materials_results = rsmeans_results.get("materials", [])
                        if materials_results:
                            for mat in materials_results:
                                mat_name = str(mat.get("name", "")).lower()
                                matched_id = mat.get("rsmeans_id", "")
                                matched_desc = mat.get("rsmeans_description") or mat.get("description", "")

                                target_key = None
                                if "bottom seal" in mat_name:
                                    target_key = "door_bottom_seal"
                                elif "top side seal" in mat_name or "top/side" in mat_name or "jamb" in mat_name:
                                    target_key = "door_top_side_seal"
                                elif "door" in mat_name:
                                    target_key = "door_material"

                                if target_key:
                                    if matched_id and not matched_rsmeans[target_key]["id"]:
                                        matched_rsmeans[target_key]["id"] = str(matched_id)
                                    if matched_desc and not matched_rsmeans[target_key]["description"]:
                                        matched_rsmeans[target_key]["description"] = str(matched_desc)

                            if rsmeans_unit_costline_id and not matched_rsmeans["door_material"]["id"] and door_option != 'none':
                                matched_rsmeans["door_material"]["id"] = rsmeans_unit_costline_id
                        for warning_msg in rsmeans_results.get("warnings", []):
                            runner.registerWarning(f"RSMeans fallback: {warning_msg}")
                        fallback_count = int(rsmeans_results.get("fallback_count", 0) or 0)
                        if fallback_count > 0:
                            runner.registerInfo(f"RSMeans fallback matches applied: {fallback_count}")
            except Exception as e:
                runner.registerWarning(f"Cost lookup failed: {e}")

            # Fallback: if RSMeans was attempted (use_custom_costs=False) but did
            # not return usable cost data, automatically try user-provided custom
            # rates. If those are also zero/unset, raise a hard error so the user
            # knows to supply them rather than silently recording $0 costs.
            if (not use_custom_costs) and (
                rsmeans_lookup is None
                or rsmeans_lookup.get("status") != "ok"
                or float(rsmeans_lookup.get("summary", {}).get("total_cost_with_overhead_profit", 0.0)) <= 0.0
            ):
                _need_door_rate = (door_option != 'none' and eligible_door_count > 0
                                   and total_eligible_door_area_m2 > 0.0)
                _need_bottom_rate = (door_bottom_seal_option != 'none'
                                     and total_sealing_bottom_length_m > 0.0)
                _need_top_side_rate = (door_top_side_seal_option != 'none'
                                       and total_sealing_side_length_m > 0.0)

                _missing = []
                if _need_door_rate and float(custom_door_cost_per_area) <= 0.0:
                    _missing.append("'custom_door_cost_per_area' ($/m²)")
                if _need_bottom_rate and float(custom_bottom_seal_cost) <= 0.0:
                    _missing.append("'custom_bottom_seal_cost_per_m' ($/m)")
                if _need_top_side_rate and float(custom_top_side_seal_cost) <= 0.0:
                    _missing.append("'custom_top_side_seal_cost_per_m' ($/m)")

                if _missing:
                    runner.registerError(
                        "RSMeans lookup failed/returned no costs AND no custom cost rates "
                        "were provided for: " + ", ".join(_missing) + ".\n"
                        "SOLUTION: Retry the measure with custom cost input:\n"
                        "  1. Set 'Use Custom Cost Inputs?' = true\n"
                        "  2. Provide non-zero values for the rates listed above. "
                        "(Only components matching your selected door/seal options need values.)"
                    )
                else:
                    runner.registerWarning(
                        "RSMeans lookup failed/returned no costs. Falling back to "
                        "user-provided custom cost rates."
                    )
                    _mult_door = int(lifetime_multiplier(door_lifetime, analysis_period))
                    _mult_seal = int(lifetime_multiplier(strip_lifetime, analysis_period))
                    door_cost_total = (float(custom_door_cost_per_area)
                                       * float(total_eligible_door_area_m2) * _mult_door
                                       if _need_door_rate else 0.0)
                    bottom_seal_cost_total = (float(custom_bottom_seal_cost)
                                              * float(total_sealing_bottom_length_m) * _mult_seal
                                              if _need_bottom_rate else 0.0)
                    top_side_seal_cost_total = (float(custom_top_side_seal_cost)
                                                * float(total_sealing_side_length_m) * _mult_seal
                                                if _need_top_side_rate else 0.0)
                    total_custom_material_cost = (door_cost_total
                                                  + bottom_seal_cost_total
                                                  + top_side_seal_cost_total)
                    total_custom_labor_cost = (
                        total_custom_material_cost * (labor_cost_multiplier - 1.0)
                        if labor_cost_multiplier > 1.0 else 0.0
                    )
                    total_custom_overhead_cost = (
                        (total_custom_material_cost + total_custom_labor_cost)
                        * (overhead_profit_percent / 100.0)
                        if overhead_profit_percent > 0.0 else 0.0
                    )
                    total_custom_installed_cost = (
                        total_custom_material_cost
                        + total_custom_labor_cost
                        + total_custom_overhead_cost
                    )
                    rsmeans_lookup = {
                        "status": "ok",
                        "cost_source": "custom_input_fallback",
                        "summary": {
                            "materials_count": len(rsmeans_materials),
                            "total_material_cost": total_custom_material_cost,
                            "total_labor_cost": total_custom_labor_cost,
                            "overhead_profit_percent": overhead_profit_percent,
                            "total_overhead_profit_cost": total_custom_overhead_cost,
                            "total_cost_with_overhead_profit": total_custom_installed_cost,
                            "release_id": "custom_fallback",
                            "location_id": "custom_fallback",
                            "labor_type": "custom_fallback",
                            "measurement_system": "custom_fallback",
                            "catalogs_searched": [],
                        },
                    }
                    runner.registerInfo(
                        "Custom-rate fallback summary "
                        "(cost_source=custom_input_fallback): "
                        f"door=${door_cost_total:,.2f}, "
                        f"bottom_seal=${bottom_seal_cost_total:,.2f}, "
                        f"top_side_seal=${top_side_seal_cost_total:,.2f}, "
                        f"material=${total_custom_material_cost:,.2f}, "
                        f"labor=${total_custom_labor_cost:,.2f} "
                        f"(multiplier={labor_cost_multiplier}), "
                        f"overhead=${total_custom_overhead_cost:,.2f} "
                        f"({overhead_profit_percent}%), "
                        f"total=${total_custom_installed_cost:,.2f}"
                    )

        # Use closest RSMeans door hit to refine replacement material properties.
        if (not use_custom_costs) and door_option != 'none' and eligible_door_count > 0:
            rsmeans_door_hit = _select_rsmeans_door_hit(rsmeans_lookup)
            if rsmeans_door_hit is not None:
                rsmeans_door_match_description = str(
                    rsmeans_door_hit.get("rsmeans_description")
                    or rsmeans_door_hit.get("description")
                    or ""
                )
                rsmeans_parsed_props = _parse_rsmeans_door_material_props(rsmeans_door_match_description)
                rsmeans_door_area_per_unit_m2 = rsmeans_parsed_props.get("area_m2")
                rsmeans_door_thickness_m = rsmeans_parsed_props.get("thickness")
                rsmeans_inferred_option = _infer_door_option_from_rsmeans(rsmeans_door_match_description)

                # If we couldn't parse a door opening area from the RSMeans
                # description, fall back to the user-supplied EPD reference
                # area so that per-EACH costs still get normalized to per-m2.
                if (rsmeans_door_area_per_unit_m2 is None or rsmeans_door_area_per_unit_m2 <= 0.0) and door_area_per_unit > 0.0:
                    rsmeans_door_area_per_unit_m2 = float(door_area_per_unit)
                    runner.registerWarning(
                        "Could not parse door opening area from RSMeans description "
                        f"'{rsmeans_door_match_description}'. Falling back to "
                        f"door_area_per_unit={door_area_per_unit:.3f} m2 for cost normalization."
                    )

                # Normalize RSMeans door costs to area-based totals.
                if rsmeans_lookup and rsmeans_lookup.get("status") == "ok":
                    rsmeans_results_dict = rsmeans_lookup.get("results", {})
                    rsmeans_summary_dict = rsmeans_lookup.get("summary", {})
                    materials_results = rsmeans_results_dict.get("materials", [])
                    if rsmeans_door_area_per_unit_m2 and rsmeans_door_area_per_unit_m2 > 0.0 and total_eligible_door_area_m2 > 0.0:
                        door_cost_before = 0.0
                        door_cost_after = 0.0
                        for mat in materials_results:
                            mat_name = str(mat.get("name", "")).lower()
                            mat_unit = str(mat.get("unit", "")).lower()
                            if "door" in mat_name and "seal" not in mat_name and mat_unit in ["ea", "each"]:
                                qty = float(mat.get("quantity", 0.0) or 0.0)
                                total_cost = float(mat.get("total_cost", 0.0) or 0.0)
                                if qty > 0.0 and total_cost >= 0.0:
                                    unit_cost_each = total_cost / qty
                                    unit_cost_per_m2 = unit_cost_each / float(rsmeans_door_area_per_unit_m2)
                                    adjusted_total_cost = unit_cost_per_m2 * float(total_eligible_door_area_m2)
                                    mat["unit_cost_per_m2"] = unit_cost_per_m2
                                    mat["total_cost_area_adjusted"] = adjusted_total_cost
                                    door_cost_before += total_cost
                                    door_cost_after += adjusted_total_cost

                        if door_cost_before > 0.0:
                            delta = door_cost_after - door_cost_before
                            adjusted_material_cost = float(rsmeans_summary_dict.get("total_material_cost", 0.0)) + delta
                            overhead_pct = float(rsmeans_summary_dict.get("overhead_profit_percent", 0.0))
                            adjusted_overhead = adjusted_material_cost * overhead_pct * 0.01
                            adjusted_total = adjusted_material_cost + adjusted_overhead
                            rsmeans_summary_dict["total_material_cost"] = adjusted_material_cost
                            rsmeans_summary_dict["total_overhead_profit_cost"] = adjusted_overhead
                            rsmeans_summary_dict["total_cost_with_overhead_profit"] = adjusted_total
                            rsmeans_area_cost_adjusted = True
                            runner.registerInfo(
                                "RSMeans door cost converted from per-unit to per-area using "
                                f"rsmeans_door_area_per_unit_m2={rsmeans_door_area_per_unit_m2:.3f}; "
                                f"door_cost: ${door_cost_before:,.2f} -> ${door_cost_after:,.2f}."
                            )
                    else:
                        runner.registerWarning(
                            "Unable to convert RSMeans door cost to area basis because "
                            "rsmeans_door_area_per_unit_m2 or total_eligible_door_area_m2 is missing/invalid."
                        )

                # The user-supplied ``door_option`` is authoritative for material
                # properties — never let an inferred option from a (possibly
                # poorly matched) RSMeans description silently override it.
                # Inference is still useful for the legacy default door_option,
                # so only use it when the user did not pick one explicitly.
                if door_option and door_option != 'none':
                    rsmeans_applied_door_option = door_option
                    if (
                        rsmeans_inferred_option
                        and rsmeans_inferred_option in self.door_material_properties()
                        and rsmeans_inferred_option != door_option
                    ):
                        runner.registerWarning(
                            f"RSMeans description suggests '{rsmeans_inferred_option}' but user "
                            f"requested '{door_option}'. Honoring user-specified door_option for "
                            f"material properties; cost reflects the matched RSMeans line."
                        )
                elif rsmeans_inferred_option in self.door_material_properties():
                    rsmeans_applied_door_option = rsmeans_inferred_option
                else:
                    rsmeans_applied_door_option = door_option

                # If user did not provide explicit properties, take defaults from the
                # inferred RSMeans door type first, then refine with parsed description values.
                inferred_defaults = self.door_material_properties().get(rsmeans_applied_door_option, {})
                if (not user_specified_door_conductivity) and inferred_defaults.get('conductivity', 0.0) > 0.0:
                    resolved_door_conductivity = float(inferred_defaults.get('conductivity'))
                if (not user_specified_door_density) and inferred_defaults.get('density', 0.0) > 0.0:
                    resolved_door_density = float(inferred_defaults.get('density'))
                if (not user_specified_door_thickness) and inferred_defaults.get('thickness', 0.0) > 0.0:
                    resolved_door_thickness = float(inferred_defaults.get('thickness'))

                if (not user_specified_door_thickness) and rsmeans_parsed_props.get('thickness', 0.0) > 0.0:
                    resolved_door_thickness = float(rsmeans_parsed_props.get('thickness'))
                if (not user_specified_door_density) and rsmeans_parsed_props.get('density', 0.0) > 0.0:
                    resolved_door_density = float(rsmeans_parsed_props.get('density'))

                # Primary user-requested behavior: when user input is 0.0, replace
                # door_density/door_thickness with values parsed from RSMeans description.
                if (not user_specified_door_density) and rsmeans_parsed_props.get('density', 0.0) > 0.0:
                    door_density = float(rsmeans_parsed_props.get('density'))
                    resolved_door_density = door_density
                if (not user_specified_door_thickness) and rsmeans_parsed_props.get('thickness', 0.0) > 0.0:
                    door_thickness = float(rsmeans_parsed_props.get('thickness'))
                    resolved_door_thickness = door_thickness

                if door_option != 'none':
                    resolved_door_material_props = self.door_material_properties().get(rsmeans_applied_door_option, {}).copy()
                    if resolved_door_conductivity is not None and resolved_door_conductivity > 0.0:
                        resolved_door_material_props['conductivity'] = resolved_door_conductivity
                    if resolved_door_density is not None and resolved_door_density > 0.0:
                        resolved_door_material_props['density'] = resolved_door_density
                    if resolved_door_thickness is not None and resolved_door_thickness > 0.0:
                        resolved_door_material_props['thickness'] = resolved_door_thickness

                model_avg_door_area_m2 = 0.0
                if eligible_door_count > 0:
                    model_avg_door_area_m2 = total_eligible_door_area_m2 / float(eligible_door_count)

                if rsmeans_door_area_per_unit_m2 is not None and model_avg_door_area_m2 > 0.0:
                    area_delta = abs(rsmeans_door_area_per_unit_m2 - model_avg_door_area_m2)
                    rel_area_delta = area_delta / model_avg_door_area_m2
                    if rel_area_delta > 0.10:
                        runner.registerWarning(
                            "RSMeans door opening area differs from model door area by more than 10% "
                            f"(RSMeans={rsmeans_door_area_per_unit_m2:.3f} m2, "
                            f"model_avg={model_avg_door_area_m2:.3f} m2). "
                            f"Costs were normalized to the model area via per-m2 conversion. "
                            f"GWP per-m2 conversion uses the EPD reference area "
                            f"`door_area_per_unit`={door_area_per_unit:.3f} m2 "
                            f"(default 1.95 m2 per door-leaf PCR). "
                            f"If the EPD basis differs, set `door_area_per_unit` explicitly."
                        )

                if (
                    resolved_door_material_props.get('conductivity', 0.0) <= 0.0
                    or resolved_door_material_props.get('thickness', 0.0) <= 0.0
                ):
                    runner.registerWarning(
                        "Unable to apply RSMeans-driven door replacement due to incomplete material properties."
                    )
                else:
                    runner.registerInfo(
                        "Applying RSMeans-driven door replacement using closest match: "
                        f"{rsmeans_door_hit.get('rsmeans_id', 'unknown')}"
                    )
                    for subsurface_name in subsurface_dict.keys():
                        if not subsurface_dict[subsurface_name].get("door_option_compatible", False):
                            continue
                        subsurface = subsurface_dict[subsurface_name]["subsurface object"]
                        if not subsurface.construction().is_initialized():
                            runner.registerWarning(f"No construction found for {subsurface_name}, RSMeans replacement skipped.")
                            continue

                        old_construction = subsurface.construction().get()
                        old_construction_name = old_construction.nameString()
                        old_r_value_si = 0.0
                        if old_construction.to_LayeredConstruction().is_initialized():
                            lc = old_construction.to_LayeredConstruction().get()
                            if lc.thermalConductance().is_initialized() and lc.thermalConductance().get() > 0.0:
                                old_r_value_si = 1.0 / lc.thermalConductance().get()

                        new_r_value_si = (
                            resolved_door_material_props['thickness']
                            / resolved_door_material_props['conductivity']
                        )
                        old_r_value_ip = openstudio.convert(old_r_value_si, "m^2*K/W", "ft^2*h*R/Btu").get()
                        new_r_value_ip = openstudio.convert(new_r_value_si, "m^2*K/W", "ft^2*h*R/Btu").get()

                        new_construction = old_construction.clone(model).to_Construction().get()
                        new_construction.setName(
                            f"{old_construction_name} - RSMeans {rsmeans_applied_door_option} R-{new_r_value_si:.2f}"
                        )

                        new_door_material = openstudio.model.StandardOpaqueMaterial(model)
                        new_door_material.setName(
                            f"RSMeans {rsmeans_applied_door_option} {rsmeans_door_hit.get('rsmeans_id', '')}"
                        )
                        new_door_material.setThickness(resolved_door_material_props['thickness'])
                        new_door_material.setConductivity(resolved_door_material_props['conductivity'])
                        new_door_material.setDensity(resolved_door_material_props['density'])
                        new_door_material.setSpecificHeat(1000)

                        new_construction.setLayers([new_door_material])
                        subsurface.setConstruction(new_construction)

                        subsurface_dict[subsurface_name]['old_r_value_si'] = old_r_value_si
                        subsurface_dict[subsurface_name]['new_r_value_si'] = new_r_value_si
                        subsurface_dict[subsurface_name]['new_construction_name'] = new_construction.nameString()
                        subsurface_dict[subsurface_name]['material_thickness_m'] = resolved_door_material_props['thickness']
                        subsurface_dict[subsurface_name]['material_conductivity_W_per_mK'] = resolved_door_material_props['conductivity']
                        subsurface_dict[subsurface_name]['material_density_kg_per_m3'] = resolved_door_material_props['density']

                        runner.registerInfo(f"\n  → RSMeans door construction updated for {subsurface_name}:")
                        runner.registerInfo(f"    RSMeans Match: {rsmeans_door_match_description}")
                        runner.registerInfo(
                            f"    R-value: {old_r_value_si:.2f} → {new_r_value_si:.2f} m²·K/W "
                            f"(R-{old_r_value_ip:.1f} → R-{new_r_value_ip:.1f} IP)"
                        )
                        runner.registerInfo(
                            f"    Thickness: {resolved_door_material_props['thickness']*1000:.1f} mm | "
                            f"Conductivity: {resolved_door_material_props['conductivity']:.3f} W/m·K"
                        )
            else:
                runner.registerWarning(
                    "No RSMeans door hit available for replacement. Keeping door_option-based material properties."
                )
        
        # ── Phase 5: AdditionalProperties write-out (centralized) ───────────
        # Keep all AdditionalProperties writes in one place for readability.
        building = model.getBuilding()
        basic_input = building.additionalProperties()
        site = model.getSite()
        reno_detail = site.additionalProperties()
        facility = model.getFacility()
        factors = facility.additionalProperties()
        simcontrol = model.getSimulationControl()
        results = simcontrol.additionalProperties()
        sizingpara = model.getSizingParameters()
        mtrl_prop = sizingpara.additionalProperties()


        # 5B) Aggregate values used by model-level bucket writes
        gwp_per_unit_list = []
        gwp_per_m2_list = []
        gwp_per_m_bottom_list = []
        gwp_per_m_side_list = []
        for name in subsurface_dict.keys():
            if 'door' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['door']:
                gwp_m2 = subsurface_dict[name]['door']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_per_m2_list.append(gwp_m2)
            if 'door' in subsurface_dict[name] and 'gwp_per_unit' in subsurface_dict[name]['door']:
                gwp_unit = subsurface_dict[name]['door']['gwp_per_unit']
                if gwp_unit is not None and gwp_unit > 0:
                    gwp_per_unit_list.append(gwp_unit)
            if 'door_bottom_sealing' in subsurface_dict[name] and 'gwp_per_m' in subsurface_dict[name]['door_bottom_sealing']:
                gwp_m = subsurface_dict[name]['door_bottom_sealing']['gwp_per_m']
                if gwp_m is not None and gwp_m > 0:
                    gwp_per_m_bottom_list.append(gwp_m)
            if 'door_side_sealing' in subsurface_dict[name] and 'gwp_per_m' in subsurface_dict[name]['door_side_sealing']:
                gwp_m = subsurface_dict[name]['door_side_sealing']['gwp_per_m']
                if gwp_m is not None and gwp_m > 0:
                    gwp_per_m_side_list.append(gwp_m)

        # Resolve a primary RSMeans unit cost ID/description for reporting in material properties.
        rsmeans_unit_cost_line_id_value = ""
        rsmeans_unit_cost_description_value = ""
        if matched_rsmeans["door_material"]["id"]:
            rsmeans_unit_cost_line_id_value = matched_rsmeans["door_material"]["id"]
            rsmeans_unit_cost_description_value = matched_rsmeans["door_material"]["description"]
        elif rsmeans_lookup and rsmeans_lookup.get("status") == "ok":
            first_hit = (rsmeans_lookup.get("results", {}).get("materials", []) or [{}])[0]
            rsmeans_unit_cost_line_id_value = str(first_hit.get("rsmeans_id", "") or "")
            rsmeans_unit_cost_description_value = str(
                first_hit.get("rsmeans_description", "") or first_hit.get("description", "") or ""
            )

        # 5C) Building bucket (basic inputs)
        basic_input.setFeature("door_enhancement_measure_name", "Door Enhancement")
        basic_input.setFeature("door_enhancement_analysis_period_years", analysis_period)
        basic_input.setFeature("door_enhancement_gwp_statistic", gwp_statistic)

        # 5D) Site bucket (renovation details)
        reno_detail.setFeature("door_enhancement_processed_door_count", len(sub_surfaces_to_change))
        reno_detail.setFeature("door_enhancement_door_area_per_unit_m2", door_area_per_unit)
        reno_detail.setFeature("door_enhancement_infiltration_reduction_percent", space_infiltration_reduction_percent)
        reno_detail.setFeature("door_bottom_seal_option", door_bottom_seal_option)
        reno_detail.setFeature("door_sealing_bottom_length_m", total_sealing_bottom_length_m)
        reno_detail.setFeature("door_top_side_seal_option", door_top_side_seal_option)
        reno_detail.setFeature("door_sealing_side_length_m", total_sealing_side_length_m)
        reno_detail.setFeature("door_option", door_option)
        # Renovated area is the area where the selected door option is actually applicable.
        reno_detail.setFeature("door_enhancement_renovated_area_m2", total_eligible_door_area_m2)
        # Keep full processed area for traceability/debugging.
        reno_detail.setFeature("door_enhancement_total_processed_area_m2", total_door_area_m2)

        # Set summary notes based on model-door compatibility conflicts.
        summary_notes = "door enhancement successfully completed!"

        normalized_door_option = str(door_option).strip().lower().replace("_", " ").replace("-", " ")
        normalized_door_option = " ".join(normalized_door_option.split())
        available_types_summary = (
            f"available subsurface counts -> "
            f"Door={available_door_subsurface_types['Door']}, "
            f"GlassDoor={available_door_subsurface_types['GlassDoor']}, "
            f"OverheadDoor={available_door_subsurface_types['OverheadDoor']}"
        )

        if (
            (not len(sub_surfaces_to_change) > 0)
            or (normalized_door_option == "wooden door" and available_door_subsurface_types["Door"] == 0)
            or (normalized_door_option in {"polystyrene core steel door", "polyurethane core steel door", "honeycomb core steel door", "stiffened core steel door"} and available_door_subsurface_types["Door"] == 0)
            or (normalized_door_option in {"garage door", "garagedoor"} and available_door_subsurface_types["OverheadDoor"] == 0)
            or (normalized_door_option in {"glass door", "glassdoor"} and available_door_subsurface_types["GlassDoor"] == 0)
        ):
            summary_notes = (
                "No door construction or appropriate door subsurface type in the model for renovation; "
                + available_types_summary
            )

        reno_detail.setFeature("door_enhancement_summary_notes", summary_notes)

        # 5E) SizingParameters bucket (material properties)
        mtrl_prop.setFeature("door_strip_lifetime_years", strip_lifetime)
        mtrl_prop.setFeature("door_lifetime_years", door_lifetime)
        # Store materials id and description from RSMeans
        if matched_rsmeans["door_material"]["id"]:
            mtrl_prop.setFeature("door_material_rsmeans_id", matched_rsmeans["door_material"]["id"])
        if matched_rsmeans["door_material"]["description"]:
            mtrl_prop.setFeature("door_material_rsmeans_description", matched_rsmeans["door_material"]["description"])
        if matched_rsmeans["door_bottom_seal"]["id"]:
            mtrl_prop.setFeature("door_bottom_seal_rsmeans_id", matched_rsmeans["door_bottom_seal"]["id"])
        if matched_rsmeans["door_bottom_seal"]["description"]:
            mtrl_prop.setFeature("door_bottom_seal_rsmeans_description", matched_rsmeans["door_bottom_seal"]["description"])
        if matched_rsmeans["door_top_side_seal"]["id"]:
            mtrl_prop.setFeature("door_top_side_seal_rsmeans_id", matched_rsmeans["door_top_side_seal"]["id"])
        if matched_rsmeans["door_top_side_seal"]["description"]:
            mtrl_prop.setFeature("door_top_side_seal_rsmeans_description", matched_rsmeans["door_top_side_seal"]["description"])
        if rsmeans_unit_cost_line_id_value:
            mtrl_prop.setFeature("rsmeans_unit_cost_line_id", rsmeans_unit_cost_line_id_value)
        if rsmeans_unit_cost_description_value:
            mtrl_prop.setFeature("rsmeans_unit_cost_description", rsmeans_unit_cost_description_value)

        # Selected door option material properties
        if door_option != 'none':
            door_r_value = self.door_r_values().get(door_option, 0.0)
            if (
                resolved_door_thickness is not None and resolved_door_thickness > 0.0
                and resolved_door_conductivity is not None and resolved_door_conductivity > 0.0
            ):
                door_r_value = resolved_door_thickness / resolved_door_conductivity
            mtrl_prop.setFeature("door_r_value_m2KperW", door_r_value)

            if resolved_door_density is not None:
                mtrl_prop.setFeature("door_density_kg_per_m3", resolved_door_density)
            if resolved_door_thickness is not None:
                mtrl_prop.setFeature("door_thickness_m", resolved_door_thickness)
            if resolved_door_conductivity is not None:
                mtrl_prop.setFeature("door_conductivity_W_per_mK", resolved_door_conductivity)

        if rsmeans_door_area_per_unit_m2 is not None:
            mtrl_prop.setFeature("rsmeans_door_area_per_unit_m2", rsmeans_door_area_per_unit_m2)
        if rsmeans_door_thickness_m is not None:
            mtrl_prop.setFeature("rsmeans_door_thickness_m", rsmeans_door_thickness_m)
        
        # Store length per unit for sealing strips
        if door_bottom_seal_option != 'none':
            bottom_length = length_per_unit_dict.get(door_bottom_seal_option, 0.0)
            mtrl_prop.setFeature("door_bottom_seal_length_per_unit_m", bottom_length)
        
        if door_top_side_seal_option != 'none':
            top_side_length = length_per_unit_dict.get(door_top_side_seal_option, 0.0)
            mtrl_prop.setFeature("door_top_side_seal_length_per_unit_m", top_side_length)

        # 5F) Facility bucket (factors)
        if gwp_per_m2_list:
            factors.setFeature("door_gwp_per_m2_kgCO2eq", float(np.mean(gwp_per_m2_list)))
        if gwp_per_unit_list:
            factors.setFeature("door_gwp_per_unit_kgCO2eq", float(np.mean(gwp_per_unit_list)))
        if gwp_per_m_bottom_list:
            factors.setFeature("door_bottom_seal_gwp_per_m_kgCO2eq", float(np.mean(gwp_per_m_bottom_list)))
        if gwp_per_m_side_list:
            factors.setFeature("door_side_seal_gwp_per_m_kgCO2eq", float(np.mean(gwp_per_m_side_list)))

        # 5G) SimulationControl bucket (results)
        # Canonical embodied carbon key used by wall/roof/window measures.
        results.setFeature("door_enhancement_embodied_carbon_kgCO2eq", total_embodied_carbon)

        # Apply lifetime multipliers to RSMeans API costs (non-custom path only).
        # For the custom path the multipliers are already baked into the component costs.
        # For RSMeans, iterate over per-material costs and scale by replacement count.
        if (rsmeans_lookup is not None
                and rsmeans_lookup.get("status") == "ok"
                and rsmeans_lookup.get("cost_source", "rsmeans_api") not in ("custom_input", "custom_input_fallback")):
            _lc_summary = rsmeans_lookup.get("summary", {})
            _lc_materials = rsmeans_lookup.get("results", {}).get("materials", [])
            _mult_door_lc = int(lifetime_multiplier(door_lifetime, analysis_period))
            _mult_seal_lc = int(lifetime_multiplier(strip_lifetime, analysis_period))
            if _mult_door_lc != 1 or _mult_seal_lc != 1:
                _adj_material = 0.0
                _adj_labor = 0.0
                _adj_equipment = 0.0
                for _m in _lc_materials:
                    _mn = str(_m.get("name", "")).lower()
                    _mc = float(_m.get("total_cost_area_adjusted", _m.get("total_cost", 0.0)))
                    _ml = float(_m.get("total_labor_cost", 0.0))
                    _me = float(_m.get("total_equipment_cost", 0.0))
                    _mult_for_mat = _mult_seal_lc if "seal" in _mn else _mult_door_lc
                    _m["total_cost"] = _mc * _mult_for_mat
                    _m["total_labor_cost"] = _ml * _mult_for_mat
                    _m["total_equipment_cost"] = _me * _mult_for_mat
                    _adj_material += _m["total_cost"]
                    _adj_labor += _m["total_labor_cost"]
                    _adj_equipment += _m["total_equipment_cost"]
                _ohp_pct = float(_lc_summary.get("overhead_profit_percent", 0.0))
                _adj_overhead = (_adj_material + _adj_labor + _adj_equipment) * _ohp_pct * 0.01
                _lc_summary["total_material_cost"] = _adj_material
                _lc_summary["total_labor_cost"] = _adj_labor
                _lc_summary["total_equipment_cost"] = _adj_equipment
                _lc_summary["total_overhead_profit_cost"] = _adj_overhead
                _lc_summary["total_cost_with_overhead_profit"] = (
                    _adj_material + _adj_labor + _adj_equipment + _adj_overhead
                )
                runner.registerInfo(
                    f"RSMeans costs scaled by lifetime multipliers: "
                    f"door_multiplier={_mult_door_lc}, seal_multiplier={_mult_seal_lc}; "
                    f"lifecycle material=${_adj_material:,.2f} "
                    f"labor=${_adj_labor:,.2f} equipment=${_adj_equipment:,.2f}"
                )

        door_rsmeans_cost_per_area_feature_value = "N/A"
        door_rsmeans_bottom_seal_cost_per_m_feature_value = "N/A"
        door_rsmeans_top_side_seal_cost_per_m_feature_value = "N/A"

        if rsmeans_lookup is not None and rsmeans_lookup.get("status") == "ok":
            rsmeans_summary_dict = rsmeans_lookup.get("summary", {})
            rsmeans_results_dict = rsmeans_lookup.get("results", {})
            cost_source_val = rsmeans_lookup.get("cost_source", "rsmeans_api")
            rsmeans_material_cost = float(rsmeans_summary_dict.get("total_material_cost", 0.0))
            rsmeans_labor_cost = float(rsmeans_summary_dict.get("total_labor_cost", 0.0))
            rsmeans_equipment_cost = float(rsmeans_summary_dict.get("total_equipment_cost", 0.0))
            rsmeans_overhead_percent = float(rsmeans_summary_dict.get("overhead_profit_percent", 0.0))
            rsmeans_overhead_cost = float(rsmeans_summary_dict.get("total_overhead_profit_cost", 0.0))
            rsmeans_total_cost = float(rsmeans_summary_dict.get("total_cost_with_overhead_profit", 0.0))

            # Derive cost_factor_basis from the units of the matched materials.
            # Doors are priced per EA (each), seals per LF (linear foot). If
            # both are present the basis is "mixed".
            matched_mats = rsmeans_results_dict.get("materials", [])
            unit_set = set()
            for mat in matched_mats:
                u = str(mat.get("unit", "")).upper().strip()
                if u:
                    unit_set.add(u)

            if cost_source_val != "custom_input":
                _door_cost_total = 0.0
                _bottom_seal_cost_total = 0.0
                _top_side_seal_cost_total = 0.0
                for mat in matched_mats:
                    _mat_name = str(mat.get("name", "")).lower()
                    _mat_cost = float(mat.get("total_cost_area_adjusted", mat.get("total_cost", 0.0)) or 0.0)
                    if "door" in _mat_name and "seal" not in _mat_name:
                        _door_cost_total += _mat_cost
                    elif "bottom seal" in _mat_name:
                        _bottom_seal_cost_total += _mat_cost
                    elif "top side seal" in _mat_name or "top/side" in _mat_name or "jamb" in _mat_name:
                        _top_side_seal_cost_total += _mat_cost

                if total_eligible_door_area_m2 > 0.0 and _door_cost_total > 0.0:
                    door_rsmeans_cost_per_area_feature_value = _door_cost_total / float(total_eligible_door_area_m2)
                if total_sealing_bottom_length_m > 0.0 and _bottom_seal_cost_total > 0.0:
                    door_rsmeans_bottom_seal_cost_per_m_feature_value = _bottom_seal_cost_total / float(total_sealing_bottom_length_m)
                if total_sealing_side_length_m > 0.0 and _top_side_seal_cost_total > 0.0:
                    door_rsmeans_top_side_seal_cost_per_m_feature_value = _top_side_seal_cost_total / float(total_sealing_side_length_m)

            if cost_source_val == "custom_input":
                cost_factor_basis = "custom_cost_per_area"
            elif rsmeans_area_cost_adjusted:
                if "LF" in unit_set:
                    cost_factor_basis = "mixed_area_length"
                else:
                    cost_factor_basis = "cost_per_area"
            elif not unit_set:
                cost_factor_basis = "not_calculated"
            elif unit_set == {"EA"}:
                cost_factor_basis = "cost_per_unit"
            elif unit_set == {"LF"}:
                cost_factor_basis = "cost_per_length"
            else:
                cost_factor_basis = "mixed"

            # -- Facility (factors) bucket: cost totals and basis metadata --
            factors.setFeature("door_enhancement_cost_source", cost_source_val)
            factors.setFeature("door_enhancement_cost_factor_basis", cost_factor_basis)
            factors.setFeature("door_enhancement_overhead_profit_percent", rsmeans_overhead_percent)
            factors.setFeature("door_enhancement_custom_labor_cost_multiplier", labor_cost_multiplier)
            factors.setFeature("door_enhancement_custom_door_cost_per_area", custom_door_cost_per_area)
            factors.setFeature("door_enhancement_custom_bottom_seal_cost_per_m", custom_bottom_seal_cost)
            factors.setFeature("door_enhancement_custom_top_side_seal_cost_per_m", custom_top_side_seal_cost)
            factors.setFeature("door_enhancement_rsmeans_door_cost_per_area", door_rsmeans_cost_per_area_feature_value)
            factors.setFeature("door_enhancement_rsmeans_bottom_seal_cost_per_m", door_rsmeans_bottom_seal_cost_per_m_feature_value)
            factors.setFeature("door_enhancement_rsmeans_top_side_seal_cost_per_m", door_rsmeans_top_side_seal_cost_per_m_feature_value)

            # -- SimulationControl (results) bucket: mirrored scalars + JSON --
            results.setFeature("door_enhancement_material_cost_$", rsmeans_material_cost)
            results.setFeature("door_enhancement_labor_cost_$", rsmeans_labor_cost)
            results.setFeature("door_enhancement_equipment_cost_$", rsmeans_equipment_cost)
            results.setFeature("door_enhancement_overhead_profit_cost_$", rsmeans_overhead_cost)
            results.setFeature("door_enhancement_total_cost_with_overhead_and_profit_$", rsmeans_total_cost)

            # Three JSON payloads for full diagnostic traceability (mirrors
            # the three-payload pattern used by wall and roof insulation measures).
            #
            # 1. matches_json – all matched materials + search_log + slim catalog summary
            # matches_payload = {
            #     "materials": matched_mats,
            #     "search_log": rsmeans_results_dict.get("search_log", []),
            #     "summary": {
            #         "release_id": rsmeans_summary_dict.get("release_id", ""),
            #         "location_id": rsmeans_summary_dict.get("location_id", ""),
            #         "labor_type": rsmeans_summary_dict.get("labor_type", ""),
            #         "measurement_system": rsmeans_summary_dict.get("measurement_system", ""),
            #         "catalogs_searched": rsmeans_summary_dict.get("catalogs_searched", []),
            #     },
            # }
            # results.setFeature("door_enhancement_rsmeans_matches_json", json.dumps(matches_payload))
            # # 2. search_results_json – full results dict (materials, errors, search_log, catalogs)
            # results.setFeature("door_enhancement_rsmeans_search_results_json", json.dumps(rsmeans_results_dict))
            # # 3. summary_json – full financial and catalog metadata
            # results.setFeature("door_enhancement_rsmeans_summary_json", json.dumps(rsmeans_summary_dict))
            # retrofit_materials_json – the search inputs sent to the API (used by
            # standalone call_rsmeans_api.py to re-run a lookup without re-running
            # the full measure)
            # results.setFeature("door_enhancement_retrofit_materials_json", json.dumps(rsmeans_materials))

            runner.registerInfo(
                f"[INFO] RSMeans cost stored: source={cost_source_val}, "
                f"basis={cost_factor_basis}, "
                f"total=${rsmeans_total_cost:,.2f}"
            )
        else:
            # Cost lookup was not attempted or did not succeed; record "none"
            # in both buckets so downstream consumers always find the key.
            factors.setFeature("door_enhancement_cost_source", "none")
            factors.setFeature("door_enhancement_cost_factor_basis", "not_calculated")
            factors.setFeature("door_enhancement_overhead_profit_percent", 0.0)
            factors.setFeature("door_enhancement_custom_labor_cost_multiplier", labor_cost_multiplier)
            factors.setFeature("door_enhancement_custom_door_cost_per_area", custom_door_cost_per_area)
            factors.setFeature("door_enhancement_custom_bottom_seal_cost_per_m", custom_bottom_seal_cost)
            factors.setFeature("door_enhancement_custom_top_side_seal_cost_per_m", custom_top_side_seal_cost)
            factors.setFeature("door_enhancement_rsmeans_door_cost_per_area", door_rsmeans_cost_per_area_feature_value)
            factors.setFeature("door_enhancement_rsmeans_bottom_seal_cost_per_m", door_rsmeans_bottom_seal_cost_per_m_feature_value)
            factors.setFeature("door_enhancement_rsmeans_top_side_seal_cost_per_m", door_rsmeans_top_side_seal_cost_per_m_feature_value)

        reno_detail.setFeature("total_doors_processed_count", len(sub_surfaces_to_change))
        reno_detail.setFeature("total_doors_with_r_value_change_count", doors_with_r_value_change)
        
        # Construction names for traceability
        if construction_names:
            basic_input.setFeature("door_enhancement_construction_names", ', '.join(construction_names))
        
        runner.registerInfo(f"\n✓ Door enhancement summary stored in organized additional properties")
        
        # Report final condition
        runner.registerInfo("\n" + "=" * 80)
        runner.registerInfo("MEASURE SUMMARY")
        runner.registerInfo("=" * 80)
        runner.registerInfo(f"Infiltration: Modified {altered_infiltration_instances} objects affecting {affected_area_si:.2f} m² ({affected_area_ip:.2f} ft²)")
        runner.registerInfo(f"Doors processed: {len(sub_surfaces_to_change)} subsurfaces")
        if doors_with_r_value_change > 0:
            runner.registerInfo(f"R-value updates: {doors_with_r_value_change} door(s) upgraded with '{door_option}' (R-{self.door_r_values()[door_option]:.2f} m²·K/W)")
        else:
            runner.registerInfo(f"R-value updates: None (sealing only or 'none' option)")
        runner.registerInfo(f"Total embodied carbon: {total_embodied_carbon:.2f} kg CO2 eq")
        runner.registerInfo("=" * 80)
        
        if doors_with_r_value_change > 0:
            runner.registerFinalCondition(
                f"Door enhancement completed: {altered_infiltration_instances} infiltration objects modified, "
                f"{len(sub_surfaces_to_change)} doors processed, {doors_with_r_value_change} R-value(s) updated, "
                f"Total EC: {total_embodied_carbon:.2f} kg CO2 eq"
            )
        else:
            runner.registerFinalCondition(
                f"Door enhancement completed: {altered_infiltration_instances} infiltration objects modified, "
                f"{len(sub_surfaces_to_change)} doors processed (sealing only), "
                f"Total EC: {total_embodied_carbon:.2f} kg CO2 eq"
            )

        return True

    def pull_rsmeans_cost_from_api(self, runner, materials):
        """
        Pull RSMeans cost data for door retrofit materials using API credentials
        from environment variables (client_id, client_secret).
        """
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()
            client_id = os.getenv("client_id")
            client_secret = os.getenv("client_secret")

            if not client_id or not client_secret:
                runner.registerWarning(
                    "RSMeans API credentials (client_id, client_secret) not found in environment. Skipping RSMeans cost retrieval."
                )
                return {}

            runner.registerInfo("Initializing RSMeans API client...")
            client = RSMeansAPIClient(client_id, client_secret, use_sandbox=False)

            if not client.authenticate():
                runner.registerWarning("Failed to authenticate with RSMeans API. Skipping cost retrieval.")
                return {}

            runner.registerInfo(f"Querying RSMeans API for {len(materials)} materials...")

            return run_rsmeans_cost_lookup(
                materials=materials,
                release_id="2024-an",
                catalogs=["bc-mf", "gb-mf", "rp-mf"],
                location_id="us-us-national",
                labor_type="std",
                measurement_system="imp",
                use_sandbox=False,
                overhead_profit_percent=10.0,
            )
        except Exception as e:
            runner.registerWarning(f"RSMeans API lookup failed: {str(e)}")
            return {}


# Register the measure
DoorEnhancement().registerWithApplication()

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import typing
from resources.call_rsmeans_api import RSMeansAPIClient, run_rsmeans_cost_lookup
import numpy as np
from resources.EC3_lookup import *

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
            door_product_url = generate_url_byname(name_like = 'window door system', plant_geography = '150')
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
        custom_door_cost_per_unit = openstudio.measure.OSArgument.makeDoubleArgument("custom_door_cost_per_unit", False)
        custom_door_cost_per_unit.setDisplayName("Custom Door Cost ($/m²)")
        custom_door_cost_per_unit.setDescription("Custom material and labor cost for door replacement per unit area. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_door_cost_per_unit.setUnits("$/m²")
        custom_door_cost_per_unit.setDefaultValue(0.0)
        args.append(custom_door_cost_per_unit)

        # make an argument for custom bottom seal cost ($/length)
        custom_bottom_seal_cost = openstudio.measure.OSArgument.makeDoubleArgument("custom_bottom_seal_cost", False)
        custom_bottom_seal_cost.setDisplayName("Custom Bottom Seal Cost ($/m)")
        custom_bottom_seal_cost.setDescription("Custom material and labor cost for bottom seal per unit length. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_bottom_seal_cost.setUnits("$/m")
        custom_bottom_seal_cost.setDefaultValue(0.0)
        args.append(custom_bottom_seal_cost)

        # make an argument for custom top/side seal cost ($/length)
        custom_top_side_seal_cost = openstudio.measure.OSArgument.makeDoubleArgument("custom_top_side_seal_cost", False)
        custom_top_side_seal_cost.setDisplayName("Custom Top/Side Seal Cost ($/m)")
        custom_top_side_seal_cost.setDescription("Custom material and labor cost for top and side seal per unit length. Only used if 'Use Custom Cost Inputs?' is true.")
        custom_top_side_seal_cost.setUnits("$/m")
        custom_top_side_seal_cost.setDefaultValue(0.0)
        args.append(custom_top_side_seal_cost)

        # optional exact RSMeans unit cost line ID override
        rsmeans_unit_costline_id = openstudio.measure.OSArgument.makeStringArgument("rsmeans_unit_costline_id", True)
        rsmeans_unit_costline_id.setDisplayName("RSMeans Unit Cost Line ID (Optional Override)")
        rsmeans_unit_costline_id.setDescription("Optional exact RSMeans unit cost line ID. If provided, the measure attempts this ID first before normal search logic.")
        rsmeans_unit_costline_id.setDefaultValue("")
        args.append(rsmeans_unit_costline_id)

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
        custom_door_cost_per_unit = runner.getDoubleArgumentValue("custom_door_cost_per_unit", user_arguments)
        custom_bottom_seal_cost = runner.getDoubleArgumentValue("custom_bottom_seal_cost", user_arguments)
        custom_top_side_seal_cost = runner.getDoubleArgumentValue("custom_top_side_seal_cost", user_arguments)
        rsmeans_unit_costline_id = runner.getStringArgumentValue("rsmeans_unit_costline_id", user_arguments).strip()

        if use_custom_costs:
            runner.registerInfo("Custom cost mode enabled. Using user-provided cost values instead of RSMeans API.")
            runner.registerInfo(f"  Door cost: ${custom_door_cost_per_unit}/m²")
            runner.registerInfo(f"  Bottom seal cost: ${custom_bottom_seal_cost}/m")
            runner.registerInfo(f"  Top/side seal cost: ${custom_top_side_seal_cost}/m")
            if rsmeans_unit_costline_id:
                runner.registerInfo("  RSMeans Unit Cost Line ID override ignored because custom cost mode is enabled.")
        elif rsmeans_unit_costline_id:
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
        if analysis_period < 0:
            runner.registerError("Choose an integer larger than 0 for analysis period of embodied carbon calculation.")
        if strip_lifetime < 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door bottom strip.")
        if door_area_per_unit < 0:
            runner.registerError("Choose a numeric value larger than 0 for door area per unit.")
        if door_lifetime < 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door.")
        if length_per_unit_bottom_side < 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door bottom sealing strip.")
        if length_per_unit_other_sides < 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door other sides sealing strip.")
        if door_thermal_conductivity < 0:
            runner.registerError("Door thermal conductivity must be non-negative.")
        if door_density < 0:
            runner.registerError("Door material density must be non-negative.")
        if door_thickness < 0:
            runner.registerError("Door thickness must be non-negative.")
        
        # Check for conflicting door options
        if door_option != 'none':
            if door_thermal_conductivity > 0.0 and door_density > 0.0 and door_thickness > 0.0:
                # All three custom properties provided - this is fine
                runner.registerInfo(f"Using custom door material properties for {door_option}")
            elif door_thermal_conductivity > 0.0 or door_density > 0.0 or door_thickness > 0.0:
                # Only some properties provided - warning
                runner.registerWarning(f"Only some door material properties provided. Missing properties will use defaults for {door_option}")
        
        ####################### Change model's space infiltration#######################
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
        
        ####################### Calculate Embodied Carbon#######################
        sub_surfaces = []
        for space in spaces:
            for surface in space.surfaces():
                for subsurface in surface.subSurfaces():
                    sub_surfaces.append(subsurface)
        
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
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
            runner.registerInfo(f"\n{'─' * 80}")
            runner.registerInfo(f"Processing: {subsurface_name}")
            runner.registerInfo(f"{'─' * 80}")
            subsurface_dict[subsurface_name] = {}
            subsurface_dict[subsurface_name]["subsurface object"] = subsurface
            subsurface_dict[subsurface_name]["Door type"] = subsurface.subSurfaceType()
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
            bottom_sealing_product_epd = fetch_epd_data(url = bottom_sealing_product_url, api_token = api_key)
            side_sealing_product_epd = fetch_epd_data(url = side_sealing_product_url, api_token = api_key)
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
            door_product_epd = fetch_epd_data(url = door_product_url, api_token = api_key)
            epd_datalist["door"] = door_product_epd
            
            if door_product_epd is None:
                runner.registerInfo(f"  DEBUG: Door EPD is None")
            elif isinstance(door_product_epd, list):
                runner.registerInfo(f"  DEBUG: Door EPD returned {len(door_product_epd)} records")

            for material_name, epd_data in epd_datalist.items():
                # Skip if no EPD data available (None or empty list), but initialize with zeros
                if epd_data is None or (isinstance(epd_data, list) and len(epd_data) == 0):
                    runner.registerInfo(f"  ⚠ No EPD data available for {material_name}, setting embodied carbon to 0")
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
                    gwp_per_m = 0.0
                    if gwp_per_unit!= 0 and material_name == "door_bottom_sealing":
                        gwp_per_m = gwp_per_unit / length_per_unit_dict[door_bottom_seal_option]
                        gwp_values["gwp_per_m"].append(float(gwp_per_m))
                    elif gwp_per_unit != 0 and material_name == "door_side_sealing":
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
                if material_name in "door_bottom_sealing" and gwp_per_m != 0.0:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] *
                            sealing_bottom_length *
                            multiplier)
                elif material_name == "door_side_sealing" and gwp_per_m != 0.0:
                    if subsurface.subSurfaceType() != 'OverheadDoor':
                        embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m"] *
                                                sealing_side_length *
                                                multiplier)
                    else:
                        embodied_carbon = 0.0
                        runner.registerInfo(f"  ○ Door side sealing skipped for {subsurface_name} (overhead door)")
                    
                elif material_name == "door" and gwp_per_m2 != 0.0:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] *
                                                door_area *
                                                multiplier)
                else:
                    runner.registerInfo(f"  ○ {material_name}: No GWP data available, entering 0.0")
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
            if door_option != 'none':
                # Get material properties for selected door type
                mat_props = self.door_material_properties()[door_option].copy()
                
                # Override with user-provided values if non-zero
                if door_thermal_conductivity > 0.0:
                    mat_props['conductivity'] = door_thermal_conductivity
                if door_density > 0.0:
                    mat_props['density'] = door_density
                if door_thickness > 0.0:
                    mat_props['thickness'] = door_thickness
                
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

            # # attach additional properties to openstudio material
            # additional_properties = subsurface_dict[subsurface_name]["subsurface object"].additionalProperties()
            # additional_properties.setFeature("Subsurface name", subsurface_name)
            # additional_properties.setFeature("embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"])
            # if door_option != 'none':
            #     additional_properties.setFeature("door_type", door_option)
            #     additional_properties.setFeature("old_r_value_si_m2KperW", subsurface_dict[subsurface_name].get('old_r_value_si', 0.0))
            #     additional_properties.setFeature("new_r_value_si_m2KperW", subsurface_dict[subsurface_name].get('new_r_value_si', 0.0))
   
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

        # -------------------------------------------------------------------
        # RSMeans lookup: query each retrofit material type separately
        # -------------------------------------------------------------------
        def _format_ft_in(value_m: float) -> str:
            inches_total = value_m * 39.37007874
            feet = int(inches_total // 12)
            inches = int(round(inches_total - feet * 12))
            if inches == 12:
                feet += 1
                inches = 0
            return f"{feet} ft {inches} in"

        rsmeans_lookup = None
        rsmeans_summary_line = None
        rsmeans_size_str = ""
        matched_rsmeans = {
            "door_material": {"id": "", "description": ""},
            "door_bottom_seal": {"id": "", "description": ""},
            "door_top_side_seal": {"id": "", "description": ""},
        }

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
            if door_option != 'none':
                rsmeans_materials.append(
                    {
                        "name": f"{door_option} door",
                        "description": f"{len(sub_surfaces_to_change)} door(s); size: {rsmeans_size_str}",
                        "quantity": float(len(sub_surfaces_to_change)),
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
                        "division_code": "08",
                    }
                )

            if door_top_side_seal_option != 'none' and total_sealing_side_length_m > 0.0:
                rsmeans_materials.append(
                    {
                        "name": f"door top side seal {door_top_side_seal_option}",
                        "description": f"Top/side seal material ({door_top_side_seal_option})",
                        "quantity": float(total_sealing_side_length_m * 3.28084),
                        "unit": "LF",
                        "division_code": "08",
                    }
                )

            try:
                if use_custom_costs:
                    runner.registerInfo("Using custom cost inputs (RSMeans API lookup skipped).")
                    # Create a mock RSMeans lookup result using custom costs
                    total_custom_cost = custom_door_cost_per_unit * float(len(sub_surfaces_to_change))
                    rsmeans_lookup = {
                        "status": "ok",
                        "cost_source": "custom_input",
                        "summary": {
                            "materials_count": 1,
                            "total_material_cost": total_custom_cost,  # Fixed field name
                            "overhead_profit_percent": 0.0,  # Fixed field name
                            "total_overhead_profit_cost": 0.0,  # Fixed field name - Custom costs assumed to already include labor/profit
                            "total_cost_with_overhead_profit": total_custom_cost,
                            "release_id": "custom",
                            "location_id": "custom",
                            "labor_type": "custom",
                            "measurement_system": "custom",
                            "catalogs_searched": []
                        }
                    }
                    rsmeans_summary_line = (
                        "Custom cost summary (cost_source=custom_input): "
                        f"door_cost=${custom_door_cost_per_unit * float(len(sub_surfaces_to_change)):,.2f} "
                        f"({len(sub_surfaces_to_change)} doors @ ${custom_door_cost_per_unit}/m²)"
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
        
        # Store summary in organized additional properties buckets (same pattern as window enhancement)
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

        # Store basic measure parameters
        basic_input.setFeature("measure_name", "Door Enhancement")
        basic_input.setFeature("analysis_period_years", analysis_period)
        reno_detail.setFeature("door_area_per_unit_m2", door_area_per_unit)
        basic_input.setFeature("gwp_statistic", gwp_statistic)

        # Store construction material lifetimes
        mtrl_prop.setFeature("door_strip_lifetime_years", strip_lifetime)
        mtrl_prop.setFeature("door_lifetime_years", door_lifetime)
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

        # Store infiltration reduction and selected renovation options
        reno_detail.setFeature("door_enhancement_infiltration_reduction_percent", space_infiltration_reduction_percent)
        reno_detail.setFeature("door_bottom_seal_option", door_bottom_seal_option)
        reno_detail.setFeature("door_top_side_seal_option", door_top_side_seal_option)
        reno_detail.setFeature("door_option", door_option)

        # Store door option and properties
        if door_option != 'none':
            door_r_value = self.door_r_values().get(door_option, 0.0)
            mtrl_prop.setFeature("door_r_value_m2KperW", door_r_value)
            
            # Get material properties for the selected door
            mat_props = self.door_material_properties().get(door_option, {})
            if mat_props:
                actual_density = door_density if door_density > 0.0 else mat_props.get('density', 0.0)
                actual_thickness = door_thickness if door_thickness > 0.0 else mat_props.get('thickness', 0.0)
                actual_conductivity = door_thermal_conductivity if door_thermal_conductivity > 0.0 else mat_props.get('conductivity', 0.0)
                
                mtrl_prop.setFeature("door_density_kg_per_m3", actual_density)
                mtrl_prop.setFeature("door_thickness_m", actual_thickness)
                mtrl_prop.setFeature("door_conductivity_W_per_mK", actual_conductivity)
        
        # Store length per unit for sealing strips
        if door_bottom_seal_option != 'none':
            bottom_length = length_per_unit_dict.get(door_bottom_seal_option, 0.0)
            mtrl_prop.setFeature("door_bottom_seal_length_per_unit_m", bottom_length)
        
        if door_top_side_seal_option != 'none':
            top_side_length = length_per_unit_dict.get(door_top_side_seal_option, 0.0)
            mtrl_prop.setFeature("door_top_side_seal_length_per_unit_m", top_side_length)
        
        # Store standardized result fields and compatibility output fields
        results.setFeature("door_enhancement_total_additional_embodied_carbon_kg", total_embodied_carbon)
        results.setFeature("door_enhancement_total_additional_material_cost_$", 0.0)  # Placeholder
        results.setFeature("door_enhancement_total_additional_overhead_profit_cost_$", 0.0)  # Placeholder
        results.setFeature("door_enhancement_total_additional_labour_cost_$", 0.0)  # Placeholder
        results.setFeature("door_enhancement_total_embodied_carbon_kgCO2eq", total_embodied_carbon)

        # Store aggregate renovation quantities
        reno_detail.setFeature("total_renovated_door_area_m2", total_door_area_m2)
        reno_detail.setFeature("total_renovated_sealing_bottom_length_m", total_sealing_bottom_length_m)
        reno_detail.setFeature("total_renovated_sealing_side_length_m", total_sealing_side_length_m)
        # reno_detail.setFeature("total_doors_processed_count", len(sub_surfaces_to_change))
        # reno_detail.setFeature("total_doors_with_r_value_change_count", doors_with_r_value_change)
        
        # Store GWP values per functional unit (aggregate from all processed doors)
        # Calculate average GWP values across all doors
        gwp_per_unit_list = []
        gwp_per_m2_list = []
        gwp_per_m_bottom_list = []
        gwp_per_m_side_list = []
        
        for name in subsurface_dict.keys():
            # Door GWP per m2
            if 'door' in subsurface_dict[name] and 'gwp_per_m2' in subsurface_dict[name]['door']:
                gwp_m2 = subsurface_dict[name]['door']['gwp_per_m2']
                if gwp_m2 is not None and gwp_m2 > 0:
                    gwp_per_m2_list.append(gwp_m2)
            
            # Door GWP per unit
            if 'door' in subsurface_dict[name] and 'gwp_per_unit' in subsurface_dict[name]['door']:
                gwp_unit = subsurface_dict[name]['door']['gwp_per_unit']
                if gwp_unit is not None and gwp_unit > 0:
                    gwp_per_unit_list.append(gwp_unit)
            
            # Bottom seal GWP per m
            if 'door_bottom_sealing' in subsurface_dict[name] and 'gwp_per_m' in subsurface_dict[name]['door_bottom_sealing']:
                gwp_m = subsurface_dict[name]['door_bottom_sealing']['gwp_per_m']
                if gwp_m is not None and gwp_m > 0:
                    gwp_per_m_bottom_list.append(gwp_m)
            
            # Side seal GWP per m
            if 'door_side_sealing' in subsurface_dict[name] and 'gwp_per_m' in subsurface_dict[name]['door_side_sealing']:
                gwp_m = subsurface_dict[name]['door_side_sealing']['gwp_per_m']
                if gwp_m is not None and gwp_m > 0:
                    gwp_per_m_side_list.append(gwp_m)
        
        # Store average GWP values as factors
        if gwp_per_m2_list:
            factors.setFeature("door_gwp_per_m2_kgCO2eq", float(np.mean(gwp_per_m2_list)))
        if gwp_per_unit_list:
            factors.setFeature("door_gwp_per_unit_kgCO2eq", float(np.mean(gwp_per_unit_list)))
        if gwp_per_m_bottom_list:
            factors.setFeature("door_bottom_seal_gwp_per_m_kgCO2eq", float(np.mean(gwp_per_m_bottom_list)))
        if gwp_per_m_side_list:
            factors.setFeature("door_side_seal_gwp_per_m_kgCO2eq", float(np.mean(gwp_per_m_side_list)))
        
        # Store construction names and handles
        construction_names = []
        construction_handles = []
        for name in subsurface_dict.keys():
            if 'new_construction_name' in subsurface_dict[name]:
                construction_names.append(subsurface_dict[name]['new_construction_name'])
                # Get construction handle
                subsurface_obj = subsurface_dict[name]["subsurface object"]
                if subsurface_obj.construction().is_initialized():
                    construction = subsurface_obj.construction().get()
                    construction_handles.append(str(construction.handle()))
        
        if construction_names:
            basic_input.setFeature("door_enhancement_construction_names", ', '.join(construction_names))
            # basic_input.setFeature("door_enhancement_construction_handles", ', '.join(construction_handles))

        # # Separate summary AdditionalProperties on Facility for standardized cross-measure extraction
        # factors.setFeature("name", "Door_Enhancement")
        # factors.setFeature("total_additional_embodied_carbon_kgCO2", total_embodied_carbon)
        
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

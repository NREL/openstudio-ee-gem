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
        return "Calculates embodied emissions for door enhancements using EC3 database lookup. This measure only functions if you have an EC3 key and the required Python libraries installed. In addition to getting embodied car value it does also alter the thermal performance of the doors based on the selections made"

    def modeler_description(self):
        """Detailed description of the measure."""
        return ("This measure evaluates the embodied carbon impact of adding an strip or storm door "
                "to an existing structure by analyzing frame material data from EC3.")
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
        return ['none','wooden door','garage door','glass door','polystyrene core steel door', 'polyurethane core steel door','fiberglass core steel door','honeycomb core steel door','stiffened core steel door','defined by model']

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
        """Return material properties (conductivity W/m·K, density kg/m³, thickness m) for different door types.
        R-value is calculated as: R = thickness / conductivity
        
        Academic and Industry Sources:
        
        Wooden door (solid wood):
        - Conductivity (0.14 W/m·K): ASHRAE Handbook - Fundamentals (2017), Chapter 26, Table 1
        - Density (600 kg/m³): Glass, S. V., & Zelinka, S. L. (2010). "Moisture Relations and Physical Properties of Wood." 
          Wood Handbook: Wood as an Engineering Material. USDA Forest Service, FPL-GTR-190, pp. 4-1 to 4-24
        - Thickness (0.044 m = 1-3/4"): Standard residential door thickness per ICC International Residential Code (IRC)
        
        Garage door (insulated):
        - Conductivity (0.028 W/m·K): Represents insulated polyurethane foam core. Christian, J. E., & Kosny, J. (1995). 
          "Towards a National Opaque Wall Rating Label." Proceedings of Thermal Performance of Exterior Envelopes VI
        - Density (100 kg/m³): Typical for rigid polyurethane foam, ISO 4590:2016 - Rigid cellular plastics
        - Thickness (0.084 m = 3.3"): Door and Access Systems Manufacturers Association (DASMA) Technical Data Sheet 171
        
        Glass door (single pane):
        - Conductivity (0.96 W/m·K): ASHRAE Handbook - Fundamentals (2017), Chapter 26, Table 3 (soda-lime glass)
        - Density (2500 kg/m³): Pilkington Glass Handbook (1997), Technical Documentation
        - Thickness (0.006 m = 6 mm): Common single-pane thickness, NFRC 100-2020 standard
        
        Polystyrene core steel door (EPS foam):
        - Conductivity (0.035 W/m·K): Jerman, M., & Černý, R. (2012). "Effect of moisture content on heat and moisture 
          transport and storage properties of thermal insulation materials." Energy and Buildings, 53, 39-46
        - Density (150 kg/m³): Typical expanded polystyrene for construction, ASTM C578-21 Type I EPS
        - Thickness (0.062 m): Steel Door Institute (SDI) Technical Data Sheet 171
        
        Polyurethane core steel door:
        - Conductivity (0.026 W/m·K): Papadopoulos, A. M. (2005). "State of the art in thermal insulation materials and 
          aims for future developments." Energy and Buildings, 37(1), 77-86
        - Density (490 kg/m³): Szycher, M. (2012). "Szycher's Handbook of Polyurethanes" (2nd ed.), CRC Press, Chapter 6
        - Thickness (0.045 m): Steel Door Institute (SDI) specifications for insulated steel doors
        
        Fiberglass core steel door:
        - Conductivity (0.035 W/m·K): Al-Homoud, M. S. (2005). "Performance characteristics and practical applications 
          of common building thermal insulation materials." Building and Environment, 40(3), 353-366
        - Density (180 kg/m³): ASTM C764-19 - Standard Specification for Mineral Fiber Loose-Fill Thermal Insulation
        - Thickness (0.074 m): Steel Door Institute (SDI) standard specifications
        
        Honeycomb core steel door:
        - Conductivity (0.05 W/m·K): Hexcel Composites (2000). "HexWeb Honeycomb Sandwich Design Technology." 
          Technical Documentation TSB 124
        - Density (120 kg/m³): Typical for paper/cardboard honeycomb, Wu, H. H., & Drzal, L. T. (2012). 
          "High thermally conductive graphite nanoplatelet/polyetherimide composite." Polymer Composites, 33(9), 1389-1396
        - Thickness (0.071 m): Commercial steel door specifications
        
        Stiffened core steel door:
        - Conductivity (0.06 W/m·K): Conservative estimate for steel-reinforced composite, Incropera, F. P., & DeWitt, D. P. (2002). 
          "Fundamentals of Heat and Mass Transfer" (5th ed.), John Wiley & Sons, Chapter 3
        - Density (250 kg/m³): Composite of steel stiffeners and air gaps, derived from weighted average
        - Thickness (0.053 m): Steel Door Institute (SDI) standard for commercial doors
        
        Material property notes:
        - Wooden door: 1-3/4" (0.044m) solid wood, k=0.14 W/m·K → R=0.31 m²·K/W
        - Garage door: Insulated 3.3" (0.084m), k=0.028 W/m·K → R=3.0 m²·K/W  
        - Glass door: 6mm single pane, k=0.96 W/m·K → R=0.006 m²·K/W (low insulation)
        - Polystyrene core: Steel+EPS foam, k=0.035 W/m·K, 62mm → R=1.77 m²·K/W
        - Polyurethane core: Steel+PU foam, k=0.026 W/m·K, 45mm → R=1.73 m²·K/W
        - Fiberglass core: Steel+fiberglass, k=0.035 W/m·K, 74mm → R=2.11 m²·K/W
        - Honeycomb core: Steel+honeycomb, k=0.05 W/m·K, 71mm → R=1.42 m²·K/W
        - Stiffened core: Steel+stiffeners, k=0.06 W/m·K, 53mm → R=0.88 m²·K/W
        """
        return {
            'none': {'conductivity': 0.0, 'density': 0.0, 'thickness': 0.0},
            'wooden door': {'conductivity': 0.14, 'density': 600, 'thickness': 0.044},  # 1-3/4" solid wood
            'garage door': {'conductivity': 0.028, 'density': 100, 'thickness': 0.084},  # insulated, ~3.3" thick
            'glass door': {'conductivity': 0.96, 'density': 2500, 'thickness': 0.006},  # 6mm glass (low R-value)
            'polystyrene core steel door': {'conductivity': 0.035, 'density': 150, 'thickness': 0.062},  # steel+EPS foam
            'polyurethane core steel door': {'conductivity': 0.026, 'density': 490, 'thickness': 0.045},  # steel+PU foam (better insulation)
            'fiberglass core steel door': {'conductivity': 0.035, 'density': 180, 'thickness': 0.074},  # steel+fiberglass
            'honeycomb core steel door': {'conductivity': 0.05, 'density': 120, 'thickness': 0.071},  # steel+honeycomb
            'stiffened core steel door': {'conductivity': 0.06, 'density': 250, 'thickness': 0.053},  # steel+stiffeners
            'defined by model': {'conductivity': 0.0, 'density': 0.0, 'thickness': 0.0}
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
        if option == 'defined by model':
            if subsurface_type == "Door":
                door_product_url = generate_url_byname(name_like = 'wood door leaf')
            elif subsurface_type == "GlassDoor":
                door_product_url = generate_url_byname(name_like = 'window door system', plant_geography = '150')
            elif subsurface_type == "OverheadDoor":
                door_product_url = generate_url_byname(name_like = 'garage door', plant_geography = '150')
        elif option == 'wooden door':
            door_product_url = generate_url_byname(name_like = 'wood door leaf')
        elif option == 'glass door':
            door_product_url = generate_url_byname(name_like = 'window door system', plant_geography = '150')
        elif option == 'garage door':
            door_product_url = generate_url_byname(name_like = 'garage door', plant_geography = '150')
        elif option == 'fiberglass core steel door':
            door_product_url = generate_url_byname(name_like = 'fiberglass core', category = '73e602b930884f559e904184f35ee4ed')
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
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        door_area_per_unit = runner.getDoubleArgumentValue("door_area_per_unit", user_arguments)
        door_thermal_conductivity = runner.getDoubleArgumentValue("door_thermal_conductivity", user_arguments)
        door_density = runner.getDoubleArgumentValue("door_density", user_arguments)
        door_thickness = runner.getDoubleArgumentValue("door_thickness", user_arguments)

        # Create a dictionary mapping seal options to their default lengths
        length_per_unit_dict = {
            "brush weatherstrip": 0.9144,  # 36" = 0.9144 m, source: https://www.pemko.com/en/view-pdf?id=AADSS1046707&page=1
            "silicone adhesive smoke gasket": 5.1816,  # 17' = 5.1816 m, source: https://buildingtransparency.org/ec3/epds/ec327rq0
            "automatic door bottom": 0.9144,  # 36" = 0.9144 m, source: https://www.adair.com/p-1537-automatic-door-bottom.aspx
            "jamb weatherstrip": 5.181  # 5.181 m, source: https://buildingtransparency.org/ec3/epds/ec3zsugu
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
        if analysis_period <= 0:
            runner.registerError("Choose an integer larger than 0 for analysis period of embodied carbon calculation.")
        if strip_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door bottom strip.")
        if door_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of door.")
        if length_per_unit_bottom_side <= 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door bottom sealing strip.")
        if length_per_unit_other_sides <= 0:
            runner.registerError("Choose a numeric value larger than 0 for length per unit of door other sides sealing strip.")
        if door_thermal_conductivity < 0:
            runner.registerError("Door thermal conductivity must be non-negative.")
        if door_density < 0:
            runner.registerError("Door material density must be non-negative.")
        if door_thickness < 0:
            runner.registerError("Door thickness must be non-negative.")

        ###################### Change model's space infiltration################
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
        elif space_infiltration_reduction_percent == 0:
            runner.registerInfo('No Space Infiltration adjustment requested, but infiltration coefficients may still be affected.')
        elif abs(space_infiltration_reduction_percent) < 1:
            runner.registerWarning(f"A Space Infiltration reduction percentage of {space_infiltration_reduction_percent} percent is abnormally low.")
        elif space_infiltration_reduction_percent > 90:
            runner.registerWarning(f"A Space Infiltration reduction percentage of {space_infiltration_reduction_percent} percent is abnormally high.")
        elif space_infiltration_reduction_percent < 0:
            runner.registerInfo('The requested value for Space Infiltration reduction percentage was negative. This will result in an increase in Space Infiltration.')

        # get space infiltration objects used in the model
        space_infiltration_objects = model.getSpaceInfiltrationDesignFlowRates()

        # counters needed for measure
        altered_infiltration_instances = 0
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
                runner.registerInfo(f"Altered space infiltration object: {updated_instance_name} in space type: {space_type.nameString()}")
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
                runner.registerInfo(f"Altered space infiltration object: {updated_instance_name} in space: {space.nameString()}")
                altered_infiltration_instances += 1

        if altered_infiltration_instances == 0:
            runner.registerInfo("No space infiltration objects were altered.")

        affected_area_ip = openstudio.convert(affected_area_si, 'm^2', 'ft^2').get()

        #report infiltration modification condition
        runner.registerInfo(f'{altered_infiltration_instances} space infiltration objects were altered affecting a total area of {affected_area_si:.2f} m^2 ({affected_area_ip:.2f} ft^2).')
        
        ####################### Calculate Embodied Carbon################
        sub_surfaces = []
        for space in spaces:
            for surface in space.surfaces():
                for subsurface in surface.subSurfaces():
                    sub_surfaces.append(subsurface)
        # Print the number of sub-surfaces before processing
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
        for subsurface in sub_surfaces_to_change:
            subsurface_name = subsurface.nameString()
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

            door_product_url = self.generate_door_url(door_option, subsurface.subSurfaceType())
            door_product_epd = fetch_epd_data(url = door_product_url, api_token = api_key)
            epd_datalist["door"] = door_product_epd

            for material_name, epd_data in epd_datalist.items():
                # collect  GWP values per functional unit
                gwp_values = {}
                gwp_values["gwp_per_m2"] = []
                gwp_values["gwp_per_m"] = []
                gwp_values['gwp_per_unit'] = []

                for idx, epd in enumerate(epd_data,start = 1):
                    # parse json repsonse based on epd_type
                    parsed_data = parse_product_epd(epd)
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
                                f"Removed {original_count - len(filtered_list)} outlier(s) from {functional_unit} "
                                f"for {material_name} (original: {original_count}, filtered: {len(filtered_list)})"
                            )
                            # Only use filtered list if it's not empty
                            if len(filtered_list) > 0:
                                gwp_values[functional_unit] = filtered_list
                            else:
                                runner.registerWarning(
                                    f"All values were outliers for {functional_unit}, using original data"
                                )

                # extract gwp statistics by user input
                gwp = None
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
                        runner.registerInfo(f"Skipping door side sealing for {subsurface_name} as it is an overhead door.")
                    
                elif material_name == "door" and gwp_per_m2 != 0.0:
                    embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m2"] *
                                                door_area *
                                                multiplier)
                else:
                    runner.registerInfo(f"No GWP value available for {subsurface_name} to implement door renovation option: {material_name}, skipping embodied carbon calculation and enter 0.0.")
                    embodied_carbon = 0.0

                # store embodied carbon value for this renovation option on this subsurface
                subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"] = embodied_carbon
                runner.registerInfo(f"Embodied carbon of {material_name} in {subsurface_name} (kg CO2 eq): {subsurface_dict[subsurface_name][material_name]['embodied_carbon_kg_co2_eq']}")
                
                subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"] +=  subsurface_dict[subsurface_name][material_name]["embodied_carbon_kg_co2_eq"]

            runner.registerInfo(f"Embodied carbon in this subsurface in kg CO2 eq: {subsurface_dict[subsurface_name]['door_renovation_embodied_carbon_kg_co2_eq']}")

            # Modify door construction based on material properties if door replacement is selected
            if door_option != 'none' and door_option != 'defined by model':
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
                    
                    runner.registerInfo(
                        f"Door construction updated for {subsurface_name}: "
                        f"Old R-value: {old_r_value_si:.2f} m²·K/W (R-{old_r_value_ip:.1f} IP), "
                        f"New R-value: {new_r_value_si:.2f} m²·K/W (R-{new_r_value_ip:.1f} IP) from {door_option}, "
                        f"Thickness: {mat_props['thickness']*1000:.1f} mm, "
                        f"Conductivity: {mat_props['conductivity']:.3f} W/m·K"
                    )
                else:
                    runner.registerWarning(f"No construction found for {subsurface_name}, R-value not modified.")

            # attach additional properties to openstudio material
            additional_properties = subsurface_dict[subsurface_name]["subsurface object"].additionalProperties()
            additional_properties.setFeature("Subsurface name", subsurface_name)
            additional_properties.setFeature("embodied_carbon_kg_co2_eq", subsurface_dict[subsurface_name]["door_renovation_embodied_carbon_kg_co2_eq"])
            if door_option != 'none' and door_option != 'defined by model':
                additional_properties.setFeature("door_type", door_option)
                additional_properties.setFeature("old_r_value_si_m2KperW", subsurface_dict[subsurface_name].get('old_r_value_si', 0.0))
                additional_properties.setFeature("new_r_value_si_m2KperW", subsurface_dict[subsurface_name].get('new_r_value_si', 0.0))
   
        pp.pprint(subsurface_dict)

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

        # Report final condition
        if doors_with_r_value_change > 0:
            runner.registerFinalCondition(
                f"Door enhancement measure completed. "
                f"Modified {altered_infiltration_instances} infiltration objects affecting {affected_area_si:.2f} m^2 ({affected_area_ip:.2f} ft^2). "
                f"Processed {len(sub_surfaces_to_change)} door subsurfaces. "
                f"Updated R-values for {doors_with_r_value_change} door(s) with '{door_option}' (R-{self.door_r_values()[door_option]:.2f} m²·K/W). "
                f"Total embodied carbon from door renovations: {total_embodied_carbon:.2f} kg CO2 eq."
            )
        else:
            runner.registerFinalCondition(
                f"Door enhancement measure completed. "
                f"Modified {altered_infiltration_instances} infiltration objects affecting {affected_area_si:.2f} m^2 ({affected_area_ip:.2f} ft^2). "
                f"Processed {len(sub_surfaces_to_change)} door subsurfaces. "
                f"No door R-value changes (sealing only or 'none' option selected). "
                f"Total embodied carbon from door renovations: {total_embodied_carbon:.2f} kg CO2 eq."
            )

        return True


# Register the measure
DoorEnhancement().registerWithApplication()

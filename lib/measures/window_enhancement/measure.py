# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import typing
from pathlib import Path
from resources.EC3_lookup import fetch_epd_data
from resources.EC3_lookup import parse_gwp_data
from resources.EC3_lookup import generate_url
# from resources.EC3_lookup import material_category
import numpy as np

RESOURCES_DIR = Path(__file__).parent / "resources"

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
    def gwp_units():
        return ["per area (m^2)", "per mass (kg)", "per volume (m^3)"]
        
    @staticmethod
    def igu_options():
        return ["electrochromic","fire_resistant","laminated","low_emissivity","tempered"]
    
    @staticmethod
    def wf_options():
        return ["anodized","painted","thermally_improved"]

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
        igu_option = openstudio.measure.OSArgument.makeChoiceArgument("igu_option",igu_options_chs, True)
        igu_option.setDisplayName("IGU option") 
        igu_option.setDescription("Type of insulating glazing unit")
        #igu_option.setDefaultValue(None)
        args.append(igu_option)

        #make an argument for numebr of panes
        num_panes = openstudio.measure.OSArgument.makeIntegerArgument("number_of_panes", True)
        num_panes.setDisplayName("Number of Panes")
        num_panes.setDescription("Number of panes for glazing unit")
        args.append(num_panes)

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
        #wf_option.setDefaultValue(None)
        args.append(wf_option)

        # make an argument for cross-sectional area of window frame
        frame_cross_section_area = openstudio.measure.OSArgument.makeDoubleArgument("frame_cross_section_area", True)
        frame_cross_section_area.setDisplayName("Frame Cross Section Area (m²)")
        frame_cross_section_area.setDescription("Cross-sectional area of the IGU frame in square meters.")
        frame_cross_section_area.setDefaultValue(0.0025)
        args.append(frame_cross_section_area)

        igu_thickness = openstudio.measure.OSArgument.makeDoubleArgument("igu_thickness", True)
        igu_thickness.setDisplayName("Thickness of Insulating Glazing Unit (m)")
        igu_thickness.setDescription("Thickness of Insulating Glazing Unit (m).")
        igu_thickness.setDefaultValue(0.0)
        args.append(igu_thickness)

        # make an argument for selcting which gwp statistic to use for embodied carbon calculation
        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistics_chs.append("single_value")
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or single value) of returned GWP value")
        gwp_statistic.setDefaultValue("single_value")
        args.append(gwp_statistic)

        # make an argument for selecting which gwp unit to use for embodied carbon calculation
        gwp_units_chs = openstudio.StringVector()
        for unit in self.gwp_units():
            gwp_units_chs.append(unit)
        gwp_unit = openstudio.measure.OSArgument.makeChoiceArgument("gwp_unit",gwp_units_chs, True)
        gwp_unit.setDisplayName("GWP Unit") 
        gwp_unit.setDescription("Unit type (per volume or area or mass) of returned GWP value")
        gwp_unit.setDefaultValue("per volume (m^3)")
        args.append(gwp_unit)

        # make an argument for total embodied carbon (TEC) of whole construction/building
        total_embodied_carbon = openstudio.measure.OSArgument.makeDoubleArgument("total_embodied_carbon", True)
        total_embodied_carbon.setDisplayName("Total Embodeid Carbon of Building/Building Assembly")
        total_embodied_carbon.setDescription("Total GWP or embodied carbon intensity of the building (assembly) in kg CO2 eq.")
        total_embodied_carbon.setDefaultValue(0.0)
        args.append(total_embodied_carbon)

        return args
    
    # def calculate_perimeter(self, sub_surface):
    #     """Calculate the perimeter of the window from its vertices."""
    #     vertices = sub_surface.vertices()
    #     if len(vertices) < 2:
    #         return 0.0

    #     perimeter = 0.0
    #     num_vertices = len(vertices)

    #     for i in range(num_vertices):
    #         v1 = vertices[i]
    #         v2 = vertices[(i + 1) % num_vertices]  # Wrap around to the first vertex
    #         edge_vector = v2 - v1  # Subtract two Point3d objects to get Vector3d
    #         edge_length = edge_vector.length()  # Use length() to get the magnitude of the vector
    #         perimeter += edge_length

    #     return perimeter

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
        #igu_component_name = runner.getStringArgumentValue("igu_component_name", user_arguments)
        frame_cross_section_area = runner.getDoubleArgumentValue("frame_cross_section_area", user_arguments)
        igu_thickness = runner.getDoubleArgumentValue("igu_thickness",user_arguments)
        num_panes = runner.getIntegerArgumentValue("number_of_panes", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        gwp_unit = runner.getStringArgumentValue("gwp_unit", user_arguments)
        igu_option = runner.getStringArgumentValue("igu_option", user_arguments)
        wf_option = runner.getStringArgumentValue("wf_option", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        igu_lifetime = runner.getIntegerArgumentValue("igu_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgumentValue("wf_lifetime",user_arguments)
        total_embodied_carbon = runner.getDoubleArgumentValue("total_embodied_carbon",user_arguments)

        # Debug: Print all user arguments received
        runner.registerInfo(f"User Arguments: {user_arguments}")
        for arg_name, arg_value in user_arguments.items():
            print(f"user_argument: {arg_name} = {arg_value.valueAsString()}")
        
        # Check if numeric values are reasonable
        if num_panes == 0 or num_panes > 2:
            runner.registerError("Choose an integer from {1,2,3} for the number of panes of IGU.")
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
        # List storing glazing materials
        glazing_materials = []
        building_material_names = []
        # loop through sub surfaces
        for subsurface in sub_surfaces:
            sub_surface_name = subsurface.nameString()
            # we already checked the exmaple model and identified the surface type: FixedWinodow
            if subsurface.outsideBoundaryCondition() == "Outdoors" and subsurface.subSurfaceType() in ["FixedWindow","OperableWindow"]:
                # append the subsurface object into list
                sub_surfaces_to_change.append(subsurface) 
                # examine if this subsurface construction exist
                if subsurface.construction().is_initialized():
                    # get the construction of the subsurface object
                    sub_surface_const = subsurface.construction().get()
                    # examine if construction is LayeredConstruction type
                    if sub_surface_const.to_LayeredConstruction().is_initialized():
                        layered_construction = sub_surface_const.to_LayeredConstruction().get()
                        runner.registerInfo(f"Construction of {sub_surface_name} is a LayeredConstruction.")
                        # loop through each material in layered construction
                        for i in range(layered_construction.numLayers()):
                            material = layered_construction.getLayer(i)
                            glazing_materials.append(material)
                            building_material_names.append(material.nameString())
                            runner.registerInfo(f"Layer {i+1}: {material.nameString()}")
                    else:
                        runner.registerWarning(f"Construction of Sub-surface {sub_surface_name} is not a LayeredConstruction.")
                        continue # exit loop becasue construction is not layered type
                else:
                    runner.registerWarning(f"Sub-surface {sub_surface_name} has no construction assigned, skipping.")
                    continue # exit loop becasue sub_surface_name == None

                # record that the measure is processing qualified window construction
                runner.registerInfo(f"Processing window: {sub_surface_name} with construction of Sub-surface {sub_surface_name}")
            
            else:# if sub_surface.outsideBoundaryCondition() != "Outdoors" or sub_surface.subSurfaceType() not in ["FixedWindow", "OperableWindow"]:
                runner.registerInfo(f"Skipping non-window surface: {sub_surface_name}")
                continue

        # Window frame calculations:
        for subsurface in sub_surfaces_to_change: # already checked the model: there is only one, fixed window
            if subsurface.windowPropertyFrameAndDivider().is_initialized(): # check if frame_and_divider exist in selected subsurface
                frame = subsurface.windowPropertyFrameAndDivider().get()
                frame_name = frame.nameString()
                building_material_names.append(frame_name)
                frame_width = frame.frameWidth()
                runner.registerInfo(f"SubSurface: {subsurface.nameString()}'s Frame: {frame_name}, Frame Width: {frame_width} m")
                window_area = frame_width*frame_width
                frame_perimeter = frame_width*4
                runner.registerInfo(f"window area: {window_area}; Window perimeter: {frame_perimeter}")
            else:
                runner.registerInfo("Frame and divider doesn't exist in selected subsurface")
        
        runner.registerInfo(f"number of layers for Subsurface 2: {len(glazing_materials)}")

        for material in glazing_materials:
            if material.to_OpaqueMaterial().is_initialized():
                opaque_material = material.to_OpaqueMaterial().get()
                runner.registerInfo(f"Material: {opaque_material.nameString()}, Thickness: {opaque_material.thickness()} m")
                igu_thickness += opaque_material.thickness()
            else:
                igu_thickness = 0.006 # assign a value if the window construction has no thickness
                runner.registerInfo(f"Material: {material.nameString()} is not an opaque material and has no thickness.")
        
        # print name of glazing materials
        for name in building_material_names:
            runner.registerInfo(f"Recorded building materials: {name}") 

        # caculate total igu volume
        total_igu_volume = igu_thickness * window_area
        total_window_frame_volume = frame_cross_section_area * frame_perimeter
        
        # Embodied carbon calculations
        #building_materials = ["InsulatingGlazingUnits","AluminiumExtrusions"]
        # dictionary storing properties of each building materials
        try:
            material_dict = {}
            for name in building_material_names:
                runner.registerInfo(f"Processing {name}")
                material_dict[name] = {}
                material_dict[name]['volume'] = None
                material_dict[name]['area'] = None
                material_dict[name]['mass'] = None
                material_dict[name]['perimeter'] = None
                material_dict[name]['embodied_carbon_intensity'] = None
                material_dict[name]['embodied_carbon'] = None
                if 'Glazing' in name:
                    material_dict[name]['object'] = layered_construction
                    material_dict[name]['api_term'] = 'InsulatingGlazingUnits'
                    material_dict[name]['volume'] = total_igu_volume
                    material_dict[name]['area'] = window_area
                    material_dict[name]['lifetime'] = igu_lifetime
                elif 'Frame' in name:
                    material_dict[name]['object'] = frame
                    material_dict[name]['api_term'] = 'AluminiumExtrusions'
                    material_dict[name]['volume'] = total_window_frame_volume
                    material_dict[name]['lifetime'] = wf_lifetime
                    material_dict[name]['perimeter'] = frame_perimeter

            for name in building_material_names:
                if igu_option and material_dict[name]['api_term'] == "InsulatingGlazingUnits":
                    product_url = generate_url(material_name = material_dict[name]['api_term'], option = igu_option, glass_panes = num_panes)
                elif wf_option and material_dict[name]['api_term'] == "AluminiumExtrusions":
                    product_url = generate_url(material_name = material_dict[name]['api_term']) # only 2 EPD available, stop using wf_option 
                else:
                    product_url = generate_url(material_name = material_dict[name]['api_term'])

                epd_data = fetch_epd_data(product_url)
                runner.registerInfo(f"Number of EPDs: {len(epd_data)}")

                if len(epd_data) == 0:
                    runner.registerError("No EPD returned from this API call")
                    #let user fill in the number then
                elif len(epd_data) == 1:
                    runner.registerInfo("Only one EPD available for this material category")
                    gwp_statistic = "single_value"
                elif gwp_statistic == "single_value":
                    runner.registerWarning("Since multiple EPD returned, use a single value is not recommended.")
                
                gwp_values = []
                for idx, epd in enumerate(epd_data,start = 1):
                    parsed_data = parse_gwp_data(epd)
                    if gwp_unit == "per area (m^2)" and parsed_data["gwp_per_unit_area (kg CO2 eq/m2)"] != 0.0:
                        gwp_value = parsed_data["gwp_per_unit_area (kg CO2 eq/m2)"]
                        gwp_values.append(float(gwp_value))
                        runner.registerInfo(f"gwp_per_unit_area (kg CO2 eq/m2):{gwp_value}")
                    elif gwp_unit == "per mass (kg)" and parsed_data["gwp_per_unit_mass (kg CO2 eq/kg)"] != 0.0:
                        gwp_value = parsed_data["gwp_per_unit_mass (kg CO2 eq/kg)"]
                        gwp_values.append(float(gwp_value))
                        runner.registerInfo(f"gwp_per_unit_mass (kg CO2 eq/kg):{gwp_value}")
                    elif gwp_unit == "per volume (m^3)" and parsed_data["gwp_per_unit_volume (kg CO2 eq/m3)"] != 0.0:
                        gwp_value = parsed_data["gwp_per_unit_volume (kg CO2 eq/m3)"]
                        gwp_values.append(float(gwp_value))
                        runner.registerInfo(f"gwp_per_unit_volume (kg CO2 eq/m3):{gwp_value}")
                if len(gwp_values) == 0:
                    runner.registerInfo("No non-zero values returned from selected functional unit")
                runner.registerInfo(f"Number of non-zero values returned from selected functional unit:{len(gwp_values)}")

                if gwp_statistic == "minimum":
                    gwp = np.min(gwp_values)
                elif gwp_statistic == "maximum":
                    gwp = np.max(gwp_values)
                elif gwp_statistic == "mean":
                    gwp = np.mean(gwp_values)
                elif gwp_statistic == "median":
                    gwp = np.median(gwp_values)
                else:
                    gwp = gwp_values[0]
                #store embodied carbon intensity of the material
                material_dict[name]["embodied_carbon_intensity"] = gwp
                runner.registerInfo(f"{gwp_statistic} GWP of {name} {gwp_unit}: {gwp:.2f} kg CO2 eq.")
                #calculate total embodied carbon from the material and its product lifetime
                if analysis_period <= material_dict[name]["lifetime"]:
                    material_dict[name]["embodied_carbon"] = gwp * material_dict[name]["volume"]
                else:
                    material_dict[name]["embodied_carbon"] = gwp * material_dict[name]["volume"] * np.ceil(analysis_period/material_dict[name]["lifetime"])
                runner.registerInfo(f"total embodied carbon of {name}: {material_dict[name]['embodied_carbon']:.2f} kg CO2 eq.")
                
                #total embodied carbon calcualted by adding up embodeid carbon from each material flow
                total_embodied_carbon += material_dict[name]["embodied_carbon"]

                # attach additional properties to openstudio material
                additional_properties = material_dict[name]['object'].additionalProperties()
                additional_properties.setFeature("Material name", name)
                additional_properties.setFeature("Embodied carbon", material_dict[name]["embodied_carbon"])

            runner.registerInfo(f"--------------------------------------Summary-----------------------------------")    
            runner.registerInfo(f"Frame cross-sectional area (given value): {frame_cross_section_area} m")
            runner.registerInfo(f"Frame width: {frame_width} m")
            runner.registerInfo(f"IGU Thickness (given value): {igu_thickness} m")
            runner.registerInfo(f"IGU volume: {total_igu_volume:.3f} m3")
            runner.registerInfo(f"Window area: {window_area:.3f} m2")
            runner.registerInfo(f"Frame perimeter: {frame_perimeter:.3f} m")
            runner.registerInfo(f"Window frame volume: {total_window_frame_volume:.3f} m3")
            runner.registerInfo(f"Total GWP of window construction: {total_embodied_carbon} kg CO2 eq.")

        except Exception as e:
            runner.registerError(f"Error fetching GWP value: {e}")
            return False
        
        building = model.getBuilding()
        additional_properties = building.additionalProperties()
        additional_properties.setName("Dummy AdditionalProperties")
        additional_properties.setFeature("Embodied Carbon [kg]:", "10")

        # additional_props = model.AdditionalProperties(model)
        # additional_props.setName("Dummy AdditionalProperties")
        # additional_props.setFeature("Embodied Carbon [kg]", "10")

        # output_var = openstudio.model.OutputVariable("WindowEnhancement:EmbodiedCarbon", model)
        # output_var.setKeyValue(igu_component_name)
        # output_var.setReportingFrequency("Monthly")
        # output_var.setName(f"Embodied Carbon for {igu_component_name}")

        return True

# Register the measure
WindowEnhancement().registerWithApplication()

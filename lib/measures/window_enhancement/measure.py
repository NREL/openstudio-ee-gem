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

        # igu_component_name = openstudio.measure.OSArgument.makeStringArgument("igu_component_name", True)
        # igu_component_name.setDisplayName("IGU Component Name")
        # igu_component_name.setDescription("Name of the IGU component to add.")
        # args.append(igu_component_name)

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

        # # we can replace this argument with the choice argument gwp_unit
        # declared_unit = openstudio.measure.OSArgument.makeStringArgument("declared_unit", True)
        # declared_unit.setDisplayName("Declared Unit for GWP")
        # declared_unit.setDescription("Unit in which the global warming potential (GWP) is measured (e.g., kgCO2e/m3).")
        # args.append(declared_unit)

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

        # make an argument for total embodied carbon (TEC)
        total_embodied_carbon = openstudio.measure.OSArgument.makeDoubleArgument("total_embodied_carbon", True)
        total_embodied_carbon.setDisplayName("Total Embodeid Carbon of Building/Building Assembly")
        total_embodied_carbon.setDescription("Total GWP or embodied carbon intensity of the building (assembly) in kg CO2 eq.")
        total_embodied_carbon.setDefaultValue(0.0)
        args.append(total_embodied_carbon)

        return args

    def calculate_perimeter(self, sub_surface):
        """Calculate the perimeter of the window from its vertices."""
        vertices = sub_surface.vertices()
        if len(vertices) < 2:
            return 0.0

        perimeter = 0.0
        num_vertices = len(vertices)

        for i in range(num_vertices):
            v1 = vertices[i]
            v2 = vertices[(i + 1) % num_vertices]  # Wrap around to the first vertex
            edge_vector = v2 - v1  # Subtract two Point3d objects to get Vector3d
            edge_length = edge_vector.length()  # Use length() to get the magnitude of the vector
            perimeter += edge_length

        return perimeter

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
        # List storing window materials
        window_materials = []

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
                            window_materials.append(material)
                            runner.registerInfo(f"Layer {i+1}: {material.nameString()}")
                            # for material in layers:
                            #     window_materials.append(material)
                            #     runner.registerInfo(f"Layer name: {material.nameString()} - Class: {material.iddObject().name()}")
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

        # Window material calculations:
        # get area in m^2 from window construction
        # refer to: openstudio-ee-gem/lib/measures/ReplaceExteriorWindowConstruction/measure.rb
        for subsurface in sub_surfaces_to_change: # already checked the model: there is only one, fixed window
            construction = subsurface.construction().get()
            if construction.isFenestration():
            #window_area = openstudio.convert(openstudio.Quantity(construction.getNetArea(), openstudio.createUnit('m^2').get())).get().value()
                window_area = subsurface.netArea()
                runner.registerInfo(f"window area: {window_area}")
            else:
                runner.registerInfo("not a fenestration")
            window_perimeter = self.calculate_perimeter(subsurface)
            runner.registerInfo(f"Calculated surface perimeter: {window_perimeter}")
        
        runner.registerInfo(f"number of layers for window construction:{len(window_materials)}")

        for material in window_materials:
            if material.to_OpaqueMaterial().is_initialized():
                opaque_material = material.to_OpaqueMaterial().get()
                runner.registerInfo(f"Material: {opaque_material.nameString()}, Thickness: {opaque_material.thickness()} m")
                igu_thickness += opaque_material.thickness()
            else:
                igu_thickness = 0.003 # assign a value if the window construction has no thickness
                runner.registerInfo(f"Material: {material.nameString()} is not an opaque material and has no thickness.")

        #caculate total igu volume
        total_igu_volume = igu_thickness * window_area
        total_window_frame_volume = frame_cross_section_area * window_perimeter
        
        ###new edits###
        # Embodied carbon calculations
        building_materials = ["InsulatingGlazingUnits","AluminiumExtrusions"]
        # dictionary storing total volume of building materials
        material_properties = {
        "InsulatingGlazingUnits": {
            "volume": total_igu_volume,
            "area": None,
            "mass": None,
            "ECI":None,
            "lifetime": igu_lifetime,
            "EC":None},
        "AluminiumExtrusions":{
            "volume": total_window_frame_volume,
            "area": None,
            "mass": None,
            "ECI":None,
            "lifetime":wf_lifetime,
            "EC":None},
        }
        # double object storing total embodied carbon in kg CO2 eq
        total_embodied_carbon = 0.0
        try:
            for material in building_materials:
                runner.registerInfo(f"Processing {material}")
                if igu_option and material == "InsulatingGlazingUnits":
                    product_url = generate_url(material_name=material,option=igu_option,glass_panes=num_panes)
                if wf_option and material == "AluminiumExtrusions":
                    product_url = generate_url(material_name=material)
                else:
                    product_url = generate_url(material_name=material)
                epd_data = fetch_epd_data(product_url)
                runner.registerInfo(f"Number of EPDs: {len(epd_data)}")

                if len(epd_data) == 0:
                    runner.registerError("No EPD returned from this API call")
                    #let user fill in the number then
                if len(epd_data) == 1:
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
                material_properties[material]["ECI"] = gwp
                runner.registerInfo(f"{gwp_statistic} GWP of {material} {gwp_unit}: {gwp:.2f} kg CO2 eq.")
                #calculate total embodied carbon from the material and its product lifetime
                if analysis_period <= material_properties[material]["lifetime"]:
                    material_properties[material]["EC"] = gwp * material_properties[material]["volume"]
                else:
                    material_properties[material]["EC"] = gwp * material_properties[material]["volume"] * np.ceil(analysis_period/material_properties[material]["lifetime"])
                runner.registerInfo(f"total GWP of {material}: {material_properties[material]['EC']:.2f} kg CO2 eq.")

                #total embodied carbon calcualted by adding up embodeid carbon from each material flow
                total_embodied_carbon += material_properties[material]["EC"]
            runner.registerInfo(f"-------------------------------------------------------------------------")    
            runner.registerInfo(f"Frame cross-sectional area: {frame_cross_section_area} m")
            runner.registerInfo(f"IGU Thickness: {igu_thickness} m")
            runner.registerInfo(f"IGU volume: {total_igu_volume:.3f} m3")
            runner.registerInfo(f"Window frame volume: {total_window_frame_volume:.3f} m3")
            runner.registerInfo(f"total GWP of window construction: {total_embodied_carbon} kg CO2 eq.")
        except Exception as e:
            runner.registerError(f"Error fetching GWP value: {e}")
            return False
        ###end###
        '''
            # the following can be deleted if new edits run successfully    
            wframe_data = fetch_epd_data(URLS["wframe"])
            igu_data = fetch_epd_data(URLS["igu"])
            runner.registerInfo(f"Number of EPDs for window frame: {len(wframe_data)}")
            runner.registerInfo(f"Number of EPDs for insulated glass unit: {len(igu_data)}")
            wframe_gwp_per_volume = []
            igu_gwp_per_volume = []
            for idx, epd in enumerate(wframe_data, start=1):
                parsed_wframe_data = parse_gwp_data(epd)
                wframe_gwp_per_volume.append(parsed_wframe_data["gwp_per_unit_volume"])
            for idx, epd in enumerate(igu_data, start=1):
                parsed_igu_data = parse_gwp_data(epd)
                igu_gwp_per_volume.append(parsed_igu_data["gwp_per_unit_volume"])

            # Temporarily, we use mean value for calculation; in the future, we allow user to pick which EPD to use
            wframe_mean_gwp_per_volume = np.mean(wframe_gwp_per_volume)
            igu_mean_gwp_per_volume = np.mean(igu_gwp_per_volume)
            # TBD: need to report the min and max to give a sense of the gwp range.
            runner.registerInfo(f"Mean GWP of window frame per volume: {wframe_mean_gwp_per_volume:.2f} kgCO2e/m3.")
            runner.registerInfo(f"Mean GWP of insulated glass unit per volume: {igu_mean_gwp_per_volume:.2f} kgCO2e/m3.")
            
        except Exception as e:
            runner.registerError(f"Error calculating GWP per volume: {e}")
            return False
            
        # Frame embodied carbon totals
        # frame_embodied_carbon = total_window_frame_volume * wframe_mean_gwp_per_volume
        runner.registerInfo(f"Total embodied carbon for {igu_component_name}: {frame_embodied_carbon:.2f} kgCO2e.")
        '''
        # TBD: IGU Calculations: need to extract IGU thicknesses, multiply by area, and lookup associated GWP
        
        building = model.getBuilding()
        additional_properties = building.additionalProperties()
        additional_properties.setFeature("Embodied Carbon [kg]:", "10")

        # output_var = openstudio.model.OutputVariable("WindowEnhancement:EmbodiedCarbon", model)
        # output_var.setKeyValue(igu_component_name)
        # output_var.setReportingFrequency("Monthly")
        # output_var.setName(f"Embodied Carbon for {igu_component_name}")

        return True

# Register the measure
WindowEnhancement().registerWithApplication()

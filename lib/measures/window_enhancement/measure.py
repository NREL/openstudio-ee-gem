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
from resources.EC3_lookup import material_category
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
    
    ###new edits###
    def gwp_statistics():
        gwp_statistics = ["minimum","maximum","mean","median"]
        return gwp_statistics
    
    def gwp_units():
        gwp_units = ["per area (m^2)","per mass (kg)","per volume (m^3)"]
        return gwp_units
    
    def igu_options():
        igu_options = ["electrochromic","fire_resistant","laminated","low_emissivity","tempered"]
        return igu_options
    
    def wf_options():
        wf_options = ["anodized","painted","thermally_improved"]
    ###end###

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define the arguments that user will input."""
        args = openstudio.measure.OSArgumentVector()

        #make an argument for analysis period
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        igu_component_name = openstudio.measure.OSArgument.makeStringArgument("igu_component_name", True)
        igu_component_name.setDisplayName("IGU Component Name")
        igu_component_name.setDescription("Name of the IGU component to add.")
        args.append(igu_component_name)

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

        # make an argument for cross-sectional area of window frame
        frame_cross_section_area = openstudio.measure.OSArgument.makeDoubleArgument("frame_cross_section_area", True)
        frame_cross_section_area.setDisplayName("Frame Cross Section Area (m²)")
        frame_cross_section_area.setDescription("Cross-sectional area of the IGU frame in square meters.")
        args.append(frame_cross_section_area)

        # we can replace this argument with the choice argument gwp_unit
        declared_unit = openstudio.measure.OSArgument.makeStringArgument("declared_unit", True)
        declared_unit.setDisplayName("Declared Unit for GWP")
        declared_unit.setDescription("Unit in which the global warming potential (GWP) is measured (e.g., kgCO2e/m3).")
        args.append(declared_unit)

        ### new edits ###
        # make an argument for selcting which gwp statistic to use for embodied carbon calculation
        gwp_statistics_chs = openstudio.StringVector.new()
        gwp_statistics = gwp_statistics()
        for gwp_statistic in gwp_statistics:
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistics_chs.append("single_value")
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or single value) of returned GWP value")
        gwp_statistic.setDefaultValue("single_value")
        args.append(gwp_statistic)

        #make an argument for selecting which gwp unit to use for embodied carbon calculation
        gwp_units_chs = openstudio.StringVector.new()
        gwp_units = gwp_units()
        for gwp_unit in gwp_units:
            gwp_units_chs.append(gwp_unit)
        gwp_unit = openstudio.measure.OSArgument.makeChoiceArgument("gwp_unit",gwp_units_chs, True)
        gwp_unit.setDisplayName("GWP Unit") 
        gwp_unit.setDescription("Unit type (per volume or area or mass) of returned GWP value")
        gwp_unit.setDefaultValue("per volume")
        args.append(gwp_statistic)

        #make an argument for igu options for filtering EPDs of igu
        igu_options_chs = openstudio.StringVector.new()
        igu_options = igu_options()
        for igu_option in igu_options:
            igu_options_chs.append(igu_option)
        igu_option = openstudio.measure.OSArgument.makeChoiceArgument("igu_option",igu_options_chs, True)
        igu_option.setDisplayName("IGU option") 
        igu_option.setDescription("Type of insulating glazing unit")
        igu_option.setDefaultValue(None)
        args.append(igu_option)

        #make an argument for numebr of panes
        num_panes = openstudio.measure.OSArgument.makeIntegerArgument("number_of_panes", True)
        num_panes.setDisplayName("Number of Panes")
        num_panes.setDescription("Number of panes for glazing unit")
        args.append(num_panes)

        #make an argument for window frame options for filtering EPDs 
        wf_options_chs = openstudio.StringVector.new()
        wf_options = wf_options()
        for wf_option in wf_options:
            wf_options_chs.append(wf_option)
        wf_option = openstudio.measure.OSArgument.makeChoiceArgument("wf_option",wf_options_chs, True)
        wf_option.setDisplayName("Window frame option") 
        wf_option.setDescription("Type of aluminum extrusion")
        wf_option.setDefaultValue(None)
        args.append(wf_option)
        ### end ###

        #make an argument for total embodied carbon (TEC)
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
        igu_component_name = runner.getStringArgumentValue("igu_component_name", user_arguments)
        frame_cross_section_area = runner.getDoubleArgumentValue("frame_cross_section_area", user_arguments)
        num_panes = runner.getIntegerArgumentValue("num_of_panes", user_arguments)
        gwp_statistic = runner.getChoiceArgumentValue("gwp_statistic", user_arguments)
        gwp_unit = runner.getChoiceArgumentValue("gwp_unit", user_arguments)
        igu_option = runner.getChoiceArgumentValue("igu_option", user_arguments)
        wf_option = runner.getChoiceArgumentValue("wf_option", user_arguments)
        analysis_period = runner.getIntegerArgument("analysis_period",user_arguments)
        igu_lifetime = runner.getIntegerArgument("igu_lifetime",user_arguments)
        wf_lifetime = runner.getIntegerArgument("wf_lifetime",user_arguments)
        total_embodied_carbon=runner.getDoubleArgument("total_embodied_carbon",user_arguments)

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

        # Calcualte volume of window frame
        total_window_frame_volume = 0.0
        ###new edits###
        total_igu_volume = 0.0
        ###end###
        for sub_surface in sub_surfaces:
            sub_surface_name = sub_surface.nameString()
            construction = sub_surface.construction()

            if construction.is_initialized:
                construction_name = construction.get().nameString()
                if isinstance(construction.get(), openstudio.model.LayeredConstruction):
                    layered_construction = construction.get().to_LayeredConstruction().get()
                else:
                    runner.registerWarning(f"Sub-surface '{sub_surface_name}' does not have a layered construction.")
                    continue

                if layered_construction.is_initialized():
                    layers = layered_construction.get().layers()
                    for layer in layers:
                        runner.registerInfo(f"Layer name: {layer.nameString()} - Class: {layer.iddObject().name()}")
                else:
                    runner.registerWarning(f"Construction {construction.get().nameString()} is not a LayeredConstruction.")

                runner.registerInfo(f"Processing window: {sub_surface_name} with construction: {construction_name}")
            else:
                runner.registerWarning(f"Sub-surface {sub_surface_name} has no construction assigned, skipping.")
                continue

            if sub_surface.outsideBoundaryCondition() != "Outdoors" or sub_surface.subSurfaceType() not in ["FixedWindow", "OperableWindow"]:
                runner.registerInfo(f"Skipping non-window surface: {sub_surface_name}")
                continue

            # Frame calculations: 
            perimeter = self.calculate_perimeter(sub_surface)
            window_frame_volume = frame_cross_section_area * perimeter
            total_window_frame_volume += window_frame_volume
            runner.registerInfo(f"Window {sub_surface_name} frame volume: {window_frame_volume:.3f} m3")

        if total_window_frame_volume == 0:
            runner.registerWarning("No valid windows found. Exiting measure.")
            return False
        
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
                
                if igu_option & material == "InsulatingGlazingUnits":
                    product_url = generate_url(material_name=material,option=igu_option,glass_panes=num_panes)
                if wf_option & material == "AluminiumExtrusions":
                    product_url = generate_url(material_name=material,option=wf_option)
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
                    if gwp_unit == "per area (m^2)" and material_properties[material]["area"] != None:
                        gwp_values.append(parsed_data["gwp_per_unit_area (kg CO2 eq/m2)"])
                    if gwp_unit == "per mass (kg)" and material_properties[material]["mass"] != None:
                        gwp_values.append(parsed_data["gwp_per_unit_mass (kg CO2 eq/kg)"])
                    if gwp_unit == "per volume (m^3)" and material_properties[material]["volume"] != None:
                        gwp_values.append(parsed_data["gwp_per_unit_volume (kg CO2 eq/m3)"])

                if gwp_statistic == "minimum":
                    gwp = np.min(gwp_values)
                if gwp_statistic == "maximum":
                    gwp = np.max(gwp_values)
                if gwp_statistic == "mean":
                    gwp = np.mean(gwp_values)
                if gwp_statistic == "median":
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
                runner.registerInfo(f"total GWP of {material}: {material_properties[material]["EC"]:.2f} kg CO2 eq.")

                #total embodied carbon calcualted by adding up embodeid carbon from each material flow
                total_embodied_carbon += material_properties[material]["EC"]
            
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
        additional_properties.setFeature(f"EmbodiedCarbon_{igu_component_name}", frame_embodied_carbon)

        output_var = openstudio.model.OutputVariable("WindowEnhancement:EmbodiedCarbon", model)
        output_var.setKeyValue(igu_component_name)
        output_var.setReportingFrequency("Monthly")
        output_var.setName(f"Embodied Carbon for {igu_component_name}")

        return True

# Register the measure
WindowEnhancement().registerWithApplication()

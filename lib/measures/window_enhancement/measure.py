# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import typing
from pathlib import Path
from resources.EC3_lookup import calculate_gwp_per_volume  # Ensure this function exists and works correctly

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

    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """Define user arguments."""
        args = openstudio.measure.OSArgumentVector()

        igu_component_name = openstudio.measure.OSArgument.makeStringArgument("igu_component_name", True)
        igu_component_name.setDisplayName("IGU Component Name")
        igu_component_name.setDescription("Name of the IGU component to add.")
        args.append(igu_component_name)

        frame_cross_section_area = openstudio.measure.OSArgument.makeDoubleArgument("frame_cross_section_area", True)
        frame_cross_section_area.setDisplayName("Frame Cross Section Area (m²)")
        frame_cross_section_area.setDescription("Cross-sectional area of the IGU frame in square meters.")
        args.append(frame_cross_section_area)

        frame_perimeter_length = openstudio.measure.OSArgument.makeDoubleArgument("frame_perimeter_length", True)
        frame_perimeter_length.setDisplayName("Frame Perimeter Length (m)")
        frame_perimeter_length.setDescription("Perimeter length of the IGU frame in meters.")
        args.append(frame_perimeter_length)

        declared_unit = openstudio.measure.OSArgument.makeStringArgument("declared_unit", True)
        declared_unit.setDisplayName("Declared Unit for GWP")
        declared_unit.setDescription("Unit in which the global warming potential (GWP) is measured (e.g., kgCO2e/m3).")
        args.append(declared_unit)

        gwp = openstudio.measure.OSArgument.makeDoubleArgument("gwp", True)
        gwp.setDisplayName("Global Warming Potential (GWP) Value")
        gwp.setDescription("Embodied carbon value from EC3 database in kgCO2e per declared unit.")
        args.append(gwp)

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
            edge_length = v1.distance(v2)
            perimeter += edge_length

        return perimeter

    def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
        """Execute the measure."""
        runner.registerInfo("Starting WindowEnhancement measure execution.")

        # Check if model exists
        if not model:
            runner.registerError("Model is None. Exiting measure.")
            return False

        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False
        
        # Debug: Print all user arguments received
        runner.registerInfo(f"User Arguments: {user_arguments}")

        for arg_name, arg_value in user_arguments.items():
            print(f"user_argument: {arg_name} = {arg_value.valueAsString()}")



        # Print the number of sub-surfaces before processing
        sub_surfaces = model.getSubSurfaces()
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")

        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Retrieve user inputs
        igu_component_name = runner.getStringArgumentValue("igu_component_name", user_arguments)
        frame_cross_section_area = runner.getDoubleArgumentValue("frame_cross_section_area", user_arguments)
        # frame_perimeter_length = runner.getDoubleArgumentValue("frame_perimeter_length", user_arguments)
        declared_unit = runner.getStringArgumentValue("declared_unit", user_arguments)
        gwp = runner.getDoubleArgumentValue("gwp", user_arguments)

        total_window_frame_volume = 0.0
        sub_surfaces = model.getSubSurfaces()
        runner.registerInfo(f"Total sub-surfaces found: {len(sub_surfaces)}")

        for sub_surface in sub_surfaces:
            sub_surface_name = sub_surface.nameString()
            construction = sub_surface.construction()

            if construction.is_initialized:
                construction_name = construction.get().nameString()
                runner.registerInfo(f"Processing window: {sub_surface_name} with construction: {construction_name}")
            else:
                runner.registerWarning(f"Sub-surface {sub_surface_name} has no construction assigned, skipping.")
                continue

            # Check if it's a valid window type (Only process windows that are "Outdoors" and of specific types)
            if sub_surface.outsideBoundaryCondition() != "Outdoors" or sub_surface.subSurfaceType() not in ["FixedWindow", "OperableWindow"]:
                runner.registerInfo(f"Skipping non-window surface: {sub_surface_name}")
                continue
            runner.registerInfo(f"Processing sub-surface: {sub_surface.nameString()}")
            perimeter = self.calculate_perimeter(sub_surface)
            window_frame_volume = frame_cross_section_area * perimeter
            total_window_frame_volume += window_frame_volume
            # runner.registerInfo(f"Window {sub_surface_name} perimeter: {perimeter:.3f} m")
            runner.registerInfo(f"Window {sub_surface_name} frame volume: {window_frame_volume:.3f} m3")

        if total_window_frame_volume == 0:
            runner.registerWarning("No valid windows found. Exiting measure.")
            return False

        # Compute GWP per volume
        try:
            gwp_per_volume = calculate_gwp_per_volume(gwp, declared_unit)
            runner.registerInfo(f"GWP per volume: {gwp_per_volume:.2f} kgCO2e/m3.")
        except Exception as e:
            runner.registerError(f"Error calculating GWP per volume: {e}")
            return False

        # Calculate total embodied carbon
        total_embodied_carbon = total_window_frame_volume * gwp_per_volume
        runner.registerInfo(f"Total embodied carbon for {igu_component_name}: {total_embodied_carbon:.2f} kgCO2e.")

        # Attach the result to the building's additional properties
        building = model.getBuilding()
        additional_properties = building.additionalProperties()
        additional_properties.setFeature(f"EmbodiedCarbon_{igu_component_name}", total_embodied_carbon)

        # Create an output variable for reporting
        output_var = openstudio.model.OutputVariable("WindowEnhancement:EmbodiedCarbon", model)
        output_var.setKeyValue(igu_component_name)
        output_var.setReportingFrequency("Monthly")
        output_var.setName(f"Embodied Carbon for {igu_component_name}")

        return True


# Register the measure
WindowEnhancement().registerWithApplication()

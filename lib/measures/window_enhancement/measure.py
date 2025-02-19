# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************
import typing
import openstudio
import typing
from pathlib import Path
import openstudio
import jinja2
from resources.EC3_lookup import calculate_gwp_per_volume, extract_numeric_value


RESOURCES_DIR = Path(__file__).parent / "resources"

# Start the measure

class WindowEnhancement(openstudio.measure.ModelMeasure):
    """A ModelMeasure."""

    def name(self):
        """
        Embodied emissions for window enhancement.
        """
        return "Window Enhancment"

    def description(self):
        """
        Calculate embodied emissions associated with adding film or IGU/
        storm window to an existing building.
        """
        return "Calculate embodied emissions for window enhancements."

    def modeler_description(self):
        """
        Basic description of the measure.
        """
        return "This measure uses EC3 database lookup for calculating embodied carbon for an IGU/storm window addition."

    # define the arguments that the user will input
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

        return args

def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
    """Execute the measure."""
    super().run(model, runner, user_arguments)  # Required

    # Validate user inputs
    if not runner.validateUserArguments(self.arguments(model), user_arguments):
        return False

    # Retrieve user inputs
    igu_component_name = runner.getStringArgumentValue("igu_component_name", user_arguments)
    frame_cross_section_area = runner.getDoubleArgumentValue("frame_cross_section_area", user_arguments)
    frame_perimeter_length = runner.getDoubleArgumentValue("frame_perimeter_length", user_arguments)
    declared_unit = runner.getStringArgumentValue("declared_unit", user_arguments)  # Assuming declared unit is an input
    gwp = runner.getDoubleArgumentValue("gwp", user_arguments)  # Assuming GWP value is an input

    # Calculate GWP per volume
    try:
        wframe_gwp_per_volume = calculate_gwp_per_volume(gwp, declared_unit)
        runner.registerInfo(f"Calculated GWP per volume: {wframe_gwp_per_volume:.2f} kgCO2e/m3.")
    except Exception as e:
        runner.registerError(f"Error calculating GWP per volume: {e}")
        return False

    # Calculate embodied carbon
    embodied_carbon = wframe_gwp_per_volume * frame_cross_section_area * frame_perimeter_length

    # Log the calculation
    runner.registerInfo(f"Embodied carbon for {igu_component_name}: {embodied_carbon:.2f} kgCO2e.")

    # Report the calculated embodied carbon for the enhancement
    print(f"Embodied carbon for {igu_component_name}: {embodied_carbon:.2f} kgCO2e.")

    # Attach the result to the building's additional properties
    additional_properties = model.getBuilding().additionalProperties()
    additional_properties.setFeature(f"EmbodiedCarbon_{igu_component_name}", embodied_carbon)

    # Optionally add output variables for reporting
    output_var = openstudio.model.OutputVariable("WindowEnhancement:EmbodiedCarbon", model)
    output_var.setKeyValue(igu_component_name)
    output_var.setReportingFrequency("Monthly")
    output_var.setName("Embodied Carbon for Window Enhancement")

    # Return success
    return True

# Register the measure
WindowEnhancement().registerWithApplication()
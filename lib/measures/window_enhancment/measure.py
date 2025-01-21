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
from resources.EC3_lookup import wframe_gwp_per_volume

RESOURCES_DIR = Path(__file__).parent / "resources"

# Start the measure

class WindowEnhancment(openstudio.measure.ModelMeasure):
    """A ModelMeasure."""

    def name(self):
        """
        Embodied emissions for window enhancement.
        """
        return "Window Enhancment"

    def description(self):
        """
        Calculate embodied emissions associated with adding film,
        storm window, or something else to an existing building.
        """
        return "Calculate embodied emissions for window enhancements."

    def modeler_description(self):
        """
        Layered construction approach will be used.
        """
        return "Layered construction approach being used."

    # define the arguments that the user will input
    def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
        """
        define what happens when the measure is run
        """
        args = openstudio.measure.OSArgumentVector()
        return args

    def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
        """Defines what happens when the measure is run."""
        super().run(model, runner, user_arguments)  # Do **NOT** remove this line

        if not (runner.validateUserArguments(self.arguments(model), user_arguments)):
            return False
        wframe_gwp = openstudio.model.WindowEnhancementVariable(model)
        wframe_gwp.setName("WindowFrameGWP")

        # Add a regular Output:Variable that references it
        wframe_gwp_ouput = openstudio.model.OutputVariable("WindowEnhancement:OutputVariable", model)
        wframe_gwp_ouput.setKeyValue(wframe_gwp.nameString())

        print(wframe_gwp_per_volume)

        return True


# register the measure to be used by the application
WindowEnhancment().registerWithApplication()
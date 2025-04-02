# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio

logger = openstudio.Logger.instance()
logger.standardOutLogger().enable()  # Enables standard output logging


class ReportAdditionalProperties(openstudio.measure.ReportingMeasure):
    def name(self):
        return "Report AdditionalProperties"

    def description(self):
        return "Reports all AdditionalProperties objects and their key-value pairs in the model."

    def modeler_description(self):
        return "Traverses the model and extracts data from AdditionalProperties objects."

    def run(self, runner):
        model = runner.lastOpenStudioModel().get()

        runner.registerInitialCondition("Starting to collect additional properties.")

        additional_properties_objects = []

        # Iterate through all model objects
        for obj in model.objects():
            if obj.additionalProperties().size() > 0:  # Check if object has additional properties
                additional_properties_objects.append(obj)

        runner.registerInfo(f"Found {len(additional_properties_objects)} objects with additional properties.")

        for obj in additional_properties_objects:
            obj_name = obj.nameString()
            runner.registerInfo(f"AdditionalProperties for: {obj_name}")

            for key in obj.additionalProperties().keys():
                value = obj.additionalProperties().get(key)
                runner.registerInfo(f"  {key}: {value}")

        runner.registerFinalCondition("All AdditionalProperties have been reported.")
        return True


# This registers the measure to be usable
measure = ReportAdditionalProperties()

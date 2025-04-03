# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio

class ReportAdditionalProperties(openstudio.measure.ReportingMeasure):
    def name(self):
        return "ReportAdditionalProperties"

    def description(self):
        return "Reports all AdditionalProperties objects and their key-value pairs in the model."

    def modeler_description(self):
        return "Traverses the model and extracts data from AdditionalProperties objects."

    def run(self, runner, model):
        
        # Check if model exists
        if not model:
            runner.registerError("Model is None. Exiting measure.")
            return False

        
        runner.registerInitialCondition("Starting to collect additional properties.")

        additional_properties_objects = []

        # Iterate through all model objects
        for obj in model.objects():
            print(obj)
            additional_properties_objects.append(obj)
           

        runner.registerInfo(f"Found {len(additional_properties_objects)} objects.")

        return True


# This registers the measure to be usable
measure = ReportAdditionalProperties()

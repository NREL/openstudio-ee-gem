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
    
    def __init__(self):
        super().__init__()
        self.material_data = {}  # Dictionary to store extracted key-value pairs

    def parse_workspace_object(self, obj):
        """Extracts Material Name and its corresponding numeric value from an OS:AdditionalProperties object."""
        num_fields = obj.numFields()
        if num_fields < 5:
            return  # Skip objects with insufficient fields

        # Assume material name is always at Field 1 and the numeric value is at the last field
        material_name = obj.getString(1, True)  # Field 1: Material Name
        numeric_value = obj.getString(num_fields - 1, True)  # Last field: Numeric Value

        if material_name.is_initialized() and numeric_value.is_initialized():
            try:
                # Convert numeric value from string to float
                self.material_data[material_name.get()] = float(numeric_value.get())
            except ValueError:
                print(f"Warning: Could not convert {numeric_value.get()} to float for {material_name.get()}")

    def run(self, runner, model):
        """Main function that searches for AdditionalProperties objects and extracts data."""
        self.material_data.clear()  # Reset dictionary before collecting data

        # Search for all OS:AdditionalProperties objects in the model
        additional_properties_objects = model.getObjectsByType(openstudio.IddObjectType("OS_AdditionalProperties"))

        if len(additional_properties_objects) > 0:
            runner.registerInfo(f"Found {len(additional_properties_objects)} AdditionalProperties objects.")
            
            for obj in additional_properties_objects:
                self.parse_workspace_object(obj)  # Call method properly using self

        # Print the collected material data
        runner.registerInfo("Extracted Material Data:")
        runner.registerInfo(str(self.material_data))

        return True

# This registers the measure to be usable
measure = ReportAdditionalProperties()

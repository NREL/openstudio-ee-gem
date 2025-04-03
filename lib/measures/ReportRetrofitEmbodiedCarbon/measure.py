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
        # Create an empty dictionary to store relevant data
        additional_properties_data = {}

        # Search for all OS:AdditionalProperties objects in the model
        additional_properties_objects = model.getObjectsByType("OS:AdditionalProperties")

        # Check if there are any objects of type OS:AdditionalProperties
        if len(additional_properties_objects) > 0:
            print(f"Found {len(additional_properties_objects)} AdditionalProperties objects.")
            
            for obj in additional_properties_objects:
                # Assuming we are dealing with a WorkspaceObject (which is a superclass)
                if isinstance(obj, openstudio.openstudioutilitiesidf.WorkspaceObject):
                    # Debug: Print the object type to check if it's what we expect
                    print(f"Object type: {type(obj)}")
                    
                    # Check if the object has relevant attributes for Handle and Object Name
                    if hasattr(obj, 'handle') and hasattr(obj, 'objectName'):
                        # Get the Handle and Object Name of the object
                        handle = obj.handle()
                        object_name = obj.objectName()

                        # Initialize a dictionary for this object if it's not already initialized
                        if handle not in additional_properties_data:
                            additional_properties_data[handle] = {
                                'Object Name': object_name,
                                'Features': []
                            }

                        # If the object has features (like 'Feature Name' and 'Feature Value')
                        if hasattr(obj, 'getFeatureNames') and hasattr(obj, 'getFeatureValues'):
                            feature_names = obj.getFeatureNames()
                            feature_values = obj.getFeatureValues()

                            # Store the feature names and values in the dictionary under 'Features'
                            for name, value in zip(feature_names, feature_values):
                                additional_properties_data[handle]['Features'].append({
                                    'Feature Name': name,
                                    'Feature Value': value
                                })

                        else:
                            print(f"Object does not have expected feature methods or attributes: {obj}")

        else:
            print("No AdditionalProperties objects found.")
        
        # Print out the collected data for debugging purposes
        print("Collected AdditionalProperties Data:")
        for handle, data in additional_properties_data.items():
            print(f"Handle: {handle}, Object Name: {data['Object Name']}")
            for feature in data['Features']:
                print(f"  Feature Name: {feature['Feature Name']}, Feature Value: {feature['Feature Value']}")
        
        runner.registerInfo(f"Found {len(additional_properties_objects)} AdditionalProperties objects.")

        return True



# This registers the measure to be usable
measure = ReportAdditionalProperties()


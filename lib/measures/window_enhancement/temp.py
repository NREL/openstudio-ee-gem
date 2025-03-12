import openstudio
import sys

# Define the output file path
output_file = "model_attributes.txt"

# Redirect stdout to the file
with open(output_file, "w") as f:
    sys.stdout = f  # Redirect stdout to file
    model = openstudio.model.Model()
    print(dir(model))  # This will now be written to the file

# Reset stdout back to default (console)
sys.stdout = sys.__stdout__

print(f"Output saved to {output_file}")

#test
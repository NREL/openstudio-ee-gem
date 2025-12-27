# import sys
import os
import openstudio
from pathlib import Path
from measure import DoorEnhancement
import configparser
import csv
from itertools import product

# read API Token from local
script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(script_dir, "../../.."))
config_path = os.path.join(repo_root, "config.ini")

if not os.path.exists(config_path):
    raise FileNotFoundError(f"Config file not found: {config_path}")

config = configparser.ConfigParser()
config.read(config_path)
API_TOKEN= config["EC3_API_TOKEN"]["API_TOKEN"]

CURRENT_DIR_PATH = Path(__file__).parent.absolute()
model_path = Path(CURRENT_DIR_PATH / "tests/ReverseTranslatedModel.osm")

def bottom_seal_options():
    # return ["brush weatherstrip", "automatic door bottom", "silicone adhesive smoke gasket"]
    return ['none']


def top_side_seal_options():
    # return ["silicone adhesive smoke gasket", "jamb weatherstrip"]
    return ['none']

def door_options():
    # return ['wooden door', 'garage door', 'polystyrene core steel door', 
            # 'polyurethane core steel door', 'honeycomb core steel door',
            # 'stiffened core steel door']
    return ['none']

# Generate all combinations
bottom_seals = bottom_seal_options()
top_side_seals = top_side_seal_options()
doors = door_options()

all_combinations = list(product(bottom_seals, top_side_seals, doors))
total_combinations = len(all_combinations)

print(f"Testing {total_combinations} retrofit combinations...")
print(f"Bottom seal options: {len(bottom_seals)}")
print(f"Top/side seal options: {len(top_side_seals)}")
print(f"Door options: {len(doors)}")
print("-" * 80)

# Prepare CSV file for results
output_csv = Path(CURRENT_DIR_PATH / "tests/output/retrofit_combinations_results.csv")
output_csv.parent.mkdir(parents=True, exist_ok=True)

with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow([
        'Combination_Number', 'Bottom_Seal', 'Top_Side_Seal', 'Door_Option', 
        'Door_R_Value', 'Result', 'Errors', 'Warnings', 'Info_Messages'
    ])
    
    # Test each combination
    for idx, (bottom_seal, top_side_seal, door_option) in enumerate(all_combinations, start=1):
        print(f"\n[{idx}/{total_combinations}] Testing combination:")
        print(f"  Bottom seal: {bottom_seal}")
        print(f"  Top/side seal: {top_side_seal}")
        print(f"  Door: {door_option}")
        
        # Load fresh model for each test
        translator = openstudio.osversion.VersionTranslator()
        model = translator.loadModel(openstudio.toPath(str(model_path))).get()
        
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        
        measure = DoorEnhancement()
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        
        # Set all required arguments
        def set_arg(name, value):
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
        
        set_arg("analysis_period", 30)
        set_arg("door_bottom_seal_option", bottom_seal)
        set_arg("door_top_side_seal_option", top_side_seal)
        set_arg("length_per_unit_bottom_side", 5.1816)
        set_arg("strip_lifetime", 15)
        set_arg('door_lifetime', 30)
        set_arg('door_area_per_unit', 1.95)
        set_arg('door_option', door_option)
        set_arg("gwp_statistic", "median")
        set_arg("space_infiltration_reduction_percent", 0)
        set_arg("api_key", API_TOKEN)
        
        # Calculate door R-value directly from door option using measure's static method
        door_r_values_dict = DoorEnhancement.door_r_values()
        door_r_value = door_r_values_dict.get(door_option, 0.0)
        
        # Run the measure
        try:
            result = measure.run(model, runner, arg_map)
            result_value = runner.result().value().valueName()
            
            # Collect messages
            errors = [error.logMessage() for error in runner.result().errors()]
            warnings = [warning.logMessage() for warning in runner.result().warnings()]
            infos = [info.logMessage() for info in runner.result().info()]
            
            print(f"  Result: {result_value}")
            if door_r_value:
                print(f"  Door R-value: {door_r_value}")
            if errors:
                print(f"  Errors: {len(errors)}")
            if warnings:
                print(f"  Warnings: {len(warnings)}")
            
            # Write to CSV
            csv_writer.writerow([
                idx,
                bottom_seal,
                top_side_seal,
                door_option,
                door_r_value,
                result_value,
                '; '.join(errors) if errors else '',
                '; '.join(warnings) if warnings else '',
                '; '.join(infos) if infos else ''
            ])
            
            # Save model for successful runs
            if result_value == "Success":
                safe_name = f"{idx}_{bottom_seal.replace(' ', '_')}_{top_side_seal.replace(' ', '_')}_{door_option.replace(' ', '_')}"
                save_path = Path(CURRENT_DIR_PATH / f"tests/output/{safe_name}.osm")
                model.save(openstudio.toPath(str(save_path)), True)
            
        except Exception as e:
            print(f"  EXCEPTION: {str(e)}")
            csv_writer.writerow([
                idx,
                bottom_seal,
                top_side_seal,
                door_option,
                '',
                'Exception',
                str(e),
                '',
                ''
            ])
        
        finally:
            del model

print("\n" + "=" * 80)
print(f"Testing complete! Results saved to: {output_csv}")
print("=" * 80)
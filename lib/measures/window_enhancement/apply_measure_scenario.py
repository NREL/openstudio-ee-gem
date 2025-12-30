# import sys
import os
import openstudio
from pathlib import Path
from measure import WindowEnhancement
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
model_path = Path(CURRENT_DIR_PATH / "tests/DOE_small_office.osm")

def frame_options():
    """Return window frame options to test"""
    return ['wood-aluminium window frame', 'wood window frame']

def caulking_options():
    """Return caulking options to test"""
    return ['polyurethane', 'acrylic']

def glass_options():
    """Return glass pane options to test"""
    return ['none']

def user_num_panes_options():
    """Return number of panes to test (only used when glass_option is 'provide user_num_panes')"""
    return [0]

def film_options():
    """Return film options to test"""
    return ['none']

def weatherstrip_options():
    """Return weatherstrip options to test"""
    return ['silicone adhesive smoke gasket']

def secondary_glazing_options():
    """Return secondary glazing options to test"""
    return ['none']

def infiltration_reduction_percentages():
    """Test different infiltration reduction scenarios"""
    return [0, 10,20,30,40, 50]

# Generate all combinations
frame_opts = frame_options()
caulking_opts = caulking_options()
glass_opts = glass_options()
film_opts = film_options()
weatherstrip_opts = weatherstrip_options()
secondary_glazing_opts = secondary_glazing_options()
infiltration_reductions = infiltration_reduction_percentages()

# Create combinations, handling glass pane and secondary glazing options properly
all_combinations = []
for frame_opt in frame_opts:
    for caulking_opt in caulking_opts:
        for glass_opt in glass_opts:
            for film_opt in film_opts:
                for weatherstrip_opt in weatherstrip_opts:
                    for secondary_glazing_opt in secondary_glazing_opts:
                        for infilt_red in infiltration_reductions:
                            # Skip incompatible combinations:
                            # 1. Secondary glazing with glass replacement (would conflict)
                            if glass_opt == 'provide user_num_panes' and secondary_glazing_opt == 'install secondary glazing':
                                continue
                            
                            if glass_opt == 'provide user_num_panes':
                                # Add combinations for each pane option
                                for num_panes in user_num_panes_options():
                                    all_combinations.append((
                                        frame_opt, caulking_opt, glass_opt, num_panes, 
                                        film_opt, weatherstrip_opt, secondary_glazing_opt, infilt_red
                                    ))
                            else:
                                # No panes option needed for 'none'
                                all_combinations.append((
                                    frame_opt, caulking_opt, glass_opt, 1, 
                                    film_opt, weatherstrip_opt, secondary_glazing_opt, infilt_red
                                ))

total_combinations = len(all_combinations)

print(f"Testing {total_combinations} window retrofit combinations...")
print(f"Frame options: {len(frame_opts)}")
print(f"Caulking options: {len(caulking_opts)}")
print(f"Glass options: {len(glass_opts)}")
print(f"Film options: {len(film_opts)}")
print(f"Weatherstrip options: {len(weatherstrip_opts)}")
print(f"Secondary glazing options: {len(secondary_glazing_opts)}")
print(f"Infiltration reduction percentages: {len(infiltration_reductions)}")
print("-" * 80)

# Prepare CSV file for results
output_csv = Path(CURRENT_DIR_PATH / "tests/output/retrofit_combinations_results.csv")
output_csv.parent.mkdir(parents=True, exist_ok=True)

with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow([
        'Combination_Number', 'Frame_Option', 'Caulking_Option', 'Glass_Option', 'Num_Panes', 
        'Film_Option', 'Weatherstrip_Option', 'Secondary_Glazing_Option',
        'Infiltration_Reduction_%', 'Result', 'Errors', 'Warnings', 'Info_Messages',
        'Total_Embodied_Carbon_kgCO2eq'
    ])
    
    # Test each combination
    for idx, (frame_opt, caulking_opt, glass_opt, num_panes, film_opt, weatherstrip_opt, 
              secondary_glazing_opt, infiltration_reduction) in enumerate(all_combinations, start=1):
        print(f"\n[{idx}/{total_combinations}] Testing combination:")
        print(f"  Frame: {frame_opt}")
        print(f"  Caulking: {caulking_opt}")
        print(f"  Glass: {glass_opt}")
        if glass_opt == 'provide user_num_panes':
            print(f"  Number of panes: {num_panes}")
        print(f"  Film: {film_opt}")
        print(f"  Weatherstrip: {weatherstrip_opt}")
        print(f"  Secondary glazing: {secondary_glazing_opt}")
        print(f"  Infiltration reduction: {infiltration_reduction}%")
        
        # Load fresh model for each test
        translator = openstudio.osversion.VersionTranslator()
        model = translator.loadModel(openstudio.toPath(str(model_path))).get()
        
        osw = openstudio.WorkflowJSON()
        runner = openstudio.measure.OSRunner(osw)
        
        measure = WindowEnhancement()
        args = measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        
        # Set all required arguments
        def set_arg(name, value):
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
        
        set_arg("analysis_period", 30)
        set_arg("wf_lifetime", 15)
        set_arg("wf_option", frame_opt)
        set_arg("caulking_option", caulking_opt)
        set_arg("film_option", film_opt)
        set_arg("weatherstrip_option", weatherstrip_opt)
        set_arg("glass_option", glass_opt)
        set_arg('user_num_panes', num_panes)
        set_arg("gwp_statistic", "median")
        set_arg("secondary_glazing_option", secondary_glazing_opt)
        set_arg("space_infiltration_reduction_percent", infiltration_reduction)
        set_arg("api_key", API_TOKEN)
        
        # Run the measure
        try:
            result = measure.run(model, runner, arg_map)
            result_value = runner.result().value().valueName()
            
            # Collect messages
            errors = [error.logMessage() for error in runner.result().errors()]
            warnings = [warning.logMessage() for warning in runner.result().warnings()]
            infos = [info.logMessage() for info in runner.result().info()]
            
            # Extract embodied carbon from building additional properties
            building = model.getBuilding()
            building_props = building.additionalProperties()
            
            total_embodied_carbon = None
            if building_props.hasFeature("window_enhancement_total_embodied_carbon_kgCO2eq"):
                total_embodied_carbon = building_props.getFeatureAsDouble("window_enhancement_total_embodied_carbon_kgCO2eq")
                if total_embodied_carbon.is_initialized():
                    total_embodied_carbon = total_embodied_carbon.get()
            
            print(f"  Result: {result_value}")
            if total_embodied_carbon is not None:
                print(f"  Total Embodied Carbon: {total_embodied_carbon:.2f} kgCO2eq")
            if errors:
                print(f"  Errors: {len(errors)}")
            if warnings:
                print(f"  Warnings: {len(warnings)}")
            
            # Write to CSV
            csv_writer.writerow([
                idx,
                frame_opt,
                caulking_opt,
                glass_opt,
                num_panes if glass_opt == 'provide user_num_panes' else '',
                film_opt,
                weatherstrip_opt,
                secondary_glazing_opt,
                infiltration_reduction,
                result_value,
                '; '.join(errors) if errors else '',
                '; '.join(warnings) if warnings else '',
                '; '.join(infos) if infos else '',
                total_embodied_carbon if total_embodied_carbon is not None else ''
            ])
            
            # Save model for successful runs
            if result_value == "Success":
                safe_name = f"{idx}_fr{frame_opt[:4]}_ca{caulking_opt[:4]}_gl{glass_opt[:4]}{num_panes if glass_opt == 'provide user_num_panes' else ''}_fi{film_opt[:4]}_ws{weatherstrip_opt[:4]}_sg{secondary_glazing_opt[:4]}_if{infiltration_reduction}"
                safe_name = safe_name.replace(' ', '_')
                save_path = Path(CURRENT_DIR_PATH / f"tests/output/{safe_name}.osm")
                model.save(openstudio.toPath(str(save_path)), True)
            
        except Exception as e:
            print(f"  EXCEPTION: {str(e)}")
            csv_writer.writerow([
                idx,
                frame_opt,
                caulking_opt,
                glass_opt,
                num_panes if glass_opt == 'provide user_num_panes' else '',
                film_opt,
                weatherstrip_opt,
                secondary_glazing_opt,
                infiltration_reduction,
                'Exception',
                str(e),
                '',
                '',
                ''
            ])
        
        finally:
            del model

print("\n" + "=" * 80)
print(f"Testing complete! Results saved to: {output_csv}")
print("=" * 80)

#!/usr/bin/env ruby

# Simple script to fix specific camelCase variable names to snake_case
# This targets only the specific variables mentioned in the task

def fix_specific_variables(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Specific variable name replacements
  variable_replacements = {
    'new_def_LCCs' => 'new_def_lccs',
    'new_def_LCC' => 'new_def_lcc',
    'exist_def_LCCs' => 'exist_def_lccs',
    'exist_def_LCC' => 'exist_def_lcc',
    'final_building_EPD' => 'final_building_epd',
    'object_LCCs' => 'object_lccs',
    'object_LCC' => 'object_lcc',
    'yr0_capital_totalCosts' => 'yr0_capital_total_costs',
    'absoluteAzimuth' => 'absolute_azimuth',
    'projectionFactor' => 'projection_factor',
    'constructionArgs' => 'construction_args',
    'constructionHandles' => 'construction_handles',
    'constructionDisplayNames' => 'construction_display_names',
    'constructionArgsHash' => 'construction_args_hash',
    'subSurfaces' => 'sub_surfaces',
    'shadingGroups' => 'shading_groups',
    'shadingSurfaces' => 'shading_surfaces',
    'spaceTypeArgs' => 'space_type_args',
    'spaceTypeHandles' => 'space_type_handles',
    'spaceTypeDisplayNames' => 'space_type_display_names',
    'spaceTypeArgsHash' => 'space_type_args_hash',
    'lightingPowerReductionPercent' => 'lighting_power_reduction_percent',
    'materialAndInstallationCost' => 'material_and_installation_cost',
    'yearsUntilCostsStart' => 'years_until_costs_start',
    'demoCostInitialConst' => 'demo_cost_initial_const',
    'expectedLife' => 'expected_life',
    'omCost' => 'om_cost',
    'omFrequency' => 'om_frequency',
    'demoCostsOfBaselineObjects' => 'demo_costs_of_baseline_objects',
    'yr0CapitalTotalCosts' => 'yr0_capital_total_costs',
    'spaceTypeLights' => 'space_type_lights',
    'spaceTypeLuminaires' => 'space_type_luminaires',
    'spaceLights' => 'space_lights',
    'spaceLuminaires' => 'space_luminaires',
    'existDef' => 'exist_def',
    'newDef' => 'new_def',
    'updatedInstance' => 'updated_instance',
    'updatedInstanceName' => 'updated_instance_name',
    'zoneSpaces' => 'zone_spaces',
    'zoneSpacesWithNewSensors' => 'zone_spaces_with_new_sensors',
    'primaryArea' => 'primary_area',
    'secondaryArea' => 'secondary_area',
    'primarySpace' => 'primary_space',
    'secondarySpace' => 'secondary_space',
    'threeOrMoreSensors' => 'three_or_more_sensors',
    'sensorPrimary' => 'sensor_primary',
    'sensorSecondary' => 'sensor_secondary',
    'buildingLightingPower' => 'building_lighting_power',
    'buildingLPD' => 'building_lpd',
    'finalBuilding' => 'final_building',
    'finalBuildingLightingPower' => 'final_building_lighting_power',
    'finalBuildingLPD' => 'final_building_lpd',
    'elecEquipPowerReductionPercent' => 'elec_equip_power_reduction_percent',
    'number_of_exist_space_shading_surf' => 'number_of_existing_space_shading_surfaces',
    'number_of_final_space_shading_surf' => 'number_of_final_space_shading_surfaces'
  }

  # Apply replacements
  variable_replacements.each do |old_name, new_name|
    content = content.gsub(/\b#{Regexp.escape(old_name)}\b/, new_name)
  end

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed variables in #{file_path}"
    return true
  end

  return false
end

# Process all measure files
Dir.glob('lib/measures/**/measure.rb').each do |file_path|
  puts "Processing #{file_path}..."
  fix_specific_variables(file_path)
end

puts 'Variable fixing complete!'

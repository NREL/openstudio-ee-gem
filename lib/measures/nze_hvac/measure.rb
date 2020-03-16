# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) 2008-2020, Alliance for Sustainable Energy, LLC.
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# (1) Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# (2) Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# (3) Neither the name of the copyright holder nor the names of any contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission from the respective party.
#
# (4) Other than as required in clauses (1) and (2), distributions in any form
# of modifications or other derivative works may not use the "OpenStudio"
# trademark, "OS", "os", or any other confusingly similar designation without
# specific prior written permission from Alliance for Sustainable Energy, LLC.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER(S) AND ANY CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER(S), ANY CONTRIBUTORS, THE
# UNITED STATES GOVERNMENT, OR THE UNITED STATES DEPARTMENT OF ENERGY, NOR ANY OF
# THEIR EMPLOYEES, BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT
# OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# *******************************************************************************

class NzeHvac < OpenStudio::Measure::ModelMeasure
  require 'openstudio-standards'

  def name
    return 'NZEHVAC'
  end

  # human readable description
  def description
    return 'This measure replaces the existing HVAC system if any with the user selected HVAC system.  The user can select how to partition the system, applying it to the whole building, a system per building type, a system per building story, or automatically partition based on residential/non-residential occupany types and space loads.'
  end

  # human readable description of modeling approach
  def modeler_description
    return 'HVAC system creation logic uses [openstudio-standards](https://github.com/NREL/openstudio-standards) and efficiency values are defined in the openstudio-standards Standards spreadsheet under the *NREL ZNE Ready 2017* template.'
  end

  def add_system_to_zones(model, runner, hvac_system_type, zones, standard,
                          doas_dcv: false)
    if doas_dcv
      doas_system_type = 'DOAS with DCV'
    else
      doas_system_type = 'DOAS'
    end

    # create HVAC system
    # use methods in openstudio-standards
    # Standard.model_add_hvac_system(model, system_type, main_heat_fuel, zone_heat_fuel, cool_fuel, zones)
    # can be combination systems or individual objects - depends on the type of system
    # todo - reenable fan_coil_capacity_control_method when major installer released with udpated standards gem from what shipped with 2.9.0
    case hvac_system_type.to_s
    when 'DOAS with fan coil chiller with boiler'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Fan Coil', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     zone_equipment_ventilation: false)
      # fan_coil_capacity_control_method: 'VariableFanVariableFlow')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'DOAS with fan coil chiller with central air source heat pump'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Fan Coil', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     zone_equipment_ventilation: false)
      # fan_coil_capacity_control_method: 'VariableFanVariableFlow')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'DOAS with fan coil air-cooled chiller with boiler'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Fan Coil', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     zone_equipment_ventilation: false)
    # fan_coil_capacity_control_method: 'VariableFanVariableFlow')

    when 'DOAS with fan coil air-cooled chiller with central air source heat pump'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Fan Coil', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     zone_equipment_ventilation: false)
    # fan_coil_capacity_control_method: 'VariableFanVariableFlow')

    # ventilation provided by zone fan coil unit in fan coil systems
    when 'Fan coil chiller with boiler'
      standard.model_add_hvac_system(self, 'Fan Coil', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature')
      # fan_coil_capacity_control_method: 'VariableFanVariableFlow')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'Fan coil chiller with central air source heat pump'
      standard.model_add_hvac_system(self, 'Fan Coil', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones)
      # fan_coil_capacity_control_method: 'VariableFanVariableFlow')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'Fan coil air-cooled chiller with boiler'
      standard.model_add_hvac_system(self, 'Fan Coil', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled')
    # fan_coil_capacity_control_method: 'VariableFanVariableFlow')

    when 'Fan coil air-cooled chiller with central air source heat pump'
      standard.model_add_hvac_system(self, 'Fan Coil', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled')
    # fan_coil_capacity_control_method: 'VariableFanVariableFlow')

    when 'DOAS with radiant slab chiller with boiler'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Radiant Slab', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'DOAS with radiant slab chiller with central air source heat pump'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Radiant Slab', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones)
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'DOAS with radiant slab air-cooled chiller with boiler'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Radiant Slab', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled')

    when 'DOAS with radiant slab air-cooled chiller with central air source heat pump'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled',
                                     air_loop_heating_type: 'Water',
                                     air_loop_cooling_type: 'Water')
      standard.model_add_hvac_system(model, 'Radiant Slab', ht = 'AirSourceHeatPump', znht = nil, cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled')

    when 'DOAS with VRF'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'Electricity', znht = nil, cl = 'Electricity', zones,
                                     air_loop_heating_type: 'DX',
                                     air_loop_cooling_type: 'DX')
      standard.model_add_hvac_system(model, 'VRF', ht = 'Electricity', znht = nil, cl = 'Electricity', zones,
                                     zone_equipment_ventilation: false)

    when 'VRF'
      standard.model_add_hvac_system(model, 'VRF', ht = 'Electricity', znht = nil, cl = 'Electricity', zones)

    when 'DOAS with water source heat pumps cooling tower with boiler'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature')
      standard.model_add_hvac_system(model, 'Water Source Heat Pumps', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     heat_pump_loop_cooling_type: 'CoolingTower',
                                     zone_equipment_ventilation: false)

    when 'DOAS with water source heat pumps with ground source heat pump'
      standard.model_add_hvac_system(model, doas_system_type, ht = 'Electricity', znht = nil, cl = 'Electricity', zones,
                                     air_loop_heating_type: 'DX',
                                     air_loop_cooling_type: 'DX')
      standard.model_add_hvac_system(model, 'Ground Source Heat Pumps', ht = 'Electricity', znht = nil, cl = 'Electricity', zones,
                                     zone_equipment_ventilation: false)

    when 'Water source heat pumps cooling tower with boiler'
      standard.model_add_hvac_system(model, 'Water Source Heat Pumps', ht = 'NaturalGas', znht = nil, cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     heat_pump_loop_cooling_type: 'CoolingTower')

    when 'Water source heat pumps with ground source heat pump'
      standard.model_add_hvac_system(model, 'Ground Source Heat Pumps', ht = 'Electricity', znht = nil, cl = 'Electricity', zones)

    # PVAV systems by default use a DX coil for cooling
    when 'PVAV with gas boiler reheat'
      standard.model_add_hvac_system(model, 'PVAV Reheat', ht = 'NaturalGas', znht = 'NaturalGas', cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature')

    when 'PVAV with central air source heat pump reheat'
      standard.model_add_hvac_system(model, 'PVAV Reheat', ht = 'AirSourceHeatPump', znht = 'AirSourceHeatPump', cl = 'Electricity', zones)

    when 'VAV chiller with gas boiler reheat'
      standard.model_add_hvac_system(model, 'VAV Reheat', ht = 'NaturalGas', znht = 'NaturalGas', cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature')
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'VAV chiller with central air source heat pump reheat'
      standard.model_add_hvac_system(model, 'VAV Reheat', ht = 'AirSourceHeatPump', znht = 'AirSourceHeatPump', cl = 'Electricity', zones)
      chilled_water_loop = model.getPlantLoopByName('Chilled Water Loop').get
      condenser_water_loop = model.getPlantLoopByName('Condenser Water Loop').get
      standard.model_add_waterside_economizer(model, chilled_water_loop, condenser_water_loop,
                                              integrated: true)

    when 'VAV air-cooled chiller with gas boiler reheat'
      standard.model_add_hvac_system(model, 'VAV Reheat', ht = 'NaturalGas', znht = 'NaturalGas', cl = 'Electricity', zones,
                                     hot_water_loop_type: 'LowTemperature',
                                     chilled_water_loop_cooling_type: 'AirCooled')

    when 'VAV air-cooled chiller with central air source heat pump reheat'
      standard.model_add_hvac_system(model, 'VAV Reheat', ht = 'AirSourceHeatPump', znht = 'AirSourceHeatPump', cl = 'Electricity', zones,
                                     chilled_water_loop_cooling_type: 'AirCooled')

    when 'PSZ-HP'
      standard.model_add_hvac_system(self, 'PSZ-HP', ht = 'Electricity', znht = nil, cl = 'Electricity', zones)
    else
      runner.registerError("HVAC System #{hvac_system_type} not recognized")
      return false
    end
    runner.registerInfo("Added HVAC System type #{hvac_system_type} to the model for #{zones.size} zones")
  end

  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    # argument to remove existing hvac system
    remove_existing_hvac = OpenStudio::Measure::OSArgument.makeBoolArgument('remove_existing_hvac', true)
    remove_existing_hvac.setDisplayName('Remove existing HVAC?')
    remove_existing_hvac.setDefaultValue(false)
    args << remove_existing_hvac

    # argument for HVAC system type
    hvac_system_type_choices = OpenStudio::StringVector.new
    hvac_system_type_choices << 'DOAS with fan coil chiller with boiler'
    hvac_system_type_choices << 'DOAS with fan coil chiller with central air source heat pump'
    hvac_system_type_choices << 'DOAS with fan coil air-cooled chiller with boiler'
    hvac_system_type_choices << 'DOAS with fan coil air-cooled chiller with central air source heat pump'
    hvac_system_type_choices << 'Fan coil chiller with boiler'
    hvac_system_type_choices << 'Fan coil chiller with central air source heat pump'
    hvac_system_type_choices << 'Fan coil air-cooled chiller with boiler'
    hvac_system_type_choices << 'Fan coil air-cooled chiller with central air source heat pump'
    hvac_system_type_choices << 'DOAS with radiant slab chiller with boiler'
    hvac_system_type_choices << 'DOAS with radiant slab chiller with central air source heat pump'
    hvac_system_type_choices << 'DOAS with radiant slab air-cooled chiller with boiler'
    hvac_system_type_choices << 'DOAS with radiant slab air-cooled chiller with central air source heat pump'
    hvac_system_type_choices << 'DOAS with VRF'
    hvac_system_type_choices << 'VRF'
    hvac_system_type_choices << 'DOAS with water source heat pumps cooling tower with boiler'
    hvac_system_type_choices << 'DOAS with water source heat pumps with ground source heat pump'
    hvac_system_type_choices << 'Water source heat pumps cooling tower with boiler'
    hvac_system_type_choices << 'Water source heat pumps with ground source heat pump'
    hvac_system_type_choices << 'VAV chiller with gas boiler reheat'
    hvac_system_type_choices << 'VAV chiller with central air source heat pump reheat'
    hvac_system_type_choices << 'VAV air-cooled chiller with gas boiler reheat'
    hvac_system_type_choices << 'VAV air-cooled chiller with central air source heat pump reheat'
    hvac_system_type_choices << 'PVAV with gas boiler reheat'
    hvac_system_type_choices << 'PVAV with central air source heat pump reheat'

    hvac_system_type = OpenStudio::Measure::OSArgument.makeChoiceArgument('hvac_system_type', hvac_system_type_choices, true)
    hvac_system_type.setDisplayName('HVAC System Type:')
    hvac_system_type.setDescription('Details on HVAC system type in measure documentation.')
    hvac_system_type.setDefaultValue('DOAS with fan coil chiller with central air source heat pump')
    args << hvac_system_type

    # make the DOAS system have DCV controls
    doas_dcv = OpenStudio::Measure::OSArgument.makeBoolArgument('doas_dcv', true)
    doas_dcv.setDisplayName('DOAS capable of demand control ventilation?')
    doas_dcv.setDescription('If a DOAS system, this will make air terminals variable air volume instead of constant volume.')
    doas_dcv.setDefaultValue(false)
    args << doas_dcv

    # argument for how to partition HVAC system
    hvac_system_partition_choices = OpenStudio::StringVector.new
    hvac_system_partition_choices << 'Automatic Partition'
    hvac_system_partition_choices << 'Whole Building'
    hvac_system_partition_choices << 'One System Per Building Story'
    hvac_system_partition_choices << 'One System Per Building Type'

    hvac_system_partition = OpenStudio::Measure::OSArgument.makeChoiceArgument('hvac_system_partition', hvac_system_partition_choices, true)
    hvac_system_partition.setDisplayName('HVAC System Partition:')
    hvac_system_partition.setDescription('Automatic Partition will separate the HVAC system by residential/non-residential and if loads and schedules are substantially different.')
    hvac_system_partition.setDefaultValue('Automatic Partition')
    args << hvac_system_partition

    # add an argument for ventilation schedule

    return args
  end # end the arguments method

  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
      return false
    end

    # assign user inputs
    remove_existing_hvac = runner.getBoolArgumentValue('remove_existing_hvac', user_arguments)
    hvac_system_type = runner.getOptionalStringArgumentValue('hvac_system_type', user_arguments)
    doas_dcv = runner.getBoolArgumentValue('doas_dcv', user_arguments)
    hvac_system_partition = runner.getOptionalStringArgumentValue('hvac_system_partition', user_arguments)
    hvac_system_partition = hvac_system_partition.to_s

    # standard to access methods in openstudio-standards
    std = Standard.build('NREL ZNE Ready 2017')

    # ensure standards building type is set
    unless model.getBuilding.standardsBuildingType.is_initialized
      dominant_building_type = std.model_get_standards_building_type(model)
      if dominant_building_type.nil?
        # use office building type if none in model
        model.getBuilding.setStandardsBuildingType('Office')
      else
        model.getBuilding.setStandardsBuildingType(dominant_building_type)
      end
    end

    # get the climate zone
    climate_zone_obj = model.getClimateZones.getClimateZone('ASHRAE', 2006)
    if climate_zone_obj.empty
      climate_zone_obj = model.getClimateZones.getClimateZone('ASHRAE', 2013)
    end

    if climate_zone_obj.empty
      runner.registerError('Please assign an ASHRAE climate zone to the model before running the measure.')
      return false
    else
      climate_zone = "ASHRAE 169-2006-#{climate_zone_obj.value}"
    end

    # remove existing hvac system from model
    if remove_existing_hvac
      runner.registerInfo('Removing existing HVAC systems from the model')
      std.remove_HVAC(model)
    end

    # exclude plenum zones, zones without thermostats, and zones with no floor area
    conditioned_zones = []
    model.getThermalZones.each do |zone|
      next if std.thermal_zone_plenum?(zone)
      next if !std.thermal_zone_heated?(zone) && !std.thermal_zone_cooled?(zone)
      conditioned_zones << zone
    end

    # logic to partition thermal zones to be served by different HVAC systems
    case hvac_system_partition

      when 'Automatic Partition'
        # group zones by occupancy type (residential/nonresidential)
        # split non-dominant groups if their total area exceeds 20,000 ft2.
        sys_groups = std.model_group_zones_by_type(model, OpenStudio.convert(20000, 'ft^2', 'm^2').get)

        # assume secondary system type is PSZ-AC for VAV Reheat otherwise assume same hvac system type
        sec_sys_type = hvac_system_type # same as primary system type
        sec_sys_type = 'PSZ-HP' if (hvac_system_type.to_s == 'VAV Reheat') || (hvac_system_type.to_s == 'PVAV Reheat')

        sys_groups.each do |sys_group|
          # add the primary system to the primary zones and the secondary system to any zones that are different
          # differentiate primary and secondary zones based on operating hours and internal loads (same as 90.1 PRM)
          pri_sec_zone_lists = std.model_differentiate_primary_secondary_thermal_zones(model, sys_group['zones'])

          # add the primary system to the primary zones
          add_system_to_zones(model, runner, hvac_system_type, pri_sec_zone_lists['primary'], std, doas_dcv: doas_dcv)

          # add the secondary system to the secondary zones (if any)
          if !pri_sec_zone_lists['secondary'].empty?
            runner.registerInfo("Secondary system type is #{sec_sys_type}")
            add_system_to_zones(model, runner, sec_sys_type, pri_sec_zone_lists['secondary'], std, doas_dcv: doas_dcv)
          end
        end

      when 'Whole Building'
        add_system_to_zones(model, runner, hvac_system_type, conditioned_zones, std, doas_dcv: doas_dcv)

      when 'One System Per Building Story'
        story_groups = std.model_group_zones_by_story(model, conditioned_zones)
        story_groups.each do |story_zones|
          add_system_to_zones(model, runner, hvac_system_type, story_zones, std, doas_dcv: doas_dcv)
        end

      when 'One System Per Building Type'
        system_groups = std.model_group_zones_by_building_type(model, 0.0)
        system_groups.each do |system_group|
          add_system_to_zones(model, runner, hvac_system_type, system_group['zones'], std, doas_dcv: doas_dcv)
        end

      else
        runner.registerError('Invalid HVAC system partition choice')
        return false
    end

    # check that the directory name isn't too long for a sizing run; sometimes this isn't necessary
    # if "#{Dir.pwd} }/SizingRun".length > 90
    #   runner.registerError("Directory path #{Dir.pwd}/SizingRun is greater than 90 characters and too long perform a sizing run.")
    #   return false
    # end

    # check that weather file exists for a sizing run
    if !model.weatherFile.is_initialized
      runner.registerError('Weather file not set. Cannot perform sizing run.')
      return false
    end

    # log the build messages and errors to a file before sizing run in case of failure
    log_messages_to_file("#{Dir.pwd}/openstudio-standards.log", debug = true)

    # perform a sizing run to get equipment sizes for efficiency standards
    if std.model_run_sizing_run(model, "#{Dir.pwd}/SizingRun") == false
      runner.registerError("Unable to perform sizing run for hvac system #{hvac_system_type} for this model.  Check the openstudio-standards.log in this measure for more details.")
      log_messages_to_file("#{Dir.pwd}/openstudio-standards.log", debug = true)
      return false
    end

    # apply the HVAC efficiency standards
    std.model_apply_hvac_efficiency_standard(model, climate_zone)

    # log the build messages and errors to a file
    log_messages_to_file("#{Dir.pwd}/openstudio-standards.log", debug = true)

    runner.registerFinalCondition("Added system type #{hvac_system_type} to model.")

    return true
  end # end the run method
end # end the measure

# this allows the measure to be used by the application
NzeHvac.new.registerWithApplication

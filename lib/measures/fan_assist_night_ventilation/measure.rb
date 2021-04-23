# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) 2008-2021, Alliance for Sustainable Energy, LLC.
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

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/measures/measure_writing_guide/

# start the measure
class FanAssistNightVentilation < OpenStudio::Measure::ModelMeasure
  # human readable name
  def name
    return 'Fan Assist Night Ventilation'
  end

  # human readable description
  def description
    return "This measure is meant to roughly model the impact of fan assisted night ventilation. The user needs to have a ventilation schedule in the model, operable windows where natural ventilation is desired, and air walls or interior operable windows in walls and floors to define the path of air through the building. The user specified flow rate is proportionally split up based on the area of exterior operable windows. The size of interior air walls and windows doesn't matter."
  end

  # human readable description of modeling approach
  def modeler_description
    return "It's up to the modeler to choose a flow rate that is approriate for the fenestration and interior openings within the building. Each zone with operable windows will get a zone ventilation object. The measure will first look for a celing opening to find a connection for zone a zone mixing object. If a ceiling isn't found, then it looks for a wall. Don't provide more than one ceiling paths or more than one wall path. The end result is zone ventilation object followed by a path of zone mixing objects. The fan consumption is modeled in the zone ventilation object, but no heat is brought in from the fan. There is no zone ventilation object at the end of the path of zones. In addition to schedule, the zone ventilation is controlled by a minimum outdoor temperature.

The measure was developed for use in un-conditioned models. Has not been tested in conjunction with mechanical systems.

To address an issue in OpenStudio zones with ZoneVentilation, this measure adds an exhaust fan added as well, but the CFM value for the exhaust fan is set to 0.0"
  end

  # define the arguments that the user will input
  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    # add argument for design_flow_rate
    design_flow_rate = OpenStudio::Measure::OSArgument.makeDoubleArgument('design_flow_rate', true)
    design_flow_rate.setDisplayName('Exhaust Flow Rate')
    design_flow_rate.setUnits('cfm')
    design_flow_rate.setDefaultValue(1000.0)
    args << design_flow_rate

    # add argument for design_flow_rate
    fan_pressure_rise = OpenStudio::Measure::OSArgument.makeDoubleArgument('fan_pressure_rise', true)
    fan_pressure_rise.setDisplayName('Fan Pressure Rise')
    fan_pressure_rise.setUnits('Pa')
    fan_pressure_rise.setDefaultValue(500.0)
    args << fan_pressure_rise

    # add argument for design_flow_rate
    efficiency = OpenStudio::Measure::OSArgument.makeDoubleArgument('efficiency', true)
    efficiency.setDisplayName('Fan Total Efficiency')
    efficiency.setDefaultValue(0.65)
    args << efficiency

    # populate raw choice argument for schedules
    schedule_handles = OpenStudio::StringVector.new
    schedule_display_names = OpenStudio::StringVector.new

    # putting raw schedules and names into hash
    schedule_args = model.getSchedules
    schedule_args_hash = {}
    schedule_args.each do |schedule_arg|
      schedule_args_hash[schedule_arg.name.to_s] = schedule_arg
    end

    # populate choice argument for ventilation_schedule
    ventilation_schedule_handles = OpenStudio::StringVector.new
    ventilation_schedule_display_names = OpenStudio::StringVector.new

    # looping through sorted hash of schedules to find air velocity schedules
    schedule_args_hash.sort.map do |key, value|
      next if value.scheduleTypeLimits.empty?
      if value.scheduleTypeLimits.get.unitType == 'Dimensionless'
        ventilation_schedule_handles << value.handle.to_s
        ventilation_schedule_display_names << key
      end
    end

    # make a choice argument for Air Velocity Schedule Name
    ventilation_schedule = OpenStudio::Measure::OSArgument.makeChoiceArgument('ventilation_schedule', ventilation_schedule_handles, ventilation_schedule_display_names, true)
    ventilation_schedule.setDisplayName('Choose a Ventilation Schedule.')
    args << ventilation_schedule

    # argument for minimum outdoor temperature
    min_outdoor_temp = OpenStudio::Measure::OSArgument.makeDoubleArgument('min_outdoor_temp', true)
    min_outdoor_temp.setDisplayName('Minimum Outdoor Temperature')
    min_outdoor_temp.setUnits('F')
    min_outdoor_temp.setDefaultValue(55.0)
    args << min_outdoor_temp

    return args
  end

  def inspect_airflow_surfaces(zone)
    array = [] # [adjacent_zone,surfaceType]
    zone.spaces.each do |space|
      space.surfaces.each do |surface|
        next if surface.adjacentSurface.is_initialized != true
        next if !surface.adjacentSurface.get.space.is_initialized
        next if !surface.adjacentSurface.get.space.get.thermalZone.is_initialized
        adjacent_zone = surface.adjacentSurface.get.space.get.thermalZone.get
        if surface.surfaceType == 'RoofCeiling' || surface.surfaceType == 'Wall'
          if surface.isAirWall
            array << [adjacent_zone, surface.surfaceType]
          else
            surface.subSurfaces.each do |sub_surface|
              next if sub_surface.adjacentSubSurface.is_initialized != true
              next if !sub_surface.adjacentSubSurface.get.surface.get.space.is_initialized
              next if !sub_surface.adjacentSubSurface.get.surface.get.space.get.thermalZone.is_initialized
              adjacent_zone = sub_surface.adjacentSubSurface.get.surface.get.space.get.thermalZone.get
              if sub_surface.isAirWall || sub_surface.subSurfaceType == 'OperableWindow'
                array << [adjacent_zone, surface.surfaceType]
              end
            end
          end
        end
      end
    end

    return array
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    design_flow_rate = runner.getDoubleArgumentValue('design_flow_rate', user_arguments)
    design_flow_rate_si = OpenStudio.convert(design_flow_rate, 'cfm', 'm^3/s').get
    fan_pressure_rise = runner.getDoubleArgumentValue('fan_pressure_rise', user_arguments)
    efficiency = runner.getDoubleArgumentValue('efficiency', user_arguments)
    ventilation_schedule = runner.getOptionalWorkspaceObjectChoiceValue('ventilation_schedule', user_arguments, model)
    min_outdoor_temp = runner.getDoubleArgumentValue('min_outdoor_temp', user_arguments)

    # TODO: - validate this
    ventilation_schedule = ventilation_schedule.get.to_Schedule.get

    # report initial condition of model
    runner.registerInitialCondition("The building started with #{model.getZoneVentilationDesignFlowRates.size} zone ventilation design flow rate objects and #{model.getZoneMixings.size} zone mixing objects.")

    # setup hash to hold path objects and exhaust zones
    path_objects = {}
    exhaust_zones = {}

    # make hash of zones and the area of operable exterior windows
    operable_ext_window_hash = {}
    bldg_area_counter = 0.0
    model.getThermalZones.sort.each do |zone|
      zone_area_counter = 0.0
      zone.spaces.each do |space|
        space.surfaces.each do |surface|
          next if surface.surfaceType != 'Wall'
          surface.subSurfaces.each do |sub_surface|
            next if sub_surface.outsideBoundaryCondition != 'Outdoors'
            next if sub_surface.subSurfaceType != 'OperableWindow'
            zone_area_counter += sub_surface.netArea * sub_surface.multiplier
          end
        end
      end

      # store airflow paths for future use
      path_objects[zone] = inspect_airflow_surfaces(zone)

      # add to operable_ext_window_hash if non-zero area
      next if zone_area_counter == 0.0
      bldg_area_counter += zone_area_counter
      operable_ext_window_hash[zone] = zone_area_counter
    end

    # setup has to store paths
    flow_paths = {}

    # return as NA if no exterior operable windows
    if operable_ext_window_hash.empty?
      runner.registerAsNotApplicable('No Exterior operable windows were found. The model will not be altered')
      return true
    end

    # Loop through zones in hash and make natural ventilation objects so the sum equals the user specified target
    operable_ext_window_hash.each do |zone, zone_opp_area|
      zone_ventilation = OpenStudio::Model::ZoneVentilationDesignFlowRate.new(model)
      zone_ventilation.setName("PathStart_#{zone.name}")
      zone_ventilation.addToThermalZone(zone)
      zone_ventilation.setVentilationType('Exhaust') # switched from Natural to use power. Need to set fan properties. Used exhaust so no heat from fan in stream
      zone_ventilation.setDesignFlowRateCalculationMethod('Flow/Zone')
      fraction_flow = design_flow_rate_si * zone_opp_area / bldg_area_counter
      zone_ventilation.setDesignFlowRate(fraction_flow)
      zone_design_flow_rate_ip = OpenStudio.convert(zone_ventilation.designFlowRate, 'm^3/s', 'cfm').get

      # inputs used for fan power
      zone_ventilation.setFanPressureRise(fan_pressure_rise)
      zone_ventilation.setFanTotalEfficiency(efficiency)

      # set schedule from user arg
      zone_ventilation.setSchedule(ventilation_schedule)

      # set min outdoor air temperature
      min_outdoor_temp_si = OpenStudio.convert(min_outdoor_temp, 'F', 'C').get
      zone_ventilation.setMinimumOutdoorTemperature(min_outdoor_temp_si)

      # for some reason min indoor temp defaults to 18 vs. -100
      zone_ventilation.setMinimumIndoorTemperature(-100.0)
      zone_ventilation.setDeltaTemperature(-100.0)

      # set coef values for constant flow
      zone_ventilation.setConstantTermCoefficient(1.0)
      zone_ventilation.setTemperatureTermCoefficient(0.0)
      zone_ventilation.setVelocityTermCoefficient(0.0)
      zone_ventilation.setVelocitySquaredTermCoefficient(0.0)

      zone_opp_area_ip = OpenStudio.convert(zone_opp_area, 'm^2', 'ft^2').get

      zone_opp_area_airflow_speed = zone_design_flow_rate_ip / (zone_opp_area_ip * 60.0)
      runner.registerInfo("Added natural ventilation to #{zone.name} of #{zone_design_flow_rate_ip.round(2)} (cfm).")
      runner.registerInfo("#{zone.name} has #{zone_opp_area_ip.round(2)} (ft^2) of operable windows, estimated airflow speed at operable window is #{zone_opp_area_airflow_speed.round(2)} (ft/sec).")
      # start trace of path adding air mixing objects
      found_path_end = false
      flow_paths[zone] = []
      current_zone = zone
      zones_used_for_this_path = [current_zone]
      until found_path_end == true
        found_ceiling = false
        path_objects[current_zone].each do |object|
          next if zones_used_for_this_path.include? (object[0])
          next if object[1].to_s != 'RoofCeiling'
          next if operable_ext_window_hash.include? (object[0])
          if found_ceiling
            runner.registerWarning("Found more than one possible airflow path for #{current_zone.name}")
          else
            flow_paths[zone] << object[0]
            current_zone = object[0]
            zones_used_for_this_path << object[0]
            found_ceiling = true
          end
        end
        if !found_ceiling
          found_wall = false
          path_objects[current_zone].each do |object|
            next if zones_used_for_this_path.include? (object[0])
            next if object[1].to_s != 'Wall'
            next if operable_ext_window_hash.include? (object[0])
            if found_wall
              runner.registerWarning("Found more than one possible airflow path for #{current_zone.name}")
            else
              flow_paths[zone] << object[0]
              current_zone = object[0]
              zones_used_for_this_path << object[0]
              found_wall = true
            end
          end
        end
        if (found_ceiling == false) && (found_wall == false)
          found_path_end = true
        end
      end

      # add one way air mixing objects along path zones
      zone_path_string_array = [zone.name]
      vent_zone = zone
      source_zone = zone
      flow_paths[zone].each do |zone|
        zone_mixing = OpenStudio::Model::ZoneMixing.new(zone)
        zone_mixing.setName("PathStart_#{vent_zone.name}_#{source_zone.name}")
        zone_mixing.setSourceZone(source_zone)
        zone_mixing.setDesignFlowRate(fraction_flow)

        # set min outdoor temp schedule
        min_outdoor_sch = OpenStudio::Model::ScheduleConstant.new(model)
        min_outdoor_sch.setValue(min_outdoor_temp_si)
        zone_mixing.setMinimumOutdoorTemperatureSchedule(min_outdoor_sch)

        # set schedule from user arg
        zone_mixing.setSchedule(ventilation_schedule)

        # change source zone to what was just target zone
        zone_path_string_array << zone.name
        source_zone = zone
      end
      runner.registerInfo("Added Zone Mixing Path: #{zone_path_string_array.join(' > ')}")

      # add to exhaust zones
      if !flow_paths[zone].empty?
        if exhaust_zones.include? flow_paths[zone].last
          exhaust_zones[flow_paths[zone].last] += fraction_flow
        else
          exhaust_zones[flow_paths[zone].last] = fraction_flow
        end
      else
        # extra code if there is no path from entry zone
        if exhaust_zones.include? zone
          exhaust_zones[zone] += fraction_flow
        else
          exhaust_zones[zone] = fraction_flow
          runner.registerWarning("#{zone.name} doesn't have path to other zones. Exhaust assumed to be with the same zone as air enters.")
        end
      end
    end

    # report how much air exhausts to each exhaust zone
    # when I add an exhaust fan to the top floor I want it to use energy but I don't want to move any additional air.
    # The air is already being brought into the zone by the zone mixing objects
    exhaust_zones.each do |zone, flow_rate|
      ip_fraction_flow_rate = OpenStudio.convert(flow_rate, 'm^3/s', 'cfm').get
      runner.registerInfo("Zone Mixing flow rate into #{zone.name} is #{ip_fraction_flow_rate.round(2)} (cfm). Fan Consumption included with zone ventilation zones.")

      # check for exterior surface area
      if zone.exteriorSurfaceArea == 0
        runner.registerWarning("Exhaust Zone #{zone.name} doesn't appear to have any exterior exposure. Review the paths to see that this is the expected result.")
      end

      # warn if zone multiplier are used
      non_default_multiplier = []
      model.getThermalZones.each do |zone|
        if zone.multiplier > 1
          non_default_multiplier << zone
        end
      end
      if !non_default_multiplier.empty?
        runner.registerWarning("This measure is not intended to be use when thermal zones have a non 1 multiplier. #{non_default_multiplier.size} zones in this model have multipliers greater than one. Results are likley invalid.")
      end

      # report final condition of model
      runner.registerFinalCondition("The building finished with #{model.getZoneVentilationDesignFlowRates.size} zone ventilation design flow rate objects and #{model.getZoneMixings.size} zone mixing objects.")

      # adding useful output variables for diagnostics
      OpenStudio::Model::OutputVariable.new('Zone Mixing Current Density Air Volume Flow Rate', model)
      OpenStudio::Model::OutputVariable.new('Zone Ventilation Current Density Volume Flow Rate', model)
      OpenStudio::Model::OutputVariable.new('Zone Ventilation Fan Electric Energy', model)
      OpenStudio::Model::OutputVariable.new('Zone Outdoor Air Drybulb Temperature', model)

      return true
    end
  end
end

# register the measure to be used by the application
FanAssistNightVentilation.new.registerWithApplication

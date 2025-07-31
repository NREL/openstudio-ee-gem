# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see
  def name
    return 'Add Daylight Sensor at the Center of Spaces with a Specified Space Type Assigned'
  end

  # human readable description
  def description
    return 'This measure will add daylighting controls to spaces that that have space types assigned with names containing the string in the argument. You can also add a cost per space for sensors added to the model.'
  end

  # human readable description of modeling approach
  def modeler_description
    return "Make an array of the spaces that meet the criteria. Locate the sensor x and y values by averaging the min and max X and Y values from floor surfaces in the space. If a space already has a daylighting control, do not add a new one and leave the original in place. Warn the user if the space isn't assigned to a thermal zone, or if the space doesn't have any translucent surfaces. Note that the cost is added to the space not the sensor. If the sensor is removed at a later date, the cost will remain."
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make a choice argument for model objects
    space_type_handles = open_studio::String_vector.new
    space_type_display_names = open_studio::String_vector.new

    # putting model object and names into hash
    space_type_args = model.get_space_types
    space_type_args_hash = {}
    space_type_args.each do |space_type_arg|
      space_type_args_hash[space_type_arg.name.to_s] = space_type_arg
    end

    # looping through sorted hash of model objects
    space_type_args_hash.sort.map do |key, value|
      # only include if space type is used in the model
      if !value.spaces.empty?
        space_type_handles << value.handle.to_s
        space_type_display_names << key
      end
    end

    # make a choice argument for space type
    space_type = open_studio::Measure::os_argument.make_choice_argument('space_type', space_type_handles, space_type_display_names, true)
    space_type.set_display_name('Add Daylight Sensors to Spaces of This Space Type')
    args << space_type

    # make an argument for setpoint
    setpoint = open_studio::Measure::os_argument.make_double_argument('setpoint', true)
    setpoint.set_display_name('Daylighting Setpoint')
    setpoint.set_units('fc')
    setpoint.set_default_value(45.0)
    args << setpoint

    # make an argument for control_type
    chs = open_studio::String_vector.new
    chs << 'None'
    chs << 'Continuous'
    chs << 'Stepped'
    chs << 'Continuous/Off'
    control_type = open_studio::Measure::os_argument.make_choice_argument('control_type', chs)
    control_type.set_display_name('Daylighting Control Type')
    control_type.set_default_value('Continuous/Off')
    args << control_type

    # make an argument for min_power_fraction
    min_power_fraction = open_studio::Measure::os_argument.make_double_argument('min_power_fraction', true)
    min_power_fraction.set_display_name('Daylighting Minimum Input Power Fraction')
    min_power_fraction.set_description('min = 0 max = 0.6')
    min_power_fraction.set_default_value(0.3)
    args << min_power_fraction

    # make an argument for min_light_fraction
    min_light_fraction = open_studio::Measure::os_argument.make_double_argument('min_light_fraction', true)
    min_light_fraction.set_display_name('Daylighting Minimum Light Output Fraction')
    min_light_fraction.set_description('min = 0 max = 0.6')
    min_light_fraction.set_default_value(0.2)
    args << min_light_fraction

    # make an argument for fraction_zone_controlled
    fraction_zone_controlled = open_studio::Measure::os_argument.make_double_argument('fraction_zone_controlled', true)
    fraction_zone_controlled.set_display_name('Fraction of zone controlled by daylight sensors')
    fraction_zone_controlled.set_default_value(1.0)
    args << fraction_zone_controlled

    # make an argument for height
    height = open_studio::Measure::os_argument.make_double_argument('height', true)
    height.set_display_name('Sensor Height')
    height.set_units('inches')
    height.set_default_value(30.0)
    args << height

    # make an argument for material and installation cost
    material_cost = open_studio::Measure::os_argument.make_double_argument('material_cost', true)
    material_cost.set_display_name('Material and Installation Costs per Space for Daylight Sensor')
    material_cost.set_units('$')
    material_cost.set_default_value(0.0)
    args << material_cost

    # make an argument for demolition cost
    demolition_cost = open_studio::Measure::os_argument.make_double_argument('demolition_cost', true)
    demolition_cost.set_display_name('Demolition Costs per Space for Daylight Sensor')
    demolition_cost.set_units('$')
    demolition_cost.set_default_value(0.0)
    args << demolition_cost

    # make an argument for duration in years until costs start
    years_until_costs_start = open_studio::Measure::os_argument.make_integer_argument('years_until_costs_start', true)
    years_until_costs_start.set_display_name('Years Until Costs Start')
    years_until_costs_start.set_units('whole years')
    years_until_costs_start.set_default_value(0)
    args << years_until_costs_start

    # make an argument to determine if demolition costs should be included in initial construction
    demo_cost_initial_const = open_studio::Measure::os_argument.make_bool_argument('demo_cost_initial_const', true)
    demo_cost_initial_const.set_display_name('Demolition Costs Occur During Initial Construction')
    demo_cost_initial_const.set_default_value(false)
    args << demo_cost_initial_const

    # make an argument for expected life
    expected_life = open_studio::Measure::os_argument.make_integer_argument('expected_life', true)
    expected_life.set_display_name('Expected Life')
    expected_life.set_units('whole years')
    expected_life.set_default_value(20)
    args << expected_life

    # make an argument for o&m cost
    om_cost = open_studio::Measure::os_argument.make_double_argument('om_cost', true)
    om_cost.set_display_name('O & M Costs per Space for Daylight Sensor')
    om_cost.set_units('$')
    om_cost.set_default_value(0.0)
    args << om_cost

    # make an argument for o&m frequency
    om_frequency = open_studio::Measure::os_argument.make_integer_argument('om_frequency', true)
    om_frequency.set_display_name('O & M Frequency')
    om_frequency.set_units('whole years')
    om_frequency.set_default_value(1)
    args << om_frequency

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validate_user_arguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    space_type = runner.get_optional_workspace_object_choice_value('space_type', user_arguments, model)
    setpoint = runner.get_double_argument_value('setpoint', user_arguments)
    control_type = runner.get_string_argument_value('control_type', user_arguments)
    min_power_fraction = runner.get_double_argument_value('min_power_fraction', user_arguments)
    min_light_fraction = runner.get_double_argument_value('min_light_fraction', user_arguments)
    fraction_zone_controlled = runner.get_double_argument_value('fraction_zone_controlled', user_arguments)
    height = runner.get_double_argument_value('height', user_arguments)
    material_cost = runner.get_double_argument_value('material_cost', user_arguments)
    demolition_cost = runner.get_double_argument_value('demolition_cost', user_arguments)
    years_until_costs_start = runner.get_integer_argument_value('years_until_costs_start', user_arguments)
    demo_cost_initial_const = runner.get_bool_argument_value('demo_cost_initial_const', user_arguments)
    expected_life = runner.get_integer_argument_value('expected_life', user_arguments)
    om_cost = runner.get_double_argument_value('om_cost', user_arguments)
    om_frequency = runner.get_integer_argument_value('om_frequency', user_arguments)

    # check the space_type for reasonableness
    if space_type.empty?
      handle = runner.get_string_argument_value('space_type', user_arguments)
      if handle.empty?
        runner.register_error('No space_type was chosen.')
      else
        runner.register_error("The selected space type with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if space_type.get.to_space_type.empty?
        runner.register_error('Script Error - argument not showing up as space type.')
        return false
      else
        space_type = space_type.get.to_space_type.get
      end
    end

    # check the setpoint for reasonableness
    if (setpoint < 0) || (setpoint > 9999) # dfg need input on good value
      runner.register_error("A setpoint of #{setpoint} foot-candles is outside the measure limit.")
      return false
    elsif setpoint > 999
      runner.register_warning("A setpoint of #{setpoint} foot-candles is abnormally high.") # dfg need input on good value
    end

    # check the min_power_fraction for reasonableness
    if (min_power_fraction < 0.0) || (min_power_fraction > 0.6)
      runner.register_error("The requested minimum input power fraction of #{min_power_fraction} for continuous dimming control is outside the acceptable range of 0 to 0.6.")
      return false
    end

    # check the min_light_fraction for reasonableness
    if (min_light_fraction < 0.0) || (min_light_fraction > 0.6)
      runner.register_error("The requested minimum light output fraction of #{min_light_fraction} for continuous dimming control is outside the acceptable range of 0 to 0.6.")
      return false
    end

    # check the height for reasonableness
    if (height < -360) || (height > 360) # neg ok because space origin may not be floor
      runner.register_error("A setpoint of #{height} inches is outside the measure limit.")
      return false
    elsif height > 72
      runner.register_warning("A setpoint of #{height} inches is abnormally high.")
    elsif height < 0
      runner.register_warning('Typically the sensor height should be a positive number, however if your space origin is above the floor then a negative sensor height may be approriate.')
    end

    # set flags to use later
    costs_requested = false
    warning_cost_assign_to_space = false

    # check costs for reasonableness
    if material_cost.abs + demolition_cost.abs + om_cost.abs == 0
      runner.register_info('No costs were requested for Daylight Sensors.')
    else
      costs_requested = true
    end

    # check lifecycle arguments for reasonableness
    if (years_until_costs_start < 0) && (years_until_costs_start > expected_life)
      runner.register_error('Years until costs start should be a non-negative integer less than Expected Life.')
    end
    if (expected_life < 1) && (expected_life > 100)
      runner.register_error('Choose an integer greater than 0 and less than or equal to 100 for Expected Life.')
    end
    if om_frequency < 1
      runner.register_error('Choose an integer greater than 0 for O & M Frequency.')
    end

    # short def to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure
    # round to 0 or 2)
    neat_numbers = lambda do |number, roundto = 2|
      if roundto == 2
        number = format '%.2f', number
      else
        number = number.round
      end
      # regex to add commas
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # helper that loops through lifecycle costs getting total costs under "Construction" or "Salvage" category and add to counter if occurs during year 0
    get_total_costs_for_objects = lambda do |objects|
      counter = 0
      objects.each do |object|
        object_lccs = object.life_cycle_costs
        object_lccs.each do |object_lcc|
          if ((object_lcc.category == 'Construction') || (object_lcc.category == 'Salvage')) && (object_lcc.years_from_start == 0)
            counter += object_lcc.total_cost
          end
        end
      end
      counter
    end

    # unit conversion from ip units to si units
    setpoint_si = Open_studio.convert(setpoint, 'fc', 'lux').get
    height_si = Open_studio.convert(height, 'in', 'm').get

    # variable to tally the area to which the overall measure is applied
    area = 0
    # variables to aggregate the number of sensors installed and the area affected
    sensor_count = 0
    sensor_area = 0
    spaces_using_space_type = space_type.spaces
    # array with subset of spaces
    spaces_using_space_type_in_zones_without_sensors = []
    affected_zones = []
    affected_zone_names = []
    # hash to hold sensor objects
    new_sensor_objects = {}

    # reporting initial condition of model
    starting_spaces = model.get_spaces
    runner.register_initial_condition("#{spaces_using_space_type.size} spaces are assigned to space type '#{space_type.name}'.")

    # get starting costs for spaces
    yr0_capital_total_costs = -1 * get_total_costs_for_objects.call(spaces_using_space_type)

    # test that there is no sensor already in the space, and that zone object doesn't already have sensors assigned.
    spaces_using_space_type.each do |space_using_space_type|
      if space_using_space_type.daylighting_controls.empty?
        space_zone = space_using_space_type.thermal_zone
        if space_zone.empty?
          runner.register_warning("Space '#{space_using_space_type.name}' is not associated with a thermal zone. It won't be part of the energy_plus simulation.")
        else
          space_zone = space_zone.get
          if space_zone.primary_daylighting_control.empty? && space_zone.secondary_daylighting_control.empty?
            spaces_using_space_type_in_zones_without_sensors << space_using_space_type
          end
        end
      else
        runner.register_warning("Space '#{space_using_space_type.name}' already has a daylighting sensor. No sensor was added.")
      end
    end

    # loop through all spaces,
    # and add a daylighting sensor with dimming to each
    space_count = 0
    spaces_using_space_type_in_zones_without_sensors.each do |space|
      space_count += 1
      area += space.floor_area

      # eliminate spaces that don't have exterior natural lighting
      has_ext_nat_light = false
      space.surfaces.each do |surface|
        next if surface.outside_boundary_condition != 'Outdoors'

        surface.sub_surfaces.each do |sub_surface|
          next if sub_surface.sub_surface_type == 'Door'
          next if sub_surface.sub_surface_type == 'overhead_door'

          has_ext_nat_light = true
        end
      end
      if has_ext_nat_light == false
        runner.register_warning("Space '#{space.name}' has no exterior natural lighting. No sensor will be added.")
        next
      end

      # find floors
      floors = []
      space.surfaces.each do |surface|
        next if surface.surface_type != 'Floor'

        floors << surface
      end

      # this method only works for flat (non-inclined) floors
      bounding_box = open_studio::Bounding_box.new
      floors.each do |floor|
        bounding_box.add_points(floor.vertices)
      end
      x_min = bounding_box.min_x.get
      y_min = bounding_box.min_y.get
      z_min = bounding_box.min_z.get
      x_max = bounding_box.max_x.get
      y_max = bounding_box.max_y.get

      # create a new sensor and put at the center of the space
      sensor = open_studio::Model::Daylighting_control.new(model)
      sensor.set_name("#{space.name} daylighting control")
      x_pos = (x_min + x_max) / 2
      y_pos = (y_min + y_max) / 2
      z_pos = z_min + height_si # put it 1 meter above the floor
      new_point = open_studio::Point3d.new(x_pos, y_pos, z_pos)
      sensor.set_position(new_point)
      sensor.set_illuminance_setpoint(setpoint_si)
      sensor.set_lighting_control_type(control_type)
      sensor.set_minimum_input_power_fractionfor_continuous_dimming_control(min_power_fraction)
      sensor.set_minimum_light_output_fractionfor_continuous_dimming_control(min_light_fraction)
      sensor.set_space(space)
      puts sensor

      # add life_cycle_cost objects if there is a non-zero value in one of the cost arguments
      if costs_requested == true

        starting_lcc_counter = space.life_cycle_costs.size

        # adding new cost items
        lcc_mat = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_mat - #{sensor.name}", space, material_cost, 'cost_per_each', 'Construction', expected_life, years_until_costs_start)
        if demo_cost_initial_const
          lcc_demo = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_demo - #{sensor.name}", space, demolition_cost, 'cost_per_each', 'Salvage', expected_life, years_until_costs_start)
        else
          lcc_demo = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_demo - #{sensor.name}", space, demolition_cost, 'cost_per_each', 'Salvage', expected_life, years_until_costs_start + expected_life)
        end
        lcc_om = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_om - #{sensor.name}", space, om_cost, 'cost_per_each', 'Maintenance', om_frequency, 0)

        if space.life_cycle_costs.size - starting_lcc_counter == 3
          if !warning_cost_assign_to_space
            runner.register_info('Cost for daylight sensors was added to spaces. The cost will remain in the model unless the space is removed. Removing only the sensor will not remove the cost.')
            warning_cost_assign_to_space = true
          end
        else
          runner.register_warning("The measure did not function as expected. #{space.life_cycle_costs.size - starting_lcc_counter} life_cycle_cost objects were made, 3 were expected.")
        end

      end

      # push unique zones to array for use later in measure
      temp_zone = space.thermal_zone.get
      if affected_zone_names.include?(temp_zone.name.to_s) == false
        affected_zones << temp_zone
        affected_zone_names << temp_zone.name.to_s
      end

      # push sensor object into hash with space name
      new_sensor_objects[space.name.to_s] = sensor

      # add floor area to the daylighting area tally
      sensor_area += space.floor_area

      # add to sensor count for reporting
      sensor_count += 1
    end

    if (sensor_count == 0) && (costs_requested == false)
      runner.register_as_not_applicable("No spaces that currently don't have sensor required a new sensor, and no lifecycle costs objects were requested.")
      return true
    end

    # loop through thermal Zones for spaces with daylighting controls added
    affected_zones.each do |zone|
      zone_spaces = zone.spaces
      zone_spaces_with_new_sensorss = []
      zone_spaces.each do |zone_space|
        if !zone_space.daylighting_controls.empty? && (zone_space.space_type.get == space_type)
          zone_spaces_with_new_sensorss << zone_space
        end
      end

      if !zone_spaces_with_new_sensorss.empty?
        # need to identify the two largest spaces
        primary_area = 0
        secondary_area = 0
        primary_space = nil
        secondary_space = nil
        three_or_more_sensors = false

        # dfg temp - need to add another if statement so only get spaces with sensors
        zone_spaces_with_new_sensorss.each do |zone_space|
          zone_space_area = zone_space.floor_area
          if zone_space_area > primary_area
            primary_area = zone_space_area
            primary_space = zone_space
          elsif zone_space_area > secondary_area
            secondary_area = zone_space_area
            secondary_space = zone_space
          else
            # setup flag to warn user that more than 2 sensors can't be added to a space
            three_or_more_sensors = true
          end
        end

        if primary_space
          # setup primary sensor
          sensor_primary = new_sensor_objects[primary_space.name.to_s]
          zone.set_primary_daylighting_control(sensor_primary)
          zone.set_fractionof_zone_controlledby_primary_daylighting_control(fraction_zone_controlled * primary_area / (primary_area + secondary_area))
        end

        if secondary_space
          # setup secondary sensor
          sensor_secondary = new_sensor_objects[secondary_space.name.to_s]
          zone.set_secondary_daylighting_control(sensor_secondary)
          zone.set_fractionof_zone_controlledby_secondary_daylighting_control(fraction_zone_controlled * secondary_area / (primary_area + secondary_area))
        end

        # warn that additional sensors were not used
        if three_or_more_sensors == true
          runner.register_warning("Thermal zone '#{zone.name}' had more than two spaces with sensors. Only two sensors were associated with the thermal zone.")
        end

      end
    end

    # setup open_studio units that we will need
    unit_area_ip = Open_studio.create_unit('ft^2').get
    unit_area_si = Open_studio.create_unit('m^2').get

    # define starting units
    area_si = open_studio::Quantity.new(sensor_area, unit_area_si)

    # unit conversion from ip units to si units
    area_ip = Open_studio.convert(area_si, unit_area_ip).get

    # get final costs for spaces
    yr0_capital_total_costs = get_total_costs_for_objects.call(spaces_using_space_type)

    # reporting final condition of model
    runner.register_final_condition("Added daylighting controls to #{sensor_count} spaces, covering #{area_ip}. Initial year costs associated with the daylighting controls is $#{neat_numbers.call(yr0_capital_total_costs, 0)}.")

    return true
  end
end

# this allows the measure to be used by the application
Add_daylight_sensors.new.register_with_application

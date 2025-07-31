# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see
  def name
    return 'Reduce Night Time Electric Equipment Loads'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make a choice argument for load def with one or more instances
    elec_load_def_handles = open_studio::String_vector.new
    elec_load_def_display_names = open_studio::String_vector.new

    # putting load defs and names into hash
    elec_load_def_args = model.get_electric_equipment_definitions
    elec_load_def_args_hash = {}
    elec_load_def_args.each do |elec_load_def_arg|
      elec_load_def_args_hash[elec_load_def_arg.name.to_s] = elec_load_def_arg
    end

    # looping through sorted hash of load defs
    elec_load_def_args_hash.sort.map do |key, value|
      if !value.instances.empty?
        elec_load_def_handles << value.handle.to_s
        elec_load_def_display_names << key
      end
    end

    # make an argument for electric equipment definition
    elec_load_def = open_studio::Measure::os_argument.make_choice_argument('elec_load_def', elec_load_def_handles, elec_load_def_display_names)
    elec_load_def.set_display_name('Pick an Electric Equipment Definition(schedules using this will be altered)')
    args << elec_load_def

    # make an argument for fractional value during specified time
    fraction_value = open_studio::Measure::os_argument.make_double_argument('fraction_value', true)
    fraction_value.set_display_name('Fractional Value for Night Time Load.')
    fraction_value.set_default_value(0.1)
    args << fraction_value

    # apply to weekday
    apply_weekday = open_studio::Measure::os_argument.make_bool_argument('apply_weekday', true)
    apply_weekday.set_display_name('Apply Schedule Changes to Weekday and Default Profiles?')
    apply_weekday.set_default_value(true)
    args << apply_weekday

    # weekday start time
    start_weekday = open_studio::Measure::os_argument.make_double_argument('start_weekday', true)
    start_weekday.set_display_name('Weekday/Default Time to Start Night Time Fraction(24hr, use decimal for sub hour).')
    start_weekday.set_default_value(18.0)
    args << start_weekday

    # weekday end time
    end_weekday = open_studio::Measure::os_argument.make_double_argument('end_weekday', true)
    end_weekday.set_display_name('Weekday/Default Time to End Night Time Fraction(24hr, use decimal for sub hour).')
    end_weekday.set_default_value(9.0)
    args << end_weekday

    # apply to saturday
    apply_saturday = open_studio::Measure::os_argument.make_bool_argument('apply_saturday', true)
    apply_saturday.set_display_name('Apply Schedule Changes to Saturdays?')
    apply_saturday.set_default_value(true)
    args << apply_saturday

    # saturday start time
    start_saturday = open_studio::Measure::os_argument.make_double_argument('start_saturday', true)
    start_saturday.set_display_name('Saturday Time to Start Night Time Fraction(24hr, use decimal for sub hour).')
    start_saturday.set_default_value(18.0)
    args << start_saturday

    # saturday end time
    end_saturday = open_studio::Measure::os_argument.make_double_argument('end_saturday', true)
    end_saturday.set_display_name('Saturday Time to End Night Time Fraction(24hr, use decimal for sub hour).')
    end_saturday.set_default_value(9.0)
    args << end_saturday

    # apply to sunday
    apply_sunday = open_studio::Measure::os_argument.make_bool_argument('apply_sunday', true)
    apply_sunday.set_display_name('Apply Schedule Changes to Sundays?')
    apply_sunday.set_default_value(true)
    args << apply_sunday

    # sunday start time
    start_sunday = open_studio::Measure::os_argument.make_double_argument('start_sunday', true)
    start_sunday.set_display_name('Sunday Time to Start Night Time Fraction(24hr, use decimal for sub hour).')
    start_sunday.set_default_value(18.0)
    args << start_sunday

    # sunday end time
    end_sunday = open_studio::Measure::os_argument.make_double_argument('end_sunday', true)
    end_sunday.set_display_name('Sunday Time to End Night Time Fraction(24hr, use decimal for sub hour).')
    end_sunday.set_default_value(9.0)
    args << end_sunday

    # make an argument for material and installation cost
    material_cost = open_studio::Measure::os_argument.make_double_argument('material_cost', true)
    material_cost.set_display_name('Material and Installation Costs per Electric Equipment Quantity ($).')
    material_cost.set_default_value(0.0)
    args << material_cost

    # make an argument for duration in years until costs start
    years_until_costs_start = open_studio::Measure::os_argument.make_integer_argument('years_until_costs_start', true)
    years_until_costs_start.set_display_name('Years Until Costs Start (whole years).')
    years_until_costs_start.set_default_value(0)
    args << years_until_costs_start

    # make an argument for expected life
    expected_life = open_studio::Measure::os_argument.make_integer_argument('expected_life', true)
    expected_life.set_display_name('Expected Life (whole years).')
    expected_life.set_default_value(20)
    args << expected_life

    # make an argument for o&m cost
    om_cost = open_studio::Measure::os_argument.make_double_argument('om_cost', true)
    om_cost.set_display_name('O & M Costs Costs per Electric Equipment Quantity ($).')
    om_cost.set_default_value(0.0)
    args << om_cost

    # make an argument for o&m frequency
    om_frequency = open_studio::Measure::os_argument.make_integer_argument('om_frequency', true)
    om_frequency.set_display_name('O & M Frequency (whole years).')
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
    elec_load_def = runner.get_optional_workspace_object_choice_value('elec_load_def', user_arguments, model)
    fraction_value = runner.get_double_argument_value('fraction_value', user_arguments)
    apply_weekday = runner.get_bool_argument_value('apply_weekday', user_arguments)
    start_weekday = runner.get_double_argument_value('start_weekday', user_arguments)
    end_weekday = runner.get_double_argument_value('end_weekday', user_arguments)
    apply_saturday = runner.get_bool_argument_value('apply_saturday', user_arguments)
    start_saturday = runner.get_double_argument_value('start_saturday', user_arguments)
    end_saturday = runner.get_double_argument_value('end_saturday', user_arguments)
    apply_sunday = runner.get_bool_argument_value('apply_sunday', user_arguments)
    start_sunday = runner.get_double_argument_value('start_sunday', user_arguments)
    end_sunday = runner.get_double_argument_value('end_sunday', user_arguments)
    material_cost = runner.get_double_argument_value('material_cost', user_arguments)
    years_until_costs_start = runner.get_integer_argument_value('years_until_costs_start', user_arguments)
    expected_life = runner.get_integer_argument_value('expected_life', user_arguments)
    om_cost = runner.get_double_argument_value('om_cost', user_arguments)
    om_frequency = runner.get_integer_argument_value('om_frequency', user_arguments)

    # check the elec_load_def for reasonableness
    if elec_load_def.empty?
      test = runner.get_string_argument_value('elec_load_def', user_arguments)
      if test.empty?
        runner.register_error('No Electric Equipment Definition was chosen.')
      else
        runner.register_error("An Electric Equipment Definition with handle '#{elec_load_def}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if elec_load_def.get.to_electric_equipment_definition.empty?
        runner.register_error('Script Error - argument not showing up as electric equipment definition.')
        return false
      else
        elec_load_def = elec_load_def.get.to_electric_equipment_definition.get
      end
    end

    # check the fraction for reasonableness
    if (fraction_value < 0) && (fraction_value <= 1)
      runner.register_error('Fractional value needs to be between or equal to 0 and 1.')
      return false
    end

    # check start_weekday for reasonableness and round to 15 minutes
    if (start_weekday < 0) && (start_weekday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24')
      return false
    else
      rounded_start_weekday = (start_weekday * 4).round / 4.0
      if start_weekday != rounded_start_weekday
        runner.register_info("Weekday start time rounded to nearest 15 minutes: #{rounded_start_weekday}")
      end
      wk_after_hour = rounded_start_weekday.truncate
      wk_after_min = (rounded_start_weekday - wk_after_hour) * 60
      wk_after_min = wk_after_min.to_i
    end

    # check end_weekday for reasonableness and round to 15 minutes
    if (end_weekday < 0) && (end_weekday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24.')
      return false
    elsif end_weekday > start_weekday
      runner.register_error('Please enter an end time earlier in the day than start time.')
      return false
    else
      rounded_end_weekday = (end_weekday * 4).round / 4.0
      if end_weekday != rounded_end_weekday
        runner.register_info("Weekday end time rounded to nearest 15 minutes: #{rounded_end_weekday}")
      end
      wk_before_hour = rounded_end_weekday.truncate
      wk_before_min = (rounded_end_weekday - wk_before_hour) * 60
      wk_before_min = wk_before_min.to_i
    end

    # check start_saturday for reasonableness and round to 15 minutes
    if (start_saturday < 0) && (start_saturday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24.')
      return false
    else
      rounded_start_saturday = (start_saturday * 4).round / 4.0
      if start_saturday != rounded_start_saturday
        runner.register_info("Saturday start time rounded to nearest 15 minutes: #{rounded_start_saturday}")
      end
      sat_after_hour = rounded_start_saturday.truncate
      sat_after_min = (rounded_start_saturday - sat_after_hour) * 60
      sat_after_min = sat_after_min.to_i
    end

    # check end_saturday for reasonableness and round to 15 minutes
    if (end_saturday < 0) && (end_saturday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24.')
      return false
    elsif end_saturday > start_saturday
      runner.register_error('Please enter an end time earlier in the day than start time.')
      return false
    else
      rounded_end_saturday = (end_saturday * 4).round / 4.0
      if end_saturday != rounded_end_saturday
        runner.register_info("Saturday end time rounded to nearest 15 minutes: #{rounded_end_saturday}")
      end
      sat_before_hour = rounded_end_saturday.truncate
      sat_before_min = (rounded_end_saturday - sat_before_hour) * 60
      sat_before_min = sat_before_min.to_i
    end

    # check start_sunday for reasonableness and round to 15 minutes
    if (start_sunday < 0) && (start_sunday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24.')
      return false
    else
      rounded_start_sunday = (start_sunday * 4).round / 4.0
      if start_sunday != rounded_start_sunday
        runner.register_info("Sunday start time rounded to nearest 15 minutes: #{rounded_start_sunday}")
      end
      sun_after_hour = rounded_start_sunday.truncate
      sun_after_min = (rounded_start_sunday - sun_after_hour) * 60
      sun_after_min = sun_after_min.to_i
    end

    # check end_sunday for reasonableness and round to 15 minutes
    if (end_sunday < 0) && (end_sunday <= 24)
      runner.register_error('Time in hours needs to be between or equal to 0 and 24.')
      return false
    elsif end_sunday > start_sunday
      runner.register_error('Please enter an end time earlier in the day than start time.')
      return false
    else
      rounded_end_sunday = (end_sunday * 4).round / 4.0
      if end_sunday != rounded_end_sunday
        runner.register_info("Sunday end time rounded to nearest 15 minutes: #{rounded_end_sunday}")
      end
      sun_before_hour = rounded_end_sunday.truncate
      sun_before_min = (rounded_end_sunday - sun_before_hour) * 60
      sun_before_min = sun_before_min.to_i
    end

    # set flags to use later
    costs_requested = false

    # check costs for reasonableness
    if material_cost.abs + om_cost.abs == 0
      runner.register_info("No costs were requested for #{elec_load_def.name}.")
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
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # breakup fractional values
    wk_before_value = fraction_value
    wk_after_value = fraction_value
    sat_before_value = fraction_value
    sat_after_value = fraction_value
    sun_before_value = fraction_value
    sun_after_value = fraction_value

    equip_schs = {}
    equip_sch_names = []
    reduced_equip_schs = {}

    # get instances of definition
    equipment_instances = model.get_electric_equipments
    equipment_instances_using_def = []

    # get schedules for equipment instances that user the picked
    equipment_instances.each do |equip|
      next unless equip.electric_equipment_definition == elec_load_def

      equipment_instances_using_def << equip
      if !equip.schedule.empty?
        equip_sch = equip.schedule.get
        equip_schs[equip_sch.name.to_s] = equip_sch
        equip_sch_names << equip_sch.name.to_s
      end
    end

    # reporting initial condition of model
    runner.register_initial_condition("The initial model had #{equipment_instances_using_def.size} instances of '#{elec_load_def.name}' load definition.")

    # loop through the unique list of equip schedules, cloning
    # and reducing schedule fraction before and after the specified times
    equip_sch_names.uniq.each do |equip_sch_name|
      equip_sch = equip_schs[equip_sch_name]
      if equip_sch.to_schedule_ruleset.empty?
        runner.register_warning("Schedule '#{equip_sch_name}' isn't a schedule_ruleset object and won't be altered by this measure.")
      else
        new_equip_sch = equip_sch.clone(model).to_schedule_ruleset.get
        new_equip_sch.set_name("#{equip_sch_name} night_load_control")
        reduced_equip_schs[equip_sch_name] = new_equip_sch
        new_equip_sch = new_equip_sch.to_schedule_ruleset.get

        # method to reduce the values in a day schedule to a give number before and after a given time
        reduce_schedule = lambda do |day_sch, before_hour, before_min, before_value, after_hour, after_min, after_value|
          runner.register_warning("Schedule '#{new_equip_sch.name}' applies to all days.  It has been treated as a Weekday schedule.")
        end
        reduce_schedule(new_equip_sch.default_day_schedule, wk_before_hour, wk_before_min, wk_before_value, wk_after_hour, wk_after_min, wk_after_value)

        # reduce weekdays
        new_equip_sch.schedule_rules.each do |sch_rule|
          if apply_weekday && (sch_rule.apply_monday || sch_rule.apply_tuesday || sch_rule.apply_wednesday || sch_rule.apply_thursday || sch_rule.apply_friday)
            reduce_schedule(sch_rule.day_schedule, wk_before_hour, wk_before_min, wk_before_value, wk_after_hour, wk_after_min, wk_after_value)
          end
        end

        # reduce saturdays
        new_equip_sch.schedule_rules.each do |sch_rule|
          if apply_saturday && sch_rule.apply_saturday
            if sch_rule.apply_monday || sch_rule.apply_tuesday || sch_rule.apply_wednesday || sch_rule.apply_thursday || sch_rule.apply_friday
              runner.register_warning("Rule '#{sch_rule.name}' for schedule '#{new_equip_sch.name}' applies to both Saturdays and Weekdays.  It has been treated as a Weekday schedule.")
            else
              reduce_schedule(sch_rule.day_schedule, sat_before_hour, sat_before_min, sat_before_value, sat_after_hour, sat_after_min, sat_after_value)
            end
          end
        end

        # reduce sundays
        new_equip_sch.schedule_rules.each do |sch_rule|
          if apply_sunday && sch_rule.apply_sunday
            if sch_rule.apply_monday || sch_rule.apply_tuesday || sch_rule.apply_wednesday || sch_rule.apply_thursday || sch_rule.apply_friday
              runner.register_warning("Rule '#{sch_rule.name}' for schedule '#{new_equip_sch.name}' applies to both Sundays and Weekdays.  It has been  treated as a Weekday schedule.")
            elsif sch_rule.apply_saturday
              runner.register_warning("Rule '#{sch_rule.name}' for schedule '#{new_equip_sch.name}' applies to both Saturdays and Sundays.  It has been treated as a Saturday schedule.")
            else
              reduce_schedule(sch_rule.day_schedule, sun_before_hour, sun_before_min, sun_before_value, sun_after_hour, sun_after_min, sun_after_value)
            end
          end
        end
      end
    end

    # loop through all electric equipment instances, replacing old equip schedules with the reduced schedules
    equipment_instances_using_def.each do |equip|
      if equip.schedule.empty?
        runner.register_warning("There was no schedule assigned for the electric equipment object named '#{equip.name}. No schedule was added.'")
      else
        old_equip_sch_name = equip.schedule.get.name.to_s
        if reduced_equip_schs[old_equip_sch_name]
          equip.set_schedule(reduced_equip_schs[old_equip_sch_name])
          runner.register_info("Schedule '#{reduced_equip_schs[old_equip_sch_name].name}' was edited for the electric equipment object named '#{equip.name}'")
        end
      end
    end

    # na if no schedules to change
    if equip_sch_names.uniq.empty?
      runner.register_not_as_applicable('There are no schedules to change.')
    end

    measure_cost = 0

    # add life_cycle_cost objects if there is a non-zero value in one of the cost arguments
    building = model.get_building
    if costs_requested == true
      quantity = elec_load_def.quantity
      # adding new cost items
      lcc_mat = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_mat - #{elec_load_def.name} night reduction", building, material_cost * quantity, 'cost_per_each', 'Construction', expected_life, years_until_costs_start)
      lcc_om = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_om - #{elec_load_def.name} night reduction", building, om_cost * quantity, 'cost_per_each', 'Maintenance', om_frequency, 0)
      measure_cost = material_cost * quantity
    end

    # reporting final condition of model
    runner.register_final_condition("#{equip_sch_names.uniq.size} schedule(s) were edited. The cost for the measure is #{neat_numbers(measure_cost, 0)}.")

    return true
  end
end

# this allows the measure to be used by the application
Reduce_night_time_electric_equipment_loads.new.register_with_application

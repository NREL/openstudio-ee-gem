# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see, this method may be deprecated as
  # the display name in pat comes from the name field in measure.xml
  def name
    return 'Improve Fan Belt Efficiency'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # populate choice argument for constructions that are applied to surfaces in the model
    loop_handles = open_studio::String_vector.new
    loop_display_names = open_studio::String_vector.new

    # putting air loops and names into hash
    loop_args = model.get_air_loop_hva_cs
    loop_args_hash = {}
    loop_args.each do |loop_arg|
      loop_args_hash[loop_arg.name.to_s] = loop_arg
    end

    # looping through sorted hash of air loops
    loop_args_hash.sort.map do |key, value|
      show_loop = false
      components = value.supply_components
      components.each do |component|
        if !component.to_fan_constant_volume.empty?
          show_loop = true
        end
        if !component.to_fan_variable_volume.empty?
          show_loop = true
        end
        if !component.to_fan_on_off.empty?
          show_loop = true
        end
      end

      # if loop as object of correct type then add to hash.
      if show_loop == true
        loop_handles << value.handle.to_s
        loop_display_names << key
      end
    end

    # add building to string vector with air loops
    building = model.get_building
    loop_handles << building.handle.to_s
    loop_display_names << '*All Air Loops*'

    # make an argument for air loops
    object = open_studio::Measure::os_argument.make_choice_argument('object', loop_handles, loop_display_names, true)
    object.set_display_name('Choose an Air Loop to Alter.')
    object.set_default_value('*All Air Loops*') # if no loop is chosen this will run on all air loops
    args << object

    # todo: - change this to choice list from design document
    # make an argument to add new space true/false
    motor_eff = open_studio::Measure::os_argument.make_double_argument('motor_eff', true)
    motor_eff.set_display_name('Motor Efficiency Improvement Due to Fan Belt Improvements(%).')
    motor_eff.set_default_value(3.0)
    args << motor_eff

    # bool argument to remove existing costs
    remove_costs = open_studio::Measure::os_argument.make_bool_argument('remove_costs', true)
    remove_costs.set_display_name('Remove Baseline Costs From Effected Fans?')
    remove_costs.set_default_value(false)
    args << remove_costs

    # make an argument for material and installation cost
    material_cost = open_studio::Measure::os_argument.make_double_argument('material_cost', true)
    material_cost.set_display_name('Material and Installation Costs per Motor ($).')
    material_cost.set_default_value(0.0)
    args << material_cost

    # make an argument for demolition cost
    demolition_cost = open_studio::Measure::os_argument.make_double_argument('demolition_cost', true)
    demolition_cost.set_display_name('Demolition Costs per Motor ($).')
    demolition_cost.set_default_value(0.0)
    args << demolition_cost

    # make an argument for duration in years until costs start
    years_until_costs_start = open_studio::Measure::os_argument.make_integer_argument('years_until_costs_start', true)
    years_until_costs_start.set_display_name('Years Until Costs Start (whole years).')
    years_until_costs_start.set_default_value(0)
    args << years_until_costs_start

    # make an argument to determine if demolition costs should be included in initial construction
    demo_cost_initial_const = open_studio::Measure::os_argument.make_bool_argument('demo_cost_initial_const', true)
    demo_cost_initial_const.set_display_name('Demolition Costs Occur During Initial Construction?')
    demo_cost_initial_const.set_default_value(false)
    args << demo_cost_initial_const

    # make an argument for expected life
    expected_life = open_studio::Measure::os_argument.make_integer_argument('expected_life', true)
    expected_life.set_display_name('Expected Life (whole years).')
    expected_life.set_default_value(20)
    args << expected_life

    # make an argument for o&m cost
    om_cost = open_studio::Measure::os_argument.make_double_argument('om_cost', true)
    om_cost.set_display_name('O & M Costs per Motor ($).')
    om_cost.set_default_value(0.0)
    args << om_cost

    # make an argument for o&m frequency
    om_frequency = open_studio::Measure::os_argument.make_integer_argument('om_frequency', true)
    om_frequency.set_display_name('O & M Frequency (whole years).')
    om_frequency.set_default_value(1)
    args << om_frequency

    return args
  end

  # define what happens when the measure is cop
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validate_user_arguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    object = runner.get_optional_workspace_object_choice_value('object', user_arguments, model) # model is passed in because of argument type
    motor_eff = runner.get_double_argument_value('motor_eff', user_arguments)
    remove_costs = runner.get_bool_argument_value('remove_costs', user_arguments)
    material_cost = runner.get_double_argument_value('material_cost', user_arguments)
    demolition_cost = runner.get_double_argument_value('demolition_cost', user_arguments)
    years_until_costs_start = runner.get_integer_argument_value('years_until_costs_start', user_arguments)
    demo_cost_initial_const = runner.get_bool_argument_value('demo_cost_initial_const', user_arguments)
    expected_life = runner.get_integer_argument_value('expected_life', user_arguments)
    om_cost = runner.get_double_argument_value('om_cost', user_arguments)
    om_frequency = runner.get_integer_argument_value('om_frequency', user_arguments)

    # check the loop for reasonableness
    apply_to_all_loops = false
    loop = nil
    if object.empty?
      handle = runner.get_string_argument_value('loop', user_arguments)
      if handle.empty?
        runner.register_error('No loop was chosen.')
      else
        runner.register_error("The selected loop with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if !object.get.to_loop.empty?
        loop = object.get.to_loop.get
      elsif !object.get.to_building.empty?
        apply_to_all_loops = true
      else
        runner.register_error('Script Error - argument not showing up as loop.')
        return false
      end
    end

    # check the user_name for reasonableness
    if (motor_eff <= 1) ||  (motor_eff >= 5)
      runner.register_warning('Requested motor efficiency improvement is not between expected values of 1% and 5%')
    end
    # motor efficiency will be checked motor by motor to see warn if higher than 0.96 and error if not between or equal to 0 and 1

    # set flags to use later
    costs_requested = false

    # set values to use later
    yr0_capital_total_costs_baseline = 0
    yr0_capital_total_costs_proposed = 0

    # If demo_cost_initial_const is true then will be applied once in the lifecycle. Future replacements use the demo cost of the new construction.
    demo_costs_of_baseline_objectss = 0

    # check costs for reasonableness
    if material_cost.abs + demolition_cost.abs + om_cost.abs == 0
      runner.register_info('No costs were requested for motors improvements.')
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

    # helper that loops through lifecycle costs getting total costs under "Construction" or "Salvage" category and add to counter if occurs during year 0
    get_total_costs_for_objects = lambda do |objects|
                  runner.register_warning("Requested efficiency of #{target_motor_efficiency * 100}% for #{h_vac_component.name} is not possible. Setting motor efficiency to 100%.")
                elsif target_motor_efficiency < 0
                  h_vac_component.set_motor_efficiency(0.0)
                  runner.register_warning("Requested efficiency of #{target_motor_efficiency * 100}% for #{h_vac_component.name} is not possible. Setting motor efficiency to 0%.")
                else
                  h_vac_component.set_motor_efficiency(target_motor_efficiency)
                  runner.register_info("Changing the motor efficiency from #{initial_motor_efficiency * 100}% to #{target_motor_efficiency * 100}% for '#{h_vac_component.name}' onloop '#{loop.name}.'")
                  if target_motor_efficiency > 0.96
                    runner.register_warning("Requested efficiency for #{h_vac_component.name} is greater than 96%.")
                  end
                end
      
                # get initial year 0 cost
                yr0_capital_total_costs_baseline += get_total_costs_for_objects([h_vac_component])
      
                # demo value of baseline costs associated with unit
                demo_lc_cs = h_vac_component.life_cycle_costs
                demo_lc_cs.each do |demo_lcc|
                  if demo_lcc.category == 'Salvage'
                    demo_costs_of_baseline_objectss += demo_lcc.total_cost
                  end
                end
      
                # remove all old costs
                if !h_vac_component.life_cycle_costs.empty? && (remove_costs == true)
                  runner.register_info("Removing existing lifecycle cost objects associated with #{h_vac_component.name}")
                  removed_costs = h_vac_component.remove_life_cycle_costs
                end
      
                # add new costs
                if costs_requested == true
      
                  # adding new cost items
                  lcc_mat = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_mat - #{h_vac_component.name}", h_vac_component, material_cost, 'cost_per_each', 'Construction', expected_life, years_until_costs_start)
                  # cost for if demo_initial_construction == true is added at the end of the measure
                  lcc_demo = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_demo - #{h_vac_component.name}", h_vac_component, demolition_cost, 'cost_per_each', 'Salvage', expected_life, years_until_costs_start + expected_life)
                  lcc_om = open_studio::Model::Life_cycle_cost.create_life_cycle_cost("lcc_om - #{h_vac_component.name}", h_vac_component, om_cost, 'cost_per_each', 'Maintenance', om_frequency, 0)
      
                  # get final year 0 cost
                  yr0_capital_total_costs_proposed += get_total_costs_for_objects([h_vac_component])
      
                end
      
              end
            end
    end

    # add one time demo cost of removed windows if appropriate
    if demo_cost_initial_const == true
      building = model.get_building
      lcc_baseline_demo = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_baseline_demo', building, demo_costs_of_baseline_objectss, 'cost_per_each', 'Salvage', 0, years_until_costs_start).get # using 0 for repeat period since one time cost.
      runner.register_info("Adding one time cost of $#{neat_numbers(lcc_baseline_demo.total_cost, 0)} related to demolition of baseline objects.")

      # if demo occurs on year 0 then add to initial capital cost counter
      if lcc_baseline_demo.years_from_start == 0
        yr0_capital_total_costs_proposed += lcc_baseline_demo.total_cost
      end
    end

    if initial_motor_efficiency_values.size + missing_initial_motor_efficiency == 0
      runner.register_as_not_applicable('The affected loop(s) does not contain any fans, the model will not be altered.')
      return true
    end

    # reporting initial condition of model
    runner.register_initial_condition("The starting motor efficiency values in affected loop(s) range from #{initial_motor_efficiency_values.min * 100}% to #{initial_motor_efficiency_values.max * 100}%. Initial year 0 capital costs for affected fans is $#{neat_numbers(yr0_capital_total_costs_baseline, 0)}.")

    # reporting final condition of model
    runner.register_final_condition("#{initial_motor_efficiency_values.size + missing_initial_motor_efficiency} fans had motor efficiency values set to altered. Final year 0 capital costs for affected fans is $#{neat_numbers(yr0_capital_total_costs_proposed, 0)}.")

    return true
  end
end

# this allows the measure to be used by the application
Improve_fan_belt_efficiency.new.register_with_application

# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see
  def name
    return 'Reduce Electric Equipment Loads by Percentage'
  end

  # human readable description
  def description
    return 'Reduce electric equipment loads. This will affect equipment that have a, power, power per area (lpd), or power per person value. This can be applied to the entire building or a specific space type. A positive percentage represents an increase electric equipment power, while a negative percentage can be used for an increase in electric equipment power.'
  end

  # human readable description of modeling approach
  def modeler_description
    return 'Loop through all electric equipment objects in the specified space type or the entire building. Clone the definition if it has not already been cloned, rename and adjust the power based on the specified percentage. Link the new definition to the existing electric equipment instance. Loop through objects first in space types and then in spaces, but only for spaces that are in the specified space type, unless entire building has been chosen.'
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

    # add building to string vector with space type
    building = model.get_building
    space_type_handles << building.handle.to_s
    space_type_display_names << '*Entire Building*'

    # make a choice argument for space type
    space_type = open_studio::Measure::os_argument.make_choice_argument('space_type', space_type_handles, space_type_display_names)
    space_type.set_display_name('Apply the Measure to a Specific Space Type or to the Entire Model')
    space_type.set_default_value('*Entire Building*') # if no space type is chosen this will run on the entire building
    args << space_type

    # make an argument for reduction percentage
    elec_equip_power_reduction_percent = open_studio::Measure::os_argument.make_double_argument('elec_equip_power_reduction_percent', true)
    elec_equip_power_reduction_percent.set_display_name('Electric Equipment Power Reduction')
    elec_equip_power_reduction_percent.set_default_value(30.0)
    elec_equip_power_reduction_percent.set_units('%')
    args << elec_equip_power_reduction_percent

    # make an argument for material and installation cost
    material_and_installation_cost = open_studio::Measure::os_argument.make_double_argument('material_and_installation_cost', true)
    material_and_installation_cost.set_display_name('Increase in Material and Installation Cost for Electric Equipment per Floor Area')
    material_and_installation_cost.set_default_value(0.0)
    material_and_installation_cost.set_units('%')
    args << material_and_installation_cost

    # make an argument for demolition cost
    demolition_cost = open_studio::Measure::os_argument.make_double_argument('demolition_cost', true)
    demolition_cost.set_display_name('Increase in Demolition Costs for Electric Equipment per Floor Area')
    demolition_cost.set_default_value(0.0)
    demolition_cost.set_units('%')
    args << demolition_cost

    # make an argument for years until costs start
    years_until_costs_start = open_studio::Measure::os_argument.make_integer_argument('years_until_costs_start', true)
    years_until_costs_start.set_display_name('Years Until Costs Start')
    years_until_costs_start.set_default_value(0)
    years_until_costs_start.set_units('whole years')
    args << years_until_costs_start

    # make a choice argument for when demo costs occur
    demo_cost_initial_const = open_studio::Measure::os_argument.make_bool_argument('demo_cost_initial_const', true)
    demo_cost_initial_const.set_display_name('Demolition Costs Occur During Initial Construction')
    demo_cost_initial_const.set_default_value(false)
    args << demo_cost_initial_const

    # make an argument for expected life
    expected_life = open_studio::Measure::os_argument.make_integer_argument('expected_life', true)
    expected_life.set_display_name('Expected Life')
    expected_life.set_default_value(15)
    expected_life.set_units('whole years')
    args << expected_life

    # make an argument for O & M cost
    om_cost = open_studio::Measure::os_argument.make_double_argument('om_cost', true)
    om_cost.set_display_name('Increase O & M Costs for Electric Equipment per Floor Area')
    om_cost.set_default_value(0.0)
    om_cost.set_units('%')
    args << om_cost

    # make an argument for O & M frequency
    om_frequency = open_studio::Measure::os_argument.make_integer_argument('om_frequency', true)
    om_frequency.set_display_name('O & M Frequency')
    om_frequency.set_default_value(1)
    om_frequency.set_units('whole years')
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
    object = runner.get_optional_workspace_object_choice_value('space_type', user_arguments, model)
    elec_equip_power_reduction_percent = runner.get_double_argument_value('elec_equip_power_reduction_percent', user_arguments)
    material_and_installation_cost = runner.get_double_argument_value('material_and_installation_cost', user_arguments)
    demolition_cost = runner.get_double_argument_value('demolition_cost', user_arguments)
    years_until_costs_start = runner.get_integer_argument_value('years_until_costs_start', user_arguments)
    demo_cost_initial_const = runner.get_bool_argument_value('demo_cost_initial_const', user_arguments)
    expected_life = runner.get_integer_argument_value('expected_life', user_arguments)
    om_cost = runner.get_double_argument_value('om_cost', user_arguments)
    om_frequency = runner.get_integer_argument_value('om_frequency', user_arguments)

    # check the space_type for reasonableness and see if measure should run on space type or on the entire building
    apply_to_building = false
    space_type = nil
    if object.empty?
      handle = runner.get_string_argument_value('space_type', user_arguments)
      if handle.empty?
        runner.register_error('No space type was chosen.')
      else
        runner.register_error("The selected space type with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if !object.get.to_space_type.empty?
        space_type = object.get.to_space_type.get
      elsif !object.get.to_building.empty?
        apply_to_building = true
      else
        runner.register_error('Script Error - argument not showing up as space type or building.')
        return false
      end
    end

    # check the elec_equip_power_reduction_percent and for reasonableness
    if elec_equip_power_reduction_percent > 100
      runner.register_error('Please Enter a Value less than or equal to 100 for the Electric Equipment Power Reduction Percentage.')
      return false
    elsif elec_equip_power_reduction_percent == 0
      runner.register_info('No electric electric equipment power adjustment requested, but some life cycle costs may still be affected.')
    elsif (elec_equip_power_reduction_percent < 1) && (elec_equip_power_reduction_percent > -1)
      runner.register_warning("A Electric Equipment Power Reduction Percentage of #{elec_equip_power_reduction_percent} percent is abnormally low.")
    elsif elec_equip_power_reduction_percent > 90
      runner.register_warning("A Electric Equipment Power Reduction Percentage of #{elec_equip_power_reduction_percent} percent is abnormally high.")
    elsif elec_equip_power_reduction_percent < 0
      runner.register_info('The requested value for electric equipment power reduction percentage was negative. This will result in an increase in electric eqipment power.')
    end

    # check lifecycle cost arguments for reasonableness
    if material_and_installation_cost < -100
      runner.register_error("Material and Installation Cost percentage increase can't be less than -100.")
      return false
    end

    if demolition_cost < -100
      runner.register_error("Demolition Cost percentage increase can't be less than -100.")
      return false
    end

    if years_until_costs_start < 0
      runner.register_error('Enter an integer greater than or equal to 0 for Years Until Costs Start.')
      return false
    end

    if expected_life < 1
      runner.register_error('Enter an integer greater than or equal to 1 for Expected Life.')
      return false
    end

    if om_cost < -100
      runner.register_error("O & M Cost percentage increase can't be less than -100.")
      return false
    end

    if om_frequency < 1
      runner.register_error('Choose an integer greater than 0 for O & M Frequency.')
    end

    # helper to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure.
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

    # helper def to add to demo cost related to baseline objects
    def add_to_baseline_demo_cost_counter(baseline_object, demo_cost_initial_const)
      counter = 0
      if demo_cost_initial_const == true
        baseline_object_lccs = baseline_object.life_cycle_costs
        baseline_object_lccs.each do |baseline_object_lcc|
          if baseline_object_lcc.category == 'Salvage'
            counter += baseline_object_lcc.total_cost
          end
        end
      end
      return counter
    end

    # def to alter performance and life cycle costs of objects
    def alter_performance_and_lcc(object, elec_equip_power_reduction_percent, material_and_installation_cost, demolition_cost, om_cost, years_until_costs_start, expected_life, om_frequency, runner)
      # edit clone based on percentage reduction
      new_def = object
      if !new_def.design_level.empty?
        new_electric_equipment_level = new_def.set_design_level(new_def.design_level.get - (new_def.design_level.get * elec_equip_power_reduction_percent * 0.01))
      elsif !new_def.wattsper_space_floor_area.empty?
        new_electric_equipment_per_area = new_def.set_wattsper_space_floor_area(new_def.wattsper_space_floor_area.get - (new_def.wattsper_space_floor_area.get * elec_equip_power_reduction_percent * 0.01))
      elsif !new_def.wattsper_person.empty?
        new_electric_equipment_per_person = new_def.set_wattsper_person(new_def.wattsper_person.get - (new_def.wattsper_person.get * elec_equip_power_reduction_percent * 0.01))
      else
        runner.register_warning("'#{new_def.name}' is used by one or more instances and has no load values. Its performance was not altered.")
      end

      new_def_lc_cs = new_def.life_cycle_costs
      if new_def_lc_cs.empty?
        if material_and_installation_cost.abs + demolition_cost.abs + om_cost.abs != 0
          runner.register_warning("'#{new_def.name}' had no life cycle cost objects. No cost was added for it.")
        end
      else
        new_def_lc_cs.each do |new_def_lcc|
          case new_def_lcc.category
          when 'Construction'
            new_def_lcc.set_cost(new_def_lcc.cost * (1 + (material_and_installation_cost / 100)))
            new_def_lcc.set_years_from_start(years_until_costs_start) # just uses argument value, does not need existing value
            new_def_lcc.set_repeat_period_years(expected_life) # just uses argument value, does not need existing value
          when 'Salvage'
            new_def_lcc.set_cost(new_def_lcc.cost * (1 + (demolition_cost / 100)))
            new_def_lcc.set_years_from_start(years_until_costs_start + expected_life) # just uses argument value, does not need existing value
            new_def_lcc.set_repeat_period_years(expected_life) # just uses argument value, does not need existing value
          when 'Maintenance'
            new_def_lcc.set_cost(new_def_lcc.cost * (1 + (om_cost / 100)))
            new_def_lcc.set_repeat_period_years(om_frequency) # just uses argument value, does not need existing value
          end

          # reset any month durations
          new_def_lcc.reset_repeat_period_months
          new_def_lcc.reset_months_from_start
        end

      end
    end

    # Initialize variables
    demo_costs_of_baseline_objectss = 0
    yr0_capital_total_costs = 0

    # make a hash of old defs and new electric equipment defs
    cloned_elecequip_defs = {}

    # get space types in model
    if apply_to_building
      space_types = model.get_space_types
    else
      space_types = []
      space_types << space_type # only run on a single space type
    end

    # loop through space types
    space_types.each do |space_type|
      next if space_type.spaces.size <= 0

      space_type_equipments = space_type.electric_equipment
      space_type_equipments.each do |space_type_equipment|
        new_def = nil

        # clone def if it has not already been cloned
        exist_def = space_type_equipment.electric_equipment_definition
        if cloned_elecequip_defs[exist_def.name.get.to_s].nil?
          # clone rename and add to hash
          new_def = exist_def.clone(model)
          new_def_name = new_def.set_name("#{exist_def.name.get} - #{elec_equip_power_reduction_percent} percent reduction")
          new_def = new_def.to_electric_equipment_definition.get
          cloned_elecequip_defs[exist_def.name.get.to_s] = new_def

          # add demo cost of object being removed to one counter for one time demo cost for baseline objects
          demo_costs_of_baseline_objectss += add_to_baseline_demo_cost_counter(exist_def, demo_cost_initial_const)

          # call def to alter performance and life cycle costs
          alter_performance_and_lcc(new_def, elec_equip_power_reduction_percent, material_and_installation_cost, demolition_cost, om_cost, years_until_costs_start, expected_life, om_frequency, runner)

        else
          new_def = cloned_elecequip_defs[exist_def.name.get.to_s]
        end

        # link instance with clone and rename
        updated_instance = space_type_equipment.set_electric_equipment_definition(new_def.to_electric_equipment_definition.get)
        updated_instance_name = space_type_equipment.set_name("#{space_type_equipment.name} #{elec_equip_power_reduction_percent} percent reduction")
      end
    end

    # getting spaces in the model
    spaces = model.get_spaces

    # get space types in model
    if apply_to_building
      spaces = model.get_spaces
    else
      if !space_type.spaces.empty?
        spaces = space_type.spaces # only run on a single space type
      end
    end

    spaces.each do |space|
      space_equipments = space.electric_equipment
      space_equipments.each do |space_equipment|
        # clone def if it has not already been cloned
        exist_def = space_equipment.electric_equipment_definition
        if cloned_elecequip_defs.any? { |k, v| k.to_s == exist_def.name.get.to_s }
          new_def = cloned_elecequip_defs[exist_def.name.get.to_s]
        else
          # clone rename and add to hash
          new_def = exist_def.clone(model)
          new_def_name = new_def.set_name("#{new_def.name} - #{elec_equip_power_reduction_percent} percent reduction")
          cloned_elecequip_defs[exist_def.name.get] = new_def
          new_def = new_def.to_electric_equipment_definition.get

          # add demo cost of object being removed to one counter for one time demo cost for baseline objects
          demo_costs_of_baseline_objectss += add_to_baseline_demo_cost_counter(exist_def, demo_cost_initial_const)

          # call def to alter performance and life cycle costs
          alter_performance_and_lcc(new_def, elec_equip_power_reduction_percent, material_and_installation_cost, demolition_cost, om_cost, years_until_costs_start, expected_life, om_frequency, runner)

        end

        # link instance with clone and rename
        updated_instance = space_equipment.set_electric_equipment_definition(new_def.to_electric_equipment_definition.get)
        updated_instance_name = space_equipment.set_name("#{space_equipment.name} #{elec_equip_power_reduction_percent} percent reduction")
      end
    end

    if cloned_elecequip_defs.empty?
      runner.register_as_not_applicable('No electric equipment objects were found in the specified space type(s).')
    end

    # get final electric equipment costs to use in final condition
    yr0_capital_total_costs += get_total_costs_for_objects(model.get_electric_equipment_definitions)

    # add one time demo cost of removed electric equipment if appropriate
    if demo_cost_initial_const == true
      building = model.get_building
      lcc_baseline_demo = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_baseline_demo', building, demo_costs_of_baseline_objectss, 'cost_per_each', 'Salvage', 0, years_until_costs_start).get # using 0 for repeat period since one time cost.
      runner.register_info("Adding one time cost of $#{neat_numbers(lcc_baseline_demo.total_cost, 0)} related to demolition of baseline objects.")

      # if demo occurs on year 0 then add to initial capital cost counter
      if lcc_baseline_demo.years_from_start == 0
        yr0_capital_total_costs += lcc_baseline_demo.total_cost
      end
    end

    # report final condition
    final_building = model.get_building
    final_building_equip_power = final_building.electric_equipment_power
    # Convert W/m^2 to W/ft^2 (1 m^2 = 10.764 ft^2)
    final_building_epd = final_building.electric_equipment_power_per_floor_area * 10.764
    runner.register_final_condition("The model's final building electric equipment power was  #{neat_numbers(final_building_equip_power, 0)} watts, an electric equipment power density of #{neat_numbers(final_building_epd)} w/ft^2. Initial capital costs associated with the improvements are $#{neat_numbers(yr0_capital_total_costs, 0)}.")

    return true
  end
end

# this allows the measure to be used by the application
Reduce_electric_equipment_loads_by_percentage.new.register_with_application

# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see
  def name
    return 'Add Overhangs by Projection Factor'
  end

  # human readable description
  def description
    return 'Add overhangs by projection factor to specified windows. The projection factor is the overhang depth divided by the window height. This can be applied to windows by the closest cardinal direction. If baseline model contains overhangs made by this measure, they will be replaced. Optionally the measure can delete any pre-existing space shading surfaces.'
  end

  # human readable description of modeling approach
  def modeler_description
    return "If requested then delete existing space shading surfaces. Then loop through exterior windows. If the requested cardinal direction is the closest to the window, then add the overhang. Name the shading surface the same as the window but append with '-Overhang'.  If a space shading surface of that name already exists, then delete it before making the new one. This measure has no life cycle cost arguments. You can see the economic impact of the measure by costing the construction used for the overhangs."
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make an argument for projection factor
    projection_factor = open_studio::Measure::os_argument.make_double_argument('projection_factor', true)
    projection_factor.set_display_name('Projection Factor')
    projection_factor.set_units('overhang depth / window height')
    projection_factor.set_default_value(0.5)
    args << projection_factor

    # make choice argument for facade
    choices = open_studio::String_vector.new
    choices << 'North'
    choices << 'East'
    choices << 'South'
    choices << 'West'
    facade = open_studio::Measure::os_argument.make_choice_argument('facade', choices)
    facade.set_display_name('Cardinal Direction')
    facade.set_default_value('South')
    args << facade

    # make an argument for deleting all existing space shading in the model
    remove_ext_space_shading = open_studio::Measure::os_argument.make_bool_argument('remove_ext_space_shading', true)
    remove_ext_space_shading.set_display_name('Remove Existing Space Shading Surfaces From the Model')
    remove_ext_space_shading.set_default_value(false)
    args << remove_ext_space_shading

    # populate choice argument for constructions that are applied to surfaces in the model
    construction_handles = open_studio::String_vector.new
    construction_display_names = open_studio::String_vector.new

    # putting space types and names into hash
    construction_args = model.get_constructions
    construction_args_hash = {}
    construction_args.each do |construction_arg|
      construction_args_hash[construction_arg.name.to_s] = construction_arg
    end

    # looping through sorted hash of constructions
    construction_args_hash.sort.map do |key, value|
      # only include if construction is not used on surface
      if !value.is_fenestration
        construction_handles << value.handle.to_s
        construction_display_names << key
      end
    end

    # make an argument for construction
    construction = open_studio::Measure::os_argument.make_choice_argument('construction', construction_handles, construction_display_names, false)
    construction.set_display_name('Optionally Choose a Construction for the Overhangs')
    args << construction

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
    projection_factor = runner.get_double_argument_value('projection_factor', user_arguments)
    facade = runner.get_string_argument_value('facade', user_arguments)
    remove_ext_space_shading = runner.get_bool_argument_value('remove_ext_space_shading', user_arguments)
    construction = runner.get_optional_workspace_object_choice_value('construction', user_arguments, model)

    # check reasonableness of fraction
    projection_factor_too_small = false
    if projection_factor < 0
      runner.register_error('Please enter a positive number for the projection factor.')
      return false
    elsif projection_factor < 0.1
      runner.register_warning("The requested projection factor of #{projection_factor} seems unusually small, no overhangs will be added.")
      projection_factor_too_small = true
    elsif projection_factor > 5
      runner.register_warning("The requested projection factor of #{projection_factor} seems unusually large.")
    end

    # check the construction for reasonableness
    construction_chosen = true
    if construction.empty?
      handle = runner.get_optional_string_argument_value('construction', user_arguments)
      if handle.empty?
        runner.register_info('No construction was chosen.')
        construction_chosen = false
      else
        runner.register_error("The selected construction with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
        return false
      end

    else
      if construction.get.to_construction.empty?
        runner.register_error('Script Error - argument not showing up as construction.')
        return false
      else
        construction = construction.get.to_construction.get
      end
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

    # helper to make it easier to do unit conversions on the fly.  The definition be called through this measure.
    unit_helper = lambda do |number, from_unit_string, to_unit_string|
      converted_number = Open_studio.convert(open_studio::Quantity.new(number, Open_studio.create_unit(from_unit_string).get), Open_studio.create_unit(to_unit_string).get).get.value
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

    # counter for year 0 capital costs
    yr0_capital_total_costs = 0

    # get initial construction costs and multiply by -1
    yr0_capital_total_costs += get_total_costs_for_objects.call(model.get_constructions) * -1

    # reporting initial condition of model
    number_of_existing_space_shading_surfaces = 0
    shading_groups = model.get_shading_surface_groups
    shading_groups.each do |shading_group|
      if shading_group.shading_surface_type == 'Space'
        number_of_existing_space_shading_surfaces += shading_group.shading_surfaces.size
      end
    end
    runner.register_initial_condition("The initial building had #{number_of_existing_space_shading_surfaces} space shading surfaces.")

    # delete all space shading groups if requested
    if remove_ext_space_shading && (number_of_existing_space_shading_surfaces > 0)
      num_removed = 0
      shading_groups.each do |shading_group|
        if shading_group.shading_surface_type == 'Space'
          shading_group.remove
          num_removed += 1
        end
      end
      runner.register_info("Removed all #{num_removed} space shading surface groups from the model.")
    end

    # flag for not applicable
    overhang_added = false

    # undefined variable that needs to be defined
    offset = 0

    # loop through surfaces finding exterior walls with proper orientation
    sub_surfaces = model.get_sub_surfaces
    sub_surfaces.each do |s|
      next if s.outside_boundary_condition != 'Outdoors'
      next if s.sub_surface_type == 'Skylight'
      next if s.sub_surface_type == 'Door'
      next if s.sub_surface_type == 'glass_door'
      next if s.sub_surface_type == 'overhead_door'
      next if s.sub_surface_type == 'tubular_daylight_dome'
      next if s.sub_surface_type == 'tubular_daylight_diffuser'

      # get the absolute_azimuth for the surface so we can categorize it
      absolute_azimuth = Open_studio.convert(s.azimuth, 'rad', 'deg').get + s.space.get.directionof_relative_north + model.get_building.north_axis
      absolute_azimuth -= 360.0 until absolute_azimuth < 360.0

      case facade
      when 'North'
        next if !((absolute_azimuth >= 315.0) || (absolute_azimuth < 45.0))
      when 'East'
        next if !((absolute_azimuth >= 45.0) && (absolute_azimuth < 135.0))
      when 'South'
        next if !((absolute_azimuth >= 135.0) && (absolute_azimuth < 225.0))
      when 'West'
        next if !((absolute_azimuth >= 225.0) && (absolute_azimuth < 315.0))
      else
        runner.register_error("Unexpected value of facade: #{facade}.")
        return false
      end

      # delete existing overhang for this window if it exists from previously run measure
      shading_groups.each do |shading_group|
        shading_s = shading_group.shading_surfaces
        shading_s.each do |ss|
          if ss.name.to_s == "#{s.name} - Overhang"
            ss.remove
            runner.register_warning("Removed pre-existing window shade named '#{ss.name}'.")
          end
        end
      end

      if projection_factor_too_small
        # new overhang would be too small and would cause errors in open_studio
        # don't actually add it, but from the measure's perspective this worked as requested
        overhang_added = true
      else
        # add the overhang
        new_overhang = s.add_overhang_by_projection_factor(projection_factor, 0)
        if new_overhang.empty?
          ok = runner.register_warning("Unable to add overhang to #{s.brief_description} with projection factor #{projection_factor} and offset #{offset}.")
          return false if !ok
        else
          new_overhang.get.set_name("#{s.name} - Overhang")
          runner.register_info("Added overhang #{new_overhang.get.brief_description} to #{s.brief_description} with projection factor #{projection_factor} and offset 0.")
          if construction_chosen && !construction.to_construction.empty?
            new_overhang.get.set_construction(construction)
          end
          overhang_added = true
        end
      end
    end

    if !overhang_added
      runner.register_as_not_applicable("The model has exterior #{facade.downcase} walls, but no windows were found to add overhangs to.")
      return true
    end

    # get final construction costs and multiply
    yr0_capital_total_costs += get_total_costs_for_objects(model.get_constructions)

    # reporting initial condition of model
    number_of_final_space_shading_surfacesacesacesacesaces = 0
    final_shading_groups = model.get_shading_surface_groups
    final_shading_groups.each do |shading_group|
      number_of_final_space_shading_surfacesacesacesacesaces += shading_group.shading_surfaces.size
    end
    runner.register_final_condition("The final building has #{number_of_final_space_shading_surfacesacesacesacesaces} space shading surfaces. Initial capital costs associated with the improvements are $#{neat_numbers.call(yr0_capital_total_costs, 0)}.")

    return true
  end
end

# this allows the measure to be used by the application
Add_overhangs_by_projection_factor.new.register_with_application

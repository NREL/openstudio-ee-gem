# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# see the url below for information on how to write open_studio measures
# http://openstudio.nrel.gov/openstudio-measure-writing-guide

# see the url below for information on using life cycle cost objects in open_studio
# http://openstudio.nrel.gov/openstudio-life-cycle-examples

# see the url below for access to C++ documentation on model objects (click on "model" in the main window to view model objects)
# http://openstudio.nrel.gov/sites/openstudio.nrel.gov/files/nv_data/cpp_documentation_it/model/html/namespaces.html

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see, this method may be deprecated as
  # the display name in pat comes from the name field in measure.xml
  def name
    return 'temp_class_0'
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
    space_type.set_display_name('Apply the Measure to a Specific Space Type or to the Entire Model.')
    space_type.set_default_value('*Entire Building*') # if no space type is chosen this will run on the entire building
    args << space_type

    # make an argument for reduction percentage
    design_spec_outdoor_air_reduction_percent = open_studio::Measure::os_argument.make_double_argument('design_spec_outdoor_air_reduction_percent', true)
    design_spec_outdoor_air_reduction_percent.set_display_name('Design Specification Outdoor Air Reduction (%).')
    design_spec_outdoor_air_reduction_percent.set_default_value(30.0)
    args << design_spec_outdoor_air_reduction_percent

    # no cost required to reduce required amount of outdoor air. Cost increase or decrease will relate to system sizing and ongoing energy use due to change in outdoor air provided.

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
    design_spec_outdoor_air_reduction_percent = runner.get_double_argument_value('design_spec_outdoor_air_reduction_percent', user_arguments)

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

    # check the design_spec_outdoor_air_reduction_percent and for reasonableness
    if design_spec_outdoor_air_reduction_percent > 100
      runner.register_error('Please enter a value less than or equal to 100 for the Outdoor Air Requirement reduction percentage.')
      return false
    elsif design_spec_outdoor_air_reduction_percent == 0
      runner.register_info('No Outdoor Air Requirement adjustment requested, but some life cycle costs may still be affected.')
    elsif (design_spec_outdoor_air_reduction_percent < 1) && (design_spec_outdoor_air_reduction_percent > -1)
      runner.register_warning("A Outdoor Air Requirement reduction percentage of #{design_spec_outdoor_air_reduction_percent} percent is abnormally low.")
    elsif design_spec_outdoor_air_reduction_percent > 90
      runner.register_warning("A Outdoor Air Requirement reduction percentage of #{design_spec_outdoor_air_reduction_percent} percent is abnormally high.")
    elsif design_spec_outdoor_air_reduction_percent < 0
      runner.register_info('The requested value for Outdoor Air Requirement reduction percentage was negative. This will result in an increase in the Outdoor Air Requirement.')
    end

    # helper to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure.
    # round to 0 or 2)
    neat_numbers = lambda do |number, roundto = 2|
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # get space design_spec_outdoor_air_objects objects used in the model
    design_spec_outdoor_air_objects = model.get_design_specification_outdoor_airs
    # todo: - it would be nice to give ranges for different calculation methods but would take some work.

    # counters needed for measure
    altered_instances = 0

    # reporting initial condition of model
    if design_spec_outdoor_air_objects.empty?
      runner.register_initial_condition('The initial model did not contain any design specification outdoor air.')
    else
      runner.register_initial_condition("The initial model contained #{design_spec_outdoor_air_objects.size} design specification outdoor air objects.")
    end

    # get space types in model
    building = model.building.get
    if apply_to_building
      space_types = model.get_space_types
      affected_area_si = building.floor_area
    else
      space_types = []
      space_types << space_type # only run on a single space type
      affected_area_si = space_type.floor_area
    end

    # split apart any shared uses of design specification outdoor air
    design_spec_outdoor_air_objects.each do |design_spec_outdoor_air_object|
      direct_use_count = design_spec_outdoor_air_object.direct_use_count
      next if direct_use_count <= 1

      direct_uses = design_spec_outdoor_air_object.sources
      original_cloned = false

      # adjust count test for direct uses that are component data
      direct_uses.each do |direct_use|
        component_data_source = direct_use.to_component_data
        if !component_data_source.empty?
          direct_use_count -= 1
        end
      end
      next if direct_use_count <= 1

      direct_uses.each do |direct_use|
        # clone and hookup design spec oa
        space_type_source = direct_use.to_space_type
        if !space_type_source.empty?
          space_type_source = space_type_source.get
          cloned_object = design_spec_outdoor_air_object.clone
          space_type_source.set_design_specification_outdoor_air(cloned_object.to_design_specification_outdoor_air.get)
          original_cloned = true
        end

        space_source = direct_use.to_space
        if !space_source.empty?
          space_source = space_source.get
          cloned_object = design_spec_outdoor_air_object.clone
          space_source.set_design_specification_outdoor_air(cloned_object.to_design_specification_outdoor_air.get)
          original_cloned = true
        end
      end

      # delete the now unused design spec oa
      if original_cloned
        runner.register_info("Making shared object #{design_spec_outdoor_air_object.name} unique.")
        design_spec_outdoor_air_object.remove
      end
    end

    # def to alter performance and life cycle costs of objects
    alter_performance = lambda do |design_spec_obj, reduction_percent, measure_runner|
      # edit clone based on percentage reduction
      if !design_spec_obj.outdoor_air_flowper_person.empty?
        new_flow_per_person = design_spec_obj.set_outdoor_air_flowper_person(design_spec_obj.outdoor_air_flowper_person.get * (1 - (reduction_percent * 0.01)))
      elsif !design_spec_obj.outdoor_air_flowper_floor_area.empty?
        new_flow_per_floor_area = design_spec_obj.set_outdoor_air_flowper_floor_area(design_spec_obj.outdoor_air_flowper_floor_area.get * (1 - (reduction_percent * 0.01)))
      elsif !design_spec_obj.outdoor_air_flow_rate.empty?
        new_flow_rate = design_spec_obj.set_outdoor_air_flow_rate(design_spec_obj.outdoor_air_flow_rate.get * (1 - (reduction_percent * 0.01)))
      elsif !design_spec_obj.air_changesper_hour.empty?
        new_air_changes_per_hour = design_spec_obj.set_air_changesper_hour(design_spec_obj.air_changesper_hour.get * (1 - (reduction_percent * 0.01)))
      else
        measure_runner.register_warning("'#{design_spec_obj.name}' is used by one or more instances and has no load values.")
      end
    end

    if altered_instances == 0
      runner.register_as_not_applicable('No design specification outdoor air objects were found in the specified space type(s).')
    end

    # report final condition
    affected_area_ip = Open_studio.convert(affected_area_si, 'm^2', 'ft^2').get
    runner.register_final_condition("#{altered_instances} design specification outdoor air objects in the model were altered affecting #{neat_numbers(affected_area_ip, 0)}(ft^2).")

    return true
  end
end

# this allows the measure to be use by the application
Reduce_ventilation_by_percentage.new.register_with_application

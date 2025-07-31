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

  # human readable description
  def description
    return 'This measure will reduce space infiltration rates by the requested percentage. A cost per square foot of building area can be added to the model.'
  end

  # human readable description of modeling approach
  def modeler_description
    return 'This can be run across a space type or the entire building. Costs will be associated with the building. If infiltration objects are removed at a later date, the costs will remain.'
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
    space_infiltration_reduction_percent = open_studio::Measure::os_argument.make_double_argument('space_infiltration_reduction_percent', true)
    space_infiltration_reduction_percent.set_display_name('Space Infiltration Power Reduction')
    space_infiltration_reduction_percent.set_default_value(30.0)
    space_infiltration_reduction_percent.set_units('%')
    args << space_infiltration_reduction_percent

    # make an argument for constant_coefficient
    constant_coefficient = open_studio::Measure::os_argument.make_double_argument('constant_coefficient', true)
    constant_coefficient.set_display_name('Constant Coefficient')
    constant_coefficient.set_default_value(1.0)
    args << constant_coefficient

    # make an argument for temperature_coefficient
    temperature_coefficient = open_studio::Measure::os_argument.make_double_argument('temperature_coefficient', true)
    temperature_coefficient.set_display_name('Temperature Coefficient')
    temperature_coefficient.set_default_value(0.0)
    args << temperature_coefficient

    # make an argument for wind_speed_coefficient
    wind_speed_coefficient = open_studio::Measure::os_argument.make_double_argument('wind_speed_coefficient', true)
    wind_speed_coefficient.set_display_name('Wind Speed Coefficient')
    wind_speed_coefficient.set_default_value(0.0)
    args << wind_speed_coefficient

    # make an argument for wind_speed_squared_coefficient
    wind_speed_squared_coefficient = open_studio::Measure::os_argument.make_double_argument('wind_speed_squared_coefficient', true)
    wind_speed_squared_coefficient.set_display_name('Wind Speed Squared Coefficient')
    wind_speed_squared_coefficient.set_default_value(0.0)
    args << wind_speed_squared_coefficient

    # make an argument for alter_coef
    alter_coef = open_studio::Measure::os_argument.make_bool_argument('alter_coef', true)
    alter_coef.set_display_name('Alter constant temperature and wind speed coefficients.')
    alter_coef.set_description('Setting this to false will result in infiltration objects that maintain the coefficients from the initial model. Setting this to true replaces the existing coefficients with the values entered for the coefficient arguments in this measure')
    alter_coef.set_default_value(true)
    args << alter_coef

    # make an argument for material and installation cost
    material_and_installation_cost = open_studio::Measure::os_argument.make_double_argument('material_and_installation_cost', true)
    material_and_installation_cost.set_display_name('Increase in Material and Installation Costs for Building per Affected Floor Area')
    material_and_installation_cost.set_default_value(0.0)
    material_and_installation_cost.set_units('$/ft^2')
    args << material_and_installation_cost

    # make an argument for O & M cost
    om_cost = open_studio::Measure::os_argument.make_double_argument('om_cost', true)
    om_cost.set_display_name('O & M Costs for Construction per Affected Floor Area')
    om_cost.set_default_value(0.0)
    om_cost.set_units('$/ft^2')
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
    space_infiltration_reduction_percent = runner.get_double_argument_value('space_infiltration_reduction_percent', user_arguments)
    constant_coefficient = runner.get_double_argument_value('constant_coefficient', user_arguments)
    temperature_coefficient = runner.get_double_argument_value('temperature_coefficient', user_arguments)
    wind_speed_coefficient = runner.get_double_argument_value('wind_speed_coefficient', user_arguments)
    wind_speed_squared_coefficient = runner.get_double_argument_value('wind_speed_squared_coefficient', user_arguments)
    alter_coef = runner.get_bool_argument_value('alter_coef', user_arguments)
    material_and_installation_cost = runner.get_double_argument_value('material_and_installation_cost', user_arguments)
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

    # check the space_infiltration_reduction_percent and for reasonableness
    if space_infiltration_reduction_percent > 100
      runner.register_error('Please enter a value less than or equal to 100 for the Space Infiltration reduction percentage.')
      return false
    elsif space_infiltration_reduction_percent == 0
      runner.register_info('No Space Infiltration adjustment requested, but infiltration coefficients or life cycle costs may still be affected.')
    elsif (space_infiltration_reduction_percent < 1) && (space_infiltration_reduction_percent > -1)
      runner.register_warning("A Space Infiltration reduction percentage of #{space_infiltration_reduction_percent} percent is abnormally low.")
    elsif space_infiltration_reduction_percent > 90
      runner.register_warning("A Space Infiltration reduction percentage of #{space_infiltration_reduction_percent} percent is abnormally high.")
    elsif space_infiltration_reduction_percent < 0
      runner.register_info('The requested value for Space Infiltration reduction percentage was negative. This will result in an increase in Space Infiltration.')
    end

    # todo: - currently not checking for negative $/ft^2 for material_and_installation_cost and om_cost, confirm if E+ will allow negative cost

    if om_frequency < 1
      runner.register_error('Choose an integer greater than 0 for O & M Frequency.')
    end

    # helper to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure.
    # round to 0 or 2)
    neat_numbers = lambda do |number, roundto = 2|
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # get space infiltration objects used in the model
    space_infiltration_objects = model.get_space_infiltration_design_flow_rates
    # todo: - it would be nice to give ranges for different calculation methods but would take some work.

    # counters needed for measure
    altered_instances = 0
    affected_area_si = 0

    # reporting initial condition of model
    if space_infiltration_objects.empty?
      runner.register_initial_condition('The initial model did not contain any space infiltration objects.')
    else
      runner.register_initial_condition("The initial model contained #{space_infiltration_objects.size} space infiltration objects.")
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

    # def to alter performance and life cycle costs of objects
    alter_performance = lambda do |object, space_infiltration_reduction_percent, constant_coefficient, temperature_coefficient, wind_speed_coefficient, wind_speed_squared_coefficient, alter_coef, runner|
      # edit clone based on percentage reduction
      if !object.design_flow_rate.empty?
        new_design_flow_rate = object.set_design_flow_rate(object.design_flow_rate.get - (object.design_flow_rate.get * space_infiltration_reduction_percent * 0.01))
      elsif !object.flowper_space_floor_area.empty?
        new_flow_per_area = object.set_flowper_space_floor_area(object.flowper_space_floor_area.get - (object.flowper_space_floor_area.get * space_infiltration_reduction_percent * 0.01))
      elsif !object.flowper_exterior_surface_area.empty?
        new_flow_per_ext_surf_area = object.set_flowper_exterior_surface_area(object.flowper_exterior_surface_area.get - (object.flowper_exterior_surface_area.get * space_infiltration_reduction_percent * 0.01))
      elsif !object.air_changesper_hour.empty?
        new_air_changes_per_hour = object.set_air_changesper_hour(object.air_changesper_hour.get - (object.air_changesper_hour.get * space_infiltration_reduction_percent * 0.01))
      else
        runner.register_warning("'#{object.name}' is used by one or more instances and has no load values.")
      end

      # only alter coefficients if requested
      if alter_coef
        object.set_constant_term_coefficient(constant_coefficient)
        object.set_temperature_term_coefficient(temperature_coefficient)
        object.set_velocity_term_coefficient(wind_speed_coefficient)
        object.set_velocity_squared_term_coefficient(wind_speed_squared_coefficient)
      end
    end

    # loop through space types
    space_types.each do |space_type|
      next if space_type.spaces.size <= 0

      space_type_infiltration_objects = space_type.space_infiltration_design_flow_rates
      space_type_infiltration_objects.each do |space_type_infiltration_object|
        # call def to alter performance and life cycle costs
        alter_performance(space_type_infiltration_object, space_infiltration_reduction_percent, constant_coefficient, temperature_coefficient, wind_speed_coefficient, wind_speed_squared_coefficient, alter_coef, runner)

        # rename
        updated_instance_name = space_type_infiltration_object.set_name("#{space_type_infiltration_object.name} #{space_infiltration_reduction_percent} percent reduction")
        altered_instances += 1
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
      space_infiltration_objects = space.space_infiltration_design_flow_rates
      space_infiltration_objects.each do |space_infiltration_object|
        # call def to alter performance and life cycle costs
        alter_performance(space_infiltration_object, space_infiltration_reduction_percent, constant_coefficient, temperature_coefficient, wind_speed_coefficient, wind_speed_squared_coefficient, alter_coef, runner)

        # rename
        updated_instance_name = space_infiltration_object.set_name("#{space_infiltration_object.name} #{space_infiltration_reduction_percent} percent reduction")
        altered_instances += 1
      end
    end

    if (altered_instances == 0) && (material_and_installation_cost == 0) && (om_cost == 0)
      runner.register_as_not_applicable('No space infiltration objects were found in the specified space type(s) and no life cycle costs were requested.')
    end

    # only add life_cy_cyle_cost_item if the user entered some non 0 cost values
    affected_area_ip = Open_studio.convert(affected_area_si, 'm^2', 'ft^2').get
    if (material_and_installation_cost != 0) || (om_cost != 0)
      lcc_mat = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_mat - Cost to Adjust Infiltration', building, affected_area_ip * material_and_installation_cost, 'cost_per_each', 'Construction', 0, 0) # 0 for expected life will result infinite expected life
      lcc_om = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_om - Cost to Adjust Infiltration', building, affected_area_ip * om_cost, 'cost_per_each', 'Maintenance', om_frequency, 0) # o&m costs start after at sane time that material and installation costs occur
      runner.register_info("Costs related to the change in infiltration are attached to the building object. Any subsequent measures that may affect infiltration won't affect these costs.")
      final_cost = lcc_mat.get.total_cost
    else
      runner.register_info('Cost arguments were not provided, no cost objects were added to the model.')
      final_cost = 0
    end

    # report final condition
    runner.register_final_condition("#{altered_instances} space infiltration objects in the model were altered affecting #{neat_numbers(affected_area_ip, 0)}(ft^2) at a total cost of $#{neat_numbers(final_cost, 0)}.")

    return true
  end
end

# this allows the measure to be use by the application
Reduce_space_infiltration_by_percentage.new.register_with_application

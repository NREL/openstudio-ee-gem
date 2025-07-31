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
    return 'Enable Demand Controlled Ventilation'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make choice argument economizer control type
    choices = open_studio::String_vector.new
    choices << 'enable_dcv'
    choices << 'disable_dcv'
    choices << 'no_change'
    dcv_type = open_studio::Measure::os_argument.make_choice_argument('dcv_type', choices, true)
    dcv_type.set_display_name('dcv Type')
    args << dcv_type

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
    dcv_type = runner.get_string_argument_value('dcv_type', user_arguments)

    # Note if dcv_type == no_change
    # and register as N/A
    if dcv_type == 'no_change'
      runner.register_as_not_applicable('N/A - User requested No Change in economizer operation.')
      return true
    end

    # short def to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure
    # round to 0 or 2)
    neat_numbers = lambda do |number, roundto = 2|
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # info for initial condition
    air_loops_changed = []

    # loop through air loops
    model.get_air_loop_hva_cs.each do |air_loop|
      # find air_loop_hvac_outdoor_air_system on loop
      air_loop.supply_components.each do |supply_component|
        h_vac_component = supply_component.to_air_loop_hvac_outdoor_air_system
        if !h_vac_component.empty?
          h_vac_component = h_vac_component.get

          # get controller_outdoor_air
          controller_oa = h_vac_component.get_controller_outdoor_air

          # get controller_mechanical_ventilation
          controller_mv = controller_oa.controller_mechanical_ventilation

          if dcv_type == 'enable_dcv'
            # check if demand control is enabled, if not, then enable it
            if controller_mv.demand_controlled_ventilation == true
              runner.register_info("#{air_loop.name} already has dcv enabled.")
            else
              controller_mv.set_demand_controlled_ventilation(true)
              runner.register_info("Enabling dcv for #{air_loop.name}.")
              air_loops_changed << air_loop
            end
          elsif dcv_type == 'disable_dcv'
            # check if demand control is disabled, if not, then disabled it
            if controller_mv.demand_controlled_ventilation == false
              runner.register_info("#{air_loop.name} already has dcv disabled.")
            else
              controller_mv.set_demand_controlled_ventilation(false)
              runner.register_info("Disabling dcv for #{air_loop.name}.")
              air_loops_changed << air_loop
            end
          end

        end
      end
    end

    # Report N/A if none of the air loops were changed
    if air_loops_changed.empty?
      runner.register_as_not_applicable('No air loops had dcv enabled or disabled.')
      return true
    end

    # Report final condition of model
    runner.register_final_condition("#{air_loops_changed.size} air loops now have demand controlled ventilation enabled.")

    return true
  end
end

# this allows the measure to be use by the application
Enable_demand_controlled_ventilation.new.register_with_application

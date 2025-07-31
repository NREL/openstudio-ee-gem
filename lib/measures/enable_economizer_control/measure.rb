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
    return 'Enable Economizer Control'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make choice argument economizer control type
    choices = open_studio::String_vector.new
    choices << 'fixed_dry_bulb'
    choices << 'no_economizer'
    choices << 'no_change'
    economizer_type = open_studio::Measure::os_argument.make_choice_argument('economizer_type', choices, true)
    economizer_type.set_display_name('Economizer Control Type')
    args << economizer_type

    # make an argument for econo_max_dry_bulb_temp
    econo_max_dry_bulb_temp = open_studio::Measure::os_argument.make_double_argument('econo_max_dry_bulb_temp', true)
    econo_max_dry_bulb_temp.set_display_name('Economizer Maximum Limit Dry-Bulb Temperature (F).')
    econo_max_dry_bulb_temp.set_default_value(69.0)
    args << econo_max_dry_bulb_temp

    # make an argument for econo_min_dry_bulb_temp
    econo_min_dry_bulb_temp = open_studio::Measure::os_argument.make_double_argument('econo_min_dry_bulb_temp', true)
    econo_min_dry_bulb_temp.set_display_name('Economizer Minimum Limit Dry-Bulb Temperature (F).')
    econo_min_dry_bulb_temp.set_default_value(-148.0)
    args << econo_min_dry_bulb_temp

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
    economizer_type = runner.get_string_argument_value('economizer_type', user_arguments)
    econo_max_dry_bulb_temp = runner.get_double_argument_value('econo_max_dry_bulb_temp', user_arguments)
    econo_min_dry_bulb_temp = runner.get_double_argument_value('econo_min_dry_bulb_temp', user_arguments)

    # Note if economizer_type == no_change
    # and register as N/A
    if economizer_type == 'no_change'
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
    loops_with_outdoor_air = false

    # loop through air loops
    model.get_air_loop_hva_cs.each do |air_loop|
      # find air_loop_hvac_outdoor_air_system on loop
      air_loop.supply_components.each do |supply_component|
        h_vac_component = supply_component.to_air_loop_hvac_outdoor_air_system
        if h_vac_component.is_initialized
          h_vac_component = h_vac_component.get

          # set flag that at least one air loop has outdoor air objects
          loops_with_outdoor_air = true

          # get controller_outdoor_air
          controller_oa = h_vac_component.get_controller_outdoor_air

          # get controller_mechanical_ventilation
          controller_mv = controller_oa.controller_mechanical_ventilation # not using this

          if controller_oa.get_economizer_control_type == economizer_type
            # report info about air loop
            runner.register_info("#{air_loop.name} already has the requested economizer type of #{economizer_type}.")
          else
            # store starting economizer type
            starting_econo_control_type = controller_oa.get_economizer_control_type

            # set economizer to the requested control type
            controller_oa.set_economizer_control_type(economizer_type)

            # report info about air loop
            runner.register_info("Changing Economizer Control Type on #{air_loop.name} from #{starting_econo_control_type} to #{controller_oa.get_economizer_control_type} and adjusting temperature and enthalpy limits per measure arguments.")

            air_loops_changed << air_loop

          end

          # set maximum limit drybulb temperature
          controller_oa.set_economizer_maximum_limit_dry_bulb_temperature(Open_studio.convert(econo_max_dry_bulb_temp, 'F', 'C').get)

          # set minimum limit drybulb temperature
          controller_oa.set_economizer_minimum_limit_dry_bulb_temperature(Open_studio.convert(econo_min_dry_bulb_temp, 'F', 'C').get)

        end
      end
    end

    # Report N/A if none of the air loops had oa systems
    if loops_with_outdoor_air == false
      runner.register_as_not_applicable('The affected loop(s) do not have any outdoor air objects.')
      return true
    end

    # Report N/A if none of the air loops were changed
    if air_loops_changed.empty?
      runner.register_as_not_applicable('No air loops had economizers added or removed.')
      return true
    end

    # Report the final condition of model
    runner.register_final_condition("#{air_loops_changed.size} air loops now have economizers.")

    return true
  end
end

# this allows the measure to be used by the application
Enable_economizer_control.new.register_with_application

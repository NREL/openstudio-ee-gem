# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# see the url below for information on how to write open_stuido measures
# http://openstudio.nrel.gov/openstudio-measure-writing-guide

# see the url below for access to C++ documentation on mondel objects (click on "model" in the main window to view model objects)
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

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validate_user_arguments(arguments(model), user_arguments)
      return false
    end

    # Define the reporting frequency
    reporting_frequency = 'hourly'

    # Define the variables to report
    variable_names = []
    variable_names << 'District Heating Rate'
    variable_names << 'District Cooling Rate'

    # Request each output variable
    variable_names.each do |variable_name|
      output_variable = open_studio::Model::Output_variable.new(variable_name, model)
      output_variable.set_reporting_frequency(reporting_frequency)
      runner.register_info("Requested output for '#{output_variable.variable_name}' at the #{output_variable.reporting_frequency} timestep.")
    end

    # Report the outlet node conditions for each plant loop in the model
    # Rename the outlet node so that it makes sense in the report
    outlet_node_variable_names = []
    outlet_node_variable_names << 'System Node Temperature'
    outlet_node_variable_names << 'System Node Setpoint Temperature'
    outlet_node_variable_names << 'System Node Mass Flow Rate'
    model.get_plant_loops.each do |plant_loop|
      outlet_node = plant_loop.supply_outlet_node
      outlet_node_name = "#{plant_loop.name} Supply Outlet Node"
      outlet_node.set_name(outlet_node_name)
      outlet_node_variable_names.each do |outlet_node_variable_name|
        output_variable = open_studio::Model::Output_variable.new(outlet_node_variable_name, model)
        output_variable.set_key_value(outlet_node_name)
        output_variable.set_reporting_frequency(reporting_frequency)
      end
    end

    return true
  end
end

# this allows the measure to be use by the application
temp_class_0.new.register_with_application

# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) 2008-2021, Alliance for Sustainable Energy, LLC.
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# (1) Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# (2) Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# (3) Neither the name of the copyright holder nor the names of any contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission from the respective party.
#
# (4) Other than as required in clauses (1) and (2), distributions in any form
# of modifications or other derivative works may not use the "OpenStudio"
# trademark, "OS", "os", or any other confusingly similar designation without
# specific prior written permission from Alliance for Sustainable Energy, LLC.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER(S) AND ANY CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER(S), ANY CONTRIBUTORS, THE
# UNITED STATES GOVERNMENT, OR THE UNITED STATES DEPARTMENT OF ENERGY, NOR ANY OF
# THEIR EMPLOYEES, BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT
# OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# *******************************************************************************

# see the URL below for information on how to write OpenStuido measures
# http://openstudio.nrel.gov/openstudio-measure-writing-guide

# see the URL below for access to C++ documentation on mondel objects (click on "model" in the main window to view model objects)
# http://openstudio.nrel.gov/sites/openstudio.nrel.gov/files/nv_data/cpp_documentation_it/model/html/namespaces.html

# start the measure
class GLHEProSetupExportLoadsforGroundHeatExchangerSizing < OpenStudio::Measure::ModelMeasure
  # define the name that a user will see, this method may be deprecated as
  # the display name in PAT comes from the name field in measure.xml
  def name
    return 'GLHEProSetupExportLoadsforGroundHeatExchangerSizing'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
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
      output_variable = OpenStudio::Model::OutputVariable.new(variable_name, model)
      output_variable.setReportingFrequency(reporting_frequency)
      runner.registerInfo("Requested output for '#{output_variable.variableName}' at the #{output_variable.reportingFrequency} timestep.")
    end

    # Report the outlet node conditions for each plant loop in the model
    # Rename the outlet node so that it makes sense in the report
    outlet_node_variable_names = []
    outlet_node_variable_names << 'System Node Temperature'
    outlet_node_variable_names << 'System Node Setpoint Temperature'
    outlet_node_variable_names << 'System Node Mass Flow Rate'
    model.getPlantLoops.each do |plant_loop|
      outlet_node = plant_loop.supplyOutletNode
      outlet_node_name = "#{plant_loop.name} Supply Outlet Node"
      outlet_node.setName(outlet_node_name)
      outlet_node_variable_names.each do |outlet_node_variable_name|
        output_variable = OpenStudio::Model::OutputVariable.new(outlet_node_variable_name, model)
        output_variable.setKeyValue(outlet_node_name)
        output_variable.setReportingFrequency(reporting_frequency)
      end
    end

    return true
  end
end

# this allows the measure to be use by the application
GLHEProSetupExportLoadsforGroundHeatExchangerSizing.new.registerWithApplication

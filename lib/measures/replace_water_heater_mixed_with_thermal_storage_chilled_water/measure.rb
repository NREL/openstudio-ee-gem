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

# see the URL below for information on how to write OpenStudio measures
# http://nrel.github.io/OpenStudio-user-documentation/reference/measure_writing_guide/

# start the measure
class ReplaceWaterHeaterMixedWithThermalStorageChilledWater < OpenStudio::Measure::ModelMeasure
  # human readable name
  def name
    return 'Replace Water Heater Mixed with Thermal Storage Chilled Water'
  end

  # human readable description
  def description
    return 'This measure is a quick fix for GUI issue that prevents putting thermal storage on two plant loops.'
  end

  # human readable description of modeling approach
  def modeler_description
    return 'The model in this case used a water heater mixed as a place holder. This measure will take a string argument, and will replace the water heater with a new thermal storage chilled water object.'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    # the name of the water heater to replace
    wh_name = OpenStudio::Measure::OSArgument.makeStringArgument('wh_name', true)
    wh_name.setDisplayName('Name of Water Heater to Replace')
    wh_name.setDescription('This object will be replaced with a new Thermal Storage Chilled Water object.')
    wh_name.setDefaultValue('CHW Tank Placeholder')
    args << wh_name

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    wh_name = runner.getStringArgumentValue('wh_name', user_arguments)

    # check the wh_name for reasonableness
    if wh_name.empty?
      runner.registerError('Empty water heater name was entered.')
      return false
    end

    # report initial condition of model
    runner.registerInitialCondition("The building started with #{model.getThermalStorageChilledWaterStratifieds.size} chilled water objects.")

    # create thermal storage object
    new_chilled_water = OpenStudio::Model::ThermalStorageChilledWaterStratified.new(model)
    # puts new_chilled_water

    placeholder = nil

    # loop through plant loops and swap objects
    model.getPlantLoops.each do |plant_loop|
      puts "Checking #{plant_loop.name}"

      plant_loop.supplyComponents.each do |component|
        if component.name.to_s == wh_name
          placeholder = component
          puts "found #{component.name}"

          # swap components
          supply_inlet_node = component.to_WaterToWaterComponent.get.supplyInletModelObject.get.to_Node.get
          new_chilled_water.addToNode(supply_inlet_node)
          demand_inlet_node = component.to_WaterToWaterComponent.get.demandInletModelObject.get.to_Node.get
          new_chilled_water.addToNode(demand_inlet_node)

        end
      end
    end

    # remove unused water heater from the model
    if !placeholder.nil?
      puts 'Removing water heater'
      placeholder.remove
    end

    # report final condition of model
    runner.registerFinalCondition("The building finished with #{model.getThermalStorageChilledWaterStratifieds.size} chilled water objects.")

    return true
  end
end

# register the measure to be used by the application
ReplaceWaterHeaterMixedWithThermalStorageChilledWater.new.registerWithApplication

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
# http://openstudio.nrel.gov/openstudio-measure-writing-guide

# see the URL below for information on using life cycle cost objects in OpenStudio
# http://openstudio.nrel.gov/openstudio-life-cycle-examples

# see the URL below for access to C++ documentation on model objects (click on "model" in the main window to view model objects)
# http://openstudio.nrel.gov/sites/openstudio.nrel.gov/files/nv_data/cpp_documentation_it/model/html/namespaces.html

# start the measure
class GLHEProGFunctionImport < OpenStudio::Measure::ModelMeasure
  # define the name that a user will see, this method may be deprecated as
  # the display name in PAT comes from the name field in measure.xml
  def name
    return 'GLHEProGFunctionImport'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = OpenStudio::Measure::OSArgumentVector.new

    # make an argument for location of G Function .idf file
    g_function_path = OpenStudio::Measure::OSArgument.makeStringArgument('g_function_path', true)
    g_function_path.setDisplayName('G Function File Path (C:/g_function.idf)')
    args << g_function_path

    # Find the names of all plant loops in the model that contain both a
    # district heating and district cooling object
    loop_names = OpenStudio::StringVector.new
    loop_handles = OpenStudio::StringVector.new
    model.getPlantLoops.each do |loop|
      dist_htg_name = nil
      dist_clg_name = nil
      loop.supplyComponents.each do |sc|
        if sc.to_DistrictHeating.is_initialized
          dist_htg_name = sc.name.get
        elsif sc.to_DistrictCooling.is_initialized
          dist_clg_name = sc.name.get
        end
      end

      if dist_htg_name && dist_clg_name
        loop_names << loop.name.get
        loop_handles << loop.handle.to_s
      end
    end

    # make an argument for plant loops
    object = OpenStudio::Measure::OSArgument.makeChoiceArgument('object', loop_handles, loop_names, true)
    object.setDisplayName('Select plant loop to add GLHX to')
    args << object

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # Use the built-in error checking
    if !runner.validateUserArguments(arguments(model), user_arguments)
      return false
    end

    # Assign the user inputs to variables
    g_function_path = runner.getStringArgumentValue('g_function_path', user_arguments)
    object = runner.getOptionalWorkspaceObjectChoiceValue('object', user_arguments, model)

    # Check to make sure the g function file exists
    if !File.exist?(g_function_path)
      runner.registerError("The G Function file '#{g_function_path}' could not be found.")
      return false
    end

    # Check the loop selection
    loop = nil
    if object.empty?
      handle = runner.getDoubleArgumentValue('object', user_arguments)
      if handle.empty?
        runner.registerError('No loop was chosen.')
      else
        runner.registerError("The selected loop with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if object.get.to_PlantLoop.is_initialized
        loop = object.get.to_PlantLoop.get
      else
        runner.registerError('Script Error - argument not showing up as loop.')
        return false
      end
    end

    # Check the location of the GFunction
    if !File.exist?(g_function_path)
      runner.registerError("Coulnd't find the G Function file.  Check file path and try again: '#{g_function_path}'.")
    end

    # Remove the district heating and district cooling objects from the loop
    loop.supplyComponents.each do |sc|
      if sc.to_DistrictHeating.is_initialized || sc.to_DistrictCooling.is_initialized
        sc.remove
        runner.registerInfo("Removed #{sc.name} from #{loop.name}.")
      end
    end

    # Fix up the IDF file (GLHEPro exports slightly malformed IDF)
    idf_text = nil
    File.open(g_function_path, 'r') { |f| idf_text = f.read }
    idf_text = idf_text.gsub('GROUND HEAT EXCHANGER:VERTICAL,', 'GROUNDHEATEXCHANGER:VERTICAL,')
    idf_text = idf_text.gsub(' :,', ',')
    File.open(g_function_path, 'w') { |f2| f2.puts idf_text }

    # Remove the setpointmanager from the supply outlet node
    # TODO: this might be necessary?

    # Add a GLHX to the loop
    glhx = OpenStudio::Model::GroundHeatExchangerVertical.new(model)
    glhx.setName("GLHX for #{loop.name}")
    loop.addSupplyBranchForComponent(glhx)
    runner.registerInfo("Added GLHX to #{loop.name}.")

    # Read the input parameters from the G Function .idf file
    g_function_file = OpenStudio::Workspace.load(g_function_path).get
    glhx_idf = g_function_file.getObjectsByType('GROUNDHEATEXCHANGER:VERTICAL'.to_IddObjectType)[0]
    max_flow = glhx_idf.getDouble(3).get
    num_boreholes = glhx_idf.getInt(4).get
    borehole_length = glhx_idf.getDouble(5).get
    borehole_radius = glhx_idf.getDouble(6).get
    ground_cond = glhx_idf.getDouble(7).get
    ground_ht_cap = glhx_idf.getDouble(8).get
    specific_heat = glhx_idf.getDouble(9).get
    t_ground = glhx_idf.getDouble(10).get
    vol_flowrate = glhx_idf.getDouble(11).get
    grout_cond = glhx_idf.getDouble(12).get
    pipe_cond = glhx_idf.getDouble(13).get
    fluid_cond = glhx_idf.getDouble(14).get
    # runner.registerInfo("fluid_cond = #{fluid_cond}")
    fluid_density = glhx_idf.getDouble(15).get
    # runner.registerInfo("fluid_density = #{fluid_density}")
    fluid_visc = glhx_idf.getDouble(16).get
    # runner.registerInfo("fluid_visc = #{fluid_visc}")
    pipe_diam = glhx_idf.getDouble(17).get
    # runner.registerInfo("pipe_diam = #{pipe_diam}")
    u_tube_sep = glhx_idf.getDouble(18).get
    # runner.registerInfo("u_tube_sep = #{u_tube_sep}")
    pipe_wall_thick = glhx_idf.getDouble(19).get
    # runner.registerInfo("pipe_wall_thick = #{pipe_wall_thick}")
    max_sim = glhx_idf.getInt(20).get
    # runner.registerInfo("max_sim = #{max_sim}")
    num_data_pairs = glhx_idf.getInt(21).get
    # runner.registerInfo("num_data_pairs = #{num_data_pairs}")
    reference_ratio = borehole_radius / borehole_length

    # Set the input parameters of the GLHE
    glhx.setMaximumFlowRate(max_flow)
    glhx.setNumberofBoreHoles(num_boreholes)
    glhx.setBoreHoleLength(borehole_length)
    glhx.setBoreHoleRadius(borehole_radius)
    glhx.setGroundThermalConductivity(ground_cond)
    glhx.setGroundThermalHeatCapacity(ground_ht_cap)
    glhx.setGroundTemperature(t_ground)
    glhx.setDesignFlowRate(vol_flowrate)
    glhx.setGroutThermalConductivity(grout_cond)
    glhx.setPipeThermalConductivity(pipe_cond)
    glhx.setPipeOutDiameter(pipe_diam)
    glhx.setUTubeDistance(u_tube_sep)
    glhx.setPipeThickness(pipe_wall_thick)
    glhx.setMaximumLengthofSimulation(max_sim)
    glhx.setGFunctionReferenceRatio(reference_ratio)

    # Add the G Function pairs after removing all old ones
    glhx.removeAllGFunctions
    pair_range = 22..(76 * 2 + 22 - 2) # Pairs start on field 22
    pair_range.step(2) do |i|
      lntts = glhx_idf.getDouble(i)
      gfnc = glhx_idf.getDouble(i + 1)
      if lntts.empty? || gfnc.empty?
        runner.registerWarning("Pair in fields #{i} and #{i + 1} missing.")
        next
      else
        lntts = lntts.get
        gfnc = gfnc.get
      end
      # runner.registerInfo("G Function pair:  #{lntts} : #{gfnc}")
      glhx.addGFunction(lntts, gfnc)
    end

    return true
  end
end

# this allows the measure to be use by the application
GLHEProGFunctionImport.new.registerWithApplication

# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) 2008-2020, Alliance for Sustainable Energy, LLC.
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

require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'fileutils'

require_relative '../measure.rb'
require 'minitest/autorun'

class AddOverhangsByProjectionFactor_Test < Minitest::Test
  # def setup
  # end

  # def teardown
  # end

  def test_AddOverhangsByProjectionFactor_bad
    # create an instance of the measure
    measure = AddOverhangsByProjectionFactor.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(4, arguments.size)
    assert_equal('projection_factor', arguments[0].name)
    assert_equal('facade', arguments[1].name)
    assert_equal('remove_ext_space_shading', arguments[2].name)
    assert_equal('construction', arguments[3].name)

    # set argument values to bad values and run the measure
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
    projection_factor = arguments[0].clone
    assert(projection_factor.setValue('-20'))
    argument_map['projection_factor'] = projection_factor
    measure.run(model, runner, argument_map)
    result = runner.result
    assert(result.value.valueName == 'Fail')
  end

  def test_AddOverhangsByProjectionFactor_good
    # create an instance of the measure
    measure = AddOverhangsByProjectionFactor.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/OverhangTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    model.getSpaces.each do |space|
      if space.name.get =~ Regexp.new(/Space 104/)
        # should be two space shading groups
        assert_equal(2, space.shadingSurfaceGroups.size)
      else
        # should be no space shading groups
        assert_equal(0, space.shadingSurfaceGroups.size)
      end
    end

    # get arguments
    arguments = measure.arguments(model)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
    projection_factor = arguments[0].clone
    assert(projection_factor.setValue(0.5))
    argument_map['projection_factor'] = projection_factor
    facade = arguments[1].clone
    assert(facade.setValue('South'))
    argument_map['facade'] = facade
    remove_ext_space_shading = arguments[2].clone
    assert(remove_ext_space_shading.setValue(true))
    argument_map['remove_ext_space_shading'] = remove_ext_space_shading
    construction = arguments[3].clone
    assert(construction.setValue('000_Interior Partition'))
    argument_map['construction'] = construction
    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    assert_equal(0, result.warnings.size)
    assert_equal(4, result.info.size)

    model.getSpaces.each do |space|
      if space.name.get =~ Regexp.new(/Space 101/) || space.name.get =~ Regexp.new(/Space 103/) || space.name.get =~ Regexp.new(/Space 104/)
        # should be one space shading groups
        assert_equal(1, space.shadingSurfaceGroups.size)
      else
        # should be no space shading groups
        assert_equal(0, space.shadingSurfaceGroups.size)
      end
    end

    # save the model
    # puts "saving model"
    # output_file_path = OpenStudio::Path.new('C:\SVN_Utilities\OpenStudio\measures\test.osm')
    # model.save(output_file_path,true)

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # get arguments
    arguments = measure.arguments(model)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
    projection_factor = arguments[0].clone
    assert(projection_factor.setValue(0.0))
    argument_map['projection_factor'] = projection_factor
    facade = arguments[1].clone
    assert(facade.setValue('South'))
    argument_map['facade'] = facade
    remove_ext_space_shading = arguments[2].clone
    assert(remove_ext_space_shading.setValue(true))
    argument_map['remove_ext_space_shading'] = remove_ext_space_shading
    construction = arguments[3].clone
    assert(construction.setValue('000_Interior Partition'))
    argument_map['construction'] = construction
    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    assert_equal(1, result.warnings.size)
    assert_equal(1, result.info.size)

    model.getSpaces.each do |space|
      # should be no space shading groups
      assert_equal(0, space.shadingSurfaceGroups.size)
    end

    # save the model
    # puts "saving model"
    # output_file_path = OpenStudio::Path.new('C:\SVN_Utilities\OpenStudio\measures\test2.osm')
    # model.save(output_file_path,true)
  end

  def test_AddOverhangsByProjectionFactor_good_noDefault
    # create an instance of the measure
    measure = AddOverhangsByProjectionFactor.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/OverhangTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments
    arguments = measure.arguments(model)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
    projection_factor = arguments[0].clone
    assert(projection_factor.setValue(0.5))
    argument_map['projection_factor'] = projection_factor
    facade = arguments[1].clone
    assert(facade.setValue('South'))
    argument_map['facade'] = facade
    remove_ext_space_shading = arguments[2].clone
    assert(remove_ext_space_shading.setValue(false))
    argument_map['remove_ext_space_shading'] = remove_ext_space_shading
    construction = arguments[3].clone

    argument_map['construction'] = construction
    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.warnings.size == 1)
    assert(result.info.size == 4)

    # save the model
    # puts "saving model"
    # output_file_path = OpenStudio::Path.new('C:\SVN_Utilities\OpenStudio\measures\test.osm')
    # model.save(output_file_path,true)
  end
end

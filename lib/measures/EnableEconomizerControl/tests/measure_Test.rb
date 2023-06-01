# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'fileutils'

require_relative '../measure.rb'
require 'minitest/autorun'

class EnableEconomizerControl_Test < Minitest::Test
  def test_EnableEconomizerControl_single_loop
    # create an instance of the measure
    measure = EnableEconomizerControl.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(3, arguments.size)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/0320_ModelWithHVAC_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # set argument values to good values and run the measure on model with spaces
    arguments = measure.arguments(model)
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    economizer_type = arguments[count += 1].clone
    assert(economizer_type.setValue('FixedDryBulb'))
    argument_map['economizer_type'] = economizer_type

    econoMaxDryBulbTemp = arguments[count += 1].clone
    assert(econoMaxDryBulbTemp.setValue(72))
    argument_map['econoMaxDryBulbTemp'] = econoMaxDryBulbTemp

    econoMinDryBulbTemp = arguments[count += 1].clone
    assert(econoMinDryBulbTemp.setValue(-150))
    argument_map['econoMinDryBulbTemp'] = econoMinDryBulbTemp

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    # assert(result.warnings.size == 2)
    # assert(result.info.size == 1)
  end

  # test on all loops

  # test warning values

  # test bad values

  # test model with some economizers on and type set to No Economiser
end

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

class ReduceVentilationByPercentage_Test < Minitest::Test
  def test_ReduceVentilationByPercentage_01_BadInputs
    # create an instance of the measure
    measure = ReduceVentilationByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(2, arguments.size)

    # fill in argument_map
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('*Entire Building*'))
    argument_map['space_type'] = space_type

    design_spec_outdoor_air_reduction_percent = arguments[count += 1].clone
    assert(design_spec_outdoor_air_reduction_percent.setValue(200.0))
    argument_map['design_spec_outdoor_air_reduction_percent'] = design_spec_outdoor_air_reduction_percent

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceVentilationByPercentage_01_BadInputs'
    # show_output(result)
    assert(result.value.valueName == 'Fail')
  end

  #################################################################################################
  #################################################################################################

  def test_ReduceVentilationByPercentage_02_HighInputs
    # create an instance of the measure
    measure = ReduceVentilationByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('*Entire Building*'))
    argument_map['space_type'] = space_type

    design_spec_outdoor_air_reduction_percent = arguments[count += 1].clone
    assert(design_spec_outdoor_air_reduction_percent.setValue(95.0))
    argument_map['design_spec_outdoor_air_reduction_percent'] = design_spec_outdoor_air_reduction_percent

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceVentilationByPercentage_02_HighInputs'
    # show_output(result)
    assert(result.value.valueName == 'Success')
    # assert(result.info.size == 1)
    # assert(result.warnings.size == 1)

    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/test_output.osm')
    model.save(output_file_path, true)
  end

  #################################################################################################
  #################################################################################################

  def test_ReduceVentilationByPercentage_04_SpaceTypeNoCosts
    # create an instance of the measure
    measure = ReduceVentilationByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('MultipleLights one LPD one Load x5 multiplier Same Schedule'))
    argument_map['space_type'] = space_type

    design_spec_outdoor_air_reduction_percent = arguments[count += 1].clone
    assert(design_spec_outdoor_air_reduction_percent.setValue(25.0))
    argument_map['design_spec_outdoor_air_reduction_percent'] = design_spec_outdoor_air_reduction_percent

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceVentilationByPercentage_04_SpaceTypeNoCosts'
    show_output(result)
    assert(result.value.valueName == 'Success')
    # assert(result.info.size == 0)
    # assert(result.warnings.size == 0)
  end

  #################################################################################################
  #################################################################################################

  # turning off this test until I can find the model that was used. I may have to re-create a similar model
  #   def test_ReduceVentilationByPercentage_05_SharedResource
  #
  #     # create an instance of the measure
  #     measure = ReduceVentilationByPercentage.new
  #
  #     # create an instance of a runner
  #     runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)
  #
  #     # re-load the test model
  #     translator = OpenStudio::OSVersion::VersionTranslator.new
  #     path = OpenStudio::Path.new(File.dirname(__FILE__) + "/SpaceTypesShareDesignSpecOutdoorAir.osm")
  #     model = translator.loadModel(path)
  #
  #     assert((not model.empty?))
  #     model = model.get
  #
  #     # refresh arguments
  #     arguments = measure.arguments(model)
  #
  #     # set argument values to highish values and run the measure on empty model
  #     argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
  #
  #     count = -1
  #
  #     space_type = arguments[count += 1].clone
  #     assert(space_type.setValue("*Entire Building*"))
  #     argument_map["space_type"] = space_type
  #
  #     design_spec_outdoor_air_reduction_percent = arguments[count += 1].clone
  #     assert(design_spec_outdoor_air_reduction_percent.setValue(25.0))
  #     argument_map["design_spec_outdoor_air_reduction_percent"] = design_spec_outdoor_air_reduction_percent
  #
  #     measure.run(model, runner, argument_map)
  #     result = runner.result
  #     puts "test_ReduceVentilationByPercentage_04_SpaceTypeNoCosts"
  #     #show_output(result)
  #     assert(result.value.valueName == "Success")
  #     # assert(result.info.size == 0)
  #     # assert(result.warnings.size == 0)
  #
  #   end
end

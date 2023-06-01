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

class ReduceLightingLoadsByPercentage_Test < Minitest::Test
  # def setup
  # end

  # def teardown
  # end

  def test_ReduceLightingLoadsByPercentage_01_BadInputs
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(9, arguments.size)

    # fill in argument_map
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('*Entire Building*'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(200.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(0.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.0))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_01_BadInputs'
    # show_output(result)
    assert(result.value.valueName == 'Fail')
  end

  #################################################################################################
  #################################################################################################

  def test_ReduceLightingLoadsByPercentage_02_HighInputs
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('*Entire Building*'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(95.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(0.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.0))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_02_HighInputs'
    # show_output(result)
    assert(result.value.valueName == 'NA')
    assert(result.info.size == 1)
    assert(result.warnings.size == 1)
  end

  #################################################################################################
  #################################################################################################

  def test_ReduceLightingLoadsByPercentage_03_EntireBuilding_FullyCosted
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
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

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(10.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(2.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.10))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    puts 'test_ReduceLightingLoadsByPercentage_03_EntireBuilding_FullyCosted'
    result = runner.result
    # show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.info.empty?)
    assert(result.warnings.size == 5)
  end

  def test_ReduceLightingLoadsByPercentage_03b_NoSurfacesInModel
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # remove all surfaces from test
    model.getSpaces.each do |space|
      # space.hardApplySpaceType(false)
      space.surfaces.each(&:remove)
    end

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('*Entire Building*'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(10.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(2.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.10))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    puts 'test_ReduceLightingLoadsByPercentage_03_EntireBuilding_FullyCosted'
    result = runner.result
    # show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.info.empty?)
    assert(result.warnings.size == 5)
  end

  #################################################################################################
  #################################################################################################

  def test_ReduceLightingLoadsByPercentage_04_SpaceTypeNoCosts
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01_FullyCosted.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('Multiple Lights Both LPD different schedules'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(0.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.2))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(3))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_04_SpaceTypeNoCosts'
    # show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.info.empty?)
    assert(result.warnings.empty?)
  end

  def test_ReduceLightingLoadsByPercentage_05_SpaceTypePartialCost
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01_FullyCosted.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('Multiple Lights Both LPD different schedules'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(20.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.0))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.0))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_05_SpaceTypePartialCost'
    # show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.info.empty?)
    assert(result.warnings.empty?)
  end

  def test_ReduceLightingLoadsByPercentage_06_SpaceTypeDemoInitialConst
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01_FullyCosted.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # refresh arguments
    arguments = measure.arguments(model)

    # set argument values to highish values and run the measure on empty model
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    space_type = arguments[count += 1].clone
    assert(space_type.setValue('Multiple Lights Both LPD different schedules'))
    argument_map['space_type'] = space_type

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(20.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.50))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(true))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.0))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_06_SpaceTypeDemoInitialConst'
    # show_output(result)
    assert(result.value.valueName == 'Success')
    assert(result.info.size == 1)
    assert(result.warnings.empty?)
  end

  def test_ReduceLightingLoadsByPercentage_07_EC
    # create an instance of the measure
    measure = ReduceLightingLoadsByPercentage.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # re-load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EC_QAQC.osm')
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

    lighting_power_reduction_percent = arguments[count += 1].clone
    assert(lighting_power_reduction_percent.setValue(25.0))
    argument_map['lighting_power_reduction_percent'] = lighting_power_reduction_percent

    material_and_installation_cost = arguments[count += 1].clone
    assert(material_and_installation_cost.setValue(20.0))
    argument_map['material_and_installation_cost'] = material_and_installation_cost

    demolition_cost = arguments[count += 1].clone
    assert(demolition_cost.setValue(0.50))
    argument_map['demolition_cost'] = demolition_cost

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(true))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost = arguments[count += 1].clone
    assert(om_cost.setValue(0.0))
    argument_map['om_cost'] = om_cost

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    puts 'test_ReduceLightingLoadsByPercentage_07_EC'
    show_output(result)
    assert(result.value.valueName == 'Success')
    # assert(result.info.size == 1)
    # assert(result.warnings.size == 0)
  end

  # TODO: - make a test that uses the cloned def hash data. I think I need to use the same def in multiple spaces/space types to accomplish this.

  # TODO: - make a test that uses lumiinares if I don't already have one.
end

# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require 'openstudio'
require 'openstudio/ruleset/ShowRunnerOutput'
require 'minitest/autorun'
require_relative '../measure.rb'
require 'fileutils'

class CreateVariableSpeedRTUTest < Minitest::Test
  def test_good_argument_values
    # create an instance of the measure
    measure = CreateVariableSpeedRTU.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/example_model.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments
    arguments = measure.arguments(model)
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    # create hash of argument values.
    # If the argument has a default that you want to use, you don't need it in the hash
    args_hash = {}
    args_hash['object'] = 'Packaged Rooftop Air Conditioner'
    # have not investigated reasonableness of argument values
    args_hash['rated_cc_eer'] = 15
    args_hash['three_quarter_cc_eer'] = 15
    args_hash['half_cc_eer'] = 15
    args_hash['quarter_cc_eer'] = 15
    args_hash['rated_hc_gas_efficiency'] = 0.9
    args_hash['rated_hc_cop'] = 3
    args_hash['three_quarter_hc_cop'] = 3
    args_hash['half_hc_cop'] = 3
    args_hash['quarter_hc_cop'] = 3

    # using defaults values from measure.rb for other arguments

    # populate argument with specified hash value if specified
    arguments.each do |arg|
      temp_arg_var = arg.clone
      if args_hash[arg.name]
        assert(temp_arg_var.setValue(args_hash[arg.name]))
      end
      argument_map[arg.name] = temp_arg_var
    end

    # run the measure
    measure.run(model, runner, argument_map)
    result = runner.result

    # show the output
    show_output(result)

    # assert that it ran correctly
    assert_equal('Success', result.value.valueName)
    # assert(result.info.size == 1)
    assert(result.warnings.empty?)

    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/test_output.osm')
    model.save(output_file_path, true)
  end

  def test_all_loops
    # create an instance of the measure
    measure = CreateVariableSpeedRTU.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/example_model.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments
    arguments = measure.arguments(model)
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    # create hash of argument values.
    # If the argument has a default that you want to use, you don't need it in the hash
    args_hash = {}
    args_hash['object'] = '*All CAV Air Loops*'
    # have not investigated reasonableness of argument values
    args_hash['rated_cc_eer'] = 15
    args_hash['three_quarter_cc_eer'] = 15
    args_hash['half_cc_eer'] = 15
    args_hash['quarter_cc_eer'] = 15
    args_hash['rated_hc_gas_efficiency'] = 0.9
    args_hash['rated_hc_cop'] = 3
    args_hash['three_quarter_hc_cop'] = 3
    args_hash['half_hc_cop'] = 3
    args_hash['quarter_hc_cop'] = 3

    # using defaults values from measure.rb for other arguments

    # populate argument with specified hash value if specified
    arguments.each do |arg|
      temp_arg_var = arg.clone
      if args_hash[arg.name]
        assert(temp_arg_var.setValue(args_hash[arg.name]))
      end
      argument_map[arg.name] = temp_arg_var
    end

    # run the measure
    measure.run(model, runner, argument_map)
    result = runner.result

    # show the output
    show_output(result)

    # assert that it ran correctly
    assert_equal('Success', result.value.valueName)
    # assert(result.info.size == 1)
    assert(result.warnings.empty?)

    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/test_all_loops.osm')
    model.save(output_file_path, true)
  end
end

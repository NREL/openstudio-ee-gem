# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'fileutils'

require_relative '../measure.rb'
require 'minitest/autorun'

puts "EC3 API Call:"
require 'net/http'
require 'uri'
require 'json'

# Parse the URL with query parameters
uri = URI.parse("https://api.buildingtransparency.org/api/epds?page_number=1&page_size=25&fields=id%2Copen_xpd_uuid%2Cis_failed%2Cfailures%2Cerrors%2Cwarnings%2Cdate_validity_ends%2Ccqd_sync_unlocked%2Cmy_capabilities%2Coriginal_data_format%2Ccategory%2Cdisplay_name%2Cmanufacturer%2Cplant_or_group%2Cname%2Cdescription%2Cprogram_operator%2Cprogram_operator_fkey%2Cverifier%2Cdeveloper%2Cmatched_plants_count%2Cplant_geography%2Cpcr%2Cshort_name%2Cversion%2Cdate_of_issue%2Clanguage%2Cgwp%2Cuncertainty_adjusted_gwp%2Cdeclared_unit%2Cupdated_on%2Ccorrections_count%2Cdeclaration_type%2Cbox_id%2Cis_downloadable&sort_by=-updated_on&name__like=window&description__like=window&q=windows&plant_geography=US&declaration_type=Product%20EPD")

# Create a new HTTP request
request = Net::HTTP::Get.new(uri)
request["Accept"] = "application/json"
request["Authorization"] = "Bearer z7z4qVkNNmKeXtBM41C2DTSj0Sta7h"

# Execute the request and store the response
response_body = nil
Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https", verify_mode: OpenSSL::SSL::VERIFY_NONE) do |http|
  response = http.request(request)
  response_body = JSON.parse(response.body) # Parse the JSON response
end

# Store the parsed response in an object
api_response = response_body
puts api_response
puts "Number of EPDs: #{api_response.size}"
# Output the object (optional)
api_response.each do |i|
  puts "Product Name: #{i['name']}"
  puts "Declared Unit: #{i['declared_unit']}"
  puts "Plant Geography: #{i['plant_geography'].join(', ')}"
  puts "Global Warming Potential (GWP): #{i['gwp']}"
end


class ReplaceExteriorWindowConstruction_Test < Minitest::Test

  def test_ReplaceExteriorWindowConstruction
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to bad values and run the measure
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)
    construction = arguments[0].clone
    assert(!construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction
    measure.run(model, runner, argument_map)
    result = runner.result

    assert(result.value.valueName == 'Fail')
  end

  def test_ReplaceExteriorWindowConstruction_new_construction_FullyCosted
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(5.0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(1.0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0.25))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')

    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/new_construction_FullyCosted.osm')
    model.save(output_file_path, true)
    end

  def test_ReplaceExteriorWindowConstruction_retrofit_FullyCosted
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01Costed.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(5.0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(1.0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(3))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(true))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0.25))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/retrofit_FullyCosted.osm')
    model.save(output_file_path, true)    
  end

  def test_ReplaceExteriorWindowConstruction_retrofit_MinimalCost
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(5.0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/retrofit_MinimalCost.osm')
    model.save(output_file_path, true)    
  end

  def test_ReplaceExteriorWindowConstruction_retrofit_NoCost
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/retrofit_NoCost.osm')
    model.save(output_file_path, true)    
  end

  def test_ReplaceExteriorWindowConstruction_ReverseTranslatedModel
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # load the test model
    translator = OpenStudio::OSVersion::VersionTranslator.new
    path = OpenStudio::Path.new(File.dirname(__FILE__) + '/ReverseTranslatedModel.osm')
    model = translator.loadModel(path)
    assert(!model.empty?)
    model = model.get

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue('Window Non-res Fixed'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'Success')
    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/ReverseTranslatedModel.osm')
    model.save(output_file_path, true)    
  end

  def test_ReplaceExteriorWindowConstruction_EmptySpaceNoLoadsOrSurfaces
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction.new

    # create an instance of a runner
    runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

    # make an empty model
    model = OpenStudio::Model::Model.new

    # add a space to the model without any geometry or loads, want to make sure measure works or fails gracefully
    new_space = OpenStudio::Model::Space.new(model)

    # make simple glazing material and then a construction to use it
    window_mat = OpenStudio::Model::SimpleGlazing.new(model)
    window_const = OpenStudio::Model::Construction.new(model)
    window_const.insertLayer(0, window_mat)

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(11, arguments.size)
    assert_equal('construction', arguments[0].name)
    assert(!arguments[0].hasDefaultValue)

    # set argument values to good values and run the measure on model with spaces
    argument_map = OpenStudio::Measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count += 1].clone
    assert(construction.setValue(window_const.name.to_s))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count += 1].clone
    assert(change_fixed_windows.setValue(true))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count += 1].clone
    assert(change_operable_windows.setValue(false))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count += 1].clone
    assert(remove_costs.setValue(true))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count += 1].clone
    assert(material_cost_ip.setValue(0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count += 1].clone
    assert(demolition_cost_ip.setValue(0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count += 1].clone
    assert(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count += 1].clone
    assert(demo_cost_initial_const.setValue(false))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count += 1].clone
    assert(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count += 1].clone
    assert(om_cost_ip.setValue(0))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count += 1].clone
    assert(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result
    show_output(result)
    assert(result.value.valueName == 'NA')
    # save the model to test output directory
    output_file_path = OpenStudio::Path.new(File.dirname(__FILE__) + '/output/EmptySpaceNoLoadsOrSurfaces.osm')
    model.save(output_file_path, true)    
  end
end

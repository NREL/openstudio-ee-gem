# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

# dependencies
require 'fileutils'
require 'minitest/autorun'
require 'openstudio'
require 'openstudio/measure/ShowRunnerOutput'
require 'openstudio-standards'
require_relative '../measure'

class NzeHvacTest < Minitest::Test
  def run_dir(test_name)
    # always generate test output in specially named 'output' directory so result files are not made part of the measure
    return "#{__dir__}/output/#{test_name}"
  end

  def model_output_path(test_name)
    return "#{run_dir(test_name)}/out.osm"
  end

  def sql_path(test_name)
    return "#{run_dir(test_name)}/run/eplusout.sql"
  end

  def report_path(test_name)
    return "#{run_dir(test_name)}/reports/eplustbl.html"
  end

  # applies the measure and then runs the model
  def run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                                hvac_system_type_input: 'DOAS with fan coil chiller with central air source heat pump',
                                doas_dcv_input: false,
                                hvac_system_partition_input: 'Whole Building',
                                max_unmet_hrs: 550)
    assert(File.exist?(osm_path))
    assert(File.exist?(epw_path))

    # remove prior runs if they exist
    FileUtils.rm_f(model_output_path(test_name))
    FileUtils.rm_f(sql_path(test_name))
    FileUtils.rm_f(report_path(test_name))

    # create run directory if it does not exist
    FileUtils.mkdir_p(run_dir(test_name))

    # temporarily change directory to the run directory and run the measure
    # only necessary for measures that do a sizing run
    start_dir = Dir.pwd
    begin
      Dir.chdir run_dir(test_name)

      # create an instance of the measure
      measure = NzeHvac.new

      # create an instance of a runner
      runner = OpenStudio::Measure::OSRunner.new(OpenStudio::WorkflowJSON.new)

      # load the test model
      translator = OpenStudio::OSVersion::VersionTranslator.new
      model = translator.loadModel(OpenStudio::Path.new(osm_path))
      assert(!model.empty?)
      model = model.get

      # set model weather file
      epw_file = OpenStudio::EpwFile.new(OpenStudio::Path.new(epw_path))
      OpenStudio::Model::WeatherFile.setWeatherFile(model, epw_file)
      assert(model.weatherFile.is_initialized)

      # set arguments to good values
      arguments = measure.arguments(model)
      argument_map = OpenStudio::Measure::OSArgumentMap.new

      remove_existing_hvac = arguments[0].clone
      assert(remove_existing_hvac.setValue(true))
      argument_map['remove_existing_hvac'] = remove_existing_hvac

      hvac_system_type = arguments[1].clone
      assert(hvac_system_type.setValue(hvac_system_type_input))
      argument_map['hvac_system_type'] = hvac_system_type

      doas_dcv = arguments[2].clone
      assert(doas_dcv.setValue(doas_dcv_input))
      argument_map['doas_dcv'] = doas_dcv

      hvac_system_partition = arguments[3].clone
      assert(hvac_system_partition.setValue(hvac_system_partition_input))
      argument_map['hvac_system_partition'] = hvac_system_partition

      # run the measure
      puts '\nAPPLYING MEASURE...'
      measure.run(model, runner, argument_map)
      result = runner.result

      # assert that it ran correctly
      assert(result.value.valueName == 'Success')
      assert(result.warnings.empty?)

      # show the output
      show_output(result)

      # save model
      model.save(model_output_path(test_name), true)

      # run the model
      if result.value.valueName == 'Success'
        std = Standard.build('90.1-2013')
        puts '\nRUNNING MODEL...'

        std.model_run_simulation_and_log_errors(model, run_dir(test_name))

        # check that the model ran successfully
        assert(File.exist?(sql_path(test_name)))
      end

      # check that the model ran successfully and generated a report
      assert(File.exist?(model_output_path(test_name)))
      assert(File.exist?(sql_path(test_name)))
      assert(File.exist?(report_path(test_name)))

      # set runner variables
      runner.setLastEpwFilePath(epw_path)
      runner.setLastOpenStudioModelPath(OpenStudio::Path.new(model_output_path(test_name)))
      runner.setLastEnergyPlusSqlFilePath(OpenStudio::Path.new(sql_path(test_name)))

      if !runner.lastEnergyPlusSqlFile.empty?
        sql = runner.lastEnergyPlusSqlFile.get
        model.setSqlFile(sql)

        # test for unmet hours
        errs = []
        unmet_heating_hrs = OpenstudioStandards::SqlFile.model_get_annual_occupied_unmet_heating_hours(model)
        unmet_cooling_hrs = OpenstudioStandards::SqlFile.model_get_annual_occupied_unmet_cooling_hours(model)
        unmet_hrs = OpenstudioStandards::SqlFile.model_get_annual_occupied_unmet_hours(model)
        if unmet_hrs
          if unmet_hrs > max_unmet_hrs
            errs << "For #{test_name} there were #{unmet_heating_hrs.round(1)} unmet occupied heating hours and #{unmet_cooling_hrs.round(1)} unmet occupied cooling hours (total: #{unmet_hrs.round(1)}), more than the limit of #{max_unmet_hrs}." if unmet_hrs > max_unmet_hrs
          else
            puts "There were #{unmet_heating_hrs.round(1)} unmet occupied heating hours and #{unmet_cooling_hrs.round(1)} unmet occupied cooling hours (total: #{unmet_hrs.round(1)})."
          end
        else
          errs << "For #{test_name} could not determine unmet hours; simulation may have failed."
        end

        # calculate EUIs to determine if HVAC EUI is appropriate
        annual_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2(model)
        int_lighting_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Interior Lighting').round(1)
        ext_lighting_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Exterior Lighting').round(1)
        int_equipment_elec_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Interior Equipment').round(1)
        int_equipment_gas_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Interior Equipment').round(1)
        int_equipment_eui = (int_equipment_elec_eui + int_equipment_gas_eui).round(1)
        refrigeration_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Refrigeration').round(1)
        shw_elec_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Water Systems').round(1)
        shw_gas_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Water Systems').round(1)
        shw_eui = (shw_elec_eui + shw_gas_eui).round(1)
        fan_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Fans').round(1)
        pump_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Pumps').round(1)
        cooling_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Cooling').round(1)
        heating_elec_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Heating').round(1)
        heating_gas_eui = OpenstudioStandards::SqlFile.model_get_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Heating').round(1)
        heating_eui = (heating_elec_eui + heating_gas_eui).round(1)
        hvac_eui = (fan_eui + pump_eui + cooling_eui + heating_eui).round(1)
        puts "Annual EUI (kBtu/ft^2): #{annual_eui.round(1)}, split:"
        puts "exterior lighting: #{ext_lighting_eui}"
        puts "interior lighting: #{int_lighting_eui}"
        puts "equipment: #{int_equipment_eui} (#{int_equipment_elec_eui} elec / #{int_equipment_gas_eui} gas)"
        puts "refrigeration: #{refrigeration_eui}"
        puts "service hot water: #{shw_eui} (#{shw_elec_eui} elec / #{shw_gas_eui} gas)"
        puts "HVAC #{hvac_eui} (fans: #{fan_eui}, pumps: #{pump_eui}, cooling: #{cooling_eui}, heating: #{heating_eui} (#{heating_elec_eui} elec / #{heating_gas_eui} gas))"

        # don't expect EUIs to be above 100 unless there are very high internal loads
        if (annual_eui > 100) && ((int_equipment_eui + int_lighting_eui) < 70)
          errs << "The annual eui is #{annual_eui.round(1)} kBtu/ft^2, higher than expected for an NZE building."
        end

        assert(errs.empty?, errs.join('\n'))
      end
    ensure
      # change back directory
      Dir.chdir(start_dir)
    end
  end

  # #**** TESTS ****##
  def test_number_of_arguments_and_argument_names
    # this test ensures that the current test is matched to the measure inputs
    puts "\n######\nTEST:#{__method__}\n######\n"

    # create an instance of the measure
    measure = NzeHvac.new

    # empty model
    model = OpenStudio::Model::Model.new

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    assert_equal(4, arguments.size)
    assert_equal('remove_existing_hvac', arguments[0].name)
    assert_equal('hvac_system_type', arguments[1].name)
    assert_equal('doas_dcv', arguments[2].name)
    assert_equal('hvac_system_partition', arguments[3].name)
  end

  def test_primary_school_fancoils_doas
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/primary_school_burlington.osm"
    epw_path = "#{__dir__}/USA_VT_Burlington.Intl.AP.726170_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil chiller with boiler',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_office_radiant_doas
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_chicago_exp_tstat.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with radiant slab chiller with central air source heat pump',
                              hvac_system_partition_input: 'Whole Building',
                              max_unmet_hrs: 2500.0) # TODO: - lower back to 600 hours after address issue with this test in release after 2.9.0, reased from 650 to 675 foor 3.4
  end

  def test_office_doas_vrf_per_story
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_chicago.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with VRF',
                              hvac_system_partition_input: 'One System Per Building Story')
  end

  def test_office_vav_reheat
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_chicago.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'VAV chiller with gas boiler reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_office_pvav_reheat
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_chicago.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'PVAV with gas boiler reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_mixed_use_vrf_doas
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_retail_mix_chicago.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with VRF',
                              hvac_system_partition_input: 'One System Per Building Type',
                              max_unmet_hrs: 650.0)
  end

  def test_mixed_use_gshp_doas
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_retail_mix_chicago.osm"
    epw_path = "#{__dir__}/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with water source heat pumps with ground source heat pump',
                              hvac_system_partition_input: 'Whole Building')
  end

  # this tests adding a vav reheat system to the model with high envelope and internal loads
  def test_model_with_sizing_issues
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/glass_box_baltimore.osm"
    epw_path = "#{__dir__}/USA_MD_Baltimore-Washington.Intl.AP.724060_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'VAV air-cooled chiller with central air source heat pump reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_fancoils_doas
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_houston.osm"
    epw_path = "#{__dir__}/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil air-cooled chiller with central air source heat pump',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_doas_fancoils_dcv
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_houston.osm"
    epw_path = "#{__dir__}/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil air-cooled chiller with central air source heat pump',
                              doas_dcv_input: true,
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_fancoils_doas_auto_partition
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_houston.osm"
    epw_path = "#{__dir__}/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil chiller with central air source heat pump',
                              hvac_system_partition_input: 'Automatic Partition')
  end

  def test_humid_office_vav_reheat_auto_partition
    puts "\n######\nTEST:#{__method__}\n######\n"
    osm_path = "#{__dir__}/office_houston.osm"
    epw_path = "#{__dir__}/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw"
    run_nze_hvac_measure_test(__method__, osm_path, epw_path,
                              hvac_system_type_input: 'VAV chiller with central air source heat pump reheat',
                              hvac_system_partition_input: 'Automatic Partition')
  end
end

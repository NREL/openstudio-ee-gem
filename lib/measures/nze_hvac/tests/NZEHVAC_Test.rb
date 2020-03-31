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
require 'openstudio-standards'
require 'openstudio/measure/ShowRunnerOutput'
require 'fileutils'
require 'minitest/autorun'
require_relative '../measure.rb'

class NzeHvac_Test < Minitest::Test
  # #**** HELPER SCRIPTS ****##

  def run_dir(test_name)
    # always generate test output in specially named 'output' directory so result files are not made part of the measure
    return "#{File.dirname(__FILE__)}/output/#{test_name}"
  end

  def model_output_path(test_name)
    return "#{run_dir(test_name)}/#{test_name}.osm"
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

    # create run directory if it does not exist
    if !File.exist?(run_dir(test_name))
      FileUtils.mkdir_p(run_dir(test_name))
    end
    assert(File.exist?(run_dir(test_name)))

    # change into run directory for tests
    start_dir = Dir.pwd
    Dir.chdir run_dir(test_name)

    # copy weather file and osm to test directory
    new_osm_path = "#{run_dir(test_name)}/#{File.basename(osm_path)}"
    FileUtils.cp(osm_path, new_osm_path)
    osm_path = new_osm_path
    new_epw_path = "#{run_dir(test_name)}/#{File.basename(epw_path)}"
    FileUtils.cp(epw_path, new_epw_path)
    epw_path = new_epw_path

    # remove prior runs if they exist
    if File.exist?(model_output_path(test_name))
      FileUtils.rm(model_output_path(test_name))
    end
    if File.exist?(report_path(test_name))
      FileUtils.rm(report_path(test_name))
    end

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
      std = Standard.build('NREL ZNE Ready 2017')
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
      unmet_heating_hrs = std.model_annual_occupied_unmet_heating_hours(model)
      unmet_cooling_hrs = std.model_annual_occupied_unmet_cooling_hours(model)
      unmet_hrs = std.model_annual_occupied_unmet_hours(model)
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
      annual_eui = std.model_annual_eui_kbtu_per_ft2(model)
      int_lighting_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Interior Lighting').round(1)
      ext_lighting_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Exterior Lighting').round(1)
      int_equipment_elec_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Interior Equipment').round(1)
      int_equipment_gas_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Interior Equipment').round(1)
      int_equipment_eui = (int_equipment_elec_eui + int_equipment_gas_eui).round(1)
      refrigeration_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Refrigeration').round(1)
      shw_elec_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Water Systems').round(1)
      shw_gas_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Water Systems').round(1)
      shw_eui = (shw_elec_eui + shw_gas_eui).round(1)
      fan_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Fans').round(1)
      pump_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Pumps').round(1)
      cooling_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Cooling').round(1)
      heating_elec_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Electricity', 'Heating').round(1)
      heating_gas_eui = std.model_annual_eui_kbtu_per_ft2_by_fuel_and_enduse(model, 'Natural Gas', 'Heating').round(1)
      heating_eui = (heating_elec_eui + heating_gas_eui).round(1)
      hvac_eui = (fan_eui + pump_eui + cooling_eui + heating_eui).round(1)
      puts "Annual EUI (kBtu/ft^2): #{annual_eui.round(1)}, split:"
      puts "exterior lighting: #{ext_lighting_eui}"
      puts "interior lighting: #{int_lighting_eui}"
      puts "equipment: #{int_equipment_eui} (#{int_equipment_elec_eui} elec / #{int_equipment_gas_eui} gas)"
      puts "refrigeration: #{refrigeration_eui}"
      puts "service hot water: #{shw_eui} (#{shw_elec_eui} elec / #{shw_gas_eui} gas)"
      puts "HVAC #{hvac_eui} (fans: #{fan_eui}, pumps: #{pump_eui}, cooling: #{cooling_eui}, heating: #{heating_eui} (#{heating_elec_eui} elec / #{heating_gas_eui} gas))"

      if annual_eui > 100
        # don't expect EUIs to be above 100 unless there are very high internal loads
        errs << "The annual eui is #{annual_eui.round(1)} kBtu/ft^2, higher than expected for an NZE building." unless (int_equipment_eui + int_lighting_eui) > 70
      end

      assert(errs.empty?, errs.join('\n'))
    end

    # change back directory
    Dir.chdir(start_dir)
  end

  # #**** TESTS ****##

  def test_number_of_arguments_and_argument_names
    # this test ensures that the current test is matched to the measure inputs
    test_name = 'test_number_of_arguments_and_argument_names'
    puts "\n######\nTEST:#{test_name}\n######\n"

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
    # this tests adding a fancoils with doas system to the model
    test_name = 'test_primary_school_fancoils_doas'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/primary_school_burlington.osm'
    epw_path = File.dirname(__FILE__) + '/USA_VT_Burlington.Intl.AP.726170_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil chiller with boiler',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_office_radiant_doas
    # this tests adding a radiant slab system with doas system to the model
    test_name = 'test_office_radiant_doas'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_chicago_exp_tstat.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with radiant slab chiller with central air source heat pump',
                              hvac_system_partition_input: 'Whole Building',
                              max_unmet_hrs: 650.0) # TODO: - lower back to 600 hours after address issue with this test in release after 2.9.0
  end

  def test_office_doas_vrf_per_story
    # this tests adding a doas with vrf system to the model
    test_name = 'test_office_vrf_doas_per_story'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_chicago.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with VRF',
                              hvac_system_partition_input: 'One System Per Building Story')
  end

  def test_office_vav_reheat
    # this tests adding a VAV reheat system to the model
    test_name = 'test_office_vav_reheat'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_chicago.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'VAV chiller with gas boiler reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_office_pvav_reheat
    # this tests adding a PVAV reheat system to the model
    test_name = 'test_office_pvav_reheat'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_chicago.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'PVAV with gas boiler reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_mixed_use_vrf_doas
    # this tests adding a vrf with doas system to the model
    test_name = 'test_mixed_use_vrf_doas'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_retail_mix_chicago.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with VRF',
                              hvac_system_partition_input: 'One System Per Building Type',
                              max_unmet_hrs: 650.0)
  end

  def test_mixed_use_gshp_doas
    # this tests adding a ghsp with doas system to the model
    test_name = 'test_mixed_use_gshp_doas'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_retail_mix_chicago.osm'
    epw_path = File.dirname(__FILE__) + '/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with water source heat pumps with ground source heat pump',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_model_with_sizing_issues
    # this tests adding a vav reheat system to the model with high envelope and internal loads
    test_name = 'test_model_with_sizing_issues'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/glass_box_baltimore.osm'
    epw_path = File.dirname(__FILE__) + '/USA_MD_Baltimore-Washington.Intl.AP.724060_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'VAV air-cooled chiller with central air source heat pump reheat',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_fancoils_doas
    # this tests adding a fancoils with doas system to the model
    test_name = 'test_humid_office_doas_fancoils'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_houston.osm'
    epw_path = File.dirname(__FILE__) + '/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil air-cooled chiller with central air source heat pump',
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_doas_fancoils_dcv
    # this tests adding a fancoils with doas system to the model
    test_name = 'test_humid_office_doas_fancoils_dcv'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_houston.osm'
    epw_path = File.dirname(__FILE__) + '/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil air-cooled chiller with central air source heat pump',
                              doas_dcv_input: true,
                              hvac_system_partition_input: 'Whole Building')
  end

  def test_humid_office_fancoils_doas_auto_partition
    # this tests adding a fancoils with doas system to the model with automatic partitioning
    test_name = 'test_humid_office_fancoils_doas_auto_partition'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_houston.osm'
    epw_path = File.dirname(__FILE__) + '/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'DOAS with fan coil chiller with central air source heat pump',
                              hvac_system_partition_input: 'Automatic Partition')
  end

  def test_humid_office_vav_reheat_auto_partition
    # this tests adding a vav reheat system to the model with automatic partitioning
    test_name = 'test_humid_office_vav_reheat_auto_partition'
    puts "\n######\nTEST:#{test_name}\n######\n"
    osm_path = File.dirname(__FILE__) + '/office_houston.osm'
    epw_path = File.dirname(__FILE__) + '/USA_TX_Houston-Bush.Intercontinental.AP.722430_TMY3.epw'
    run_nze_hvac_measure_test(test_name, osm_path, epw_path,
                              hvac_system_type_input: 'VAV chiller with central air source heat pump reheat',
                              hvac_system_partition_input: 'Automatic Partition')
  end
end

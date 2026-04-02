# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require 'openstudio'
require 'openstudio/ruleset/ShowRunnerOutput'
require 'minitest/autorun'
require 'fileutils'

# Note: This measure is implemented in Python, not Ruby
# This test file provides basic compatibility with the Ruby test framework
# The actual measure logic is in measure.py

class ReportRetrofitImpacts_Test < Minitest::Test
  def test_measure_exists
    # Verify the Python measure file exists
    measure_path = File.expand_path('../measure.py', __dir__)
    assert File.exist?(measure_path), "measure.py should exist at #{measure_path}"
  end

  def test_example_models_exist
    # Verify test models exist
    test_dir = File.expand_path('.', __dir__)
    
    
    assert File.exist?(File.join(measure_dir, 'Inputs', 'example_baseline.osm')), 
           'example_baseline.osm should exist in Inputs directory'
    assert File.exist?(File.join(measure_dir, 'Inputs', 'example_measure_applied.osm')), 
           'example_measure_applied.osm should exist in Inputs directory'
  end

  def test_required_python_files_exist
    # Verify supporting Python files exist
    measure_dir = File.expand_path('..', __dir__)
    
    assert File.exist?(File.join(measure_dir, 'apply_measure.py')), 
           'apply_measure.py should exist'
    
    assert File.exist?(File.join(measure_dir, 'call_RSmeans.py')), 
           'call_RSmeans.py should exist'
  end

  def test_resources_directory_exists
    # Verify resources directory and template exist
    resources_dir = File.expand_path('../resources', __dir__)
    
    assert File.directory?(resources_dir), 
           'resources directory should exist'
    
    template_path = File.join(resources_dir, 'retrofit_report_template.html')
    assert File.exist?(template_path), 
           'retrofit_report_template.html should exist in resources directory'
    
    excel_path = File.join(resources_dir, 'optimization.xlsx')
    assert File.exist?(excel_path), 
           'optimization.xlsx should exist in resources directory'
  end

  def test_output_directory_exists
    # Verify outputs directory exists
    output_dir = File.expand_path('./outputs', __dir__)
    assert File.directory?(output_dir), 
           'outputs directory should exist in tests directory'
  end

  def test_python_measure_syntax
    # Verify Python measure has valid syntax
    measure_path = File.expand_path('../measure.py', __dir__)
    
    # Use Python to check syntax
    # This will pass if Python is available and the file has valid syntax
    result = system("python -m py_compile \"#{measure_path}\"")
    
    # If Python is not available or syntax is invalid, this test will fail
    # If you don't have Python in CI, you can skip this with:
    # skip "Python not available" unless system("python --version")
    
    assert result, "measure.py should have valid Python syntax"
  end
end

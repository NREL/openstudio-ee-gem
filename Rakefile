# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require 'bundler/gem_tasks'
require 'rspec/core/rake_task'

RSpec::Core::RakeTask.new(:spec)

require 'rubocop/rake_task'
RuboCop::RakeTask.new

# Load in the rake tasks from the base extension gem
require 'openstudio/extension/rake_task'
require 'openstudio/ee_measures'
rake_task = OpenStudio::Extension::RakeTask.new
rake_task.set_extension_class(OpenStudio::EeMeasures::Extension, 'nrel/openstudio-ee-gem')

require 'openstudio_measure_tester/rake_task'
OpenStudioMeasureTester::RakeTask.new

task default: :spec

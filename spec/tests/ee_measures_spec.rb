# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

require_relative '../spec_helper'

RSpec.describe OpenStudio::EeMeasures do
  it 'has a version number' do
    expect(OpenStudio::EeMeasures::VERSION).not_to be nil
  end

  it 'has a measures directory' do
    instance = OpenStudio::EeMeasures::Extension.new
    expect(File.exist?(File.join(instance.measures_dir, 'AddDaylightSensors/'))).to be true
  end
end

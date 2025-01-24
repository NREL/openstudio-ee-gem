require 'openstudio'

class MyMeasure < OpenStudio::Measure::ModelMeasure
  def name
    return 'MyMeasure'
  end

  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # Call the Python script here
    system('python measure.py')

    return true
  end
end
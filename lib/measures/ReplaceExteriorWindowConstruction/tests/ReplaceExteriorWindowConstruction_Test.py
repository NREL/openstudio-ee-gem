# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import unittest
import shutil
import sys
import os

# Get the absolute path of the measure directory
measure_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Add it to sys.path
sys.path.append(measure_dir)

from measure import ReplaceExteriorWindowConstruction  # Import the measure script

class ReplaceExteriorWindowConstruction_Test(unittest.TestCase):

  def test_ReplaceExteriorWindowConstruction(self):
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction()

    # create an instance of a runner
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())

    # make an empty model
    model = openstudio.model.Model()

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    self.assertEqual(len(arguments), 11)
    self.assertEqual(arguments[0].name(), 'construction')
    self.assertFalse(arguments[0].hasDefaultValue())

    # set argument values to bad values and run the measure
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
    construction = arguments[0].clone()
    self.assertFalse(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction
        
    measure.run(model, runner, argument_map)
    result = runner.result()
        
    self.assertEqual(result.value().valueName(), 'Fail')

  def test_ReplaceExteriorWindowConstruction_new_construction_FullyCosted(self):
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction()

    # create an instance of a runner
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())

    # load the test model
    translator = openstudio.OSVersion.VersionTranslator()
    path = openstudio.path(__file__).parent() / 'EnvelopeAndLoadTestModel_01.osm'
    model = translator.loadModel(path)
    self.assertFalse(model.empty())
    model = model.get()

    # get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    self.assertEqual(arguments[0].name(), 'construction')
    self.assertFalse(arguments[0].hasDefaultValue())

    # set argument values to good values and run the measure on model with spaces
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count := count + 1].clone()
    self.assertTrue(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count := count + 1].clone()
    self.assertTrue(change_fixed_windows.setValue(True))
    argument_map['change_fixed_windows'] = change_fixed_windows
        
    change_operable_windows = arguments[count := count + 1].clone()
    self.assertTrue(change_operable_windows.setValue(False))
    argument_map['change_operable_windows'] = change_operable_windows
        
    remove_costs = arguments[count := count + 1].clone()
    self.assertTrue(remove_costs.setValue(True))
    argument_map['remove_costs'] = remove_costs
        
    material_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(material_cost_ip.setValue(5.0))
    argument_map['material_cost_ip'] = material_cost_ip
        
    demolition_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(demolition_cost_ip.setValue(1.0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip
        
    years_until_costs_start = arguments[count := count + 1].clone()
    self.assertTrue(years_until_costs_start.setValue(0))
    argument_map['years_until_costs_start'] = years_until_costs_start
        
    demo_cost_initial_const = arguments[count := count + 1].clone()
    self.assertTrue(demo_cost_initial_const.setValue(False))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const
        
    expected_life = arguments[count := count + 1].clone()
    self.assertTrue(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life
        
    om_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(om_cost_ip.setValue(0.25))
    argument_map['om_cost_ip'] = om_cost_ip
        
    om_frequency = arguments[count := count + 1].clone()
    self.assertTrue(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency
        
    measure.run(model, runner, argument_map)
    result = runner.result()
    print(result)  # Show output
    self.assertEqual(result.value().valueName(), 'Success')    

    # Save the model to test output directory
    output_file_path = openstudio.path(__file__).parent() / 'output/new_construction_FullyCosted.osm'
    model.save(output_file_path, True)

  def test_ReplaceExteriorWindowConstruction_retrofit_FullyCosted(self):
    # create an instance of the measure
    measure = ReplaceExteriorWindowConstruction()

    # Create an instance of a runner
    runner = openstudio.measure.OSRunner(openstudio.workflow.WorkflowJSON())

    # Load the test model
    translator = openstudio.osversion.VersionTranslator()
    path = openstudio.path(__file__).parent() / 'EnvelopeAndLoadTestModel_01Costed.osm'
    model = translator.loadModel(path)
    self.assertFalse(model.empty())
    model = model.get()

    # Get arguments and test that they are what we are expecting
    arguments = measure.arguments(model)
    self.assertEqual(len(arguments), 11)
    self.assertEqual(arguments[0].name(), 'construction')
    self.assertFalse(arguments[0].hasDefaultValue())

    # Set argument values to good values and run the measure on model with spaces
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)

    count = -1

    construction = arguments[count := count + 1].clone()
    self.assertTrue(construction.setValue('000_Exterior Window'))
    argument_map['construction'] = construction

    change_fixed_windows = arguments[count := count + 1].clone()
    self.assertTrue(change_fixed_windows.setValue(True))
    argument_map['change_fixed_windows'] = change_fixed_windows

    change_operable_windows = arguments[count := count + 1].clone()
    self.assertTrue(change_operable_windows.setValue(False))
    argument_map['change_operable_windows'] = change_operable_windows

    remove_costs = arguments[count := count + 1].clone()
    self.assertTrue(remove_costs.setValue(True))
    argument_map['remove_costs'] = remove_costs

    material_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(material_cost_ip.setValue(5.0))
    argument_map['material_cost_ip'] = material_cost_ip

    demolition_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(demolition_cost_ip.setValue(1.0))
    argument_map['demolition_cost_ip'] = demolition_cost_ip

    years_until_costs_start = arguments[count := count + 1].clone()
    self.assertTrue(years_until_costs_start.setValue(3))
    argument_map['years_until_costs_start'] = years_until_costs_start

    demo_cost_initial_const = arguments[count := count + 1].clone()
    self.assertTrue(demo_cost_initial_const.setValue(True))
    argument_map['demo_cost_initial_const'] = demo_cost_initial_const

    expected_life = arguments[count := count + 1].clone()
    self.assertTrue(expected_life.setValue(20))
    argument_map['expected_life'] = expected_life

    om_cost_ip = arguments[count := count + 1].clone()
    self.assertTrue(om_cost_ip.setValue(0.25))
    argument_map['om_cost_ip'] = om_cost_ip

    om_frequency = arguments[count := count + 1].clone()
    self.assertTrue(om_frequency.setValue(1))
    argument_map['om_frequency'] = om_frequency

    measure.run(model, runner, argument_map)
    result = runner.result()
    print(result)  # Show output
    self.assertEqual(result.value().valueName(), 'Success')

    # Save the model to test output directory
    output_file_path = openstudio.path(__file__).parent() / 'output/retrofit_FullyCosted.osm'
    model.save(output_file_path, True)

  def test_replace_exterior_window_construction_retrofit_minimal_cost():
    measure = ReplaceExteriorWindowConstruction()
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())
    
    translator = openstudio.osversion.VersionTranslator()
    path = openstudio.path(os.path.dirname(__file__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert model.is_initialized()
    model = model.get()
    
    arguments = measure.arguments(model)
    assert len(arguments) == 11
    assert arguments[0].name() == 'construction'
    assert not arguments[0].hasDefaultValue()
    
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
    count = -1
    
    argument_values = [
        ('000_Exterior Window', True, False, True, 5.0, 0, 0, False, 20, 0, 1)
    ]
    
    for value, argument in zip(argument_values, arguments):
        assert argument.setValue(value)
        argument_map[argument.name()] = argument
    
    measure.run(model, runner, argument_map)
    result = runner.result()
    assert result.value().valueName() == 'Success'
    
    output_file_path = openstudio.path(os.path.dirname(__file__) + '/output/retrofit_MinimalCost.osm')
    model.save(output_file_path, True)

def test_replace_exterior_window_construction_retrofit_no_cost():
    measure = ReplaceExteriorWindowConstruction()
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())
    
    translator = openstudio.osversion.VersionTranslator()
    path = openstudio.path(os.path.dirname(__file__) + '/EnvelopeAndLoadTestModel_01.osm')
    model = translator.loadModel(path)
    assert model.is_initialized()
    model = model.get()
    
    arguments = measure.arguments(model)
    assert len(arguments) == 11
    assert arguments[0].name() == 'construction'
    assert not arguments[0].hasDefaultValue()
    
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
    count = -1
    
    argument_values = [
        ('000_Exterior Window', True, False, True, 0, 0, 0, False, 20, 0, 1)
    ]
    
    for value, argument in zip(argument_values, arguments):
        assert argument.setValue(value)
        argument_map[argument.name()] = argument
    
    measure.run(model, runner, argument_map)
    result = runner.result()
    assert result.value().valueName() == 'Success'
    
    output_file_path = openstudio.path(os.path.dirname(__file__) + '/output/retrofit_NoCost.osm')
    model.save(output_file_path, True)

def test_replace_exterior_window_construction_reverse_translated_model():
    measure = ReplaceExteriorWindowConstruction()
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())
    
    translator = openstudio.osversion.VersionTranslator()
    path = openstudio.path(os.path.dirname(__file__) + '/ReverseTranslatedModel.osm')
    model = translator.loadModel(path)
    assert model.is_initialized()
    model = model.get()
    
    arguments = measure.arguments(model)
    assert len(arguments) == 11
    assert arguments[0].name() == 'construction'
    assert not arguments[0].hasDefaultValue()
    
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
    count = -1
    
    argument_values = [
        ('Window Non-res Fixed', True, False, True, 0, 0, 0, False, 20, 0, 1)
    ]
    
    for value, argument in zip(argument_values, arguments):
        assert argument.setValue(value)
        argument_map[argument.name()] = argument
    
    measure.run(model, runner, argument_map)
    result = runner.result()
    assert result.value().valueName() == 'Success'
    
    output_file_path = openstudio.path(os.path.dirname(__file__) + '/output/ReverseTranslatedModel.osm')
    model.save(output_file_path, True)

def test_replace_exterior_window_construction_empty_space_no_loads_or_surfaces():
    measure = ReplaceExteriorWindowConstruction()
    runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())
    
    model = openstudio.model.Model()
    new_space = openstudio.model.Space(model)
    
    window_mat = openstudio.model.SimpleGlazing(model)
    window_const = openstudio.model.Construction(model)
    window_const.insertLayer(0, window_mat)
    
    arguments = measure.arguments(model)
    assert len(arguments) == 11
    assert arguments[0].name() == 'construction'
    assert not arguments[0].hasDefaultValue()
    
    argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
    count = -1
    
    argument_values = [
        (window_const.name().get(), True, False, True, 0, 0, 0, False, 20, 0, 1)
    ]
    
    for value, argument in zip(argument_values, arguments):
        assert argument.setValue(value)
        argument_map[argument.name()] = argument
    
    measure.run(model, runner, argument_map)
    result = runner.result()
    assert result.value().valueName() == 'NA'
    
    output_file_path = openstudio.path(os.path.dirname(__file__) + '/output/EmptySpaceNoLoadsOrSurfaces.osm')
    model.save(output_file_path, True)
import unittest
import openstudio
import os

from measure import IncreaseInsulationRValueForExteriorWalls

class TestIncreaseInsulationRValueForExteriorWalls(unittest.TestCase):

    def setUp(self):
        self.measure = IncreaseInsulationRValueForExteriorWalls()
        self.runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())

    def load_model(self, filename):
        path = openstudio.path(os.path.join(os.path.dirname(__file__), filename))
        vt = openstudio.osversion.VersionTranslator()
        model = vt.loadModel(path)
        self.assertTrue(model.is_initialized())
        return model.get()

    def set_arguments(self, model, vals):
        args = self.measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        for arg in args:
            val = vals[arg.name()]
            a = arg.clone()
            if isinstance(val, bool):
                a.setValue("true" if val else "false")
            else:
                a.setValue(val)
            arg_map[arg.name()] = a
        return arg_map

    def test_bad_r_value(self):
        model = openstudio.model.Model()
        vals = {
            "r_value": 9000.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 0.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)
        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Fail")

    def test_new_construction_fully_costed(self):
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        vals = {
            "r_value": 50.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 2.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Success")
        self.assertGreaterEqual(len(result.info()), 9)
        self.assertEqual(len(result.warnings()), 2)

    def test_retrofit_fully_costed(self):
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        vals = {
            "r_value": 50.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 2.0,
            "one_time_retrofit_cost_ip": 3.5,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Success")
        self.assertGreaterEqual(len(result.info()), 14)
        self.assertEqual(len(result.warnings()), 2)

    def test_retrofit_no_cost(self):
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        vals = {
            "r_value": 50.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 0.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Success")
        self.assertGreaterEqual(len(result.info()), 4)
        self.assertEqual(len(result.warnings()), 2)

    def test_reverse_translated_model(self):
        model = self.load_model("ReverseTranslatedModel.osm")
        vals = {
            "r_value": 50.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 0.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Success")
        self.assertGreaterEqual(len(result.info()), 1)
        self.assertEqual(len(result.warnings()), 1)

    def test_empty_space_no_surfaces(self):
        model = openstudio.model.Model()
        _ = openstudio.model.Space(model)

        vals = {
            "r_value": 10.0,
            "allow_reduction": False,
            "material_cost_increase_ip": 0.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "NA")
        self.assertEqual(len(result.warnings()), 0)

    def test_allow_reduction_true(self):
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        vals = {
            "r_value": 5.0,
            "allow_reduction": True,
            "material_cost_increase_ip": 0.0,
            "one_time_retrofit_cost_ip": 0.0,
            "years_until_retrofit_cost": 0
        }
        arg_map = self.set_arguments(model, vals)

        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        self.assertEqual(result.value().valueName(), "Success")
        self.assertGreaterEqual(len(result.info()), 4)
        self.assertGreaterEqual(len(result.warnings()), 1)

    def test_no_mass_material(self):
        if openstudio.toVersionString(openstudio.openStudioVersion()) >= openstudio.toVersionString("2.5.1"):
            model = self.load_model("no_mass.osm")
            vals = {
                "r_value": 5.0,
                "allow_reduction": True,
                "material_cost_increase_ip": 0.0,
                "one_time_retrofit_cost_ip": 0.0,
                "years_until_retrofit_cost": 0
            }
            arg_map = self.set_arguments(model, vals)

            self.measure.run(model, self.runner, arg_map)
            result = self.runner.result()
            self.assertEqual(result.value().valueName(), "Success")

if __name__ == "__main__":
    unittest.main()

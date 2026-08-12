import os
import unittest

import openstudio

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

    def default_values(self):
        return {
            "r_value": 13.0,
            "analysis_period": 30,
            "gwp_statistic": "mean",
            "api_key": "dummy_key_for_test",
            "insulation_material_type": "Fiberglass Batts",
            "insulation_material_lifetime": 30,
            "insulation_thermal_conductivity": 0.0,
            "insulation_material_density": 0.0,
            "use_custom_costs": False,
            "custom_cost_per_cf": 0.0,
            "labor_cost_multiplier": 1.0,
            "overhead_profit_percent": 10.0,
            "use_exact_costline_id": False,
            "exact_costline_id": "",
        }

    def set_arguments(self, model, vals):
        args = self.measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        for arg in args:
            arg_name = arg.name()
            self.assertIn(arg_name, vals, f"Missing test value for argument: {arg_name}")
            val = vals[arg_name]
            a = arg.clone()
            if isinstance(val, bool):
                a.setValue("true" if val else "false")
            else:
                a.setValue(str(val))
            arg_map[arg_name] = a
        return arg_map

    def run_measure(self, model, overrides=None):
        vals = self.default_values()
        if overrides:
            vals.update(overrides)
        arg_map = self.set_arguments(model, vals)
        self.measure.run(model, self.runner, arg_map)
        return self.runner.result()

    def test_bad_r_value(self):
        model = openstudio.model.Model()
        result = self.run_measure(model, {"r_value": 9000.0})
        self.assertEqual(result.value().valueName(), "Fail")

    def test_no_surfaces_not_applicable(self):
        model = openstudio.model.Model()
        _ = openstudio.model.Space(model)
        result = self.run_measure(model)
        self.assertEqual(result.value().valueName(), "NA")

    def test_success_with_custom_costs(self):
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        result = self.run_measure(model, {
            "r_value": 30.0,
            "use_custom_costs": True,
            "custom_cost_per_cf": 2.5,
            "insulation_material_type": "Pure Wool Batts",
        })
        self.assertEqual(result.value().valueName(), "Success")

    def test_success_reverse_translated_model(self):
        model = self.load_model("ReverseTranslatedModel.osm")
        result = self.run_measure(model, {"r_value": 20.0})
        self.assertEqual(result.value().valueName(), "Success")


if __name__ == "__main__":
    unittest.main()

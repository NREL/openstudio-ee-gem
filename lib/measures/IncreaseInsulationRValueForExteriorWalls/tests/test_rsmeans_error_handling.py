"""
Tests for RSMeans error handling and fallback to custom costs.
Verifies that when RSMeans lookup fails (e.g., for unsupported materials like Pure Wool Batts),
appropriate error messages guide users to retry with custom cost input.
"""

import unittest
import openstudio
import os
from pathlib import Path

# Add parent directory to path to import measure
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from measure import IncreaseInsulationRValueForExteriorWalls


class TestRSMeansErrorHandling(unittest.TestCase):
    """Test RSMeans failure handling and error messaging."""

    def setUp(self):
        self.measure = IncreaseInsulationRValueForExteriorWalls()
        self.runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())

    def load_model(self, filename):
        """Load an OSM model file from tests directory."""
        test_dir = Path(__file__).parent
        model_path = test_dir / filename
        if not model_path.exists():
            self.skipTest(f"Test model {filename} not found at {model_path}")
        
        path = openstudio.path(str(model_path))
        vt = openstudio.osversion.VersionTranslator()
        model = vt.loadModel(path)
        self.assertTrue(model.is_initialized(), f"Failed to load model {filename}")
        return model.get()

    def set_arguments(self, model, vals):
        """Convert argument values dict to OSArgumentMap."""
        args = self.measure.arguments(model)
        arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
        for arg in args:
            arg_name = arg.name()
            if arg_name in vals:
                val = vals[arg_name]
                a = arg.clone()
                if isinstance(val, bool):
                    a.setValue("true" if val else "false")
                else:
                    a.setValue(str(val))
                arg_map[arg_name] = a
        return arg_map

    def test_pure_wool_batts_rsmeans_failure_error_message(self):
        """
        Test that Pure Wool Batts triggers an error when RSMeans is used
        (since Pure Wool Batts is not in INSULATION_FALLBACK_IDS).
        Verifies error message guides user to custom costs.
        """
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        
        # Configure measure with:
        # - Pure Wool Batts (unsupported in RSMeans fallback)
        # - RSMeans enabled (use_custom_costs = false)
        # - Calculate costs enabled
        vals = {
            "r_value": 30.0,
            "allow_reduction": False,
            "calculate_costs": True,
            "use_custom_costs": False,  # Force RSMeans lookup
            "custom_cost_per_sf": 0.0,
            "insulation_material_type": "Pure Wool Batts",
            "insulation_material_lifetime": 60,
            "analysis_period": 60,
            "gwp_statistic": "mean",
            "api_key": "dummy_key_for_test",
        }
        
        arg_map = self.set_arguments(model, vals)
        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        
        # Should produce error(s) related to RSMeans failure
        errors = result.errors()
        error_messages = [str(e) for e in errors]
        
        # Verify guidance message is present
        error_text = " ".join(error_messages)
        self.assertIn("Custom Cost Inputs", error_text, 
                      "Error message should suggest using custom cost input")
        self.assertIn("use_custom_costs", error_text,
                      "Error message should reference the use_custom_costs parameter")

    def test_pure_wool_batts_with_custom_cost_succeeds(self):
        """
        Test that Pure Wool Batts succeeds when custom costs are used.
        Verifies the fallback path works when RSMeans is skipped.
        """
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        
        # Configure measure with:
        # - Pure Wool Batts
        # - Custom costs enabled
        # - Reasonable cost estimate for wool batts
        vals = {
            "r_value": 30.0,
            "allow_reduction": False,
            "calculate_costs": True,
            "use_custom_costs": True,  # Use custom cost, skip RSMeans
            "custom_cost_per_sf": 2.50,  # Typical Pure Wool Batts cost
            "insulation_material_type": "Pure Wool Batts",
            "insulation_material_lifetime": 60,
            "analysis_period": 60,
            "gwp_statistic": "mean",
            "api_key": "dummy_key_for_test",
        }
        
        arg_map = self.set_arguments(model, vals)
        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        
        # Should succeed with custom cost
        self.assertEqual(result.value().valueName(), "Success",
                         f"Measure should succeed with custom costs. Errors: {result.errors()}")
        
        # Verify cost was calculated
        info_messages = [str(m) for m in result.info()]
        info_text = " ".join(info_messages)
        self.assertIn("custom_input", info_text.lower(),
                      "Info should indicate custom cost was used")

    def test_error_message_includes_retry_instructions(self):
        """
        Test that error messages include clear retry instructions.
        Verifies user guidance is complete and actionable.
        """
        model = self.load_model("EnvelopeAndLoadTestModel_01.osm")
        
        vals = {
            "r_value": 25.0,
            "allow_reduction": False,
            "calculate_costs": True,
            "use_custom_costs": False,
            "insulation_material_type": "Pure Wool Batts",
            "insulation_material_lifetime": 60,
            "analysis_period": 60,
            "gwp_statistic": "mean",
            "api_key": "dummy_key_for_test",
        }
        
        arg_map = self.set_arguments(model, vals)
        self.measure.run(model, self.runner, arg_map)
        result = self.runner.result()
        
        errors = result.errors()
        error_text = " ".join([str(e) for e in errors])
        
        # Verify key guidance elements are present
        self.assertIn("Set", error_text, "Error should include action verb")
        self.assertIn("use_custom_costs", error_text, 
                      "Should mention parameter name")
        self.assertIn("Custom Insulation Cost", error_text,
                      "Should mention custom cost parameter")


if __name__ == '__main__':
    unittest.main()

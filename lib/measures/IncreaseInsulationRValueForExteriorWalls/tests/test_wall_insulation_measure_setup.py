#!/usr/bin/env python
"""
Integration-lite tests for IncreaseInsulationRValueForExteriorWalls measure.

Covers:
- Measure file and resources exist
- Argument names include RSMeans toggles
- RSMeans parser derives conductivity from description
"""

import unittest
from pathlib import Path


class TestWallInsulationMeasureSetup(unittest.TestCase):
    def setUp(self):
        self.measure_dir = Path(__file__).parent.parent

    def test_measure_and_helper_exist(self):
        measure_path = self.measure_dir / "measure.py"
        helper_path = self.measure_dir / "resources" / "call_rsmeans_api.py"
        self.assertTrue(measure_path.exists(), "measure.py not found")
        self.assertTrue(helper_path.exists(), "resources/call_rsmeans_api.py not found")
        helper_content = helper_path.read_text(encoding="utf-8")
        self.assertNotIn("def _load_shared_helper", helper_content)
        self.assertNotIn("importlib.util", helper_content)

    def test_measure_arguments_defined(self):
        measure_path = self.measure_dir / "measure.py"
        content = measure_path.read_text(encoding="utf-8")
        required_args = [
            "calculate_costs",
            "use_custom_costs",
            "custom_cost_per_cf",
            "labor_cost_multiplier",
            "overhead_profit_percent",
            "use_exact_costline_id",
            "exact_costline_id",
        ]
        for arg_name in required_args:
            self.assertIn(arg_name, content, f"Argument '{arg_name}' not found in measure.py")

    def test_rsmeans_parser_derives_conductivity(self):
        measure_path = self.measure_dir / "measure.py"
        content = measure_path.read_text(encoding="utf-8")
        self.assertIn("extracted['conductivity_W_mK'] = parsed_k", content)
        self.assertIn("if 'rsmeans_rvalue_ip_in_description' in extracted", content)


if __name__ == "__main__":
    unittest.main()

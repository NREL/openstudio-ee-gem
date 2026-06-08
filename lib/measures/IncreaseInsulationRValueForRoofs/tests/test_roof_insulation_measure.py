#!/usr/bin/env python
"""
Integration-lite tests for IncreaseInsulationRValueForRoofs measure.

Covers:
- Measure file and resources exist
- Documentation files exist
- Argument names include cost toggles
"""

import unittest
from pathlib import Path


class TestRoofInsulationMeasureSetup(unittest.TestCase):
    # Basic file presence tests to catch missing measure artifacts early.
    def setUp(self):
        # Root folder for the measure under test.
        self.measure_dir = Path(__file__).parent.parent

    def test_measure_file_exists(self):
        # Ensure the main measure entry point exists.
        measure_path = self.measure_dir / "measure.py"
        self.assertTrue(measure_path.exists(), "measure.py not found")

    def test_resources_exist(self):
        # Validate expected resource helpers (RSMeans wrapper).
        resources_dir = self.measure_dir / "resources"
        self.assertTrue(resources_dir.exists(), "resources directory not found")
        required_files = ["call_rsmeans_api.py"]
        for filename in required_files:
            file_path = resources_dir / filename
            self.assertTrue(file_path.exists(), f"{filename} not found in resources")

    def test_documentation_exists(self):
        # Documentation should be present for setup and RSMeans usage.
        docs_dir = self.measure_dir / "docs"
        self.assertTrue(docs_dir.exists(), "docs directory not found")
        required_docs = [
            "ENVIRONMENT_SETUP.md",
            "RSMEANS_SEARCH_STRATEGY.md",
            "Increase_Insulation_Roofs.md",
        ]
        for doc in required_docs:
            doc_path = docs_dir / doc
            self.assertTrue(doc_path.exists(), f"{doc} not found in docs")

    def test_measure_arguments_defined(self):
        # Ensure cost-related arguments are declared in the measure.
        measure_path = self.measure_dir / "measure.py"
        content = measure_path.read_text(encoding="utf-8")
        required_args = [
            "use_custom_costs",
            "custom_cost_per_cf",
            "labor_cost_multiplier",
            "overhead_profit_percent",
        ]
        for arg_name in required_args:
            self.assertIn(arg_name, content, f"Argument '{arg_name}' not found in measure.py")

    def test_helper_is_local_and_decoupled(self):
        helper_path = self.measure_dir / "resources" / "call_rsmeans_api.py"
        content = helper_path.read_text(encoding="utf-8")
        self.assertNotIn("window_enhancement_call_rsmeans_api", content)
        self.assertNotIn("window_enhancement/resources", content)
        self.assertNotIn("_load_shared_helper", content)

    def test_validation_script_has_no_window_path_hack(self):
        validation_path = self.measure_dir / "resources" / "validate_enhancements.py"
        content = validation_path.read_text(encoding="utf-8")
        self.assertNotIn("window_enhancement", content)

    def test_rsmeans_parser_derives_conductivity(self):
        measure_path = self.measure_dir / "measure.py"
        content = measure_path.read_text(encoding="utf-8")
        self.assertIn("extracted['conductivity_W_mK'] = parsed_k", content)
        self.assertIn("if 'rsmeans_rvalue_ip_in_description' in extracted", content)


if __name__ == "__main__":
    unittest.main()

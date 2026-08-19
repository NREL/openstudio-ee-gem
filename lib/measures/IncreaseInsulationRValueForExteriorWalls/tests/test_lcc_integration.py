#!/usr/bin/env python
"""Tests for the current wall insulation cost and carbon contract."""

import unittest
from pathlib import Path


class TestWallInsulationCostCarbonContract(unittest.TestCase):
    """Verify volume-based cost and carbon calculations without legacy LCC objects."""

    @classmethod
    def setUpClass(cls):
        cls.measure_path = Path(__file__).parent.parent / "measure.py"
        cls.content = cls.measure_path.read_text(encoding="utf-8")

    def test_uses_incremental_r_value_for_added_material(self):
        self.assertIn("delta_r = max(0, r_value_si - max_r)", self.content)
        self.assertIn("required_thickness = delta_r * selected_k", self.content)
        self.assertIn("new_insul.setThermalResistance(delta_r)", self.content)

    def test_calculates_added_volume_from_area_and_thickness(self):
        self.assertIn("volume_m3 = area_m2 * required_thickness", self.content)
        self.assertIn(
            '"added_total_volume_m3": item["added_thickness_m"] * item["total_area_m2"]',
            self.content,
        )
        self.assertIn(
            'total_added_volume_m3 = sum(gwp_summary[idx]["added_total_volume_m3"]',
            self.content,
        )

    def test_uses_added_volume_for_embodied_carbon_and_cost(self):
        self.assertIn("total_area_m2*added_thickness_m", self.content)
        self.assertIn(
            "insulation_material_density * total_area_m2 * added_thickness_m",
            self.content,
        )
        self.assertIn('"quantity_volume": float(total_added_volume_ft3)', self.content)

    def test_writes_current_cost_and_carbon_outputs(self):
        required_features = [
            "wall_insulation_embodied_carbon_kgCO2eq",
            "wall_insulation_total_cost_with_overhead_and_profit_$",
            "wall_insulation_material_cost_$",
            "wall_insulation_labor_cost_$",
            "wall_insulation_added_volume_m3",
        ]
        for feature in required_features:
            self.assertIn(feature, self.content)

    def test_rejects_nonpositive_lifetime(self):
        self.assertIn("if insulation_material_lifetime <= 0:", self.content)
        self.assertIn("product lifetime of insulating material", self.content.lower())

    def test_does_not_require_legacy_lcc_objects(self):
        self.assertNotIn("LifeCycleCost.createLifeCycleCost", self.content)


if __name__ == "__main__":
    unittest.main(verbosity=2)

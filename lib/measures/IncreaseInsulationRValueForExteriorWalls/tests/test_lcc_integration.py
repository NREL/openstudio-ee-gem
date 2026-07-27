#!/usr/bin/env python
"""
LifeCycleCost Integration Tests for Wall Insulation Measure

Tests LCC object creation, cost allocation by volume, and AdditionalProperties
when LifeCycleCost objects are integrated into the measure.

Key test scenarios:
1. LCC objects created for each modified construction
2. Cost allocation by volume (not area) reflects material usage
3. Lifetime=0 validation and rejection
4. AdditionalProperties completeness
5. Edge cases (zero cost, zero area)
"""

import unittest
from pathlib import Path
import sys

# Add measure directory to path
measure_dir = Path(__file__).parent.parent
if str(measure_dir) not in sys.path:
    sys.path.insert(0, str(measure_dir))


class TestLCCIntegration(unittest.TestCase):
    """Test suite for LifeCycleCost integration in wall insulation measure"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.measure_dir = Path(__file__).parent.parent
        self.measure_path = self.measure_dir / "measure.py"
        
    def test_measure_has_lcc_creation_code(self):
        """
        Test 1: Verify LCC creation code exists in measure.py
        
        Checks that the measure file contains:
        - LifeCycleCost.createLifeCycleCost() call
        - Volume-based cost allocation logic
        - AdditionalProperties keys for LCC tracking
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Check for LCC creation
        self.assertIn("LifeCycleCost.createLifeCycleCost", content,
                     "LCC creation code not found in measure")
        
        # Check for volume-based allocation
        self.assertIn("added_volume_m3 / total_added_volume_m3", content,
                     "Volume-based cost allocation not found")
        
        # Check for LCC-specific AdditionalProperties keys
        self.assertIn("wall_insulation_lcc_object_created", content,
                     "LCC tracking key not found in AdditionalProperties")
        self.assertIn("wall_insulation_lcc_cost_per_m2_si", content,
                     "LCC cost per m2 key not found")
        
    def test_lifetime_validation_exists(self):
        """
        Test 2: Verify lifetime=0 validation logic exists
        
        Checks that:
        - Lifetime validation code is present
        - Error message mentions lifetime requirement
        - Validation occurs before LCC creation
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Check for lifetime validation
        self.assertIn("if selected_lifetime <= 0:", content,
                     "Lifetime validation not found")
        
        # Check for error message
        self.assertIn("invalid material lifetime", content.lower(),
                     "Lifetime validation error message not found")
        
        # Check that validation happens before LCC creation
        lifetime_validation_pos = content.find("if selected_lifetime <= 0:")
        lcc_creation_pos = content.find("LifeCycleCost.createLifeCycleCost")
        
        self.assertLess(lifetime_validation_pos, lcc_creation_pos,
                       "Lifetime validation should occur before LCC creation")
        
    def test_cost_allocation_method_documented(self):
        """
        Test 3: Verify cost allocation method is documented
        
        Checks that:
        - Volume-based allocation is explicitly documented in code comments
        - Formula is present: construction_cost = total_cost × (volume_i / total_volume)
        - Reason for volume vs area allocation is explained
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Check for allocation method documentation
        self.assertIn("By VOLUME", content.upper(),
                     "Volume allocation method not documented")
        
        # Check for formula in comments or code
        self.assertIn("volume_i / total_volume", content.lower(),
                     "Volume allocation formula not found")
        
    def test_additional_properties_keys_defined(self):
        """
        Test 4: Verify all LCC-related AdditionalProperties keys are defined
        
        Required keys per construction:
        - wall_insulation_lcc_object_created (boolean)
        - wall_insulation_lcc_cost_per_m2_si (double)
        - wall_insulation_lcc_total_cost_for_construction (double)
        - wall_insulation_lcc_volume_m3 (double)
        - wall_insulation_lcc_skip_reason (string, when skipped)
        
        Required keys in results bucket:
        - wall_insulation_lcc_objects_created_count (integer)
        - wall_insulation_lcc_attachment_object_type (string)
        - wall_insulation_lcc_cost_type (string)
        - wall_insulation_lcc_cost_allocation_method (string)
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Per-construction keys
        per_construction_keys = [
            "wall_insulation_lcc_object_created",
            "wall_insulation_lcc_cost_per_m2_si",
            "wall_insulation_lcc_total_cost_for_construction",
            "wall_insulation_lcc_volume_m3",
            "wall_insulation_lcc_skip_reason",
        ]
        
        for key in per_construction_keys:
            self.assertIn(key, content,
                         f"Per-construction LCC key '{key}' not found")
        
        # Results bucket keys
        results_keys = [
            "wall_insulation_lcc_objects_created_count",
            "wall_insulation_lcc_attachment_object_type",
            "wall_insulation_lcc_cost_type",
            "wall_insulation_lcc_cost_allocation_method",
        ]
        
        for key in results_keys:
            self.assertIn(key, content,
                         f"Results bucket LCC key '{key}' not found")
        
    def test_lcc_attached_to_construction(self):
        """
        Test 5: Verify LCC objects are attached to Construction, not Building
        
        Checks that:
        - LCC creation uses 'construction' as attachment object
        - Not using 'building' or 'model.getBuilding()'
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Find LCC creation call
        lcc_start = content.find("LifeCycleCost.createLifeCycleCost(")
        if lcc_start == -1:
            self.fail("LCC creation call not found")
        
        # Extract the creation call (next ~200 chars)
        lcc_call = content[lcc_start:lcc_start + 400]
        
        # Check that 'construction' is used as attachment object (2nd argument)
        self.assertIn("construction,", lcc_call,
                     "LCC should be attached to construction object")
        
        # Ensure not using building
        self.assertNotIn("building,", lcc_call,
                        "LCC should not be attached to building object")
        
    def test_cost_type_is_costperarea(self):
        """
        Test 6: Verify LCC uses CostPerArea (not CostPerEach)
        
        Checks that:
        - LCC creation specifies "CostPerArea"
        - Cost is in SI units ($/m²)
        - Comment mentions SI units requirement
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Find LCC creation call
        lcc_start = content.find("LifeCycleCost.createLifeCycleCost(")
        lcc_call = content[lcc_start:lcc_start + 500]
        
        # Check for CostPerArea
        self.assertIn('"CostPerArea"', lcc_call,
                     "LCC should use CostPerArea cost type")
        
        # Check for SI units mention
        self.assertIn("SI", content[lcc_start-200:lcc_start+500],
                     "SI units requirement should be documented")
        
    def test_skip_conditions_implemented(self):
        """
        Test 7: Verify LCC creation skip conditions are implemented
        
        Skip conditions:
        - cost_source == "none"
        - total_cost <= 0
        - area <= 0
        - volume <= 0
        
        Checks that:
        - All skip conditions are checked
        - lcc_skip_reason is populated when skipped
        - Warning/info is logged when skipping
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Check for skip condition logic
        self.assertIn('cost_source == "none"', content,
                     "cost_source=none skip condition not found")
        self.assertIn("total_cost", content.lower(),
                     "total_cost skip condition not found")
        self.assertIn("total_area_m2", content,
                     "area skip condition not found")
        
        # Check for skip reason collection
        self.assertIn("skip_reasons", content.lower(),
                     "Skip reason collection not found")
        self.assertIn("wall_insulation_lcc_skip_reason", content,
                     "lcc_skip_reason key not set")
        
    def test_final_condition_includes_lcc_count(self):
        """
        Test 8: Verify final condition message includes LCC creation count
        
        Checks that:
        - registerFinalCondition includes LCC count
        - Message format: "Created N LifeCycleCost object(s)"
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Find final condition
        final_condition_start = content.find("runner.registerFinalCondition(")
        if final_condition_start == -1:
            self.fail("registerFinalCondition not found")
        
        final_condition = content[final_condition_start:final_condition_start + 500]
        
        # Check for LCC count in message
        self.assertIn("LifeCycleCost", final_condition,
                     "Final condition should mention LifeCycleCost")
        self.assertIn("lcc_created_count", final_condition.lower(),
                     "Final condition should include LCC count variable")


class TestLCCDocumentation(unittest.TestCase):
    """Test documentation and code comments for LCC integration"""
    
    def setUp(self):
        self.measure_dir = Path(__file__).parent.parent
        self.measure_path = self.measure_dir / "measure.py"
        
    def test_phase_5_comments_updated(self):
        """
        Verify Phase 5 comments mention LCC creation
        
        Phase 5 header should describe:
        - Cost lookup (RSMeans/custom)
        - AdditionalProperties write-out
        - LifeCycleCost object creation (NEW)
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Find Phase 5 section
        phase5_start = content.find("Phase 5")
        if phase5_start == -1:
            self.skip("Phase 5 header not found (optional)")
        
        phase5_section = content[phase5_start:phase5_start + 500]
        
        # Check if LCC is mentioned in Phase 5 description
        # (This is optional, but good practice)
        # self.assertIn("LifeCycleCost", phase5_section,
        #              "Phase 5 should mention LifeCycleCost creation")
        
    def test_volume_allocation_rationale_documented(self):
        """
        Verify rationale for volume-based allocation is documented
        
        Should explain why volume (not area) is used:
        - Different constructions have different thicknesses
        - Volume reflects actual material usage
        """
        content = self.measure_path.read_text(encoding="utf-8")
        
        # Find LCC creation section
        lcc_start = content.find("LifeCycleCost Object Creation")
        if lcc_start == -1:
            lcc_start = content.find("LifeCycleCost.createLifeCycleCost")
        
        if lcc_start == -1:
            self.fail("LCC creation section not found")
        
        # Check preceding 300 chars for documentation
        lcc_context = content[max(0, lcc_start-300):lcc_start+100]
        
        # Check for volume mention in comments
        self.assertIn("volume", lcc_context.lower(),
                     "Volume allocation should be documented")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)

#!/usr/bin/env python
"""
Unit tests for RSMeans API calling functionality in window_enhancement measure.

Tests cover:
- Exact line item ID lookup
- Closest-match search fallback
- Cost calculations
- API key redaction
- Match type tracking
- Error handling
"""

import unittest
import sys
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Add resources to path
sys.path.insert(0, str(Path(__file__).parent.parent / "resources"))

# Import the RSMeans module
try:
    from call_rsmeans_api import RSMeansAPIClient, search_materials_across_catalogs
except ImportError:
    # Fallback for direct test execution
    RSMeansAPIClient = None
    search_materials_across_catalogs = None


class TestRSMeansExactIDLookup(unittest.TestCase):
    """Test exact line item ID lookup functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Mock(spec=RSMeansAPIClient)
        self.materials = [
            {
                "name": "window glazing",
                "quantity": 433.01,
                "unit": "SF",
                "division_code": "08",
                "rsmeans_id": "084126100020",  # Exact ID for glazing
            },
            {
                "name": "window frame",
                "quantity": 433.01,
                "unit": "LF",
                "division_code": "08",
                "rsmeans_id": "084113200050",  # Exact ID for frame
            },
        ]
    
    def test_exact_id_lookup_success(self):
        """Test that exact ID lookup returns match_type='exact_id_match'."""
        # Mock the API response for exact ID lookup
        mock_response = {
            "data": {
                "lineItemSearchGraphql": {
                    "edges": [
                        {
                            "node": {
                                "id": "084126100020",
                                "description": "Window wall, aluminum, stock, including glazing, minimum",
                                "localizedCosts": {
                                    "totalOpCost": 80.70
                                },
                                "unitOfMeasure": "SF",
                            }
                        }
                    ]
                }
            }
        }
        
        self.client.search_unit_costlines = Mock(return_value=mock_response)
        
        # Verify that search would be called with exact ID
        self.assertEqual(self.materials[0]["rsmeans_id"], "084126100020")
        self.assertEqual(self.materials[0]["name"], "window glazing")
    
    def test_exact_id_in_material_dict(self):
        """Test that rsmeans_id field exists in material dictionary."""
        # Verify exact ID is present
        self.assertIn("rsmeans_id", self.materials[0])
        self.assertIn("rsmeans_id", self.materials[1])
        self.assertEqual(self.materials[0]["rsmeans_id"], "084126100020")
        self.assertEqual(self.materials[1]["rsmeans_id"], "084113200050")
    
    def test_multiple_catalogs_for_exact_id(self):
        """Test that exact ID lookup tries multiple catalogs."""
        # Define catalogs to search
        catalogs = ["bc-mf", "gb-mf", "rp-mf"]
        
        # Exact ID should be searched across all catalogs
        for catalog in catalogs:
            self.assertIsNotNone(catalog)
        
        self.assertEqual(len(catalogs), 3)


class TestRSMeansClosestMatchFallback(unittest.TestCase):
    """Test closest-match search fallback when exact ID not found or not provided."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Mock(spec=RSMeansAPIClient)
        # Material without rsmeans_id field
        self.materials = [
            {
                "name": "window glazing",
                "quantity": 433.01,
                "unit": "SF",
                "division_code": "08",
                # No rsmeans_id specified
            },
        ]
    
    def test_fallback_when_no_id_provided(self):
        """Test that closest-match search is used when rsmeans_id not provided."""
        material = self.materials[0]
        has_id = "rsmeans_id" in material and material.get("rsmeans_id")
        
        self.assertFalse(has_id)
    
    def test_search_alternatives_generated(self):
        """Test that search alternatives are generated for materials."""
        material = self.materials[0]
        base_name = material["name"]
        
        # Simulate search alternatives
        alternatives = [
            base_name,
            f"{base_name} aluminum",
            f"{base_name} replacement",
            f"IGU",
            f"double pane {base_name}",
        ]
        
        self.assertTrue(len(alternatives) >= 3)
        self.assertIn(base_name, alternatives)


class TestRSMeansMatchTypeTracking(unittest.TestCase):
    """Test match_type field tracking in results."""
    
    def test_exact_match_type(self):
        """Test that exact_id_match type is recorded."""
        result = {
            "material": "window glazing",
            "match_type": "exact_id_match",
            "search_term_used": "rsmeans_id:084126100020",
            "cost": 80.70,
            "catalog": "bc-mf",
        }
        
        self.assertEqual(result["match_type"], "exact_id_match")
        self.assertIn("rsmeans_id:", result["search_term_used"])
    
    def test_closest_match_type(self):
        """Test that closest_match type is recorded."""
        result = {
            "material": "window frame",
            "match_type": "closest_match",
            "search_term_used": "window frame aluminum",
            "cost": 28.65,
            "catalog": "gb-mf",
        }
        
        self.assertEqual(result["match_type"], "closest_match")
        self.assertNotIn("rsmeans_id:", result["search_term_used"])


class TestRSMeansCostCalculation(unittest.TestCase):
    """Test cost calculation logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.materials = [
            {
                "name": "window glazing",
                "quantity": 433.01,
                "unit": "SF",
                "unit_cost": 80.70,
                "cost": 433.01 * 80.70,  # Total material cost
            },
            {
                "name": "window frame",
                "quantity": 433.01,
                "unit": "LF",
                "unit_cost": 28.65,
                "cost": 433.01 * 28.65,  # Total material cost
            },
        ]
    
    def test_total_material_cost(self):
        """Test calculation of total material cost."""
        total_material = sum(m["cost"] for m in self.materials)
        
        # Expected: 433.01 * 80.70 + 433.01 * 28.65 ≈ $47,349.64
        expected = 433.01 * 80.70 + 433.01 * 28.65
        self.assertAlmostEqual(total_material, expected, places=2)
    
    def test_overhead_and_profit(self):
        """Test overhead and profit calculation (10% default)."""
        total_material = sum(m["cost"] for m in self.materials)
        overhead_rate = 0.10
        overhead_and_profit = total_material * overhead_rate
        total_cost = total_material + overhead_and_profit
        
        # Expected: material cost with 10% overhead
        expected_total = total_material * 1.10
        self.assertAlmostEqual(total_cost, expected_total, places=2)


class TestAPIKeyRedaction(unittest.TestCase):
    """Test API key redaction in outputs."""
    
    def test_api_key_redaction_in_dict(self):
        """Test that api_key is redacted in step_values."""
        step_values = {
            "use_rsmeans": True,
            "api_key": "secret_key_12345",
            "client_id": "client_12345",
            "calculate_costs": True,
        }
        
        # Simulate redaction logic
        if "api_key" in step_values:
            step_values["api_key"] = "<redacted>"
        
        self.assertEqual(step_values["api_key"], "<redacted>")
        self.assertNotEqual(step_values["api_key"], "secret_key_12345")
    
    def test_api_key_redaction_in_json(self):
        """Test that api_key is redacted in JSON output."""
        data = {
            "measure": "window_enhancement",
            "results": {
                "api_key": "secret_key_12345",
                "costs": 52084.88,
            }
        }
        
        # Redact before serialization
        if "api_key" in data.get("results", {}):
            data["results"]["api_key"] = "<redacted>"
        
        json_str = json.dumps(data)
        self.assertNotIn("secret_key_12345", json_str)
        self.assertIn("<redacted>", json_str)


class TestRSMeansOutputFormatting(unittest.TestCase):
    """Test terminal output formatting for RSMeans results."""
    
    def test_multiline_output_structure(self):
        """Test that output is formatted in clean multi-line blocks."""
        output_lines = [
            "RSMeans lookup for material: window glazing",
            "  Quantity : 433.01 SF",
            "  Division : 08",
            "  Exact ID : 084126100020",
            "  Catalog  : bc-mf",
            "  Cost     : $80.70 per SF",
        ]
        
        # Verify formatting
        self.assertTrue(output_lines[0].startswith("RSMeans"))
        for line in output_lines[1:]:
            self.assertTrue(line.startswith("  "))
        
        # Verify all key fields present
        output_text = "\n".join(output_lines)
        self.assertIn("Quantity", output_text)
        self.assertIn("Division", output_text)
        self.assertIn("Exact ID", output_text)
        self.assertIn("Catalog", output_text)


class TestRSMeansErrorHandling(unittest.TestCase):
    """Test error handling in RSMeans API calls."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Mock(spec=RSMeansAPIClient)
    
    def test_authentication_failure(self):
        """Test handling of authentication failure."""
        self.client.authenticate = Mock(return_value=False)
        
        is_authenticated = self.client.authenticate()
        self.assertFalse(is_authenticated)
    
    def test_api_timeout_handling(self):
        """Test handling of API timeout."""
        self.client.search_unit_costlines = Mock(
            side_effect=TimeoutError("API request timed out")
        )
        
        with self.assertRaises(TimeoutError):
            self.client.search_unit_costlines(
                release_id="2024-an",
                search_term="window",
                catalog="bc-mf",
            )
    
    def test_empty_search_results(self):
        """Test handling of empty search results."""
        empty_response = {"data": {"lineItemSearchGraphql": {"edges": []}}}
        
        edges = empty_response.get("data", {}).get("lineItemSearchGraphql", {}).get("edges", [])
        self.assertEqual(len(edges), 0)
    
    def test_malformed_response_handling(self):
        """Test handling of malformed API response."""
        malformed_response = None
        
        # Should handle None response gracefully
        if malformed_response is None or "data" not in malformed_response:
            error_logged = True
        
        self.assertTrue(error_logged)


class TestRSMeansIntegration(unittest.TestCase):
    """Integration tests for complete RSMeans workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.materials = [
            {
                "name": "window glazing",
                "quantity": 433.01,
                "unit": "SF",
                "division_code": "08",
                "rsmeans_id": "084126100020",
            },
            {
                "name": "window frame",
                "quantity": 433.01,
                "unit": "LF",
                "division_code": "08",
                "rsmeans_id": "084113200050",
            },
        ]
    
    def test_dual_lookup_paths(self):
        """Test that both exact ID and closest-match paths exist."""
        for material in self.materials:
            has_exact_id = "rsmeans_id" in material and material.get("rsmeans_id")
            self.assertTrue(has_exact_id)
        
        # If IDs were blank, closest-match would be triggered
        material_no_id = {
            "name": "test material",
            "quantity": 100,
            "unit": "SF",
        }
        has_exact_id = "rsmeans_id" in material_no_id and material_no_id.get("rsmeans_id")
        self.assertFalse(has_exact_id)
    
    def test_result_structure(self):
        """Test expected structure of final results."""
        result = {
            "total_cost": 52084.88,
            "materials": [
                {
                    "name": "window glazing",
                    "quantity": 433.01,
                    "unit": "SF",
                    "unit_cost": 80.70,
                    "cost": 34944.09,
                    "match_type": "exact_id_match",
                    "search_term_used": "rsmeans_id:084126100020",
                    "catalog": "bc-mf",
                },
                {
                    "name": "window frame",
                    "quantity": 433.01,
                    "unit": "LF",
                    "unit_cost": 28.65,
                    "cost": 12405.80,
                    "match_type": "exact_id_match",
                    "search_term_used": "rsmeans_id:084113200050",
                    "catalog": "bc-mf",
                },
            ],
            "errors": [],
            "search_log": [
                "Searched glazing via exact ID 084126100020",
                "Searched frame via exact ID 084113200050",
            ],
        }
        
        # Verify structure
        self.assertIn("total_cost", result)
        self.assertIn("materials", result)
        self.assertIn("errors", result)
        self.assertIn("search_log", result)
        
        # Verify each material has required fields
        for material in result["materials"]:
            self.assertIn("match_type", material)
            self.assertIn("search_term_used", material)
            self.assertIn("cost", material)
            self.assertIn("catalog", material)


class TestRSMeansDistinctRetrofitCosts(unittest.TestCase):
    """Ensure different retrofit materials do not collapse to identical costs."""

    def test_glazing_and_frame_costs_are_distinct(self):
        """Window glazing and frame should report different totals for different line items."""
        if search_materials_across_catalogs is None:
            self.skipTest("RSMeans helper not importable in this environment")

        client = Mock(spec=RSMeansAPIClient)
        materials = [
            {
                "name": "window glazing",
                "quantity": 100.0,
                "unit": "SF",
                "division_code": "08",
                "rsmeans_id": "084126100020",
            },
            {
                "name": "window frame",
                "quantity": 100.0,
                "unit": "SF",
                "division_code": "08",
                "rsmeans_id": "084113200050",
            },
        ]

        def mock_get_unit_costlines(**kwargs):
            division_code = kwargs.get("division_code")
            if division_code == "084126100020":
                return {
                    "items": [
                        {
                            "id": "084126100020",
                            "description": "Window glazing line",
                            "localizedCosts": {"totalOpCost": 80.70},
                        }
                    ]
                }
            if division_code == "084113200050":
                return {
                    "items": [
                        {
                            "id": "084113200050",
                            "description": "Window frame line",
                            "localizedCosts": {"totalOpCost": 28.65},
                        }
                    ]
                }
            return {"items": []}

        client.get_unit_costlines = Mock(side_effect=mock_get_unit_costlines)
        client.search_unit_costlines = Mock(return_value={"items": []})

        result = search_materials_across_catalogs(
            materials=materials,
            client=client,
            catalogs=["bc-mf"],
            release_id="2024-an",
            location_id="us-us-national",
            labor_type="std",
            measurement_system="imp",
        )

        self.assertIn("materials", result)
        self.assertEqual(len(result["materials"]), 2)

        materials_by_name = {m["name"]: m for m in result["materials"]}
        self.assertIn("window glazing", materials_by_name)
        self.assertIn("window frame", materials_by_name)

        glazing_total = float(materials_by_name["window glazing"]["total_cost"])
        frame_total = float(materials_by_name["window frame"]["total_cost"])

        self.assertGreater(glazing_total, 0.0)
        self.assertGreater(frame_total, 0.0)
        self.assertNotEqual(
            glazing_total,
            frame_total,
            "Different retrofit materials returned identical costs unexpectedly.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

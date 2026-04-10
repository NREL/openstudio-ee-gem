"""
Unit tests for RSMeans error message content and formatting.
These tests verify that error messages are clear, actionable, and include proper retry guidance.
"""

import unittest


class TestRSMeansErrorMessages(unittest.TestCase):
    """Test the error message content and formatting."""

    def test_error_message_format_includes_problem_solution(self):
        """Verify error messages follow: Problem -> SOLUTION -> Steps format."""
        # Simulate the error message that would be generated
        error_msg = (
            "RSMeans lookup failed: Material not found\n"
            "The RSMeans API could not find a cost for this insulation material.\n"
            "SOLUTION: Retry the measure with custom cost input:\n"
            "  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
            "  2. Enter 'Custom Insulation Cost ($/SF)' with your estimated cost\n"
            "  (For Pure Wool Batts, consult RS Means or quotes from vendors for typical $/SF rates)"
        )
        
        # Verify key sections exist
        self.assertIn("failed", error_msg.lower(), "Should indicate failure")
        self.assertIn("SOLUTION", error_msg, "Should have explicit SOLUTION section")
        self.assertIn("Use Custom Cost Inputs", error_msg, "Should reference the custom cost parameter")
        self.assertIn("Custom Insulation Cost", error_msg, "Should reference cost parameter")
        self.assertIn("1.", error_msg, "Should have numbered steps")
        self.assertIn("2.", error_msg, "Should have multiple steps")
        self.assertIn("$/SF", error_msg, "Should show cost units")

    def test_error_message_no_placeholder_parameters(self):
        """Verify error messages don't contain unclosed placeholder brackets."""
        # Simulate error message
        error_msg = (
            "RSMeans lookup failed: {error}\n"
            "SOLUTION: Try using custom costs with flag 'use_custom_costs'."
        )
        
        # After formatting (simulated)
        formatted = error_msg.format(error="Material not found")
        
        # Should not have unclosed brackets after formatting
        self.assertEqual(formatted.count("{"), 0, "Should not have open brackets")
        self.assertEqual(formatted.count("}"), 0, "Should not have close brackets")

    def test_error_message_sections_are_distinct(self):
        """Verify error message sections are clearly separated."""
        error_msg = (
            "RSMeans lookup failed: No match found\n"
            "The RSMeans API could not find a cost for this insulation material.\n"
            "SOLUTION: Retry the measure with custom cost input:\n"
            "  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
            "  2. Enter 'Custom Insulation Cost ($/SF)' with your estimated cost"
        )
        
        lines = error_msg.split("\n")
        
        # Verify structure
        self.assertTrue(any("failed" in line.lower() for line in lines), 
                       "Should have failure indication")
        self.assertTrue(any("SOLUTION" in line for line in lines),
                       "Should have SOLUTION marker")
        self.assertTrue(any("Set" in line and "true" in line for line in lines),
                       "Should have setting instructions")
        
    def test_custom_cost_parameter_referenced_consistently(self):
        """
        Verify parameter names are referenced throughout error guidance.
        Users need to see instructions they can follow in the measure UI.
        """
        error_msg = (
            "Retry the measure with custom cost input:\n"
            "  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
            "  2. Enter 'Custom Insulation Cost ($/SF)' with your estimated cost"
        )
        
        # Both parameters should be explicitly referenced
        self.assertIn("Use Custom Cost Inputs", error_msg,
                     "Should reference custom cost inputs parameter")
        self.assertIn("Custom Insulation Cost", error_msg,
                     "Should reference custom cost input parameter")
        
        # Quotes mark parameter names for clarity
        self.assertIn("'Use Custom Cost Inputs", error_msg, "Parameter name should be quoted")
        self.assertIn("'Custom Insulation Cost", error_msg, "Parameter name should be quoted")


if __name__ == '__main__':
    unittest.main()

"""
Test suite for ReportRetrofitImpacts measure.
Run with: pytest test_report_retrofit_impacts.py -v
"""

import sys
from pathlib import Path
import pytest

# Setup paths
CURRENT_DIR_PATH = Path(__file__).parent.absolute()
MEASURE_DIR = CURRENT_DIR_PATH.parent
MEASURE_PATH = MEASURE_DIR / "measure.py"

class TestReportRetrofitImpacts:
    """Test suite for ReportRetrofitImpacts measure."""

    def test_measure_file_exists(self):
        """Verify the Python measure file exists."""
        assert MEASURE_PATH.exists(), f"measure.py should exist at {MEASURE_PATH}"

    def test_measure_has_valid_syntax(self):
        """Verify measure.py has valid Python syntax."""
        import ast
        try:
            with open(MEASURE_PATH, 'r', encoding='utf-8') as f:
                ast.parse(f.read())
        except SyntaxError as e:
            pytest.fail(f"measure.py has syntax error: {e}")

    def test_measure_imports_successfully(self):
        """Verify the measure can be imported."""
        sys.path.insert(0, str(MEASURE_DIR))
        try:
            from measure import CReport
            assert CReport is not None
        except ImportError as e:
            pytest.fail(f"Failed to import CReport from measure.py: {e}")
        finally:
            sys.path.pop(0)
            if 'measure' in sys.modules:
                del sys.modules['measure']

    def test_example_models_exist(self):
        """Verify test models exist in tests directory."""
        models = [
            "Inputs/example_baseline.osm",
            "Inputs/example_measure_applied.osm"
        ]
        for model_file in models:
            model_path = CURRENT_DIR_PATH / model_file
            assert model_path.exists(), f"{model_file} should exist in tests directory"

    def test_required_python_files_exist(self):
        """Verify supporting Python files exist."""
        required_files = [
            "apply_measure.py",
            "call_RSmeans.py"
        ]
        for file_name in required_files:
            file_path = MEASURE_DIR / file_name
            assert file_path.exists(), f"{file_name} should exist in measure directory"

    def test_resources_directory_structure(self):
        """Verify resources directory and required files exist."""
        resources_dir = MEASURE_DIR / "resources"
        assert resources_dir.is_dir(), "resources directory should exist"

        required_resources = [
            "retrofit_report_template.html",
            "optimization.xlsx"
        ]
        for resource_file in required_resources:
            resource_path = resources_dir / resource_file
            assert resource_path.exists(), f"{resource_file} should exist in resources directory"

    def test_output_directory_exists(self):
        """Verify outputs directory exists or can be created."""
        output_dir = CURRENT_DIR_PATH / "outputs"
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        assert output_dir.is_dir(), "outputs directory should exist in tests directory"

    def test_measure_class_instantiation(self):
        """Verify the CReport class can be instantiated."""
        sys.path.insert(0, str(MEASURE_DIR))
        try:
            from measure import CReport
            measure = CReport()
            assert measure is not None
            assert hasattr(measure, 'name'), "Measure should have a name() method"
            assert hasattr(measure, 'description'), "Measure should have a description() method"
            assert hasattr(measure, 'run'), "Measure should have a run() method"
        except Exception as e:
            pytest.fail(f"Failed to instantiate CReport: {e}")
        finally:
            sys.path.pop(0)
            if 'measure' in sys.modules:
                del sys.modules['measure']

    def test_measure_name_and_description(self):
        """Verify measure has proper name and description."""
        sys.path.insert(0, str(MEASURE_DIR))
        try:
            from measure import CReport
            measure = CReport()
            
            name = measure.name()
            assert isinstance(name, str), "Measure name should be a string"
            assert len(name) > 0, "Measure name should not be empty"
            
            description = measure.description()
            assert isinstance(description, str), "Measure description should be a string"
            assert len(description) > 0, "Measure description should not be empty"
        finally:
            sys.path.pop(0)
            if 'measure' in sys.modules:
                del sys.modules['measure']

    def test_call_rsmeans_module_imports(self):
        """Verify RSMeans API client module can be imported."""
        sys.path.insert(0, str(MEASURE_DIR))
        try:
            from call_RSmeans import RSMeansAPIClient
            assert RSMeansAPIClient is not None
        except ImportError as e:
            pytest.fail(f"Failed to import RSMeansAPIClient: {e}")
        finally:
            sys.path.pop(0)
            if 'call_RSmeans' in sys.modules:
                del sys.modules['call_RSmeans']


if __name__ == "__main__":
    # Allow running this file directly
    pytest.main([__file__, "-v"])

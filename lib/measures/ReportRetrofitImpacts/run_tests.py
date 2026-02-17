"""
Simple test runner for ReportRetrofitImpacts measure.
Run with: python run_tests.py
"""

import sys
from pathlib import Path

# Add measure directory to path
CURRENT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(CURRENT_DIR))

def run_all_tests():
    """Run all tests and report results."""
    print("=" * 70)
    print("Running ReportRetrofitImpacts Tests")
    print("=" * 70)
    
    tests_passed = 0
    tests_failed = 0
    
    def test(name, func):
        """Run a single test."""
        nonlocal tests_passed, tests_failed
        try:
            func()
            print(f"✓ {name}")
            tests_passed += 1
        except AssertionError as e:
            print(f"✗ {name}: {e}")
            tests_failed += 1
        except Exception as e:
            print(f"✗ {name}: ERROR - {e}")
            tests_failed += 1
    
    # Test 1: Measure file exists
    def test_measure_exists():
        measure_path = CURRENT_DIR / "measure.py"
        assert measure_path.exists(), f"measure.py not found at {measure_path}"
    
    test("Measure file exists", test_measure_exists)
    
    # Test 2: Valid Python syntax
    def test_syntax():
        import ast
        measure_path = CURRENT_DIR / "measure.py"
        with open(measure_path, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
    
    test("Measure has valid Python syntax", test_syntax)
    
    # Test 3: Measure imports
    def test_imports():
        from measure import CReport
        assert CReport is not None
    
    test("Measure imports successfully", test_imports)
    
    # Test 4: Measure instantiation
    def test_instantiation():
        from measure import CReport
        measure = CReport()
        assert measure is not None
        assert hasattr(measure, 'name')
        assert hasattr(measure, 'run')
    
    test("CReport class instantiates", test_instantiation)
    
    # Test 5: Example models exist
    def test_models():
        tests_dir = CURRENT_DIR / "tests"
        models = [
            "example_model.osm",
            "example_model_2_with_AdditionalProperties.osm"
        ]
        for model_file in models:
            path = tests_dir / model_file
            assert path.exists(), f"{model_file} not found"
    
    test("Example models exist", test_models)
    
    # Test 6: Supporting files exist
    def test_supporting_files():
        files = ["apply_measure.py", "call_RSmeans.py"]
        for file_name in files:
            path = CURRENT_DIR / file_name
            assert path.exists(), f"{file_name} not found"
    
    test("Supporting Python files exist", test_supporting_files)
    
    # Test 7: Resources directory
    def test_resources():
        resources_dir = CURRENT_DIR / "resources"
        assert resources_dir.is_dir(), "resources directory not found"
        
        required = ["retrofit_report_template.html", "optimization.xlsx"]
        for resource in required:
            path = resources_dir / resource
            assert path.exists(), f"{resource} not found in resources"
    
    test("Resources directory structure valid", test_resources)
    
    # Test 8: RSMeans API client
    def test_rsmeans():
        from call_RSmeans import RSMeansAPIClient
        assert RSMeansAPIClient is not None
    
    test("RSMeans API client imports", test_rsmeans)
    
    # Summary
    print("=" * 70)
    total = tests_passed + tests_failed
    print(f"Tests: {tests_passed} passed, {tests_failed} failed, {total} total")
    
    if tests_failed == 0:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"✗ {tests_failed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())

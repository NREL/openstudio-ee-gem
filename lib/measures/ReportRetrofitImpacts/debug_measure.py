#!/usr/bin/env python
"""Debug script to test the measure functionality."""

import sys
from pathlib import Path

# Test imports
print("Testing imports...")
try:
    import openstudio
    print("✓ openstudio")
except Exception as e:
    print(f"✗ openstudio: {e}")
    sys.exit(1)

try:
    from measure import CReport
    print("✓ measure.CReport")
except Exception as e:
    print(f"✗ measure.CReport: {e}")
    sys.exit(1)

# Test model loading
print("\nTesting model loading...")
try:
    CURRENT_DIR_PATH = Path(__file__).parent.absolute()
    model_path = CURRENT_DIR_PATH / "tests/example_model_2_with_AdditionalProperties.osm"
    
    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(openstudio.toPath(str(model_path)))
    
    if not model_opt.is_initialized():
        print(f"✗ Model failed to load from {model_path}")
        sys.exit(1)
    
    model = model_opt.get()
    print(f"✓ Model loaded: {model_path}")
    print(f"  Objects: {len(model.objects())}")
    
except Exception as e:
    print(f"✗ Model loading failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test measure creation and run
print("\nTesting measure...")
try:
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    
    measure = CReport()
    print("✓ Measure created")
    
    user_arguments = {}
    result = measure.run(runner, user_arguments, model)
    print(f"✓ Measure run complete: {result}")
    
    # Print results
    print("\nMeasure results:")
    print(f"  Result: {runner.result().value().valueName()}")
    for info in runner.result().info():
        print(f"  INFO: {info.logMessage()}")
    for warning in runner.result().warnings():
        print(f"  WARNING: {warning.logMessage()}")
    for error in runner.result().errors():
        print(f"  ERROR: {error.logMessage()}")
    
except Exception as e:
    print(f"✗ Measure execution failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check output files
print("\nChecking output files...")
tests_outputs = CURRENT_DIR_PATH / "tests/outputs"
if tests_outputs.exists():
    files = list(tests_outputs.glob("*"))
    if files:
        print(f"✓ Output files created:")
        for f in files:
            print(f"  - {f.name}")
    else:
        print("✗ No output files found in tests/outputs/")
else:
    print(f"✗ Output directory does not exist: {tests_outputs}")

print("\nDebug complete!")

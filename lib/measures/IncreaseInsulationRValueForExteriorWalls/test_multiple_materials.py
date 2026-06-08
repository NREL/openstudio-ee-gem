"""
Test script to run IncreaseInsulationRValueForExteriorWalls with multiple
insulation materials and verify that different materials produce different costs.
"""

from pathlib import Path
import sys
import json
import configparser

# ---------------------------------------------------------------------------
# OpenStudio path setup
# ---------------------------------------------------------------------------
OPENSTUDIO_VERSION = "3.11.0"

# Try Windows path first
openstudio_path = f"C:\\Program Files\\openstudio-{OPENSTUDIO_VERSION}\\Python"
if not Path(openstudio_path).exists():
    # Fall back to macOS path
    openstudio_path = f"/Applications/OpenStudio-{OPENSTUDIO_VERSION}/Python"

if Path(openstudio_path).exists():
    sys.path.insert(0, openstudio_path)
    print(f"Using OpenStudio from: {openstudio_path}")
else:
    print(f"Warning: OpenStudio path not found")
    print("Will attempt to use system OpenStudio installation")

import openstudio
from measure import IncreaseInsulationRValueForExteriorWalls

print(f"OpenStudio version: {openstudio.openStudioVersion()}")

# ---------------------------------------------------------------------------
# Read API token from repo-level config.ini
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.absolute()
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config.ini"

API_TOKEN = "PLACEHOLDER"
if CONFIG_PATH.exists():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    try:
        API_TOKEN = config["EC3_API_TOKEN"]["API_TOKEN"]
        print(f"API token loaded from: {CONFIG_PATH}")
    except KeyError:
        print(f"Warning: could not read API_TOKEN from {CONFIG_PATH}")
else:
    print(f"Warning: config.ini not found at {CONFIG_PATH}")


def load_model(model_path):
    """Load an OSM file and return the Model object."""
    translator = openstudio.osversion.VersionTranslator()
    translator.setAllowNewerVersions(True)
    loaded = translator.loadModel(openstudio.toPath(str(model_path)))
    if not loaded.is_initialized():
        raise RuntimeError(f"Failed to load model: {model_path}\n"
                           f"Errors: {translator.errors()}")
    return loaded.get()


def run_measure(model, material_type, use_exact_id=False, exact_id=""):
    """
    Instantiate and run the measure.

    Args:
        model: openstudio.model.Model
        material_type: str - insulation material type
        use_exact_id: bool - whether to use exact costline ID
        exact_id: str - exact costline ID if use_exact_id is True

    Returns:
        (success: bool, runner: OSRunner, material_cost, overhead_cost, total_cost)
    """
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForExteriorWalls()

    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

    def set_arg(name, value):
        if name in arg_map:
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
        else:
            print(f"  Warning: argument '{name}' not found in measure arguments")

    # --- Measure arguments ---
    set_arg("r_value", 20.0)
    set_arg("analysis_period", 30)
    set_arg("gwp_statistic", "median")
    set_arg("api_key", API_TOKEN)
    set_arg("insulation_material_type", material_type)
    set_arg("insulation_material_lifetime", 30)
    set_arg("insulation_thermal_conductivity", 0.0)
    set_arg("insulation_material_density", 0.0)
    set_arg("use_custom_costs", False)
    set_arg("use_exact_costline_id", use_exact_id)
    if use_exact_id and exact_id:
        set_arg("exact_costline_id", exact_id)

    print(f"\n  Running measure with: {material_type}")
    measure.run(model, runner, arg_map)
    success = runner.result().value().valueName() == "Success"
    
    # Extract costs from AdditionalProperties
    material_cost = None
    overhead_cost = None
    
    facility = model.getFacility()
    ap = facility.additionalProperties()
    
    if ap.hasFeature("wall_insulation_total_additional_material_cost_$"):
        val = ap.getFeatureAsDouble("wall_insulation_total_additional_material_cost_$")
        if val.is_initialized():
            material_cost = float(val.get())
    
    if ap.hasFeature("wall_insulation_total_additional_overhead_profit_cost_$"):
        val = ap.getFeatureAsDouble("wall_insulation_total_additional_overhead_profit_cost_$")
        if val.is_initialized():
            overhead_cost = float(val.get())
    
    total_cost = (material_cost or 0.0) + (overhead_cost or 0.0) if material_cost is not None else None
    
    return success, runner, material_cost, overhead_cost, total_cost


def main():
    print("=" * 80)
    print("IncreaseInsulationRValueForExteriorWalls – Multi-Material Cost Test")
    print("=" * 80)

    # Load base model once
    model_path = SCRIPT_DIR / "tests" / "DOE_small_office.osm"
    output_dir = SCRIPT_DIR / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not model_path.exists():
        print(f"\nERROR: Model file not found: {model_path}")
        sys.exit(1)

    print(f"\nLoading model: {model_path}")
    
    # Test materials
    materials = [
        ("Blown Cellulose", False, ""),
        ("Blown Fiberglass", False, ""),
        ("Blown Mineral Wool", False, ""),
        ("Polyiso Insulation Foam Board", False, ""),
        ("Graphite Polystyrene (GPS) Foam Board", False, ""),
        ("Expanded Polystyrene (EPS) Foam Board", False, ""),
        ("Extruded Polystyrene (XPS) Foam Board", False, ""),
        ("Mineral Wool Heavy Density Blanket", False, ""),
        ("Mineral Wool Light Density Blanket", False, ""),
        ("Fiberglass Batts", False, ""),
        ("Pure Wool Batts", True, "072116201320"),
    ]

    results = []
    
    for material_type, use_exact_id, exact_id in materials:
        print(f"\n{'='*80}")
        print(f"Testing: {material_type}")
        print(f"{'='*80}")
        
        # Reload model fresh for each test
        model = load_model(model_path)
        
        try:
            success, runner, material_cost, overhead_cost, total_cost = run_measure(
                model, material_type, use_exact_id, exact_id
            )
            
            result_data = {
                "material": material_type,
                "success": success,
                "material_cost": material_cost,
                "overhead_cost": overhead_cost,
                "total_cost": total_cost,
            }
            
            if success:
                print(f"\n  [OK] Success")
                if material_cost is not None:
                    print(f"    Material Cost: ${material_cost:,.2f}")
                    print(f"    Overhead Cost: ${overhead_cost:,.2f}")
                    print(f"    Total Cost:   ${total_cost:,.2f}")
                else:
                    print(f"    (No cost data available)")
            else:
                print(f"\n  [FAIL] Failed")
                print("\n  Errors from runner:")
                if runner.result().errors():
                    for msg in runner.result().errors():
                        print(f"    {msg.logMessage()}")
                print("\n  Warnings from runner:")
                if runner.result().warnings():
                    for msg in runner.result().warnings():
                        print(f"    {msg.logMessage()}")
            
            results.append(result_data)
            
        except Exception as e:
            print(f"\n  [ERROR] Exception: {e}")
            results.append({
                "material": material_type,
                "success": False,
                "error": str(e),
            })

    # Summary and comparison
    print(f"\n\n{'='*80}")
    print("COST COMPARISON SUMMARY")
    print(f"{'='*80}\n")
    
    successful_results = [r for r in results if r.get("success") and r.get("total_cost") is not None]
    
    if not successful_results:
        print("No successful results with costs to compare.")
        return 1
    
    # Sort by total cost
    successful_results.sort(key=lambda x: x["total_cost"])
    
    print(f"{'Material':<45} {'Total Cost':>15}")
    print("-" * 62)
    for r in successful_results:
        print(f"{r['material']:<45} ${r['total_cost']:>13,.2f}")
    
    # Check for duplicate costs
    print(f"\n\n{'='*80}")
    print("DUPLICATE COST CHECK")
    print(f"{'='*80}\n")
    
    costs = {}
    for r in successful_results:
        cost = round(r["total_cost"], 2)
        if cost not in costs:
            costs[cost] = []
        costs[cost].append(r["material"])
    
    duplicates_found = False
    for cost, materials_list in sorted(costs.items()):
        if len(materials_list) > 1:
            duplicates_found = True
            print(f"[DUPLICATE] COST ${cost:,.2f}:")
            for mat in materials_list:
                print(f"    - {mat}")
        else:
            print(f"[UNIQUE] Cost ${cost:,.2f}: {materials_list[0]}")
    
    if duplicates_found:
        print(f"\n[WARNING] Some materials have identical costs!")
        print("This may indicate RSMeans is returning the same line item for different materials.")
    else:
        print(f"\n[SUCCESS] All materials have unique costs!")
    
    # Save detailed results to JSON
    results_json_path = output_dir / "multi_material_cost_test_results.json"
    with open(results_json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nDetailed results saved to: {results_json_path}")
    
    return 0 if not duplicates_found else 1


if __name__ == "__main__":
    sys.exit(main())

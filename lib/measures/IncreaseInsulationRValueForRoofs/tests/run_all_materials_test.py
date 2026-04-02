#!/usr/bin/env python
"""
Run IncreaseInsulationRValueForRoofs measure for all 11 insulation materials.

Tests per-construction RSMeans cost lookup with actual thicknesses.
"""

import sys
import json
from pathlib import Path

# Add measure directory to path
MEASURE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MEASURE_DIR))

import openstudio
from measure import IncreaseInsulationRValueForRoofs


# Materials to test (11 total)
MATERIALS = [
    "Fiberglass Batts",
    "Blown Fiberglass",
    "Blown Cellulose",
    "Mineral Wool Heavy Density Blanket",
    "Mineral Wool Light Density Blanket",
    "Polyiso Insulation Foam Board",
    "Expanded Polystyrene (EPS) Foam Board",
    "Extruded Polystyrene (XPS) Foam Board",
    "Graphite Polystyrene (GPS) Foam Board",
    "Pure Wool Batts",
    "Blown Mineral Wool"
]


def load_model(model_path):
    """Load an OSM file."""
    translator = openstudio.osversion.VersionTranslator()
    translator.setAllowNewerVersions(True)
    loaded = translator.loadModel(openstudio.toPath(str(model_path)))
    if not loaded.is_initialized():
        print(f"ERROR: Failed to load model: {model_path}")
        return None
    return loaded.get()


def run_material_test(model_path, material_name, output_base_dir):
    """Run measure for a single material."""
    print(f"\n{'='*70}")
    print(f"Testing: {material_name}")
    print(f"{'='*70}")
    
    # Load fresh model for each test
    model = load_model(model_path)
    if model is None:
        return None
    
    # Create measure and runner
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForRoofs()
    
    # Set up arguments
    args = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)
    
    # Configure arguments
    def set_arg(name, value):
        if name in arg_map:
            arg = arg_map[name]
            arg.setValue(value)
            arg_map[name] = arg
    
    set_arg("r_value", 30.0)
    set_arg("insulation_material_type", material_name)
    set_arg("analysis_period", 30)
    set_arg("gwp_statistic", "median")
    set_arg("calculate_costs", True)
    set_arg("use_custom_costs", False)
    
    # Run measure
    print("Running measure...")
    success = measure.run(model, runner, arg_map)
    
    # Collect results
    results = {
        "material": material_name,
        "success": success,
        "messages": [],
        "rsmeans_data": None
    }
    
    # Collect runner output
    if runner.result():
        for step in runner.result().stepValues():
            try:
                msg = step.valueAsString()
                results["messages"].append(msg)
                if "RSMeans" in msg or "costline_id" in msg:
                    print(f"  {msg}")
            except Exception:
                pass
    
    # Extract RSMeans diagnostics from AdditionalProperties
    sim_control = model.getSimulationControl()
    sim_ap = sim_control.additionalProperties()
    prop_name = "roof_insulation_rsmeans_matches_json"
    if sim_ap.hasFeature(prop_name):
        try:
            json_str = sim_ap.getFeatureAsString(prop_name).get()
            rsmeans_data = json.loads(json_str)
            results["rsmeans_data"] = rsmeans_data

            # Print summary
            if "materials" in rsmeans_data:
                for mat in rsmeans_data["materials"]:
                    print(f"  Material: {mat.get('material_name', 'unknown')}")
                    print(f"    Costline ID: {mat.get('rsmeans_id', 'N/A')}")
                    print(f"    Unit Cost: ${mat.get('unit_cost', 0):.2f}")
                    print(f"    Total Cost: ${mat.get('total_cost', 0):.2f}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"  Could not parse RSMeans JSON: {e}")

    # Extract cost totals from AdditionalProperties
    mat_cost_prop = "roof_insulation_total_additional_material_cost_$"
    total_cost_prop = "roof_insulation_total_cost_with_overhead_and_profit_$"
    if sim_ap.hasFeature(mat_cost_prop):
        val = sim_ap.getFeatureAsDouble(mat_cost_prop)
        results["material_cost"] = val.get() if val.is_initialized() else 0.0
    if sim_ap.hasFeature(total_cost_prop):
        val = sim_ap.getFeatureAsDouble(total_cost_prop)
        results["total_cost"] = val.get() if val.is_initialized() else 0.0
    
    # Save modified model
    clean_name = material_name.lower().replace(" ", "_")
    clean_name = clean_name.replace("(", "").replace(")", "")
    material_folder = output_base_dir / clean_name
    material_folder.mkdir(parents=True, exist_ok=True)
    
    output_osm_name = "DOE_small_office_roof_insulation_upgraded.osm"
    output_osm = material_folder / output_osm_name
    output_json = material_folder / "apply_measure_results.json"
    
    try:
        model.save(openstudio.toPath(str(output_osm)), True)
        print(f"  Model saved: {output_osm}")
    except Exception as e:
        print(f"  ERROR saving model: {e}")
    
    # Save results JSON
    try:
        with open(output_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results saved: {output_json}")
    except Exception as e:
        print(f"  ERROR saving results: {e}")
    
    return results


def main():
    """Run tests for all materials."""
    print("=" * 70)
    print("IncreaseInsulationRValueForRoofs - Multi-Material Validation")
    print("=" * 70)
    
    # Setup paths
    test_dir = Path(__file__).parent
    model_path = test_dir / "DOE_small_office.osm"
    output_dir = test_dir / "output"
    
    if not model_path.exists():
        print(f"ERROR: Test model not found: {model_path}")
        return 1
    
    print(f"\nTest model: {model_path}")
    print(f"Output directory: {output_dir}")
    print(f"Materials to test: {len(MATERIALS)}")
    
    # Run tests
    all_results = []
    successful = 0
    failed = 0
    
    for i, material in enumerate(MATERIALS, 1):
        print(f"\n[{i}/{len(MATERIALS)}]", end=" ")
        result = run_material_test(model_path, material, output_dir)
        
        if result:
            all_results.append(result)
            if result["success"]:
                successful += 1
                print("  [PASSED]")
            else:
                failed += 1
                print("  [FAILED]")
        else:
            failed += 1
            print("  [ERROR]")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total tests: {len(MATERIALS)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    # Cost analysis
    print("\nCost Breakdown by Material:")
    costs_by_material = {}
    for result in all_results:
        if result.get("rsmeans_data"):
            materials = result["rsmeans_data"].get("materials", [])
            for mat in materials:
                material_name = result["material"]
                total_cost = mat.get("total_cost", 0)
                costline_id = mat.get("rsmeans_id", "N/A")
                costs_by_material[material_name] = {
                    "total_cost": total_cost,
                    "costline_id": costline_id
                }
    
    if costs_by_material:
        for material, data in sorted(
            costs_by_material.items(),
            key=lambda x: x[1]["total_cost"]
        ):
            cost = data["total_cost"]
            cid = data["costline_id"]
            print(f"  {material:40s} ${cost:10,.2f} "
                  f"(costline_id={cid})")
    
    # Save overall summary
    summary = {
        "test_date": str(Path.cwd()),
        "total_materials": len(MATERIALS),
        "successful": successful,
        "failed": failed,
        "materials_tested": all_results
    }

    summary_file = output_dir / "validation_summary_per_construction.json"
    try:
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nSummary saved: {summary_file}")
    except Exception as e:
        print(f"ERROR saving summary: {e}")

    # Save compact material comparison summary (no output_dir)
    comparison_rows = []
    for result in all_results:
        rsmeans_data = result.get("rsmeans_data") or {}
        materials_list = rsmeans_data.get("materials", [])
        first_mat = materials_list[0] if materials_list else {}
        comparison_rows.append({
            "material": result["material"],
            "success": result["success"],
            "material_cost": result.get(
                "material_cost", first_mat.get("total_cost", 0)
            ),
            "total_cost": result.get("total_cost", 0),
            "rsmeans_id": first_mat.get("rsmeans_id", "N/A"),
        })

    comparison_file = output_dir / "rsmeans_material_comparison_summary.json"
    try:
        with open(comparison_file, "w") as f:
            json.dump(comparison_rows, f, indent=2)
        print(f"Comparison summary saved: {comparison_file}")
    except Exception as e:
        print(f"ERROR saving comparison summary: {e}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""
Validate roof insulation measure with enhanced scoring and search alternatives.
Runs all 11 material types and compares RSMeans cost results.
"""
import json
import os
import sys
import shutil
from pathlib import Path

# Add library path
# From resources/ -> up to repo root ../../../../
lib_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(lib_path))

import openstudio


def run_measure(model_path, material_name, r_value_increase):
    """Run the increase insulation measure for a specific material."""
    print(f"\n{'='*70}")
    print(f"Testing: {material_name} (R+{r_value_increase})")
    print(f"{'='*70}")

    # Load model
    translator = openstudio.osversion.VersionTranslator()
    model = translator.loadModel(model_path)
    if model.empty:
        print(f"ERROR: Failed to load model {model_path}")
        return None, None

    # Create measure runner
    runner = openstudio.measure.OSRunner(
        openstudio.runmanager.Workflow()
    )

    # Load and run measure
    # From resources/ -> up 2 levels gets to IncreaseInsulationRValueForRoofs
    measure_dir = Path(__file__).parent.parent
    measure = openstudio.measure.ModelMeasure(str(measure_dir))

    # Set arguments
    arg_map = measure.arguments(model)
    arg_map["r_value_increase"].setValue(r_value_increase)

    # Run measure
    print(f"Running measure...")
    success = measure.run(model, runner, arg_map)

    print(f"\nMeasure Result: {'SUCCESS' if success else 'FAILURE'}")

    if not success:
        # Print initial conditions messages
        for msg in runner.initialCondition().messages:
            print(f"  Initial: {msg.logMessage()}")
        # Print step values
        for step in runner.getSteps():
            print(f"  Step: {step.logMessage()}")
        # Print final conditions
        for msg in runner.finalCondition().messages:
            print(f"  Final: {msg.logMessage()}")

    # Extract RSMeans results from step values
    results = {}
    for step in runner.getSteps():
        msg = step.logMessage()
        if "RSMeans Unit Cost" in msg or "Total Cost" in msg:
            print(f"  {msg}")
            if "RSMeans Unit Cost" in msg:
                parts = msg.split(":")
                if len(parts) > 1:
                    try:
                        val = float(parts[1].strip().split()[0])
                        results['unit_cost'] = val
                    except:
                        pass
            if "Total Cost" in msg:
                parts = msg.split(":")
                if len(parts) > 1:
                    try:
                        val = float(parts[1].strip().split()[0])
                        results['total_cost'] = val
                    except:
                        pass

    # Extract RSMeans data from additional properties
    facility = model.getFacility()
    sim_control = model.getSimulationControl()

    rsmeans_data = None

    # Check facility properties
    prop_name = "roof_insulation_rsmeans_matches_json"
    if facility.additionalProperties().hasProperty(prop_name):
        json_str = (
            facility.additionalProperties()
            .getFeatureAsString(prop_name).get()
        )
        try:
            rsmeans_data = json.loads(json_str)
            print(f"\nRSMeans Data (from Facility):")
            if "materials" in rsmeans_data:
                for mat in rsmeans_data["materials"]:
                    mat_name = mat.get('material_name', 'unknown')
                    print(f"  Material: {mat_name}")
                    print(f"    RSMeans ID: {mat.get('rsmeans_id')}")
                    print(f"    Unit Cost: ${mat.get('unit_cost', 0):.2f}")
                    print(f"    Total Cost: ${mat.get('total_cost', 0):.2f}")
                    if "search_log" in mat:
                        log = mat['search_log']
                        print(f"    Search Attempts: {len(log)}")
                        for i, entry in enumerate(log):
                            term = entry.get('search_term', '?')
                            cat = entry.get('catalog', '?')
                            status = entry.get('status', 'unknown')
                            print(f"      Attempt {i+1}: {term} "
                                  f"in {cat} ({status})")
                            scores = entry.get(
                                'candidate_scores', []
                            )
                            if scores:
                                print(f"        Top candidates:")
                                for cand in scores[:3]:
                                    score = cand.get('score', 0)
                                    rid = cand.get('rsmeans_id', '?')
                                    desc = cand.get('description', '')
                                    desc = desc[:50]
                                    print(f"          [{score:.0f}] "
                                          f"{rid}: {desc}")
        except json.JSONDecodeError as e:
            print(f"  Failed to parse RSMeans JSON: {e}")

    return results, rsmeans_data


def main():
    """Run validation for all 11 insulation materials."""

    # Test model path
    # From resources/ -> up to repo root ../../../../tests/models/
    test_model = (
        Path(__file__).parent.parent.parent.parent
        / "tests" / "models" / "DOE_small_office_roof_insulation.osm"
    )

    if not test_model.exists():
        print(f"ERROR: Test model not found at {test_model}")
        return 1

    # Materials to test
    materials = [
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

    # Output tracking
    # From resources/ -> up to repo root ../../../../tests/output/
    output_dir = (
        Path(__file__).parent.parent.parent.parent
        / "tests" / "output"
        / "roof_insulation_enhanced_validation"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    results_summary = {}
    all_rsmeans_data = []

    # Run measure for each material
    for material in materials:
        # Create material-specific output folder
        clean_name = (
            material.replace(" ", "_").replace("(", "").replace(")", "")
        )
        mat_folder = output_dir / clean_name
        mat_folder.mkdir(parents=True, exist_ok=True)

        # Run measure
        results, rsmeans_data = run_measure(
            str(test_model), material, 10.0
        )

        if results:
            results_summary[material] = results
            all_rsmeans_data.append({
                "material": material,
                "results": results,
                "rsmeans_data": rsmeans_data
            })

    # Write summary
    summary_file = output_dir / "validation_summary.json"
    with open(summary_file, "w") as f:
        summary_data = {
            "materials_tested": len(results_summary),
            "unique_costs": len(set(
                str(r.get('total_cost'))
                for r in results_summary.values()
            )),
            "results_by_material": results_summary,
            "detailed_rsmeans_data": all_rsmeans_data
        }
        json.dump(summary_data, f, indent=2)

    print(f"\n\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Materials tested: {len(results_summary)}")
    print(f"Output directory: {output_dir}")
    print(f"Summary file: {summary_file}")

    # Show cost breakdown
    cost_groups = {}
    for mat, res in results_summary.items():
        cost = res.get('total_cost', 0)
        cost_key = f"${cost:.2f}"
        if cost_key not in cost_groups:
            cost_groups[cost_key] = []
        cost_groups[cost_key].append(mat)

    print(f"\nCost Groups ({len(cost_groups)} groups):")
    for cost, materials_in_group in sorted(cost_groups.items()):
        count = len(materials_in_group)
        print(f"  {cost}: {count} materials")
        for mat in materials_in_group:
            print(f"    - {mat}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

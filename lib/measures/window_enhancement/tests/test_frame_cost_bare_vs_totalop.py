#!/usr/bin/env python
"""
Test script to verify window frame cost calculation in bare_material vs totalop mode.
This validates the fix for frame cost derivation to use correct cost types.
"""

import sys
import os
import json
from pathlib import Path

# Add resources directory to path
MEASURE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MEASURE_DIR / "resources"))

from dotenv import load_dotenv
load_dotenv()

from call_rsmeans_api import RSMeansAPIClient, _derive_frame_cost_from_window_minus_glass

def test_frame_cost_comparison():
    """Compare frame costs between totalop and bare_material modes."""
    
    client_id = os.getenv('client_id')
    client_secret = os.getenv('client_secret')
    
    if not client_id or not client_secret or client_id == "PLACEHOLDER":
        print("SKIP: RSMeans credentials not set")
        return

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=False)
    
    if not client.authenticate():
        print("FAIL: Authentication failed")
        return
    
    print("=" * 80)
    print("Window Frame Cost: bare_material vs totalop Comparison")
    print("=" * 80)
    
    # Test material definition (wood frame, double-pane)
    frame_material = {
        "name": "window frame",
        "quantity": 1.0,
        "unit": "SF",
        "window_unit_id": "085210700100",  # Wood operable window
        "glazing_id": "088130100020",      # Double-pane IGU
        "window_area_sf": 9.0,             # 3'x3' window
        "num_panes": 2,
    }
    
    all_materials = [frame_material]
    
    catalogs = ['bc-mf', 'gb-mf', 'rp-mf']
    release_id = '2024-an'
    location_id = 'us-us-national'
    labor_type = 'std'
    measurement_system = 'imp'
    
    results = {}
    
    # Test both modes
    for mode in ["totalop", "bare_material"]:
        print(f"\n{'─' * 80}")
        print(f"Testing mode: {mode}")
        print(f"{'─' * 80}")
        
        derived = _derive_frame_cost_from_window_minus_glass(
            material=frame_material,
            all_materials=all_materials,
            client=client,
            catalogs=catalogs,
            release_id=release_id,
            location_id=location_id,
            labor_type=labor_type,
            measurement_system=measurement_system,
            cost_calculation_basis=mode,
        )
        
        if derived:
            frame_cost = derived.get("unit_cost", 0.0)
            window_cost = derived.get("_window_unit_cost_per_sf", 0.0)
            glazing_cost = derived.get("_glazing_unit_cost_per_sf", 0.0)
            window_id = derived.get("window_unit_id", "N/A")
            glazing_id = derived.get("glazing_id", "N/A")
            window_desc = derived.get("window_unit_desc", "")
            glazing_desc = derived.get("glazing_desc", "")
            
            results[mode] = {
                "frame_cost_per_sf": frame_cost,
                "window_unit_cost_per_sf": window_cost,
                "glazing_unit_cost_per_sf": glazing_cost,
                "window_unit_id": window_id,
                "glazing_id": glazing_id,
                "window_desc": window_desc,
                "glazing_desc": glazing_desc,
            }
            
            print(f"  Window unit ID:        {window_id}")
            print(f"  Window unit cost:      ${window_cost:.2f}/SF")
            print(f"  Glazing ID:            {glazing_id}")
            print(f"  Glazing cost:          ${glazing_cost:.2f}/SF")
            print(f"  → Frame cost:          ${frame_cost:.2f}/SF")
        else:
            print(f"  ERROR: Frame derivation failed")
            results[mode] = None
    
    # Compare results
    print(f"\n{'═' * 80}")
    print("COMPARISON SUMMARY")
    print(f"{'═' * 80}")
    
    if results.get("totalop") and results.get("bare_material"):
        totalop_cost = results["totalop"]["frame_cost_per_sf"]
        bare_cost = results["bare_material"]["frame_cost_per_sf"]
        totalop_window = results["totalop"]["window_unit_cost_per_sf"]
        bare_window = results["bare_material"]["window_unit_cost_per_sf"]
        totalop_glazing = results["totalop"]["glazing_unit_cost_per_sf"]
        bare_glazing = results["bare_material"]["glazing_unit_cost_per_sf"]
        
        difference = totalop_cost - bare_cost
        percent_diff = (difference / totalop_cost) * 100 if totalop_cost > 0 else 0
        
        print(f"  totalop window cost:        ${totalop_window:.2f}/SF")
        print(f"  bare_material window cost:  ${bare_window:.2f}/SF")
        print(f"  totalop glazing cost:       ${totalop_glazing:.2f}/SF")
        print(f"  bare_material glazing cost: ${bare_glazing:.2f}/SF")
        print()
        print(f"  totalop frame cost:         ${totalop_cost:.2f}/SF")
        print(f"  bare_material frame cost:   ${bare_cost:.2f}/SF")
        print(f"  Difference:                 ${difference:.2f}/SF ({percent_diff:.1f}%)")
        print()
        
        # Expected: bare_material should be 30-40% lower (no O&P)
        if bare_cost < totalop_cost:
            if 25 <= percent_diff <= 45:
                print("  ✓ PASS: bare_material cost is 25-45% lower (expected range)")
            else:
                print(f"  ⚠ WARN: Cost difference {percent_diff:.1f}% is outside expected 25-45% range")
        elif bare_cost == totalop_cost:
            print("  ✗ FAIL: Costs are identical (bug not fixed)")
        else:
            print("  ✗ FAIL: bare_material cost is higher than totalop (unexpected)")
    else:
        print("  ✗ FAIL: Could not retrieve costs for comparison")
    
    print(f"{'═' * 80}")
    
    # Save results to JSON
    output_path = MEASURE_DIR / "tests" / "output" / "frame_cost_comparison.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")

if __name__ == "__main__":
    test_frame_cost_comparison()

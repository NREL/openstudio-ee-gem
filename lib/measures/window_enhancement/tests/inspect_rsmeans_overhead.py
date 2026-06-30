#!/usr/bin/env python
"""
Inspect RSMeans API response to understand O&P structure for window and glazing.
"""

import sys
import os
import json
from pathlib import Path

MEASURE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MEASURE_DIR / "resources"))

from dotenv import load_dotenv
load_dotenv()

from call_rsmeans_api import RSMeansAPIClient

def inspect_rsmeans_costs():
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
    print("RSMeans Cost Structure Analysis")
    print("=" * 80)
    
    # Cost lines to inspect
    test_items = [
        ("085210700100", "Wood operable window, 3'×3', double IGU"),
        ("088130100020", "Insulating glass, 2 lites, 1/8\" float, under 15 SF"),
    ]
    
    for rsmeans_id, description in test_items:
        print(f"\n{'─' * 80}")
        print(f"{description}")
        print(f"RSMeans ID: {rsmeans_id}")
        print(f"{'─' * 80}")
        
        response = client.get_unit_costlines(
            release_id='2024-an',
            catalog='bc-mf',
            location_id='us-us-national',
            labor_type='std',
            measurement_system='imp',
            division_code=rsmeans_id,
        )
        
        if not response or 'items' not in response:
            print("  ERROR: No response from API")
            continue
        
        # Find the matching item
        item = None
        for i in response['items']:
            if i.get('id') == rsmeans_id:
                item = i
                break
        
        if not item:
            print(f"  ERROR: Could not find item {rsmeans_id} in response")
            continue
        
        loc = item.get('localizedCosts', {})
        
        # Extract both bare and O&P costs
        total_bare = loc.get('totalCost', 0.0)
        total_op = loc.get('totalOpCost', 0.0)
        
        mat_bare = loc.get('materialCost', 0.0)
        mat_op = loc.get('materialOpCost', 0.0)
        
        lab_bare = loc.get('laborCost', 0.0)
        lab_op = loc.get('laborOpCost', 0.0)
        
        eq_bare = loc.get('equipmentCost', 0.0)
        eq_op = loc.get('equipmentOpCost', 0.0)
        
        # Calculate O&P amounts and percentages
        total_overhead = total_op - total_bare
        total_overhead_pct = (total_overhead / total_bare * 100) if total_bare > 0 else 0
        
        mat_overhead = mat_op - mat_bare
        mat_overhead_pct = (mat_overhead / mat_bare * 100) if mat_bare > 0 else 0
        
        lab_overhead = lab_op - lab_bare
        lab_overhead_pct = (lab_overhead / lab_bare * 100) if lab_bare > 0 else 0
        
        eq_overhead = eq_op - eq_bare
        eq_overhead_pct = (eq_overhead / eq_bare * 100) if eq_bare > 0 else 0
        
        print(f"\n  Material:")
        print(f"    Bare cost:        ${mat_bare:,.2f}")
        print(f"    With O&P:         ${mat_op:,.2f}")
        print(f"    O&P amount:       ${mat_overhead:,.2f} ({mat_overhead_pct:.1f}%)")
        
        print(f"\n  Labor:")
        print(f"    Bare cost:        ${lab_bare:,.2f}")
        print(f"    With O&P:         ${lab_op:,.2f}")
        print(f"    O&P amount:       ${lab_overhead:,.2f} ({lab_overhead_pct:.1f}%)")
        
        if eq_bare > 0:
            print(f"\n  Equipment:")
            print(f"    Bare cost:        ${eq_bare:,.2f}")
            print(f"    With O&P:         ${eq_op:,.2f}")
            print(f"    O&P amount:       ${eq_overhead:,.2f} ({eq_overhead_pct:.1f}%)")
        
        print(f"\n  Total:")
        print(f"    Bare cost:        ${total_bare:,.2f}")
        print(f"    With O&P:         ${total_op:,.2f}")
        print(f"    O&P amount:       ${total_overhead:,.2f} ({total_overhead_pct:.1f}%)")
        
        print(f"\n  Unit: {loc.get('unitOfMeasure', 'N/A')}")
        print(f"  Description: {item.get('description', 'N/A')}")
    
    print(f"\n{'═' * 80}")
    print("ANALYSIS")
    print(f"{'═' * 80}")
    print("If O&P percentages differ between window unit and glazing,")
    print("the subtraction method (frame = window - glazing) will produce")
    print("different results in totalop vs bare_material mode.")
    print(f"{'═' * 80}")

if __name__ == "__main__":
    inspect_rsmeans_costs()

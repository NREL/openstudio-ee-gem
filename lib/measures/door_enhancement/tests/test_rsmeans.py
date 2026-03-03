#!/usr/bin/env python
"""
Test script to explore RSMeans API for window materials.
"""

import sys
import os
import json
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Get credentials
import configparser
REPO_ROOT = Path(__file__).parent.parent.parent.parent
config = configparser.ConfigParser()
config.read(REPO_ROOT / "config.ini")

from resources.call_rsmeans_api import RSMeansAPIClient

def test_rsmeans():
    client_id = os.getenv('client_id')
    client_secret = os.getenv('client_secret')
    
    if not client_id or not client_secret:
        print("ERROR: RSMeans credentials not set")
        return

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=False)
    
    if not client.authenticate():
        print("Failed to authenticate")
        return
    
    print("=" * 80)
    print("RSMeans API Test - Window Materials")
    print("=" * 80)
    
    # Test different search terms and divisions
    test_queries = [
        # (search_term, division_code, description)
        ("window", "08", "Generic window"),
        ("windows", "08", "Windows plural"),
        ("glazing", "08", "Glazing"),
        ("glass", "08", "Glass"),
        ("IGU", "08", "Insulated Glass Unit"),
        ("insulated glass", "08", "Insulated glass"),
        ("replacement window", "08", "Replacement window"),
        ("window assembly", "08", "Window assembly"),
        ("aluminum window", "08", "Aluminum window frame"),
        ("wood window", "08", "Wood window frame"),
        ("window frame", "08", "Window frame"),
        ("window sash", "08", "Window sash"),
        ("double hung window", "08", "Double hung window"),
        ("casement window", "08", "Casement window"),
        ("fixed window", "08", "Fixed window"),
    ]
    
    results = {}
    
    for search_term, division, description in test_queries:
        print(f"\nTesting: {description}")
        print(f"  Search term: '{search_term}', Division: {division}")
        
        try:
            response = client.search_unit_costlines(
                release_id='2025-q4',
                measurement_system='imp',
                search_term=search_term,
                catalog='gb-mf',  # Try Green Building catalog
                location_id='us-us-national',
                labor_type='std',
                division_code=division,
            )
            
            if response and 'items' in response:
                items = response['items']
                print(f"  ✓ Found {len(items)} results")
                if items:
                    for i, item in enumerate(items[:3]):  # Show first 3
                        print(f"    [{i+1}] {item.get('description', 'N/A')}")
                        results[search_term] = {
                            'count': len(items),
                            'first_match': item.get('description', 'N/A'),
                            'division': division
                        }
            else:
                print(f"  ✗ No results")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY - Search Terms That Found Results:")
    print("=" * 80)
    for term, data in results.items():
        print(f"{term:30s} → {data['count']:3d} results, First: {data['first_match'][:40]}")
    
    print(f"\nSuccessful searches: {len(results)} out of {len(test_queries)}")
    
    # Try getting cost data for a successful search
    if results:
        first_successful = list(results.keys())[0]
        print(f"\n\nAttempting to get cost data for: '{first_successful}'")
        
        try:
            response = client.search_unit_costlines(
                release_id='2025-q4',
                measurement_system='imp',
                search_term=first_successful,
                catalog='gb-mf',
                location_id='us-us-national',
                labor_type='std',
                division_code='08',
            )
            
            if response and 'items' in response and response['items']:
                first_item = response['items'][0]
                division_id = first_item.get('id')
                
                print(f"Getting cost line for: {first_item.get('description')}")
                
                cost_response = client.get_unit_costlines(
                    release_id='2025-q4',
                    catalog='gb-mf',
                    location_id='us-us-national',
                    labor_type='std',
                    measurement_system='imp',
                    division_code=division_id,
                )
                
                if cost_response and 'items' in cost_response:
                    for item in cost_response['items'][:3]:
                        costs = item.get('localizedCosts', {})
                        unit_cost = costs.get('totalOpCost', 0)
                        print(f"\n  Description: {item.get('description', 'N/A')}")
                        print(f"  Unit Cost: ${unit_cost:,.2f}")
                        print(f"  Unit: {item.get('unit_of_measure', 'N/A')}")
        except Exception as e:
            print(f"Error getting cost data: {e}")

if __name__ == "__main__":
    test_rsmeans()

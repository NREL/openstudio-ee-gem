#!/usr/bin/env python
"""
Test RSMeans API across different catalogs.
"""

import sys
import os
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import configparser
REPO_ROOT = Path(__file__).parent.parent.parent.parent
config = configparser.ConfigParser()
config.read(REPO_ROOT / "config.ini")

from resources.call_rsmeans_api import RSMeansAPIClient

def test_catalogs():
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
    print("Testing RSMeans Catalogs for Window-related Materials")
    print("=" * 80)
    
    # Test different catalogs
    catalogs = ['bc-mf', 'gb-mf', 'rp-mf', 'sq-mf', 'hc-mf', 'si-mf']
    test_terms = ['window', 'glass', 'glazing', 'frame']
    
    catalog_results = {}
    
    for catalog in catalogs:
        print(f"\nCatalog: {catalog}")
        print("-" * 40)
        
        for search_term in test_terms:
            try:
                response = client.search_unit_costlines(
                    release_id='2025-q4',
                    measurement_system='imp',
                    search_term=search_term,
                    catalog=catalog,
                    location_id='us-us-national',
                    labor_type='std',
                    division_code='08',
                )
                
                if response and 'items' in response and response['items']:
                    count = len(response['items'])
                    first_desc = response['items'][0].get('description', 'N/A')
                    print(f"  {search_term:15s} → {count:3d} results")
                    if catalog not in catalog_results:
                        catalog_results[catalog] = {}
                    catalog_results[catalog][search_term] = count
            except Exception as e:
                pass
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY - Results by Catalog:")
    print("=" * 80)
    
    for catalog in catalogs:
        if catalog in catalog_results and catalog_results[catalog]:
            results = catalog_results[catalog]
            total = sum(results.values())
            print(f"{catalog:10s}: {total:3d} total results")
            for term, count in results.items():
                print(f"             {term}: {count}")
        else:
            print(f"{catalog:10s}: No results")

if __name__ == "__main__":
    test_catalogs()

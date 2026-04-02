#!/usr/bin/env python
"""
Test RSMeans API across different divisions for window materials.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import configparser
REPO_ROOT = Path(__file__).parent.parent.parent.parent
config = configparser.ConfigParser()
config.read(REPO_ROOT / "config.ini")

from resources.call_rsmeans_api import RSMeansAPIClient

def test_divisions():
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
    print("Testing RSMeans Divisions for Window-related Materials")
    print("=" * 80)
    
    # Test different divisions
    divisions = [
        ('01', 'General Requirements'),
        ('02', 'Existing Conditions'),
        ('03', 'Concrete'),
        ('04', 'Masonry'),
        ('05', 'Metals'),
        ('06', 'Wood/Plastic/Composites'),
        ('07', 'Thermal/Moisture Protection'),
        ('08', 'Openings/Windows/Doors'),
        ('09', 'Finishes'),
        ('10', 'Specialties'),
        ('21', 'Fire Suppression'),
        ('22', 'Plumbing'),
        ('23', 'HVAC'),
        ('26', 'Electrical'),
    ]
    
    test_term = 'window'
    catalog = 'bc-mf'  # Building Construction catalog
    
    results = {}
    
    for div_code, div_name in divisions:
        try:
            response = client.search_unit_costlines(
                release_id='2025-q4',
                measurement_system='imp',
                search_term=test_term,
                catalog=catalog,
                location_id='us-us-national',
                labor_type='std',
                division_code=div_code,
            )
            
            if response and 'items' in response and response['items']:
                count = len(response['items'])
                first_desc = response['items'][0].get('description', 'N/A')[:60]
                print(f"Division {div_code}: {count:3d} results - {first_desc}")
                results[div_code] = count
            else:
                print(f"Division {div_code}: No results")
        except Exception as e:
            print(f"Division {div_code}: Error - {str(e)[:50]}")
    
    # Try without division constraint
    print("\n" + "=" * 40)
    print("Trying without division constraint:")
    print("=" * 40)
    
    try:
        response = client.search_unit_costlines(
            release_id='2025-q4',
            measurement_system='imp',
            search_term=test_term,
            catalog=catalog,
            location_id='us-us-national',
            labor_type='std',
            division_code=None,
        )
        
        if response and 'items' in response and response['items']:
            count = len(response['items'])
            print(f"Found {count} results when searching all divisions:")
            for i, item in enumerate(response['items'][:5]):
                print(f"  [{i+1}] {item.get('description', 'N/A')}")
        else:
            print("No results found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_divisions()

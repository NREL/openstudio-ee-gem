#!/usr/bin/env python
"""
Simple RSMeans API demo: search-term-based cost lookup.

Usage:
    python test_call_rsmeans_api.py

This script:
    - Loads RSMeans credentials from .env or environment variables
    - Searches one RSMeans catalog using a single search term
    - Picks the first matching cost line
    - Retrieves detailed costs for that line item
    - Writes JSON outputs next to this script

Required environment variables (or .env file):
    client_id
    client_secret
"""

import os
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"
if str(RESOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(RESOURCES_DIR))

from call_rsmeans_api import RSMeansAPIClient

# ---- Hard-coded demo inputs ----
SEARCH_TERM = "aluminum door frame"
DIVISION_CODE_FILTER = None  # e.g. "08" to constrain search to Division 08
QUANTITY = 1.0
UNIT = "ea"

RELEASE_ID = "2024-an"
CATALOG = "bc-mf"
LOCATION_ID = "us-us-national"
LABOR_TYPE = "std"
MEASUREMENT_SYSTEM = "imp"
USE_SANDBOX = False


def load_search_input() -> Dict[str, Any]:
    """Load search parameters from JSON input file."""
    input_file = "rsmeans_search_input.json"
    if os.path.exists(input_file):
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load {input_file}: {e}")
    return {"search_term": SEARCH_TERM, "user_description": ""}


def prompt_for_user_description() -> bool:
    """Ask user if they want to provide additional description."""
    response = input("\nDo you want to provide additional description keywords? (yes/no): ").strip().lower()
    return response in ["yes", "y"]


def filter_by_user_description(items: list, user_description: str) -> list:
    """Filter search items by user-provided description keywords."""
    if not user_description.strip():
        return items
    
    keywords = [kw.strip().lower() for kw in user_description.split(" ") if kw.strip()]
    filtered = []
    
    for item in items:
        description = item.get("description", "").lower()
        # Item matches if it contains ALL keywords
        if all(kw in description for kw in keywords):
            filtered.append(item)
    
    return filtered if filtered else items  # Return original if no matches


def load_credentials() -> Optional[Dict[str, str]]:
    load_dotenv()
    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret}


def _extract_search_items(search_results: Dict[str, Any]) -> list:
    # Handles both shapes: {"items": [...]} and {"unitLines": {"items": [...]}}
    if isinstance(search_results.get("items"), list):
        return search_results["items"]
    return search_results.get("unitLines", {}).get("items", [])


def lookup_by_search_term(client: RSMeansAPIClient, search_term: str, user_description: str = "") -> Dict[str, Any]:
    # Auto-detect division based on search term
    division_code = DIVISION_CODE_FILTER
    if "door" in search_term.lower():
        division_code = "08"  # Division 08: Openings
        print(f"Auto-detected 'door' in search term. Constraining to Division 08 (Openings)")

    search_results = client.search_unit_costlines(
        release_id=RELEASE_ID,
        measurement_system=MEASUREMENT_SYSTEM,
        search_term=search_term,
        catalog=CATALOG,
        location_id=LOCATION_ID,
        labor_type=LABOR_TYPE,
        division_code=division_code,
    )

    if not search_results:
        return {
            "status": "search_error",
            "message": "Search call failed or returned no payload",
        }

    with open("search_results.json", "w", encoding="utf-8") as f:
        json.dump(search_results, f, indent=2)

    items = _extract_search_items(search_results)
    if not items:
        return {
            "status": "no_match",
            "message": "No RSMeans match found for search term",
            "search_term": search_term,
        }

    # Filter out demolition results
    filtered_items = []
    for item in items:
        description = item.get("description", "").lower()
        if "demolition" not in description and "demo" not in description:
            filtered_items.append(item)
    
    if not filtered_items:
        filtered_items = items  # Fall back to all items if none pass demo filter
    
    # Apply user description filter if provided
    if user_description.strip():
        user_filtered = filter_by_user_description(filtered_items, user_description)
        if user_filtered:
            filtered_items = user_filtered
            print(f"Filtered search results using description: '{user_description}'")
    
    first_match = filtered_items[0]

    cost_line_id = first_match.get("id")
    if not cost_line_id:
        return {
            "status": "no_costline_id",
            "message": "Selected result did not include an id",
            "first_match": first_match,
        }

    cost_lines = client.get_unit_costlines(
        release_id=RELEASE_ID,
        measurement_system=MEASUREMENT_SYSTEM,
        division_code=cost_line_id,
        catalog=CATALOG,
        location_id=LOCATION_ID,
        labor_type=LABOR_TYPE,
    )

    if not cost_lines or not cost_lines.get("items"):
        return {
            "status": "no_cost_detail",
            "message": "No cost detail returned for matched item",
            "first_match": first_match,
        }

    with open("unit_costline_results.json", "w", encoding="utf-8") as f:
        json.dump(cost_lines, f, indent=2)

    matched_item = next((item for item in cost_lines["items"] if item.get("id") == cost_line_id), None)
    if not matched_item:
        return {
            "status": "no_cost_match",
            "message": "Could not find matched item in cost detail list",
            "first_match": first_match,
        }

    unit_cost = float(matched_item.get("localizedCosts", {}).get("totalOpCost", 0.0))
    total_cost = unit_cost * float(QUANTITY)

    return {
        "status": "matched",
        "search_term": search_term,
        "match": {
            "rsmeans_id": matched_item.get("id", ""),
            "description": matched_item.get("description", ""),
            "unit": UNIT,
            "quantity": QUANTITY,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
        },
        "search_metadata": {
            "division_code_filter": DIVISION_CODE_FILTER,
            "division_code_applied": division_code,
            "release_id": RELEASE_ID,
            "catalog": CATALOG,
            "location_id": LOCATION_ID,
            "labor_type": LABOR_TYPE,
            "measurement_system": MEASUREMENT_SYSTEM,
        },
    }


def main() -> int:
    # Load input parameters from JSON file
    search_input = load_search_input()
    search_term = search_input.get("search_term", SEARCH_TERM)
    user_description = search_input.get("user_description", "")
    
    # If no user description provided, ask user
    if not user_description.strip():
        if prompt_for_user_description():
            print(f"\nPlease edit the file 'rsmeans_search_input.json' in this directory.")
            print(f"Add your description keywords to the 'user_description' field.")
            print(f"Example: '3\'-0\" x 7\'-0\"' or 'single opening' or 'aluminum hollow metal'")
            print(f"Then run this script again.\n")
            return 0
    
    creds = load_credentials()
    if not creds:
        print("ERROR: RSMeans API credentials not found.")
        print("Set environment variables: client_id, client_secret")
        print("Or create a .env file with these values.")
        return 1

    client = RSMeansAPIClient(creds["client_id"], creds["client_secret"], use_sandbox=USE_SANDBOX)
    if not client.authenticate():
        print("ERROR: Authentication failed.")
        return 1

    result = lookup_by_search_term(client, search_term, user_description)

    print("\n" + "=" * 70)
    print("RSMeans Search-Term Result")
    print("=" * 70)
    print(f"Status: {result.get('status')}")

    if result.get("status") == "matched":
        match = result.get("match", {})
        print(f"Search Term:      {search_term}")
        if user_description:
            print(f"Description Filt: {user_description}")
        print(f"RSMeans ID:       {match.get('rsmeans_id', 'N/A')}")
        print(f"Description:      {match.get('description', 'N/A')}")
        print(f"Unit Cost:        ${match.get('unit_cost', 0.0):,.2f}")
        print(f"Total Cost:       ${match.get('total_cost', 0.0):,.2f}")
        print("Saved:            search_results.json, unit_costline_results.json")
    else:
        print(f"Message: {result.get('message', 'No additional details')}")

    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

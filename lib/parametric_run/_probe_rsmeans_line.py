"""Probe the RSMeans API for a specific costline ID and dump localizedCosts keys."""
import sys
from pathlib import Path
import json

HERE = Path(__file__).parent
ROOF_RES = HERE.parent / "measures" / "IncreaseInsulationRValueForRoofs" / "resources"
sys.path.insert(0, str(ROOF_RES))

from dotenv import load_dotenv  # noqa: E402
import os  # noqa: E402

# Load .env from various candidate spots
for cand in [HERE / ".env", HERE.parent / ".env", HERE.parent.parent / ".env", ROOF_RES / ".env"]:
    if cand.exists():
        load_dotenv(cand)
        break
else:
    load_dotenv()

import call_rsmeans_api as cra  # noqa: E402

client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
print("client_id present:", bool(client_id), "secret present:", bool(client_secret))

client = cra.RSMeansAPIClient(client_id, client_secret, use_sandbox=False)
if not client.authenticate():
    print("AUTH FAILED")
    sys.exit(1)

ids_to_probe = [
    "072216101910",  # XPS roof
    "072126101000",  # Blown FG roof
    "072216101700",  # Polyiso roof
    "072123100100",  # Blown mineral wool roof
]
for line_id in ids_to_probe:
    print("=" * 70)
    print("Line:", line_id)
    for catalog in ["bc-mf", "gb-mf", "rp-mf"]:
        try:
            r = client.get_unit_costlines(
                release_id="2024-an",
                catalog=catalog,
                location_id="us-us-national",
                labor_type="std",
                measurement_system="imp",
                division_code=line_id,
            )
        except Exception as e:
            print(f"  catalog={catalog} ERROR: {e}")
            continue
        if not r or "items" not in r:
            print(f"  catalog={catalog} no items")
            continue
        match = next((it for it in r["items"] if it.get("id") == line_id), None)
        if not match:
            print(f"  catalog={catalog} id not found in items")
            continue
        print(f"  catalog={catalog}")
        print(f"    description: {match.get('description', '')[:100]}")
        print(f"    UoM: {match.get('unitOfMeasure', '')}")
        lc = match.get("localizedCosts", {})
        print(f"    localizedCosts keys: {sorted(lc.keys())}")
        print(f"    localizedCosts: {json.dumps(lc, indent=2)}")
        # also dump top-level keys to find anything else useful
        print(f"    item top-level keys: {sorted(match.keys())}")
        break

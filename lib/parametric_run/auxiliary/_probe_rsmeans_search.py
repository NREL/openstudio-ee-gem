"""Probe RSMeans API by searching for candidate costline IDs.

Searches for terms relevant to:
  - Graphite Polystyrene (GPS) Foam Board (vs current EPS R4 fallback)
  - Mineral Wool Heavy Density Blanket (vs current R15 batt fallback)
  - Honeycomb Core Steel Door (vs current hollow-core steel fallback)
"""
import sys
import os
import json
from pathlib import Path

HERE = Path(__file__).parent
PARAMETRIC_RUN_DIR = HERE.parent
ROOF_RES = PARAMETRIC_RUN_DIR.parent / "measures" / "IncreaseInsulationRValueForRoofs" / "resources"
sys.path.insert(0, str(ROOF_RES))

from dotenv import load_dotenv  # noqa: E402

for cand in [HERE / ".env", PARAMETRIC_RUN_DIR / ".env", PARAMETRIC_RUN_DIR.parent / ".env", ROOF_RES / ".env"]:
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

# (search_term, division_code_or_None, label)
QUERIES = [
    # GPS / EPS / XPS variants -- looking for graphite or higher R/inch lines
    ("graphite polystyrene", "07", "GPS direct"),
    ("polystyrene foam board", "0721", "Polystyrene rigid 0721"),
    ("polystyrene rigid", "0721", "Polystyrene rigid 0721 v2"),
    ("expanded polystyrene", "0721", "EPS lines"),
    # Mineral wool heavy density / rigid board
    ("mineral wool rigid", "0721", "Mineral wool rigid"),
    ("mineral wool board", "0721", "Mineral wool board"),
    ("mineral fiber board", "0721", "Mineral fiber board"),
    ("rockwool", "0721", "Rockwool"),
    ("mineral wool", "07", "Mineral wool any 07"),
    # Steel doors -- looking for honeycomb / 18ga commercial
    ("honeycomb steel door", "08", "Honeycomb steel"),
    ("honeycomb core door", "08", "Honeycomb core"),
    ("steel door 18 ga", "0813", "Steel door 18ga"),
    ("steel flush door", "0813", "Steel flush"),
]

for term, div, label in QUERIES:
    print("\n" + "=" * 80)
    print(f"[{label}]  term={term!r}  division={div!r}")
    found_any = False
    for catalog in ["bc-mf"]:
        r = client.search_unit_costlines(
            release_id="2024-an",
            measurement_system="imp",
            search_term=term,
            catalog=catalog,
            division_code=div,
        )
        if not r:
            continue
        items = r.get("items") or r.get("unitLines", {}).get("items") or []
        # Sort: prefer items where description contains key words
        def score(it):
            d = (it.get("description") or "").lower()
            s = 0
            if "graphite" in d:
                s += 100
            if "rigid" in d or "board" in d:
                s += 5
            if "honeycomb" in d:
                s += 100
            if "demolition" in d or "remove" in d:
                s -= 50
            return -s
        items_sorted = sorted(items, key=score)
        for it in items_sorted[:8]:
            desc = (it.get("description") or "").replace("\n", " ")[:140]
            print(f"  [{catalog}] {it.get('id')}  uom={it.get('unitOfMeasure', '')}  {desc}")
            found_any = True
    if not found_any:
        print("  (no items)")

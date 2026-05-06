"""Aggregate key metrics across run_test_001..008 for cross-run comparison."""
import csv
from pathlib import Path

HERE = Path(__file__).parent
RUNS = [f"run_test_{i:03d}" for i in range(1, 9)]
COMBOS = {
    "run_test_001": "S1,S2,S3", "run_test_002": "S1,S4,S5",
    "run_test_003": "S2,S5,S6", "run_test_004": "S3,S4,S6",
    "run_test_005": "S5,S6,S7", "run_test_006": "S6,S7,S8",
    "run_test_007": "S7,S8,S9", "run_test_008": "S1,S5,S9",
}
KEYS = [
    "scenario", "total_site_energy_gj",
    "annual_electricity_cost_usd", "annual_gas_cost_usd",
    "wall_insulation_total_cost_with_overhead_and_profit_usd",
    "roof_insulation_total_cost_with_overhead_and_profit_usd",
    "window_enhancement_total_cost_with_overhead_and_profit_usd",
    "door_enhancement_total_cost_with_overhead_and_profit_usd",
    "window_enhancement_material_cost_usd",
    "door_enhancement_material_cost_usd",
    "total_additional_embodied_carbon_kg",
    "wall_insulation_material_type", "roof_insulation_material_type",
    "door_option", "caulking_option", "window_num_panes",
]


def load(run):
    p = HERE / "simulations" / run / "parametric_results.csv"
    if not p.exists():
        return None
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    by = {r[0]: r[1:] for r in rows if r}
    scenarios = by.get("scenario", [])
    out = []
    for i, sc in enumerate(scenarios):
        rec = {"scenario": sc}
        for k in KEYS[1:]:
            v = by.get(k, [""] * len(scenarios))
            rec[k] = v[i] if i < len(v) else ""
        out.append(rec)
    return out


def f(s):
    try:
        return float(s)
    except Exception:
        return None


print(f"\n{'Run':<14}{'Combos':<10}{'Scenario':<42}{'Site_GJ':>9}{'OpCost$':>10}{'Wall$':>9}{'Roof$':>9}{'Win$':>9}{'Door$':>9}{'EmbC_kg':>10}")
print("=" * 131)
for run in RUNS:
    data = load(run)
    if not data:
        print(f"{run}  (no data)")
        continue
    for r in data:
        site = f(r["total_site_energy_gj"]) or 0
        op = (f(r["annual_electricity_cost_usd"]) or 0) + (f(r["annual_gas_cost_usd"]) or 0)
        wc = f(r["wall_insulation_total_cost_with_overhead_and_profit_usd"]) or 0
        rc = f(r["roof_insulation_total_cost_with_overhead_and_profit_usd"]) or 0
        wi = f(r["window_enhancement_total_cost_with_overhead_and_profit_usd"]) or 0
        dc = f(r["door_enhancement_total_cost_with_overhead_and_profit_usd"]) or 0
        ec = f(r["total_additional_embodied_carbon_kg"]) or 0
        sc = r["scenario"][:40]
        print(f"{run:<14}{COMBOS[run]:<10}{sc:<42}{site:>9.1f}{op:>10.0f}{wc:>9.0f}{rc:>9.0f}{wi:>9.0f}{dc:>9.0f}{ec:>10.0f}")
    print("-" * 131)

# Component-level deep dive: per-scenario material vs labor for door/window
print("\n\nDETAIL: door/window material costs per scenario")
print(f"{'Run':<14}{'Scenario':<44}{'WinMat$':>10}{'DoorMat$':>10}{'Door_opt':<28}{'Caulk':<14}{'Panes':<6}")
print("=" * 130)
for run in RUNS:
    data = load(run)
    if not data:
        continue
    for r in data:
        wm = f(r["window_enhancement_material_cost_usd"]) or 0
        dm = f(r["door_enhancement_material_cost_usd"]) or 0
        do = (r.get("door_option") or "")[:26]
        ck = (r.get("caulking_option") or "")[:12]
        panes = (r.get("window_num_panes") or "")[:4]
        sc = r["scenario"][:42]
        print(f"{run:<14}{sc:<44}{wm:>10.0f}{dm:>10.0f}{do:<28}{ck:<14}{panes:<6}")

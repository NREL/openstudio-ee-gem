"""Drive workflow.py multiple times with distinct CUSTOM_COMBOS per RUN_NAME.

Each entry in RUNS triggers one full subprocess invocation of workflow.py with
WORKFLOW_RUN_NAME, WORKFLOW_OVERWRITE_EXISTING=1, and WORKFLOW_CUSTOM_COMBOS_JSON
set in the child env. Outputs land in simulations/<run_name>/. Because
OVERWRITE_EXISTING is forced on, prior results are recomputed against the
current measure code -- useful after editing any measure.

To run a single test, comment out the other entries in RUNS, or invoke
workflow.py directly with WORKFLOW_RUN_NAME / WORKFLOW_CUSTOM_COMBOS_JSON set
manually.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOW = HERE / "workflow.py"

# --- The 9 historical retrofit scenarios, each labeled S1..S9. ---
S1 = {
    "wall_r_value": 10,
    "wall_insulation_material_type": "Fiberglass Batts",
    "roof_r_value": 20,
    "roof_insulation_material_type": "Blown Fiberglass",
    "window_num_panes": None,
    "door_option": None,
}
S2 = {
    "wall_r_value": 13,
    "wall_insulation_material_type": "Fiberglass Batts",
    "roof_r_value": 24.4,
    "roof_insulation_material_type": "Blown Fiberglass",
    "window_num_panes": None,
    "door_option": None,
}
S3 = {
    "wall_r_value": 13,
    "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    "roof_r_value": 24.4,
    "roof_insulation_material_type": "Extruded Polystyrene (XPS) Foam Board",
    "window_num_panes": None,
    "door_option": None,
}
S4 = {
    "wall_r_value": 20,
    "wall_insulation_material_type": "Fiberglass Batts",
    "roof_r_value": 30,
    "roof_insulation_material_type": "Blown Fiberglass",
    "window_num_panes": None,
    "door_option": None,
}
S5 = {
    "wall_r_value": 30,
    "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    "roof_r_value": None,
    "window_num_panes": None,
    "door_option": None,
}
S6 = {
    "wall_r_value": None,
    "roof_r_value": 30,
    "roof_insulation_material_type": "Blown Fiberglass",
    "window_num_panes": None,
    "door_option": None,
}
S7 = {
    "wall_r_value": 10,
    "wall_insulation_material_type": "Extruded Polystyrene (XPS) Foam Board",
    "roof_r_value": 15,
    "roof_insulation_material_type": "Blown Mineral Wool",
    "door_option": "glass door",
    "door_infiltration_reduction_percent": 20.0,
    "door_bottom_seal_option": "none",
    "door_top_side_seal_option": "none",
    "window_num_panes": 1,
    "window_infiltration_reduction_percent": 20.0,
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "wf_option": "none",
    "film_option": "safety film",
    "caulking_option": "none",
}
S8 = {
    "wall_r_value": 30,
    "wall_insulation_material_type": "Expanded Polystyrene (EPS) Foam Board",
    "roof_r_value": 25,
    "roof_insulation_material_type": "Polyiso Insulation Foam Board",
    "door_option": "polystyrene core steel door",
    "door_infiltration_reduction_percent": 25.0,
    "door_bottom_seal_option": "brush weatherstrip",
    "door_top_side_seal_option": "silicone adhesive smoke gasket",
    "window_num_panes": 2,
    "window_infiltration_reduction_percent": 25.0,
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "wf_option": "none",
    "film_option": "anti-graffiti film",
    "caulking_option": "polyurethane",
}
S9 = {
    "wall_r_value": 20.4,
    "wall_insulation_material_type": "Fiberglass Batts",
    "roof_r_value": 34.5,
    "roof_insulation_material_type": "Blown Fiberglass",
    "door_option": "wooden door",
    "door_infiltration_reduction_percent": 30.0,
    "door_bottom_seal_option": "automatic door bottom",
    "door_top_side_seal_option": "jamb weatherstrip",
    "window_num_panes": 3,
    "window_enhancement_infiltration_reduction_percent": 30.0,
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "wf_option": "none",
    "film_option": "low-e film",
    "caulking_option": "acrylic",
}

# S10: fresh combo with Mineral Wool wall + GPS roof + honeycomb steel door +
# 2-pane glazing, wood-aluminium frame, solar-control film, polyurethane caulk.
# Distinct from S1..S9 in every measure component.
S10 = {
    "wall_r_value": 30,
    "wall_insulation_material_type": "Mineral Wool Heavy Density Blanket",
    "roof_r_value": 28,
    "roof_insulation_material_type": "Graphite Polystyrene (GPS) Foam Board",
    "door_option": "honeycomb core steel door",
    "door_infiltration_reduction_percent": 22.0,
    "door_bottom_seal_option": "brush weatherstrip",
    "door_top_side_seal_option": "jamb weatherstrip",
    "window_num_panes": 2,
    "window_enhancement_infiltration_reduction_percent": 22.0,
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "wf_option": "wood-aluminium window frame",
    "film_option": "solar control film",
    "caulking_option": "polyurethane",
}

# --- Mapping of run_name -> list of scenario combos to feed workflow.py. ---
# Each list entry produces one non-baseline scenario (workflow.py always adds
# its own baseline). Modify, comment out, or add rows here to control what gets
# simulated when this script runs.
RUNS = [
    ("run_test_001", [S1, S2, S3]),
    ("run_test_002", [S1, S4, S5]),
    ("run_test_003", [S2, S5, S6]),
    ("run_test_004", [S3, S4, S6]),
    ("run_test_005", [S5, S6, S7]),
    ("run_test_006", [S6, S7, S8]),
    ("run_test_007", [S7, S8, S9]),
    ("run_test_008", [S1, S5, S9]),
    ("run_test_009", [S10]),
]


def main() -> int:
    """Iterate RUNS, invoking workflow.py once per (run_name, combos) entry."""
    overall_start = time.time()
    failures: list[str] = []
    for idx, (run_name, combos) in enumerate(RUNS, start=1):
        # Banner per run for readability in the combined console log.
        print("\n" + "#" * 78)
        print(f"# [{idx}/{len(RUNS)}] {run_name}  ({len(combos)} retrofit scenarios)")
        print("#" * 78, flush=True)
        # Pass run-specific config to workflow.py via env vars (it reads these
        # in lieu of editing RUN_NAME / CUSTOM_COMBOS in the source file).
        env = os.environ.copy()
        env["WORKFLOW_RUN_NAME"] = run_name
        env["WORKFLOW_OVERWRITE_EXISTING"] = "1"
        env["WORKFLOW_CUSTOM_COMBOS_JSON"] = json.dumps(combos)
        run_start = time.time()
        # Launch workflow.py in a fresh subprocess so each run is fully isolated
        # (no leftover state, no module-level caching across runs).
        proc = subprocess.run([sys.executable, str(WORKFLOW)], env=env, cwd=str(HERE))
        elapsed = (time.time() - run_start) / 60.0
        print(f"\n>>> {run_name} finished in {elapsed:.1f} min (exit={proc.returncode})", flush=True)
        if proc.returncode != 0:
            failures.append(run_name)

    # Final summary across all runs.
    total = (time.time() - overall_start) / 60.0
    print("\n" + "=" * 78)
    print(f"ALL RUNS COMPLETE in {total:.1f} min")
    print(f"  Failures: {failures if failures else 'none'}")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

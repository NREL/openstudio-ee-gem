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

# Window frame type comparison: wood vs aluminum
WF_Wood = {
    "wall_r_value": None,
    "roof_r_value": None,
    "door_option": None,
    "window_num_panes": 2,
    "wf_option": "wood window frame",
    "film_option": "low-e film",
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "caulking_option": "polyurethane",
    "caulking_thickness": 0.008,
    "secondary_glazing_option": "install secondary glazing",
    "window_enhancement_infiltration_reduction_percent": 25.0,
}

WF_Aluminum = {
    "wall_r_value": None,
    "roof_r_value": None,
    "door_option": None,
    "window_num_panes": 2,
    "wf_option": "aluminum window frame",
    "film_option": "low-e film",
    "weatherstrip_option": "silicone adhesive smoke gasket",
    "caulking_option": "polyurethane",
    "caulking_thickness": 0.008,
    "secondary_glazing_option": "install secondary glazing",
    "window_enhancement_infiltration_reduction_percent": 25.0,
}

# --- Mapping of run_name -> list of scenario combos to feed workflow.py. ---
# Each list entry produces one non-baseline scenario (workflow.py always adds
# its own baseline). Modify, comment out, or add rows here to control what gets
# simulated when this script runs.
RUNS = [
    ("run_test_window_frames", [WF_Wood, WF_Aluminum]),
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

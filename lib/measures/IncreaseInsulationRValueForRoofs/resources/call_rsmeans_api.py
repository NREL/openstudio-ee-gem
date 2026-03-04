#!/usr/bin/env python
"""
RSMeans API helper for IncreaseInsulationRValueForRoofs.

This module re-exports the shared RSMeans API helper used by the
window_enhancement and door_enhancement measures, so this measure can
perform the same cost lookups without duplicating the implementation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_shared_helper():
    helper_path = (
        Path(__file__).resolve().parents[2]
        / "window_enhancement"
        / "resources"
        / "call_rsmeans_api.py"
    )
    if not helper_path.exists():
        raise FileNotFoundError(
            f"Shared RSMeans helper not found at {helper_path}."
        )
    spec = importlib.util.spec_from_file_location(
        "window_enhancement_call_rsmeans_api", helper_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_shared = _load_shared_helper()

RSMeansAPIClient = _shared.RSMeansAPIClient
run_rsmeans_cost_lookup = _shared.run_rsmeans_cost_lookup
search_materials_across_catalogs = _shared.search_materials_across_catalogs
extract_materials_from_model = _shared.extract_materials_from_model
DEFAULT_FEATURE_KEYS = _shared.DEFAULT_FEATURE_KEYS


def main() -> int:
    return _shared.main()


if __name__ == "__main__":
    raise SystemExit(main())

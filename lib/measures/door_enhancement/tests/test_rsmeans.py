#!/usr/bin/env python
"""Deterministic tests for door RSMeans helper logic."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"
if str(RESOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(RESOURCES_DIR))

from call_rsmeans_api import (
    DOOR_FALLBACK_RSMEANS_IDS,
    _get_default_fallback_rsmeans_id,
    generate_search_term_alternatives,
    search_materials_across_catalogs,
)


class FakeClient:
    def __init__(self, search_payload=None, fallback_payload=None):
        self.search_payload = search_payload or {"items": []}
        self.fallback_payload = fallback_payload or {}

    def search_unit_costlines(self, **kwargs):
        return self.search_payload

    def get_unit_costlines(self, **kwargs):
        rsmeans_id = kwargs.get("division_code")
        item = self.fallback_payload.get(rsmeans_id)
        if not item:
            return {"items": []}
        return {"items": [item]}


def test_generate_search_term_alternatives_contains_door_terms():
    alternatives = generate_search_term_alternatives("polystyrene core steel door")
    terms = [term for term, _ in alternatives]

    assert "door replacement" in terms
    assert "door unit" in terms
    assert "door" in terms


def test_generate_search_term_alternatives_no_window_specific_boilerplate():
    alternatives = generate_search_term_alternatives("window glazing")
    terms = [term for term, _ in alternatives]

    # Door helper should not inject window-measure-specific boilerplate terms.
    assert "window replacement" not in terms
    assert "window unit" not in terms
    assert "window assembly" not in terms


def test_get_default_fallback_rsmeans_id_uses_door_specific_mapping():
    assert _get_default_fallback_rsmeans_id("garage door") == DOOR_FALLBACK_RSMEANS_IDS["garage door"]
    assert _get_default_fallback_rsmeans_id("jamb weatherstripping") == DOOR_FALLBACK_RSMEANS_IDS["jamb weatherstrip"]
    assert _get_default_fallback_rsmeans_id("silicone smoke gasket") == DOOR_FALLBACK_RSMEANS_IDS["silicone adhesive smoke gasket"]
    assert _get_default_fallback_rsmeans_id("generic door") == DOOR_FALLBACK_RSMEANS_IDS["commercial glass door system"]


def test_excel_fallback_ids_are_pinned():
    assert DOOR_FALLBACK_RSMEANS_IDS["silicone adhesive smoke gasket"] == "087125105050"
    assert DOOR_FALLBACK_RSMEANS_IDS["brush weatherstrip"] == "087125103700"
    assert DOOR_FALLBACK_RSMEANS_IDS["automatic door bottom"] == "087125103650"
    assert DOOR_FALLBACK_RSMEANS_IDS["jamb weatherstrip"] == "083323104000"
    assert DOOR_FALLBACK_RSMEANS_IDS["wood door leaf"] == "081416090025"
    assert DOOR_FALLBACK_RSMEANS_IDS["garage door"] == "083613200200"
    assert DOOR_FALLBACK_RSMEANS_IDS["commercial glass door system"] == "083213100450"
    # Legacy alias retained for compatibility.
    assert DOOR_FALLBACK_RSMEANS_IDS["window door system"] == "083213100450"
    assert DOOR_FALLBACK_RSMEANS_IDS["polystyrene core steel door"] == "081313130020"


def test_search_materials_uses_fallback_id_when_no_search_match():
    fallback_id = DOOR_FALLBACK_RSMEANS_IDS["polystyrene core steel door"]
    client = FakeClient(
        search_payload={"items": []},
        fallback_payload={
            fallback_id: {
                "id": fallback_id,
                "description": "Doors and frames, fallback sample",
                "localizedCosts": {"totalOpCost": 1250.0},
            }
        },
    )

    materials = [
        {
            "name": "polystyrene core steel door",
            "quantity": 2.0,
            "unit": "ea",
            "division_code": "08",
        }
    ]

    results = search_materials_across_catalogs(
        materials=materials,
        client=client,
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 1
    assert results["materials"][0]["source"] == "rsmeans_fallback_id"
    assert results["materials"][0]["rsmeans_id"] == fallback_id
    assert results["fallback_count"] == 1
    assert len(results["warnings"]) == 1
    assert results["total_cost"] == 2500.0


def test_search_materials_prefers_direct_search_match_over_fallback():
    direct_id = "081116100020"
    client = FakeClient(
        search_payload={
            "items": [
                {
                    "id": direct_id,
                    "description": "Direct search match",
                }
            ]
        },
        fallback_payload={
            direct_id: {
                "id": direct_id,
                "description": "Direct search cost",
                "localizedCosts": {"totalOpCost": 1000.0},
            }
        },
    )

    materials = [{"name": "commercial glass door system", "quantity": 1.0, "unit": "ea", "division_code": "08"}]

    results = search_materials_across_catalogs(
        materials=materials,
        client=client,
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 1
    assert results["materials"][0]["source"] == "rsmeans_search"
    assert results["fallback_count"] == 0
    assert not results["warnings"]


def test_different_material_applications_produce_different_costs():
    class MultiMaterialFakeClient:
        def search_unit_costlines(self, **kwargs):
            term = str(kwargs.get("search_term", "")).lower()
            if "metal door" in term:
                return {"items": [{"id": "081116100020", "description": "Metal door match"}]}
            if "automatic door bottom" in term:
                return {"items": [{"id": "081313138100", "description": "Automatic bottom match"}]}
            return {"items": []}

        def get_unit_costlines(self, **kwargs):
            rsmeans_id = kwargs.get("division_code")
            items = {
                "081116100020": {
                    "id": "081116100020",
                    "description": "Doors and frames, aluminum entrance",
                    "localizedCosts": {"totalOpCost": 3245.0},
                },
                "081313138100": {
                    "id": "081313138100",
                    "description": "Doors, commercial, steel, bottom louver add",
                    "localizedCosts": {"totalOpCost": 425.0},
                },
            }
            item = items.get(rsmeans_id)
            return {"items": [item]} if item else {"items": []}

    materials = [
        {"name": "metal door", "quantity": 1.0, "unit": "ea", "division_code": "08"},
        {"name": "automatic door bottom", "quantity": 1.0, "unit": "ea", "division_code": "08"},
    ]

    results = search_materials_across_catalogs(
        materials=materials,
        client=MultiMaterialFakeClient(),
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 2
    by_name = {entry["name"]: entry for entry in results["materials"]}

    assert by_name["metal door"]["rsmeans_id"] == "081116100020"
    assert by_name["automatic door bottom"]["rsmeans_id"] == "081313138100"
    assert by_name["metal door"]["total_cost"] == 3245.0
    assert by_name["automatic door bottom"]["total_cost"] == 425.0
    assert by_name["metal door"]["total_cost"] != by_name["automatic door bottom"]["total_cost"]
    assert results["total_cost"] == 3670.0
    assert results["fallback_count"] == 0


def test_search_materials_uses_user_provided_exact_rsmeans_id_when_available():
    explicit_id = "081116100020"

    class ExplicitIdClient:
        def search_unit_costlines(self, **kwargs):
            return {"items": []}

        def get_unit_costlines(self, **kwargs):
            rsmeans_id = kwargs.get("division_code")
            if rsmeans_id == explicit_id:
                return {
                    "items": [
                        {
                            "id": explicit_id,
                            "description": "Explicit ID match",
                            "localizedCosts": {"totalOpCost": 3210.0},
                        }
                    ]
                }
            return {"items": []}

    results = search_materials_across_catalogs(
        materials=[
            {
                "name": "metal door",
                "quantity": 1.0,
                "unit": "ea",
                "division_code": "08",
                "explicit_rsmeans_id": explicit_id,
            }
        ],
        client=ExplicitIdClient(),
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 1
    assert results["materials"][0]["source"] == "rsmeans_user_id"
    assert results["materials"][0]["search_term_used"] == "user_rsmeans_id"
    assert results["materials"][0]["rsmeans_id"] == explicit_id
    assert results["materials"][0]["total_cost"] == 3210.0
    assert results["fallback_count"] == 0


def test_search_materials_falls_back_when_user_provided_id_not_found():
    explicit_id = "099999999999"
    fallback_id = DOOR_FALLBACK_RSMEANS_IDS["polystyrene core steel door"]

    class MissingExplicitIdClient:
        def search_unit_costlines(self, **kwargs):
            return {"items": []}

        def get_unit_costlines(self, **kwargs):
            rsmeans_id = kwargs.get("division_code")
            if rsmeans_id == fallback_id:
                return {
                    "items": [
                        {
                            "id": fallback_id,
                            "description": "Fallback match",
                            "localizedCosts": {"totalOpCost": 800.0},
                        }
                    ]
                }
            return {"items": []}

    results = search_materials_across_catalogs(
        materials=[
            {
                "name": "polystyrene core steel door",
                "quantity": 1.0,
                "unit": "ea",
                "division_code": "08",
                "explicit_rsmeans_id": explicit_id,
            }
        ],
        client=MissingExplicitIdClient(),
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 1
    assert results["materials"][0]["source"] == "rsmeans_fallback_id"
    assert results["materials"][0]["rsmeans_id"] == fallback_id
    assert any("User-provided RSMeans ID" in msg for msg in results["warnings"])


def test_score_out_of_bounds_triggers_fallback_id():
    fallback_id = DOOR_FALLBACK_RSMEANS_IDS["polystyrene core steel door"]

    class ScoreFallbackClient:
        def search_unit_costlines(self, **kwargs):
            # Empty description yields raw score -1.0 and triggers score-bound fallback path.
            return {"items": [{"id": "badcandidate", "description": ""}]}

        def get_unit_costlines(self, **kwargs):
            rsmeans_id = kwargs.get("division_code")
            if rsmeans_id == fallback_id:
                return {
                    "items": [
                        {
                            "id": fallback_id,
                            "description": "Fallback line",
                            "localizedCosts": {"totalOpCost": 777.0},
                        }
                    ]
                }
            return {"items": []}

    results = search_materials_across_catalogs(
        materials=[
            {
                "name": "polystyrene core steel door",
                "quantity": 1.0,
                "unit": "ea",
                "division_code": "08",
            }
        ],
        client=ScoreFallbackClient(),
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert len(results["materials"]) == 1
    assert results["materials"][0]["source"] == "rsmeans_fallback_id"
    assert results["materials"][0]["rsmeans_id"] == fallback_id
    assert results["fallback_count"] == 1
    assert any("candidate score bounds" in msg for msg in results["warnings"])


# ---------------------------------------------------------------------------
# Measure-level integration: runner warning surfacing
# ---------------------------------------------------------------------------

class FakeRunner:
    """Minimal mock of the OpenStudio runner used in measure.py."""

    def __init__(self):
        self.warnings = []
        self.infos = []

    def registerWarning(self, msg):
        self.warnings.append(msg)

    def registerInfo(self, msg):
        self.infos.append(msg)


def _apply_measure_rsmeans_surfacing(results, runner):
    """Replicate the measure.py block that surfaces fallback warnings (lines ~1140-1147)."""
    for warning_msg in results.get("warnings", []):
        runner.registerWarning(f"RSMeans fallback: {warning_msg}")
    fallback_count = int(results.get("fallback_count", 0) or 0)
    if fallback_count > 0:
        runner.registerInfo(f"RSMeans fallback matches applied: {fallback_count}")


def test_measure_registers_warning_for_fallback_source():
    """When RSMeans uses a fallback ID, runner.registerWarning must be called."""
    fallback_id = DOOR_FALLBACK_RSMEANS_IDS["polystyrene core steel door"]
    client = FakeClient(
        search_payload={"items": []},
        fallback_payload={
            fallback_id: {
                "id": fallback_id,
                "description": "Steel door fallback",
                "localizedCosts": {"totalOpCost": 1250.0},
            }
        },
    )

    results = search_materials_across_catalogs(
        materials=[{"name": "polystyrene core steel door", "quantity": 2.0, "unit": "ea", "division_code": "08"}],
        client=client,
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    runner = FakeRunner()
    _apply_measure_rsmeans_surfacing(results, runner)

    assert results["materials"][0]["source"] == "rsmeans_fallback_id"
    assert len(runner.warnings) == 1
    assert runner.warnings[0].startswith("RSMeans fallback:")
    assert runner.infos == ["RSMeans fallback matches applied: 1"]


def test_measure_no_warning_for_direct_search_match():
    """When RSMeans finds a direct search match, runner emits no fallback warning."""
    direct_id = "081116100020"
    client = FakeClient(
        search_payload={"items": [{"id": direct_id, "description": "Direct match"}]},
        fallback_payload={
            direct_id: {
                "id": direct_id,
                "description": "Direct cost item",
                "localizedCosts": {"totalOpCost": 500.0},
            }
        },
    )

    results = search_materials_across_catalogs(
        materials=[{"name": "commercial glass door system", "quantity": 1.0, "unit": "ea", "division_code": "08"}],
        client=client,
        catalogs=["bc-mf"],
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    runner = FakeRunner()
    _apply_measure_rsmeans_surfacing(results, runner)

    assert results["materials"][0]["source"] == "rsmeans_search"
    assert runner.warnings == []
    assert runner.infos == []

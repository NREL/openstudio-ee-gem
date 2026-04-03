#!/usr/bin/env python
"""Additional deterministic tests for door RSMeans helper internals."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"
if str(RESOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(RESOURCES_DIR))

from call_rsmeans_api import _extract_search_items, _filter_demo_items, _lookup_cost_item_by_rsmeans_id


class FakeClient:
    def __init__(self, cost_items=None):
        self.cost_items = cost_items or []

    def get_unit_costlines(self, **kwargs):
        return {"items": self.cost_items}


def test_extract_search_items_handles_both_response_shapes():
    direct = {"items": [{"id": "a"}]}
    nested = {"unitLines": {"items": [{"id": "b"}]}}

    assert _extract_search_items(direct) == [{"id": "a"}]
    assert _extract_search_items(nested) == [{"id": "b"}]


def test_filter_demo_items_removes_demolition_hits():
    items = [
        {"id": "1", "description": "Door demolition, remove"},
        {"id": "2", "description": "Doors and frames, aluminum"},
    ]

    filtered = _filter_demo_items(items)
    assert len(filtered) == 1
    assert filtered[0]["id"] == "2"


def test_lookup_cost_item_by_rsmeans_id_returns_exact_match():
    rsmeans_id = "081116100020"
    client = FakeClient(
        cost_items=[
            {"id": "other", "localizedCosts": {"totalOpCost": 5.0}},
            {"id": rsmeans_id, "localizedCosts": {"totalOpCost": 15.0}},
        ]
    )

    item = _lookup_cost_item_by_rsmeans_id(
        client=client,
        rsmeans_id=rsmeans_id,
        catalog="bc-mf",
        release_id="2024-an",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
    )

    assert item is not None
    assert item["id"] == rsmeans_id

"""Offline RSMeans CSV helpers shared by measure-level RSMeans adapters.

Primary CSV->localizedCosts mapping used by offline mode:
1) material -> localizedCosts.materialCost
2) labor -> localizedCosts.laborCost
3) equipment -> localizedCosts.equipmentCost
4) total_incl_op -> localizedCosts.totalOpCost
5) bare_cost_total -> localizedCosts.totalCost

Compatibility note:
- materialOpCost/laborOpCost/equipmentOpCost are mirrored from the same
    CSV component values only to support existing helper code paths.
"""

import csv
import os
from pathlib import Path
from typing import Any, Dict, Optional

_FORCE_ENV = "RSMEANS_OFFLINE_CSV_FORCE"
_PATH_ENV = "RSMEANS_OFFLINE_CSV_PATH"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def is_offline_csv_mode_enabled() -> bool:
    """Return True when RSMeans requests should be satisfied from local CSV."""
    raw = str(os.environ.get(_FORCE_ENV, "")).strip().lower()
    return raw in _TRUE_VALUES


def offline_csv_path_for_logging(default_path: Optional[str] = None) -> str:
    """Return the resolved CSV path string for logs."""
    return _resolve_csv_path(default_path)


def lookup_rsmeans_row_by_id(
    costline_id: Any,
    default_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the CSV row for query_id == costline_id, or None if not found."""
    norm_id = str(costline_id or "").strip()
    if not norm_id:
        return None

    csv_path = _resolve_csv_path(default_path)
    if not csv_path:
        return None

    index = _load_index(csv_path)
    return index.get(norm_id)


def build_rsmeans_item_from_csv_row(
    costline_id: Any,
    row: Dict[str, Any],
    description_fallback: str = "",
) -> Dict[str, Any]:
    """Build an RSMeans-like API item dict from a CSV row.

    Primary field mapping:
    - CSV material      -> localizedCosts.materialCost
    - CSV labor         -> localizedCosts.laborCost
    - CSV equipment     -> localizedCosts.equipmentCost
    - CSV total_incl_op -> localizedCosts.totalOpCost
    - CSV bare_cost_total -> localizedCosts.totalCost
    """
    material = _to_float(row.get("material"))
    labor = _to_float(row.get("labor"))
    equipment = _to_float(row.get("equipment"))
    bare_total = _to_float(row.get("bare_cost_total"))
    total_op = _to_float(row.get("total_incl_op"))

    if total_op <= 0.0:
        total_op = material + labor + equipment
    if bare_total <= 0.0:
        bare_total = material + labor + equipment

    desc = str(row.get("description") or "").strip() or description_fallback or "offline csv match"
    unit_text = str(row.get("unit") or "").strip()

    return {
        "id": str(costline_id or row.get("query_id") or "").strip(),
        "description": desc,
        "unitOfMeasure": unit_text,
        "localizedCosts": {
            # Primary offline mapping from CSV columns.
            "materialCost": material,
            "laborCost": labor,
            "equipmentCost": equipment,
            "totalCost": bare_total,
            # Compatibility mirrors for helpers that read *OpCost components.
            "materialOpCost": material,
            "laborOpCost": labor,
            "equipmentOpCost": equipment,
            "totalOpCost": total_op,
        },
    }


def _resolve_csv_path(default_path: Optional[str]) -> str:
    candidate = str(os.environ.get(_PATH_ENV, "")).strip()
    if candidate:
        return candidate

    if default_path:
        return str(default_path)

    helper_path = Path(__file__).resolve()
    repo_root = helper_path.parents[2]
    return str(repo_root / "parametric_run" / "custom_cost_datasets" / "2026_rsmeans_data.csv")


def _load_index(csv_path: str) -> Dict[str, Dict[str, Any]]:
    norm_path = str(Path(csv_path).resolve())
    if norm_path in _CACHE:
        return _CACHE[norm_path]

    index: Dict[str, Dict[str, Any]] = {}
    try:
        with open(norm_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = str(row.get("query_id") or "").strip()
                if key:
                    index[key] = row
    except Exception:
        index = {}

    _CACHE[norm_path] = index
    return index


def _to_float(raw: Any) -> float:
    try:
        text = str(raw).strip()
        if not text:
            return 0.0
        return float(text)
    except Exception:
        return 0.0

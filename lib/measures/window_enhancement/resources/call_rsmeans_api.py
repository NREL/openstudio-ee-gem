#!/usr/bin/env python
"""
RSMeans API helper for the window_enhancement measure.

This script can be used in two ways:
1. As a library imported by the measure (via measure.py)
2. As a standalone CLI tool to query RSMeans costs from saved OSM files

Search behavior summary:
1. If a specific RSMeans costline ID is provided for a material, exact ID
    lookup is attempted first.
2. Otherwise, multi-catalog closest-match search is used with scored
    candidates and a minimum accepted score threshold.
3. If the best score is below threshold, a material-specific fallback
    costline ID is used when available.

When run as a script, it discovers model paths from apply_measure.py and
searches across configured RSMeans catalogs.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import urllib3
try:
    from dotenv import load_dotenv as _dotenv_load_dotenv
except Exception:
    _dotenv_load_dotenv = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_dotenv() -> bool:
    """Load .env values if python-dotenv is present, otherwise parse .env manually."""
    if _dotenv_load_dotenv is not None:
        _dotenv_load_dotenv()
        return True

    for base in [Path.cwd(), *Path.cwd().parents]:
        env_path = base / ".env"
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
            return True
        except Exception:
            continue
    return False


DEFAULT_FEATURE_KEYS = {
    "name": "retrofit_material_name",
    "description": "retrofit_material_description",
    "quantity": "retrofit_material_quantity",
    "unit": "retrofit_material_unit",
    "division_code": "rsmeans_division_code",
    "unit_cost": "rsmeans_unit_cost",
    "total_cost": "rsmeans_total_cost",
}

# Default fallback RSMeans IDs used for low-confidence matches.
# Keep this list window-focused for the window_enhancement measure.
#
# Caulking fallbacks must be priced per L.F. of installed bead so they are
# UOM-compatible with the LF quantity submitted by measure.py (window
# perimeter where caulking is applied). The previous "bulk Gal." cost-lines
# (079213200050, 079213203200) priced sealant material only and were rejected
# by the UOM guard, producing $0 totals. The 1/4" x 1/2" bead size is the
# typical RSMeans line item used for a window-perimeter joint.
WINDOW_DEFAULT_FALLBACK_COSTLINES = {
    "silicone adhesive smoke gasket": "087125105050",
    "brush weatherstrip": "087125103700",
    "num pane 1 secondary glazing": "088155100015",
    "num pane 2": "088130100400",
    "wood operatble window": "085210700100",
    "wood operable window": "085210700100",
    "wood fixed window": "085210550100",
    # 0792 joint-sealant lines per EC3 Query Strings spreadsheet (RSMeans sheet).
    "acrylic": "079213200050",       # joint sealant, bulk acrylic latex
    "polyurethane": "079213203200",  # joint sealant, polyurethane bulk, 1 or 2 component
    "safety film": "088716100050",
    "solar control film": "088713101020",
    "anti graffiti film": "088753100020",
    "decorative film": "088726100050",
    "low e film": "088713101020",
}

# Minimum clamped candidate score [0-100] required to accept a closest match.
# Below this threshold, helper falls back to material-specific fallback IDs.
# Aligned with door_enhancement (70) after run_test_008 showed unrelated lines
# (e.g. stainless-steel glass entrance) scoring high enough at 50 to be
# accepted for distinct materials. Curated fallback IDs are reliable, so it is
# safer to fall through to them when the search match is weak.
MIN_ACCEPTABLE_MATCH_SCORE = 70.0


def _id_matches_division(item_id, division_code) -> bool:
    """Return True if ``item_id`` (RSMeans line number) starts with
    ``division_code`` prefix. Empty division means no constraint.
    Defense-in-depth so a window lookup never accepts a stray match in
    an unrelated division (e.g. window caulking matching concrete
    sealants under 0701).
    """
    if not division_code:
        return True
    if not item_id:
        return False
    return str(item_id).strip().startswith(str(division_code).strip())


# ----------------------------------------------------------------------------
# UOM compatibility guard
# ----------------------------------------------------------------------------
# RSMeans cost-lines come back with a ``unitOfMeasure`` such as "L.F.", "S.F.",
# "C.F.", "C.Y.", "Ea." with inconsistent punctuation/casing. The requested
# material ``unit`` is one of "LF", "SF", "CF", "CY", "EA". Multiplying a per-LF
# cost by a CY quantity (or vice versa) silently produces wildly wrong totals,
# so every cost-line we consume must be UOM-checked before use.
_UOM_NORMALIZE = {
    "lf": "LF", "l.f.": "LF", "linear foot": "LF", "linear feet": "LF",
    "sf": "SF", "s.f.": "SF", "square foot": "SF", "square feet": "SF",
    "cf": "CF", "c.f.": "CF", "cubic foot": "CF", "cubic feet": "CF",
    "cy": "CY", "c.y.": "CY", "cubic yard": "CY", "cubic yards": "CY",
    "ea": "EA", "ea.": "EA", "each": "EA",
    "opng": "OPNG", "opening": "OPNG",
    "lb": "LB", "lb.": "LB", "pound": "LB",
    "set": "SET",
    "job": "JOB",
}


def _normalize_uom(uom: Any) -> str:
    """Normalize an RSMeans unitOfMeasure string to a canonical token."""
    if uom is None:
        return ""
    text = str(uom).strip().lower()
    if not text:
        return ""
    return _UOM_NORMALIZE.get(text, text.upper().replace(".", "").replace(" ", ""))


def _uom_compatible(requested_unit: Any, returned_uom: Any) -> bool:
    """Return True if a cost-line priced in ``returned_uom`` can be safely
    multiplied by a quantity expressed in ``requested_unit``.

    Compatibility rules:
    - Empty / unknown returned UOM -> treated as compatible (best-effort,
      preserves existing behaviour for older API responses).
    - Empty requested unit -> treated as compatible.
    - Otherwise: tokens must match after normalization. EA and OPNG are
      treated as interchangeable.
    - SF and CF are interchangeable when costing_mode is volume_from_area
      (caller is responsible for this case via ``_compute_total_cost_for_material``).
    """
    req = _normalize_uom(requested_unit)
    ret = _normalize_uom(returned_uom)
    if not ret or not req:
        return True
    if req == ret:
        return True
    if req in {"EA", "OPNG"} and ret in {"EA", "OPNG"}:
        return True
    return False


def _get_double_pane_fallback_rsmeans_id(area_sf: float) -> str:
    """Return double-pane glass fallback ID by area bin.

    Bins:
      - < 15 SF  -> 088130100020
      - 15-30 SF -> 088130100200
      - 30-70 SF -> 088130100400
    """
    if area_sf < 15.0:
        return "088130100020"
    if area_sf < 30.0:
        return "088130100200"
    return "088130100400"


def _get_default_fallback_rsmeans_id(material_name: str, material: Optional[Dict[str, Any]] = None) -> Optional[str]:
    name_norm = _normalize_search_text(material_name)
    description_norm = _normalize_search_text((material or {}).get("description", ""))
    # Prefer explicit glazing_area_sf (preserved total area) over quantity, which may be an
    # EA count when the material was built with num_windows-based pricing.
    quantity_sf = float(
        (material or {}).get("glazing_area_sf", (material or {}).get("quantity", 0.0)) or 0.0
    )

    # Handle area-sensitive double-pane options before static lookups.
    if (
        "num pane 2" in name_norm
        or "double pane" in name_norm
        or "2 pane" in description_norm
        or "2-pane" in description_norm
        or "double" in description_norm
    ):
        return _get_double_pane_fallback_rsmeans_id(quantity_sf)

    if name_norm in WINDOW_DEFAULT_FALLBACK_COSTLINES:
        return WINDOW_DEFAULT_FALLBACK_COSTLINES[name_norm]

    # Window-measure material names are often generic; use description hints.
    if name_norm == "weatherstrip":
        if "silicone adhesive smoke gasket" in description_norm:
            return "087125105050"
        if "brush" in description_norm:
            return "087125103700"

    if name_norm == "sealant":
        # Match the LF "in place" cost-line keys in WINDOW_DEFAULT_FALLBACK_COSTLINES
        # so the UOM guard (LF requested by measure.py) doesn't reject the line.
        if "polyurethane" in description_norm:
            return "079213203500"
        if "acrylic" in description_norm:
            return "079213200065"

    if name_norm == "glazing film":
        if "safety" in description_norm:
            return "088716100050"
        if "solar control" in description_norm:
            return "088713101020"
        if "anti graffiti" in description_norm:
            return "088753100020"
        if "decorative" in description_norm:
            return "088726100050"
        if "low e" in description_norm or "low-e" in description_norm:
            return "088713101020"

    if "secondary glazing" in name_norm or "num pane 1" in name_norm:
        return "088155100015"
    if "wood" in name_norm and "operable" in name_norm and "window" in name_norm:
        return "085113204100"
    if "wood" in name_norm and "fixed" in name_norm and "window" in name_norm:
        return "085210550100"

    # Handle generic glazing names where pane-count detail is in description.
    if "glazing" in name_norm and (
        "2 pane" in description_norm
        or "2-pane" in description_norm
        or "double" in description_norm
    ):
        return _get_double_pane_fallback_rsmeans_id(quantity_sf)

    return None


def _extract_bare_components(item: Dict[str, Any]) -> Dict[str, Any]:
    """Pull material/labor/equipment unit costs (Including O&P) from a RSMeans line item.

    The RSMeans API returns both bare (no overhead/profit) and "Op" (already
    including the published O&P markups) variants of the material, labor and
    equipment components. To match the book's published "Total Incl. O&P"
    exactly, this helper extracts the ``*OpCost`` fields so the per-line sum
    equals ``totalOpCost`` (no additional markup is needed).

    Falls back to attributing the entire ``totalOpCost`` to ``material`` when
    the per-component breakdown is missing. The function name is retained for
    backward compatibility.
    """
    lc = item.get("localizedCosts", {}) or {}
    if any(k in lc for k in ("materialOpCost", "laborOpCost", "equipmentOpCost")):
        return {
            "material": float(lc.get("materialOpCost", 0.0) or 0.0),
            "labor": float(lc.get("laborOpCost", 0.0) or 0.0),
            "equipment": float(lc.get("equipmentOpCost", 0.0) or 0.0),
            "source": "op_components",
        }
    return {
        "material": float(lc.get("totalOpCost", 0.0) or 0.0),
        "labor": 0.0,
        "equipment": 0.0,
        "source": "total_op_cost_fallback",
    }


def _fetch_unit_cost_for_costline_id(
    client: "RSMeansAPIClient",
    rsmeans_id: str,
    catalogs: List[str],
    release_id: str,
    location_id: str,
    labor_type: str,
    measurement_system: str,
) -> tuple:
    """Fetch unit cost and description for a given RSMeans costline ID.

    Returns (unit_cost, description, catalog, bare_components) or
    (None, None, None, None). ``unit_cost`` is the BARE unit cost
    (material+labor+equipment, without OHP) when bare components are
    available; otherwise falls back to ``totalOpCost``.
    """
    for catalog in catalogs:
        try:
            cost_line = client.get_unit_costlines(
                release_id=release_id,
                catalog=catalog,
                location_id=location_id,
                labor_type=labor_type,
                measurement_system=measurement_system,
                division_code=rsmeans_id,
            )
            if not cost_line or "items" not in cost_line:
                continue
            for item in cost_line["items"]:
                if item.get("id") == rsmeans_id:
                    bare = _extract_bare_components(item)
                    bare_unit = bare["material"] + bare["labor"] + bare["equipment"]
                    if bare_unit > 0.0:
                        unit_cost = bare_unit
                    else:
                        unit_cost = float(item.get("localizedCosts", {}).get("totalOpCost", 0.0) or 0.0)
                    if unit_cost > 0.0:
                        return unit_cost, str(item.get("description", "")), catalog, bare
        except Exception:
            continue
    return None, None, None, None


def _derive_frame_cost_from_window_minus_glass(
    material: Dict[str, Any],
    all_materials: List[Dict[str, Any]],
    client: "RSMeansAPIClient",
    catalogs: List[str],
    release_id: str,
    location_id: str,
    labor_type: str,
    measurement_system: str,
) -> Optional[Dict[str, Any]]:
    """Derive window frame cost using: window unit cost - glass pane cost."""
    material_name_norm = _normalize_search_text(material.get("name", ""))
    if material_name_norm != "window frame":
        return None

    frame_desc_norm = _normalize_search_text(material.get("description", ""))
    # num_windows is the per-EA quantity for frame cost; quantity_sf is the glazing area used
    # for fallback ID bin selection.  Both may be carried explicitly on the material dict.
    num_windows = float(material.get("num_windows") or 0.0)
    quantity_sf = float(material.get("glazing_area_sf", material.get("quantity", 0.0)) or 0.0)
    if quantity_sf <= 0.0 and num_windows <= 0.0:
        return None
    if num_windows <= 0.0:
        num_windows = quantity_sf  # backward-compat fallback
        # osm_window_area_sf is the model window-area basis used for total frame cost.
        # parsed_window_area_sf is the per-window area used to derive the frame unit cost.
        osm_window_area_sf = float(material.get("window_area_sf") or 0.0)
        if osm_window_area_sf <= 0.0:
            osm_window_area_sf = quantity_sf
        parsed_window_area_sf = (osm_window_area_sf / num_windows) if num_windows > 0.0 else quantity_sf
        if parsed_window_area_sf <= 0.0:
            parsed_window_area_sf = quantity_sf

    # Determine pane-count from glazing material description if available.
    pane_count = None
    glazing_area_sf = quantity_sf
    for m in all_materials:
        if _normalize_search_text(m.get("name", "")) == "window glazing":
            # Prefer the preserved glazing_area_sf over the quantity field, which may now
            # hold the EA count when num_windows-based pricing is in use.
            glazing_area_sf = float(m.get("glazing_area_sf", m.get("quantity", quantity_sf)) or quantity_sf)
            glazing_desc_norm = _normalize_search_text(m.get("description", ""))
            if "1 pane" in glazing_desc_norm or "1-pane" in glazing_desc_norm or "single" in glazing_desc_norm:
                pane_count = 1
            elif "2 pane" in glazing_desc_norm or "2-pane" in glazing_desc_norm or "double" in glazing_desc_norm:
                pane_count = 2
            elif "3 pane" in glazing_desc_norm or "3-pane" in glazing_desc_norm or "triple" in glazing_desc_norm:
                pane_count = 3
            break

    # Select representative window unit ID (per EC3 Query Strings spreadsheet).
    if "wood" in frame_desc_norm and "fixed" in frame_desc_norm:
        window_unit_id = "085210550100"
    else:
        # Default to operable wood-window unit for frame-derivation baseline.
        window_unit_id = "085210700100"

    # Select glazing ID.
    if pane_count == 1:
        glazing_id = "088155100015"
    else:
        # Use double-pane area bins as requested (also used when pane count is unknown).
        glazing_id = _get_double_pane_fallback_rsmeans_id(glazing_area_sf)

    window_unit_cost, window_desc, window_catalog, window_bare = _fetch_unit_cost_for_costline_id(
        client=client,
        rsmeans_id=window_unit_id,
        catalogs=catalogs,
        release_id=release_id,
        location_id=location_id,
        labor_type=labor_type,
        measurement_system=measurement_system,
    )
    # Prefer the RSMeans window description for the per-window area used by unit-cost derivation.
    if window_desc:
        _parsed_area_per_window = _parse_window_area_sf_from_description(window_desc)
        if _parsed_area_per_window and _parsed_area_per_window > 0.0:
            parsed_window_area_sf = _parsed_area_per_window

    glazing_unit_cost, glazing_desc, glazing_catalog, glazing_bare = _fetch_unit_cost_for_costline_id(
        client=client,
        rsmeans_id=glazing_id,
        catalogs=catalogs,
        release_id=release_id,
        location_id=location_id,
        labor_type=labor_type,
        measurement_system=measurement_system,
    )

    if window_unit_cost is None or glazing_unit_cost is None:
        return None

    # glazing_unit_cost is $/SF (RSMeans flat glass is priced per S.F.).
    # Derive one-window frame $/SF from the window unit price minus one window's glazing cost.
    _frame_unit_total = max(0.0, window_unit_cost - glazing_unit_cost * parsed_window_area_sf)
    frame_unit_cost = (
        _frame_unit_total / parsed_window_area_sf if parsed_window_area_sf > 0.0 else 0.0
    )
    # Apply the derived unit cost to the model's total window-area basis.
    frame_total_cost = frame_unit_cost * osm_window_area_sf

    # Per-component bare split follows the same two-step derivation: per-window unit first,
    # then apply the derived $/SF to the model window-area basis.
    if window_bare and glazing_bare:
        _w_mat = float(window_bare.get("material", 0.0))
        _w_lab = float(window_bare.get("labor", 0.0))
        _w_eq  = float(window_bare.get("equipment", 0.0))
        _g_mat = float(glazing_bare.get("material", 0.0))
        _g_lab = float(glazing_bare.get("labor", 0.0))
        _g_eq  = float(glazing_bare.get("equipment", 0.0))
        _frame_unit_mat = (
            max(0.0, _w_mat - _g_mat * parsed_window_area_sf) / parsed_window_area_sf
            if parsed_window_area_sf > 0.0 else 0.0
        )
        _frame_unit_lab = (
            max(0.0, _w_lab - _g_lab * parsed_window_area_sf) / parsed_window_area_sf
            if parsed_window_area_sf > 0.0 else 0.0
        )
        _frame_unit_eq = (
            max(0.0, _w_eq - _g_eq * parsed_window_area_sf) / parsed_window_area_sf
            if parsed_window_area_sf > 0.0 else 0.0
        )
        _frame_bare_mat = _frame_unit_mat * osm_window_area_sf
        _frame_bare_lab = _frame_unit_lab * osm_window_area_sf
        _frame_bare_eq  = _frame_unit_eq  * osm_window_area_sf
        _frame_bare_total = _frame_bare_mat + _frame_bare_lab + _frame_bare_eq
        if _frame_bare_total > 0.0 and frame_total_cost > 0.0:
            _scale = frame_total_cost / _frame_bare_total
            _frame_total_mat = _frame_bare_mat * _scale
            _frame_total_lab = _frame_bare_lab * _scale
            _frame_total_eq  = _frame_bare_eq  * _scale
        else:
            _frame_total_mat, _frame_total_lab, _frame_total_eq = frame_total_cost, 0.0, 0.0
        _comp_source = window_bare.get("source", "bare_components")
    else:
        _frame_total_mat, _frame_total_lab, _frame_total_eq = frame_total_cost, 0.0, 0.0
        _comp_source = "total_op_cost_fallback"

    return {
        "unit_cost": frame_unit_cost,
        "total_cost": frame_total_cost,
        "total_material_cost": _frame_total_mat,
        "total_labor_cost": _frame_total_lab,
        "total_equipment_cost": _frame_total_eq,
        "cost_component_source": _comp_source,
        "window_unit_id": window_unit_id,
        "window_unit_desc": window_desc or "",
        "window_unit_catalog": window_catalog,
        "glazing_id": glazing_id,
        "glazing_desc": glazing_desc or "",
        "glazing_catalog": glazing_catalog,
        "window_area_sf": osm_window_area_sf,
        "unit_cost_basis": material.get("unit", "SF"),
        "costing_mode": "derived_window_minus_glass",
    }


def _get_feature_as_string(props, feature_name: str) -> Optional[str]:
    if not props.hasFeature(feature_name):
        return None
    value_str = props.getFeatureAsString(feature_name)
    if value_str.is_initialized():
        return value_str.get()
    value_double = props.getFeatureAsDouble(feature_name)
    if value_double.is_initialized():
        return str(value_double.get())
    value_int = props.getFeatureAsInteger(feature_name)
    if value_int.is_initialized():
        return str(value_int.get())
    return None


def _get_feature_as_float(props, feature_name: str) -> Optional[float]:
    if not props.hasFeature(feature_name):
        return None
    value_double = props.getFeatureAsDouble(feature_name)
    if value_double.is_initialized():
        return float(value_double.get())
    value_int = props.getFeatureAsInteger(feature_name)
    if value_int.is_initialized():
        return float(value_int.get())
    value_str = props.getFeatureAsString(feature_name)
    if value_str.is_initialized():
        try:
            return float(value_str.get())
        except ValueError:
            return None
    return None


def _extract_search_items(search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not search_results:
        return []
    items = search_results.get("items")
    if isinstance(items, list):
        return items
    return search_results.get("unitLines", {}).get("items", [])


def _filter_demo_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reject demolition / removal cost-lines.

    Excludes any item that:
    - has an ``id`` starting with ``0805`` (MasterFormat Demolition for
      Openings — relevant when this helper is loaded in place of the door
      helper due to Python module-name caching across measures), or
    - whose description mentions demolition / demo / remove (without an
      "and replace" qualifier).

    Important: returns an empty list if everything was filtered out, so the
    caller can fall through to other catalogs / fallback IDs instead of
    silently accepting a demolition match.
    """
    filtered = []
    for item in items:
        item_id = str(item.get("id", "")).strip()
        if item_id.startswith("0805"):
            continue
        description = str(item.get("description", "")).lower()
        if "demolition" in description:
            continue
        if re.search(r"\bremove\b", description) and "replace" not in description:
            continue
        if re.search(r"\bdemo\b", description):
            continue
        filtered.append(item)
    return filtered


def _normalize_search_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokenize_search_text(text: str) -> set:
    tokens = _normalize_search_text(text).split()
    return {tok for tok in tokens if len(tok) > 2}


def _score_rsmeans_candidate(material_name: str, item: Dict[str, Any]) -> float:
    """Score an RSMeans candidate against a material name.

    Score components:
    - +60 if normalized material name appears in description
    - +12 per overlapping token between material and description
    - +10 if both contain the token "window"
    - -20 if description looks like non-installation accessory line
    - +0..1 for description length bonus

    Returns a raw score; caller clamps it to [0, 100].
    """
    description = str(item.get("description", ""))
    if not description:
        return -1.0

    material_norm = _normalize_search_text(material_name)
    description_norm = _normalize_search_text(description)
    material_tokens = _tokenize_search_text(material_name)
    description_tokens = _tokenize_search_text(description)

    score = 0.0
    if material_norm and material_norm in description_norm:
        score += 60.0

    token_overlap = material_tokens.intersection(description_tokens)
    score += 12.0 * len(token_overlap)

    # Prefer window entries for window materials.
    if "window" in material_norm and "window" in description_norm:
        score += 10.0

    # Penalize likely non-installation accessory lines.
    if any(tok in description_norm for tok in ["fastener", "clip", "anchor", "hanger"]):
        score -= 20.0

    # Heavily penalize cost-lines that explicitly exclude glazing when the
    # material we are searching for IS the glazing (e.g. RSMeans line
    # "Windows ... projected window, excl. glazing and trim" must not match
    # a "window glazing" search — that line prices a frame only).
    if "glaz" in material_norm and any(
        phrase in description_norm
        for phrase in (
            "excl glazing",
            "excluding glazing",
            "less glazing",
            "no glazing",
            "without glazing",
        )
    ):
        score -= 200.0

    score += min(len(description_norm), 120) / 120.0
    return score


def _is_disallowed_candidate(item: Dict[str, Any]) -> bool:
    """Return True if candidate line should be excluded from ranking.

    Excludes fasteners/hangers/anchors and board-foot line items that are
    usually not direct retrofit scope lines for this measure.
    """
    desc = _normalize_search_text(item.get("description", ""))
    if not desc:
        return False

    disallowed_tokens = (
        "fastener",
        "fasteners",
        "wire fastener",
        "spring type wire",
        "clip",
        "clips",
        "hanger",
        "hangers",
        "anchor",
        "anchors",
        "board foot",
        "board feet",
        "bf",
    )
    if any(token in desc for token in disallowed_tokens):
        return True

    unit_tokens = [
        _normalize_search_text(item.get("uom", "")),
        _normalize_search_text(item.get("unit", "")),
        _normalize_search_text(item.get("unitOfMeasure", "")),
    ]
    if any(token in {"bf", "board foot", "board feet"} for token in unit_tokens if token):
        return True

    return False


def _select_best_rsmeans_candidate(
    material_name: str,
    items: List[Dict[str, Any]],
    material: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Return best candidate and ranked score list for diagnostics.

    Behavior:
    - Filters disallowed candidates where possible.
    - Scores candidates and clamps to [0, 100].
    - If best clamped score is below MIN_ACCEPTABLE_MATCH_SCORE, returns a
      fallback pseudo-candidate when fallback mapping exists.
    """
    if not items:
        return None, []

    eligible_items = [item for item in items if not _is_disallowed_candidate(item)]
    if not eligible_items:
        eligible_items = items

    # When the material we're costing is the glazing itself, drop any cost-line
    # whose description explicitly excludes glazing (those lines price a window
    # frame/sash unit "excl. glazing and trim" — they are NOT glazing material).
    material_norm_for_filter = _normalize_search_text(material_name)
    if "glaz" in material_norm_for_filter:
        glazing_exclusion_phrases = (
            "excl glazing",
            "excluding glazing",
            "less glazing",
            "no glazing",
            "without glazing",
        )
        non_excl = [
            item
            for item in eligible_items
            if not any(
                phrase in _normalize_search_text(item.get("description", ""))
                for phrase in glazing_exclusion_phrases
            )
        ]
        if non_excl:
            eligible_items = non_excl

    scored = []
    for idx, item in enumerate(eligible_items):
        raw_score = _score_rsmeans_candidate(material_name, item)
        bounded_score = max(0.0, min(100.0, raw_score))
        scored.append(
            {
                "index": idx,
                "rsmeans_id": item.get("id", "unknown"),
                "description": str(item.get("description", ""))[:100],
                "score": round(bounded_score, 2),
                "raw_score": round(raw_score, 2),
            }
        )

    scored.sort(key=lambda x: -x["score"])
    top_score = scored[0].get("score", 0.0)
    if top_score < MIN_ACCEPTABLE_MATCH_SCORE:
        fallback_id = _get_default_fallback_rsmeans_id(material_name, material)
        if fallback_id:
            return {
                "id": fallback_id,
                "description": f"[fallback costline] {material_name}",
                "is_fallback": True,
                "fallback_reason": (
                    f"poor_match_score_fallback:{top_score:.1f}<"
                    f"{MIN_ACCEPTABLE_MATCH_SCORE}"
                ),
            }, scored

    best_idx = scored[0]["index"]
    best_candidate = eligible_items[best_idx]
    return best_candidate, scored


def _parse_inches_token(token: str) -> Optional[float]:
    token = str(token).strip()
    if not token:
        return None
    if "-" in token:
        whole, frac = token.split("-", 1)
        try:
            whole_val = float(whole)
        except ValueError:
            return None
        if "/" in frac:
            num, den = frac.split("/", 1)
            try:
                return whole_val + (float(num) / float(den))
            except (ValueError, ZeroDivisionError):
                return None
        return None
    if "/" in token:
        num, den = token.split("/", 1)
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(token)
    except ValueError:
        return None


def _extract_thickness_ft_from_description(description: str) -> Optional[float]:
    desc = str(description or "")
    if not desc:
        return None

    patterns = [
        r"(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*\"",
        r"(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*(?:in|inch|inches)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, desc, flags=re.IGNORECASE)
        if match:
            inches = _parse_inches_token(match.group(1))
            if inches and inches > 0:
                return inches / 12.0
    return None


def _parse_window_area_sf_from_description(description: str) -> Optional[float]:
    """Parse window WxH dimensions from RSMeans description and return area in SF.

    Handles formats:
    - "3'-0\" x 4'-0\""  (feet-inches, e.g. RSMeans standard)
    - "3' x 4'"          (feet only)
    - "3 x 4"            (plain numbers assumed to be feet, sanity-checked)
    """
    desc = str(description or "")
    if not desc:
        return None

    # Pattern 1: N'-M" x N'-M" (feet with inch component, e.g. "3'-0\" x 4'-6\"")
    m = re.search(
        r"(\d+)'-(\d+(?:[/]\d+)?)\"\s*[xX\u00d7]\s*(\d+)'-(\d+(?:[/]\d+)?)\""
        , desc)
    if m:
        w_ft = float(m.group(1)) + (_parse_inches_token(m.group(2)) or 0.0) / 12.0
        h_ft = float(m.group(3)) + (_parse_inches_token(m.group(4)) or 0.0) / 12.0
        if w_ft > 0.0 and h_ft > 0.0:
            return w_ft * h_ft

    # Pattern 2: N' x N' (feet only, e.g. "3' x 4'")
    m = re.search(r"(\d+(?:\.\d+)?)'[ ]*[xX\u00d7][ ]*(\d+(?:\.\d+)?)'", desc)
    if m:
        try:
            w, h = float(m.group(1)), float(m.group(2))
            if w > 0.0 and h > 0.0:
                return w * h
        except ValueError:
            pass

    # Pattern 3: plain "N x N" (assumed feet; sanity-bounded to 0.5–50 ft)
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*[xX\u00d7]\s*(\d+(?:\.\d+)?)\b", desc)
    if m:
        try:
            w, h = float(m.group(1)), float(m.group(2))
            if 0.5 < w < 50.0 and 0.5 < h < 50.0:
                return w * h
        except ValueError:
            pass

    return None


def _compute_total_cost_for_material(material: Dict[str, Any], unit_cost: float, matched_description: str) -> Dict[str, Any]:
    quantity = float(material.get("quantity", 1.0) or 1.0)
    default = {
        "unit_cost": float(unit_cost),
        "total_cost": float(unit_cost) * quantity,
        "costing_mode": "area",
        "effective_unit": material.get("unit", ""),
    }

    if str(material.get("costing_mode", "")).lower() != "volume_from_area":
        return default

    quantity_volume = material.get("quantity_volume")
    if quantity_volume is None:
        return default

    line_thickness_ft_raw = _extract_thickness_ft_from_description(matched_description)
    if line_thickness_ft_raw is None:
        line_thickness_ft_raw = material.get("rsmeans_thickness_ft")
    try:
        line_thickness_ft = float(line_thickness_ft_raw)
    except (TypeError, ValueError):
        return default

    if line_thickness_ft <= 0.0:
        return default

    unit_cost_per_cf = float(unit_cost) / line_thickness_ft
    total_cost = unit_cost_per_cf * float(quantity_volume)
    return {
        "unit_cost": unit_cost_per_cf,
        "total_cost": total_cost,
        "costing_mode": "volume_from_area",
        "effective_unit": material.get("unit_volume", "CF"),
        "source_unit_cost_per_sf": float(unit_cost),
        "source_line_thickness_ft": line_thickness_ft,
    }


def generate_search_term_alternatives(material_name: str) -> List[tuple]:
    """Generate ordered (search_term, division_code) alternatives.

    Uses material-specific heuristics and progressive simplification so
    searches can recover when the exact source term is absent in RSMeans.
    """
    alternatives = []
    name_lower = material_name.lower().strip()
    # Remove size tokens like "5 ft 3 in x 7 ft 7 in" to improve match rate
    cleaned_name = re.sub(r"\b\d+(?:\.\d+)?\b", "", name_lower)
    cleaned_name = cleaned_name.replace("ft", " ").replace("in", " ").replace("x", " ")
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
    
    # Strategy 1: Original name with detected division
    original_division = get_division_from_material_type(material_name)
    alternatives.append((material_name, original_division))
    if cleaned_name and cleaned_name != name_lower:
        alternatives.append((cleaned_name, get_division_from_material_type(cleaned_name)))
    
    # Strategy 2: Window-specific alternatives
    if "window" in name_lower:
        if "glaz" in name_lower:
            # Window glazing alternatives
            alternatives.extend([
                ("insulated glass unit", "08"),
                ("double glazed window", "08"),
                ("glass window", "08"),
                ("window glass", "08"),
                ("glazing", "08"),
                ("IGU", "08"),
            ])
        elif "frame" in name_lower:
            # Window frame alternatives based on common materials
            alternatives.extend([
                ("window replacement", "08"),
                ("window unit", "08"),
                ("wood window frame", "08"),
                ("vinyl window frame", "08"),
                ("aluminum window frame", "08"),
                ("window sash", "08"),
                ("window", "08"),
            ])
        else:
            # Generic window alternatives
            alternatives.extend([
                ("window replacement", "08"),
                ("window unit", "08"),
                ("window assembly", "08"),
                ("window", "08"),
            ])
    
    # Strategy 3: Door-specific alternatives
    elif "door" in name_lower:
        if "metal" in name_lower or "steel" in name_lower:
            alternatives.append(("metal door", "08"))
        alternatives.extend([
            ("door replacement", "08"),
            ("door unit", "08"),
            ("door assembly", "08"),
            ("door", "08"),
        ])
    
    # Strategy 4: Insulation alternatives
    elif "insulation" in name_lower or "insul" in name_lower:
        alternatives.extend([
            ("wall insulation", "07"),
            ("roof insulation", "07"),
            ("batt insulation", "07"),
            ("rigid insulation", "07"),
            ("insulation", "07"),
        ])
    
    # Strategy 5: HVAC alternatives
    elif any(term in name_lower for term in ["hvac", "heat pump", "furnace", "boiler", "chiller"]):
        alternatives.extend([
            (material_name.replace("system", "unit"), "23"),
            (material_name.replace("equipment", "unit"), "23"),
            ("HVAC equipment", "23"),
        ])
    
    # Strategy 6: Try simplifying compound terms (remove adjectives/modifiers)
    words = cleaned_name.split() if cleaned_name else name_lower.split()
    if len(words) > 1:
        # Try just the last word (often the noun)
        last_word = words[-1]
        last_div = get_division_from_material_type(last_word)
        if (last_word, last_div) not in alternatives:
            alternatives.append((last_word, last_div))
        
        # Try first + last word
        if len(words) > 2:
            simplified = f"{words[0]} {words[-1]}"
            simp_div = get_division_from_material_type(simplified)
            if (simplified, simp_div) not in alternatives:
                alternatives.append((simplified, simp_div))
    
    # Strategy 7: Try without division constraint (let RSMeans search all divisions)
    if (material_name, None) not in alternatives:
        alternatives.append((material_name, None))
    
    return alternatives


def get_division_from_material_type(material_type: str) -> Optional[str]:
    mapping = {
        "concrete": "03",
        "footing": "03",
        "slab": "03",
        "brick": "04",
        "masonry": "04",
        "block": "04",
        "steel": "05",
        "metal": "05",
        "wood": "06",
        "lumber": "06",
        "insulation": "07",
        "roofing": "07",
        "waterproofing": "07",
        "sealant": "07",
        "door": "08",
        "window": "08",
        "glazing": "08",
        "glass": "08",
        "frame": "08",
        "sash": "08",
        "drywall": "09",
        "gypsum": "09",
        "paint": "09",
        "flooring": "09",
        "ceiling": "09",
        "tile": "09",
        "plumbing": "22",
        "pipe": "22",
        "hvac": "23",
        "duct": "23",
        "boiler": "23",
        "chiller": "23",
        "furnace": "23",
        "electrical": "26",
        "lighting": "26",
        "wiring": "26",
    }

    material_lower = material_type.lower().strip()
    if material_lower in mapping:
        return mapping[material_lower]

    for key, division in mapping.items():
        if key in material_lower or material_lower in key:
            return division
    return None


class RSMeansAPIClient:
    def __init__(self, client_id, client_secret, use_sandbox: bool = False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://login.gordian.com/connect/token"
        self.base_url = "https://dataapi-sb.gordian.com" if use_sandbox else "https://dataapi.gordian.com"
        self.access_token = None
        self.token_type = None

    def authenticate(self) -> bool:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "rsm_api:costdata",
        }
        try:
            response = requests.post(self.token_url, data=data, verify=False)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            self.token_type = token_data.get("token_type", "Bearer")
            print("Authentication successful!")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return {
            "Authorization": f"{self.token_type} {self.access_token}",
            "Content-Type": "application/json",
        }

    def search_unit_costlines(
        self,
        release_id: str,
        measurement_system: str,
        search_term: str,
        catalog: Optional[str] = "bc-mf",
        location_id: Optional[str] = "us-us-national",
        labor_type: Optional[str] = "std",
        division_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        catalog_id = f"{catalog}-{measurement_system}-{labor_type}-{release_id}-{location_id}"
        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines/_search"
        params = {"searchTerm": search_term} if search_term else {}
        if division_code:
            params["divisionCode"] = division_code
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print("    Search:")
            print(f"      Catalog : {catalog_id}")
            print(f"      Division: {division_code or 'any'}")
            print(f"      Term    : {search_term or ''}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost line: {e}")
            return None

    def get_unit_costlines(
        self,
        release_id: str,
        measurement_system: str,
        division_code: str,
        catalog: str = "bc-mf",
        location_id: str = "us-us-national",
        labor_type: str = "std",
    ) -> Optional[Dict[str, Any]]:
        catalog_id = f"{catalog}-{measurement_system}-{labor_type}-{release_id}-{location_id}"
        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines"
        params = {"divisionCode": division_code} if division_code else {}
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print(f"Cost lines: catalog={catalog_id}, division={division_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost line: {e}")
            return None

    def search_materials_batch(
        self,
        materials: List[Dict[str, Any]],
        release_id: str = "2019-an",
        catalog: str = "bc-mf",
        location_id: str = "us-us-national",
        labor_type: str = "std",
        measurement_system: str = "imp",
        save_search_results_path: Optional[str] = None,
        skip_if_cost_present: bool = True,
    ) -> Dict[str, Any]:
        results = {
            "total_cost": 0.0,
            "materials": [],
            "errors": [],
            "search_log": [],
        }

        for material in materials:
            material_name = material.get("name", "")
            quantity = material.get("quantity", 1.0)
            division_hint = material.get("division_code")
            existing_unit_cost = material.get("unit_cost")
            existing_total_cost = material.get("total_cost")

            if not material_name:
                results["errors"].append("Material name is required")
                continue

            if skip_if_cost_present and existing_total_cost is not None:
                results["materials"].append({
                    **material,
                    "unit_cost": existing_unit_cost,
                    "total_cost": existing_total_cost,
                    "source": "additional_properties",
                })
                results["total_cost"] += float(existing_total_cost)
                continue

            # Generate alternative search terms
            search_alternatives = generate_search_term_alternatives(material_name)
            
            # If we have a division hint from material properties, prioritize it
            if division_hint:
                # Insert original name with provided division at the front
                search_alternatives.insert(0, (material_name, division_hint))
            
            search_results = None
            tried_terms = []
            
            # Try each alternative search term until we find a match
            for alt_term, alt_division in search_alternatives:
                tried_terms.append(f"{alt_term} (div:{alt_division or 'any'})")
                
                try:
                    search_results = self.search_unit_costlines(
                        release_id=release_id,
                        measurement_system=measurement_system,
                        search_term=alt_term,
                        catalog=catalog,
                        location_id=location_id,
                        labor_type=labor_type,
                        division_code=alt_division,
                    )
                    
                    items = _filter_demo_items(_extract_search_items(search_results))
                    if items:
                        if alt_term != material_name:
                            print(f"  -> Found match using alternative term: '{alt_term}'")
                        break
                except Exception as e:
                    continue
            
            items = _filter_demo_items(_extract_search_items(search_results))
            if not items:
                error_msg = f"No RSMeans match found for: {material_name}"
                if len(tried_terms) > 1:
                    error_msg += f" (tried {len(tried_terms)} alternatives)"
                results["errors"].append(error_msg)
                results["search_log"].append({
                    "material": material_name,
                    "tried_terms": tried_terms,
                    "result": "no_match"
                })
                continue
            
            try:

                first_item = items[0]
                division_code = first_item.get("id")
                item_description = first_item.get("description", material_name)

                if not division_code:
                    results["errors"].append(f"No division code found for: {material_name}")
                    continue

                cost_line = self.get_unit_costlines(
                    release_id=release_id,
                    catalog=catalog,
                    location_id=location_id,
                    labor_type=labor_type,
                    measurement_system=measurement_system,
                    division_code=division_code,
                )

                results["search_log"].append({
                    "material_name": material_name,
                    "division_hint": division_hint,
                    "search_results_count": len(items),
                    "division_code": division_code,
                    "first_match": first_item.get("description", ""),
                    "has_cost_data": cost_line is not None and "items" in cost_line,
                })

                if cost_line and "items" in cost_line:
                    for item in cost_line["items"]:
                        if item.get("id") == division_code:
                            unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                            total_material_cost = unit_cost * quantity

                            results["materials"].append({
                                **material,
                                "description": item_description,
                                "division_code": division_code,
                                "unit_cost": unit_cost,
                                "total_cost": total_material_cost,
                                "source": "rsmeans_api",
                            })

                            results["total_cost"] += total_material_cost
                            break
                    else:
                        results["errors"].append(f"Division code not found in response: {division_code}")
                else:
                    results["errors"].append(f"No cost data returned for: {material_name}")

            except Exception as e:
                results["errors"].append(f"Error processing material '{material_name}': {str(e)}")

        if save_search_results_path:
            try:
                output_path = Path(save_search_results_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)
            except Exception as e:
                results["errors"].append(f"Could not save search results to JSON: {str(e)}")

        return results


def load_openstudio_model(model_path: Path):
    try:
        import openstudio  # pylint: disable=import-error
    except Exception as exc:
        raise RuntimeError("openstudio python bindings are required to read a model") from exc

    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(openstudio.toPath(str(model_path)))
    if not model_opt.is_initialized():
        raise RuntimeError(f"Failed to load model: {model_path}")
    return model_opt.get()


def _format_feet_inches(value_m: float) -> str:
    inches_total = value_m * 39.37007874
    feet = int(inches_total // 12)
    inches = int(round(inches_total - feet * 12))
    if inches == 12:
        feet += 1
        inches = 0
    return f"{feet} ft {inches} in"


def _estimate_door_dimensions_m(subsurface) -> Optional[Dict[str, float]]:
    try:
        vertices = subsurface.vertices()
    except Exception:
        return None
    if not vertices or len(vertices) < 3:
        return None

    xs = [v.x() for v in vertices]
    ys = [v.y() for v in vertices]
    zs = [v.z() for v in vertices]

    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)

    width_m = max(dx, dy)
    height_m = dz if dz > 0 else min(dx, dy)
    if width_m <= 0 or height_m <= 0:
        return None
    return {"width_m": width_m, "height_m": height_m}


def _get_default_exterior_door_construction(model):
    try:
        building = model.getBuilding()
        dcs_opt = building.defaultConstructionSet()
        if not dcs_opt.is_initialized():
            return None
        dcs = dcs_opt.get()
        ext_subs_opt = dcs.defaultExteriorSubSurfaceConstructions()
        if not ext_subs_opt.is_initialized():
            return None
        ext_subs = ext_subs_opt.get()
        door_opt = ext_subs.doorConstruction()
        if door_opt.is_initialized():
            return door_opt.get()
    except Exception:
        return None
    return None


def _collect_material_keywords_from_construction(construction) -> List[str]:
    keywords = set()
    try:
        if construction.to_LayeredConstruction().is_initialized():
            lc = construction.to_LayeredConstruction().get()
            layers = lc.layers()
        else:
            layers = []
    except Exception:
        layers = []

    for layer in layers:
        try:
            name = layer.nameString().lower()
        except Exception:
            name = ""
        if "metal" in name or "steel" in name:
            keywords.add("metal")
        if "aluminum" in name or "aluminium" in name:
            keywords.add("aluminum")
        if "insulation" in name or "insul" in name:
            keywords.add("insulated")
        if "wood" in name:
            keywords.add("wood")
        if "glass" in name or "glaz" in name:
            keywords.add("glass")
    return sorted(keywords)


def _material_phrase_from_keywords(keywords: List[str]) -> str:
    kws = set(keywords)
    if "glass" in kws and "metal" in kws:
        return "metal framed glass"
    if "glass" in kws:
        return "glass"
    if "metal" in kws and "insulated" in kws:
        return "insulated metal"
    if "metal" in kws:
        return "metal"
    if "wood" in kws:
        return "wood"
    if "insulated" in kws:
        return "insulated"
    return ""


def build_door_search_material_from_model(model) -> Optional[Dict[str, Any]]:
    doors = [ss for ss in model.getSubSurfaces()
             if ss.subSurfaceType() in ("Door", "GlassDoor", "OverheadDoor")]
    if not doors:
        return None

    default_door_construction = _get_default_exterior_door_construction(model)
    all_keywords = set()

    for door in doors:
        construction = None
        if door.construction().is_initialized():
            construction = door.construction().get()
        elif default_door_construction is not None:
            construction = default_door_construction

        if construction is not None:
            for kw in _collect_material_keywords_from_construction(construction):
                all_keywords.add(kw)

    dims = _estimate_door_dimensions_m(doors[0])
    if dims:
        width_ft_in = _format_feet_inches(dims["width_m"])
        height_ft_in = _format_feet_inches(dims["height_m"])
        size_str = f"{width_ft_in} x {height_ft_in}"
    else:
        size_str = "approx size unknown"

    material_phrase = _material_phrase_from_keywords(sorted(all_keywords))
    if material_phrase:
        search_term = f"{material_phrase} door {size_str}"
    else:
        search_term = f"door {size_str}"

    description = f"{len(doors)} door(s); materials: {', '.join(sorted(all_keywords)) or 'unspecified'}; size: {size_str}"

    return {
        "name": search_term.strip(),
        "description": description,
        "quantity": float(len(doors)),
        "unit": "ea",
        "division_code": "08",
    }


def extract_materials_from_model(model, feature_keys: Dict[str, str]) -> List[Dict[str, Any]]:
    materials: List[Dict[str, Any]] = []

    for obj in model.objects():
        if not hasattr(obj, "additionalProperties"):
            continue
        try:
            props = obj.additionalProperties()
        except Exception:
            continue

        if not props.featureNames() or not props.hasFeature(feature_keys["name"]):
            continue

        name = _get_feature_as_string(props, feature_keys["name"])
        if not name:
            continue

        quantity = _get_feature_as_float(props, feature_keys["quantity"]) or 1.0
        unit = _get_feature_as_string(props, feature_keys["unit"]) or ""
        description = _get_feature_as_string(props, feature_keys["description"]) or ""
        division_code = _get_feature_as_string(props, feature_keys["division_code"])
        unit_cost = _get_feature_as_float(props, feature_keys["unit_cost"])
        total_cost = _get_feature_as_float(props, feature_keys["total_cost"])

        material = {
            "name": name,
            "description": description,
            "quantity": quantity,
            "unit": unit,
            "division_code": division_code,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
        }

        try:
            material["object_handle"] = obj.handle().__str__()
        except Exception:
            material["object_handle"] = None

        try:
            material["object_name"] = obj.nameString()
        except Exception:
            material["object_name"] = None

        materials.append(material)

    return materials


def extract_paths_from_apply_measure(script_dir: Path) -> tuple:
    """
    Parse apply_measure.py to find input and output model paths.
    
    Args:
        script_dir: Directory containing apply_measure.py (parent of resources/)
    
    Returns:
        tuple: (input_model_path, output_model_path)
    """
    apply_measure_path = script_dir / "apply_measure.py"
    
    if not apply_measure_path.exists():
        raise FileNotFoundError(f"apply_measure.py not found at {apply_measure_path}")
    
    with open(apply_measure_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Look for: model_path = SCRIPT_DIR / "tests" / "DOE_small_office.osm"
    input_match = re.search(r'model_path\s*=\s*SCRIPT_DIR\s*/\s*"tests"\s*/\s*"([^"]+)"', content)
    if not input_match:
        raise ValueError("Could not find model_path in apply_measure.py")
    
    input_filename = input_match.group(1)
    input_path = script_dir / "tests" / input_filename
    
    # Look for: output_dir = SCRIPT_DIR / "tests" / "output"
    output_dir_match = re.search(r'output_dir\s*=\s*SCRIPT_DIR\s*/\s*"tests"\s*/\s*"([^"]+)"', content)
    if output_dir_match:
        output_subdir = output_dir_match.group(1)
        output_dir = script_dir / "tests" / output_subdir
    else:
        output_dir = script_dir / "tests" / "output"  # fallback
    
    # Look for: output_model_path = output_dir / "DOE_small_office_window_enhanced.osm"
    output_match = re.search(r'output_model_path\s*=\s*output_dir\s*/\s*"([^"]+)"', content)
    if not output_match:
        raise ValueError("Could not find output_model_path in apply_measure.py")
    
    output_filename = output_match.group(1)
    output_path = output_dir / output_filename
    
    return (input_path, output_path)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for standalone usage."""
    
    # Determine script directory (parent of resources/ if running from resources/)
    script_file = Path(__file__).resolve()
    if script_file.parent.name == "resources":
        measure_dir = script_file.parent.parent
    else:
        measure_dir = script_file.parent
    
    # Try to extract default paths from apply_measure.py
    try:
        default_input, default_output_model = extract_paths_from_apply_measure(measure_dir)
        default_output_json = default_output_model.parent / "rsmeans_search_results.json"
        auto_detected = True
    except Exception:
        # Fallback to reasonable defaults
        default_output_model = measure_dir / "tests" / "output" / "model_enhanced.osm"
        default_output_json = measure_dir / "tests" / "output" / "rsmeans_search_results.json"
        auto_detected = False
    
    parser = argparse.ArgumentParser(
        description="RSMeans API lookup for materials stored in OpenStudio OSM files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect paths from apply_measure.py and search multiple catalogs
  python resources/call_rsmeans_api.py
  
  # Search specific catalogs with 25%% overhead
  python resources/call_rsmeans_api.py --catalogs bc-mf,gb-mf,sq-mf --overhead-profit-percent 25
  
  # Use custom model path
  python resources/call_rsmeans_api.py --model path/to/model.osm
        """
    )
    
    help_text = "Path to OSM file"
    if auto_detected:
        help_text += " (default: auto-detected from apply_measure.py)"
    
    parser.add_argument("--model", default=str(default_output_model), help=help_text)
    parser.add_argument("--output", default=str(default_output_json), help="Path to save JSON results")
    parser.add_argument("--release", default="2024-an", help="RSMeans release ID (e.g., 2024-an)")
    parser.add_argument(
        "--catalogs",
        default="bc-mf,gb-mf,rp-mf",
        help="Comma-separated catalog codes (bc-mf, gb-mf, rp-mf, sq-mf, hc-mf, si-mf)"
    )
    parser.add_argument("--location", default="us-us-national", help="Location ID")
    parser.add_argument("--labor-type", default="std", help="Labor type (std, opn, fmr, fed, he)")
    parser.add_argument("--measurement-system", default="imp", help="Measurement system (imp, met)")
    parser.add_argument("--use-sandbox", action="store_true", help="Use RSMeans sandbox API")
    parser.add_argument(
        "--overhead-profit-percent",
        type=float,
        default=0.0,
        help="Percent applied to material cost for overhead+profit",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point when run as a standalone script."""
    args = parse_args()
    load_dotenv()

    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")

    if not client_id or not client_secret:
        print("ERROR: RSMeans API credentials not found.")
        print("Set environment variables: client_id, client_secret")
        print("Or create a .env file with these values.")
        return 1

    model_path = Path(args.model).resolve()
    if not model_path.exists():
        print(f"ERROR: Model file not found: {model_path}")
        return 1

    # Try multiple methods to extract materials
    materials = None
    model_dir = model_path.parent
    
    # Method 1: Pre-saved JSON file
    materials_file = model_dir / "window_enhancement_retrofit_materials.json"
    if materials_file.exists():
        try:
            with open(materials_file, "r", encoding="utf-8") as f:
                materials = json.load(f)
            print(f"Extracted {len(materials)} materials from {materials_file.name}")
        except Exception as e:
            print(f"Warning: Could not load materials file: {e}")
    
    # Method 2: Extract from model's Facility AdditionalProperties
    if not materials:
        print(f"Loading model from {model_path.name}...")
        model = load_openstudio_model(model_path)
        
        if model.facility().is_initialized():
            facility = model.facility().get()
            props = facility.additionalProperties()
            
            # Try window_enhancement specific property first
            if props.hasFeature("window_enhancement_retrofit_materials_json"):
                try:
                    opt_str = props.getFeatureAsString("window_enhancement_retrofit_materials_json")
                    if opt_str.is_initialized():
                        json_str = opt_str.get()
                        materials = json.loads(json_str)
                        print(f"Extracted {len(materials)} materials from Facility.window_enhancement_retrofit_materials_json")
                except Exception as e:
                    print(f"Warning: Could not parse retrofit_materials_json: {e}")
        
        # Method 3: Fall back to individual property extraction
        if not materials:
            materials = extract_materials_from_model(model, DEFAULT_FEATURE_KEYS)
            if materials:
                print(f"Extracted {len(materials)} materials using standard property keys")

        # Method 4: Derive a door-based search term from the model
        if not materials:
            derived = build_door_search_material_from_model(model)
            if derived:
                materials = [derived]
                print("Derived door-based RSMeans search term from model:")
                print(f"  Search term: {derived['name']}")
                print(f"  Details: {derived['description']}")

    if not materials:
        print("ERROR: No retrofit materials found in model.")
        print("The model must have materials stored in AdditionalProperties.")
        return 1

    # Parse catalog list
    catalogs = [c.strip() for c in args.catalogs.split(",")]
    print(f"\nSearching RSMeans catalogs: {', '.join(catalogs)}")
    
    # Authenticate
    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=args.use_sandbox)
    if not client.authenticate():
        print("ERROR: Authentication failed.")
        return 1

    # Search across all catalogs
    print(f"Searching for {len(materials)} materials...")
    results = search_materials_across_catalogs(
        materials=materials,
        client=client,
        catalogs=catalogs,
        release_id=args.release,
        location_id=args.location,
        labor_type=args.labor_type,
        measurement_system=args.measurement_system,
    )

    # Calculate costs
    total_material_cost = float(results.get("total_cost", 0.0))
    # Per-line unit costs already include RSMeans O&P (``totalOpCost``); no
    # additional markup is layered here.
    overhead_profit_cost = 0.0
    total_cost = total_material_cost

    # Prepare summary
    summary = {
        "total_material_cost": total_material_cost,
        "overhead_profit_percent": args.overhead_profit_percent,
        "total_overhead_profit_cost": overhead_profit_cost,
        "total_cost_with_overhead_profit": total_cost,
        "materials_count": len(results.get("materials", [])),
        "materials_searched": len(materials),
        "catalogs_searched": catalogs,
    }

    # Save results
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("COST SUMMARY")
    print("=" * 70)
    print(f"Materials searched:  {len(materials)}")
    print(f"Materials matched:   {len(results.get('materials', []))}")
    print(f"Material cost:       ${total_material_cost:,.2f}")
    print(f"Overhead+profit:     ${overhead_profit_cost:,.2f} ({args.overhead_profit_percent}%)")
    print(f"TOTAL COST:          ${total_cost:,.2f}")
    print("=" * 70)
    
    if results.get("errors"):
        print(f"\nWarnings ({len(results['errors'])} items):")
        for error in results["errors"][:5]:
            print(f"  - {error}")
        if len(results["errors"]) > 5:
            print(f"  ... and {len(results['errors']) - 5} more")
    
    print(f"\nResults saved to: {output_path}")
    return 0


def search_materials_across_catalogs(
    materials: List[Dict[str, Any]],
    client: "RSMeansAPIClient",
    catalogs: Optional[List[str]] = None,
    release_id: str = "2024-an",
    location_id: str = "us-us-national",
    labor_type: str = "std",
    measurement_system: str = "imp",
) -> Dict[str, Any]:
    """
    Search for materials across multiple RSMeans catalogs and return best matches.
    
    Args:
        materials: List of material dicts with 'name', 'quantity', 'unit', etc.
        client: Authenticated RSMeansAPIClient instance
        catalogs: List of catalog codes to search (default: all common catalogs)
        release_id: RSMeans release ID (e.g., "2024-an")
        location_id: Location for pricing
        labor_type: Labor type code
        measurement_system: "imp" or "met"
    
    Returns:
        Dict with 'total_cost', 'materials' (with catalog info), 'errors', 'search_log'
    """
    if catalogs is None:
        # Default to common building-related catalogs
        catalogs = ["bc-mf", "gb-mf", "rp-mf"]  # Building Construction, Green Building, Repair & Remodeling
    
    all_results = []
    search_log = []
    errors = []
    total_cost = 0.0
    total_material_cost_bare = 0.0
    total_labor_cost_bare = 0.0
    total_equipment_cost_bare = 0.0
    
    for material in materials:
        material_name = material.get("name", "unknown")
        quantity = material.get("quantity", 1.0)
        unit = material.get("unit", "")
        division_code = material.get("division_code")
        specified_id = material.get("rsmeans_id")

        print("\n" + "-" * 70)
        print(f"RSMeans lookup for material: {material_name}")
        print(f"  Quantity : {quantity} {unit}")
        print(f"  Division : {division_code or 'auto'}")
        
        best_match = None
        best_cost = None
        best_catalog = None
        matched_term = None
        best_unit_cost = None
        best_unit_basis = unit
        best_costing_mode = "area"
        best_total_material_cost = 0.0
        best_total_labor_cost = 0.0
        best_total_equipment_cost = 0.0
        best_component_source = None
        _derived_window_area_sf = 0.0

        # For window frame, derive cost when direct frame RSMeans lines are not available:
        # frame_cost = window_unit_cost - glazing_cost.
        if not specified_id and _normalize_search_text(material_name) == "window frame":
            derived = _derive_frame_cost_from_window_minus_glass(
                material=material,
                all_materials=materials,
                client=client,
                catalogs=catalogs,
                release_id=release_id,
                location_id=location_id,
                labor_type=labor_type,
                measurement_system=measurement_system,
            )
            if derived:
                best_match = {
                    "id": "derived_window_frame",
                    "description": "window frame (derived from window unit - glazing)",
                }
                best_cost = derived["total_cost"]
                best_catalog = derived.get("window_unit_catalog")
                matched_term = "derived:window_unit_minus_glazing"
                best_unit_cost = derived["unit_cost"]
                best_unit_basis = derived.get("unit_cost_basis", unit)
                best_costing_mode = derived.get("costing_mode", "derived_window_minus_glass")
                best_total_material_cost = float(derived.get("total_material_cost", 0.0))
                best_total_labor_cost = float(derived.get("total_labor_cost", 0.0))
                best_total_equipment_cost = float(derived.get("total_equipment_cost", 0.0))
                best_component_source = derived.get("cost_component_source")
                _derived_window_area_sf = float(derived.get("window_area_sf", 0.0) or 0.0)
                search_log.append({
                    "material": material_name,
                    "status": "derived_frame_cost",
                    "search_term": matched_term,
                    "catalog": best_catalog,
                    "quantity": quantity,
                    "unit_cost": best_unit_cost,
                    "total_cost": best_cost,
                    "unit_cost_basis": best_unit_basis,
                    "costing_mode": best_costing_mode,
                    "window_unit_id": derived.get("window_unit_id"),
                    "window_unit_desc": derived.get("window_unit_desc"),
                    "glazing_id": derived.get("glazing_id"),
                    "glazing_desc": derived.get("glazing_desc"),
                })
        
        # If a specific RSMeans line item ID is provided, attempt exact match first
        if specified_id and division_code and not _id_matches_division(specified_id, division_code):
            search_log.append({
                "material": material_name,
                "search_term": specified_id,
                "status": "explicit_id_division_mismatch_rejected",
                "requested_division": division_code,
            })
            specified_id = None

        if specified_id:
            for catalog in catalogs:
                try:
                    print(f"  Exact ID : {specified_id}")
                    print(f"  Catalog  : {catalog}")
                    cost_line = client.get_unit_costlines(
                        release_id=release_id,
                        catalog=catalog,
                        location_id=location_id,
                        labor_type=labor_type,
                        measurement_system=measurement_system,
                        division_code=specified_id,
                    )
                    if cost_line and "items" in cost_line:
                        for item in cost_line["items"]:
                            if item.get("id") == specified_id:
                                unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                line_uom = item.get("unitOfMeasure", "")
                                # Reject if the cost-line UOM is incompatible with the requested
                                # material unit. ``volume_from_area`` materials legitimately
                                # consume SF-priced lines for CF quantities, so skip the guard
                                # in that mode (``_compute_total_cost_for_material`` performs
                                # the SF->CF conversion using parsed line thickness).
                                if (
                                    unit_cost > 0
                                    and str(material.get("costing_mode", "")).lower() != "volume_from_area"
                                    and not _uom_compatible(unit, line_uom)
                                ):
                                    search_log.append({
                                        "material": material_name,
                                        "search_term": specified_id,
                                        "catalog": catalog,
                                        "division": division_code,
                                        "status": "explicit_id_uom_mismatch_rejected",
                                        "requested_unit": unit,
                                        "line_uom": line_uom,
                                        "rsmeans_id": specified_id,
                                        "rsmeans_description": item.get("description", ""),
                                    })
                                    break
                                if unit_cost > 0:
                                    _bare = _extract_bare_components(item)
                                    _bare_unit = _bare["material"] + _bare["labor"] + _bare["equipment"]
                                    if _bare_unit > 0:
                                        unit_cost = _bare_unit
                                    computed = _compute_total_cost_for_material(
                                        material,
                                        unit_cost,
                                        str(item.get("description", "")),
                                    )
                                    _total_bare = float(computed["total_cost"])
                                    _mat_frac = (_bare["material"] / _bare_unit) if _bare_unit > 0 else 1.0
                                    _lab_frac = (_bare["labor"] / _bare_unit) if _bare_unit > 0 else 0.0
                                    _eq_frac = (_bare["equipment"] / _bare_unit) if _bare_unit > 0 else 0.0
                                    best_total_material_cost = _total_bare * _mat_frac
                                    best_total_labor_cost = _total_bare * _lab_frac
                                    best_total_equipment_cost = _total_bare * _eq_frac
                                    best_component_source = _bare["source"]
                                    best_match = item
                                    best_cost = computed["total_cost"]
                                    best_catalog = catalog
                                    matched_term = f"rsmeans_id:{specified_id}"
                                    best_unit_cost = computed["unit_cost"]
                                    best_unit_basis = computed.get("effective_unit", unit)
                                    best_costing_mode = computed.get("costing_mode", "area")
                                    search_log.append({
                                        "material": material_name,
                                        "search_term": specified_id,
                                        "catalog": catalog,
                                        "division": division_code,
                                        "status": "exact_id_match",
                                        "unit_cost": computed["unit_cost"],
                                        "quantity": quantity,
                                        "total_cost": best_cost,
                                        "costing_mode": best_costing_mode,
                                        "unit_cost_basis": best_unit_basis,
                                        "source_unit_cost_per_sf": computed.get("source_unit_cost_per_sf"),
                                        "source_line_thickness_ft": computed.get("source_line_thickness_ft"),
                                    })
                                    break
                        if best_match:
                            break
                except Exception as e:
                    search_log.append({
                        "material": material_name,
                        "search_term": specified_id,
                        "catalog": catalog,
                        "status": "error",
                        "error": str(e)
                    })

        # Generate alternative search terms
        search_alternatives = generate_search_term_alternatives(material_name)
        
        # If we have a division code from material properties, prioritize it
        if division_code:
            search_alternatives.insert(0, (material_name, division_code))
        
        # Try each catalog with intelligent search term alternatives
        for catalog in catalogs:
            if best_match:
                break  # Already found a match in a previous catalog
            
            # Try alternative search terms within this catalog
            for alt_term, alt_division in search_alternatives:
                try:
                    print("  Search:")
                    print(f"    Term    : {alt_term}")
                    print(f"    Division: {alt_division or 'any'}")
                    print(f"    Catalog : {catalog}")
                    results = client.search_unit_costlines(
                        search_term=alt_term,
                        division_code=alt_division,
                        catalog=catalog,
                        release_id=release_id,
                        location_id=location_id,
                        labor_type=labor_type,
                        measurement_system=measurement_system,
                    )

                    if not results:
                        continue
                    
                    items = _filter_demo_items(_extract_search_items(results))
                    if items:
                        match, ranked_candidates = _select_best_rsmeans_candidate(material_name, items, material)
                        if not match:
                            continue
                        division_id = match.get("id", "")
                        if match.get("is_fallback"):
                            print("  Fallback:")
                            print(f"    Reason      : {match.get('fallback_reason', 'out_of_bounds')}")
                            print(f"    Costline ID : {division_id}")
                        print("  Match:")
                        print(f"    ID          : {division_id}")
                        print(f"    Description : {match.get('description', '')}")
                        
                        # Get detailed cost data
                        cost_line = client.get_unit_costlines(
                            release_id=release_id,
                            catalog=catalog,
                            location_id=location_id,
                            labor_type=labor_type,
                            measurement_system=measurement_system,
                            division_code=division_id,
                        )
                        
                        if cost_line and "items" in cost_line:
                            for item in cost_line["items"]:
                                if item.get("id") == division_id:
                                    if division_code and not _id_matches_division(division_id, division_code):
                                        search_log.append({
                                            "material": material_name,
                                            "search_term": alt_term,
                                            "catalog": catalog,
                                            "division": alt_division,
                                            "status": "division_mismatch_rejected",
                                            "requested_division": division_code,
                                            "rsmeans_id": division_id,
                                            "rsmeans_description": item.get("description", ""),
                                        })
                                        break
                                    unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                    line_uom = item.get("unitOfMeasure", "")
                                    # Reject if cost-line UOM is incompatible with requested
                                    # material unit (e.g. CY-requested caulking matched to an
                                    # LF-priced sealant line). ``volume_from_area`` materials
                                    # legitimately consume SF-priced lines for CF quantities.
                                    if (
                                        unit_cost > 0
                                        and str(material.get("costing_mode", "")).lower() != "volume_from_area"
                                        and not _uom_compatible(unit, line_uom)
                                    ):
                                        search_log.append({
                                            "material": material_name,
                                            "search_term": alt_term,
                                            "catalog": catalog,
                                            "division": alt_division,
                                            "status": "uom_mismatch_rejected",
                                            "requested_unit": unit,
                                            "line_uom": line_uom,
                                            "rsmeans_id": division_id,
                                            "rsmeans_description": match.get("description", ""),
                                        })
                                        break

                                    if unit_cost > 0:
                                        _bare = _extract_bare_components(item)
                                        _bare_unit = _bare["material"] + _bare["labor"] + _bare["equipment"]
                                        if _bare_unit > 0:
                                            unit_cost = _bare_unit
                                        computed = _compute_total_cost_for_material(
                                            material,
                                            unit_cost,
                                            str(match.get("description", "")),
                                        )
                                        _total_bare = float(computed["total_cost"])
                                        _mat_frac = (_bare["material"] / _bare_unit) if _bare_unit > 0 else 1.0
                                        _lab_frac = (_bare["labor"] / _bare_unit) if _bare_unit > 0 else 0.0
                                        _eq_frac = (_bare["equipment"] / _bare_unit) if _bare_unit > 0 else 0.0
                                        best_total_material_cost = _total_bare * _mat_frac
                                        best_total_labor_cost = _total_bare * _lab_frac
                                        best_total_equipment_cost = _total_bare * _eq_frac
                                        best_component_source = _bare["source"]
                                        best_match = item
                                        best_cost = computed["total_cost"]
                                        best_catalog = catalog
                                        matched_term = alt_term
                                        best_unit_cost = computed["unit_cost"]
                                        best_unit_basis = computed.get("effective_unit", unit)
                                        best_costing_mode = computed.get("costing_mode", "area")
                                        
                                        status_msg = f"match_found"
                                        if alt_term != material_name:
                                            status_msg += f" (using '{alt_term}')"
                                            print(f"  Note: matched on alternative term '{alt_term}' in {catalog}")
                                        
                                        search_log.append({
                                            "material": material_name,
                                            "search_term": alt_term,
                                            "catalog": catalog,
                                            "division": alt_division,
                                            "status": status_msg,
                                            "unit_cost": computed["unit_cost"],
                                            "quantity": quantity,
                                            "total_cost": best_cost,
                                            "candidate_scores": ranked_candidates[:5],
                                            "rsmeans_id": division_id,
                                            "rsmeans_description": match.get("description", ""),
                                            "costing_mode": computed.get("costing_mode", "area"),
                                            "unit_cost_basis": computed.get("effective_unit", unit),
                                            "source_unit_cost_per_sf": computed.get("source_unit_cost_per_sf"),
                                            "source_line_thickness_ft": computed.get("source_line_thickness_ft"),
                                        })
                                        break
                            
                            if best_match:
                                break  # Exit alternative terms loop
                    
                except Exception as e:
                    search_log.append({
                        "material": material_name,
                        "search_term": alt_term,
                        "catalog": catalog,
                        "status": "error",
                        "error": str(e)
                    })
        
        if best_match:
            match_type = "closest_match"
            if matched_term and str(matched_term).startswith("rsmeans_id:"):
                match_type = "exact_id_match"
            material_result = {
                **material,
                "catalog": best_catalog,
                "search_term_used": matched_term,
                "unit_cost": best_unit_cost if best_unit_cost is not None else best_match.get("localizedCosts", {}).get("totalOpCost", 0.0),
                "total_cost": best_cost,
                "total_material_cost": best_total_material_cost,
                "total_labor_cost": best_total_labor_cost,
                "total_equipment_cost": best_total_equipment_cost,
                "cost_component_source": best_component_source,
                "rsmeans_id": best_match.get("id", ""),
                "rsmeans_description": best_match.get("description", ""),
                "match_type": match_type,
                "unit_cost_basis": best_unit_basis,
                "costing_mode": best_costing_mode,
            }
            if _derived_window_area_sf > 0.0:
                material_result["window_area_sf"] = _derived_window_area_sf
            all_results.append(material_result)
            total_cost += float(best_cost or 0.0)
            total_material_cost_bare += float(best_total_material_cost or 0.0)
            total_labor_cost_bare += float(best_total_labor_cost or 0.0)
            total_equipment_cost_bare += float(best_total_equipment_cost or 0.0)
        else:
            errors.append(f"No RSMeans match found in any catalog for: {material_name}")
            search_log.append({
                "material": material_name,
                "status": "no_match",
                "catalogs_searched": catalogs,
                "alternatives_tried": len(search_alternatives)
            })
    
    return {
        "total_cost": total_cost,
        "total_material_cost": total_material_cost_bare,
        "total_labor_cost": total_labor_cost_bare,
        "total_equipment_cost": total_equipment_cost_bare,
        "materials": all_results,
        "errors": errors,
        "search_log": search_log,
        "catalogs_searched": catalogs
    }


def run_rsmeans_cost_lookup(
    materials: List[Dict[str, Any]],
    release_id: str = "2024-an",
    catalogs: Optional[List[str]] = None,
    location_id: str = "us-us-national",
    labor_type: str = "std",
    measurement_system: str = "imp",
    use_sandbox: bool = False,
    overhead_profit_percent: float = 0.0,
) -> Dict[str, Any]:
    """Run RSMeans lookup for provided materials and return summary/results."""
    load_dotenv()
    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")

    if not client_id or not client_secret:
        return {
            "status": "auth_error",
            "message": "RSMeans API credentials not found in environment",
        }

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=use_sandbox)
    if not client.authenticate():
        return {
            "status": "auth_error",
            "message": "RSMeans authentication failed",
        }

    results = search_materials_across_catalogs(
        materials=materials,
        client=client,
        catalogs=catalogs,
        release_id=release_id,
        location_id=location_id,
        labor_type=labor_type,
        measurement_system=measurement_system,
    )

    total_material_cost = float(results.get("total_material_cost", 0.0))
    total_labor_cost = float(results.get("total_labor_cost", 0.0))
    total_equipment_cost = float(results.get("total_equipment_cost", 0.0))
    total_bare_cost = total_material_cost + total_labor_cost + total_equipment_cost
    if total_bare_cost <= 0.0:
        total_bare_cost = float(results.get("total_cost", 0.0))
        total_material_cost = total_bare_cost
    # Per-line unit costs already include RSMeans O&P (``totalOpCost``); no
    # additional markup is layered here. ``overhead_profit_percent`` is
    # retained in the summary for traceability but does not alter the total.
    overhead_profit_cost = 0.0
    total_cost = total_bare_cost

    summary = {
        "total_material_cost": total_material_cost,
        "total_labor_cost": total_labor_cost,
        "total_equipment_cost": total_equipment_cost,
        "total_bare_cost": total_bare_cost,
        "overhead_profit_percent": overhead_profit_percent,
        "total_overhead_profit_cost": overhead_profit_cost,
        "total_cost_with_overhead_profit": total_cost,
        "materials_count": len(results.get("materials", [])),
        "materials_searched": len(materials),
        "catalogs_searched": results.get("catalogs_searched", catalogs or []),
        "release_id": release_id,
        "location_id": location_id,
        "labor_type": labor_type,
        "measurement_system": measurement_system,
        "use_sandbox": use_sandbox,
    }

    return {
        "status": "ok",
        "summary": summary,
        "results": results,
    }


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
RSMeans API helper for the IncreaseInsulationRValueForExteriorWalls measure.

Two usage modes
---------------
1. Library (imported by measure.py via importlib):
             results = run_rsmeans_cost_lookup(materials, ...)
     Returns a dict with "status", "summary", and "results" keys.

2. Standalone CLI (python call_rsmeans_api.py --model path/to/model.osm):
     Reads retrofit material data from the OSM file's AdditionalProperties,
     searches RSMeans, and writes a JSON cost report.

API call sequence (per material)
---------------------------------
Step 1 — search_unit_costlines():  POST /_search?searchTerm=...
                 Returns candidate line items: id, description, uom/unit/unitOfMeasure
                 The best candidate is selected by _select_best_rsmeans_candidate().

Step 2 — get_unit_costlines():  GET /costlines?divisionCode=<id>
                 Returns the full cost record.  The only cost field extracted is:
                         localizedCosts.totalOpCost  →  Total Incl. O&P  ($/unit)

Costing modes
-------------
"area"            : total_cost = unit_cost × area_SF
"volume_from_area": unit_cost/SF is divided by the RSMeans line-item thickness (ft)
                                        to derive a $/CF rate, then multiplied by the added volume.
                                        Used for wall insulation where thickness varies per project.

Credentials
-----------
Set environment variables client_id and client_secret, or place them in a .env
file next to this script.  Authentication uses the Gordian OAuth2 client_credentials flow.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


_AUXILIARY_UTILS_DIR = Path(__file__).resolve().parents[3] / "parametric_run" / "auxiliary"
if str(_AUXILIARY_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(_AUXILIARY_UTILS_DIR))

from rsmeans_logging import append_measure_raw_record, append_measure_summary_record


# Keys used when extracting material data from an OSM model's AdditionalProperties
# in CLI mode.  measure.py bypasses these and passes materials directly as dicts.
DEFAULT_FEATURE_KEYS = {
    "name": "retrofit_material_name",
    "description": "retrofit_material_description",
    "quantity": "retrofit_material_quantity",
    "unit": "retrofit_material_unit",
    "division_code": "rsmeans_division_code",
    "unit_cost": "rsmeans_unit_cost",
    "total_cost": "rsmeans_total_cost",
}

# Score threshold below which the scoring system is considered to have failed and
# a hardcoded fallback ID is used instead (see INSULATION_FALLBACK_IDS below).
# Aligned with door_enhancement / window_enhancement (70) after run_test_008
# showed unrelated lines scoring high enough at 50 to be accepted for distinct
# materials. Curated fallback IDs are reliable, so it is safer to fall through
# to them when the search match is weak.
MIN_ACCEPTABLE_MATCH_SCORE = 70.0

RSMEANS_RAW_LOG_ENV = "RSMEANS_SCENARIO_RAW_LOG_PATH"
MEASURE_LOG_SLUG = "wall_insulation"
_WRITE_API_LOGS = True


def _append_rsmeans_summary_log(payload: Dict[str, Any]) -> None:
    if not _WRITE_API_LOGS:
        return
    append_measure_summary_record(MEASURE_LOG_SLUG, payload)


def _append_rsmeans_raw_log(material, matched_item, catalog, match_type, search_term):
    """Append raw RSMeans unit-cost fields for the matched line item."""
    if not _WRITE_API_LOGS:
        return
    if not isinstance(matched_item, dict):
        return
    append_measure_raw_record(MEASURE_LOG_SLUG, material, matched_item, catalog, match_type, search_term)


def _id_matches_division(item_id, division_code) -> bool:
    """Return True if ``item_id`` (RSMeans line number) starts with
    ``division_code`` prefix. Empty division means no constraint.
    Defense-in-depth so a wall-insulation lookup never accepts a match
    from an unrelated MasterFormat division.
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
#
# For insulation the request is typically "SF" (area) and the costing_mode is
# "volume_from_area" — meaning the SF-priced line is internally converted to
# $/CF using the parsed line thickness via _compute_total_cost_for_material.
# That conversion is intentional; the UOM guard is therefore relaxed when
# costing_mode == "volume_from_area" so SF-priced lines are still acceptable.
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


def _uom_check_ok_for_material(material: Dict[str, Any], unit: Any, line_uom: Any) -> bool:
    """Helper that combines _uom_compatible with the volume_from_area exemption.

    Insulation materials use costing_mode='volume_from_area' to convert an
    SF-priced line into a $/CF rate via the parsed line thickness.  In that
    mode a CF-requested quantity legitimately consumes an SF-priced line, so
    the UOM check is bypassed.  All other materials require UOM compatibility.
    """
    if str(material.get("costing_mode", "")).lower() == "volume_from_area":
        return True
    return _uom_compatible(unit, line_uom)

# Hardcoded RSMeans costline IDs used when the text-matching score falls below
# MIN_ACCEPTABLE_MATCH_SCORE.  These are verified 2024-an catalog IDs.
INSULATION_FALLBACK_IDS = {
    "Blown Cellulose": "072126100020",
    "Blown Fiberglass": "072126101000",
    "Blown Mineral Wool": "072123100100",
    "Polyiso Insulation Foam Board": "072216101700",
    "polyiso foam board": "072216101700",
    # Per EC3 Query Strings spreadsheet (RSMeans sheet): GPS maps to
    # 072113130600 (expanded polystyrene 1" R4 line); RSMeans 2024-an has no
    # dedicated graphite-PS costline.
    "Graphite Polystyrene (GPS) Foam Board": "072113130600",
    "Expanded Polystyrene (EPS) Foam Board": "072113130600",
    "Extruded Polystyrene (XPS) Foam Board": "072216101910",

    "Mineral Wool Heavy Density Blanket": "072116201320",
    "Mineral Wool Light Density Blanket": "072116201320",
    "Fiberglass Batts": "072116200620",
}


def _resolve_insulation_fallback_costline_id(material_name: str) -> Optional[str]:
    exact = INSULATION_FALLBACK_IDS.get(material_name)
    if exact:
        return exact

    material_norm = _normalize_search_text(material_name)
    for key, fallback_id in INSULATION_FALLBACK_IDS.items():
        if _normalize_search_text(key) == material_norm:
            return fallback_id
    for key, fallback_id in INSULATION_FALLBACK_IDS.items():
        key_norm = _normalize_search_text(key)
        if key_norm and key_norm in material_norm:
            return fallback_id
    return None


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
    # RSMeans returns items under "items" (search endpoint) or "unitLines.items"
    # (cost-line endpoint).  This normalises both shapes into a flat list.
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


# _normalize_search_text / _tokenize_search_text: pre-process strings before
# comparing them so punctuation, casing, and extra whitespace don't affect scores.
def _normalize_search_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokenize_search_text(text: str) -> set:
    tokens = _normalize_search_text(text).split()
    return {tok for tok in tokens if len(tok) > 2}


def _score_rsmeans_candidate(material_name: str, item: Dict[str, Any]) -> float:
    """
    Score a single RSMeans search result against the target material name (0–100).

    Scoring rules (higher = better match):
    +100  exact full-string match
    + 60  material name is a substring of description
    + 15  per overlapping token
    - 20  description contains "insulation" but shares fewer than 2 tokens (too generic)
    - 10  expected context word (roof/wall) missing from description
    - 25  roof material matched a wall description (cross-type penalty)
    +30–40 polyiso/polyisocyanurate exact keyword bonus
    """
    description = str(item.get("description", ""))
    if not description:
        return -1.0

    material_norm = _normalize_search_text(material_name)
    description_norm = _normalize_search_text(description)
    material_tokens = _tokenize_search_text(material_name)
    description_tokens = _tokenize_search_text(description)
    overlap = material_tokens.intersection(description_tokens)

    score = 0.0
    if material_norm == description_norm:
        score += 100.0
    elif material_norm and material_norm in description_norm:
        score += 60.0

    for token in material_tokens:
        if token in description_tokens:
            score += 15.0

    if "insulation" in description_norm and len(overlap) < 2:
        score -= 20.0
    if "roof" in material_norm and "roof" not in description_norm:
        score -= 10.0
    if "wall" in material_norm and "wall" not in description_norm:
        score -= 10.0

    if "roof" in material_norm and "wall" in description_norm and "roof" not in description_norm:
        score -= 25.0

    if "polyiso" in material_norm or "polyisocyanurate" in material_norm:
        if "polyisocyanurate" in description_norm:
            score += 40.0
        elif "polyiso" in description_norm:
            score += 30.0
        else:
            score -= 30.0

    score += min(len(description_norm), 120) / 120.0
    # Clamp score to 0-100 range
    return max(0.0, min(100.0, score))


def _is_disallowed_candidate(item: Dict[str, Any]) -> bool:
    """
    Return True for line items that are accessories or non-material entries that
    would produce misleading $/SF costs (fasteners, hangers, board-foot priced items).
    """
    desc = _normalize_search_text(item.get("description", ""))
    if not desc:
        return False

    if "tapered for drainage" in desc or ("tapered" in desc and "drainage" in desc):
        return True

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


def _select_best_rsmeans_candidate(material_name: str, items: List[Dict[str, Any]]) -> tuple:
    """
    Select the best RSMeans line item from a list of candidates.

    Returns (best_item_dict, scored_list).  Two-tier selection:
    1. Score all non-disallowed candidates; pick the highest scorer.
    2. If the best score < MIN_ACCEPTABLE_MATCH_SCORE and a hardcoded fallback ID
       exists for this material, return a synthetic item with that ID instead.
    """
    if not items:
        return None, []

    eligible_items = [item for item in items if not _is_disallowed_candidate(item)]
    if not eligible_items:
        eligible_items = items

    scored = []
    for idx, item in enumerate(eligible_items):
        score = _score_rsmeans_candidate(material_name, item)
        desc = item.get("description", "")
        desc = desc[:80] if desc else ""
        scored.append({
            "index": idx,
            "rsmeans_id": item.get("costlineID", "unknown"),
            "description": desc,
            "score": round(score, 2),
        })

    scored.sort(key=lambda x: -x["score"])
    
    # If best score is below threshold (poor match), use fallback ID if available
    best_score = scored[0]["score"] if scored else -1.0
    if best_score < MIN_ACCEPTABLE_MATCH_SCORE and material_name in INSULATION_FALLBACK_IDS:
        fallback_id = INSULATION_FALLBACK_IDS[material_name]
        # Create a synthetic candidate with fallback ID and score indicator
        return {
            "costlineID": fallback_id,
            "description": f"[Fallback ID: {fallback_id}]",
            "is_fallback": True,
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


def _extract_bare_components(item: Dict[str, Any]) -> Dict[str, Any]:
    """Pull material/labor/equipment unit costs from a RSMeans line item.

    The Gordian/RSMeans cost API returns both bare (no overhead/profit) and
    "Op" (already including the published O&P markups) variants of the
    material, labor and equipment components:

      - ``materialCost`` / ``materialOpCost``
      - ``laborCost``    / ``laborOpCost``
      - ``equipmentCost``/ ``equipmentOpCost``
      - ``totalCost``    / ``totalOpCost``

    Returned ``material``/``labor``/``equipment`` keys hold the Op-marked-up
    values so the per-line sum equals ``totalOpCost`` (matches the book's
    "Total Incl. O&P" figure). The additional ``bare_*`` keys hold the
    no-O&P values so callers can persist them separately. The function name
    is retained for backward compatibility.
    """
    lc = item.get("localizedCosts", {}) or {}
    bare_material = float(lc.get("materialCost", 0.0) or 0.0)
    bare_labor = float(lc.get("laborCost", 0.0) or 0.0)
    bare_equipment = float(lc.get("equipmentCost", 0.0) or 0.0)
    bare_total = float(lc.get("totalCost", 0.0) or 0.0)
    if any(k in lc for k in ("materialOpCost", "laborOpCost", "equipmentOpCost")):
        return {
            "material": float(lc.get("materialOpCost", 0.0) or 0.0),
            "labor": float(lc.get("laborOpCost", 0.0) or 0.0),
            "equipment": float(lc.get("equipmentOpCost", 0.0) or 0.0),
            "bare_material": bare_material,
            "bare_labor": bare_labor,
            "bare_equipment": bare_equipment,
            "bare_total": bare_total,
            "source": "op_components",
        }
    return {
        "material": float(lc.get("totalOpCost", 0.0) or 0.0),
        "labor": 0.0,
        "equipment": 0.0,
        "bare_material": bare_material,
        "bare_labor": bare_labor,
        "bare_equipment": bare_equipment,
        "bare_total": bare_total,
        "source": "total_op_cost_fallback",
    }


def _compute_total_cost_for_material(
    material: Dict[str, Any],
    unit_cost: float,
    matched_description: str,
    line_uom: Any = None,
) -> Dict[str, Any]:
    """
    Translate a raw RSMeans unit cost into a project total.

    Standard mode ("area"):
        total = unit_cost × area_SF  (unit_cost already in $/SF)

    Volume mode ("volume_from_area"):
        - If the matched RSMeans line is already priced per volume (CF/CY),
          the unit cost is in $/CF (or $/CY); we use it directly against the
          actual added volume — NO thickness conversion is performed. CY lines
          are scaled by 1/27 to put the unit cost in $/CF.
        - Otherwise (line is per SF), RSMeans prices insulation per SF at a
          specific thickness listed in the description (e.g., "3-1/2 inch").
          We extract that thickness, convert the $/SF to $/CF, then multiply
          by the actual added volume (CF). If the description has no
          parseable thickness, raises ValueError instead of falling back to
          a project-supplied thickness — the caller must reject this line.
    """
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

    # If RSMeans already prices the line per volume, skip the thickness
    # division entirely — using unit_cost directly is both simpler and
    # correct. This avoids spurious $/CF values derived from the project's
    # added thickness (a non-property of the RSMeans line).
    line_uom_norm = _normalize_uom(line_uom) if line_uom is not None else ""
    if line_uom_norm in ("CF", "CY"):
        unit_cost_per_cf = float(unit_cost) / 27.0 if line_uom_norm == "CY" else float(unit_cost)
        total_cost = unit_cost_per_cf * float(quantity_volume)
        return {
            "unit_cost": unit_cost_per_cf,
            "total_cost": total_cost,
            "costing_mode": "volume_direct",
            "effective_unit": material.get("unit_volume", "CF"),
            "line_uom": line_uom_norm,
        }

    line_thickness_ft_raw = _extract_thickness_ft_from_description(matched_description)
    if line_thickness_ft_raw is None:
        raise ValueError(
            "RSMeans line description has no parseable thickness; cannot compute "
            f"volume-based cost for material {material.get('name', '?')!r}. "
            f"Description: {matched_description!r}"
        )
    try:
        line_thickness_ft = float(line_thickness_ft_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"RSMeans line thickness is not numeric ({line_thickness_ft_raw!r}); "
            f"cannot compute volume-based cost. Description: {matched_description!r}"
        ) from exc

    if line_thickness_ft <= 0.0:
        raise ValueError(
            f"RSMeans line thickness is non-positive ({line_thickness_ft} ft); "
            f"cannot compute volume-based cost. Description: {matched_description!r}"
        )

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
    """
    Generate alternative search terms and divisions for a material.
    Returns list of (search_term, division_code) tuples in priority order.
    
    Args:
        material_name: Original material name (e.g., "window glazing")
    
    Returns:
        List of (search_term, division_code) tuples to try in order
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
        insulation_alts = []
        if "polyiso" in name_lower or "polyisocyanurate" in name_lower:
            insulation_alts.extend([
                ("polyisocyanurate board insulation", "07"),
                ("polyiso rigid insulation", "07"),
                ("polyisocyanurate insulation", "07"),
            ])
        if "wool" in name_lower:
            insulation_alts.extend([
                ("mineral wool batt insulation", "07"),
                ("wool batt insulation", "07"),
            ])
        if "cellulose" in name_lower:
            insulation_alts.append(("cellulose insulation", "07"))

        insulation_alts.extend([
            ("wall insulation", "07"),
            ("roof insulation", "07"),
            ("batt insulation", "07"),
            ("rigid insulation", "07"),
            ("insulation", "07"),
        ])
        alternatives.extend(insulation_alts)
    
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
    """
    Thin wrapper around the Gordian RSMeans Data API.

    Typical usage:
        client = RSMeansAPIClient(client_id, client_secret)
        client.authenticate()                        # OAuth2 client_credentials
        results = client.search_unit_costlines(...)  # Step 1: find candidate IDs
        cost    = client.get_unit_costlines(...)     # Step 2: fetch cost for chosen ID
    """
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
        # Step 1 of 2: full-text search; returns candidate items with id + description.
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
        # Step 2 of 2: fetch the full cost record for a known division_code.
        # The only cost value extracted downstream is localizedCosts.totalOpCost (Total Incl. O&P).
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
        # NOTE: This method searches a single catalog.  For multi-catalog fallback
        # (the primary path used by measure.py), use search_materials_across_catalogs().

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


def build_wall_search_material_from_model(model) -> Optional[Dict[str, Any]]:
    walls = [
        s for s in model.getSurfaces()
        if s.surfaceType() == "Wall" and s.outsideBoundaryCondition() == "Outdoors"
    ]
    if not walls:
        return None

    total_area_m2 = sum(float(s.grossArea()) for s in walls)
    if total_area_m2 <= 0.0:
        return None

    total_area_ft2 = total_area_m2 * 10.763910416709722
    description = (
        f"{len(walls)} exterior wall surface(s); total area {total_area_m2:.2f} m2"
    )

    return {
        "name": "wall insulation",
        "description": description,
        "quantity": float(total_area_ft2),
        "unit": "SF",
        "division_code": "07",
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
    
    # Method 1: Pre-saved JSON file (wall-specific)
    materials_files = [
        model_dir / "wall_insulation_retrofit_materials.json",
    ]
    for materials_file in materials_files:
        if not materials_file.exists():
            continue
        try:
            with open(materials_file, "r", encoding="utf-8") as f:
                materials = json.load(f)
            print(f"Extracted {len(materials)} materials from {materials_file.name}")
            break
        except Exception as e:
            print(f"Warning: Could not load materials file {materials_file.name}: {e}")
    
    # Method 2: Extract from model's Facility AdditionalProperties
    if not materials:
        print(f"Loading model from {model_path.name}...")
        model = load_openstudio_model(model_path)
        
        if model.facility().is_initialized():
            facility = model.facility().get()
            props = facility.additionalProperties()
            
            # Try wall-specific property
            retrofit_keys = [
                "wall_insulation_retrofit_materials_json",
            ]
            for retrofit_key in retrofit_keys:
                if not props.hasFeature(retrofit_key):
                    continue
                try:
                    opt_str = props.getFeatureAsString(retrofit_key)
                    if opt_str.is_initialized():
                        json_str = opt_str.get()
                        materials = json.loads(json_str)
                        print(f"Extracted {len(materials)} materials from Facility.{retrofit_key}")
                        break
                except Exception as e:
                    print(f"Warning: Could not parse Facility.{retrofit_key}: {e}")
        
        # Method 3: Fall back to individual property extraction
        if not materials:
            materials = extract_materials_from_model(model, DEFAULT_FEATURE_KEYS)
            if materials:
                print(f"Extracted {len(materials)} materials using standard property keys")

        # Method 4: Derive a wall-insulation search term from the model
        if not materials:
            derived = build_wall_search_material_from_model(model)
            if derived:
                materials = [derived]
                print("Derived wall-insulation RSMeans search term from model:")
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

        material_name_lower = str(material_name).lower()
        if not specified_id and any(k in material_name_lower for k in ["polyiso", "polyisocyanurate"]):
            specified_id = "072216101700"

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
        best_bare_material_unit_cost = 0.0
        best_bare_material_total_cost = 0.0
        best_line_uom = None
        best_component_source = None
        chosen_source_type = "search"
        
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
                                line_uom = item.get("unitOfMeasure", "")
                                if not _uom_check_ok_for_material(material, unit, line_uom):
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
                                unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                _bare = _extract_bare_components(item)
                                _bare_unit = _bare["material"] + _bare["labor"] + _bare["equipment"]
                                if unit_cost > 0:
                                    computed = _compute_total_cost_for_material(
                                        material,
                                        unit_cost,
                                        str(item.get("description", "")),
                                        line_uom=line_uom,
                                    )
                                    _total_op = float(computed["total_cost"])
                                    _mat_frac = (_bare["material"] / _bare_unit) if _bare_unit > 0 else 1.0
                                    _lab_frac = (_bare["labor"] / _bare_unit) if _bare_unit > 0 else 0.0
                                    _eq_frac = (_bare["equipment"] / _bare_unit) if _bare_unit > 0 else 0.0
                                    best_total_material_cost = _total_op * _mat_frac
                                    best_total_labor_cost = _total_op * _lab_frac
                                    best_total_equipment_cost = _total_op * _eq_frac
                                    # Project total for bare material (no O&P): scale the project Op-total by
                                    # the bare/Op material ratio from the RSMeans line. Fall back to 0 when
                                    # the API did not return per-component bare costs.
                                    _bare_mat_unit = float(_bare.get("bare_material", 0.0) or 0.0)
                                    _op_mat_unit = float(_bare.get("material", 0.0) or 0.0)
                                    if _bare_mat_unit > 0 and _op_mat_unit > 0:
                                        best_bare_material_unit_cost = (
                                            float(computed["unit_cost"]) * _mat_frac * (_bare_mat_unit / _op_mat_unit)
                                        )
                                        best_bare_material_total_cost = (
                                            best_total_material_cost * (_bare_mat_unit / _op_mat_unit)
                                        )
                                    else:
                                        best_bare_material_unit_cost = 0.0
                                        best_bare_material_total_cost = 0.0
                                    best_component_source = _bare["source"]
                                    best_match = item
                                    best_cost = computed["total_cost"]
                                    best_catalog = catalog
                                    matched_term = f"rsmeans_id:{specified_id}"
                                    best_unit_cost = computed["unit_cost"]
                                    best_unit_basis = computed.get("effective_unit", unit)
                                    best_costing_mode = computed.get("costing_mode", "area")
                                    best_line_uom = line_uom
                                    chosen_source_type = "user_id"
                                    search_log.append({
                                        "material": material_name,
                                        "search_term": specified_id,
                                        "catalog": catalog,
                                        "division": division_code,
                                        "status": "exact_id_match",
                                        "unit_cost": computed["unit_cost"],
                                        "quantity": quantity,
                                        "total_cost": best_cost,
                                        "total_material_cost": best_total_material_cost,
                                        "total_labor_cost": best_total_labor_cost,
                                        "total_equipment_cost": best_total_equipment_cost,
                                        "bare_material_unit_cost": best_bare_material_unit_cost,
                                        "bare_material_total_cost": best_bare_material_total_cost,
                                        "cost_component_source": best_component_source,
                                        "costing_mode": best_costing_mode,
                                        "unit_cost_basis": best_unit_basis,
                                        "line_uom": line_uom,
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
                        match, ranked_candidates = _select_best_rsmeans_candidate(material_name, items)
                        if not match:
                            continue
                        division_id = match.get("id", "")
                        _candidate_count = len(ranked_candidates or [])
                        _fallback_id = _resolve_insulation_fallback_costline_id(material_name)
                        _force_fallback_multi = (
                            not specified_id and _candidate_count > 1 and bool(_fallback_id)
                        )
                        if _force_fallback_multi:
                            division_id = str(_fallback_id)
                            search_log.append({
                                "material": material_name,
                                "search_term": alt_term,
                                "catalog": catalog,
                                "division": alt_division,
                                "status": "multi_candidate_fallback",
                                "candidates_considered": _candidate_count,
                                "forced_fallback_costline_id": division_id,
                                "candidate_scores": ranked_candidates,
                            })
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
                                    line_uom = item.get("unitOfMeasure", "")
                                    if not _uom_check_ok_for_material(material, unit, line_uom):
                                        search_log.append({
                                            "material": material_name,
                                            "search_term": alt_term,
                                            "catalog": catalog,
                                            "division": alt_division,
                                            "status": "closest_match_uom_mismatch_rejected",
                                            "requested_unit": unit,
                                            "line_uom": line_uom,
                                            "rsmeans_id": division_id,
                                            "rsmeans_description": item.get("description", ""),
                                        })
                                        break
                                    unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                    _bare = _extract_bare_components(item)
                                    _bare_unit = _bare["material"] + _bare["labor"] + _bare["equipment"]

                                    if unit_cost > 0:
                                        _matched_desc = str(item.get("description", "")) if _force_fallback_multi else str(match.get("description", ""))
                                        computed = _compute_total_cost_for_material(
                                            material,
                                            unit_cost,
                                            _matched_desc,
                                            line_uom=line_uom,
                                        )
                                        _total_op = float(computed["total_cost"])
                                        _mat_frac = (_bare["material"] / _bare_unit) if _bare_unit > 0 else 1.0
                                        _lab_frac = (_bare["labor"] / _bare_unit) if _bare_unit > 0 else 0.0
                                        _eq_frac = (_bare["equipment"] / _bare_unit) if _bare_unit > 0 else 0.0
                                        best_total_material_cost = _total_op * _mat_frac
                                        best_total_labor_cost = _total_op * _lab_frac
                                        best_total_equipment_cost = _total_op * _eq_frac
                                        _bare_mat_unit = float(_bare.get("bare_material", 0.0) or 0.0)
                                        _op_mat_unit = float(_bare.get("material", 0.0) or 0.0)
                                        if _bare_mat_unit > 0 and _op_mat_unit > 0:
                                            best_bare_material_unit_cost = (
                                                float(computed["unit_cost"]) * _mat_frac * (_bare_mat_unit / _op_mat_unit)
                                            )
                                            best_bare_material_total_cost = (
                                                best_total_material_cost * (_bare_mat_unit / _op_mat_unit)
                                            )
                                        else:
                                            best_bare_material_unit_cost = 0.0
                                            best_bare_material_total_cost = 0.0
                                        best_component_source = _bare["source"]
                                        best_match = item
                                        best_cost = computed["total_cost"]
                                        best_catalog = catalog
                                        matched_term = f"fallback:{division_id}" if _force_fallback_multi else alt_term
                                        best_unit_cost = computed["unit_cost"]
                                        best_unit_basis = computed.get("effective_unit", unit)
                                        best_costing_mode = computed.get("costing_mode", "area")
                                        best_line_uom = line_uom
                                        if _force_fallback_multi or match.get("is_fallback"):
                                            chosen_source_type = "fallback"
                                        
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
                                            "total_material_cost": best_total_material_cost,
                                            "total_labor_cost": best_total_labor_cost,
                                            "total_equipment_cost": best_total_equipment_cost,
                                            "bare_material_unit_cost": best_bare_material_unit_cost,
                                            "bare_material_total_cost": best_bare_material_total_cost,
                                            "cost_component_source": best_component_source,
                                            "selected_id": division_id,
                                            "selected_description": match.get("description", ""),
                                            "top_candidates": ranked_candidates[:5],
                                            "costing_mode": computed.get("costing_mode", "area"),
                                            "unit_cost_basis": computed.get("effective_unit", unit),
                                            "line_uom": line_uom,
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
            if chosen_source_type == "user_id" and matched_term and str(matched_term).startswith("rsmeans_id:"):
                match_type = "exact_id_match"
            elif chosen_source_type == "fallback":
                match_type = "fallback_id"
            _raw_comp = _extract_bare_components(best_match)
            _raw_unit_cost = float(_raw_comp.get("material", 0.0) or 0.0) + float(_raw_comp.get("labor", 0.0) or 0.0) + float(_raw_comp.get("equipment", 0.0) or 0.0)
            _raw_uom = _normalize_uom(best_match.get("unitOfMeasure", ""))
            if _raw_unit_cost <= 0.0:
                _raw_unit_cost = float(best_unit_cost or 0.0)
            if not _raw_uom:
                _raw_uom = str(best_line_uom or best_unit_basis or material.get("unit", ""))
            material_result = {
                **material,
                "catalog": best_catalog,
                "search_term_used": matched_term,
                "unit_cost": best_unit_cost if best_unit_cost is not None else best_match.get("localizedCosts", {}).get("totalOpCost", 0.0),
                "total_cost": best_cost,
                "total_material_cost": best_total_material_cost,
                "total_labor_cost": best_total_labor_cost,
                "total_equipment_cost": best_total_equipment_cost,
                "bare_material_unit_cost": best_bare_material_unit_cost,
                "bare_material_unit_basis": best_unit_basis,
                "bare_material_total_cost": best_bare_material_total_cost,
                "line_uom": best_line_uom,
                "cost_component_source": best_component_source,
                "rsmeans_id": best_match.get("id", ""),
                "rsmeans_description": best_match.get("description", ""),
                "match_type": match_type,
                "chosen_source_type": chosen_source_type,
                "unit_cost_basis": best_unit_basis,
                "costing_mode": best_costing_mode,
                "pricing_unit_cost_raw": _raw_unit_cost,
                "pricing_unit_uom_raw": _raw_uom,
                "pricing_unit_cost_effective": float(best_unit_cost or 0.0),
                "pricing_unit_uom_effective": best_unit_basis,
                "pricing_source": "rsmeans_direct" if float(best_unit_cost or 0.0) > 0.0 else "unavailable",
            }
            all_results.append(material_result)
            _append_rsmeans_raw_log(material, best_match, best_catalog, match_type, matched_term)
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
    # Public entry point called by measure.py.
    # Authenticates, delegates to search_materials_across_catalogs(), and wraps
    # the result in a standardised {"status", "summary", "results"} envelope.
    materials: List[Dict[str, Any]],
    release_id: str = "2024-an",
    catalogs: Optional[List[str]] = None,
    location_id: str = "us-us-national",
    labor_type: str = "std",
    measurement_system: str = "imp",
    use_sandbox: bool = False,
    overhead_profit_percent: float = 0.0,
    cost_calculation_basis: str = "totalop",
    write_api_log: bool = True,
) -> Dict[str, Any]:
    """Run RSMeans lookup for provided materials and return summary/results."""
    global _WRITE_API_LOGS
    previous_write_api_logs = _WRITE_API_LOGS
    _WRITE_API_LOGS = bool(write_api_log)

    try:
        load_dotenv()
        client_id = os.getenv("client_id")
        client_secret = os.getenv("client_secret")

        if not client_id or not client_secret:
            _append_rsmeans_summary_log({
                "status": "auth_error",
                "message": "RSMeans API credentials not found in environment",
            })
            return {
                "status": "auth_error",
                "message": "RSMeans API credentials not found in environment",
            }

        client = RSMeansAPIClient(client_id, client_secret, use_sandbox=use_sandbox)
        if not client.authenticate():
            _append_rsmeans_summary_log({
                "status": "auth_error",
                "message": "RSMeans authentication failed",
            })
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
            # Fallback: per-component breakdown was unavailable; use legacy total
            # (which is the per-line ``totalOpCost`` aggregated by the search step).
            total_bare_cost = float(results.get("total_cost", 0.0))
            total_material_cost = total_bare_cost
        # Per-line unit costs already include RSMeans O&P (``totalOpCost``); no
        # additional markup is layered here. ``overhead_profit_percent`` is
        # retained in the summary for traceability but does not alter the total.
        overhead_profit_cost = 0.0
        total_cost = total_bare_cost
        normalized_basis = str(cost_calculation_basis or "totalop").strip().lower()
        if normalized_basis not in ("totalop", "bare_material"):
            normalized_basis = "totalop"
        selected_total_cost = total_material_cost if normalized_basis == "bare_material" else total_cost

        summary = {
            "total_material_cost": total_material_cost,
            "total_labor_cost": total_labor_cost,
            "total_equipment_cost": total_equipment_cost,
            "total_bare_cost": total_bare_cost,
            "overhead_profit_percent": overhead_profit_percent,
            "total_overhead_profit_cost": overhead_profit_cost,
            "total_cost_with_overhead_profit": total_cost,
            "cost_calculation_basis": normalized_basis,
            "selected_total_cost": selected_total_cost,
            "materials_count": len(results.get("materials", [])),
            "materials_searched": len(materials),
            "catalogs_searched": results.get("catalogs_searched", catalogs or []),
            "release_id": release_id,
            "location_id": location_id,
            "labor_type": labor_type,
            "measurement_system": measurement_system,
            "use_sandbox": use_sandbox,
        }

        _append_rsmeans_summary_log({
            "status": "ok",
            "summary": summary,
            "results": results,
        })

        return {
            "status": "ok",
            "summary": summary,
            "results": results,
        }
    finally:
        _WRITE_API_LOGS = previous_write_api_logs


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
Standalone RSMeans API helper for IncreaseInsulationRValueForRoofs.

This helper is intentionally local to the roof measure so RSMeans lookup
behavior does not depend on other measure directories.

Search behavior summary:
1) Prefer exact costline ID when one is supplied.
2) Otherwise run closest-match scoring over candidate search results.
3) Reject weak closest matches and fall back to configured fallback IDs.
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


DEFAULT_FEATURE_KEYS = {
    "name": "retrofit_material_name",
    "description": "retrofit_material_description",
    "quantity": "retrofit_material_quantity",
    "unit": "retrofit_material_unit",
    "division_code": "rsmeans_division_code",
    "unit_cost": "rsmeans_unit_cost",
    "total_cost": "rsmeans_total_cost",
}

# Closest-match results below this score are treated as unresolved and
# redirected to fallback IDs when available. Aligned with door_enhancement /
# window_enhancement / wall_insulation (70) after run_test_008 showed
# unrelated lines scoring high enough at 50 to be accepted for distinct
# materials. Curated fallback IDs are reliable, so it is safer to fall through
# to them when the search match is weak.
MIN_ACCEPTABLE_MATCH_SCORE = 70.0

RSMEANS_RAW_LOG_ENV = "RSMEANS_SCENARIO_RAW_LOG_PATH"
MEASURE_LOG_SLUG = "roof_insulation"


def _append_rsmeans_raw_log(material, matched_item, catalog, match_type, search_term):
    """Append raw RSMeans unit-cost fields for the matched line item."""
    if not isinstance(matched_item, dict):
        return
    append_measure_raw_record(MEASURE_LOG_SLUG, material, matched_item, catalog, match_type, search_term)


def _id_matches_division(item_id, division_code) -> bool:
    """Return True if ``item_id`` (RSMeans line number) starts with
    ``division_code`` prefix. Empty division means no constraint.
    Defense-in-depth so an insulation lookup (e.g. division '07') never
    accepts a match from an unrelated division.
    """
    if not division_code:
        return True
    if not item_id:
        return False
    return str(item_id).strip().startswith(str(division_code).strip())


# ----------------------------------------------------------------------------
# UOM compatibility guard
# ----------------------------------------------------------------------------
# Roof insulation requests are SF (area) with costing_mode='volume_from_area',
# so the SF-priced cost-line is internally converted to $/CF via the parsed
# line thickness in _compute_total_cost_for_material. The guard is therefore
# bypassed when costing_mode == 'volume_from_area' so SF-priced lines stay
# acceptable; for all other modes the requested unit must match the line UOM.
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


def _normalize_uom(uom) -> str:
    if uom is None:
        return ""
    text = str(uom).strip().lower()
    if not text:
        return ""
    return _UOM_NORMALIZE.get(text, text.upper().replace(".", "").replace(" ", ""))


def _uom_compatible(requested_unit, returned_uom) -> bool:
    req = _normalize_uom(requested_unit)
    ret = _normalize_uom(returned_uom)
    if not ret or not req:
        return True
    if req == ret:
        return True
    if req in {"EA", "OPNG"} and ret in {"EA", "OPNG"}:
        return True
    return False


def _uom_check_ok_for_material(material, unit, line_uom) -> bool:
    if str(material.get("costing_mode", "")).lower() == "volume_from_area":
        return True
    return _uom_compatible(unit, line_uom)


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


def _extract_unit_cost_components(item: Dict[str, Any]) -> Dict[str, Any]:
    """Pull material/labor/equipment unit costs from a RSMeans line item.

            _raw_comp = _extract_bare_components(best_match)
            _raw_unit_cost = float(_raw_comp.get("material", 0.0) or 0.0) + float(_raw_comp.get("labor", 0.0) or 0.0) + float(_raw_comp.get("equipment", 0.0) or 0.0)
            _raw_uom = _normalize_uom(best_match.get("unitOfMeasure", ""))
            if _raw_unit_cost <= 0.0:
                _raw_unit_cost = float(calc.get("unit_cost", 0.0) or 0.0)
            if not _raw_uom:
                _raw_uom = str(calc.get("line_uom") or calc.get("effective_unit", material.get("unit", "")))
    The Gordian/RSMeans cost API returns a ``localizedCosts`` object containing
    both bare and "Op" (already includes overhead & profit) variants of the
    material, labor and equipment cost components:

      - ``materialCost`` / ``materialOpCost``
      - ``laborCost``    / ``laborOpCost``
      - ``equipmentCost``/ ``equipmentOpCost``
      - ``totalCost``    / ``totalOpCost``

    Returned ``material``/``labor``/``equipment`` keys hold the Op-marked-up
    values so the per-line sum equals ``totalOpCost`` (matches the book's
    "Total Incl. O&P" figure). Additional ``bare_*`` keys carry the no-O&P
    component values so callers can persist them separately.

    If the per-component O&P fields are missing from the response, the helper
    falls back to attributing the entire ``totalOpCost`` value to material so
    upstream behavior is preserved.

    Returns:
        Dict with keys ``material``, ``labor``, ``equipment`` (Op variants),
        ``bare_material``/``bare_labor``/``bare_equipment``/``bare_total``
        (no-O&P variants), ``op_total`` (the API's totalOpCost for reference)
        and ``source`` ("op_components" or "total_op_cost_fallback").
    """
    lc = item.get("localizedCosts", {}) or {}
    op_total = float(lc.get("totalOpCost", 0.0) or 0.0)
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
            "op_total": op_total,
            "source": "op_components",
        }

    return {
        "material": op_total,
        "labor": 0.0,
        "equipment": 0.0,
        "bare_material": bare_material,
        "bare_labor": bare_labor,
        "bare_equipment": bare_equipment,
        "bare_total": bare_total,
        "op_total": op_total,
        "source": "total_op_cost_fallback",
    }


def _compute_total_costs_by_component(
    material: Dict[str, Any],
    components: Dict[str, float],
    matched_description: str,
    line_uom: Any = None,
) -> Dict[str, Any]:
    """Run the unit→quantity conversion for each cost component independently.

    The thickness conversion encoded in :func:`_compute_total_cost_for_material`
    depends only on ``costing_mode``, the matched RSMeans line description and
    the line's unit of measure, not on the magnitude of the cost. We therefore
    call it once per component (material / labor / equipment, plus the bare
    counterparts) so the same area→volume normalization is applied uniformly.

    Returns a dict with per-component unit and total costs, plus combined
    ``unit_cost``/``total_cost`` (sum of Op components), bare counterparts
    (``unit_bare_*_cost``, ``total_bare_*_cost``) and pass-through metadata.
    """
    out: Dict[str, Any] = {}
    sample = None
    for name in ("material", "labor", "equipment"):
        comp_calc = _compute_total_cost_for_material(
            material,
            float(components.get(name, 0.0) or 0.0),
            matched_description,
            line_uom=line_uom,
        )
        out[f"unit_{name}_cost"] = comp_calc["unit_cost"]
        out[f"total_{name}_cost"] = comp_calc["total_cost"]
        if sample is None:
            sample = comp_calc

    # Same conversion applied to the bare (no-O&P) components so the bare
    # material total can be persisted alongside the Op-marked-up total.
    for name in ("material", "labor", "equipment"):
        bare_calc = _compute_total_cost_for_material(
            material,
            float(components.get(f"bare_{name}", 0.0) or 0.0),
            matched_description,
            line_uom=line_uom,
        )
        out[f"unit_bare_{name}_cost"] = bare_calc["unit_cost"]
        out[f"total_bare_{name}_cost"] = bare_calc["total_cost"]

    out["costing_mode"] = sample["costing_mode"]
    out["effective_unit"] = sample["effective_unit"]
    out["line_uom"] = sample.get("line_uom", line_uom)
    if "source_unit_cost_per_sf" in sample:
        out["source_line_thickness_ft"] = sample.get("source_line_thickness_ft")
    out["unit_cost"] = (
        out["unit_material_cost"] + out["unit_labor_cost"] + out["unit_equipment_cost"]
    )
    out["total_cost"] = (
        out["total_material_cost"] + out["total_labor_cost"] + out["total_equipment_cost"]
    )
    out["unit_bare_total_cost"] = (
        out["unit_bare_material_cost"] + out["unit_bare_labor_cost"] + out["unit_bare_equipment_cost"]
    )
    out["total_bare_total_cost"] = (
        out["total_bare_material_cost"] + out["total_bare_labor_cost"] + out["total_bare_equipment_cost"]
    )
    out["component_source"] = components.get("source", "unknown")
    return out


def _compute_total_cost_for_material(
    material: Dict[str, Any],
    unit_cost: float,
    matched_description: str,
    line_uom: Any = None,
) -> Dict[str, Any]:
    """Convert a RSMeans unit cost into a total cost for the given material quantity.

    RSMeans often prices insulation per SF at a specific thickness (e.g. '$/SF for
    3-1/2" thick batts').  When the measure needs a different thickness, the unit
    cost must be re-expressed as $/CF so it can be multiplied against the actual
    installed volume rather than a fixed-thickness area. However some lines
    (e.g. blown/poured loose-fill, mineral wool poured-in) are *already* priced
    per volume (CF or CY) by RSMeans — in that case we use the unit cost
    directly and skip the thickness conversion entirely.

    Costing modes:
      - 'area'            : total = unit_cost * area_SF  (no conversion needed)
      - 'volume_from_area':
          * line_uom in {CF, CY}: total = unit_cost_per_cf * volume_CF
              (CY lines are scaled by 1/27 to put unit cost in $/CF)
          * otherwise           : total = (unit_cost / line_thickness_ft) * volume_CF
              The thickness is parsed from the matched RSMeans description
              string. If the description has no parseable thickness, this
              function raises ValueError and the caller must reject the line
              (no fallback to a project-supplied thickness).

    Args:
        material:            The retrofit material dict (name, quantity, unit, etc.).
        unit_cost:           RSMeans localizedCosts.totalOpCost for the matched line.
        matched_description: Description text of the matched RSMeans cost line,
                             used to extract the reference thickness.
        line_uom:            The matched RSMeans line's unitOfMeasure string
                             (e.g. "C.F.", "S.F."). Used to detect volume-priced
                             lines so we don't divide by a fabricated thickness.

    Returns:
        Dict with keys: unit_cost, total_cost, costing_mode, effective_unit,
        and (for volume-from-area mode) source_unit_cost_per_sf,
        source_line_thickness_ft. For volume-direct mode, includes ``line_uom``.
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
    # correct. Avoids deriving a spurious $/CF from the project's added
    # thickness (which is not a property of the RSMeans line).
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


def _score_rsmeans_candidate(
    material_name: str,
    item: Dict[str, Any],
) -> tuple:
    """Score a single RSMeans search-result candidate against the requested material.

    The score reflects how well the RSMeans line item description matches the
    material we are looking for.  Higher is better.

    Scoring rules (additive):
      +100  exact string match (normalised)
      +60   material name is a substring of description
      +15   per shared token (word-level overlap)
      -20   description mentions 'insulation' but shares fewer than 2 tokens
              (catches unrelated insulation types)
      -10   material name mentions 'roof' but description does not
      -25   material is for roofs but description mentions walls only
      +/-30/40  polyiso/polyisocyanurate specificity bonus/penalty
      +0..1 slight length tiebreaker (longer descriptions are slightly preferred)

    Returns:
        (raw_score, clamped_score) where raw_score may exceed [0, 100] and
        clamped_score is max(0, min(100, raw_score)).  The clamped value is
        compared against MIN_ACCEPTABLE_MATCH_SCORE to decide whether to fall
        back to a pre-configured costline ID.
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
    if "roof" not in description_norm and "roof" in material_norm:
        score -= 10.0
    if (
        "roof" in material_norm
        and "wall" in description_norm
        and "roof" not in description_norm
    ):
        score -= 25.0
    if "polyiso" in material_norm or "polyisocyanurate" in material_norm:
        if "polyisocyanurate" in description_norm:
            score += 40.0
        elif "polyiso" in description_norm:
            score += 30.0
        else:
            score -= 30.0

    score += min(len(description_norm), 120) / 120.0
    # Keep both scores: raw helps diagnostics, clamped is used for thresholding.
    clamped_score = max(0.0, min(100.0, score))
    return score, clamped_score


def _resolve_fallback_costline_id(
    material_name: str,
    fallback_costline_ids: Dict[str, str],
) -> Optional[str]:
    """Return a pre-configured fallback RSMeans costline ID for a material name.

    The fallback dict supports three kinds of keys:
      - Exact name match:  key == material_name  (highest priority)
      - Keyword match:     key starts with 'keyword:'  and the keyword
                           appears anywhere in the normalised material name
      - Default:           key == '__default__'  (lowest priority, always matches)

    This is used when the scored closest-match search returns a weak result
    (score < MIN_ACCEPTABLE_MATCH_SCORE) or finds nothing at all, ensuring the
    measure still produces a cost estimate rather than failing silently.

    Returns:
        A costline ID string, or None if the dict is empty or has no match.
    """
    if not fallback_costline_ids:
        return None

    exact = fallback_costline_ids.get(material_name)
    if exact:
        return exact

    material_norm = _normalize_search_text(material_name)
    for key, fallback_id in fallback_costline_ids.items():
        if not isinstance(key, str) or not key.lower().startswith("keyword:"):
            continue
        keyword = _normalize_search_text(key.split(":", 1)[1])
        if keyword and keyword in material_norm:
            return fallback_id

    return fallback_costline_ids.get("__default__")


def _is_disallowed_candidate(item: Dict[str, Any]) -> bool:
    """Return True if a RSMeans search result should be excluded from scoring.

    Some search results share a division code with insulation but are not
    insulation materials themselves (fasteners, hangers, board-foot priced items,
    tapered drainage boards, etc.).  Including them in scoring would pollute
    the best-match selection with irrelevant or misleading line items.

    Excluded categories:
      - Fasteners, clips, hangers, anchors (accessories, not insulation)
      - Board-foot (BF) unit items  (pricing basis incompatible with SF/CF)
      - Tapered-for-drainage items  (specialty slope boards, not flat insulation)

    Returns:
        True if the item should be skipped; False if it is eligible for scoring.
    """
    desc = _normalize_search_text(item.get("description", ""))
    if not desc:
        return False

    if "tapered for drainage" in desc or (
        "tapered" in desc and "drainage" in desc
    ):
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


def _select_best_rsmeans_candidate(
    material_name: str,
    items: List[Dict[str, Any]],
) -> tuple:
    """Choose the best-matching RSMeans candidate from a list of search results.

    Steps:
      1. Filter out disallowed items (accessories, BF-priced lines, drainage boards).
      2. Score every eligible item with _score_rsmeans_candidate.
      3. Sort descending by clamped score and return the top item.

    The full scored list is also returned so the measure can:
      a) detect ties (ambiguous matches) and warn the user, and
      b) record candidate scores in the diagnostics JSON for traceability.

    Args:
        material_name: The insulation material string we are searching for.
        items:         Raw search-result items from the RSMeans API response.

    Returns:
        (best_item, scored_list) where best_item is the winning RSMeans dict
        and scored_list is a list of dicts with rsmeans_id, description,
        raw_score, and score for every candidate considered.
    """
    if not items:
        return None, []

    eligible_items = [item for item in items if not _is_disallowed_candidate(item)]
    if not eligible_items:
        eligible_items = items

    scored = []
    for idx, item in enumerate(eligible_items):
        raw_score, clamped_score = _score_rsmeans_candidate(material_name, item)
        desc = item.get("description", "")
        desc = desc[:80] if desc else ""
        scored.append({
            "index": idx,
            "rsmeans_id": item.get("costlineID", item.get("id", "unknown")),
            "description": desc,
            "raw_score": round(raw_score, 2),
            "score": round(clamped_score, 2),
        })

    scored.sort(key=lambda x: -x["score"])
    best_idx = scored[0]["index"]
    best_candidate = eligible_items[best_idx]

    return best_candidate, scored


def generate_search_term_alternatives(material_name: str) -> List[tuple]:
    """Generate an ordered list of (search_term, division_code) pairs to try.

    RSMeans search can be narrow (specific term + division) or broad (generic
    term, any division).  This function produces a progressive fallback list
    so the caller can try the most specific query first and broaden if nothing
    is found.

    Examples of generated alternatives for 'Blown Cellulose':
      ('Blown Cellulose', '07')
      ('blown cellulose', '07')
      ('cellulose insulation', '07')
      ('roof insulation', '07')
      ('insulation', '07')
      ('cellulose', '07')  <- last-word fallback

    The division code '07' is used for all thermal/moisture protection items
    (roofing, insulation, waterproofing).

    Returns:
        List of (term, division_code) 2-tuples.  division_code may be None
        for the broadest fallback terms.
    """
    alternatives = []
    name_lower = material_name.lower().strip()
    cleaned_name = re.sub(r"\b\d+(?:\.\d+)?\b", "", name_lower)
    cleaned_name = cleaned_name.replace("ft", " ").replace("in", " ").replace("x", " ")
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()

    original_division = get_division_from_material_type(material_name)
    alternatives.append((material_name, original_division))
    if cleaned_name and cleaned_name != name_lower:
        alternatives.append((cleaned_name, get_division_from_material_type(cleaned_name)))

    if "window" in name_lower:
        if "glaz" in name_lower:
            alternatives.extend([
                ("insulated glass unit", "08"),
                ("double glazed window", "08"),
                ("glass window", "08"),
                ("window glass", "08"),
                ("glazing", "08"),
                ("IGU", "08"),
            ])
        elif "frame" in name_lower:
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
            alternatives.extend([
                ("window replacement", "08"),
                ("window unit", "08"),
                ("window assembly", "08"),
                ("window", "08"),
            ])
    elif "door" in name_lower:
        if "metal" in name_lower or "steel" in name_lower:
            alternatives.append(("metal door", "08"))
        alternatives.extend([
            ("door replacement", "08"),
            ("door unit", "08"),
            ("door assembly", "08"),
            ("door", "08"),
        ])
    elif "insulation" in name_lower or "insul" in name_lower:
        if "fiberglass" in name_lower or "fiber glass" in name_lower:
            if "blown" in name_lower or "loose" in name_lower:
                alternatives.extend([
                    ("blown fiberglass", "07"),
                    ("loose fill fiberglass", "07"),
                    ("fiberglass loose fill", "07"),
                    ("fiberglass batts", "07"),
                ])
            else:
                alternatives.extend([
                    ("fiberglass batts", "07"),
                    ("fiberglass blanket", "07"),
                    ("blown fiberglass", "07"),
                    ("roof fiberglass", "07"),
                ])
        if "cellulose" in name_lower:
            alternatives.extend([
                ("blown cellulose", "07"),
                ("cellulose insulation", "07"),
            ])
        if "mineral wool" in name_lower or "mineral" in name_lower:
            if "blown" in name_lower or "loose" in name_lower:
                alternatives.extend([
                    ("blown mineral wool", "07"),
                    ("mineral wool loose fill", "07"),
                    ("loose fill mineral wool", "07"),
                    ("mineral wool batts", "07"),
                ])
            elif "heavy" in name_lower:
                alternatives.extend([
                    ("mineral wool board", "07"),
                    ("mineral wool rigid", "07"),
                    ("mineral wool heavy density", "07"),
                    ("mineral wool batts", "07"),
                ])
            elif "light" in name_lower:
                alternatives.extend([
                    ("mineral wool blanket", "07"),
                    ("mineral wool light density", "07"),
                    ("mineral wool batts", "07"),
                ])
            else:
                alternatives.extend([
                    ("mineral wool batts", "07"),
                    ("mineral wool blanket", "07"),
                    ("mineral wool insulation", "07"),
                ])
        if "polyiso" in name_lower:
            alternatives.extend([
                ("polyiso insulation", "07"),
                ("polyiso board", "07"),
                ("polyiso foam", "07"),
            ])
        xps_match = (
            ("extruded" in name_lower and "polystyrene" in name_lower)
            or "xps" in name_lower
        )
        gps_match = (
            ("graphite" in name_lower and "polystyrene" in name_lower)
            or "gps" in name_lower
        )
        eps_match = (
            ("expanded" in name_lower and "polystyrene" in name_lower)
            or "eps" in name_lower
        )
        if xps_match:
            alternatives.extend([
                ("extruded polystyrene", "07"),
                ("xps foam board", "07"),
                ("xps insulation", "07"),
            ])
        elif gps_match:
            alternatives.extend([
                ("graphite polystyrene", "07"),
                ("gps foam board", "07"),
                ("gps insulation", "07"),
            ])
        elif eps_match:
            alternatives.extend([
                ("expanded polystyrene", "07"),
                ("eps foam board", "07"),
                ("eps insulation", "07"),
            ])
        elif "polystyrene" in name_lower:
            alternatives.extend([
                ("foam board insulation", "07"),
                ("polystyrene insulation", "07"),
            ])
        if "wool" in name_lower or "batts" in name_lower:
            is_natural_wool = (
                "pure wool" in name_lower
                or "natural wool" in name_lower
                or "sheep wool" in name_lower
            )
            if is_natural_wool:
                alternatives.extend([
                    ("natural wool insulation", "07"),
                    ("sheep wool insulation", "07"),
                    ("wool batt insulation", "07"),
                    ("batt insulation", "07"),
                ])
            elif "mineral" not in name_lower:
                alternatives.extend([
                    ("wool batts", "07"),
                    ("wool insulation", "07"),
                ])
        alternatives.extend([
            ("wall insulation", "07"),
            ("roof insulation", "07"),
            ("batt insulation", "07"),
            ("rigid insulation", "07"),
            ("insulation", "07"),
        ])
    elif any(term in name_lower for term in ["hvac", "heat pump", "furnace", "boiler", "chiller"]):
        alternatives.extend([
            (material_name.replace("system", "unit"), "23"),
            (material_name.replace("equipment", "unit"), "23"),
            ("HVAC equipment", "23"),
        ])

    words = cleaned_name.split() if cleaned_name else name_lower.split()
    if len(words) > 1:
        last_word = words[-1]
        last_div = get_division_from_material_type(last_word)
        if (last_word, last_div) not in alternatives:
            alternatives.append((last_word, last_div))

        if len(words) > 2:
            simplified = f"{words[0]} {words[-1]}"
            simp_div = get_division_from_material_type(simplified)
            if (simplified, simp_div) not in alternatives:
                alternatives.append((simplified, simp_div))

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
        self.base_url = (
            "https://dataapi-sb.gordian.com"
            if use_sandbox else "https://dataapi.gordian.com"
        )
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
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                params=params,
                verify=False,
            )
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
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                params=params,
                verify=False,
            )
            response.raise_for_status()
            print(f"Cost lines: catalog={catalog_id}, division={division_code}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost line: {e}")
            return None


def load_openstudio_model(model_path: Path):
    try:
        import openstudio  # pylint: disable=import-error
    except Exception as exc:
        raise RuntimeError(
            "openstudio python bindings are required to read a model"
        ) from exc

    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(openstudio.toPath(str(model_path)))
    if not model_opt.is_initialized():
        raise RuntimeError(f"Failed to load model: {model_path}")
    return model_opt.get()


def extract_materials_from_model(
    model,
    feature_keys: Dict[str, str],
) -> List[Dict[str, Any]]:
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
    apply_measure_path = script_dir / "apply_measure.py"

    if not apply_measure_path.exists():
        raise FileNotFoundError(f"apply_measure.py not found at {apply_measure_path}")

    with open(apply_measure_path, "r", encoding="utf-8") as f:
        content = f.read()

    input_match = re.search(
        r'model_path\s*=\s*SCRIPT_DIR\s*/\s*"tests"\s*/\s*"([^"]+)"',
        content,
    )
    if not input_match:
        raise ValueError("Could not find model_path in apply_measure.py")

    input_filename = input_match.group(1)
    input_path = script_dir / "tests" / input_filename

    output_dir_match = re.search(
        r'output_dir\s*=\s*SCRIPT_DIR\s*/\s*"tests"\s*/\s*"([^"]+)"',
        content,
    )
    if output_dir_match:
        output_subdir = output_dir_match.group(1)
        output_dir = script_dir / "tests" / output_subdir
    else:
        output_dir = script_dir / "tests" / "output"

    output_match = re.search(
        r'output_model_path\s*=\s*output_dir\s*/\s*"([^"]+)"',
        content,
    )
    if not output_match:
        raise ValueError("Could not find output_model_path in apply_measure.py")

    output_filename = output_match.group(1)
    output_path = output_dir / output_filename

    return (input_path, output_path)


def parse_args() -> argparse.Namespace:
    script_file = Path(__file__).resolve()
    if script_file.parent.name == "resources":
        measure_dir = script_file.parent.parent
    else:
        measure_dir = script_file.parent

    try:
        _, default_output_model = extract_paths_from_apply_measure(measure_dir)
        default_output_json = default_output_model.parent / "rsmeans_search_results.json"
        auto_detected = True
    except Exception:
        default_output_model = measure_dir / "tests" / "output" / "model_enhanced.osm"
        default_output_json = measure_dir / "tests" / "output" / "rsmeans_search_results.json"
        auto_detected = False

    parser = argparse.ArgumentParser(
        description="RSMeans API lookup for materials stored in OpenStudio OSM files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="Comma-separated catalog codes (bc-mf, gb-mf, rp-mf, sq-mf, hc-mf, si-mf)",
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

    materials = None
    model_dir = model_path.parent

    materials_file = model_dir / "roof_insulation_retrofit_materials.json"
    if materials_file.exists():
        try:
            with open(materials_file, "r", encoding="utf-8") as f:
                materials = json.load(f)
            print(f"Extracted {len(materials)} materials from {materials_file.name}")
        except Exception as e:
            print(f"Warning: Could not load materials file: {e}")

    if not materials:
        print(f"Loading model from {model_path.name}...")
        model = load_openstudio_model(model_path)

        facility = model.getFacility()
        props = facility.additionalProperties()
        if props.hasFeature("roof_insulation_retrofit_materials_json"):
            try:
                opt_str = props.getFeatureAsString("roof_insulation_retrofit_materials_json")
                if opt_str.is_initialized():
                    json_str = opt_str.get()
                    materials = json.loads(json_str)
                    print(
                        "Extracted "
                        f"{len(materials)} materials from "
                        "Facility.roof_insulation_retrofit_materials_json"
                    )
            except Exception as e:
                print(f"Warning: Could not parse roof retrofit_materials_json: {e}")

        if not materials:
            materials = extract_materials_from_model(model, DEFAULT_FEATURE_KEYS)
            if materials:
                print(f"Extracted {len(materials)} materials using standard property keys")

    if not materials:
        print("ERROR: No retrofit materials found in model.")
        print("The model must have materials stored in AdditionalProperties.")
        return 1

    catalogs = [c.strip() for c in args.catalogs.split(",")]
    print(f"\nSearching RSMeans catalogs: {', '.join(catalogs)}")

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=args.use_sandbox)
    if not client.authenticate():
        print("ERROR: Authentication failed.")
        return 1

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

    total_material_cost = float(results.get("total_material_cost", 0.0))
    total_labor_cost = float(results.get("total_labor_cost", 0.0))
    total_equipment_cost = float(results.get("total_equipment_cost", 0.0))
    total_bare_cost = total_material_cost + total_labor_cost + total_equipment_cost
    if total_bare_cost <= 0.0:
        total_bare_cost = float(results.get("total_cost", 0.0))
        total_material_cost = total_bare_cost
    # Per-line unit costs already include RSMeans O&P (``totalOpCost``); no
    # additional markup is layered here.
    overhead_profit_cost = 0.0
    total_cost = total_bare_cost

    summary = {
        "total_material_cost": total_material_cost,
        "total_labor_cost": total_labor_cost,
        "total_equipment_cost": total_equipment_cost,
        "total_bare_cost": total_bare_cost,
        "overhead_profit_percent": args.overhead_profit_percent,
        "total_overhead_profit_cost": overhead_profit_cost,
        "total_cost_with_overhead_profit": total_cost,
        "materials_count": len(results.get("materials", [])),
        "materials_searched": len(materials),
        "catalogs_searched": catalogs,
    }

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    print("\n" + "=" * 70)
    print("COST SUMMARY")
    print("=" * 70)
    print(f"Materials searched:  {len(materials)}")
    print(f"Materials matched:   {len(results.get('materials', []))}")
    print(f"Material cost:       ${total_material_cost:,.2f}")
    print(f"Labor cost:          ${total_labor_cost:,.2f}")
    print(f"Equipment cost:      ${total_equipment_cost:,.2f}")
    print(
        f"Overhead+profit:     ${overhead_profit_cost:,.2f} "
        f"({args.overhead_profit_percent}%)"
    )
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
    fallback_costline_ids: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if catalogs is None:
        catalogs = ["bc-mf", "gb-mf", "rp-mf"]

    if fallback_costline_ids is None:
        fallback_costline_ids = {}

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

        if not specified_id:
            material_name_norm = _normalize_search_text(material_name)
            if "polyiso" in material_name_norm or "polyisocyanurate" in material_name_norm:
                specified_id = "072216101700"

        material_fallback_id = _resolve_fallback_costline_id(material_name, fallback_costline_ids)

        print("\n" + "-" * 70)
        print(f"RSMeans lookup for material: {material_name}")
        print(f"  Quantity : {quantity} {unit}")
        print(f"  Division : {division_code or 'auto'}")

        best_match = None
        best_cost = None
        best_cost_calc = None
        best_catalog = None
        matched_term = None
        force_fallback_due_to_score = False
        force_fallback_due_to_ambiguity = False
        explicit_id_used = False

        if specified_id:
            if division_code and not _id_matches_division(specified_id, division_code):
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
                                components = _extract_unit_cost_components(item)
                                cost_calc = _compute_total_costs_by_component(
                                    material,
                                    components,
                                    item.get("description", ""),
                                    line_uom=line_uom,
                                )
                                if cost_calc["total_cost"] > 0:
                                    best_match = item
                                    best_cost = cost_calc["total_cost"]
                                    best_cost_calc = cost_calc
                                    best_catalog = catalog
                                    matched_term = f"rsmeans_id:{specified_id}"
                                    explicit_id_used = True
                                    search_log.append({
                                        "material": material_name,
                                        "search_term": specified_id,
                                        "catalog": catalog,
                                        "division": division_code,
                                        "status": "exact_id_match",
                                        "unit_cost": cost_calc["unit_cost"],
                                        "unit_material_cost": cost_calc["unit_material_cost"],
                                        "unit_labor_cost": cost_calc["unit_labor_cost"],
                                        "unit_equipment_cost": cost_calc["unit_equipment_cost"],
                                        "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                        "costing_mode": cost_calc.get("costing_mode", "area"),
                                        "quantity": quantity,
                                        "total_cost": best_cost,
                                        "total_material_cost": cost_calc["total_material_cost"],
                                        "total_labor_cost": cost_calc["total_labor_cost"],
                                        "total_equipment_cost": cost_calc["total_equipment_cost"],
                                        "cost_component_source": cost_calc.get("component_source"),
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
                        "error": str(e),
                    })

        search_alternatives = generate_search_term_alternatives(material_name)
        if division_code:
            search_alternatives.insert(0, (material_name, division_code))

        for catalog in catalogs:
            if best_match:
                break

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

                    items = _filter_demo_items(_extract_search_items(results))
                    if items:
                        match, candidate_details = _select_best_rsmeans_candidate(
                            material_name,
                            items,
                        )
                        if not match:
                            continue
                        division_id = match.get("id", "")
                        print("  Match:")
                        print(f"    ID          : {division_id}")
                        print(f"    Description : {match.get('description', '')}")
                        print(
                            f"    Candidates  : {len(items)} "
                            "(best-scored selected)"
                        )

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
                                    components = _extract_unit_cost_components(item)
                                    cost_calc = _compute_total_costs_by_component(
                                        material,
                                        components,
                                        match.get("description", ""),
                                        line_uom=line_uom,
                                    )

                                    if cost_calc["total_cost"] > 0:
                                        _candidate_count = len(candidate_details or [])
                                        if not specified_id and _candidate_count > 1 and material_fallback_id:
                                            force_fallback_due_to_ambiguity = True
                                            search_log.append({
                                                "material": material_name,
                                                "search_term": alt_term,
                                                "catalog": catalog,
                                                "status": "multi_candidate_fallback",
                                                "fallback_costline_id": material_fallback_id,
                                                "candidates_considered": _candidate_count,
                                                "candidate_scores": candidate_details,
                                            })
                                            break
                                        top_score = candidate_details[0].get("score", 0.0)
                                        if top_score < MIN_ACCEPTABLE_MATCH_SCORE and material_fallback_id:
                                            force_fallback_due_to_score = True
                                            search_log.append({
                                                "material": material_name,
                                                "search_term": alt_term,
                                                "catalog": catalog,
                                                "status": "poor_match_score_fallback",
                                                "score": top_score,
                                                "min_acceptable_score": MIN_ACCEPTABLE_MATCH_SCORE,
                                                "fallback_costline_id": material_fallback_id,
                                                "candidates_considered": len(items),
                                                "candidate_scores": candidate_details,
                                            })
                                            break

                                        best_match = item
                                        best_catalog = catalog
                                        matched_term = alt_term
                                        best_cost = cost_calc["total_cost"]
                                        best_cost_calc = cost_calc

                                        status_msg = "match_found"
                                        if alt_term != material_name:
                                            status_msg += f" (using '{alt_term}')"
                                            print(
                                                "  Note: matched on alternative term "
                                                f"'{alt_term}' in {catalog}"
                                            )

                                        search_log.append({
                                            "material": material_name,
                                            "search_term": alt_term,
                                            "catalog": catalog,
                                            "division": alt_division,
                                            "status": status_msg,
                                            "candidates_considered": len(items),
                                            "candidate_scores": candidate_details,
                                            "rsmeans_id": division_id,
                                            "rsmeans_description": match.get("description", ""),
                                            "unit_cost": cost_calc["unit_cost"],
                                            "unit_material_cost": cost_calc["unit_material_cost"],
                                            "unit_labor_cost": cost_calc["unit_labor_cost"],
                                            "unit_equipment_cost": cost_calc["unit_equipment_cost"],
                                            "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                            "costing_mode": cost_calc.get("costing_mode", "area"),
                                            "quantity": quantity,
                                            "total_cost": best_cost,
                                            "total_material_cost": cost_calc["total_material_cost"],
                                            "total_labor_cost": cost_calc["total_labor_cost"],
                                            "total_equipment_cost": cost_calc["total_equipment_cost"],
                                            "cost_component_source": cost_calc.get("component_source"),
                                        })
                                        break

                            if best_match:
                                break
                            if force_fallback_due_to_ambiguity:
                                break
                            if force_fallback_due_to_score:
                                break

                except Exception as e:
                    search_log.append({
                        "material": material_name,
                        "search_term": alt_term,
                        "catalog": catalog,
                        "status": "error",
                        "error": str(e),
                    })
            if force_fallback_due_to_score:
                break
            if force_fallback_due_to_ambiguity:
                break

        if best_match:
            match_type = "closest_match"
            chosen_source_type = "search"
            if explicit_id_used and matched_term and str(matched_term).startswith("rsmeans_id:"):
                match_type = "exact_id_match"
                chosen_source_type = "user_id"
            # Pull breakdown from the cost_calc dict captured at match time so
            # each material contributes its own bare material/labor/equipment
            # totals to the catalog-wide aggregate. Falls back to combined
            # totals when component data is unavailable (e.g. legacy results).
            calc = best_cost_calc or {}
            mat_cost = float(calc.get("total_material_cost", best_cost) or 0.0)
            lab_cost = float(calc.get("total_labor_cost", 0.0) or 0.0)
            eqp_cost = float(calc.get("total_equipment_cost", 0.0) or 0.0)
            material_result = {
                **material,
                "catalog": best_catalog,
                "search_term_used": matched_term,
                "unit_cost": calc.get(
                    "unit_cost",
                    best_match.get("localizedCosts", {}).get("totalOpCost", 0.0),
                ),
                "unit_material_cost": calc.get("unit_material_cost", 0.0),
                "unit_labor_cost": calc.get("unit_labor_cost", 0.0),
                "unit_equipment_cost": calc.get("unit_equipment_cost", 0.0),
                "total_cost": best_cost,
                "total_material_cost": mat_cost,
                "total_labor_cost": lab_cost,
                "total_equipment_cost": eqp_cost,
                "bare_material_unit_cost": calc.get("unit_bare_material_cost", 0.0),
                "bare_material_unit_basis": calc.get("line_uom") or calc.get("effective_unit", material.get("unit", "")),
                "bare_material_total_cost": calc.get("total_bare_material_cost", 0.0),
                "bare_total_unit_cost": calc.get("unit_bare_total_cost", 0.0),
                "bare_total_total_cost": calc.get("total_bare_total_cost", 0.0),
                "line_uom": calc.get("line_uom"),
                "cost_component_source": calc.get("component_source"),
                "rsmeans_id": best_match.get("id", ""),
                "rsmeans_description": best_match.get("description", ""),
                "match_type": match_type,
                "chosen_source_type": chosen_source_type,
                "unit_cost_basis": calc.get("effective_unit", material.get("unit", "")),
                "costing_mode": calc.get("costing_mode", "area"),
                "pricing_unit_cost_raw": _raw_unit_cost,
                "pricing_unit_uom_raw": _raw_uom,
                "pricing_unit_cost_effective": float(calc.get("unit_cost", 0.0) or 0.0),
                "pricing_unit_uom_effective": calc.get("effective_unit", material.get("unit", "")),
                "pricing_source": "rsmeans_direct" if float(calc.get("unit_cost", 0.0) or 0.0) > 0.0 else "unavailable",
            }
            all_results.append(material_result)
            _append_rsmeans_raw_log(material, best_match, best_catalog, match_type, matched_term)
            total_cost += best_cost
            total_material_cost_bare += mat_cost
            total_labor_cost_bare += lab_cost
            total_equipment_cost_bare += eqp_cost
        else:
            fallback_id = material_fallback_id
            if fallback_id and division_code and not _id_matches_division(fallback_id, division_code):
                search_log.append({
                    "material": material_name,
                    "status": "fallback_division_mismatch_rejected",
                    "fallback_costline_id": fallback_id,
                    "requested_division": division_code,
                })
                fallback_id = None
            if fallback_id:
                print(
                    f"  Fallback: Using default costline ID "
                    f"'{fallback_id}' for {material_name}"
                )
                try:
                    for catalog in catalogs:
                        cost_line = client.get_unit_costlines(
                            release_id=release_id,
                            catalog=catalog,
                            location_id=location_id,
                            labor_type=labor_type,
                            measurement_system=measurement_system,
                            division_code=fallback_id,
                        )
                        if cost_line and "items" in cost_line:
                            for item in cost_line["items"]:
                                if item.get("id") == fallback_id:
                                    fallback_line_uom = item.get("unitOfMeasure", "")
                                    components = _extract_unit_cost_components(item)
                                    cost_calc = _compute_total_costs_by_component(
                                        material,
                                        components,
                                        item.get("description", ""),
                                        line_uom=fallback_line_uom,
                                    )
                                    if cost_calc["total_cost"] > 0:
                                        material_result = {
                                            **material,
                                            "catalog": catalog,
                                            "search_term_used": f"fallback:{fallback_id}",
                                            "unit_cost": cost_calc["unit_cost"],
                                            "unit_material_cost": cost_calc["unit_material_cost"],
                                            "unit_labor_cost": cost_calc["unit_labor_cost"],
                                            "unit_equipment_cost": cost_calc["unit_equipment_cost"],
                                            "total_cost": cost_calc["total_cost"],
                                            "total_material_cost": cost_calc["total_material_cost"],
                                            "total_labor_cost": cost_calc["total_labor_cost"],
                                            "total_equipment_cost": cost_calc["total_equipment_cost"],
                                            "bare_material_unit_cost": cost_calc.get("unit_bare_material_cost", 0.0),
                                            "bare_material_unit_basis": cost_calc.get("line_uom") or cost_calc.get("effective_unit", ""),
                                            "bare_material_total_cost": cost_calc.get("total_bare_material_cost", 0.0),
                                            "bare_total_unit_cost": cost_calc.get("unit_bare_total_cost", 0.0),
                                            "bare_total_total_cost": cost_calc.get("total_bare_total_cost", 0.0),
                                            "line_uom": cost_calc.get("line_uom"),
                                            "cost_component_source": cost_calc.get("component_source"),
                                            "rsmeans_id": item.get("id", ""),
                                            "rsmeans_description": item.get("description", ""),
                                            "match_type": "fallback_id",
                                            "chosen_source_type": "fallback",
                                            "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                            "costing_mode": cost_calc.get("costing_mode", "area"),
                                        }
                                        all_results.append(material_result)
                                        _append_rsmeans_raw_log(material, item, catalog, "fallback_id", f"fallback:{fallback_id}")
                                        total_cost += cost_calc["total_cost"]
                                        total_material_cost_bare += cost_calc["total_material_cost"]
                                        total_labor_cost_bare += cost_calc["total_labor_cost"]
                                        total_equipment_cost_bare += cost_calc["total_equipment_cost"]
                                        search_log.append({
                                            "material": material_name,
                                            "status": "fallback_id_used",
                                            "fallback_costline_id": fallback_id,
                                            "catalog": catalog,
                                            "rsmeans_id": item.get("id", ""),
                                            "unit_cost": cost_calc["unit_cost"],
                                            "unit_material_cost": cost_calc["unit_material_cost"],
                                            "unit_labor_cost": cost_calc["unit_labor_cost"],
                                            "unit_equipment_cost": cost_calc["unit_equipment_cost"],
                                            "total_cost": cost_calc["total_cost"],
                                            "total_material_cost": cost_calc["total_material_cost"],
                                            "total_labor_cost": cost_calc["total_labor_cost"],
                                            "total_equipment_cost": cost_calc["total_equipment_cost"],
                                            "cost_component_source": cost_calc.get("component_source"),
                                        })
                                        best_match = item
                                        break
                            if best_match:
                                break
                except Exception as e:
                    print(f"  Fallback error: {e}")

            if not best_match:
                errors.append(f"No RSMeans match found in any catalog for: {material_name}")
                search_log.append({
                    "material": material_name,
                    "status": "no_match",
                    "catalogs_searched": catalogs,
                    "alternatives_tried": len(search_alternatives),
                    "fallback_available": fallback_id is not None,
                })

    return {
        "total_cost": total_cost,
        "total_material_cost": total_material_cost_bare,
        "total_labor_cost": total_labor_cost_bare,
        "total_equipment_cost": total_equipment_cost_bare,
        "materials": all_results,
        "errors": errors,
        "search_log": search_log,
        "catalogs_searched": catalogs,
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
    fallback_costline_ids: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    load_dotenv()
    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")

    if not client_id or not client_secret:
        append_measure_summary_record(MEASURE_LOG_SLUG, {
            "status": "auth_error",
            "message": "RSMeans API credentials not found in environment",
        })
        return {
            "status": "auth_error",
            "message": "RSMeans API credentials not found in environment",
        }

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=use_sandbox)
    if not client.authenticate():
        append_measure_summary_record(MEASURE_LOG_SLUG, {
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
        fallback_costline_ids=fallback_costline_ids,
    )

    # Totals from the per-line breakdown. The per-line unit cost is the
    # RSMeans ``totalOpCost`` (Total Incl. O&P) so no extra markup is layered.
    total_material_cost = float(results.get("total_material_cost", 0.0))
    total_labor_cost = float(results.get("total_labor_cost", 0.0))
    total_equipment_cost = float(results.get("total_equipment_cost", 0.0))
    total_bare_cost = total_material_cost + total_labor_cost + total_equipment_cost
    if total_bare_cost <= 0.0:
        # Fallback for legacy/edge results where component breakdown was
        # unavailable; the aggregated ``total_cost`` is already the line-level
        # ``totalOpCost`` summed across materials.
        total_bare_cost = float(results.get("total_cost", 0.0))
        total_material_cost = total_bare_cost
    # ``overhead_profit_percent`` is retained in the summary for traceability
    # but does not alter the total (the per-line cost already includes O&P).
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

    append_measure_summary_record(MEASURE_LOG_SLUG, {
        "status": "ok",
        "summary": summary,
        "results": results,
    })

    return {
        "status": "ok",
        "summary": summary,
        "results": results,
    }


if __name__ == "__main__":
    raise SystemExit(main())

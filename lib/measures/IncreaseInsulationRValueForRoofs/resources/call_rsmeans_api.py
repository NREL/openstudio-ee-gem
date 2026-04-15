#!/usr/bin/env python
"""
Standalone RSMeans API helper for IncreaseInsulationRValueForRoofs.

This helper is intentionally local to the roof measure so RSMeans lookup
behavior does not depend on other measure directories.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


DEFAULT_FEATURE_KEYS = {
    "name": "retrofit_material_name",
    "description": "retrofit_material_description",
    "quantity": "retrofit_material_quantity",
    "unit": "retrofit_material_unit",
    "division_code": "rsmeans_division_code",
    "unit_cost": "rsmeans_unit_cost",
    "total_cost": "rsmeans_total_cost",
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
    filtered = []
    for item in items:
        description = str(item.get("description", "")).lower()
        if "demolition" in description or "demo" in description:
            continue
        filtered.append(item)
    return filtered or items


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


def _compute_total_cost_for_material(
    material: Dict[str, Any],
    unit_cost: float,
    matched_description: str,
) -> Dict[str, Any]:
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

    line_thickness_ft = _extract_thickness_ft_from_description(matched_description)
    if line_thickness_ft is None:
        line_thickness_ft = material.get("rsmeans_thickness_ft")
    try:
        line_thickness_ft = float(line_thickness_ft)
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


def _score_rsmeans_candidate(
    material_name: str,
    item: Dict[str, Any],
) -> tuple:
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
    clamped_score = max(0.0, min(100.0, score))
    return score, clamped_score


def _resolve_fallback_costline_id(
    material_name: str,
    fallback_costline_ids: Dict[str, str],
) -> Optional[str]:
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

    total_material_cost = float(results.get("total_cost", 0.0))
    overhead_profit_cost = total_material_cost * (args.overhead_profit_percent / 100.0)
    total_cost = total_material_cost + overhead_profit_cost

    summary = {
        "total_material_cost": total_material_cost,
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
        best_catalog = None
        matched_term = None
        force_fallback_due_to_score = False

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
                                cost_calc = _compute_total_cost_for_material(
                                    material,
                                    unit_cost,
                                    item.get("description", ""),
                                )
                                if cost_calc["total_cost"] > 0:
                                    best_match = item
                                    best_cost = cost_calc["total_cost"]
                                    best_catalog = catalog
                                    matched_term = f"rsmeans_id:{specified_id}"
                                    search_log.append({
                                        "material": material_name,
                                        "search_term": specified_id,
                                        "catalog": catalog,
                                        "division": division_code,
                                        "status": "exact_id_match",
                                        "unit_cost": cost_calc["unit_cost"],
                                        "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                        "costing_mode": cost_calc.get("costing_mode", "area"),
                                        "quantity": quantity,
                                        "total_cost": best_cost,
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
                                    unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                    cost_calc = _compute_total_cost_for_material(
                                        material,
                                        unit_cost,
                                        match.get("description", ""),
                                    )

                                    if cost_calc["total_cost"] > 0:
                                        top_raw_score = candidate_details[0].get("raw_score", 0.0)
                                        if top_raw_score < 0.0 and material_fallback_id:
                                            force_fallback_due_to_score = True
                                            search_log.append({
                                                "material": material_name,
                                                "search_term": alt_term,
                                                "catalog": catalog,
                                                "status": "poor_match_raw_score_fallback",
                                                "raw_score": top_raw_score,
                                                "fallback_costline_id": material_fallback_id,
                                                "candidates_considered": len(items),
                                                "candidate_scores": candidate_details,
                                            })
                                            break

                                        best_match = item
                                        best_catalog = catalog
                                        matched_term = alt_term
                                        best_cost = cost_calc["total_cost"]

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
                                            "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                            "costing_mode": cost_calc.get("costing_mode", "area"),
                                            "quantity": quantity,
                                            "total_cost": best_cost,
                                        })
                                        break

                            if best_match:
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

        if best_match:
            match_type = "closest_match"
            if matched_term and str(matched_term).startswith("rsmeans_id:"):
                match_type = "exact_id_match"
            material_result = {
                **material,
                "catalog": best_catalog,
                "search_term_used": matched_term,
                "unit_cost": next((
                    log_entry.get("unit_cost")
                    for log_entry in reversed(search_log)
                    if log_entry.get("material") == material_name
                    and log_entry.get("total_cost") == best_cost
                ), best_match.get("localizedCosts", {}).get("totalOpCost", 0.0)),
                "total_cost": best_cost,
                "rsmeans_id": best_match.get("id", ""),
                "rsmeans_description": best_match.get("description", ""),
                "match_type": match_type,
                "unit_cost_basis": next((
                    log_entry.get("unit_cost_basis")
                    for log_entry in reversed(search_log)
                    if log_entry.get("material") == material_name
                    and log_entry.get("total_cost") == best_cost
                ), material.get("unit", "")),
                "costing_mode": next((
                    log_entry.get("costing_mode")
                    for log_entry in reversed(search_log)
                    if log_entry.get("material") == material_name
                    and log_entry.get("total_cost") == best_cost
                ), "area"),
            }
            all_results.append(material_result)
            total_cost += best_cost
        else:
            fallback_id = material_fallback_id
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
                                    unit_cost = item.get("localizedCosts", {}).get("totalOpCost", 0.0)
                                    cost_calc = _compute_total_cost_for_material(
                                        material,
                                        unit_cost,
                                        item.get("description", ""),
                                    )
                                    if cost_calc["total_cost"] > 0:
                                        material_result = {
                                            **material,
                                            "catalog": catalog,
                                            "search_term_used": f"fallback:{fallback_id}",
                                            "unit_cost": cost_calc["unit_cost"],
                                            "total_cost": cost_calc["total_cost"],
                                            "rsmeans_id": item.get("id", ""),
                                            "rsmeans_description": item.get("description", ""),
                                            "match_type": "fallback_id",
                                            "unit_cost_basis": cost_calc.get("effective_unit", ""),
                                            "costing_mode": cost_calc.get("costing_mode", "area"),
                                        }
                                        all_results.append(material_result)
                                        total_cost += cost_calc["total_cost"]
                                        search_log.append({
                                            "material": material_name,
                                            "status": "fallback_id_used",
                                            "fallback_costline_id": fallback_id,
                                            "catalog": catalog,
                                            "rsmeans_id": item.get("id", ""),
                                            "unit_cost": cost_calc["unit_cost"],
                                            "total_cost": cost_calc["total_cost"],
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
        fallback_costline_ids=fallback_costline_ids,
    )

    total_material_cost = float(results.get("total_cost", 0.0))
    overhead_profit_cost = total_material_cost * (overhead_profit_percent / 100.0)
    total_cost = total_material_cost + overhead_profit_cost

    summary = {
        "total_material_cost": total_material_cost,
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

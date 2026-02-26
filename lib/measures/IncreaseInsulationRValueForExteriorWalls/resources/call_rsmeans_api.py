#!/usr/bin/env python
"""
Modular RSMeans API helper for OpenStudio measures.

This script is designed to live in a measure's resources folder and can be
reused by other measures. It expects an OpenStudio model (.osm) with
AdditionalProperties describing retrofit materials and quantities. It can:

  - Extract materials from AdditionalProperties
  - Query RSMeans for unit costs
  - Return costs without modifying the model

Required AdditionalProperties keys (defaults):
  - retrofit_material_name
  - retrofit_material_quantity
  - retrofit_material_unit
Optional keys:
  - retrofit_material_description
  - rsmeans_division_code
  - rsmeans_unit_cost
  - rsmeans_total_cost
"""

import argparse
import json
import os
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
    """
    Read one AdditionalProperties feature and return it as a string.
    """
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
    """
    Read one AdditionalProperties feature and return it as a float.
    """
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


def get_division_from_material_type(material_type: str) -> Optional[str]:
    """
    Infer a CSI division code from a material name/type string.

    """
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
        """Initialize API credentials, auth endpoint, and base URL selection."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://login.gordian.com/connect/token"
        self.base_url = "https://dataapi-sb.gordian.com" if use_sandbox else "https://dataapi.gordian.com"
        self.access_token = None
        self.token_type = None

    def authenticate(self) -> bool:
        """
        Request an OAuth client-credentials token from Gordian.

        """
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
        """Build authenticated request headers for RSMeans API calls."""
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
        """
        Search RSMeans unit cost lines by **material search term**.

        This is the first-stage lookup used to identify candidate items and IDs.
        Optionally narrows results by CSI division code.
        """
        catalog_id = f"{catalog}-{measurement_system}-{labor_type}-{release_id}-{location_id}"
        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines/_search"
        params = {"searchTerm": search_term} if search_term else {}
        if division_code:
            params["divisionCode"] = division_code
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print(
                f"Search: catalog={catalog_id}, division={division_code}, term={search_term}"
            )
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
        """
        Retrieve cost lines for a division from a **specific catalog context**.

        This is the second-stage call used after search to read localized costs.
        """
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
        """
        Resolve costs for a list of materials and aggregate batch totals.

        For each material:
        - Optionally reuse existing costs from AdditionalProperties.
        - Infer division code when missing.
        - Search RSMeans, fetch cost lines, and compute total_cost = unit_cost * quantity.

        Returns:
            Dict with total_cost, per-material results, errors, and search_log.
        """
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

            if not division_hint:
                division_hint = get_division_from_material_type(material_name)
                if division_hint:
                    print(f"Auto-detected division {division_hint} for material: {material_name}")

            try:
                search_results = self.search_unit_costlines(
                    release_id=release_id,
                    measurement_system=measurement_system,
                    search_term=material_name,
                    catalog=catalog,
                    location_id=location_id,
                    labor_type=labor_type,
                    division_code=division_hint,
                )

                if not search_results or "items" not in search_results or len(search_results["items"]) == 0:
                    results["errors"].append(f"No RSMeans match found for: {material_name}")
                    continue

                first_item = search_results["items"][0]
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
                    "search_results_count": len(search_results.get("items", [])),
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
    """
    Load an OpenStudio model from disk using VersionTranslator.

    Raises RuntimeError when OpenStudio bindings are unavailable or loading fails.
    """
    try:
        import openstudio  # pylint: disable=import-error
    except Exception as exc:
        raise RuntimeError("openstudio python bindings are required to read a model") from exc

    translator = openstudio.osversion.VersionTranslator()
    model_opt = translator.loadModel(openstudio.toPath(str(model_path)))
    if not model_opt.is_initialized():
        raise RuntimeError(f"Failed to load model: {model_path}")
    return model_opt.get()


def extract_materials_from_model(model, feature_keys: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Extract retrofit material records from AdditionalProperties across model objects.

    Expected keys are configurable via feature_keys. Missing quantity defaults to 1.0.
    Also captures object handle/name to help trace where each record came from.
    """
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
            "division_code": division_code, # how we distinguish cellulose or fiberglass insulation when searching RSMeans?
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


def parse_args() -> argparse.Namespace:
    """Define and parse CLI arguments for the RSMeans helper script."""
    parser = argparse.ArgumentParser(description="RSMeans API helper for OpenStudio measures")
    parser.add_argument("--model", required=True, help="Path to OpenStudio model (.osm)")
    parser.add_argument("--output", help="Path to save JSON results")
    parser.add_argument("--release", default="2025-q4", help="RSMeans release ID (e.g., 2025-q4)")
    parser.add_argument("--catalog", default="gb-mf", help="Catalog code (e.g., gb-mf, bc-mf)")
    parser.add_argument("--location", default="us-us-national", help="Location ID (e.g., us-us-national)")
    parser.add_argument("--labor-type", default="std", help="Labor type (std, opn, fmr, fed, he)")
    parser.add_argument("--measurement-system", default="imp", help="Measurement system (imp, met)")
    parser.add_argument("--use-sandbox", action="store_true", help="Use RSMeans sandbox API")
    parser.add_argument("--skip-if-cost-present", action="store_true", help="Skip API if cost exists")
    return parser.parse_args()


def main() -> int:
    """
    CLI entrypoint: load env, read model materials, query RSMeans, and print summary.

    Exit codes:
        0 on success, 1 on credential/input/API precondition failures.
    """
    args = parse_args()
    load_dotenv()

    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")

    if not client_id or not client_secret:
        print("RSMeans API credentials (client_id, client_secret) not found in environment.")
        return 1

    model_path = Path(args.model).resolve()
    if not model_path.exists():
        print(f"Model file not found: {model_path}")
        return 1

    model = load_openstudio_model(model_path)
    materials = extract_materials_from_model(model, DEFAULT_FEATURE_KEYS)

    if not materials:
        print("No retrofit materials found in AdditionalProperties.")
        return 1

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=args.use_sandbox)
    if not client.authenticate():
        return 1

    results = client.search_materials_batch(
        materials=materials,
        release_id=args.release,
        catalog=args.catalog,
        location_id=args.location,
        labor_type=args.labor_type,
        measurement_system=args.measurement_system,
        save_search_results_path=args.output,
        skip_if_cost_present=args.skip_if_cost_present,
    )

    print(f"Total cost: ${results.get('total_cost', 0.0):.2f}")
    if results.get("errors"):
        print("Errors encountered:")
        for error in results["errors"]:
            print(f"  - {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

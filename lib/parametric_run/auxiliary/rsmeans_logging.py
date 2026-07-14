import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


RSMEANS_RAW_LOG_ENV = "RSMEANS_SCENARIO_RAW_LOG_PATH"


def _read_env_path() -> Optional[Path]:
    raw_path = os.environ.get(RSMEANS_RAW_LOG_ENV)
    if not raw_path:
        return None
    try:
        return Path(raw_path)
    except Exception:
        return None


def resolve_measure_log_path(measure_slug: str, scenario_raw_log_path: Optional[str] = None) -> Optional[Path]:
    raw_path = Path(scenario_raw_log_path) if scenario_raw_log_path else _read_env_path()
    if raw_path is None:
        return None

    scenario_dir = raw_path.parent
    run_dir = scenario_dir.parent
    api_log_dir = run_dir / "api_logs"
    return api_log_dir / f"{scenario_dir.name}__{measure_slug}.jsonl"


def append_jsonl_record(log_path: Optional[Path], record: Dict[str, Any]) -> None:
    if not log_path:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n\n")
    except Exception:
        return


def build_raw_rsmeans_record(material: Dict[str, Any], matched_item: Dict[str, Any], catalog: str, match_type: str, search_term: str) -> Dict[str, Any]:
    localized = matched_item.get("localizedCosts") or {}
    return {
        "record_type": "material_match",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "material_name": material.get("name"),
        "material_description": material.get("description"),
        "material_quantity": material.get("quantity"),
        "material_unit": material.get("unit"),
        "catalog": catalog,
        "match_type": match_type,
        "search_term_used": search_term,
        "rsmeans_id": matched_item.get("id"),
        "rsmeans_description": matched_item.get("description"),
        "rsmeans_unit_of_measure": matched_item.get("unitOfMeasure"),
        "localizedCosts": {
            "materialCost": localized.get("materialCost"),
            "laborCost": localized.get("laborCost"),
            "equipmentCost": localized.get("equipmentCost"),
            "totalCost": localized.get("totalCost"),
            "materialOpCost": localized.get("materialOpCost"),
            "laborOpCost": localized.get("laborOpCost"),
            "equipmentOpCost": localized.get("equipmentOpCost"),
            "totalOpCost": localized.get("totalOpCost"),
        },
    }


def append_measure_raw_record(measure_slug: str, material: Dict[str, Any], matched_item: Dict[str, Any], catalog: str, match_type: str, search_term: str) -> None:
    log_path = resolve_measure_log_path(measure_slug)
    append_jsonl_record(log_path, build_raw_rsmeans_record(material, matched_item, catalog, match_type, search_term))


def append_measure_summary_record(measure_slug: str, payload: Dict[str, Any]) -> None:
    log_path = resolve_measure_log_path(measure_slug)
    record = {
        "record_type": "lookup_summary",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "measure_slug": measure_slug,
        "log_path": str(log_path) if log_path else None,
        **payload,
    }
    append_jsonl_record(log_path, record)

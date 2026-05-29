import csv
import html
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
TEST_A = ROOT / "lib" / "parametric_run" / "simulations" / "run_test_017_custom_rsmeans"
TEST_B = ROOT / "lib" / "parametric_run" / "simulations" / "run_test_018_rsmeans_api"
OUT_CSV = ROOT / "lib" / "parametric_run" / "018api_017custom_material_effective_cost_comparison_table.csv"

SCENARIOS = ["scenario_1", "scenario_2", "scenario_3"]
FT_PER_M = 3.280839895013123
FT2_PER_M2 = 10.7639104167097


def strip_token(line: str) -> str:
    token = line.split("!-")[0].rstrip().rstrip(",;").strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    return html.unescape(token)


def extract_additional_properties(osm_path: Path) -> Dict[str, str]:
    lines = osm_path.read_text(encoding="utf-8").splitlines()
    result: Dict[str, str] = {}

    i = 0
    while i < len(lines):
        line = lines[i]
        if "!- Feature Name" not in line:
            i += 1
            continue

        feature_name = strip_token(line)

        # Find the next Feature Value line after this Feature Name line.
        j = i + 1
        feature_value = ""
        while j < len(lines):
            if "!- Feature Name" in lines[j]:
                break
            if "!- Feature Value" in lines[j]:
                feature_value = strip_token(lines[j])
                break
            j += 1

        if feature_name:
            result[feature_name] = feature_value.strip()

        i += 1

    return result


def choose_numeric(primary: str, fallback: str = "") -> str:
    p = (primary or "").strip()
    if p and p.upper() != "N/A":
        return p
    f = (fallback or "").strip()
    if f and f.upper() != "N/A":
        return f
    return "N/A"


def primary_numeric_or_na(primary: str) -> str:
    p = (primary or "").strip()
    if p and p.upper() != "N/A":
        return p
    return "N/A"


def choose_text(*candidates: str) -> str:
    for c in candidates:
        v = (c or "").strip()
        if v and v.upper() != "N/A":
            return v
    return "N/A"


def is_custom_mode(props: Dict[str, str], key: str) -> bool:
    v = (props.get(key, "") or "").strip().lower()
    return "custom" in v


def is_none_option(props: Dict[str, str], *keys: str) -> bool:
    for key in keys:
        raw = (props.get(key, "") or "").strip().lower()
        if raw:
            return raw == "none"
    return False


def lf_to_m_cost(value_per_lf: str) -> str:
    v = (value_per_lf or "").strip()
    if not v or v.upper() == "N/A":
        return "N/A"
    try:
        return str(float(v) * FT_PER_M)
    except ValueError:
        return "N/A"


def m_to_lf_cost(value_per_m: str) -> str:
    v = (value_per_m or "").strip()
    if not v or v.upper() == "N/A":
        return "N/A"
    try:
        return str(float(v) / FT_PER_M)
    except ValueError:
        return "N/A"


def m2_to_ft2_cost(value_per_m2: str) -> str:
    v = (value_per_m2 or "").strip()
    if not v or v.upper() == "N/A":
        return "N/A"
    try:
        return str(float(v) / FT2_PER_M2)
    except ValueError:
        return "N/A"


def build_component_rows(props: Dict[str, str]) -> List[Tuple[str, str, str, str, str]]:
    wall_custom_mode = is_custom_mode(props, "wall_insulation_cost_source")
    roof_custom_mode = is_custom_mode(props, "roof_insulation_cost_source")
    door_custom_mode = is_custom_mode(props, "door_enhancement_cost_source")
    window_custom_mode = is_custom_mode(props, "window_enhancement_cost_factor_basis")
    door_option_none = is_none_option(props, "door_option")
    door_bottom_none = is_none_option(props, "door_bottom_seal_option")
    door_top_none = is_none_option(props, "door_top_side_seal_option")
    wall_none = is_none_option(props, "wall_insulation_material_type")
    roof_none = is_none_option(props, "roof_insulation_material_type")
    window_glass_none = is_none_option(props, "window_glass_option", "glass_option")
    window_frame_none = is_none_option(props, "window_frame_option", "wf_option")
    window_caulking_none = is_none_option(props, "window_caulking_option", "caulking_option")
    window_film_none = is_none_option(props, "window_film_option", "film_option")
    window_weather_none = is_none_option(props, "window_weatherstrip_option", "weatherstrip_option")

    rsmeans_door_area = props.get("door_enhancement_rsmeans_door_cost_per_area", "")
    custom_door_area = choose_numeric(
        props.get("door_enhancement_custom_door_cost_per_area", ""),
        props.get("custom_door_cost_per_ft2", ""),
    )
    door_val = choose_numeric(rsmeans_door_area, custom_door_area)
    if door_custom_mode:
        door_val = choose_numeric(custom_door_area, rsmeans_door_area)
    else:
        door_val = m2_to_ft2_cost(door_val)
    door_desc = choose_text(props.get("rsmeans_unit_cost_description", ""))
    if (props.get("door_enhancement_rsmeans_door_cost_per_area", "") or "").strip().upper() in ("", "N/A"):
        door_desc = choose_text(props.get("door_option", ""), door_desc)
    if door_option_none:
        door_val = "N/A"
        door_desc = "none"

    bottom_val = choose_numeric(
        props.get("door_enhancement_rsmeans_bottom_seal_cost_per_m", ""),
        props.get("door_enhancement_custom_bottom_seal_cost_per_m", ""),
    )
    if door_custom_mode:
        bottom_val = choose_numeric(
            props.get("door_enhancement_custom_bottom_seal_cost_per_lf", ""),
            bottom_val,
        )
    else:
        bottom_val = m_to_lf_cost(bottom_val)
    bottom_desc = choose_text(props.get("door_bottom_seal_rsmeans_description", ""), props.get("door_bottom_seal_option", ""))
    if door_bottom_none:
        bottom_val = "N/A"
        bottom_desc = "none"

    top_val = choose_numeric(
        props.get("door_enhancement_rsmeans_top_side_seal_cost_per_m", ""),
        props.get("door_enhancement_custom_top_side_seal_cost_per_m", ""),
    )
    if door_custom_mode:
        top_val = choose_numeric(
            props.get("door_enhancement_custom_top_side_seal_cost_per_lf", ""),
            top_val,
        )
    else:
        top_val = m_to_lf_cost(top_val)
    top_desc = choose_text(props.get("door_top_side_seal_rsmeans_description", ""), props.get("door_top_side_seal_option", ""))
    if door_top_none:
        top_val = "N/A"
        top_desc = "none"

    wall_val = choose_numeric(
        props.get("wall_insulation_material_rsmeans_cost_per_cf", ""),
        props.get("wall_insulation_custom_cost_per_cf", ""),
    )
    if wall_custom_mode:
        wall_val = choose_numeric(
            props.get("wall_insulation_custom_cost_per_cf", ""),
            props.get("wall_insulation_material_rsmeans_cost_per_cf", ""),
        )
    wall_desc = choose_text(props.get("wall_insulation_material_rsmeans_description", ""), props.get("wall_insulation_material_type", ""))
    if wall_none:
        wall_val = "N/A"
        wall_desc = "none"

    roof_val = choose_numeric(
        props.get("roof_insulation_material_rsmeans_cost_per_cf", ""),
        props.get("roof_insulation_custom_cost_per_cf", ""),
    )
    if roof_custom_mode:
        roof_val = choose_numeric(
            props.get("roof_insulation_custom_cost_per_cf", ""),
            props.get("roof_insulation_material_rsmeans_cost_per_cf", ""),
        )
    roof_desc = choose_text(props.get("roof_insulation_material_rsmeans_description", ""), props.get("roof_insulation_material_type", ""))
    if roof_none:
        roof_val = "N/A"
        roof_desc = "none"

    glass_val = primary_numeric_or_na(props.get("window_enhancement_glass_cost_per_cf", ""))
    if window_custom_mode:
        glass_val = choose_numeric(
            props.get("window_custom_glass_cost_per_cf", ""),
            props.get("window_enhancement_glass_cost_per_cf", ""),
        )
    glass_desc = choose_text(props.get("window_glass_option", ""))
    if window_glass_none:
        glass_val = "N/A"
        glass_desc = "none"

    frame_val = primary_numeric_or_na(props.get("window_enhancement_frame_cost_per_sf", ""))
    if window_custom_mode:
        frame_val = choose_numeric(
            props.get("window_custom_frame_cost_per_sf", ""),
            props.get("window_enhancement_frame_cost_per_sf", ""),
        )
    frame_desc = choose_text(props.get("window_frame_rsmeans_description", ""), props.get("window_frame_option", ""))
    if window_frame_none:
        frame_val = "N/A"
        frame_desc = "none"

    caulking_val = primary_numeric_or_na(props.get("window_enhancement_caulking_cost_per_cy", ""))
    if window_custom_mode:
        caulking_val = choose_numeric(
            props.get("window_custom_caulking_cost_per_cy", ""),
            props.get("window_enhancement_caulking_cost_per_cy", ""),
        )
    caulking_desc = choose_text(props.get("window_caulking_rsmeans_description", ""), props.get("window_caulking_option", ""))
    if window_caulking_none:
        caulking_val = "N/A"
        caulking_desc = "none"

    film_val = primary_numeric_or_na(props.get("window_enhancement_film_cost_per_sf", ""))
    if window_custom_mode:
        film_val = choose_numeric(
            props.get("window_custom_film_cost_per_sf", ""),
            props.get("window_enhancement_film_cost_per_sf", ""),
        )
    film_desc = choose_text(props.get("window_film_rsmeans_description", ""), props.get("window_film_option", ""))
    if window_film_none:
        film_val = "N/A"
        film_desc = "none"

    weather_val = primary_numeric_or_na(props.get("window_enhancement_weatherstrip_cost_per_lf", ""))
    if window_custom_mode:
        weather_val = choose_numeric(
            props.get("window_custom_weatherstrip_cost_per_lf", ""),
            props.get("window_enhancement_weatherstrip_cost_per_lf", ""),
        )
    weather_desc = choose_text(props.get("window_weatherstrip_option", ""))
    if window_weather_none:
        weather_val = "N/A"
        weather_desc = "none"

    return [
        ("door_enhancement", "door", "$/ft2", door_val, door_desc),
        ("door_enhancement", "bottom_seal", "$/LF", bottom_val, bottom_desc),
        ("door_enhancement", "top_side_seal", "$/LF", top_val, top_desc),
        ("wall_insulation", "material", "$/CF", wall_val, wall_desc),
        ("roof_insulation", "material", "$/CF", roof_val, roof_desc),
        ("window_enhancement", "glass", "$/CF", glass_val, glass_desc),
        ("window_enhancement", "frame", "$/SF", frame_val, frame_desc),
        ("window_enhancement", "caulking", "$/CY", caulking_val, caulking_desc),
        ("window_enhancement", "film", "$/SF", film_val, film_desc),
        ("window_enhancement", "weatherstrip", "$/LF", weather_val, weather_desc),
    ]


def main() -> None:
    header = [
        "scenario",
        "measure",
        "component",
        "unit",
        "test_017_custom_rsmeans_material_cost_per_unit",
        "test_017_custom_rsmeans_material_description",
        "test_018_rsmeans_api_material_cost_per_unit",
        "test_018_rsmeans_api_material_description",
    ]

    out_rows: List[List[str]] = []

    for sc in SCENARIOS:
        osm_a = TEST_A / f"{sc}_SmallOffice_Buffalo" / "model_to_run.osm"
        osm_b = TEST_B / f"{sc}_SmallOffice_Buffalo" / "model_to_run.osm"

        props_a = extract_additional_properties(osm_a)
        props_b = extract_additional_properties(osm_b)

        rows_a = build_component_rows(props_a)
        rows_b = build_component_rows(props_b)

        for ra, rb in zip(rows_a, rows_b):
            measure, component, unit, a_val, a_desc = ra
            _, _, _, b_val, b_desc = rb
            out_rows.append([
                sc,
                measure,
                component,
                unit,
                a_val,
                a_desc,
                b_val,
                b_desc,
            ])

        out_rows.append(["", "", "", "", "", "", "", ""])

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out_rows)

    print(f"Wrote: {OUT_CSV}")


if __name__ == "__main__":
    main()

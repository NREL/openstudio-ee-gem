from pathlib import Path
import sys, argparse, os, configparser
import openstudio
from measure import IncreaseInsulationRValueForRoofs

def find_model_path(default_dir: Path) -> Path | None:
    candidate = default_dir / "tests/example_model.osm"
    if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    for alt in [
        default_dir / "tests/model.osm",
        default_dir / "example_model.osm",
        default_dir.parent / "tests/example_model.osm",
        default_dir.parent / "example_model.osm",
    ]:
        if alt.exists() and alt.is_file() and alt.stat().st_size > 0:
            return alt
    try:
        for p in default_dir.rglob("*.osm"):
            if p.is_file() and p.stat().st_size > 0:
                return p
    except Exception:
        pass
    return None

def list_dir_sample(dirpath: Path, label: str):
    if not dirpath.exists():
        return
    print(f"\n[{label}] {dirpath}")
    for p in sorted(dirpath.iterdir()):
        kind = "DIR " if p.is_dir() else "FILE"
        print(f" - {kind:<4} {p.name}")

def load_model_or_new(model_path: Path | None) -> openstudio.model.Model:
    if model_path is None:
        print("No .osm found — creating a new empty Model so the measure can run.")
        return openstudio.model.Model()
    print(f"Attempting to load model: {model_path}")
    vt = openstudio.osversion.VersionTranslator()
    opt = vt.loadModel(openstudio.toPath(str(model_path)))
    if opt.is_initialized():
        return opt.get()
    opt2 = openstudio.model.Model.load(openstudio.toPath(str(model_path)))
    if opt2.is_initialized():
        return opt2.get()
    print(f"Failed to load OSM at {model_path}. Creating a blank model instead.")
    return openstudio.model.Model()

def get_api_key(cur_dir: Path) -> str:
    api_key = os.getenv("EC3_API_TOKEN", "").strip()
    if api_key:
        return api_key
    for cfg in [cur_dir / "config.ini", cur_dir.parent / "config.ini"]:
        if cfg.exists():
            cp = configparser.ConfigParser()
            cp.read(cfg)
            try:
                return cp["EC3_API_TOKEN"]["API_TOKEN"].strip()
            except Exception:
                pass
    return "Obtain the key from EC3 website"

def run_measure():
    CURRENT_DIR = Path(__file__).parent.resolve()
    list_dir_sample(CURRENT_DIR, "Current dir")
    list_dir_sample(CURRENT_DIR / "tests", "tests dir (if exists)")

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="", help="Path to an OSM file to load")
    args = parser.parse_args()

    model_path = Path(args.model).resolve() if args.model else find_model_path(CURRENT_DIR)
    if model_path is None or not model_path.exists():
        print("WARNING: Could not locate an example .osm; continuing with a new empty model.")
    else:
        print(f"Using model: {model_path}")

    model = load_model_or_new(model_path)
    osw = openstudio.WorkflowJSON()
    runner = openstudio.measure.OSRunner(osw)
    measure = IncreaseInsulationRValueForRoofs()

    args_vec = measure.arguments(model)
    arg_map = openstudio.measure.convertOSArgumentVectorToMap(args_vec)

    def set_arg(name, value):
        if name in arg_map:
            a = arg_map[name]
            a.setValue(value)
            arg_map[name] = a
        else:
            print(f"Argument '{name}' not found in this measure.")

    # --- Print arguments cleanly ---
    print("\n== Measure Arguments ==")
    for i in range(args_vec.size()):
        a = args_vec[i]
        req = "yes" if a.required() else "no"
        try:
            default_str = a.defaultValueAsString() if a.hasDefaultValue() else ""
        except Exception:
            default_str = ""
        print(f"  - {a.name()} (required={req}, default={default_str})")

    # --- Set arguments ---
    set_arg("r_value", 60.0)
    set_arg("allow_reduction", True)
    set_arg("material_cost_increase_ip", 0.0)
    set_arg("one_time_retrofit_cost_ip", 0.0)
    set_arg("years_until_retrofit_cost", 0)

    set_arg("analysis_period", 30)
    set_arg("gwp_statistic", "median")
    set_arg("api_key", get_api_key(CURRENT_DIR))
    set_arg("insulation_material_type", "Polyiso (ISO)")
    set_arg("insulation_material_lifetime", 30)
    set_arg("insulation_thermal_conductivity", 0.0)
    set_arg("insulation_material_density", 0.0)

    result_ok = measure.run(model, runner, arg_map)
    result = runner.result()

    print("\n== RESULT =", result.value().valueName(), "==")
    for info in result.info():
        print("INFO   :", info.logMessage())
    for warn in result.warnings():
        print("WARNING:", warn.logMessage())
    for err in result.errors():
        print("ERROR  :", err.logMessage())

    out_dir = CURRENT_DIR / "tests" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / "example_model_roof_rvalue_upgrade.osm"

    ok = model.save(openstudio.toPath(str(save_path)), True)
    if not ok:
        raise RuntimeError(f"Failed to save model to {save_path}")
    print(f"\nSaved: {save_path}")

if __name__ == "__main__":
    run_measure()
